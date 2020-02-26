from dataclasses import asdict, dataclass, field
import enum
import functools
import pathlib
from typing import AbstractSet, Any, Callable, Dict, List

from fpr.models.docker_image import DockerImage, DockerImageName


@enum.unique
class DependencyFileKind(enum.Enum):
    MANIFEST_FILE = enum.auto()
    LOCKFILE = enum.auto()


@dataclass(frozen=True)
class DependencyFilePattern:
    search_glob: str
    kind: DependencyFileKind


@dataclass(frozen=True)
class DependencyFile:
    # path relative to the repo root including the filename
    path: pathlib.Path

    # sha256 hex digest of the file
    sha256: str

    @staticmethod
    def from_dict(d: Dict) -> "DependencyFile":
        return DependencyFile(path=pathlib.Path(d["path"]), sha256=d["sha256"])

    def to_dict(self: "DependencyFile") -> Dict:
        d = asdict(self)
        d["path"] = str(self.path)
        return d


def always_true(_: AbstractSet[str]) -> bool:
    return True


@dataclass(frozen=True)
class ContainerTask:
    # task name for logginer e.g. audit, list_metadata
    name: str

    # the command to run e.g. 'echo true' or 'npm install'
    command: str

    # check on files in the working directory to run the command; defaults to
    # always True
    has_files_check: Callable[[AbstractSet[str]], bool] = field(default=always_true)

    # check and throw if the exit code is non-zero
    check: bool = False


@dataclass(frozen=True)
class PackageManager:
    name: str

    # tasks to run to install, list metadata, audit dependency files or run other actions
    tasks: Dict[str, ContainerTask]

    # ripgrep patterns to search for the dependency files
    patterns: List[DependencyFilePattern]
    ignore_patterns: List[str] = field(default_factory=list)

    # commands for listing the package manager version
    version_commands: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Language:
    name: str
    package_managers: Dict[str, PackageManager]

    # commands for listing the language compiler or runtime version
    version_commands: Dict[str, str]

    # docker images to build and run tasks in
    images: Dict[str, DockerImage]


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


def has_file(filename: str, files: AbstractSet[str]) -> bool:
    return filename in files


def has_manifest_with_any_lockfile(
    manifest_filename: str, lockfilenames: AbstractSet[str], files: AbstractSet[str]
) -> bool:
    return has_file(manifest_filename, files) and any(
        has_file(lockfilename, files) for lockfilename in lockfilenames
    )


has_npm_manifest_with_any_lockfile = functools.partial(
    has_manifest_with_any_lockfile,
    "package.json",
    {"package-lock.json", "npm-shrinkwrap.json"},
)
has_package_json_and_yarn_lock = functools.partial(
    has_manifest_with_any_lockfile, "package.json", {"yarn.lock"}
)
has_package_json = functools.partial(has_file, "package.json")
has_package_lock_json = functools.partial(has_file, "package-lock.json")


def has_package_json_and_package_lock_json(files: AbstractSet[str]) -> bool:
    return has_package_json(files) and has_package_lock_json(files)


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
            tasks={
                "install": ContainerTask(
                    name="install",
                    command="npm install --save=true",
                    # NB: create or update package-lock.json or npm-shrinkwrap.json
                    has_files_check=has_package_json,
                ),
                "ci": ContainerTask(
                    name="ci",
                    command="npm ci",
                    # ci errors for missing package-lock.json or npm-shrinkwrap.json
                    # and does not update the files
                    has_files_check=has_npm_manifest_with_any_lockfile,
                ),
                "list_metadata": ContainerTask(
                    name="list_metadata",
                    # list requires "npm ci" or "npm install" to not just show a bunch of missing warnings/errors
                    command="npm list --json",  # or "npm list --json --long"
                    has_files_check=has_package_json,
                ),
                "audit": ContainerTask(
                    name="audit",
                    command="npm audit --json",
                    has_files_check=has_package_json,  # has_npm_manifest_with_any_lockfile,
                ),
                "pack": ContainerTask(
                    name="pack", command="npm pack .", has_files_check=has_package_json
                ),
            },
            version_commands={"npm": "npm --version"},
        ),
        PackageManager(
            name="yarn",
            patterns=[
                dependency_file_patterns["package.json"],
                dependency_file_patterns["yarn.lock"],
            ],
            ignore_patterns=[],
            tasks={
                "install": ContainerTask(
                    name="install",
                    command="yarn install --frozen-lockfile",
                    has_files_check=has_package_json_and_yarn_lock,
                ),
                "list_metadata": ContainerTask(
                    name="list_metadata",
                    command="yarn list --json --frozen-lockfile",
                    has_files_check=has_package_json_and_yarn_lock,
                ),
                "audit": ContainerTask(
                    name="audit",
                    command="yarn audit --json --frozen-lockfile",
                    has_files_check=has_package_json_and_yarn_lock,
                ),
                "pack": ContainerTask(
                    name="pack", command="yarn pack .", has_files_check=has_package_json
                ),
            },
            version_commands={"yarn": "yarn --version"},
        ),
        PackageManager(
            name="cargo",
            patterns=[
                dependency_file_patterns["cargo.toml"],
                dependency_file_patterns["cargo.lock"],
            ],
            ignore_patterns=[],
            tasks={
                "install": ContainerTask(
                    name="install",
                    command="cargo install --all-features --locked",
                    has_files_check=lambda files: ("Cargo.toml" in files),
                ),
                "list_metadata": ContainerTask(
                    name="list_metadata",
                    command="cargo metadata --format-version 1 --locked",
                    has_files_check=lambda files: ("Cargo.toml" in files),
                ),
                "audit": ContainerTask(
                    name="audit",
                    command="cargo audit --json",
                    has_files_check=lambda files: ("Cargo.lock" in files),
                ),
                "pack": ContainerTask(
                    name="pack",
                    # creates target/package/<package name>-<pkg version>.crate
                    command="cargo build",  # or -p <package name>
                    has_files_check=lambda files: ("Cargo.toml" in files),
                ),
            },
            version_commands={
                "cargo": "cargo --version",
                "cargo-audit": "cargo audit --version",
            },
        ),
    ]
}
package_manager_names = [pm.name for pm in package_managers.values()]


docker_images: Dict[str, DockerImage] = {
    "dep-obs/find-git-refs:latest": DockerImage(
        base=DockerImageName(None, "debian", "buster-slim"),
        local=DockerImageName("dep-obs", "find-git-refs", "latest"),
        dockerfile_template="""FROM {base.repo_name}:{base.tag}
RUN apt-get -y update && apt-get install -y git ripgrep
CMD ["bash", "-c"]
""",
    ),
    "dep-obs/find-dep-files:latest": DockerImage(
        base=DockerImageName(None, "debian", "buster-slim"),
        local=DockerImageName("dep-obs", "find-dep-files", "latest"),
        dockerfile_template="""FROM {base.repo_name}:{base.tag}
RUN apt-get -y update && apt-get install -y git ripgrep
CMD ["bash", "-c"]
""",
    ),
    "dep-obs/node-10:latest": DockerImage(
        base=DockerImageName(None, "node", "10-buster-slim"),
        local=DockerImageName("dep-obs", "node-10", "latest"),
        dockerfile_template="""FROM {base.repo_name}:{base.tag}
RUN apt-get -y update && apt-get install -y git ripgrep
CMD ["node"]
""",
    ),
    "dep-obs/rust-1:latest": DockerImage(
        base=DockerImageName(None, "rust", "1-buster-slim"),
        local=DockerImageName("dep-obs", "rust-1", "latest"),
        dockerfile_template="""FROM {base.repo_name}:{base.tag}
RUN apt-get -y update && apt-get install -y git ripgrep
RUN cargo install cargo-audit
CMD ["rustc"]
""",
    ),
}
docker_image_names = list(docker_images.keys())

languages: Dict[str, Language] = {
    l.name: l
    for l in [
        Language(
            name="rust",
            package_managers={pm.name: pm for pm in [package_managers["cargo"]]},
            version_commands={"rustc": "rustc --version"},
            images={"dep-obs/rust-1:latest": docker_images["dep-obs/rust-1:latest"]},
        ),
        Language(
            name="nodejs",
            package_managers={
                pm.name: pm
                for pm in [package_managers["npm"], package_managers["yarn"]]
            },
            version_commands={"node": "node --version"},
            images={"dep-obs/node-10:latest": docker_images["dep-obs/node-10:latest"]},
        ),
    ]
}
language_names = [l.name for l in languages.values()]
