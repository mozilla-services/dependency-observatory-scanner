import argparse
import sys
from dataclasses import dataclass, field
from typing import AbstractSet, Callable, Optional

from fpr.graph_util import NODE_ID_FORMATS, NODE_LABEL_FORMATS, GROUP_ATTRS


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
    pipeline_parser.add_argument(
        "-a",
        "--append-outfile",
        type=argparse.FileType("a", encoding="UTF-8"),
        required=False,
        default=None,
        help="Output file to append to instead of overwriting like outfile (defaults to None)",
    )
    return pipeline_parser


def add_db_arg(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    pipeline_parser.add_argument(
        "--db",
        type=str,
        default=":memory:",
        help="SQLite3 database name to save crates io metadata to. Defaults to :memory:",
    )
    return pipeline_parser


def add_aiohttp_args(
    pipeline_parser: argparse.ArgumentParser
) -> argparse.ArgumentParser:
    pipeline_parser.add_argument(
        "--user-agent",
        type=str,
        default="https://github.com/mozilla-services/find-package-rugaru (foxsec+fpr@mozilla.com)",
        help="User agent to user to query crates.io",
    )
    pipeline_parser.add_argument(
        "--total-timeout",
        type=int,
        default=240,
        help="aiohttp total timeout in seconds (defaults to 240)",
    )
    pipeline_parser.add_argument(
        "--max-connections",
        type=int,
        default=100,
        help="number of simultaneous connections (defaults to 100)",
    )
    pipeline_parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="time to sleep between requests in seconds (defaults to 0.5)",
    )
    return pipeline_parser


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
    parser.add_argument(
        "--dot-filename",
        type=str,
        default="output.dot",
        help="crate graph dotfile output name",
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
