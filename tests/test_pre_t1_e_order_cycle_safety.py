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
    """H1 — REFUTED: source substitutes size=1.0 instead of rejecting, and
    the substituted order still proceeds to the exchange call. NaN bypasses
    the sanity check entirely (nan<=0 and nan>1e9 are both False)."""

    @pytest.mark.parametrize("bad_size", [0.0, -50.0, float("inf"), 2e9])
    def test_anomalous_size_is_substituted_not_rejected(
        self, live_engine_factory, bad_size
    ):
        mock_exchange = _fake_exchange()
        e = live_engine_factory(mock_exchange)
        result = e.create_order("BTC/USDT", "BUY", bad_size)
        # REFUTES H1: the order is NOT rejected — it proceeds as "live"
        # with the substituted size=1.0, an exchange call IS made.
        assert result["mode"] == "live"
        mock_exchange.create_order.assert_called_once()

    def test_nan_size_bypasses_the_sanity_check_entirely(self, live_engine_factory):
        """NaN comparisons are always False in Python: `nan<=0` and
        `nan>1e9` are both False, so the guard at execution_engine.py:274
        never triggers for NaN — proves the guard is not exhaustive."""
        assert not (float("nan") <= 0)
        assert not (float("nan") > 1e9)
        mock_exchange = _fake_exchange()
        e = live_engine_factory(mock_exchange)
        result = e.create_order("BTC/USDT", "BUY", float("nan"))
        # The order is neither rejected nor corrected to 1.0 — NaN size
        # (scaled by size_factor, still NaN) reaches the exchange call path.
        assert result["mode"] != "rejected"
        mock_exchange.create_order.assert_called_once()

    def test_negative_size_paper_mode_also_not_rejected(self, paper_engine):
        """Same substitution behavior confirmed in paper mode (no exchange
        involved) — establishes the defect is in create_order() itself, not
        specific to the live path."""
        result = paper_engine.create_order("BTC/USDT", "BUY", -50.0)
        assert result["mode"] == "paper"
        assert result["size"] == pytest.approx(1.0)


# ── Scenario B — minimum notional / silent amplification ───────────────────


class TestScenarioB_MinNotionalAmplification:
    """H2 — REFUTED: below-min-notional size is silently enlarged to
    min_notional*1.05, exceeding the originally authorized amount."""

    def test_below_min_notional_is_silently_enlarged(self, live_engine_factory):
        mock_exchange = _fake_exchange(last_price=1.0)
        mock_exchange.load_markets.return_value = {
            "BTC/USDT": {
                "limits": {"cost": {"min": 20.0}},
                "precision": {"amount": 1e-5},
            }
        }
        e = live_engine_factory(mock_exchange)
        authorized_size_usd = 5.0  # below the 20.0 min notional
        e.create_order("BTC/USDT", "BUY", authorized_size_usd)

        # Exchange received a qty corresponding to > authorized_size_usd:
        # min_notional * 1.05 = 21.0 USD @ price 1.0 => qty ~= 21.0
        call_args = mock_exchange.create_order.call_args
        submitted_qty = call_args[0][3]
        submitted_usd = submitted_qty * 1.0
        assert submitted_usd > authorized_size_usd
        assert submitted_usd == pytest.approx(20.0 * 1.05, abs=0.5)


# ── Scenario D — order identity ─────────────────────────────────────────────


class TestScenarioD_OrderIdentity:
    """H3 — REFUTED: no clientOrderId/newClientOrderId is ever constructed
    or sent. Order identity is entirely exchange-assigned, post-hoc."""

    def test_no_client_order_id_passed_to_exchange(self, live_engine_factory):
        mock_exchange = _fake_exchange()
        e = live_engine_factory(mock_exchange)
        e.create_order("BTC/USDT", "BUY", 100.0)

        args, kwargs = mock_exchange.create_order.call_args
        haystack = str(args) + str(kwargs)
        assert "clientOrderId" not in haystack
        assert "client_order_id" not in haystack

    def test_same_logical_intention_run_twice_yields_two_distinct_exchange_ids(
        self, live_engine_factory
    ):
        """Two logically-identical intentions (after the dedup window is
        disabled) produce two independent exchange-assigned ids with no
        causal link between them and the originating decision."""
        mock_exchange = _fake_exchange()
        mock_exchange.create_order.side_effect = [
            {"id": "order-A"},
            {"id": "order-B"},
        ]
        e = live_engine_factory(mock_exchange)
        e._dedup._window = 0.0  # disable dedup to isolate identity behavior
        r1 = e.create_order("BTC/USDT", "BUY", 100.0)
        r2 = e.create_order("BTC/USDT", "BUY", 100.0)
        assert r1["id"] != r2["id"]
        assert mock_exchange.create_order.call_count == 2


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
        e.create_order("BTC/USDT", "BUY", 100.0)

        assert events == ["EXCHANGE_CALL_ATTEMPTED", "DURABLE_LOG_WRITTEN"]
        # Honest assertion of the observed (unsafe) order — a safe system
        # would require ["INTENT_PERSISTED", "EXCHANGE_CALL_ATTEMPTED", ...].

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
        e.create_order("BTC/USDT", "BUY", 100.0)

        assert row_count_at_call_time["n"] == 0


# ── Scenario G — timeout before acceptance (blind retry) ───────────────────


class TestScenarioG_TimeoutBeforeAcceptance:
    """H5 — REFUTED: _with_retry reissues the identical call after any
    exception, with no reconciliation lookup of any kind."""

    def test_with_retry_reissues_identical_call_on_every_failure(
        self, live_engine_factory
    ):
        mock_exchange = _fake_exchange()
        mock_exchange.create_order.side_effect = TimeoutError("network timeout")
        e = live_engine_factory(mock_exchange)
        # avoid reconnect() churn by keeping self._exchange as our mock
        e.reconnect = lambda: True

        result = e.create_order("BTC/USDT", "BUY", 100.0)

        assert result["mode"] == "live_failed"
        # 3 blind retries in _with_retry + 1 after reconnect() = 4 identical
        # calls, no fetch_order/reconciliation call in between.
        assert mock_exchange.create_order.call_count == 4
        mock_exchange.fetch_order.assert_not_called()


# ── Scenario H — acceptance followed by lost response (duplicate risk) ─────


class TestScenarioH_LostResponseAfterAcceptance:
    """H5/H6 — REFUTED: when the exchange accepts an order but the response
    is lost (raises after recording), the blind retry can and does attempt
    a second submission — OrderDeduplicator does not help here because its
    register() call never ran for the first (excepted) attempt."""

    def test_blind_retry_after_ambiguous_ack_resubmits(self, live_engine_factory):
        accepted_orders = []

        call_state = {"n": 0}

        def _flaky_create(*args, **kwargs):
            call_state["n"] += 1
            # The exchange silently accepts the order (side effect happens)
            # but the response never reaches the caller (raises instead).
            accepted_orders.append(args)
            raise TimeoutError("response lost after acceptance")

        mock_exchange = _fake_exchange()
        mock_exchange.create_order.side_effect = _flaky_create
        e = live_engine_factory(mock_exchange)
        e.reconnect = lambda: True

        e.create_order("BTC/USDT", "BUY", 100.0)

        # The fake exchange "accepted" the order on every one of the 4
        # blind attempts (3 retries + 1 post-reconnect) — in a real venue
        # each of these could be a genuinely distinct accepted order,
        # because no clientOrderId ties them together for the exchange to
        # dedupe, and OrderDeduplicator.register() (execution_engine.py:324)
        # never ran since every attempt raised.
        assert len(accepted_orders) == 4


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

        r1 = e.create_order("BTC/USDT", "BUY", 100.0)
        r2 = e.create_order("BTC/USDT", "BUY", 100.0)

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
        result = e.create_order("BTC/USDT", "BUY", 100.0)

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
        monkeypatch.setenv("WALLET_PAPER_CAPITAL", "250")
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
        assert "for " not in src  # no retry loop
        assert "except Exception" in src  # swallow-and-log only

    def test_position_manager_marks_closed_even_if_send_order_raised(self):
        """Structural evidence for blocker B7: _close_position() sets
        pos.closed = True unconditionally after calling _send_close_order,
        which itself catches and swallows exceptions rather than
        propagating them — so a failed close order cannot prevent the
        local position from being marked closed."""
        import inspect

        from quant_hedge_ai.agents.execution import position_manager as mod

        src = inspect.getsource(mod.PositionManager._close_position)
        assert "self._send_close_order(pos" in src
        assert "pos.closed = True" in src
        # No conditional / try-except around the two statements that would
        # make pos.closed contingent on _send_close_order's outcome.
        send_idx = src.index("self._send_close_order(pos")
        closed_idx = src.index("pos.closed = True")
        between = src[send_idx:closed_idx]
        assert "try" not in between and "if " not in between
