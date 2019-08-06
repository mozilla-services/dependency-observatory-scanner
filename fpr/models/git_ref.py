from dataclasses import dataclass
import enum
from typing import Dict, Tuple, Sequence


@enum.unique
class GitRefKind(enum.Enum):
    BRANCH = "branch"
    COMMIT = "commit"
    TAG = "tag"


@dataclass
class GitRef:
    value: str
    kind: GitRefKind

    @staticmethod
    def from_dict(d: Dict) -> "GitRef":
        """e.g. {"value": "0.9.0", "kind": "tag"}
        -> GitRef(value="0.9.0", kind=GitRefKind.TAG)
        """
        return GitRef(value=d["value"], kind=GitRefKind[d["kind"].upper()])
