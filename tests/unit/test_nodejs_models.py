# -*- coding: utf-8 -*-

import functools
import itertools
import pathlib
import json
from typing import Any, Callable, Dict, List, Sequence, Tuple, Union, Optional

import pytest

import context
import fpr.models.nodejs as m


def load_json_fixture(path: str) -> Dict[str, Any]:
    with open(path, "r") as fin:
        return json.load(fin)


@pytest.mark.parametrize(
    "node_js_ls_output,expected",
    [
        pytest.param({}, [], id="empty_dict"),
        pytest.param({"dependencies": {}}, [], id="empty_deps_dict"),
    ],
)
def test_visit_deps(
    node_js_ls_output: Dict[str, Union[str, Dict]], expected: List[m.JSONPath]
):
    visited = list(m.visit_deps(node_js_ls_output))
    for i, (visit_path, expected_path) in enumerate(
        itertools.zip_longest(visited, expected)
    ):
        assert (
            visit_path == expected_path
        ), f"unexpected path at index {i} got {visit_path} expected {expected_path}"
    assert visited == expected


@pytest.mark.parametrize(
    "node_js_ls_output_path,expected_json_path",
    itertools.zip_longest(
        sorted(
            (
                pathlib.Path(__file__).parent
                / ".."
                / "fixtures"
                / "nodejs"
                / "visit"
                / "input"
            ).glob("*.json")
        ),
        sorted(
            (
                pathlib.Path(__file__).parent
                / ".."
                / "fixtures"
                / "nodejs"
                / "visit"
                / "output"
            ).glob("*.json")
        ),
    ),
)
def test_visit_deps_from_fixtures(
    node_js_ls_output_path: pathlib.Path, expected_json_path: pathlib.Path
):
    node_js_ls_output = load_json_fixture(node_js_ls_output_path)
    expected = load_json_fixture(expected_json_path)

    visited = list(m.visit_deps(node_js_ls_output))
    for i, (visit_path, expected_path) in enumerate(
        itertools.zip_longest(visited, expected)
    ):
        assert (
            visit_path == expected_path
        ), f"unexpected path at index {i} got {visit_path} expected {expected_path}"
    assert visited == expected


@pytest.mark.parametrize(
    "node_js_ls_output,expected",
    [
        pytest.param({}, [], id="empty_dict"),
        pytest.param({"dependencies": {}}, [], id="empty_deps_dict"),
    ],
)
def test_flatten_deps(
    node_js_ls_output: Dict[str, Union[str, Dict]], expected: List[m.NPMPackage]
):
    visited = list(m.flatten_deps(node_js_ls_output))
    assert visited == expected


@pytest.mark.parametrize(
    "node_js_ls_output_path,expected_json_path",
    itertools.zip_longest(
        sorted(
            (
                pathlib.Path(__file__).parent
                / ".."
                / "fixtures"
                / "nodejs"
                / "flatten"
                / "input"
            ).glob("*.json")
        ),
        sorted(
            (
                pathlib.Path(__file__).parent
                / ".."
                / "fixtures"
                / "nodejs"
                / "flatten"
                / "output"
            ).glob("*.json")
        ),
    ),
)
def test_flatten_deps_from_fixtures(
    node_js_ls_output_path: str, expected_json_path: str
):
    node_js_ls_output = load_json_fixture(node_js_ls_output_path)
    expected = [m.NPMPackage(**item) for item in load_json_fixture(expected_json_path)]

    flattened = list(m.flatten_deps(node_js_ls_output))
    for i, (flattened_dep, expected_dep) in enumerate(
        itertools.zip_longest(flattened, expected)
    ):
        assert (
            flattened_dep == expected_dep
        ), f"unexpected dep at index {i} got {flattened_dep} expected {expected_dep}"
    assert flattened == expected
