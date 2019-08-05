# -*- coding: utf-8 -*-

import json
import pathlib
import pytest

import context
import fpr.pipelines.cargo_metadata as m
import fpr.serialize_util as su


@pytest.fixture
def cargo_metadata_output():
    tests_dir = pathlib.Path(__file__).parent / ".."
    with (
        tests_dir
        / "fixtures"
        / "mozilla_services_channelserver_79157df7b193857a2e7e3fe8e61e38305e1d47d4_cargo_metadata_output.json"
    ).open("r") as fin:
        return fin.read()


@pytest.fixture
def pipeline_output(cargo_metadata_output):
    return {
        "org": "mozilla-services",
        "repo": "channelserver",
        "commit": "79157df7b193857a2e7e3fe8e61e38305e1d47d4",
        "cargo_version": "cargo 1.36.0 (c4fcfb725 2019-05-15)",
        "ripgrep_version": "ripgrep 11.0.1 (rev 1f1cd9b467)",
        "rustc_version": "rustc 1.36.0 (a53f9df32 2019-07-03)",
        "cargo_tomlfile_path": "Cargo.toml",
        "metadata_output": cargo_metadata_output,
    }


def test_serialize_returns_expected_result(pipeline_output):
    expected_meta_output = json.loads(pipeline_output["metadata_output"])

    serialized = m.serialize(pipeline_output)
    # top-level FIELDS get passed through
    for field in m.FIELDS:
        assert serialized[field] == pipeline_output[field]

    meta = serialized["metadata"]
    assert meta["version"] == 1
    assert meta["root"] is None
    assert len(meta["nodes"]) == 250
    assert meta["nodes"][0] == su.extract_fields(
        expected_meta_output["resolve"]["nodes"][0], m.NODE_FIELDS
    )
