from __future__ import annotations

import json

from observability import market_radar_snapshot as market


def _packets():
    return [
        {
            "symbol": "BTC/USDT",
            "confidence": 80,
            "side": "BUY",
            "regime": "bull_trend",
            "created_at": "2026-09-14T20:00:00Z",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
        },
        {
            "symbol": "BTC/USDT",
            "confidence": 70,
            "side": "BUY",
            "regime": "bull_trend",
            "created_at": "2026-09-14T20:01:00Z",
        },
        {
            "symbol": "ETH/USDT",
            "confidence": 62,
            "side": "SELL",
            "regime": "sideways",
            "created_at": "2026-09-14T19:59:00Z",
        },
        {
            "symbol": "SOL/USDT",
            "confidence": 45,
            "side": "BUY",
            "regime": "bull_trend",
            "created_at": "2026-09-14T19:58:00Z",
        },
    ]


def test_build_market_snapshot_reuses_radar_stats_without_execution_fields(monkeypatch):
    monkeypatch.setattr(market.radar_bot, "load_recent_packets", lambda _hours: _packets())

    snap = market.build_market_snapshot(now_fn=lambda: 1_757_883_660.0)

    assert snap["product"] == "CryptoRadar"
    assert snap["domain"] == "market"
    assert snap["authority"] == "OBSERVATIONAL_TELEMETRY"
    assert snap["mode"] == "OBSERVATION"
    assert snap["packets_observed"] == 4
    assert snap["source_updated_at_utc"] == "2026-09-14T20:01:00Z"
    assert snap["universe_size"] == 3
    assert snap["actionable_count"] == 1
    assert snap["watchlist_count"] == 1
    assert snap["market_regime"] == "bull_trend"

    assert len(snap["top_opportunities"]) == 1
    row = snap["top_opportunities"][0]
    assert row["symbol"] == "BTC/USDT"
    assert row["avg_confidence"] == 75.0
    assert row["dominant_side"] == "LONG"

    blob = json.dumps(snap).lower()
    for forbidden in (
        '"entry"',
        '"entry_price"',
        '"sl"',
        '"stop_loss"',
        '"tp"',
        '"take_profit"',
        '"trade_allowed"',
        '"is_actionable"',
    ):
        assert forbidden not in blob


def test_atomic_writer_publishes_parseable_complete_document(tmp_path, monkeypatch):
    monkeypatch.setattr(market.radar_bot, "load_recent_packets", lambda _hours: _packets())
    path = tmp_path / "cryptoradar_market_snapshot.json"

    produced = market.write_market_snapshot(path, now_fn=lambda: 1_757_883_660.0)

    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == produced


def test_publish_once_is_fail_passive(tmp_path, monkeypatch):
    monkeypatch.setattr(
        market,
        "write_market_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    assert market.publish_once(tmp_path / "market.json") is False
