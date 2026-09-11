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
    pm = PositionManager(exchange=object(), domain=ExecutionDomain.REAL)
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
