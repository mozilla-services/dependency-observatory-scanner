import argparse
import logging
from typing import AbstractSet, Any, Dict, Iterable, List, Tuple, TypeVar, Set, Union

import networkx as nx

from fpr.models.nodejs import NPMPackage
from fpr.models.rust import RustCrate, RustPackageID, RustPackage

T = TypeVar("T")

log = logging.getLogger("fpr.models.graph_util")


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


def npm_packages_to_networkx_digraph(packages: Iterable[NPMPackage]) -> nx.DiGraph:
    g = nx.DiGraph()
    for package in packages:
        node_id = package.package_id
        g.add_node(node_id, label=node_id)
        for dep_id in package.dependencies:
            g.add_edge(node_id, dep_id)
    return g


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


def get_authors(g: nx.DiGraph) -> Set[str]:
    return {
        author
        for (nid, n) in g.nodes(data=True)
        for author in n["crate_package"].authors or []
        if author
    }


def get_repos(g: nx.DiGraph) -> Set[str]:
    return {n["crate_package"].repository for (nid, n) in g.nodes(data=True)}


def has_changes(result: Dict) -> bool:
    for k, v in result.items():
        if not isinstance(v, dict):
            continue
        if "new" in v:
            if len(v["new"]):
                return True
        if "old" in v:
            if len(v["removed"]):
                return True
    return False


def get_new_removed_and_new_total(
    lset: AbstractSet[T], rset: AbstractSet[T]
) -> Tuple[AbstractSet[T], AbstractSet[T], int]:
    new = rset - lset
    removed = lset - rset
    new_total = len(rset)
    return new, removed, new_total


def get_graph_stats(g: nx.DiGraph) -> Dict[str, Union[int, bool, List[int], List[str]]]:
    stats = dict(
        node_count=g.number_of_nodes(),
        edge_count=g.number_of_edges(),
        # zero (no edges) to one (complete / all nodes directly linked to each other)
        density=nx.density(g),
        # list index is the degree count, value is the number of nodes with that degree (# of adjacent nodes)
        degree_histograph=nx.classes.function.degree_histogram(g),  # List[int]
        is_dag=nx.algorithms.dag.is_directed_acyclic_graph(g),  # bool
    )

    if stats["is_dag"]:
        # longest/deepest path through the DAG
        stats["longest_path"] = nx.algorithms.dag.dag_longest_path(g)  # List[str]
        stats["longest_path_length"] = len(stats["longest_path"])
    else:
        stats["cycle"] = list(nx.find_cycle(g))

    # number of edges pointing to a node
    stats["average_in_degree"] = sum(d for n, d in g.in_degree()) / float(
        stats["node_count"]
    )

    # number of edges a node points to
    stats["average_out_degree"] = sum(d for n, d in g.out_degree()) / float(
        stats["node_count"]
    )
    # NB: avg in and out degrees should be equal

    return stats
