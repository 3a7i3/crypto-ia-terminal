import ast
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from observability import storage_snapshot as producer
from observability.storage_contract import METRICS, validate_storage_snapshot
from observability.operator_api import app as api
from observability.operator_api.storage_reader import StorageSnapshotReader
from tests.cross_stack.generate_storage_fixture import NOW, STAMP, generate


def test_real_chain_exact_metadata_no_private_data(tmp_path):
    result = generate(tmp_path)
    doc = result["body"]
    assert result["http_status"] == 200 and validate_storage_snapshot(doc, transport=True)
    assert doc["source_status"] == "PRESENT"
    assert doc["matched_file_count"] == 2 and doc["entries_observed"] == 3
    assert doc["total_bytes"] == len(b"not JSON; private content\n")
    assert "SECRET" not in json.dumps(doc) and "private" not in json.dumps(doc)
    source = tmp_path / "_producer" / "N_storage" / "private-source"
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()}
    producer.publish_storage_snapshot(tmp_path / "capture.json", generated_at_utc=STAMP, source_directory=source)
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == values for p, values in before.items())


def test_empty_missing_unconfigured_are_distinct(tmp_path):
    unknown = producer.build_storage_snapshot(generated_at_utc=STAMP)
    assert unknown["source_status"] == "NOT_CONFIGURED" and all(unknown[k] is None for k in METRICS)
    missing = producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=tmp_path / "missing")
    assert missing["source_status"] == "MISSING" and all(missing[k] is None for k in METRICS)
    empty = producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=tmp_path)
    assert empty["source_status"] == "PRESENT" and empty["matched_file_count"] == empty["total_bytes"] == 0
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "decision_packets_nested.jsonl").write_text("nested")
    assert producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=tmp_path)["matched_file_count"] == 0


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_matching_nonregular_file_invalidates_entire_capture(tmp_path, kind):
    matching = tmp_path / "decision_packets_bad.jsonl"
    if kind == "symlink":
        target = tmp_path / "private"
        target.write_text("secret")
        matching.symlink_to(target)
    elif kind == "directory":
        matching.mkdir()
    else:
        os.mkfifo(matching)
    (tmp_path / "decision_packets_good.jsonl").write_text("good")
    doc = producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=tmp_path)
    assert doc["source_status"] == "INVALID_PATH" and all(doc[k] is None for k in METRICS)


def test_no_journal_open_and_root_symlink_rejected(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "decision_packets_test.jsonl").write_text("invalid journal")
    original = producer.os.open
    def guarded(path, flags, *args, **kwargs):
        assert Path(path) == source, "Producer tried to open a journal"
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(producer.os, "open", guarded)
    assert producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=source)["source_status"] == "PRESENT"
    monkeypatch.setattr(producer.os, "open", original)
    alias = tmp_path / "alias"
    alias.symlink_to(source)
    assert producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=alias)["source_status"] != "PRESENT"


def test_limits_include_unrelated_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(producer, "MAX_ENTRIES", 2)
    for index in range(3):
        (tmp_path / str(index)).write_text("")
    doc = producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=tmp_path)
    assert doc["source_status"] == "OUTPUT_LIMIT" and doc["total_bytes"] is None


def test_concurrent_file_change_rejected(tmp_path, monkeypatch):
    source = tmp_path / "decision_packets_test.jsonl"
    source.write_text("initial")
    original = producer._inventory
    calls = 0
    def changed(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_text("changed-size")
        return original(fd)
    monkeypatch.setattr(producer, "_inventory", changed)
    doc = producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=tmp_path)
    assert doc["source_status"] == "SOURCE_CHANGED" and all(doc[k] is None for k in METRICS)


def test_permission_future_metadata_and_output_source_guard(tmp_path, monkeypatch):
    source = tmp_path / "decision_packets_test.jsonl"
    source.write_text("test")
    os.utime(source, (NOW + 1, NOW + 1))
    assert producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=tmp_path)["source_status"] == "INVALID_METADATA"
    with pytest.raises(ValueError, match="OUTPUT_WITHIN_SOURCE"):
        producer.publish_storage_snapshot(tmp_path / "capture.json", generated_at_utc=STAMP, source_directory=tmp_path)
    def denied(_fd):
        raise PermissionError("SECRET_PATH")
    monkeypatch.setattr(producer, "_inventory", denied)
    doc = producer.build_storage_snapshot(generated_at_utc=STAMP, source_directory=tmp_path)
    assert doc["source_status"] == "READ_ERROR" and "SECRET" not in json.dumps(doc)


def test_atomic_failure_preserves_existing_artifact(tmp_path, monkeypatch):
    output = tmp_path / "capture.json"
    output.write_text("previous")
    def fail(*_args):
        raise OSError("replace failed")
    monkeypatch.setattr(producer.os, "replace", fail)
    with pytest.raises(OSError):
        producer.publish_storage_snapshot(output, generated_at_utc=STAMP)
    assert output.read_text() == "previous" and not list(tmp_path.glob(".storage-*"))


@pytest.mark.parametrize("field,value", [("source_status", []), ("matched_file_count", True), ("total_bytes", -1), ("total_bytes", 1.5), ("inventory_sha256", "bad"), ("latest_file_modified_at_utc", None)])
def test_closed_contract(tmp_path, field, value):
    doc = generate(tmp_path)["body"]
    doc[field] = value
    assert not validate_storage_snapshot(doc, transport=True)


def test_reader_stale_future_corrupt_missing_and_get_only(tmp_path, monkeypatch):
    generate(tmp_path)
    artifact = tmp_path / "_producer" / "N_storage" / "storage_snapshot.json"
    reader = StorageSnapshotReader(artifact, now_fn=lambda: NOW + 100)
    assert reader.read().snapshot["freshness_classification"] == "STALE"
    assert StorageSnapshotReader(artifact, now_fn=lambda: NOW - 1).read().error_code == "STORAGE_FUTURE_TIMESTAMP"
    monkeypatch.setattr(api, "_storage_reader", reader)
    before = artifact.read_bytes()
    with TestClient(api.app) as client:
        assert client.get("/api/operator/v1/storage").status_code == 200
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)("/api/operator/v1/storage").status_code == 405
        artifact.unlink()
        assert client.get("/api/operator/v1/storage").json() == {"error_code": "STORAGE_MISSING"}
    doc = json.loads(before)
    doc["private_path"] = "secret"
    artifact.write_text(json.dumps(doc))
    assert reader.read().error_code == "STORAGE_INVALID_SCHEMA"
    artifact.write_text('{"a":1,"a":2}')
    assert reader.read().error_code == "STORAGE_INVALID_ARTIFACT"
    imports = [n.module for n in ast.walk(ast.parse(Path("observability/operator_api/storage_reader.py").read_text())) if isinstance(n, ast.ImportFrom)]
    assert not any("storage_snapshot" in name or "paper_trading" in name or "dashboard_api" in name for name in imports)
