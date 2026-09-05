"""
tests/test_runtime_provenance_snapshot.py — S-03D focused tests.

Couvre mission section 19, items 1-10 et 15. Les items 11-14 (BlackBox
provenance) sont couverts par test_black_box_provenance.py.

Toutes les écritures se font dans tmp_path — jamais dans databases/ réel
(DS-001).
"""

from __future__ import annotations

import json

from observability import runtime_provenance_snapshot as rps


def test_schema_completeness():
    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs())
    assert snap["schema_version"] == rps.SCHEMA_VERSION
    assert "generated_at_utc" in snap
    for key in (
        "process",
        "decision_observation",
        "event_bus",
        "rejection_store",
        "regret_scheduler",
        "dip",
        "black_box",
    ):
        assert key in snap
    assert "pid" in snap["process"]
    assert "exposure_epoch_id" in snap["process"]
    assert "uptime_s" in snap["process"]


def test_decision_observation_counters_copied():
    from observability import decision_observation as do

    do._record_provenance_failure("missing_packet_id")
    do._record_provenance_failure("missing_trace_id")
    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs())
    live = do.get_provenance_failure_stats()
    assert snap["decision_observation"]["missing_packet_id"] == live["missing_packet_id"]
    assert snap["decision_observation"]["missing_trace_id"] == live["missing_trace_id"]


class _FakeEventBus:
    def get_stats(self):
        return {
            "observations_published": 7,
            "listener_deliveries_submitted": 6,
            "listener_deliveries_succeeded": 5,
            "listener_deliveries_failed": 1,
            "deliveries_dropped_during_shutdown": 0,
        }


def test_event_bus_counters_copied():
    bus = _FakeEventBus()
    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs(decision_event_bus=bus))
    block = snap["event_bus"]
    assert block["status"] == "ACTIVE"
    assert block["observations_published"] == 7
    assert block["listener_deliveries_failed"] == 1


class _FakeRejectionStore:
    def stats(self):
        return {"writes": 3, "errors": 0, "skipped_provenance": 2}


def test_rejection_store_counters_copied():
    store = _FakeRejectionStore()
    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs(rejection_store=store))
    block = snap["rejection_store"]
    assert block == {
        "status": "ACTIVE",
        "writes": 3,
        "errors": 0,
        "skipped_provenance": 2,
    }


class _FakeRegretScheduler:
    def stats(self):
        return {
            "pending_candidates": 4,
            "horizons_evaluated": 12,
            "running": True,
            "skipped_invalid_provenance": 0,
        }


def test_regret_scheduler_counters_copied():
    sched = _FakeRegretScheduler()
    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs(regret_scheduler=sched))
    block = snap["regret_scheduler"]
    assert block["pending_candidates"] == 4
    assert block["horizons_evaluated"] == 12
    assert block["running"] is True


class _FakeDIP:
    is_started = True

    def get_stats(self):
        return {"handler_count": 2, "skipped_invalid_provenance": 0}


def test_dip_counters_copied():
    dip = _FakeDIP()
    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs(dip_observer=dip))
    block = snap["dip"]
    assert block["status"] == "ACTIVE"
    assert block["handler_count"] == 2


def test_unavailable_component_is_not_zero():
    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs())
    for key in ("event_bus", "rejection_store", "regret_scheduler", "black_box"):
        block = snap[key]
        assert block.get("status") == "UNAVAILABLE"
        # No fabricated numeric fields alongside UNAVAILABLE.
        assert set(block.keys()) == {"status"}
    # dip_observer=None means DIP was never started (S-03D-R1 blocker 1) —
    # a distinct status from UNAVAILABLE, still with zero fabricated
    # numeric fields.
    dip_block = snap["dip"]
    assert dip_block == {"status": "NOT_STARTED"}


def test_snapshot_atomic_write(tmp_path):
    path = tmp_path / "sub" / "runtime_provenance_snapshot.json"
    writer = rps.RuntimeProvenanceSnapshotWriter(path=path, min_interval_s=0.0)
    wrote = writer.maybe_refresh(rps.RuntimeProvenanceInputs(), force=True)
    assert wrote is True
    assert path.exists()
    # No leftover tmp file after a successful atomic replace.
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == rps.SCHEMA_VERSION


def test_snapshot_respects_cadence(tmp_path):
    path = tmp_path / "runtime_provenance_snapshot.json"
    writer = rps.RuntimeProvenanceSnapshotWriter(path=path, min_interval_s=3600.0)
    assert writer.maybe_refresh(rps.RuntimeProvenanceInputs()) is True
    # Second call within the cadence window is a no-op (returns False).
    assert writer.maybe_refresh(rps.RuntimeProvenanceInputs()) is False


def test_snapshot_no_secret_material(tmp_path):
    path = tmp_path / "runtime_provenance_snapshot.json"
    writer = rps.RuntimeProvenanceSnapshotWriter(path=path, min_interval_s=0.0)
    writer.maybe_refresh(rps.RuntimeProvenanceInputs(), force=True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    rps.assert_no_secret_material(payload)  # must not raise
    blob = json.dumps(payload).lower()
    for forbidden in (
        "p10_crypto_master_secret",
        "telegram_token",
        "bot_token",
        "api_key",
        "password",
        "ssh",
    ):
        assert forbidden not in blob


def test_uses_injected_live_instances_not_fresh_construction():
    """The snapshot must reflect whatever object is passed in — never a
    freshly constructed replacement with independent state."""

    class _StatefulBus:
        def __init__(self):
            self.calls = 0

        def get_stats(self):
            self.calls += 1
            return {
                "observations_published": 42,
                "listener_deliveries_submitted": 0,
                "listener_deliveries_succeeded": 0,
                "listener_deliveries_failed": 0,
                "deliveries_dropped_during_shutdown": 0,
            }

    bus = _StatefulBus()
    snap = rps.build_snapshot(rps.RuntimeProvenanceInputs(decision_event_bus=bus))
    assert snap["event_bus"]["observations_published"] == 42
    assert bus.calls == 1  # the exact injected instance was read, once


def test_process_epoch_fields_deterministic_enough():
    snap1 = rps.build_snapshot(rps.RuntimeProvenanceInputs())
    snap2 = rps.build_snapshot(rps.RuntimeProvenanceInputs())
    # Same process -> same pid and exposure_epoch_id across snapshots.
    assert snap1["process"]["pid"] == snap2["process"]["pid"]
    assert snap1["process"]["exposure_epoch_id"] == snap2["process"]["exposure_epoch_id"]
    assert snap2["process"]["uptime_s"] >= snap1["process"]["uptime_s"]
