import logging
import sys
import time
import json
from dataclasses import dataclass

import rx
import rx.operators as op
from rx.subject import Subject

from fpr.rx_util import map_async
from fpr.serialize_util import get_in
import fpr.containers as containers
from fpr.models.org_repo import OrgRepo
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.cargo_audit")


@dataclass
class CargoAuditBuildArgs:
    base_image_name: str = "rust"
    base_image_tag: str = "1"

    cargo_audit_version: str = ""

    # NB: for buster variants a ripgrep package is available
    _DOCKERFILE = """
FROM {0.base_image}
RUN curl -LO https://github.com/BurntSushi/ripgrep/releases/download/11.0.1/ripgrep_11.0.1_amd64.deb
RUN dpkg -i ripgrep_11.0.1_amd64.deb
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
    def dockerfile(self) -> str:
        return CargoAuditBuildArgs._DOCKERFILE.format(self).encode("utf-8")


async def build_container(args: CargoAuditBuildArgs = None) -> "Future[None]":
    # NB: can shell out to docker build if this doesn't work
    if args is None:
        args = CargoAuditBuildArgs()
    await containers.build(args.dockerfile, args.repo_tag, pull=True)
    return args.repo_tag


async def run_cargo_audit(org_repo, commit="master"):
    name = "dep-obs-cargo-audit-{0.org}-{0.repo}".format(org_repo)
    async with containers.run(
        "dep-obs/cargo-audit:latest", name=name, cmd="/bin/bash"
    ) as c:
        await containers.ensure_repo(c, org_repo.github_clone_url, commit=commit)
        commit = await containers.get_commit(c)
        cargo_version = await containers.get_cargo_version(c)
        rustc_version = await containers.get_rustc_version(c)
        cargo_audit_version = await containers.get_cargo_audit_version(c)
        ripgrep_version = await containers.get_ripgrep_version(c)

        log.debug("{} stdout: {}".format(name, await c.log(stdout=True)))
        log.debug("{} stderr: {}".format(name, await c.log(stderr=True)))

        cargo_lockfiles = await containers.find_cargo_lockfiles(c, working_dir="/repo")
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
                commit=commit,
                # branch
                # tag
                cargo_lockfile=cargo_lockfile,
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


def on_build_next(tag):
    log.info("tagged image {}".format(tag))


def on_build_error(e):
    log.error("error occurred building the cargo audit image: {0}".format(e))
    raise e


def on_build_complete():
    log.info("image built successfully")


def run_pipeline(source):
    build_status = Subject()

    # workaround for 'RuntimeError: no running event loop'
    build_pipeline = rx.of(["start_build"]).pipe(
        op.do_action(lambda x: log.info("pipeline started")),
        map_async(lambda x: build_container()),
        op.do_action(
            on_next=on_build_next,
            on_error=on_build_error,
            on_completed=on_build_complete,
        ),
    )

    def on_run_cargo_audit_error(e, _, *args):
        log.error("error running run_cargo_audit:\n{}".format(exc_to_str()))
        return rx.from_iterable([])

    pipeline = rx.concat(build_pipeline, source).pipe(
        op.skip(1),  # skip the build_pipeline sentinal
        op.map(lambda x: x["repo_url"]),
        op.map(OrgRepo.from_github_repo_url),
        op.do_action(lambda x: log.debug("processing {}".format(x))),
        map_async(run_cargo_audit),
        op.catch(on_run_cargo_audit_error),
        op.do_action(lambda x: log.debug("processed {}".format(x))),
        op.map(lambda x: rx.from_iterable(x)),
        op.merge_all(),
    )

    return pipeline


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


def serialize(audit_result):
    log.debug("serializing result {}".format(audit_result))
    r = {
        k: v
        for k, v in audit_result.items()
        if k
        in {
            "org",
            "repo",
            "commit",
            "branch",
            "tag",
            "commit",
            "cargo_lockfile_path",
            "cargo_version",
            "rustc_version",
            "cargo_audit_version",
            "ripgrep_version",
        }
    }
    r["audit"] = serialize_cargo_audit_output(audit_result["audit_output"])
    log.debug("serialized result {}".format(r))
    return r
