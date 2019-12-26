# -*- coding: utf-8 -*-

import math
import pathlib

import pytest

import context
import fpr.docker.log_reader as m


@pytest.fixture
def long_cargo_metadata_output():
    tests_dir = pathlib.Path(__file__).parent / ".."
    with (
        tests_dir
        / "fixtures"
        / "mozilla_services_channelserver_79157df7b193857a2e7e3fe8e61e38305e1d47d4_cargo_metadata_output.out"
    ).open("r+b") as fin:
        return fin.read()


@pytest.mark.dlog
def test_too_short_for_prefix():
    with pytest.raises(m.DockerLogReadError):
        next(m.iter_messages(b"123"))


@pytest.mark.dlog
def test_corrupt_prefix_in_middle():
    with pytest.raises(m.DockerLogReadError):
        next(m.iter_messages(b"Hi!\x01\x00\x00\x00"))


@pytest.mark.dlog
def test_unrecognized_stream_byte():
    with pytest.raises(m.DockerLogReadError):
        next(m.iter_messages(b"\x03\x00\x00\x00\x00\x00\x00\x01"))
    with pytest.raises(m.DockerLogReadError):
        next(m.iter_messages(b"\x03\x00\x00\x00\x00\x00\x00\x01\n"))


@pytest.mark.dlog
@pytest.mark.xfail
def test_grows_initial_buffer():
    pass


@pytest.mark.dlog
@pytest.mark.xfail
def test_message_limit_at_limit():
    pass


@pytest.mark.dlog
@pytest.mark.xfail
def test_message_limit_exceeds():
    pass


@pytest.mark.dlog
def test_corrupt_message_missing_body():
    # no body
    with pytest.raises(m.DockerLogReadError):
        next(m.iter_messages(b"\x01\x00\x00\x00\x00\x00\x00\x05"))


@pytest.mark.dlog
def test_corrupt_message_partial_body():
    # no trailing newline
    with pytest.raises(m.DockerLogReadError):
        next(m.iter_messages(b"\x01\x00\x00\x00\x00\x00\x00\x06hello"))
    # trailing newline bad length
    with pytest.raises(m.DockerLogReadError):
        next(m.iter_messages(b"\x01\x00\x00\x00\x00\x00\x00\x07hello\n"))


@pytest.mark.dlog
def test_message_read_failure():
    # expected message length 5 from header does not match line length 4
    with pytest.raises(m.DockerLogReadError):
        next(m.iter_messages(b"\x01\x00\x00\x00\x00\x00\x00\x05"))


def test_empty_message_skipped():
    assert tuple(m.iter_messages(b"")) == ()


@pytest.mark.dlog
def test_two_small_messages_parsed_correctly():
    assert tuple(
        m.iter_messages(
            b"\x01\x00\x00\x00\x00\x00\x00\x06hello\n"
            b"\x02\x00\x00\x00\x00\x00\x00\x06world\n"
        )
    ) == (
        (m.DockerLogStream.STDOUT, b"hello\n"),
        (m.DockerLogStream.STDERR, b"world\n"),
    )


@pytest.mark.dlog
def test_two_small_messages_to_same_stream_parsed_correctly():
    assert tuple(
        m.iter_messages(
            b"\x01\x00\x00\x00\x00\x00\x00\x06hello\n"
            b"\x01\x00\x00\x00\x00\x00\x00\x06world\n"
        )
    ) == (
        (m.DockerLogStream.STDOUT, b"hello\n"),
        (m.DockerLogStream.STDOUT, b"world\n"),
    )


def test_two_small_messages_different_streams_parsed_correctly():
    assert tuple(
        m.iter_messages(
            b"\x01\x00\x00\x00\x00\x00\x00\x06hello\n"
            b"\x02\x00\x00\x00\x00\x00\x00\x06world\n"
        )
    ) == (
        (m.DockerLogStream.STDOUT, b"hello\n"),
        (m.DockerLogStream.STDERR, b"world\n"),
    )


def test_small_message():
    assert next(m.iter_messages(b"\x01\x00\x00\x00\x00\x00\x00\x0bCargo.lock\n")) == (
        m.DockerLogStream.STDOUT,
        b"Cargo.lock\n",
    )


def test_message_containing_newline():
    assert next(
        m.iter_messages(b"\x01\x00\x00\x00\x00\x00\x00\x0eCargo.lock\nfoo")
    ) == (m.DockerLogStream.STDOUT, b"Cargo.lock\nfoo")


def test_messages_handles_one_long_line_over_many_messages(long_cargo_metadata_output):
    assert len(tuple(m.iter_messages(long_cargo_metadata_output))) == math.ceil(
        len(long_cargo_metadata_output) / m.STARTING_BUF_CONTENTS_LEN
    )


def test_messages_combined_to_one_line(long_cargo_metadata_output):
    assert len(tuple(m.iter_lines(m.iter_messages(long_cargo_metadata_output)))) == 1


def test_messages_final_line_returned_even_without_final_newline():
    msgs = (msg for msg in [(m.DockerLogStream.STDOUT, b"Cargo.lock")])
    assert len(tuple(m.iter_lines(msgs))) == 1


def test_messages_line_containing_newline():
    msgs = (
        msg for msg in [(m.DockerLogStream.STDOUT, b"Cargo.lock\nfoo/Cargo.lock\n")]
    )
    assert tuple(m.iter_lines(msgs)) == ("Cargo.lock", "foo/Cargo.lock")
    msgs = (msg for msg in [(m.DockerLogStream.STDOUT, b"Cargo.lock\nfoo/Cargo.lock")])
    assert tuple(m.iter_lines(msgs)) == ("Cargo.lock", "foo/Cargo.lock")
    msgs = (msg for msg in [(m.DockerLogStream.STDOUT, b"\nCargo.lock\nfoo")])
    assert tuple(m.iter_lines(msgs)) == ("", "Cargo.lock", "foo")
    msgs = (msg for msg in [(m.DockerLogStream.STDOUT, b"\nCargo.lock\n")])
    assert tuple(m.iter_lines(msgs)) == ("", "Cargo.lock")


def test_messages_defaults_to_returning_stdout():
    msgs = (
        msg
        for msg in [
            (m.DockerLogStream.STDOUT, b"Cargo.lock\n"),
            (m.DockerLogStream.STDERR, b"Error!\n"),
        ]
    )
    assert len(tuple(m.iter_lines(msgs))) == 1
