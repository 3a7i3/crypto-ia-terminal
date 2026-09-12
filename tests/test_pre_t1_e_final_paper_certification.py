"""O-02W-PRE-T1-E — FINAL PRE-T1-E PAPER CERTIFICATION.

Hermetic adversarial proof suite. No real exchange, no network, no
credentials. Uses fake/tripwire exchange objects that raise loudly on any
unexpected mutating call. Covers mission scenarios A-L plus the C1
blocking diagnostic.

This is a certification test file, not a remediation. It asserts the
CURRENT behavior of `ExecutionEngine`/`PositionManager`/`MexcSimulator`/
`PositionReconciler`/`BootGate` under `PAPER_TRADING_ENABLED=true` /
`LIVE_TRADING_CONFIRMED=false` — no production source is modified by this
mission.
"""

from __future__ import annotations

import pytest


# ── Tripwire exchange objects ────────────────────────────────────────────────


class MutationTripwire(RuntimeError):
    """Raised the instant any mutating exchange method is invoked."""


class TripwireSpotExchange:
    """A fake ccxt-shaped spot exchange: read-only calls succeed, any
    mutating call raises immediately and loudly. `id` mimics ccxt's
    exchange-id attribute some code paths inspect."""

    id = "mexc"

    def __init__(self):
        self.mutation_calls: list[str] = []

    def fetch_ticker(self, symbol):
        return {"last": 100.0, "bid": 99.9, "ask": 100.1}

    def fetch_balance(self):
        return {"USDT": {"free": 100000.0}, "free": {"USDT": 100000.0}}

    def load_markets(self):
        return {}

    def create_order(self, *a, **kw):
        self.mutation_calls.append("create_order")
        raise MutationTripwire(f"create_order called: args={a} kwargs={kw}")

    def create_market_order(self, *a, **kw):
        self.mutation_calls.append("create_market_order")
        raise MutationTripwire("create_market_order called")

    def create_limit_order(self, *a, **kw):
        self.mutation_calls.append("create_limit_order")
        raise MutationTripwire("create_limit_order called")

    def cancel_order(self, *a, **kw):
        self.mutation_calls.append("cancel_order")
        raise MutationTripwire("cancel_order called")

    def cancel_all_orders(self, *a, **kw):
        self.mutation_calls.append("cancel_all_orders")
        raise MutationTripwire("cancel_all_orders called")

    def set_leverage(self, *a, **kw):
        self.mutation_calls.append("set_leverage")
        raise MutationTripwire("set_leverage called")

    def set_margin_mode(self, *a, **kw):
        self.mutation_calls.append("set_margin_mode")
        raise MutationTripwire("set_margin_mode called")

    def transfer(self, *a, **kw):
        self.mutation_calls.append("transfer")
        raise MutationTripwire("transfer called")

    def withdraw(self, *a, **kw):
        self.mutation_calls.append("withdraw")
        raise MutationTripwire("withdraw called")

    def fetch_positions(self, *a, **kw):
        # read-only observation — allowed, must never confer sizing/mutation
        # authority (Scenario L).
        return []


class TripwireFuturesExchange(TripwireSpotExchange):
    """Same tripwire behavior, used to stand in for a futures-demo/testnet
    handle."""

    id = "krakenfutures"


def _certify_and_bypass_causal_gates(monkeypatch):
    """These scenarios prove ZERO MUTATION at the exchange boundary — they
    are not exercising REM-B's decision-identity/causal-binding gate (that
    is covered exhaustively by
    `tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py`). Bypass those
    upstream gates exactly like the existing test suites do (see
    `_certify_mexc_for_test` in `test_execution_engine.py`/
    `test_execution_engine_futures.py`) so a *missing* decision_id can never
    be mistaken here for the tripwire-based PAPER/LIVE-FALSE proof this file
    exists to make."""
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine as _EE

    monkeypatch.setattr(
        _EE, "_decision_id_is_durably_persisted", lambda self, decision_id: bool(decision_id)
    )
    monkeypatch.setattr(
        _EE,
        "_decision_execution_denial_reason",
        lambda self, decision_id: None if decision_id else "MISSING_CAUSAL_ID",
    )
    monkeypatch.setattr(_EE, "_bind_decision_to_intent", lambda self, decision_id, intent: None)


@pytest.fixture(autouse=True)
def _paper_true_live_false(monkeypatch):
    """The central invariant under test: PAPER_TRADING_ENABLED=true AND
    LIVE_TRADING_CONFIRMED=false for every test in this file, unless a test
    explicitly overrides one flag to probe the authority matrix itself."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "false")


@pytest.fixture
def engine_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    monkeypatch.setenv("EXEC_DEDUP_WINDOW", "30")
    _certify_and_bypass_causal_gates(monkeypatch)

    def _make(with_spot_handle=False, with_futures_handle=False):
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        eng = ExecutionEngine(live=False)  # construction-time PAPER path
        eng.start_session(equity=10_000.0)
        spot = TripwireSpotExchange() if with_spot_handle else None
        fut = TripwireFuturesExchange() if with_futures_handle else None
        if spot is not None:
            eng._exchange = spot
        if fut is not None:
            eng._exchange_futures = fut
        return eng, spot, fut

    return _make


# ── Scenario A — PAPER BUY, spot handle exists → zero mutation ─────────────


def test_scenario_a_paper_buy_zero_mutation(engine_factory):
    eng, spot, _ = engine_factory(with_spot_handle=True)

    result = eng.create_order("BTC/USDT", "BUY", 100.0, decision_id="cert-A-buy")

    assert spot.mutation_calls == []
    assert result.get("mode") != "live"


# ── Scenario B — PAPER SELL/CLOSE, spot handle exists → zero mutation ──────


def test_scenario_b_paper_sell_zero_mutation(engine_factory):
    eng, spot, _ = engine_factory(with_spot_handle=True)

    result = eng.create_order("ETH/USDT", "SELL", 50.0, decision_id="cert-B-sell")

    assert spot.mutation_calls == []
    assert result.get("mode") != "live"


# ── Scenario C — PAPER engine + futures handle + leverage=1 → narrow ───────
# zero-mutation proof only (not a general/actionable-decision proof; see C1)
# futures mutation calls


def test_scenario_c_paper_futures_zero_mutation_leverage_1_only_NOT_GENERAL(
    engine_factory,
):
    """NARROW PROOF, NOT A GENERAL SAFETY CLAIM: `leverage=1` never calls
    `set_leverage` at all (see `execution_engine.py`'s `if leverage != 1:`
    guard) — this test proves only that the default-leverage path reaches
    neither `set_leverage` nor `create_order` on the tripwire. It says
    NOTHING about `leverage != 1`, which is a materially different code
    path: see `test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL`
    below, which proves the general case is currently UNSAFE (C1, BLOCKS
    T-1 per docs/contracts/O-02W-PRE-T1-E_ORDER_CYCLE_SAFETY.md §24)."""
    eng, _, fut = engine_factory(with_futures_handle=True)

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=1, decision_id="cert-C-futures"
    )

    assert fut.mutation_calls == []
    assert result.get("mode") != "live"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PRE-T1-E blocker C1: set_leverage mutation precedes PAPER/LIVE "
        "authority gate"
    ),
)
def test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL(engine_factory):
    """C1 (BLOCKS T-1): `create_futures_order()` calls
    `self._exchange_futures.set_leverage(leverage, ccxt_symbol)`
    (`execution_engine.py`, inside `if leverage != 1:`) BEFORE
    `authorize_order()` and with no inline
    PAPER_TRADING_ENABLED/LIVE_TRADING_CONFIRMED/`self._live` check of its
    own. Its only safety is that `self._exchange_futures` happens to be
    `None` on every construction path this repository exercises today —
    that is caller-inherited safety, not an authority gate on the function
    itself. A foreign/stale/tripwire futures handle force-attached in
    memory (exactly what this test does) with `leverage=3` reaches
    `set_leverage` regardless of PAPER=true/LIVE=false, which violates the
    adversarial invariant that a REAL/TESTNET/FUTURES handle present in
    memory must never allow mutation under PAPER=true/LIVE=false.

    This test is expected to XFAIL (strict) until C1 is fixed: it asserts
    zero tripwire mutation calls, but `fut.mutation_calls` will actually
    contain `"set_leverage"` on the current HEAD."""
    eng, _, fut = engine_factory(with_futures_handle=True)

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=3, decision_id="cert-C1-leverage-change"
    )

    assert fut.mutation_calls == []
    assert result.get("mode") != "live"


def test_scenario_c_construction_never_attaches_futures_handle_in_paper(
    tmp_path, monkeypatch
):
    """Certification-relevant construction proof: under
    PAPER_TRADING_ENABLED=true/LIVE_TRADING_CONFIRMED=false,
    `ExecutionEngine.from_env()` never sets `live=True`, and `__init__`
    only calls `_init_futures_demo()` when `live=True` — so in the actual
    reachable construction path, `_exchange_futures` stays `None` and
    `create_futures_order()` short-circuits to `mode=futures_unavailable`
    with zero possibility of reaching `set_leverage`/`create_order`.

    NOTE (residual finding, documented in the certification, not fixed
    here per audit-first scope): `create_futures_order()` itself performs
    no internal `PAPER_TRADING_ENABLED` re-check before its `set_leverage`
    call — its safety is entirely inherited from `_exchange_futures` being
    `None`, exactly the same caller-inherited-safety shape §7/H10 already
    documented for `PositionManager._send_close_order`. This is
    SOURCE_PROVEN unreachable under every construction path found in this
    repository (`from_env()`, `reconnect()`), not independently gated by
    the function itself."""
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t2.sqlite"))
    monkeypatch.setenv("EXCHANGE_ID", "mexc")
    monkeypatch.delenv("MEXC_API_KEY", raising=False)
    monkeypatch.delenv("MEXC_API_SECRET", raising=False)
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    eng = ExecutionEngine.from_env()
    assert eng._live is False
    assert eng._exchange_futures is None

    result = eng.create_futures_order("BTC/USDT", "BUY", 100.0, leverage=3)
    assert result.get("mode") == "futures_unavailable"


# ── Scenario D — restored PAPER position closes → zero external mutation ──


def test_scenario_d_restored_paper_position_close_zero_mutation(monkeypatch):
    from quant_hedge_ai.agents.execution.position_manager import (
        ExecutionDomain,
        Position,
        PositionManager,
        PositionSide,
    )

    # A PositionManager with no exchange handle at all is unconditionally
    # PAPER (self._paper = paper_mode or exchange is None) — this models a
    # position reconstructed from durable PAPER ledger state after restart.
    pm = PositionManager(exchange=None, paper_mode=True)
    pos = Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=50_000.0,
        size_usd=500.0,
        qty=0.01,
        current_price=51_000.0,
        domain=ExecutionDomain.PAPER,
    )
    pm.add_position(pos)

    result = pm._send_close_order(pos)

    assert result["mutation_attempted"] is False
    assert result["mode"] == "paper"
    assert result["authorized"] is True


# ── Scenario E — UNKNOWN execution domain → fail-closed/non-comparable ────


def test_scenario_e_unknown_domain_reconciliation_fails_closed():
    from quant_hedge_ai.agents.execution.position_manager import (
        ExecutionDomain,
        PositionManager,
    )
    from system.position_reconciler import PositionReconciler

    class _TripwireRealExchange(TripwireSpotExchange):
        def fetch_positions(self):
            return [{"symbol": "BTC/USDT", "side": "long", "contracts": 1.0, "markPrice": 100.0}]

    exch = _TripwireRealExchange()
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.UNKNOWN)
    reconciler = PositionReconciler(
        pos_manager=pm, exchange_futures=exch, expected_domain=ExecutionDomain.REAL
    )

    report = reconciler.reconcile(force=True)

    assert report.comparable is False
    assert report.ghost_positions == []
    assert report.orphan_positions == []
    assert exch.mutation_calls == []


# ── Scenario F — PAPER manager with foreign REAL exchange handle cannot ────
# submit an external close (authority re-check fails closed)


def test_scenario_f_paper_manager_with_foreign_real_handle_cannot_submit(monkeypatch):
    from quant_hedge_ai.agents.execution.position_manager import (
        ExecutionDomain,
        Position,
        PositionManager,
        PositionSide,
    )

    tripwire = TripwireSpotExchange()
    # paper_mode=True forces self._paper=True even though a real exchange
    # object is (mis)attached — the PAPER branch must win and no mutation
    # may reach the foreign handle.
    pm = PositionManager(exchange=tripwire, paper_mode=True, domain=ExecutionDomain.PAPER)
    pos = Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=50_000.0,
        size_usd=500.0,
        qty=0.01,
        current_price=51_000.0,
        domain=ExecutionDomain.PAPER,
    )
    pm.add_position(pos)

    result = pm._send_close_order(pos)

    assert result["mutation_attempted"] is False
    assert result["mode"] == "paper"
    assert tripwire.mutation_calls == []


# ── Scenario G — direct PAPER ExecutionEngine call with HOLD → zero ────────
# external mutation (does NOT exercise DecisionPacket authorization; see
# core/decision_packet.py / advisor_loop.py G8 for that gate)


def test_scenario_g_direct_paper_hold_zero_external_mutation(engine_factory):
    eng, spot, _ = engine_factory(with_spot_handle=True)

    # "HOLD" / non-actionable action never reaches create_order in
    # production (advisor_loop only calls create_order for BUY/SELL). This
    # models a defensive call with an explicitly non-actionable action
    # string reaching the engine anyway; the sanity/size-authorization gate
    # (REM-A) must still deny before any mutation, never guess a side.
    result = eng.create_order("BTC/USDT", "HOLD", 100.0, decision_id="cert-G-hold")

    assert spot.mutation_calls == []
    assert result.get("mode") != "live"


# ── Scenario H — direct PAPER ExecutionEngine call without decision_id → ───
# zero external mutation (does NOT exercise DecisionPacket authorization;
# decision_id is REM-B causal identity, a distinct concern — see contract §24)


def test_scenario_h_direct_paper_missing_decision_id_zero_external_mutation(engine_factory):
    eng, spot, _ = engine_factory(with_spot_handle=True)

    result = eng.create_order("BTC/USDT", "BUY", 100.0)  # no decision_id at all

    assert spot.mutation_calls == []
    # PAPER routes before the causal-id gate is even reached in this build;
    # either way, zero mutation is the only invariant this scenario proves.
    assert result.get("mode") != "live"


# ── Scenario I — restart with incomplete paper evidence → None/UNKNOWN ────
# preserved, no fabricated PnL/result


def test_scenario_i_restart_incomplete_evidence_no_fabrication(tmp_path):
    from paper_trading.recorder import PaperTradeRecorder

    db_path = tmp_path / "paper_ledger.jsonl"
    recorder = PaperTradeRecorder(log_path=str(db_path))
    trade_id = "cert-I-restart-001"
    recorder.record_open(
        trade_id=trade_id,
        symbol="BTC/USDT",
        side="long",
        price=50_000.0,
        size_usd=500.0,
        mode="paper",
        tp_price=None,
        sl_price=None,
        fee_entry_usd=None,
    )
    # Simulate the honest-restart path: close with genuinely unknown PnL
    # (e.g. expired-during-downtime) — must never be coerced to 0.0/False.
    recorder.record_close(
        trade_id=trade_id,
        exit_price=None,
        pnl_usd=None,
        pnl_pct=None,
        reason="expired_on_restore",
        symbol="BTC/USDT",
        side="long",
        size_usd=500.0,
        mode="paper",
    )

    trades = recorder.trades()
    closed = [t for t in trades if getattr(t, "trade_id", None) == trade_id]
    assert closed, "expected the closed trade to be recoverable from the ledger"
    trade = closed[0]
    assert trade.pnl_usd is None
    assert trade.pnl_pct is None
    assert getattr(trade, "is_win", "MISSING") is None


# ── Scenario J — BootGate NON_COMPARABLE → cannot become clear/clean ───────


def test_scenario_j_boot_gate_non_comparable_blocks_clearance():
    from system.boot_gate import BootGate
    from system.position_reconciler import PositionReconciler
    from quant_hedge_ai.agents.execution.position_manager import (
        ExecutionDomain,
        PositionManager,
    )

    exch = TripwireSpotExchange()

    class _ExchWithPositions(TripwireSpotExchange):
        def fetch_positions(self):
            return []

    exch = _ExchWithPositions()
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.UNKNOWN)
    reconciler = PositionReconciler(
        pos_manager=pm, exchange_futures=exch, expected_domain=ExecutionDomain.REAL
    )
    gate = BootGate(reconciler=reconciler)

    report = gate.check(exchange=exch)

    assert report.cleared is False
    assert report.position_reconcile_comparable is False
    assert exch.mutation_calls == []


# ── Scenario K — reconcile skipped too soon → cannot be labeled CLEAN ──────


def test_scenario_k_reconcile_skipped_too_soon_not_clean():
    from quant_hedge_ai.agents.execution.position_manager import (
        ExecutionDomain,
        PositionManager,
    )
    from system.position_reconciler import PositionReconciler

    exch = TripwireSpotExchange()
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    reconciler = PositionReconciler(
        pos_manager=pm, exchange_futures=exch, expected_domain=ExecutionDomain.REAL
    )

    # First call with force=True marks the rate-limit clock; a rapid
    # second call without force=True must be skipped (too soon), not
    # silently reported as clean.
    reconciler.reconcile(force=True)
    report = reconciler.reconcile(force=False)

    assert report.performed is False
    assert report.is_clean is False
    assert exch.mutation_calls == []


# ── Scenario L — read-only real-account observation occurs → no sizing ────
# authority, no mutation authority


def test_scenario_l_real_account_observation_confers_no_authority(monkeypatch):
    """`WalletSync.observe_exchange_balance()` is a read-only accessor that
    must never feed `fetch_available_capital()`/sizing, and observing a
    real account must never itself trigger a mutating call."""
    from infra import wallet_sync

    class _ObservedExchange(TripwireSpotExchange):
        def fetch_balance(self):
            return {"USDT": {"free": 987654.0}, "free": {"USDT": 987654.0}}

    exch = _ObservedExchange()
    ws = wallet_sync.WalletSync()

    # Read-only observation must succeed without any mutation call.
    observed = ws.observe_exchange_balance(exch)
    assert exch.mutation_calls == []

    # The scientific-capital function used for sizing must be provably
    # independent of that observation: it is a pure function of
    # WALLET_PAPER_CAPITAL + ledger PnL and takes no exchange argument at
    # all — call it and confirm no mutation call happened as a side
    # effect, and that its signature has no path to the observed exchange.
    capital = wallet_sync.get_scientific_capital()
    assert exch.mutation_calls == []
    assert isinstance(capital, (int, float))
    # Observed balance must not silently become the sizing basis.
    assert capital != pytest.approx(987654.0)
    _ = observed  # observed value is legitimately read, never used for sizing here
