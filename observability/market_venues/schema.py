"""Closed presentation schema. Validation does not compute prices or comparisons."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from .models import ENDPOINTS

TOP = {
    "schema_version",
    "product",
    "authority",
    "evidence_kind",
    "generated_at_utc",
    "valid_until_utc",
    "execution_authority",
    "costs_funding_fx_included",
    "quality_policy",
    "source_counts",
    "groups",
}
ROW = {
    "venue",
    "native_symbol",
    "bid",
    "ask",
    "bid_size_base",
    "ask_size_base",
    "observed_at_utc",
    "received_at_utc",
    "observer_clock_id",
    "timestamp_kind",
    "book_state",
    "status",
    "reason",
    "mid",
    "spread_bps",
    "event_age_ms",
    "source",
}
SOURCE = {
    "endpoint_id",
    "payload_sha256",
    "mapping_id",
    "mapping_sha256",
    "identity_evidence",
    "native_sequence",
    "timestamp_note",
}
INSTRUMENT = {
    "base_asset_id",
    "quote_asset_id",
    "market_kind",
    "settlement_asset_id",
    "contract_identity",
}
PAIR_NUMBERS = {
    "event_skew_ms",
    "mid_basis_bps",
    "buy_reference_sell_other_gross_bps",
    "buy_other_sell_reference_gross_bps",
    "buy_reference_sell_other_top_size_base",
    "buy_other_sell_reference_top_size_base",
}
PAIR = {"reference_venue", "other_venue", "status", "reason"} | PAIR_NUMBERS
GROUP = {"instrument_id", "instrument", "default_reference", "rows", "comparisons"}


def keys(value, expected):
    return isinstance(value, dict) and set(value) == expected


def stamp(value):
    if not isinstance(value, str) or not value.endswith("Z") or len(value) > 40:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def text(value, pattern=r"[A-Za-z0-9@.:/_=-]{1,120}"):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def decimal(value, *, positive=False, signed=False):
    if (
        not isinstance(value, str)
        or len(value) > 90
        or not re.fullmatch(r"-?\d+(?:\.\d+)?", value)
    ):
        return False
    try:
        n = Decimal(value)
        return n.is_finite() and (signed or n >= 0) and (not positive or n > 0)
    except InvalidOperation:
        return False


def state(record):
    return (record["status"] == "AVAILABLE" and record["reason"] is None) or (
        record["status"] == "NOT_AVAILABLE"
        and text(record["reason"], r"[A-Z][A-Z0-9_]{1,79}")
    )


def validate_publication(doc):
    try:
        return _validate(doc)
    except (KeyError, TypeError, ValueError, OverflowError, InvalidOperation):
        return False


def _validate(doc):
    if (
        not keys(doc, TOP)
        or doc["schema_version"] != "1.0.0"
        or doc["product"] != "MarketVenueComparison"
    ):
        return False
    if doc["authority"] != "OBSERVATIONAL_TELEMETRY" or doc["evidence_kind"] not in (
        "OBSERVATION",
        "SYNTHETIC",
    ):
        return False
    if (
        doc["execution_authority"] is not False
        or doc["costs_funding_fx_included"] is not False
    ):
        return False
    generated = stamp(doc["generated_at_utc"])
    expiry = stamp(doc["valid_until_utc"])
    if not generated or (
        doc["valid_until_utc"] is not None and (expiry is None or expiry < generated)
    ):
        return False
    if not keys(doc["quality_policy"], {"max_age_ms", "max_skew_ms"}) or not all(
        integer(x) for x in doc["quality_policy"].values()
    ):
        return False
    if not keys(doc["source_counts"], {"expected", "supplied", "available"}) or not all(
        integer(x) for x in doc["source_counts"].values()
    ):
        return False
    if not isinstance(doc["groups"], list) or not 1 <= len(doc["groups"]) <= 1000:
        return False
    total = supplied = available = pair_count = 0
    seen_groups, expected_expiries = set(), []
    from datetime import timedelta

    for group in doc["groups"]:
        if not keys(group, GROUP) or not keys(group["instrument"], INSTRUMENT):
            return False
        ins = group["instrument"]
        if not all(
            text(v) and v.upper() not in ("UNKNOWN", "UNRESOLVED", "NOT_AVAILABLE")
            for v in ins.values()
        ):
            return False
        if ins["market_kind"] not in (
            "SPOT",
            "PERPETUAL_LINEAR",
            "PERPETUAL_INVERSE",
            "FUTURE_LINEAR",
            "FUTURE_INVERSE",
        ) or (ins["market_kind"] == "SPOT" and ins["contract_identity"] != "SPOT"):
            return False
        ident = hashlib.sha256(json.dumps(ins, sort_keys=True).encode()).hexdigest()[
            :24
        ]
        if group["instrument_id"] != ident or ident in seen_groups:
            return False
        seen_groups.add(ident)
        if (
            not isinstance(group["rows"], list)
            or not 1 <= len(group["rows"]) <= 50
            or not isinstance(group["comparisons"], list)
        ):
            return False
        venues = set()
        for row in group["rows"]:
            if (
                not keys(row, ROW)
                or row["venue"] not in ENDPOINTS
                or row["venue"] in venues
                or not state(row)
            ):
                return False
            venues.add(row["venue"])
            if not text(row["native_symbol"]) or (
                row["observer_clock_id"] is not None
                and not text(row["observer_clock_id"])
            ):
                return False
            if row["timestamp_kind"] not in (
                "UNRESOLVED",
                "BOOK_PUBLICATION",
                "MATCHING_ENGINE",
            ) or row["book_state"] not in ("UNRESOLVED", "SNAPSHOT", "SYNCHRONIZED"):
                return False
            for field in (
                "bid",
                "ask",
                "bid_size_base",
                "ask_size_base",
                "mid",
                "spread_bps",
                "event_age_ms",
            ):
                if row[field] is not None and not decimal(
                    row[field],
                    positive=field
                    in ("bid", "ask", "bid_size_base", "ask_size_base", "mid"),
                ):
                    return False
            for field in ("observed_at_utc", "received_at_utc"):
                if row[field] is not None and stamp(row[field]) is None:
                    return False
            src = row["source"]
            if not keys(src, SOURCE) or src["endpoint_id"] != ENDPOINTS[row["venue"]]:
                return False
            if not text(src["mapping_id"]) or not text(
                src["mapping_sha256"], r"[a-f0-9]{64}"
            ):
                return False
            if src["payload_sha256"] is not None and not text(
                src["payload_sha256"], r"[a-f0-9]{64}"
            ):
                return False
            if src["identity_evidence"] not in (
                "REQUEST_CONTEXT",
                "NATIVE_SYMBOL_ECHO",
            ) or not text(src["timestamp_note"]):
                return False
            if src["native_sequence"] is not None and not text(
                src["native_sequence"], r"\d{1,30}"
            ):
                return False
            total += 1
            supplied += src["payload_sha256"] is not None
            if row["status"] == "AVAILABLE":
                if any(
                    row[k] is None
                    for k in (
                        "bid",
                        "ask",
                        "mid",
                        "spread_bps",
                        "event_age_ms",
                        "observed_at_utc",
                        "received_at_utc",
                        "observer_clock_id",
                    )
                ):
                    return False
                observed, received = (
                    stamp(row["observed_at_utc"]),
                    stamp(row["received_at_utc"]),
                )
                if (
                    not observed <= received <= generated
                    or row["timestamp_kind"] == "UNRESOLVED"
                    or row["book_state"] == "UNRESOLVED"
                ):
                    return False
                if (
                    Decimal(row["ask"]) < Decimal(row["bid"])
                    or Decimal(row["event_age_ms"])
                    > doc["quality_policy"]["max_age_ms"]
                    or src["payload_sha256"] is None
                ):
                    return False
                expected_expiries.append(
                    observed
                    + timedelta(milliseconds=doc["quality_policy"]["max_age_ms"])
                )
                available += 1
            elif row["mid"] is not None or row["spread_bps"] is not None:
                return False
        if group["default_reference"] not in venues:
            return False
        expected_pairs = {(a, b) for a in venues for b in venues if a != b}
        pairs = set()
        statuses = {r["venue"]: r["status"] for r in group["rows"]}
        row_by_venue = {r["venue"]: r for r in group["rows"]}
        for pair in group["comparisons"]:
            if not keys(pair, PAIR) or not state(pair):
                return False
            key = (pair["reference_venue"], pair["other_venue"])
            if key not in expected_pairs or key in pairs:
                return False
            pairs.add(key)
            for field in PAIR_NUMBERS:
                if pair[field] is not None and not decimal(
                    pair[field], signed=field.endswith("_bps")
                ):
                    return False
            if pair["status"] == "AVAILABLE":
                if (
                    statuses[key[0]] != "AVAILABLE"
                    or statuses[key[1]] != "AVAILABLE"
                    or any(
                        pair[k] is None
                        for k in (
                            "mid_basis_bps",
                            "buy_reference_sell_other_gross_bps",
                            "buy_other_sell_reference_gross_bps",
                            "event_skew_ms",
                        )
                    )
                ):
                    return False
                left, right = row_by_venue[key[0]], row_by_venue[key[1]]
                if (
                    left["observer_clock_id"] != right["observer_clock_id"]
                    or left["timestamp_kind"] != right["timestamp_kind"]
                ):
                    return False
                delta = abs(
                    stamp(left["observed_at_utc"]) - stamp(right["observed_at_utc"])
                )
                skew = (
                    Decimal(
                        (delta.days * 86400 + delta.seconds) * 1000000
                        + delta.microseconds
                    )
                    / 1000
                )
                if (
                    Decimal(pair["event_skew_ms"]) != skew
                    or skew > doc["quality_policy"]["max_skew_ms"]
                ):
                    return False
            elif any(pair[k] is not None for k in PAIR_NUMBERS - {"event_skew_ms"}):
                return False
        if pairs != expected_pairs:
            return False
        pair_count += len(pairs)
    if total > 1000 or pair_count > 10_000:
        return False
    return doc["source_counts"] == {
        "expected": total,
        "supplied": supplied,
        "available": available,
    } and expiry == (min(expected_expiries) if expected_expiries else None)
