"""tests/cross_stack/generate_fixtures.py — O-02W-D3 cross-stack fixture
generator.

Generates, for each mandatory compatibility scenario (mission §5 A-F), the
EXACT JSON body (plus HTTP status) that the real O-02W-D1 FastAPI process
returns for a snapshot produced through the real O-02W-C producer path
(``build_operator_snapshot`` + the real atomic writers) and read back
through the real ``SafeSnapshotReader``. No handwritten "golden" JSON is
committed — every fixture file is generated at test/CI time from the
production serialization/reader/API code, using only deterministic
passive fakes for the advisor-owned live references (never a real
exchange, never real credentials).

This module never imports ``core.advisor_loop``, never constructs a real
``MexcSimulator``/``WalletSync``/``RealAccountsObserver``, and never reads a
JSONL ledger.

Usage (CLI): ``python -m tests.cross_stack.generate_fixtures --out <dir>``
Programmatic: ``generate_fixture_bundle(Path(out_dir))``
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

from observability import operator_runtime_manifest as manifest_mod
from observability import operator_snapshot_builder as osb
from observability.operator_api import app as api_app
from observability.operator_api.reader import SafeSnapshotReader
from observability.source_evidence import DeploymentEvidence, SourceEvidence

# Reuse the already-existing, already-reviewed deterministic passive fakes
# from the O-02W-C producer test suite — never a second, competing fake
# model that could quietly drift from what the real tests already exercise.
from tests.test_operator_snapshot_builder import (  # noqa: E402
    _FakeDecisionPacket,
    _FakePosition,
    _FakeRealAccountsObserverConfiguredOk,
    _FakeSimulator,
    _FakeWallet,
)


def _iso_utc(ts: float) -> str:
    """Format a fixed epoch-seconds value as an ISO-8601 UTC string — the
    same format the real producer's own `_iso_utc()` emits. Never wall-clock
    time (O-02W-D3-R1 Correction B)."""

    return (
        _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


# ── O-02W-D3-R1 Correction B — one coherent deterministic fixture timeline ──
#
# The R0 harness used FIXED_NOW (2023-11-14T22:13:20Z, an arbitrary
# deterministic snapshot-generation instant) alongside hardcoded 2026-09-10
# deployment/boot evidence strings — years AFTER the snapshot clock. That is
# a scientifically incoherent payload: deployment/boot evidence can never be
# observed after the snapshot they describe was generated. Every deterministic
# fixture timestamp is now derived from ONE anchor (FIXED_NOW) so the
# ordering deployment-evidence-observation <= boot <= snapshot-generation
# always holds, with no real current time anywhere in this module.
FIXED_NOW = 1_700_000_000.0  # snapshot generation instant for every scenario
_BOOT_TIMESTAMP_UTC = _iso_utc(FIXED_NOW - 3600.0)  # 1h before snapshot generation
_DEPLOYMENT_OBSERVED_AT_UTC = _iso_utc(FIXED_NOW - 7200.0)  # 2h before snapshot generation
_DEPLOYMENT_EVIDENCE_REF = _dt.datetime.fromtimestamp(
    FIXED_NOW - 7200.0, tz=_dt.timezone.utc
).strftime("deploy-%Y%m%d-%H%M")

assert _BOOT_TIMESTAMP_UTC <= _iso_utc(FIXED_NOW), "boot time must precede snapshot generation"
assert _DEPLOYMENT_OBSERVED_AT_UTC <= _BOOT_TIMESTAMP_UTC, (
    "deployment-evidence observation must precede boot, which must precede snapshot generation"
)


class _CountingWallet:
    """A fail-if-called fake: any access to `get_balance()`/`capital_x`
    increments a counter, so scenario B can assert ZERO wallet access in
    UNKNOWN mode with genuine proof, not merely an absence of a crash."""

    def __init__(self) -> None:
        self.get_balance_calls = 0
        self.capital_x_reads = 0

    def get_balance(self) -> float:
        self.get_balance_calls += 1
        return 999999.0

    @property
    def capital_x(self) -> float:
        self.capital_x_reads += 1
        return 999999.0


def _source_evidence(**overrides: Any) -> SourceEvidence:
    base: Dict[str, Any] = dict(
        source_sha="deadbeefcafef00d",
        worktree_state="CLEAN",
        deployment_evidence=DeploymentEvidence(
            status="VERIFIED",
            source="deploy_tag",
            evidence_ref=_DEPLOYMENT_EVIDENCE_REF,
            observed_at_utc=_DEPLOYMENT_OBSERVED_AT_UTC,
        ),
        runtime_sha_evidence_status="CLAIMED_ONLY",
    )
    base.update(overrides)
    return SourceEvidence(**base)


def _write_snapshot_and_manifest(
    scenario_dir: Path,
    inputs: osb.OperatorSnapshotInputs,
    manifest_process_instance_id: str | None = None,
) -> Path:
    """Write the snapshot via the REAL builder + REAL atomic writer, and the
    manifest via the REAL manifest writer — no handwritten JSON anywhere in
    this function."""

    scenario_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = scenario_dir / "operator_snapshot.json"
    manifest_path = scenario_dir / "operator_runtime_manifest.json"

    writer = osb.OperatorSnapshotWriter(path=snapshot_path, min_interval_s=0.0)
    writer.maybe_refresh(inputs, force=True)

    manifest_mod.write_runtime_manifest(
        process_instance_id=manifest_process_instance_id or inputs.process_instance_id,
        source_sha=inputs.source_evidence.source_sha,
        pid=4242,
        path=manifest_path,
        now_fn=lambda: FIXED_NOW,
        boot_timestamp_utc=_BOOT_TIMESTAMP_UTC,
    )
    return scenario_dir


def _fetch_via_real_api(scenario_dir: Path) -> Dict[str, Any]:
    """Configure the REAL FastAPI app's reader at this scenario's temporary
    paths and issue a real in-process HTTP GET via `TestClient` — the exact
    boundary the real read-only API process serves in production, minus a
    public socket.

    O-02W-D3-R1 Correction C: test-isolated. The module-global
    ``observability.operator_api.app`` reader is a shared, process-wide
    singleton (the same one `configure_reader()`/`get_reader()` manage) —
    any caller that repoints it and never restores it leaves every LATER
    consumer of that module (a real API test running after this generator
    in the same interpreter) silently pointed at this scenario's temporary
    files. The previous reader is captured before mutation and restored in
    a ``finally`` block, so a raised exception during the request can never
    leave global API state contaminated for whatever runs next.
    """

    previous_reader = api_app.get_reader()
    reader = SafeSnapshotReader(
        snapshot_path=scenario_dir / "operator_snapshot.json",
        manifest_path=scenario_dir / "operator_runtime_manifest.json",
        now_fn=lambda: FIXED_NOW,
    )
    api_app._reader = reader  # same mechanism configure_reader() uses
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/snapshot")
        return {"http_status": response.status_code, "body": response.json()}
    finally:
        api_app._reader = previous_reader


# ── Scenario builders ───────────────────────────────────────────────────────


def _scenario_a_minimal_canonical(base_dir: Path) -> Dict[str, Any]:
    """A. Canonical minimal snapshot — CURRENT instance, one open position,
    one actionable decision, everything materializable this cycle."""

    sim = _FakeSimulator(
        positions={"BTC/USDT": _FakePosition("pos-a1", "BTC/USDT")},
        prices={"BTC/USDT": 51000.0},
    )
    inputs = osb.OperatorSnapshotInputs(
        cycle=7,
        process_instance_id="inst-scenario-a",
        source_evidence=_source_evidence(),
        mode="PAPER",
        mexc_simulator=sim,
        wallet_sync=_FakeWallet(balance=10000.0),
        ledger_trades=[],
        decisions=[
            osb.DecisionRecord(
                symbol="BTC/USDT",
                decision_packet=_FakeDecisionPacket(actionable=True),
                legacy_trade_allowed=True,
                legacy_first_blocker=None,
            )
        ],
        now_fn=lambda: FIXED_NOW,
    )
    scenario_dir = base_dir / "A_minimal_canonical"
    _write_snapshot_and_manifest(scenario_dir, inputs, manifest_process_instance_id="inst-scenario-a")
    return _fetch_via_real_api(scenario_dir)


def _scenario_b_unknown_mode_fail_closed(base_dir: Path) -> Dict[str, Any]:
    """B. UNKNOWN mode never queries wallet balance/capital_x — proven with
    a fail-if-called counting fake, not merely an absent crash."""

    wallet = _CountingWallet()
    inputs = osb.OperatorSnapshotInputs(
        cycle=3,
        process_instance_id="inst-scenario-b",
        source_evidence=_source_evidence(worktree_state="UNKNOWN"),
        mode="UNKNOWN",
        mexc_simulator=None,
        wallet_sync=wallet,
        ledger_trades=[],
        decisions=[],
        now_fn=lambda: FIXED_NOW,
    )
    scenario_dir = base_dir / "B_unknown_mode_fail_closed"
    _write_snapshot_and_manifest(scenario_dir, inputs, manifest_process_instance_id="inst-scenario-b")
    result = _fetch_via_real_api(scenario_dir)
    assert wallet.get_balance_calls == 0, "UNKNOWN mode must never call get_balance()"
    assert wallet.capital_x_reads == 0, "UNKNOWN mode must never read capital_x"
    result["_proof"] = {
        "wallet_get_balance_calls": wallet.get_balance_calls,
        "wallet_capital_x_reads": wallet.capital_x_reads,
    }
    return result


def _scenario_c_portfolio_semantics(base_dir: Path) -> Dict[str, Any]:
    """C. PAPER vs REAL account separation; unavailable price/PnL stay
    UNAVAILABLE, never fabricated."""

    sim = _FakeSimulator(
        positions={"ETH/USDT": _FakePosition("pos-c1", "ETH/USDT")},
        prices={"ETH/USDT": 0.0},  # 0.0 == unavailable price evidence, never a real zero price
    )
    inputs = osb.OperatorSnapshotInputs(
        cycle=11,
        process_instance_id="inst-scenario-c",
        source_evidence=_source_evidence(),
        mode="PAPER",
        mexc_simulator=sim,
        wallet_sync=_FakeWallet(balance=2500.0),
        ledger_trades=[],
        real_accounts_observer=_FakeRealAccountsObserverConfiguredOk(),
        decisions=[],
        now_fn=lambda: FIXED_NOW,
    )
    scenario_dir = base_dir / "C_portfolio_semantics"
    _write_snapshot_and_manifest(scenario_dir, inputs, manifest_process_instance_id="inst-scenario-c")
    return _fetch_via_real_api(scenario_dir)


def _scenario_d_decision_authority(base_dir: Path) -> Dict[str, Any]:
    """D. Decision authority mapping + a missing DecisionPacket failing
    closed to is_actionable=False."""

    inputs = osb.OperatorSnapshotInputs(
        cycle=5,
        process_instance_id="inst-scenario-d",
        source_evidence=_source_evidence(),
        mode="PAPER",
        mexc_simulator=None,
        wallet_sync=None,
        ledger_trades=[],
        decisions=[
            osb.DecisionRecord(
                symbol="BTC/USDT",
                decision_packet=_FakeDecisionPacket(actionable=True),
                legacy_trade_allowed=False,
                legacy_first_blocker="RISK_GATE",
            ),
            osb.DecisionRecord(
                symbol="ETH/USDT",
                decision_packet=None,  # missing packet -> fail-closed
                legacy_trade_allowed=None,
                legacy_first_blocker=None,
            ),
        ],
        now_fn=lambda: FIXED_NOW,
    )
    scenario_dir = base_dir / "D_decision_authority"
    _write_snapshot_and_manifest(scenario_dir, inputs, manifest_process_instance_id="inst-scenario-d")
    return _fetch_via_real_api(scenario_dir)


def _scenario_e_previous_instance(base_dir: Path) -> Dict[str, Any]:
    """E. A usable manifest naming a DIFFERENT process instance than the one
    that produced the snapshot -> LAST_KNOWN/PRODUCER_RESTARTED, never
    CURRENT_INSTANCE."""

    inputs = osb.OperatorSnapshotInputs(
        cycle=2,
        process_instance_id="inst-scenario-e-old",
        source_evidence=_source_evidence(),
        mode="PAPER",
        mexc_simulator=None,
        wallet_sync=_FakeWallet(balance=100.0),
        ledger_trades=[],
        decisions=[],
        now_fn=lambda: FIXED_NOW,
    )
    scenario_dir = base_dir / "E_previous_instance"
    # Manifest names a NEWER instance than the one that produced the snapshot.
    _write_snapshot_and_manifest(
        scenario_dir, inputs, manifest_process_instance_id="inst-scenario-e-new"
    )
    return _fetch_via_real_api(scenario_dir)


def _scenario_f_failure_honesty(base_dir: Path) -> Dict[str, Any]:
    """F. A malformed snapshot artifact (unsupported schema_version) must
    surface as the governed structured 503 — never HTTP 200 with fabricated
    or partial domains."""

    scenario_dir = base_dir / "F_failure_honesty"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = scenario_dir / "operator_snapshot.json"
    manifest_path = scenario_dir / "operator_runtime_manifest.json"

    # Built from a real snapshot, then a single field is corrupted — this
    # exercises the reader's real schema-value validation, not a
    # hand-shaped fixture designed to satisfy both sides.
    inputs = osb.OperatorSnapshotInputs(
        cycle=9,
        process_instance_id="inst-scenario-f",
        source_evidence=_source_evidence(),
        mode="PAPER",
        mexc_simulator=None,
        wallet_sync=None,
        ledger_trades=[],
        decisions=[],
        now_fn=lambda: FIXED_NOW,
    )
    snapshot = osb.build_operator_snapshot(inputs)
    snapshot["schema_version"] = "999.0.0"  # unsupported -> SNAPSHOT_UNSUPPORTED_SCHEMA_VERSION
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    manifest_mod.write_runtime_manifest(
        process_instance_id="inst-scenario-f",
        source_sha=inputs.source_evidence.source_sha,
        pid=4242,
        path=manifest_path,
        now_fn=lambda: FIXED_NOW,
        boot_timestamp_utc=_BOOT_TIMESTAMP_UTC,
    )
    return _fetch_via_real_api(scenario_dir)


_SCENARIOS = {
    "A_minimal_canonical": _scenario_a_minimal_canonical,
    "B_unknown_mode_fail_closed": _scenario_b_unknown_mode_fail_closed,
    "C_portfolio_semantics": _scenario_c_portfolio_semantics,
    "D_decision_authority": _scenario_d_decision_authority,
    "E_previous_instance": _scenario_e_previous_instance,
    "F_failure_honesty": _scenario_f_failure_honesty,
}


def generate_fixture_bundle(out_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Generate every scenario's producer/manifest artifacts under
    ``out_dir/_producer/<scenario>/`` and write the resulting exact API
    response (``{scenario}.json`` = ``{"http_status": ..., "body": ...}``)
    directly under ``out_dir`` — the ONLY files the frontend test reads.
    """

    out_dir = Path(out_dir)
    producer_dir = out_dir / "_producer"
    results: Dict[str, Dict[str, Any]] = {}
    for name, builder in _SCENARIOS.items():
        result = builder(producer_dir)
        results[name] = result
        (out_dir / f"{name}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output directory for generated fixtures")
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    generate_fixture_bundle(out_dir)
    print(f"[cross-stack] Generated {len(_SCENARIOS)} fixtures under {out_dir}")


if __name__ == "__main__":
    main()
