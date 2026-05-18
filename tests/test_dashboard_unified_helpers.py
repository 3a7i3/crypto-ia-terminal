from __future__ import annotations

from dashboard_unified_helpers import (
    build_signal_lists,
    describe_feed_status,
    normalize_positions,
    summarize_multi_exchange,
)


def test_normalize_positions_supports_snapshot_shape() -> None:
    rows = normalize_positions(
        [
            {
                "symbol": "BTCUSDT",
                "side": "long",
                "entry": 64000.0,
                "current": 64500.0,
                "pnl_usd": 125.5,
                "pnl_pct": 1.96,
                "size_usd": 1500.0,
                "leverage": 3,
                "regime": "trend_bull",
                "age_min": 12.5,
            }
        ]
    )

    assert rows == [
        {
            "SYMBOL": "BTCUSDT",
            "SIDE": "LONG",
            "ENTRY": 64000.0,
            "CURRENT": 64500.0,
            "PNL USD": 125.5,
            "PNL %": 1.96,
            "SIZE USD": 1500.0,
            "LEVERAGE": 3,
            "REGIME": "trend_bull",
            "AGE MIN": 12.5,
        }
    ]


def test_build_signal_lists_prioritizes_tradeable_signals() -> None:
    signals = build_signal_lists(
        [
            {
                "symbol": "BTCUSDT",
                "signal": "BUY",
                "trade_allowed": True,
                "actionable": True,
                "confirmed": True,
                "conviction_score": 91,
                "score": 88,
                "regime": "trend_bull",
            },
            {
                "symbol": "ETHUSDT",
                "signal": "SELL",
                "trade_allowed": True,
                "actionable": True,
                "confirmed": True,
                "conviction_score": 89,
                "score": 86,
                "regime": "trend_bear",
            },
            {
                "symbol": "SOLUSDT",
                "signal": "BUY",
                "trade_allowed": False,
                "actionable": True,
                "confirmed": True,
                "conviction_score": 87,
                "score": 84,
                "regime": "volatile",
            },
        ],
        top_n=2,
    )

    assert [row["Symbole"] for row in signals["dominant"]] == ["BTCUSDT", "ETHUSDT"]
    assert [row["Symbole"] for row in signals["buy"]] == ["BTCUSDT", "SOLUSDT"]
    assert [row["Symbole"] for row in signals["sell"]] == ["ETHUSDT"]


def test_describe_feed_status_marks_stale_payload() -> None:
    status = describe_feed_status({"ts": 100.0}, now_ts=160.0, warn_after_s=20, stale_after_s=45)

    assert status["status"] == "STALE"
    assert status["age_seconds"] == 60.0
    assert status["age_label"] == "1.0m"


def test_summarize_multi_exchange_reports_coverage() -> None:
    summary = summarize_multi_exchange(
        {
            "total_exchanges": 2,
            "symbols": {
                "BTCUSDT": {
                    "binance": {"price": 64000.0},
                    "bybit": {"price": 64010.0},
                },
                "ETHUSDT": {
                    "binance": {"price": 3100.0},
                    "bybit": {"price": None},
                },
            },
            "spreads": {
                "BTCUSDT": {"spread_pct": 0.015},
                "ETHUSDT": {"spread_pct": 0.025},
            },
        }
    )

    assert summary["coverage_pct"] == 75.0
    assert summary["exchange_rows"] == [
        {"Exchange": "BINANCE", "Couverture": "2/2", "Statut": "OK"},
        {"Exchange": "BYBIT", "Couverture": "1/2", "Statut": "PARTIEL"},
    ]
    assert summary["symbol_rows"] == [
        {"Symbole": "BTCUSDT", "Couverture": "2/2", "Spread %": 0.015, "Statut": "OK"},
        {"Symbole": "ETHUSDT", "Couverture": "1/2", "Spread %": 0.025, "Statut": "PARTIEL"},
    ]
