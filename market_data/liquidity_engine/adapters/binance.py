from __future__ import annotations

import json
from datetime import datetime, timezone

from market_data.liquidity_engine.adapters.base_ws import BaseWebSocketClient
from market_data.liquidity_engine.models import MarketEvent


class BinanceWebSocketClient(BaseWebSocketClient):
    exchange = "binance"
    ws_url = "wss://stream.binance.com:9443/stream"

    async def _subscribe(self, ws) -> None:
        params = []
        for symbol in self.symbols:
            s = symbol.lower()
            params.append(f"{s}@trade")
            params.append(f"{s}@depth@100ms")
        payload = {
            "method": "SUBSCRIBE",
            "params": params,
            "id": 1,
        }
        await ws.send(json.dumps(payload))

    def parse_message(self, raw_message: str, received_at: datetime) -> list[MarketEvent]:
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return []

        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return []

        if data.get("e") == "trade":
            raw_t = data.get("T")
            raw_e = data.get("E")
            if raw_t is not None:
                ts = int(raw_t)
            elif raw_e is not None:
                ts = int(raw_e)
            else:
                ts = int(received_at.timestamp() * 1000)
            exchange_ts = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
            price = float(data.get("p", 0))
            qty = float(data.get("q", 0))
            side = "SELL" if bool(data.get("m", False)) else "BUY"
            notional = price * qty
            return [
                MarketEvent(
                    exchange=self.exchange,
                    symbol=str(data.get("s", "")).upper(),
                    event_type="trade",
                    timestamp_exchange=exchange_ts,
                    timestamp_received=received_at,
                    price=price,
                    quantity=qty,
                    notional_usd=notional,
                    side=side,
                    trade_id=str(data.get("t", "")),
                    latency_ms=(received_at - exchange_ts).total_seconds() * 1000,
                    priority=1 if notional >= 10_000 else 0,
                    raw_payload=data,
                )
            ]

        if data.get("e") == "depthUpdate" or ("b" in data and "a" in data):
            ts = int(data.get("E") or int(received_at.timestamp() * 1000))
            exchange_ts = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
            symbol = str(data.get("s", "")).upper()
            bids = [[float(p), float(q)] for p, q in data.get("b", [])]
            asks = [[float(p), float(q)] for p, q in data.get("a", [])]
            return [
                MarketEvent(
                    exchange=self.exchange,
                    symbol=symbol,
                    event_type="orderbook",
                    timestamp_exchange=exchange_ts,
                    timestamp_received=received_at,
                    latency_ms=(received_at - exchange_ts).total_seconds() * 1000,
                    raw_payload={"bids": bids, "asks": asks, "raw": data},
                )
            ]

        return []
