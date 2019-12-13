from collections import ChainMap
from dataclasses import dataclass, field
import enum
import functools
import logging
from typing import (
    AbstractSet,
    Any,
    Dict,
    List,
    Optional,
    Callable,
    Union,
    Generator,
    Sequence,
    Tuple,
    Type,
)

import quiz

from fpr.quiz_util import (
    get_kwargs_in,
    update_in,
    upsert_kwargs,
    drop_fields,
    SelectionPath,
    SelectionUpdate,
    multi_upsert_kwargs,
)
from fpr.serialize_util import get_in as get_in_dict, extract_fields


JSONPathElement = Union[int, str]
JSONPath = Sequence[JSONPathElement]


@enum.unique
class ResourceKind(enum.Enum):
    RATE_LIMIT = enum.auto()
    REPO = enum.auto()
    REPO_LANGS = enum.auto()
    REPO_DEP_MANIFESTS = enum.auto()
    REPO_DEP_MANIFEST_DEPS = enum.auto()
    REPO_VULN_ALERTS = enum.auto()
    REPO_VULN_ALERT_VULNS = enum.auto()


QueryDiff = SelectionUpdate
# i.e. a tuple of (path in selection to update kwargs at, relevant
# update_kwargs key to read from the query context (args, input line (org and
# repo), or previous query response json))


MISSING = "MISSING fpr gql param."


@dataclass(frozen=True)
class Resource:
    kind: ResourceKind
    base_graphql: quiz.Selection

    # where to pull results from the query response JSON for pagination
    page_path: JSONPath

    # diffs to apply to base_graphql to get a first page selection
    first_page_diffs: List[QueryDiff] = field(default_factory=list)

    # nested resources to fetch
    children: List["Resource"] = field(default_factory=list)


@dataclass(frozen=True)
class Request:
    resource: Resource
    graphql: quiz.Selection


@dataclass(frozen=True)
class Response:
    resource: Resource
    # dict for a JSON response from the GitHub API
    json: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RequestResponseExchange:
    request: Request
    response: Response


_ = quiz.SELECTOR

# TODO: save E-Tag or Last-Modified then send If-Modified-Since or
# If-None-Match and check for HTTP 304 Not Modified
# https://developer.github.com/v3/#conditional-requests
# NB: this might not be supported https://developer.github.com/v4/guides/resource-limitations/
rate_limit_gql = _.rateLimit[
    # https://developer.github.com/v4/object/ratelimit/
    _.limit.cost.remaining.resetAt
]

# fmt: off
repo_gql = _.repository(owner=MISSING, name=MISSING)[
    # https://developer.github.com/v4/object/repository/#fields
    _
    .databaseId
    .id
    .name
    .createdAt
    .updatedAt
    .description
    .isArchived
    .isDisabled
    .diskUsage
    .isPrivate
    .isFork
    .isLocked
    .isMirror
    .isTemplate
    .updatedAt
    .pushedAt
    .licenseInfo[
        # NB: more fields available https://developer.github.com/v4/object/license/
        _.key
    ]
    .primaryLanguage[_.name.id]
    .defaultBranchRef[_.name.id.prefix.target]
]
# fmt: on

repo_langs_gql = _.repository(owner=MISSING, name=MISSING)[
    _.databaseId.id.name.languages(first=MISSING)[
        # https://developer.github.com/v4/object/languageconnection/
        _.pageInfo[_.hasNextPage.endCursor].totalCount.totalSize.edges[
            _.node[_.id.name]
        ]
    ]
]

repo_manifests_gql = _.repository(owner=MISSING, name=MISSING)[
    _.databaseId.id.name.dependencyGraphManifests(first=MISSING)[
        # https://developer.github.com/v4/object/dependencygraphmanifestconnection/
        _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
            _.node[
                _.id.blobPath.dependenciesCount.exceedsMaxSize.filename.parseable.dependencies(
                    first=2
                )[
                    _.pageInfo[_.hasNextPage.endCursor].totalCount.nodes[
                        _.packageName.packageManager.hasDependencies.requirements
                    ]
                ]
            ]
        ]
    ]
]

repo_dep_gql = _.repository(owner=MISSING, name=MISSING)[
    _.databaseId.id.name.dependencyGraphManifests(
        first=1,
        # after=MISSING, # required for the second and later manifests
        # dependenciesFirst=MISSING,
        # dependenciesAfter=MISSING,
    )[
        # https://developer.github.com/v4/object/dependencygraphdependencyconnection/
        _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
            _.node[
                _.id.dependencies(first=MISSING)[  # or do we want dependencies edges?
                    _.pageInfo[_.hasNextPage.endCursor].totalCount.nodes[
                        _.packageName.packageManager.hasDependencies.requirements
                    ]
                ]
            ]
        ]
    ]
]

repo_vuln_alerts_gql = _.repository(owner=MISSING, name=MISSING)[
    _.databaseId.id.name.vulnerabilityAlerts(first=MISSING)[
        _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
            _.node[
                _.id.dismissReason.dismissedAt.dismisser[
                    _.id.name  # need user:email oauth scope for .email
                ]
                .securityAdvisory[
                    _.id.ghsaId.summary.description.severity.publishedAt.updatedAt.withdrawnAt.identifiers[
                        _.type.value
                    ].vulnerabilities(
                        first=25
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

repo_vuln_alert_vulns_gql = _.repository(owner=MISSING, name=MISSING)[
    _.databaseId.id.name.vulnerabilityAlerts(first=1, after=MISSING)[
        _.pageInfo[_.hasNextPage.endCursor].totalCount.edges[
            _.node[
                _.id.dismissReason.dismissedAt.dismisser[
                    _.id.name  # need user:email oauth scope for .email
                ]
                .securityAdvisory[
                    _.id.ghsaId.summary.description.severity.publishedAt.updatedAt.withdrawnAt.identifiers[
                        _.type.value
                    ].vulnerabilities(
                        first=MISSING
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


SetRepositoryOwnerAndName: QueryDiff = (
    ["repository"],  # Repo.page_path
    dict(owner="owner", name="name"),
)
SetRepositoryLanguagesFirst: QueryDiff = (
    ["repository", "languages"],  # RepoLangs.page_path
    dict(first="github_repo_langs_page_size"),
)
SetRepositoryManifestsFirst: QueryDiff = (
    ["repository", "dependencyGraphManifests"],  # RepoManifests.page_path
    dict(first="github_repo_dep_manifests_page_size"),
)
SetRepositoryManifestsAfter: QueryDiff = (
    ["repository", "dependencyGraphManifests"],  # RepoManifests.page_path
    dict(after="parent_after"),
)
SetRepositoryVulnAlertsFirst: QueryDiff = (
    ["repository", "vulnerabilityAlerts"],  # RepoVulnAlertVulns.page_path
    dict(first="github_repo_vuln_alerts_page_size"),
)
SetRepositoryVulnAlertsAfter: QueryDiff = (
    ["repository", "vulnerabilityAlerts"],  # RepoVulnAlertVulns.page_path
    dict(after="parent_after"),
)
SetRepositoryManifestDepsFirst: QueryDiff = (
    [
        "repository",
        "dependencyGraphManifests",
        "edges",
        "node",
        "dependencies",
    ],  # RepoManifestDeps.page_path,
    dict(first="github_repo_dep_manifest_deps_page_size"),
)
SetRepositoryVulnAlertVulnsFirst: QueryDiff = (
    [
        "repository",
        "vulnerabilityAlerts",
        "edges",
        "node",
        "securityAdvisory",
        "vulnerabilities",
    ],  # RepoVulnAlertVulns.page_path,
    dict(first="github_repo_vuln_alert_vulns_page_size"),
)


Repo = Resource(
    kind=ResourceKind.REPO,
    base_graphql=repo_gql,
    page_path=["repository"],
    first_page_diffs=[SetRepositoryOwnerAndName],
)


RepoLangs = Resource(
    kind=ResourceKind.REPO_LANGS,
    base_graphql=repo_langs_gql,
    page_path=["repository", "languages"],
    first_page_diffs=[SetRepositoryOwnerAndName, SetRepositoryLanguagesFirst],
)

RepoManifestDeps = Resource(
    kind=ResourceKind.REPO_DEP_MANIFEST_DEPS,
    base_graphql=repo_dep_gql,
    page_path=[
        "repository",
        "dependencyGraphManifests",
        "edges",
        0,
        "node",
        "dependencies",
    ],
    first_page_diffs=[
        SetRepositoryOwnerAndName,
        SetRepositoryManifestsFirst,
        SetRepositoryManifestsAfter,
        SetRepositoryManifestDepsFirst,
    ],
)


RepoManifests = Resource(
    kind=ResourceKind.REPO_DEP_MANIFESTS,
    base_graphql=repo_manifests_gql,
    page_path=["repository", "dependencyGraphManifests"],
    children=[RepoManifestDeps],
    first_page_diffs=[SetRepositoryOwnerAndName, SetRepositoryManifestsFirst],
)


RepoVulnAlertVulns = Resource(
    kind=ResourceKind.REPO_VULN_ALERT_VULNS,
    base_graphql=repo_vuln_alert_vulns_gql,
    page_path=[
        "repository",
        "vulnerabilityAlerts",
        "edges",
        0,
        "node",
        "securityAdvisory",
        "vulnerabilities",
    ],
    first_page_diffs=[
        SetRepositoryOwnerAndName,
        SetRepositoryVulnAlertsFirst,
        SetRepositoryVulnAlertsAfter,
        SetRepositoryVulnAlertVulnsFirst,
    ],
)


RepoVulnAlerts = Resource(
    kind=ResourceKind.REPO_VULN_ALERTS,
    base_graphql=repo_vuln_alerts_gql,
    page_path=["repository", "vulnerabilityAlerts"],
    children=[RepoVulnAlertVulns],
    first_page_diffs=[SetRepositoryOwnerAndName, SetRepositoryVulnAlertsFirst],
)


_resources: Sequence[Resource] = [
    Repo,
    RepoLangs,
    RepoManifests,
    RepoManifestDeps,
    RepoVulnAlerts,
    RepoVulnAlertVulns,
]


def apply_diff(diff: QueryDiff, context: ChainMap) -> SelectionUpdate:
    return (diff[0], {k: context[v] for k, v in diff[1].items()})


def get_first_page_selection(resource: Resource, context: ChainMap) -> quiz.Selection:
    """replaces dataclass.MISSING params in a Request using
    github_metadata pipeline args and returns a quiz graphql selection"""
    updates = [apply_diff(diff, context) for diff in resource.first_page_diffs]
    selection = multi_upsert_kwargs(updates, resource.base_graphql)
    return selection


def get_next_page_selection(
    path: SelectionPath, selection: quiz.Selection, next_page_kwargs: Dict[str, str]
) -> quiz.Selection:
    """returns quiz.Selection to fetch the next page of resource.

    At the param path in the selection it:

    1. adds or update the after cursor
    2. drops totalCount and totalSize attrs when present

    e.g.

    _.languages(first=MISSING)[
            _.pageInfo[_.hasNextPage.endCursor].totalCount.totalSize.edges[
                _.node[_.id.name]
            ]
    ]

    _.languages(first=first, after=after)[
        _.pageInfo[_.hasNextPage.endCursor].edges[
                _.node[_.id.name]
            ]
    ]
    """
    selection = update_in(
        selection, path, functools.partial(upsert_kwargs, path[-1], next_page_kwargs)
    )
    selection = update_in(
        selection,
        path,
        functools.partial(drop_fields, {"totalCount", "totalSize"}, path[-1]),
    )
    return selection


def get_owner_repo_kwargs(last_graphql: quiz.Selection) -> Dict[str, str]:
    repo_kwargs = get_kwargs_in(last_graphql, ["repository"])
    assert repo_kwargs is not None
    return extract_fields(repo_kwargs, ["owner", "name"])


def get_next_page_request(
    log: logging.Logger, exchange: RequestResponseExchange
) -> Optional[Request]:
    """for the req res exchange returns a Request for the next page if any or None
    """
    assert isinstance(exchange.response.json, dict)
    page_info = get_in_dict(
        exchange.response.json, list(exchange.request.resource.page_path) + ["pageInfo"]
    )
    if not (
        page_info and "hasNextPage" in page_info and page_info["hasNextPage"] is True
    ):
        return None

    log.debug(f"got {exchange.request.resource.kind.name} page response with next page")
    assert "endCursor" in page_info

    # path in the selection to add the selection page size and after cursor params
    # e.g.
    path: SelectionPath = [
        path_part for path_part in exchange.request.resource.page_path if path_part != 0
    ]

    # return previous query with after set to endCursor value
    return Request(
        resource=exchange.request.resource,
        graphql=get_next_page_selection(
            path, exchange.request.graphql, dict(after=page_info["endCursor"])
        ),
    )


def get_nested_next_page_request(
    log: logging.Logger,
    exchange: RequestResponseExchange,
    child_resource: Resource,
    context: ChainMap,
) -> Optional[Request]:
    """for the req res exchange returns a Request for the next page of a

    nested resource (e.g. manifest deps or vuln alerts vulns) if any or
    None
    """
    # path in the selection to add the parent after cursor params (can't get
    # from response since that cursor gives the next page of the parent
    # (alternatively use a before param?)
    path: SelectionPath = [
        path_part for path_part in exchange.request.resource.page_path if path_part != 0
    ]
    parent_params = get_kwargs_in(exchange.request.graphql, path)
    assert parent_params is not None

    # NB: builds gql with 'null' as the after param but GH's API is OK with it
    context = ChainMap(
        dict(parent_after=parent_params.get("after", None)),
        context,
        get_owner_repo_kwargs(exchange.request.graphql),
    )
    log.debug(
        f"querying for first nested page of {child_resource.kind.name} for {exchange.request.resource.kind.name}"
    )
    return Request(
        resource=child_resource,
        graphql=get_first_page_selection(child_resource, context),
    )


def get_next_requests(
    log: logging.Logger,
    context: ChainMap,
    last_exchange: Optional[RequestResponseExchange] = None,
) -> Generator[Request, None, None]:
    """Generates next github Requests to run

    Uses the context of allowed github resources and an optional
    last_exchange param to generate the first, next, or next dependent
    resource requests.
    """
    assert "github_query_type" in context and isinstance(
        context["github_query_type"], list
    )
    # get the first page for resources that don't depend on other resources to
    # fetch
    if last_exchange is None:
        assert "owner" in context
        assert "name" in context

        for resource_kind_name in context["github_query_type"]:
            for resource in [Repo, RepoLangs, RepoManifests, RepoVulnAlerts]:
                if resource_kind_name == resource.kind.name:
                    yield Request(
                        resource=resource,
                        graphql=get_first_page_selection(
                            resource=resource, context=context
                        ),
                    )
    else:
        next_page_req = get_next_page_request(log, last_exchange)
        if next_page_req:
            log.debug(
                f"fetching another page of {last_exchange.request.resource.kind.name}"
            )
            yield next_page_req

        for child_resource in last_exchange.request.resource.children:
            if child_resource.kind.name not in context["github_query_type"]:
                log.debug(
                    f"skipping fetch of nested page of {child_resource.kind.name} \
for {last_exchange.request.resource.kind.name}"
                )
                continue

            next_page_req = get_nested_next_page_request(
                log, last_exchange, child_resource, context
            )
            if next_page_req:
                log.debug(
                    f"fetch nested page of {child_resource.kind.name} for \
{last_exchange.request.resource.kind.name}"
                )
                yield next_page_req
