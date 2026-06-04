"""Tests Paper Arena V1 — ETH 4h RSI 15/85.

Protège : calcul PnL, friction ENL, métriques, gate statistique, sérialisation.
"""

import math

import pytest

from src.paper.paper_gate import MAX_DD_PCT, MIN_TRADES, gate_passed, gate_status
from src.paper.paper_metrics import PaperMetrics
from src.paper.paper_position_manager import MEXC_FEE_RATE, PaperPositionManager
from src.paper.paper_report import notify_entry, notify_exit, notify_summary
from src.paper.paper_runner import _enl_fill

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def empty_metrics():
    return PaperMetrics(initial_equity=10_000.0, equity=10_000.0, peak_equity=10_000.0)


@pytest.fixture
def mgr():
    return PaperPositionManager()


def _winning_metrics(n: int = MIN_TRADES) -> PaperMetrics:
    """Métriques avec n trades gagnants — passe toutes les gates."""
    m = PaperMetrics(initial_equity=10_000.0, equity=10_000.0, peak_equity=10_000.0)
    for _ in range(n):
        m.record_trade(pnl_net=100.0, enl_cost=2.0, hold_seconds=14_400.0)
    return m


# ── 1. Ouverture de position ───────────────────────────────────────────────────


def test_open_position_sets_state(mgr):
    assert not mgr.in_position
    mgr.open("ETHUSDT", "LONG", 4_000.0, 1_000.0, rsi=14.2)
    assert mgr.in_position
    pos = mgr.position
    assert pos.symbol == "ETHUSDT"
    assert pos.side == "LONG"
    assert pos.entry_price == 4_000.0
    assert pos.size_usdt == 1_000.0
    assert pos.entry_rsi == pytest.approx(14.2)


def test_double_open_raises(mgr):
    mgr.open("ETHUSDT", "LONG", 4_000.0, 1_000.0, rsi=14.0)
    with pytest.raises(RuntimeError):
        mgr.open("ETHUSDT", "LONG", 4_100.0, 1_000.0, rsi=13.0)


# ── 2. Fermeture et PnL ───────────────────────────────────────────────────────


def test_close_long_profitable(mgr):
    mgr.open("ETHUSDT", "LONG", 4_000.0, 1_000.0, rsi=14.0)
    _pos, pnl_net, fee, hold_s = mgr.close(exit_price=4_200.0)
    qty = 1_000.0 / 4_000.0
    expected_gross = (4_200.0 - 4_000.0) * qty
    expected_fee = 1_000.0 * MEXC_FEE_RATE * 2
    assert pnl_net == pytest.approx(expected_gross - expected_fee, rel=1e-6)
    assert pnl_net > 0
    assert not mgr.in_position


def test_close_long_losing(mgr):
    mgr.open("ETHUSDT", "LONG", 4_000.0, 1_000.0, rsi=14.0)
    _pos, pnl_net, _fee, _hold = mgr.close(exit_price=3_800.0)
    assert pnl_net < 0


def test_close_short_profitable(mgr):
    mgr.open("ETHUSDT", "SHORT", 4_000.0, 1_000.0, rsi=86.0)
    _pos, pnl_net, _fee, _hold = mgr.close(exit_price=3_800.0)
    assert pnl_net > 0


def test_close_applies_double_fee(mgr):
    mgr.open("ETHUSDT", "LONG", 4_000.0, 1_000.0, rsi=14.0)
    _pos, pnl_net, fee, _hold = mgr.close(
        exit_price=4_000.0
    )  # prix identique → seul la fee
    expected_fee = 1_000.0 * MEXC_FEE_RATE * 2
    assert fee == pytest.approx(expected_fee, rel=1e-9)
    assert pnl_net == pytest.approx(-expected_fee, rel=1e-9)


def test_close_without_open_raises(mgr):
    with pytest.raises(RuntimeError):
        mgr.close(exit_price=4_000.0)


# ── 3. Métriques ──────────────────────────────────────────────────────────────


def test_record_trade_updates_equity(empty_metrics):
    m = empty_metrics
    m.record_trade(pnl_net=200.0, enl_cost=3.0, hold_seconds=7_200.0)
    assert m.equity == pytest.approx(10_200.0)
    assert m.trade_count == 1


def test_record_loss_updates_equity(empty_metrics):
    m = empty_metrics
    m.record_trade(pnl_net=-150.0, enl_cost=3.0, hold_seconds=3_600.0)
    assert m.equity == pytest.approx(9_850.0)


def test_max_drawdown_after_loss(empty_metrics):
    m = empty_metrics
    m.record_trade(pnl_net=500.0, enl_cost=1.0, hold_seconds=3_600.0)  # peak=10500
    m.record_trade(pnl_net=-1_050.0, enl_cost=1.0, hold_seconds=3_600.0)  # equity=9450
    dd = m.max_drawdown_pct
    assert dd == pytest.approx(10.0, rel=1e-3)


def test_profit_factor_only_wins(empty_metrics):
    m = empty_metrics
    for _ in range(5):
        m.record_trade(100.0, 1.0, 3_600.0)
    assert m.profit_factor == math.inf


def test_profit_factor_mixed(empty_metrics):
    m = empty_metrics
    for _ in range(3):
        m.record_trade(100.0, 1.0, 3_600.0)  # 300 gross win
    m.record_trade(-100.0, 1.0, 3_600.0)  # 100 gross loss
    assert m.profit_factor == pytest.approx(3.0, rel=1e-6)


def test_win_rate(empty_metrics):
    m = empty_metrics
    m.record_trade(100.0, 1.0, 3_600.0)
    m.record_trade(-50.0, 1.0, 3_600.0)
    assert m.win_rate == pytest.approx(0.5)


def test_avg_hold_hours(empty_metrics):
    m = empty_metrics
    m.record_trade(0.0, 0.0, 7_200.0)  # 2h
    m.record_trade(0.0, 0.0, 14_400.0)  # 4h
    assert m.avg_hold_hours == pytest.approx(3.0)


# ── 4. Friction ENL ───────────────────────────────────────────────────────────


def test_enl_buy_raises_price():
    exec_price, friction = _enl_fill(4_000.0, "buy")
    assert exec_price > 4_000.0
    assert friction > 0.0


def test_enl_sell_lowers_price():
    exec_price, friction = _enl_fill(4_000.0, "sell")
    assert exec_price < 4_000.0
    assert friction > 0.0


def test_enl_friction_nonzero_over_many_calls():
    total_friction = sum(_enl_fill(4_000.0, "buy")[1] for _ in range(100))
    assert total_friction > 0.0


def test_enl_exec_price_positive():
    for side in ("buy", "sell"):
        exec_price, _ = _enl_fill(1.0, side)
        assert exec_price > 0.0


# ── 5. Gate statistique ───────────────────────────────────────────────────────


def test_gate_blocked_insufficient_trades():
    m = _winning_metrics(MIN_TRADES - 1)
    assert not gate_passed(m)


def test_gate_passes_at_min_trades():
    m = _winning_metrics(MIN_TRADES)
    assert gate_passed(m)


def test_gate_blocked_low_pf():
    m = _winning_metrics(MIN_TRADES)
    # Ajouter des pertes pour faire chuter le PF sous MIN_PF
    for _ in range(MIN_TRADES * 10):
        m.record_trade(-50.0, 1.0, 3_600.0)
    assert not gate_passed(m)


def test_gate_blocked_negative_expectancy():
    m = PaperMetrics(initial_equity=10_000.0, equity=10_000.0, peak_equity=10_000.0)
    for _ in range(MIN_TRADES):
        m.record_trade(-10.0, 1.0, 3_600.0)
    assert not gate_passed(m)


def test_gate_blocked_high_drawdown():
    m = PaperMetrics(initial_equity=10_000.0, equity=10_000.0, peak_equity=10_000.0)
    for _ in range(MIN_TRADES):
        m.record_trade(1.0, 0.0, 3_600.0)  # small wins → peak monte
    m.record_trade(-m.equity * (MAX_DD_PCT / 100 + 0.05), 0.0, 3_600.0)  # DD > seuil
    assert not gate_passed(m)


def test_gate_status_contains_all_criteria():
    m = _winning_metrics(MIN_TRADES)
    status = gate_status(m)
    assert "trades" in status
    assert "PF" in status
    assert "expectancy" in status
    assert "maxDD" in status


def test_gate_status_shows_pass_symbols():
    m = _winning_metrics(MIN_TRADES)
    status = gate_status(m)
    assert "✓" in status


def test_gate_status_shows_fail_symbols():
    m = PaperMetrics(initial_equity=10_000.0, equity=10_000.0, peak_equity=10_000.0)
    status = gate_status(m)
    assert "✗" in status


# ── 6. Rapport Telegram (sans envoi réseau) ───────────────────────────────────


def test_notify_entry_no_crash_without_token(empty_metrics):
    # Sans PAPER_ARENA_TG_TOKEN configuré → doit se terminer sans exception
    notify_entry("ETHUSDT", "LONG", 4_215.22, 1_000.0, 14.3, empty_metrics)


def test_notify_exit_no_crash_without_token(empty_metrics):
    notify_exit("ETHUSDT", 4_215.22, 4_292.44, 77.22, run=1, metrics=empty_metrics)


def test_notify_summary_no_crash_without_token(empty_metrics):
    notify_summary(empty_metrics)


# ── 7. Sérialisation / Recovery ───────────────────────────────────────────────


def test_position_manager_round_trip_no_position():
    mgr = PaperPositionManager()
    d = mgr.to_dict()
    assert d is None
    restored = PaperPositionManager.from_dict(d)
    assert not restored.in_position


def test_position_manager_round_trip_with_position():
    mgr = PaperPositionManager()
    mgr.open("ETHUSDT", "LONG", 4_000.0, 1_000.0, rsi=14.2)
    d = mgr.to_dict()
    assert d is not None
    restored = PaperPositionManager.from_dict(d)
    assert restored.in_position
    pos = restored.position
    assert pos.symbol == "ETHUSDT"
    assert pos.side == "LONG"
    assert pos.entry_price == pytest.approx(4_000.0)
    assert pos.size_usdt == pytest.approx(1_000.0)
    assert pos.entry_rsi == pytest.approx(14.2)


def test_metrics_round_trip_empty(empty_metrics):
    d = empty_metrics.to_dict()
    restored = PaperMetrics.from_dict(d)
    assert restored.equity == pytest.approx(empty_metrics.equity)
    assert restored.trade_count == 0


def test_metrics_round_trip_with_trades(empty_metrics):
    m = empty_metrics
    m.record_trade(200.0, 2.5, 14_400.0)
    m.record_trade(-80.0, 2.0, 7_200.0)
    d = m.to_dict()
    restored = PaperMetrics.from_dict(d)
    assert restored.equity == pytest.approx(m.equity)
    assert restored.trade_count == 2
    assert restored.profit_factor == pytest.approx(m.profit_factor)
    assert restored.signal_count == m.signal_count


def test_recovery_preserves_open_position():
    """Simule un redémarrage avec une position déjà ouverte."""
    mgr = PaperPositionManager()
    mgr.open("ETHUSDT", "LONG", 4_100.0, 1_000.0, rsi=13.5)

    # Sérialise (snapshot avant redémarrage)
    snapshot = mgr.to_dict()

    # Redémarrage : recrée le manager depuis le snapshot
    mgr_restarted = PaperPositionManager.from_dict(snapshot)

    assert mgr_restarted.in_position
    assert mgr_restarted.position.entry_price == pytest.approx(4_100.0)
    assert mgr_restarted.position.side == "LONG"


def test_recovery_preserves_metrics_history():
    """Simule un redémarrage avec historique de trades."""
    m = PaperMetrics(initial_equity=10_000.0, equity=10_000.0, peak_equity=10_000.0)
    for _ in range(15):
        m.record_trade(50.0, 1.0, 3_600.0)
    m.signal_count = 42

    snapshot = m.to_dict()
    m_restarted = PaperMetrics.from_dict(snapshot)

    assert m_restarted.trade_count == 15
    assert m_restarted.equity == pytest.approx(m.equity)
    assert m_restarted.signal_count == 42
    assert m_restarted.profit_factor == m.profit_factor
