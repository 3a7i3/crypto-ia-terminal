"""Pure publication builder; no writer, schedule, socket or exchange client."""

from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
from decimal import Decimal
from observability.venue_quote_comparison import compare_quotes, quote_metrics
from .decoders import aware, unavailable, validate_binding
from .models import ENDPOINTS, iso
from .schema import validate_publication

PAIR_FIELDS = (
    "status",
    "reason",
    "event_skew_ms",
    "mid_basis_bps",
    "buy_reference_sell_other_gross_bps",
    "buy_other_sell_reference_gross_bps",
    "buy_reference_sell_other_top_size_base",
    "buy_other_sell_reference_top_size_base",
)


def instrument_id(instrument):
    return hashlib.sha256(
        json.dumps(asdict(instrument), sort_keys=True).encode()
    ).hexdigest()[:24]


def exact(value):
    return None if value is None else format(value, "f")


def build_publication(
    bindings, observations, *, as_of, max_age_ms, max_skew_ms, evidence_kind
):
    if not aware(as_of) or evidence_kind not in ("OBSERVATION", "SYNTHETIC"):
        raise ValueError("Explicit publication clock and evidence kind required")
    bindings, observations = list(bindings), list(observations)
    if not bindings or len(bindings) > 1000:
        raise ValueError("Explicit bounded binding roster required")
    groups, expected, received = {}, {}, {}
    for b in bindings:
        validate_binding(b)
        key = (instrument_id(b.instrument), b.venue)
        if key in expected:
            raise ValueError("Duplicate venue/instrument binding")
        expected[key] = b
        groups.setdefault(key[0], []).append(b)
    for item in observations:
        key = (instrument_id(item.binding.instrument), item.binding.venue)
        if key not in expected or expected[key] != item.binding or key in received:
            raise ValueError("Foreign, changed or duplicate observation")
        if (
            item.quote.venue != item.binding.venue
            or item.quote.venue_symbol != item.binding.native_symbol
            or item.quote.instrument != item.binding.instrument
        ):
            raise ValueError("Quote differs from its explicit binding")
        received[key] = item
    result, expiries, available, pairs_count = [], [], 0, 0
    for ident, roster in groups.items():
        rows, entries, comparisons = [], [], []
        for b in roster:
            d = received.get((ident, b.venue), unavailable(b))
            q = d.quote
            m = quote_metrics(q, as_of=as_of, max_age_ms=max_age_ms)
            reason = d.decode_error or m["reason"]
            status = "NOT_AVAILABLE" if reason else m["status"]
            if status == "AVAILABLE":
                available += 1
                expiries.append(q.observed_at + timedelta(milliseconds=max_age_ms))
            rows.append(
                {
                    "venue": b.venue,
                    "native_symbol": b.native_symbol,
                    "bid": exact(q.bid),
                    "ask": exact(q.ask),
                    "bid_size_base": exact(q.bid_size_base),
                    "ask_size_base": exact(q.ask_size_base),
                    "observed_at_utc": iso(q.observed_at),
                    "received_at_utc": iso(q.received_at),
                    "observer_clock_id": q.observer_clock_id or None,
                    "timestamp_kind": q.timestamp_kind,
                    "book_state": q.book_state,
                    "status": status,
                    "reason": reason,
                    "mid": format(Decimal(m["mid"]), "f")
                    if status == "AVAILABLE"
                    else None,
                    "spread_bps": m["spread_bps"] if status == "AVAILABLE" else None,
                    "event_age_ms": m["event_age_ms"],
                    "source": {
                        "endpoint_id": ENDPOINTS[b.venue],
                        "payload_sha256": d.payload_sha256,
                        "mapping_id": b.mapping_id,
                        "mapping_sha256": b.mapping_sha256,
                        "identity_evidence": d.identity_evidence,
                        "native_sequence": d.native_sequence,
                        "timestamp_note": d.timestamp_note,
                    },
                }
            )
            entries.append(d)
        for a in entries:
            for b in entries:
                if a.binding.venue == b.binding.venue:
                    continue
                metric = compare_quotes(
                    a.quote,
                    b.quote,
                    as_of=as_of,
                    max_age_ms=max_age_ms,
                    max_skew_ms=max_skew_ms,
                )
                if a.decode_error or b.decode_error:
                    metric = {
                        **metric,
                        "status": "NOT_AVAILABLE",
                        "reason": "QUOTE_UNAVAILABLE",
                    }
                comparisons.append(
                    {
                        "reference_venue": a.binding.venue,
                        "other_venue": b.binding.venue,
                        **{
                            k: (
                                format(Decimal(metric[k]), "f")
                                if k not in ("status", "reason")
                                and metric[k] is not None
                                else metric[k]
                            )
                            for k in PAIR_FIELDS
                        },
                    }
                )
        pairs_count += len(comparisons)
        if pairs_count > 10_000:
            raise ValueError("Publication pair budget exceeded; never truncate")
        instrument = roster[0].instrument
        result.append(
            {
                "instrument_id": ident,
                "instrument": asdict(instrument),
                "default_reference": roster[0].venue,
                "rows": rows,
                "comparisons": comparisons,
            }
        )
    snapshot = {
        "schema_version": "1.0.0",
        "product": "MarketVenueComparison",
        "authority": "OBSERVATIONAL_TELEMETRY",
        "evidence_kind": evidence_kind,
        "generated_at_utc": iso(as_of),
        "valid_until_utc": iso(min(expiries)) if expiries else None,
        "execution_authority": False,
        "costs_funding_fx_included": False,
        "quality_policy": {"max_age_ms": max_age_ms, "max_skew_ms": max_skew_ms},
        "source_counts": {
            "expected": len(bindings),
            "supplied": sum(d.payload_sha256 is not None for d in received.values()),
            "available": available,
        },
        "groups": result,
    }
    if not validate_publication(snapshot):
        raise ValueError("Publication failed its closed presentation contract")
    return snapshot
