"""
tests/visualization/test_regret_api.py — RegretInvestigationSnapshot loader.

Sprint A.5 — répond à "de quoi se compose un regret ?" (couche bloqueuse,
régime, score, semaine) sans toucher au pipeline de décision. Aucun accès
aux données réelles — fixtures synthétiques en tmp_path.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from visualization.api.regret_api import load_regret_investigation


def _record(
    regret_type: str,
    regime: str,
    score: float,
    refused_by: list[str],
    ts_evaluated: float,
) -> dict:
    return {
        "candidate_id": f"c-{ts_evaluated}",
        "ts_signal": ts_evaluated - 3600,
        "ts_evaluated": ts_evaluated,
        "symbol": "BTC/USDT",
        "signal": "BUY",
        "score": score,
        "regime": regime,
        "price_signal": 100.0,
        "price_eval": 103.0,
        "move_pct": 0.03,
        "direction_correct": regret_type == "MISSED_WIN",
        "regret_value": 0.5,
        "regret_type": regret_type,
        "refused_by": refused_by,
        "conviction_level": "medium",
        "potential_pnl_pct": 0.03,
    }


def _write_db(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_load_regret_investigation_breaks_down_by_layer_regime_score_week(tmp_path):
    ts_w1 = datetime(2026, 5, 25, tzinfo=timezone.utc).timestamp()
    ts_w2 = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()

    records = [
        _record("MISSED_WIN", "sideways", 72, ["gate"], ts_w1),
        _record("MISSED_WIN", "sideways", 75, ["gate"], ts_w1),
        _record("MISSED_WIN", "sideways", 65, ["gate", "portfolio_brain"], ts_w2),
        _record("MISSED_WIN", "bull_trend", 82, ["meta_strategy"], ts_w2),
        _record("GOOD_REFUSAL", "sideways", 55, ["gate"], ts_w2),
        _record("NEUTRAL", "sideways", 60, ["gate"], ts_w2),
    ]
    db_path = tmp_path / "regret.jsonl"
    _write_db(db_path, records)

    snap = load_regret_investigation(regret_db_path=db_path, regret_type="MISSED_WIN")

    assert snap.regret_type == "MISSED_WIN"
    assert snap.n_total == 4
    assert snap.by_layer == {"gate": 3, "portfolio_brain": 1, "meta_strategy": 1}
    assert snap.by_regime == {"sideways": 3, "bull_trend": 1}
    assert snap.by_score_bin == {"70-79": 2, "60-69": 1, "80+": 1}
    assert sum(snap.by_week.values()) == 4
    assert len(snap.by_week) == 2  # deux semaines ISO distinctes
    assert snap.first_evaluated_at is not None
    assert snap.last_evaluated_at is not None
    assert snap.first_evaluated_at <= snap.last_evaluated_at


def test_load_regret_investigation_filters_by_type(tmp_path):
    ts = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
    records = [
        _record("MISSED_WIN", "sideways", 72, ["gate"], ts),
        _record("GOOD_REFUSAL", "sideways", 55, ["gate"], ts),
    ]
    db_path = tmp_path / "regret.jsonl"
    _write_db(db_path, records)

    snap = load_regret_investigation(regret_db_path=db_path, regret_type="GOOD_REFUSAL")
    assert snap.n_total == 1
    assert snap.by_regime == {"sideways": 1}


def test_load_regret_investigation_missing_file_returns_empty(tmp_path):
    snap = load_regret_investigation(regret_db_path=tmp_path / "missing.jsonl")
    assert snap.n_total == 0
    assert snap.by_layer == {}
    assert snap.by_regime == {}
    assert snap.by_score_bin == {}
    assert snap.by_week == {}
    assert snap.first_evaluated_at is None
    assert snap.last_evaluated_at is None
