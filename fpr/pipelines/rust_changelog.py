import argparse
import logging
import functools
import itertools
import sys
import time
import json
from dataclasses import dataclass
from typing import (
    AbstractSet,
    Dict,
    Tuple,
    List,
    Set,
    Any,
    Union,
    Generator,
    AsyncGenerator,
)

from fpr.rx_util import on_next_save_to_jsonl
from fpr.serialize_util import get_in, extract_fields, iter_jsonlines, REPO_FIELDS
import fpr.docker.containers as containers
from fpr.models.pipeline import Pipeline
from fpr.models.org_repo import OrgRepo
from fpr.models.git_ref import GitRef
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

1. builds a dict of manifest filename to cargo meta
2. groups the output into pairs (i.e. 1, 2, 3 -> (1, 2), (2, 3) in the provided order
3. compares each pair as follows:
  a. compare each manifest filename:
    1) count new and removed dependencies
    2) new and removed authors and repo urls

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
        required=False,
        default=None,
        help="Filter to only display results for one Cargo.toml manifest",
    )
    return parser


def compare_rust_cargo_files(
    args: argparse.Namespace, lmeta: Dict, rmeta: Dict
) -> Dict[str, Any]:
    assert lmeta is not None and rmeta is not None
    log.debug(
        "processing {[cargo_tomlfile_path]} {[ref][value]} -> {[ref][value]}".format(
            lmeta, lmeta, rmeta
        )
    )
    lgraph, rgraph = [
        rust_crates_and_packages_to_networkx_digraph(
            args, cargo_metadata_to_rust_crate_and_packages(meta)
        )
        for meta in [lmeta, rmeta]
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
        "manifest_path": lmeta["cargo_tomlfile_path"],
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


def run_compare_rust_commits(
    args: argparse.Namespace,
    lcommit_meta: Dict[str, Dict],
    rcommit_meta: Dict[str, Dict],
) -> Dict[str, Any]:
    # TODO: report new, removed, and changed Cargo.toml manifest files
    # either the key is in both commits or just the left commit (removed) or just the right (added)
    manifest_paths = {
        k for k in itertools.chain(lcommit_meta.keys(), rcommit_meta.keys())
    }
    diff = {
        manifest_path: compare_rust_cargo_files(
            args, lcommit_meta[manifest_path], rcommit_meta[manifest_path]
        )
        for manifest_path in manifest_paths
    }
    return diff


async def run_pipeline(
    source: Generator[Dict, None, None], args: argparse.Namespace
) -> AsyncGenerator[None, None]:
    if args.manifest_path is not None:
        source = (
            meta for meta in source if meta["cargo_tomlfile_path"] == args.manifest_path
        )

    # combine meta outputs for each commit (e.g. {path1: meta1, path2: meta2})
    commits_with_meta = list(
        {meta["cargo_tomlfile_path"]: meta for meta in group}
        for commit, group in itertools.groupby(source, key=lambda meta: meta["commit"])
    )

    last_commit_metas = None
    for i, commit_metas in enumerate(commits_with_meta):
        if last_commit_metas is not None:
            try:
                diff = run_compare_rust_commits(args, last_commit_metas, commit_metas)
                yield diff
            except Exception as e:
                log.error(
                    "error running run_compare_rust_commits:\n{}".format(exc_to_str())
                )
        if i > 0:
            last_commit_metas = commit_metas


# TODO: rename to output fields
FIELDS: AbstractSet[str] = set()


def serialize(_: argparse.Namespace, result: Dict):
    if not result:
        return {}

    for manifest_path, diff in result.items():
        if not diff:
            return {}

        for k, v in diff.items():
            if not isinstance(v, dict):
                continue

            for subkey, subv in v.items():
                if isinstance(subv, set):
                    diff[k][subkey] = sorted(list(subv))

        if not has_changes(diff):
            log.info(
                """{0[manifest_path]} {0[old_ref]} -> {0[new_ref]}: No changes.""".format(
                    diff
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
                    diff
                )
            )
        result[manifest_path] = diff
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
