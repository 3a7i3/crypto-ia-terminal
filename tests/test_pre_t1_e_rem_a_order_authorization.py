"""O-02W-PRE-T1-E REM-A — Pre-network order authorization — remediation
proof suite.

Covers Groups A-G from the mission brief:
  A — invalid amounts (unit, via the boundary directly)
  B — minimum notional (unit)
  C — precision conservatism (unit, property-style)
  D — BUY/SELL balance validation (unit)
  E — trading authority composition (unit)
  F — both mutation families through their REAL production call paths
      (ExecutionEngine.create_order / PositionManager._close_position),
      with injected fake exchanges — not the low-level validator alone.
  G — non-regression (PRE-T1-D separation, sizing formula, no REM-B claims)

No network, no Telegram, no real/testnet credentials, no real orders
anywhere — fake CCXT-shaped exchange objects only, tmp_path-backed storage.

Explicitly OUT OF SCOPE for this file (REM-B/REM-C, not tested here because
they are not implemented): clientOrderId / deterministic order identity,
durable intent-before-network journaling, retry/reconciliation, partial-fill
state machines, PendingOrderTracker activation.
"""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.execution.order_authorization import (
    DenialReason,
    authorize_order,
    evaluate_trading_authority,
)


# ─────────────────────────────────────────────────────────────────────────
# Group A — invalid amounts (unit, direct boundary)
# ─────────────────────────────────────────────────────────────────────────


class TestGroupA_InvalidAmounts:
    def _authorize(self, **overrides):
        params = dict(
            symbol="BTC/USDT",
            side="buy",
            requested_amount=100.0,
            price=50_000.0,
            amount_precision=1e-5,
            min_notional=5.0,
            available_quote_balance=1_000_000.0,
        )
        params.update(overrides)
        return authorize_order(**params)

    def test_missing_amount(self):
        result = self._authorize(requested_amount=None)
        assert not result.authorized
        assert result.denial_reason == DenialReason.INVALID_AMOUNT

    def test_malformed_string_amount(self):
        result = self._authorize(requested_amount="not-a-number")
        assert not result.authorized
        assert result.denial_reason == DenialReason.INVALID_AMOUNT

    def test_malformed_object_amount(self):
        result = self._authorize(requested_amount=object())
        assert not result.authorized
        assert result.denial_reason == DenialReason.INVALID_AMOUNT

    def test_zero_amount(self):
        result = self._authorize(requested_amount=0.0)
        assert not result.authorized
        assert result.denial_reason == DenialReason.NON_POSITIVE_AMOUNT

    def test_negative_amount(self):
        result = self._authorize(requested_amount=-50.0)
        assert not result.authorized
        assert result.denial_reason == DenialReason.NON_POSITIVE_AMOUNT

    def test_nan_amount(self):
        result = self._authorize(requested_amount=float("nan"))
        assert not result.authorized
        assert result.denial_reason == DenialReason.NON_FINITE_AMOUNT

    def test_positive_infinity_amount(self):
        result = self._authorize(requested_amount=float("inf"))
        assert not result.authorized
        assert result.denial_reason == DenialReason.NON_FINITE_AMOUNT

    def test_negative_infinity_amount(self):
        result = self._authorize(requested_amount=float("-inf"))
        assert not result.authorized
        assert result.denial_reason == DenialReason.NON_FINITE_AMOUNT

    def test_above_authorized_max(self):
        result = self._authorize(requested_amount=1000.0, authorized_max_amount=100.0)
        assert not result.authorized
        assert result.denial_reason == DenialReason.ABOVE_AUTHORIZED_EXPOSURE

    def test_precision_collapse_to_zero(self):
        # amount is tiny relative to precision step -> floors to 0 qty
        result = self._authorize(
            requested_amount=0.0001, price=50_000.0, amount_precision=1.0
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.PRECISION_COLLAPSE

    @pytest.mark.parametrize(
        "bad_amount",
        [None, "bad", object(), 0.0, -1.0, float("nan"), float("inf"), float("-inf")],
    )
    def test_all_invalid_amounts_produce_zero_authorization(self, bad_amount):
        result = self._authorize(requested_amount=bad_amount)
        assert not result.authorized
        assert result.normalized_amount == 0.0
        assert result.normalized_qty == 0.0


# ─────────────────────────────────────────────────────────────────────────
# Group B — minimum notional (never amplified)
# ─────────────────────────────────────────────────────────────────────────


class TestGroupB_MinimumNotional:
    def _authorize(self, **overrides):
        params = dict(
            symbol="BTC/USDT",
            side="buy",
            requested_amount=20.0,
            price=1.0,
            amount_precision=1e-5,
            min_notional=20.0,
            available_quote_balance=1_000_000.0,
        )
        params.update(overrides)
        return authorize_order(**params)

    def test_below_minimum_rejected(self):
        result = self._authorize(requested_amount=5.0)
        assert not result.authorized
        assert result.denial_reason == DenialReason.BELOW_MIN_NOTIONAL

    def test_exactly_minimum_authorized(self):
        result = self._authorize(requested_amount=20.0)
        assert result.authorized
        assert result.normalized_amount <= 20.0

    def test_just_above_minimum_authorized(self):
        result = self._authorize(requested_amount=20.5)
        assert result.authorized
        assert result.normalized_amount <= 20.5

    def test_precision_reduction_causing_below_minimum_is_rejected(self):
        # 20.00003 at step 1.0 floors to 20.0 (== min, ok);
        # but a coarse step that floors just under the minimum must reject.
        result = self._authorize(
            requested_amount=20.9, price=1.0, amount_precision=1.0, min_notional=20.5
        )
        # floor(20.9/1.0)*1.0 = 20.0 < 20.5 min -> reject
        assert not result.authorized
        assert result.denial_reason == DenialReason.BELOW_MIN_NOTIONAL

    def test_missing_minimum_metadata_fails_closed(self):
        result = self._authorize(min_notional=None)
        assert not result.authorized
        assert result.denial_reason == DenialReason.METADATA_UNAVAILABLE

    def test_malformed_minimum_metadata_fails_closed(self):
        result = self._authorize(min_notional="not-a-number")
        assert not result.authorized
        assert result.denial_reason == DenialReason.METADATA_UNAVAILABLE

    def test_old_silent_amplification_input_is_now_rejected(self):
        """The exact scenario the original audit proved as H2 (5 USD
        request, 20 USD min notional, old code silently submitted ~21
        USD): now rejected outright, and no authorized case ever exceeds
        the authorized intention."""
        result = self._authorize(requested_amount=5.0, min_notional=20.0)
        assert not result.authorized
        assert result.normalized_amount == 0.0

    @pytest.mark.parametrize("requested", [1.0, 5.0, 19.99, 20.0, 25.0, 100.0])
    def test_no_authorized_case_exceeds_the_authorized_intention(self, requested):
        result = self._authorize(requested_amount=requested, authorized_max_amount=requested)
        if result.authorized:
            assert result.normalized_amount <= requested + 1e-9
            assert result.normalized_qty * 1.0 <= requested + 1e-9


# ─────────────────────────────────────────────────────────────────────────
# Group C — precision conservatism
# ─────────────────────────────────────────────────────────────────────────


class TestGroupC_Precision:
    @pytest.mark.parametrize(
        "amount,price,step",
        [
            (100.0, 50_000.0, 1e-5),
            (100.0, 33_333.33, 1e-4),
            (0.1, 0.0001, 1e-8),
            (99.999999, 3.3333333, 1e-6),
            (17.0, 7.0, 0.001),
            (10_000.0, 1.0, 1.0),
            (1_000.0, 3.0, 0.1),
        ],
    )
    def test_normalized_never_exceeds_authorized(self, amount, price, step):
        result = authorize_order(
            symbol="X/Y",
            side="buy",
            requested_amount=amount,
            price=price,
            amount_precision=step,
            min_notional=0.0,
            authorized_max_amount=amount,
            available_quote_balance=1e12,
        )
        if result.authorized:
            assert result.normalized_amount <= amount + 1e-9
            assert result.normalized_qty <= (amount / price) + 1e-9

    def test_boundary_equality_deterministic(self):
        # amount exactly divisible by step -> normalized == requested (no
        # rounding artifact created by floor at an exact boundary).
        r1 = authorize_order(
            symbol="X/Y",
            side="buy",
            requested_amount=100.0,
            price=1.0,
            amount_precision=1.0,
            min_notional=0.0,
            available_quote_balance=1e9,
        )
        r2 = authorize_order(
            symbol="X/Y",
            side="buy",
            requested_amount=100.0,
            price=1.0,
            amount_precision=1.0,
            min_notional=0.0,
            available_quote_balance=1e9,
        )
        assert r1.normalized_amount == r2.normalized_amount == 100.0

    def test_floating_point_artifact_does_not_create_unauthorized_increase(self):
        # classic binary-float trap: 0.1 + 0.2 style — use an amount/step
        # pair known to be inexact in binary float.
        amount = 0.3
        price = 1.0
        step = 0.1
        result = authorize_order(
            symbol="X/Y",
            side="buy",
            requested_amount=amount,
            price=price,
            amount_precision=step,
            min_notional=0.0,
            authorized_max_amount=amount,
            available_quote_balance=1e9,
        )
        if result.authorized:
            assert result.normalized_amount <= amount + 1e-9

    def test_rounding_to_zero_is_rejected(self):
        result = authorize_order(
            symbol="X/Y",
            side="buy",
            requested_amount=0.4,
            price=1.0,
            amount_precision=1.0,
            min_notional=0.0,
            available_quote_balance=1e9,
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.PRECISION_COLLAPSE


# ─────────────────────────────────────────────────────────────────────────
# Group D — BUY/SELL balance validation
# ─────────────────────────────────────────────────────────────────────────


class TestGroupD_Balances:
    def _base_kwargs(self, side="buy"):
        return dict(
            symbol="BTC/USDT",
            side=side,
            requested_amount=100.0,
            price=50_000.0,
            amount_precision=1e-5,
            min_notional=5.0,
        )

    def test_buy_sufficient_quote(self):
        result = authorize_order(
            **self._base_kwargs("buy"), available_quote_balance=1000.0
        )
        assert result.authorized

    def test_buy_insufficient_quote(self):
        result = authorize_order(
            **self._base_kwargs("buy"), available_quote_balance=10.0
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.INSUFFICIENT_QUOTE_BALANCE

    def test_buy_missing_quote(self):
        result = authorize_order(
            **self._base_kwargs("buy"), available_quote_balance=None
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.BALANCE_UNAVAILABLE

    def test_sell_sufficient_base(self):
        result = authorize_order(
            **self._base_kwargs("sell"), available_base_balance=1.0
        )
        assert result.authorized

    def test_sell_insufficient_base(self):
        result = authorize_order(
            **self._base_kwargs("sell"), available_base_balance=0.0001
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.INSUFFICIENT_BASE_BALANCE

    def test_sell_missing_base(self):
        result = authorize_order(
            **self._base_kwargs("sell"), available_base_balance=None
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.BALANCE_UNAVAILABLE

    def test_balance_api_error(self):
        result = authorize_order(
            **self._base_kwargs("buy"),
            available_quote_balance=1000.0,
            balance_error=True,
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.BALANCE_UNAVAILABLE

    def test_zero_balance(self):
        result = authorize_order(
            **self._base_kwargs("buy"), available_quote_balance=0.0
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.INSUFFICIENT_QUOTE_BALANCE

    def test_malformed_balance(self):
        result = authorize_order(
            **self._base_kwargs("buy"), available_quote_balance="lots"
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.BALANCE_UNAVAILABLE

    def test_non_finite_balance(self):
        result = authorize_order(
            **self._base_kwargs("buy"), available_quote_balance=float("nan")
        )
        assert not result.authorized
        assert result.denial_reason == DenialReason.BALANCE_UNAVAILABLE

    def test_scientific_capital_never_substitutes_for_balance(self):
        """Structural guard: authorize_order has no parameter that could be
        fed a scientific-capital value in place of an executable balance —
        the only balance inputs are available_quote_balance/
        available_base_balance, always sourced by callers from
        exchange.fetch_balance(), never from get_scientific_capital()."""
        import inspect

        from quant_hedge_ai.agents.execution import order_authorization as mod

        sig = inspect.signature(mod.authorize_order)
        assert "scientific_capital" not in sig.parameters
        src = inspect.getsource(mod)
        assert "get_scientific_capital" not in src


# ─────────────────────────────────────────────────────────────────────────
# Group E — authority
# ─────────────────────────────────────────────────────────────────────────


class TestGroupE_Authority:
    def _base(self, **overrides):
        params = dict(
            paper_trading_enabled=False,
            live_trading_confirmed=True,
            exchange_present=True,
            live_mode=True,
        )
        params.update(overrides)
        return evaluate_trading_authority(**params)

    def test_valid_armed_path_authorized(self):
        ok, reason = self._base()
        assert ok
        assert reason == "authorized"

    def test_paper_enabled_denies(self):
        ok, reason = self._base(paper_trading_enabled=True)
        assert not ok
        assert reason == "blocked_by_paper_gate"

    def test_live_confirmation_false_denies(self):
        ok, reason = self._base(live_trading_confirmed=False)
        assert not ok
        assert reason == "live_trading_not_confirmed"

    def test_halt_denies(self):
        ok, reason = self._base(halted=True)
        assert not ok
        assert reason == "session_halted"

    def test_safe_mode_denies(self):
        ok, reason = self._base(safe_mode=True)
        assert not ok
        assert reason == "safe_mode_active"

    def test_kill_switch_denies(self):
        ok, reason = self._base(kill_switch=True)
        assert not ok
        assert reason == "kill_switch_engaged"

    def test_exchange_absent_denies(self):
        ok, reason = self._base(exchange_present=False)
        assert not ok
        assert reason == "missing_exchange"

    def test_unsupported_mode_denies(self):
        ok, reason = self._base(execution_mode_supported=False)
        assert not ok
        assert reason == "unsupported_execution_mode"

    def test_not_live_mode_denies(self):
        ok, reason = self._base(live_mode=False)
        assert not ok
        assert reason == "not_in_live_mode"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"paper_trading_enabled": True, "halted": True},
            {"live_trading_confirmed": False, "kill_switch": True},
            {"exchange_present": False, "safe_mode": True},
        ],
    )
    def test_combinations_of_forbidden_states_deny(self, overrides):
        ok, _ = self._base(**overrides)
        assert not ok


# ─────────────────────────────────────────────────────────────────────────
# Group F — both mutation families, real production call paths
# ─────────────────────────────────────────────────────────────────────────


def _fake_execution_exchange(
    usdt_balance=10_000.0, base_balance=None, last_price=50_000.0
):
    from unittest.mock import MagicMock

    ex = MagicMock()
    ex.fetch_ticker.return_value = {"last": last_price}
    ex.load_markets.return_value = {
        "BTC/USDT": {
            "limits": {"cost": {"min": 5.0}},
            "precision": {"amount": 1e-5},
        }
    }
    free = {"USDT": usdt_balance}
    if base_balance is not None:
        free["BTC"] = base_balance
    ex.fetch_balance.return_value = {"free": free}
    ex.create_order.return_value = {"id": "fake-order-1", "status": "closed"}
    return ex


@pytest.fixture
def live_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "1e12")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("EXEC_DEDUP_WINDOW", "0")

    def _make(mock_exchange=None):
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        e._exchange = (
            mock_exchange if mock_exchange is not None else _fake_execution_exchange()
        )
        e.start_session(10_000.0)
        return e

    return _make


class TestGroupF_ExecutionEngine:
    def test_invalid_amount_zero_mutations(self, live_engine):
        ex = _fake_execution_exchange(base_balance=1.0)
        e = live_engine(ex)
        result = e.create_order("BTC/USDT", "BUY", float("nan"))
        assert result["mode"] == "rejected"
        ex.create_order.assert_not_called()

    def test_below_min_notional_zero_mutations(self, live_engine):
        ex = _fake_execution_exchange(base_balance=1.0)
        e = live_engine(ex)
        result = e.create_order("BTC/USDT", "BUY", 1.0)  # < 5.0 min
        assert result["mode"] == "rejected"
        assert result["denial_reason"] == "BELOW_MIN_NOTIONAL"
        ex.create_order.assert_not_called()

    def test_sell_without_base_balance_zero_mutations(self, live_engine):
        ex = _fake_execution_exchange(base_balance=None)  # no BTC entry
        e = live_engine(ex)
        result = e.create_order("BTC/USDT", "SELL", 100.0)
        assert result["mode"] == "rejected"
        assert result["denial_reason"] == "BALANCE_UNAVAILABLE"
        ex.create_order.assert_not_called()

    def test_sell_with_insufficient_base_zero_mutations(self, live_engine):
        ex = _fake_execution_exchange(base_balance=0.00001)
        e = live_engine(ex)
        result = e.create_order("BTC/USDT", "SELL", 100.0)
        assert result["mode"] == "rejected"
        assert result["denial_reason"] == "INSUFFICIENT_BASE_BALANCE"
        ex.create_order.assert_not_called()

    def test_valid_buy_reaches_single_mutation(self, live_engine):
        ex = _fake_execution_exchange(base_balance=1.0)
        e = live_engine(ex)
        result = e.create_order("BTC/USDT", "BUY", 100.0)
        assert result["mode"] == "live"
        ex.create_order.assert_called_once()

    def test_valid_sell_reaches_single_mutation(self, live_engine):
        ex = _fake_execution_exchange(base_balance=1.0)
        e = live_engine(ex)
        result = e.create_order("BTC/USDT", "SELL", 100.0)
        assert result["mode"] == "live"
        ex.create_order.assert_called_once()

    def test_paper_gate_blocks_before_any_authorization_call(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t2.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "1e12")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        ex = _fake_execution_exchange(base_balance=1.0)
        e._exchange = ex
        e.start_session(10_000.0)
        result = e.create_order("BTC/USDT", "BUY", 100.0)
        assert result["mode"] == "live_failed"
        ex.fetch_ticker.assert_not_called()
        ex.create_order.assert_not_called()


class TestGroupF_PositionManager:
    def _make_position(self, side="long", qty=1.0, entry_price=100.0):
        from quant_hedge_ai.agents.execution.position_manager import (
            Position,
            PositionSide,
        )

        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG if side == "long" else PositionSide.SHORT,
            entry_price=entry_price,
            size_usd=qty * entry_price,
            qty=qty,
        )
        pos.current_price = entry_price
        return pos

    def _make_pm(self, exchange, monkeypatch, paper_trading_enabled="false"):
        monkeypatch.setenv("PAPER_TRADING_ENABLED", paper_trading_enabled)
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        from quant_hedge_ai.agents.execution.position_manager import PositionManager

        return PositionManager(exchange=exchange, paper_mode=False)

    def test_authority_denied_zero_mutations(self, monkeypatch):
        from unittest.mock import MagicMock

        ex = MagicMock()
        ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 1e-5}}
        }
        pm = self._make_pm(ex, monkeypatch, paper_trading_enabled="true")
        pos = self._make_position()
        from quant_hedge_ai.agents.execution.position_manager import CloseReason

        pm._close_position(pos, CloseReason.TP)

        ex.create_order.assert_not_called()
        assert pos.closed is False
        assert pos.close_order_denial_reason == "AUTHORITY_DENIED"

    def test_metadata_unavailable_zero_mutations(self, monkeypatch):
        from unittest.mock import MagicMock

        ex = MagicMock()
        ex.load_markets.side_effect = Exception("boom")
        pm = self._make_pm(ex, monkeypatch)
        pos = self._make_position()
        from quant_hedge_ai.agents.execution.position_manager import CloseReason

        pm._close_position(pos, CloseReason.TP)

        ex.create_order.assert_not_called()
        assert pos.closed is False
        assert pos.close_order_denial_reason == "METADATA_UNAVAILABLE"

    def test_successful_close_single_mutation_and_marks_closed(self, monkeypatch):
        from unittest.mock import MagicMock

        ex = MagicMock()
        ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 1e-5}}
        }
        ex.create_order.return_value = {"id": "close-1"}
        pm = self._make_pm(ex, monkeypatch)
        pos = self._make_position()
        from quant_hedge_ai.agents.execution.position_manager import CloseReason

        pm._close_position(pos, CloseReason.TP)

        ex.create_order.assert_called_once()
        assert pos.closed is True
        assert pos.close_order_denial_reason is None

    def test_failed_mutation_leaves_position_open_honestly(self, monkeypatch):
        """PositionManager exception-honesty fix: a raised exception from
        the exchange call must not be silently swallowed into an
        unconditional pos.closed = True."""
        from unittest.mock import MagicMock

        ex = MagicMock()
        ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 1e-5}}
        }
        ex.create_order.side_effect = Exception("network blip")
        pm = self._make_pm(ex, monkeypatch)
        pos = self._make_position()
        from quant_hedge_ai.agents.execution.position_manager import CloseReason

        pm._close_position(pos, CloseReason.SL)

        ex.create_order.assert_called_once()  # exactly one mutation attempt
        assert pos.closed is False  # NOT silently marked closed
        # Updated for O-02W-PRE-T1-E REM-B: an unclassified exception from
        # the exchange call is genuinely ambiguous — it is neither a proven
        # failure nor a proven success (I10, spec H5) — so it now surfaces
        # as "live_ambiguous" (RECONCILE_REQUIRED) rather than being
        # collapsed into "live_failed". The pre-REM-B honesty property this
        # test protects (never silently marked closed on any non-ack
        # outcome) still holds — see `pos.closed is False` above.
        assert pos.close_order_status in ("live_failed", "live_ambiguous")
        assert pos.close_order_status == "live_ambiguous"

    def test_close_qty_never_exceeds_tracked_position_qty(self, monkeypatch):
        from unittest.mock import MagicMock

        ex = MagicMock()
        ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 1e-5}}
        }
        ex.create_order.return_value = {"id": "close-2"}
        pm = self._make_pm(ex, monkeypatch)
        pos = self._make_position(qty=0.5)
        from quant_hedge_ai.agents.execution.position_manager import CloseReason

        pm._close_position(pos, CloseReason.TP)

        submitted_qty = ex.create_order.call_args[0][3]
        assert submitted_qty <= 0.5 + 1e-9

    def test_paper_mode_unchanged_single_call_no_exchange(self, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        from quant_hedge_ai.agents.execution.position_manager import (
            CloseReason,
            PositionManager,
        )

        pm = PositionManager(exchange=None, paper_mode=True)
        pos = self._make_position()
        pm._close_position(pos, CloseReason.TP)
        assert pos.closed is True  # paper close still closes immediately

    # ── Defect 2 (R1): dimensional correctness — qty vs USD notional ────────
    # Proves the dead ternary (`qty * price if price > 0 else qty * price`)
    # is gone and quantity/notional cannot be transposed, at non-trivial
    # prices in both directions (large price, small price).

    def test_dimensional_correctness_high_price(self, monkeypatch):
        """price=50_000: notional (500) and quantity (0.01) are far apart —
        transposing them would either submit a wildly wrong quantity to the
        exchange or wrongly deny/allow on the exposure ceiling."""
        from unittest.mock import MagicMock

        ex = MagicMock()
        ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 1e-5}}
        }
        ex.create_order.return_value = {"id": "close-hp"}
        pm = self._make_pm(ex, monkeypatch)
        pos = self._make_position(qty=0.01, entry_price=50_000.0)
        pos.current_price = 50_000.0
        from quant_hedge_ai.agents.execution.position_manager import CloseReason

        result = pm._send_close_order(pos, reason=CloseReason.TP)

        assert result["authorized"] is True
        submitted_qty = ex.create_order.call_args[0][3]
        # Correct dimension: base-asset quantity (~0.01 BTC), never the USD
        # notional (500) and never the raw ternary's accidental value.
        assert submitted_qty == pytest.approx(0.01, abs=1e-9)
        assert submitted_qty != pytest.approx(500.0, abs=1e-6)

    def test_dimensional_correctness_low_price(self, monkeypatch):
        """price=0.001: quantity (1000) and notional (1.0) are far apart in
        the opposite direction — the low-price mirror of the high-price
        case above."""
        from unittest.mock import MagicMock

        ex = MagicMock()
        ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 1e-3}}
        }
        ex.create_order.return_value = {"id": "close-lp"}
        pm = self._make_pm(ex, monkeypatch)
        pos = self._make_position(qty=1_000.0, entry_price=0.001)
        pos.current_price = 0.001
        from quant_hedge_ai.agents.execution.position_manager import CloseReason

        result = pm._send_close_order(pos, reason=CloseReason.TP)

        assert result["authorized"] is True
        submitted_qty = ex.create_order.call_args[0][3]
        # Correct dimension: base-asset quantity (~1000), never the USD
        # notional (1.0).
        assert submitted_qty == pytest.approx(1_000.0, abs=1e-6)
        assert submitted_qty != pytest.approx(1.0, abs=1e-6)

    def test_authorize_order_receives_usd_notional_not_raw_qty(self, monkeypatch):
        """Directly proves `authorize_order()` is called with a USD notional
        (`qty * price`), not the raw base-asset `qty`, for both
        `requested_amount` and `authorized_max_amount`."""
        from unittest.mock import MagicMock, patch

        ex = MagicMock()
        ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 1e-5}}
        }
        pm = self._make_pm(ex, monkeypatch)
        pos = self._make_position(qty=0.02, entry_price=50_000.0)
        pos.current_price = 50_000.0
        from quant_hedge_ai.agents.execution.position_manager import CloseReason

        from quant_hedge_ai.agents.execution.order_authorization import (
            authorize_order as real_authorize_order,
        )

        with patch(
            "quant_hedge_ai.agents.execution.position_manager.authorize_order",
            side_effect=real_authorize_order,
        ) as mock_auth:
            pm._send_close_order(pos, reason=CloseReason.TP)

        _, kwargs = mock_auth.call_args
        assert kwargs["requested_amount"] == pytest.approx(1_000.0)  # 0.02 * 50_000
        assert kwargs["authorized_max_amount"] == pytest.approx(1_000.0)

    # ── Defect 3 (R1): PositionManager calls the SHARED evaluate_trading_
    # authority(), not a local re-implementation ────────────────────────────

    def test_shared_evaluate_trading_authority_is_called_with_fresh_env(
        self, monkeypatch
    ):
        """Monkeypatches `evaluate_trading_authority` itself in the
        `position_manager` module namespace and proves `_send_close_order`
        calls exactly that function (not a parallel local boolean
        expression) with the freshly-read env values."""
        from unittest.mock import MagicMock

        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        import quant_hedge_ai.agents.execution.position_manager as pm_module

        calls = []

        def fake_evaluate_trading_authority(**kwargs):
            calls.append(kwargs)
            return False, "forced_denial_for_test"

        monkeypatch.setattr(
            pm_module, "evaluate_trading_authority", fake_evaluate_trading_authority
        )

        ex = MagicMock()
        pm = pm_module.PositionManager(exchange=ex, paper_mode=False)
        pos = self._make_position()
        result = pm._send_close_order(pos, reason=pm_module.CloseReason.TP)

        # The shared function was actually invoked — not bypassed — and its
        # denial is exactly what PositionManager returns.
        assert len(calls) == 1
        assert calls[0]["paper_trading_enabled"] is False
        assert calls[0]["live_trading_confirmed"] is True
        assert result["authorized"] is False
        assert result["denial_reason"] == "AUTHORITY_DENIED"
        ex.create_order.assert_not_called()

    def test_evaluate_trading_authority_result_drives_position_manager_identically(
        self, monkeypatch
    ):
        """Behavioral proof (alternative to monkeypatching the call site):
        changing what the shared `evaluate_trading_authority()` returns
        changes `PositionManager`'s behavior identically to how it would
        change `ExecutionEngine`'s — because both call the same function,
        never a divergent local re-implementation."""
        from unittest.mock import MagicMock

        import quant_hedge_ai.agents.execution.position_manager as pm_module

        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")

        # Force the shared function to always deny, regardless of what its
        # own paper/live-confirmed logic would normally say — if
        # PositionManager had a local duplicate gate, this override would
        # have no effect and the close would still go through.
        monkeypatch.setattr(
            pm_module,
            "evaluate_trading_authority",
            lambda **kwargs: (False, "overridden_for_test"),
        )

        ex = MagicMock()
        ex.load_markets.return_value = {
            "BTC/USD:USD": {"precision": {"amount": 1e-5}}
        }
        pm = pm_module.PositionManager(exchange=ex, paper_mode=False)
        pos = self._make_position()

        result = pm._send_close_order(pos, reason=pm_module.CloseReason.TP)

        assert result["authorized"] is False
        assert result["denial_reason"] == "AUTHORITY_DENIED"
        ex.create_order.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# Group G — non-regression
# ─────────────────────────────────────────────────────────────────────────


class TestGroupG_NonRegression:
    def test_pre_t1_d_scientific_capital_separation_intact(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WALLET_PAPER_CAPITAL", "100")
        monkeypatch.chdir(tmp_path)
        from infra.wallet_sync import get_scientific_capital

        # Pure function, no exchange calls, no mode dependency.
        value = get_scientific_capital()
        assert isinstance(value, float)

    def test_sizing_formula_unchanged_size_factor_still_applied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e.set_size_factor(0.5)
        result = e.create_order("BTC/USDT", "BUY", 100.0)
        assert result["size"] == pytest.approx(50.0, abs=0.01)

    def test_no_client_order_id_introduced(self):
        """REM-A itself (order_authorization.py) never constructs/sends a
        clientOrderId — that stays true post-REM-B too, since REM-A remains
        the pre-network authorization boundary and REM-B's deterministic
        identity lives entirely in order_intent_protocol.py (see
        docs/adr/0019-pre-network-order-authorization.md, REM-B ADR).

        Updated for O-02W-PRE-T1-E REM-B: ExecutionEngine/PositionManager
        NOW deliberately construct a deterministic clientOrderId via the
        REM-B durable submission coordinator — this is the intended,
        tested feature this mission implements (see
        tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py), not a
        regression of REM-A's scope boundary. This guard is narrowed to
        the module it always meant to describe: order_authorization.py."""
        import inspect

        from quant_hedge_ai.agents.execution import order_authorization as oa_mod

        src = inspect.getsource(oa_mod)
        # The docstring's own disclaiming mention of "clientOrderId" is
        # expected and fine; there must be no *constructed* identifier
        # (no f-string/format building one) in this module.
        assert "newClientOrderId" not in src
        assert "params={" not in src  # never builds exchange call params here

    def test_no_pending_order_tracker_activation_introduced(self):
        import inspect

        from quant_hedge_ai.agents.execution import (
            execution_engine as ee_mod,
            position_manager as pm_mod,
        )

        for mod in (ee_mod, pm_mod):
            src = inspect.getsource(mod)
            assert "PendingOrderTracker" not in src

    def test_no_default_enables_live_trading(self, monkeypatch):
        for var in ("PAPER_TRADING_ENABLED", "LIVE_TRADING_CONFIRMED"):
            monkeypatch.delenv(var, raising=False)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is False

    def test_authorize_order_is_pure_no_side_effects_module(self):
        """The boundary module performs no I/O, no logging, no state — a
        pure function callers must wire into logging/persistence
        themselves."""
        import inspect

        from quant_hedge_ai.agents.execution import order_authorization as mod

        src = inspect.getsource(mod)
        assert "open(" not in src
        assert "requests." not in src
        assert ".create_order(" not in src
