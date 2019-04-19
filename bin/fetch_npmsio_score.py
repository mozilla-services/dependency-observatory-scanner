#!/usr/bin/env python

"""
Fetches npms.io score and analysis for one or more node package names and saves them to ./<output_dir>/dependency_npmsio_scores.json

Uses: https://api-docs.npms.io/#api-Package-GetMultiPackageInfo

Example usage:

bin/fetch_npmsio_score.py hapi
"""

import os
import sys

import argparse
import asyncio
import aiohttp
import json
import pathlib
import itertools
import time


def aiohttp_session():
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=4),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla-Dependency-Observatory/g-k",
        },
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch npms.io score", usage=__doc__)

    parser.add_argument(
        "-o",
        "--output-dir",
        type=pathlib.Path,
        default="output",
        help="Output directory to write repo metadata",
    )

    parser.add_argument(
        "--append-results",
        action="store_true",
        default=False,
        help="Append results to the file in the output directory instead of truncating them",
    )

    parser.add_argument(
        "package_names", type=str, nargs="+", help="npm names e.g. 'hapi'"
    )

    return parser.parse_args()


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


async def async_query(session, json):
    url = "https://api.npms.io/v2/package/mget"
    response = await session.post(url, json=json)
    response_json = await response.json()
    return response_json


async def async_main(package_names):
    pkgs_per_request = 2
    async with aiohttp_session() as s:
        tasks = []
        for group in grouper(package_names, pkgs_per_request):
            group = list(filter(None, group))
            tasks.append(asyncio.ensure_future(async_query(s, group)))
        await asyncio.gather(*tasks)
        return list(zip(package_names, tasks))


def run(args):
    loop = asyncio.get_event_loop()
    async_results = loop.run_until_complete(async_main(args.package_names))

    results = []
    for package_names, task in async_results:
        if not isinstance(task, asyncio.Task) and isinstance(task, str):  # dry run
            print(org_repo, task)
            continue
        if not task.done():
            print("task for ", org_repo, "still running somehow", file=sys.stderr)
            continue
        if task.cancelled():
            print("task for ", org_repo, "was cancelled", file=sys.stderr)
            continue
        if task.exception():
            print("task for ", org_repo, "errored.", file=sys.stderr)
            task.print_stack()
            continue
        result = task.result()
        if result is None:
            print("task for ", org_repo, "returned result None.", file=sys.stderr)
            continue

        results.append((package_names, result))

    return results


def main():
    args = parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    fout_path = args.output_dir / pathlib.Path("dependency_npmsio_scores.json")

    with open(fout_path, "a" if args.append_results else "w") as fout:
        for package_names, results in run(args):
            # flatten {package_name_1: {data1}, package_name_2: {data2}}
            # to [{data1}, {data2}]
            for result in results.values():
                json.dump(result, fout, sort_keys=True)

                # BigQuery wants newline delimited JSON
                # https://cloud.google.com/bigquery/docs/loading-data-cloud-storage-json
                fout.write("\n")


if __name__ == "__main__":
    main()
