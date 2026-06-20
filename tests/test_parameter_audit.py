"""
Tests — config/parameter_audit.py

AUD-01  record_parameter_change → change_id format CFG-YYYYMMDD-NNNN
AUD-02  séquence dans la même journée → NNNN incrémental
AUD-03  entrée JSONL contient tous les champs requis
AUD-04  runtime_config.json mis à jour avec _config_version
AUD-05  current_config_version() retourne CFG-INITIAL si pas d'entrée
AUD-06  current_config_version() retourne le dernier change_id après écriture
AUD-07  record_open() du recorder embarque runtime_config_version
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ── Helpers ───────────────────────────────────────────────────────────────────


def _read_audit(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ── Tests ────────────────────────────────────────────────────────────────────


def test_aud_01_change_id_format(tmp_path):
    from config.parameter_audit import record_parameter_change

    audit = tmp_path / "audit.jsonl"
    cfg = tmp_path / "runtime_config.json"
    change_id = record_parameter_change(
        "SIGNAL_MIN_SCORE", 60, 66, audit_path=audit, runtime_config_path=cfg
    )
    assert re.match(r"CFG-\d{8}-\d{4}", change_id), change_id


def test_aud_02_sequential_ids(tmp_path):
    from config.parameter_audit import record_parameter_change

    audit = tmp_path / "audit.jsonl"
    cfg = tmp_path / "runtime_config.json"
    ids = [
        record_parameter_change(
            "SIGNAL_MIN_SCORE", i, i + 1, audit_path=audit, runtime_config_path=cfg
        )
        for i in range(3)
    ]
    seqs = [int(cid.split("-")[-1]) for cid in ids]
    assert seqs == [1, 2, 3]


def test_aud_03_entry_fields(tmp_path):
    from config.parameter_audit import record_parameter_change

    audit = tmp_path / "audit.jsonl"
    cfg = tmp_path / "runtime_config.json"
    change_id = record_parameter_change(
        parameter="SIGNAL_MIN_SCORE",
        old_value=60,
        new_value=66,
        source="telegram",
        command="/set SIGNAL_MIN_SCORE 66",
        operator="123456789",
        audit_path=audit,
        runtime_config_path=cfg,
    )
    entries = _read_audit(audit)
    assert len(entries) == 1
    e = entries[0]
    assert e["change_id"] == change_id
    assert e["parameter"] == "SIGNAL_MIN_SCORE"
    assert e["old"] == 60
    assert e["new"] == 66
    assert e["source"] == "telegram"
    assert e["operator"] == "123456789"
    assert e["confirmed"] is True
    assert "timestamp" in e


def test_aud_04_runtime_config_updated(tmp_path):
    from config.parameter_audit import record_parameter_change

    audit = tmp_path / "audit.jsonl"
    cfg = tmp_path / "runtime_config.json"
    cfg.write_text(json.dumps({"SIGNAL_MIN_SCORE": 60}), encoding="utf-8")

    change_id = record_parameter_change(
        "SIGNAL_MIN_SCORE", 60, 66, audit_path=audit, runtime_config_path=cfg
    )

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["_config_version"] == change_id
    assert data["SIGNAL_MIN_SCORE"] == 60  # le reste est inchangé


def test_aud_05_current_version_initial(tmp_path):
    from config.parameter_audit import current_config_version

    cfg = tmp_path / "nonexistent.json"
    assert current_config_version(cfg) == "CFG-INITIAL"


def test_aud_06_current_version_after_write(tmp_path):
    from config.parameter_audit import current_config_version, record_parameter_change

    audit = tmp_path / "audit.jsonl"
    cfg = tmp_path / "runtime_config.json"
    change_id = record_parameter_change(
        "SIGNAL_MIN_SCORE", 60, 66, audit_path=audit, runtime_config_path=cfg
    )
    assert current_config_version(cfg) == change_id


def test_aud_07_recorder_embeds_config_version(tmp_path, monkeypatch):
    from config.parameter_audit import record_parameter_change
    from paper_trading.recorder import PaperTradeRecorder

    audit = tmp_path / "audit.jsonl"
    cfg = tmp_path / "runtime_config.json"
    change_id = record_parameter_change(
        "SIGNAL_MIN_SCORE", 60, 66, audit_path=audit, runtime_config_path=cfg
    )

    monkeypatch.setattr("config.parameter_audit._DEFAULT_RUNTIME_CONFIG", cfg)

    recorder = PaperTradeRecorder(log_path=str(tmp_path / "trades.jsonl"))
    recorder.record_open(
        trade_id="t-001",
        symbol="BTC/USDT",
        side="buy",
        price=65000.0,
        size_usd=15.0,
        regime="bull_trend",
        score=75,
    )

    lines = (tmp_path / "trades.jsonl").read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    assert event["runtime_config_version"] == change_id
