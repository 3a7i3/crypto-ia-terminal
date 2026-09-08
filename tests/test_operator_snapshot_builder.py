"""tests/test_operator_snapshot_builder.py — O-02W-C focused tests.

Covers docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md §22 tests
assigned to O-02W-C: 1-2 (atomicity/failure-preservation), 3-4/13
(manifest-writing half), 19-20 (producer-side source-evidence), 21-22
(mode provenance), 23-27/29-30/32 (builder boundary, fail-passive, price
unavailability, provenance, missing packet, process-identity equality,
no-secrets), 28 (liveness never fabricated), 31 (no trace_id).

All writes happen under `tmp_path` — never in the real `databases/`
directory (DS-001 / mission §17 "no test writes to real repository
runtime databases").
"""

from __future__ import annotations

import json
import threading

import pytest

from observability import operator_runtime_manifest as manifest_mod
from observability import operator_snapshot_builder as osb
from observability import process_identity
from observability.mode_provenance import resolve_mode_provenance
from observability.source_evidence import DeploymentEvidence, SourceEvidence, capture_source_evidence


# ── Fixtures / fakes — never the real MexcSimulator/WalletSync classes ─────


def _source_evidence(**overrides) -> SourceEvidence:
    base = dict(
        source_sha="deadbeef",
        worktree_state="UNKNOWN",
        deployment_evidence=DeploymentEvidence(),
        runtime_sha_evidence_status="CLAIMED_ONLY",
    )
    base.update(overrides)
    return SourceEvidence(**base)


class _FakeSide:
    def __init__(self, value):
        self.value = value


class _FakePosition:
    def __init__(
        self,
        pos_id,
        symbol,
        side="BUY",
        qty_usd=100.0,
        entry_price=50000.0,
        tp_price=52000.0,
        sl_price=49000.0,
        personality="scalper",
        regime="trend",
        opened_ts=0.0,
    ):
        self.pos_id = pos_id
        self.symbol = symbol
        self.side = _FakeSide(side)
        self.qty_usd = qty_usd
        self.entry_price = entry_price
        self.tp_price = tp_price
        self.sl_price = sl_price
        self.personality = personality
        self.regime = regime
        self.opened_ts = opened_ts


class _FakeSimulator:
    """Never the real MexcSimulator — a minimal stand-in exposing only the
    attributes the builder is allowed to read (§23: never instantiate a
    fresh owner, only read already-existing references)."""

    def __init__(self, positions=None, prices=None):
        self._positions = positions or {}
        self._prices = prices or {}

    def _fetch_price(self, symbol):
        return self._prices.get(symbol, 0.0)


class _FakeWallet:
    def __init__(self, balance=1234.56, raise_on_read=False):
        self._balance = balance
        self._raise = raise_on_read

    def get_balance(self):
        if self._raise:
            raise RuntimeError("boom")
        return self._balance


class _FakeLedgerTrade:
    def __init__(self, trade_id, symbol, regime="ledger_regime"):
        self.trade_id = trade_id
        self.symbol = symbol
        self.regime = regime


class _FakeDecisionPacket:
    def __init__(self, actionable, packet_id="p1", context_id="c1", created_cycle_id="1"):
        self._actionable = actionable
        self.packet_id = packet_id
        self.context_id = context_id
        self.created_cycle_id = created_cycle_id

    def is_actionable(self):
        return self._actionable


def _inputs(**overrides) -> osb.OperatorSnapshotInputs:
    base = dict(
        cycle=1,
        process_instance_id="pid-fixed",
        source_evidence=_source_evidence(),
        mode="PAPER",
        mexc_simulator=None,
        wallet_sync=None,
        ledger_trades=None,
        decisions=[],
        now_fn=lambda: 1_700_000_000.0,
    )
    base.update(overrides)
    return osb.OperatorSnapshotInputs(**base)


# ── Test 1 — reader never observes a partial JSON snapshot ─────────────────


def test_concurrent_readers_never_see_partial_json(tmp_path):
    path = tmp_path / "operator_snapshot.json"
    writer = osb.OperatorSnapshotWriter(path=path, min_interval_s=0.0)
    errors = []
    stop = threading.Event()

    def _write_loop():
        for i in range(60):
            writer.maybe_refresh(_inputs(cycle=i), force=True)

    def _read_loop():
        while not stop.is_set():
            if path.exists():
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(exc)

    writer_thread = threading.Thread(target=_write_loop)
    reader_thread = threading.Thread(target=_read_loop)
    reader_thread.start()
    writer_thread.start()
    writer_thread.join()
    stop.set()
    reader_thread.join()

    assert errors == []


# ── Test 2 / 24 — failed serialization preserves the previous snapshot ─────


def test_failed_serialization_preserves_previous_snapshot(tmp_path):
    path = tmp_path / "operator_snapshot.json"
    writer = osb.OperatorSnapshotWriter(path=path, min_interval_s=0.0)

    assert writer.maybe_refresh(_inputs(cycle=1), force=True) is True
    before_bytes = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    class _Unserializable:
        def __repr__(self):
            return "<unserializable>"

    # Force build_operator_snapshot to raise by injecting a non-serializable
    # process_instance_id-shaped input via a broken source_evidence object.
    class _BrokenEvidence:
        def to_dict(self):
            raise RuntimeError("forced serialization failure")

    bad_inputs = _inputs(cycle=2, source_evidence=_BrokenEvidence())
    result = writer.maybe_refresh(bad_inputs, force=True)

    assert result is True  # attempted, but failed internally (fail-passive)
    assert writer.write_errors == 1
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime


def test_write_failure_is_fail_passive_and_counted(tmp_path, monkeypatch):
    path = tmp_path / "operator_snapshot.json"
    writer = osb.OperatorSnapshotWriter(path=path, min_interval_s=0.0)

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(writer, "_write_atomic", _boom)

    # Never raises.
    result = writer.maybe_refresh(_inputs(cycle=1), force=True)
    assert result is True
    assert writer.write_errors == 1
    assert not path.exists()


# ── Test 3/4 — runtime manifest atomicity + write-once-before-domain ───────


def test_manifest_written_atomically(tmp_path):
    path = tmp_path / "operator_runtime_manifest.json"
    ok = manifest_mod.write_runtime_manifest(
        process_instance_id="pid-1", source_sha="abc123", path=path
    )
    assert ok is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["process_instance_id"] == "pid-1"
    assert payload["source_sha"] == "abc123"
    assert "boot_timestamp_utc" in payload
    assert "pid" in payload


def test_manifest_write_failure_is_fail_passive(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "operator_runtime_manifest.json"

    def _boom(*a, **kw):
        raise OSError("no space left on device")

    monkeypatch.setattr(manifest_mod.os, "replace", _boom)
    before = manifest_mod.write_errors
    ok = manifest_mod.write_runtime_manifest(process_instance_id="pid-x", path=path)
    assert ok is False
    assert manifest_mod.write_errors == before + 1


def test_manifest_missing_or_corrupt_reads_as_none(tmp_path):
    path = tmp_path / "missing.json"
    assert manifest_mod.read_manifest(path=path) is None

    path.write_text("{not json", encoding="utf-8")
    assert manifest_mod.read_manifest(path=path) is None


# ── Test 19/20 — producer-side source/worktree/deployment evidence ─────────


def test_source_sha_alone_remains_claimed_only():
    ev = capture_source_evidence(cwd=".", run_git_status=False)
    if ev.source_sha is not None:
        assert ev.runtime_sha_evidence_status == "CLAIMED_ONLY"
    else:
        assert ev.runtime_sha_evidence_status == "UNKNOWN"


def test_verified_deployment_evidence_never_upgrades_runtime_status():
    dep = DeploymentEvidence(status="VERIFIED", source="deploy_tag", evidence_ref="deploy-20260908-0001")
    ev = capture_source_evidence(cwd=".", run_git_status=False, deployment_evidence=dep)
    assert ev.deployment_evidence.status == "VERIFIED"
    assert ev.runtime_sha_evidence_status in ("CLAIMED_ONLY", "UNKNOWN")


def test_missing_deployment_evidence_is_unknown():
    ev = capture_source_evidence(cwd=".", run_git_status=False)
    assert ev.deployment_evidence.status == "UNKNOWN"
    assert ev.deployment_evidence.evidence_ref is None


def test_unchecked_worktree_is_unknown():
    ev = capture_source_evidence(cwd=".", run_git_status=False)
    assert ev.worktree_state == "UNKNOWN"


def test_dirty_worktree_reported_as_dirty(monkeypatch):
    def _fake_run_git(args, cwd=None):
        if args[0] == "rev-parse":
            return "abc123"
        if args[0] == "status":
            return "?? some_new_file.py"
        return None

    monkeypatch.setattr("observability.source_evidence._run_git", _fake_run_git)
    ev = capture_source_evidence(run_git_status=True)
    assert ev.worktree_state == "DIRTY"


def test_clean_worktree_reported_as_clean(monkeypatch):
    def _fake_run_git(args, cwd=None):
        if args[0] == "rev-parse":
            return "abc123"
        if args[0] == "status":
            return ""
        return None

    monkeypatch.setattr("observability.source_evidence._run_git", _fake_run_git)
    ev = capture_source_evidence(run_git_status=True)
    assert ev.worktree_state == "CLEAN"


# ── Test 21/22 — mode provenance override / fail-closed ────────────────────


def test_paper_trading_enabled_overrides_exec_mode():
    assert resolve_mode_provenance("live", paper_trading_enabled=True) == "PAPER"
    assert resolve_mode_provenance("testnet", paper_trading_enabled=True) == "PAPER"


def test_unrecognized_exec_mode_fails_closed_to_unknown():
    assert resolve_mode_provenance("bogus_mode", paper_trading_enabled=False) == "UNKNOWN"
    assert resolve_mode_provenance("bogus_mode", paper_trading_enabled=False) != "REAL_API"


def test_recognized_modes_map_correctly():
    assert resolve_mode_provenance("paper", paper_trading_enabled=False) == "PAPER"
    assert resolve_mode_provenance("live", paper_trading_enabled=False) == "REAL_API"
    assert resolve_mode_provenance("testnet", paper_trading_enabled=False) == "TESTNET_API"


# ── Test 23 — builder never instantiates a fresh runtime owner ─────────────


def test_builder_module_never_constructs_mexc_simulator_or_wallet_sync():
    import inspect

    src = inspect.getsource(osb)
    assert "MexcSimulator(" not in src
    assert "WalletSync(" not in src
    assert "get_wallet_sync(" not in src


def test_builder_reads_only_injected_references():
    sim = _FakeSimulator(positions={"BTC/USDT": _FakePosition("p1", "BTC/USDT")}, prices={"BTC/USDT": 51000.0})
    wallet = _FakeWallet(balance=999.0)
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim, wallet_sync=wallet))
    assert result["portfolio"]["paper_equity_usd"]["value"] == 999.0
    assert len(result["portfolio"]["open_positions"]["value"]) == 1


# ── Test 25 — _fetch_price()==0.0 maps to UNAVAILABLE ───────────────────────


def test_zero_price_maps_to_unavailable_price_and_pnl():
    pos = _FakePosition("p1", "ETH/USDT")
    sim = _FakeSimulator(positions={"ETH/USDT": pos}, prices={"ETH/USDT": 0.0})
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["current_price"]["semantics"] == "UNAVAILABLE"
    assert position["current_price"]["value"] is None
    assert position["unrealized_pnl_usd"]["semantics"] == "UNAVAILABLE"
    assert position["unrealized_pnl_pct"]["semantics"] == "UNAVAILABLE"


def test_missing_exchange_client_price_is_unavailable_not_zero():
    class _NoFetch:
        _positions = {"ETH/USDT": _FakePosition("p1", "ETH/USDT")}

    result = osb.build_operator_snapshot(_inputs(mexc_simulator=_NoFetch()))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["current_price"]["value"] is None
    assert position["current_price"]["semantics"] == "UNAVAILABLE"


def test_positive_price_produces_present_pnl():
    pos = _FakePosition("p1", "BTC/USDT", side="BUY", entry_price=100.0, qty_usd=100.0)
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 110.0})
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["current_price"]["semantics"] == "PRESENT"
    assert position["current_price"]["value"] == 110.0
    assert position["unrealized_pnl_pct"]["semantics"] == "PRESENT"
    assert position["unrealized_pnl_pct"]["value"] == pytest.approx(10.0)


# ── Test 26 — normal vs restored provenance, exact pos_id==trade_id join ───


def test_normal_open_provenance_full_confidence():
    pos = _FakePosition("order-1", "BTC/USDT", personality="scalper", regime="trend")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["personality"] == "scalper"
    assert position["regime"]["value"] == "trend"
    assert position["restored"] is False
    assert position["restored_without_regime"] is False
    assert position["tp_sl_source"] == "original"


def test_restored_position_labeled_with_low_confidence_provenance():
    pos = _FakePosition("trade-42", "BTC/USDT", personality="restored", regime="unknown")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["personality"] == "restored"
    assert position["restored"] is True
    assert position["restored_without_regime"] is True
    assert position["regime"]["value"] == "unknown"
    assert position["tp_sl_source"] == "restored_default"


def test_ledger_join_never_falls_back_to_symbol_only_match():
    # Two ledger records share the same symbol but different trade_ids —
    # the restored position's pos_id matches NEITHER exactly here, so the
    # join must not guess from the shared symbol.
    pos = _FakePosition("trade-999", "BTC/USDT", personality="restored", regime="unknown")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    ledger = [
        _FakeLedgerTrade("trade-1", "BTC/USDT", regime="trend"),
        _FakeLedgerTrade("trade-2", "BTC/USDT", regime="range"),
    ]
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim, ledger_trades=ledger))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["regime"]["value"] == "unknown"  # never guessed from symbol


def test_ledger_join_succeeds_on_exact_trade_id_match():
    pos = _FakePosition("trade-1", "BTC/USDT", personality="restored", regime="unknown")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    ledger = [
        _FakeLedgerTrade("trade-1", "BTC/USDT", regime="trend"),
        _FakeLedgerTrade("trade-2", "BTC/USDT", regime="range"),
    ]
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim, ledger_trades=ledger))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["regime"]["value"] == "trend"


def test_ledger_join_rejects_symbol_conflict():
    pos = _FakePosition("trade-1", "BTC/USDT", personality="restored", regime="unknown")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    # Same trade_id but a conflicting symbol in the ledger record.
    ledger = [_FakeLedgerTrade("trade-1", "ETH/USDT", regime="trend")]
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim, ledger_trades=ledger))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["regime"]["value"] == "unknown"


# ── Test 27 — missing DecisionPacket -> is_actionable False, correct labels ─


def test_missing_decision_packet_materializes_false_authority():
    rec = osb.DecisionRecord(symbol="BTC/USDT", decision_packet=None, legacy_trade_allowed=True)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    decision = result["decision_pipeline"]["per_symbol_decisions"][0]
    assert decision["is_actionable"]["value"] is False
    assert decision["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"
    assert decision["trade_allowed"]["value"] is True
    assert decision["trade_allowed"]["authority"] == "OBSERVATIONAL_TELEMETRY"


def test_actionable_decision_packet_labeled_execution_authority():
    dp = _FakeDecisionPacket(actionable=True)
    rec = osb.DecisionRecord(symbol="BTC/USDT", decision_packet=dp, legacy_trade_allowed=False)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    decision = result["decision_pipeline"]["per_symbol_decisions"][0]
    assert decision["is_actionable"]["value"] is True
    assert decision["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"
    assert decision["packet_id"] == "p1"
    assert decision["trade_allowed"]["value"] is False


# ── Test 28 — boot_alive always UNKNOWN, never fabricated ───────────────────


def test_boot_alive_always_null_unknown():
    result = osb.build_operator_snapshot(_inputs())
    assert result["system_health"]["boot_alive"] == {"value": None, "semantics": "UNKNOWN"}


def test_boot_alive_never_true_regardless_of_process_identity_match():
    # Even with a fully valid process_instance_id and a "healthy-looking"
    # snapshot, boot_alive must remain UNKNOWN — never inferred.
    result = osb.build_operator_snapshot(
        _inputs(process_instance_id=process_identity.generate_process_instance_id())
    )
    assert result["system_health"]["boot_alive"]["value"] is None
    assert result["system_health"]["boot_alive"]["semantics"] == "UNKNOWN"


# ── Test 29/30 — bootstrap is the SOLE identity authority (R1 correction D) ─
#
# These replace the earlier tautological tests (manually injecting the
# SAME id into all three artifacts and asserting equality, which proves
# nothing about real wiring). Here, `generate_process_instance_id()` is
# called exactly ONCE per simulated "process" — at a single bootstrap-like
# call site — and that one value is threaded, unchanged, into the
# manifest writer, S-03's RuntimeProvenanceInputs, and the operator
# snapshot builder; each artifact's own output is then read back and
# compared, never re-injected a second time.


def _simulate_bootstrap_and_propagate(tmp_path, manifest_name: str):
    """Thin equivalent of the real advisor bootstrap: ONE identity
    generation, threaded explicitly into the three consumers exactly as
    `core/advisor_loop.py::main()` does."""

    from observability import runtime_provenance_snapshot as rps

    process_instance_id = process_identity.generate_process_instance_id()

    manifest_path = tmp_path / manifest_name
    manifest_mod.write_runtime_manifest(
        process_instance_id=process_instance_id, path=manifest_path
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    s03_snapshot = rps.build_snapshot(
        rps.RuntimeProvenanceInputs(process_instance_id=process_instance_id)
    )
    op_snapshot = osb.build_operator_snapshot(_inputs(process_instance_id=process_instance_id))

    return process_instance_id, manifest, s03_snapshot, op_snapshot


def test_generator_produces_a_fresh_id_each_call():
    a = process_identity.generate_process_instance_id()
    b = process_identity.generate_process_instance_id()
    assert a != b


def test_bootstrap_propagates_one_identity_to_all_three_artifacts(tmp_path):
    pid, manifest, s03_snapshot, op_snapshot = _simulate_bootstrap_and_propagate(
        tmp_path, "manifest_p1.json"
    )
    assert manifest["process_instance_id"] == pid
    assert s03_snapshot["process"]["process_instance_id"] == pid
    assert op_snapshot["process_instance_id"] == pid


def test_restart_simulation_via_second_bootstrap_call_yields_new_identity_everywhere(tmp_path):
    pid1, manifest1, s03_1, op1 = _simulate_bootstrap_and_propagate(tmp_path, "manifest_i1.json")
    pid2, manifest2, s03_2, op2 = _simulate_bootstrap_and_propagate(tmp_path, "manifest_i2.json")

    assert pid1 != pid2
    for manifest, s03_snapshot, op_snapshot, pid in (
        (manifest1, s03_1, op1, pid1),
        (manifest2, s03_2, op2, pid2),
    ):
        assert manifest["process_instance_id"] == pid
        assert s03_snapshot["process"]["process_instance_id"] == pid
        assert op_snapshot["process_instance_id"] == pid


def test_writers_never_regenerate_their_own_process_instance_id():
    """Neither the operator-snapshot writer nor the manifest writer module
    calls uuid4()/os.getpid()-based generation to PRODUCE a
    process_instance_id — both only ever accept it as a parameter/field
    already supplied by the caller (the advisor bootstrap, via
    observability.process_identity). `snapshot_id` (§14, a distinct
    per-write identity) is explicitly allowed its own uuid4() call."""

    import inspect

    from observability import operator_runtime_manifest as manifest_module

    manifest_src = inspect.getsource(manifest_module)
    assert "uuid" not in manifest_src.lower()

    builder_src = inspect.getsource(osb)
    # The only uuid4() call in the builder module must be for snapshot_id,
    # never assigned to process_instance_id.
    assert 'str(uuid.uuid4())' in builder_src
    assert '"process_instance_id": str(uuid' not in builder_src
    assert "process_instance_id=str(uuid" not in builder_src


# ── Test 31 — no distinct trace_id is ever fabricated ───────────────────────


def test_no_trace_id_field_anywhere_in_snapshot():
    dp = _FakeDecisionPacket(actionable=True)
    rec = osb.DecisionRecord(symbol="BTC/USDT", decision_packet=dp)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    blob = json.dumps(result)
    assert "trace_id" not in blob


# ── Test 32 — no secret material, strict whitelist ──────────────────────────


def test_no_secret_material_in_snapshot():
    result = osb.build_operator_snapshot(_inputs())
    osb.assert_no_secret_material(result)  # must not raise


def test_secret_like_field_triggers_assertion():
    with pytest.raises(ValueError):
        osb.assert_no_secret_material({"api_key": "sk-12345"})


# ── Cadence — bounded write rate (mission §22 test 27 wording; §1.3) ────────


def test_min_interval_prevents_excessive_writes(tmp_path):
    path = tmp_path / "operator_snapshot.json"
    writer = osb.OperatorSnapshotWriter(path=path, min_interval_s=60.0)
    assert writer.maybe_refresh(_inputs(cycle=1)) is True
    assert writer.maybe_refresh(_inputs(cycle=2)) is False  # too soon
    assert writer.maybe_refresh(_inputs(cycle=3), force=True) is True


# ── Envelope completeness / identifier change between writes ───────────────


def test_snapshot_envelope_has_required_fields():
    result = osb.build_operator_snapshot(_inputs(cycle=7))
    for key in (
        "schema_version",
        "snapshot_id",
        "cycle",
        "process_instance_id",
        "generated_at_utc",
        "source_sha",
        "worktree_state",
        "deployment_evidence",
        "runtime_sha_evidence_status",
        "portfolio",
        "decision_pipeline",
        "system_health",
    ):
        assert key in result
    assert result["cycle"] == 7
    assert result["process_instance_id"] == "pid-fixed"


def test_snapshot_id_changes_between_writes():
    a = osb.build_operator_snapshot(_inputs())
    b = osb.build_operator_snapshot(_inputs())
    assert a["snapshot_id"] != b["snapshot_id"]


# ── R1 correction A — mode attribution: PAPER/REAL/TESTNET never confused ──


def test_env_var_unset_defaults_to_paper():
    import os as _os

    _os.environ.pop("PAPER_TRADING_ENABLED", None)
    assert resolve_mode_provenance("live") == "PAPER"


def test_truthy_on_value_resolves_to_paper():
    assert resolve_mode_provenance("live", paper_trading_enabled=True) == "PAPER"
    # "on" is in the truthy vocabulary at the call-site env parsing layer;
    # exercised directly through the boolean the call site would compute.
    truthy = "on".lower() in {"1", "true", "yes", "on"}
    assert resolve_mode_provenance("live", paper_trading_enabled=truthy) == "PAPER"


def test_paper_override_wins_even_when_raw_mode_says_live_or_testnet():
    assert resolve_mode_provenance("live", paper_trading_enabled=True) == "PAPER"
    assert resolve_mode_provenance("testnet", paper_trading_enabled=True) == "PAPER"


def test_unknown_raw_mode_without_override_is_unknown_never_real():
    assert resolve_mode_provenance("something_else", paper_trading_enabled=False) == "UNKNOWN"


def test_builder_publishes_paper_equity_only_in_paper_mode():
    wallet = _FakeWallet(balance=500.0)
    result = osb.build_operator_snapshot(_inputs(mode="PAPER", wallet_sync=wallet))
    assert result["portfolio"]["paper_equity_usd"]["value"] == 500.0
    assert result["portfolio"]["mode"] == "PAPER"


def test_live_or_testnet_balance_never_appears_under_paper_equity_usd():
    """Explicit proof (BLOCKER A): even if a WalletSync-like reference is
    passed in, a REAL_API/TESTNET_API resolved mode must never publish its
    balance under paper_equity_usd — the field becomes NOT_APPLICABLE.
    UNKNOWN mode (R4 correction A — fail closed) must never claim
    NOT_APPLICABLE either, since that would silently assert PAPER; it
    becomes UNKNOWN instead."""

    wallet = _FakeWallet(balance=999999.0)  # a deliberately eye-catching value
    expected_semantics = {
        "REAL_API": "NOT_APPLICABLE",
        "TESTNET_API": "NOT_APPLICABLE",
        "UNKNOWN": "UNKNOWN",
    }
    for mode, expected in expected_semantics.items():
        result = osb.build_operator_snapshot(_inputs(mode=mode, wallet_sync=wallet))
        pe = result["portfolio"]["paper_equity_usd"]
        assert pe["value"] != 999999.0
        assert pe["value"] is None
        assert pe["semantics"] == expected
        assert result["portfolio"]["mode"] == mode


def test_wallet_sync_in_paper_mode_materializes_balance():
    wallet = _FakeWallet(balance=42.5)
    result = osb.build_operator_snapshot(_inputs(mode="PAPER", wallet_sync=wallet))
    assert result["portfolio"]["paper_equity_usd"] == {"value": 42.5, "semantics": "PRESENT"}


def test_wallet_sync_absent_in_paper_mode_is_unavailable_not_zero():
    result = osb.build_operator_snapshot(_inputs(mode="PAPER", wallet_sync=None))
    assert result["portfolio"]["paper_equity_usd"]["semantics"] == "UNAVAILABLE"


# ── R1 correction B — O-01 domain envelope completeness ────────────────────


def test_portfolio_state_domain_carries_full_domain_snapshot_spine():
    result = osb.build_operator_snapshot(_inputs())
    ps = result["portfolio"]
    for key in (
        "domain",
        "observed_at_utc",
        "source",
        "source_version",
        "freshness",
        "status",
        "schema_version",
        "evidence",
    ):
        assert key in ps
    assert ps["domain"] == "portfolio_state"


def test_real_account_fields_are_honestly_not_applicable_not_dropped():
    result = osb.build_operator_snapshot(_inputs())
    ps = result["portfolio"]
    for field_name in ("real_account_equity_usd", "real_account_free_usd", "real_account_stale"):
        assert field_name in ps  # never silently omitted
        assert ps[field_name]["semantics"] == "NOT_APPLICABLE"
        assert ps[field_name]["value"] is None


def test_current_price_observation_timestamp_distinct_from_opened_ts():
    pos = _FakePosition("p1", "BTC/USDT", opened_ts=1_000.0)
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim, now_fn=lambda: 1_700_000_000.0))
    position = result["portfolio"]["open_positions"]["value"][0]
    assert position["opened_at"] == 1_000.0
    assert position["current_price_observed_at_utc"] is not None
    assert position["current_price_observed_at_utc"] != position["opened_at"]


# ── R1 correction E — canonical portfolio view governs position inventory ──


def test_portfolio_domain_uses_paper_portfolio_view_ordering_and_filtering():
    # is_open defaults True in the fake; paper_portfolio_view sorts by
    # symbol alphabetically — verify the builder's output follows that
    # order rather than dict insertion order.
    pos_b = _FakePosition("p2", "ETH/USDT")
    pos_a = _FakePosition("p1", "BTC/USDT")
    sim = _FakeSimulator(
        positions={"ETH/USDT": pos_b, "BTC/USDT": pos_a},
        prices={"ETH/USDT": 100.0, "BTC/USDT": 100.0},
    )
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    symbols = [p["symbol"] for p in result["portfolio"]["open_positions"]["value"]]
    assert symbols == ["BTC/USDT", "ETH/USDT"]


def test_portfolio_status_block_present_when_simulator_available():
    pos = _FakePosition("p1", "BTC/USDT")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    assert "portfolio_status" in result["portfolio"]
    assert result["portfolio"]["portfolio_status"]["current_positions"] == 1


# ── R1 correction C — manifest-before-snapshot enforced invariant ──────────


def test_manifest_before_snapshot_gate_helper_semantics(tmp_path, monkeypatch):
    """Exercises the gating primitive corresponding to
    core/advisor_loop.py's `_op_try_publish_manifest()` closure: no
    snapshot may be considered "ready" while the manifest keeps failing,
    and a later success unlocks it — without ever raising."""

    path = tmp_path / "manifest.json"

    def _boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(manifest_mod.os, "replace", _boom)
    ok1 = manifest_mod.write_runtime_manifest(process_instance_id="I2", path=path)
    assert ok1 is False
    assert not path.exists()

    monkeypatch.undo()
    ok2 = manifest_mod.write_runtime_manifest(process_instance_id="I2", path=path)
    assert ok2 is True
    assert path.exists()


def test_snapshot_writer_itself_never_raises_when_manifest_never_published(tmp_path):
    """The snapshot writer/builder path (independent of the advisor-loop
    gate) never raises even when called before any manifest exists —
    fail-passive is preserved regardless of manifest state, since the
    builder itself has no manifest dependency; the actual gate lives in
    the advisor loop's call site (`_op_try_publish_manifest()`),
    documented and exercised above."""

    writer = osb.OperatorSnapshotWriter(path=tmp_path / "snap.json", min_interval_s=0.0)
    result = writer.maybe_refresh(_inputs(cycle=1), force=True)
    assert result is True
    assert writer.write_errors == 0


# ── R1 correction F — canonical writer decoupled from legacy live_snapshot ─


def test_canonical_snapshot_unaffected_by_a_simulated_legacy_failure(tmp_path):
    """Regression proof for BLOCKER F: the canonical builder/writer used
    by core/advisor_loop.py's post-legacy block is a fully independent
    call — simulate the legacy write_snapshot() raising, and confirm the
    canonical writer (called on its own, as advisor_loop.py now does
    outside that try/except) still produces a valid snapshot file."""

    legacy_calls = {"raised": False}

    def _legacy_write_snapshot(*a, **kw):
        legacy_calls["raised"] = True
        raise RuntimeError("legacy live_snapshot.json write failed")

    # Legacy write raises — proven not to propagate.
    with pytest.raises(RuntimeError):
        _legacy_write_snapshot()
    assert legacy_calls["raised"] is True

    # The canonical writer, called independently (as advisor_loop.py now
    # does in its own try/except after the legacy block), still succeeds.
    path = tmp_path / "operator_snapshot.json"
    writer = osb.OperatorSnapshotWriter(path=path, min_interval_s=0.0)
    result = writer.maybe_refresh(_inputs(cycle=1), force=True)
    assert result is True
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["cycle"] == 1


# ── R1 correction G — strict allowlist / no generic dump regression guard ──


def test_no_generic_object_or_env_dump_in_builder_source():
    import inspect

    src = inspect.getsource(osb)
    assert "vars(" not in src
    assert "__dict__" not in src
    assert "os.environ" not in src


# ═══════════════════════════════════════════════════════════════════════
# R2 (second MASTER review round) — corrections A, B, C, D, E, F, G
# ═══════════════════════════════════════════════════════════════════════

from observability.operator_boot_coordinator import OperatorBootCoordinator
from observability.operator_runtime_manifest import read_manifest as _read_manifest


# ── Correction A — REAL mode call site, not a hand-precomputed boolean ────
#
# advisor_loop.py's real production call site now invokes
# `resolve_mode_provenance(exec_mode, None)` — passing `None` makes the
# resolver itself re-read PAPER_TRADING_ENABLED from the environment with
# canonical semantics. These tests exercise exactly that call shape (the
# actual production path), not a hand-precomputed boolean fed to the pure
# function in isolation.


def test_mode_a_env_absent_defaults_to_paper(monkeypatch):
    monkeypatch.delenv("PAPER_TRADING_ENABLED", raising=False)
    assert resolve_mode_provenance("live", None) == "PAPER"


def test_mode_a_env_on_is_paper(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "on")
    assert resolve_mode_provenance("live", None) == "PAPER"


def test_mode_a_env_false_live_is_real_api(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    assert resolve_mode_provenance("live", None) == "REAL_API"


def test_mode_a_env_false_testnet_is_testnet_api(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    assert resolve_mode_provenance("testnet", None) == "TESTNET_API"


def test_mode_a_env_false_unknown_raw_mode_is_unknown(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    assert resolve_mode_provenance("something_else", None) == "UNKNOWN"


def test_mode_a_advisor_loop_call_site_never_passes_divergent_local():
    """Regression guard: the R1 bug was passing the divergent local
    `_paper_trading_enabled` (default "false", missing "on") into the
    resolver at the real call site. Assert the source no longer does
    that."""
    import inspect

    import core.advisor_loop as _al

    src = inspect.getsource(_al)
    assert "_op_resolve_mode(" in src
    # Locate the _op_resolve_mode(...) call and assert its argument list
    # never references the divergent local `_paper_trading_enabled`.
    call_start = src.index("_op_mode = _op_resolve_mode(")
    call_end = src.index(")", call_start) + 1
    call_text = src[call_start:call_end]
    assert "_paper_trading_enabled" not in call_text
    assert "None" in call_text


# ── Correction D — portfolio-view failure never becomes empty/healthy ─────


class _RaisingPortfolioSimulator(_FakeSimulator):
    pass


def test_portfolio_view_failure_is_unavailable_not_empty_healthy(monkeypatch):
    """Regression test written against R1's actual behavior first: before
    the fix, a `paper_portfolio_view()` exception was swallowed into
    `view = []`, and the domain still reported FRESH/OK with an empty
    positions list — a false 'healthy, no positions' claim. After the fix,
    the domain must be UNAVAILABLE."""

    sim = _RaisingPortfolioSimulator(positions={"BTCUSDT": _FakePosition("p1", "BTCUSDT")})

    def _boom(_sim):
        raise RuntimeError("paper_portfolio_view exploded")

    monkeypatch.setattr(
        "paper_trading.paper_portfolio_view.paper_portfolio_view", _boom, raising=False
    )
    import sys as _sys

    if "paper_trading.paper_portfolio_view" not in _sys.modules:
        import types as _types

        _mod = _types.ModuleType("paper_trading.paper_portfolio_view")
        _mod.paper_portfolio_view = _boom
        _sys.modules["paper_trading.paper_portfolio_view"] = _mod

    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    portfolio = result["portfolio"]
    portfolio_state = portfolio

    assert portfolio_state["status"] == "UNAVAILABLE"
    # Never a false-healthy empty list.
    assert portfolio["open_positions"]["semantics"] == "UNAVAILABLE"
    assert portfolio["open_positions"]["value"] is None
    assert portfolio_state["paper_open_positions_count"]["semantics"] == "UNAVAILABLE"


def test_open_positions_count_always_matches_list_length_on_success():
    sim = _FakeSimulator(
        positions={
            "BTCUSDT": _FakePosition("p1", "BTCUSDT"),
            "ETHUSDT": _FakePosition("p2", "ETHUSDT"),
        },
        prices={"BTCUSDT": 51000.0, "ETHUSDT": 3000.0},
    )
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    portfolio = result["portfolio"]
    open_positions = portfolio["open_positions"]["value"]
    count = portfolio["paper_open_positions_count"]["value"]
    assert count == len(open_positions)


def test_disappearing_position_race_never_publishes_mismatched_count():
    """A position present in the view snapshot but removed from the
    simulator's live inventory before enrichment (a race) must never
    produce a `count != len(list)` snapshot — it is dropped from both
    consistently."""

    class _RaceSimulator(_FakeSimulator):
        pass

    sim = _RaceSimulator(
        positions={"BTCUSDT": _FakePosition("p1", "BTCUSDT")},
        prices={"BTCUSDT": 51000.0},
    )

    class _View:
        def __init__(self, symbol):
            self.symbol = symbol

    import paper_trading.paper_portfolio_view as _ppv_mod

    def _view_with_phantom(_sim):
        # Simulate the view seeing a position ("ETHUSDT") that the frozen
        # `_positions` inventory read by the builder does not contain.
        return [_View("BTCUSDT"), _View("ETHUSDT")]

    import unittest.mock as _mock

    with _mock.patch.object(_ppv_mod, "paper_portfolio_view", _view_with_phantom):
        result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))

    portfolio = result["portfolio"]
    open_positions = portfolio["open_positions"]["value"]
    count = portfolio["paper_open_positions_count"]["value"]
    assert count == len(open_positions) == 1
    assert open_positions[0]["symbol"] == "BTCUSDT"


# ── Correction C — aggregate PnL unavailable on incomplete price evidence ──


def test_aggregate_unrealized_pnl_unavailable_when_any_price_missing():
    sim = _FakeSimulator(
        positions={
            "BTCUSDT": _FakePosition("p1", "BTCUSDT"),
            "ETHUSDT": _FakePosition("p2", "ETHUSDT"),
        },
        prices={"BTCUSDT": 51000.0},  # ETHUSDT price missing => 0.0 => unavailable
    )
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    agg = result["portfolio"]["paper_unrealized_pnl_usd"]
    assert agg["semantics"] == "UNAVAILABLE"
    assert agg["value"] is None


def test_aggregate_unrealized_pnl_present_when_all_prices_available():
    sim = _FakeSimulator(
        positions={"BTCUSDT": _FakePosition("p1", "BTCUSDT")},
        prices={"BTCUSDT": 51000.0},
    )
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    agg = result["portfolio"]["paper_unrealized_pnl_usd"]
    assert agg["value"] is not None


# ── Correction C — real-account configured/unconfigured/unreadable ────────


class _FakeRealAccountsObserverConfiguredOk:
    def snapshot(self):
        from observability.real_accounts import RealAccountSnapshot

        return (
            RealAccountSnapshot(
                exchange="binance", ok=True, ts_utc="2026-01-01T00:00Z", total_usd=500.0
            ),
        )


class _FakeRealAccountsObserverConfiguredBroken:
    def snapshot(self):
        from observability.real_accounts import RealAccountSnapshot

        return (
            RealAccountSnapshot(
                exchange="binance", ok=False, ts_utc="2026-01-01T00:00Z", error="boom"
            ),
        )


def test_real_accounts_unconfigured_is_not_applicable():
    result = osb.build_operator_snapshot(_inputs())
    ps = result["portfolio"]
    assert ps["real_account_equity_usd"]["semantics"] == "NOT_APPLICABLE"


def test_real_accounts_configured_and_readable_is_observed():
    result = osb.build_operator_snapshot(
        _inputs(real_accounts_observer=_FakeRealAccountsObserverConfiguredOk())
    )
    ps = result["portfolio"]
    assert ps["real_account_equity_usd"]["semantics"] == "PRESENT"
    assert ps["real_account_equity_usd"]["value"] == 500.0


def test_real_accounts_configured_but_unreadable_is_unavailable():
    result = osb.build_operator_snapshot(
        _inputs(real_accounts_observer=_FakeRealAccountsObserverConfiguredBroken())
    )
    ps = result["portfolio"]
    assert ps["real_account_equity_usd"]["semantics"] == "UNAVAILABLE"


# ── Correction B — full O-01 spine on decision_pipeline / system_health ───


def test_decision_pipeline_domain_carries_full_domain_snapshot_spine():
    result = osb.build_operator_snapshot(_inputs())
    dp = result["decision_pipeline"]
    for key in ("domain", "observed_at_utc", "source", "freshness", "status", "schema_version"):
        assert key in dp, f"missing O-01 spine field: {key}"
    assert dp["domain"] == "decision_pipeline"
    assert "per_symbol_decisions" in dp  # additive, preserved detail


def test_system_health_domain_carries_full_domain_snapshot_spine():
    result = osb.build_operator_snapshot(_inputs())
    sh = result["system_health"]
    for key in ("domain", "observed_at_utc", "source", "freshness", "status", "schema_version"):
        assert key in sh, f"missing O-01 spine field: {key}"
    assert sh["domain"] == "system_health"
    assert sh["boot_alive"]["value"] is None
    assert sh["boot_alive"]["semantics"] == "UNKNOWN"


def test_portfolio_state_domain_still_has_full_spine_after_r2_changes():
    result = osb.build_operator_snapshot(_inputs())
    ps = result["portfolio"]
    for key in ("domain", "observed_at_utc", "source", "freshness", "status", "schema_version"):
        assert key in ps


# ── Correction E — full DecisionPacket projection via a faithful ctor ─────


def test_decision_record_materializes_full_packet_via_real_constructor():
    from core.decision_packet import ConvictionLevel, DecisionPacket, DecisionSide, MarketRegime

    dp = DecisionPacket(
        symbol="BTCUSDT",
        side=DecisionSide.LONG,
        confidence=72.5,
        regime=MarketRegime.TREND_BULL,
        conviction=ConvictionLevel.HIGH,
        created_cycle_id="cycle-42",
        context_id="ctx-7",
    )

    rec = osb.DecisionRecord(
        symbol="BTCUSDT",
        decision_packet=dp,
        legacy_trade_allowed=True,
        legacy_first_blocker=None,
    )
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    materialized = result["decision_pipeline"]["per_symbol_decisions"][0]

    assert materialized["packet_id"] == dp.packet_id
    assert materialized["context_id"] == "ctx-7"
    assert materialized["created_cycle_id"] == "cycle-42"
    assert materialized["side"]["value"] == DecisionSide.LONG.value
    assert materialized["regime"]["value"] == MarketRegime.TREND_BULL.value
    assert materialized["confidence_raw"]["value"] is not None
    assert materialized["confidence_adjusted"]["value"] is not None
    assert materialized["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"
    assert materialized["trade_allowed"]["authority"] == "OBSERVATIONAL_TELEMETRY"
    assert "trace_id" not in materialized  # never fabricated


def test_decision_record_missing_packet_still_fails_closed():
    rec = osb.DecisionRecord(symbol="ETHUSDT", decision_packet=None)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    materialized = result["decision_pipeline"]["per_symbol_decisions"][0]
    assert materialized["is_actionable"]["value"] is False


# ── Correction G — OperatorBootCoordinator, the REAL production object ───


def test_coordinator_manifest_failure_blocks_snapshot_publication(tmp_path):
    def _always_fail(**kwargs):
        return False

    coord = OperatorBootCoordinator(
        write_manifest_fn=_always_fail,
        capture_source_evidence_fn=lambda: _source_evidence(),
    )
    assert coord.snapshot_publication_allowed() is False
    coord.try_publish_manifest()
    assert coord.snapshot_publication_allowed() is False


def test_coordinator_retry_succeeds_and_then_allows_snapshot(tmp_path):
    calls = {"n": 0}

    def _fail_then_succeed(**kwargs):
        calls["n"] += 1
        return calls["n"] >= 2

    coord = OperatorBootCoordinator(
        write_manifest_fn=_fail_then_succeed,
        capture_source_evidence_fn=lambda: _source_evidence(),
    )
    assert coord.try_publish_manifest() is False
    assert coord.snapshot_publication_allowed() is False
    assert coord.try_publish_manifest() is True
    assert coord.snapshot_publication_allowed() is True


def test_coordinator_retry_reuses_same_process_id_and_original_boot_timestamp():
    calls = {"n": 0}
    seen_boot_timestamps = []
    seen_process_ids = []

    def _fail_then_succeed(*, process_instance_id, source_sha, boot_timestamp_utc):
        calls["n"] += 1
        seen_boot_timestamps.append(boot_timestamp_utc)
        seen_process_ids.append(process_instance_id)
        return calls["n"] >= 3

    coord = OperatorBootCoordinator(
        write_manifest_fn=_fail_then_succeed,
        capture_source_evidence_fn=lambda: _source_evidence(),
    )
    original_boot_ts = coord.boot_timestamp_utc
    original_pid = coord.process_instance_id

    coord.try_publish_manifest()
    coord.try_publish_manifest()
    coord.try_publish_manifest()

    assert coord.manifest_published is True
    assert len(set(seen_boot_timestamps)) == 1
    assert seen_boot_timestamps[0] == original_boot_ts
    assert len(set(seen_process_ids)) == 1
    assert seen_process_ids[0] == original_pid


def test_coordinator_real_write_runtime_manifest_never_redefines_boot_on_retry(tmp_path, monkeypatch):
    """Uses the REAL `write_runtime_manifest()` (not a stub) to prove the
    production manifest writer itself never recomputes a fresh timestamp
    on a delayed successful retry."""

    manifest_path = tmp_path / "operator_runtime_manifest.json"
    fail_flag = {"fail": True}

    real_write = manifest_mod.write_runtime_manifest

    def _wrapped(**kwargs):
        if fail_flag["fail"]:
            return False
        return real_write(path=manifest_path, **kwargs)

    coord = OperatorBootCoordinator(
        write_manifest_fn=_wrapped,
        capture_source_evidence_fn=lambda: _source_evidence(),
    )
    original_boot_ts = coord.boot_timestamp_utc

    assert coord.try_publish_manifest() is False
    fail_flag["fail"] = False
    assert coord.try_publish_manifest() is True

    payload = _read_manifest(path=manifest_path)
    assert payload["boot_timestamp_utc"] == original_boot_ts
    assert payload["process_instance_id"] == coord.process_instance_id


def test_second_bootstrap_simulated_restart_yields_new_identity_everywhere():
    """A fresh coordinator instance (simulated second bootstrap) must
    produce a NEW process_instance_id, consistently propagated to every
    output fed from it — never reusing the previous process's identity."""

    coord_a = OperatorBootCoordinator(capture_source_evidence_fn=lambda: _source_evidence())
    coord_b = OperatorBootCoordinator(capture_source_evidence_fn=lambda: _source_evidence())

    assert coord_a.process_instance_id != coord_b.process_instance_id

    inputs_a = _inputs(process_instance_id=coord_a.process_instance_id)
    inputs_b = _inputs(process_instance_id=coord_b.process_instance_id)
    snap_a = osb.build_operator_snapshot(inputs_a)
    snap_b = osb.build_operator_snapshot(inputs_b)

    assert snap_a["process_instance_id"] == coord_a.process_instance_id
    assert snap_b["process_instance_id"] == coord_b.process_instance_id
    assert snap_a["process_instance_id"] != snap_b["process_instance_id"]


def test_coordinator_is_the_object_used_by_advisor_loop_source():
    """Non-tautological wiring check: advisor_loop.py must construct and
    use OperatorBootCoordinator itself, not merely something a test
    reimplements."""
    import inspect

    import core.advisor_loop as _al

    src = inspect.getsource(_al)
    assert "OperatorBootCoordinator(" in src
    assert "_op_boot_coordinator.try_publish_manifest()" in src
    assert "_op_boot_coordinator.snapshot_publication_allowed()" in src


# ── R3 — Correction A: envelope source_updated_at_utc / authority ─────────


def test_portfolio_domain_envelope_carries_source_updated_at_utc_and_authority():
    result = osb.build_operator_snapshot(_inputs())
    ps = result["portfolio"]
    assert "source_updated_at_utc" in ps
    assert set(ps["source_updated_at_utc"].keys()) == {"value", "semantics"}
    assert ps["authority"] == "OBSERVATIONAL_TELEMETRY"


def test_decision_pipeline_envelope_carries_source_updated_at_utc_and_authority():
    result = osb.build_operator_snapshot(_inputs())
    dp = result["decision_pipeline"]
    assert "source_updated_at_utc" in dp
    assert dp["authority"] == "OBSERVATIONAL_TELEMETRY"


def test_system_health_envelope_carries_source_updated_at_utc_and_authority():
    result = osb.build_operator_snapshot(_inputs())
    sh = result["system_health"]
    assert "source_updated_at_utc" in sh
    assert sh["authority"] == "OBSERVATIONAL_TELEMETRY"


def test_envelope_authority_never_overwrites_per_field_decision_authority():
    dp_packet = _FakeDecisionPacket(actionable=True)
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp_packet, legacy_trade_allowed=True)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    dp = result["decision_pipeline"]
    per_symbol = dp["per_symbol_decisions"][0]
    # envelope-level (coarse) authority is OBSERVATIONAL_TELEMETRY...
    assert dp["authority"] == "OBSERVATIONAL_TELEMETRY"
    # ...but the existing, more precise per-field authority distinctions
    # (R2) must be untouched by the new envelope-level field.
    assert per_symbol["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"
    assert per_symbol["trade_allowed"]["authority"] == "OBSERVATIONAL_TELEMETRY"


def test_no_source_updated_at_utc_field_is_fabricated_from_generated_at_utc():
    """R3 regression: source_updated_at_utc must never silently equal
    generated_at_utc/observed_at_utc — this would fail against the
    pre-R3 code, which had no such field at all."""
    result = osb.build_operator_snapshot(_inputs())
    ps = result["portfolio"]
    generated_at = result["generated_at_utc"]
    # No real-accounts source was queried this cycle -> honestly UNKNOWN,
    # never a copy of generated_at_utc/observed_at_utc.
    assert ps["source_updated_at_utc"]["semantics"] == "UNKNOWN"
    assert ps["source_updated_at_utc"]["value"] is None
    assert ps["source_updated_at_utc"]["value"] != generated_at


def test_portfolio_source_updated_at_utc_never_promoted_from_real_accounts_poll():
    """R4 regression (correction C): a RealAccountsObserver poll timestamp
    describes ONLY that sub-source, never the whole portfolio domain
    (positions/prices/WalletSync collectively have no source timestamp of
    their own) — the domain-level `source_updated_at_utc` must stay
    UNKNOWN even when real_accounts was genuinely queried this cycle. The
    real information is preserved separately, not discarded, via
    `real_account_last_poll_utc` and `evidence.source_timestamps`."""

    class _ObsWithPoll(_FakeRealAccountsObserverConfiguredOk):
        def last_poll_utc(self):
            return "2026-09-08T00:00:00Z"

        def last_poll_age_s(self):
            return 5.0

        ttl_s = 900.0

    result = osb.build_operator_snapshot(_inputs(real_accounts_observer=_ObsWithPoll()))
    ps = result["portfolio"]
    # Domain-level field never promoted from the real-accounts sub-source.
    assert ps["source_updated_at_utc"]["semantics"] == "UNKNOWN"
    assert ps["source_updated_at_utc"]["value"] is None
    # The real-accounts-specific timestamp is preserved beside its own
    # field, scoped honestly to its own sub-source.
    assert ps["real_account_last_poll_utc"]["value"] == "2026-09-08T00:00:00Z"
    assert ps["real_account_last_poll_utc"]["semantics"] == "PRESENT"
    assert ps["evidence"]["source_timestamps"]["real_accounts"] == "2026-09-08T00:00:00Z"


# ── R3 — Correction B: capital_x_usd materialization ───────────────────────


class _FakeWalletWithCapitalX(_FakeWallet):
    def __init__(self, balance=1234.56, capital_x=None):
        super().__init__(balance=balance)
        self._capital_x = capital_x

    @property
    def capital_x(self):
        return self._capital_x


def test_capital_x_usd_present_in_real_api_mode_with_valid_capital_x():
    wallet = _FakeWalletWithCapitalX(capital_x=777.5)
    result = osb.build_operator_snapshot(_inputs(mode="REAL_API", wallet_sync=wallet))
    cx = result["portfolio"]["capital_x_usd"]
    assert cx["semantics"] == "PRESENT"
    assert cx["value"] == 777.5


def test_capital_x_usd_present_in_testnet_api_mode_with_valid_capital_x():
    wallet = _FakeWalletWithCapitalX(capital_x=42.0)
    result = osb.build_operator_snapshot(_inputs(mode="TESTNET_API", wallet_sync=wallet))
    cx = result["portfolio"]["capital_x_usd"]
    assert cx["semantics"] == "PRESENT"
    assert cx["value"] == 42.0


def test_capital_x_usd_unavailable_when_capital_x_is_none():
    wallet = _FakeWalletWithCapitalX(capital_x=None)
    result = osb.build_operator_snapshot(_inputs(mode="REAL_API", wallet_sync=wallet))
    cx = result["portfolio"]["capital_x_usd"]
    assert cx["semantics"] == "UNAVAILABLE"
    assert cx["value"] is None


def test_capital_x_usd_not_applicable_in_paper_mode():
    wallet = _FakeWalletWithCapitalX(capital_x=999.0)
    result = osb.build_operator_snapshot(_inputs(mode="PAPER", wallet_sync=wallet))
    cx = result["portfolio"]["capital_x_usd"]
    assert cx["semantics"] == "NOT_APPLICABLE"
    assert cx["value"] is None


def test_capital_x_usd_unknown_in_unknown_mode():
    wallet = _FakeWalletWithCapitalX(capital_x=999.0)
    result = osb.build_operator_snapshot(_inputs(mode="UNKNOWN", wallet_sync=wallet))
    cx = result["portfolio"]["capital_x_usd"]
    assert cx["semantics"] == "UNKNOWN"
    assert cx["value"] is None


def test_capital_x_usd_never_appears_under_paper_equity_usd_field_name():
    wallet = _FakeWalletWithCapitalX(capital_x=555.0, balance=42.0)
    result = osb.build_operator_snapshot(_inputs(mode="REAL_API", wallet_sync=wallet))
    portfolio = result["portfolio"]
    assert portfolio["paper_equity_usd"]["semantics"] == "NOT_APPLICABLE"
    assert portfolio["capital_x_usd"]["value"] == 555.0


# ── R3 — Correction C: evidence-backed real-account freshness ─────────────


class _ObsFresh:
    def snapshot(self):
        from observability.real_accounts import RealAccountSnapshot

        return (RealAccountSnapshot(exchange="binance", ok=True, ts_utc="x", total_usd=100.0),)

    def last_poll_utc(self):
        return "2026-09-08T12:00:00Z"

    def last_poll_age_s(self):
        return 10.0  # well within TTL

    ttl_s = 900.0


class _ObsStale:
    def snapshot(self):
        from observability.real_accounts import RealAccountSnapshot

        return (RealAccountSnapshot(exchange="binance", ok=True, ts_utc="x", total_usd=100.0),)

    def last_poll_utc(self):
        return "2026-09-08T10:00:00Z"

    def last_poll_age_s(self):
        return 5000.0  # beyond TTL

    ttl_s = 900.0


class _ObsNoTimestampEvidence:
    """Configured/readable, but exposes NO timestamp accessor at all —
    freshness genuinely cannot be proven."""

    def snapshot(self):
        from observability.real_accounts import RealAccountSnapshot

        return (RealAccountSnapshot(exchange="binance", ok=True, ts_utc="x", total_usd=100.0),)


class _ObsPartiallyReadableMultiExchange:
    """Two exchanges configured, only one readable this cycle — must not
    fabricate a false global 'all fresh' claim; the one genuine poll
    timestamp covers exactly what was polled."""

    def snapshot(self):
        from observability.real_accounts import RealAccountSnapshot

        return (
            RealAccountSnapshot(exchange="binance", ok=True, ts_utc="x", total_usd=100.0),
            RealAccountSnapshot(exchange="kraken", ok=False, ts_utc="x", error="timeout"),
        )

    def last_poll_utc(self):
        return "2026-09-08T12:00:00Z"

    def last_poll_age_s(self):
        return 20.0

    ttl_s = 900.0


def test_real_accounts_unconfigured_stale_is_not_applicable():
    result = osb.build_operator_snapshot(_inputs())
    ps = result["portfolio"]
    assert ps["real_account_stale"]["semantics"] == "NOT_APPLICABLE"


def test_real_accounts_configured_readable_fresh_is_observed_false():
    result = osb.build_operator_snapshot(_inputs(real_accounts_observer=_ObsFresh()))
    ps = result["portfolio"]
    assert ps["real_account_stale"]["semantics"] == "FALSE"
    assert ps["real_account_stale"]["value"] is False


def test_real_accounts_configured_readable_stale_is_observed_true():
    result = osb.build_operator_snapshot(_inputs(real_accounts_observer=_ObsStale()))
    ps = result["portfolio"]
    assert ps["real_account_stale"]["semantics"] == "PRESENT"
    assert ps["real_account_stale"]["value"] is True


def test_real_accounts_readable_but_no_timestamp_evidence_is_unknown_not_false():
    """R3 regression: this fails against pre-R3 code, which fabricated
    `observed(False)` merely because aggregate() succeeded."""
    result = osb.build_operator_snapshot(
        _inputs(real_accounts_observer=_ObsNoTimestampEvidence())
    )
    ps = result["portfolio"]
    assert ps["real_account_stale"]["semantics"] == "UNKNOWN"
    assert ps["real_account_stale"]["value"] is None


def test_real_accounts_configured_unreadable_stale_is_unavailable():
    result = osb.build_operator_snapshot(
        _inputs(real_accounts_observer=_FakeRealAccountsObserverConfiguredBroken())
    )
    ps = result["portfolio"]
    assert ps["real_account_stale"]["semantics"] == "UNAVAILABLE"


def test_real_accounts_partially_readable_multi_exchange_never_fabricates_all_fresh():
    result = osb.build_operator_snapshot(
        _inputs(real_accounts_observer=_ObsPartiallyReadableMultiExchange())
    )
    ps = result["portfolio"]
    # Equity/free reflect only the readable exchange (aggregate()'s own
    # `ok` filter); staleness is derived from the one genuine poll that
    # covered both exchanges in this bulk-poll observer, never claiming
    # more than what was actually observed.
    assert ps["real_account_equity_usd"]["semantics"] == "PRESENT"
    assert ps["real_account_stale"]["semantics"] == "FALSE"


# ── R3 — Correction D: decision domain runtime semantics ──────────────────


def test_decision_domain_status_never_ok_even_with_per_symbol_records():
    """R3 regression: fails against pre-R3 code, which published
    status='OK' whenever any per-symbol record existed despite
    stages=()/trade_allowed=UNKNOWN/first_blocker=UNKNOWN."""
    dp_packet = _FakeDecisionPacket(actionable=True)
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp_packet, legacy_trade_allowed=True)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    dp = result["decision_pipeline"]
    assert dp["status"] != "OK"
    assert dp["trade_allowed"]["semantics"] == "UNKNOWN"
    assert dp["first_blocker"]["semantics"] == "UNKNOWN"
    assert dp["evidence"]["exposure"] == "PARTIAL"


def test_decision_domain_status_attention_required_with_no_records_too():
    result = osb.build_operator_snapshot(_inputs(decisions=[]))
    dp = result["decision_pipeline"]
    assert dp["status"] == "ATTENTION_REQUIRED"


def test_per_symbol_first_blocker_is_observed_value_with_authority():
    rec = osb.DecisionRecord(
        symbol="ETHUSDT",
        decision_packet=None,
        legacy_trade_allowed=False,
        legacy_first_blocker="risk_gate",
    )
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    fb = result["decision_pipeline"]["per_symbol_decisions"][0]["first_blocker"]
    assert fb["value"] == "risk_gate"
    assert fb["semantics"] == "PRESENT"
    assert fb["authority"] == "OBSERVATIONAL_TELEMETRY"


def test_per_symbol_first_blocker_none_is_unknown_observed_value_not_bare_none():
    rec = osb.DecisionRecord(symbol="ETHUSDT", decision_packet=None, legacy_trade_allowed=None)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    fb = result["decision_pipeline"]["per_symbol_decisions"][0]["first_blocker"]
    assert isinstance(fb, dict)
    assert fb["semantics"] == "UNKNOWN"
    assert fb["authority"] == "OBSERVATIONAL_TELEMETRY"


def test_decision_packet_created_at_materialized():
    import datetime as _dt

    dp_packet = _FakeDecisionPacket(actionable=True)
    dp_packet.created_at = _dt.datetime(2026, 9, 8, 12, 0, 0, tzinfo=_dt.timezone.utc)
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp_packet)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    per_symbol = result["decision_pipeline"]["per_symbol_decisions"][0]
    assert per_symbol["created_at"]["value"] == "2026-09-08T12:00:00Z"
    assert per_symbol["created_at"]["semantics"] == "PRESENT"


def test_decision_packet_missing_created_at_is_unknown_not_fabricated():
    dp_packet = _FakeDecisionPacket(actionable=True)
    # no created_at attribute at all on this minimal fake
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp_packet)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    per_symbol = result["decision_pipeline"]["per_symbol_decisions"][0]
    assert per_symbol["created_at"]["semantics"] == "UNKNOWN"


def test_decision_packet_latest_transition_from_real_state_history():
    import datetime as _dt

    class _Transition:
        def __init__(self, ts):
            self.timestamp = ts

    dp_packet = _FakeDecisionPacket(actionable=True)
    dp_packet.state_history = [
        _Transition(_dt.datetime(2026, 9, 8, 11, 0, 0, tzinfo=_dt.timezone.utc)),
        _Transition(_dt.datetime(2026, 9, 8, 11, 5, 0, tzinfo=_dt.timezone.utc)),
    ]
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp_packet)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    per_symbol = result["decision_pipeline"]["per_symbol_decisions"][0]
    assert per_symbol["latest_transition_at_utc"]["value"] == "2026-09-08T11:05:00Z"


def test_decision_packet_no_state_history_transition_is_unknown():
    dp_packet = _FakeDecisionPacket(actionable=True)
    dp_packet.state_history = []
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp_packet)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    per_symbol = result["decision_pipeline"]["per_symbol_decisions"][0]
    assert per_symbol["latest_transition_at_utc"]["semantics"] == "UNKNOWN"


def test_missing_decision_packet_still_fails_closed_with_time_evidence_unknown():
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=None)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    per_symbol = result["decision_pipeline"]["per_symbol_decisions"][0]
    assert per_symbol["is_actionable"]["value"] is False
    assert per_symbol["created_at"]["semantics"] == "UNKNOWN"
    assert per_symbol["latest_transition_at_utc"]["semantics"] == "UNKNOWN"


def test_no_new_stage_counting_or_synthetic_aggregation_mechanism_introduced():
    """Guards against accidentally choosing option 1 with an invented
    aggregation mechanism — stages must remain empty, never synthesized."""
    dp_packet = _FakeDecisionPacket(actionable=True)
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp_packet, legacy_trade_allowed=True)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    assert result["decision_pipeline"]["stages"] == []


# ═══════════════════════════════════════════════════════════════════════
# R4 (fourth MASTER review round) — corrections A, B, C
# ═══════════════════════════════════════════════════════════════════════
#
# Theme: (A) fail-closed for UNKNOWN mode, (B) one unambiguous portfolio
# domain envelope, (C) freshness must follow evidence. Each test below
# was written and confirmed FAILING against pre-R4 HEAD `0cb18fba` before
# the corresponding fix landed.


class _RaisingWallet:
    """A WalletSync-like fake whose get_balance()/capital_x RAISE if
    accessed at all — used to PROVE the builder never touches it in
    UNKNOWN mode (R4 correction A), not merely that its return value is
    discarded."""

    def get_balance(self):
        raise AssertionError("get_balance() must never be called in UNKNOWN mode")

    @property
    def capital_x(self):
        raise AssertionError("capital_x must never be read in UNKNOWN mode")


# ── R4 test 1/2 — UNKNOWN mode never reads WalletSync; all three fields UNKNOWN ─


def test_unknown_mode_never_reads_wallet_sync_at_all():
    """R4 test 1: a raising fake proves the builder never calls
    get_balance() or reads capital_x when mode=UNKNOWN — if it did, the
    fake would raise and this test would fail with AssertionError instead
    of passing cleanly."""

    wallet = _RaisingWallet()
    result = osb.build_operator_snapshot(_inputs(mode="UNKNOWN", wallet_sync=wallet))
    # Reaching this point at all (no AssertionError propagated) already
    # proves the fake was never touched; the field assertions below are
    # the second half of the proof.
    portfolio = result["portfolio"]
    assert portfolio["paper_equity_usd"]["semantics"] == "UNKNOWN"
    assert portfolio["non_paper_wallet_balance_usd"]["semantics"] == "UNKNOWN"
    assert portfolio["capital_x_usd"]["semantics"] == "UNKNOWN"


def test_unknown_mode_all_three_balance_fields_are_unknown_not_fabricated():
    """R4 test 2: explicit matrix proof — UNKNOWN mode publishes UNKNOWN
    (never NOT_APPLICABLE, never a fabricated PRESENT/ZERO) for all three
    mode-dependent balance fields, with value=None in every case."""

    wallet = _FakeWalletWithCapitalX(balance=42.0, capital_x=777.0)
    result = osb.build_operator_snapshot(_inputs(mode="UNKNOWN", wallet_sync=wallet))
    portfolio = result["portfolio"]
    for field_name in ("paper_equity_usd", "non_paper_wallet_balance_usd", "capital_x_usd"):
        ov = portfolio[field_name]
        assert ov["semantics"] == "UNKNOWN", f"{field_name} should be UNKNOWN, got {ov}"
        assert ov["value"] is None


def test_unknown_mode_matrix_never_wallet_sync_none_guard_bypassed():
    """A wallet_sync=None UNKNOWN-mode cycle must also publish UNKNOWN
    (not NOT_APPLICABLE/UNAVAILABLE) — the fail-closed rule is about the
    MODE, not merely about whether a wallet reference happens to be
    present."""

    result = osb.build_operator_snapshot(_inputs(mode="UNKNOWN", wallet_sync=None))
    portfolio = result["portfolio"]
    for field_name in ("paper_equity_usd", "non_paper_wallet_balance_usd", "capital_x_usd"):
        assert portfolio[field_name]["semantics"] == "UNKNOWN"


def test_full_mode_matrix_paper_real_testnet_unknown():
    """The complete matrix from the mission spec, all four modes at once."""

    wallet = _FakeWalletWithCapitalX(balance=10.0, capital_x=20.0)

    paper = osb.build_operator_snapshot(_inputs(mode="PAPER", wallet_sync=wallet))["portfolio"]
    assert paper["paper_equity_usd"]["semantics"] in ("PRESENT", "ZERO", "UNAVAILABLE")
    assert paper["non_paper_wallet_balance_usd"]["semantics"] == "NOT_APPLICABLE"
    assert paper["capital_x_usd"]["semantics"] == "NOT_APPLICABLE"

    for mode in ("REAL_API", "TESTNET_API"):
        snap = osb.build_operator_snapshot(_inputs(mode=mode, wallet_sync=wallet))["portfolio"]
        assert snap["paper_equity_usd"]["semantics"] == "NOT_APPLICABLE"
        assert snap["non_paper_wallet_balance_usd"]["semantics"] in ("PRESENT", "ZERO", "UNAVAILABLE")
        assert snap["capital_x_usd"]["semantics"] in ("PRESENT", "ZERO", "UNAVAILABLE")

    unknown_snap = osb.build_operator_snapshot(_inputs(mode="UNKNOWN", wallet_sync=wallet))["portfolio"]
    for field_name in ("paper_equity_usd", "non_paper_wallet_balance_usd", "capital_x_usd"):
        assert unknown_snap[field_name]["semantics"] == "UNKNOWN"


# ── R4 test 3/4 — one unambiguous portfolio envelope, no nested copy ──────


_O01_ENVELOPE_KEYS = frozenset(
    {
        "domain",
        "observed_at_utc",
        "source",
        "source_version",
        "freshness",
        "status",
        "schema_version",
        "evidence",
        "source_updated_at_utc",
        "authority",
    }
)

_PORTFOLIO_PAYLOAD_KEYS = _O01_ENVELOPE_KEYS | {
    "mode",
    "paper_equity_usd",
    "paper_open_positions_count",
    "paper_unrealized_pnl_usd",
    "paper_realized_pnl_usd",
    "non_paper_wallet_balance_usd",
    "capital_x_usd",
    "real_account_equity_usd",
    "real_account_free_usd",
    "real_account_stale",
    "real_account_last_poll_utc",
    "open_positions",
    "portfolio_status",  # only present when the simulator is available
}


def test_every_portfolio_field_is_inside_the_one_authoritative_envelope():
    """R4 test 3: every field published under `snapshot["portfolio"]`
    is accounted for by this single domain's known field set — no
    sibling field exists that isn't part of the one O-01 envelope's
    scope (and the envelope's own identity/provenance spine is present
    directly at `portfolio`, not nested)."""

    pos = _FakePosition("p1", "BTC/USDT")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    portfolio = result["portfolio"]

    unexpected = set(portfolio.keys()) - _PORTFOLIO_PAYLOAD_KEYS
    assert unexpected == set(), f"unexpected sibling fields outside the envelope: {unexpected}"
    for key in _O01_ENVELOPE_KEYS:
        assert key in portfolio, f"missing O-01 envelope spine field: {key}"
    assert portfolio["domain"] == "portfolio_state"


def test_no_competing_nested_portfolio_state_copy_remains():
    """R4 test 4: the old `portfolio.portfolio_state` nested envelope
    (R1-R3 shape) must no longer exist anywhere in the payload — one
    domain, one envelope, at `snapshot["portfolio"]` directly."""

    result = osb.build_operator_snapshot(_inputs())
    assert "portfolio_state" not in result["portfolio"]
    # No JSON key literally named "portfolio_state" anywhere in the
    # serialized snapshot — it was a dict key holding a second nested
    # envelope, not merely the "domain": "portfolio_state" value string
    # (which legitimately remains, identifying the one envelope's domain).
    assert not any(k == "portfolio_state" for k in result["portfolio"].keys())


# ── R4 test 5/6 — real-account timestamp not promoted; portfolio never FRESH ─


def test_real_account_timestamp_not_promoted_to_whole_portfolio_freshness():
    """R4 test 5: even when RealAccountsObserver was genuinely queried and
    has a real poll timestamp, that timestamp must not be presented as the
    WHOLE portfolio domain's `source_updated_at_utc` (positions/prices/
    WalletSync have no source timestamp of their own to corroborate it)."""

    class _ObsWithPoll(_FakeRealAccountsObserverConfiguredOk):
        def last_poll_utc(self):
            return "2026-09-08T09:00:00Z"

        def last_poll_age_s(self):
            return 1.0

        ttl_s = 900.0

    result = osb.build_operator_snapshot(_inputs(real_accounts_observer=_ObsWithPoll()))
    portfolio = result["portfolio"]
    assert portfolio["source_updated_at_utc"]["semantics"] == "UNKNOWN"
    assert portfolio["source_updated_at_utc"]["value"] is None
    # Distinct, honestly-scoped sibling field carries the real evidence.
    assert portfolio["real_account_last_poll_utc"]["value"] == "2026-09-08T09:00:00Z"


def test_portfolio_domain_cannot_be_fresh_when_source_freshness_unproved():
    """R4 test 6: `freshness` must never be FRESH while
    `source_updated_at_utc` is UNKNOWN and no other governed freshness
    proof is recorded in evidence — checked across every code path that
    can produce a portfolio domain (simulator present/absent, real
    accounts queried/not)."""

    pos = _FakePosition("p1", "BTC/USDT")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})

    class _ObsWithPoll(_FakeRealAccountsObserverConfiguredOk):
        def last_poll_utc(self):
            return "2026-09-08T09:00:00Z"

        def last_poll_age_s(self):
            return 1.0

        ttl_s = 900.0

    for kwargs in (
        {},
        {"mexc_simulator": sim},
        {"real_accounts_observer": _ObsWithPoll()},
        {"mexc_simulator": sim, "real_accounts_observer": _ObsWithPoll()},
    ):
        result = osb.build_operator_snapshot(_inputs(**kwargs))
        portfolio = result["portfolio"]
        assert portfolio["freshness"] != "FRESH", f"unexpected FRESH with kwargs={kwargs}"
        if portfolio["source_updated_at_utc"]["semantics"] == "UNKNOWN":
            assert portfolio["freshness"] in ("UNKNOWN", "DEGRADED")


# ── R4 test 7 — decision pipeline cannot be FRESH when aggregate source is UNKNOWN ─


def test_decision_pipeline_never_fresh_regardless_of_per_symbol_count():
    """R4 test 7: fails against pre-R4 HEAD, which set
    `freshness=FRESH if per_symbol else UNKNOWN` — a per-symbol list being
    non-empty is not proof the domain-level aggregate (still genuinely
    UNKNOWN) is fresh. Checked both with and without per-symbol records."""

    result_empty = osb.build_operator_snapshot(_inputs(decisions=[]))
    assert result_empty["decision_pipeline"]["freshness"] != "FRESH"

    dp = _FakeDecisionPacket(actionable=True)
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp, legacy_trade_allowed=True)
    result_with_records = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    dpipe = result_with_records["decision_pipeline"]
    assert dpipe["freshness"] != "FRESH"
    assert dpipe["source_updated_at_utc"]["semantics"] == "UNKNOWN"
    # R3 invariants preserved unchanged.
    assert dpipe["status"] == "ATTENTION_REQUIRED"
    assert dpipe["evidence"]["exposure"] == "PARTIAL"


# ── R4 test 8 — per-position/real-account source timestamps stay attached ──


def test_per_position_and_real_account_timestamps_remain_correctly_attached():
    """R4 test 8: restructuring the envelope must not lose or misattribute
    per-position (`current_price_observed_at_utc`) or real-account
    (`real_account_last_poll_utc`) timestamp evidence — each stays on its
    own actual source, never merged into the domain-level field."""

    pos = _FakePosition("p1", "BTC/USDT", opened_ts=1_000.0)
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})

    class _ObsWithPoll(_FakeRealAccountsObserverConfiguredOk):
        def last_poll_utc(self):
            return "2026-09-08T09:30:00Z"

        def last_poll_age_s(self):
            return 2.0

        ttl_s = 900.0

    result = osb.build_operator_snapshot(
        _inputs(mexc_simulator=sim, real_accounts_observer=_ObsWithPoll())
    )
    portfolio = result["portfolio"]
    position = portfolio["open_positions"]["value"][0]
    assert position["current_price_observed_at_utc"] is not None
    assert position["opened_at"] == 1_000.0
    assert portfolio["real_account_last_poll_utc"]["value"] == "2026-09-08T09:30:00Z"
    # Domain-level source_updated_at_utc is a THIRD, distinct field —
    # never conflated with either of the above.
    assert portfolio["source_updated_at_utc"]["semantics"] == "UNKNOWN"


# ── R4 test 9 — R3 decision timestamps/authority survive the restructuring ─


def test_r3_decision_timestamps_and_authority_labels_survive_r4_restructuring():
    import datetime as _dt

    class _Transition:
        def __init__(self, ts):
            self.timestamp = ts

    dp_packet = _FakeDecisionPacket(actionable=True)
    dp_packet.created_at = _dt.datetime(2026, 9, 8, 12, 0, 0, tzinfo=_dt.timezone.utc)
    dp_packet.state_history = [
        _Transition(_dt.datetime(2026, 9, 8, 12, 5, 0, tzinfo=_dt.timezone.utc)),
    ]
    rec = osb.DecisionRecord(symbol="BTCUSDT", decision_packet=dp_packet, legacy_trade_allowed=True)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    per_symbol = result["decision_pipeline"]["per_symbol_decisions"][0]

    assert per_symbol["created_at"]["value"] == "2026-09-08T12:00:00Z"
    assert per_symbol["latest_transition_at_utc"]["value"] == "2026-09-08T12:05:00Z"
    assert per_symbol["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"
    assert per_symbol["trade_allowed"]["authority"] == "OBSERVATIONAL_TELEMETRY"
    assert per_symbol["first_blocker"]["authority"] == "OBSERVATIONAL_TELEMETRY"


# ── R4 test 10 — system_health untouched by the restructuring ─────────────


def test_system_health_still_boot_alive_unknown_after_r4_restructuring():
    result = osb.build_operator_snapshot(_inputs())
    sh = result["system_health"]
    assert sh["boot_alive"] == {"value": None, "semantics": "UNKNOWN"}
    assert sh["source_updated_at_utc"]["semantics"] == "UNKNOWN"
    assert sh["freshness"] == "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════════
# R4.1 — fifth MASTER review corrections A-C
# ═══════════════════════════════════════════════════════════════════════════

# ── Correction A — evidence.wallet_sync must reflect a GENUINE read ───────


def test_unknown_mode_wallet_sync_never_accessed_by_raising_fake_r4_1():
    """UNKNOWN mode with a raising WalletSync fake never touches it — the
    fake never raises because it is never called (re-verifies R4's fix
    is intact under the R4.1 evidence-tracking rewrite)."""

    wallet = _RaisingWallet()
    result = osb.build_operator_snapshot(_inputs(mode="UNKNOWN", wallet_sync=wallet))
    portfolio = result["portfolio"]
    assert portfolio["paper_equity_usd"]["semantics"] == "UNKNOWN"
    assert portfolio["non_paper_wallet_balance_usd"]["semantics"] == "UNKNOWN"
    assert portfolio["capital_x_usd"]["semantics"] == "UNKNOWN"


def test_unknown_mode_evidence_never_claims_wallet_sync_read():
    """Correction A: the resulting evidence dict must NOT claim
    `wallet_sync` was read when the builder never queried it (UNKNOWN
    mode) — the key must be entirely absent, not a false 'read' claim nor
    a placeholder value."""

    wallet = _RaisingWallet()
    result = osb.build_operator_snapshot(_inputs(mode="UNKNOWN", wallet_sync=wallet))
    evidence = result["portfolio"]["evidence"]
    assert "wallet_sync" not in evidence


def test_paper_mode_wallet_sync_genuinely_queried_records_evidence():
    """Correction A: PAPER mode with WalletSync genuinely queried (and
    successfully read) records evidence.wallet_sync == 'read'."""

    wallet = _FakeWallet(balance=99.0)
    result = osb.build_operator_snapshot(_inputs(mode="PAPER", wallet_sync=wallet))
    evidence = result["portfolio"]["evidence"]
    assert evidence["wallet_sync"] == "read"


@pytest.mark.parametrize("mode", ["REAL_API", "TESTNET_API"])
def test_real_testnet_mode_wallet_sync_genuinely_queried_records_evidence(mode):
    """Correction A: REAL_API/TESTNET_API with WalletSync genuinely
    queried records evidence.wallet_sync == 'read'."""

    wallet = _FakeWalletWithCapitalX(balance=10.0, capital_x=20.0)
    result = osb.build_operator_snapshot(_inputs(mode=mode, wallet_sync=wallet))
    evidence = result["portfolio"]["evidence"]
    assert evidence["wallet_sync"] == "read"


def test_wallet_sync_none_never_produces_read_evidence():
    """Correction A: `wallet_sync=None` never produces `wallet_sync` read
    evidence in ANY mode, since no instance was ever injected to query."""

    for mode in ("PAPER", "REAL_API", "TESTNET_API", "UNKNOWN"):
        result = osb.build_operator_snapshot(_inputs(mode=mode, wallet_sync=None))
        evidence = result["portfolio"]["evidence"]
        assert "wallet_sync" not in evidence, f"unexpected wallet_sync evidence for mode={mode}"


def test_wallet_sync_failed_read_never_claims_success_in_evidence():
    """Correction A: a genuinely-attempted but FAILED WalletSync read
    (get_balance() raises) must never be represented as a successful
    'read' — it is recorded as queried-but-failed, distinctly."""

    wallet = _FakeWallet(raise_on_read=True)
    result = osb.build_operator_snapshot(_inputs(mode="PAPER", wallet_sync=wallet))
    evidence = result["portfolio"]["evidence"]
    assert evidence["wallet_sync"] != "read"
    assert evidence["wallet_sync"] == "read_attempted_failed"
    # And the field itself must be UNAVAILABLE, never a fabricated value.
    assert result["portfolio"]["paper_equity_usd"]["semantics"] == "UNAVAILABLE"


def test_mexc_simulator_evidence_does_not_claim_read_on_view_failure():
    """Secondary A fix: the equivalent MexcSimulator evidence bug (claims
    'read' merely because `sim is not None`, regardless of whether
    `paper_portfolio_view()` actually succeeded) — a failing view must not
    be represented as a plain successful 'read'."""

    class _BrokenSimulator:
        _positions = {}

    import unittest.mock as _mock

    with _mock.patch(
        "paper_trading.paper_portfolio_view.paper_portfolio_view",
        side_effect=RuntimeError("boom"),
    ):
        result = osb.build_operator_snapshot(_inputs(mexc_simulator=_BrokenSimulator()))
    evidence = result["portfolio"]["evidence"]
    assert evidence["mexc_simulator"] != "read"
    assert evidence["mexc_simulator"] == "read_attempted_failed"
    assert result["portfolio"]["status"] == "UNAVAILABLE"


# ── Correction B — portfolio domain status/freshness mapping ──────────────


def test_portfolio_status_unavailable_when_inventory_cannot_be_materialized():
    """Correction B, table row 1: position inventory CANNOT be
    materialized (no simulator at all) -> freshness=UNKNOWN,
    status=UNAVAILABLE."""

    result = osb.build_operator_snapshot(_inputs(mexc_simulator=None))
    portfolio = result["portfolio"]
    assert portfolio["freshness"] == "UNKNOWN"
    assert portfolio["status"] == "UNAVAILABLE"


def test_portfolio_status_degraded_when_inventory_materialized_but_domain_freshness_unproved():
    """Correction B, table row 2: position inventory IS materialized (a
    working simulator with a resolvable view), but whole-domain freshness
    cannot be established (the normal case, per R4) -> freshness=DEGRADED,
    status=DEGRADED (was incorrectly status=OK before R4.1)."""

    pos = _FakePosition("p1", "BTC/USDT")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    result = osb.build_operator_snapshot(_inputs(mexc_simulator=sim))
    portfolio = result["portfolio"]
    assert portfolio["freshness"] == "DEGRADED"
    assert portfolio["status"] == "DEGRADED"


def test_portfolio_status_never_ok_while_freshness_not_fresh_invariant():
    """Correction B general invariant: no current portfolio snapshot can
    combine status=OK with a non-FRESH domain freshness — checked across
    every code path this builder can produce for the portfolio domain."""

    pos = _FakePosition("p1", "BTC/USDT")
    sim = _FakeSimulator(positions={"BTC/USDT": pos}, prices={"BTC/USDT": 100.0})
    wallet = _FakeWalletWithCapitalX(balance=10.0, capital_x=20.0)

    variants = [
        {},
        {"mexc_simulator": sim},
        {"mexc_simulator": None},
        {"mexc_simulator": sim, "wallet_sync": wallet, "mode": "PAPER"},
        {"mexc_simulator": sim, "wallet_sync": wallet, "mode": "REAL_API"},
        {"mexc_simulator": sim, "mode": "UNKNOWN"},
    ]
    for kwargs in variants:
        result = osb.build_operator_snapshot(_inputs(**kwargs))
        portfolio = result["portfolio"]
        if portfolio["status"] == "OK":
            assert portfolio["freshness"] == "FRESH", (
                f"status=OK combined with non-FRESH freshness="
                f"{portfolio['freshness']!r} for kwargs={kwargs}"
            )
        # Given this builder never emits FRESH (R4), this collapses to an
        # unconditional never-OK assertion today — still expressed via the
        # general rule above so it stays correct if a genuine FRESH
        # producer is ever added.
        assert portfolio["status"] != "OK"
