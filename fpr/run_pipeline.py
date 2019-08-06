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
from typing import IO
import json

import rx
import rx.operators as op
from rx.scheduler.eventloop import AsyncIOScheduler

import fpr.pipelines
import fpr.pipelines.cargo_audit
import fpr.pipelines.cargo_metadata
from fpr.pipelines.util import exc_to_str
from fpr.serialize_util import iter_jsonlines

log = logging.getLogger("fpr")
log.setLevel(logging.DEBUG)
fh = logging.FileHandler("fpr-debug.log")
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
log.addHandler(fh)
log.addHandler(ch)


def parse_args():
    parser = argparse.ArgumentParser(description="", usage=__doc__)

    parser.add_argument(
        "pipeline_name",
        type=str,
        choices=["cargo_audit", "cargo_metadata"],
        help="pipeline step or name torun",
    )
    parser.add_argument(
        "infile",
        type=argparse.FileType("r", encoding="UTF-8"),
        help="pipeline input file (use '-' for stdin)",
    )
    parser.add_argument(
        "-o",
        "--outfile",
        type=argparse.FileType("w", encoding="UTF-8"),
        required=False,
        default=sys.stdout,
        help="pipeline output file (defaults to stdout)",
    )
    return parser.parse_args()


def on_next_save_to_jsonl(outfile: IO, item):
    log.debug("saving final pipeline item to {0}:\n{1}".format(outfile, item))
    line = "{}\n".format(json.dumps(item))
    outfile.write(line)
    log.debug("wrote jsonl to {0}:\n{1}".format(outfile, line))


def on_serialize_error(pipeline_name, e, *args):
    log.error(
        "error serializing result for {} pipeline:\n{}".format(
            pipeline_name, exc_to_str()
        )
    )


def on_error(pipeline_name, e, *args):
    log.error("error running {} pipeline:\n{}".format(pipeline_name, exc_to_str()))


def on_completed(loop):
    log.info("pipeline finished")
    loop.stop()
    log.debug("on_completed done!")


def main():
    args = parse_args()
    log.debug("args: {}".format(args))

    loop = asyncio.get_event_loop()
    asyncio.set_event_loop(loop)
    aio_scheduler = AsyncIOScheduler(loop=loop)  # NB: not thread safe

    pipeline = getattr(fpr.pipelines, args.pipeline_name)

    log.info(
        "running pipeline {0.pipeline_name} on {0.infile.name} writing to {0.outfile.name}".format(
            args
        )
    )
    source = rx.from_iterable(iter_jsonlines(args.infile))
    pipeline.run_pipeline(source).pipe(
        op.map(pipeline.serialize),
        op.catch(functools.partial(on_serialize_error, args.pipeline_name)),
    ).subscribe(
        on_next=functools.partial(on_next_save_to_jsonl, args.outfile),
        on_error=functools.partial(on_error, args.pipeline_name),
        on_completed=functools.partial(on_completed, loop=loop),
        scheduler=aio_scheduler,
    )
    loop.run_forever()
    log.debug("main finished!")


if __name__ == "__main__":
    main()
