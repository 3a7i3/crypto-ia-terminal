"""Fail-closed event capture and transport, never a running machine."""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from observability.event_center_contract import MAX_BYTES, validate_event_center
from observability.event_center_snapshot import build_event_center, publish_event_center, _ppl_events
from observability.operator_api import app as api
from observability.operator_api.event_center_reader import EventCenterReader
from tests.cross_stack.generate_burn_in_fixture import NOW
from tests.cross_stack.generate_event_center_fixture import generate

STAMP = "2027-01-15T08:06:40Z"


def alert(ts=NOW - 10):
    return json.dumps({"rule": "MEMORY", "severity": "CRITICAL", "ts": ts, "message": "secret", "value": 91, "threshold": 90}) + "\n"


def test_real_chain_preserves_sources_and_excludes_secrets(tmp_path):
    result = generate(tmp_path)
    body = result["body"]
    assert result["http_status"] == 200
    assert validate_event_center(body, transport=True)
    assert len(body["events"]) == 8
    assert [s["status"] for s in body["sources"]] == ["PRESENT"] * 3
    assert [s["freshness_classification"] for s in body["sources"]] == ["UNKNOWN", "UNKNOWN", "FRESH"]
    assert body["sources"][1]["undated_count"] == 1
    assert body["sources"][1]["excluded_records"] == 1
    assert {e["symbol"] for e in body["events"] if e["symbol"]} == {"BTC/USDT", "ETH/USDT", "SOL/USDT"}
    assert "secret" not in json.dumps(body).lower()
    root = tmp_path / "_producer" / "L_events"
    raw = (root / "alerts.jsonl").read_bytes()
    assert body["sources"][0]["source_sha256"] == hashlib.sha256(raw).hexdigest()
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and p.name != "event_center_snapshot.json"}
    publish_event_center(root / "event_center_snapshot.json", generated_at_utc=STAMP, p12_alerts=root / "alerts.jsonl")
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("raw", [b'{', b'{}\n', alert().rstrip().encode(), b'{"a":1,"a":2}\n',
                                alert().replace('91', 'NaN').encode(), alert().replace('91', '1e400').encode(),
                                alert().encode() + b'bad\n', alert(NOW + 1).encode()])
def test_invalid_source_never_exports_partial_rows(tmp_path, raw):
    path = tmp_path / "alerts"
    path.write_bytes(raw)
    doc = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    assert doc["sources"][0]["status"] == "INVALID"
    assert doc["sources"][0]["events_observed"] is None
    assert doc["events"] == []


def test_empty_missing_limit_and_symlink_are_distinct(tmp_path):
    path = tmp_path / "alerts"
    doc = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    assert [s["status"] for s in doc["sources"]] == ["MISSING", "NOT_CONFIGURED", "NOT_CONFIGURED"]
    path.write_bytes(b"")
    doc = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    assert doc["sources"][0]["status"] == "PRESENT" and doc["sources"][0]["events_observed"] == 0
    path.write_bytes(b" " * (MAX_BYTES + 1))  # oversized and no complete line in any window
    assert build_event_center(generated_at_utc=STAMP, p12_alerts=path)["sources"][0]["status"] == "INVALID"
    huge = tmp_path / "burn_in"  # the projection is one JSON document: no window, explicit limit
    huge.write_bytes(b" " * (MAX_BYTES + 1))
    assert build_event_center(generated_at_utc=STAMP, ppl_lifecycles=huge)["sources"][2]["status"] == "OUTPUT_LIMIT"
    link = tmp_path / "link"
    link.symlink_to(path)
    assert build_event_center(generated_at_utc=STAMP, p12_alerts=link)["sources"][0]["status"] == "READ_ERROR"


def test_truncation_stable_alert_ids_and_output_guard(tmp_path):
    path = tmp_path / "alerts"
    path.write_text(alert() * 101)
    first = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    assert first["sources"][0]["truncated"] and len(first["events"]) == 100
    path.write_text(alert() * 102)
    second = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    assert len({e["event_id"] for e in first["events"]} & {e["event_id"] for e in second["events"]}) == 99
    with pytest.raises(ValueError, match="OUTPUT_IS_SOURCE"):
        publish_event_center(path, generated_at_utc=STAMP, p12_alerts=path)
    assert not list(tmp_path.glob(".events-*"))


@pytest.mark.parametrize("stamp,status", [("2027-01-15T08:00:00", "PRESENT"), ("nonsense", "INVALID"), (None, "INVALID")])
def test_legacy_date_unknown_only_when_valid_naive(tmp_path, stamp, status):
    path = tmp_path / "audit"
    path.write_text(json.dumps({"type": "legacy", "severity": "warning", "timestamp": stamp}) + "\n")
    doc = build_event_center(generated_at_utc=STAMP, supervision_alerts=path)
    assert doc["sources"][1]["status"] == status
    if status == "PRESENT":
        assert doc["events"][0]["occurred_at_utc"] is None


def test_ppl_identity_survives_history_reorder(tmp_path):
    generate(tmp_path)
    path = tmp_path / "_producer" / "J_burn_in" / "burn_in_status_snapshot.json"
    doc = json.loads(path.read_text())
    first = _ppl_events(path.read_bytes())[0]
    # Isolate event identity from the enclosing U2 order validator.
    from observability.event_center_snapshot import _event
    event = first[0]
    row = doc["lifecycle_history"][0]
    same = _event("ppl_lifecycles", 99, event["kind"], event["severity"], event["occurred_at_utc"],
                  identity_ref=doc["paper_epoch_id"] + ":" + row["trade_id"], symbol=event["symbol"], sequence=event["sequence"])
    assert event["event_id"] == same["event_id"]


@pytest.mark.parametrize("field,value", [("status", []), ("published_count", True), ("source_sha256", "bad")])
def test_contract_rejects_malformed_values_without_raising(tmp_path, field, value):
    doc = generate(tmp_path)["body"]
    doc["sources"][0][field] = value
    assert not validate_event_center(doc, transport=True)


def test_transport_stale_future_missing_and_http_methods(tmp_path, monkeypatch):
    generate(tmp_path)
    path = tmp_path / "_producer" / "L_events" / "event_center_snapshot.json"
    reader = EventCenterReader(path, now_fn=lambda: NOW + 100)
    doc = reader.read().snapshot
    assert doc["freshness_classification"] == "STALE"
    assert doc["sources"][2]["freshness_classification"] == "STALE"
    assert EventCenterReader(path, now_fn=lambda: NOW - 1).read().error_code == "EVENT_CENTER_FUTURE_TIMESTAMP"
    monkeypatch.setattr(api, "_event_center_reader", reader)
    before = path.read_bytes()
    with TestClient(api.app) as client:
        assert client.get("/api/operator/v1/events").status_code == 200
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)("/api/operator/v1/events").status_code == 405
        path.unlink()
        response = client.get("/api/operator/v1/events")
        assert response.status_code == 503 and response.json()["error_code"] == "EVENT_CENTER_MISSING"
    path.write_bytes(before)
    broken = copy.deepcopy(json.loads(before))
    broken["events"][0]["unexpected"] = "secret"
    path.write_text(json.dumps(broken))
    assert reader.read().error_code == "EVENT_CENTER_INVALID_SCHEMA"


def test_reader_has_no_producer_or_runtime_imports():
    import ast
    path = Path("observability/operator_api/event_center_reader.py")
    imports = [n.module for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.ImportFrom)]
    assert not any("snapshot" in name or "paper_trading" in name or "supervision" in name for name in imports)


def test_partial_source_and_concurrent_change_do_not_hide_good_source(tmp_path, monkeypatch):
    from observability import event_center_artifact as artifact
    path = tmp_path / "alerts"
    path.write_text(alert())
    audit = tmp_path / "audit"
    audit.write_text("bad\n")
    doc = build_event_center(generated_at_utc=STAMP, p12_alerts=path, supervision_alerts=audit)
    assert [s["status"] for s in doc["sources"]] == ["PRESENT", "INVALID", "NOT_CONFIGURED"]
    assert len(doc["events"]) == 1
    original = artifact.os.fstat
    calls = 0
    def changing(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_text(alert() * 2)
        return original(fd)
    monkeypatch.setattr(artifact.os, "fstat", changing)
    doc = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    assert doc["sources"][0]["status"] == "INVALID" and doc["events"] == []


def test_fresh_capture_keeps_old_ppl_projection_stale(tmp_path):
    generate(tmp_path)
    root = tmp_path / "_producer"
    path = root / "L_events" / "event_center_snapshot.json"
    publish_event_center(path, generated_at_utc="2027-01-15T08:10:00Z", ppl_lifecycles=root / "J_burn_in" / "burn_in_status_snapshot.json")
    result = EventCenterReader(path, now_fn=lambda: NOW + 201).read().snapshot
    assert result["freshness_classification"] == "FRESH"
    assert result["sources"][2]["freshness_classification"] == "STALE"


# ----------------------- bounded tail window (schema 1.1.0) -----------------------

from observability.event_center_contract import (  # noqa: E402
    MAX_RECORDS, TAIL_WINDOW_BYTES, VERSION_BASE, VERSION_COVERAGE,
)


def numbered(i, pad=100):
    return json.dumps({"rule": "MEMORY", "severity": "WARNING", "ts": NOW - 10,
                       "message": "m" * pad, "value": i, "threshold": 90}) + "\n"


def big_log(tmp_path, lines=None, pad=100):
    """Append-only log larger than MAX_BYTES; record i carries value=i."""
    path = tmp_path / "alerts.jsonl"
    count = lines or (MAX_BYTES // len(numbered(0, pad)) + 2000)
    path.write_text("".join(numbered(i, pad) for i in range(1, count + 1)))
    return path, count


def test_oversized_alert_log_is_an_explicit_partial_tail_never_exhaustive(tmp_path):
    path, count = big_log(tmp_path)
    size = path.stat().st_size
    assert size > MAX_BYTES
    doc = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    source = doc["sources"][0]
    assert doc["schema_version"] == VERSION_COVERAGE and validate_event_center(doc)
    assert source["status"] == "PARTIAL_TAIL" and source["coverage"] == "TAIL_WINDOW"
    assert source["source_bytes"] == size and 0 < source["window_bytes"] <= TAIL_WINDOW_BYTES
    assert source["window_bytes"] < size
    assert 0 < source["records_observed"] < count  # records before the window are not counted
    # the window is the END of the file, cut on a line start: first record is complete
    raw = path.read_bytes()[-source["window_bytes"]:]
    assert raw.startswith(b'{"rule"') and raw.endswith(b"\n")
    assert source["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert source["records_observed"] == raw.count(b"\n")
    first_in_window = count - source["records_observed"] + 1
    assert json.loads(raw.splitlines()[0])["value"] == first_in_window
    assert doc["sources"][1]["coverage"] is None and doc["sources"][2]["source_bytes"] is None


def fixed(size, value=7):
    """One valid alert line of exactly `size` bytes."""
    pad = size - len(numbered(value, 0).encode())
    line = numbered(value, pad)
    assert len(line.encode()) == size
    return line


def test_limit_boundary_full_file_keeps_schema_1_0_0_and_a_larger_file_becomes_tail(tmp_path):
    small = tmp_path / "small.jsonl"
    small.write_text(numbered(1) * 3)
    full = build_event_center(generated_at_utc=STAMP, p12_alerts=small)
    assert full["schema_version"] == VERSION_BASE and full["sources"][0]["status"] == "PRESENT"
    assert "coverage" not in full["sources"][0]  # published exactly as before
    exact = tmp_path / "exact.jsonl"  # exactly MAX_BYTES (8192 lines of 256 B): still read whole
    exact.write_text(fixed(256) * (MAX_BYTES // 256))
    assert exact.stat().st_size == MAX_BYTES
    assert build_event_center(generated_at_utc=STAMP, p12_alerts=exact)["sources"][0]["status"] == "PRESENT"
    with exact.open("ab") as handle:
        handle.write(fixed(256).encode())  # one more record: now above the limit
    over = build_event_center(generated_at_utc=STAMP, p12_alerts=exact)
    assert over["sources"][0]["status"] == "PARTIAL_TAIL" and validate_event_center(over)


def test_more_than_max_records_in_a_small_file_is_the_last_records_not_output_limit(tmp_path):
    path = tmp_path / "audit.jsonl"
    rows = [json.dumps({"type": "drawdown", "severity": "info", "timestamp": "2027-01-15T08:05:00Z"}) + "\n"
            for _ in range(MAX_RECORDS + 7)]
    path.write_text("".join(rows))
    assert path.stat().st_size < MAX_BYTES
    doc = build_event_center(generated_at_utc=STAMP, supervision_alerts=path)
    source = doc["sources"][1]
    assert validate_event_center(doc) and source["status"] == "PARTIAL_TAIL"
    assert source["records_observed"] == MAX_RECORDS
    assert source["window_bytes"] < source["source_bytes"] == path.stat().st_size


def test_window_cut_on_a_line_start_keeps_it_and_a_mid_line_cut_drops_the_partial_line(tmp_path):
    path = tmp_path / "alerts.jsonl"
    path.write_text(fixed(256) * (MAX_BYTES // 256 + 100))
    assert (path.stat().st_size - TAIL_WINDOW_BYTES) % 256 == 0  # the cut is a line start
    on_cut = build_event_center(generated_at_utc=STAMP, p12_alerts=path)["sources"][0]
    assert on_cut["window_bytes"] == TAIL_WINDOW_BYTES and on_cut["records_observed"] == TAIL_WINDOW_BYTES // 256
    path.write_text(fixed(256) * (MAX_BYTES // 256 + 100) + fixed(130))  # the cut now lands mid-line
    mid = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    raw = path.read_bytes()
    window = mid["sources"][0]["window_bytes"]
    assert validate_event_center(mid) and window < TAIL_WINDOW_BYTES and (window - 130) % 256 == 0
    assert raw[-window:].startswith(b'{"rule"')  # the partial first line was dropped, not parsed


def test_window_without_a_complete_line_and_an_unterminated_tail_are_invalid(tmp_path):
    path = tmp_path / "alerts.jsonl"
    path.write_bytes(b"x" * (MAX_BYTES + 10) + b"\n")  # one line longer than the window
    assert build_event_center(generated_at_utc=STAMP, p12_alerts=path)["sources"][0]["status"] == "INVALID"
    big, _ = big_log(tmp_path)
    big.write_bytes(big.read_bytes() + b'{"rule":')  # a record being written right now
    assert build_event_center(generated_at_utc=STAMP, p12_alerts=big)["sources"][0]["status"] == "INVALID"


def test_change_during_the_windowed_read_is_rejected_not_published(tmp_path, monkeypatch):
    from observability import event_center_artifact as artifact

    path, _ = big_log(tmp_path)
    real, calls = artifact.os.fstat, []

    def growing(fd):
        info = real(fd)
        calls.append(1)
        if len(calls) == 2:  # the "after" stat: the file grew meanwhile
            return os.stat_result((info.st_mode, info.st_ino, info.st_dev, info.st_nlink, info.st_uid,
                                   info.st_gid, info.st_size + 120, 0, int(info.st_mtime) + 1, 0))
        return info

    monkeypatch.setattr(artifact.os, "fstat", growing)
    doc = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    assert doc["sources"][0]["status"] == "INVALID" and doc["events"] == []


def test_contract_rejects_misused_or_forged_coverage(tmp_path):
    path, _ = big_log(tmp_path)
    doc = build_event_center(generated_at_utc=STAMP, p12_alerts=path)
    assert validate_event_center(doc)

    def mutate(fn):
        copy_ = copy.deepcopy(doc)
        fn(copy_)
        return validate_event_center(copy_)

    assert not mutate(lambda d: d.update(schema_version=VERSION_BASE))            # partial needs 1.1.0
    assert not mutate(lambda d: d["sources"][0].update(status="PRESENT"))          # tail posing as full
    assert not mutate(lambda d: d["sources"][0].update(coverage="FULL"))
    assert not mutate(lambda d: d["sources"][0].update(window_bytes=d["sources"][0]["source_bytes"]))
    assert not mutate(lambda d: d["sources"][0].pop("coverage"))
    assert not mutate(lambda d: d["sources"][2].update(status="PARTIAL_TAIL"))     # JSON projection: never
    assert not mutate(lambda d: d["sources"][0].update(window_bytes=0))
    base = build_event_center(generated_at_utc=STAMP, p12_alerts=tmp_path / "missing")
    assert base["schema_version"] == VERSION_BASE and validate_event_center(base)
    base["sources"][0]["coverage"] = None
    assert not validate_event_center(base)  # 1.0.0 carries no coverage keys


def test_partial_tail_flows_through_the_api_reader_with_unknown_freshness(tmp_path):
    path, _ = big_log(tmp_path)
    artifact = tmp_path / "event_center_snapshot.json"
    publish_event_center(artifact, generated_at_utc=STAMP, p12_alerts=path)
    now = EventCenterReader(artifact, now_fn=lambda: 0).read()
    assert not now.ok and now.error_code == "EVENT_CENTER_FUTURE_TIMESTAMP"
    from observability.event_center_contract import utc_seconds
    result = EventCenterReader(artifact, now_fn=lambda: utc_seconds(STAMP) + 5).read()
    assert result.ok and validate_event_center(result.snapshot, transport=True)
    source = result.snapshot["sources"][0]
    assert source["status"] == "PARTIAL_TAIL" and source["freshness_classification"] == "UNKNOWN"
    assert source["source_bytes"] > source["window_bytes"] > 0
