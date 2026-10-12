"""Falsifiable synthetic roster acquisition; no real producer certification."""

import hashlib
import json
import pathlib
import subprocess
import sys


def test_parent_roster_precedes_worker_and_missing_outputs_remain_unknown():
    root = pathlib.Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(root / "scripts/research/qualify_future_roster_lab.py"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    reports = {
        r["laboratory_case"]: r for r in map(json.loads, result.stdout.splitlines())
    }
    assert set(reports) == {"none", "drop_packet", "drop_receipt", "worker_crash"}
    for r in reports.values():
        assert r["roster_unchanged"]
        assert (
            hashlib.sha256(r["scheduler_roster_json"].encode()).hexdigest()
            == r["scheduler_roster_sha256"]
        )
        assert len(json.loads(r["scheduler_roster_json"])) == 4
        assert r["fixture_population"] == "SYNTHETIC_ONLY"
        assert r["fsync_witness"] == "NOT_QUALIFIED"
        assert r["real_producer_completeness"] == "NOT_PROVEN"
        assert (
            r["future_capture_activation"] == r["paper_stress_runtime_go"] == "DENIED"
        )
        d = r["reconciliation"]
        assert d["roster_entries"] == 4 and d["planned_attempts"] == 3
        assert d["not_selected"] == 1
        assert sum(d["counts"].values()) == 3
    normal = reports["none"]["reconciliation"]["counts"]
    assert normal["PACKET_CAPTURED"] == 1
    assert normal["PROVEN_RETURN_NO_PACKET"] == 1
    assert normal["PROVEN_EXCEPTION_BEFORE_PACKET"] == 1
    assert (
        reports["drop_packet"]["reconciliation"]["counts"][
            "RETURNED_PACKET_NOT_CAPTURED"
        ]
        == 1
    )
    assert (
        reports["drop_receipt"]["reconciliation"]["counts"][
            "MISSING_INVOCATION_RECEIPT"
        ]
        == 1
    )
    assert (
        reports["drop_receipt"]["reconciliation"][
            "packet_without_unambiguous_return_receipt"
        ]
        == 1
    )
    crashed = reports["worker_crash"]
    assert crashed["worker_exits"] == [3, 0, 0]
    assert crashed["reconciliation"]["counts"]["MISSING_INVOCATION_RECEIPT"] == 1
    assert crashed["reconciliation"]["counts"]["PROVEN_RETURN_NO_PACKET"] == 1
