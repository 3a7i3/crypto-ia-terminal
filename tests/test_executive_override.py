"""
Tests pour ExecutiveOverride — 5 niveaux, transitions, check_trade.
"""

from __future__ import annotations

from quant_hedge_ai.agents.risk.executive_override import (
    ExecutiveOverride,
    OverrideLevel,
)


def _eo(capital: float = 1000.0) -> ExecutiveOverride:
    return ExecutiveOverride(total_capital=capital)


# ── État initial ──────────────────────────────────────────────────────────────


def test_initial_state_is_clear():
    eo = _eo()
    verdict = eo.check_trade(size_usd=55.0)
    assert verdict.level == OverrideLevel.CLEAR
    assert verdict.allowed is True
    assert verdict.size_factor == 1.0


# ── Transitions par drawdown ──────────────────────────────────────────────────


def test_drawdown_3pct_triggers_reduce():
    eo = _eo(capital=1000.0)
    eo.update(capital_current=965.0)  # drawdown = 3.5%
    verdict = eo.check_trade()
    assert verdict.level >= OverrideLevel.REDUCE
    assert verdict.size_factor < 1.0


def test_drawdown_5pct_triggers_careful():
    eo = _eo(capital=1000.0)
    eo.update(capital_current=940.0)  # drawdown = 6%
    verdict = eo.check_trade()
    assert verdict.level >= OverrideLevel.CAREFUL
    assert verdict.size_factor <= 0.25


def test_drawdown_10pct_triggers_veto():
    eo = _eo(capital=1000.0)
    eo.update(capital_current=880.0)  # drawdown = 12%
    verdict = eo.check_trade()
    assert verdict.level == OverrideLevel.VETO
    assert verdict.allowed is False
    assert verdict.size_factor == 0.0


# ── Transitions par loss_streak ───────────────────────────────────────────────


def test_loss_streak_3_triggers_reduce():
    eo = _eo()
    eo.update(loss_streak=3)
    verdict = eo.check_trade()
    assert verdict.level >= OverrideLevel.REDUCE


def test_loss_streak_10_triggers_veto():
    eo = _eo()
    eo.update(loss_streak=10)
    verdict = eo.check_trade()
    assert verdict.level == OverrideLevel.VETO
    assert verdict.allowed is False


# ── VETO → trade impossible ───────────────────────────────────────────────────


def test_veto_blocks_any_size():
    eo = _eo(capital=1000.0)
    eo.update(capital_current=850.0)  # 15% drawdown
    for size in [10.0, 100.0, 1000.0]:
        verdict = eo.check_trade(size_usd=size)
        assert not verdict.allowed, f"VETO doit bloquer size={size}"
        assert verdict.size_factor == 0.0


# ── REDUCE/CAREFUL/MINIMAL — taille réduite mais autorisé ────────────────────


def test_reduce_level_allows_but_reduces_size():
    eo = _eo(capital=1000.0)
    eo.update(capital_current=968.0)  # ~3.2% drawdown → REDUCE
    verdict = eo.check_trade(size_usd=100.0)
    assert verdict.allowed is True
    assert verdict.size_factor == 0.5


def test_careful_level_reduces_to_25pct():
    eo = _eo(capital=1000.0)
    eo.update(capital_current=940.0)  # 6% drawdown → CAREFUL
    verdict = eo.check_trade()
    assert verdict.allowed is True
    assert verdict.size_factor == 0.25


# ── daily_loss threshold ──────────────────────────────────────────────────────


def test_daily_loss_8pct_triggers_veto():
    eo = _eo()
    eo.update(daily_loss_pct=-0.09)  # 9% perte journalière → VETO
    verdict = eo.check_trade()
    assert verdict.level == OverrideLevel.VETO


def test_daily_loss_2pct_triggers_reduce():
    eo = _eo()
    eo.update(daily_loss_pct=-0.025)  # 2.5% → REDUCE
    verdict = eo.check_trade()
    assert verdict.level >= OverrideLevel.REDUCE


# ── record_trade ─────────────────────────────────────────────────────────────


def test_record_trade_increments_trades_today():
    eo = _eo()
    eo.record_trade()
    eo.record_trade()
    assert eo._metrics.trades_today == 2


# ── Verdict fields ────────────────────────────────────────────────────────────


def test_verdict_has_reason_string():
    eo = _eo()
    verdict = eo.check_trade()
    assert isinstance(verdict.reason, str)
    assert len(verdict.reason) > 0


def test_verdict_bool_matches_allowed():
    eo = _eo(capital=1000.0)
    # CLEAR
    v_clear = eo.check_trade()
    assert bool(v_clear) == v_clear.allowed

    # VETO
    eo.update(capital_current=850.0)
    v_veto = eo.check_trade()
    assert bool(v_veto) == v_veto.allowed
    assert bool(v_veto) is False
