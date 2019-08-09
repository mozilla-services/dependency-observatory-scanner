# -*- coding: utf-8 -*-

import json
import pathlib

import pytest

import context
import fpr.pipelines.cargo_audit as cargo_audit
import fpr.pipelines.cargo_metadata as cargo_metadata


def load_test_fixture(filename):
    tests_dir = pathlib.Path(__file__).parent / ".."
    with (tests_dir / "fixtures" / filename).open("r") as fin:
        return json.load(fin)


@pytest.mark.parametrize(
    "pipeline", [cargo_audit, cargo_metadata], ids=lambda p: p.name
)
def test_serialize_returns_audit_result(pipeline):
    unserialized = load_test_fixture("{}_unserialized.json".format(pipeline.name))
    expected_serialized = load_test_fixture("{}_serialized.json".format(pipeline.name))

    serialized = pipeline.serializer(None, unserialized)
    for field in sorted(pipeline.fields):
        assert field in serialized
        assert field in expected_serialized
        assert serialized[field] == expected_serialized[field]

    assert serialized == expected_serialized
