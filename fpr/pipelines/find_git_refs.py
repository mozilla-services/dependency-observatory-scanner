import argparse
from dataclasses import dataclass
import functools
import logging
from random import randrange
from typing import Tuple, Dict, Generator, AsyncGenerator

from fpr.rx_util import sleep_by_index, on_next_save_to_jsonl
from fpr.serialize_util import get_in, extract_fields, iter_jsonlines
import fpr.containers as containers
from fpr.models import GitRef, OrgRepo, Pipeline
from fpr.models.pipeline import add_infile_and_outfile
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
        return "{0.base_image_name}:{0.base_image_tag}".format(self)

    @property
    def dockerfile(self) -> bytes:
        return FindGitRefsBuildArgs._DOCKERFILE.format(self).encode("utf-8")


async def build_container(args: FindGitRefsBuildArgs = None) -> str:
    # NB: can shell out to docker build if this doesn't work
    if args is None:
        args = FindGitRefsBuildArgs()

    await containers.build(args.dockerfile, args.repo_tag, pull=True)
    log.info("image built and successfully tagged {}".format(args.repo_tag))
    return args.repo_tag


def parse_args(pipeline_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = add_infile_and_outfile(pipeline_parser)
    parser.add_argument(
        "-t",
        "--tags",
        action="store_true",
        default=False,
        required=False,
        help="Output metadata for each tag in the repo",
    )
    return parser


async def run_find_git_refs(org_repo: OrgRepo):
    # takes a json line with a repo_url
    log.debug("finding git refs for repo {!r}".format(org_repo.github_clone_url))
    name = "dep-obs-find-git-refs-{0.org}-{0.repo}-{1}".format(
        org_repo, hex(randrange(1 << 32))[2:]
    )
    results = []
    async with containers.run(
        "dep-obs/find-git-refs:latest", name=name, cmd="/bin/bash"
    ) as c:
        await containers.ensure_repo(c, org_repo.github_clone_url, working_dir="/")
        tags = await containers.get_tags(c, working_dir="/repo")

        log.debug("{} stdout: {}".format(name, await c.log(stdout=True)))
        log.debug("{} stderr: {}".format(name, await c.log(stderr=True)))
        for tag in tags:
            git_ref = GitRef.from_dict(dict(value=tag, kind="tag"))
            result = dict(
                org=org_repo.org,
                repo=org_repo.repo,
                ref=git_ref.to_dict(),
                repo_url=org_repo.github_clone_url,
            )
            log.debug("{} find git refs result {}".format(name, result))
            results.append(result)
    return results


async def run_pipeline(
    source: Generator[Dict[str, str], None, None], _: argparse.Namespace
) -> AsyncGenerator[OrgRepo, None]:
    log.info("pipeline started")
    try:
        await build_container()
    except Exception as e:
        log.error(
            "error occurred building the find git refs image: {0}\n{1}".format(
                e, exc_to_str()
            )
        )

    for i, item in enumerate(source):
        row = (i, OrgRepo.from_github_repo_url(item["repo_url"]))
        await sleep_by_index(sleep_per_index=3.0, item=row)
        log.debug("processing {!r}".format(row[1]))
        try:
            for ref in await run_find_git_refs(row[1]):
                yield ref
        except Exception as e:
            log.error("error running find_git_refs:\n{}".format(exc_to_str()))


def serialize(_: argparse.Namespace, result: Dict):
    return result


FIELDS = {"repo_url", "ref"}

pipeline = Pipeline(
    name="find_git_refs",
    desc=__doc__,
    fields=FIELDS,
    argparser=parse_args,
    reader=iter_jsonlines,
    runner=run_pipeline,
    serializer=serialize,
    writer=on_next_save_to_jsonl,
)
