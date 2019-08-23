import argparse
import logging
import functools
import sys
import time
import json
from dataclasses import dataclass
from typing import Dict, Tuple, List, Set, Any

import rx
import rx.operators as op

from fpr.rx_util import map_async, on_next_save_to_jsonl
from fpr.serialize_util import (
    get_in,
    extract_fields,
    iter_jsonlines,
    REPO_FIELDS,
    RUST_FIELDS,
)
import fpr.containers as containers
from fpr.models import GitRef, OrgRepo, Pipeline
from fpr.models.rust import cargo_metadata_to_rust_crate_and_packages
from fpr.graph_util import (
    rust_crates_and_packages_to_networkx_digraph,
    get_authors,
    get_repos,
    has_changes,
    get_new_removed_and_new_total,
)
from fpr.models.pipeline import add_infile_and_outfile, add_graphviz_graph_args
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.rust_changelog")

__doc__ = """
Given ordered cargo metadata output for git refs from the same repo:

1. filters by the manifest filename
2. groups the output into pairs (i.e. 1, 2, 3 -> (1, 2), (2, 3)
3. compares each pair as folows:
  a. count new and removed dependencies
  b. new and removed authors and repo urls

TODO: report new, removed, and changed Cargo.toml manifest files
TODO: output a diff of the updated dep code (need to update the cargo metadata pipeline to pull these)
TODO: take audit output to show new and fixed Rust vulns
TODO: detect dep version changes
"""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_graphviz_graph_args(parser)
    parser.add_argument(
        "-m",
        "--manifest-path",
        type=str,
        required=True,
        help="Filter to only display results for one Cargo.toml manifest",
    )
    return parser


def run_compare_rust_commits(args: argparse.Namespace, item: List[Dict[str, str]]):
    if len(item) != 2:  # the last buffered value will be the last value so ignore it
        return {}
    lmeta, rmeta = item
    log.debug(
        "processing {} {[ref][value]} -> {[ref][value]}".format(
            args.manifest_path, lmeta, rmeta
        )
    )
    lgraph, rgraph = [
        rust_crates_and_packages_to_networkx_digraph(
            args, cargo_metadata_to_rust_crate_and_packages(meta)
        )
        for meta in item
    ]
    lauthors, rauthors = get_authors(lgraph), get_authors(rgraph)
    new_authors, removed_authors, new_total_authors = get_new_removed_and_new_total(
        lauthors, rauthors
    )

    lrepos, rrepos = get_repos(lgraph), get_repos(rgraph)
    new_repos, removed_repos, new_total_repos = get_new_removed_and_new_total(
        lrepos, rrepos
    )
    new_deps, removed_deps, new_total_deps = get_new_removed_and_new_total(
        set(lgraph.nodes), set(rgraph.nodes)
    )

    return {
        "manifest_path": args.manifest_path,
        "old_ref": lmeta["ref"]["value"],
        "new_ref": rmeta["ref"]["value"],
        "authors": {
            "new": new_authors,
            "removed": removed_authors,
            "new_total": new_total_authors,
        },
        "repositories": {
            "new": new_repos,
            "removed": removed_repos,
            "new_total": new_total_repos,
        },
        "deps": {"new": new_deps, "removed": removed_deps, "new_total": new_total_deps},
    }


def run_pipeline(source: rx.Observable, args: argparse.Namespace) -> rx.Observable:
    def on_run_compare_rust_commits_error(e, _, *args):
        log.error("error running run_compare_rust_commits:\n{}".format(exc_to_str()))
        return rx.empty([])

    pipeline = source.pipe(
        op.filter(lambda x: x["cargo_tomlfile_path"] == args.manifest_path),
        op.buffer_with_count(2, 1),
        op.map(functools.partial(run_compare_rust_commits, args)),
        op.catch(on_run_compare_rust_commits_error),
    )
    return pipeline


# TODO: rename to output fields
FIELDS = {}  # RUST_FIELDS | REPO_FIELDS | {"cargo_tomlfile_path", "ripgrep_version"}


def serialize(_: argparse.Namespace, result: Dict):
    if not result:
        return {}

    for k, v in result.items():
        if not isinstance(v, dict):
            continue
        for subkey, subv in v.items():
            if isinstance(subv, set):
                result[k][subkey] = sorted(list(subv))

    if not has_changes(result):
        log.info(
            """{0[manifest_path]} {0[old_ref]} -> {0[new_ref]}: No changes.""".format(
                result
            )
        )
    else:
        log.info(
            """{0[manifest_path]} {0[old_ref]} -> {0[new_ref]}:
authors:
  new: {0[authors][new]}
  removed: {0[authors][removed]}
  total: {0[authors][new_total]}

repos:
  new: {0[repositories][new]}
  removed: {0[repositories][removed]}
  total: {0[repositories][new_total]}

deps:
  new: {0[deps][new]}
  removed: {0[deps][removed]}
  total: {0[deps][new_total]}
""".format(
                result
            )
        )

    return result


pipeline = Pipeline(
    name="rust_changelog",
    desc=__doc__,
    fields=FIELDS,
    argparser=parse_args,
    reader=iter_jsonlines,
    runner=run_pipeline,
    serializer=serialize,
    writer=on_next_save_to_jsonl,
)
