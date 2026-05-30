"""
Tests pour CapitalAllocationEngine.allocate() — sizing, Kelly, régimes, vol.
"""

from __future__ import annotations

from quant_hedge_ai.agents.risk.capital_allocation_engine import (
    AllocationResult,
    CapitalAllocationEngine,
)


def _engine(capital: float = 1000.0) -> CapitalAllocationEngine:
    return CapitalAllocationEngine(total_capital=capital)


def _good_params(**overrides) -> dict:
    base = {
        "base_size_usd": 55.0,
        "win_rate": 0.55,
        "avg_win_pct": 0.04,
        "avg_loss_pct": 0.02,
        "volatility": 0.015,
        "conviction_factor": 1.0,
        "regime": "bull_trend",
        "leverage": 1,
        "n_trades_history": 20,
    }
    base.update(overrides)
    return base


# ── Régimes ───────────────────────────────────────────────────────────────────


def test_flash_crash_regime_returns_zero():
    cae = _engine()
    result = cae.allocate(**_good_params(regime="flash_crash"))
    assert result.size_usd == 0.0
    assert not bool(result)
    assert "flash_crash" in result.reason.lower() or "aucun" in result.reason.lower()


def test_bull_trend_allows_full_allocation():
    cae = _engine(capital=1000.0)
    result = cae.allocate(**_good_params(regime="bull_trend"))
    assert result.size_usd > 0.0
    assert bool(result)


def test_high_volatility_regime_reduces_cap():
    cae = _engine(capital=1000.0)
    result_bull = cae.allocate(**_good_params(regime="bull_trend"))
    result_hvol = cae.allocate(**_good_params(regime="high_volatility_regime"))
    assert result_hvol.size_usd <= result_bull.size_usd


def test_unknown_regime_uses_conservative_cap():
    cae = _engine(capital=1000.0)
    result = cae.allocate(**_good_params(regime="unknown"))
    assert result.size_usd > 0.0
    assert result.factors.get("regime_cap", 1.0) == 0.50


# ── Kelly fraction ────────────────────────────────────────────────────────────


def test_insufficient_history_uses_conservative_mode():
    cae = _engine()
    # n_trades_history=0 → mode conservateur : kelly fixe à 0.08 (fallback)
    result = cae.allocate(**_good_params(n_trades_history=0))
    assert result.size_usd > 0.0
    assert (
        result.kelly_fraction == 0.08
    )  # Kelly conservateur fixe (pas de calcul Kelly)


def test_sufficient_history_activates_kelly():
    cae = _engine()
    result = cae.allocate(**_good_params(n_trades_history=20))
    assert result.kelly_fraction > 0.0


def test_negative_ev_with_history_returns_zero_or_low():
    # win_rate faible, avg_loss > avg_win → EV négatif → Kelly = 0
    cae = _engine()
    result = cae.allocate(
        **_good_params(
            win_rate=0.3,
            avg_win_pct=0.01,
            avg_loss_pct=0.05,
            n_trades_history=20,
        )
    )
    assert result.size_usd == 0.0 or result.kelly_fraction == 0.0


# ── Volatilité ────────────────────────────────────────────────────────────────


def test_high_volatility_reduces_size():
    cae = _engine()
    result_low_vol = cae.allocate(**_good_params(volatility=0.01))
    result_high_vol = cae.allocate(**_good_params(volatility=0.10))
    assert result_high_vol.size_usd <= result_low_vol.size_usd


# ── Conviction factor ─────────────────────────────────────────────────────────


def test_low_conviction_reduces_size():
    cae = _engine()
    result_high = cae.allocate(**_good_params(conviction_factor=1.5))
    result_low = cae.allocate(**_good_params(conviction_factor=0.2))
    assert result_low.size_usd <= result_high.size_usd


# ── AllocationResult ─────────────────────────────────────────────────────────


def test_allocation_result_bool_true_when_size_positive():
    result = AllocationResult(size_usd=55.0, leverage=1.0, reason="ok")
    assert bool(result) is True


def test_allocation_result_bool_false_when_zero():
    result = AllocationResult(size_usd=0.0, leverage=0.0, reason="blocked")
    assert bool(result) is False


def test_update_capital_updates_internal_capital():
    cae = _engine(capital=500.0)
    cae.update_capital(2000.0)
    result = cae.allocate(**_good_params(base_size_usd=100.0, n_trades_history=0))
    # Capital plus grand → allocation potentiellement plus haute
    assert result.size_usd >= 0.0


def test_leverage_capped_at_max():
    cae = _engine()
    result = cae.allocate(**_good_params(leverage=10))
    assert result.leverage <= cae.LEVERAGE_MAX
