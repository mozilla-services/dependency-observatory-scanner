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
from typing import BinaryIO, IO, Sequence
import aiodocker
import traceback

import fpr.docker_log_reader as dlog
from fpr.models import GitRef, GitRefKind
from fpr.pipelines.util import exc_to_str

log = logging.getLogger("fpr.containers")


class DockerRunException(Exception):
    pass


class Exec:
    # from: https://github.com/hirokiky/aiodocker/blob/8a91b27cff7311398ca36f5453d94679fed99d11/aiodocker/execute.py

    def __init__(self, exec_id, container):
        self.exec_id = exec_id
        self.container = container
        self.start_result = None
        self.last_inspect = None

    @classmethod
    async def create(cls, container, **kwargs) -> "Exec":
        """ Create and return an instance of Exec
        """
        data = await container.docker._query_json(
            "containers/{container._id}/exec".format(container=container),
            method="POST",
            data=kwargs,
        )
        return cls(data["Id"], container)

    async def start(self, stream=False, timeout=None, receive_timeout=None, **kwargs):
        """
        Start an exec.
        stream
        ======
        If it's False, this method will return result of exec process as binary string.
        If it's True, "WebSocketClientResponse" will be returned.
        You can use it as same as response of "ws_connect" of aiohttp.
        """
        # Don't use docker._query_json
        # content-type of response will be "vnd.docker.raw-stream",
        # so it will cause error.
        response = await self.container.docker._query(
            "exec/{exec_id}/start".format(exec_id=self.exec_id),
            method="POST",
            headers={"content-type": "application/json"},
            data=json.dumps(kwargs),
            # read_until_eof=not stream,
            timeout=timeout,
        )

        if stream:
            conn = response.connection
            transport = conn.transport
            protocol = conn.protocol
            loop = response._loop

            reader = FlowControlDataQueue(protocol, limit=2 ** 16, loop=loop)
            writer = ExecWriter(transport)
            protocol.set_parser(ExecReader(reader), reader)
            return ClientWebSocketResponse(
                reader,
                writer,
                None,  # protocol
                response,
                timeout,
                True,  # autoclose
                False,  # autoping
                loop,
                receive_timeout=receive_timeout,
            )

        else:
            result = await response.read()
            await response.release()
            return result

    async def resize(self, **kwargs):
        await self.container.docker._query(
            "exec/{exec_id}/resize".format(exec_id=self.exec_id),
            method="POST",
            params=kwargs,
        )

    async def inspect(self):
        data = await self.container.docker._query_json(
            "exec/{exec_id}/json".format(exec_id=self.exec_id), method="GET"
        )
        self.last_inspect = data
        return data

    async def wait(self):
        while True:
            resp = await self.inspect()
            log.debug("Exec wait resp:", resp)
            if resp["Running"] is False:
                break
            else:
                await asyncio.sleep(0.1)

    @property
    def decoded_start_result_stdout(self: "Exec") -> [str]:
        return list(
            dlog.iter_lines(
                dlog.iter_messages(self.start_result),
                output_stream=dlog.DockerLogStream.STDOUT,
            )
        )


async def _exec_create(self, **kwargs) -> Exec:
    """ Create an exec (Instance of Exec).
    """
    return await Exec.create(self, **kwargs)


aiodocker.containers.DockerContainer.exec_create = _exec_create


async def _run(
    self,
    cmd,
    attach_stdout=True,
    attach_stderr=True,
    detach=False,
    tty=False,
    working_dir=None,
    # fpr specific args
    wait=True,
    check=True,
    **kwargs
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
        if exec_.last_inspect is None:
            await exec_.inspect()
        if exec_.last_inspect["ExitCode"] != 0:
            raise DockerRunException(
                "{} command {} failed with non-zero exit code {}".format(
                    self._id, cmd, exec_.last_inspect["ExitCode"]
                )
            )
    return exec_


aiodocker.containers.DockerContainer.run = _run


@contextlib.asynccontextmanager
async def run(repository_tag, name, cmd=None, entrypoint=None, working_dir=None):
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
def temp_dockerfile_tgz(fileobject: BinaryIO) -> IO:
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


async def build(dockerfile: str, tag: str, pull: bool = False):
    client = aiodocker.Docker()
    log.info("building image {}".format(tag))
    log.debug("building image {} with dockerfile:\n{}".format(tag, dockerfile))
    with temp_dockerfile_tgz(BytesIO(dockerfile)) as tar_obj:
        async for build_log_line in await client.images.build(
            fileobj=tar_obj, encoding="utf-8", rm=True, tag=tag, pull=pull, stream=True
        ):
            log.debug("building image {}: {}".format(tag, build_log_line))

    image_info = await client.images.inspect(tag)
    log.info("built docker image: {} {}".format(tag, image_info["Id"]))
    await client.close()
    return tag


async def ensure_repo(container, repo_url, working_dir="/"):
    cmds = [
        "rm -rf repo",
        "git clone --depth=1 {repo_url} repo".format(repo_url=repo_url),
    ]
    for cmd in cmds:
        await container.run(cmd, wait=True, check=True, working_dir=working_dir)


async def fetch_branch(
    container, branch: str, remote: str = "origin", working_dir: str = "/repo"
):
    cmd = "git fetch {remote} {branch}".format(branch=branch, remote=remote)
    await container.run(cmd, wait=True, check=True, working_dir=working_dir)


async def fetch_tags(container, working_dir="/repo"):
    await container.run(
        "git fetch --tags origin", working_dir=working_dir, wait=True, check=True
    )


async def ensure_ref(container, ref: GitRef, working_dir="/repo"):
    if ref.kind == GitRefKind.TAG:
        await fetch_tags(container, working_dir=working_dir)
    elif ref.kind == GitRefKind.BRANCH:
        await fetch_branch(container, branch=ref.value, working_dir=working_dir)

    await container.run(
        "git checkout {ref}".format(ref=ref.value),
        working_dir=working_dir,
        wait=True,
        check=True,
    )


async def run_container_cmd_no_args_return_first_line_or_none(
    cmd, container, working_dir="/repo"
):
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


async def cargo_audit(container, working_dir="/repo"):
    exec_ = await container.run(
        "cargo audit --json", working_dir=working_dir, check=False, wait=True
    )
    return exec_.decoded_start_result_stdout[0]


async def cargo_metadata(container, working_dir="/repo"):
    exec_ = await container.run(
        "cargo metadata --format-version 1 --locked",
        working_dir=working_dir,
        check=True,
    )
    return exec_.decoded_start_result_stdout[0]


async def find_files(filename, container, working_dir="/repo"):
    cmd = "rg --no-ignore -g {} --files".format(filename)
    exec_ = await container.run(cmd, working_dir=working_dir, check=True)
    log.info("{} result: {}".format(cmd, exec_.start_result))

    return exec_.decoded_start_result_stdout


async def get_tags(container, working_dir="/repo"):
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


def path_relative_to_working_dir(working_dir: "Path", file_path: "Path") -> "Path":
    return pathlib.Path(working_dir) / pathlib.Path(file_path).parent
