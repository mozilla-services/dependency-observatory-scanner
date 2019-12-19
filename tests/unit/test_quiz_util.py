# -*- coding: utf-8 -*-

import dataclasses
import functools

import pytest

import context
import fpr.quiz_util as m


@pytest.fixture(scope="module")
def _():
    return m.quiz.SELECTOR


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
def set_org_repo_kwargs():
    def add_org_repo_to_repository_field(
        selection: m.quiz.Selection,
    ) -> m.quiz.Selection:
        return m.update_in(
            selection,
            ["repository"],
            functools.partial(
                m.upsert_kwargs, "repository", dict(owner="owner", name="repo_name")
            ),
        )

    return add_org_repo_to_repository_field


def test_get_in(_):
    selection = _.repository(owner="testrepoowner", name="testreponame")[_.id]

    assert m.get_in(selection, ["DNE"]) is None
    assert m.get_in(selection, []) == selection
    assert m.get_in(selection, ["repository"]) == selection
    assert m.get_in(selection, ["repository", "id"]) == _.id

    assert m.get_in(selection, [0]) == selection
    assert m.get_in(selection, [1]) is None
    assert m.get_in(selection, [0, 0]) == _.id

    vuln_alert_vulns_sel = _.repository(owner="owner", name="repo_name")[
        _.databaseId.id.name.vulnerabilityAlerts(first=1, after="after")[
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

    assert str(
        m.get_in(
            vuln_alert_vulns_sel,
            [
                "repository",
                "vulnerabilityAlerts",
                "edges",
                "node",
                "securityAdvisory",
                "vulnerabilities",
            ],
        )
    ) == str(
        _.id.ghsaId.summary.description.severity.publishedAt.updatedAt.withdrawnAt.identifiers[
            _.type.value
        ].vulnerabilities(
            first=25
        )[
            _.pageInfo[_.hasNextPage.endCursor].totalCount.nodes[
                _.package[_.name.ecosystem].severity.updatedAt.vulnerableVersionRange
            ]
        ]
    )


def test_update_in_top_level_by_name(_, set_org_repo_kwargs):
    selection = _.repository(owner="testrepoowner", name="testreponame")[_.id]
    assert (
        m.update_in(selection, ["repository"], set_org_repo_kwargs)
        == _.repository(owner="owner", name="repo_name")[_.id]
    )


def test_update_in_top_level_by_index(_, set_org_repo_kwargs):
    selection = _.foo.repository(owner="testrepoowner", name="testreponame")[_.id]
    assert (
        m.update_in(selection, [1], set_org_repo_kwargs)
        == _.foo.repository(owner="owner", name="repo_name")[_.id]
    )


def test_update_in_nested_by_name(_, set_org_repo_kwargs):
    selection = _.baz.foo[
        _.bar.repository(owner="testrepoowner", name="testreponame")[_.id]
    ]
    expected_selection = _.baz.foo[
        _.bar.repository(owner="owner", name="repo_name")[_.id]
    ]
    assert (
        m.update_in(selection, ["foo", "repository"], set_org_repo_kwargs)
        == expected_selection
    )


def test_update_in_nested_three_levels(_, set_org_repo_kwargs):
    selection = _.blah[
        _.baz.foo[_.bar.repository(owner="testrepoowner", name="testreponame")[_.id]]
    ]
    expected_selection = _.blah[
        _.baz.foo[_.bar.repository(owner="owner", name="repo_name")[_.id]]
    ]
    assert (
        m.update_in(selection, ["blah", "foo", "repository"], set_org_repo_kwargs)
        == expected_selection
    )


@pytest.mark.xfail(reason="sort out later")
def test_update_in_nested_by_index(_, set_org_repo_kwargs):
    selection = _.foo[
        _.bar.repository(owner="testrepoowner", name="testreponame")[_.id]
    ]
    assert (
        m.update_in(selection, [0, 1], set_org_repo_kwargs)
        == _.foo[_.repository(owner="owner", name="repo_name")[_.id]]
    )


@pytest.mark.xfail(reason="sort out later")
def test_update_in_nested_by_name_then_index(_, set_org_repo_kwargs):
    selection = _.foo[
        _.bar.repository(owner="testrepoowner", name="testreponame")[_.id]
    ]
    assert (
        m.update_in(selection, ["foo", 1], set_org_repo_kwargs)
        == _.foo[_.repository(owner="owner", name="repo_name")[_.id]]
    )


def test_get_kwargs_in(_):
    selection = _.repository(name="foo", owner="blah")[_.id.page(eggs="good")]
    assert m.get_kwargs_in(selection, []) is None
    assert m.get_kwargs_in(selection, ["repository"]) == dict(name="foo", owner="blah")
    assert m.get_kwargs_in(selection, ["repository", "page"]) == dict(eggs="good")
    assert m.get_kwargs_in(selection, ["repository", "page", "does_not_exist"]) is None
