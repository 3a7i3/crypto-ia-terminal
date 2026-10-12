"""Synthetic scheduler/worker laboratory only; no deployed producer or witness.

No caller paths: only an owned temporary directory and explicit supplied plans.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import types
from datetime import UTC, datetime, timedelta

WORKER = r"""
import datetime,json,sys
job=json.loads(sys.stdin.read())
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
start=now(); packet=None
if job['fault']=='worker_crash' and job['mode']=='packet':
    sys.exit(3)
try:
    if job['mode']=='raised':
        raise RuntimeError('synthetic failure before packet')
    if job['mode']=='packet':
        packet={**job['identity'],'packet_id':'LAB-PACKET-'+job['identity']['attempt_id']}
        outcome='RETURN_WITH_PACKET'
    else:
        outcome='RETURN_NO_PACKET'
except RuntimeError:
    outcome='RAISED_BEFORE_PACKET'
receipt={**job['identity'],'started_at':start,'ended_at':now(),
    'outcome':outcome,'packet_id':None if packet is None else packet['packet_id']}
print(json.dumps({'receipt':receipt,'packet':packet}))
"""


def _verifier(root: pathlib.Path):
    """Explicit pure source loading in this standalone lab process only."""
    pkg = types.ModuleType("research_data")
    pkg.__path__ = []
    sys.modules["research_data"] = pkg
    pins = {}
    for name in ("stress_d1_evidence_contract", "stress_d1_producer_attempts"):
        path = root / "research_data" / f"{name}.py"
        pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        spec = importlib.util.spec_from_file_location(f"research_data.{name}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return sys.modules["research_data.stress_d1_producer_attempts"], pins


def run_case(fault: str = "none") -> dict:
    if fault not in {"none", "drop_packet", "drop_receipt", "worker_crash"}:
        raise ValueError("Unknown laboratory fault")
    root = pathlib.Path(__file__).resolve().parents[2]
    verifier, pins = _verifier(root)
    start = datetime.now(UTC)
    boundary = {
        "paper_epoch_id": "SYNTHETIC-LAB-NOT-ACTIVE",
        "code_sha": "a" * 40,
        "config_sha256": "b" * 64,
        "dataset_id": "SYNTHETIC-DECLARATION-NOT-CERTIFIED",
        "source_boundary_id": "SYNTHETIC-DECLARATION-NOT-CERTIFIED",
        "window_start": start.isoformat(),
        "window_end": (start + timedelta(seconds=60)).isoformat(),
        "capture_cutoff": (start + timedelta(seconds=120)).isoformat(),
    }
    modes = ("packet", "no_packet", "raised", "not_selected")
    roster = [
        {
            "boundary": boundary,
            "roster_id": f"LAB-R{i}",
            "cycle_id": "LAB-CYCLE",
            "symbol": f"LAB-{i}",
            "selected_for_analysis": mode != "not_selected",
            "selected_at": start.isoformat(),
            "attempt_ids": [] if mode == "not_selected" else [f"LAB-A{i}"],
        }
        for i, mode in enumerate(modes)
    ]
    raw = json.dumps(roster, sort_keys=True, separators=(",", ":")).encode()
    expected_roster_hash = hashlib.sha256(raw).hexdigest()
    receipts, packets, exits = [], [], []
    with tempfile.TemporaryDirectory(prefix="roster-qualification-lab-") as tmp:
        path = pathlib.Path(tmp) / "scheduler_roster.json"
        path.write_bytes(raw)
        # The scheduler artifact exists before every invocation and never derives
        # candidates/plans from the returned worker packets or receipts.
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_roster_hash:
            raise AssertionError("Roster changed before workers")
        for row, mode in zip(roster, modes, strict=True):
            if not row["selected_for_analysis"]:
                continue
            identity = {
                key: row[key] for key in ("boundary", "roster_id", "cycle_id", "symbol")
            }
            identity["attempt_id"] = row["attempt_ids"][0]
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", WORKER],
                input=json.dumps({"identity": identity, "mode": mode, "fault": fault}),
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
            exits.append(result.returncode)
            if result.returncode:
                # No synthetic terminal receipt for a crashed/missing worker.
                continue
            output = json.loads(result.stdout)
            if fault != "drop_receipt" or mode != "packet":
                receipts.append(output["receipt"])
            if output["packet"] is not None and fault != "drop_packet":
                packets.append(output["packet"])
        roster_unchanged = (
            hashlib.sha256(path.read_bytes()).hexdigest() == expected_roster_hash
        )
        if not roster_unchanged:
            raise AssertionError("Roster changed after workers")
    report = verifier.reconcile_producer_attempts(
        roster, receipts, packets, boundary=boundary
    )
    if report["roster_entries"] != 4 or report["planned_attempts"] != 3:
        raise AssertionError("Laboratory plan conservation failed")
    if report["not_selected"] != 1 or report["selected_roster_entries"] != 3:
        raise AssertionError("Laboratory selection conservation failed")
    if sum(report["counts"].values()) != 3:
        raise AssertionError("Attempt conservation failed")
    return {
        "laboratory_case": fault,
        "fixture_population": "SYNTHETIC_ONLY",
        "source_sha256": pins,
        "worker_sha256": hashlib.sha256(WORKER.encode()).hexdigest(),
        "scheduler_roster_sha256": expected_roster_hash,
        "roster_unchanged": roster_unchanged,
        "scheduler_roster_json": raw.decode("utf-8"),
        "captured_receipts": receipts,
        "captured_packets": packets,
        "worker_exits": exits,
        "reconciliation": report,
        "roster_mechanism": "PARENT_PLAN_BEFORE_SEPARATE_WORKER",
        "real_producer_completeness": "NOT_PROVEN",
        "fsync_witness": "NOT_QUALIFIED",
        "future_capture_activation": "DENIED",
        "paper_stress_runtime_go": "DENIED",
    }


def main() -> None:
    for fault in ("none", "drop_packet", "drop_receipt", "worker_crash"):
        print(json.dumps(run_case(fault), sort_keys=True))


if __name__ == "__main__":
    main()
