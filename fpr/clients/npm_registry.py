import argparse
import asyncio
import aiohttp
import itertools
from typing import Any, AsyncGenerator, Dict, Iterable, Optional
import logging

log = logging.getLogger(f"fpr.clients.npm_registry")
log.setLevel(logging.WARN)


def aiohttp_session(args: argparse.Namespace) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": args.user_agent,
        },
        timeout=aiohttp.ClientTimeout(total=args.total_timeout),
        connector=aiohttp.TCPConnector(limit=args.max_connections),
        raise_for_status=True,
    )


async def async_query(
    session: aiohttp.ClientSession, package_name: str, dry_run: bool
) -> Optional[Dict]:
    # NB: scoped packages OK e.g. https://registry.npmjs.com/@babel/core
    url = f"https://registry.npmjs.com/{package_name}"
    response_json: Optional[Dict] = None
    if dry_run:
        log.warn(f"in dry run mode: skipping GET {url}")
        return response_json

    try:
        log.debug(f"GET {url}")
        response = await session.get(url)
        response_json = await response.json()
        return response_json
    except aiohttp.ClientResponseError as err:
        if err.status == 404:
            log.warn(f"{url} not found: {err}")
            return None
        raise err


async def fetch_npm_registry_metadata(
    args: argparse.Namespace, package_names: Iterable[str]
) -> AsyncGenerator[Dict[str, Dict], None]:
    """
    Fetches npm registry metadata for one or more node package names
    """
    async with aiohttp_session(args) as s:
        results = await asyncio.gather(
            *[
                async_query(s, package_name, args.dry_run)
                for package_name in package_names
                if package_name is not None
            ]
        )
        for result in results:
            if result is not None:
                yield result
