# -*- coding: utf-8 -*-

import pytest

import context
import fpr.docker_log_reader as m


# tests ported from https://github.com/ahmetb/dlog/blob/master/reader_test.go


def test_too_short_for_prefix():
    with pytest.raises(m.DockerLogReadError):
        m.DockerRawLog.decode_lines(b"123")


def test_corrupt_prefix_in_middle():
    with pytest.raises(m.DockerLogReadError):
        m.DockerRawLog.decode_lines(b"Hi!\x01\x00\x00\x00")


def test_unrecognized_stream_byte():
    with pytest.raises(m.DockerLogReadError):
        m.DockerRawLog.decode_lines(b"\x03\x00\x00\x00\x00\x00\x00\x01")
    with pytest.raises(m.DockerLogReadError):
        m.DockerRawLog.decode_lines(b"\x03\x00\x00\x00\x00\x00\x00\x01\n")


@pytest.mark.xfail
def test_grows_initial_buffer():
    pass


@pytest.mark.xfail
def test_message_limit_at_limit():
    pass


@pytest.mark.xfail
def test_message_limit_exceeds():
    pass


def test_corrupt_message_missing_body():
    # no body
    with pytest.raises(m.DockerLogReadError):
        m.DockerRawLog.decode_lines(b"\x01\x00\x00\x00\x00\x00\x00\x05")


def test_corrupt_message_partial_body():
    # no trailing newline
    with pytest.raises(m.DockerLogReadError):
        m.DockerRawLog.decode_lines(b"\x01\x00\x00\x00\x00\x00\x00\x06hello")
    # trailing newline bad length
    with pytest.raises(m.DockerLogReadError):
        m.DockerRawLog.decode_lines(b"\x01\x00\x00\x00\x00\x00\x00\x07hello\n")


def test_message_read_failure():
    # expected message length 5 from header does not match line length 4
    with pytest.raises(m.DockerLogReadError):
        m.DockerRawLog.decode_lines(b"\x01\x00\x00\x00\x00\x00\x00\x05")


def test_two_small_messages_parsed_correctly():
    decoded = m.DockerRawLog.decode_lines(
        b"\x01\x00\x00\x00\x00\x00\x00\x06hello\n"
        b"\x02\x00\x00\x00\x00\x00\x00\x06world\n"
    )
    assert decoded.stdout == ["hello\n"]
    assert decoded.stderr == ["world\n"]


def test_two_small_messages_to_same_stream_parsed_correctly():
    decoded = m.DockerRawLog.decode_lines(
        b"\x01\x00\x00\x00\x00\x00\x00\x06hello\n"
        b"\x01\x00\x00\x00\x00\x00\x00\x06world\n"
    )
    assert decoded.stdout == ["hello\n", "world\n"]
    assert decoded.stderr == []


def test_decode_lines():
    assert m.DockerRawLog.decode_lines(
        b"\x01\x00\x00\x00\x00\x00\x00\x0bCargo.lock\n"
    ).stdout == ["Cargo.lock\n"]


def test_decode_line_with_newlines():
    assert m.DockerRawLog.decode_lines(
        b"\x01\x00\x00\x00\x00\x00\x00\x0eCargo.lock\nfoo"
    ).stdout == ["Cargo.lock\nfoo"]


def test_iter_messages():
    assert list(
        m.iter_messages(
            b"\x01\x00\x00\x00\x00\x00\x00\x06hello\n"
            b"\x02\x00\x00\x00\x00\x00\x00\x06world\n"
        )
    ) == [(1, b"hello\n"), (2, b"world\n")]
