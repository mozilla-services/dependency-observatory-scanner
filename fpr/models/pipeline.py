import argparse
import sys
from dataclasses import dataclass, field
from typing import AbstractSet, Callable, Optional


def add_infile_and_outfile(pipeline_parser: Callable) -> None:
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
