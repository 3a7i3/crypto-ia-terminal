"""Synthetic full-catalogue proof through the real producer, reader and GET route.

No restored data, exchange, collector, Telegram or execution is used.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from observability import market_radar_snapshot as producer
from observability.operator_api import app as api_app
from observability.operator_api.market_reader import MarketSnapshotReader

FIXED_NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc).timestamp()


def packet(symbol, confidence, *, age=60, side="BUY", regime="RANGE"):
    return {
        "symbol": symbol,
        "confidence": confidence,
        "side": side,
        "regime": regime,
        "created_at": datetime.fromtimestamp(FIXED_NOW - age, timezone.utc).isoformat(),
        "entry_price": 123,
        "secret": "SYNTHETIC_MUST_NOT_ESCAPE",
        "volume": 1000,
    }


def synthetic_packets():
    rows = [
        packet(f"COIN{i:02d}/USDT", 90 - i * .3,
               side="BUY" if i % 2 == 0 else "SELL",
               regime="VOLATILE" if i % 3 == 0 else "RANGE")
        for i in range(45)
    ]
    return rows + [
        packet("BTC/USDT", 68, side="SELL", regime="TREND_BEAR"),
        packet("BTC/USDT", 30, age=120, regime="RANGE"),
        packet("ETH/USDT", 55),
        packet("OLD/USDT", 99, age=5 * 3600),
        packet("FUTURE/USDT", 99, age=-60),
        {**packet("UNDATED/USDT", 99), "created_at": "unresolved"},
    ]


def generate_market_catalogue_fixture(out_dir: Path):
    out_dir = Path(out_dir)
    artifact = out_dir / "_producer" / "R_market_catalogue" / "market.json"
    original_loader = producer.radar_bot.load_recent_packets
    previous_reader = api_app.get_market_reader()
    try:
        producer.radar_bot.load_recent_packets = lambda _hours: synthetic_packets()
        producer.write_market_snapshot(
            artifact, include_catalogue=True, window_hours=4,
            top_n=20, now_fn=lambda: FIXED_NOW,
        )
        api_app._market_reader = MarketSnapshotReader(
            path=artifact, now_fn=lambda: FIXED_NOW + 120,
        )
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/market")
        result = {"http_status": response.status_code, "body": response.json()}
        (out_dir / "R_market_catalogue.json").write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8",
        )
        return result
    finally:
        producer.radar_bot.load_recent_packets = original_loader
        api_app._market_reader = previous_reader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    generate_market_catalogue_fixture(parser.parse_args().out)


if __name__ == "__main__":
    main()
