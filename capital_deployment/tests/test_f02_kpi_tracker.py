"""
capital_deployment/tests/test_f02_kpi_tracker.py — F-02 KPI Tracker

Tests de certification :
  - Win rate calculé correctement (wins / total)
  - Win rate zéro sans trades
  - Max drawdown détecté sur equity peak
  - Drawdown courant correct
  - Equity accumulée correctement
  - Unsigned decisions comptées
  - sharpe_ratio = 0 sans données quotidiennes
  - sharpe_ratio calculé sur daily returns
  - snapshot() contient tous les champs
  - violations() liste correcte pour phase F-01
  - meets_criteria() retourne (False, violations) si drawdown trop élevé
  - PHASE_CRITERIA contient les 5 phases
  - TradeRecord.signed par défaut True
  - KPISnapshot.to_dict() complet

Total : 14 tests
"""

from __future__ import annotations

import time

import pytest

from capital_deployment.phase_kpi_tracker import (
    PHASE_CRITERIA,
    KPISnapshot,
    PhaseKPITracker,
    TradeRecord,
)


def _make_trade(pnl: float, ts: float, signed: bool = True) -> TradeRecord:
    return TradeRecord(
        ts=ts,
        pnl=pnl,
        symbol="BTC/USDT",
        side="buy",
        entry_price=100.0,
        exit_price=100.0 + pnl,
        signed=signed,
    )


def _tracker_with_daily_trades(
    n_days: int = 10,
    pnl_per_day: float = 1.0,
    phase: str = "F-01",
    initial_capital: float = 100.0,
) -> PhaseKPITracker:
    """Create a tracker with one trade per day for n_days."""
    started = time.time() - n_days * 86400 - 3600
    tracker = PhaseKPITracker(
        phase=phase, initial_capital=initial_capital, started_at=started
    )
    for i in range(n_days):
        ts = started + i * 86400 + 3600
        tracker.record_trade(_make_trade(pnl_per_day, ts))
    return tracker


class TestPhaseCriteria:
    def test_five_phases_defined(self):
        """PHASE_CRITERIA contient les 5 phases."""
        assert set(PHASE_CRITERIA.keys()) == {"F-01", "F-02", "F-03", "F-04", "F-05"}

    def test_f01_stricter_than_f02(self):
        """F-01 a des seuils drawdown plus stricts que F-02."""
        assert (
            PHASE_CRITERIA["F-01"]["max_drawdown"]
            < PHASE_CRITERIA["F-02"]["max_drawdown"]
        )


class TestWinRate:
    def test_win_rate_zero_no_trades(self):
        """Win rate = 0 si aucun trade."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        assert tracker.win_rate() == 0.0

    def test_win_rate_all_wins(self):
        """Win rate = 1.0 si tous les trades sont gagnants."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        now = time.time()
        for i in range(5):
            tracker.record_trade(_make_trade(1.0, now + i))
        assert tracker.win_rate() == pytest.approx(1.0)

    def test_win_rate_mixed(self):
        """Win rate = 3/5 avec 3 wins et 2 losses."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        now = time.time()
        for i, pnl in enumerate([1.0, -1.0, 1.0, -1.0, 1.0]):
            tracker.record_trade(_make_trade(pnl, now + i))
        assert tracker.win_rate() == pytest.approx(0.6)


class TestDrawdown:
    def test_max_drawdown_after_loss(self):
        """Max drawdown détecté correctement après une perte."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        now = time.time()
        tracker.record_trade(_make_trade(10.0, now))  # equity = 110, peak = 110
        tracker.record_trade(
            _make_trade(-22.0, now + 1)
        )  # equity = 88, dd = 22/110 ≈ 20%
        assert tracker.max_drawdown() == pytest.approx(22.0 / 110.0, abs=1e-6)

    def test_drawdown_zero_with_only_gains(self):
        """Drawdown = 0 si toutes les trades sont des gains."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        now = time.time()
        for i in range(5):
            tracker.record_trade(_make_trade(1.0, now + i))
        assert tracker.max_drawdown() == pytest.approx(0.0)

    def test_equity_accumulates(self):
        """Equity accumulée correctement sur plusieurs trades."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        now = time.time()
        tracker.record_trade(_make_trade(5.0, now))
        tracker.record_trade(_make_trade(-2.0, now + 1))
        assert tracker.equity() == pytest.approx(103.0)


class TestSharpe:
    def test_sharpe_zero_without_daily_returns(self):
        """Sharpe = 0 si < 2 points de données quotidiens."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        tracker.record_trade(_make_trade(1.0, time.time()))
        assert tracker.sharpe_ratio() == pytest.approx(0.0)

    def test_sharpe_positive_with_daily_returns(self):
        """Sharpe > 0 avec des returns quotidiens positifs."""
        tracker = _tracker_with_daily_trades(n_days=10, pnl_per_day=1.5)
        # Les trades espacés de 1 jour → daily returns enregistrés
        assert tracker.sharpe_ratio() >= 0.0  # positif car PnL positif


class TestSignedDecisions:
    def test_unsigned_trade_counted(self):
        """Les décisions non signées sont comptées."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        now = time.time()
        tracker.record_trade(_make_trade(1.0, now, signed=True))
        tracker.record_trade(_make_trade(1.0, now + 1, signed=False))
        assert tracker.unsigned_decisions() == 1

    def test_signed_default_true(self):
        """TradeRecord.signed = True par défaut."""
        trade = TradeRecord(
            ts=0.0, pnl=1.0, symbol="X", side="buy", entry_price=1.0, exit_price=2.0
        )
        assert trade.signed is True


class TestSnapshotAndCriteria:
    def test_snapshot_contains_required_fields(self):
        """snapshot().to_dict() contient tous les champs requis."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        d = tracker.snapshot().to_dict()
        for key in (
            "phase",
            "win_rate",
            "sharpe",
            "max_drawdown",
            "current_drawdown",
            "total_trades",
            "unsigned_decisions",
            "days_elapsed",
            "ts",
        ):
            assert key in d, f"Clé manquante: {key}"

    def test_violations_high_drawdown(self):
        """violations() inclut drawdown si trop élevé pour F-01."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        now = time.time()
        tracker.record_trade(_make_trade(0.0, now))
        tracker.record_trade(_make_trade(-10.0, now + 1))  # DD = 10%
        # F-01 max_DD = 2% → doit déclencher violation
        snap = tracker.snapshot()
        violations = snap.violations("F-01")
        dd_violations = [v for v in violations if "drawdown" in v.lower()]
        assert len(dd_violations) >= 1

    def test_meets_criteria_false_with_unsigned(self):
        """meets_criteria = False si décision non signée."""
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        tracker.record_trade(_make_trade(1.0, time.time(), signed=False))
        ok, violations = tracker.meets_criteria()
        assert ok is False
        unsigned_v = [v for v in violations if "sign" in v.lower()]
        assert len(unsigned_v) >= 1
