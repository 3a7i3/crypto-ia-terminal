"""Contrat MC-001 : schéma, diagnostics, fraîcheur et idempotence de lecture."""

from __future__ import annotations

import json
import time

from tools.regret_repository import (
    diagnostics,
    is_fresh,
    last_canonical_evaluated_ts,
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
    # Le fichier vient d'être écrit (mtime frais) mais le ts_eval scientifique
    # est vieux de 48h : la fraîcheur ne doit dépendre que du second.
    assert last_event_ts(regret_dir=tmp_path) == old
    assert is_fresh(max_stale_h=6, regret_dir=tmp_path) is False


def test_stale_canonical_with_fresh_noncanonical_horizon_is_not_fresh(tmp_path):
    """Un 5m frais ne doit jamais faire passer la fraîcheur canonique (1h) à vrai."""
    now = time.time()
    old = now - 48 * 3600
    stale_1h = _evidence("obs-1", horizon="1h")
    stale_1h["ts_eval"] = old
    stale_1h["result"]["ts_eval"] = old
    fresh_5m = _evidence("obs-2", horizon="5m")
    _write(tmp_path, [stale_1h, fresh_5m])

    assert last_canonical_evaluated_ts(regret_dir=tmp_path) == old
    assert is_fresh(max_stale_h=6, regret_dir=tmp_path) is False
    # Vivacité producteur (toutes horizons/statuts) reste vraie : le
    # scheduler écrit toujours, seule l'évidence canonique est périmée.
    assert abs(last_event_ts(regret_dir=tmp_path) - now) < 5.0


def test_stale_canonical_with_fresh_canonical_dropped_is_not_fresh(tmp_path):
    """Un DROPPED récent sur l'horizon canonique n'est pas une preuve exploitable."""
    now = time.time()
    old = now - 48 * 3600
    stale_1h = _evidence("obs-1", horizon="1h")
    stale_1h["ts_eval"] = old
    stale_1h["result"]["ts_eval"] = old
    fresh_dropped_1h = _evidence("obs-2", horizon="1h", status="DROPPED")
    _write(tmp_path, [stale_1h, fresh_dropped_1h])

    assert last_canonical_evaluated_ts(regret_dir=tmp_path) == old
    assert is_fresh(max_stale_h=6, regret_dir=tmp_path) is False
    assert abs(last_event_ts(regret_dir=tmp_path) - now) < 5.0


def test_fresh_canonical_evaluated_is_fresh(tmp_path):
    fresh_1h = _evidence("obs-1", horizon="1h")
    _write(tmp_path, [fresh_1h])
    assert is_fresh(max_stale_h=6, regret_dir=tmp_path) is True
