"""Invented offline answers only. Never a source of market observations."""

from datetime import datetime, timezone
import json
from .capture import Instant, Response


class SyntheticClock:
    def __init__(self):
        self.wall = (
            int(datetime(2026, 10, 31, 12, tzinfo=timezone.utc).timestamp())
            * 1000000000
        )
        self.mono = 1000000000

    def sample(self):
        return Instant(self.wall, self.mono)

    def advance(self, milliseconds):
        self.wall += milliseconds * 1000000
        self.mono += milliseconds * 1000000

    def sleep(self, seconds):
        self.advance(round(seconds * 1000))


class SyntheticTransport:
    evidence_kind = "SYNTHETIC"

    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    def fetch(self, spec, *, timeout_ms, max_bytes):
        spec.validate()
        self.calls.append(spec)
        self.clock.advance(20)
        ms = self.clock.wall // 1000000
        base = (
            "BTC"
            if spec.native_symbol and spec.native_symbol.startswith("BTC")
            else "ETH"
        )
        if spec.purpose == "time":
            body = (
                {
                    "retCode": 0,
                    "result": {
                        "timeNano": str(self.clock.wall),
                        "timeSecond": str(self.clock.wall // 1000000000),
                    },
                }
                if spec.venue == "bybit"
                else {"code": "0", "data": [{"ts": str(ms)}]}
            )
        elif spec.purpose == "metadata":
            body = (
                {
                    "retCode": 0,
                    "result": {
                        "category": "spot",
                        "list": [
                            {
                                "symbol": spec.native_symbol,
                                "baseCoin": base,
                                "quoteCoin": "USDT",
                                "status": "Trading",
                                "priceFilter": {"tickSize": "0.1"},
                                "lotSizeFilter": {"basePrecision": "0.000001"},
                            }
                        ],
                    },
                }
                if spec.venue == "bybit"
                else {
                    "code": "0",
                    "data": [
                        {
                            "instId": spec.native_symbol,
                            "instType": "SPOT",
                            "baseCcy": base,
                            "quoteCcy": "USDT",
                            "state": "live",
                            "tickSz": "0.1",
                            "lotSz": "0.000001",
                        }
                    ],
                }
            )
        elif spec.venue == "bybit":
            body = {
                "retCode": 0,
                "result": {
                    "s": spec.native_symbol,
                    "b": [["100", "2"]],
                    "a": [["100.2", "3"]],
                    "ts": ms - 5,
                    "u": len(self.calls),
                },
            }
        else:
            body = {
                "code": "0",
                "data": [
                    {
                        "bids": [["100.3", "2", "0", "1"]],
                        "asks": [["100.5", "3", "0", "1"]],
                        "ts": str(ms - 5),
                        "seqId": len(self.calls),
                    }
                ],
            }
        return Response(
            200, json.dumps(body).encode(), {"content-type": "application/json"}
        )
