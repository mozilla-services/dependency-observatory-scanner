import argparse
import itertools
import json
from typing import Any, Dict, Iterable, Set, Sequence, List, Union, Generator

JSONPathElement = Union[int, str]
JSONPath = Sequence[JSONPathElement]


def get_in(d: Dict, path: Iterable[JSONPathElement], default: Any = None):
    sentinel = object()
    for path_part in path:
        if isinstance(path_part, str):
            if not hasattr(d, "get"):
                return default
            assert hasattr(d, "get")
            d = d.get(path_part, sentinel)
            if d == sentinel:
                return default
        elif isinstance(path_part, int):
            if not hasattr(d, "__getitem__"):
                return default
            assert hasattr(d, "__getitem__")
            if not (-1 < path_part < len(d)):
                return default
            d = d[path_part]
        else:
            raise NotImplementedError()
    return d


REPO_FIELDS = {"org", "repo", "commit", "branch", "tag", "ref"}


def extract_fields(d: Dict, fields: Iterable[str]) -> Dict:
    "returns a new dict with top-level param fields extracted from param d"
    return {field: d.get(field) for field in fields}


def extract_nested_fields(d: Dict, fields: Dict[str, JSONPath]) -> Dict:
    return {field: get_in(d, path, None) for field, path in fields.items()}


def iter_jsonlines(
    f: Sequence,
) -> Generator[Union[Dict, Sequence, int, str, None], None, None]:
    "Generator over JSON lines http://jsonlines.org/ files with extension .jsonl"
    for line in f:
        yield json.loads(line)


def identity_serializer(_: argparse.Namespace, result: Dict) -> Dict:
    return result


def grouper(iterable: Iterable[Any], n: int, fillvalue: Any = None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    # from https://docs.python.org/3/library/itertools.html#itertools-recipes
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)
