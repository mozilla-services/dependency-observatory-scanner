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

    log.debug("args: {}".format(args))

    loop = asyncio.get_event_loop()
    asyncio.set_event_loop(loop)

    pipeline = next(p for p in pipelines if p.name == args.pipeline_name)
    if args.append_outfile:
        log.info(
            "running pipeline {0.pipeline_name} on {0.infile.name} writing to "
            "{0.outfile.name} and appending to {0.append_outfile.name}".format(args)
        )
    else:
        log.info(
            "running pipeline {0.pipeline_name} on {0.infile.name} writing to "
            "{0.outfile.name}".format(args)
        )

    async def main():
        async for row in pipeline.runner(pipeline.reader(args.infile), args):
            save_to_tmpfile(
                "{}_unserialized_".format(args.pipeline_name),
                file_ext=".pickle",
                item=row,
            )
            try:
                serialized = pipeline.serializer(args, row)
            except Exception as e:
                log.error(
                    "error serializing result for {} pipeline:\n{}".format(
                        args.pipeline_name, exc_to_str()
                    )
                )
            save_to_tmpfile(
                "{}_serialized_".format(args.pipeline_name),
                file_ext=".json",
                item=serialized,
            )
            writer = getattr(pipeline, "writer")
            writer(args.outfile, serialized)
            if args.append_outfile:
                writer(args.append_outfile, serialized)

    try:
        asyncio.run(main(), debug=False)
    except Exception as e:
        log.error(
            "error running {} pipeline:\n{}".format(args.pipeline_name, exc_to_str())
        )

    log.info("pipeline finished")
    log.debug("main finished!")


if __name__ == "__main__":
    main()
