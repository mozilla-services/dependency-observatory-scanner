import argparse
import asyncio
from dataclasses import asdict, dataclass
import functools
import logging
from random import randrange
from typing import Tuple, Dict, Generator, AsyncGenerator, Union

from fpr.rx_util import on_next_save_to_jsonl
from fpr.serialize_util import get_in, extract_fields, iter_jsonlines
import fpr.docker.containers as containers
import fpr.docker.volumes as volumes
from fpr.models.pipeline import Pipeline
from fpr.models.org_repo import OrgRepo
from fpr.models.git_ref import GitRef
from fpr.models.pipeline import add_infile_and_outfile, add_volume_arg
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.pipelines.find_git_refs")

__doc__ = """
Given a repo_url, clones the repo, lists git refs for each tag
TODO: every Nth commit, or commit every time interval.
TODO: since and until args
TODO: find branches
"""


@dataclass
class FindGitRefsBuildArgs:
    base_image_name: str = "debian"
    base_image_tag: str = "buster-slim"

    # NB: for buster variants a ripgrep package is available
    _DOCKERFILE = """
FROM {0.base_image}
RUN apt-get -y update && apt-get install -y git
CMD ["bash", "-c"]
"""

    repo_tag = "dep-obs/find-git-refs"

    @property
    def base_image(self) -> str:
        return f"{self.base_image_name}:{self.base_image_tag}"

    @property
    def dockerfile(self) -> bytes:
        return FindGitRefsBuildArgs._DOCKERFILE.format(self).encode("utf-8")


async def build_container(args: FindGitRefsBuildArgs = None) -> str:
    # NB: can shell out to docker build if this doesn't work
    if args is None:
        args = FindGitRefsBuildArgs()

    await containers.build(args.dockerfile, args.repo_tag, pull=True)
    log.info(f"image built and successfully tagged {args.repo_tag}")
    return args.repo_tag


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser = add_volume_arg(parser)
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
        ],
    ) as c:
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
    log.info("pipeline started")
    try:
        await build_container()
    except Exception as e:
        log.error(
            f"error occurred building the find git refs image: {e}\n{exc_to_str()}"
        )

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
