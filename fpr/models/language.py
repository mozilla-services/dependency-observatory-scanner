from dataclasses import dataclass, field
import enum
from typing import Dict, List


@enum.unique
class DependencyFileKind(enum.Enum):
    MANIFEST_FILE = enum.auto()
    LOCKFILE = enum.auto()


@dataclass(frozen=True)
class DependencyFilePattern:
    search_glob: str
    kind: DependencyFileKind


@dataclass(frozen=True)
class PackageManager:
    name: str

    # ripgrep patterns to search for the dependency files
    patterns: List[DependencyFilePattern]
    ignore_patterns: List[str] = field(default_factory=list)

    # commands to run to install, list metadata, audit dependency files or run other actions
    commands: Dict[str, List[str]] = field(
        default_factory=lambda: dict(install=list(), list_metadata=list(), audit=list())
    )


@dataclass(frozen=True)
class Language:
    name: str
    package_managers: List[PackageManager]


dependency_file_patterns: Dict[str, DependencyFilePattern] = {
    dfp.search_glob: dfp
    for dfp in [
        DependencyFilePattern(
            search_glob="package.json", kind=DependencyFileKind.MANIFEST_FILE
        ),
        DependencyFilePattern(
            search_glob="package-lock.json", kind=DependencyFileKind.LOCKFILE
        ),
        DependencyFilePattern(
            search_glob="yarn.lock", kind=DependencyFileKind.LOCKFILE
        ),
        DependencyFilePattern(
            search_glob="npm-shrinkwrap.json", kind=DependencyFileKind.LOCKFILE
        ),
        DependencyFilePattern(
            search_glob="cargo.lock", kind=DependencyFileKind.LOCKFILE
        ),
        DependencyFilePattern(
            search_glob="cargo.toml", kind=DependencyFileKind.MANIFEST_FILE
        ),
    ]
}

package_managers: Dict[str, PackageManager] = {
    pm.name: pm
    for pm in [
        PackageManager(
            name="npm",
            patterns=[
                dependency_file_patterns["package.json"],
                dependency_file_patterns["package-lock.json"],
                dependency_file_patterns["npm-shrinkwrap.json"],
            ],
            ignore_patterns=["node_modules/"],
            commands={
                # requires package-lock.json or npm-shrinkwrap.json
                "install": ["npm ci"],
                "list_metadata": ["npm list --json"],
                "audit": ["npm audit --json"],
            },
        ),
        PackageManager(
            name="yarn",
            patterns=[
                dependency_file_patterns["package.json"],
                dependency_file_patterns["yarn.lock"],
            ],
            ignore_patterns=[],
            commands={
                "install": ["yarn install --frozen-lockfile"],
                "list_metadata": ["yarn list --json --frozen-lockfile"],
                "audit": ["yarn audit --json --frozen-lockfile"],
            },
        ),
        PackageManager(
            name="cargo",
            patterns=[
                dependency_file_patterns["cargo.toml"],
                dependency_file_patterns["cargo.lock"],
            ],
            ignore_patterns=[],
            commands={
                "install": ["cargo install --all-features --locked"],
                "list_metadata": ["cargo metadata --format-version 1 --locked"],
                "audit": ["cargo audit --json"],
            },
        ),
    ]
}


languages: Dict[str, Language] = {
    l.name: l
    for l in [
        Language(name="rust", package_managers=[package_managers["cargo"]]),
        Language(
            name="nodejs",
            package_managers=[package_managers["npm"], package_managers["yarn"]],
        ),
    ]
}
