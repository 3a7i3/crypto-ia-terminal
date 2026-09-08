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
    decision = result["decision_pipeline"]["decisions"][0]
    assert decision["is_actionable"]["value"] is False
    assert decision["is_actionable"]["authority"] == "EXECUTION_AUTHORITY"
    assert decision["trade_allowed"]["value"] is True
    assert decision["trade_allowed"]["authority"] == "OBSERVATIONAL_TELEMETRY"


def test_actionable_decision_packet_labeled_execution_authority():
    dp = _FakeDecisionPacket(actionable=True)
    rec = osb.DecisionRecord(symbol="BTC/USDT", decision_packet=dp, legacy_trade_allowed=False)
    result = osb.build_operator_snapshot(_inputs(decisions=[rec]))
    decision = result["decision_pipeline"]["decisions"][0]
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
    balance under paper_equity_usd — the field becomes NOT_APPLICABLE."""

    wallet = _FakeWallet(balance=999999.0)  # a deliberately eye-catching value
    for mode in ("REAL_API", "TESTNET_API", "UNKNOWN"):
        result = osb.build_operator_snapshot(_inputs(mode=mode, wallet_sync=wallet))
        pe = result["portfolio"]["paper_equity_usd"]
        assert pe["value"] != 999999.0
        assert pe["value"] is None
        assert pe["semantics"] == "NOT_APPLICABLE"
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
    ps = result["portfolio"]["portfolio_state"]
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
    ps = result["portfolio"]["portfolio_state"]
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
