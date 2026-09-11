"""O-02W-PRE-T1-E — Order-Cycle Safety Audit — hermetic evidence.

Audit-first: these tests assert OBSERVED behavior of the current source at
HEAD `0ace5ccc13e3c111bc7191834c059ef5391e9f65` (branched from). No
production code is modified by this mission. Every test uses a fake
CCXT-shaped exchange object, tmp_path-backed SQLite/JSONL storage, and
explicit call counters. No real network, credentials, or sleep().

See docs/contracts/O-02W-PRE-T1-E_ORDER_CYCLE_SAFETY.md for the full
narrative, hypotheses H1-H12, and evidence-class discussion. Tests here
honestly assert what the source DOES, including defects — several tests
below (marked "REFUTES") pass precisely because they prove the mission's
safety hypothesis is violated. This is intentional: an audit must not encode
the desired future implementation as if it already existed.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest


def _fake_exchange(usdt_balance: float = 10_000.0, last_price: float = 50_000.0):
    """A minimal CCXT-shaped fake exchange with no network access."""
    ex = MagicMock()
    ex.fetch_ticker.return_value = {"last": last_price}
    ex.load_markets.return_value = {}
    ex.fetch_balance.return_value = {"free": {"USDT": usdt_balance}}
    ex.create_order.return_value = {"id": "fake-order-1", "status": "closed"}
    return ex


@pytest.fixture
def live_engine_factory(tmp_path, monkeypatch):
    """Builds an ExecutionEngine wired to a fake exchange, live path open
    (PAPER_TRADING_ENABLED=false, SEC-01 gate open), no real sleep."""
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "1e12")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("EXEC_DEDUP_WINDOW", "30")

    def _make(mock_exchange=None):
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        e._exchange = mock_exchange if mock_exchange is not None else _fake_exchange()
        e.start_session(10_000.0)
        return e

    return _make


@pytest.fixture
def paper_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades_paper.sqlite"))
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "1e12")
    monkeypatch.setenv("EXEC_DEDUP_WINDOW", "30")
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    e = ExecutionEngine(live=False)
    e.start_session(10_000.0)
    return e


# ── Scenario A — invalid sizes ──────────────────────────────────────────────


class TestScenarioA_InvalidSizes:
    """H1 — REFUTED at the original audit HEAD (`0ace5ccc1`): source
    substituted size=1.0 instead of rejecting, and the substituted order
    still proceeded to the exchange call. NaN bypassed the sanity check
    entirely (nan<=0 and nan>1e9 are both False).

    UPDATED by O-02W-PRE-T1-E REM-A (docs/adr/0019-...): Correction A
    removed the substitution — invalid/non-finite/non-positive sizes are now
    REJECTED before any network call, zero exchange mutations. These
    assertions were flipped to match the corrected behavior so this file
    stays an honest, current regression suite rather than asserting a
    defect that no longer exists; the full REM-A proof (fail-before/pass-
    after against this exact starting HEAD) lives in
    tests/test_pre_t1_e_rem_a_order_authorization.py."""

    @pytest.mark.parametrize("bad_size", [0.0, -50.0, float("inf"), 2e9])
    def test_anomalous_size_is_rejected_not_substituted(
        self, live_engine_factory, bad_size
    ):
        mock_exchange = _fake_exchange()
        e = live_engine_factory(mock_exchange)
        result = e.create_order("BTC/USDT", "BUY", bad_size)
        # REM-A fix: the order IS rejected — no substitution, zero mutation.
        assert result["mode"] == "rejected"
        mock_exchange.create_order.assert_not_called()

    def test_nan_size_is_now_caught_by_the_finiteness_check(
        self, live_engine_factory
    ):
        """NaN comparisons are always False in Python: `nan<=0` and
        `nan>1e9` are both False, so the ORIGINAL guard at
        execution_engine.py:274 never triggered for NaN. REM-A added an
        explicit `math.isfinite()` check ahead of those comparisons, closing
        that gap."""
        assert not (float("nan") <= 0)
        assert not (float("nan") > 1e9)
        mock_exchange = _fake_exchange()
        e = live_engine_factory(mock_exchange)
        result = e.create_order("BTC/USDT", "BUY", float("nan"))
        assert result["mode"] == "rejected"
        assert result["denial_reason"] == "NON_FINITE_AMOUNT"
        mock_exchange.create_order.assert_not_called()

    def test_negative_size_paper_mode_also_rejected(self, paper_engine):
        """Same rejection behavior confirmed in paper mode (no exchange
        involved) — the fix is in create_order() itself, not specific to the
        live path."""
        result = paper_engine.create_order("BTC/USDT", "BUY", -50.0)
        assert result["mode"] == "rejected"
        assert result["denial_reason"] == "NON_POSITIVE_AMOUNT"


# ── Scenario B — minimum notional / silent amplification ───────────────────


class TestScenarioB_MinNotionalAmplification:
    """H2 — REFUTED at the original audit HEAD: below-min-notional size was
    silently enlarged to min_notional*1.05, exceeding the originally
    authorized amount.

    UPDATED by O-02W-PRE-T1-E REM-A: Correction B removed the amplification
    — a below-minimum order is now REJECTED (BELOW_MIN_NOTIONAL), never
    enlarged. See tests/test_pre_t1_e_rem_a_order_authorization.py Group B
    for the full proof set."""

    def test_below_min_notional_is_rejected_not_enlarged(self, live_engine_factory):
        mock_exchange = _fake_exchange(last_price=1.0)
        mock_exchange.load_markets.return_value = {
            "BTC/USDT": {
                "limits": {"cost": {"min": 20.0}},
                "precision": {"amount": 1e-5},
            }
        }
        e = live_engine_factory(mock_exchange)
        authorized_size_usd = 5.0  # below the 20.0 min notional
        result = e.create_order("BTC/USDT", "BUY", authorized_size_usd)

        assert result["mode"] == "rejected"
        assert result["denial_reason"] == "BELOW_MIN_NOTIONAL"
        mock_exchange.create_order.assert_not_called()


# ── Scenario D — order identity ─────────────────────────────────────────────


class TestScenarioD_OrderIdentity:
    """H3 — REFUTED at HEAD `297eba89`: no clientOrderId/newClientOrderId
    was ever constructed or sent, and two logically-identical intentions
    produced two independent, uncorrelated exchange orders.

    REMEDIATED_IN_PRE_T1_E_REM_B: `order_intent_protocol.py` derives a
    deterministic `clientOrderId` from the canonical intent and the
    coordinator returns the existing recorded state (no re-submission) for
    a repeated identical intent — see
    `tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` for full proof.
    These two tests are updated to assert the corrected behavior instead
    of re-stating the historical defect as if it still passed.
    """

    def test_client_order_id_now_passed_to_exchange(self, live_engine_factory):
        mock_exchange = _fake_exchange()
        e = live_engine_factory(mock_exchange)
        e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-d-client-id"
        )

        args, kwargs = mock_exchange.create_order.call_args
        params = kwargs.get("params", {})
        assert "clientOrderId" in params
        assert params["clientOrderId"]  # non-empty, deterministic

    def test_same_logical_intention_run_twice_is_idempotent_not_duplicated(
        self, live_engine_factory
    ):
        """A truly identical logical intention (same decision_id, same
        trade fields) submitted twice now yields exactly ONE exchange
        mutation call — the second invocation returns the already-recorded
        state instead of creating a second, uncorrelated order."""
        mock_exchange = _fake_exchange()
        mock_exchange.create_order.return_value = {"id": "order-A"}
        e = live_engine_factory(mock_exchange)
        e._dedup._window = 0.0  # isolate REM-B idempotence from dedup
        r1 = e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-d-repeat"
        )
        r2 = e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-d-repeat"
        )
        # A duplicate of an already-ACKNOWLEDGED intent correctly reports
        # ACKNOWLEDGED again (with the SAME exchange order id) rather than
        # a separate "still pending" label — the invariant under test is
        # that no second mutation call ever occurred, not the exact label.
        assert r1["mode"] == "live"
        assert r2["mode"] == "live"
        assert r1["id"] == r2["id"] == "order-A"
        assert mock_exchange.create_order.call_count == 1


# ── Scenario E — intent persistence ordering ────────────────────────────────


class TestScenarioE_PersistenceOrdering:
    """H4 — REFUTED: the durable TradeLogger write happens strictly after
    the exchange mutation call, not before."""

    def test_exchange_call_precedes_durable_log_write(self, live_engine_factory):
        events: list[str] = []
        mock_exchange = _fake_exchange()
        mock_exchange.create_order.side_effect = lambda *a, **k: (
            events.append("EXCHANGE_CALL_ATTEMPTED") or {"id": "z1"}
        )
        e = live_engine_factory(mock_exchange)

        real_log = e._logger.log

        def _spy_log(*a, **k):
            events.append("DURABLE_LOG_WRITTEN")
            return real_log(*a, **k)

        e._logger.log = _spy_log
        e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-e-precedence"
        )

        # REMEDIATED_IN_PRE_T1_E_REM_B (partial — see contract §22): the
        # REM-B durable order-intent journal (INTENT_RECORDED then
        # SUBMISSION_STARTED, both fsync'd) IS now written and durably
        # synced strictly BEFORE this exact exchange call — proven
        # end-to-end in tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py
        # Group B. This assertion is intentionally scoped to what it always
        # measured: TradeLogger's separate SQLite audit-log write, which
        # REM-B does not touch and which still occurs after the exchange
        # call — that specific ordering claim remains an accurate,
        # unremediated observation about TradeLogger, not about REM-B's own
        # durable intent journal.
        assert events == ["EXCHANGE_CALL_ATTEMPTED", "DURABLE_LOG_WRITTEN"]

    def test_sqlite_log_is_empty_at_the_moment_of_the_exchange_call(
        self, live_engine_factory, tmp_path
    ):
        """Directly queries the SQLite file mid-flight (from the fake
        exchange's own create_order side effect) to prove no row exists
        yet for this order at the moment the network mutation happens."""
        db_path = tmp_path / "trades.sqlite"
        row_count_at_call_time = {}

        def _capture(*a, **k):
            conn = sqlite3.connect(str(db_path))
            row_count_at_call_time["n"] = conn.execute(
                "SELECT COUNT(*) FROM trades"
            ).fetchone()[0]
            conn.close()
            return {"id": "z2"}

        mock_exchange = _fake_exchange()
        mock_exchange.create_order.side_effect = _capture
        e = live_engine_factory(mock_exchange)
        e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-e-sqlite-empty"
        )

        assert row_count_at_call_time["n"] == 0


# ── Scenario G — timeout before acceptance (blind retry) ───────────────────


class TestScenarioG_TimeoutBeforeAcceptance:
    """H5 — REFUTED at HEAD `297eba89`: `_with_retry` reissued the
    identical mutation call after any exception, with no reconciliation
    lookup of any kind.

    REMEDIATED_IN_PRE_T1_E_REM_B: the mutation call itself is never wrapped
    in `_with_retry` (`_mutate_via_coordinator`'s docstring: "REM-B never
    adds its OWN retry loop around a submission") — a timeout is classified
    AMBIGUOUS and persisted RECONCILE_REQUIRED after exactly one call.
    """

    def test_timeout_causes_exactly_one_call_and_reconcile_required(
        self, live_engine_factory
    ):
        mock_exchange = _fake_exchange()
        mock_exchange.create_order.side_effect = TimeoutError("network timeout")
        e = live_engine_factory(mock_exchange)
        e.reconnect = lambda: True

        result = e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-g-timeout"
        )

        assert result["mode"] == "live_ambiguous"
        assert result["order_intent_outcome"] == "RECONCILE_REQUIRED"
        # Exactly one mutation call — no blind retry (I5).
        assert mock_exchange.create_order.call_count == 1
        mock_exchange.fetch_order.assert_not_called()


# ── Scenario H — acceptance followed by lost response (duplicate risk) ─────


class TestScenarioH_LostResponseAfterAcceptance:
    """H5/H6 — REFUTED at HEAD `297eba89`: when the exchange accepted an
    order but the response was lost (raised after recording), the blind
    retry could and did attempt a second submission.

    REMEDIATED_IN_PRE_T1_E_REM_B: exactly one mutation call is made; the
    lost/ambiguous response is persisted RECONCILE_REQUIRED and reconciled
    read-only by deterministic clientOrderId (never a blind resubmission)
    — see tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py Group F.
    """

    def test_lost_response_causes_exactly_one_acceptance_attempt(
        self, live_engine_factory
    ):
        accepted_orders = []

        def _flaky_create(*args, **kwargs):
            # The exchange silently accepts the order (side effect happens)
            # but the response never reaches the caller (raises instead).
            accepted_orders.append(args)
            raise TimeoutError("response lost after acceptance")

        mock_exchange = _fake_exchange()
        mock_exchange.create_order.side_effect = _flaky_create
        e = live_engine_factory(mock_exchange)
        e.reconnect = lambda: True

        result = e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-h-lost-response"
        )

        # Exactly one attempt — no blind retry to compound the ambiguity.
        assert len(accepted_orders) == 1
        assert result["order_intent_outcome"] == "RECONCILE_REQUIRED"


# ── Scenario I — duplicate invocation (same-process, non-ambiguous case) ───


class TestScenarioI_DuplicateInvocation:
    """H6 — the ONE case OrderDeduplicator does cover: two full, successful
    create_order() calls with matching (symbol, action, size-bucket) inside
    the dedup window. The second is rejected before any exchange call."""

    def test_second_identical_call_within_window_is_rejected(
        self, live_engine_factory
    ):
        mock_exchange = _fake_exchange()
        e = live_engine_factory(mock_exchange)

        r1 = e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-i-dup-1"
        )
        r2 = e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-i-dup-2"
        )

        assert r1["mode"] == "live"
        assert r2["mode"] == "rejected"
        assert mock_exchange.create_order.call_count == 1


# ── Scenario J — partial fill ───────────────────────────────────────────────


class TestScenarioJ_PartialFill:
    """H8/H9 (fill handling) — the live path does not distinguish a partial
    fill from a full fill; `mode` stays "live" either way, and no follow-up
    polling occurs."""

    def test_partial_fill_response_is_not_distinguished_from_full_fill(
        self, live_engine_factory
    ):
        mock_exchange = _fake_exchange()
        mock_exchange.create_order.return_value = {
            "id": "partial-1",
            "status": "open",
            "filled": 0.0005,
            "remaining": 0.0015,
            "amount": 0.002,
        }
        e = live_engine_factory(mock_exchange)
        result = e.create_order(
            "BTC/USDT", "BUY", 100.0, decision_id="scenario-j-partial-fill"
        )

        assert result["mode"] == "live"
        # No distinct "partial" mode/flag exists on this return value.
        assert "partial" not in str(result.get("mode", "")).lower()
        # Only one create_order call — no follow-up fetch_order to resolve
        # the remaining quantity.
        mock_exchange.fetch_order.assert_not_called()


# ── Scenario M — authority matrix ───────────────────────────────────────────


class TestScenarioM_AuthorityMatrix:
    """H10 — every forbidden authority combination examined yields ZERO
    exchange mutation calls on Path A (ExecutionEngine)."""

    def test_paper_trading_enabled_true_blocks_even_with_live_exchange_wired(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "1e12")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        mock_exchange = _fake_exchange()
        e._exchange = mock_exchange
        e.start_session(10_000.0)

        result = e.create_order("BTC/USDT", "BUY", 100.0)

        assert result["mode"] == "live_failed"
        mock_exchange.create_order.assert_not_called()
        mock_exchange.fetch_ticker.assert_not_called()

    def test_live_trading_not_confirmed_never_reaches_live_branch(
        self, tmp_path, monkeypatch
    ):
        """from_env(): keys present but LIVE_TRADING_CONFIRMED unset ->
        self._live stays False -> create_order() always takes the paper
        branch, exchange object is never even constructed as active."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXCHANGE_ID", "mexc")
        monkeypatch.setenv("MEXC_API_KEY", "fake")
        monkeypatch.setenv("MEXC_API_SECRET", "fake")
        monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is False
        e.start_session(10_000.0)
        result = e.create_order("BTC/USDT", "BUY", 10.0)
        assert result["mode"] == "paper"

    def test_session_halted_blocks_before_any_exchange_call(
        self, live_engine_factory
    ):
        mock_exchange = _fake_exchange()
        e = live_engine_factory(mock_exchange)
        e._guard._state.halted = True
        e._guard._state.halt_reason = "test_halt"

        result = e.create_order("BTC/USDT", "BUY", 100.0)

        assert result["mode"] == "rejected"
        mock_exchange.create_order.assert_not_called()


# ── Scenario P — PRE-T1-D non-regression ────────────────────────────────────


class TestScenarioP_PreT1DSeparationNonRegression:
    """H11/H15 — scientific capital and exchange observation stay separated
    on this HEAD. Full boundary suite is re-run separately (see contract
    §17 and the delivery PR); this test re-asserts the two structural
    invariants directly from inside this audit's own file, independent of
    that suite's fixtures."""

    def test_fetch_available_capital_makes_zero_exchange_calls(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv(
            "PAPER_TRADE_LOG", str(tmp_path / "paper_trades_ptd_e.jsonl")
        )
        # infra.wallet_sync._PAPER_CAPITAL is a module-level constant read
        # once from WALLET_PAPER_CAPITAL at import time (`infra/wallet_sync.py`
        # line 50: `_PAPER_CAPITAL = float(os.getenv("WALLET_PAPER_CAPITAL",
        # "100"))`), not re-read per call. Since the module is very likely
        # already imported by the time this test runs (as part of the full
        # suite), monkeypatching the env var alone has no effect on it —
        # patch the already-bound module attribute directly instead, which
        # is what get_scientific_capital() actually reads.
        import infra.wallet_sync as _ws

        monkeypatch.setattr(_ws, "_PAPER_CAPITAL", 250.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        mock_exchange = _fake_exchange()
        e._exchange = mock_exchange  # present but must be irrelevant
        e._live = True

        capital = e.fetch_available_capital()

        assert capital == pytest.approx(250.0)
        mock_exchange.fetch_balance.assert_not_called()
        mock_exchange.fetch_ticker.assert_not_called()

    def test_observe_exchange_balance_never_called_by_sizing_path(self):
        import inspect

        from quant_hedge_ai.agents.execution import execution_engine as mod

        src = inspect.getsource(mod.ExecutionEngine.fetch_available_capital)
        # The docstring documents observe_exchange_balance()'s EXISTENCE
        # only to warn it must never feed this return value — the executed
        # body (last non-blank line) is the sole check that matters here.
        body_line = [ln.strip() for ln in src.splitlines() if ln.strip()][-1]
        assert body_line == "return get_scientific_capital()"
        assert "get_scientific_capital" in src


# ── Structural / source-inspection evidence (call-site inventory support) ──


class TestCallSiteInventory:
    """SOURCE_PROVEN structural checks backing contract §5-§6. These
    intentionally test via source inspection where a hermetic behavioral
    test would require importing modules with heavier side-effect surfaces
    (e.g. position_manager.py's construction chain) that are out of scope
    to fully mock in this audit round — documented per mission instructions
    rather than silently skipped."""

    def test_pending_order_tracker_not_imported_by_execution_engine(self):
        import inspect

        from quant_hedge_ai.agents.execution import execution_engine as mod

        src = inspect.getsource(mod)
        assert "PendingOrderTracker" not in src
        assert "pending_order_tracker" not in src

    def test_position_manager_close_order_has_no_retry_wrapper(self):
        """Structural evidence for contract §6 Path B: _send_close_order
        has a single try/except with no _with_retry-style loop."""
        import inspect

        from quant_hedge_ai.agents.execution import position_manager as mod

        src = inspect.getsource(mod.PositionManager._send_close_order)
        assert "_with_retry" not in src
        # Updated for O-02W-PRE-T1-E REM-B: the mutation call itself is now
        # wrapped by the REM-B durable coordinator (order_intent_protocol.py)
        # instead of a bare try/except at this call site — REM-B's whole
        # point is that an ambiguous result becomes RECONCILE_REQUIRED, not
        # a blind retry loop. A comprehension used only to classify an
        # exception message ("for k in (...)") is not a retry loop; the
        # structural guarantee this test protects — no `while`-based retry
        # and no second create_order() call on the same path — is checked
        # directly instead of banning the substring "for ".
        assert "while " not in src  # no retry loop
        assert src.count("create_order(") <= 1  # exactly one mutation call site

    def test_position_manager_close_honesty_fixed_by_rem_a(self):
        """Blocker B7 at the original audit HEAD: _close_position() set
        pos.closed = True unconditionally after calling _send_close_order,
        which itself caught and swallowed exceptions rather than
        propagating them — so a failed close order could not prevent the
        local position from being marked closed.

        UPDATED by O-02W-PRE-T1-E REM-A (PositionManager exception-honesty
        fix, narrow scope per mission instructions): _send_close_order now
        returns an explicit authorized/mutation_attempted/mode/
        denial_reason outcome, and _close_position only marks pos.closed
        when that outcome was not a denial or a failed mutation. This test
        now asserts the fix is present rather than the original defect —
        see tests/test_pre_t1_e_rem_a_order_authorization.py Group F for
        the behavioral proof."""
        import inspect

        from quant_hedge_ai.agents.execution import position_manager as mod

        src = inspect.getsource(mod.PositionManager._close_position)
        assert "self._send_close_order(pos" in src
        assert "pos.closed = True" in src
        # The two statements are now separated by an explicit outcome check
        # — closing is no longer unconditional.
        send_idx = src.index("self._send_close_order(pos")
        closed_idx = src.index("pos.closed = True")
        between = src[send_idx:closed_idx]
        assert "authorized" in between
        assert "mutation_attempted" in between
