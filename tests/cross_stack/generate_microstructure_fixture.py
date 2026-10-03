"""Real U3b producer -> atomic artifact -> reader -> GET, synthetic LMI evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from observability.market_microstructure_snapshot import write_microstructure_snapshot
from observability.operator_api import app as api
from observability.operator_api.market_microstructure_reader import MarketMicrostructureReader

NOW = 1_789_416_000.0


def lmi_source():
    return {
        "updated_at": "2026-09-14T20:00:00+00:00", "exchange": "mexc",
        "watchlist": ["BTCUSDT", "ETHUSDT", "WAITUSDT"], "stream_watchlist": ["BTCUSDT", "ETHUSDT"],
        "coverage": {
            "BTCUSDT": {"status": "LIVE", "age_ms": 1000, "stream_requested": True, "reason": None},
            "ETHUSDT": {"status": "STALE", "age_ms": 30_000, "stream_requested": True, "reason": None},
            "WAITUSDT": {"status": "UNAVAILABLE", "age_ms": None, "stream_requested": False, "reason": "not_in_mexc_futures_catalog"},
        },
        "contract_meta": {"source": "api", "degraded_symbols": []}, "stats": {"events": 123},
        "symbols": {
            "BTCUSDT": {"symbol": "BTCUSDT", "timestamp_ms": int((NOW - 1) * 1000),
                        "state": "accumulation", "state_confidence": 0.8123, "price": 65_000,
                        "price_change_bps": 1.5, "flow": {"buy_volume_usd": 12_500.25,
                        "sell_volume_usd": 5000.75, "pressure_ratio": 0.7143, "window_ms": 10_000,
                        "timestamp_ms": int((NOW - 2) * 1000), "buy_count": 12, "sell_count": 5,
                        "buy_avg_size_usd": 1041.69, "sell_avg_size_usd": 1000.15,
                        "large_buy_count": 0, "large_sell_count": 0,
                        "buy_acceleration": -123.4567, "sell_acceleration": 0, "dominant_side": "buy",
                        "secret": "MUST_NOT_ESCAPE"},
                        "resistance": {"resistance_score": 12345.67, "fragility_score": 0.9877},
                        "liquidity": {"timestamp_ms": int((NOW - 40) * 1000),
                        "bid_added_usd": 100.25, "ask_added_usd": 0,
                        "bid_removed_usd": 12.5, "ask_removed_usd": 50,
                        "bid_consumed_usd": 0, "ask_consumed_usd": 500.125,
                        "cancellation_rate_bid": 1, "cancellation_rate_ask": 0.0909,
                        "net_liquidity_change_usd": -462.375, "raw": "MUST_NOT_ESCAPE"},
                        "state_components": {"pressure_ratio": 0.7143, "absorption": 0,
                        "fragility": 0.9877, "displacement_bps": 1.5, "canc_bid": 1,
                        "canc_ask": 0.0909, "message": "MUST_NOT_ESCAPE"},
                        "entry_price": 100, "secret": "MUST_NOT_ESCAPE"},
            "ETHUSDT": {"symbol": "ETHUSDT", "timestamp_ms": int((NOW - 30) * 1000),
                        "state": "quiet", "state_confidence": 0, "price": 0,
                        "flow": {}, "resistance": {}},
            # Ghost legacy state outside current watchlist must never become population.
            "GHOSTUSDT": {"symbol": "GHOSTUSDT", "state": "quiet", "price": 123},
        },
    }


def generate_microstructure_fixture(out_dir):
    out_dir = Path(out_dir)
    base = out_dir / "_producer" / "M_microstructure"
    base.mkdir(parents=True, exist_ok=True)
    source, artifact = base / "lmi.json", base / "microstructure.json"
    source.write_text(json.dumps(lmi_source()), encoding="utf-8")
    before = source.read_bytes()
    write_microstructure_snapshot(source, artifact, now_fn=lambda: NOW)
    with patch.object(api, "_microstructure_reader", MarketMicrostructureReader(artifact, now_fn=lambda: NOW + 2)), TestClient(api.app) as client:
        response = client.get("/api/operator/v1/market-microstructure")
    result = {"http_status": response.status_code, "body": response.json(), "_proof": {"source_unchanged": source.read_bytes() == before}}
    (out_dir / "M_microstructure.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    generate_microstructure_fixture(parser.parse_args().out)
