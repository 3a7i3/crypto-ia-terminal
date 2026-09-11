"""REM-C R1 — execution-domain provenance, reconciliation domain-safety,
and PAPER restart evidence-honesty.

Hermetic tests only: no network, no exchange secrets, no Telegram. Uses the
real PositionManager and real PositionReconciler classes (not mocks of the
interface under test), and the real MexcSimulator/PaperTradeRecorder restore
path via tmp_path.
"""

from __future__ import annotations

import time

from quant_hedge_ai.agents.execution.position_manager import (
    ExecutionDomain,
    Position,
    PositionManager,
    PositionSide,
)
from system.position_reconciler import PositionReconciler


class _FakeRealExchange:
    """Hermetic stand-in for a ccxt-style REAL exchange handle."""

    def __init__(self, positions: list[dict]) -> None:
        self._positions = positions

    def fetch_positions(self) -> list[dict]:
        return self._positions


def _real_position(symbol="BTC/USDT", price=100.0) -> dict:
    return {
        "symbol": symbol,
        "side": "long",
        "contracts": 1.0,
        "markPrice": price,
    }


# ── Scenario A — reconciler API mismatch (fail-before, now regression) ──────


def test_scenario_a_position_manager_has_no_get_open_positions():
    """The canonical PositionManager never exposed get_open_positions() —
    only get_open(). This is the exact defect REM-C R0 found; kept as a
    permanent regression guard so a future rename doesn't reintroduce it
    silently guarded by hasattr()."""
    pm = PositionManager(exchange=_FakeRealExchange([]))
    assert not hasattr(pm, "get_open_positions")
    assert hasattr(pm, "get_open")
    assert pm.get_open() == []


def test_scenario_a_reconciler_now_reads_canonical_api():
    """After the fix, reconcile() must actually see internal positions
    through get_open() instead of silently treating pos_manager as empty."""
    exch = _FakeRealExchange([_real_position("BTC/USDT", 100.0)])
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    pos = Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        size_usd=1000.0,
        qty=10.0,
        domain=ExecutionDomain.REAL,
    )
    pm.add_position(pos, silent=True)

    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.comparable is True
    assert report.internal_positions == 1
    assert report.ghost_positions == []
    assert report.orphan_positions == []


# ── Scenario B — cross-domain false reconciliation risk ─────────────────────


def test_scenario_b_paper_domain_never_compared_against_real_exchange():
    """A PAPER-domain PositionManager must never be reconciled against a
    REAL exchange fetch_positions() — naively swapping get_open_positions()
    for get_open() without a domain check would make an internal PAPER
    position with the SAME symbol as a real exchange position look
    consistent (or, on mismatch, spuriously ghost/orphan) purely by symbol
    string collision. The domain gate must refuse the comparison outright."""
    exch = _FakeRealExchange([_real_position("BTC/USDT", 100.0)])
    paper_pm = PositionManager(exchange=None, paper_mode=True)
    assert paper_pm.domain is ExecutionDomain.PAPER

    paper_pos = Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        size_usd=1000.0,
        qty=10.0,
    )
    paper_pm.add_position(paper_pos, silent=True)
    assert paper_pos.domain is ExecutionDomain.PAPER

    rec = PositionReconciler(exch, paper_pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.comparable is False
    assert report.pm_domain == ExecutionDomain.PAPER.value
    assert report.ghost_positions == []
    assert report.orphan_positions == []
    assert report.internal_positions == 0
    assert report.exchange_positions == 0


def test_scenario_b_unknown_domain_fails_closed():
    """A pos_manager whose domain could not be established (UNKNOWN) must
    never be reconciled either — UNKNOWN is not treated as REAL."""
    exch = _FakeRealExchange([_real_position("ETH/USDT", 10.0)])
    pm = PositionManager()  # no exchange, no paper_mode -> UNKNOWN
    assert pm.domain is ExecutionDomain.UNKNOWN

    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.comparable is False
    assert report.ghost_positions == []
    assert report.orphan_positions == []


def test_individual_unknown_domain_position_excluded_not_fabricated_ghost():
    """Even when pos_manager as a whole is REAL, an individual position
    that somehow carries UNKNOWN domain must be excluded from ghost/orphan
    comparison, not silently treated as REAL and flagged ghost."""
    exch = _FakeRealExchange([])  # nothing on exchange
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    stray = Position(
        symbol="SOL/USDT",
        side=PositionSide.LONG,
        entry_price=20.0,
        size_usd=100.0,
        qty=5.0,
        domain=ExecutionDomain.UNKNOWN,
    )
    # Bypass add_position()'s auto-stamping (which would resolve UNKNOWN to
    # the manager's own domain) to simulate a position that reached the
    # internal store with a genuinely unresolved domain (e.g. loaded from
    # a historical/legacy source outside the normal construction path).
    pm._positions[stray.symbol] = stray

    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.comparable is True
    assert report.ghost_positions == []  # never fabricated from UNKNOWN
    assert report.unresolved_domain_positions == ["SOL/USDT"]


# ── Scenario C — PAPER restart evidence fabrication ──────────────────────────


def test_scenario_c_restore_no_longer_fabricates_pnl_on_expiry(tmp_path, monkeypatch):
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    recorder = PaperTradeRecorder(log_path=str(log_path))
    old_ts = time.time() - 999999
    recorder.record_open(
        trade_id="T1",
        symbol="BTC/USDT",
        side="buy",
        price=100.0,
        size_usd=50.0,
        mode="futures_demo",
    )
    # Force the OPEN event's timestamp into the past to trigger expiry.
    import json

    lines = log_path.read_text().splitlines()
    evt = json.loads(lines[0])
    evt["ts"] = old_ts
    log_path.write_text(json.dumps(evt) + "\n")

    recorder.record_close(
        trade_id="T1",
        exit_price=100.0,
        pnl_usd=None,
        pnl_pct=None,
        reason="expired_on_restore",
        opened_at=old_ts,
        symbol="BTC/USDT",
        side="buy",
        size_usd=50.0,
    )

    trades = recorder.trades()
    assert len(trades) == 1
    ct = trades[0]
    assert ct.exit_reason == "expired_on_restore"
    # Core R1-I7 invariant: missing evidence must stay None, never 0.0.
    assert ct.pnl_usd is None
    assert ct.pnl_pct is None


def test_scenario_c_restore_flags_reconstructed_tp_sl_and_fee(tmp_path, monkeypatch):
    """Pre-v4 (or otherwise incomplete) ledger records carry no tp_price/
    sl_price/fee_entry_usd. Restoration must recompute usable values (the
    position-manager can't run with no TP/SL at all) but must NOT claim
    them as the original evidence — MexcPosition.restored_evidence_gaps
    must say so, and personality must not silently read 'restored' as if
    fully evidenced."""
    from paper_trading.mexc_simulator import MexcSimulator
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="T2",
        symbol="ETH/USDT",
        side="buy",
        price=2000.0,
        size_usd=100.0,
        mode="futures_demo",
        # tp_price/sl_price/fee_entry_usd intentionally omitted — simulates
        # a pre-schema-v4 record where this evidence was never captured.
    )

    import paper_trading.recorder as _recorder_mod

    _recorder_mod._recorder = None  # avoid leaking a prior test's singleton
    sim = MexcSimulator()
    sim._capital = 100000.0
    restored = sim._restore_positions()

    assert restored == 1
    pos = sim._positions["ETH/USDT"]
    assert "tp_sl_reconstructed_default" in pos.restored_evidence_gaps
    assert "fee_entry_unknown" in pos.restored_evidence_gaps
    assert pos.personality == "restored_evidence_incomplete"


def test_scenario_c_restore_honors_durably_recorded_tp_sl_fee(tmp_path, monkeypatch):
    """When schema-v4 evidence genuinely exists, restoration must use it
    verbatim rather than recomputing defaults (R1-I9)."""
    from paper_trading.mexc_simulator import MexcSimulator
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="T3",
        symbol="XRP/USDT",
        side="buy",
        price=1.0,
        size_usd=50.0,
        mode="futures_demo",
        tp_price=1.10,
        sl_price=0.95,
        fee_entry_usd=0.05,
    )

    import paper_trading.recorder as _recorder_mod

    _recorder_mod._recorder = None  # avoid leaking a prior test's singleton
    sim = MexcSimulator()
    sim._capital = 100000.0
    restored = sim._restore_positions()

    assert restored == 1
    pos = sim._positions["XRP/USDT"]
    assert pos.tp_price == 1.10
    assert pos.sl_price == 0.95
    assert pos.fee_entry_usd == 0.05
    assert pos.restored_evidence_gaps == []
    assert pos.personality == "restored"


# ── Observational-only invariant (R1-I6) ─────────────────────────────────────


def test_reconciler_never_calls_any_mutation_method():
    """PositionReconciler must only ever call fetch_positions() on the
    exchange handle and get_open() on pos_manager — never anything that
    could create/close/modify an order or position."""

    class _MutationTrap:
        def fetch_positions(self):
            return [_real_position("BTC/USDT", 100.0)]

        def __getattr__(self, name):
            if name in (
                "create_order",
                "cancel_order",
                "close_position",
                "create_market_order",
            ):
                raise AssertionError(f"reconciler attempted mutation: {name}")
            raise AttributeError(name)

    exch = _MutationTrap()
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)
    assert report.comparable is True


# ═════════════════════════════════════════════════════════════════════════════
# REM-C R1.1 — MASTER correction round
# ═════════════════════════════════════════════════════════════════════════════
#
# R1 introduced ExecutionDomain but still let `PositionManager(exchange=X)`
# infer REAL from mere non-nullness, let same-domain labels alone authorize
# reconciliation across distinct exchange handles, still substituted
# entry_price as a fabricated exit_price on downtime expiry, converted
# unknown PnL into a LOSS via `is_win`, and let BootGate clear trading on a
# non-comparable (never-actually-performed) position reconciliation. This
# section reproduces each defect against the exact reviewed R1 HEAD
# (027cb0c71ce291209794ba929bff729ab71876c0) semantics, then re-asserts the
# corrected behavior as a permanent regression.


# ── Finding A — opaque exchange handle is not proof of REAL ─────────────────


def test_a1_nonnull_exchange_alone_is_not_real():
    """A1 — PositionManager(exchange=<opaque non-None>) with no explicit
    domain and paper_mode=False must resolve UNKNOWN, never REAL. This is
    the exact defect R1 shipped (`exchange is not None -> REAL`)."""
    pm = PositionManager(exchange=object())
    assert pm.domain is ExecutionDomain.UNKNOWN


def test_a2_testnet_provenance_cannot_become_real_silently():
    """A2 — an explicitly-TESTNET PositionManager must stay TESTNET even
    though a non-None exchange handle is also present."""
    pm = PositionManager(exchange=object(), domain=ExecutionDomain.TESTNET)
    assert pm.domain is ExecutionDomain.TESTNET


def test_a3_futures_demo_provenance_cannot_become_real_silently():
    """A3 — same guarantee for FUTURES_DEMO."""
    pm = PositionManager(exchange=object(), domain=ExecutionDomain.FUTURES_DEMO)
    assert pm.domain is ExecutionDomain.FUTURES_DEMO


def test_a4_paper_still_resolves_correctly():
    """A4 — paper_mode=True still resolves PAPER regardless of exchange."""
    assert PositionManager(paper_mode=True).domain is ExecutionDomain.PAPER
    assert (
        PositionManager(exchange=object(), paper_mode=True).domain
        is ExecutionDomain.PAPER
    )


def test_a5_unknown_remains_unknown():
    """A5 — no exchange, no paper_mode, no explicit domain -> UNKNOWN."""
    assert PositionManager().domain is ExecutionDomain.UNKNOWN


def test_a6_advisor_construction_supplies_proven_domain_explicitly():
    """A6 — `core/advisor_loop.py::_futures_position_domain()` must derive
    the domain from `ExecutionEngine._mode` (proven evidence), never from
    whether `_get_exchange_futures()` happened to return a non-None
    object. Covers: paper_mode short-circuit, live -> REAL, testnet ->
    TESTNET, and an unrecognized/absent mode failing closed to UNKNOWN —
    even when a non-None exchange handle is attached to the fake engine
    (proving the handle's presence plays no role in the decision)."""
    from core.advisor_loop import _futures_position_domain

    class _FakeEngine:
        def __init__(self, mode):
            self._mode = mode
            self._exchange_futures = object()  # non-None on purpose

    assert _futures_position_domain(_FakeEngine("live"), True) is ExecutionDomain.PAPER
    assert (
        _futures_position_domain(_FakeEngine("live"), False) is ExecutionDomain.REAL
    )
    assert (
        _futures_position_domain(_FakeEngine("testnet"), False)
        is ExecutionDomain.TESTNET
    )
    assert (
        _futures_position_domain(_FakeEngine("paper"), False)
        is ExecutionDomain.UNKNOWN
    )
    assert (
        _futures_position_domain(_FakeEngine(None), False) is ExecutionDomain.UNKNOWN
    )


# ── Finding B — same domain label is not same account/exchange ─────────────


def test_b1_same_domain_same_exchange_handle_is_comparable():
    """B1 — same domain + identical exchange object -> comparable (when
    otherwise valid). Regression pin of the existing Scenario A fix."""
    exch = _FakeRealExchange([])
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)
    assert report.comparable is True


def test_b2_same_domain_different_exchange_handles_is_non_comparable():
    """B2 — both PositionManager and PositionReconciler are labeled REAL,
    but they hold DIFFERENT exchange objects (e.g. two distinct accounts
    both happening to be labeled REAL). Must be non-comparable — a domain
    label alone must never authorize reconciliation."""
    exch_a = _FakeRealExchange([_real_position("BTC/USDT", 100.0)])
    exch_b = _FakeRealExchange([_real_position("BTC/USDT", 100.0)])
    pm = PositionManager(exchange=exch_a, domain=ExecutionDomain.REAL)

    rec = PositionReconciler(exch_b, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.comparable is False
    assert report.ghost_positions == []
    assert report.orphan_positions == []
    assert "identity" in (report.error or "")


def test_b3_unknown_exchange_identity_is_non_comparable():
    """B3 — a pos_manager that exposes no usable `_exchange` attribute at
    all (identity unprovable) must not be reconciled even if some other
    signal made its domain label match."""

    class _NoExchangeAttrPM:
        domain = ExecutionDomain.REAL

        def get_open(self):
            return []

    exch = _FakeRealExchange([])
    rec = PositionReconciler(exch, _NoExchangeAttrPM(), expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.comparable is False
    assert report.ghost_positions == []
    assert report.orphan_positions == []


def test_b4_zero_exchange_mutation_still_holds():
    """B4 — regression: the exchange-identity check itself must not touch
    the exchange object in any mutating way (attribute access only)."""

    class _MutationTrap:
        def fetch_positions(self):
            return []

        def __getattr__(self, name):
            if name != "fetch_positions":
                raise AssertionError(f"unexpected exchange access: {name}")
            raise AttributeError(name)

    exch = _MutationTrap()
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)
    assert report.comparable is True


# ── Finding C — expired PAPER restore must not fabricate exit price ────────


def test_c_expired_restore_exit_price_is_none(tmp_path, monkeypatch):
    from paper_trading.mexc_simulator import MexcSimulator
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    recorder = PaperTradeRecorder(log_path=str(log_path))
    old_ts = time.time() - 999999
    recorder.record_open(
        trade_id="T4",
        symbol="ADA/USDT",
        side="buy",
        price=0.5,
        size_usd=50.0,
        mode="futures_demo",
    )
    import json

    lines = log_path.read_text().splitlines()
    evt = json.loads(lines[0])
    evt["ts"] = old_ts
    log_path.write_text(json.dumps(evt) + "\n")

    import paper_trading.recorder as _recorder_mod

    _recorder_mod._recorder = None
    sim = MexcSimulator()
    sim._capital = 100000.0
    sim._restore_positions()

    trades = PaperTradeRecorder(log_path=str(log_path)).trades()
    assert len(trades) == 1
    ct = trades[0]
    assert ct.exit_reason == "expired_on_restore"
    # Core R1.1 correction: exit_price must stay unknown, never the entry
    # price presented as if it were the genuine (unrecorded) exit price.
    assert ct.exit_price is None
    assert ct.pnl_usd is None
    assert ct.pnl_pct is None


# ── Finding D — unknown PnL must not become a LOSS ──────────────────────────


def test_d1_d2_d3_d4_expired_restore_is_fully_unknown(tmp_path, monkeypatch):
    """D1-D4 — expired restore -> exit_price/pnl_usd/pnl_pct/is_win all
    None, never coerced into known-zero or LOSS."""
    from paper_trading.mexc_simulator import MexcSimulator
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    recorder = PaperTradeRecorder(log_path=str(log_path))
    old_ts = time.time() - 999999
    recorder.record_open(
        trade_id="T5",
        symbol="DOT/USDT",
        side="sell",
        price=5.0,
        size_usd=50.0,
        mode="futures_demo",
    )
    import json

    lines = log_path.read_text().splitlines()
    evt = json.loads(lines[0])
    evt["ts"] = old_ts
    log_path.write_text(json.dumps(evt) + "\n")

    import paper_trading.recorder as _recorder_mod

    _recorder_mod._recorder = None
    sim = MexcSimulator()
    sim._capital = 100000.0
    sim._restore_positions()

    ct = PaperTradeRecorder(log_path=str(log_path)).trades()[0]
    assert ct.exit_price is None
    assert ct.pnl_usd is None
    assert ct.pnl_pct is None
    assert ct.is_win is None  # D4 — never False (LOSS) merely from None


def test_d5_status_display_does_not_render_unknown_as_loss(capsys, monkeypatch):
    """D5 — paper_trading/status.py must render an unknown outcome as a
    neutral label, never as LOSS. Drives the real `main()` entry point
    against a fake recorder (no disk I/O) that returns one
    `expired_on_restore` trade with is_win=None."""
    import paper_trading.status as status_mod
    from paper_trading.recorder import CompleteTrade

    unknown_trade = CompleteTrade(
        trade_id="t-unknown",
        symbol="ADA/USDT",
        side="buy",
        regime="unknown",
        score=50,
        mode="futures_demo",
        entry_price=0.5,
        size_usd=50.0,
        opened_at=time.time() - 100,
        opened_iso="",
        order_id="",
        exit_price=None,
        pnl_usd=None,
        pnl_pct=None,
        exit_reason="expired_on_restore",
        closed_at=time.time(),
        closed_iso="",
        is_open=False,
        is_win=None,
    )

    class _FakeRecorder:
        _path = "<fake>"

        def trades(self):
            return [unknown_trade]

        def summary(self):
            return {
                "total_closed": 1,
                "total_open": 0,
                "win_rate": 0.0,
                "pnl_total_usd": 0.0,
                "pnl_avg_pct": None,
                "best_trade_pct": None,
                "worst_trade_pct": None,
                "avg_duration_min": None,
                "go_live_ready": False,
            }

    monkeypatch.setattr(status_mod, "PaperTradeRecorder", _FakeRecorder)
    status_mod.main()
    out = capsys.readouterr().out
    assert "LOSS" not in out
    assert "N/A" in out


def test_d6_dataset_validator_still_excludes_expired_on_restore(tmp_path):
    """D6 — regression: `validate_corpus()`'s exclusion of
    `expired_on_restore` from win/loss population stats is unaffected by
    the None-PnL/None-exit-price changes (drives the real recorder/
    validator through a temp JSONL log, no internal helper reached
    directly)."""
    from paper_trading.dataset_validator import validate_corpus
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "corpus.jsonl"
    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="t1",
        symbol="BTC/USDT",
        side="buy",
        price=100.0,
        size_usd=50.0,
        mode="futures_demo",
    )
    recorder.record_close(
        trade_id="t1",
        exit_price=None,
        pnl_usd=None,
        pnl_pct=None,
        reason="expired_on_restore",
        opened_at=time.time() - 100,
        symbol="BTC/USDT",
        side="buy",
        size_usd=50.0,
    )

    report = validate_corpus(str(log_path))
    assert report.expired_on_restore == 1
    assert report.win_count == 0
    assert report.loss_count == 0


def test_d7_genuine_zero_pnl_stays_distinguishable_from_unknown():
    """D7 — a real, recorded pnl_usd=0.0 trade remains a known non-win
    (is_win=False), distinct from a genuinely-unknown pnl_usd=None
    (is_win=None)."""
    from paper_trading.recorder import PaperTradeRecorder, TradeEvent

    now = time.time()
    op = TradeEvent(
        event="OPEN",
        trade_id="t2",
        ts=now - 100,
        ts_iso="",
        symbol="ETH/USDT",
        side="buy",
        price=100.0,
        size_usd=50.0,
        mode="futures_demo",
    )
    cl_zero = TradeEvent(
        event="CLOSE",
        trade_id="t2",
        ts=now,
        ts_iso="",
        symbol="ETH/USDT",
        side="buy",
        price=100.0,
        size_usd=50.0,
        mode="futures_demo",
        exit_price=100.0,
        pnl_usd=0.0,
        pnl_pct=0.0,
        reason="stop_loss",
    )
    cl_unknown = TradeEvent(
        event="CLOSE",
        trade_id="t2",
        ts=now,
        ts_iso="",
        symbol="ETH/USDT",
        side="buy",
        price=0.0,
        size_usd=50.0,
        mode="futures_demo",
        exit_price=None,
        pnl_usd=None,
        pnl_pct=None,
        reason="expired_on_restore",
    )

    class _FakeRecorder(PaperTradeRecorder):
        def __init__(self, events):
            self._events = events

        def events(self):
            return self._events

    zero_trade = _FakeRecorder([op, cl_zero]).trades()[0]
    unknown_trade = _FakeRecorder([op, cl_unknown]).trades()[0]

    assert zero_trade.pnl_usd == 0.0
    assert zero_trade.is_win is False  # known non-win, not unknown
    assert unknown_trade.pnl_usd is None
    assert unknown_trade.is_win is None  # genuinely unknown


# ── Finding E — BootGate must fail closed on non-comparable reconciliation ─


def _boot_gate_with_report(report):
    from unittest.mock import MagicMock

    from system.boot_gate import BootGate

    rec = MagicMock()
    rec.reconcile.return_value = report
    return BootGate(rec)


def test_e1_comparable_clean_report_preserves_clearance():
    from system.position_reconciler import ReconcileReport

    gate = _boot_gate_with_report(ReconcileReport())
    report = gate.check()
    assert report.cleared is True


def test_e2_non_comparable_report_denies_clearance():
    """E2 — the exact MASTER-reported gap: a NON_COMPARABLE reconciliation
    (empty ghost/orphan by construction) must not clear the gate."""
    from system.position_reconciler import ReconcileReport

    non_comparable = ReconcileReport(
        comparable=False,
        pm_domain=ExecutionDomain.PAPER.value,
        expected_domain=ExecutionDomain.REAL.value,
        error="non-comparable execution domains: pos_manager=paper expected=real",
    )
    assert non_comparable.ghost_positions == []
    assert non_comparable.orphan_positions == []

    gate = _boot_gate_with_report(non_comparable)
    report = gate.check()

    assert report.cleared is False
    assert not gate.is_cleared()
    assert "non-comparable" in (report.reason or "").lower() or "identity" in (
        report.reason or ""
    ).lower() or "domain" in (report.reason or "").lower()


def test_e3_domain_account_mismatch_denies_clearance():
    """E3 — same as E2 for the exchange-identity-mismatch flavor of
    non-comparable (both labeled REAL, different accounts)."""
    from system.position_reconciler import ReconcileReport

    mismatched = ReconcileReport(
        comparable=False,
        pm_domain=ExecutionDomain.REAL.value,
        expected_domain=ExecutionDomain.REAL.value,
        error="domain matches (real) but exchange/account identity is unproven",
    )
    gate = _boot_gate_with_report(mismatched)
    report = gate.check()

    assert report.cleared is False


def test_e4_ghost_orphan_behavior_unchanged():
    from system.position_reconciler import ReconcileReport

    dirty = ReconcileReport(ghost_positions=["BTC/USDT"])
    gate = _boot_gate_with_report(dirty)
    report = gate.check()

    assert report.cleared is False
    assert "BTC/USDT" in report.ghost_positions


def test_e5_no_mutation_in_boot_gate_path():
    """E5 — BootGate.check() must only read from the reconciler mock, never
    call anything beyond `.reconcile()`."""
    from unittest.mock import MagicMock

    from system.boot_gate import BootGate
    from system.position_reconciler import ReconcileReport

    rec = MagicMock(spec=["reconcile"])
    rec.reconcile.return_value = ReconcileReport()
    gate = BootGate(rec)
    report = gate.check()
    assert report.cleared is True


# ── Section 6 — ReconcileReport must never claim CLEAN for a skipped run ───


def test_skipped_reconcile_is_not_reported_as_clean():
    from system.position_reconciler import PositionReconciler

    exch = _FakeRealExchange([])
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)

    rec.reconcile(force=True)  # first run, sets _last_reconcile
    skipped = rec.reconcile(force=False)  # too soon -> skipped

    assert skipped.performed is False
    assert skipped.is_clean is False
    assert skipped.error == "skipped — too soon"


# ═════════════════════════════════════════════════════════════════════════════
# REM-C R1.2 — MASTER correction round
# ═════════════════════════════════════════════════════════════════════════════
#
# MASTER review of R1.1 (head 79cb77ebb77d202c8323509b0119cdd264f754a5) found:
#   A. unresolved_domain_positions could coexist with is_clean=True;
#   B. an internal-state read failure (missing get_open()/raised exception)
#      fell back to treating the internal side as empty — fail-open, not
#      fail-closed;
#   C. the raw PaperTradeRecorder ledger event still fabricated price=0.0
#      for an expired_on_restore CLOSE even though the derived exit_price/
#      pnl fields were already None.
# Each is reproduced against the exact reviewed semantics, then re-asserted
# as a permanent regression.


# ── Finding A — unresolved domain positions must deny CLEAN ────────────────


def test_a1_unresolved_domain_position_denies_clean_without_fabricating_findings():
    exch = _FakeRealExchange([])
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    stray = Position(
        symbol="SOL/USDT",
        side=PositionSide.LONG,
        entry_price=20.0,
        size_usd=100.0,
        qty=5.0,
        domain=ExecutionDomain.UNKNOWN,
    )
    pm._positions[stray.symbol] = stray  # bypass add_position's auto-stamp

    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.ghost_positions == []
    assert report.orphan_positions == []
    assert "SOL/USDT" in report.unresolved_domain_positions
    assert report.is_clean is False  # R1.2 core invariant


def test_a2_boot_gate_denies_clearance_on_unresolved_domain_position():
    from unittest.mock import MagicMock

    from system.boot_gate import BootGate

    exch = _FakeRealExchange([])
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    stray = Position(
        symbol="SOL/USDT",
        side=PositionSide.LONG,
        entry_price=20.0,
        size_usd=100.0,
        qty=5.0,
        domain=ExecutionDomain.UNKNOWN,
    )
    pm._positions[stray.symbol] = stray

    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    gate_rec = MagicMock()
    gate_rec.reconcile.return_value = rec.reconcile(force=True)
    gate = BootGate(gate_rec)
    report = gate.check()

    assert report.cleared is False


def test_a3_summary_reports_unresolved_domain_never_clean():
    exch = _FakeRealExchange([])
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    stray = Position(
        symbol="SOL/USDT",
        side=PositionSide.LONG,
        entry_price=20.0,
        size_usd=100.0,
        qty=5.0,
        domain=ExecutionDomain.UNKNOWN,
    )
    pm._positions[stray.symbol] = stray

    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert "UNRESOLVED_DOMAIN" in report.summary()
    assert report.summary() != "CLEAN"


# ── Finding B — internal-state read failure must fail closed ───────────────


def test_b1_get_open_raises_with_empty_exchange_is_not_clean():
    """Fail-before proof: an exception from get_open() must never allow a
    CLEAN result just because the exchange side happens to be empty."""

    class _RaisingPM:
        domain = ExecutionDomain.REAL
        _exchange = None

        def get_open(self):
            raise RuntimeError("internal state corrupted")

    exch = _FakeRealExchange([])
    pm = _RaisingPM()
    pm._exchange = exch
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.is_clean is False
    assert report.internal_state_readable is False
    assert report.ghost_positions == []
    assert report.orphan_positions == []


def test_b2_get_open_raises_with_nonempty_exchange_does_not_fabricate_orphan():
    """Fail-before proof: with real exchange positions present, a failed
    internal read must not manufacture ORPHAN findings for every one of
    them."""

    class _RaisingPM:
        domain = ExecutionDomain.REAL

        def get_open(self):
            raise RuntimeError("internal state corrupted")

    exch = _FakeRealExchange([_real_position("BTC/USDT", 100.0)])
    pm = _RaisingPM()
    pm._exchange = exch
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.orphan_positions == []
    assert report.is_clean is False
    assert report.internal_state_readable is False


def test_b3_missing_get_open_fails_closed_not_empty():
    """Fail-before proof: a pos_manager exposing no get_open() at all must
    not be silently treated as `[]` (zero positions)."""

    class _NoGetOpenPM:
        domain = ExecutionDomain.REAL

    exch = _FakeRealExchange([_real_position("ETH/USDT", 10.0)])
    pm = _NoGetOpenPM()
    pm._exchange = exch
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.internal_state_readable is False
    assert report.is_clean is False
    assert report.orphan_positions == []


def test_b4_valid_empty_get_open_is_distinguishable_and_can_be_clean():
    """A pos_manager that genuinely has zero open positions (get_open()
    returns [] without raising) must still be able to reach CLEAN when the
    exchange is also genuinely empty — distinct from B1/B3's unreadable
    state."""
    exch = _FakeRealExchange([])
    pm = PositionManager(exchange=exch, domain=ExecutionDomain.REAL)
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)
    report = rec.reconcile(force=True)

    assert report.internal_state_readable is True
    assert report.is_clean is True


def test_b5_boot_gate_denies_clearance_on_unreadable_internal_state():
    from unittest.mock import MagicMock

    from system.boot_gate import BootGate

    class _RaisingPM:
        domain = ExecutionDomain.REAL

        def get_open(self):
            raise RuntimeError("internal state corrupted")

    exch = _FakeRealExchange([])
    pm = _RaisingPM()
    pm._exchange = exch
    rec = PositionReconciler(exch, pm, expected_domain=ExecutionDomain.REAL)

    gate_rec = MagicMock()
    gate_rec.reconcile.return_value = rec.reconcile(force=True)
    gate = BootGate(gate_rec)
    report = gate.check()

    assert report.cleared is False


# ── Finding C — raw ledger event must not fabricate price=0.0 ──────────────


def test_c1_raw_jsonl_expired_close_has_null_price(tmp_path, monkeypatch):
    """Fail-before proof: the raw JSONL CLOSE line for an expired_on_restore
    event must contain `"price": null`, never `0.0`."""
    import json

    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="T10",
        symbol="LTC/USDT",
        side="buy",
        price=100.0,
        size_usd=50.0,
        mode="futures_demo",
    )
    recorder.record_close(
        trade_id="T10",
        exit_price=None,
        pnl_usd=None,
        pnl_pct=None,
        reason="expired_on_restore",
        opened_at=time.time() - 100,
        symbol="LTC/USDT",
        side="buy",
        size_usd=50.0,
    )

    lines = log_path.read_text().splitlines()
    close_line = json.loads(lines[1])
    assert close_line["event"] == "CLOSE"
    assert close_line["price"] is None


def test_c2_events_round_trip_preserves_price_none(tmp_path):
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="T11",
        symbol="LTC/USDT",
        side="buy",
        price=100.0,
        size_usd=50.0,
        mode="futures_demo",
    )
    recorder.record_close(
        trade_id="T11",
        exit_price=None,
        pnl_usd=None,
        pnl_pct=None,
        reason="expired_on_restore",
        opened_at=time.time() - 100,
        symbol="LTC/USDT",
        side="buy",
        size_usd=50.0,
    )

    events = PaperTradeRecorder(log_path=str(log_path)).events()
    close_evt = [e for e in events if e.event == "CLOSE"][0]
    assert close_evt.price is None


def test_c3_trades_still_reconstructs_full_unknown_semantics(tmp_path):
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="T12",
        symbol="LTC/USDT",
        side="buy",
        price=100.0,
        size_usd=50.0,
        mode="futures_demo",
    )
    recorder.record_close(
        trade_id="T12",
        exit_price=None,
        pnl_usd=None,
        pnl_pct=None,
        reason="expired_on_restore",
        opened_at=time.time() - 100,
        symbol="LTC/USDT",
        side="buy",
        size_usd=50.0,
    )

    ct = PaperTradeRecorder(log_path=str(log_path)).trades()[0]
    assert ct.exit_price is None
    assert ct.pnl_usd is None
    assert ct.pnl_pct is None
    assert ct.is_win is None


def test_c4_normal_close_with_genuine_price_is_unchanged(tmp_path):
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="T13",
        symbol="LTC/USDT",
        side="buy",
        price=100.0,
        size_usd=50.0,
        mode="futures_demo",
    )
    recorder.record_close(
        trade_id="T13",
        exit_price=105.0,
        pnl_usd=2.5,
        pnl_pct=0.05,
        reason="take_profit",
        opened_at=time.time() - 100,
        symbol="LTC/USDT",
        side="buy",
        size_usd=50.0,
    )

    ct = PaperTradeRecorder(log_path=str(log_path)).trades()[0]
    assert ct.exit_price == 105.0
    assert ct.pnl_usd == 2.5
    assert ct.is_win is True


# ── Finding 4 — fee-entry evidence must not be reported as fully evidenced ──


def test_fee_evidence_incomplete_flagged_on_restored_position_close(
    tmp_path, monkeypatch
):
    """A restored position whose fee_entry_usd evidence was unknown (pre-
    schema-v4 record) must have its eventual realized PnL flagged
    `pnl_fee_evidence_incomplete=True` — the PnL is real arithmetic, but
    must never be indistinguishable from a fully-evidenced trade."""
    from paper_trading.mexc_simulator import MexcSimulator
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="T14",
        symbol="XRP/USDT",
        side="buy",
        price=1.0,
        size_usd=50.0,
        mode="futures_demo",
        # tp_price/sl_price/fee_entry_usd intentionally omitted.
    )

    import paper_trading.recorder as _recorder_mod

    _recorder_mod._recorder = None
    sim = MexcSimulator()
    sim._capital = 100000.0
    sim._initial_capital = 100000.0
    sim._restore_positions()

    pos = sim._positions["XRP/USDT"]
    assert "fee_entry_unknown" in pos.restored_evidence_gaps

    sim._close_position("XRP/USDT", exit_price=1.10, reason="take_profit")

    ct = PaperTradeRecorder(log_path=str(log_path)).trades()[-1]
    assert ct.pnl_usd is not None  # real arithmetic, not fabricated
    assert ct.pnl_fee_evidence_incomplete is True


def test_fee_evidence_complete_when_fee_was_durably_recorded(tmp_path, monkeypatch):
    """Regression: a normal, fully-evidenced position's close must NOT be
    flagged — only genuinely-assumed entry fees are."""
    from paper_trading.mexc_simulator import MexcSimulator
    from paper_trading.recorder import PaperTradeRecorder

    log_path = tmp_path / "paper_trades.jsonl"
    monkeypatch.setenv("PAPER_TRADE_LOG", str(log_path))

    recorder = PaperTradeRecorder(log_path=str(log_path))
    recorder.record_open(
        trade_id="T15",
        symbol="ADA/USDT",
        side="buy",
        price=0.5,
        size_usd=50.0,
        mode="futures_demo",
        tp_price=0.55,
        sl_price=0.47,
        fee_entry_usd=0.05,
    )

    import paper_trading.recorder as _recorder_mod

    _recorder_mod._recorder = None
    sim = MexcSimulator()
    sim._capital = 100000.0
    sim._initial_capital = 100000.0
    sim._restore_positions()

    pos = sim._positions["ADA/USDT"]
    assert pos.restored_evidence_gaps == []

    sim._close_position("ADA/USDT", exit_price=0.55, reason="take_profit")

    ct = PaperTradeRecorder(log_path=str(log_path)).trades()[-1]
    assert ct.pnl_fee_evidence_incomplete is False
