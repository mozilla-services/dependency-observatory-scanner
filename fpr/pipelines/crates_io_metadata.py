import argparse
import asyncio
import logging
from typing import Dict, Tuple, AsyncGenerator, Generator

import aiohttp

from fpr.db import (
    connect,
    create_crates_io_meta_table,
    crate_name_in_db,
    save_crate_meta,
)
from fpr.rx_util import on_next_save_to_jsonl
from fpr.serialize_util import iter_jsonlines
from fpr.models import RustCrate, Pipeline, SerializedCargoMetadata
from fpr.models.rust import cargo_metadata_to_rust_crates
from fpr.models.pipeline import add_infile_and_outfile, add_db_arg
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.crates_io_metadata")

__doc__ = """Given cargo metadata output fetches metadata from the crates.io
registry for the resolved packages and outputs them to jsonl and saves them to
a local SQLite3 DB.

Assumes crates are on crates.io.
"""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_db_arg(parser)
    parser.add_argument(
        "--user-agent",
        type=str,
        default="https://github.com/mozilla-services/find-package-rugaru (foxsec+fpr@mozilla.com)",
        help="User agent to user to query crates.io",
    )
    parser.add_argument(
        "--total-timeout",
        type=int,
        default=240,
        help="aiohttp total timeout in seconds (defaults to 240)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="time to sleep between requests in seconds (defaults to 0.5)",
    )
    return parser


async def fetch_crates_io_metadata(session, url):
    log.debug("fetching crates-io-metadata for {!r}".format(url))
    async with session.get(url) as resp:
        return await resp.json()


async def run_pipeline(
    source: Generator[SerializedCargoMetadata, None, None], args: argparse.Namespace
) -> AsyncGenerator[Dict, None]:
    log.info("pipeline crates_io_metadata started")

    rust_crate_dicts: Generator[Dict[str, RustCrate], None, None] = (
        cargo_metadata_to_rust_crates(cargo_meta) for cargo_meta in source
    )

    with connect(args.db) as connection:
        cursor = connection.cursor()
        create_crates_io_meta_table(cursor)

        async with aiohttp.ClientSession(
            headers={"User-Agent": args.user_agent},
            timeout=aiohttp.ClientTimeout(total=args.total_timeout),
            raise_for_status=True,
        ) as session:
            for rust_crate_dict in rust_crate_dicts:
                for rust_crate in rust_crate_dict.values():
                    if crate_name_in_db(cursor, rust_crate.package_id.name):
                        log.debug(
                            "skipping crate {} already in the DB".format(
                                rust_crate.package_id.name
                            )
                        )
                        continue

                    url = rust_crate.package_id.crates_io_metadata_url
                    if url is None:
                        log.info(
                            "skipping crate {} with non-registry source".format(
                                rust_crate.package_id
                            )
                        )
                        continue
                    await asyncio.sleep(args.delay)
                    try:
                        response = await fetch_crates_io_metadata(session, url)
                    except Exception as e:
                        log.error(
                            "error fetching crates-io-metadata for {}:\n{}".format(
                                url, exc_to_str()
                            )
                        )
                    save_crate_meta(cursor, response)
                    connection.commit()
                    log.debug(
                        "saved crate {} to the DB".format(response["crate"]["name"])
                    )
                    yield response


FIELDS = {"crate", "categories", "keywords", "versions"}


def serialize(_: argparse.Namespace, result: Dict) -> Dict:
    return result


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
