"""Invented, native-shaped inputs for the L1 tests. No real observation is used."""
import copy
import json

from observability.radar_composite.composite import V1_HYPOTHESIS
from observability.radar_composite.decoders import payload_sha256
from observability.radar_composite.instruments import (
    Binding, instrument_dict, spot_instrument,
)

START = 1_795_128_000_000  # UTC-aligned M5 boundary
STEP = 10_000
BTC = spot_instrument("BTC", "USDT")
MEXC = Binding("mexc", "BTCUSDT", "BTCUSDT", BTC)
KRAKEN = Binding("kraken", "XBTUSDT", "XBTUSDT", BTC, "kraken.Assets:XXBT.altname=XBT")
DIGEST = payload_sha256(b"synthetic")


def instants():
    return [START + k * STEP for k in range(30)]


def trade(venue, price, trade_ms, received_ms, *, trade_id=None, kind="SYNTHETIC",
          qty="0.01", side="buy"):
    binding = MEXC if venue == "mexc" else KRAKEN
    return {
        "venue": venue, "provider": venue, "native_symbol": binding.native_symbol,
        "price": price, "qty": qty, "side": side, "trade_ms": trade_ms,
        "native_time": str(trade_ms), "trade_id": trade_id, "received_ms": received_ms,
        "payload_sha256": DIGEST,
        "identity_evidence": "REQUEST_CONTEXT" if venue == "mexc" else "NATIVE_KEY_ECHO",
        "evidence_kind": kind,
    }


def poll(venue, requested_ms, received_ms, status="OK", reason=None):
    binding = MEXC if venue == "mexc" else KRAKEN
    return {
        "venue": venue, "native_symbol": binding.native_symbol, "provider": venue,
        "requested_ms": requested_ms, "received_ms": received_ms, "status": status,
        "reason": reason, "payload_sha256": None,
    }


def series(venue, base_price=62000, lag=700, receipt=100, skip=()):
    """One trade per instant, executed ``lag`` ms before and received ``receipt`` ms before."""
    out = []
    for k, instant in enumerate(instants()):
        if k in skip:
            continue
        price = str(base_price + k)
        tid = f"{venue[0]}{k}"
        out.append(trade(venue, price, instant - lag, instant - receipt, trade_id=tid))
    return out


def packet(trades, polls=(), venues=("mexc", "kraken"), kind="SYNTHETIC", **params):
    parameters = copy.deepcopy(V1_HYPOTHESIS)
    parameters["max_trade_age_ms"] = {v: parameters["max_trade_age_ms"][v] for v in venues}
    parameters.update(params)
    bindings = [b for b in (MEXC, KRAKEN) if b.venue in venues]
    return {
        "version": 2, "kind": kind, "instrument": instrument_dict(BTC),
        "bindings": [
            {k: v for k, v in b.as_dict().items() if k != "instrument_id"} for b in bindings
        ],
        "reference_venue": "mexc" if "mexc" in venues else venues[0],
        "start_ms": START, "parameters": parameters,
        "polls": list(polls), "trades": list(trades),
    }


def mexc_payload(rows):
    return json.dumps(rows).encode()


def kraken_payload(key, rows, last="1795128300000000000"):
    return json.dumps({"error": [], "result": {key: rows, "last": last}}).encode()
