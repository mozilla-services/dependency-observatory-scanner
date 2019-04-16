#!/usr/bin/env python

"""
Fetches repo, language, manifest, dep metadata, and vuln alerts (if
accessible) for a github repo and saves it as CSVs files in
./:output_dir/:org_name/:repo_name/

Caches github graphql schema to: ./github_graphql_schema.json
This needs to be cleared manually to be updated.

Example usage:

$ GITHUB_PAT=$GITHUB_PERSONAL_ACCESS_TOKEN bin/fetch_github_metadata_for_repo.py mozilla/normandy
mozilla/normandy fetching repo page
mozilla/normandy fetched repo page with 7/7 langs, 23/23 dep manifests, and 0/0 vuln alerts
mozilla/normandy package.json fetched 33/33 deps
mozilla/normandy yarn.lock fetched 100/674 deps
mozilla/normandy docs/requirements.txt fetched 0/0 deps
mozilla/normandy mozjexl/package.json fetched 0/0 deps
mozilla/normandy requirements/constraints.txt fetched 60/60 deps
mozilla/normandy requirements/default.txt fetched 47/47 deps
mozilla/normandy requirements/docs.txt fetched 3/3 deps
mozilla/normandy requirements/py36_docs.txt fetched 3/3 deps
mozilla/normandy recipe-server/package-lock.json fetched 0/0 deps
mozilla/normandy recipe-server/package.json fetched 0/0 deps
mozilla/normandy recipe-client-addon/package.json fetched 0/0 deps
mozilla/normandy eslint-config-normandy/package.json fetched 0/0 deps
mozilla/normandy ci/circleci/requirements/constraints.txt fetched 0/0 deps
mozilla/normandy client/actions/console-log/package.json fetched 0/0 deps
mozilla/normandy recipe-server/requirements/default.txt fetched 0/0 deps
mozilla/normandy client/actions/opt-out-study/package.json fetched 0/0 deps
mozilla/normandy client/actions/show-heartbeat/package.json fetched 0/0 deps
mozilla/normandy functional_tests/requirements/constraints.txt fetched 0/0 deps
mozilla/normandy client/actions/preference-experiment/package.json fetched 0/0 deps
mozilla/normandy recipe-server/client/actions/console-log/package.json fetched 0/0 deps
mozilla/normandy recipe-server/client/actions/opt-out-study/package.json fetched 0/0 deps
mozilla/normandy recipe-server/client/actions/show-heartbeat/package.json fetched 0/0 deps
mozilla/normandy recipe-server/client/actions/preference-experiment/package.json fetched 0/0 deps
mozilla/normandy yarn.lock fetching 100 deps from manifest cursor None and dep cursor MTAw
mozilla/normandy yarn.lock fetched dep page w/ 100 deps for 200/674
mozilla/normandy yarn.lock fetching 100 deps from manifest cursor None and dep cursor MjAw
mozilla/normandy yarn.lock fetched dep page w/ 100 deps for 300/674
mozilla/normandy yarn.lock fetching 100 deps from manifest cursor None and dep cursor MzAw
mozilla/normandy yarn.lock fetched dep page w/ 100 deps for 400/674
mozilla/normandy yarn.lock fetching 100 deps from manifest cursor None and dep cursor NDAw
mozilla/normandy yarn.lock fetched dep page w/ 100 deps for 500/674
mozilla/normandy yarn.lock fetching 100 deps from manifest cursor None and dep cursor NTAw
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
import enum
import pathlib

import quiz

from .client import aiohttp_session


async def async_main(args):
    async with aiohttp_session() as s:
        async_exec = quiz.async_executor(
            url="https://api.github.com/graphql",
            auth=auth_factory(args.auth_token),
            client=s,
        )

        schema = await async_github_schema_from_cache_or_url(
            "github_graphql_schema.json", async_exec
        )

        tasks = []
        for org_repo in args.org_repos:
            tasks.append(
                asyncio.ensure_future(query_repo_data(schema, org_repo, async_exec))
            )

        await asyncio.gather(*tasks)
        return list(zip(args.org_repos, tasks))


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

    # parser.add_argument(
    #     "-n",
    #     "--dry-run",
    #     action='store_true',
    #     default=False,
    #     help="Don't run queries just fetch schema and print queries to run",
    # )

    parser.add_argument(
        "-o",
        "--output-dir",
        type=pathlib.Path,
        default="github_repo_metadata",
        help="Output directory to write repo metadata",
    )

    parser.add_argument(
        "org_repos",
        type=str,
        nargs="+",
        help="GH :org/:repo names e.g. 'mozilla-services/screenshots'",
    )

    return parser.parse_args()


class Sentinal:
    "A Sentinal type so we to distinguish from fields with value None. type of this is type"
    pass


def main():
    args = parse_args()
    # print(args)

    # TODO: print http error codes

    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(async_main(args))

    os.makedirs(args.output_dir, exist_ok=True)

    for org_repo, task in results:
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

        org_name, repo_name = org_repo.split("/", 1)

        result = task.result()

        output_path = args.output_dir / pathlib.Path(org_name) / pathlib.Path(repo_name)
        os.makedirs(output_path, exist_ok=True)

        # TODO: figure out how to cast quiz.Query -> quiz.JSON type (inverse of quiz.types.load)
        # print(result.repository)
        # json.dump(result.repository, fout, indent=4, sort_keys=True)
        # pickle.dump(result.repository, fout)

        base_dict = dict(org=org_name, repo=repo_name)
        repo = result.repository
        scalar_types = set([str, bool, int, float, type(None)])

        print("saving", output_path / pathlib.Path("repository.csv"), file=sys.stderr)
        with open(output_path / pathlib.Path("repository.csv"), "w") as fout:
            # 'createdAt', 'description', 'isArchived', 'isFork', 'isPrivate', 'updatedAt'
            row = {
                f: getattr(repo, f)
                for f in dir(repo)
                if not f.startswith("__")
                and type(getattr(repo, f, Sentinal)) in scalar_types
            }
            row["languages.totalCount"] = repo.languages.totalCount
            row["languages.totalSize"] = repo.languages.totalSize  # in bytes
            row[
                "dependencyGraphManifests.totalCount"
            ] = repo.dependencyGraphManifests.totalCount
            row["vulnerabilityAlerts.totalCount"] = repo.vulnerabilityAlerts.totalCount
            row.update(base_dict)

            writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
            writer.writeheader()
            writer.writerow(row)

        print("saving", output_path / pathlib.Path("languages.csv"), file=sys.stderr)
        with open(output_path / pathlib.Path("languages.csv"), "w") as fout:
            for i, edge in enumerate(repo.languages.edges):
                row = {
                    field: getattr(edge.node, field, Sentinal)
                    for field in set(["id", "name"])
                }
                row.update(base_dict)

                if i == 0:
                    writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
                    writer.writeheader()
                writer.writerow(row)

        print(
            "saving",
            output_path / pathlib.Path("dependencyGraphManifests.csv"),
            file=sys.stderr,
        )
        with open(
            output_path / pathlib.Path("dependencyGraphManifests.csv"), "w"
        ) as fout:
            for i, edge in enumerate(repo.dependencyGraphManifests.edges):
                # blobPath,dependenciesCount,exceedsMaxSize,filename,id,org,parseable,repo
                row = {
                    field: getattr(edge.node, field, Sentinal)
                    for field in dir(edge.node)
                    if not field.startswith("__")
                    and type(getattr(edge.node, field, Sentinal)) in scalar_types
                }
                row.update(base_dict)

                if i == 0:
                    writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
                    writer.writeheader()
                writer.writerow(row)

        print(
            "saving",
            output_path / pathlib.Path("dependencyGraphManifests.dependencies.csv"),
            file=sys.stderr,
        )
        with open(
            output_path / pathlib.Path("dependencyGraphManifests.dependencies.csv"), "w"
        ) as fout:
            wrote_header = False  # first manifest can have no deps
            for _tmp in repo.dependencyGraphManifests.edges:
                manifest_edge = _tmp.node
                for j, dep in enumerate(manifest_edge.dependencies.nodes):
                    row = {
                        field: getattr(dep, field, Sentinal)
                        for field in dir(dep)
                        if not field.startswith("__")
                        and type(getattr(dep, field, Sentinal)) in scalar_types
                    }
                    row["manifest_filename"], row["manifest_id"] = (
                        manifest_edge.filename,
                        manifest_edge.id,
                    )
                    row.update(base_dict)

                    if not wrote_header:
                        writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
                        writer.writeheader()
                        wrote_header = True

                    writer.writerow(row)

        print(
            "saving",
            output_path / pathlib.Path("vulnerabilityAlerts.csv"),
            file=sys.stderr,
        )
        with open(output_path / pathlib.Path("vulnerabilityAlerts.csv"), "w") as fout:

            def serialize_vuln(vuln):
                return {
                    "firstPatchedVersion.identifier": getattr(
                        vuln, "firstPatchedVersion", None
                    )
                    and getattr(vuln.firstPatchedVersion, "identifier", None),
                    "package.ecosystem": getattr(vuln, "package", None)
                    and getattr(vuln.package, "ecosystem", None)
                    and vuln.package.ecosystem.value,
                    "package.name": getattr(vuln, "package", None)
                    and getattr(vuln.package, "name", None),
                    "severity": getattr(vuln, "severity", None) and vuln.severity.value,
                    "updatedAt": getattr(vuln, "updatedAt", None),
                    "vulnerableVersionRange": getattr(
                        vuln, "vulnerableVersionRange", None
                    ),
                }

            for i, edge in enumerate(repo.vulnerabilityAlerts.edges):
                row = {
                    field: getattr(edge.node, field, Sentinal)
                    for field in dir(edge.node)
                    if not field.startswith("__")
                    and type(getattr(edge.node, field, Sentinal)) in scalar_types
                }
                advisory = {
                    "securityAdvisory."
                    + field: getattr(edge.node.securityAdvisory, field, Sentinal)
                    for field in dir(edge.node.securityAdvisory)
                    if not field.startswith("__")
                    and type(getattr(edge.node.securityAdvisory, field, Sentinal))
                    in scalar_types
                }

                advisory[
                    "securityAdvisory.severity"
                ] = (
                    edge.node.securityAdvisory.severity.value
                )  # .value since it's an enum
                advisory["securityAdvisory.identifiers"] = [
                    (sa_id.type, sa_id.value)
                    for sa_id in edge.node.securityAdvisory.identifiers
                ]
                advisory["securityAdvisory.vulnerabilities"] = [
                    serialize_vuln(n)
                    for n in edge.node.securityAdvisory.vulnerabilities.nodes
                ]
                advisory["securityAdvisory.referenceUrls"] = [
                    getattr(r, "url", None)
                    for r in getattr(edge.node.securityAdvisory, "references", [])
                ]

                row.update(advisory)
                row.update(base_dict)
                # TODO: make less gross
                for field in [
                    "dismisser.id",
                    "dismisser.name",
                    "dismissedAt",
                    "dismissReason",
                ]:
                    if field in row:
                        continue
                    if field.startswith("dismisser."):
                        dismisser = getattr(edge.node, "dismisser", None)
                        if dismisser:
                            row[field] = getattr(
                                dismisser, field.split(".", 1)[-1], None
                            )
                        else:
                            row[field] = None
                    else:
                        row[field] = getattr(edge.node, field, None)
                if "dismisser" in row:  # we only want the nested dismisser.* fields
                    del row["dismisser"]

                if i == 0:
                    writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
                    writer.writeheader()
                writer.writerow(row)


if __name__ == "__main__":
    main()
