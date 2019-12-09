# -*- coding: utf-8 -*-

import argparse
import json
import pathlib
import pickle
from typing import Callable, Any

import pytest

import context

import fpr.serialize_util as m


@pytest.mark.parametrize(
    "path,default,expected",
    [
        ([], None, {"a": 1, "b": {"foo": [-1, {}]}}),
        ([-7], "not found", "not found"),
        (["a"], None, 1),
        (["b", "foo", 1], None, {}),
        (["b", "foo", 1], None, {}),
    ],
)
def test_get_in(path, default, expected):
    assert m.get_in({"a": 1, "b": {"foo": [-1, {}]}}, path, default) == expected


@pytest.mark.parametrize(
    "value,path,default,expected_error",
    [
        ("", [""], None, AssertionError),
        (set(), [-1], None, AssertionError),
        ({}, [set()], None, NotImplementedError),
    ],
)
def test_get_in_errors(value, path, default, expected_error):
    with pytest.raises(expected_error):
        m.get_in(value, path, default)
