import json
from typing import Any, Dict, Iterable, Set, Sequence, List, Union, Generator


def get_in(d: Dict, key_path: Iterable[str], default: Any = None):
    if default is None:
        sentinel = object()
    for key_part in key_path:
        d = d.get(key_part, sentinel)
        if d == sentinel:
            return default
    return d


REPO_FIELDS = {"org", "repo", "commit", "branch", "tag", "ref"}

RUST_FIELDS = {"cargo_version", "rustc_version"}


def extract_fields(d: Dict, fields: Iterable[str]) -> Dict:
    "returns a new dict with top-level param fields extracted from param d"
    return {field: d.get(field) for field in fields}


def iter_jsonlines(
    f: Sequence
) -> Generator[Union[Dict, Sequence, int, str, None], None, None]:
    "Generator over JSON lines http://jsonlines.org/ files with extension .jsonl"
    for line in f:
        yield json.loads(line)
