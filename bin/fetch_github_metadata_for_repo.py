#!/usr/bin/env python

"""
Fetches repo, language, manifest, dep metadata, and vuln alerts (if
accessible) for a github repo and saves it as CSVs files in
./github_repo_metadata/:org_name/:repo_name/

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

import aiohttp
import snug
import quiz


# https://developer.github.com/v4/previews/#access-to-a-repositories-dependency-graph
DEP_GRAPH_PREVIEW = "application/vnd.github.hawkgirl-preview+json"

# https://developer.github.com/v4/previews/#repository-vulnerability-alerts
VULN_ALERT_PREVIEW = "application/vnd.github.vixen-preview+json"


def auth_factory(auth):
    """Add an HTTP Authorization header from a Github PAT"""
    assert isinstance(auth, str)
    return snug.header_adder(dict(Authorization="bearer {auth}".format(auth=auth)))


def aiohttp_session():
    return aiohttp.ClientSession(
        headers=dict(Accept=",".join([DEP_GRAPH_PREVIEW, VULN_ALERT_PREVIEW]))
    )


async def async_query(async_executor, query):
    try:
        result = await async_executor(query)
    except quiz.ErrorResponse as err:
        print(err, err.errors, file=sys.stderr)
        result = None
    return result


async def async_github_schema_from_cache_or_url(schema_path, async_exec):
    # TODO: save E-Tag or Last-Modified then send If-Modified-Since or
    # If-None-Match and check for HTTP 304 Not Modified
    # https://developer.github.com/v3/#conditional-requests
    # NB: this might not be supported https://developer.github.com/v4/guides/resource-limitations/
    try:
        schema = quiz.Schema.from_path(schema_path)
    except IOError:
        print("Fetching github schema", file=sys.stderr)
        result = await async_exec(quiz.INTROSPECTION_QUERY)
        schema = quiz.Schema.from_raw(result["__schema"], scalars=(), module=None)
        schema.to_path(schema_path)
    return schema


def repo_query(schema, org_name, repo_name, first=10):
    _ = quiz.SELECTOR
    return schema.query[
        _.rateLimit[_.limit.cost.remaining.resetAt].repository(
            owner=org_name, name=repo_name
        )[
            _.createdAt.updatedAt.description.isArchived.isPrivate.isFork.languages(
                first=first
            )[
                _.pageInfo[_.hasNextPage.endCursor].totalCount.totalSize.edges[
                    _.node[_.id.name]
                ]
            ]
            .dependencyGraphManifests(first=first)[
                _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
                    _.node[
                        _.id.blobPath.dependenciesCount.exceedsMaxSize.filename.parseable.dependencies(
                            first=first
                        )[
                            _.pageInfo[_.hasNextPage.endCursor].totalCount.nodes[
                                _.packageName.packageManager.hasDependencies.requirements
                            ]
                        ]
                    ]
                ]
            ]
            .vulnerabilityAlerts(first=first)[
                _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
                    _.node[
                        _.id.dismissReason.dismissedAt.dismisser[
                            _.id.name  # need user:email oauth scope for .email
                        ]
                        .securityAdvisory[
                            _.id.ghsaId.summary.description.severity.publishedAt.updatedAt.withdrawnAt.identifiers[
                                _.type.value
                            ].vulnerabilities(
                                first=first
                            )[
                                _.pageInfo[_.hasNextPage.endCursor].totalCount.nodes[
                                    _.package[
                                        _.name.ecosystem
                                    ].severity.updatedAt.vulnerableVersionRange
                                ]
                            ]
                        ]
                        .vulnerableManifestFilename.vulnerableManifestPath.vulnerableRequirements
                    ]
                ]
            ]
        ]
    ]


def repo_langs_query_next_page(schema, org_name, repo_name, after, first=10):
    _ = quiz.SELECTOR
    return schema.query[
        _.rateLimit[_.limit.cost.remaining.resetAt].repository(
            owner=org_name, name=repo_name
        )[
            _.languages(after=after, first=first)[
                _.pageInfo[_.hasNextPage.endCursor].edges[_.node[_.id.name]]
            ]
        ]
    ]


def repo_manifests_query_next_page(schema, org_name, repo_name, after, first=10):
    _ = quiz.SELECTOR
    return schema.query[
        _.rateLimit[_.limit.cost.remaining.resetAt].repository(
            owner=org_name, name=repo_name
        )[
            _.dependencyGraphManifests(first=first, after=after)[
                _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
                    _.node[
                        _.id.blobPath.dependenciesCount.exceedsMaxSize.filename.parseable.dependencies(
                            first=first
                        )[
                            _.pageInfo[_.hasNextPage.endCursor].totalCount.nodes[
                                _.packageName.packageManager.hasDependencies.requirements
                            ]
                        ]
                    ]
                ]
            ]
        ]
    ]


def repo_manifest_deps_query_next_page(
    schema, org_name, repo_name, manifest_first, manifest_after, after, first=10
):
    _ = quiz.SELECTOR
    if manifest_after is None:
        return schema.query[
            _.rateLimit[_.limit.cost.remaining.resetAt].repository(
                owner=org_name, name=repo_name
            )[
                _.dependencyGraphManifests(first=first)[
                    _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
                        _.node[
                            _.id.blobPath.dependenciesCount.exceedsMaxSize.filename.parseable.dependencies(
                                first=first, after=after
                            )[
                                _.pageInfo[_.hasNextPage.endCursor].totalCount.nodes[
                                    _.packageName.packageManager.hasDependencies.requirements
                                ]
                            ]
                        ]
                    ]
                ]
            ]
        ]
    else:
        return schema.query[
            _.rateLimit[_.limit.cost.remaining.resetAt].repository(
                owner=org_name, name=repo_name
            )[
                _.dependencyGraphManifests(first=first, after=after)[
                    _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
                        _.node[
                            _.id.blobPath.dependenciesCount.exceedsMaxSize.filename.parseable.dependencies(
                                first=first, after=after
                            )[
                                _.pageInfo[_.hasNextPage.endCursor].totalCount.nodes[
                                    _.packageName.packageManager.hasDependencies.requirements
                                ]
                            ]
                        ]
                    ]
                ]
            ]
        ]


async def query_repo_data(schema, org_repo, async_exec):
    repo_page_size = 100
    lang_page_size = 30
    manifests_page_size = 50
    dep_page_size = 100

    # fetch top-level repo info w/ first repo_page_size of linked nodes except manifests
    query = repo_query(schema, *org_repo.split("/", 1), first=repo_page_size)
    print(org_repo, "fetching repo page", file=sys.stderr)
    repo = await async_query(async_exec, query)
    print(
        org_repo,
        "fetched repo page with %d/%d langs, %d/%d dep manifests, and %d/%d vuln alerts"
        % (
            len(repo.repository.languages.edges),
            repo.repository.languages.totalCount,
            len(repo.repository.dependencyGraphManifests.edges),
            repo.repository.dependencyGraphManifests.totalCount,
            len(repo.repository.vulnerabilityAlerts.edges),
            repo.repository.vulnerabilityAlerts.totalCount,
        ),
        file=sys.stderr,
    )
    if repo.repository.vulnerabilityAlerts.totalCount > repo_page_size:
        print(
            org_repo,
            "warning: missing %d vuln alerts"
            % repo.repository.vulnerabilityAlerts.totalCount
            - len(repo.repository.vulnerabilityAlerts.edges),
            file=sys.stderr,
        )

    for e in repo.repository.dependencyGraphManifests.edges:
        print(
            org_repo,
            e.node.filename,
            "fetched %d/%d deps"
            % (len(e.node.dependencies.nodes), e.node.dependenciesCount),
            file=sys.stderr,
        )
        if e.node.exceedsMaxSize or not e.node.parseable:
            print(
                org_repo,
                e.node.filename,
                "warning: not parseable? %s or exceedsMaxSize? %s"
                % (not e.node.parseable, e.node.exceedsMaxSize),
                file=sys.stderr,
            )

    response = repo
    while response.repository.languages.pageInfo.hasNextPage:
        cursor = response.repository.languages.pageInfo.endCursor
        query = repo_langs_query_next_page(
            schema, *org_repo.split("/", 1), first=lang_page_size, after=cursor
        )
        print(
            org_repo,
            "fetching lang page of size %d w/ cursor %s" % (lang_page_size, cursor),
            file=sys.stderr,
        )
        response = await async_query(async_exec, query)
        repo.repository.languages.edges.extend(response.repository.languages.edges)
        print(
            org_repo,
            "fetched lang page w/ %d langs for %d/%d"
            % (
                len(response.repository.languages.edges),
                len(repo.repository.languages.edges),
                repo.repository.languages.totalCount,
            ),
            file=sys.stderr,
        )
    assert len(repo.repository.languages.edges) == repo.repository.languages.totalCount

    # TODO: figure out why we only getting one manifest back when first=1 in repo query (i.e. pagination seems to be broken)
    response = repo
    while response.repository.dependencyGraphManifests.pageInfo.hasNextPage:
        cursor = response.repository.dependencyGraphManifests.pageInfo.endCursor
        query = repo_manifests_query_next_page(
            schema, *org_repo.split("/", 1), first=manifests_page_size, after=cursor
        )
        print(
            org_repo,
            "fetching %d manifests from cursor %s" % (manifests_page_size, cursor),
            file=sys.stderr,
        )
        response = await async_query(async_exec, query)
        print(
            org_repo,
            "fetched %d/%d manifests"
            % (
                len(repo.repository.dependencyGraphManifests.edges),
                repo.repository.dependencyGraphManifests.totalCount,
            ),
            file=sys.stderr,
        )
        repo.repository.dependencyGraphManifests.edges.extend(
            response.repository.dependencyGraphManifests.edges
        )
    assert (
        len(repo.repository.dependencyGraphManifests.edges)
        == repo.repository.dependencyGraphManifests.totalCount
    )

    for manifest_edge in repo.repository.dependencyGraphManifests.edges:
        manifest = manifest_edge.node
        manifest_id = manifest.id
        response = repo
        while manifest_edge.node.dependencies.pageInfo.hasNextPage:
            cursor = manifest_edge.node.dependencies.pageInfo.endCursor
            manifest_cursor = None
            query = repo_manifest_deps_query_next_page(
                schema,
                *org_repo.split("/", 1),
                manifest_first=manifests_page_size,
                manifest_after=manifest_cursor,  # response.repository.dependencyGraphManifests.pageInfo.endCursor,
                first=dep_page_size,
                after=cursor
            )
            print(
                org_repo,
                manifest.filename,
                "fetching %d deps from manifest cursor %s and dep cursor %s"
                % (dep_page_size, manifest_cursor, cursor),
                file=sys.stderr,
            )

            response = await async_query(async_exec, query)
            for response_edge in response.repository.dependencyGraphManifests.edges:
                if response_edge.node.id == manifest_id:
                    manifest.dependencies.nodes.extend(
                        response_edge.node.dependencies.nodes
                    )

            print(
                org_repo,
                manifest_edge.node.filename,
                "fetched dep page w/ %d deps for %d/%d"
                % (
                    next(
                        len(e.node.dependencies.nodes)
                        for e in response.repository.dependencyGraphManifests.edges
                        if e.node.id == manifest_id
                    ),
                    next(
                        len(e.node.dependencies.nodes)
                        for e in repo.repository.dependencyGraphManifests.edges
                        if e.node.id == manifest_id
                    ),
                    next(
                        e.node.dependenciesCount
                        for e in repo.repository.dependencyGraphManifests.edges
                        if e.node.id == manifest_id
                    ),
                ),
                file=sys.stderr,
            )

            manifest_edge = next(
                e
                for e in response.repository.dependencyGraphManifests.edges
                if e.node.id == manifest_id
            )
        assert next(
            len(e.node.dependencies.nodes)
            for e in repo.repository.dependencyGraphManifests.edges
            if e.node.id == manifest_id
        ) == next(
            e.node.dependenciesCount
            for e in repo.repository.dependencyGraphManifests.edges
            if e.node.id == manifest_id
        )

    # TODO: add vuln reports back; skipping for now since we don't have their data
    return repo


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
    parser = argparse.ArgumentParser(description=__doc__)

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

        output_path = (
            args.output_dir
            / pathlib.Path(org_name)
            / pathlib.Path(repo_name)
        )
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
            row = {f: getattr(repo, f) for f in dir(repo) if not f.startswith('__') and type(getattr(repo, f, Sentinal)) in scalar_types}
            row['languages.totalCount'] = repo.languages.totalCount
            row['languages.totalSize'] = repo.languages.totalSize # in bytes
            row['dependencyGraphManifests.totalCount'] = repo.dependencyGraphManifests.totalCount
            row['vulnerabilityAlerts.totalCount'] = repo.vulnerabilityAlerts.totalCount
            row.update(base_dict)

            writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
            writer.writeheader()
            writer.writerow(row)

        print("saving", output_path / pathlib.Path("languages.csv"), file=sys.stderr)
        with open(output_path / pathlib.Path("languages.csv"), "w") as fout:
            for i, edge in enumerate(repo.languages.edges):
                row = {field: getattr(edge.node, field, Sentinal) for field in set(['id', 'name'])}
                row.update(base_dict)

                if i == 0:
                    writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
                    writer.writeheader()
                writer.writerow(row)

        print("saving", output_path / pathlib.Path("dependencyGraphManifests.csv"), file=sys.stderr)
        with open(output_path / pathlib.Path("dependencyGraphManifests.csv"), "w") as fout:
            for i, edge in enumerate(repo.dependencyGraphManifests.edges):
                # blobPath,dependenciesCount,exceedsMaxSize,filename,id,org,parseable,repo
                row = {field: getattr(edge.node, field, Sentinal) for field in dir(edge.node) if not field.startswith('__') and type(getattr(edge.node, field, Sentinal)) in scalar_types}
                row.update(base_dict)

                if i == 0:
                    writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
                    writer.writeheader()
                writer.writerow(row)

        print("saving", output_path / pathlib.Path("dependencyGraphManifests.dependencies.csv"), file=sys.stderr)
        with open(output_path / pathlib.Path("dependencyGraphManifests.dependencies.csv"), "w") as fout:
            wrote_header = False # first manifest can have no deps
            for _tmp in repo.dependencyGraphManifests.edges:
                manifest_edge = _tmp.node
                for j, dep in enumerate(manifest_edge.dependencies.nodes):
                    row = {field: getattr(dep, field, Sentinal) for field in dir(dep) if not field.startswith('__') and type(getattr(dep, field, Sentinal)) in scalar_types}
                    row['manifest_filename'], row['manifest_id'] = manifest_edge.filename, manifest_edge.id
                    row.update(base_dict)

                    if not wrote_header:
                        writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
                        writer.writeheader()
                        wrote_header = True

                    writer.writerow(row)

        print("saving", output_path / pathlib.Path("vulnerabilityAlerts.csv"), file=sys.stderr)
        with open(output_path / pathlib.Path("vulnerabilityAlerts.csv"), "w") as fout:
            def serialize_vuln(vuln):
                return {
                    'firstPatchedVersion.identifier': getattr(vuln, 'firstPatchedVersion', None) and getattr(vuln.firstPatchedVersion, 'identifier', None),
                    'package.ecosystem': getattr(vuln, 'package', None) and getattr(vuln.package, 'ecosystem', None) and vuln.package.ecosystem.value,
                    'package.name': getattr(vuln, 'package', None) and getattr(vuln.package, 'name', None),
                    'severity': getattr(vuln, 'severity', None) and vuln.severity.value,
                    'updatedAt': getattr(vuln, 'updatedAt', None),
                    'vulnerableVersionRange': getattr(vuln, 'vulnerableVersionRange', None),
                }

            for i, edge in enumerate(repo.vulnerabilityAlerts.edges):
                row = {field: getattr(edge.node, field, Sentinal) for field in dir(edge.node) if not field.startswith('__') and type(getattr(edge.node, field, Sentinal)) in scalar_types}
                advisory = {'securityAdvisory.' + field: getattr(edge.node.securityAdvisory, field, Sentinal) for field in dir(edge.node.securityAdvisory) if not field.startswith('__') and type(getattr(edge.node.securityAdvisory, field, Sentinal)) in scalar_types}

                advisory['securityAdvisory.severity'] = edge.node.securityAdvisory.severity.value # .value since it's an enum
                advisory['securityAdvisory.identifiers'] = [(sa_id.type, sa_id.value) for sa_id in edge.node.securityAdvisory.identifiers]
                advisory['securityAdvisory.vulnerabilities'] = [serialize_vuln(n) for n in edge.node.securityAdvisory.vulnerabilities.nodes]
                advisory['securityAdvisory.referenceUrls'] = [getattr(r, 'url', None) for r in getattr(edge.node.securityAdvisory, 'references', [])]

                row.update(advisory)
                row.update(base_dict)

                if i == 0:
                    writer = csv.DictWriter(fout, fieldnames=sorted(row.keys()))
                    writer.writeheader()
                writer.writerow(row)


if __name__ == "__main__":
    main()
