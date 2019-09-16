# -*- coding: utf-8 -*-

import json
import pathlib
import pickle
from typing import Callable, Any

import pytest

import context

import fpr.pipelines
from fpr.pipelines import pipelines


def load_test_fixture(filename: str, load_fn: Callable) -> Any:
    tests_dir = pathlib.Path(__file__).parent / ".."
    with (tests_dir / "fixtures" / filename).open("r+b") as fin:
        return load_fn(fin)


@pytest.mark.parametrize("pipeline", pipelines, ids=lambda p: p.name)
def test_serialize_returns_audit_result(pipeline):
    # TODO: have crate graph output jsonl and extract dot graph from each line
    if pipeline.name == "crate_graph":
        return pytest.xfail()

    # TODO: convert other unserialized fixtures to .pickle
    if pipeline.name == "rust_changelog":
        unserialized = load_test_fixture(
            "{}_unserialized.pickle".format(pipeline.name), pickle.load
        )
    else:
        unserialized = load_test_fixture(
            "{}_unserialized.json".format(pipeline.name), json.load
        )
    expected_serialized = load_test_fixture(
        "{}_serialized.json".format(pipeline.name), json.load
    )

    serialized = pipeline.serializer(None, unserialized)
    for field in sorted(pipeline.fields):
        assert field in serialized
        assert field in expected_serialized
        assert serialized[field] == expected_serialized[field]

    assert serialized == expected_serialized
