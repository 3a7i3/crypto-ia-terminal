"""One-shot passive projection of an existing LMI sidecar; no engine imports."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from observability.market_microstructure_artifact import read_document
from observability.market_microstructure_contract import (
    DETAIL_FIELDS, MAX_BYTES, MAX_SYMBOLS, ROW_KEYS, STATES, finite, symbol, unsigned,
    validate_microstructure_snapshot,
)

DEFAULT_SOURCE = Path("databases/trade_analysis/lmi_live_state.json")
DEFAULT_PATH = Path("databases/market_microstructure_snapshot.json")


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _source_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_SOURCE_TIMESTAMP")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("INVALID_SOURCE_TIMESTAMP")
    return parsed.timestamp()


def _population(value):
    if not isinstance(value, list) or len(value) > MAX_SYMBOLS or not all(symbol(s) for s in value) or len(set(value)) != len(value):
        raise ValueError("INVALID_POPULATION")
    return value


def _metric(doc, key):
    value = doc.get(key)
    if value is not None and not finite(value):
        raise ValueError("INVALID_METRIC")
    return value


def _detail(st, source_time):
    result = {}
    for name, fields in DETAIL_FIELDS.items():
        raw = st.get(name)
        if raw is None:
            result[name] = None
            continue
        if not isinstance(raw, dict):
            raise ValueError("INVALID_METRIC_GROUP")
        group = {key: raw.get(key) for key in fields}
        if name != "state_components":
            stamp = raw.get("timestamp_ms")
            if stamp is not None and (not unsigned(stamp) or stamp / 1000 > source_time):
                raise ValueError("INVALID_OBSERVATION_TIMESTAMP")
            group["observed_at_utc"] = None if stamp is None else iso(stamp / 1000)
        if name == "liquidity":
            # The unchanged engine also publishes fallback zeros before any book.
            group["observation_evidence"] = "SOURCE_VALUES_ONLY"
        result[name] = group
    return result


def build_microstructure_snapshot(source: Path = DEFAULT_SOURCE, *, now_fn=time.time):
    doc, raw = read_document(Path(source), limit=524_288)
    now = float(now_fn())
    source_time = _source_timestamp(doc.get("updated_at"))
    if not finite(now) or source_time < 0 or source_time > now:
        raise ValueError("FUTURE_SOURCE_TIMESTAMP")
    requested = _population(doc.get("watchlist"))
    streamable = _population(doc.get("stream_watchlist"))
    if not set(streamable) <= set(requested):
        raise ValueError("INCONSISTENT_POPULATION")
    states, coverage = doc.get("symbols"), doc.get("coverage")
    if not isinstance(states, dict) or not isinstance(coverage, dict) or set(coverage) != set(requested):
        raise ValueError("INVALID_SOURCE_COVERAGE")
    rows = []
    for sym in requested:
        cov = coverage[sym]
        if not isinstance(cov, dict) or cov.get("status") not in {"LIVE", "STALE", "UNAVAILABLE"} or cov.get("stream_requested") is not (sym in streamable):
            raise ValueError("INVALID_SOURCE_COVERAGE")
        row = dict.fromkeys(ROW_KEYS | {"detail"})
        row.update(symbol=sym, stream_requested=sym in streamable)
        st = states.get(sym)
        if cov["status"] == "UNAVAILABLE" or st is None:
            row.update(availability="UNAVAILABLE", unavailable_reason="NO_OBSERVATION" if cov.get("reason") in {None, "no_pressure_field"} else "SOURCE_UNAVAILABLE")
        else:
            if not isinstance(st, dict) or st.get("symbol") != sym or sym not in streamable:
                raise ValueError("INVALID_SYMBOL_STATE")
            row["availability"] = "OBSERVED"
            timestamp = st.get("timestamp_ms")
            if timestamp is not None:
                if not unsigned(timestamp) or timestamp / 1000 > source_time:
                    raise ValueError("INVALID_OBSERVATION_TIMESTAMP")
                row["observed_at_utc"] = iso(timestamp / 1000)
            state = st.get("state")
            if state is not None and state not in STATES:
                raise ValueError("INVALID_STATE")
            row.update(state=state, state_confidence=_metric(st, "state_confidence"), price=_metric(st, "price"), price_change_bps=_metric(st, "price_change_bps"))
            row["detail"] = _detail(st, source_time)
            flow, resistance = st.get("flow") or {}, st.get("resistance") or {}
            if not isinstance(flow, dict) or not isinstance(resistance, dict):
                raise ValueError("INVALID_METRIC_GROUP")
            row["flow_window_ms"] = flow.get("window_ms")
            ratio = _metric(flow, "pressure_ratio")
            if ratio is not None:
                row["buy_pressure_pct"] = ratio * 100
                row["sell_pressure_pct"] = (1 - ratio) * 100
            buy, sell = _metric(flow, "buy_volume_usd"), _metric(flow, "sell_volume_usd")
            row.update(buy_flow_usd=buy, sell_flow_usd=sell, total_flow_usd=None if buy is None or sell is None else buy + sell,
                       resistance=_metric(resistance, "resistance_score"), fragility=_metric(resistance, "fragility_score"))
            confidence = row["state_confidence"]
            row["notable"] = None if state is None or confidence is None else state != "quiet" and confidence >= 0.6
        rows.append(row)
    meta = doc.get("contract_meta", {})
    if not isinstance(meta, dict):
        raise ValueError("INVALID_UNIT_PROVENANCE")
    unit_source = meta.get("source", "unknown")
    if unit_source == "n/a":
        unit_source = "unknown"  # no contractSize evidence, never claim reliable units
    degraded = meta.get("degraded_symbols")
    if degraded is not None and (not isinstance(degraded, list) or not all(symbol(s) for s in degraded)):
        raise ValueError("INVALID_UNIT_PROVENANCE")
    stats = doc.get("stats", {})
    if not isinstance(stats, dict):
        raise ValueError("INVALID_SOURCE_STATS")
    result = {
        "schema_version": "1.1.0", "product": "MarketMicrostructureSnapshot",
        "domain": "market_microstructure", "authority": "OBSERVATIONAL_TELEMETRY", "mode": "READ_ONLY",
        "generated_at_utc": iso(now), "source_updated_at_utc": iso(source_time),
        "source_artifact_sha256": hashlib.sha256(raw).hexdigest(), "exchange": doc.get("exchange"),
        "unit_contract_source": unit_source, "unit_contract_degraded": None if degraded is None else bool(degraded),
        "pressure_field_count": stats.get("events"),
        "coverage": {"requested": len(requested), "streamable": len(streamable),
                     "observed": sum(r["availability"] == "OBSERVED" for r in rows),
                     "unavailable": sum(r["availability"] == "UNAVAILABLE" for r in rows)},
        "rows": rows,
    }
    if not validate_microstructure_snapshot(result):
        raise ValueError("INVALID_PROJECTION")
    return result


def write_microstructure_snapshot(source=DEFAULT_SOURCE, path=DEFAULT_PATH, *, now_fn=time.time):
    source, path = Path(source), Path(path)
    if source.resolve() == path.resolve():
        raise ValueError("SOURCE_OUTPUT_COLLISION")
    doc = build_microstructure_snapshot(source, now_fn=now_fn)
    raw = json.dumps(doc, allow_nan=False, sort_keys=True).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("OUTPUT_LIMIT")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    try:
        write_microstructure_snapshot(args.source, args.out)
    except (OSError, ValueError, TypeError, OverflowError):
        print("MICROSTRUCTURE_PUBLICATION_FAILED")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
