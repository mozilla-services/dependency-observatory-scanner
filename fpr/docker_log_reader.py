import enum
import logging
import struct
import sys
from io import BytesIO
from typing import BinaryIO, IO, Sequence, Tuple, Generator, Union


log = logging.getLogger("fpr.docker_log_reader")


class DockerLogReadError(Exception):
    """For errors parsing docker output logs
    """

    pass


@enum.unique
class DockerLogStream(enum.Enum):
    STDOUT = 1
    STDERR = 2


DockerLogMessage = bytes


# byte lengths from https://github.com/moby/moby/blob/master/pkg/stdcopy/stdcopy.go
# commit 0f95b23d98384a3ae3769b75292cd5b14ba38437
HEADER_LENGTH = 8
STARTING_BUF_CONTENTS_LEN = 32 * 1024

# big endian
# B: bool of 1 for stdout or 2 for stderr
# xxx: three padding bytes
# L: length of the following message
#
# see also: https://ahmet.im/blog/docker-logs-api-binary-format-explained/
LOG_HEADER_FORMAT = ">BxxxL"


def stream_no_to_DockerLogStream(stream_no: int) -> DockerLogStream:
    if stream_no == DockerLogStream.STDOUT.value:
        return DockerLogStream.STDOUT
    elif stream_no == DockerLogStream.STDERR.value:
        return DockerLogStream.STDERR
    else:
        raise DockerLogReadError(
            "Unrecognized raw log stream no {!r}".format(stream_no)
        )


def read_message(msg_bytes: bytes) -> Tuple[DockerLogStream, bytes, bytes]:
    log.debug("reading {} byte message {}".format(len(msg_bytes), msg_bytes))
    if len(msg_bytes) < HEADER_LENGTH:
        raise DockerLogReadError(
            "Too few bytes in {!r}. Need at least {}.".format(msg_bytes, HEADER_LENGTH)
        )

    msg_header, rest = msg_bytes[:HEADER_LENGTH], msg_bytes[HEADER_LENGTH:]
    stream_no, msg_length_from_header = struct.unpack(LOG_HEADER_FORMAT, msg_header)
    if len(rest) < msg_length_from_header:
        raise DockerLogReadError(
            "message header wants {} bytes but message only has {} left".format(
                msg_length_from_header, len(rest)
            )
        )
    return (
        stream_no_to_DockerLogStream(stream_no),
        rest[:msg_length_from_header],
        rest[msg_length_from_header:],
    )


def iter_messages(
    msg_bytes: bytes,
) -> Generator[Tuple[DockerLogStream, DockerLogMessage], None, None]:
    msg_bytes_remaining = msg_bytes
    log.debug("itering through {} msg bytes".format(len(msg_bytes)))
    while True:
        if not msg_bytes_remaining:
            log.debug("nothing to read from {!r}".format(msg_bytes_remaining))
            break

        stream, content, msg_bytes_remaining = read_message(msg_bytes_remaining)
        log.debug(
            "read msg {} ({} bytes, {} left) {}".format(
                stream, len(content), len(msg_bytes_remaining), content
            )
        )
        yield stream, content
        if not msg_bytes_remaining:
            break


def iter_lines(
    msgs_iter: Union[
        Sequence[Tuple[DockerLogStream, DockerLogMessage]],
        Generator[Tuple[DockerLogStream, DockerLogMessage], None, None],
    ],
    output_stream: DockerLogStream = DockerLogStream.STDOUT,
) -> Generator[str, None, None]:
    buf = bytes()
    for stream, msg in msgs_iter:
        if stream != output_stream:
            log.debug("Skipping {} message {}".format(stream, msg))
            continue

        before = msg
        while True:
            before, newline, after = before.partition(b"\n")
            if newline:
                yield str(buf + before, encoding="utf-8")
                buf = bytes()
                before = after
            else:
                buf += before
                break

    if len(buf):
        yield buf.decode("utf-8")


if __name__ == "__main__":
    msgs_iter = iter_messages(sys.stdin.buffer.read())
    for line in iter_lines(msgs_iter):
        print(line, file=sys.stdout)
