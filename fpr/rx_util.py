import asyncio
import functools
import json
import logging
import pickle
import tempfile
from typing import Dict, IO, Tuple, Any


log = logging.getLogger("fpr.rx_util")


async def sleep_by_index(sleep_per_index: float, item: Tuple[int, Any]):
    i, val = item
    log.debug("got index {} sleeping for {} seconds".format(i, sleep_per_index * i))
    await asyncio.sleep(sleep_per_index * i)
    return val


def save_to_tmpfile(prefix: str, item: Dict, file_ext=".json"):
    "Serializes item to JSON and saves it to a named temp file with the given prefix"
    if file_ext == ".json":
        with tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", prefix=prefix, suffix=file_ext, delete=False
        ) as tmpout:
            try:
                json.dump(item, tmpout, sort_keys=True, indent=2)
                log.debug("saved to {}".format(tmpout.name))
            except TypeError as e:
                log.debug(
                    "error dumping JSON to save item to {}: {}".format(tmpout.name, e)
                )
    elif file_ext == ".pickle":
        with tempfile.NamedTemporaryFile(
            mode="w+b", prefix=prefix, suffix=file_ext, delete=False
        ) as tmpout:
            try:
                pickle.dump(item, tmpout)
                log.debug("saved to {}".format(tmpout.name))
            except Exception as e:
                log.debug(
                    "error pickling to save item to {}: {}".format(tmpout.name, e)
                )
    else:
        log.debug(
            "unknown type {} to dump {} item to temp file".format(file_ext, type(item))
        )


def on_next_save_to_jsonl(outfile: IO, item):
    log.debug("saving final pipeline item to {0}:\n{1}".format(outfile, item))
    line = "{}\n".format(json.dumps(item))
    outfile.write(line)
    log.debug("wrote jsonl to {0}:\n{1}".format(outfile, line))


def on_next_save_to_file(outfile: IO, item):
    log.debug("saving final pipeline item to {0}:\n{1}".format(outfile, item))
    outfile.write(item)
    log.debug("wrote to {0}:\n{1}".format(outfile, item))
