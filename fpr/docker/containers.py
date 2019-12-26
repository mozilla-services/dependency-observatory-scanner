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
    AsyncGenerator,
    BinaryIO,
    IO,
    Sequence,
    List,
    Generator,
    Union,
    Dict,
    Optional,
)
import aiodocker

import fpr.docker.log_reader as docker_log_reader
from fpr.models import GitRef, GitRefKind
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
            "containers/{container._id}/exec".format(container=container),
            method="POST",
            data=kwargs,
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
            "exec/{exec_id}/start".format(exec_id=self.exec_id),
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
            "exec/{exec_id}/resize".format(exec_id=self.exec_id),
            method="POST",
            params=kwargs,
        )

    async def inspect(self: "Exec") -> DockerExecInspectResult:
        data = await self.container.docker._query_json(
            "exec/{exec_id}/json".format(exec_id=self.exec_id), method="GET"
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
    log.info(
        "container {} in {} running {!r}".format(container_log_name, working_dir, cmd)
    )
    exec_ = await self.exec_create(**config)

    with tempfile.NamedTemporaryFile(
        mode="w+",
        encoding="utf-8",
        prefix="fpr_container_{0[Id]}_exec_{1.exec_id}_stdout".format(self, exec_),
        delete=False,
    ) as tmpout:
        exec_.start_result = await exec_.start(Detach=detach, Tty=tty)
        for line in exec_.decoded_start_result_stdout:
            tmpout.write(line + "\n")
        log.info(
            "container {} in {} ran {} saved start result to {}".format(
                container_log_name, working_dir, config, tmpout.name
            )
        )
    if wait:
        await exec_.wait()
    if check:
        last_inspect = await exec_.inspect()
        if last_inspect["ExitCode"] != 0:
            raise DockerRunException(
                "{} command {} failed with non-zero exit code {}".format(
                    self._id, cmd, last_inspect["ExitCode"]
                )
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
) -> AsyncGenerator[aiodocker.docker.DockerContainer, None]:
    client = aiodocker.Docker()
    config = dict(
        Cmd=cmd,
        Image=repository_tag,
        LogConfig={"Type": "json-file"},
        AttachStdout=True,
        AttachStderr=True,
        Tty=True,
    )
    if entrypoint:
        config["Entrypoint"] = entrypoint
    if working_dir:
        config["WorkingDir"] = working_dir
    log.info("starting image {} as {}".format(repository_tag, name))
    log.debug("container {} starting {} with config {}".format(name, cmd, config))
    container = await client.containers.run(config=config, name=name)
    # fetch container info so we can include container name in logs
    await container.show()
    try:
        yield container
    except DockerRunException as e:
        container_log_name = (
            container["Name"] if "Name" in container._container else container["Id"]
        )
        log.error(
            "{} error running docker command {}:\n{}".format(
                container_log_name, cmd, exc_to_str()
            )
        )
    finally:
        await container.stop()
        await container.delete()
        await client.close()


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


@contextlib.contextmanager
async def aiodocker_client():
    client = aiodocker.Docker()
    try:
        yield client
    finally:
        await client.close()


async def build(dockerfile: bytes, tag: str, pull: bool = False) -> str:
    client = aiodocker.Docker()
    log.info("building image {}".format(tag))
    log.debug("building image {} with dockerfile:\n{}".format(tag, dockerfile))
    with temp_dockerfile_tgz(BytesIO(dockerfile)) as tar_obj:
        async for build_log_line in client.images.build(
            fileobj=tar_obj, encoding="utf-8", rm=True, tag=tag, pull=pull, stream=True
        ):
            log.debug("building image {}: {}".format(tag, build_log_line))

    image_info = await client.images.inspect(tag)
    log.info("built docker image: {} {}".format(tag, image_info["Id"]))
    await client.close()
    return tag


async def ensure_repo(
    container: aiodocker.containers.DockerContainer, repo_url: str, working_dir="/"
):
    cmds = [
        "rm -rf repo",
        "git clone --depth=1 {repo_url} repo".format(repo_url=repo_url),
    ]
    for cmd in cmds:
        await container.run(cmd, wait=True, check=True, working_dir=working_dir)


async def fetch_branch(
    container: aiodocker.containers.DockerContainer,
    branch: str,
    remote: str = "origin",
    working_dir: str = "/repo",
):
    cmd = "git fetch {remote} {branch}".format(branch=branch, remote=remote)
    await container.run(cmd, wait=True, check=True, working_dir=working_dir)


async def fetch_commit(
    container: aiodocker.containers.DockerContainer,
    commit: str,
    remote: str = "origin",
    working_dir: str = "/repo",
):
    # per https://stackoverflow.com/a/30701724
    cmd = "git fetch {remote} {commit}".format(commit=commit, remote=remote)
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


async def ensure_ref(container, ref: GitRef, working_dir="/repo"):
    if ref.kind == GitRefKind.TAG:
        await fetch_tag(container, tag_name=ref.value, working_dir=working_dir)
    elif ref.kind == GitRefKind.BRANCH:
        await fetch_branch(container, branch=ref.value, working_dir=working_dir)
    elif ref.kind == GitRefKind.COMMIT:
        await fetch_commit(container, commit=ref.value, working_dir=working_dir)

    await container.run(
        "git checkout {ref}".format(ref=ref.value),
        working_dir=working_dir,
        wait=True,
        check=True,
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
get_cargo_version = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "cargo --version"
)
get_cargo_audit_version = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "cargo audit --version"
)
get_ripgrep_version = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "rg --version"
)
get_rustc_version = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "rustc --version"
)
get_node_version = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "node --version"
)
get_npm_version = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "npm --version"
)
get_yarn_version = functools.partial(
    run_container_cmd_no_args_return_first_line_or_none, "yarn --version"
)


async def cargo_audit(
    container: aiodocker.containers.DockerContainer, working_dir: str = "/repo"
) -> str:
    exec_ = await container.run(
        "cargo audit --json", working_dir=working_dir, check=False, wait=True
    )
    return exec_.decoded_start_result_stdout[0]


async def cargo_metadata(
    container: aiodocker.containers.DockerContainer, working_dir: str = "/repo"
) -> str:
    exec_ = await container.run(
        "cargo metadata --format-version 1 --locked",
        working_dir=working_dir,
        check=True,
    )
    return exec_.decoded_start_result_stdout[0]


async def find_files(
    filename: str,
    container: aiodocker.containers.DockerContainer,
    working_dir: str = "/repo",
) -> str:
    cmd = "rg --no-ignore -g {} --files".format(filename)
    exec_ = await container.run(cmd, working_dir=working_dir, check=True)
    log.info("{} result: {}".format(cmd, exec_.start_result))

    return exec_.decoded_start_result_stdout


async def get_tags(
    container: aiodocker.containers.DockerContainer, working_dir: str = "/repo"
) -> str:
    await fetch_tags(container, working_dir=working_dir)
    # sort tags from oldest to newest
    cmd = "git tag -l --sort=creatordate"
    exec_ = await container.run(cmd, working_dir="/repo", check=True)
    log.info("{} result: {}".format(cmd, exec_.start_result))

    return exec_.decoded_start_result_stdout


find_cargo_tomlfiles = functools.partial(find_files, "Cargo.toml")
find_cargo_tomlfiles.__doc__ = (
    """Finds the relative paths to Cargo.toml files in a repo using ripgrep"""
)

find_cargo_lockfiles = functools.partial(find_files, "Cargo.lock")
find_cargo_lockfiles.__doc__ = """Find the relative paths to Cargo.lock files in a repo in one or
    more ways:

    git clone the repo in a container
    TODO use searchfox.org (mozilla central only)
    TODO using github search
    """


async def find_nodejs_files(
    container: aiodocker.containers.DockerContainer, working_dir: str = "/repo"
) -> AsyncGenerator[str, None]:
    """Finds the relative paths to node.js dep and lock files in a repo
    using ripgrep"""
    for fn in ["package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock"]:
        results = await find_files(fn, container, working_dir)
        for result in results:
            yield result


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
