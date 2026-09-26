"""ACC-01 — unresolved/missing PnL must never become numeric zero or a win."""

from __future__ import annotations

import json

import pytest

from scripts.burnin_calibration_v3 import _compute_trade_stats
from scripts.prelive_gate import _compute_metrics
from tools.cri_calculator import (
    CLEAN_DATA_SINCE_ACTIVE,
    ScientificDatasetUnavailableError,
    balance_score,
    load_clean_trades,
    require_resolved_pnl_usd,
)


def _legacy_close(*, symbol: str, pnl_usd, evidence_status: str | None = None) -> dict:
    row = {
        "event": "CLOSE",
        "ts": CLEAN_DATA_SINCE_ACTIVE.timestamp() + 3600,
        "symbol": symbol,
        "price": 1000.0,
        "score": 70,
        "regime": "RANGE",
        "duration_s": 60,
        "pnl_usd": pnl_usd,
        "pnl_pct": 0.0 if pnl_usd is None else float(pnl_usd) / 10.0,
    }
    if evidence_status is not None:
        row["evidence_status"] = evidence_status
    return row


def test_legacy_loader_excludes_unresolved_and_missing_pnl(tmp_path, monkeypatch):
    monkeypatch.delenv("PAPER_LIFECYCLE_AUTHORITY", raising=False)
    monkeypatch.delenv("PPL_AUTHORITY_EPOCH_ID", raising=False)
    path = tmp_path / "paper_trades.jsonl"
    rows = [
        _legacy_close(symbol="AAA/USDT", pnl_usd=None, evidence_status="UNRESOLVED"),
        _legacy_close(symbol="BBB/USDT", pnl_usd=None),
        _legacy_close(symbol="CCC/USDT", pnl_usd=-5.0),
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    kept = load_clean_trades(path)

    assert [(row["symbol"], row["pnl_usd"]) for row in kept] == [("CCC/USDT", -5.0)]


@pytest.mark.parametrize(
    "row",
    [
        {"pnl_usd": None},
        {"pnl_usd": None, "evidence_status": "UNRESOLVED"},
        {"pnl_usd": float("nan")},
        {"pnl_usd": float("inf")},
    ],
)
def test_required_realized_pnl_fails_closed(row):
    with pytest.raises(ScientificDatasetUnavailableError):
        require_resolved_pnl_usd(row)


def test_exact_zero_is_breakeven_not_win_for_balance_score():
    trades = [{"pnl_usd": 0.0}, {"pnl_usd": -1.0}]
    assert balance_score(trades) == 0.0


def test_balance_score_rejects_missing_pnl():
    with pytest.raises(ScientificDatasetUnavailableError):
        balance_score([{"pnl_usd": None}])


def test_prelive_metrics_reject_missing_pnl():
    with pytest.raises(ScientificDatasetUnavailableError):
        _compute_metrics([{"pnl_usd": None, "pnl_pct": 0.0}])


def test_burnin_stats_reject_missing_pnl():
    with pytest.raises(ScientificDatasetUnavailableError):
        _compute_trade_stats([{"pnl_usd": None, "pnl_pct": 0.0, "duration_s": 1}])


def test_burnin_zero_is_breakeven_not_win():
    stats = _compute_trade_stats(
        [
            {"pnl_usd": 0.0, "pnl_pct": 0.0, "duration_s": 1},
            {"pnl_usd": -1.0, "pnl_pct": -0.01, "duration_s": 1},
        ]
    )
    assert stats.count == 2
    assert stats.wins == 0
    assert stats.losses == 1
    assert stats.win_rate_pct == 0.0
