import asyncio
import contextlib
import functools
import sys
import os
import logging
import json
import pathlib
from io import BytesIO
import tarfile
import tempfile
from typing import (
    Any,
    AsyncGenerator,
    BinaryIO,
    IO,
    Sequence,
    List,
    Generator,
    Union,
    Dict,
    Optional,
    Tuple,
)
import aiodocker

from fpr.docker.client import aiodocker_client
import fpr.docker.log_reader as docker_log_reader
import fpr.docker.volumes
from fpr.models.git_ref import GitRef, GitRefKind
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.containers")


# https://docs.docker.com/engine/api/v1.37/#operation/ExecInspect
# {
#   "CanRemove": false,
#   "ContainerID": "b53ee82b53a40c7dca428523e34f741f3abc51d9f297a14ff874bf761b995126",
#   "DetachKeys": "",
#   "ExitCode": 2,
#   "ID": "f33bbfb39f5b142420f4759b2348913bd4a8d1a6d7fd56499cb41a1bb91d7b3b",
#   "OpenStderr": true,
#   "OpenStdin": true,
#   "OpenStdout": true,
#   "ProcessConfig": {
#     "arguments": [
#       "-c",
#       "exit 2"
#     ],
#     "entrypoint": "sh",
#     "privileged": false,
#     "tty": true,
#     "user": "1000"
#   },
#   "Running": false,
#   "Pid": 42000
# }
DockerExecInspectResult = Dict[str, Union[int, str, List[str], bool]]


class DockerRunException(Exception):
    pass


class Exec:
    # from: https://github.com/hirokiky/aiodocker/blob/8a91b27cff7311398ca36f5453d94679fed99d11/aiodocker/execute.py

    def __init__(self, exec_id: str, container: aiodocker.docker.DockerContainer):
        self.exec_id: str = exec_id
        self.container: aiodocker.docker.DockerContainer = container
        self.start_result: Optional[bytes] = None

    @classmethod
    async def create(
        cls, container: aiodocker.docker.DockerContainer, **kwargs
    ) -> "Exec":
        """ Create and return an instance of Exec
        """
        data = await container.docker._query_json(
            f"containers/{container._id}/exec", method="POST", data=kwargs
        )
        return cls(data["Id"], container)

    async def start(self: "Exec", timeout: int = None, **kwargs) -> bytes:
        """
        Start executing a process

        returns result of exec process as binary string.
        """
        # Don't use docker._query_json
        # content-type of response will be "vnd.docker.raw-stream",
        # so it will cause error.
        response_cm = self.container.docker._query(
            f"exec/{self.exec_id}/start",
            method="POST",
            headers={"content-type": "application/json"},
            data=json.dumps(kwargs),
            timeout=timeout,
        )
        async with response_cm as response:
            result = await response.read()
            response.release()
            return result

    async def resize(self: "Exec", **kwargs) -> None:
        await self.container.docker._query(
            f"exec/{self.exec_id}/resize", method="POST", params=kwargs
        )

    async def inspect(self: "Exec") -> DockerExecInspectResult:
        data = await self.container.docker._query_json(
            f"exec/{self.exec_id}/json", method="GET"
        )
        return data

    async def wait(self: "Exec") -> None:
        while True:
            resp = await self.inspect()
            log.debug("Exec wait resp:", resp)
            if resp["Running"] is False:
                break
            else:
                await asyncio.sleep(0.1)

    @property
    def decoded_start_result_stdout_and_stderr_line_iters(
        self: "Exec",
    ) -> Tuple[Generator[str, None, None], Generator[str, None, None]]:
        assert self.start_result is not None
        return docker_log_reader.stdout_stderr_line_iters(
            docker_log_reader.iter_messages(self.start_result)
        )

    @property
    def decoded_start_result_stdout(self: "Exec") -> List[str]:
        assert self.start_result is not None
        return list(
            docker_log_reader.iter_lines(
                docker_log_reader.iter_messages(self.start_result),
                output_stream=docker_log_reader.DockerLogStream.STDOUT,
            )
        )


async def _exec_create(self: aiodocker.containers.DockerContainer, **kwargs) -> Exec:
    """ Create an exec (Instance of Exec).
    """
    return await Exec.create(self, **kwargs)


aiodocker.containers.DockerContainer.exec_create = _exec_create


async def _run(
    self: aiodocker.containers.DockerContainer,
    cmd: str,
    attach_stdout: bool = True,
    attach_stderr: bool = True,
    detach: bool = False,
    tty: bool = False,
    working_dir: Optional[str] = None,
    # fpr specific args
    wait: bool = True,
    check: bool = True,
    **kwargs,
) -> Exec:
    """Create and run an instance of exec (Instance of Exec). Optionally wait for it to finish and check its exit code
    """
    config = dict(
        Cmd=cmd.split(" "), AttachStdout=attach_stdout, AttachStderr=attach_stderr
    )
    if working_dir is not None:
        config["WorkingDir"] = working_dir
    container_log_name = self["Name"] if "Name" in self._container else self["Id"]
    log.debug(f"container {container_log_name} in {working_dir} running {cmd!r}")
    exec_ = await self.exec_create(**config)
    exec_.start_result = await exec_.start(Detach=detach, Tty=tty)

    if wait:
        await exec_.wait()
    if check:
        last_inspect = await exec_.inspect()
        if last_inspect["ExitCode"] != 0:
            raise DockerRunException(
                f"{self._id} command {cmd} failed with non-zero exit code {last_inspect['ExitCode']}"
            )
    return exec_


aiodocker.containers.DockerContainer.run = _run


@contextlib.asynccontextmanager
async def run(
    repository_tag: str,
    name: str,
    cmd: str = None,
    entrypoint: Optional[str] = None,
    working_dir: Optional[str] = None,
    volumes: Optional[List[fpr.docker.volumes.DockerVolumeConfig]] = None,
) -> AsyncGenerator[aiodocker.docker.DockerContainer, None]:
    async with aiodocker_client() as client:
        volume_configs: List[
            fpr.docker.volumes.DockerVolumeConfig
        ] = volumes if volumes is not None else []
        async with fpr.docker.volumes.ensure_many(log, client, volume_configs):
            config: Dict[str, Any] = dict(
                Cmd=cmd,
                Image=repository_tag,
                LogConfig={"Type": "json-file"},
                AttachStdout=True,
                AttachStderr=True,
                Tty=True,
                HostConfig={
                    # "ContainerIDFile": "./"
                    "Mounts": []
                },
            )
            if entrypoint:
                config["Entrypoint"] = entrypoint
            if working_dir:
                config["WorkingDir"] = working_dir
            if volumes:
                config["Volumes"] = {cfg.mount_point: dict() for cfg in volume_configs}
                config["HostConfig"]["Mounts"] = [
                    dict(Target=cfg.mount_point, Source=cfg.name, Type="volume")
                    for cfg in volume_configs
                ]
            log.info(f"starting image {repository_tag} as {name}")
            log.debug(f"container {name} starting {cmd} with config {config}")
            container = await client.containers.run(config=config, name=name)
            # fetch container info so we can include container name in logs
            await container.show()
            try:
                yield container
            except DockerRunException as e:
                container_log_name = (
                    container["Name"]
                    if "Name" in container._container
                    else container["Id"]
                )
                log.error(
                    f"{container_log_name} error running docker command {cmd}:\n{exc_to_str()}"
                )
            finally:
                await container.stop()
                await container.delete()


@contextlib.contextmanager
def temp_dockerfile_tgz(fileobject: BinaryIO) -> Generator[IO, None, None]:
    """
    Create a zipped tar archive from a Dockerfile
    **Remember to close the file object**
    Args:
        fileobj: a Dockerfile
    Returns:
        a NamedTemporaryFile() object

    from https://github.com/aio-libs/aiodocker/blob/335acade67eea409bc09a51309123134f3a3c57a/aiodocker/utils.py#L230
    """
    f = tempfile.NamedTemporaryFile()
    t = tarfile.open(mode="w:gz", fileobj=f)

    if isinstance(fileobject, BytesIO):
        dfinfo = tarfile.TarInfo("Dockerfile")
        dfinfo.size = len(fileobject.getvalue())
        fileobject.seek(0)
    else:
        dfinfo = t.gettarinfo(fileobj=fileobject, arcname="Dockerfile")

    t.addfile(dfinfo, fileobject)
    t.close()
    f.seek(0)
    try:
        yield f
    finally:
        f.close()


async def build(dockerfile: bytes, tag: str, pull: bool = False) -> str:
    # NB: can shell out to docker build if this doesn't work
    async with aiodocker_client() as client:
        log.debug(f"building image {tag} with dockerfile:\n{dockerfile}")
        with temp_dockerfile_tgz(BytesIO(dockerfile)) as tar_obj:
            async for build_log_line in client.images.build(
                fileobj=tar_obj,
                encoding="utf-8",
                rm=True,
                tag=tag,
                pull=pull,
                stream=True,
            ):
                log.debug(f"building image {tag}: {build_log_line}")

        image_info = await client.images.inspect(tag)
        log.info(f"built docker image: {tag} {image_info['Id']}")
    return tag


async def ensure_repo(
    container: aiodocker.containers.DockerContainer,
    repo_url: str,
    git_clean=True,
    working_dir="/",
) -> None:
    test_repo_exec: Exec = await container.run(
        f"test -d repo", wait=True, check=False, working_dir=working_dir
    )
    test_repo_exec_inspect_result = await test_repo_exec.inspect()
    log.debug(f"test repo result: {test_repo_exec_inspect_result}")
    if test_repo_exec_inspect_result["ExitCode"] == 0:
        log.debug(
            f"git repo found for: {repo_url} at {working_dir}; checking remote url and cleaning"
        )
        # TODO: for multiple repos make sure the repo remote matches repo_url
        cmds = [("git remote get-url origin", True)]
        if git_clean:
            cmds.append(("git clean -f -d -x -q", True))
        working_dir += "repo"
    else:
        cmds = [
            ("rm -rf repo", False),
            (f"git clone --depth=1 --origin origin {repo_url} repo", True),
        ]
    for cmd, check in cmds:
        await container.run(cmd, wait=True, check=check, working_dir=working_dir)


async def fetch_branch(
    container: aiodocker.containers.DockerContainer,
    branch: str,
    remote: str = "origin",
    working_dir: str = "/repo",
):
    cmd = f"git fetch {remote} {branch}"
    await container.run(cmd, wait=True, check=True, working_dir=working_dir)


async def fetch_commit(
    container: aiodocker.containers.DockerContainer,
    commit: str,
    remote: str = "origin",
    working_dir: str = "/repo",
):
    # per https://stackoverflow.com/a/30701724
    cmd = f"git fetch {remote} {commit}"
    await container.run(cmd, wait=True, check=True, working_dir=working_dir)


async def fetch_tags(
    container: aiodocker.containers.DockerContainer, working_dir="/repo"
):
    await container.run(
        "git fetch --tags origin", working_dir=working_dir, wait=True, check=True
    )


async def fetch_tag(
    container: aiodocker.containers.DockerContainer, tag_name: str, working_dir="/repo"
):
    await container.run(
        f"git fetch origin -f tag {tag_name} --no-tags",
        working_dir=working_dir,
        wait=True,
        check=True,
    )


async def ensure_ref(
    container: aiodocker.containers.DockerContainer, ref: GitRef, working_dir="/repo"
):
    if ref.kind == GitRefKind.TAG:
        await fetch_tag(container, tag_name=ref.value, working_dir=working_dir)
    elif ref.kind == GitRefKind.BRANCH:
        await fetch_branch(container, branch=ref.value, working_dir=working_dir)
    elif ref.kind == GitRefKind.COMMIT:
        await fetch_commit(container, commit=ref.value, working_dir=working_dir)

    await container.run(
        f"git checkout {ref.value}", working_dir=working_dir, wait=True, check=True
    )


async def run_container_cmd_no_args_return_first_line_or_none(
    cmd: str, container: aiodocker.containers.DockerContainer, working_dir="/repo"
) -> Optional[str]:
    exec_ = await container.run(cmd, working_dir=working_dir, detach=False)
    if len(exec_.decoded_start_result_stdout):
        return exec_.decoded_start_result_stdout[0]
    else:
        return None

    return exec_.decoded_start_result_stdout[0]


get_commit = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "git rev-parse HEAD"
)
get_branch = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none,
    "git rev-parse --abbrev-ref HEAD",
)
get_tag = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "git tag -l --points-at HEAD"
)
get_committer_timestamp = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none,
    'git show -s --format="%ct" HEAD',
)
get_ripgrep_version = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "rg --version"
)


async def find_files(
    search_patterns: List[str],
    container: aiodocker.containers.DockerContainer,
    working_dir: str = "/repo",
) -> str:
    cmd = "rg --no-ignore --files"
    for search_pattern in search_patterns:
        cmd += f" --iglob {search_pattern}"
    exec_ = await container.run(cmd, working_dir=working_dir, check=True)
    log.info(f"{cmd} result: {exec_.start_result}")

    return exec_.decoded_start_result_stdout


async def get_tags(
    container: aiodocker.containers.DockerContainer, working_dir: str = "/repos/repo"
) -> AsyncGenerator[Tuple[str, Optional[str], Optional[str]], None]:
    "get a repo tags and when they were tagged as a unix timestamp"
    await fetch_tags(container, working_dir=working_dir)
    # sort tags from newest to oldest tagging time
    # https://git-scm.com/docs/git-for-each-ref/
    cmd = (
        "git for-each-ref --sort=-taggerdate"
        ' --format="%(refname:short)\t%(taggerdate:unix)\t%(creatordate:unix)" refs/tags'
    )
    exec_ = await container.run(cmd, working_dir=working_dir, check=True)
    for line in exec_.decoded_start_result_stdout:
        tag_name, tag_ts, commit_ts = [part.strip('",') for part in line.split("\t", 2)]
        if tag_ts == "":
            tag_ts = None
        if commit_ts == "":
            commit_ts = None
        yield (tag_name, tag_ts, commit_ts)


async def nodejs_metadata(
    container: aiodocker.containers.DockerContainer, working_dir: str = "/repo"
) -> str:
    await container.run("npm install", working_dir=working_dir, check=True)
    exec_ = await container.run(
        "npm ls --json --long", working_dir=working_dir, check=True
    )
    return exec_.decoded_start_result_stdout[0]


async def nodejs_audit(
    container: aiodocker.containers.DockerContainer, working_dir: str = "/repo"
) -> str:
    # npm audit exits with non-zero code when a vuln is found
    exec_ = await container.run(
        "npm audit --json", working_dir=working_dir, check=False
    )
    return exec_.decoded_start_result_stdout[0]


async def sha256sum(
    container: aiodocker.containers.DockerContainer,
    file_path: str,
    working_dir: str = "/repo",
) -> Optional[str]:
    result = await run_container_cmd_no_args_return_first_line_or_none(
        container=container, cmd=f"sha256sum {file_path}", working_dir=working_dir
    )
    # e.g. "553bb7ff086dea3b4eb195c09517fbe7d006422f78d990811bfb5d4eeaec7166  out.json"
    # to "553bb7ff086dea3b4eb195c09517fbe7d006422f78d990811bfb5d4eeaec7166"
    if result and len(result.split(" ", 1)) > 1:
        return result.split(" ", 1)[0]
    return result


def path_relative_to_working_dir(
    working_dir: Union[str, pathlib.Path], file_path: Union[str, pathlib.Path]
) -> pathlib.Path:
    return pathlib.Path(working_dir) / pathlib.Path(file_path).parent
