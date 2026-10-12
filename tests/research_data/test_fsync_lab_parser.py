"""Parser fixtures are synthetic, not actual syscall evidence."""

import pytest

from scripts.research.qualify_fsync_lab import parse_trace


def test_success_fd_path_and_errno_distinct():
    rows = parse_trace(
        "1791835200.123 fsync(3</tmp/owned-lab/real.jsonl>) = 0\n"
        "1791835200.124 fsync(-1) = -1 EBADF (Bad file descriptor)\n"
    )
    assert rows[0]["returned"] == 0
    assert rows[0]["path"] == "/tmp/owned-lab/real.jsonl"
    assert rows[1]["errno"] == "EBADF"
    assert rows[1]["fd"] == -1


def test_writer_claim_without_syscall_is_no_evidence():
    assert parse_trace("") == []


@pytest.mark.parametrize(
    "trace",
    [
        "writer says fsync success",
        "1791835200.123 fsync(3) <unfinished ...>",
        "1791835200.123 <... fsync resumed>) = 0",
        "1791835200.123 fsync(-1) = -1",
        "1791835200.123 fsync(3) = 0 EBADF (contradiction)",
        "1791835200.123 fsync(3) = 1",
    ],
)
def test_unsupported_or_contradictory_trace_aborts(trace):
    with pytest.raises(ValueError):
        parse_trace(trace)
