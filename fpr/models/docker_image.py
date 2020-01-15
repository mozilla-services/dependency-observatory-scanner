from dataclasses import dataclass
from typing import Optional


@dataclass
class DockerImageName:
    # e.g. mozilla/dependencyscan:latest
    #      ^repo   ^name          ^tag

    # repository name e.g. mozilla
    # use docker.io/library for the official images
    # should be official or an org you trust without a trailing slash
    repo: Optional[str]

    # image name e.g. dependencyscan
    name: str

    # tag name defaults to latest, stretch, 1.31, 1-slim
    tag: str = "latest"

    @property
    def repo_name(self) -> str:
        if self.repo is None:
            return f"{self.name}"
        else:
            return f"{self.repo}/{self.name}"

    @property
    def repo_name_tag(self) -> str:
        return f"{self.repo_name}:{self.tag}"


@dataclass
class DockerImage:
    base: DockerImageName

    # local tag
    local: DockerImageName

    # dockerfile contents template should start with 'FROM {base.repo_name}:{base.tag}'
    dockerfile_template: str

    @property
    def dockerfile_bytes(self) -> bytes:
        return self.dockerfile_template.format(base=self.base).encode("utf-8")
