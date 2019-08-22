import argparse
import sys
from dataclasses import dataclass, field
from typing import AbstractSet, Callable, Optional


def add_infile_and_outfile(
    pipeline_parser: argparse.ArgumentParser
) -> argparse.ArgumentParser:
    pipeline_parser.add_argument(
        "-i",
        "--infile",
        type=argparse.FileType("r", encoding="UTF-8"),
        required=False,
        default=sys.stdin,
        help="pipeline input file (use '-' for stdin)",
    )
    pipeline_parser.add_argument(
        "-o",
        "--outfile",
        type=argparse.FileType("w", encoding="UTF-8"),
        required=False,
        default=sys.stdout,
        help="pipeline output file (defaults to stdout)",
    )
    return pipeline_parser


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


def add_graphviz_graph_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
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


@dataclass
class Pipeline:
    """
    A Pipeline to run. run_pipeline.py will:

    0. use the .argparser to read any additional program arguments
    1. read the infile with .reader
    2. process the parsed infile with .runner
    3. optionally serializer the processed result with .serializer
    4. write the output to outfile with .writer
    """

    # pipeline name
    name: str
    # pipeline description
    desc: str

    # top-level fields to serialize
    fields: AbstractSet[str]

    reader: Callable
    runner: Callable
    serializer: Optional[Callable]
    writer: Callable
    argparser: Optional[Callable] = field(default=add_infile_and_outfile)
