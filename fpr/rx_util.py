import asyncio
import functools
import json
import logging
import tempfile
from typing import Dict, IO

import rx
import rx.operators as op


log = logging.getLogger("fpr.rx_util")


def do_async(func, *args, **kwds):
    @functools.wraps(func)
    def wrapper(*fargs, **fkwds):
        return rx.from_future(asyncio.create_task(func(*fargs, **fkwds)))

    return wrapper


def map_async(func, *args, **kwds):
    return op.flat_map(do_async(func, *args, **kwds))


def save_to_tmpfile(prefix: str, item: Dict):
    "Serializes item to JSON and saves it to a named temp file with the given prefix"
    if not isinstance(item, Dict):
        log.debug("skipped saving non-dict {} item to temp file".format(type(item)))
        return

    with tempfile.NamedTemporaryFile(
        mode="w+", encoding="utf-8", prefix=prefix, delete=False
    ) as tmpout:
        json.dump(item, tmpout, sort_keys=True, indent=2)
        log.debug("saved to {}".format(tmpout.name))


def on_next_save_to_jsonl(outfile: IO, item):
    log.debug("saving final pipeline item to {0}:\n{1}".format(outfile, item))
    line = "{}\n".format(json.dumps(item))
    outfile.write(line)
    log.debug("wrote jsonl to {0}:\n{1}".format(outfile, line))


def on_next_save_to_file(outfile: IO, item):
    log.debug("saving final pipeline item to {0}:\n{1}".format(outfile, item))
    outfile.write(item)
    log.debug("wrote to {0}:\n{1}".format(outfile, item))
