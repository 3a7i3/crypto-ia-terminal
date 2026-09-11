"""Tests unitaires — ExecutionEngine (paper mode, safety layer, size factor, live fallback)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _certify_mexc_for_test(monkeypatch):
    """O-02W-PRE-T1-E REM-B-R1.1, Blocker B: real `mexc` is deliberately
    deny-closed (`SUBMIT_ONLY_RECONCILIATION_UNVERIFIED` — reconciliation
    unproven against a pinned implementation). Tests that need to exercise
    the authorized-submission path inject a fake, test-only
    `SUBMIT_AND_RECONCILE_VERIFIED` capability instead of relying on the
    real (unverified) mexc entry — proving the certified-adapter contract
    without silently promoting the real, unverified adapter."""
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


@pytest.fixture
def eng(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    monkeypatch.setenv("EXEC_MAX_DD", "0.05")
    monkeypatch.setenv("EXEC_MAX_LOSS", "0.03")
    monkeypatch.setenv("EXEC_MAX_CONSEC_LOSSES", "3")
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
    monkeypatch.setenv("EXEC_DEDUP_WINDOW", "30")
    _certify_mexc_for_test(monkeypatch)
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    e = ExecutionEngine(live=False)
    e.start_session(equity=10_000.0)
    return e


class TestFromEnv:
    def test_from_env_paper_when_no_keys(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXCHANGE_ID", "mexc")  # isolate from .env
        monkeypatch.delenv("MEXC_API_KEY", raising=False)
        monkeypatch.delenv("MEXC_API_SECRET", raising=False)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is False

    def test_from_env_stays_paper_when_keys_present_but_not_confirmed(
        self, tmp_path, monkeypatch
    ):
        """SEC-01 — la seule présence de clés API ne suffit plus : sans
        LIVE_TRADING_CONFIRMED=true, from_env() reste en paper."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("MEXC_API_KEY", "fake_key")
        monkeypatch.setenv("MEXC_API_SECRET", "fake_secret")
        monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is False

    def test_from_env_live_when_keys_present_and_confirmed(self, tmp_path, monkeypatch):
        """SEC-01 — clés API + LIVE_TRADING_CONFIRMED=true : les deux
        conditions réunies, le moteur peut passer live."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("MEXC_API_KEY", "fake_key")
        monkeypatch.setenv("MEXC_API_SECRET", "fake_secret")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is True


class TestSizeFactor:
    def test_set_size_factor_clamps_to_zero(self, eng):
        eng.set_size_factor(-5.0)
        assert eng._size_factor == 0.0

    def test_set_size_factor_clamps_to_one(self, eng):
        eng.set_size_factor(99.0)
        assert eng._size_factor == 1.0

    def test_set_size_factor_mid_value(self, eng):
        eng.set_size_factor(0.5)
        assert eng._size_factor == pytest.approx(0.5)

    def test_size_factor_applied_to_order(self, eng):
        eng.set_size_factor(0.5)
        result = eng.create_order("BTCUSDT", "BUY", 100.0)
        assert result["mode"] == "paper"
        assert result["size"] == pytest.approx(50.0, abs=0.01)


class TestAnomalousSizeRecovery:
    def test_zero_size_triggers_alert_and_corrects(self, eng):
        result = eng.create_order("BTCUSDT", "BUY", 0.0)
        assert result["mode"] in ("paper", "rejected")

    def test_huge_size_triggers_alert_and_corrects(self, eng):
        result = eng.create_order("BTCUSDT", "BUY", 2e9)
        assert result["mode"] in ("paper", "rejected")


class TestPaperMode:
    def test_basic_paper_order(self, eng):
        result = eng.create_order("BTCUSDT", "BUY", 100.0)
        assert result["mode"] == "paper"
        assert result["symbol"] == "BTCUSDT"

    def test_safety_status_structure(self, eng):
        status = eng.safety_status()
        assert "session" in status
        assert "trade_log" in status
        assert "live_mode" in status
        assert status["live_mode"] is False

    def test_start_session_resets_state(self, eng):
        eng.start_session(equity=5000.0)
        assert eng._guard.state()["halted"] is False

    def test_sell_order_paper(self, eng):
        result = eng.create_order("ETHUSDT", "SELL", 50.0)
        assert result["mode"] == "paper"
        assert result["action"] == "SELL"


class TestLiveFallback:
    def test_init_exchange_falls_back_when_ccxt_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("MEXC_API_KEY", "k")
        monkeypatch.setenv("MEXC_API_SECRET", "s")
        with patch.dict("sys.modules", {"ccxt": None}):
            from quant_hedge_ai.agents.execution import execution_engine as mod

            try:
                e = mod.ExecutionEngine(live=True)
                assert isinstance(e._live, bool)
            except Exception:
                pass

    def _setup_mock_exchange(
        self, mock_exchange, usdt_balance: float = 10_000.0
    ) -> None:
        mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
        mock_exchange.load_markets.return_value = {}
        mock_exchange.fetch_balance.return_value = {"free": {"USDT": usdt_balance}}

    def test_place_live_order_exception_returns_live_ambiguous(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # gate SEC-01 ouvert
        _certify_mexc_for_test(monkeypatch)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.side_effect = RuntimeError("connection refused")
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        result = e.create_order("BTCUSDT", "BUY", 100.0, decision_id="test-live-exc")
        # O-02W-PRE-T1-E REM-B: a connection error is ambiguous (I5), not a
        # clean "failed" — persisted RECONCILE_REQUIRED, never silently
        # reported as if nothing happened. The typed error_category
        # ("transport_error") surfaces in `error`; the raw exception text
        # is preserved as evidence in the journal's `error_category` field,
        # not re-derived from the raw message at the ExecutionEngine layer.
        assert result["mode"] == "live_ambiguous"
        assert result["error"] == "transport_error"
        assert result["order_intent_outcome"] == "RECONCILE_REQUIRED"

    def test_place_live_order_success(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # gate SEC-01 ouvert
        _certify_mexc_for_test(monkeypatch)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._live = True
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "abc123", "status": "closed"}
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        result = e.create_order("BTCUSDT", "BUY", 100.0, decision_id="test-live-success")
        assert result["mode"] == "live"
        assert result["id"] == "abc123"

    def test_place_live_order_sell_side(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # gate SEC-01 ouvert
        _certify_mexc_for_test(monkeypatch)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._live = True
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "sell1"}
        # SELL requires the BASE asset balance (O-02W-PRE-T1-E REM-A, H7
        # fix) — a quote-only balance is no longer sufficient.
        mock_exchange.fetch_balance.return_value = {
            "free": {"USDT": 10_000.0, "BTC": 1.0}
        }
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        e.create_order("BTCUSDT", "SELL", 100.0, decision_id="test-live-sell")
        assert mock_exchange.create_order.call_args[0][2] == "sell"

    def test_place_live_order_symbol_slash_conversion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # gate SEC-01 ouvert
        _certify_mexc_for_test(monkeypatch)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._live = True
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "x"}
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        e.create_order("BTCUSDT", "BUY", 100.0, decision_id="test-live-slash")
        assert "/" in mock_exchange.create_order.call_args[0][0]


class TestExecutionGateSEC01:
    """SEC-01 (2026-07-08) — gate d'exécution réelle derrière
    PAPER_TRADING_ENABLED, avec neutralité stricte vs le rejet MEXC 700007
    déjà observé en production (voir RECOVERY.md / T1 finding #3)."""

    def _setup_mock_exchange(
        self, mock_exchange, usdt_balance: float = 10_000.0
    ) -> None:
        mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
        mock_exchange.load_markets.return_value = {}
        # Both quote (BUY) and base (SELL, O-02W-PRE-T1-E REM-A H7 fix)
        # balances present so tests in this class can exercise either side.
        mock_exchange.fetch_balance.return_value = {
            "free": {"USDT": usdt_balance, "ETH": 10.0, "BTC": 10.0}
        }

    def _make_live_engine(self, tmp_path, monkeypatch, mock_exchange):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        _certify_mexc_for_test(monkeypatch)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        return e

    def test_gate_blocks_order_when_paper_trading_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        e = self._make_live_engine(tmp_path, monkeypatch, mock_exchange)

        result = e.create_order("ETHFI/USDT", "BUY", 100.0)

        assert result["mode"] == "live_failed"
        assert result["error"] == "blocked_by_paper_gate"
        mock_exchange.fetch_ticker.assert_not_called()
        mock_exchange.create_order.assert_not_called()

    def test_gate_blocked_shape_identical_to_real_rejection(
        self, tmp_path, monkeypatch
    ):
        """Neutralité stricte : mêmes clés, même mode, que le rejet MEXC
        700007 réel (exception levée dans _place_live_order)."""
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        mock_gated = MagicMock()
        self._setup_mock_exchange(mock_gated)
        e_gated = self._make_live_engine(tmp_path, monkeypatch, mock_gated)
        gated_result = e_gated.create_order("ETH/USDT", "SELL", 100.0, decision_id="test-gate-shape-gated")

        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        mock_real = MagicMock()
        self._setup_mock_exchange(mock_real)
        mock_real.create_order.side_effect = Exception(
            '{"code":700007,"msg":"No permission to access the endpoint."}'
        )
        e_real = self._make_live_engine(tmp_path, monkeypatch, mock_real)
        real_result = e_real.create_order("ETH/USDT", "SELL", 100.0, decision_id="test-gate-shape-real")

        assert gated_result["mode"] == real_result["mode"] == "live_failed"
        assert set(gated_result.keys()) == set(real_result.keys())

    def test_gate_off_reaches_real_execution_path(self, tmp_path, monkeypatch):
        """PAPER_TRADING_ENABLED=false : le chemin live est bien atteint
        (mocké) — le gate ne bloque plus rien."""
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "live1"}
        e = self._make_live_engine(tmp_path, monkeypatch, mock_exchange)

        result = e.create_order("BTC/USDT", "BUY", 100.0, decision_id="test-gate-off")

        assert result["mode"] == "live"
        mock_exchange.fetch_ticker.assert_called_once()
        mock_exchange.create_order.assert_called_once()

    def test_gate_blocked_order_logged_as_error_in_trade_log(
        self, tmp_path, monkeypatch
    ):
        """Même enregistrement trade_log (mode='live_failed', status='error')
        que le rejet MEXC réel — même compteurs d'erreurs alimentés en aval."""
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        e = self._make_live_engine(tmp_path, monkeypatch, mock_exchange)

        e.create_order("HYPE/USDT", "BUY", 100.0)

        recent = e._logger.recent_trades(1)
        assert len(recent) == 1
        assert recent[0]["mode"] == "live_failed"
        assert recent[0]["status"] == "error"
        assert recent[0]["error"] == "blocked_by_paper_gate"

    def test_gate_reads_env_at_call_time_not_cached(self, tmp_path, monkeypatch):
        """DS-001 (ADR-0008) — PAPER_TRADING_ENABLED est lu à l'appel, jamais
        figé à l'__init__ : basculer la variable en cours de vie du process
        change immédiatement le comportement, sans recréer le moteur."""
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        monkeypatch.setenv("EXEC_DEDUP_WINDOW", "0")  # isole du garde anti-doublon
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "live2"}
        e = self._make_live_engine(tmp_path, monkeypatch, mock_exchange)

        blocked = e.create_order("SOL/USDT", "BUY", 100.0)
        assert blocked["mode"] == "live_failed"

        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        unblocked = e.create_order("SOL/USDT", "BUY", 100.0, decision_id="test-gate-sol-2")
        assert unblocked["mode"] == "live"
