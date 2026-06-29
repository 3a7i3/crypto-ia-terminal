"""
tests/scripts/test_regime_audit.py — Tests de régression pour analysis/regime_audit.py
et analysis/hypotheses.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from analysis.base import Trade, full_metrics
from analysis.hypotheses import (
    _binomial_p_value,
    _wilson_ci,
    h1_buy_sideways,
    h2_sell_bear,
    h3_high_score_better,
    run_all_hypotheses,
)
from analysis.regime_audit import _filter_by_date
from analysis.regime_audit import main as audit_main

# ── _filter_by_date ───────────────────────────────────────────────────────────


def _make_trade(
    regime: str = "sideways",
    side: str = "BUY",
    pnl: float = 1.0,
    ts: float = 1_782_500_000.0,
    score: int = 70,
) -> Trade:
    return Trade(
        trade_id="T",
        symbol="X/Y",
        side=side,
        regime=regime,
        score=score,
        entry_price=1.0,
        pnl_usd=pnl,
        pnl_pct=pnl / 100,
        mae_pct=-0.1,
        mfe_pct=0.5,
        duration_s=3600.0,
        exit_reason="TP",
        opened_at=ts,
    )


def test_filter_keeps_recent() -> None:
    since = datetime(2026, 6, 25, tzinfo=timezone.utc)
    t = _make_trade(ts=1_782_500_000.0)  # ~2026-06-25+
    result = _filter_by_date([t], since)
    assert len(result) == 1


def test_filter_removes_old() -> None:
    since = datetime(2026, 6, 25, tzinfo=timezone.utc)
    t = _make_trade(ts=1_782_000_000.0)  # ~2026-06-10
    result = _filter_by_date([t], since)
    assert len(result) == 0


def test_filter_none_returns_all() -> None:
    trades = [_make_trade() for _ in range(5)]
    assert len(_filter_by_date(trades, None)) == 5


def test_filter_skips_none_timestamp() -> None:
    t = _make_trade()
    t.opened_at = None
    since = datetime(2026, 6, 25, tzinfo=timezone.utc)
    result = _filter_by_date([t], since)
    assert len(result) == 0  # sans timestamp → exclu


# ── Wilson CI ─────────────────────────────────────────────────────────────────


def test_wilson_ci_50pct() -> None:
    lo, hi = _wilson_ci(50, 100)
    assert lo < 0.5 < hi


def test_wilson_ci_zero_n() -> None:
    assert _wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_ci_bounds() -> None:
    lo, hi = _wilson_ci(5, 10)
    assert 0 <= lo <= hi <= 1


# ── Binomial p-value ──────────────────────────────────────────────────────────


def test_pvalue_neutral() -> None:
    p = _binomial_p_value(50, 100, p0=0.5)
    assert p > 0.9  # neutre → pas de rejet


def test_pvalue_extreme_high() -> None:
    p = _binomial_p_value(90, 100, p0=0.5)
    assert p < 0.001  # fortement significatif


def test_pvalue_extreme_low() -> None:
    p = _binomial_p_value(10, 100, p0=0.5)
    assert p < 0.001


def test_pvalue_zero_n() -> None:
    assert _binomial_p_value(0, 0) == 1.0


# ── H1 — BUY sideways ────────────────────────────────────────────────────────


def test_h1_non_conclusive_not_enough_data() -> None:
    trades = [_make_trade("sideways", "BUY", -1.0) for _ in range(10)]
    result = h1_buy_sideways(trades)
    assert result.accepted is None
    assert result.n == 10


def test_h1_accepted_with_sufficient_data() -> None:
    trades = [_make_trade("sideways", "BUY", -2.0) for _ in range(35)]
    result = h1_buy_sideways(trades)
    assert result.n == 35
    assert result.accepted is True  # expectancy < 0, p-value devrait être < 0.05


def test_h1_ignores_non_sideways() -> None:
    trades = [_make_trade("sideways", "BUY", -2.0) for _ in range(35)] + [
        _make_trade("bull_trend", "BUY", 10.0) for _ in range(100)
    ]
    result = h1_buy_sideways(trades)
    assert result.n == 35  # seuls les sideways BUY comptent


# ── H2 — SELL bear ────────────────────────────────────────────────────────────


def test_h2_non_conclusive() -> None:
    trades = [_make_trade("bear_trend", "SELL", 1.0) for _ in range(5)]
    result = h2_sell_bear(trades)
    assert result.accepted is None


def test_h2_accepted() -> None:
    trades = [_make_trade("bear_trend", "SELL", 3.0) for _ in range(35)]
    result = h2_sell_bear(trades)
    assert result.accepted is True


# ── H3 — Score ────────────────────────────────────────────────────────────────


def test_h3_non_conclusive_not_enough() -> None:
    trades = [_make_trade(score=80) for _ in range(5)]
    result = h3_high_score_better(trades)
    assert result.accepted is None


# ── run_all_hypotheses ────────────────────────────────────────────────────────


def test_run_all_hypotheses_empty() -> None:
    results = run_all_hypotheses([])
    assert len(results) == 4
    for r in results:
        assert r.accepted is None  # toutes non concluantes


def test_run_all_hypotheses_returns_4() -> None:
    trades = [_make_trade() for _ in range(100)]
    results = run_all_hypotheses(trades)
    assert len(results) == 4
    assert [r.name for r in results] == ["H1", "H2", "H3", "H4"]


# ── audit_main ────────────────────────────────────────────────────────────────


def _write_jsonl(path: Path, events: list[dict]) -> None:
    with path.open("w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def test_audit_main_missing_file() -> None:
    assert audit_main(jsonl_path="/nonexistent/file.jsonl") == 1


def test_audit_main_insufficient_data(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    events = []
    for i in range(3):
        events += [
            {
                "event": "OPEN",
                "trade_id": f"T{i}",
                "symbol": "X/Y",
                "side": "BUY",
                "entry_price": 1.0,
                "timestamp": 1_782_500_000.0 + i * 1000,
                "regime": "sideways",
            },
            {
                "event": "CLOSE",
                "trade_id": f"T{i}",
                "symbol": "X/Y",
                "pnl_usd": 1.0,
                "pnl_pct": 0.1,
            },
        ]
    _write_jsonl(p, events)
    result = audit_main(jsonl_path=str(p))
    assert result == 0  # données insuffisantes → exit 0 avec message


def test_audit_main_with_data(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    events = []
    for i in range(15):
        events += [
            {
                "event": "OPEN",
                "trade_id": f"T{i}",
                "symbol": "ETH/USDT",
                "side": "BUY",
                "entry_price": 3000.0,
                "timestamp": 1_782_500_000.0 + i * 1000,
                "regime": "sideways",
                "score": 70,
            },
            {
                "event": "CLOSE",
                "trade_id": f"T{i}",
                "symbol": "ETH/USDT",
                "pnl_usd": (2.0 if i % 2 else -1.0),
                "pnl_pct": 0.1,
            },
        ]
    _write_jsonl(p, events)
    result = audit_main(jsonl_path=str(p))
    assert result == 0


# ── full_metrics cohérence ────────────────────────────────────────────────────


def test_full_metrics_consistency() -> None:
    pnls = [5.0, -3.0, 8.0, -1.0, 2.0]
    m = full_metrics(pnls)
    assert m["n"] == 5
    assert m["total_pnl_usd"] == pytest.approx(11.0)
    assert m["win_rate"] == pytest.approx(0.6)
    assert m["profit_factor"] == pytest.approx(15.0 / 4.0)
