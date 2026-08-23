from __future__ import annotations

import json
from datetime import datetime, timezone

from market_data.liquidity_engine.adapters.base_ws import BaseWebSocketClient
from market_data.liquidity_engine.models import MarketEvent


class MexcWebSocketClient(BaseWebSocketClient):
    exchange = "mexc"
    ws_url = "wss://contract.mexc.com/ws"

    async def _subscribe(self, ws) -> None:
        for symbol in self.symbols:
            sym = self._mexc_symbol(symbol)
            await ws.send(
                json.dumps({"method": "sub.deal", "param": {"symbol": sym}})
            )
            await ws.send(
                json.dumps({"method": "sub.depth", "param": {"symbol": sym}})
            )

    def parse_message(self, raw_message: str, received_at: datetime) -> list[MarketEvent]:
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return []

        channel = payload.get("channel")
        if channel == "push.deal":
            symbol = self._normalize_symbol(payload.get("symbol") or payload.get("symbolName") or payload.get("data", {}).get("symbol", ""))
            out: list[MarketEvent] = []
            for t in payload.get("data", {}).get("deals", []):
                ts = int(t.get("t") or int(received_at.timestamp() * 1000))
                if ts < 1_000_000_000_000:
                    ts *= 1000
                exchange_ts = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
                price = float(t.get("p", 0))
                qty = float(t.get("v", 0))
                side = "BUY" if int(t.get("T", 1)) == 1 else "SELL"
                notional = price * qty
                out.append(
                    MarketEvent(
                        exchange=self.exchange,
                        symbol=symbol,
                        event_type="trade",
                        timestamp_exchange=exchange_ts,
                        timestamp_received=received_at,
                        price=price,
                        quantity=qty,
                        notional_usd=notional,
                        side=side,
                        trade_id=str(t.get("id", "")),
                        latency_ms=(received_at - exchange_ts).total_seconds() * 1000,
                        priority=1 if notional >= 10_000 else 0,
                        raw_payload=t,
                    )
                )
            return out

        if channel == "push.depth":
            data = payload.get("data", {})
            ts = int(data.get("timestamp") or int(received_at.timestamp() * 1000))
            if ts < 1_000_000_000_000:
                ts *= 1000
            exchange_ts = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
            symbol = self._normalize_symbol(payload.get("symbol") or data.get("symbol", ""))
            bids = [[float(p), float(q)] for p, q in zip(data.get("bids", []), data.get("bidVols", []))]
            asks = [[float(p), float(q)] for p, q in zip(data.get("asks", []), data.get("askVols", []))]
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

    @staticmethod
    def _mexc_symbol(symbol: str) -> str:
        s = symbol.upper().replace("/", "")
        if s.endswith("USDT") and "_" not in s:
            return s[:-4] + "_USDT"
        return s

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return str(symbol or "").replace("_", "").replace("/", "").upper()
