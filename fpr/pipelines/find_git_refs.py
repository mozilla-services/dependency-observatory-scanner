import argparse
import asyncio
from dataclasses import asdict
import functools
import logging
from random import randrange
from typing import Tuple, Dict, Generator, AsyncGenerator, Union, Iterable

from fpr.rx_util import on_next_save_to_jsonl
from fpr.serialize_util import get_in, extract_fields, iter_jsonlines
import fpr.docker.containers as containers
from fpr.docker.images import build_images
import fpr.docker.volumes as volumes
from fpr.models.pipeline import Pipeline
from fpr.models.org_repo import OrgRepo
from fpr.models.git_ref import GitRef
from fpr.models.language import DockerImage, docker_images
from fpr.models.pipeline import add_infile_and_outfile, add_docker_args, add_volume_args
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.find_git_refs")

__doc__ = """
Given a repo_url, clones the repo, lists git refs for each tag
TODO: every Nth commit, or commit every time interval.
TODO: since and until args
TODO: find branches
"""


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_docker_args(parser)
    parser = add_volume_args(parser)
    parser.add_argument(
        "-t",
        "--tags",
        action="store_true",
        default=False,
        required=False,
        help="Output metadata for each tag in the repo. Defaults to False.",
    )
    return parser


async def run_find_git_refs(org_repo: OrgRepo, args: argparse.Namespace):
    # takes a json line with a repo_url
    log.debug(f"finding git refs for repo {org_repo.github_clone_url!r}")
    name = f"dep-obs-find-git-refs-{org_repo.org}-{org_repo.repo}-{hex(randrange(1 << 32))[2:]}"
    results = []
    async with containers.run(
        "dep-obs/find-git-refs:latest",
        name=name,
        cmd="/bin/bash",
        volumes=[
            volumes.DockerVolumeConfig(
                name=f"fpr-org_{org_repo.org}-repo_{org_repo.repo}",
                mount_point="/repos",
                labels=asdict(org_repo),
                delete=not args.keep_volumes,
            )
        ]
        if args.use_volumes
        else [],
    ) as c:
        if not args.use_volumes:
            await c.run("mkdir -p /repos", wait=True, check=True)
        await containers.ensure_repo(
            c, org_repo.github_clone_url, working_dir="/repos/"
        )
        log.debug(f"{name} stdout: {await c.log(stdout=True)}")
        log.debug(f"{name} stderr: {await c.log(stderr=True)}")
        async for tag, tag_ts, commit_ts in containers.get_tags(
            c, working_dir="/repos/repo"
        ):
            git_ref = GitRef.from_dict(
                dict(value=tag, kind="tag", tag_ts=tag_ts, commit_ts=commit_ts)
            )

            result = dict(
                org=org_repo.org,
                repo=org_repo.repo,
                ref=git_ref.to_dict(),
                repo_url=org_repo.github_clone_url,
            )
            log.debug(f"{name} find git refs result {result}")
            results.append(result)
    return results


async def run_pipeline(
    source: Generator[Dict[str, str], None, None], args: argparse.Namespace
) -> AsyncGenerator[OrgRepo, None]:
    log.info("pipeline find_git_refs started")
    if args.docker_build:
        images: Iterable[DockerImage] = [docker_images["dep-obs/find-git-refs:latest"]]
        log.info(
            f"building images: {[image.base.repo_name_tag + ' as ' + image.local.repo_name_tag for image in images]}"
        )
        built_image_tags: Iterable[str] = await build_images(args.docker_pull, images)
        log.info(f"successfully built and tagged images {built_image_tags}")

    for i, item in enumerate(source):
        row = (i, OrgRepo.from_github_repo_url(item["repo_url"]))
        await asyncio.sleep(min(1 * i, 30))
        log.debug(f"processing {row[1]!r}")
        try:
            for ref in await run_find_git_refs(row[1], args):
                yield ref
        except Exception as e:
            log.error(f"error running find_git_refs:\n{exc_to_str()}")


# fields and types for the input and output JSON
IN_FIELDS: Dict[str, type] = {"repo_url": str}
OUT_FIELDS: Dict[str, Union[type, str, Dict[str, str]]] = {
    **IN_FIELDS,
    **asdict(
        OrgRepo.from_github_repo_url(
            "https://github.com/mozilla-services/syncstorage-rs.git"
        )
    ),
    **{"ref": GitRef.from_dict(dict(value="dummy", kind="tag")).to_dict()},
}


pipeline = Pipeline(
    name="find_git_refs",
    desc=__doc__,
    fields=set(OUT_FIELDS.keys()),
    argparser=parse_args,
    reader=iter_jsonlines,
    runner=run_pipeline,
    writer=on_next_save_to_jsonl,
)
