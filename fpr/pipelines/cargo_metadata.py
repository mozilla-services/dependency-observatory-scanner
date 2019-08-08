import logging
import sys
import time
import json
from dataclasses import dataclass
from typing import Tuple

import rx
import rx.operators as op

from fpr.rx_util import map_async, on_next_save_to_jsonl
from fpr.serialize_util import (
    get_in,
    extract_fields,
    iter_jsonlines,
    REPO_FIELDS,
    RUST_FIELDS,
)
import fpr.containers as containers
from fpr.models import GitRef, OrgRepo
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.cargo_metadata")

pipeline_name = name = "cargo_metadata"
pipeline_reader = reader = iter_jsonlines
pipeline_writer = writer = on_next_save_to_jsonl


@dataclass
class CargoMetadataBuildArgs:
    base_image_name: str = "rust"
    base_image_tag: str = "1-slim"

    # NB: for buster variants a ripgrep package is available
    _DOCKERFILE = """
FROM {0.base_image}
RUN apt-get -y update && apt-get install -y curl git
RUN curl -LO https://github.com/BurntSushi/ripgrep/releases/download/11.0.2/ripgrep_11.0.2_amd64.deb
RUN dpkg -i ripgrep_11.0.2_amd64.deb
CMD ["cargo", "metadata"]
"""

    repo_tag = "dep-obs/cargo-metadata"

    @property
    def base_image(self) -> str:
        return "{0.base_image_name}:{0.base_image_tag}".format(self)

    @property
    def dockerfile(self) -> str:
        return CargoMetadataBuildArgs._DOCKERFILE.format(self).encode("utf-8")


async def build_container(args: CargoMetadataBuildArgs = None) -> "Future[None]":
    # NB: can shell out to docker build if this doesn't work
    if args is None:
        args = CargoMetadataBuildArgs()
    await containers.build(args.dockerfile, args.repo_tag, pull=True)
    return args.repo_tag


async def run_cargo_metadata(item: Tuple[OrgRepo, GitRef]):
    org_repo, git_ref = item
    log.debug(
        "running cargo-metadata on repo {!r} ref {!r}".format(
            org_repo.github_clone_url, git_ref
        )
    )
    name = "dep-obs-cargo-metadata-{0.org}-{0.repo}".format(org_repo)
    async with containers.run(
        "dep-obs/cargo-metadata:latest", name=name, cmd="/bin/bash"
    ) as c:
        await containers.ensure_repo(c, org_repo.github_clone_url)
        await containers.ensure_ref(c, git_ref, working_dir="/repo")
        branch = await containers.get_branch(c)
        commit = await containers.get_commit(c)
        tag = await containers.get_tag(c)
        cargo_version = await containers.get_cargo_version(c)
        rustc_version = await containers.get_rustc_version(c)
        ripgrep_version = await containers.get_ripgrep_version(c)

        log.debug("{} stdout: {}".format(name, await c.log(stdout=True)))
        log.debug("{} stderr: {}".format(name, await c.log(stderr=True)))

        cargo_tomlfiles = await containers.find_cargo_tomlfiles(c, working_dir="/repo")
        log.info("{} found Cargo.toml files: {}".format(c["Name"], cargo_tomlfiles))

        results = []
        for cargo_tomlfile in cargo_tomlfiles:
            working_dir = str(
                containers.path_relative_to_working_dir(
                    working_dir="/repo", file_path=cargo_tomlfile
                )
            )
            log.info("working_dir: {}".format(working_dir))
            cargo_meta = await containers.cargo_metadata(c, working_dir=working_dir)

            result = dict(
                org=org_repo.org,
                repo=org_repo.repo,
                commit=commit,
                branch=branch,
                tag=tag,
                ref=git_ref.to_dict(),
                cargo_tomlfile_path=cargo_tomlfile,
                cargo_version=cargo_version,
                ripgrep_version=ripgrep_version,
                rustc_version=rustc_version,
                metadata_output=cargo_meta,
            )
            log.debug("{} metadata result {}".format(name, result))
            log.debug("{} stdout: {}".format(name, await c.log(stdout=True)))
            log.debug("{} stderr: {}".format(name, await c.log(stderr=True)))
            results.append(result)
        return results


def on_build_next(tag):
    log.info("tagged image {}".format(tag))


def on_build_error(e):
    log.error("error occurred building the cargo metadata image: {0}".format(e))
    raise e


def on_build_complete():
    log.info("image built successfully")


def run_pipeline(source):
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

    def on_run_cargo_metadata_error(e, _, *args):
        log.error("error running run_cargo_metadata:\n{}".format(exc_to_str()))
        return rx.from_iterable([])

    pipeline = rx.concat(build_pipeline, source).pipe(
        op.skip(1),  # skip the build_pipeline sentinal
        op.map(
            lambda x: (
                OrgRepo.from_github_repo_url(x["repo_url"]),
                GitRef.from_dict(x["ref"]),
            )
        ),
        op.do_action(lambda x: log.debug("processing {!r}".format(x))),
        map_async(run_cargo_metadata),
        op.catch(on_run_cargo_metadata_error),
        op.map(lambda x: rx.from_iterable(x)),
        op.merge_all(),
    )

    return pipeline


def serialize_cargo_metadata_output(metadata_output):
    metadata_output = json.loads(metadata_output)
    result = {}

    for read_key_path, output_key in [
        [["version"], "version"],  # str should be 1
        [["resolve", "root"], "root"],  # can be null str of pkg id
    ]:
        result[output_key] = get_in(metadata_output, read_key_path)

    result["nodes"] = [
        extract_fields(node, NODE_FIELDS)
        for node in get_in(metadata_output, ["resolve", "nodes"])
    ]
    return result


# id: str, features: Seq[str], deps[{}]
NODE_FIELDS = {"id", "features", "deps"}

FIELDS = RUST_FIELDS | REPO_FIELDS | {"cargo_tomlfile_path", "ripgrep_version"}


def serialize(metadata_result):
    r = extract_fields(metadata_result, FIELDS)
    r["metadata"] = serialize_cargo_metadata_output(metadata_result["metadata_output"])
    return r
