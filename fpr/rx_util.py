import asyncio
import functools
import json
import logging
import tempfile
from typing import Dict

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
