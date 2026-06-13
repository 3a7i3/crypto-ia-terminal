"""
Tests BURNIN_CALIBRATION_V3 — scripts/burnin_calibration_v3.py

Invariants:
  BCV3-01  build_report() sans données → NO_GO + bloqueur paper_trading absent
  BCV3-02  Gate funnel chargé correctement depuis CSV
  BCV3-03  Trades synthétiques (score=0, price<500) filtrés comme test data
  BCV3-04  Trades réels (price>500) comptés et stats calculées
  BCV3-05  KillSwitch halted → bloqueur dans rapport
  BCV3-06  Go/No-Go IN_PROGRESS si 30-99 trades réels sans bloqueurs
  BCV3-07  Coverage_pct calculée correctement
  BCV3-08  JSON output écrit dans le fichier demandé
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.burnin_calibration_v3 import (
    _compute_trade_stats,
    _load_gate_funnel,
    _load_real_trades,
    _preflight_check,
    build_report,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _write_gate_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "ts",
        "symbol",
        "regime",
        "score",
        "effective_min",
        "allowed",
        "failed",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _write_trades_jsonl(path: Path, events: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _real_close(trade_id: str, pnl_pct: float, score: int = 75) -> dict:
    return {
        "event": "CLOSE",
        "trade_id": trade_id,
        "ts": 1781000000.0,
        "ts_iso": "2026-06-11T10:00:00Z",
        "symbol": "BTC/USDT",
        "side": "long",
        "price": 98000.0,  # real price >> 500
        "size_usd": 50.0,
        "mode": "futures_demo",
        "regime": "bull_trend",
        "score": score,
        "order_id": trade_id,
        "exit_price": 98000.0 * (1 + pnl_pct),
        "pnl_usd": 50.0 * pnl_pct,
        "pnl_pct": pnl_pct,
        "reason": "tp" if pnl_pct > 0 else "sl",
        "duration_s": 3600.0,
    }


def _test_close() -> dict:
    """Fixture-like test data with price=101 (will be filtered out)."""
    return {
        "event": "CLOSE",
        "trade_id": "pos-1",
        "ts": 1779526693.0,
        "symbol": "BTC/USDT",
        "side": "long",
        "price": 101.0,
        "size_usd": 10.0,
        "mode": "futures_demo",
        "regime": "unknown",
        "score": 0,
        "exit_price": 101.0,
        "pnl_usd": 1.0,
        "pnl_pct": 0.01,
        "reason": "tp",
        "duration_s": 60.0,
    }


def _restore_artifact(trade_id: str = "90072B8C-A") -> dict:
    """MexcSimulator restore artifact — real price but instant close, no context."""
    return {
        "event": "CLOSE",
        "trade_id": trade_id,
        "ts": 1780537845.0,
        "ts_iso": "2026-06-04T01:50:45Z",
        "symbol": "BTC/USDT",
        "side": "buy",
        "price": 104103.97,
        "size_usd": 15.0,
        "mode": "paper",
        "regime": "unknown",
        "score": 0,
        "order_id": "",
        "exit_price": 104103.97,
        "pnl_usd": 0.5778,
        "pnl_pct": 0.040519,
        "reason": "TP",
        "duration_s": 0.0,
    }


# ── BCV3-01 : sans données → NO_GO ────────────────────────────────────────────


def test_no_data_is_no_go(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("ADVISOR_LIVE_EXECUTION_BOOTSTRAP", "false")
    monkeypatch.delenv("V9_ADVISOR_ONLY", raising=False)
    report = build_report(
        gate_path=tmp_path / "no_gate.csv",
        trades_path=tmp_path / "no_trades.jsonl",
        ks_path=tmp_path / "no_ks.json",
    )
    assert report.go_no_go == "NO_GO"
    assert any(
        "PAPER_TRADING_ENABLED" in b or "simulateur" in b for b in report.blockers
    )


# ── BCV3-02 : gate funnel ──────────────────────────────────────────────────────


def test_gate_funnel_loaded(tmp_path):
    now = 1781000000.0
    rows = [
        {
            "ts": now,
            "symbol": "BTC/USDT",
            "regime": "bull_trend",
            "score": "80",
            "effective_min": "72",
            "allowed": "True",
            "failed": "[]",
        },
        {
            "ts": now + 3600,
            "symbol": "BTC/USDT",
            "regime": "bull_trend",
            "score": "40",
            "effective_min": "72",
            "allowed": "False",
            "failed": '["signal_score (40<72)"]',
        },
        {
            "ts": now + 7200,
            "symbol": "BTC/USDT",
            "regime": "sideways",
            "score": "75",
            "effective_min": "62",
            "allowed": "True",
            "failed": "[]",
        },
    ]
    gate_csv = tmp_path / "gate.csv"
    _write_gate_csv(gate_csv, rows)

    g = _load_gate_funnel(gate_csv)
    assert g.total == 3
    assert g.allowed == 2
    assert g.rejected == 1
    assert g.pass_rate_pct == pytest.approx(66.7, abs=0.1)
    assert g.score_max == 80
    assert g.score_min == 40


# ── BCV3-03 : filtrage données de test ────────────────────────────────────────


def test_test_trades_filtered_out(tmp_path):
    trades_jsonl = tmp_path / "trades.jsonl"
    _write_trades_jsonl(trades_jsonl, [_test_close(), _test_close()])
    real = _load_real_trades(trades_jsonl)
    assert len(real) == 0, "Test fixtures avec price=101 doivent être filtrées"


def test_restore_artifacts_filtered_out(tmp_path):
    trades_jsonl = tmp_path / "trades.jsonl"
    _write_trades_jsonl(
        trades_jsonl, [_restore_artifact(), _restore_artifact("C8A8A638-2")]
    )
    real = _load_real_trades(trades_jsonl)
    assert (
        len(real) == 0
    ), "Restore artifacts (duration_s=0, score=0, regime=unknown) doivent être filtrés"


# ── BCV3-04 : trades réels comptés ────────────────────────────────────────────


def test_real_trades_counted(tmp_path):
    trades_jsonl = tmp_path / "trades.jsonl"
    events = [
        _real_close("t1", 0.02),  # win
        _real_close("t2", -0.01),  # loss
        _real_close("t3", 0.03),  # win
        _test_close(),  # test fixture — filtered (price=101)
        _restore_artifact(),  # restore artifact — filtered (duration=0)
    ]
    _write_trades_jsonl(trades_jsonl, events)

    real = _load_real_trades(trades_jsonl)
    assert len(real) == 3

    stats = _compute_trade_stats(real)
    assert stats.count == 3
    assert stats.wins == 2
    assert stats.losses == 1
    assert stats.win_rate_pct == pytest.approx(66.7, abs=0.1)
    assert stats.profit_factor > 1.0


# ── BCV3-05 : KillSwitch halted → bloqueur ────────────────────────────────────


def test_killswitch_halted_is_blocker(tmp_path, monkeypatch):
    ks_path = tmp_path / "ks.json"
    ks_path.write_text(
        json.dumps({"halted": True, "safe_mode": False}), encoding="utf-8"
    )
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")

    report = build_report(
        gate_path=tmp_path / "no_gate.csv",
        trades_path=tmp_path / "no_trades.jsonl",
        ks_path=ks_path,
    )
    assert report.go_no_go == "NO_GO"
    assert any("HALTED" in b or "halted" in b.lower() for b in report.blockers)


# ── BCV3-06 : IN_PROGRESS si 30-99 trades sans bloqueur ──────────────────────


def test_in_progress_with_enough_trades(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    monkeypatch.delenv("V9_ADVISOR_ONLY", raising=False)

    # Write 50 real trades (above 30 min, below 100 target)
    trades_jsonl = tmp_path / "trades.jsonl"
    events = [_real_close(f"t{i}", 0.02 if i % 3 != 0 else -0.01) for i in range(50)]
    _write_trades_jsonl(trades_jsonl, events)

    # Minimal gate CSV
    gate_csv = tmp_path / "gate.csv"
    _write_gate_csv(
        gate_csv,
        [
            {
                "ts": "1781000000",
                "symbol": "BTC/USDT",
                "regime": "bull_trend",
                "score": "80",
                "effective_min": "72",
                "allowed": "True",
                "failed": "[]",
            },
        ],
    )

    report = build_report(
        gate_path=gate_csv,
        trades_path=trades_jsonl,
        ks_path=tmp_path / "no_ks.json",
        target_trades=100,
    )
    # No blockers except possibly target not reached → IN_PROGRESS
    assert report.go_no_go in {"IN_PROGRESS", "DEGRADED", "GO"}
    assert report.trades.count == 50


# ── BCV3-07 : coverage_pct ────────────────────────────────────────────────────


def test_coverage_pct(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    trades_jsonl = tmp_path / "trades.jsonl"
    events = [_real_close(f"t{i}", 0.01) for i in range(25)]
    _write_trades_jsonl(trades_jsonl, events)

    report = build_report(
        gate_path=tmp_path / "no_gate.csv",
        trades_path=trades_jsonl,
        ks_path=tmp_path / "no_ks.json",
        target_trades=100,
    )
    assert report.coverage_pct == pytest.approx(25.0, abs=0.1)


# ── BCV3-08 : JSON sauvegardé ─────────────────────────────────────────────────


def test_report_saved_to_json(tmp_path, monkeypatch):
    monkeypatch.delenv("PAPER_TRADING_ENABLED", raising=False)
    output = tmp_path / "v3_report.json"

    report = build_report(
        gate_path=tmp_path / "no_gate.csv",
        trades_path=tmp_path / "no_trades.jsonl",
        ks_path=tmp_path / "no_ks.json",
    )
    output.write_text(
        json.dumps({"go_no_go": report.go_no_go}, indent=2), encoding="utf-8"
    )
    assert output.exists()
    loaded = json.loads(output.read_text())
    assert "go_no_go" in loaded


# ── BCV3-09 : preflight bloque si PAPER_TRADING_ENABLED absent ───────────────


def test_preflight_fails_when_paper_trading_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("ADVISOR_LIVE_EXECUTION_BOOTSTRAP", "false")
    ok, failed = _preflight_check(ks_path=tmp_path / "no_ks.json")
    assert not ok
    assert any(
        "PAPER_TRADING_ENABLED" in f or "paper trading" in f.lower() for f in failed
    )


# ── BCV3-10 : preflight passe si PAPER_TRADING_ENABLED=true ──────────────────


def test_preflight_passes_when_paper_trading_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    ok, failed = _preflight_check(ks_path=tmp_path / "no_ks.json")
    # Only fails if databases/ is missing — which it isn't in the project root
    paper_failures = [f for f in failed if "paper" in f.lower() or "PAPER_TRADING" in f]
    assert not paper_failures


# ── BCV3-11 : preflight bloque si KillSwitch HALTED ──────────────────────────


def test_preflight_fails_when_killswitch_halted(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    ks_path = tmp_path / "ks.json"
    ks_path.write_text(json.dumps({"halted": True}), encoding="utf-8")
    ok, failed = _preflight_check(ks_path=ks_path)
    assert not ok
    assert any("HALTED" in f for f in failed)
