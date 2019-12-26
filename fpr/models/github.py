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
from uuid import uuid4, UUID

import quiz

from fpr.quiz_util import (
    get_kwargs_in,
    SelectionPath,
    SelectionUpdate,
    SelectionKwargs,
    SelectionKwargsValue,
    multi_upsert_kwargs,
)
from fpr.serialize_util import (
    get_in as get_in_dict,
    extract_fields,
    JSONPath,
    JSONPathElement,
)


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

    @property
    def children(self: "Resource") -> List["Resource"]:
        # nested resources to fetch
        return [edge.child for edge in _resource_edges if edge.parent.kind == self.kind]

    @property
    def parent(self: "Resource") -> Optional["Resource"]:
        for edge in _resource_edges:
            if edge.child.kind == self.kind:
                return edge.parent
        return None

    @property
    def next_page_selection_path(self: "Resource") -> SelectionPath:
        """path in the quiz.Selection to add params like page size or

        after cursor
        """
        return [path_part for path_part in self.page_path if path_part != 0]

    @property
    def result_path(self: "Resource") -> JSONPath:
        """path in the JSON response to get results
        """
        result_path_item = "nodes" if self.parent else "edges"
        return list(self.page_path) + [result_path_item]


@dataclass(frozen=True)
class Request:
    resource: Resource
    selection_updates: List[SelectionUpdate]
    page_number: int = 0
    guid: UUID = field(default_factory=uuid4)

    @property
    def graphql(self: "Request") -> quiz.Selection:
        return multi_upsert_kwargs(self.selection_updates, self.resource.base_graphql)

    def _get_selection_kwarg_at_path(
        self: "Request", selection_path: SelectionPath, kwarg_key: str
    ) -> Optional[SelectionKwargsValue]:
        for (path, update_kwargs) in reversed(self.selection_updates):
            if path == selection_path and kwarg_key in update_kwargs:
                kwarg = update_kwargs.get(kwarg_key, None)
                return kwarg
        return None

    def _get_repo_owner_and_name_kwargs(self: "Request") -> Optional[SelectionKwargs]:
        if (
            len(self.selection_updates)
            and self.selection_updates[0][0] == SetRepositoryOwnerAndName[0]
        ):
            return self.selection_updates[0][1]
        return None

    @property
    def repo_owner(self: "Request") -> Optional[str]:
        kwargs = self._get_repo_owner_and_name_kwargs()
        if kwargs and "owner" in kwargs:
            assert isinstance(kwargs["owner"], str)
            return kwargs["owner"]
        return None

    @property
    def repo_name(self: "Request") -> Optional[str]:
        kwargs = self._get_repo_owner_and_name_kwargs()
        if kwargs and "name" in kwargs:
            assert isinstance(kwargs["name"], str)
            return kwargs["name"]
        return None

    @property
    def page_size(self: "Request") -> Optional[int]:
        size = self._get_selection_kwarg_at_path(
            self.resource.next_page_selection_path, "first"
        )
        assert isinstance(size, int) or size is None
        return size

    @property
    def page_cursor(self: "Request") -> Optional[str]:
        cursor = self._get_selection_kwarg_at_path(
            self.resource.next_page_selection_path, "after"
        )
        assert isinstance(cursor, str) or cursor is None
        return cursor

    @property
    def parent_page_size(self: "Request") -> Optional[int]:
        if not self.resource.parent:
            return None
        parent_page_size = self._get_selection_kwarg_at_path(
            self.resource.parent.next_page_selection_path, "first"
        )
        if parent_page_size is None:
            return None
        assert isinstance(parent_page_size, int)
        return parent_page_size

    @property
    def parent_page_cursor(self: "Request") -> Optional[str]:
        if not self.resource.parent:
            return None
        parent_page_cursor = self._get_selection_kwarg_at_path(
            self.resource.parent.next_page_selection_path, "after"
        )
        if parent_page_cursor is None:
            return None
        assert isinstance(parent_page_cursor, str)
        return parent_page_cursor

    @property
    def log_id(self: "Request") -> str:
        return f"request {self.guid}"

    @property
    def log_str(self: "Request") -> str:
        "returns a less verbose string for debug logging than the full __repr__"
        s = (
            f"{self.log_id} {self.repo_owner}/{self.repo_name}"
            f" {self.resource.kind.name} page {self.page_number}"
            f" (size {self.page_size}, cursor {self.page_cursor})"
        )
        if self.resource.parent:
            s += (
                f" parent {self.resource.parent.kind.name}"
                f"(size {self.parent_page_size}, cursor {self.parent_page_cursor})"
            )
        return s


@dataclass(frozen=True)
class Response:
    resource: Resource
    # dict for a JSON response from the GitHub API
    json: Optional[Dict[str, Any]] = None

    def _json_is_dict(self: "Response") -> bool:
        return self.json is not None and isinstance(self.json, dict)

    @property
    def end_cursor(self: "Response") -> Optional[str]:
        if not self._json_is_dict():
            return None
        assert self.json is not None
        assert isinstance(self.json, dict)

        page_info = get_in_dict(self.json, list(self.resource.page_path) + ["pageInfo"])
        if page_info and page_info.get("hasNextPage", False):
            return page_info.get("endCursor", None)
        return None

    @property
    def num_results(self: "Response") -> Optional[int]:
        "count of results for this page"
        if not self._json_is_dict():
            return None
        assert self.json is not None
        assert isinstance(self.json, dict)

        results = get_in_dict(self.json, self.resource.result_path)
        if results is None:
            return 0
        return len(results)

    @property
    def total_results(self: "Response") -> Optional[int]:
        "count of results for all pages"
        if not self._json_is_dict():
            return None
        assert self.json is not None
        assert isinstance(self.json, dict)

        total = get_in_dict(self.json, list(self.resource.page_path) + ["totalCount"])
        if total is None:
            return 0
        assert isinstance(total, int)
        return total

    @property
    def log_str(self: "Response") -> str:
        if not self._json_is_dict():
            return "invalid response!"
        assert self.json is not None
        assert isinstance(self.json, dict)
        return f"{self.num_results} of {self.total_results}"


def is_page_update(resource: Resource, update: QueryDiff) -> bool:
    path, kwargs = update
    return path == resource.next_page_selection_path and "after" in kwargs


@dataclass(frozen=True)
class RequestResponseExchange:
    request: Request
    response: Response

    @property
    def next_page_request(self: "RequestResponseExchange") -> Optional[Request]:
        """returns a Request for the next page of the same resource type or None

        Set request graphql after param to response endCursor value
        """
        if self.response.end_cursor is None:
            return None

        updates = self.request.selection_updates + get_next_page_selection_updates(
            self.request.resource, dict(after=self.response.end_cursor)
        )
        # de-duplicate after updates for more pages
        if (
            len(updates) > 1
            and is_page_update(self.request.resource, updates[-1])
            and is_page_update(self.request.resource, updates[-2])
        ):
            last_update = updates.pop()
            updates.pop()
            updates.append(last_update)

        return Request(
            resource=self.request.resource,
            selection_updates=updates,
            page_number=self.request.page_number + 1,
        )

    def next_nested_page_requests_iter(
        self: "RequestResponseExchange", context: ChainMap
    ) -> Generator[Request, None, None]:
        for child_resource in self.request.resource.children:
            next_page_request = get_nested_next_page_request(
                self, child_resource, context
            )
            if next_page_request is None:
                continue
            yield next_page_request


_ = quiz.SELECTOR

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
    .defaultBranchRef[
        _
        .name
        .id
        .prefix
        .target[
            _
            .id
            .oid
            .commitUrl
         ]
    ]
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


@dataclass
class ResourceEdge:
    parent: Resource
    child: Resource


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

_resource_edges: Sequence[ResourceEdge] = [
    ResourceEdge(parent=RepoManifests, child=RepoManifestDeps),
    ResourceEdge(parent=RepoVulnAlerts, child=RepoVulnAlertVulns),
]


def get_diff_kwargs(diff: QueryDiff, context: ChainMap) -> SelectionUpdate:
    path, kwargs = diff
    return (
        path,
        {
            kwargs_dest: context[context_key]
            for kwargs_dest, context_key in kwargs.items()
        },
    )


def get_first_page_selection_updates(
    resource: Resource, context: ChainMap
) -> List[SelectionUpdate]:
    """returns updates to replace dataclass.MISSING params in a

    quiz.Selection from a context dict
    """
    return [get_diff_kwargs(diff, context) for diff in resource.first_page_diffs]


def get_next_page_selection_updates(
    resource: Resource, new_page_kwargs: SelectionKwargs
) -> List[SelectionUpdate]:
    return [(resource.next_page_selection_path, new_page_kwargs)]


def get_owner_repo_kwargs(last_graphql: quiz.Selection) -> Dict[str, str]:
    repo_kwargs = get_kwargs_in(last_graphql, ["repository"])
    assert repo_kwargs is not None
    return extract_fields(repo_kwargs, ["owner", "name"])


def get_nested_next_page_request(
    exchange: RequestResponseExchange, child_resource: Resource, context: ChainMap
) -> Optional[Request]:
    """for the req res exchange returns a Request for the next page of a

    nested resource (e.g. manifest deps or vuln alerts vulns) if any or
    None
    """
    # path in the selection to add the parent after cursor params (can't get
    # from response since that cursor gives the next page of the parent
    # (alternatively could use a before param)
    parent_params = get_kwargs_in(
        exchange.request.graphql, exchange.request.resource.next_page_selection_path
    )
    assert parent_params is not None

    # NB: builds gql with 'null' as the after param but GH's API is OK with it
    context = ChainMap(
        dict(parent_after=parent_params.get("after", None)),
        context,
        get_owner_repo_kwargs(exchange.request.graphql),
    )
    return Request(
        resource=child_resource,
        selection_updates=get_first_page_selection_updates(child_resource, context),
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
                    updates = get_first_page_selection_updates(resource, context)
                    yield Request(resource=resource, selection_updates=updates)
    else:
        if last_exchange.next_page_request:
            log.debug(
                f"fetching another page of {last_exchange.request.resource.kind.name}"
            )
            yield last_exchange.next_page_request

        for next_page_request in last_exchange.next_nested_page_requests_iter(context):
            if next_page_request.resource.kind.name not in context["github_query_type"]:
                log.debug(
                    f"skipping fetch of nested page of {next_page_request.resource.kind.name} \
for {last_exchange.request.resource.kind.name}"
                )
                continue
            log.debug(
                f"fetching nested page of {next_page_request.resource.kind.name} for \
{last_exchange.request.resource.kind.name}"
            )
            yield next_page_request
