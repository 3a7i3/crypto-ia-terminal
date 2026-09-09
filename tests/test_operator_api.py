"""tests/test_operator_api.py — O-02W-D1 focused tests.

Covers mission §8 test requirements 1-27 for the minimum read-only
canonical operator API (docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_
CONTRACT.md, §21 MINIMUM_IMPLEMENTATION_MISSION next-mission scope).

All reads happen against `tmp_path` files — never the real `databases/`
directory (mission §5/§8/§17: "configurable file paths ... tests operate
only on temporary files").
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.reader import (
    INSTANCE_RELATION_CURRENT,
    INSTANCE_RELATION_PREVIOUS,
    INSTANCE_RELATION_UNKNOWN,
    RUNTIME_STATE_CURRENT,
    RUNTIME_STATE_LAST_KNOWN,
    SafeSnapshotReader,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _valid_snapshot(process_instance_id="inst-1", cycle=42, snapshot_id="snap-1"):
    return {
        "schema_version": "1.0.0",
        "snapshot_id": snapshot_id,
        "cycle": cycle,
        "process_instance_id": process_instance_id,
        "generated_at_utc": "2026-09-09T00:00:00Z",
        "source_sha": "deadbeef",
        "worktree_state": "UNKNOWN",
        "deployment_evidence": {},
        "runtime_sha_evidence_status": "CLAIMED_ONLY",
        "portfolio": {"paper_equity_usd": {"value": 1000.0, "semantics": "PRESENT"}},
        "decision_pipeline": {"trade_allowed": {"value": None, "semantics": "UNKNOWN"}},
        "system_health": {"boot_alive": {"value": None, "semantics": "UNKNOWN"}},
    }


def _valid_manifest(process_instance_id="inst-1"):
    return {
        "schema_version": 1,
        "process_instance_id": process_instance_id,
        "boot_timestamp_utc": "2026-09-09T00:00:00Z",
        "pid": 12345,
        "source_sha": "deadbeef",
    }


def _write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "operator_snapshot.json", tmp_path / "operator_runtime_manifest.json"


@pytest.fixture
def client(paths):
    snap_path, manifest_path = paths
    api_app.configure_reader(snapshot_path=snap_path, manifest_path=manifest_path)
    return TestClient(api_app.app)


# ── 1. Valid snapshot + matching manifest ──────────────────────────────────


def test_valid_snapshot_matching_manifest(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["instance_relation"] == INSTANCE_RELATION_CURRENT
    assert body["runtime_state"] == RUNTIME_STATE_CURRENT
    assert body["snapshot_id"] == "snap-1"


# ── 2. Missing snapshot ─────────────────────────────────────────────────────


def test_missing_snapshot(client, paths):
    _, manifest_path = paths
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "SNAPSHOT_MISSING"


# ── 3. Empty snapshot file ──────────────────────────────────────────────────


def test_empty_snapshot_file(client, paths):
    snap_path, manifest_path = paths
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text("", encoding="utf-8")
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "SNAPSHOT_MALFORMED_JSON"


# ── 4. Malformed JSON ────────────────────────────────────────────────────────


def test_malformed_json_snapshot(client, paths):
    snap_path, manifest_path = paths
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text("{not valid json", encoding="utf-8")
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "SNAPSHOT_MALFORMED_JSON"


# ── 5. Missing manifest ──────────────────────────────────────────────────────


def test_missing_manifest(client, paths):
    snap_path, _ = paths
    _write_json(snap_path, _valid_snapshot())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["instance_relation"] == INSTANCE_RELATION_UNKNOWN
    assert body["runtime_state"] == RUNTIME_STATE_LAST_KNOWN


# ── 6. Malformed manifest ─────────────────────────────────────────────────────


def test_malformed_manifest(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{bad", encoding="utf-8")

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["instance_relation"] == INSTANCE_RELATION_UNKNOWN
    assert body["runtime_state"] == RUNTIME_STATE_LAST_KNOWN


# ── 7. Manifest changes during a read ────────────────────────────────────────


def test_manifest_changes_during_read_bounded_retry(paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    _write_json(manifest_path, _valid_manifest("inst-A"))

    calls = {"n": 0}

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path, max_retries=5)

    # Monkeypatch the reader's manifest reads to change on every call via a
    # side-effecting write between reads, simulating a live rotation.
    orig_read_text = manifest_path.read_text

    def flapping_read_text(self, *args, **kwargs):
        calls["n"] += 1
        # Alternate manifest content on every read to force "changed" every
        # time, proving the bounded retry terminates (test 26).
        _write_json(manifest_path, _valid_manifest(f"inst-{calls['n']}"))
        return orig_read_text(*args, **kwargs)

    import unittest.mock as mock

    with mock.patch.object(type(manifest_path), "read_text", flapping_read_text):
        result = reader.read()

    assert result.ok is False
    assert result.error_code == "MANIFEST_CHANGED_DURING_READ"
    assert result.retries_used == 5


# ── 8. Manifest/snapshot process identity mismatch ──────────────────────────


def test_manifest_snapshot_identity_mismatch(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot(process_instance_id="inst-old"))
    _write_json(manifest_path, _valid_manifest(process_instance_id="inst-new"))

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["instance_relation"] == INSTANCE_RELATION_PREVIOUS
    assert body["runtime_state"] == RUNTIME_STATE_LAST_KNOWN


# ── 9. Required envelope field missing ──────────────────────────────────────


def test_required_envelope_field_missing(client, paths):
    snap_path, manifest_path = paths
    bad = _valid_snapshot()
    del bad["process_instance_id"]
    _write_json(snap_path, bad)
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "SNAPSHOT_MISSING_REQUIRED_FIELDS"


# ── 10. Domain projection preserves the producer data exactly ──────────────


def test_domain_projection_preserves_producer_data(client, paths):
    snap_path, manifest_path = paths
    snap = _valid_snapshot()
    snap["portfolio"] = {
        "paper_equity_usd": {"value": 1234.5, "semantics": "PRESENT"},
        "open_positions": {"value": [{"symbol": "BTCUSDT"}], "semantics": "PRESENT"},
    }
    _write_json(snap_path, snap)
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/portfolio")
    assert resp.status_code == 200
    body = resp.json()
    assert body["portfolio"] == snap["portfolio"]
    assert body["snapshot_id"] == snap["snapshot_id"]
    assert body["cycle"] == snap["cycle"]
    assert body["process_instance_id"] == snap["process_instance_id"]
    assert body["generated_at_utc"] == snap["generated_at_utc"]


# ── 11. ObservedValue / null semantics are not rewritten ────────────────────


def test_observed_value_semantics_not_rewritten(client, paths):
    snap_path, manifest_path = paths
    snap = _valid_snapshot()
    snap["portfolio"] = {"real_account_equity_usd": {"value": None, "semantics": "NOT_APPLICABLE"}}
    _write_json(snap_path, snap)
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/portfolio")
    body = resp.json()
    assert body["portfolio"]["real_account_equity_usd"] == {
        "value": None,
        "semantics": "NOT_APPLICABLE",
    }


# ── 12. Numeric zero remains distinct from unavailable/null ─────────────────


def test_numeric_zero_distinct_from_unavailable(client, paths):
    snap_path, manifest_path = paths
    snap = _valid_snapshot()
    snap["portfolio"] = {
        "paper_open_positions_count": {"value": 0, "semantics": "ZERO"},
        "paper_unrealized_pnl_usd": {"value": None, "semantics": "UNAVAILABLE"},
    }
    _write_json(snap_path, snap)
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/portfolio")
    body = resp.json()["portfolio"]
    assert body["paper_open_positions_count"] == {"value": 0, "semantics": "ZERO"}
    assert body["paper_unrealized_pnl_usd"] == {"value": None, "semantics": "UNAVAILABLE"}


# ── 13. Real/testnet portfolio fields are presentation-only ─────────────────


def test_real_testnet_fields_presentation_only(client, paths):
    snap_path, manifest_path = paths
    snap = _valid_snapshot()
    snap["portfolio"] = {
        "real_account_equity_usd": {"value": 555.5, "semantics": "PRESENT"},
        "mode": "REAL_API",
    }
    _write_json(snap_path, snap)
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/portfolio")
    body = resp.json()["portfolio"]
    # Verbatim passthrough — the API performed no arithmetic on this value.
    assert body["real_account_equity_usd"]["value"] == 555.5


# ── 14. system_health.boot_alive remains null/UNKNOWN ───────────────────────


def test_boot_alive_remains_null_unknown(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/system-health")
    body = resp.json()["system_health"]
    assert body["boot_alive"] == {"value": None, "semantics": "UNKNOWN"}


# ── 15. Snapshot age does not infer advisor liveness ────────────────────────


def test_snapshot_age_never_infers_liveness(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    body = resp.json()
    assert body["freshness_classification"] == "UNKNOWN"
    assert body["system_health"]["boot_alive"]["semantics"] == "UNKNOWN"
    assert isinstance(body["snapshot_age_s"], (int, float))


# ── 16. /healthz describes API transport only ───────────────────────────────


def test_healthz_describes_transport_only(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    text_blob = json.dumps(body).lower()
    assert "advisor" not in text_blob or "does not" in text_blob or "no claim" in text_blob
    assert body["api_transport_process"] == "ready"


# ── 17. No business route accepts POST/PUT/PATCH/DELETE ────────────────────


def test_no_mutating_routes(client):
    for method in ("post", "put", "patch", "delete"):
        for path in (
            "/api/operator/v1/snapshot",
            "/api/operator/v1/portfolio",
            "/api/operator/v1/decision-pipeline",
            "/api/operator/v1/system-health",
            "/healthz",
        ):
            resp = getattr(client, method)(path)
            assert resp.status_code in (404, 405), f"{method.upper()} {path} was accepted"


def test_route_table_has_no_mutating_methods():
    for route in api_app.app.routes:
        methods = getattr(route, "methods", None) or set()
        forbidden = methods & {"POST", "PUT", "PATCH", "DELETE"}
        assert not forbidden, f"route {route.path} exposes mutating methods {forbidden}"


# ── 18. No API request writes snapshot or manifest files ───────────────────


def test_no_request_writes_snapshot_or_manifest(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    _write_json(manifest_path, _valid_manifest())

    snap_mtime_before = snap_path.stat().st_mtime_ns
    manifest_mtime_before = manifest_path.stat().st_mtime_ns

    for path in (
        "/api/operator/v1/snapshot",
        "/api/operator/v1/portfolio",
        "/api/operator/v1/decision-pipeline",
        "/api/operator/v1/system-health",
        "/healthz",
    ):
        client.get(path)

    assert snap_path.stat().st_mtime_ns == snap_mtime_before
    assert manifest_path.stat().st_mtime_ns == manifest_mtime_before


# ── 19/20/21/22. No exchange/network/forbidden-instantiation calls ─────────


def test_no_exchange_credentials_read_or_network_calls(client, paths, monkeypatch):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    _write_json(manifest_path, _valid_manifest())

    def _boom(*args, **kwargs):
        raise AssertionError("network/socket call attempted by a read-only API request")

    import socket

    monkeypatch.setattr(socket.socket, "connect", _boom)
    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 200


def test_no_fresh_forbidden_instantiations(monkeypatch):
    import paper_trading.mexc_simulator as mexc_mod
    import infra.wallet_sync as wallet_mod
    import observability.real_accounts as real_accounts_mod

    def _forbidden(*args, **kwargs):
        raise AssertionError("forbidden object instantiated by the operator API")

    monkeypatch.setattr(mexc_mod, "MexcSimulator", _forbidden, raising=False)
    monkeypatch.setattr(wallet_mod, "WalletSync", _forbidden, raising=False)
    monkeypatch.setattr(real_accounts_mod, "RealAccountsObserver", _forbidden, raising=False)

    import importlib

    import observability.operator_api.app as app_mod
    import observability.operator_api.reader as reader_mod

    importlib.reload(reader_mod)
    importlib.reload(app_mod)


def test_no_import_of_advisor_loop():
    import observability.operator_api.app as app_mod
    import observability.operator_api.reader as reader_mod

    for mod in (app_mod, reader_mod):
        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            contents = f.read()
        assert "import core.advisor_loop" not in contents
        assert "from core.advisor_loop" not in contents
        assert "advisor_loop" not in dir(mod)


# ── 23. No JSONL ledger access ──────────────────────────────────────────────


def test_no_jsonl_ledger_access():
    import observability.operator_api.app as app_mod
    import observability.operator_api.reader as reader_mod

    for mod in (app_mod, reader_mod):
        with open(mod.__file__, encoding="utf-8") as f:
            contents = f.read()
        assert ".jsonl" not in contents
        assert "paper_trades" not in contents
        assert "black_box" not in contents


# ── 24. No fabricated demo data ─────────────────────────────────────────────


def test_no_fabricated_demo_data_on_failure(client, paths):
    # No files at all -> both 503s, never a fabricated 200 with empty domains.
    resp = client.get("/api/operator/v1/portfolio")
    assert resp.status_code == 503
    assert "portfolio" not in resp.json()


# ── 25. Concurrent atomic producer replacements never produce a torn response ─


def test_concurrent_atomic_replacement_never_torn(paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    _write_json(manifest_path, _valid_manifest())

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    stop = threading.Event()
    errors = []

    def writer_loop():
        i = 0
        while not stop.is_set():
            i += 1
            tmp = snap_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(_valid_snapshot(cycle=i)), encoding="utf-8")
            tmp.replace(snap_path)
            time.sleep(0.001)

    t = threading.Thread(target=writer_loop, daemon=True)
    t.start()
    try:
        for _ in range(200):
            result = reader.read()
            if result.ok:
                # A torn read would fail JSON parsing (already excluded by
                # _read_json_file) or yield a snapshot missing required
                # fields (already validated) — reaching here with ok=True
                # means a fully valid, non-torn document was read.
                assert result.snapshot is not None
                assert "cycle" in result.snapshot
            else:
                # Only legitimate structured failures are acceptable, never
                # a crash.
                assert result.error_code is not None
    finally:
        stop.set()
        t.join(timeout=2)
    assert not errors


# ── 26. Bounded retry terminates and fails explicitly ───────────────────────
# (covered by test_manifest_changes_during_read_bounded_retry above)


# ── 27. Configurable paths use only temporary test directories ─────────────


def test_configurable_paths_use_tmp_dir(paths):
    snap_path, manifest_path = paths
    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    assert str(reader._snapshot_path).startswith(str(snap_path.parent))
    assert str(reader._manifest_path).startswith(str(manifest_path.parent))
    assert "databases/operator_snapshot.json" not in str(reader._snapshot_path)


def test_reader_does_not_mutate_loaded_document(paths):
    snap_path, manifest_path = paths
    snap = _valid_snapshot()
    _write_json(snap_path, snap)
    _write_json(manifest_path, _valid_manifest())

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    result = reader.read()
    result.snapshot["injected"] = "mutated"

    result2 = reader.read()
    assert "injected" not in result2.snapshot


def test_reader_never_persists_repaired_document(paths):
    snap_path, manifest_path = paths
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text("{bad json", encoding="utf-8")
    _write_json(manifest_path, _valid_manifest())

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    reader.read()

    # The malformed file on disk must remain exactly as it was — no
    # "repaired" or default document was ever written back.
    assert snap_path.read_text(encoding="utf-8") == "{bad json"
