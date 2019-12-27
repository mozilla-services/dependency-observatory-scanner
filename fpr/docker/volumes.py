from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import logging
from typing import AsyncContextManager, AsyncGenerator, Dict, List, Optional, Union

import aiodocker

from fpr.docker.client import aiodocker_client

# https://docs.docker.com/engine/api/v1.32/#operation/VolumeList
DockerVolumeResponseJSON = Dict[str, Union[str, Dict[str, str]]]


@dataclass
class DockerVolumeConfig:
    name: str
    mount_point: str
    labels: Dict[str, str] = field(default_factory=dict)
    driver: str = "local"
    delete: bool = True


async def list_volumes(
    client: aiodocker.docker.Docker, filters: Optional[Dict[str, str]] = None
) -> Dict[str, Union[List[str], List[DockerVolumeResponseJSON]]]:
    return await client.volumes.list()


async def create(
    client: aiodocker.docker.Docker,
    name: str,
    labels: Optional[Dict[str, str]] = None,
    driver: str = "local",
) -> aiodocker.volumes.DockerVolume:
    return await client.volumes.create(
        {"Name": name, "Labels": labels, "Driver": driver}
    )


async def delete(
    client: aiodocker.docker.Docker, volume: aiodocker.volumes.DockerVolume
) -> None:
    async with client._query(
        "volumes/{self.name}".format(self=volume), method="DELETE"
    ):
        pass


@asynccontextmanager
async def ensure(
    log: logging.Logger, client: aiodocker.docker.Docker, config: DockerVolumeConfig
) -> AsyncGenerator[aiodocker.volumes.DockerVolume, None]:
    "Creates or returns an existing volume"
    volume: aiodocker.volumes.DockerVolume
    volume = aiodocker.volumes.DockerVolume(docker=client, name=config.name)
    try:
        volume_details = await volume.show()
        log.debug(f"found volume {config.name}")
    except aiodocker.exceptions.DockerError as e:
        log.debug(f"error finding docker volume {config.name}: {e}")
        if e.status == 404:
            volume = await create(
                client, name=config.name, labels=config.labels, driver=config.driver
            )
            log.debug(f"create volume {config.name} response: {volume}")
            log.info(f"created volume {config.name}")

    try:
        yield volume
    finally:
        if config.delete:
            await delete(client, volume)
            log.info(f"deleted volume {config.name}")
        else:
            log.info(f"did not delete volume {config.name}")


@asynccontextmanager
async def ensure_many(
    log: logging.Logger,
    client: aiodocker.docker.Docker,
    configs: List[DockerVolumeConfig],
) -> AsyncGenerator[aiodocker.volumes.DockerVolume, None]:
    volume_handles: Dict[str, AsyncContextManager[aiodocker.volumes.DockerVolume]] = {}
    for config in configs:
        volume_handles[config.name] = ensure(log, client, config)
        await volume_handles[config.name].__aenter__()
    try:
        yield
    finally:
        for vh in volume_handles.values():
            await vh.__aexit__(None, None, None)
