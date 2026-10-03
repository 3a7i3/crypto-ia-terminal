"""Offline passive capture of explicitly selected sources; no runtime imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from observability.burn_in_status_contract import validate_burn_in_status_snapshot
from observability.event_center_artifact import read_bytes, strict_json
from observability.event_center_contract import (
    FORMATS, KINDS, MAX_BYTES, MAX_EVENTS_PER_SOURCE, MAX_RECORDS,
    SOURCE_IDS, SOURCE_KEYS, canonical_time, event_order, finite, utc_seconds,
    validate_event_center,
)


def _event(source_id, record, kind, severity, timestamp, *, identity_ref, symbol=None, sequence=None):
    identity = json.dumps([source_id, identity_ref, record if source_id != "ppl_lifecycles" else None, kind, timestamp, symbol, sequence], allow_nan=False)
    return {
        "event_id": hashlib.sha256(identity.encode()).hexdigest(),
        "source_id": source_id, "source_record": record, "kind": kind,
        "severity": severity, "occurred_at_utc": timestamp,
        "time_status": "UNKNOWN" if timestamp is None else "PRESENT",
        "symbol": symbol, "sequence": sequence,
    }


def _alert_events(raw, source_id):
    if raw and not raw.endswith(b"\n"):
        raise ValueError("INCOMPLETE_RECORD")
    lines = raw.splitlines()
    if len(lines) > MAX_RECORDS:
        raise OverflowError("OUTPUT_LIMIT")
    events, excluded = [], 0
    for record, line in enumerate(lines, 1):
        obj = strict_json(line)
        if not isinstance(obj, dict):
            raise ValueError("INVALID_RECORD")
        if source_id == "p12_alerts":
            if not {"rule", "severity", "ts", "message", "value", "threshold"} <= set(obj):
                raise ValueError("INVALID_RECORD")
            if not finite(obj["ts"]) or not finite(obj["value"]) or not finite(obj["threshold"]):
                raise ValueError("INVALID_RECORD")
            timestamp = datetime.fromtimestamp(obj["ts"], timezone.utc).isoformat().replace("+00:00", "Z")
            kind = obj["rule"] if obj["rule"] in KINDS - {"POSITION_OPENED", "POSITION_CLOSED", "POSITION_UNRESOLVED"} else "OTHER_ALERT"
            severity = obj["severity"]
        else:
            alert = obj.get("alert", obj)
            if not isinstance(alert, dict) or not {"type", "severity", "timestamp"} <= set(alert):
                # Nested legacy audit carries timestamp in its outer envelope.
                if not isinstance(alert, dict) or not {"type", "severity"} <= set(alert) or "timestamp" not in obj:
                    raise ValueError("INVALID_RECORD")
            if obj.get("correction") is True:
                excluded += 1
                continue
            if "correction" in obj:
                raise ValueError("INVALID_RECORD")
            raw_time = obj.get("timestamp", alert.get("timestamp"))
            if not isinstance(alert["type"], str) or not isinstance(raw_time, str) or "T" not in raw_time:
                raise ValueError("INVALID_TIMESTAMP")
            datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            timestamp = canonical_time(raw_time)
            kind = "DRAWDOWN" if alert["type"] == "drawdown" else "OTHER_ALERT"
            severity = alert["severity"].upper() if isinstance(alert["severity"], str) else None
        if severity not in {"INFO", "WARNING", "CRITICAL"}:
            raise ValueError("INVALID_SEVERITY")
        events.append(_event(source_id, record, kind, severity, timestamp, identity_ref=hashlib.sha256(line).hexdigest()))
    return events, len(lines), excluded, None, None


def _ppl_events(raw):
    doc = strict_json(raw)
    if not validate_burn_in_status_snapshot(doc):
        raise ValueError("INVALID_BURN_IN_PROJECTION")
    generated = canonical_time(doc["generated_at_utc"])
    if generated is None:
        raise ValueError("INVALID_TIMESTAMP")
    events = []
    for row in doc["lifecycle_history"]:
        events.append(_event("ppl_lifecycles", len(events) + 1, "POSITION_OPENED", "INFO",
                             canonical_time(row["opened_at_utc"]), identity_ref=doc["paper_epoch_id"] + ":" + row["trade_id"], symbol=row["symbol"], sequence=row["opened_sequence"]))
        if row["status"] != "OPEN":
            kind = "POSITION_" + row["status"]
            events.append(_event("ppl_lifecycles", len(events) + 1, kind,
                                 "WARNING" if kind == "POSITION_UNRESOLVED" else "INFO",
                                 canonical_time(row["terminal_at_utc"]), identity_ref=doc["paper_epoch_id"] + ":" + row["trade_id"], symbol=row["symbol"], sequence=row["terminal_sequence"]))
    if len(events) > MAX_RECORDS or len({event["sequence"] for event in events}) != len(events):
        raise ValueError("INVALID_LIFECYCLE_SEQUENCE")
    return events, len(events), 0, generated, doc["paper_epoch_id"]


def build_event_center(*, generated_at_utc, p12_alerts=None, supervision_alerts=None, ppl_lifecycles=None):
    """Capture only explicit paths. No default source discovery or producer startup."""
    generated = utc_seconds(generated_at_utc)
    if generated is None:
        raise ValueError("INVALID_GENERATION_TIME")
    sources, published = [], []
    for index, path in enumerate((p12_alerts, supervision_alerts, ppl_lifecycles)):
        source_id = SOURCE_IDS[index]
        source = dict.fromkeys(SOURCE_KEYS)
        source.update(source_id=source_id, format=FORMATS[index], status="NOT_CONFIGURED")
        if path is not None:
            try:
                raw = read_bytes(path)
                result = _ppl_events(raw) if index == 2 else _alert_events(raw, source_id)
                events, records, excluded, source_generated, epoch = result
                if source_generated is not None and utc_seconds(source_generated) > generated:
                    raise ValueError("FUTURE_SOURCE")
                if any(event["occurred_at_utc"] is not None and utc_seconds(event["occurred_at_utc"]) > generated for event in events):
                    raise ValueError("FUTURE_EVENT")
                selected = sorted(events, key=event_order)[:MAX_EVENTS_PER_SOURCE]
                source.update(status="PRESENT", source_sha256=hashlib.sha256(raw).hexdigest(),
                              records_observed=records, events_observed=len(events), excluded_records=excluded,
                              published_count=len(selected), undated_count=sum(e["time_status"] == "UNKNOWN" for e in events),
                              truncated=len(selected) < len(events), source_generated_at_utc=source_generated, paper_epoch_id=epoch)
                # Validate each source before retaining its rows (all-or-nothing source).
                trial_sources = [dict.fromkeys(SOURCE_KEYS) for _ in SOURCE_IDS]
                for i, item in enumerate(trial_sources):
                    item.update(source_id=SOURCE_IDS[i], format=FORMATS[i], status="NOT_CONFIGURED")
                trial_sources[index] = source
                if not validate_event_center(_document(generated_at_utc, trial_sources, selected)):
                    raise ValueError("INVALID_SOURCE_PROJECTION")
                published.extend(selected)
            except FileNotFoundError:
                source["status"] = "MISSING"
            except OverflowError:
                source["status"] = "OUTPUT_LIMIT"
            except OSError:
                source["status"] = "READ_ERROR"
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                source["status"] = "INVALID"
            if source["status"] != "PRESENT":
                source = {key: source[key] if key in {"source_id", "format", "status"} else None for key in SOURCE_KEYS}
        sources.append(source)
    doc = _document(generated_at_utc, sources, sorted(published, key=event_order))
    if not validate_event_center(doc):
        raise ValueError("INVALID_EVENT_CENTER")
    return doc


def _document(generated_at_utc, sources, events):
    return {"schema_version": "1.0.0", "product": "EventCenterSnapshot", "domain": "event_center",
            "authority": "OBSERVATIONAL_PRESENTATION", "mode": "READ_ONLY",
            "generated_at_utc": generated_at_utc, "sources": sources, "events": events,
            "order": "SOURCE_THEN_TIME_DESC_UNDATED_LAST"}


def publish_event_center(path, **kwargs):
    """One atomic presentation write; source files stay untouched."""
    path = Path(path)
    inputs = [kwargs.get(key) for key in SOURCE_IDS]
    if any(item is not None and Path(item).resolve() == path.resolve() for item in inputs):
        raise ValueError("OUTPUT_IS_SOURCE")
    doc = build_event_center(**kwargs)
    raw = json.dumps(doc, sort_keys=True, allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("OUTPUT_LIMIT")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".events-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--generated-at-utc", required=True)
    for key in SOURCE_IDS:
        parser.add_argument("--" + key.replace("_", "-"), type=Path)
    args = vars(parser.parse_args())
    publish_event_center(args.pop("out"), **args)


if __name__ == "__main__":
    main()
