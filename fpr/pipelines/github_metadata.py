import os
import sys
import argparse
import asyncio
from collections import ChainMap
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
from fpr.models import OrgRepo, Pipeline
from fpr.models.github import (
    ResourceKind,
    Request,
    Response,
    RequestResponseExchange,
    get_next_requests,
)
from fpr.models.rust import cargo_metadata_to_rust_crates
from fpr.models.pipeline import add_infile_and_outfile, add_aiohttp_args
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.github_metadata")

__doc__ = """Given an input file with repo urls metadata output fetches
dependency and vulnerability metadata from GitHub and an optional GitHub PAT
and outputs them to jsonl and optionally saves them to a local SQLite3 DB.
"""


async def run_graphql(
    schema: quiz.Schema,
    executor: quiz.execution.async_executor,
    selection: quiz.Selection,
) -> quiz.execution.RawResult:
    """run_graphql runs a single graphql query against the GitHub API.

    It returns the response JSON as a string

    TODO: check rate limits and sleep as necessary
    """
    try:
        gql_query = str(schema.query[selection])
        log.debug(f"run_graphql: gql_query is {gql_query!r}")
        response = await executor(gql_query)
        log.debug(f"run_graphql: got response {response!r}")
        return response
    except quiz.ErrorResponse as err:
        log.error(f"run_graphql: got a quiz.ErrorResponse {err} {err.errors}")
        # if len(err.errors) and err.errors[0].get("type", None) == "NOT_FOUND":
        #     break
        raise err
    except quiz.HTTPError as err:
        log.error(f"run_graphql: got a quiz.HTTPError {err} {err.response}")
        raise err
        # if err.response.status_code == 404:
        #     break
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
        help="frequency in seconds to check whether worker queues are empty and quit (defaults to 30)",
        type=int,
        default=30,
    )
    return parser


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
        auth=snug.header_adder(
            {
                "Authorization": "bearer {auth_token}".format(
                    auth_token=args.github_auth_token
                )
            }
        ),
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
):
    # response = await run_graphql(schema, executor, rate_limit_graphql())
    # log.debug("fetched rate limits {}".format(response))

    while True:
        if shutdown.is_set():
            log.debug(f"{name} shutting down")
            break

        try:
            request: Request = await asyncio.wait_for(to_run.get(), 2)
        except asyncio.TimeoutError:
            log.debug(f"{name} didn't get any new requests after 2s timeout")
            continue

        # run query
        # TODO: retry if it failed due to rate limit or intermittant error; otherwise log error
        try:
            log.debug(
                f"{name} running query {type(request)} {type(request.resource.kind)}"
            )
            response: quiz.execution.RawResult = await run_graphql(
                schema, executor, request.graphql
            )
            log.debug(f"{name} writing query to to_write {response!r}")
            # write non-empty responses to stdout
            assert response
            to_write.put_nowait(
                RequestResponseExchange(
                    request, Response(resource=request.resource, json=response)
                )
            )
        except Exception as err:
            log.error(f"{name} error running query {request}\n:{exc_to_str()}")

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

        to_run: asyncio.Queue = asyncio.Queue()
        to_write: asyncio.Queue = asyncio.Queue()
        stop_workers = asyncio.Event()

        # start workers that run queries from to_run and write responses to
        # to_write until the stop_workers event is set

        # TODO: waiting for a worker to read results off the wire before
        # writing them to the write queue means main (here) can cancel workers
        # before all results come in i.e.
        #
        # queue a request in to_run
        # worker pick up to_run job and waits for the result
        # main sees empty to_run and to_write queues and stops the workers
        # worker gets result with next page, but was canceled so more pages aren't fetched and we miss data
        #
        # as a workaround: we run with a larger poll timeout, but we want to track pending/in flight jobs

        worker_tasks: AbstractSet[asyncio.Task] = {
            asyncio.create_task(
                worker(f"worker-{i}", to_run, to_write, schema, executor, stop_workers)
            )
            for i in range(args.github_workers)
        }
        log.debug(f"started {len(worker_tasks)} GH workers")

        # add initial items to the queue
        args_dict = vars(args)
        for item in source:
            org_repo: OrgRepo = OrgRepo.from_github_repo_url(item["repo_url"])
            context = ChainMap(args_dict, dict(owner=org_repo.org, name=org_repo.repo))
            for request in get_next_requests(log, context, last_exchange=None):
                log.debug(
                    f"initial request for resource kind {request.resource.kind} context {context}"
                )
                to_run.put_nowait(request)
        log.debug(f"queued {to_run.qsize()} initial queries")

        while True:
            log.debug(
                f"run queue size is {to_run.qsize()}; write queue size is {to_write.qsize()}"
            )
            try:
                exchange: RequestResponseExchange = to_write.get_nowait()

                # add any follow up reqs to the queue (as written these won't run)
                for request in get_next_requests(log, ChainMap(args_dict), exchange):
                    to_run.put_nowait(request)

                # yield results to sink to write to stdout
                response_json = exchange.response.json
                assert response_json
                assert isinstance(response_json, dict)
                # drop __metadata__ from the quiz.execution.RawResult since it hits the
                # recursion limit when pickled
                yield {k: v for k, v in response_json.items() if k != "__metadata__"}
            except asyncio.QueueEmpty:
                log.debug(
                    f"no responses to write. sleeping for {args.github_poll_seconds}s"
                )
                await asyncio.sleep(args.github_poll_seconds)

            if to_run.empty() and to_write.empty():
                log.debug(f"queues are empty stopping workers")
                stop_workers.set()
                for worker_task in worker_tasks:
                    try:
                        await asyncio.wait_for(worker_task, timeout=5)
                    except asyncio.TimeoutError:
                        log.debug(f"cancelling worker {worker_task} after 5s timeout")
                        worker_task.cancel()
                break

        assert all(get_response(task) for task in worker_tasks)


FIELDS: AbstractSet[str] = set()  # "crate", "categories", "keywords", "versions"}


def serialize(args: argparse.Namespace, result: Dict) -> Dict[str, Any]:
    return result


pipeline = Pipeline(
    name="github_metadata",
    desc=__doc__,
    argparser=parse_args,
    fields=FIELDS,
    reader=iter_jsonlines,
    runner=run_pipeline,
    serializer=serialize,
    writer=on_next_save_to_jsonl,
)
