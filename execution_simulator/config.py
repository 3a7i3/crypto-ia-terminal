"""
execution_simulator/config.py — Presets de simulateurs preconfigures.

Fonctions factory qui retournent un ExecutionSimulator pret a l'emploi.

mexc_futures_simulator(seed) : preset MEXC Futures/Perp
  - SqrtSlippage  (Almgren-Chriss, eta=0.1, noise=0.5 bps)
  - LatencyModel  (base=50ms, jitter=20ms)
  - DynamicSpread (base=0.5 bps, vol-sensitive)
  - LiquidityBasedFill (max 5% ADV, decay exp)
  - FeeModel      (taker=4 bps, maker=2 bps)

mexc_spot_simulator(seed) : preset MEXC Spot
  - Memes modeles mais fees differentes (taker=10 bps, maker=10 bps standard)
  - Spread legerement plus large

conservative_simulator(seed) : preset pessimiste pour stress-test
  - Slippage fixe 5 bps
  - Latence elevee (base=200ms)
  - Spread 3 bps
  - Fill partiel agressif (max 2% ADV)

Alias de compatibilite : binance_usdt_futures_simulator, binance_spot_simulator.
"""

from __future__ import annotations

from execution_simulator.fill_simulator import AlwaysFullFill, LiquidityBasedFill
from execution_simulator.latency import LatencyModel
from execution_simulator.simulator import ExecutionSimulator, FeeModel
from execution_simulator.slippage import FixedSlippage, SqrtSlippage
from execution_simulator.spread import DynamicSpread, FixedSpread


def mexc_futures_simulator(seed: int | None = None) -> ExecutionSimulator:
    """Preset MEXC Futures/Perp — parametres calibres sur donnees reelles."""
    return ExecutionSimulator(
        fill_simulator=LiquidityBasedFill(
            max_participation=0.05,
            fill_decay_factor=10.0,
            min_fill_ratio=0.01,
            limit_fill_prob=0.70,
            vol_limit_penalty=0.02,
        ),
        latency_model=LatencyModel(
            base_ms=50.0,
            jitter_ms=20.0,
            max_ms=500.0,
            drift_factor=1.0,
        ),
        slippage_model=SqrtSlippage(
            eta=0.10,
            noise_bps=0.5,
        ),
        spread_model=DynamicSpread(
            base_bps=0.5,
            vol_multiplier=0.10,
            noise_bps=0.2,
        ),
        fee_model=FeeModel(
            taker_rate_bps=4.0,
            maker_rate_bps=2.0,
        ),
        seed=seed,
    )


def mexc_spot_simulator(seed: int | None = None) -> ExecutionSimulator:
    """Preset MEXC Spot — frais standard, spread un peu plus large."""
    return ExecutionSimulator(
        fill_simulator=LiquidityBasedFill(
            max_participation=0.03,
            fill_decay_factor=8.0,
            min_fill_ratio=0.01,
            limit_fill_prob=0.65,
            vol_limit_penalty=0.025,
        ),
        latency_model=LatencyModel(
            base_ms=60.0,
            jitter_ms=25.0,
            max_ms=600.0,
            drift_factor=1.0,
        ),
        slippage_model=SqrtSlippage(
            eta=0.12,
            noise_bps=0.6,
        ),
        spread_model=DynamicSpread(
            base_bps=0.8,
            vol_multiplier=0.12,
            noise_bps=0.3,
        ),
        fee_model=FeeModel(
            taker_rate_bps=10.0,
            maker_rate_bps=10.0,
        ),
        seed=seed,
    )


def conservative_simulator(seed: int | None = None) -> ExecutionSimulator:
    """Preset pessimiste pour stress-test et scenarii adverses."""
    return ExecutionSimulator(
        fill_simulator=LiquidityBasedFill(
            max_participation=0.02,
            fill_decay_factor=15.0,
            min_fill_ratio=0.05,
            limit_fill_prob=0.50,
            vol_limit_penalty=0.05,
        ),
        latency_model=LatencyModel(
            base_ms=200.0,
            jitter_ms=80.0,
            max_ms=2000.0,
            drift_factor=1.5,
        ),
        slippage_model=FixedSlippage(bps=5.0),
        spread_model=FixedSpread(bps=3.0),
        fee_model=FeeModel(
            taker_rate_bps=6.0,
            maker_rate_bps=4.0,
        ),
        seed=seed,
    )


# Aliases de compatibilite ascendante
binance_usdt_futures_simulator = mexc_futures_simulator
binance_spot_simulator = mexc_spot_simulator
