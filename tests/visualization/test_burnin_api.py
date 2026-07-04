"""
tests/visualization/test_burnin_api.py — BurnInSnapshot loader.

Couvre l'exposition (aucun calcul métier nouveau) des seuils du statisticien
(CLAUDE.md § Règle du statisticien) à partir de burnin_v3.json et de
RegretEngine.stats(). Aucun accès aux données réelles — fixtures en tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

from visualization.api.burnin_api import (
    CRI_MIN,
    GOOD_REFUSAL_MIN,
    LOSSES_MIN,
    MISSED_WIN_MIN,
    PER_LAYER_MIN,
    PER_REGIME_MIN,
    TRADES_MIN,
    WINS_MIN,
    load_burnin_snapshot,
)


def _write_burnin_v3(path: Path, **overrides) -> None:
    base = {
        "generated_at": "2026-06-25T02:00:59Z",
        "trades": {
            "count": 11,
            "wins": 6,
            "losses": 5,
            "win_rate_pct": 54.5,
            "profit_factor": 46.22,
            "expectancy_pct": 2.1965,
        },
        "go_no_go": "NO_GO",
        "blockers": ["11 trades reels < 30 minimum statistique"],
        "warnings": ["Warmup state FAILED"],
        "coverage_pct": 11.0,
    }
    base.update(overrides)
    path.write_text(json.dumps(base), encoding="utf-8")


def _write_regret_db(path: Path, missed: int, good: int) -> None:
    def _record(regret_type: str, i: int) -> dict:
        return {
            "candidate_id": f"c{i}",
            "ts_signal": 1000.0 + i,
            "ts_evaluated": 2000.0 + i,
            "symbol": "BTC/USDT",
            "signal": "BUY",
            "score": 70,
            "regime": "bull_trend",
            "price_signal": 100.0,
            "price_eval": 103.0,
            "move_pct": 0.03,
            "direction_correct": regret_type == "MISSED_WIN",
            "regret_value": 0.5,
            "regret_type": regret_type,
            "refused_by": ["conviction"],
            "conviction_level": "medium",
            "potential_pnl_pct": 0.03,
        }

    with path.open("w", encoding="utf-8") as f:
        for i in range(missed):
            f.write(json.dumps(_record("MISSED_WIN", i)) + "\n")
        for i in range(good):
            f.write(json.dumps(_record("GOOD_REFUSAL", i + missed)) + "\n")


def test_load_burnin_snapshot_exposes_thresholds_and_counts(tmp_path, monkeypatch):
    monkeypatch.delenv("FEATURE_AUTO_CALIBRATION", raising=False)

    burnin_path = tmp_path / "burnin_v3.json"
    regret_path = tmp_path / "regret_analysis.jsonl"
    _write_burnin_v3(burnin_path)
    _write_regret_db(regret_path, missed=3, good=7)

    snap = load_burnin_snapshot(burnin_path=burnin_path, regret_db_path=regret_path)

    assert snap.trades_count == 11
    assert snap.trades_min == TRADES_MIN == 500
    assert snap.wins == 6
    assert snap.wins_min == WINS_MIN == 150
    assert snap.losses == 5
    assert snap.losses_min == LOSSES_MIN == 150
    assert snap.missed_win_count == 3
    assert snap.missed_win_min == MISSED_WIN_MIN == 100
    assert snap.good_refusal_count == 7
    assert snap.good_refusal_min == GOOD_REFUSAL_MIN == 100
    assert snap.per_regime_min == PER_REGIME_MIN == 50
    assert snap.per_layer_min == PER_LAYER_MIN == 30
    assert snap.cri_min == CRI_MIN == 90
    assert snap.cri is None  # jamais calculé tant que cri_calculator.py n'existe pas
    assert snap.go_no_go == "NO_GO"
    assert snap.blockers == ["11 trades reels < 30 minimum statistique"]
    assert snap.warnings == ["Warmup state FAILED"]
    assert snap.win_rate_pct == 54.5
    assert snap.profit_factor == 46.22


def test_load_burnin_snapshot_clamps_infinite_profit_factor(tmp_path, monkeypatch):
    """profit_factor = gross_profit / gross_loss is +inf with zero losses —
    a real state at N<10 trades. JSON has no Infinity literal; FastAPI's
    response encoder raises ValueError on it if left unclamped."""
    monkeypatch.delenv("FEATURE_AUTO_CALIBRATION", raising=False)
    burnin_path = tmp_path / "burnin_v3.json"
    _write_burnin_v3(
        burnin_path,
        trades={
            "count": 6,
            "wins": 6,
            "losses": 0,
            "win_rate_pct": 100.0,
            "profit_factor": float("inf"),
            "expectancy_pct": 4.05,
        },
    )

    snap = load_burnin_snapshot(
        burnin_path=burnin_path, regret_db_path=tmp_path / "missing.jsonl"
    )

    assert snap.profit_factor == 999.0
    json.dumps(snap.profit_factor)  # doit rester serialisable


def test_load_burnin_snapshot_missing_files_returns_zeros(tmp_path):
    snap = load_burnin_snapshot(
        burnin_path=tmp_path / "missing.json",
        regret_db_path=tmp_path / "missing.jsonl",
    )

    assert snap.trades_count == 0
    assert snap.wins == 0
    assert snap.losses == 0
    assert snap.missed_win_count == 0
    assert snap.good_refusal_count == 0
    assert snap.go_no_go == "UNKNOWN"
    assert snap.blockers == []
    assert snap.warnings == []


def test_calibration_locked_reflects_env_var(tmp_path, monkeypatch):
    burnin_path = tmp_path / "burnin_v3.json"
    _write_burnin_v3(burnin_path)

    monkeypatch.setenv("FEATURE_AUTO_CALIBRATION", "false")
    snap = load_burnin_snapshot(
        burnin_path=burnin_path, regret_db_path=tmp_path / "missing.jsonl"
    )
    assert snap.calibration_locked is True

    monkeypatch.setenv("FEATURE_AUTO_CALIBRATION", "true")
    snap = load_burnin_snapshot(
        burnin_path=burnin_path, regret_db_path=tmp_path / "missing.jsonl"
    )
    assert snap.calibration_locked is False
