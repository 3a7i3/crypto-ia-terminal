"""Contrat MC-001 : schéma, diagnostics, fraîcheur et idempotence de lecture."""

from __future__ import annotations

import json
import time

from tools.regret_repository import (
    diagnostics,
    is_fresh,
    last_event_ts,
    read_canonical_observations,
    read_canonical_regrets,
)


def _evidence(obs: str, horizon: str = "1h", status: str = "EVALUATED") -> dict:
    now = time.time()
    result = None
    if status == "EVALUATED":
        result = {
            "horizon": horizon,
            "ts_eval": now,
            "return_pct": 0.05,
            "direction_ok": True,
            "regret_type": "MISSED_WIN",
            "favorable_endpoint_pct": 0.05,
            "adverse_endpoint_pct": 0.0,
            "price_at_signal": 100.0,
            "price_at_eval": 105.0,
            "price_source": "test_snapshot",
            "price_observed_ts": now,
            "price_age_s": 0.0,
            "eval_delay_s": 2.0,
        }
    return {
        "schema_version": 2,
        "dataset_version": "regret-v2",
        "record_type": "HORIZON_EVIDENCE",
        "evidence_id": f"{obs}:{horizon}",
        "observation_id": obs,
        "packet_id": f"pkt-{obs}",
        "trace_id": f"trace-{obs}",
        "ts_signal": now - 3600,
        "ts_eval": now,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "score": 72,
        "regime": "bull",
        "all_blockers": ["gate"],
        "horizon": horizon,
        "horizon_status": status,
        "status_reason": "late" if status == "DROPPED" else None,
        "result": result,
    }


def _write(root, rows) -> None:
    root.mkdir(exist_ok=True)
    path = root / "regret_horizons_2026-09-03.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_canonical_read_preserves_provenance_and_deduplicates(tmp_path):
    row = _evidence("obs-1")
    _write(tmp_path, [row, row])
    records = read_canonical_regrets(regret_dir=tmp_path)
    assert len(records) == 1
    assert records[0]["packet_id"] == "pkt-obs-1"
    assert records[0]["trace_id"] == "trace-obs-1"
    assert records[0]["horizon_status"] == "EVALUATED"
    assert records[0]["favorable_endpoint_pct"] == 0.05


def test_dropped_visible_but_not_a_canonical_label(tmp_path):
    _write(tmp_path, [_evidence("obs-drop", status="DROPPED")])
    assert read_canonical_regrets(regret_dir=tmp_path) == []
    rows = read_canonical_observations(regret_dir=tmp_path)
    assert rows[0]["horizon_status"] == "DROPPED"
    assert rows[0]["regret_type"] is None


def test_diagnostics_exposes_corruption_and_missing_horizon(tmp_path):
    _write(tmp_path, [_evidence("obs-5m", horizon="5m")])
    path = next(tmp_path.glob("*.jsonl"))
    with path.open("a", encoding="utf-8") as stream:
        stream.write("{corrupt\n")
        stream.write(json.dumps({"foreign": True}) + "\n")
    report = diagnostics(regret_dir=tmp_path)
    assert report["invalid_json_lines"] == 1
    assert report["invalid_records"] == 1
    assert report["incomplete_observations"] == 1


def test_diagnostics_rejects_foreign_dataset_version(tmp_path):
    row = _evidence("obs-foreign")
    row["dataset_version"] = "regret-v1"
    _write(tmp_path, [row])
    assert diagnostics(regret_dir=tmp_path)["invalid_records"] == 1
    assert read_canonical_regrets(regret_dir=tmp_path) == []


def test_freshness_uses_event_timestamp_not_file_mtime(tmp_path):
    row = _evidence("obs-old")
    old = time.time() - 48 * 3600
    row["ts_eval"] = old
    row["result"]["ts_eval"] = old
    _write(tmp_path, [row])
    assert last_event_ts(regret_dir=tmp_path) == old
    assert is_fresh(max_stale_h=6, regret_dir=tmp_path) is False
