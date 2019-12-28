from dataclasses import asdict, dataclass
import enum
from typing import Dict


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

    def to_dict(self: "GitRef") -> Dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d
