import argparse
from dataclasses import dataclass
import functools
import itertools
import logging
import json
import random
from typing import Dict, Tuple, Sequence, Iterable, Generator, AsyncGenerator

import networkx as nx
from networkx.drawing.nx_pydot import to_pydot
from networkx.utils import make_str
import pydot

from fpr.rx_util import on_next_save_to_jsonl
from fpr.graph_util import npm_packages_to_networkx_digraph, get_graph_stats
from fpr.models.pipeline import Pipeline
from fpr.models.nodejs import NPMPackage
from fpr.models.pipeline import (
    add_infile_and_outfile,
    add_graphviz_graph_args,
    NODE_ID_FORMATS,
    NODE_LABEL_FORMATS,
    GROUP_ATTRS,
)
from fpr.serialize_util import extract_fields, get_in, iter_jsonlines
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.dep_graph")

__doc__ = """Parses the output of the cargo metadata pipeline and writes a .dot
file of the dependencies to outfile"""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_graphviz_graph_args(parser)
    return parser


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
        return {}

    log.info("getting node groups by: {}".format(group_attrs))

    grouped_groups: Dict[str, Dict[str, nx.DiGraph]] = {}
    for g_attr in group_attrs:
        grouper = GROUP_ATTRS[g_attr]
        groups: Dict[str, nx.DiGraph] = {}
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


def strip_crate_and_package_attrs(pdot: pydot.Graph):
    """Remove crate and crate_package attrs from nodes, since it can
    break graphviz dot rendering"""
    for node in pdot.get_nodes():
        del node.obj_dict["attributes"]["crate"]
        del node.obj_dict["attributes"]["crate_package"]


def group_graph_nodes(
    group_attrs: Sequence[str], g: nx.DiGraph, pdot: pydot.Graph
) -> None:
    """Groups nodes with matching attrs into single subgraph nodes
    """
    # TODO(#53): remove duplicate edges and nodes between subgraph and graph
    if not group_attrs:
        return

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

    for i, pdot_subgraph in enumerate(pdot.get_subgraphs()):
        # relabel subgraphs so they show up
        relabel_subgraph(pdot_subgraph, i)


def relabel_subgraph(subgraph: pydot.Subgraph, new_label_id: int) -> None:
    colors = ["blue", "red", "#db8625", "green", "gray", "cyan", "#ed125b"]
    subgraph.set_name("cluster{}".format(new_label_id))
    subgraph.set(
        "bgcolor", random.choice(colors)
    )  # workaround mypy failing to resolve pydot.Common dynamic setter for set_bgcolor


@dataclass
class GraphStyle:
    label_substr: str
    # dot attrs at https://www.graphviz.org/doc/info/lang.html
    dot_attr_name: str
    dot_attr_value: str


def style_graph_nodes(styles: Iterable[str], g: nx.DiGraph) -> nx.DiGraph:
    """Styles nodes with labels matching the style

    string. Rightmost / last style arg wins.
    """
    if not styles:
        return g

    parsed_styles = [GraphStyle(*s.split(":", 2)) for s in styles]
    log.debug("applying styles: {}".format(parsed_styles))

    for (nid, attrs) in g.nodes.items():
        for s in parsed_styles:
            if s.label_substr in attrs["label"]:
                g.nodes[nid][s.dot_attr_name] = s.dot_attr_value
    return g


async def run_pipeline(
    source: Generator[Dict, None, None], args: argparse.Namespace
) -> AsyncGenerator[nx.DiGraph, None]:
    log.info(f"pipeline {pipeline.name} started")
    for item in source:
        nx_graph: nx.DiGraph = npm_packages_to_networkx_digraph(
            NPMPackage(**package_dict) for package_dict in item.get("dependencies", [])
        )
        log.info(f"graph stats {get_graph_stats(nx_graph)}")
        filtered_graph: nx.DiGraph = filter_graph_nodes(args.filter, nx_graph)
        yield filtered_graph


def serialize(args: argparse.Namespace, g: nx.DiGraph) -> Dict[str, str]:
    # https://github.com/pydot/pydot/issues/169#issuecomment-378000510
    g = style_graph_nodes(args.style, g)
    pdot: pydot.Graph = to_pydot(g)
    group_graph_nodes(args.groupby, g, pdot)
    pdot.set("rankdir", "LR")
    return {"dep_graph_pdot": str(pdot), "dot_filename": args.dot_filename}


pipeline = Pipeline(
    name="dep_graph",
    desc=__doc__,
    fields=set(),
    argparser=parse_args,
    reader=iter_jsonlines,
    runner=run_pipeline,
    serializer=serialize,
    writer=on_next_save_to_jsonl,
)
