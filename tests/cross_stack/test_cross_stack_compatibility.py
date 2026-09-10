"""tests/cross_stack/test_cross_stack_compatibility.py — O-02W-D3 LOCAL
CROSS-STACK COMPATIBILITY GATE.

Proves that one canonical payload generated through the actual Python
producer path (O-02W-C `build_operator_snapshot` + real atomic writers)
travels unchanged through the real `SafeSnapshotReader` and the real
FastAPI route (O-02W-D1) — this file only asserts the PYTHON-side half of
the boundary (producer -> reader -> API JSON body). The frontend half
(API JSON body -> `validateOperatorSnapshot()` -> cockpit render) is
asserted by `frontend/src/test/crossStack.compat.test.ts` against the
exact fixture files this module generates.

Everything here writes only inside `tmp_path`; never the real
`databases/` directory. No exchange call, no credential, no VPS/network
access.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from observability.operator_api import app as api_app
from observability.operator_api.reader import SafeSnapshotReader
from tests.cross_stack import generate_fixtures as gf
from tests.cross_stack.generate_fixtures import (
    FIXED_NOW,
    _BOOT_TIMESTAMP_UTC,
    _DEPLOYMENT_OBSERVED_AT_UTC,
    _iso_utc,
    generate_fixture_bundle,
)


def test_generates_all_six_mandatory_scenarios(tmp_path: Path):
    results = generate_fixture_bundle(tmp_path)
    assert set(results.keys()) == {
        "A_minimal_canonical",
        "B_unknown_mode_fail_closed",
        "C_portfolio_semantics",
        "D_decision_authority",
        "E_previous_instance",
        "F_failure_honesty",
    }
    for name in results:
        assert (tmp_path / f"{name}.json").is_file()


def test_scenario_a_minimal_canonical_is_current_and_actionable(tmp_path: Path):
    results = generate_fixture_bundle(tmp_path)
    r = results["A_minimal_canonical"]
    assert r["http_status"] == 200
    body = r["body"]
    assert body["instance_relation"] == "CURRENT_INSTANCE"
    assert body["runtime_state"] == "CURRENT"
    assert body["stale_reason"] is None
    positions = body["portfolio"]["open_positions"]["value"]
    assert len(positions) == 1
    assert positions[0]["current_price"]["value"] == 51000.0
    decisions = body["decision_pipeline"]["per_symbol_decisions"]
    assert decisions[0]["is_actionable"]["value"] is True
    assert decisions[0]["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"


def test_scenario_b_unknown_mode_never_touches_wallet(tmp_path: Path):
    results = generate_fixture_bundle(tmp_path)
    r = results["B_unknown_mode_fail_closed"]
    assert r["http_status"] == 200
    body = r["body"]
    assert body["portfolio"]["mode"] == "UNKNOWN"
    assert body["portfolio"]["paper_equity_usd"] == {"value": None, "semantics": "UNKNOWN"}
    assert body["portfolio"]["non_paper_wallet_balance_usd"] == {"value": None, "semantics": "UNKNOWN"}
    assert body["portfolio"]["capital_x_usd"] == {"value": None, "semantics": "UNKNOWN"}
    assert r["_proof"]["wallet_get_balance_calls"] == 0
    assert r["_proof"]["wallet_capital_x_reads"] == 0


def test_scenario_c_portfolio_semantics_never_fabricates(tmp_path: Path):
    results = generate_fixture_bundle(tmp_path)
    r = results["C_portfolio_semantics"]
    assert r["http_status"] == 200
    body = r["body"]
    portfolio = body["portfolio"]
    # PAPER equity present; separate from the REAL account fields.
    assert portfolio["paper_equity_usd"]["semantics"] == "PRESENT"
    assert portfolio["real_account_equity_usd"]["semantics"] == "PRESENT"
    assert portfolio["real_account_equity_usd"]["value"] == 500.0
    assert portfolio["paper_equity_usd"]["value"] != portfolio["real_account_equity_usd"]["value"]
    # Unavailable price/PnL stay UNAVAILABLE, never a fabricated 0.
    position = portfolio["open_positions"]["value"][0]
    assert position["current_price"] == {"value": None, "semantics": "UNAVAILABLE"}
    assert position["unrealized_pnl_usd"] == {"value": None, "semantics": "UNAVAILABLE"}
    assert position["unrealized_pnl_pct"] == {"value": None, "semantics": "UNAVAILABLE"}


def test_scenario_d_decision_authority_mapping_and_fail_closed(tmp_path: Path):
    results = generate_fixture_bundle(tmp_path)
    r = results["D_decision_authority"]
    body = r["body"]
    by_symbol = {d["symbol"]: d for d in body["decision_pipeline"]["per_symbol_decisions"]}

    actionable = by_symbol["BTC/USDT"]
    assert actionable["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"
    assert actionable["is_actionable"]["value"] is True
    assert actionable["trade_allowed"]["authority"] == "OBSERVATIONAL_TELEMETRY"
    assert actionable["first_blocker"]["authority"] == "OBSERVATIONAL_TELEMETRY"

    missing_packet = by_symbol["ETH/USDT"]
    assert missing_packet["is_actionable"]["value"] is False
    assert missing_packet["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"


def test_scenario_e_previous_instance_never_relabeled_current(tmp_path: Path):
    results = generate_fixture_bundle(tmp_path)
    r = results["E_previous_instance"]
    body = r["body"]
    assert body["instance_relation"] == "PREVIOUS_INSTANCE"
    assert body["runtime_state"] == "LAST_KNOWN"
    assert body["stale_reason"] == "PRODUCER_RESTARTED"
    assert body["instance_relation"] != "CURRENT_INSTANCE"


def test_scenario_f_malformed_snapshot_is_governed_503(tmp_path: Path):
    results = generate_fixture_bundle(tmp_path)
    r = results["F_failure_honesty"]
    assert r["http_status"] == 503
    body = r["body"]
    assert body["error_code"] == "SNAPSHOT_UNSUPPORTED_SCHEMA_VERSION"
    assert "portfolio" not in body
    assert "decision_pipeline" not in body


# ── O-02W-D3-R1 Correction B — deterministic fixture chronology ────────────


def test_fixture_chronology_boot_precedes_snapshot_generation():
    """Boot time must never be after the snapshot-generation instant."""
    assert _BOOT_TIMESTAMP_UTC <= _iso_utc(FIXED_NOW)


def test_fixture_chronology_deployment_evidence_precedes_boot_and_snapshot():
    """Deployment-evidence observation must precede both boot and snapshot
    generation — an impossible payload (evidence observed years after the
    snapshot it describes) must never be generated again."""
    assert _DEPLOYMENT_OBSERVED_AT_UTC <= _BOOT_TIMESTAMP_UTC
    assert _DEPLOYMENT_OBSERVED_AT_UTC <= _iso_utc(FIXED_NOW)


def test_generated_scenario_a_carries_the_coherent_timeline():
    """The actual generated snapshot/API body reflects the same coherent
    ordering, not merely the module-level constants in isolation."""
    results = generate_fixture_bundle(Path.cwd() / ".pytest_chronology_tmp")
    try:
        body = results["A_minimal_canonical"]["body"]
        generated_at = body["generated_at_utc"]
        deployment_observed_at = body["deployment_evidence"]["observed_at_utc"]
        assert deployment_observed_at <= generated_at
    finally:
        import shutil

        shutil.rmtree(Path.cwd() / ".pytest_chronology_tmp", ignore_errors=True)


# ── O-02W-D3-R1 Correction C — FastAPI reader restoration ──────────────────


def test_fetch_via_real_api_restores_the_exact_previous_reader(tmp_path: Path):
    sentinel_reader = SafeSnapshotReader(
        snapshot_path=tmp_path / "sentinel_snapshot.json",
        manifest_path=tmp_path / "sentinel_manifest.json",
    )
    api_app._reader = sentinel_reader
    try:
        scenario_dir = tmp_path / "scenario"
        gf._write_snapshot_and_manifest(
            scenario_dir,
            _minimal_inputs(),
            manifest_process_instance_id="inst-restore-check",
        )
        result = gf._fetch_via_real_api(scenario_dir)
        assert result["http_status"] == 200
        assert api_app.get_reader() is sentinel_reader
    finally:
        api_app._reader = SafeSnapshotReader()


def test_fetch_via_real_api_restores_the_previous_reader_even_if_the_request_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sentinel_reader = SafeSnapshotReader(
        snapshot_path=tmp_path / "sentinel_snapshot.json",
        manifest_path=tmp_path / "sentinel_manifest.json",
    )
    api_app._reader = sentinel_reader

    class _ExplodingTestClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            raise RuntimeError("simulated request-path failure")

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(gf, "TestClient", _ExplodingTestClient)

    try:
        scenario_dir = tmp_path / "scenario_raises"
        gf._write_snapshot_and_manifest(
            scenario_dir,
            _minimal_inputs(),
            manifest_process_instance_id="inst-restore-raise-check",
        )
        with pytest.raises(RuntimeError, match="simulated request-path failure"):
            gf._fetch_via_real_api(scenario_dir)
        assert api_app.get_reader() is sentinel_reader
    finally:
        api_app._reader = SafeSnapshotReader()


def test_fixture_generation_never_contaminates_a_later_api_test(tmp_path: Path):
    """Running the full cross-stack generator, then a plain API test against
    its own real (non-temporary-scenario) reader configuration afterward,
    must never observe the generator's last temporary scenario paths."""

    real_snapshot_path = tmp_path / "real_databases" / "operator_snapshot.json"
    real_manifest_path = tmp_path / "real_databases" / "operator_runtime_manifest.json"
    api_app.configure_reader(snapshot_path=real_snapshot_path, manifest_path=real_manifest_path)
    try:
        generate_fixture_bundle(tmp_path / "fixtures_out")

        # The generator must have restored api_app's reader back to the one
        # configured immediately above — never left pointed at the last
        # scenario's (now possibly-cleaned-up) temporary files.
        current_reader = api_app.get_reader()
        assert current_reader._snapshot_path == real_snapshot_path
        assert current_reader._manifest_path == real_manifest_path

        with gf.TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/snapshot")
        # MISSING, not a leftover scenario body — proves no contamination.
        assert response.status_code == 503
        assert response.json()["error_code"] == "SNAPSHOT_MISSING"
    finally:
        api_app._reader = SafeSnapshotReader()


def _minimal_inputs():
    from tests.test_operator_snapshot_builder import _inputs as _base_inputs

    return _base_inputs(now_fn=lambda: FIXED_NOW)
