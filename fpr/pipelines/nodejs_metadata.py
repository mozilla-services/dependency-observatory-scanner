import argparse
import asyncio
from collections import ChainMap
from dataclasses import asdict, dataclass
import functools
import itertools
import json
import logging
import pathlib
from random import randrange
import sys
import time
from typing import (
    AbstractSet,
    Any,
    AnyStr,
    AsyncGenerator,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)
import typing

from fpr.rx_util import on_next_save_to_jsonl
from fpr.serialize_util import get_in, extract_fields, iter_jsonlines, REPO_FIELDS
import fpr.docker.containers as containers
import fpr.docker.volumes as volumes
from fpr.models import GitRef, OrgRepo, Pipeline, SerializedNodeJSMetadata
from fpr.models.language import DependencyFile, languages, ContainerTask
from fpr.models.pipeline import add_infile_and_outfile, add_volume_arg
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.nodejs_metadata")

__doc__ = """Runs specified install, list_metadata, and audit tasks on a git
ref for the provided dep. files."""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_volume_arg(parser)
    parser.add_argument(
        "-m",
        "--manifest-path",
        type=str,
        required=False,
        default=None,
        help="Filter to only run npm install, list, and audit "
        "for matching manifest file name and path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        required=False,
        default=False,
        help="Print commands we would run and their context, but don't run them.",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        required=False,
        default=True,
        help="Cache and results for the same repo, and dep file directory and SHA2"
        "sums for multiple git refs (NB: ignores changes to non-dep files e.g. to "
        "node.js install hook scripts).",
    )
    parser.add_argument(
        "--dir",
        type=str,
        required=False,
        default=None,
        help="Only run against matching directory. "
        "e.g. './' for root directory or './packages/fxa-js-client/' for a subdirectory",
    )
    parser.add_argument(
        "--repo-task",
        type=str,
        action="append",
        required=False,
        default=[],
        help="Run install, list_metadata, or audit tasks in the order provided. "
        "Defaults to none of them.",
    )
    return parser


@dataclass
class NodeJSMetadataBuildArgs:
    base_image_name: str = "node"
    base_image_tag: str = "10"

    _DOCKERFILE = """
FROM {0.base_image}
RUN apt-get -y update && apt-get install -y git
CMD ["node"]
"""

    repo_tag = "dep-obs/nodejs-metadata"

    @property
    def base_image(self) -> str:
        return f"{self.base_image_name}:{self.base_image_tag}"

    @property
    def dockerfile(self) -> bytes:
        return NodeJSMetadataBuildArgs._DOCKERFILE.format(self).encode("utf-8")


async def build_container(args: NodeJSMetadataBuildArgs = None) -> str:
    # NB: can shell out to docker build if this doesn't work
    if args is None:
        args = NodeJSMetadataBuildArgs()
    await containers.build(args.dockerfile, args.repo_tag, pull=True)
    log.info(f"successfully built and tagged image {args.repo_tag}")
    return args.repo_tag


async def run_in_repo_at_ref(
    args: argparse.Namespace,
    item: Tuple[OrgRepo, GitRef, pathlib.Path],
    tasks: List[ContainerTask],
    version_commands: typing.Mapping[str, str],
    dry_run: bool,
    cwd_files: AbstractSet[str],
) -> AsyncGenerator[Dict[str, Any], None]:
    (org_repo, git_ref, path) = item

    name = f"dep-obs-nodejs-metadata-{org_repo.org}-{org_repo.repo}-{hex(randrange(1 << 32))[2:]}"
    async with containers.run(
        "dep-obs/nodejs-metadata:latest",
        name=name,
        cmd="/bin/bash",
        volumes=[
            volumes.DockerVolumeConfig(
                name=f"fpr-org_{org_repo.org}-repo_{org_repo.repo}",
                mount_point="/repos",
                labels=asdict(org_repo),
                delete=not args.keep_volumes,
            )
        ],
    ) as c:
        await containers.ensure_repo(
            c, org_repo.github_clone_url, working_dir="/repos/"
        )
        await containers.ensure_ref(c, git_ref, working_dir="/repos/repo")
        branch, commit, tag, *version_results = await asyncio.gather(
            *(
                [
                    containers.get_branch(c, working_dir="/repos/repo"),
                    containers.get_commit(c, working_dir="/repos/repo"),
                    containers.get_tag(c, working_dir="/repos/repo"),
                ]
                + [
                    containers.run_container_cmd_no_args_return_first_line_or_none(
                        command, c, working_dir="/repos/repo"
                    )
                    for command in version_commands.values()
                ]
            )
        )
        versions = {
            command_name: version_results[i]
            for (i, (command_name, command)) in enumerate(version_commands.items())
        }

        working_dir = str(pathlib.Path("/repos/repo") / path)
        for task in tasks:
            last_inspect = dict(ExitCode=None)
            stdout = "dummy-stdout"

            if dry_run:
                log.info(
                    f"{name} in {working_dir} for task {task.name} skipping running {task.command} for dry run"
                )
                continue

            # use getattr since mypy thinks we're passing a self arg otherwise
            if not getattr(task, "has_files_check")(cwd_files):
                log.warn(
                    f"Missing files to run {task.name} {task.command} in {working_dir!r}"
                )
                continue
            else:
                log.debug(
                    f"have files to run {task.name} in {working_dir!r}: {cwd_files}"
                )

            log.info(
                f"{name} at {git_ref} in {working_dir} for task {task.name} running {task.command}"
            )
            try:
                job_run = await c.run(
                    cmd=task.command,
                    working_dir=working_dir,
                    wait=True,
                    check=task.check,
                )
                last_inspect = await job_run.inspect()
            except containers.DockerRunException as e:
                log.error(
                    f"{name} in {working_dir} for task {task.name} error running {task.command}: {e}"
                )
                break

            stdout = "".join(job_run.decoded_start_result_stdout)

            result: Dict[str, Any] = dict(
                versions=versions,
                branch=branch,
                commit=commit,
                tag=tag,
                relative_path=str(path),
                task={
                    "name": task.name,
                    "command": task.command,
                    "container_name": name,
                    "working_dir": working_dir,
                    "exit_code": last_inspect["ExitCode"],
                    "stdout": stdout,
                },
            )
            c_stdout, c_stderr = await asyncio.gather(
                c.log(stdout=True), c.log(stderr=True)
            )
            log.debug(f"{name} stdout: {c_stdout}")
            log.debug(f"{name} stderr: {c_stderr}")
            yield result


DepFileRow = Tuple[OrgRepo, GitRef, DependencyFile]


def group_by_org_repo_ref_path(
    source: Generator[Dict[str, Any], None, None]
) -> Generator[Tuple[Tuple[str, str, pathlib.Path], List[DepFileRow]], None, None]:
    # read all input rows into memory
    rows: List[DepFileRow] = [
        (
            OrgRepo(item["org"], item["repo"]),
            GitRef.from_dict(item["ref"]),
            DependencyFile(
                path=pathlib.Path(item["dep_file_path"]), sha256=item["dep_file_sha256"]
            ),
        )
        for item in source
    ]

    # sort in-place by org repo then ref value (sorted is stable)
    sorted(rows, key=lambda row: row[0].org_repo)
    sorted(rows, key=lambda row: row[1].value)

    # group by org repo then ref value
    for org_repo_ref_key, group_iter in itertools.groupby(
        rows, key=lambda row: (row[0].org_repo, row[1].value)
    ):
        org_repo_key, ref_value_key = org_repo_ref_key
        org_repo_ref_rows = list(group_iter)

        # sort and group by path parent e.g. /foo/bar for /foo/bar/package.json
        sorted(org_repo_ref_rows, key=lambda row: row[2].path.parent)
        for dep_file_parent_key, inner_group_iter in itertools.groupby(
            org_repo_ref_rows, key=lambda row: row[2].path.parent
        ):
            file_rows = list(inner_group_iter)
            yield (org_repo_key, ref_value_key, dep_file_parent_key), file_rows


async def run_pipeline(
    source: Generator[Dict[str, Any], None, None], args: argparse.Namespace
) -> AsyncGenerator[Dict, None]:
    log.info(f"{pipeline.name} pipeline started")

    # TODO: build images for each lang version, etc? (configure with CLI args?)
    try:
        await build_container()
    except Exception as e:
        log.error(
            f"error occurred building the nodejs metadata image: {e}\n{exc_to_str()}"
        )

    version_commands = ChainMap(
        languages["nodejs"].version_commands,
        *[pm.version_commands for pm in languages["nodejs"].package_managers.values()],
    )
    tasks: List[ContainerTask] = [
        languages["nodejs"].package_managers["npm"].tasks[task_name]
        for task_name in args.repo_task
    ]

    # cache of results by org/repo, dep files dir path, and dep file sha256
    # sums
    cache: Dict[Tuple[str, pathlib.Path, str], List[Dict]] = {}
    for (
        (org_repo_key, ref_value_key, dep_file_parent_key),
        file_rows,
    ) in group_by_org_repo_ref_path(source):
        files = {fr[2].path.parts[-1] for fr in file_rows}
        file_hashes = sorted([fr[2].sha256 for fr in file_rows])

        log.debug(f"in {dep_file_parent_key!r} with files {files}")
        if args.dir is not None:
            if pathlib.PurePath(args.dir) != dep_file_parent_key:
                log.debug(
                    f"Skipping non-matching folder {dep_file_parent_key} for glob {args.dir}"
                )
                continue
            else:
                log.debug(
                    f"matching folder {dep_file_parent_key!r} for glob {args.dir!r}"
                )

        # TODO: use caching decorator
        cache_key = (org_repo_key, dep_file_parent_key, "-".join(file_hashes))
        if args.use_cache and cache_key in cache:
            log.debug(f"using cached result for {cache_key}")
            for cached_result in cache[cache_key]:
                cached_result["data_source"] = "in_memory_cache"
                yield cached_result
            continue

        cache[cache_key] = []
        try:
            async for result in run_in_repo_at_ref(
                args,
                (file_rows[0][0], file_rows[0][1], dep_file_parent_key),
                tasks,
                version_commands,
                args.dry_run,
                files,
            ):
                cache[cache_key].append(result)
                yield result
            log.debug(f"saved cached result for {cache_key}")
        except Exception as e:
            log.error(f"error running tasks {tasks!r}:\n{exc_to_str()}")


# TODO: clarify input vs. output fields, improve validation, and specify field providers
FIELDS: AbstractSet = set()


def serialize(_: argparse.Namespace, result: Dict):
    return result


pipeline = Pipeline(
    # TODO: make generic over langs and package managers and rename
    name="nodejs_metadata",
    desc=__doc__,
    fields=FIELDS,
    argparser=parse_args,
    reader=iter_jsonlines,
    runner=run_pipeline,
    serializer=serialize,
    writer=on_next_save_to_jsonl,
)
