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


def test_scenario_c1_leverage_change_gated_before_mutation_REMEDIATED(engine_factory):
    """C1 REMEDIATED (O-02W-PRE-T1-E C1 remediation,
    `ExecutionEngine._futures_mutation_authorized()`):
    `create_futures_order()` now evaluates the external-mutation authority
    gate (PAPER_TRADING_ENABLED / self._live / LIVE_TRADING_CONFIRMED)
    BEFORE `self._exchange_futures.set_leverage(...)`,
    `fetch_ticker`/`load_markets`, `authorize_order()`, and
    `create_order(...)`. A foreign/stale/tripwire futures handle
    force-attached in memory (exactly what this test does) with
    `leverage=3` no longer reaches `set_leverage`: PAPER=true/LIVE=false
    fails the gate closed regardless of handle identity — handle presence
    != execution authority.

    Was strict-XFAIL (`test_scenario_c1_leverage_change_mutates_before_paper_gate_XFAIL`)
    proving the defect; now an ordinary PASS proving the fix."""
    eng, _, fut = engine_factory(with_futures_handle=True)

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=3, decision_id="cert-C1-leverage-change"
    )

    assert fut.mutation_calls == []
    assert result.get("mode") != "live"
    assert result.get("denial_reason") == "AUTHORITY_DENIED"


# ── C1 authority matrix (O-02W-PRE-T1-E C1 remediation) ─────────────────────


def test_c1_a_paper_gate_zero_mutation(engine_factory, monkeypatch):
    """C1-A: PAPER=true, self._live=false, LIVE_TRADING_CONFIRMED=false,
    futures handle exists, leverage=3 → zero mutation."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "false")
    eng, _, fut = engine_factory(with_futures_handle=True)
    eng._live = False

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=3, decision_id="c1-a"
    )

    assert fut.mutation_calls == []
    assert result["mode"] == "rejected"
    assert result["denial_reason"] == "AUTHORITY_DENIED"


def test_c1_b_stale_handle_with_paper_zero_mutation(engine_factory, monkeypatch):
    """C1-B: PAPER=true, self._live=false, foreign/stale futures handle
    exists → zero mutation regardless of handle identity."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "false")
    eng, _, fut = engine_factory(with_futures_handle=True)
    eng._live = False
    # Foreign/stale handle: a different tripwire instance than construction.
    eng._exchange_futures = TripwireFuturesExchange()

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=3, decision_id="c1-b"
    )

    assert eng._exchange_futures.mutation_calls == []
    assert result["mode"] == "rejected"
    assert result["denial_reason"] == "AUTHORITY_DENIED"


def test_c1_c_live_object_not_armed_by_environment(engine_factory, monkeypatch):
    """C1-C: PAPER=false, self._live=true, LIVE_TRADING_CONFIRMED=false,
    futures handle exists, leverage=3 → zero mutation. Proves merely
    constructing/corrupting an object with `live=True` does not bypass the
    explicit operator confirmation."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "false")
    eng, _, fut = engine_factory(with_futures_handle=True)
    eng._live = True

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=3, decision_id="c1-c"
    )

    assert fut.mutation_calls == []
    assert result["mode"] == "rejected"
    assert result["denial_reason"] == "AUTHORITY_DENIED"


def test_c1_d_live_false_remains_fail_closed(engine_factory, monkeypatch):
    """C1-D: PAPER=false, self._live=false, LIVE_TRADING_CONFIRMED=true,
    futures handle exists → zero mutation."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
    eng, _, fut = engine_factory(with_futures_handle=True)
    eng._live = False

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=3, decision_id="c1-d"
    )

    assert fut.mutation_calls == []
    assert result["mode"] == "rejected"
    assert result["denial_reason"] == "AUTHORITY_DENIED"


def test_c1_e_authorized_path_remains_reachable(engine_factory, monkeypatch):
    """C1-E (R2): PAPER=false, self._live=true, LIVE_TRADING_CONFIRMED=true,
    leverage=1, fake (non-tripwire) exchange only → the C1 gate does not
    permanently disable the legitimate future TESTNET/LIVE code path. This
    proves ONLY that authorized authority state can proceed past the C1
    gate to a single `create_order` mutation — not that live trading is
    safe, and not anything about leverage (leverage>1 is a separate,
    fail-closed policy — see `test_c1_leverage_gt_1_authorized_fail_closed`
    below). No network call is made (the fake exchange is fully
    in-memory). `set_leverage` must NEVER be called on this path per the
    R2 single-mutation correction (ADR-0020: one coordinator callback =
    one physical exchange mutation)."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
    monkeypatch.setenv("EXCHANGE_ID", "mexc")
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
    eng, _, _ = engine_factory(with_futures_handle=False)
    eng._live = True

    class _FakeAuthorizedFuturesExchange:
        id = "krakenfutures"

        def __init__(self):
            self.leverage_calls = []
            self.order_calls = []

        def set_leverage(self, leverage, symbol):
            self.leverage_calls.append((leverage, symbol))

        def fetch_ticker(self, symbol):
            return {"last": 100.0}

        def load_markets(self):
            return {}

        def create_order(self, symbol, order_type, side, qty, params=None):
            self.order_calls.append((symbol, order_type, side, qty))
            return {"id": "fake-order-1", "status": "closed", "avgPrice": 100.0}

    fake = _FakeAuthorizedFuturesExchange()
    eng._exchange_futures = fake

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=1, decision_id="c1-e"
    )

    assert result["mode"] != "rejected"
    assert fake.leverage_calls == []
    assert fake.order_calls != []


def test_c1_leverage_gt_1_authorized_fail_closed(engine_factory, monkeypatch):
    """O-02W-PRE-T1-E C1 R2 — temporary leverage safety policy. Even with
    FULL authority (PAPER=false, self._live=true, LIVE_TRADING_CONFIRMED=
    true) and a futures handle present, `leverage != 1` must fail closed
    BEFORE any exchange interaction: `set_leverage` is an independent
    external mutation whose durable, at-most-once semantics REM-B's
    single-mutation OrderIntent protocol (ADR-0020) does not model. This
    is not an authority denial — the caller has valid trading authority —
    so the reason is `UNSUPPORTED_MARKET_SEMANTICS`, not
    `AUTHORITY_DENIED`."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
    eng, _, _ = engine_factory(with_futures_handle=False)
    eng._live = True

    class _AllCallsTripwire:
        id = "krakenfutures"

        def __init__(self):
            self.calls: list[str] = []

        def set_leverage(self, *a, **kw):
            self.calls.append("set_leverage")
            raise MutationTripwire("set_leverage called")

        def fetch_ticker(self, *a, **kw):
            self.calls.append("fetch_ticker")
            return {"last": 100.0}

        def load_markets(self, *a, **kw):
            self.calls.append("load_markets")
            return {}

        def create_order(self, *a, **kw):
            self.calls.append("create_order")
            raise MutationTripwire("create_order called")

    tripwire = _AllCallsTripwire()
    eng._exchange_futures = tripwire

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=3, decision_id="c1-leverage-fail-closed"
    )

    assert tripwire.calls == []
    assert result["mode"] == "rejected"
    assert result["denial_reason"] == "UNSUPPORTED_MARKET_SEMANTICS"


def test_c1_mutation_ordering_zero_calls_when_unauthorized(engine_factory, monkeypatch):
    """Mutation ordering proof: under an unauthorized authority state, NO
    call of any kind (mutating or read-only) reaches the futures handle —
    the gate short-circuits before `set_leverage`, `fetch_ticker`,
    `load_markets`, AND `create_order`."""
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "false")
    eng, _, _ = engine_factory(with_futures_handle=False)
    eng._live = False

    class _AllCallsTripwire:
        id = "krakenfutures"

        def __init__(self):
            self.calls: list[str] = []

        def set_leverage(self, *a, **kw):
            self.calls.append("set_leverage")
            raise MutationTripwire("set_leverage called")

        def fetch_ticker(self, *a, **kw):
            self.calls.append("fetch_ticker")
            return {"last": 100.0}

        def load_markets(self, *a, **kw):
            self.calls.append("load_markets")
            return {}

        def create_order(self, *a, **kw):
            self.calls.append("create_order")
            raise MutationTripwire("create_order called")

    tripwire = _AllCallsTripwire()
    eng._exchange_futures = tripwire

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=3, decision_id="c1-ordering"
    )

    assert tripwire.calls == []
    assert result["mode"] == "rejected"
    assert result["denial_reason"] == "AUTHORITY_DENIED"


def test_c1_authorized_ordering_proof_full_pipeline(tmp_path, monkeypatch):
    """O-02W-PRE-T1-E C1 R2 — authorized-path ordering proof (durable,
    not merely label-appended).

    Complements `test_c1_mutation_ordering_zero_calls_when_unauthorized`
    (the negative proof) with the positive one: under a fully authorized
    state (leverage=1, per the R2 single-mutation policy), the recorded
    event sequence must be exactly

        C1_AUTHORITY -> REM_A_AUTHORIZE -> REM_B_BIND ->
        INTENT_RECORDED -> SUBMISSION_STARTED -> create_order

    `INTENT_RECORDED` and `SUBMISSION_STARTED` are NOT labels appended by
    this test ahead of time — they are recorded by wrapping the REAL
    `OrderIntentJournal.append_transition`, which `OrderIntentCoordinator.
    submit()` calls to durably persist each state before ever invoking the
    `mutate` callback (ADR-0020). This test additionally asserts that, at
    the exact instant the fake exchange's `create_order` is invoked, the
    real journal already contains a durable `SUBMISSION_STARTED` record
    for this intent — the strongest available proof that the durable
    record precedes the network mutation, not merely that events happen
    to append in the right order. Also asserts `set_leverage` is never
    called (call_count == 0) and `create_order` is called exactly once
    (call_count == 1), consistent with the ADR-0020 single-mutation
    contract restored in R2."""
    from quant_hedge_ai.agents.execution import execution_engine as ee_module
    from quant_hedge_ai.agents.execution import order_intent_protocol as oip
    from quant_hedge_ai.agents.execution.decision_identity import (
        DecisionIdentityJournal,
    )
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    events: list[str] = []

    real_authorized = ExecutionEngine._futures_mutation_authorized

    def recording_authorized(self):
        result = real_authorized(self)
        if result:
            events.append("C1_AUTHORITY")
        return result

    real_authorize_order = ee_module.authorize_order

    def recording_authorize_order(*args, **kwargs):
        auth = real_authorize_order(*args, **kwargs)
        if auth.authorized:
            events.append("REM_A_AUTHORIZE")
        return auth

    real_bind = ExecutionEngine._bind_decision_to_intent

    def recording_bind(self, decision_id, intent):
        denial = real_bind(self, decision_id, intent)
        if denial is None:
            events.append("REM_B_BIND")
        return denial

    real_append_transition = oip.OrderIntentJournal.append_transition
    journal_ref: dict = {}

    def recording_append_transition(self, *, state, **kwargs):
        record = real_append_transition(self, state=state, **kwargs)
        events.append(state.value)
        journal_ref["journal"] = self
        journal_ref["digest"] = kwargs.get("intent_digest")
        return record

    monkeypatch.setattr(ExecutionEngine, "_futures_mutation_authorized", recording_authorized)
    monkeypatch.setattr(ee_module, "authorize_order", recording_authorize_order)
    monkeypatch.setattr(ExecutionEngine, "_bind_decision_to_intent", recording_bind)
    monkeypatch.setattr(oip.OrderIntentJournal, "append_transition", recording_append_transition)

    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("EXEC_FUTURES_MIN_ORDER_USD", "55")
    monkeypatch.setenv("EXEC_FUTURES_MAX_ORDER_USD", "200")

    mexc_caps = oip.AdapterCapabilities(
        verdict=oip.AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED,
        client_order_id_param="clientOrderId",
    )
    decisions_path = tmp_path / "decisions.jsonl"
    intents_path = tmp_path / "order_intents.jsonl"

    eng = ExecutionEngine(live=False, _sleep=lambda _: None)
    eng._live = True
    eng._decision_identity_journal = DecisionIdentityJournal(decisions_path)
    eng._order_intent_journal = oip.OrderIntentJournal(intents_path)
    eng._order_intent_coordinator = oip.OrderIntentCoordinator(
        eng._order_intent_journal, mexc_caps
    )
    eng.start_session(equity=10_000.0)
    eng._decision_identity_journal.persist("c1-ordering-authorized", namespace="test")

    class _EventRecordingFuturesExchange:
        id = "krakenfutures"

        def __init__(self):
            self.set_leverage_call_count = 0
            self.create_order_call_count = 0

        def set_leverage(self, leverage, symbol):
            self.set_leverage_call_count += 1
            events.append("set_leverage")

        def fetch_ticker(self, symbol):
            return {"last": 100.0}

        def load_markets(self):
            return {}

        def create_order(self, symbol, order_type, side, qty, params=None):
            self.create_order_call_count += 1
            # Strongest proof: at the instant of the network mutation, the
            # REAL durable journal must already show SUBMISSION_STARTED
            # for this exact intent digest.
            journal = journal_ref["journal"]
            digest = journal_ref["digest"]
            record = journal.get(digest)
            assert record is not None
            assert record["state"] == oip.IntentState.SUBMISSION_STARTED.value
            events.append("create_order")
            return {"id": "fake-order-2", "status": "closed", "avgPrice": 100.0}

    fake = _EventRecordingFuturesExchange()
    eng._exchange_futures = fake

    result = eng.create_futures_order(
        "BTC/USDT", "BUY", 100.0, leverage=1, decision_id="c1-ordering-authorized"
    )

    assert result["mode"] != "rejected"
    assert events[:6] == [
        "C1_AUTHORITY",
        "REM_A_AUTHORIZE",
        "REM_B_BIND",
        "INTENT_RECORDED",
        "SUBMISSION_STARTED",
        "create_order",
    ]
    # Any further events are the coordinator's post-mutation durable
    # classification (e.g. ACKNOWLEDGED) — must come AFTER, never before,
    # the single `create_order` mutation.
    assert "set_leverage" not in events
    assert events.count("create_order") == 1
    assert fake.set_leverage_call_count == 0
    assert fake.create_order_call_count == 1


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
