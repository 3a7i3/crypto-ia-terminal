"""Transcript fixtures qualify parser refusals, never native fault acquisition."""

import json

import pytest

from scripts.research.qualify_fsync_binding_lab import RECORDS
from scripts.research.qualify_fsync_fault_lab import evaluate_case

PATH = "/tmp/fault/records.jsonl"


def transcript():
    rows = []
    for i, raw in enumerate(RECORDS):
        rows.append(
            f"write(3<{PATH}>, {json.dumps(raw.decode())}, {len(raw)}) = {len(raw)}"
        )
        if i == 1:
            rows.append(f"fsync(3<{PATH}>) = 0")
    rows.append(f"close(3<{PATH}>) = 0")
    return "\n".join(rows)


def test_normal_control_is_required():
    assert evaluate_case("normal", transcript(), PATH, 3, b"".join(RECORDS))[
        "expectation_met"
    ]
    assert not evaluate_case("rotation", transcript(), PATH, 3, b"".join(RECORDS))[
        "expectation_met"
    ]


@pytest.mark.parametrize(
    "operation",
    [
        f"lseek(3<{PATH}>, 0, SEEK_SET) = 0",
        f"ftruncate(3<{PATH}>, 0) = 0",
        f"dup(3<{PATH}>) = 4<{PATH}>",
        f"fsync(3<{PATH}>) = 0",
    ],
)
def test_out_of_contract_operations_refused(operation):
    text = transcript().replace(
        f"close(3<{PATH}>) = 0", operation + f"\nclose(3<{PATH}>) = 0"
    )
    result = evaluate_case("second_fsync", text, PATH, 3, b"".join(RECORDS))
    assert result["actual"] == "REFUSE" and result["expectation_met"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace(f"fsync(3<{PATH}>) = 0", ""),
        lambda t: t.replace("LAB-D1", "OTHER1"),
        lambda t: t.replace(
            f"fsync(3<{PATH}>) = 0",
            f"fsync(3<{PATH}>) = 0\nclose(3<{PATH}>) = 0",
        ),
        lambda t: t.replace(
            json.dumps(RECORDS[0].decode()),
            json.dumps(RECORDS[0][:60].decode()),
        ).replace(
            ", 120) = 120",
            ", 60) = 60",
            1,
        ),
    ],
)
def test_missing_corrupted_rotated_and_fragmented_transcripts_refused(mutate):
    assert evaluate_case(
        "partial_record", mutate(transcript()), PATH, 3, b"".join(RECORDS)
    )["expectation_met"]


def test_unknown_case_is_not_implicitly_negative():
    with pytest.raises(ValueError, match="UNKNOWN_LAB_MODE"):
        evaluate_case("unknown", transcript(), PATH, 3, b"".join(RECORDS))
