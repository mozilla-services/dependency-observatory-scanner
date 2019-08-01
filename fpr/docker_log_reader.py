import asyncio
import contextlib
from dataclasses import dataclass
import enum
import sys
import os
import subprocess
import logging
import json
import struct
import time
from io import BytesIO
import tarfile
import tempfile
from typing import BinaryIO, IO, Sequence
import aiodocker
import traceback


log = logging.getLogger("fpr.docker_log_reader")


class DockerLogReadError(Exception):
    """For errors parsing docker output logs
    """

    pass


@enum.unique
class DockerLogStream(enum.Enum):
    STDOUT = 1
    STDERR = 2


def read_message(msg_bytes: BytesIO) -> BytesIO:
    if len(msg_bytes) < 8:
        raise DockerLogReadError(
            "Too few bytes in {!r}. Need at least 8.".format(msg_bytes)
        )

    msg_header, rest = msg_bytes[:8], msg_bytes[8:]
    stream_no, msg_length_from_header = struct.unpack(
        DockerRawLog._LOG_HEADER_FORMAT, msg_header
    )
    if len(rest) < msg_length_from_header:
        raise DockerLogReadError(
            "message header wants {} bytes but message only has {} left".format(
                msg_length_from_header, len(rest)
            )
        )
    return stream_no, rest[:msg_length_from_header], rest[msg_length_from_header:]


def iter_messages(msg_bytes: BytesIO) -> BytesIO:
    msg_bytes_remaining = msg_bytes
    while True:
        stream_no, content, msg_bytes_remaining = read_message(msg_bytes_remaining)
        log.debug(
            "read msg {} {} {}".format(stream_no, content, len(msg_bytes_remaining))
        )
        yield stream_no, content
        if not msg_bytes_remaining:
            break


@dataclass
class DockerRawLog:
    # big endian
    # B: bool of 1 for stdout or 2 for stderr
    # xxx: three padding bytes
    # L: length of the following message
    #
    # see also: https://ahmet.im/blog/docker-logs-api-binary-format-explained/
    _LOG_HEADER_FORMAT = ">BxxxL"

    stdout: Sequence[str]
    stderr: Sequence[str]

    @classmethod
    def decode_lines(cls, lines: BytesIO):
        log.debug("decoding lines {}".format(lines))
        stdout_lines, stderr_lines = [], []

        for stream_no, msg_content in iter_messages(lines):
            if stream_no == DockerLogStream.STDOUT.value:
                stdout_lines.append(msg_content.decode("utf-8"))
            elif stream_no == DockerLogStream.STDERR.value:
                stderr_lines.append(msg_content.decode("utf-8"))
            else:
                raise DockerLogReadError(
                    "Unrecognized raw log stream no {!r}".format(stream_no)
                )

        return cls(stdout=stdout_lines, stderr=stderr_lines)
