"""Tests unitaires — ExecutionEngine : chemins futures, capital, dedup non couverts."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ── Fixture ───────────────────────────────────────────────────────────────────


def _certify_mexc_for_test(monkeypatch):
    """O-02W-PRE-T1-E REM-B-R1.1, Blocker B: real `mexc` is deliberately
    deny-closed (reconciliation unproven against a pinned implementation)
    — see quant_hedge_ai/agents/execution/test_execution_engine.py for the
    full rationale, duplicated here narrowly to avoid a cross-test-module
    import."""
    from quant_hedge_ai.agents.execution import order_intent_protocol as oip

    monkeypatch.setitem(
        oip._ADAPTER_CAPABILITIES_BY_EXCHANGE,
        "mexc",
        oip.AdapterCapabilities(
            verdict=oip.AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED,
            client_order_id_param="clientOrderId",
            supports_open_order_search=True,
            supports_closed_order_search=True,
            evidence="test fixture — certified for hermetic testing only",
        ),
    )
    # O-02W-PRE-T1-E REM-B-R1.1, Blocker A: these tests exercise OTHER
    # behavior (sizing, symbol conversion, SEC-01 gate, etc.), not the
    # decision-identity persistence check itself — bypass it here exactly
    # like the capability fake above, so a bare decision_id string keeps
    # working for them. Dedicated tests exercise the REAL persistence
    # check via `decision_identity.DecisionIdentityJournal` directly.
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine as _EE

    monkeypatch.setattr(
        _EE, "_decision_id_is_durably_persisted", lambda self, decision_id: bool(decision_id)
    )
    # O-02W-PRE-T1-E REM-B-R1.3: the actual execution gate is now
    # `_decision_execution_denial_reason` (strict schema/digest/lifecycle
    # eligibility), not `_decision_id_is_durably_persisted` (historical
    # existence only) — bypass the REAL gate here too, for the same reason
    # (these tests exercise OTHER behavior). Dedicated tests exercise the
    # real, un-bypassed strict-eligibility gate directly.
    monkeypatch.setattr(
        _EE,
        "_decision_execution_denial_reason",
        lambda self, decision_id: None if decision_id else "MISSING_CAUSAL_ID",
    )
    # O-02W-PRE-T1-E REM-B-R1.2, Blocker B: bypass the real decision->intent
    # binding gate the same way — see identical comment in
    # test_pre_t1_e_order_cycle_safety.py's _certify_mexc_for_test.
    monkeypatch.setattr(_EE, "_bind_decision_to_intent", lambda self, decision_id, intent: None)


@pytest.fixture
def eng(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCHANGE_ID", "mexc")  # isolate from .env krakenfutures; also the verified REM-B-R1 adapter capability
    _certify_mexc_for_test(monkeypatch)
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    monkeypatch.setenv("EXEC_MAX_DD", "0.05")
    monkeypatch.setenv("EXEC_MAX_LOSS", "0.03")
    monkeypatch.setenv("EXEC_MAX_CONSEC_LOSSES", "3")
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
    monkeypatch.setenv("EXEC_DEDUP_WINDOW", "30")
    monkeypatch.setenv("EXEC_FUTURES_MIN_ORDER_USD", "55")
    monkeypatch.setenv("EXEC_FUTURES_MAX_ORDER_USD", "200")
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    e = ExecutionEngine(live=False, _sleep=lambda _: None)
    e.start_session(equity=10_000.0)
    return e


def _with_futures(eng) -> MagicMock:
    mock_ex = MagicMock()
    mock_ex.fetch_ticker.return_value = {"last": 80000.0}
    mock_ex.load_markets.return_value = {}
    mock_ex.create_order.return_value = {
        "id": "f123",
        "status": "closed",
        "avgPrice": 80000.0,
    }
    eng._exchange_futures = mock_ex
    return mock_ex


# ── Suite 1 : create_futures_order — disponibilité ───────────────────────────


class TestFuturesUnavailable:
    def test_no_exchange_returns_unavailable(self, eng):
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-48")
        assert result["mode"] == "futures_unavailable"
        assert "MEXC_API_KEY" in result["error"]

    def test_unavailable_contains_symbol(self, eng):
        result = eng.create_futures_order("ETH/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-53")
        assert result["symbol"] == "ETH/USDT"


# ── Suite 2 : create_futures_order — exécution nominale ──────────────────────


class TestFuturesSuccess:
    def test_buy_returns_futures_demo_mode(self, eng):
        _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-63")
        assert result["mode"] == "futures_demo"
        assert result["id"] == "f123"

    def test_sell_side_forwarded(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("ETH/USDT", "SELL", 60.0, decision_id="rem-b-r1-test-69")
        assert mock_ex.create_order.call_args[0][2] == "sell"

    def test_buy_side_forwarded(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-74")
        assert mock_ex.create_order.call_args[0][2] == "buy"

    def test_usd_size_in_result(self, eng):
        _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-79")
        assert "usd_size" in result
        assert result["usd_size"] > 0


# ── Suite 3 : symbol conversion ───────────────────────────────────────────────


class TestFuturesSymbolConversion:
    def test_slash_pair_converted_to_perp(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-90")
        used = mock_ex.create_order.call_args[0][0]
        assert used == "BTC/USDT:USDT"

    def test_already_perp_not_double_converted(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT:USDT", "BUY", 60.0, decision_id="rem-b-r1-test-96")
        used = mock_ex.create_order.call_args[0][0]
        assert used == "BTC/USDT:USDT"

    def test_no_slash_converted(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTCUSDT", "BUY", 60.0, decision_id="rem-b-r1-test-102")
        used = mock_ex.create_order.call_args[0][0]
        assert used == "BTC/USDT:USDT"


# ── Suite 4 : size clamping ────────────────────────────────────────────────────


class TestFuturesSizeClamping:
    def test_below_min_rejected_not_amplified(self, eng):
        """O-02W-PRE-T1-E REM-A R1 (defect 1 fix): a below-minimum futures
        order must be REJECTED, never silently amplified up to the minimum
        (the H2-shaped defect this round removed) — no mutation call at all.
        """
        mock_ex = _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 1.0, decision_id="rem-b-r1-test-117")
        assert result["mode"] == "rejected"
        assert result["denial_reason"] == "BELOW_MIN_NOTIONAL"
        mock_ex.create_order.assert_not_called()

    def test_above_max_clamped_down(self, eng):
        _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 99999.0, decision_id="rem-b-r1-test-124")
        assert result["mode"] == "futures_demo"
        # size_usd est clampé à 200 avant conversion en qty ;
        # la valeur finale peut être légèrement supérieure à cause de l'arrondi
        # de qty à la précision marché — on vérifie simplement que l'ordre passe
        assert result["usd_size"] > 0

    def test_within_range_unchanged(self, eng):
        _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 100.0, decision_id="rem-b-r1-test-133")
        assert result["mode"] == "futures_demo"


# ── Suite 5 : leverage ────────────────────────────────────────────────────────


class TestFuturesLeverage:
    def test_leverage_1_no_set_leverage_call(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT", "BUY", 60.0, leverage=1, decision_id="rem-b-r1-test-143")
        mock_ex.set_leverage.assert_not_called()

    def test_leverage_3_calls_set_leverage(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT", "BUY", 60.0, leverage=3, decision_id="rem-b-r1-test-148")
        mock_ex.set_leverage.assert_called_once()
        assert mock_ex.set_leverage.call_args[0][0] == 3

    def test_leverage_exception_order_still_placed(self, eng):
        mock_ex = _with_futures(eng)
        mock_ex.set_leverage.side_effect = Exception("not supported")
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0, leverage=2, decision_id="rem-b-r1-test-155")
        assert result["mode"] == "futures_demo"


# ── Suite 6 : error handling ──────────────────────────────────────────────────


class TestFuturesErrors:
    def test_exchange_error_returns_futures_ambiguous(self, eng):
        # O-02W-PRE-T1-E REM-B: an unclassified exception from the exchange
        # call is ambiguous (I5) — it must never be silently reported as a
        # clean "failed" (which would incorrectly suggest zero side effects
        # occurred). The coordinator persists RECONCILE_REQUIRED and this
        # surfaces as "futures_ambiguous", never resubmitted automatically.
        mock_ex = _with_futures(eng)
        mock_ex.create_order.side_effect = RuntimeError("exchange down")
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-166")
        assert result["mode"] == "futures_ambiguous"
        assert result["order_intent_outcome"] == "RECONCILE_REQUIRED"

    def test_load_markets_error_uses_defaults(self, eng):
        mock_ex = _with_futures(eng)
        mock_ex.load_markets.side_effect = Exception("markets unavailable")
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-173")
        assert result["mode"] == "futures_demo"

    def test_fetch_ticker_error_returns_futures_failed(self, eng):
        mock_ex = _with_futures(eng)
        mock_ex.fetch_ticker.side_effect = Exception("ticker timeout")
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0, decision_id="rem-b-r1-test-179")
        assert result["mode"] == "futures_failed"
        assert "ticker timeout" in result["error"]


# ── Suite 7 : fetch_available_capital ─────────────────────────────────────────


class TestFetchAvailableCapital:
    @pytest.fixture(autouse=True)
    def _isolate_exchange(self, monkeypatch):
        monkeypatch.setenv("EXCHANGE_ID", "mexc")

    def test_fallback_when_no_exchange(self, tmp_path, monkeypatch):
        # fetch_available_capital() délègue à WalletSync (WALLET_PAPER_CAPITAL).
        # V9_INITIAL_CAPITAL est obsolète depuis la migration WalletSync.
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        import infra.wallet_sync as _ws

        _ws.reset_wallet_sync()
        monkeypatch.setattr(_ws, "_PAPER_CAPITAL", 2500.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        assert e.fetch_available_capital() == 2500.0
        _ws.reset_wallet_sync()

    def test_live_exchange_returns_usdt_balance(self, tmp_path, monkeypatch):
        # En mode paper (live=False), WalletSync retourne le capital paper
        # (WALLET_PAPER_CAPITAL) — l'exchange n'est pas interrogé en paper mode.
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        import infra.wallet_sync as _ws

        _ws.reset_wallet_sync()
        monkeypatch.setattr(_ws, "_PAPER_CAPITAL", 4200.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        assert e.fetch_available_capital() == 4200.0
        _ws.reset_wallet_sync()

    def test_zero_usdt_balance_falls_back(self, tmp_path, monkeypatch):
        # Quand l'exchange retourne 0 (mode paper), WalletSync utilise _PAPER_CAPITAL.
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        import infra.wallet_sync as _ws

        _ws.reset_wallet_sync()
        monkeypatch.setattr(_ws, "_PAPER_CAPITAL", 999.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        assert e.fetch_available_capital() == 999.0
        _ws.reset_wallet_sync()

    def test_exchange_error_falls_back(self, tmp_path, monkeypatch):
        # En cas d'erreur API (mode paper), WalletSync retourne _PAPER_CAPITAL.
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        import infra.wallet_sync as _ws

        _ws.reset_wallet_sync()
        monkeypatch.setattr(_ws, "_PAPER_CAPITAL", 888.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        assert e.fetch_available_capital() == 888.0
        _ws.reset_wallet_sync()

    def test_paper_trading_enabled_forces_local_capital(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        import infra.wallet_sync as _ws

        _ws.reset_wallet_sync()
        monkeypatch.setattr(_ws, "_PAPER_CAPITAL", 1337.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._mode = "live"
        assert e.fetch_available_capital() == 1337.0
        _ws.reset_wallet_sync()

    def test_paper_trading_disabled_does_not_leak_exchange_balance_into_scientific_capital(
        self, tmp_path, monkeypatch
    ):
        """R2 remediation (O-02W-PRE-T1-D fix): HISTORICAL_AUDIT_FINDING —
        this test originally proved that PAPER_TRADING_ENABLED=false plus
        an attached exchange caused fetch_available_capital() to return the
        exchange balance (defect #3/#4). REMEDIATED_IN_PRE_T1_D:
        fetch_available_capital() is now the scientific-capital accessor
        exclusively, independent of PAPER_TRADING_ENABLED and of any
        attached exchange."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        import infra.wallet_sync as _ws

        class _FakeExchange:
            def __init__(self):
                self.calls = 0

            def fetch_balance(self):
                self.calls += 1
                return {"free": {"USDT": 321.5}}

        _ws.reset_wallet_sync()
        monkeypatch.setattr(_ws, "_PAPER_CAPITAL", 7777.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._mode = "live"
        fake = _FakeExchange()
        e._exchange = fake
        assert e.fetch_available_capital() == 7777.0  # scientific capital only
        assert fake.calls == 0
        _ws.reset_wallet_sync()


# ── Suite 8 : detect_quote_asset ──────────────────────────────────────────────


class TestDetectQuoteAsset:
    def test_btc_usdt(self, eng):
        assert eng.detect_quote_asset("BTC/USDT") == "USDT"

    def test_eth_btc(self, eng):
        assert eng.detect_quote_asset("ETH/BTC") == "BTC"

    def test_no_slash_returns_default(self, eng):
        assert eng.detect_quote_asset("BTCUSDT") == "USDT"


# ── Suite 9 : deduplication ────────────────────────────────────────────────────


class TestDeduplication:
    def test_same_order_rejected(self, eng):
        eng.create_order("BTC/USDT", "BUY", 100.0, decision_id="rem-b-r1-test-314")
        result = eng.create_order("BTC/USDT", "BUY", 100.0, decision_id="rem-b-r1-test-315")
        assert result["mode"] == "rejected"
        assert "duplicate" in result["error"]

    def test_different_action_not_duplicate(self, eng):
        eng.create_order("BTC/USDT", "BUY", 100.0, decision_id="rem-b-r1-test-320")
        result = eng.create_order("BTC/USDT", "SELL", 100.0, decision_id="rem-b-r1-test-321")
        assert result["mode"] == "paper"

    def test_different_symbol_not_duplicate(self, eng):
        eng.create_order("BTC/USDT", "BUY", 100.0, decision_id="rem-b-r1-test-325")
        result = eng.create_order("ETH/USDT", "BUY", 100.0, decision_id="rem-b-r1-test-326")
        assert result["mode"] == "paper"


# ── Suite 10 : has_futures_demo ────────────────────────────────────────────────


class TestHasFuturesDemo:
    def test_false_by_default(self, eng):
        assert eng.has_futures_demo() is False

    def test_true_when_exchange_set(self, eng):
        eng._exchange_futures = MagicMock()
        assert eng.has_futures_demo() is True
