"""Closed passive LMI presentation contract; no market/exchange I/O."""
from __future__ import annotations

import math
import re
from datetime import datetime

MAX_BYTES = 262_144
MAX_SYMBOLS = 100
STALE_AFTER_S = 15.0
STATES = {
    "accumulation", "distribution", "absorption_buy", "absorption_sell",
    "fragility_up", "fragility_down", "compression", "expansion",
    "exhaustion_buy", "exhaustion_sell", "vacuum_up", "vacuum_down", "conflict", "quiet",
}
BASE_KEYS = {
    "schema_version", "product", "domain", "authority", "mode", "generated_at_utc",
    "source_updated_at_utc", "source_artifact_sha256", "exchange", "unit_contract_source",
    "unit_contract_degraded", "pressure_field_count", "coverage", "rows",
}
ROW_KEYS = {
    "symbol", "stream_requested", "availability", "unavailable_reason", "observed_at_utc",
    "state", "state_confidence", "price", "price_change_bps", "buy_pressure_pct",
    "sell_pressure_pct", "buy_flow_usd", "sell_flow_usd", "total_flow_usd",
    "resistance", "fragility", "flow_window_ms", "notable",
}
METRICS = {"state_confidence", "price", "price_change_bps", "buy_pressure_pct",
           "sell_pressure_pct", "buy_flow_usd", "sell_flow_usd", "total_flow_usd", "resistance", "fragility"}


def exact(value, keys):
    return isinstance(value, dict) and set(value) == keys


def unsigned(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 9_007_199_254_740_991


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def utc_seconds(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError):
        return None


def symbol(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9_/-]{0,63}", value) is not None


def _validate(doc, transport):
    temporal = {"source_age_s", "freshness_classification", "read_at_utc"}
    if not exact(doc, BASE_KEYS | (temporal if transport else set())):
        return False
    for key, value in {"schema_version": "1.0.0", "product": "MarketMicrostructureSnapshot",
                       "domain": "market_microstructure", "authority": "OBSERVATIONAL_TELEMETRY", "mode": "READ_ONLY"}.items():
        if doc[key] != value:
            return False
    source, generated = utc_seconds(doc["source_updated_at_utc"]), utc_seconds(doc["generated_at_utc"])
    if source is None or generated is None or not 0 <= source <= generated:
        return False
    if not isinstance(doc["source_artifact_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", doc["source_artifact_sha256"]):
        return False
    if doc["exchange"] not in {"mexc", "binance"}:
        return False
    if doc["unit_contract_source"] not in {"api", "fallback", "mixed", "unknown"}:
        return False
    if doc["unit_contract_degraded"] is not None and not isinstance(doc["unit_contract_degraded"], bool):
        return False
    if doc["pressure_field_count"] is not None and not unsigned(doc["pressure_field_count"]):
        return False
    rows = doc["rows"]
    if not isinstance(rows, list) or len(rows) > MAX_SYMBOLS:
        return False
    c = doc["coverage"]
    if not exact(c, {"requested", "streamable", "observed", "unavailable"}) or not all(unsigned(v) for v in c.values()):
        return False
    if c["requested"] != len(rows) or c["observed"] + c["unavailable"] != len(rows):
        return False
    if len({r["symbol"] for r in rows}) != len(rows):
        return False
    observed_count = streamable_count = 0
    for row in rows:
        keys = ROW_KEYS | ({"observation_age_s", "freshness_classification"} if transport else set())
        if not exact(row, keys) or not symbol(row["symbol"]) or not isinstance(row["stream_requested"], bool):
            return False
        streamable_count += int(row["stream_requested"])
        if row["availability"] not in {"OBSERVED", "UNAVAILABLE"}:
            return False
        if row["availability"] == "UNAVAILABLE":
            if row["unavailable_reason"] not in {"SOURCE_UNAVAILABLE", "NO_OBSERVATION"}:
                return False
            if any(row[k] is not None for k in ROW_KEYS - {"symbol", "stream_requested", "availability", "unavailable_reason"}):
                return False
        else:
            observed_count += 1
            if not row["stream_requested"] or row["unavailable_reason"] is not None:
                return False
            stamp = utc_seconds(row["observed_at_utc"])
            if row["observed_at_utc"] is not None and (stamp is None or not 0 <= stamp <= source):
                return False
            if row["state"] is not None and row["state"] not in STATES:
                return False
            if row["flow_window_ms"] is not None and not unsigned(row["flow_window_ms"]):
                return False
            for key in METRICS:
                value = row[key]
                if value is None:
                    continue
                if not finite(value):
                    return False
                if key != "price_change_bps" and value < 0:
                    return False
                if key in {"buy_pressure_pct", "sell_pressure_pct"} and value > 100:
                    return False
                if key in {"state_confidence", "fragility"} and value > 1:
                    return False
            buy, sell = row["buy_pressure_pct"], row["sell_pressure_pct"]
            if (buy is None) != (sell is None) or (buy is not None and abs(buy + sell - 100) > 1e-8):
                return False
            total, b, s = row["total_flow_usd"], row["buy_flow_usd"], row["sell_flow_usd"]
            if b is None or s is None:
                if total is not None:
                    return False
            elif total is None or not math.isclose(total, b + s, rel_tol=1e-12, abs_tol=1e-8):
                return False
            expected = None if row["state"] is None or row["state_confidence"] is None else row["state"] != "quiet" and row["state_confidence"] >= 0.6
            if row["notable"] is not expected:
                return False
        if transport:
            read = utc_seconds(doc["read_at_utc"])
            if read is None or read < generated:
                return False
            expected_age = None if row["observed_at_utc"] is None else read - utc_seconds(row["observed_at_utc"])
            age = row["observation_age_s"]
            if expected_age is None:
                if age is not None:
                    return False
            elif not finite(age) or not math.isclose(age, expected_age, rel_tol=1e-12, abs_tol=1e-6):
                return False
            expected_class = "NOT_AVAILABLE" if row["availability"] == "UNAVAILABLE" else "UNKNOWN" if age is None else "STALE" if age > STALE_AFTER_S or read - source > STALE_AFTER_S else "FRESH"
            if row["freshness_classification"] != expected_class:
                return False
    if observed_count != c["observed"] or streamable_count != c["streamable"]:
        return False
    if transport:
        read = utc_seconds(doc["read_at_utc"])
        age = doc["source_age_s"]
        if read is None or read < generated or not finite(age) or not math.isclose(age, read - source, rel_tol=1e-12, abs_tol=1e-6):
            return False
        if doc["freshness_classification"] != ("STALE" if age > STALE_AFTER_S else "FRESH"):
            return False
    return True


def validate_microstructure_snapshot(doc, *, transport=False):
    try:
        return _validate(doc, transport)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
