#!/usr/bin/env python

"""
find-package-rugaru
"""

import argparse
import asyncio
import functools
import logging
import os
import sys
import json

from fpr.pipelines import pipelines
from fpr.pipelines.util import exc_to_str
from fpr.rx_util import save_to_tmpfile

log = logging.getLogger("fpr")
log.setLevel(logging.DEBUG)
fh = logging.FileHandler("fpr-debug.log")
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)
ch.setFormatter(formatter)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Runs a single pipeline", usage=__doc__
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug logging to the console",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=False,
        help="don't log anything to the console",
    )
    parser.add_argument(
        "--save-to-tmpfile",
        action="store_true",
        default=False,
        help="Save unserialized and serizalized results to temp files. Defaults to False.",
    )

    subparsers = parser.add_subparsers(help="available pipelines", dest="pipeline_name")
    for pipeline in pipelines:
        pipeline_parser = subparsers.add_parser(pipeline.name, help=pipeline.desc)
        pipeline.argparser(pipeline_parser)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.verbose:
        ch.setLevel(logging.DEBUG)

    # add the handlers to the logger
    log.addHandler(fh)
    log.addHandler(ch)

    if args.quiet:
        log.removeHandler(ch)

    _scrub_arg_names = {"github_auth_token", "npm_auth_token"}
    debug_args = {k: v for (k, v) in vars(args).items() if k not in _scrub_arg_names}
    log.debug(f"args: {debug_args}")

    loop = asyncio.get_event_loop()
    asyncio.set_event_loop(loop)

    pipeline = next(p for p in pipelines if p.name == args.pipeline_name)
    log_line = (
        f"running pipeline {args.pipeline_name} on {args.infile.name} writing to "
        f"{args.outfile.name}"
    )
    if args.append_outfile:
        log_line += f"and appending to {args.append_outfile.name}"
    log.info(log_line)

    async def main():
        async for row in pipeline.runner(pipeline.reader(args.infile), args):
            if args.save_to_tmpfile:
                save_to_tmpfile(
                    f"{args.pipeline_name}_unserialized_", file_ext=".pickle", item=row
                )

            try:
                serialized = pipeline.serializer(args, row)
                if args.save_to_tmpfile:
                    save_to_tmpfile(
                        f"{args.pipeline_name}_serialized_",
                        file_ext=".json",
                        item=serialized,
                    )
                writer = getattr(pipeline, "writer")
                writer(args.outfile, serialized)
                if args.append_outfile:
                    writer(args.append_outfile, serialized)
            except Exception as e:
                log.error(
                    f"error serializing result for {args.pipeline_name} pipeline:\n{exc_to_str()}"
                )

    try:
        asyncio.run(main(), debug=False)
    except Exception as e:
        log.error(f"error running {args.pipeline_name} pipeline:\n{exc_to_str()}")

    log.info(f"pipeline {args.pipeline_name} finished")


if __name__ == "__main__":
    main()
