#!/usr/bin/env python

"""
Fetches repo, language, manifest, dep metadata, and vuln alerts (if
accessible) for a github repo and saves it as CSVs files in
./<output_dir>/<response_type>.csv

Caches github graphql schema to: ./github_graphql_schema.json
This needs to be cleared manually to be updated.

Example usage:

$ GITHUB_PAT=$GITHUB_PERSONAL_ACCESS_TOKEN bin/fetch_github_metadata_for_repo.py mozilla/normandy
mozilla/normandy fetching repo page
mozilla/normandy fetched repo page with 7/7 langs, 23/23 dep manifests, and 0/0 vuln alerts
mozilla/normandy package.json fetched 33/33 deps
mozilla/normandy yarn.lock fetched 100/674 deps
...
mozilla/normandy recipe-server/client/actions/show-heartbeat/package.json fetched 0/0 deps
mozilla/normandy recipe-server/client/actions/preference-experiment/package.json fetched 0/0 deps
mozilla/normandy yarn.lock fetching 100 deps from manifest cursor None and dep cursor MTAw
mozilla/normandy yarn.lock fetched dep page w/ 100 deps for 200/674
...
mozilla/normandy yarn.lock fetched dep page w/ 100 deps for 600/674
mozilla/normandy yarn.lock fetching 100 deps from manifest cursor None and dep cursor NjAw
mozilla/normandy yarn.lock fetched dep page w/ 74 deps for 674/674
saving github_repo_metadata/mozilla/normandy.json
$
"""

# resources fetched:
#
# * the repo https://developer.github.com/v4/object/repository/
#
# repo's:
#
# * languages https://developer.github.com/v4/object/language/
# * manifests https://developer.github.com/v4/object/dependencygraphmanifest/
# * manifest deps https://developer.github.com/v4/object/dependencygraphdependency/
# * vulnerabilityAlerts (first 100) https://developer.github.com/v4/object/repositoryvulnerabilityalert/

# TODO: paginate vulnerabilityAlerts
# TODO: handle rate limits if that becomes an issue https://developer.github.com/v4/guides/resource-limitations/#rate-limit

import os
import sys

import asyncio
import argparse
import csv
import io
import pathlib

import quiz

from client import run
from serializer import ResponseType, serialize_result


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch github repo metadata", usage=__doc__
    )

    parser.add_argument(
        "-a",
        "--auth-token",
        default=os.environ.get("GITHUB_PAT", None),
        help="A github personal access token. Defaults GITHUB_PAT env var. It should have most of the scopes from https://developer.github.com/v4/guides/forming-calls/#authenticating-with-graphql",
    )

    parser.add_argument(
        "-o",
        "--output-dir",
        type=pathlib.Path,
        default="github_repo_metadata",
        help="Output directory to write repo metadata",
    )

    parser.add_argument(
        "--append-results",
        action='store_true',
        default=False,
        help="Append results to files in the output directory instead of truncating them.",
    )

    parser.add_argument(
        "org_repos",
        type=str,
        nargs="+",
        help="GH :org/:repo names e.g. 'mozilla-services/screenshots'",
    )

    return parser.parse_args()


def aggregate_by_type(async_result_iter):
    responses_by_type = {t: [] for t in iter(ResponseType)}
    for org_repo, result in async_result_iter:
        org_name, repo_name = org_repo.split("/", 1)
        base_dict = dict(org=org_name, repo=repo_name)

        for response_type, row in serialize_result(result.repository):
            row.update(base_dict)
            responses_by_type[response_type].append(row)
    return responses_by_type


def main():
    args = parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    for response_type, rows in aggregate_by_type(
        run(args.auth_token, args.org_repos)
    ).items():
        fout_path = args.output_dir / pathlib.Path(response_type.name.lower() + ".csv")
        print("saving {} items to {}".format(len(rows), fout_path), file=sys.stderr)
        with open(fout_path, "a" if args.append_results else "w") as fout:
            if not rows:
                print("no rows to save", file=sys.stderr)
                break
            writer = csv.DictWriter(fout, fieldnames=sorted(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
