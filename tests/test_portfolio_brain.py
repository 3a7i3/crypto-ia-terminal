"""
Tests pour PortfolioBrain.check_new_trade() — exposition, concentration, régime.
"""

from __future__ import annotations

from quant_hedge_ai.agents.execution.position_manager import Position, PositionSide
from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain, PortfolioVerdict


def _brain(capital: float = 1000.0) -> PortfolioBrain:
    return PortfolioBrain(total_capital=capital)


def _pos(
    symbol: str, size_usd: float, side: str = "long", regime: str = "bull_trend"
) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide.LONG if side == "long" else PositionSide.SHORT,
        entry_price=100.0,
        size_usd=size_usd,
        qty=size_usd / 100.0,
        regime=regime,
    )


# ── Portfolio vide ────────────────────────────────────────────────────────────


def test_empty_portfolio_allows_trade():
    brain = _brain(capital=1000.0)
    verdict = brain.check_new_trade("BTC/USDT", "BUY", 55.0, "bull_trend", [])
    assert verdict.allowed is True
    assert verdict.size_factor > 0.0


def test_empty_portfolio_verdict_bool_true():
    brain = _brain()
    verdict = brain.check_new_trade("BTC/USDT", "BUY", 50.0, "bull_trend", [])
    assert bool(verdict) is True


# ── Exposition totale ─────────────────────────────────────────────────────────


def test_total_exposure_exceeded_blocks_trade():
    brain = _brain(capital=1000.0)
    # 3 positions de 150 USD = 450 USD = 45% du capital (> MAX 40%)
    open_pos = [
        _pos("BTC/USDT", 150.0),
        _pos("ETH/USDT", 150.0),
        _pos("SOL/USDT", 150.0),
    ]
    verdict = brain.check_new_trade("XRP/USDT", "BUY", 100.0, "bull_trend", open_pos)
    assert verdict.allowed is False
    assert "exposition" in verdict.reason.lower()


def test_exposure_within_limit_allowed():
    brain = _brain(capital=1000.0)
    open_pos = [_pos("BTC/USDT", 50.0)]  # 5% exposé
    verdict = brain.check_new_trade("ETH/USDT", "BUY", 50.0, "bull_trend", open_pos)
    assert verdict.allowed is True


# ── Concentration sur un actif ────────────────────────────────────────────────


def test_single_symbol_concentration_reduces_size():
    brain = _brain(capital=1000.0)
    # Déjà 200 USD sur BTC = 20% → tenter 100 USD de plus = 30%
    # Overshoot de 10pp → size_factor réduit à 0 (soft block)
    open_pos = [_pos("BTC/USDT", 200.0)]
    verdict = brain.check_new_trade("BTC/USDT", "BUY", 100.0, "bull_trend", open_pos)
    assert (
        verdict.size_factor == 0.0
    ), f"Concentration doit réduire factor à 0: {verdict}"
    assert (
        "BTC/USDT" in verdict.reason
        or "concentration" in verdict.reason.lower()
        or verdict.warnings
    )


def test_different_symbols_allowed():
    brain = _brain(capital=1000.0)
    open_pos = [_pos("BTC/USDT", 150.0)]  # 15% BTC
    verdict = brain.check_new_trade("ETH/USDT", "BUY", 50.0, "bull_trend", open_pos)
    assert verdict.allowed is True


# ── Nombre max de positions ───────────────────────────────────────────────────


def test_max_positions_exceeded_blocks_trade():
    brain = _brain(capital=10000.0)  # capital élevé pour éviter exposition block
    open_pos = [_pos(f"TOKEN{i}/USDT", 100.0) for i in range(5)]  # MAX_POSITIONS = 5
    verdict = brain.check_new_trade("NEW/USDT", "BUY", 50.0, "bull_trend", open_pos)
    assert verdict.allowed is False


def test_below_max_positions_allowed():
    brain = _brain(capital=10000.0)
    open_pos = [_pos(f"TOKEN{i}/USDT", 100.0) for i in range(3)]
    verdict = brain.check_new_trade("NEW/USDT", "BUY", 50.0, "bull_trend", open_pos)
    assert verdict.allowed is True


# ── PortfolioVerdict ──────────────────────────────────────────────────────────


def test_verdict_bool_false_when_not_allowed():
    verdict = PortfolioVerdict(
        allowed=False, reason="test", size_factor=0.0, capital_available=0.0
    )
    assert bool(verdict) is False


def test_verdict_bool_true_when_allowed():
    verdict = PortfolioVerdict(
        allowed=True, reason="ok", size_factor=1.0, capital_available=100.0
    )
    assert bool(verdict) is True


# ── update_capital ────────────────────────────────────────────────────────────


def test_update_capital_changes_limits():
    brain = _brain(capital=100.0)  # petit capital
    # 50 USD = 50% du capital → dépasse la limite 40%
    v_small = brain.check_new_trade("BTC/USDT", "BUY", 50.0, "bull_trend", [])

    brain.update_capital(10000.0)  # grand capital
    v_big = brain.check_new_trade("BTC/USDT", "BUY", 50.0, "bull_trend", [])

    # Avec un grand capital, le même trade devrait être plus facilement autorisé
    if not v_small.allowed:
        assert v_big.allowed is True
