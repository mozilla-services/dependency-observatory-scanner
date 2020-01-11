import os
import argparse
import logging
import pathlib
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, Tuple, Union

from fpr.rx_util import on_next_save_to_jsonl
from fpr.clients.npmsio import fetch_npmsio_scores
from fpr.clients.npm_registry import fetch_npm_registry_metadata
from fpr.models.pipeline import Pipeline, add_infile_and_outfile, add_aiohttp_args
from fpr.pipelines.util import exc_to_str
from fpr.serialize_util import iter_jsonlines


NAME = "fetch_package_data"

log = logging.getLogger(f"fpr.pipelines.{NAME}")

__doc__ = """Fetches additional data about a dependency."""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_aiohttp_args(parser)
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
        choices=["fetch_npmsio_scores", "fetch_npm_registry_metadata"],
        default="fetch_npmsio_scores",
        help="Task to run on each package. Defaults to 'fetch_npmsio_scores'",
    )
    parser.add_argument(
        "--package-batch-size",
        type=int,
        required=False,
        default=50,
        help="Number of packages per fetch_npmsio_scores request. Defaults to 50.",
    )
    parser.add_argument(
        "--npm-auth-token",
        default=os.environ.get("NPM_PAT", None),
        help="An npm registry access token for fetch_npm_registry_metadata."
        " Defaults NPM_PAT env var. Should be read-only.",
    )
    return parser


def is_dict_with_name(package: Any) -> bool:
    return isinstance(package, dict) and "name" in package


async def run_pipeline(
    source: Generator[Dict[str, Any], None, None], args: argparse.Namespace
) -> AsyncGenerator[Dict, None]:
    log.info(f"{pipeline.name} pipeline started with task {args.package_task}")

    packages = [package for package in source]
    assert all(is_dict_with_name(package) for package in packages)
    package_names = [package["name"] for package in packages]
    log.info(
        f"fetching {args.package_task} for {len(package_names)} package names in batches of {args.package_batch_size}"
    )
    if args.package_task == "fetch_npmsio_scores":
        async for package_result in fetch_npmsio_scores(args, package_names):
            yield package_result
    elif args.package_task == "fetch_npm_registry_metadata":
        async for package_result in fetch_npm_registry_metadata(args, package_names):
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
