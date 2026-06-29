"""
tests/scripts/test_analysis_base.py — Tests de régression pour analysis/base.py.

Couvre toutes les fonctions statistiques + load_trades.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.base import (
    Trade,
    expectancy,
    full_metrics,
    kelly_fraction,
    load_trades,
    mar_ratio,
    max_drawdown,
    profit_factor,
    recovery_factor,
    sharpe,
    sortino,
    ulcer_index,
    win_rate,
)

# ── profit_factor ─────────────────────────────────────────────────────────────


def test_pf_normal() -> None:
    assert profit_factor([10.0, -5.0]) == pytest.approx(2.0)


def test_pf_no_losses() -> None:
    assert profit_factor([5.0, 3.0]) == float("inf")


def test_pf_all_losses() -> None:
    assert profit_factor([-5.0, -3.0]) == 0.0


def test_pf_empty() -> None:
    assert profit_factor([]) is None


# ── win_rate ──────────────────────────────────────────────────────────────────


def test_wr_half() -> None:
    assert win_rate([1.0, -1.0]) == pytest.approx(0.5)


def test_wr_all_wins() -> None:
    assert win_rate([1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_wr_empty() -> None:
    assert win_rate([]) is None


# ── expectancy ────────────────────────────────────────────────────────────────


def test_expectancy_positive() -> None:
    assert expectancy([10.0, -5.0]) == pytest.approx(2.5)


def test_expectancy_negative() -> None:
    assert expectancy([-10.0, -5.0]) == pytest.approx(-7.5)


def test_expectancy_empty() -> None:
    assert expectancy([]) is None


# ── sharpe ────────────────────────────────────────────────────────────────────


def test_sharpe_requires_min_2() -> None:
    assert sharpe([1.0]) is None


def test_sharpe_zero_std() -> None:
    assert sharpe([5.0, 5.0, 5.0]) is None


def test_sharpe_positive() -> None:
    result = sharpe([10.0, 20.0, 15.0, 5.0])
    assert result is not None and result > 0


# ── sortino ───────────────────────────────────────────────────────────────────


def test_sortino_no_downside() -> None:
    assert sortino([5.0, 3.0, 1.0]) == float("inf")


def test_sortino_with_losses() -> None:
    result = sortino([10.0, -5.0, 8.0, -2.0])
    assert result is not None


# ── max_drawdown ──────────────────────────────────────────────────────────────


def test_max_drawdown_flat() -> None:
    assert max_drawdown([1.0, 1.0, 1.0]) == 0.0


def test_max_drawdown_sequence() -> None:
    # +10, -5, +2 → peak=10, low=5, dd=5
    assert max_drawdown([10.0, -5.0, 2.0]) == pytest.approx(5.0)


def test_max_drawdown_all_positive() -> None:
    assert max_drawdown([1.0, 2.0, 3.0]) == 0.0


# ── ulcer_index ───────────────────────────────────────────────────────────────


def test_ulcer_requires_min_2() -> None:
    assert ulcer_index([1.0]) is None


def test_ulcer_no_drawdown() -> None:
    result = ulcer_index([1.0, 2.0, 3.0])
    assert result == pytest.approx(0.0)


# ── recovery_factor ───────────────────────────────────────────────────────────


def test_recovery_no_drawdown() -> None:
    result = recovery_factor([5.0, 3.0, 2.0])
    assert result == float("inf")


def test_recovery_with_drawdown() -> None:
    result = recovery_factor([10.0, -5.0, 8.0])
    assert result is not None and result > 0


# ── kelly_fraction ────────────────────────────────────────────────────────────


def test_kelly_requires_min_10() -> None:
    assert kelly_fraction([1.0, -1.0]) is None


def test_kelly_all_wins() -> None:
    result = kelly_fraction([1.0] * 15)
    assert result == pytest.approx(1.0)


def test_kelly_positive() -> None:
    pnls = [5.0, -2.0] * 10  # 50% WR, ratio 2.5
    result = kelly_fraction(pnls)
    assert result is not None and result >= 0


# ── mar_ratio ─────────────────────────────────────────────────────────────────


def test_mar_negative_net() -> None:
    assert mar_ratio([-5.0, -3.0]) is None


def test_mar_no_drawdown() -> None:
    assert mar_ratio([5.0, 3.0]) is None


# ── full_metrics ──────────────────────────────────────────────────────────────


def test_full_metrics_keys() -> None:
    m = full_metrics([10.0, -5.0, 8.0])
    expected_keys = {
        "n",
        "total_pnl_usd",
        "profit_factor",
        "win_rate",
        "expectancy_usd",
        "sharpe",
        "sortino",
        "max_drawdown_usd",
        "ulcer_index",
        "recovery_factor",
        "kelly_fraction",
        "mar_ratio",
    }
    assert expected_keys == set(m.keys())


def test_full_metrics_n() -> None:
    m = full_metrics([1.0, 2.0, 3.0])
    assert m["n"] == 3


def test_full_metrics_empty() -> None:
    m = full_metrics([])
    assert m["n"] == 0
    assert m["profit_factor"] is None
    assert m["win_rate"] is None


# ── load_trades ───────────────────────────────────────────────────────────────


def _write_jsonl(path: Path, events: list[dict]) -> None:
    with path.open("w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def test_load_trades_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_trades("/nonexistent/path.jsonl")


def test_load_trades_empty(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text("")
    trades = load_trades(str(p))
    assert trades == []


def test_load_trades_one_complete(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_jsonl(
        p,
        [
            {
                "event": "OPEN",
                "trade_id": "T1",
                "symbol": "BTC/USDT",
                "side": "BUY",
                "entry_price": 60000.0,
                "timestamp": 1_782_500_000.0,
                "regime": "bull_trend",
                "score": 80,
            },
            {
                "event": "CLOSE",
                "trade_id": "T1",
                "symbol": "BTC/USDT",
                "pnl_usd": 10.0,
                "pnl_pct": 0.5,
                "mae_pct": -0.1,
                "mfe_pct": 0.8,
                "duration_s": 3600.0,
                "reason": "TP",
            },
        ],
    )
    trades = load_trades(str(p))
    assert len(trades) == 1
    t = trades[0]
    assert t.trade_id == "T1"
    assert t.symbol == "BTC/USDT"
    assert t.side == "BUY"
    assert t.pnl_usd == pytest.approx(10.0)
    assert t.regime == "bull_trend"


def test_load_trades_orphan_open_ignored(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_jsonl(
        p,
        [
            {
                "event": "OPEN",
                "trade_id": "T2",
                "symbol": "X",
                "side": "BUY",
                "entry_price": 1.0,
                "timestamp": 1_782_500_000.0,
            },
        ],
    )
    trades = load_trades(str(p))
    assert trades == []


def test_load_trades_multiple(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    events = []
    for i in range(5):
        events += [
            {
                "event": "OPEN",
                "trade_id": f"T{i}",
                "symbol": "ETH/USDT",
                "side": "SELL",
                "entry_price": 3000.0,
                "timestamp": 1_782_500_000.0 + i * 1000,
                "regime": "sideways",
            },
            {
                "event": "CLOSE",
                "trade_id": f"T{i}",
                "symbol": "ETH/USDT",
                "pnl_usd": (-1.0 if i % 2 else 2.0),
                "pnl_pct": (-0.1 if i % 2 else 0.2),
            },
        ]
    _write_jsonl(p, events)
    trades = load_trades(str(p))
    assert len(trades) == 5


# ── Trade dataclass ───────────────────────────────────────────────────────────


def test_trade_dataclass_fields() -> None:
    t = Trade(
        trade_id="X",
        symbol="A/B",
        side="BUY",
        regime="bull_trend",
        score=75,
        entry_price=100.0,
        pnl_usd=5.0,
        pnl_pct=0.05,
        mae_pct=-0.1,
        mfe_pct=0.2,
        duration_s=1800.0,
        exit_reason="TP",
    )
    assert t.atr_pct is None
    assert t.volume_usd is None
    assert t.opened_at is None
