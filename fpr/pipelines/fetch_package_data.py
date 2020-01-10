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
from fpr.clients.npmsio import fetch_npmsio_scores
from fpr.models import GitRef, OrgRepo, Pipeline, SerializedNodeJSMetadata
from fpr.models.language import DependencyFile, languages, ContainerTask
from fpr.models.pipeline import add_infile_and_outfile, add_volume_arg
from fpr.pipelines.util import exc_to_str


NAME = "fetch_package_data"

log = logging.getLogger(f"fpr.pipelines.{NAME}")

__doc__ = """Fetches additional data about a dependency."""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        required=False,
        default=False,
        help="Print commands we would run and their context, but don't run them.",
    )
    parser.add_argument(
        dest="package_task",
        type=str,
        choices=["fetch_npmsio_scores"],
        default="fetch_npmsio_scores",
        help="Task to run on each package. Defaults to 'fetch_npmsio_scores'",
    )
    parser.add_argument(
        "--package-batch-size",
        type=int,
        required=False,
        default=50,
        help="Number of packages to fetch data for. Defaults to 50.",
    )
    return parser


async def run_pipeline(
    source: Generator[Dict[str, Any], None, None], args: argparse.Namespace
) -> AsyncGenerator[Dict, None]:
    log.info(f"{pipeline.name} pipeline started with task {args.package_task}")

    if args.package_task == "fetch_npmsio_scores":
        packages = [package for package in source]
        assert all(
            isinstance(package, dict) and "name" in package for package in packages
        )
        package_names = [package["name"] for package in packages]
        log.info(
            f"fetching npmsio scores for {len(package_names)} package names in batches of {args.package_batch_size}"
        )
        async for package_result in fetch_npmsio_scores(
            package_names,
            pkgs_per_request=args.package_batch_size,
            dry_run=args.dry_run,
        ):
            yield package_result
    else:
        raise NotImplementedError(f"unrecognized task {args.package_task}")


# TODO: improve validation and specify field providers
IN_FIELDS: Dict[str, Union[type, str, Dict[str, str]]] = {
    # might be able to infer these
    "language": str,  # Language.name
    "package_manager": str,  # PackageManager.name
    # NPMPackage, RustCrate, or RustCrate (resolved or unresolved)
    "name": str,  # the pcakage name
    "version": Optional[str],
}
OUT_FIELDS: Dict[str, Any] = dict()


pipeline = Pipeline(
    name=NAME,
    desc=__doc__,
    fields=set(OUT_FIELDS.keys()),
    argparser=parse_args,
    reader=iter_jsonlines,
    runner=run_pipeline,
    writer=on_next_save_to_jsonl,
)
