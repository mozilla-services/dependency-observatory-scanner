import asyncio
import aiohttp
import itertools
from typing import Any, AsyncGenerator, Dict, Iterable, Optional
import logging

log = logging.getLogger(f"fpr.clients.npmsio")
log.setLevel(logging.WARN)


def aiohttp_session():
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=4),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla-Dependency-Observatory/g-k",
        },
        raise_for_status=True,
    )


async def async_query(
    session: aiohttp.ClientSession, json: Iterable[str], dry_run: bool
) -> Optional[Dict]:
    url = "https://api.npms.io/v2/package/mget"
    log.debug(f"posting {json} to {url}")
    response_json: Optional[Dict] = None
    if dry_run:
        log.warn(f"in dry run mode: skipping POST")
    else:
        response = await session.post(url, json=json)
        response_json = await response.json()
    log.debug(f"got response json {response_json!r}")
    return response_json


def grouper(iterable: Iterable[Any], n: int, fillvalue: Any = None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    # from https://docs.python.org/3/library/itertools.html#itertools-recipes
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


async def fetch_npmsio_scores(
    package_names: Iterable[str], pkgs_per_request: int = 100, dry_run: bool = False
) -> AsyncGenerator[Dict[str, Dict], None]:
    """
    Fetches npms.io score and analysis for one or more node package names

    Uses: https://api-docs.npms.io/#api-Package-GetMultiPackageInfo
    """
    async with aiohttp_session() as s:
        group_results = await asyncio.gather(
            *[
                async_query(
                    s,
                    [
                        package_name
                        for package_name in group
                        if package_name is not None
                    ],
                    dry_run,
                )
                for group in grouper(package_names, pkgs_per_request)
                if group is not None
            ]
        )
        # NB: org/scope e.g. "@babel" in @babel/babel is flattened into the scope field.
        # pull {data1}, {data2} from {package_name_1: {data1}, package_name_2: {data2}}
        for group_result in group_results:
            if group_result is None:
                continue

            for result in group_result.values():
                yield result
