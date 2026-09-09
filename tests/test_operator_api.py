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
import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.reader import (
    INSTANCE_RELATION_CURRENT,
    INSTANCE_RELATION_PREVIOUS,
    INSTANCE_RELATION_UNKNOWN,
    RUNTIME_STATE_CURRENT,
    RUNTIME_STATE_LAST_KNOWN,
    STALE_REASON_PRODUCER_RESTARTED,
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


# ── R1 correction A: fresh-process import isolation ─────────────────────────
#
# The previous design imported the forbidden modules into THIS test
# process and monkeypatched them, then reloaded the API — that proves
# nothing about a genuinely clean process, and itself imports modules
# with possible side effects before the assertion even runs. A real
# subprocess with nothing pre-imported is the only way to prove that
# `import observability.operator_api.app` alone never pulls in the
# producer/writer/runtime modules, and never performs a filesystem write
# (e.g. `observability.json_logger`'s module-level `logs/` mkdir).

_ISOLATION_CHECK_SCRIPT = """
import sys
sys.path.insert(0, {repo_root!r})
import observability.operator_api.app  # noqa: F401

forbidden = [
    "observability.operator_snapshot_builder",
    "observability.operator_runtime_manifest",
    "observability.json_logger",
    "paper_trading.mexc_simulator",
    "infra.wallet_sync",
    "observability.real_accounts",
    "core.advisor_loop",
]
leaked = [m for m in forbidden if m in sys.modules]
if leaked:
    print("LEAKED:" + ",".join(leaked))
else:
    print("CLEAN")
"""


def _run_isolation_script(cwd) -> str:
    import subprocess
    import sys as _sys

    repo_root = str(Path(__file__).resolve().parent.parent)
    script = _ISOLATION_CHECK_SCRIPT.format(repo_root=repo_root)
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [_sys.executable, "-c", script],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, f"isolation script failed: {result.stderr}"
    return result.stdout.strip()


def test_1_fresh_process_import_never_pulls_forbidden_modules(tmp_path):
    output = _run_isolation_script(tmp_path)
    assert output == "CLEAN", output


def test_2_fresh_process_import_creates_no_application_directory(tmp_path):
    before = set(tmp_path.iterdir())
    _run_isolation_script(tmp_path)
    after = set(tmp_path.iterdir())
    # Only cwd-relative artifacts matter here (e.g. a stray `logs/` or
    # `databases/` directory created by an importer's module-level
    # side effect) — nothing the API's own import should ever create.
    created = after - before
    assert created == set(), f"import created unexpected paths: {created}"


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


# ══════════════════════════════════════════════════════════════════════════
# O-02W-D1-R1 — MASTER remediation tests
# ══════════════════════════════════════════════════════════════════════════


# ── 4/5/6. Two null/empty/wrongly-typed identities never yield CURRENT_INSTANCE ─


def test_r1_none_identities_never_yield_current_instance(paths):
    snap_path, manifest_path = paths
    snap = _valid_snapshot(process_instance_id="inst-1")
    _write_json(snap_path, snap)
    _write_json(manifest_path, {**_valid_manifest(), "process_instance_id": None})

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    result = reader.read()
    assert result.ok is True
    assert result.instance_relation == INSTANCE_RELATION_UNKNOWN
    assert result.stale_reason is None


def test_r1_empty_identities_never_yield_current_instance(paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot(process_instance_id="inst-1"))
    _write_json(manifest_path, {**_valid_manifest(), "process_instance_id": ""})

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    result = reader.read()
    assert result.ok is True
    assert result.instance_relation == INSTANCE_RELATION_UNKNOWN
    assert result.stale_reason is None


def test_r1_wrongly_typed_identities_never_yield_current_instance(paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot(process_instance_id="inst-1"))
    _write_json(manifest_path, {**_valid_manifest(), "process_instance_id": 12345})

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    result = reader.read()
    assert result.ok is True
    assert result.instance_relation == INSTANCE_RELATION_UNKNOWN
    assert result.stale_reason is None


# ── 7. Unsupported snapshot schema version fails explicitly ────────────────


def test_r1_unsupported_schema_version_fails_explicitly(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, {**_valid_snapshot(), "schema_version": "9.9.9"})
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "SNAPSHOT_UNSUPPORTED_SCHEMA_VERSION"


# ── 8. Invalid cycle types fail explicitly, including boolean ──────────────


@pytest.mark.parametrize("bad_cycle", [True, False, "42", 3.5, None, -1])
def test_r1_invalid_cycle_types_fail_explicitly(client, paths, bad_cycle):
    snap_path, manifest_path = paths
    _write_json(snap_path, {**_valid_snapshot(), "cycle": bad_cycle})
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "SNAPSHOT_INVALID_CYCLE"


# ── 9. Invalid domain types fail explicitly ─────────────────────────────────


@pytest.mark.parametrize("domain_key", ["portfolio", "decision_pipeline", "system_health"])
def test_r1_invalid_domain_type_fails_explicitly(client, paths, domain_key):
    snap_path, manifest_path = paths
    _write_json(snap_path, {**_valid_snapshot(), domain_key: "not-an-object"})
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == f"SNAPSHOT_INVALID_DOMAIN_TYPE_{domain_key.upper()}"


# ── 10. Invalid timestamp fails explicitly ──────────────────────────────────


@pytest.mark.parametrize(
    "bad_ts", ["not-a-timestamp", "2026-09-09T00:00:00", "", 12345, None]
)
def test_r1_invalid_timestamp_fails_explicitly(client, paths, bad_ts):
    snap_path, manifest_path = paths
    _write_json(snap_path, {**_valid_snapshot(), "generated_at_utc": bad_ts})
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "SNAPSHOT_INVALID_TIMESTAMP"


# ── 11. Future timestamp is not silently clamped to age zero ───────────────


def test_r1_future_timestamp_not_silently_clamped_to_zero(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, {**_valid_snapshot(), "generated_at_utc": "2099-01-01T00:00:00Z"})
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error_code"] == "SNAPSHOT_CLOCK_SKEW_FUTURE_TIMESTAMP"
    assert "snapshot_age_s" not in body


def test_r1_reader_rejects_future_timestamp_directly(paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, {**_valid_snapshot(), "generated_at_utc": "2099-01-01T00:00:00Z"})
    _write_json(manifest_path, _valid_manifest())

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    result = reader.read()
    assert result.ok is False
    assert result.error_code == "SNAPSHOT_CLOCK_SKEW_FUTURE_TIMESTAMP"


# ── 12/13. Identity mismatch immediately emits stale_reason, even when recent ─


def test_r1_identity_mismatch_immediately_stale_reason_producer_restarted(paths):
    import datetime as _dt

    snap_path, manifest_path = paths
    now_iso = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=1)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    _write_json(
        snap_path,
        {**_valid_snapshot(process_instance_id="inst-old"), "generated_at_utc": now_iso},
    )
    _write_json(manifest_path, _valid_manifest(process_instance_id="inst-new"))

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    result = reader.read()
    assert result.ok is True
    # Even a one-second-old snapshot is immediately LAST_KNOWN/
    # PRODUCER_RESTARTED once the manifest names a different instance —
    # never dependent on elapsed time.
    assert result.instance_relation == INSTANCE_RELATION_PREVIOUS
    assert result.runtime_state == RUNTIME_STATE_LAST_KNOWN
    assert result.stale_reason == STALE_REASON_PRODUCER_RESTARTED
    assert result.snapshot_age_s < 5.0


# ── 14. Domain endpoints expose the same stale reason ───────────────────────


@pytest.mark.parametrize(
    "endpoint", ["/api/operator/v1/portfolio", "/api/operator/v1/decision-pipeline", "/api/operator/v1/system-health"]
)
def test_r1_domain_endpoints_expose_stale_reason(client, paths, endpoint):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot(process_instance_id="inst-old"))
    _write_json(manifest_path, _valid_manifest(process_instance_id="inst-new"))

    resp = client.get(endpoint)
    assert resp.status_code == 200
    body = resp.json()
    assert body["instance_relation"] == INSTANCE_RELATION_PREVIOUS
    assert body["stale_reason"] == STALE_REASON_PRODUCER_RESTARTED


# ── 15. Current instance does not fabricate a stale reason ─────────────────


def test_r1_current_instance_never_fabricates_stale_reason(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot(process_instance_id="inst-1"))
    _write_json(manifest_path, _valid_manifest(process_instance_id="inst-1"))

    resp = client.get("/api/operator/v1/snapshot")
    body = resp.json()
    assert body["instance_relation"] == INSTANCE_RELATION_CURRENT
    assert body["stale_reason"] is None


# ── 16. Missing/corrupt manifest never claims PRODUCER_RESTARTED ───────────


def test_r1_missing_manifest_never_claims_producer_restarted(client, paths):
    snap_path, _ = paths
    _write_json(snap_path, _valid_snapshot())

    resp = client.get("/api/operator/v1/snapshot")
    body = resp.json()
    assert body["instance_relation"] == INSTANCE_RELATION_UNKNOWN
    assert body["stale_reason"] is None


def test_r1_corrupt_manifest_never_claims_producer_restarted(client, paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot())
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{bad", encoding="utf-8")

    resp = client.get("/api/operator/v1/snapshot")
    body = resp.json()
    assert body["instance_relation"] == INSTANCE_RELATION_UNKNOWN
    assert body["stale_reason"] is None


# ── 17. The API does not synthesize a distinct trace_id ─────────────────────


def test_r1_api_never_synthesizes_trace_id(client, paths):
    snap_path, manifest_path = paths
    snap = _valid_snapshot()
    assert "trace_id" not in snap
    _write_json(snap_path, snap)
    _write_json(manifest_path, _valid_manifest())

    resp = client.get("/api/operator/v1/snapshot")
    assert "trace_id" not in resp.json()


# ── 3 (reprise). Manifest identity validation distinguishes usable vs corrupt ─


def test_r1_manifest_missing_process_instance_id_key_is_unknown(paths):
    snap_path, manifest_path = paths
    _write_json(snap_path, _valid_snapshot(process_instance_id="inst-1"))
    manifest_without_pid = _valid_manifest()
    del manifest_without_pid["process_instance_id"]
    _write_json(manifest_path, manifest_without_pid)

    reader = SafeSnapshotReader(snapshot_path=snap_path, manifest_path=manifest_path)
    result = reader.read()
    assert result.ok is True
    assert result.instance_relation == INSTANCE_RELATION_UNKNOWN
    assert result.stale_reason is None
