import argparse
from dataclasses import dataclass
import functools
import itertools
import logging
import json
import random
from typing import Dict, Tuple, Sequence, List

import networkx as nx
from networkx.drawing.nx_pydot import to_pydot
from networkx.utils import make_str
import rx
import rx.operators as op
import pydot

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
    "name_version_repository": "{crate.package_id.name} {crate.package_id.version}\n{crate_package.repository}",
    "name_license": "{crate.package_id.name}\n{crate_package.license}",
    "name_package_source": "{crate.package_id.name}\n{crate_package.source}",
    "name_metadata": "{crate.package_id.name}\n{crate_package.metadata}",
}

GROUP_ATTRS = {
    "author": lambda node: node[1]["crate_package"].authors or [],
    "repository": lambda node: node[1]["crate_package"].repository or "",
    # 'workspace':
    # 'manifest_path':
    # 'source_repository':
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
    parser.add_argument(
        "-s",
        "--style",
        type=str,
        action="append",
        help="Style nodes with a label matching the substring with the provided graphviz dot attr. "
        "Format is <label substring>:<dot attr name>:<dot attr value> e.g. serde:shape:egg",
    )
    parser.add_argument(
        "-g",
        "--groupby",
        choices=GROUP_ATTRS.keys(),
        action="append",
        help="Group nodes by crate attribute",
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
    log.debug("graphing with args: {}".format(args))
    crates, packages = crates_and_packages

    node_id_format = NODE_ID_FORMATS[args.node_key]
    node_label_format = NODE_LABEL_FORMATS[args.node_label]

    g = nx.DiGraph()
    for c in crates.values():
        node_id = node_id_format.format(pkg_id=c.package_id)

        g.add_node(
            node_id,
            label=node_label_format.format(crate=c, crate_package=packages[c.id]),
            crate=c,
            crate_package=packages[c.id],
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


def get_graph_groups(
    group_attrs: Sequence[str], g: nx.DiGraph
) -> Dict[str, Dict[str, nx.DiGraph]]:
    "returns a next dict of grouper attr to group key to a list of node ids in that group"
    if not group_attrs:
        return g

    log.info("getting node groups by: {}".format(group_attrs))

    grouped_groups = {}
    for g_attr in group_attrs:
        grouper = GROUP_ATTRS[g_attr]
        groups = {}
        sorted_nodes = sorted(g.nodes.items(), key=grouper)
        for key, group in itertools.groupby(sorted_nodes, key=grouper):
            subgraph_node_ids = list(n[0] for n in group)
            groups[str(key)] = g.subgraph(subgraph_node_ids)
        grouped_groups[g_attr] = groups

    return grouped_groups


def to_pydot_subgraph(N: nx.DiGraph, cluster_id: int) -> pydot.Subgraph:
    """from

    https://github.com/networkx/networkx/blob/networkx-2.3/networkx/drawing/nx_pydot.py#L174
    with a 'subgraph' graph_type
    """
    graph_defaults = N.graph.get("graph", {})
    strict = nx.number_of_selfloops(N) == 0 and not N.is_multigraph()

    P = pydot.Subgraph("cluster{}".format(cluster_id), strict=strict, **graph_defaults)
    try:
        P.set_node_defaults(**N.graph["node"])
    except KeyError:
        pass
    try:
        P.set_edge_defaults(**N.graph["edge"])
    except KeyError:
        pass

    for n, nodedata in N.nodes(data=True):
        str_nodedata = dict((k, make_str(v)) for k, v in nodedata.items())
        p = pydot.Node(make_str(n), **str_nodedata)
        P.add_node(p)

    assert not N.is_multigraph()
    for u, v, edgedata in N.edges(data=True):
        str_edgedata = dict((k, make_str(v)) for k, v in edgedata.items())
        edge = pydot.Edge(make_str(u), make_str(v), **str_edgedata)
        P.add_edge(edge)

    return P


def group_graph_nodes(
    group_attrs: Sequence[str], g: nx.DiGraph, pdot: pydot.Graph
) -> pydot.Graph:
    """Groups nodes with matching attrs into single subgraph nodes
    """
    for g_attr, groups in get_graph_groups(group_attrs, g).items():
        if not g_attr:
            continue
        for key, subgraph in groups.items():
            if len(subgraph) < 2:
                continue
            log.debug(
                "adding subgraph for {} with {} nodes and {} edges".format(
                    key, len(subgraph), len(subgraph.edges)
                )
            )
            pdot.add_subgraph(to_pydot_subgraph(subgraph, 0))

    colors = ["blue", "red", "#db8625", "green", "gray", "cyan", "#ed125b"]
    for i, subgraph in enumerate(pdot.get_subgraphs()):
        # relabel subgraphs so they show up
        subgraph.set_name("cluster{}".format(i))
        subgraph.set_bgcolor(random.choice(colors))

    # TODO(#53): remove duplicate edges and nodes between subgraph and graph
    return pdot


@dataclass
class GraphStyle:
    label_substr: str
    # dot attrs at https://www.graphviz.org/doc/info/lang.html
    dot_attr_name: str
    dot_attr_value: str


def style_graph_nodes(styles: Sequence[Dict[str, str]], g: nx.DiGraph) -> nx.DiGraph:
    """Styles nodes with labels matching the style

    string. Rightmost / last style arg wins.
    """
    if not styles:
        return g

    styles = [GraphStyle(*s.split(":", 2)) for s in styles]
    log.debug("applying styles: {}".format(styles))

    for (nid, attrs) in g.nodes.items():
        for s in styles:
            if s.label_substr in attrs["label"]:
                g.nodes[nid][s.dot_attr_name] = s.dot_attr_value
    return g


def run_pipeline(source: rx.Observable, args: argparse.Namespace):
    pipeline = source.pipe(
        op.do_action(lambda x: log.debug("processing {!r}".format(x))),
        op.map(cargo_metadata_to_rust_crate_and_packages),
        op.map(functools.partial(rust_crates_and_packages_to_networkx_digraph, args)),
        op.map(functools.partial(filter_graph_nodes, args.filter)),
    )
    return pipeline


def serialize(args: argparse.Namespace, g: nx.DiGraph):
    # https://github.com/pydot/pydot/issues/169#issuecomment-378000510
    g = style_graph_nodes(args.style, g)
    pdot = to_pydot(g)
    pydot = group_graph_nodes(args.groupby, g, pdot)
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
