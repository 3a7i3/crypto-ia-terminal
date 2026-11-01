"""Closed four-instrument pilot plan; not an activation authorisation."""

from dataclasses import asdict, dataclass
import hashlib
import json
from urllib.parse import urlencode
from observability.market_venues.models import Binding
from observability.venue_quote_comparison import InstrumentKey

HOSTS = {"bybit": "api.bybit.com", "okx": "www.okx.com"}
NATIVE = {
    "bybit": {"BTC": "BTCUSDT", "ETH": "ETHUSDT"},
    "okx": {"BTC": "BTC-USDT", "ETH": "ETH-USDT"},
}


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def roster():
    result = []
    for base in ("BTC", "ETH"):
        for venue in ("bybit", "okx"):
            native = NATIVE[venue][base]
            definition = {
                "venue": venue,
                "native_symbol": native,
                "base": base,
                "quote": "USDT",
                "market_kind": "SPOT",
                "contract_identity": "SPOT",
            }
            result.append(
                Binding(
                    venue,
                    native,
                    InstrumentKey(base, "USDT", "SPOT", "USDT", "SPOT"),
                    "PILOT539_" + venue + "_" + base,
                    fingerprint(definition),
                )
            )
    return tuple(result)


@dataclass(frozen=True)
class RequestSpec:
    venue: str
    purpose: str
    native_symbol: str | None = None

    def validate(self):
        if self.venue not in HOSTS or self.purpose not in ("metadata", "time", "book"):
            raise ValueError("REQUEST_NOT_ALLOWLISTED")
        if self.purpose == "time":
            if self.native_symbol is not None:
                raise ValueError("REQUEST_NOT_ALLOWLISTED")
        elif self.native_symbol not in NATIVE[self.venue].values():
            raise ValueError("REQUEST_NOT_ALLOWLISTED")
        return self

    @property
    def host(self):
        self.validate()
        return HOSTS[self.venue]

    @property
    def target(self):
        self.validate()
        if self.venue == "bybit":
            path = {
                "metadata": "/v5/market/instruments-info",
                "time": "/v5/market/time",
                "book": "/v5/market/orderbook",
            }[self.purpose]
            params = (
                {}
                if self.purpose == "time"
                else {"category": "spot", "symbol": self.native_symbol}
            )
            if self.purpose == "book":
                params["limit"] = "1"
        else:
            path = {
                "metadata": "/api/v5/public/instruments",
                "time": "/api/v5/public/time",
                "book": "/api/v5/market/books",
            }[self.purpose]
            params = {} if self.purpose == "time" else {"instId": self.native_symbol}
            if self.purpose == "metadata":
                params["instType"] = "SPOT"
            if self.purpose == "book":
                params["sz"] = "1"
        return path + ("?" + urlencode(params) if params else "")

    def document(self):
        return {
            "venue": self.venue,
            "purpose": self.purpose,
            "native_symbol": self.native_symbol,
            "method": "GET",
            "host": self.host,
            "target": self.target,
        }


@dataclass(frozen=True)
class PilotPlan:
    cycles: int = 120
    interval_ms: int = 5000
    duration_ms: int = 600000
    max_age_ms: int = 5000
    max_skew_ms: int = 500
    max_rtt_ms: int = 1000
    max_clock_jump_ms: int = 50
    max_clock_offset_ms: int = 250
    request_timeout_ms: int = 3000
    max_response_bytes: int = 65536
    max_run_bytes: int = 16777216

    def validate(self):
        limits = {
            "cycles": (1, 120),
            "interval_ms": (5000, 60000),
            "duration_ms": (1, 600000),
            "max_age_ms": (1, 5000),
            "max_skew_ms": (0, 500),
            "max_rtt_ms": (1, 1000),
            "max_clock_jump_ms": (0, 50),
            "max_clock_offset_ms": (0, 250),
            "request_timeout_ms": (1, 3000),
            "max_response_bytes": (256, 65536),
            "max_run_bytes": (16384, 16777216),
        }
        for name, (lo, hi) in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError("INVALID_PILOT_LIMIT:" + name)
        return self

    def document(self):
        self.validate()
        return {
            "schema_version": "1.0.0",
            "mission": "MARKET-MULTI-VENUE-04",
            "activation_status": "PREPARED_NOT_AUTHORISED",
            "parameters": asdict(self),
            "bindings": [asdict(b) for b in roster()],
            "maximum_requests": 4 + 6 * self.cycles,
            "network_methods": ["GET"],
            "credentials": False,
            "trading_authority": False,
            "instrument_mapping_admission": "PENDING_OPERATOR_REVIEW",
            "endpoints": [s.document() for s in requests()],
        }


def requests():
    return tuple(
        [RequestSpec(v, "time") for v in HOSTS]
        + [
            RequestSpec(b.venue, p, b.native_symbol)
            for b in roster()
            for p in ("metadata", "book")
        ]
    )
