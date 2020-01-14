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
from fpr.graph_util import npm_packages_to_networkx_digraph, get_graph_stats
from fpr.serialize_util import (
    get_in,
    extract_fields,
    extract_nested_fields,
    iter_jsonlines,
    REPO_FIELDS,
)
from fpr.models import GitRef, OrgRepo, Pipeline, SerializedNodeJSMetadata
from fpr.models.language import DependencyFile, languages, ContainerTask
from fpr.models.pipeline import add_infile_and_outfile
from fpr.models.nodejs import flatten_deps
from fpr.pipelines.util import exc_to_str


NAME = "postprocess"

log = logging.getLogger(f"fpr.pipelines.{NAME}")


__doc__ = """Post processes tasks for various outputs e.g. flattening deps,
filtering and extracting fields, etc.

Does not spin up containers or hit the network.
"""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser.add_argument(
        "--repo-task",
        type=str,
        action="append",
        required=False,
        default=[],
        help="postprocess install, list_metadata, or audit tasks."
        "Defaults to none of them.",
    )
    return parser


# want: (repo, ref/tag, dep_files w/ hashes, deps, [dep. stats or vuln. stats] (join for final analysis))


def parse_stdout(stdout: Optional[str]) -> Optional[Dict]:
    if stdout is None:
        return None

    try:
        parsed_stdout = json.loads(stdout)
        return parsed_stdout
    except json.decoder.JSONDecodeError as e:
        log.warn(f"error parsing stdout as JSON: {e}")

    return None


async def run_pipeline(
    source: Generator[Dict[str, Any], None, None], args: argparse.Namespace
) -> AsyncGenerator[Dict, None]:
    log.info(f"{pipeline.name} pipeline started")

    for i, line in enumerate(source):
        # filter for node list_metadata output to parse and flatten deps
        task_name = get_in(line, ["task", "name"], None)
        if task_name not in args.repo_task:
            continue

        # TODO: reuse cached results for each set of dep files w/ hashes and task name
        parsed_stdout = parse_stdout(get_in(line, ["task", "stdout"], None))
        if parsed_stdout is None:
            log.debug("got empty stdout")
            continue

        result = extract_fields(
            line,
            [
                "branch",
                "commit",
                "tag",
                "org",
                "repo",
                "repo_url",
                "ref",
                "dependency_files",
            ],
        )
        result["task"] = extract_fields(
            line["task"],
            [
                "command",
                "container_name",
                "exit_code",
                "name",
                "relative_path",
                "working_dir",
            ],
        )

        if task_name == "list_metadata":
            deps = [dep for dep in flatten_deps(parsed_stdout)]
            result["graph_stats"] = get_graph_stats(
                npm_packages_to_networkx_digraph(deps)
            )

            list_results = {"problems": get_in(parsed_stdout, ["problems"], [])}
            list_results["dependencies"] = [asdict(dep) for dep in deps]
            list_results["dependencies_count"] = len(deps)
            list_results["problems_count"] = len(list_results["problems"])

            list_results["root"] = deps[-1] if len(deps) else None
            list_results["direct_dependencies_count"] = (
                len(deps[-1].dependencies) if len(deps) else None
            )
            result.update(list_results)
            log.info(
                f"wrote {result['task']['name']} {result['org']}/{result['repo']} {result['task']['relative_path']}"
                f" {result['ref']['value']} w/"
                f" {result['dependencies_count']} deps and {result['problems_count']} problems"
                f" {result['graph_stats']}"
            )
        elif task_name == "audit":
            # has format:
            # {
            #   actions: ...
            #   advisories: null or {
            #     <npm adv. id>: {
            # metadata: null also has an exploitablity score
            #
            # } ...
            #   }
            #   metadata: null or e.g. {
            #     "vulnerabilities": {
            #         "info": 0,
            #         "low": 0,
            #         "moderate": 6,
            #         "high": 0,
            #         "critical": 0
            #     },
            #     "dependencies": 896680,
            #     "devDependencies": 33885,
            #     "optionalDependencies": 10215,
            #     "totalDependencies": 940274
            #   }
            # }
            result.update(
                extract_nested_fields(
                    parsed_stdout,
                    {
                        "dependencies_count": ["metadata", "dependencies"],
                        "dev_dependencies_count": ["metadata", "devDependencies"],
                        "optional_dependencies_count": [
                            "metadata",
                            "optionalDependencies",
                        ],
                        "total_dependencies_count": ["metadata", "totalDependencies"],
                        "vulnerabilities": ["metadata", "vulnerabilities"],
                        "advisories": ["advisories"],
                        "error": ["error"],
                    },
                )
            )
            result["advisories"] = (
                dict() if result["advisories"] is None else result["advisories"]
            )
            result["vulnerabilities"] = (
                dict()
                if result["vulnerabilities"] is None
                else result["vulnerabilities"]
            )
            result["vulnerabilities_count"] = sum(result["vulnerabilities"].values())

            log.info(
                f"wrote {result['task']['name']} {result['org']}/{result['repo']} {result['task']['relative_path']}"
                f" {result['ref']['value']} w/"
                f" {result['vulnerabilities_count']} vulns"
            )
        yield result


FIELDS: AbstractSet = set()


pipeline = Pipeline(
    # TODO: make generic over langs and package managers and rename
    name=NAME,
    desc=__doc__,
    fields=FIELDS,
    argparser=parse_args,
    reader=iter_jsonlines,
    runner=run_pipeline,
    writer=on_next_save_to_jsonl,
)
