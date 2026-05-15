"""
execution_simulator/simulator.py — Compositeur principal du simulateur d'execution.

ExecutionSimulator orchestre dans l'ordre :
  1. FillSimulator  -> filled_size, is_partial
  2. LatencyModel   -> latency_ms, price_after_latency
  3. SlippageModel  -> slippage_bps (calcule sur price_after_latency)
  4. SpreadModel    -> spread_cost_bps
  5. Fees           -> fee_usd, fee_rate_bps

Sortie : SimulatedFill (audit complet + rejection_reason si echec)

Usage minimal :
    from execution_simulator.config import binance_usdt_futures_simulator
    sim = binance_usdt_futures_simulator(seed=42)
    fill = sim.execute(intent, snapshot)
"""

from __future__ import annotations

import random
import uuid

from execution_simulator.fill_simulator import AlwaysFullFill, BaseFillSimulator
from execution_simulator.latency import LatencyModel
from execution_simulator.models import MarketSnapshot, OrderIntent, SimulatedFill
from execution_simulator.slippage import BaseSlippage, FixedSlippage
from execution_simulator.spread import BaseSpread, FixedSpread


class FeeModel:
    """
    Calcule les frais d'execution (maker/taker).

    taker_rate_bps : frais taker en bps (market orders)
    maker_rate_bps : frais maker en bps (limit orders dans le book)
    """

    def __init__(
        self,
        taker_rate_bps: float = 4.0,
        maker_rate_bps: float = 2.0,
    ) -> None:
        if taker_rate_bps < 0:
            raise ValueError(f"taker_rate_bps must be >= 0")
        if maker_rate_bps < 0:
            raise ValueError(f"maker_rate_bps must be >= 0")
        self.taker_rate_bps = taker_rate_bps
        self.maker_rate_bps = maker_rate_bps

    def compute(
        self, intent: OrderIntent, fill_value_usd: float
    ) -> tuple[float, float]:
        """Retourne (fee_usd, fee_rate_bps)."""
        rate = (
            self.maker_rate_bps if intent.order_type == "limit" else self.taker_rate_bps
        )
        fee_usd = fill_value_usd * (rate / 10_000.0)
        return fee_usd, rate


class ExecutionSimulator:
    """
    Simulateur d'execution complet.

    Tous les composants sont injectables pour faciliter les tests et la calibration.
    Le seed controle le RNG partage entre tous les composants — garantit le determinisme.
    """

    def __init__(
        self,
        fill_simulator: BaseFillSimulator,
        latency_model: LatencyModel,
        slippage_model: BaseSlippage,
        spread_model: BaseSpread,
        fee_model: FeeModel,
        seed: int | None = None,
    ) -> None:
        self._fill = fill_simulator
        self._latency = latency_model
        self._slippage = slippage_model
        self._spread = spread_model
        self._fee = fee_model
        self._rng = random.Random(seed)

    def execute(self, intent: OrderIntent, snapshot: MarketSnapshot) -> SimulatedFill:
        """Execute un ordre et retourne le fill simule (audit complet)."""
        order_id = str(uuid.uuid4())[:8]

        # 1. Fill probability
        filled_size, is_partial, rejection_reason = self._fill.simulate(
            intent, snapshot, self._rng
        )
        if rejection_reason is not None:
            return SimulatedFill.rejected(intent, rejection_reason, snapshot.timestamp)

        # 2. Latence + derive de prix
        latency_ms, price_after_latency = self._latency.apply(
            intent, snapshot, self._rng
        )
        drift_bps = self._latency.latency_drift_bps(snapshot.price, price_after_latency)

        # 3. Slippage (calcule sur le prix post-latence)
        slippage_bps = self._slippage.compute(intent, snapshot, self._rng)

        # La direction du slippage depend du sens de l'ordre :
        # buy  -> prix monte  -> slippage positif (achat plus cher)
        # sell -> prix descend -> slippage positif mais dans l'autre sens
        direction_sign = intent.direction  # +1 buy, -1 sell
        fill_price = price_after_latency * (
            1.0 + direction_sign * slippage_bps / 10_000.0
        )

        # 4. Spread
        spread_cost_bps = self._spread.compute(intent, snapshot, self._rng)
        fill_price = fill_price * (1.0 + direction_sign * spread_cost_bps / 10_000.0)

        # 5. Fees
        fill_value_usd = filled_size * fill_price
        fee_usd, fee_rate_bps = self._fee.compute(intent, fill_value_usd)

        return SimulatedFill(
            order_id=order_id,
            symbol=intent.symbol,
            side=intent.side,
            requested_size=intent.size,
            filled_size=filled_size,
            fill_price=fill_price,
            signal_price=intent.signal_price,
            slippage_bps=slippage_bps,
            spread_cost_bps=spread_cost_bps,
            latency_ms=latency_ms,
            fee_usd=fee_usd,
            fee_rate_bps=fee_rate_bps,
            is_partial=is_partial,
            is_rejected=False,
            rejection_reason=None,
            fill_timestamp=snapshot.timestamp + latency_ms / 1000.0,
            price_at_execution=price_after_latency,
            latency_price_drift_bps=drift_bps,
        )

    def reset_rng(self, seed: int | None = None) -> None:
        """Reinitialise le RNG (utile pour rejouer une sequence exacte)."""
        self._rng = random.Random(seed)
