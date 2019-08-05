from typing import Any, Dict, List


def get_in(v: Dict, key_path: List, default: Any = None):
    if default is None:
        sentinel = object()
    for key_part in key_path:
        v = v.get(key_part, sentinel)
        if v == sentinel:
            return default
    return v
