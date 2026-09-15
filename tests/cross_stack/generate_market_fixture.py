"""Generate the WEB-01 MARKET cross-stack fixture through the real code path.

The fixture is not a handwritten API body. It is produced by:

    deterministic passive DecisionPacket-like evidence
        -> observability.market_radar_snapshot.write_market_snapshot
        -> atomic JSON artifact
        -> MarketSnapshotReader
        -> real FastAPI GET /api/operator/v1/market

Only the evidence source is deterministic/fake; the producer, atomic writer,
reader, validation and API route are the production implementation under test.
No Telegram call, exchange call, credential, advisor, risk, execution or PPL
authority is involved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from observability import market_radar_snapshot as market_producer
from observability.operator_api import app as api_app
from observability.operator_api.market_reader import MarketSnapshotReader

MARKET_FIXED_NOW = 1_789_416_000.0  # 2026-09-14T20:00:00Z
MARKET_READ_NOW = MARKET_FIXED_NOW + 30.0


def _packets() -> List[Dict[str, Any]]:
    return [
        {
            "symbol": "BTC/USDT",
            "confidence": 82.0,
            "side": "BUY",
            "regime": "bull_trend",
            "created_at": "2026-09-14T19:59:50Z",
            # Deliberately present upstream: the strict MARKET projection must
            # remove every execution-shaped field from the exposed payload.
            "entry_price": 60123.0,
            "stop_loss": 59000.0,
            "take_profit": 62000.0,
        },
        {
            "symbol": "BTC/USDT",
            "confidence": 74.0,
            "side": "BUY",
            "regime": "bull_trend",
            "created_at": "2026-09-14T19:59:55Z",
        },
        {
            "symbol": "ETH/USDT",
            "confidence": 61.0,
            "side": "SELL",
            "regime": "sideways",
            "created_at": "2026-09-14T19:59:40Z",
        },
    ]


def generate_market_fixture(out_dir: Path) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "_producer" / "G_market" / "cryptoradar_market_snapshot.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    original_loader = market_producer.radar_bot.load_recent_packets
    previous_market_reader = api_app.get_market_reader()
    try:
        market_producer.radar_bot.load_recent_packets = lambda _hours: _packets()
        producer_doc = market_producer.write_market_snapshot(
            artifact_path,
            now_fn=lambda: MARKET_FIXED_NOW,
        )

        # API reader uses the real file produced above and a deterministic
        # reader clock 30 s later, therefore expected freshness is FRESH.
        api_app._market_reader = MarketSnapshotReader(
            path=artifact_path,
            stale_after_s=90.0,
            now_fn=lambda: MARKET_READ_NOW,
        )
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/market")

        body = response.json()
        result = {
            "http_status": response.status_code,
            "body": body,
            "_proof": {
                "producer_authority": producer_doc.get("authority"),
                "producer_product": producer_doc.get("product"),
                "producer_rows": len(producer_doc.get("top_opportunities", [])),
                "artifact_is_regular_file": artifact_path.is_file(),
            },
        }
        (out_dir / "G_market.json").write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return result
    finally:
        market_producer.radar_bot.load_recent_packets = original_loader
        api_app._market_reader = previous_market_reader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate_market_fixture(args.out)


if __name__ == "__main__":
    main()
