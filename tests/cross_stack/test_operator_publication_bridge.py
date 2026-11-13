"""Publication and failure boundaries using the real canonical fixture chain."""
import fcntl
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from observability import operator_publication_bridge as bridge
from observability.operator_api import app as api
from tests.cross_stack.generate_burn_in_fixture import NOW, generate


@pytest.fixture
def args(tmp_path):
    generate(tmp_path / "fixtures")
    root = tmp_path / "fixtures/_producer/J_burn_in"
    return dict(source_root=root, store_root=root / "ppl",
                config_path=root / "burn-in-config.json", epoch="CROSS-STACK-BURN-IN-001",
                output_root=tmp_path / "presentation", now_fn=lambda: NOW + 10)


def source_bytes(args):
    return {str(p): p.read_bytes() for p in args["source_root"].rglob("*") if p.is_file()}


def test_real_producers_to_generation_to_both_get_routes(args):
    # Fixture epoch is read from config, never guessed from directory names.
    args["epoch"] = json.loads(args["config_path"].read_text())["paper_epoch_id"]
    before = source_bytes(args)
    manifest = bridge.publish(**args)
    current = args["output_root"] / "current"
    assert current.is_symlink()
    assert not (current / "burn_in_status_snapshot.json").is_symlink()
    old_burn, old_events = api.get_burn_in_status_reader(), api.get_event_center_reader()
    try:
        api.configure_burn_in_status_reader(current / "burn_in_status_snapshot.json", now_fn=lambda: NOW + 11)
        api.configure_event_center_reader(current / "event_center_snapshot.json", now_fn=lambda: NOW + 11)
        with TestClient(api.app) as client:
            burn = client.get("/api/operator/v1/burn-in")
            events = client.get("/api/operator/v1/events")
        assert burn.status_code == events.status_code == 200
        assert burn.json()["last_sequence"] == manifest["last_sequence"]
        assert events.json()["sources"][2]["status"] == "PRESENT"
        assert events.json()["sources"][0]["status"] == "NOT_CONFIGURED"
    finally:
        api._burn_in_status_reader, api._event_center_reader = old_burn, old_events
    assert before == source_bytes(args)
    assert not (args["store_root"] / ".ppl-event-store.lock").exists()


@pytest.fixture
def configured(args):
    args["epoch"] = json.loads(args["config_path"].read_text())["paper_epoch_id"]
    return args


def test_failed_generation_preserves_previous_pointer_and_bytes(configured):
    first = bridge.publish(**configured)
    pointer = configured["output_root"] / "current"
    before = {p.name: p.read_bytes() for p in pointer.iterdir()}
    with patch.object(bridge, "build_event_center", side_effect=ValueError("PRIVATE_SOURCE_DETAIL")):
        with pytest.raises(ValueError):
            bridge.publish(**configured)
    assert Path(os.readlink(pointer)).name == first["generation"]
    assert before == {p.name: p.read_bytes() for p in pointer.iterdir()}
    assert not list((configured["output_root"] / "generations").glob(".building-*"))


def test_two_generations_keep_rollback_target(configured):
    first = bridge.publish(**configured)
    second = bridge.publish(**configured)
    assert first["generation"] != second["generation"]
    assert (configured["output_root"] / "generations" / first["generation"]).is_dir()
    assert Path(os.readlink(configured["output_root"] / "current")).name == second["generation"]


def test_concurrent_publisher_fails_busy_without_switching(configured):
    first = bridge.publish(**configured)
    with (configured["output_root"] / ".publish.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(bridge.BridgeError, match="BUSY"):
            bridge.publish(**configured)
    assert Path(os.readlink(configured["output_root"] / "current")).name == first["generation"]


def test_source_overlap_and_symlink_outputs_refused_before_write(configured, tmp_path):
    args = {**configured, "output_root": configured["source_root"] / "new-output"}
    with pytest.raises(bridge.BridgeError, match="OUTPUT_OVERLAPS_SOURCE"):
        bridge.publish(**args)
    assert not args["output_root"].exists()
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(bridge.BridgeError, match="SYMLINK_PATH"):
        bridge.publish(**{**configured, "output_root": link / "new"})


def test_source_corruption_and_config_mismatch_do_not_publish(configured):
    configured["config_path"].write_text('{"paper_epoch_id":"WRONG"}')
    with pytest.raises(ValueError):
        bridge.publish(**configured)
    assert not (configured["output_root"] / "current").exists()


def test_retention_limit_does_not_delete_old_generation(configured):
    first = bridge.publish(**configured)
    with patch.object(bridge, "MAX_GENERATIONS", 1), pytest.raises(bridge.BridgeError, match="RETENTION_LIMIT"):
        bridge.publish(**configured)
    assert (configured["output_root"] / "generations" / first["generation"]).is_dir()


def test_unrecognized_pointer_never_overwritten(configured, tmp_path):
    output = configured["output_root"]
    output.mkdir(mode=0o700)
    (output / "current").symlink_to(tmp_path)
    with pytest.raises(bridge.BridgeError, match="INVALID_CURRENT_POINTER"):
        bridge.publish(**configured)
    assert os.readlink(output / "current") == str(tmp_path)


def test_explicit_p12_is_filtered_and_supervision_invalid_is_not_empty(configured):
    alerts = configured["source_root"] / "alerts.jsonl"
    alerts.write_text(
        json.dumps(
            {
                "rule": "MEMORY",
                "severity": "WARNING",
                "ts": NOW,
                "message": "PRIVATE_TEST_CONTENT",
                "value": 90,
                "threshold": 80,
            }
        )
        + "\n"
    )
    supervision = configured["source_root"] / "supervision.jsonl"
    supervision.write_text('{"unexpected":"PRIVATE_TEST_CONTENT"}\n')
    before = source_bytes(configured)
    manifest = bridge.publish(
        **configured, p12_alerts=alerts, supervision_alerts=supervision
    )
    raw = (configured["output_root"] / "current/event_center_snapshot.json").read_text()
    doc = json.loads(raw)
    assert "PRIVATE_TEST_CONTENT" not in raw
    assert doc["sources"][0]["status"] == "PRESENT"
    assert doc["sources"][0]["published_count"] == 1
    assert doc["sources"][1]["status"] == "INVALID"
    assert doc["sources"][1]["published_count"] is None
    assert manifest["alerts"]["p12_alerts"]["status"] == "PRESENT"
    assert before == source_bytes(configured)


def test_missing_alert_is_explicit_and_ppl_remains_present(configured):
    bridge.publish(**configured, p12_alerts=configured["source_root"] / "missing.jsonl")
    doc = json.loads(
        (configured["output_root"] / "current/event_center_snapshot.json").read_text()
    )
    assert doc["sources"][0]["status"] == "MISSING"
    assert doc["sources"][0]["events_observed"] is None
    assert doc["sources"][2]["status"] == "PRESENT"


def test_external_or_symlink_alert_refused_before_output_write(configured, tmp_path):
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n")
    for path in [outside, configured["source_root"] / "linked.jsonl"]:
        if path != outside:
            path.symlink_to(outside)
        with pytest.raises(bridge.BridgeError):
            bridge.publish(**configured, p12_alerts=path)
        assert not configured["output_root"].exists()
