import argparse
import asyncio
import logging
import sqlite3
from typing import Callable, Dict, Tuple, AsyncGenerator, Generator, Optional, Iterable

import aiohttp

from fpr.db import (
    connect,
    create_crates_io_meta_table,
    crate_name_in_db,
    save_crate_meta,
)
from fpr.rx_util import on_next_save_to_jsonl
from fpr.serialize_util import iter_jsonlines
from fpr.models import RustPackageID, Pipeline, SerializedCargoMetadata
from fpr.models.rust import cargo_metadata_to_rust_crates
from fpr.models.pipeline import add_infile_and_outfile, add_db_arg, add_aiohttp_args
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.crates_io_metadata")

__doc__ = """Given cargo metadata output fetches metadata from the crates.io
registry for the resolved packages and outputs them to jsonl and a local
SQLite3 DB.

Assumes all crates with non-file source are on crates.io and reads all cargo
metadata into memory.
"""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_db_arg(parser)
    parser = add_aiohttp_args(parser)
    return parser


async def fetch_crates_io_metadata(
    args: argparse.Namespace, session: aiohttp.ClientSession, url: str
) -> Optional[Dict]:
    await asyncio.sleep(args.delay)
    try:
        log.debug("fetching crates-io-metadata for {!r}".format(url))
        async with session.get(url) as resp:
            response_json = await resp.json()
    except Exception as e:
        log.error(
            "error fetching crates-io-metadata for {}:\n{}".format(url, exc_to_str())
        )
        raise e

    return response_json


async def run_pipeline(
    source: Generator[SerializedCargoMetadata, None, None], args: argparse.Namespace
) -> AsyncGenerator[Dict, None]:
    log.info("pipeline crates_io_metadata started")
    rust_crate_ids: Generator[RustPackageID, None, None] = (
        rust_crate.package_id
        for cargo_meta in source
        for rust_crate in cargo_metadata_to_rust_crates(cargo_meta).values()
    )

    async with aiohttp.ClientSession(
        headers={"User-Agent": args.user_agent},
        timeout=aiohttp.ClientTimeout(total=args.total_timeout),
        connector=aiohttp.TCPConnector(limit=args.max_connections),
        raise_for_status=True,
    ) as session:
        tasks: Dict[str, asyncio.Future] = {}
        for rust_crate_id in rust_crate_ids:
            url = rust_crate_id.crates_io_metadata_url
            if url is None:
                log.info(
                    "skipping crate {} with non-registry source".format(rust_crate_id)
                )
                continue
            if url in tasks:
                log.debug(
                    "skipping duplicate crate url {} for {}".format(url, rust_crate_id)
                )
                continue
            tasks[url] = asyncio.create_task(
                fetch_crates_io_metadata(args, session, url)
            )

        await asyncio.gather(*tasks.values())
        for task_url, task in tasks.items():
            assert task.done()
            assert isinstance(task, asyncio.Task)
            if task.cancelled():
                log.warn("task fetching {} was cancelled".format(task_url))
                continue
            if task.exception():
                log.error("task fetching {} errored".format(task_url))
                task.print_stack()
                continue
            response = task.result()
            if response is None:
                log.debug("task fetching {} returned result None".format(task_url))
                continue
            yield response


FIELDS = {"crate", "categories", "keywords", "versions"}


def serialize(args: argparse.Namespace, response_json: Dict) -> Dict:
    crate_name = response_json["crate"]["name"]
    with connect(args.db) as connection:
        cursor = connection.cursor()
        create_crates_io_meta_table(cursor, drop_if_exists=False)

        if crate_name_in_db(cursor, crate_name):
            log.debug("skipping crate {} already in the DB".format(crate_name))
        else:
            save_crate_meta(cursor, response_json)
            connection.commit()
            log.debug("saved crate {} to the DB".format(crate_name))
    return response_json


pipeline = Pipeline(
    name="crates_io_metadata",
    desc=__doc__,
    argparser=parse_args,
    fields=FIELDS,
    reader=iter_jsonlines,
    runner=run_pipeline,
    serializer=serialize,
    writer=on_next_save_to_jsonl,
)
