"""Invented observations. No venue was contacted; names only label two unit conventions.

``exchange_a`` publishes OI in contracts (size 0.0001 BTC) and funding every 8 h.
``exchange_b`` publishes OI in base units and funding every 1 h.
"""

import copy
import hashlib
from datetime import datetime, timedelta, timezone

T0 = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ms(dt):
    return int(dt.timestamp() * 1000)


def obs_a(at=T0, *, oi="1250000", mark="65000.5", received_delay_s=1, run="run-1", **overrides):
    doc = {
        "contract_version": "1.0.0",
        "venue": "exchange_a", "native_symbol": "BTC_USDT", "contract_type": "PERPETUAL_LINEAR",
        "quote_currency": "USDT", "base_currency": "BTC",
        "source_time_utc": iso(at), "received_at_utc": iso(at + timedelta(seconds=received_delay_s)),
        "provenance": {"source": "synthetic:exchange_a/ticker", "payload_sha256": sha("a" + iso(at) + oi + mark),
                       "mapping_id": "SYNTHETIC-A-BTC_USDT", "mapping_sha256": sha("SYNTHETIC-A-BTC_USDT"),
                       "collector_run_id": run},
        "measures": {
            "mark_price": {"value": mark},
            "index_price": {"value": "64990.0"},
            "spot_reference": {"value": "64980.25", "qualification": "QUALIFIED", "venue": "exchange_a",
                               "native_symbol": "BTCUSDT", "qualification_ref": "SYNTHETIC-SPOT-QUAL-1"},
            "open_interest": {"value": oi, "unit": "CONTRACTS", "contract_size_base": "0.0001"},
            "funding_rate": {"value": "0.0001", "interval_s": 28800, "interval_attested_by": "synthetic:contract-detail",
                             "next_funding_utc": iso(at + timedelta(hours=2))},
        },
    }
    doc.update(overrides)
    return doc


def obs_b(at=T0, *, oi="125.5", mark="65010", received_delay_s=1, **overrides):
    doc = {
        "contract_version": "1.0.0",
        "venue": "exchange_b", "native_symbol": "PF_XBTUSD", "contract_type": "PERPETUAL_LINEAR",
        "quote_currency": "USD", "base_currency": "BTC",
        "source_time_utc": iso(at), "received_at_utc": iso(at + timedelta(seconds=received_delay_s)),
        "provenance": {"source": "synthetic:exchange_b/tickers", "payload_sha256": sha("b" + iso(at) + oi)},
        "measures": {
            "mark_price": {"value": mark},
            "index_price": {"value": "65000"},
            "spot_reference": {"unavailable": "SPOT_REFERENCE_NOT_QUALIFIED"},
            "open_interest": {"value": oi, "unit": "BASE"},
            "funding_rate": {"value": "-0.00002", "interval_s": 3600, "interval_attested_by": "synthetic:docs"},
        },
    }
    doc.update(overrides)
    return doc


def without_source_time(doc, *, received, capture_id=None):
    out = copy.deepcopy(doc)
    out["source_time_utc"] = None
    out["received_at_utc"] = iso(received)
    if capture_id is not None:
        out["capture_id"] = capture_id
    return out
