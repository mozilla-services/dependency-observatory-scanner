import argparse
import functools
import logging
import json
from typing import Dict, Tuple, Sequence

import networkx as nx
from networkx.drawing.nx_pydot import to_pydot
import rx
import rx.operators as op

from fpr.rx_util import on_next_save_to_file
from fpr.models import Pipeline, RustCrate, RustPackageID, RustPackage
from fpr.models.pipeline import add_infile_and_outfile
from fpr.serialize_util import extract_fields, get_in
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.crate_graph")

__doc__ = """Parses the output of the cargo metadata pipeline and writes a .dot
file of the dependencies to outfile"""


NODE_ID_FORMATS = {
    "name": "{pkg_id.name}",
    "name_version": "{pkg_id.name} {pkg_id.version}",
    "name_version_source": "{pkg_id.name} {pkg_id.version} {pkg_id.source}",
    "source": "{pkg_id.source}",
}

NODE_LABEL_FORMATS = {
    "name": "{crate.package_id.name}",
    "name_version": "{crate.package_id.name} {crate.package_id.version}",
    "name_version_source": "{crate.package_id.name} {crate.package_id.version} {crate.package_id.source}",
    "source": "{crate.package_id.source}",
    "name_authors": "{crate.package_id.name}\n{crate_package.authors}",
    "name_readme": "{crate.package_id.name}\n{crate_package.readme}",
    "name_repository": "{crate.package_id.name}\n{crate_package.repository}",
    "name_license": "{crate.package_id.name}\n{crate_package.license}",
    "name_package_source": "{crate.package_id.name}\n{crate_package.source}",
    "name_metadata": "{crate.package_id.name}\n{crate_package.metadata}",
}


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser.add_argument(
        "-k",
        "--node-key",
        type=str,
        choices=NODE_ID_FORMATS.keys(),
        required=False,
        default="name_version",
        help="The node key to use to link nodes",
    )
    parser.add_argument(
        "-l",
        "--node-label",
        type=str,
        choices=NODE_LABEL_FORMATS.keys(),
        required=False,
        default="name_version",
        help="The node label to display",
    )
    parser.add_argument(
        "-f",
        "--filter",
        type=str,
        action="append",
        required=False,
        # TODO: filter by path, features, edge attrs, or non-label node data
        help="Node label substring filters to apply",
    )
    return parser


def cargo_metadata_to_rust_crate_and_packages(
    cargo_meta_out: Dict
) -> Tuple[Dict[str, RustCrate], Dict[str, RustPackage]]:
    log.debug(
        "running crate-graph on {0[cargo_tomlfile_path]} in {0[org]}/{0[repo]} at {0[commit]} ".format(
            cargo_meta_out
        )
    )
    assert (
        get_in(cargo_meta_out, ["metadata", "version"]) == 1
    ), "cargo metadata format was not version 1"

    # build hashmap by pkg_id so we can lookup additional package info from
    # resolved crate as packages[crate.id]
    crates = {}
    for n in get_in(cargo_meta_out, ["metadata", "nodes"]):
        crate = RustCrate(**extract_fields(n, {"id", "features", "deps"}))
        assert crate.id not in crates
        crates[crate.id] = crate

    packages = {}
    for p in get_in(cargo_meta_out, ["metadata", "packages"]):
        pkg = RustPackage(**p)
        assert pkg.id not in packages
        packages[pkg.id] = pkg

    return (crates, packages)


def rust_crates_and_packages_to_networkx_digraph(
    args: argparse.Namespace,
    crates_and_packages: Tuple[Dict[str, RustCrate], Dict[str, RustPackage]],
) -> nx.DiGraph:
    log.info("graphing with args: {}".format(args))
    crates, packages = crates_and_packages

    node_id_format = NODE_ID_FORMATS[args.node_key]
    node_label_format = NODE_LABEL_FORMATS[args.node_label]

    g = nx.DiGraph()
    for c in crates.values():
        node_id = node_id_format.format(pkg_id=c.package_id)

        # print('node ', node_id, 'label', node_label_format.format(crate=c, crate_package=packages[c.id]))
        g.add_node(
            node_id,
            label=node_label_format.format(crate=c, crate_package=packages[c.id]),
        )
        for dep in c.deps:
            dep_id = node_id_format.format(pkg_id=RustPackageID.parse(dep["pkg"]))
            g.add_edge(
                node_id,
                dep_id,
                # name=dep["name"],
                # features=dep["features"],
            )

    return g


def filter_graph_nodes(filters: Sequence[str], g: nx.DiGraph) -> nx.DiGraph:
    """Removes nodes from the graph with labels that do not match at
    least one substring of the filters args
    """
    if not filters:
        return g

    unfiltered_node_count = len(g.nodes)
    log.debug("removing nodes matching: {}".format(filters))
    matching_nodes = [
        nid
        for (nid, attrs) in g.nodes.items()
        if not any(f in attrs["label"] for f in filters)
    ]
    g.remove_nodes_from(matching_nodes)
    log.debug(
        "removed {} nodes of {}".format(len(matching_nodes), unfiltered_node_count)
    )
    return g


def run_pipeline(source: rx.Observable, args: argparse.Namespace):
    pipeline = source.pipe(
        op.do_action(lambda x: log.debug("processing {!r}".format(x))),
        op.map(cargo_metadata_to_rust_crate_and_packages),
        op.map(functools.partial(rust_crates_and_packages_to_networkx_digraph, args)),
        op.map(functools.partial(filter_graph_nodes, args.filter)),
    )
    return pipeline


def serialize(_: argparse.Namespace, g: "DiGraph"):
    pdot = to_pydot(g)
    pdot.set("rankdir", "LR")
    return str(pdot)


pipeline = Pipeline(
    name="crate_graph",
    desc=__doc__,
    fields=set(),
    argparser=parse_args,
    reader=lambda infile: [json.load(infile)],
    runner=run_pipeline,
    serializer=serialize,
    writer=on_next_save_to_file,
)
