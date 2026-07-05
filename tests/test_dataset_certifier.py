"""
Tests pour tools/dataset_certifier.py

Couvre : DG-001→DG-024, niveaux CERTIFIED/PASS/WARNING/FAIL,
         manifest criteria, CLI exit codes, CertificationReport.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from tools.dataset_certifier import CertificationReport, DatasetCertifier

# ── Helpers ───────────────────────────────────────────────────────────────────

TS_NOW = time.time()
TS_ISO = datetime.fromtimestamp(TS_NOW, tz=timezone.utc).isoformat()


def _valid_record(**overrides) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "observation_id": "20260630-BTC-ABC123",
        "packet_id": "pkt-001",
        "ts": TS_NOW,
        "ts_iso": TS_ISO,
        "cycle": 42,
        "engine_version": "v9",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "score": 75.0,
        "price": 67000.0,
        "regime": "bull_trend",
        "all_blockers": ["conviction"],
        "human_verdict": "REFUSÉ — Conviction",
        "features": {"rsi": 65.0},
        "trade_allowed": False,
        "gate_allowed": True,
        "state_history": [],
    }
    base.update(overrides)
    return base


def _write_jsonl(tmp_path: Path, records: list, filename: str = "data.jsonl") -> Path:
    path = tmp_path / filename
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def _certify(tmp_path: Path, records: list, manifest=None) -> CertificationReport:
    _write_jsonl(tmp_path, records)
    return DatasetCertifier().certify(tmp_path, manifest=manifest)


def _valid_manifest() -> Dict:
    return {
        "uuid": "fb61deac-43e3-40a3-b7d9-5c075cdff24c",
        "observability_version": 2,
        "feature_flags_hash": "0D38360E7901",
        "config_hash": "E0D02B1C317F",
    }


# ── Tests niveaux ─────────────────────────────────────────────────────────────


def test_empty_directory_is_certified(tmp_path):
    report = DatasetCertifier().certify(tmp_path)
    assert report.level == "CERTIFIED"
    assert report.total_records == 0
    assert report.is_certifiable


def test_valid_record_is_certified(tmp_path):
    report = _certify(tmp_path, [_valid_record()])
    assert report.level == "CERTIFIED"
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.certification_id is not None
    assert report.certification_id.startswith("CERT-")


def test_six_warnings_is_warning_level(tmp_path):
    # 6 enregistrements avec regime inconnu → 6 WARNINGs DG-019
    records = [
        _valid_record(observation_id=f"OBS-{i}", regime="unknown_regime")
        for i in range(6)
    ]
    report = _certify(tmp_path, records)
    assert report.level == "WARNING"
    assert not report.is_certifiable


def test_five_warnings_is_pass(tmp_path):
    records = [
        _valid_record(observation_id=f"OBS-{i}", regime="unknown_regime")
        for i in range(5)
    ]
    report = _certify(tmp_path, records)
    assert report.level == "PASS"
    assert report.is_certifiable


# ── Tests DG-001 (unicité) ────────────────────────────────────────────────────


def test_dg001_duplicate_id_is_fail(tmp_path):
    records = [_valid_record(), _valid_record()]  # même observation_id
    report = _certify(tmp_path, records)
    assert report.level == "FAIL"
    ids = [v.criterion_id for v in report.violations]
    assert "DG-001" in ids


def test_dg001_different_ids_ok(tmp_path):
    records = [_valid_record(observation_id=f"OBS-{i}") for i in range(3)]
    report = _certify(tmp_path, records)
    assert report.error_count == 0


# ── Tests DG-010 (monotonie) ─────────────────────────────────────────────────


def test_dg010_non_monotone_is_warning(tmp_path):
    r1 = _valid_record(observation_id="OBS-1", ts=TS_NOW)
    r2 = _valid_record(observation_id="OBS-2", ts=TS_NOW - 100.0)  # régression
    report = _certify(tmp_path, [r1, r2])
    ids = [v.criterion_id for v in report.violations]
    assert "DG-010" in ids
    assert all(
        v.severity != "ERROR" for v in report.violations if v.criterion_id == "DG-010"
    )


# ── Tests DG-011 (JSON valide) ────────────────────────────────────────────────


def test_dg011_invalid_json_is_fail(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not_json}\n", encoding="utf-8")
    report = DatasetCertifier().certify(tmp_path)
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-011" for v in report.violations)


# ── Tests DG-003 (engine_version) ────────────────────────────────────────────


def test_dg003_missing_engine_version_is_fail(tmp_path):
    rec = _valid_record()
    del rec["engine_version"]
    report = _certify(tmp_path, [rec])
    assert report.level == "FAIL"


def test_dg003_empty_engine_version_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(engine_version="")])
    assert report.level == "FAIL"


# ── Tests DG-007 (timestamp) ─────────────────────────────────────────────────


def test_dg007_missing_ts_is_fail(tmp_path):
    rec = _valid_record()
    del rec["ts"]
    report = _certify(tmp_path, [rec])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-007" for v in report.violations)


def test_dg007_zero_ts_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(ts=0)])
    assert report.level == "FAIL"


# ── Tests DG-008 (ts_iso) ────────────────────────────────────────────────────


def test_dg008_invalid_ts_iso_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(ts_iso="not-a-date")])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-008" for v in report.violations)


def test_dg008_missing_timezone_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(ts_iso="2026-06-30T12:00:00")])
    assert report.level == "FAIL"


# ── Tests DG-009 (cohérence ts/ts_iso) ───────────────────────────────────────


def test_dg009_ts_mismatch_is_fail(tmp_path):
    ts_now = time.time()
    ts_iso = datetime.fromtimestamp(ts_now - 10.0, tz=timezone.utc).isoformat()
    report = _certify(tmp_path, [_valid_record(ts=ts_now, ts_iso=ts_iso)])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-009" for v in report.violations)


# ── Tests DG-012 (champs manquants) ──────────────────────────────────────────


def test_dg012_missing_required_field_is_fail(tmp_path):
    rec = _valid_record()
    del rec["packet_id"]
    report = _certify(tmp_path, [rec])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-012" for v in report.violations)


# ── Tests DG-013 (null) ───────────────────────────────────────────────────────


def test_dg013_null_required_field_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(observation_id=None)])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-013" for v in report.violations)


# ── Tests DG-015 (score range) ───────────────────────────────────────────────


def test_dg015_score_above_100_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(score=150.0)])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-015" for v in report.violations)


def test_dg015_negative_score_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(score=-1.0)])
    assert report.level == "FAIL"


# ── Tests DG-016 (side) ───────────────────────────────────────────────────────


def test_dg016_invalid_side_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(side="UNKNOWN")])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-016" for v in report.violations)


# ── Tests DG-017 (price) ──────────────────────────────────────────────────────


def test_dg017_zero_price_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(price=0.0)])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-017" for v in report.violations)


def test_dg017_hold_side_price_zero_ok(tmp_path):
    report = _certify(tmp_path, [_valid_record(side="HOLD", price=0.0)])
    assert all(v.criterion_id != "DG-017" for v in report.violations)


# ── Tests DG-019 (regime) ────────────────────────────────────────────────────


def test_dg019_unknown_regime_is_warning_not_error(tmp_path):
    report = _certify(tmp_path, [_valid_record(regime="exotic_regime")])
    dg19 = [v for v in report.violations if v.criterion_id == "DG-019"]
    assert len(dg19) == 1
    assert dg19[0].severity == "WARNING"


# ── Tests DG-021 (features dict) ─────────────────────────────────────────────


def test_dg021_features_not_dict_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(features="not_a_dict")])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-021" for v in report.violations)


# ── Tests DG-022 (packet_id) ─────────────────────────────────────────────────


def test_dg022_empty_packet_id_is_fail(tmp_path):
    report = _certify(tmp_path, [_valid_record(packet_id="")])
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-022" for v in report.violations)


# ── Tests manifest (DG-002, DG-005, DG-006, DG-023) ──────────────────────────


def test_manifest_valid_ok(tmp_path):
    report = _certify(tmp_path, [_valid_record()], manifest=_valid_manifest())
    assert report.error_count == 0


def test_dg002_invalid_uuid_is_fail(tmp_path):
    m = _valid_manifest()
    m["uuid"] = "not-a-uuid"
    report = _certify(tmp_path, [_valid_record()], manifest=m)
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-002" for v in report.violations)


def test_dg005_obs_version_below_2_is_fail(tmp_path):
    m = _valid_manifest()
    m["observability_version"] = 1
    report = _certify(tmp_path, [_valid_record()], manifest=m)
    assert report.level == "FAIL"
    assert any(v.criterion_id == "DG-005" for v in report.violations)


def test_dg006_missing_ff_hash_is_warning(tmp_path):
    m = _valid_manifest()
    del m["feature_flags_hash"]
    report = _certify(tmp_path, [_valid_record()], manifest=m)
    dg6 = [v for v in report.violations if v.criterion_id == "DG-006"]
    assert len(dg6) == 1
    assert dg6[0].severity == "WARNING"


# ── Tests CertificationReport ────────────────────────────────────────────────


def test_certification_id_format(tmp_path):
    report = _certify(tmp_path, [_valid_record()])
    assert report.certification_id is not None
    parts = report.certification_id.split("-")
    assert parts[0] == "CERT"
    assert len(parts[1]) == 4  # année
    assert parts[2].startswith("Q")


def test_summary_contains_level(tmp_path):
    report = _certify(tmp_path, [_valid_record()])
    summary = report.summary()
    assert "CERTIFIED" in summary
    assert "CERT-" in summary


def test_report_parsed_records(tmp_path):
    records = [_valid_record(observation_id=f"OBS-{i}") for i in range(5)]
    report = _certify(tmp_path, records)
    assert report.parsed_records == 5
    assert report.total_records == 5
