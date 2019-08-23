import argparse
import logging
from typing import Dict, Tuple, Set, Any

import networkx as nx

from fpr.models.rust import RustCrate, RustPackageID, RustPackage

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


def get_new_removed_and_new_total(lset, rset) -> Tuple[Set[Any], Set[Any], int]:
    new = rset - lset
    removed = lset - rset
    new_total = len(rset)
    return new, removed, new_total
