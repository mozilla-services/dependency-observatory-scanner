# -*- coding: utf-8 -*-

import functools
import pathlib
import json
from typing import Any, Callable, Dict, List, Tuple, Union

import pytest

import context
import fpr.models.github as m


@pytest.fixture(scope="module")
def _():
    return m.quiz.SELECTOR


__ = m.quiz.SELECTOR


def load_graphql_fixture(filename: str) -> str:
    tests_dir = pathlib.Path(__file__).parent / ".."
    with (tests_dir / "fixtures" / "graphql" / f"{filename}.graphql").open("r") as fin:
        return fin.read()


def load_json_fixture(filename: str) -> Dict[str, Any]:
    tests_dir = pathlib.Path(__file__).parent / ".."
    with (tests_dir / "fixtures" / f"{filename}.json").open("r") as fin:
        return json.load(fin)


def repo_gql(_):
    # fmt: off
    return _.repository(owner=dataclasses.MISSING, name=dataclasses.MISSING)[
        # https://developer.github.com/v4/object/repository/#fields
        _.databaseId
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
            _.key
        ].primaryLanguage[
            _.name
            .id
        ]
    ]
    # fmt: on


@pytest.fixture
def repo_langs_gql(_):
    return _.id.languages(first=2)[
        _.pageInfo[_.hasNextPage.endCursor].totalCount.totalSize.edges[
            _.node[_.id.name]
        ]
    ]


@pytest.fixture
def set_owner_repo_kwargs() -> Callable:
    def add_owner_repo_to_repository_field(
        selection: m.quiz.Selection
    ) -> m.quiz.Selection:
        return m.update_in(
            selection,
            ["repository"],
            functools.partial(
                m.upsert_kwargs, "repository", dict(owner="owner", name="repo_name")
            ),
        )

    return add_owner_repo_to_repository_field


@pytest.fixture
def github_args_dict() -> Dict[str, int]:
    return {
        "github_repo_langs_page_size": 7,
        "github_repo_dep_manifests_page_size": 1,
        "github_repo_dep_manifest_deps_page_size": 2,
        "github_repo_vuln_alerts_page_size": 1,
        "github_repo_vuln_alert_vulns_page_size": 3,
    }


@pytest.fixture
def owner_repo_dict() -> Dict[str, str]:
    return dict(owner="test_org_or_owner_name", name="test_repo_name")


def resource_id(val: Union[m.Resource, m.SelectionPath]) -> str:
    if isinstance(val, m.Resource):
        return f"{val.kind.name}"
    elif all(isinstance(path_item, str) for path_item in val):
        return f"path:{val}"


def unique_diff_paths() -> List[Tuple[m.Resource, m.SelectionPath]]:
    result = []
    for resource in m._resources:
        for diff in resource.first_page_diffs:
            if (resource, diff[0]) not in result:
                result.append((resource, diff[0]))
    return result


def assert_selection_is_sane(selection: m.quiz.Selection, schema: m.quiz.Schema):
    schema.query[selection]  # should not raise a validation error
    assert str(m.MISSING) not in str(selection)


@pytest.mark.parametrize("resource,diff_path", unique_diff_paths(), ids=resource_id)
def test_can_get_diff_paths(resource: m.Resource, diff_path: m.SelectionPath):
    assert m.get_kwargs_in(resource.base_graphql, diff_path) is not None


@pytest.mark.parametrize("resource", m._resources, ids=lambda r: r.kind.name)
def test_get_first_page_selection(
    resource, github_args_dict, owner_repo_dict, github_schema
):
    context = m.ChainMap(
        github_args_dict, owner_repo_dict, dict(parent_after="test_parent_after_cursor")
    )
    selection = m.get_first_page_selection(
        resource, m.get_first_page_selection_updates(resource, context)
    )
    assert_selection_is_sane(selection, github_schema)
    if len(resource.children):  # a root resource
        assert "after" not in str(selection)
    # else:
    #     assert "after" in str(selection)


def test_get_next_page_selection(_):
    # should add first and after params and drop totalCount, totalSize
    assert (
        m.get_next_page_selection(
            _.repository[
                _.id.databaseId.name.languages(first="test-first")[
                    _.pageInfo[_.hasNextPage.endCursor].totalCount.totalSize.edges[
                        _.node[_.id.name]
                    ]
                ]
            ],
            m.get_next_page_selection_updates(
                m.RepoLangs, dict(first=25, after="test-cursor-xyz")
            ),
        )
        == _.repository[
            _.id.databaseId.name.languages(first=25, after="test-cursor-xyz")[
                _.pageInfo[_.hasNextPage.endCursor].totalCount.totalSize.edges[
                    _.node[_.id.name]
                ]
            ]
        ]
    )

    # example 2nd to 3rd page query
    assert (
        m.get_next_page_selection(
            _.repository[
                _.id.databaseId.name.languages(first=25, after="test-2nd-page-cursor")[
                    _.pageInfo[_.hasNextPage.endCursor].edges[_.node[_.id.name]]
                ]
            ],
            m.get_next_page_selection_updates(
                m.RepoLangs, dict(first=5, after="test-3rd-page-cursor")
            ),
        )
        == _.repository[
            _.id.databaseId.name.languages(first=5, after="test-3rd-page-cursor")[
                _.pageInfo[_.hasNextPage.endCursor].edges[_.node[_.id.name]]
            ]
        ]
    )


@pytest.mark.parametrize("resource", m._resources, ids=lambda r: r.kind.name)
def test_get_first_page_selection_against_fixtures(
    resource, github_args_dict, owner_repo_dict
):
    context = m.ChainMap(
        github_args_dict, owner_repo_dict, dict(parent_after="test_parent_after_cursor")
    )
    expected_serialized = load_graphql_fixture(f"{resource.kind.name}_first_selection")
    serialized = str(
        m.get_first_page_selection(
            resource, m.get_first_page_selection_updates(resource, context)
        )
    )
    assert serialized == expected_serialized


@pytest.fixture(scope="module")
def logger():
    return m.logging.getLogger("fpr.pipelines.github_model_test")


@pytest.fixture(scope="module")
def github_schema():
    tests_dir = pathlib.Path(__file__).parent / ".."
    schema = m.quiz.Schema.from_path(
        tests_dir / "fixtures" / "graphql" / f"github_schema.json"
    )
    return schema


get_next_requests_for_initial_requests_params = [
    ([], []),
    (["REPO"], [m.Repo.kind]),
    (
        [k.name for k in m.ResourceKind],
        [m.Repo.kind, m.RepoLangs.kind, m.RepoManifests.kind, m.RepoVulnAlerts.kind],
    ),
]


@pytest.mark.parametrize(
    "github_resource_types,expected_request_resources",
    get_next_requests_for_initial_requests_params,
    ids=[
        f"github_query_type:{repr(p[0])}"
        for p in get_next_requests_for_initial_requests_params
    ],
)
def test_get_next_requests_for_initial_requests(
    logger,
    github_args_dict,
    owner_repo_dict,
    github_resource_types,
    expected_request_resources,
):
    context = m.ChainMap(
        github_args_dict, owner_repo_dict, {"github_query_type": github_resource_types}
    )
    initial_requests = list(m.get_next_requests(logger, context, None))
    assert len(initial_requests) == len(expected_request_resources)
    for r, er in zip(initial_requests, expected_request_resources):
        assert r.resource.kind == er

        expected_serialized = load_graphql_fixture(f"{er.name}_first_selection")
        assert str(r.graphql) == str(expected_serialized)


all_resource_kinds = [k.name for k in m.ResourceKind]


def id_resource_by_kind(val):
    if isinstance(val, m.Resource):
        return f"{val.kind.name}"
    else:
        return repr(val)


@pytest.mark.parametrize("last_resource", m._resources, ids=id_resource_by_kind)
def test_get_next_requests_for_last_page_returns_no_more_requests_for_resource(
    logger, github_args_dict, owner_repo_dict, last_resource
):
    context = m.ChainMap(
        owner_repo_dict, github_args_dict, {"github_query_type": all_resource_kinds}
    )
    last_exchange = m.RequestResponseExchange(
        request=m.Request(
            resource=last_resource,
            graphql=m.get_first_page_selection(
                last_resource,
                m.get_first_page_selection_updates(last_resource, context),
            ),
        ),
        response=m.Response(
            resource=last_resource,
            json=load_json_fixture(
                f"{last_resource.kind.name}_first_page_response_no_next_page"
            ),
        ),
    )
    next_requests = list(m.get_next_requests(logger, context, last_exchange))
    assert all(r.resource != last_resource for r in next_requests)
    for r in next_requests:
        assert_selection_is_sane(r.graphql, github_schema)
        assert str(r.graphql) == load_graphql_fixture(
            f"{r.resource.kind.name}_next_selection"
        ), f"did not matched expected serialized \
gql for next {r.resource.kind} from {last_exchange.request.resource.kind}"


@pytest.mark.parametrize(
    "last_resource", [r for r in m._resources if r != m.Repo], ids=id_resource_by_kind
)
def test_get_next_requests_returns_more_pages_of_the_same_resource_and_linked_resources(
    logger, github_args_dict, owner_repo_dict, last_resource, github_schema
):
    context = m.ChainMap(
        owner_repo_dict,
        github_args_dict,
        {
            "github_query_type": all_resource_kinds,
            "parent_after": "test_parent_after_cursor",  # only for nested pages
        },
    )
    last_exchange = m.RequestResponseExchange(
        request=m.Request(
            resource=last_resource,
            graphql=m.get_first_page_selection(
                last_resource,
                m.get_first_page_selection_updates(last_resource, context),
            ),
        ),
        response=m.Response(
            resource=last_resource,
            json=load_json_fixture(
                f"{last_resource.kind.name}_first_page_response_next_page"
            ),
        ),
    )
    next_requests = list(m.get_next_requests(logger, context, last_exchange))
    assert len(next_requests) == 1 + len(last_resource.children)
    for r in next_requests:
        assert_selection_is_sane(r.graphql, github_schema)

        if r.resource in last_resource.children:
            assert str(r.graphql) == load_graphql_fixture(
                f"{r.resource.kind.name}_nested_first_selection"
            ), f"did not matched expected serialized \
gql for next {r.resource.kind} from {last_exchange.request.resource.kind}"
        else:
            assert str(r.graphql) == load_graphql_fixture(
                f"{r.resource.kind.name}_next_selection"
            ), f"did not matched expected serialized \
gql for next {r.resource.kind} from {last_exchange.request.resource.kind}"


@pytest.mark.parametrize("last_resource", m._resources, ids=id_resource_by_kind)
def test_get_next_requests_for_last_page_returns_no_more_requests_for_resource(
    logger, github_args_dict, owner_repo_dict, last_resource, github_schema
):
    context = m.ChainMap(
        owner_repo_dict,
        github_args_dict,
        {
            "github_query_type": all_resource_kinds,
            "parent_after": "test_parent_first_page_after_cursor",  # only for nested pages
        },
    )
    last_exchange = m.RequestResponseExchange(
        request=m.Request(
            resource=last_resource,
            graphql=m.get_first_page_selection(
                last_resource,
                m.get_first_page_selection_updates(last_resource, context),
            ),
        ),
        response=m.Response(
            resource=last_resource,
            json=load_json_fixture(
                f"{last_resource.kind.name}_first_page_response_no_next_page"
            ),
        ),
    )
    next_requests = list(m.get_next_requests(logger, context, last_exchange))
    for r in next_requests:
        assert r.resource != last_resource
        assert_selection_is_sane(r.graphql, github_schema)
        assert str(r.graphql) == load_graphql_fixture(
            f"{r.resource.kind.name}_nested_first_selection"
        ), f"did not matched expected serialized \
gql for next {r.resource.kind} from {last_exchange.request.resource.kind}"


def test_get_next_requests_only_returns_requests_for_enabled_resource(
    logger, github_args_dict, owner_repo_dict, github_schema
):
    last_resource = m.RepoManifests
    context = m.ChainMap(
        owner_repo_dict,
        github_args_dict,
        {
            "github_query_type": [m.RepoManifests],
            "parent_after": "test_parent_after_cursor",  # only for nested pages
        },
    )
    last_exchange = m.RequestResponseExchange(
        request=m.Request(
            resource=last_resource,
            graphql=m.get_first_page_selection(
                last_resource,
                m.get_first_page_selection_updates(
                    last_resource, m.ChainMap(context, owner_repo_dict)
                ),
            ),
        ),
        response=m.Response(
            resource=last_resource,
            json=load_json_fixture(
                f"{last_resource.kind.name}_first_page_response_next_page"
            ),
        ),
    )
    next_requests = list(m.get_next_requests(logger, context, last_exchange))
    assert len(next_requests) == 1
    r = next_requests[0]
    assert r.resource == m.RepoManifests
    assert_selection_is_sane(r.graphql, github_schema)
    assert str(r.graphql) == load_graphql_fixture(
        f"{r.resource.kind.name}_next_selection"
    ), f"did not matched expected serialized \
gql for next {r.resource.kind} from {last_exchange.request.resource.kind}"
