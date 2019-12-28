import argparse
import logging
import sys
import time
import json
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Generator, AsyncGenerator

from fpr.rx_util import on_next_save_to_jsonl
from fpr.serialize_util import (
    get_in,
    extract_fields,
    iter_jsonlines,
    REPO_FIELDS,
    RUST_FIELDS,
)
import fpr.docker.containers as containers
from fpr.models import GitRef, OrgRepo, Pipeline
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.cargo_audit")

__doc__ = """
Given a repo_url and git ref, clones the repo, finds Cargo.lock files, and runs cargo audit on them.
"""


@dataclass
class CargoAuditBuildArgs:
    base_image_name: str = "rust"
    base_image_tag: str = "1"

    cargo_audit_version: str = ""

    # NB: for buster variants a ripgrep package is available
    _DOCKERFILE = """
FROM {0.base_image}
RUN curl -LO https://github.com/BurntSushi/ripgrep/releases/download/11.0.2/ripgrep_11.0.2_amd64.deb
RUN dpkg -i ripgrep_11.0.2_amd64.deb
RUN cargo install {0._cargo_audit_install_args}
CMD ["cargo", "audit", "--json"]
"""

    repo_tag = "dep-obs/cargo-audit"

    @property
    def base_image(self) -> str:
        return "{0.base_image_name}:{0.base_image_tag}".format(self)

    @property
    def _cargo_audit_install_args(self) -> str:
        if self.cargo_audit_version:
            return 'cargo-audit --version "{}"'.format(self.cargo_audit_version)
        else:
            return "cargo-audit"

    @property
    def dockerfile(self) -> bytes:
        return CargoAuditBuildArgs._DOCKERFILE.format(self).encode("utf-8")


async def build_container(args: CargoAuditBuildArgs = None) -> str:
    # NB: can shell out to docker build if this doesn't work
    if args is None:
        args = CargoAuditBuildArgs()
    await containers.build(args.dockerfile, args.repo_tag, pull=True)
    log.info("image built and successfully tagged {}".format(args.repo_tag))
    return args.repo_tag


async def run_cargo_audit(item: Tuple[OrgRepo, GitRef]):
    org_repo, git_ref = item
    log.debug(
        "running cargo-audit on repo {!r} ref {!r}".format(
            org_repo.github_clone_url, git_ref
        )
    )
    name = "dep-obs-cargo-audit-{0.org}-{0.repo}".format(org_repo)
    async with containers.run(
        "dep-obs/cargo-audit:latest", name=name, cmd="/bin/bash"
    ) as c:
        await containers.ensure_repo(c, org_repo.github_clone_url)
        await containers.ensure_ref(c, git_ref, working_dir="/repo")
        branch = await containers.get_branch(c)
        commit = await containers.get_commit(c)
        tag = await containers.get_tag(c)

        cargo_version = await containers.get_cargo_version(c)
        rustc_version = await containers.get_rustc_version(c)
        cargo_audit_version = await containers.get_cargo_audit_version(c)
        ripgrep_version = await containers.get_ripgrep_version(c)

        log.debug("{} stdout: {}".format(name, await c.log(stdout=True)))
        log.debug("{} stderr: {}".format(name, await c.log(stderr=True)))

        cargo_lockfiles = await containers.find_files(
            ["Cargo.lock"], c, working_dir="/repo"
        )
        log.info("{} found Cargo.lock files: {}".format(c["Name"], cargo_lockfiles))

        results = []
        for cargo_lockfile in cargo_lockfiles:
            working_dir = str(
                containers.path_relative_to_working_dir(
                    working_dir="/repo", file_path=cargo_lockfile
                )
            )
            log.info("working_dir: {}".format(working_dir))
            cargo_audit = await containers.cargo_audit(c, working_dir=working_dir)

            result = dict(
                org=org_repo.org,
                repo=org_repo.repo,
                ref=git_ref.to_dict(),
                commit=commit,
                branch=branch,
                tag=tag,
                cargo_lockfile_path=cargo_lockfile,
                cargo_version=cargo_version,
                ripgrep_version=ripgrep_version,
                rustc_version=rustc_version,
                cargo_audit_version=cargo_audit_version,
                audit_output=cargo_audit,
            )
            log.debug("{} audit result {}".format(name, result))
            log.debug("{} stdout: {}".format(name, await c.log(stdout=True)))
            log.debug("{} stderr: {}".format(name, await c.log(stderr=True)))
            results.append(result)
        return results


async def run_pipeline(
    source: Generator[Dict[str, Any], None, None], _: argparse.Namespace
) -> AsyncGenerator[OrgRepo, None]:
    log.info("pipeline started")
    try:
        await build_container()
    except Exception as e:
        log.error(
            "error occurred building the cargo audit image: {0}\n{1}".format(
                e, exc_to_str()
            )
        )

    for item in source:
        log.debug("processing {!r}".format(item))
        org_repo, git_ref = (
            OrgRepo.from_github_repo_url(item["repo_url"]),
            GitRef.from_dict(item["ref"]),
        )
        try:
            for result in await run_cargo_audit((org_repo, git_ref)):
                yield result
        except Exception as e:
            log.error("error running run_cargo_audit:\n{}".format(exc_to_str()))


def serialize_cargo_audit_output(audit_output):
    audit_output = json.loads(audit_output)
    result = {}
    for read_key_path, output_key in [
        [["lockfile", "dependency-count"], "lockfile_dependency_count"],
        [["lockfile", "path"], "lockfile_path"],  # str
        [["vulnerabilities", "count"], "vulnerabilities_count"],  # int
        [["vulnerabilities", "found"], "vulnerabilities_found"],  # bool
        [["vulnerabilities", "list"], "vulnerabilities"],  # object
    ]:
        result[output_key] = get_in(audit_output, read_key_path)
    return result


FIELDS = (
    RUST_FIELDS
    | REPO_FIELDS
    | {"cargo_lockfile_path", "cargo_audit_version", "ripgrep_version"}
)


def serialize(_: argparse.Namespace, audit_result: Dict):
    r = extract_fields(audit_result, FIELDS)
    r["audit"] = serialize_cargo_audit_output(audit_result["audit_output"])
    return r


pipeline = Pipeline(
    name="cargo_audit",
    desc=__doc__,
    fields=FIELDS,
    reader=iter_jsonlines,
    runner=run_pipeline,
    serializer=serialize,
    writer=on_next_save_to_jsonl,
)
