import os
import sys
import argparse
import asyncio
import backoff
from collections import ChainMap
from contextlib import contextmanager
import logging
import time
from typing import (
    AbstractSet,
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Tuple,
)

import aiohttp
import snug
import quiz

from fpr.rx_util import on_next_save_to_jsonl
from fpr.serialize_util import iter_jsonlines
from fpr.quiz_util import raw_result_to_dict
from fpr.models.pipeline import Pipeline
from fpr.models.org_repo import OrgRepo
from fpr.models.github import (
    ResourceKind,
    Request,
    Response,
    RequestResponseExchange,
    get_next_requests,
    MISSING,
)
from fpr.models.rust import cargo_metadata_to_rust_crates
from fpr.models.pipeline import add_infile_and_outfile, add_aiohttp_args
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.github_metadata")

__doc__ = """Given an input file with repo urls metadata output fetches
dependency and vulnerability metadata from GitHub and an optional GitHub PAT
and outputs them to jsonl and optionally saves them to a local SQLite3 DB.
"""


def is_not_found_exception(err: Exception) -> bool:
    is_quiz_not_found_err_response = (
        isinstance(err, quiz.ErrorResponse)
        and len(err.errors)
        and err.errors[0].get("type", None) == "NOT_FOUND"
    )
    is_quiz_http_404 = (
        isinstance(err, quiz.HTTPError) and err.response.status_code == 404
    )
    return is_quiz_not_found_err_response or is_quiz_http_404


async def run_graphql(
    executor: quiz.execution.async_executor, worker_name: str, gql_query: str
) -> quiz.execution.RawResult:
    """run_graphql runs a single serialized graphql query against the

    GitHub API and returns the response JSON
    """
    try:
        result = await executor(gql_query)
        log.debug(f"{worker_name} run_graphql: got result: {result}")
        return result
    except quiz.ErrorResponse as err:
        log.error(
            f"{worker_name} run_graphql: got a quiz.ErrorResponse {err} {err.errors}"
        )
        raise err
    except quiz.HTTPError as err:
        log.error(
            f"{worker_name} run_graphql: got a quiz.HTTPError {err} {err.response}"
        )
        raise err
        # if we hit the rate limit or the server is down
        # elif err.response.status_code in {403, 503}:


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_aiohttp_args(parser)
    parser.add_argument(
        "--github-accept-header",
        nargs="*",
        action="append",
        default=[
            # https://developer.github.com/v4/previews/#access-to-a-repositories-dependency-graph
            "application/vnd.github.hawkgirl-preview+json",
            # https://developer.github.com/v4/previews/#repository-vulnerability-alerts
            "application/vnd.github.vixen-preview+json",
        ],
    )
    parser.add_argument(
        "--github-auth-token",
        default=os.environ.get("GITHUB_PAT", None),
        help="A github personal access token. Defaults GITHUB_PAT env var. It"
        "should have most of the scopes from"
        "https://developer.github.com/v4/guides/forming-calls/#authenticating-with-graphql",
    )
    parser.add_argument(
        "--github-workers",
        help="the number of concurrent workers to run github requests (defaults to 3)",
        type=int,
        default=3,
    )
    query_types = [k.name for k in ResourceKind]
    parser.add_argument(
        "--github-query-type",
        help="a github query type to fetch. Defaults to all types",
        action="append",
        choices=query_types,
    )
    parser.add_argument(
        "--github-repo-langs-page-size",
        help="number of github repo langs to fetch with each request (defaults to 25)",
        type=int,
        default=25,
    )
    parser.add_argument(
        "--github-repo-dep-manifests-page-size",
        help="number of github repo dep manifests to fetch with each request (defaults to 1)",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--github-repo-dep-manifest-deps-page-size",
        help="number of github repo deps for a manifest to fetch with each request (defaults to 100)",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--github-repo-vuln-alerts-page-size",
        help="number of github repo vuln alerts to fetch with each request (defaults to 25)",
        type=int,
        default=25,
    )
    parser.add_argument(
        "--github-repo-vuln-alert-vulns-page-size",
        help="number of github repo vulns per alerts to fetch with each request (defaults to 25)",
        type=int,
        default=25,
    )
    parser.add_argument(
        "--github-poll-seconds",
        help="frequency in seconds to check whether worker queues are empty and quit (defaults to 3)",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--github-max-retries",
        help="max times to retry a query with jitter and exponential backoff (defaults to 12)"
        "Ignores 404s and graphql not found errors",
        type=int,
        default=12,
    )
    return parser


@contextmanager
def event_in_progress(event: asyncio.Event):
    "sets an asyncio.Event to true for the duration of the yield"
    event.set()
    yield
    event.clear()


def aiohttp_session(args: argparse.Namespace) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        headers={
            "Accept": ",".join(args.github_accept_header),
            "User-Agent": args.user_agent,
        },
        timeout=aiohttp.ClientTimeout(total=args.total_timeout),
        connector=aiohttp.TCPConnector(limit=args.max_connections),
        raise_for_status=True,
    )


async def quiz_executor_and_schema(
    args: argparse.Namespace, session: aiohttp.ClientSession
) -> Tuple[quiz.execution.async_executor, quiz.Schema]:
    async_executor = quiz.async_executor(
        url="https://api.github.com/graphql",
        auth=snug.header_adder({"Authorization": f"Bearer {args.github_auth_token}"}),
        client=session,
    )
    result = await async_executor(quiz.INTROSPECTION_QUERY)
    schema: quiz.Schema = quiz.Schema.from_raw(
        result["__schema"], scalars=(), module=None
    )
    log.debug("fetched github graphql schema")
    return async_executor, schema


async def worker(
    name: str,
    to_run: asyncio.Queue,
    to_write: asyncio.Queue,
    schema: quiz.Schema,
    executor: quiz.execution.async_executor,
    shutdown: asyncio.Event,
    request_pending: asyncio.Event,
    run_graphql_with_backoff: Callable[
        [quiz.execution.async_executor, str, str], quiz.execution.RawResult
    ],
):
    """worker runs Github metadata requests until shutdown

    More specifically until the shutdown event fires it repeatedly:

    1. pulls a request from the to_run queue
    2. sets request pending
    3. runs the request
    4. clears request pending
    5. pushes successful request response exhcanges to the to_write queue
    """
    queue_wait_timeout_seconds = 2

    while True:
        if shutdown.is_set():
            log.debug(f"{name} shutting down")
            break

        try:
            request: Request = await asyncio.wait_for(
                to_run.get(), queue_wait_timeout_seconds
            )
        except asyncio.TimeoutError:
            log.debug(f"{name} no new requests after {queue_wait_timeout_seconds}s")
            continue

        with event_in_progress(request_pending):
            # TODO: retry if request fails due to rate limit or intermittant error
            try:
                gql_query = str(schema.query[request.graphql])
                assert str(MISSING) not in gql_query
                log.info(f"{name} running {request.log_str}")
                log.debug(f"{name} {request.log_id} gql_query is: {gql_query}")
                result: quiz.execution.RawResult = await run_graphql_with_backoff(
                    executor, name, gql_query
                )
                response: Response = Response(resource=request.resource, json=result)
                log.debug(
                    f"{name} for {request.log_id} queued response {response.log_str} to write"
                )
                # write non-empty responses to stdout
                assert response
                to_write.put_nowait(RequestResponseExchange(request, response))
            except Exception as err:
                log.error(f"{name} error running {request.log_id}\n:{exc_to_str()}")

            # Notify the queue that the "work item" has been processed.
            to_run.task_done()


def get_response(task):
    assert task.done()
    assert isinstance(task, asyncio.Task)

    if task.cancelled():
        log.warn("task fetching {} was cancelled".format(None))

    if task.exception():
        log.error("task fetching {} errored".format(None))
        task.print_stack()

    yield task.result()


async def run_pipeline(
    source: Generator[Dict[str, str], None, None], args: argparse.Namespace
):
    log.info("pipeline github_metadata started")

    async with aiohttp_session(args) as session:
        executor, schema = await quiz_executor_and_schema(args, session)
        run_graphql_with_backoff = backoff.on_exception(
            backoff.expo,
            (quiz.ErrorResponse, quiz.HTTPError),
            max_tries=args.github_max_retries,
            giveup=is_not_found_exception,
            logger=log,
        )(run_graphql)

        to_run: asyncio.Queue = asyncio.Queue()
        to_write: asyncio.Queue = asyncio.Queue()
        stop_workers = asyncio.Event()

        # start workers that run queries from to_run and write responses to
        # to_write until the stop_workers event is set
        pending_tasks: Dict[str, asyncio.Event] = {
            f"worker-{i}": asyncio.Event() for i in range(args.github_workers)
        }
        worker_tasks: Dict[str, asyncio.Task] = {
            name: asyncio.create_task(
                worker(
                    name,
                    to_run,
                    to_write,
                    schema,
                    executor,
                    stop_workers,
                    request_pending,
                    run_graphql_with_backoff,
                )
            )
            for (name, request_pending) in pending_tasks.items()
        }
        log.info(f"started {len(worker_tasks)} GH workers")

        # add initial items to the queue
        args_dict = vars(args)
        for item in source:
            org_repo: OrgRepo = OrgRepo.from_github_repo_url(item["repo_url"])
            context = ChainMap(args_dict, dict(owner=org_repo.org, name=org_repo.repo))
            for request in get_next_requests(log, context, last_exchange=None):
                log.debug(f"initial request: {request.log_id}")
                assert len(request.selection_updates) == len(
                    request.resource.first_page_diffs
                )
                to_run.put_nowait(request)
        log.info(f"queued {to_run.qsize()} initial requests")

        while True:
            try:
                exchange: RequestResponseExchange = to_write.get_nowait()

                next_requests = list(
                    get_next_requests(log, ChainMap(args_dict), exchange)
                )
                for request in next_requests:
                    assert (
                        len(request.selection_updates)
                        <= len(request.resource.first_page_diffs) + 1
                    )
                    log.debug(f"queued {request.log_id} from {exchange.request.log_id}")
                    to_run.put_nowait(request)

                log.debug(
                    f"queued {len(next_requests)} more requests from {exchange.request.log_id}"
                )

                # yield results to sink to write to stdout
                yield raw_result_to_dict(exchange.response.json)
                log.debug(
                    f"writing {exchange.response.log_str} for {exchange.request.log_id}"
                )
                to_write.task_done()
            except asyncio.QueueEmpty:
                log.debug(
                    f"no responses to write. sleeping for {args.github_poll_seconds}s"
                )
                await asyncio.sleep(args.github_poll_seconds)

            log.debug(
                f"{to_run.qsize()} to run; "
                f"{len([pending for pending in pending_tasks.values() if pending.is_set()])} pending; "
                f"{to_write.qsize()} to write"
            )
            if (
                to_run.empty()
                and to_write.empty()
                and not any(pending.is_set() for pending in pending_tasks.values())
            ):
                log.info(f"queues are empty stopping workers")
                stop_workers.set()
                for worker_task in worker_tasks.values():
                    try:
                        await asyncio.wait_for(worker_task, timeout=5)
                    except asyncio.TimeoutError:
                        log.error(f"cancelling worker {worker_task} after 5s timeout")
                        worker_task.cancel()
                break

        assert all(get_response(task) for task in worker_tasks.values())


FIELDS: AbstractSet[str] = set()  # "crate", "categories", "keywords", "versions"}


pipeline = Pipeline(
    name="github_metadata",
    desc=__doc__,
    argparser=parse_args,
    fields=FIELDS,
    reader=iter_jsonlines,
    runner=run_pipeline,
    writer=on_next_save_to_jsonl,
)
