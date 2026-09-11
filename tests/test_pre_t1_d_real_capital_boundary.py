"""O-02W-PRE-T1-D — Real capital boundary audit — hermetic characterization tests.

Audit-only mission: these tests establish, from actually-executed code, the
provenance of capital used by sizing/risk/execution across PAPER / TESTNET /
REAL_API modes, and the WalletSync singleton construction/refresh order.

Scope discipline:
  - No network, no secrets, no real exchange/Telegram calls.
  - Fake exchange objects and monkeypatched env vars only.
  - Every test resets the WalletSync singleton before and after, and uses
    tmp_path for the paper ledger so nothing is written into the repo CWD.
  - These are CHARACTERIZATION tests: they describe the system's actual
    current behavior. A passing test is not an endorsement that the
    behavior is correct — see docs/contracts/O-02W-PRE-T1-D_REAL_CAPITAL_BOUNDARY.md
    for the classification of each behavior and the final verdict.

Behavioral matrix covered (see contract for full narrative): A-L.
"""

from __future__ import annotations

import json

import pytest

import infra.wallet_sync as ws


# ─────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_wallet_singleton():
    """Hard reset of the WalletSync singleton before and after each test —
    the singleton is module-global state and must never leak between tests
    or into other test modules running in the same process."""
    ws.reset_wallet_sync()
    yield
    ws.reset_wallet_sync()


@pytest.fixture
def isolated_ledger(tmp_path, monkeypatch):
    """Point the paper ledger at a tmp_path file — never the repo CWD."""
    trades_path = tmp_path / "paper_trades.jsonl"
    monkeypatch.setattr(ws, "_TRADES_LOG", trades_path)
    return trades_path


def _write_close(path, pnl_usd: float) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "CLOSE", "pnl_usd": pnl_usd}) + "\n")


class FakeExchange:
    """Minimal ccxt-shaped fake — no network, deterministic balance."""

    def __init__(self, free_usdt: float = 0.0, raise_on_fetch: bool = False):
        self._free_usdt = free_usdt
        self._raise = raise_on_fetch
        self.calls = 0

    def fetch_balance(self):
        self.calls += 1
        if self._raise:
            raise ConnectionError("simulated network failure — no real call made")
        return {"free": {"USDT": self._free_usdt}}


# ─────────────────────────────────────────────────────────────────────────
# H3 — mode-predicate consistency (env truthy-set divergence)
# ─────────────────────────────────────────────────────────────────────────


class TestH3ModePredicateConsistency:
    """PAPER_TRADING_ENABLED is read by at least two independent predicates
    in this codebase with DIFFERENT truthy sets:

      - ExecutionEngine._paper_trading_enabled() / fetch_available_capital():
        {"1", "true", "yes", "on"} (case-insensitive).
      - core/advisor_loop.py's bootstrap-time `_paper_mode` local
        (line ~3778): strict `.lower() == "true"` only.

    This test proves the divergence exists in ExecutionEngine's own gate
    (SOURCE_PROVEN) via direct import of the static predicate, and proves
    the four accepted values are treated identically by it (BEHAVIOR_PROVEN_HERMETIC),
    which is the precondition for the divergence claim to matter for §H3/K.
    """

    @pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE", "On", "YES"])
    def test_execution_engine_accepts_full_truthy_set(self, value, monkeypatch):
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        monkeypatch.setenv("PAPER_TRADING_ENABLED", value)
        assert ExecutionEngine._paper_trading_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", ""])
    def test_execution_engine_rejects_falsy_values(self, value, monkeypatch):
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        monkeypatch.setenv("PAPER_TRADING_ENABLED", value)
        assert ExecutionEngine._paper_trading_enabled() is False

    def test_execution_engine_default_is_paper_when_unset(self, monkeypatch):
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        monkeypatch.delenv("PAPER_TRADING_ENABLED", raising=False)
        assert ExecutionEngine._paper_trading_enabled() is True

    @pytest.mark.parametrize("value", ["1", "yes", "on"])
    def test_advisor_loop_bootstrap_predicate_diverges_from_execution_engine(
        self, value, monkeypatch
    ):
        """CONTRADICTION_FOUND: reproduces core/advisor_loop.py's bootstrap
        `_paper_mode` computation verbatim (it is a bare local, not an
        importable function) and shows it disagrees with
        ExecutionEngine._paper_trading_enabled() for "1"/"yes"/"on".

        Scope note: at bootstrap this local only selects which Telegram
        STANDBY/LIVE message string is sent (observability/real_accounts
        Flow 1, DISPLAY_ONLY) — it does not feed sizing/risk/execution.
        The decisional gate (ExecutionEngine._paper_trading_enabled(),
        used inside fetch_available_capital() and _place_live_order())
        already uses the full {1,true,yes,on} set consistently. This test
        exists to make the source-level predicate divergence explicit and
        auditable, not to claim it is currently decisional.
        """
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        monkeypatch.setenv("PAPER_TRADING_ENABLED", value)

        # Verbatim reproduction of core/advisor_loop.py line ~3778.
        import os

        advisor_loop_paper_mode = (
            os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"
        )
        execution_engine_paper = ExecutionEngine._paper_trading_enabled()

        assert execution_engine_paper is True
        assert advisor_loop_paper_mode is False
        assert advisor_loop_paper_mode != execution_engine_paper


# ─────────────────────────────────────────────────────────────────────────
# H2 / H1 / L — WalletSync singleton construction order
# ─────────────────────────────────────────────────────────────────────────


class TestH2SingletonConstructionOrder:
    def test_first_call_with_no_mode_defaults_from_exchange_mode_env(
        self, monkeypatch, isolated_ledger
    ):
        """SOURCE_PROVEN: get_wallet_sync() falls back to os.getenv(
        "EXCHANGE_MODE", "paper") only when the singleton does not yet
        exist and no explicit mode is passed."""
        monkeypatch.setenv("EXCHANGE_MODE", "live")
        wallet = ws.get_wallet_sync()
        assert wallet.mode == "live"

    def test_singleton_created_first_retains_its_mode_despite_later_explicit_mode(
        self, monkeypatch, isolated_ledger
    ):
        """Scenario L: a caller that creates the singleton BEFORE the call
        that explicitly supplies wallet_mode gets no retroactive mode
        change. get_wallet_sync(mode=...) only sets mode at first
        construction; a later call with a different `mode` argument is
        silently ignored for an already-existing singleton — only a
        missing `exchange` is attached retroactively, never mode."""
        monkeypatch.setenv("EXCHANGE_MODE", "live")
        first = ws.get_wallet_sync()  # created with mode="live" from env
        assert first.mode == "live"

        second = ws.get_wallet_sync(mode="paper")  # explicit mode requested
        assert second is first
        assert second.mode == "live"  # NOT "paper" — mode ignored post-creation

    def test_bootstrap_capital_x_creates_singleton_before_fetch_available_capital_mode(
        self, monkeypatch, isolated_ledger
    ):
        """H2: reproduces core/advisor_loop.py's actual bootstrap order —
        bootstrap_capital_x(exchange) runs first (creates the singleton,
        mode resolved from EXCHANGE_MODE env, default "paper"), and only
        later does ExecutionEngine.fetch_available_capital() call
        get_wallet_sync(mode=wallet_mode) with a mode computed from
        PAPER_TRADING_ENABLED. Because the singleton already exists, that
        second mode request is a no-op for `.mode`."""
        monkeypatch.delenv("EXCHANGE_MODE", raising=False)  # defaults to "paper"
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # would request live/testnet

        fake_exchange = FakeExchange(free_usdt=500.0)

        # Step 1 (advisor_loop.py ~3777): bootstrap_capital_x() creates the
        # singleton via get_wallet_sync(exchange=exchange) with no mode arg.
        x = ws.bootstrap_capital_x(exchange=fake_exchange)
        assert x == 500.0
        wallet = ws.get_wallet_sync()
        assert wallet.mode == "paper"  # EXCHANGE_MODE default, NOT PAPER_TRADING_ENABLED

        # Step 2 (execution_engine.py fetch_available_capital): would like
        # wallet_mode="live" here (PAPER_TRADING_ENABLED=false), but the
        # singleton already exists — mode is NOT retroactively changed.
        wallet2 = ws.get_wallet_sync(exchange=fake_exchange, mode="live")
        assert wallet2 is wallet
        assert wallet2.mode == "paper"  # still paper — construction order won

    def test_exchange_attaches_retroactively_when_singleton_created_without_one(
        self, isolated_ledger
    ):
        """Only the exchange object is attached retroactively to an
        existing singleton lacking one — this is asymmetric with mode,
        which is never retroactively changed (see test above)."""
        wallet = ws.get_wallet_sync()  # no exchange, mode="paper" default
        assert wallet._exchange is None

        fake_exchange = FakeExchange(free_usdt=42.0)
        wallet2 = ws.get_wallet_sync(exchange=fake_exchange)
        assert wallet2 is wallet
        assert wallet2._exchange is fake_exchange


# ─────────────────────────────────────────────────────────────────────────
# Scenario A-C — PAPER mode isolation from exchange balance (H1)
# ─────────────────────────────────────────────────────────────────────────


class TestScenarioAPaperIsolationWithRealBalance:
    def test_paper_mode_ignores_real_exchange_balance(
        self, monkeypatch, isolated_ledger
    ):
        """Scenario A: PAPER enabled, exchange available with a real
        (large, distinctive) balance — the balance must NOT influence
        get_balance() at all. BEHAVIOR_PROVEN_HERMETIC."""
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)
        fake_exchange = FakeExchange(free_usdt=999_999.0)

        wallet = ws.WalletSync(exchange=fake_exchange, mode="paper")
        balance = wallet.get_balance()

        assert balance == 1000.0
        assert fake_exchange.calls == 0  # never even queried in paper mode

    def test_execution_engine_fetch_available_capital_paper_mode_ignores_exchange(
        self, monkeypatch, isolated_ledger, tmp_path
    ):
        """Same as above, but through the real call path:
        ExecutionEngine.fetch_available_capital() -> get_wallet_sync()."""
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 250.0)
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        eng = ExecutionEngine(live=False)
        eng._exchange = FakeExchange(free_usdt=1_234_567.0)
        eng._mode = "live"  # even if internal _mode claims live

        capital = eng.fetch_available_capital()
        assert capital == 250.0


class TestScenarioBPaperNoExchange:
    def test_paper_mode_with_no_exchange_uses_paper_capital(
        self, monkeypatch, isolated_ledger
    ):
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 100.0)
        wallet = ws.WalletSync(exchange=None, mode="paper")
        assert wallet.get_balance() == 100.0


class TestScenarioCPaperTruthyVariants:
    @pytest.mark.parametrize("value", ["1", "yes", "on"])
    def test_execution_engine_paper_capital_source_for_truthy_variants(
        self, value, monkeypatch, isolated_ledger, tmp_path
    ):
        """Scenario C: PAPER_TRADING_ENABLED = "1" / "yes" / "on" must
        route to wallet_mode="paper" inside fetch_available_capital() —
        proves the decisional predicate (not the advisor_loop bootstrap
        display-only local from TestH3) uses the full truthy set."""
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 77.0)
        monkeypatch.setenv("PAPER_TRADING_ENABLED", value)
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        eng = ExecutionEngine(live=False)
        eng._exchange = FakeExchange(free_usdt=888.0)
        eng._mode = "live"

        assert eng.fetch_available_capital() == 77.0


# ─────────────────────────────────────────────────────────────────────────
# Scenario D/E — TESTNET_API / REAL_API modes
# ─────────────────────────────────────────────────────────────────────────


class TestScenarioDETestnetAndRealApiModes:
    def test_testnet_mode_fetches_from_exchange(
        self, monkeypatch, isolated_ledger, tmp_path
    ):
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        eng = ExecutionEngine(live=False)
        eng._exchange = FakeExchange(free_usdt=321.5)
        eng._mode = "testnet"

        assert eng.fetch_available_capital() == 321.5

    def test_live_mode_fetches_from_exchange(
        self, monkeypatch, isolated_ledger, tmp_path
    ):
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        eng = ExecutionEngine(live=False)
        eng._exchange = FakeExchange(free_usdt=4321.0)
        eng._mode = "live"

        assert eng.fetch_available_capital() == 4321.0

    def test_live_order_blocked_by_paper_gate_even_with_exchange_attached(
        self, monkeypatch, tmp_path
    ):
        """H1/E: PAPER_TRADING_ENABLED true (default) blocks a live order
        BEFORE any network call reaches the exchange, per SEC-01, even
        when self._live and self._exchange are set."""
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        monkeypatch.delenv("PAPER_TRADING_ENABLED", raising=False)  # default true

        eng = ExecutionEngine(live=False)
        eng._live = True
        eng._exchange = FakeExchange(free_usdt=999.0)

        result = eng._place_live_order("BTC/USDT", "BUY", 50.0)
        assert result["mode"] == "live_failed"
        assert result["error"] == "blocked_by_paper_gate"
        assert eng._exchange.calls == 0  # never reached the exchange


# ─────────────────────────────────────────────────────────────────────────
# Scenario F/G/H — API errors / stale cache / zero balance (H4)
# ─────────────────────────────────────────────────────────────────────────


class TestScenarioFGHApiFailureFallbacks:
    def test_live_mode_api_error_no_cache_falls_back_to_paper_capital_constant(
        self, monkeypatch, isolated_ledger
    ):
        """Scenario F: live/testnet mode, API raises, no prior successful
        fetch (no cache) -> _fallback() -> _base_capital() -> since
        self._x is None (never bootstrapped), returns _PAPER_CAPITAL.
        H4 CONFIRMED: WALLET_PAPER_CAPITAL numerically feeds a live-mode
        sizing call under this condition."""
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 42.0)
        fake_exchange = FakeExchange(raise_on_fetch=True)
        wallet = ws.WalletSync(exchange=fake_exchange, mode="live")

        balance = wallet.get_balance(force_refresh=True)
        assert balance == 42.0  # WALLET_PAPER_CAPITAL, silently, in "live" mode

    def test_live_mode_api_error_with_stale_cache_returns_last_known_value(
        self, monkeypatch, isolated_ledger
    ):
        """Scenario G: a prior successful fetch cached _last_value; a
        later failure (even outside the TTL window, via force_refresh)
        returns that stale value rather than the paper constant."""
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 42.0)
        monkeypatch.setattr(ws, "_CACHE_TTL_S", 0.0)  # cache never "fresh" by TTL
        fake_exchange = FakeExchange(free_usdt=777.0)
        wallet = ws.WalletSync(exchange=fake_exchange, mode="live")

        first = wallet.get_balance(force_refresh=True)
        assert first == 777.0

        fake_exchange._raise = True  # now the exchange starts failing
        second = wallet.get_balance(force_refresh=True)
        assert second == 777.0  # stale _last_value, not 42.0 paper constant

    def test_live_mode_zero_balance_falls_back_rather_than_returning_zero(
        self, monkeypatch, isolated_ledger
    ):
        """Scenario H: exchange returns free USDT = 0. get_balance()'s
        `if usdt > 0` guard rejects it and falls through to _fallback(),
        so a genuinely empty live account silently reads as the paper
        constant (or stale cache) rather than as 0.0 — the caller cannot
        distinguish 'exchange truly empty' from 'exchange unreachable'."""
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 42.0)
        fake_exchange = FakeExchange(free_usdt=0.0)
        wallet = ws.WalletSync(exchange=fake_exchange, mode="live")

        balance = wallet.get_balance(force_refresh=True)
        assert balance == 42.0

    def test_bootstrap_zero_balance_returns_none_not_zero(self, isolated_ledger):
        """Contrast with bootstrap(): bootstrap()'s own MIN_CAPITAL_X
        check does correctly return None (not silently substitute) when
        the API balance is below MIN_CAPITAL_X — this is the one capital
        entry point in this module that fails closed to None instead of
        substituting a number."""
        fake_exchange = FakeExchange(free_usdt=0.0)
        wallet = ws.WalletSync(mode="live")
        result = wallet.bootstrap(fake_exchange)
        assert result is None
        assert wallet.capital_x is None


# ─────────────────────────────────────────────────────────────────────────
# Scenario I — capital below MIN_CAPITAL_X
# ─────────────────────────────────────────────────────────────────────────


class TestScenarioIBelowMinCapital:
    def test_set_x_rejects_value_below_min_capital(self, isolated_ledger):
        wallet = ws.WalletSync(mode="live")
        with pytest.raises(ValueError):
            wallet.set_x(0.5)  # < MIN_CAPITAL_X (1.0)
        assert wallet.capital_x is None

    def test_bootstrap_below_min_capital_returns_none(self, isolated_ledger):
        fake_exchange = FakeExchange(free_usdt=0.99)
        wallet = ws.WalletSync(mode="live")
        assert wallet.bootstrap(fake_exchange) is None


# ─────────────────────────────────────────────────────────────────────────
# Scenario J — positive capital refresh after initialization (H5)
# ─────────────────────────────────────────────────────────────────────────


class TestScenarioJRefreshPropagation:
    def test_live_mode_get_balance_reflects_updated_exchange_balance_after_ttl(
        self, monkeypatch, isolated_ledger
    ):
        monkeypatch.setattr(ws, "_CACHE_TTL_S", 0.0)
        fake_exchange = FakeExchange(free_usdt=100.0)
        wallet = ws.WalletSync(exchange=fake_exchange, mode="live")

        first = wallet.get_balance()
        assert first == 100.0

        fake_exchange._free_usdt = 150.0
        second = wallet.get_balance(force_refresh=True)
        assert second == 150.0

    def test_capital_allocation_engine_update_capital_changes_subsequent_kelly_size(
        self,
    ):
        """H5: CapitalAllocationEngine.update_capital() does propagate into
        subsequent .allocate() calls — the consumer itself is not frozen,
        only the `order_size` base value computed once in
        core/advisor_loop.py at bootstrap (line ~4046) is never
        recomputed from a refreshed capital figure; see contract §
        'Initial behavior vs. refresh behavior' for the source citation."""
        from quant_hedge_ai.agents.risk.capital_allocation_engine import (
            CapitalAllocationEngine,
        )

        cae = CapitalAllocationEngine(total_capital=1000.0)
        low = cae.allocate(
            base_size_usd=55.0,
            win_rate=0.55,
            avg_win_pct=0.04,
            avg_loss_pct=0.02,
            n_trades_history=20,
        )

        cae.update_capital(10_000.0)
        high = cae.allocate(
            base_size_usd=55.0,
            win_rate=0.55,
            avg_win_pct=0.04,
            avg_loss_pct=0.02,
            n_trades_history=20,
        )
        assert high.size_usd >= low.size_usd

    def test_portfolio_brain_update_capital_changes_capital_available(self):
        from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain

        brain = PortfolioBrain(total_capital=1000.0)
        before = brain.check_new_trade(
            "BTC/USDT", "BUY", 50.0, regime="bull_trend", open_positions=[]
        )
        brain.update_capital(100_000.0)
        after = brain.check_new_trade(
            "BTC/USDT", "BUY", 50.0, regime="bull_trend", open_positions=[]
        )
        assert after.capital_available > before.capital_available

    def test_executive_override_update_capital_recomputes_drawdown(self):
        from quant_hedge_ai.agents.risk.executive_override import ExecutiveOverride

        eo = ExecutiveOverride(total_capital=1000.0)
        eo.update_capital(1000.0)
        assert eo.metrics_snapshot()["drawdown_pct"] == 0.0

        eo.update_capital(900.0)  # 10% drawdown from peak
        snap = eo.metrics_snapshot()
        assert snap["drawdown_pct"] == pytest.approx(10.0, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────
# H6 — CapitalThrottle (capital_deployment) pinned to paper capital
# ─────────────────────────────────────────────────────────────────────────


class TestH6CapitalThrottlePinnedToPaperCapital:
    """capital_deployment/capital_throttle.py's CapitalThrottle enforces a
    phase ceiling as a percentage of a `total_capital` figure supplied at
    construction. core/advisor_loop.py (line ~3871) constructs it with
    `_paper_capital` (WALLET_PAPER_CAPITAL) unconditionally — including
    in the non-advisor_only (live) branch — per an explicit ADR-0011
    comment: "base épinglée pour stationnarité du sizing pendant la
    validation." This matches CLAUDE.md's ADR-0007 sizing-pin invariant.
    These tests establish the throttle's mechanical effect, not whether
    pinning it to paper capital while gating live order sizes is itself
    desirable — that is an explicit, ADR-documented operator decision,
    not a defect this audit adjudicates."""

    def test_throttle_ceiling_is_independent_of_live_capital_value(self):
        from capital_deployment.capital_throttle import CapitalThrottle

        paper_capital = 1000.0
        real_capital_much_larger = 50_000.0

        throttle = CapitalThrottle(total_capital=paper_capital, phase="F-01")
        # F-01: 1% of total_capital, capped at 100 EUR absolute.
        assert throttle.allocated_capital == pytest.approx(10.0)

        # Even though live capital is 50x larger, the throttle object built
        # from paper_capital knows nothing about it — no live figure was
        # ever passed to its constructor in the code path under audit.
        assert throttle.allocated_capital < real_capital_much_larger

    def test_throttled_size_clamps_to_paper_based_ceiling_regardless_of_requested_size(
        self,
    ):
        from capital_deployment.capital_throttle import CapitalThrottle

        throttle = CapitalThrottle(total_capital=1000.0, phase="F-01")
        assert throttle.throttled_size(10_000.0) == pytest.approx(10.0)


# ─────────────────────────────────────────────────────────────────────────
# H7 — display-only surfaces never feed decisions
# ─────────────────────────────────────────────────────────────────────────


class TestH7DisplayOnlySurfacesDoNotDecide:
    def test_real_accounts_observer_snapshot_has_no_sizing_side_effects(self):
        """RealAccountsObserver.snapshot()/aggregate() return plain
        dataclasses with no reference to WalletSync, PortfolioBrain,
        CapitalAllocationEngine, or ExecutionEngine — SOURCE_PROVEN via
        the absence of any such import in observability/real_accounts.py.
        This test proves the emitted objects carry no callable/mutating
        surface an accidental caller could use to influence sizing."""
        from observability.real_accounts import RealAccountSnapshot

        snap = RealAccountSnapshot(exchange="mexc", ok=True, ts_utc="2026-01-01T00:00Z")
        # Frozen dataclass: no setter exists that could be wired into a
        # decision path even by accident.
        with pytest.raises(Exception):
            snap.total_usd = 999999.0  # type: ignore[misc]

    def test_configured_exchanges_reads_env_but_does_not_touch_wallet_sync(
        self, monkeypatch
    ):
        import observability.real_accounts as ra

        monkeypatch.setenv("MEXC_API_KEY", "k")
        monkeypatch.setenv("MEXC_API_SECRET", "s")
        monkeypatch.setenv("REAL_ACCOUNTS_EXCHANGES", "mexc")
        assert ra.configured_exchanges() == ["mexc"]
        # No WalletSync singleton should have been created as a side effect.
        assert ws._singleton is None


# ─────────────────────────────────────────────────────────────────────────
# Scenario K — divergence between PAPER_TRADING_ENABLED / EXCHANGE_MODE /
# advisor_only
# ─────────────────────────────────────────────────────────────────────────


class TestScenarioKEnvDivergence:
    def test_paper_trading_enabled_wins_over_exchange_mode_for_capital_source(
        self, monkeypatch, isolated_ledger, tmp_path
    ):
        """Even when EXCHANGE_MODE=live (which would seed a fresh
        singleton's default mode to "live"), fetch_available_capital()'s
        own paper_trading_enabled check requests wallet_mode="paper" —
        and because this is the FIRST call (no pre-existing singleton in
        this test), that request does take effect."""
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 55.0)
        monkeypatch.setenv("EXCHANGE_MODE", "live")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        eng = ExecutionEngine(live=False)
        eng._exchange = FakeExchange(free_usdt=9999.0)
        eng._mode = "live"

        assert eng.fetch_available_capital() == 55.0
        assert ws.get_wallet_sync().mode == "paper"

    def test_mode_provenance_label_fails_closed_on_unrecognized_exec_mode(self):
        """resolve_mode_provenance() (observability/mode_provenance.py) —
        the DISPLAY-layer provenance label — fails closed to UNKNOWN for
        an unrecognized exec_mode, never defaulting to REAL_API. Contrasts
        with WalletSync.get_balance(), which always returns a concrete
        float and never an UNKNOWN/None sentinel (see H4 tests above) —
        the two must not be conflated (§9c of the O-02W-E contract)."""
        from observability.mode_provenance import resolve_mode_provenance

        assert (
            resolve_mode_provenance("nonexistent_mode", paper_trading_enabled=False)
            == "UNKNOWN"
        )
        assert (
            resolve_mode_provenance(None, paper_trading_enabled=True) == "PAPER"
        )


# ─────────────────────────────────────────────────────────────────────────
# H1 — end-to-end: paper isolation survives a full PAPER cycle regardless
# of exchange behavior
# ─────────────────────────────────────────────────────────────────────────


class TestH1EndToEndPaperIsolation:
    def test_paper_ledger_pnl_drives_balance_not_exchange_state(
        self, monkeypatch, isolated_ledger
    ):
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)
        fake_exchange = FakeExchange(free_usdt=5.0)  # near MIN_CAPITAL_X
        wallet = ws.WalletSync(exchange=fake_exchange, mode="paper")

        _write_close(isolated_ledger, -30.0)
        _write_close(isolated_ledger, 80.0)

        assert wallet.get_balance() == pytest.approx(1050.0)
        assert fake_exchange.calls == 0


# ─────────────────────────────────────────────────────────────────────────
# R1 CORRECTION — Cases 1-5: full causal-order combination through the REAL
# path (bootstrap_capital_x -> ExecutionEngine.fetch_available_capital ->
# WalletSync.get_balance), proving/disproving H1's unconditional claim.
# ─────────────────────────────────────────────────────────────────────────


class TestR1Case1LiveModeSingletonFreezesDespitePaperFlag:
    """Case 1: EXCHANGE_MODE=live, PAPER_TRADING_ENABLED=true, fake exchange
    with a distinctive balance, bootstrap_capital_x() runs BEFORE
    fetch_available_capital() — the real advisor_loop.py causal order.

    Proves: the singleton is created in "live" mode by bootstrap_capital_x()
    (EXCHANGE_MODE), and fetch_available_capital()'s wallet_mode="paper"
    request (from PAPER_TRADING_ENABLED) is silently ignored for `.mode` —
    but get_balance() itself branches on `self._mode` at CALL time, and
    since `self._mode` is frozen to "live", get_balance() takes the
    live/testnet branch and DOES call exchange.fetch_balance(), even though
    PAPER_TRADING_ENABLED=true. The PAPER execution gate (_place_live_order)
    still blocks a real order, but the API balance HAS influenced the
    numeric capital figure returned to callers — H1's unconditional
    "PAPER is isolated" claim is FALSE in this reachable scenario.
    """

    def test_live_singleton_frozen_before_paper_request_lets_api_balance_through(
        self, monkeypatch, isolated_ledger, tmp_path
    ):
        monkeypatch.setenv("EXCHANGE_MODE", "live")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        fake_exchange = FakeExchange(free_usdt=13_579.0)  # distinctive value

        # Real causal order: bootstrap_capital_x() first (advisor_loop.py ~3777).
        x = ws.bootstrap_capital_x(exchange=fake_exchange)
        assert x == 13_579.0  # bootstrap() itself always reads the real API
        assert ws.get_wallet_sync().mode == "live"  # frozen from EXCHANGE_MODE
        calls_after_bootstrap = fake_exchange.calls
        assert calls_after_bootstrap == 1

        # Then ExecutionEngine.fetch_available_capital() — the REAL path,
        # not a direct WalletSync.get_balance() call.
        eng = ExecutionEngine(live=False)
        eng._exchange = fake_exchange
        eng._mode = "live"

        capital = eng.fetch_available_capital()

        # wallet_mode requested was "paper" (PAPER_TRADING_ENABLED=true), but
        # the singleton's .mode is still "live" — get_balance() branches on
        # self._mode, which is "live", so it fetches from the exchange.
        assert ws.get_wallet_sync().mode == "live"
        assert capital == 13_579.0  # API balance leaked into the "paper" request
        assert fake_exchange.calls == calls_after_bootstrap + 1  # exchange WAS queried

        # The PAPER execution gate still blocks a REAL ORDER (separate concern
        # from capital provenance) — proves distinction (2) vs (1)/(3) in BLOCKER A.
        result = eng._place_live_order("BTC/USDT", "BUY", 50.0)
        assert result["mode"] == "live_failed"
        assert result["error"] == "blocked_by_paper_gate"


class TestR1Case2PaperTruthyVariantsDoNotChangeCase1Outcome:
    """Case 2: same scenario as Case 1, but PAPER_TRADING_ENABLED set to
    "1"/"yes"/"on" instead of "true" — proves the outcome is identical
    regardless of which truthy spelling is used, since the requested
    wallet_mode is ignored either way once the singleton pre-exists."""

    @pytest.mark.parametrize("value", ["1", "yes", "on"])
    def test_truthy_variant_still_lets_api_balance_through(
        self, value, monkeypatch, isolated_ledger, tmp_path
    ):
        monkeypatch.setenv("EXCHANGE_MODE", "live")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", value)
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        fake_exchange = FakeExchange(free_usdt=24_680.0)

        ws.bootstrap_capital_x(exchange=fake_exchange)
        assert ws.get_wallet_sync().mode == "live"

        eng = ExecutionEngine(live=False)
        eng._exchange = fake_exchange
        eng._mode = "live"

        # Confirm ExecutionEngine's own predicate does recognize this value
        # as PAPER-truthy (it does — the divergence is not in this
        # predicate, it's in the singleton-mode-freezing mechanism).
        assert ExecutionEngine._paper_trading_enabled() is True

        capital = eng.fetch_available_capital()
        assert capital == 24_680.0  # same leak regardless of truthy spelling


class TestR1Case3PaperSingletonFreezesLiveTestnetRequest:
    """Case 3: mirror direction — EXCHANGE_MODE absent (singleton starts in
    "paper"), PAPER_TRADING_ENABLED=false, ExecutionEngine._mode set to
    "live"/"testnet" (self._mode, the attribute ExecutionEngine uses
    internally after from_env()/__init__ — verified in execution_engine.py:
    self._mode = "paper" default at __init__, overwritten by from_env()'s
    ExchangeFactory.detect_mode() result). Fake exchange available and
    working. Proves the live/testnet request is silently ignored and the
    PAPER ledger value is used despite a working, queryable API — the
    mirror-image contamination direction connecting to H4."""

    @pytest.mark.parametrize("requested_mode", ["live", "testnet"])
    def test_live_testnet_request_ignored_paper_value_used_despite_working_api(
        self, requested_mode, monkeypatch, isolated_ledger, tmp_path
    ):
        monkeypatch.delenv("EXCHANGE_MODE", raising=False)  # singleton -> "paper"
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 321.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        fake_exchange = FakeExchange(free_usdt=99_999.0)  # working, distinctive

        # Singleton created first, in "paper" mode (no EXCHANGE_MODE set).
        ws.bootstrap_capital_x(exchange=fake_exchange)
        assert ws.get_wallet_sync().mode == "paper"
        calls_after_bootstrap = fake_exchange.calls

        eng = ExecutionEngine(live=False)
        eng._exchange = fake_exchange
        eng._mode = requested_mode  # engine "wants" live/testnet

        capital = eng.fetch_available_capital()

        # wallet_mode computed inside fetch_available_capital() would be
        # `requested_mode` (PAPER_TRADING_ENABLED=false), but the pre-existing
        # singleton's .mode stays "paper" — get_balance() takes the paper
        # branch: WALLET_PAPER_CAPITAL + ledger PnL, exchange never queried.
        assert ws.get_wallet_sync().mode == "paper"
        assert capital == pytest.approx(321.0)
        assert fake_exchange.calls == calls_after_bootstrap  # not queried again


class TestR1Case4LiveErrorNoCacheNoXRealPath:
    """Case 4: effective singleton mode "live", PAPER_TRADING_ENABLED=false,
    API error (raises), no cache, no successful bootstrap (_x never set).
    Tested through the REAL path ExecutionEngine.fetch_available_capital(),
    not a direct WalletSync.get_balance() call."""

    def test_live_error_no_cache_no_x_returns_paper_capital_via_real_path(
        self, monkeypatch, isolated_ledger, tmp_path
    ):
        monkeypatch.setenv("EXCHANGE_MODE", "live")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 42.0)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        fake_exchange = FakeExchange(raise_on_fetch=True)

        # Create the singleton via get_wallet_sync directly with no bootstrap
        # success (bootstrap() is NOT called here -> _x stays None), mirroring
        # "no successful bootstrap" precisely.
        wallet = ws.get_wallet_sync(exchange=fake_exchange)
        assert wallet.mode == "live"
        assert wallet.capital_x is None

        eng = ExecutionEngine(live=False)
        eng._exchange = fake_exchange
        eng._mode = "live"

        capital = eng.fetch_available_capital()

        # get_balance() -> live branch -> fetch_balance() raises -> _fallback()
        # -> _last_value is None -> _base_capital() -> self._x is None ->
        # WALLET_PAPER_CAPITAL. Exactly one failed call attempted.
        assert capital == 42.0
        assert fake_exchange.calls == 1


# ─────────────────────────────────────────────────────────────────────────
# R1.1 CORRECTION (BLOCKER A) — Cases 1-4 above construct ExecutionEngine
# directly (`ExecutionEngine(live=False)` then manual `_exchange`/`_mode`
# assignment). That is a real, hermetic exercise of the WalletSync/
# fetch_available_capital mechanism, but it is NOT `ExecutionEngine.from_env()`
# — and the specific combination those cases use (`_mode="live"` with an
# attached exchange, while `LIVE_TRADING_CONFIRMED` is left at its default
# "false") is a state `from_env()` never produces: `from_env()` only attaches
# a live exchange when `LIVE_TRADING_CONFIRMED` is truthy (execution_engine.py
# `from_env()`, line ~199). Cases 6-7 below close that gap: they call the
# REAL `ExecutionEngine.from_env()` classmethod, with `ExchangeFactory.create`
# monkeypatched to a fake (no network, no ccxt dependency), and prove what
# that real construction path actually does — both for the source-reachable
# but operator-incoherent PAPER_TRADING_ENABLED=true + LIVE_TRADING_CONFIRMED=true
# combination (Case 6) and for the LIVE_TRADING_CONFIRMED=false contrast
# (Case 7).
# ─────────────────────────────────────────────────────────────────────────


class TestR1_1Case6FromEnvRealConstructionLiveConfirmedPaperEnabled:
    """Case 6 (REAL_FROM_ENV_PATH_PROVEN_HERMETIC): the actual
    ExecutionEngine.from_env() classmethod is called — not a direct
    ExecutionEngine(live=...) construction with manually assigned
    `_exchange`/`_mode`. Configuration: fake API keys present,
    EXCHANGE_TESTNET unset/false (-> ExchangeFactory.detect_mode()=="live"),
    LIVE_TRADING_CONFIRMED=true, PAPER_TRADING_ENABLED=true,
    EXCHANGE_MODE=live (WalletSync singleton seed), fake exchange returning a
    distinctive balance. ExchangeFactory.create is monkeypatched to return
    the fake exchange — no network, no ccxt import needed.

    This proves a SOURCE_REACHABLE_CONFIGURATION that is operator-incoherent
    (PAPER_TRADING_ENABLED=true and LIVE_TRADING_CONFIRMED=true are both set)
    but currently allowed by independent predicates: from_env() genuinely
    attaches a live exchange, the WalletSync singleton is genuinely created
    in live mode, fetch_available_capital() genuinely returns the API
    balance despite the PAPER gate, and _place_live_order still blocks the
    order before any order-creation call — all through the real production
    call chain, not injected engine state.
    """

    def test_from_env_attaches_live_exchange_and_leaks_balance_despite_paper_gate(
        self, monkeypatch, isolated_ledger, tmp_path
    ):
        monkeypatch.setenv("MEXC_API_KEY", "fake-key")
        monkeypatch.setenv("MEXC_API_SECRET", "fake-secret")
        monkeypatch.delenv("EXCHANGE_TESTNET", raising=False)  # -> mode "live"
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        monkeypatch.setenv("EXCHANGE_MODE", "live")  # WalletSync singleton seed
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)

        fake_exchange = FakeExchange(free_usdt=55_555.0)
        from infra.exchange_factory import ExchangeFactory

        monkeypatch.setattr(
            ExchangeFactory, "create", staticmethod(lambda *a, **k: fake_exchange)
        )

        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        # The REAL from_env() classmethod — not a direct ExecutionEngine(...)
        # construction with manual attribute assignment.
        eng = ExecutionEngine.from_env()

        # from_env() genuinely attached a live exchange: has_api_key=True,
        # mode="live"!="paper", LIVE_TRADING_CONFIRMED truthy -> live=True ->
        # __init__ calls _init_exchange() -> ExchangeFactory.create().
        assert eng._live is True
        assert eng._exchange is fake_exchange
        assert eng._mode == "live"

        # bootstrap_capital_x() runs before fetch_available_capital(), as the
        # real core/advisor_loop.py boot order requires.
        x = ws.bootstrap_capital_x(exchange=eng._exchange)
        assert x == 55_555.0
        assert ws.get_wallet_sync().mode == "live"  # singleton created live
        calls_after_bootstrap = fake_exchange.calls
        assert calls_after_bootstrap == 1

        # fetch_available_capital() returns the API balance despite the
        # PAPER_TRADING_ENABLED=true gate, because the singleton's mode was
        # already frozen "live" by bootstrap_capital_x() above.
        capital = eng.fetch_available_capital()
        assert capital == 55_555.0
        assert fake_exchange.calls == calls_after_bootstrap + 1  # a balance-read call

        # The order-placement gate still blocks the order — distinct
        # counters: no further exchange calls are made for the blocked
        # order (it never reaches ticker/balance/create_order calls).
        calls_before_order_attempt = fake_exchange.calls
        result = eng._place_live_order("BTC/USDT", "BUY", 50.0)
        assert result["mode"] == "live_failed"
        assert result["error"] == "blocked_by_paper_gate"
        assert fake_exchange.calls == calls_before_order_attempt  # 0 order-attempt calls


class TestR1_1Case7FromEnvRealConstructionConfirmedFalseContrast:
    """Case 7 (REAL_FROM_ENV_PATH_PROVEN_HERMETIC, contrast to Case 6):
    same fake API keys present, but LIVE_TRADING_CONFIRMED=false (the
    default) and PAPER_TRADING_ENABLED=true. Proves, through the REAL
    from_env() path (no manual `_exchange`/`_mode` assignment), what
    actually happens: from_env()'s three-way AND (has_api_key AND
    mode!="paper" AND LIVE_TRADING_CONFIRMED) evaluates False, so
    __init__ never calls _init_exchange() at all -- no live exchange is
    attached, self._mode stays the __init__ default "paper", and the
    engine falls back to the paper/testnet-unreached branch. This is the
    honest replacement for the BLOCKER A-flagged mismatch: the original
    Case-1-style tests' `LIVE_TRADING_CONFIRMED=false` + injected `_mode=
    "live"` combination never actually arises from from_env()."""

    def test_from_env_confirmed_false_never_attaches_exchange(
        self, monkeypatch, isolated_ledger, tmp_path
    ):
        monkeypatch.setenv("MEXC_API_KEY", "fake-key")
        monkeypatch.setenv("MEXC_API_SECRET", "fake-secret")
        monkeypatch.delenv("EXCHANGE_TESTNET", raising=False)
        monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)  # default false
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        monkeypatch.delenv("EXCHANGE_MODE", raising=False)  # singleton -> "paper"
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)

        fake_exchange = FakeExchange(free_usdt=77_777.0)
        from infra.exchange_factory import ExchangeFactory

        # Even though create() is patched to succeed, from_env()'s own gate
        # must prevent it from ever being called, because live=False.
        create_calls = {"n": 0}

        def _tracking_create(*a, **k):
            create_calls["n"] += 1
            return fake_exchange

        monkeypatch.setattr(
            ExchangeFactory, "create", staticmethod(_tracking_create)
        )

        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        eng = ExecutionEngine.from_env()

        assert eng._live is False
        assert eng._exchange is None  # __init__ only calls _init_exchange() if live
        assert eng._mode == "paper"  # __init__ default, never overwritten
        assert create_calls["n"] == 0  # ExchangeFactory.create() never invoked

        # fetch_available_capital(): no exchange attached, wallet_mode forced
        # "paper" by PAPER_TRADING_ENABLED=true anyway -> WalletSync singleton
        # created fresh (no prior bootstrap_capital_x call in this test) in
        # paper mode -> WALLET_PAPER_CAPITAL + ledger PnL, exchange untouched.
        capital = eng.fetch_available_capital()
        assert capital == 1000.0
        assert fake_exchange.calls == 0  # the fake exchange was never reached
        assert ws.get_wallet_sync().mode == "paper"


class TestR1Case5DistinguishableFallbackSources:
    """Case 5: (a) stale cache, (b) bootstrap-seeded `_last_value` replay
    (R1.2: not `_x` via `_base_capital()` — see the renamed test below),
    (c) genuine zero
    balance, (d) API error — all through get_balance()/fetch_available_capital,
    proving they are code-path-distinguishable even where the returned
    float coincides. Where the current code CANNOT distinguish two cases
    (zero balance vs. error, both falling through the same `_fallback()`
    call with no side channel), this is stated as an explicit finding,
    not papered over."""

    def test_a_stale_cache_returns_cached_value_not_paper_or_x(
        self, monkeypatch, isolated_ledger
    ):
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 42.0)
        monkeypatch.setattr(ws, "_CACHE_TTL_S", 9999.0)  # cache stays "fresh"
        fake_exchange = FakeExchange(free_usdt=777.0)
        wallet = ws.WalletSync(exchange=fake_exchange, mode="live")
        wallet.set_x(500.0)  # _x also set, to prove cache wins over _x too

        first = wallet.get_balance(force_refresh=True)
        assert first == 777.0
        assert fake_exchange.calls == 1

        fake_exchange._raise = True
        second = wallet.get_balance()  # no force_refresh -> serves fresh cache
        assert second == 777.0  # cache, not 500.0 (_x) or 42.0 (paper)
        assert fake_exchange.calls == 1  # exchange not called again — cache hit

    def test_bootstrap_seeded_last_value_is_returned_after_api_failure(
        self, monkeypatch, isolated_ledger
    ):
        """R1.2 correction (was `test_b_bootstrapped_x_used_when_no_cache_and_api_fails`,
        renamed to reflect its real behavior — R1.1 incorrectly left the old
        framing ("_x, via _base_capital()") uncorrected).

        Proves, in order:
          1. bootstrap() returns 300.0.
          2. wallet.capital_x (_x) == 300.0.
          3. wallet._last_value == 300.0 immediately after bootstrap (set_x()
             seeds both fields in the same call — wallet_sync.py:126,
             "fallback live aussi").
          4. the API then fails.
          5. _fallback() (reached via get_balance()) returns _last_value.
          6. _base_capital() is NOT necessary to produce this result — proven
             with a spy that increments a counter on every call; the counter
             is 0 after the fallback runs, so the `_x` branch of
             `_base_capital()` was never reached.
        """
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 42.0)
        fake_exchange = FakeExchange(raise_on_fetch=False, free_usdt=0.0)
        wallet = ws.WalletSync(exchange=fake_exchange, mode="live")

        # 1-2: bootstrap() succeeds via a SEPARATE fake exchange with a valid
        # balance (simulating boot-time success), setting _x.
        boot_exchange = FakeExchange(free_usdt=300.0)
        assert wallet.bootstrap(boot_exchange) == 300.0
        assert wallet.capital_x == 300.0

        # 3: bootstrap() -> set_x() ALSO seeds _last_value = self._x
        # (wallet_sync.py:126) — _x and _last_value are populated together,
        # not through get_balance()'s own successful-fetch path.
        assert wallet._last_value == 300.0

        # 4: the API then fails.
        fake_exchange._raise = True

        # 6 (spy installed before the call): count _base_capital() calls.
        base_capital_calls = {"n": 0}
        real_base_capital = wallet._base_capital

        def _spy_base_capital():
            base_capital_calls["n"] += 1
            return real_base_capital()

        monkeypatch.setattr(wallet, "_base_capital", _spy_base_capital)

        # 5: force_refresh=True bypasses the cache-freshness check, the API
        # call fails, so get_balance() falls through to _fallback(), which
        # finds _last_value (300.0, seeded by bootstrap's set_x) is not None
        # and returns it directly — _base_capital() is never reached.
        result = wallet.get_balance(force_refresh=True)
        assert result == 300.0  # NOT 42.0 (paper) — code-path distinguishable

        # 6: proof that _base_capital() (and therefore its `_x` branch) was
        # NOT necessary to produce this result.
        assert base_capital_calls["n"] == 0

    def test_c_and_d_zero_balance_and_api_error_are_NOT_source_distinguishable(
        self, monkeypatch, isolated_ledger
    ):
        """FINDING (not papered over): a genuine zero USDT balance (c) and
        an API error (d) both fall through the SAME `if usdt > 0` guard /
        except branch into the SAME `_fallback()` call, with no distinct
        return value, flag, exception type recorded, or log field surfaced
        to the caller. The current implementation genuinely cannot
        distinguish "exchange reachable, balance truly zero" from "exchange
        unreachable" from get_balance()'s return value alone — this test
        proves both produce the identical float via the identical code
        branch (WalletSync.get_balance -> `except Exception: pass` /
        `if usdt > 0` both drop into `return self._fallback()`), which is
        the finding itself, not a gap in this test's coverage."""
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 42.0)

        zero_exchange = FakeExchange(free_usdt=0.0)
        wallet_zero = ws.WalletSync(exchange=zero_exchange, mode="live")
        result_zero = wallet_zero.get_balance(force_refresh=True)

        error_exchange = FakeExchange(raise_on_fetch=True)
        wallet_error = ws.WalletSync(exchange=error_exchange, mode="live")
        result_error = wallet_error.get_balance(force_refresh=True)

        # Same numeric outcome via the same fallback path — proven identical,
        # not merely asserted; this IS the H4-adjacent ambiguity finding.
        assert result_zero == 42.0
        assert result_error == 42.0
        assert result_zero == result_error
        # Both exchanges WERE called once (proving reachability differs
        # upstream even though the return value can't tell you that).
        assert zero_exchange.calls == 1
        assert error_exchange.calls == 1


# ─────────────────────────────────────────────────────────────────────────
# R1.2 — documentary regression tests: the contract doc must not regress to
# the R1.1 factual error about the `_x`/`_last_value` fallback chain (the
# doc claimed Case 5b passed through `_base_capital()`'s `_x` branch; it
# does not — see the corrected §4/§11 text and the renamed Case 5b test
# above). These tests read the actual doc file and assert on scoped,
# specific pieces of text — never permissive `or`-joined checks.
# ─────────────────────────────────────────────────────────────────────────

import pathlib
import re

_CONTRACT_DOC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "docs"
    / "contracts"
    / "O-02W-PRE-T1-D_REAL_CAPITAL_BOUNDARY.md"
)


def _read_contract_doc() -> str:
    return _CONTRACT_DOC_PATH.read_text(encoding="utf-8")


def _extract_section(doc: str, heading: str, next_heading_prefix: str = "## ") -> str:
    """Return the text of the section starting at `heading` (a full line,
    e.g. "## 4. H4 — ...") up to (not including) the next line starting
    with `next_heading_prefix`. Raises AssertionError if `heading` is not
    found verbatim as its own line — keeps section lookups exact rather
    than fuzzy-matched."""
    lines = doc.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i
            break
    assert start is not None, f"heading not found verbatim: {heading!r}"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith(next_heading_prefix):
            end = j
            break
    return "\n".join(lines[start:end])


class TestR1_2DocumentaryRegressionCorrectXLastValueFraming:
    """Regression tests for the R1.2 correction of the `_x`/`_last_value`
    fallback-chain framing. Each test targets one specific, scoped claim —
    no permissive `or`-joined assertions."""

    def test_doc_states_set_x_initializes_last_value(self):
        section = _extract_section(
            _read_contract_doc(),
            "## 4. H4 — API-mode fallback chain (value origin vs. internal storage vs. branch executed)",
        )
        assert (
            "`set_x()` writes `self._last_value = self._x` in the same"
            in section
        )
        assert "call (`wallet_sync.py:126`" in section

    def test_doc_states_normal_bootstrap_returns_x_value_via_last_value(self):
        section = _extract_section(
            _read_contract_doc(),
            "## 4. H4 — API-mode fallback chain (value origin vs. internal storage vs. branch executed)",
        )
        assert (
            "The `_base_capital() → _x` branch is therefore\n**normally not reached** "
            "after a successful public bootstrap, because\n`_fallback()` returns "
            "`_last_value` first"
            in section
        )

    def test_doc_no_longer_claims_case_5b_passes_through_base_capital(self):
        doc = _read_contract_doc()
        # The exact R1.1 wrong phrase must be gone.
        assert "returns `300.0` (`_x`, via\n    `_base_capital()`" not in doc
        # And no remaining sentence in the document claims Case 5b's result
        # was produced "via `_base_capital()`" (case-insensitive, tolerant
        # of internal line wraps).
        collapsed = re.sub(r"\s+", " ", doc)
        assert "300.0 (_x, via _base_capital()" not in collapsed
        assert "300.0 (_x, via\n    `_base_capital()`" not in doc

    def test_doc_classifies_x_only_state_as_not_from_public_bootstrap_path(self):
        assert (
            "INTERNAL_STATE_ONLY_NOT_PRODUCED_BY_PUBLIC_BOOTSTRAP_PATH"
            in _read_contract_doc()
        )

    def test_doc_case_5b_summary_references_last_value_not_x_branch(self):
        section = _extract_section(
            _read_contract_doc(),
            "## 11. Case 1-5 results (R1 combined causal-order tests) — `PRODUCTION_FUNCTIONS_WITH_INJECTED_STATE`",
        )
        assert "5b bootstrap-seeded `_last_value`:" in section
        assert "not** via\n    `_base_capital()`'s `_x` branch" in section

    def test_renamed_case_5b_test_exists_with_base_capital_spy_assertion(self):
        test_source = pathlib.Path(__file__).read_text(encoding="utf-8")
        assert (
            "def test_bootstrap_seeded_last_value_is_returned_after_api_failure("
            in test_source
        )
        assert 'assert base_capital_calls["n"] == 0' in test_source
        # The old (R1.1) test name must not exist as a *test definition* —
        # checked structurally (a `def <old name>(` line), not merely as a
        # substring, so this assertion is not defeated by this very file
        # mentioning the old name in a comment/docstring elsewhere.
        old_def = "def " + "test_b_bootstrapped_x_used_when_no_cache_and_api_fails" + "("
        def_lines = [
            ln for ln in test_source.splitlines() if ln.strip().startswith(old_def)
        ]
        assert def_lines == []
