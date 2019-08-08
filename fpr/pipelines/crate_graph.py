import logging
import json
from typing import Dict

import networkx as nx
from networkx.drawing.nx_pydot import to_pydot
import rx
import rx.operators as op

from fpr.rx_util import on_next_save_to_file
from fpr.serialize_util import extract_fields, get_in
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.crate_tree")

pipeline_name = name = "crate_tree"
pipeline_reader = reader = lambda infile: [json.load(infile)]
pipeline_writer = writer = on_next_save_to_file


def cargo_metadata_pipeline_to_networkx_digraph(cargo_meta_out: Dict) -> "Digraph":
    log.debug(
        "running crate-tree on {0[cargo_tomlfile_path]} in {0[org]}/{0[repo]} at {0[commit]} ".format(
            cargo_meta_out
        )
    )
    assert (
        get_in(cargo_meta_out, ["metadata", "version"]) == 1
    ), "cargo metadata format was not version 1"

    def clean_pkgid(s):
        """strip off trailing:
        ' (registry+https://github.com/rust-lang/crates.io-index)' from
        pkgids so we only show the package name and version number
        """
        return s.split(" (")[0]

    g = nx.DiGraph()
    for n in get_in(cargo_meta_out, ["metadata", "nodes"]):
        n["id"] = clean_pkgid(n["id"])
        g.add_node(n["id"])  # , **extract_fields(n, {"id", "features"}))
        for dep in n["deps"]:
            g.add_edge(n["id"], clean_pkgid(dep["pkg"]))  # , name=dep["name"])
    return g


def run_pipeline(source):
    pipeline = source.pipe(
        op.do_action(lambda x: log.debug("processing {!r}".format(x))),
        op.map(cargo_metadata_pipeline_to_networkx_digraph),
    )
    return pipeline


def serialize(g: "DiGraph"):
    pdot = to_pydot(g)
    pdot.set("rankdir", "LR")
    return str(pdot)
