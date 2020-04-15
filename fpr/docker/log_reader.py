import enum
import logging
import struct
import sys
import itertools
from io import BytesIO
from typing import (
    BinaryIO,
    Callable,
    Generator,
    IO,
    Iterable,
    Iterator,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

T = TypeVar("T")

log = logging.getLogger("fpr.docker_log_reader")
log.setLevel(logging.WARN)


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
        raise DockerLogReadError(f"Unrecognized raw log stream no {stream_no}")


def read_message(msg_bytes: bytes) -> Tuple[DockerLogStream, bytes, bytes]:
    log.debug(f"reading {len(msg_bytes)} byte message {msg_bytes}")
    if len(msg_bytes) < HEADER_LENGTH:
        raise DockerLogReadError(
            f"Too few bytes in {msg_bytes}. Need at least {HEADER_LENGTH}."
        )

    msg_header, rest = msg_bytes[:HEADER_LENGTH], msg_bytes[HEADER_LENGTH:]
    stream_no, msg_length_from_header = struct.unpack(LOG_HEADER_FORMAT, msg_header)
    if len(rest) < msg_length_from_header:
        raise DockerLogReadError(
            f"message header wants {msg_length_from_header} bytes but message only has {len(rest)} left"
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
    log.debug(f"itering through {len(msg_bytes)} msg bytes")
    while True:
        if not msg_bytes_remaining:
            log.debug(f"nothing to read from {msg_bytes_remaining}")
            break

        stream, content, msg_bytes_remaining = read_message(msg_bytes_remaining)
        log.debug(
            f"read msg {stream} ({len(content)} bytes, {len(msg_bytes_remaining)} left) {content}"
        )
        yield stream, content
        if not msg_bytes_remaining:
            break


def partition(
    pred: Callable[[T], bool], iterable: Iterable[T]
) -> Tuple[Iterator[T], Iterator[T]]:
    """Use a predicate to partition entries into false entries and true entries

    from: https://docs.python.org/3/library/itertools.html#itertools-recipes
    """
    # partition(is_odd, range(10)) --> 0 2 4 6 8   and  1 3 5 7 9
    t1, t2 = itertools.tee(iterable)
    return itertools.filterfalse(pred, t1), filter(pred, t2)


def split_streams(
    msgs_iter: Iterable[Tuple[DockerLogStream, DockerLogMessage]],
) -> Tuple[Iterable[DockerLogMessage], Iterable[DockerLogMessage]]:
    """Splits a docker log messages iterator into respective stdout and
    stderr streams"""
    is_stderr_msg: Callable[
        [Tuple[DockerLogStream, DockerLogMessage]], bool
    ] = lambda tmp: tmp[0] == DockerLogStream.STDERR
    stdout_msgs, stderr_msgs = partition(is_stderr_msg, msgs_iter)
    return (
        (msg_bytes for (_, msg_bytes) in stdout_msgs),
        (msg_bytes for (_, msg_bytes) in stderr_msgs),
    )


def iter_newlines(
    msg_bytes_iter: Iterable[DockerLogMessage],
) -> Generator[str, None, None]:
    """
    Returns content of '\n' delimited lines decoded as utf8 for an iterator over bytes
    """
    buf = bytes()
    for msg_bytes in msg_bytes_iter:
        before = msg_bytes
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


def iter_lines(
    msgs_iter: Iterable[Tuple[DockerLogStream, DockerLogMessage]],
    output_stream: DockerLogStream = DockerLogStream.STDOUT,
) -> Generator[str, None, None]:
    stdout_msgs, stderr_msgs = split_streams(msgs_iter)

    if output_stream == DockerLogStream.STDERR:
        stream_msgs_iter = stderr_msgs
    else:
        stream_msgs_iter = stdout_msgs

    yield from iter_newlines(stream_msgs_iter)


def stdout_stderr_line_iters(
    msgs_iter: Iterable[Tuple[DockerLogStream, DockerLogMessage]]
) -> Tuple[Generator[str, None, None], Generator[str, None, None]]:
    stdout_msgs, stderr_msgs = split_streams(msgs_iter)
    return iter_newlines(stdout_msgs), iter_newlines(stderr_msgs)


if __name__ == "__main__":
    msgs_iter = iter_messages(sys.stdin.buffer.read())
    for line in iter_lines(msgs_iter):
        print(line, file=sys.stdout)
