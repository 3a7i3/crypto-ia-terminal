"""U3a bounded scanner fixture through the actual publisher, reader and GET API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from observability import market_radar_snapshot as producer
from observability.operator_api import app as api
from observability.operator_api.market_reader import MarketSnapshotReader
from tests.cross_stack.generate_market_fixture import MARKET_FIXED_NOW


def scanner_packets():
    return [
        {"symbol": f"S{i:02}/USDT", "confidence": 95 - i / 3,
         "side": ("BUY", "SELL", "UNKNOWN")[i % 3], "regime": "sideways",
         "created_at": "2026-09-14T19:59:55Z", "entry_price": 100,
         "stop_loss": 90, "take_profit": 110, "risk_pct": 2}
        for i in range(60)
    ]


def generate_scanner_fixture(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / "_producer" / "L_scanner" / "market.json"
    with patch.object(producer.radar_bot, "load_recent_packets", return_value=scanner_packets()):
        producer.write_market_snapshot(artifact, now_fn=lambda: MARKET_FIXED_NOW)
    reader = MarketSnapshotReader(path=artifact, now_fn=lambda: MARKET_FIXED_NOW + 30)
    with patch.object(api, "_market_reader", reader), TestClient(api.app) as client:
        response = client.get("/api/operator/v1/market")
    result = {"http_status": response.status_code, "body": response.json()}
    (out_dir / "L_scanner.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    generate_scanner_fixture(parser.parse_args().out)
