"""Synthetic parser tests, never syscall acquisition proof."""

import json

import pytest

from scripts.research.qualify_fsync_binding_lab import RECORDS, bind_trace

PATH = "/tmp/lab/records.jsonl"


def trace():
    lines = []
    for i, raw in enumerate(RECORDS):
        lines.append(
            f"write(3<{PATH}>, {json.dumps(raw.decode())}, {len(raw)}) = {len(raw)}"
        )
        if i == 1:
            lines.append(f"fsync(3<{PATH}>) = 0")
    lines.append(f"close(3<{PATH}>) = 0")
    return "\n".join(lines)


def test_third_record_not_synced_by_prior_fsync():
    result = bind_trace(trace(), PATH, 3, b"".join(RECORDS))
    assert result["synced_records"] == 2 and result["records_without_fsync_return"] == 1
    assert [r["lab_fsync_return_covers_range"] for r in result["records"]] == [
        True,
        True,
        False,
    ]
    assert result["records"][0]["byte_start"] == 0
    assert result["records"][2]["byte_end"] == sum(map(len, RECORDS))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace("fsync(", "claimed_fsync("),
        lambda t: t.replace("fsync(3<", "fsync(4<"),
        lambda t: t.replace(
            "fsync(3<" + PATH + ">) = 0", "fsync(3<" + PATH + ">) = -1 EIO (error)"
        ),
        lambda t: t.replace("close(3<" + PATH + ">) = 0", ""),
        lambda t: t + "\n" + f'write(3<{PATH}>, "x", 1) = 1',
        lambda t: t.replace("LAB-P1", "WRONG-P1"),
    ],
)
def test_contradictory_or_unsupported_trace_aborts(mutate):
    with pytest.raises(ValueError):
        bind_trace(mutate(trace()), PATH, 3, b"".join(RECORDS))


def test_captured_file_bytes_mismatch_aborts():
    with pytest.raises(ValueError):
        bind_trace(trace(), PATH, 3, b"".join(RECORDS) + b"x")
