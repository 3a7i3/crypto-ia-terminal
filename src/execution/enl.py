"""
Execution Noise Layer (ENL) — simule les frictions réelles d'exécution.

Wrapping de VirtualExchange avec la même interface.
Se branche dans ExecutionRouter.sim_engine sans modifier le reste.

Frictions modélisées :
  spread   : coût bid/ask (en basis points)
  slippage : bruit d'exécution proportionnel à la volatilité
  fill_rate: fraction de l'ordre réellement exécutée (liquidité)
"""

import random
from dataclasses import dataclass

from src.domain.order import Order
from src.domain.position import Position


@dataclass
class ENLConfig:
    spread_bps: float = 10.0  # spread bid/ask en basis points (10bps = 0.10%)
    slippage_sigma: float = 0.001  # écart-type du slippage (0.1% = 0.001)
    fill_rate: float = 1.0  # 1.0 = fill complet, 0.9 = 90% de la taille
    seed: int | None = None  # None = aléatoire, int = reproductible

    # Presets lisibles
    @classmethod
    def clean(cls) -> "ENLConfig":
        return cls(spread_bps=0.0, slippage_sigma=0.0, fill_rate=1.0)

    @classmethod
    def light(cls) -> "ENLConfig":
        return cls(spread_bps=5.0, slippage_sigma=0.001, fill_rate=1.0)

    @classmethod
    def realistic(cls) -> "ENLConfig":
        return cls(spread_bps=10.0, slippage_sigma=0.002, fill_rate=0.99)

    @classmethod
    def heavy(cls) -> "ENLConfig":
        return cls(spread_bps=20.0, slippage_sigma=0.004, fill_rate=0.97)


class NoisyExchange:
    """
    Wrapper de VirtualExchange qui applique les frictions ENL avant chaque fill.
    Même interface que VirtualExchange : place_order / close_position.
    """

    def __init__(self, exchange, config: ENLConfig | None = None):
        self._exchange = exchange
        self._cfg = config or ENLConfig.realistic()
        self._rng = random.Random(self._cfg.seed)

        # Statistiques de friction (audit)
        self.total_spread_cost: float = 0.0
        self.total_slippage_cost: float = 0.0
        self.rejected_fills: int = 0

    # -- Délégation du portfolio --
    @property
    def portfolio(self):
        return self._exchange.portfolio

    # ------------------------------------------------------------------ #
    # Interface VirtualExchange                                             #
    # ------------------------------------------------------------------ #

    def place_order(self, order: Order, price: float) -> Position | None:
        adj_size = order.size * self._cfg.fill_rate
        if adj_size < 1e-8:
            self.rejected_fills += 1
            return None

        adj_price = self._fill_price(order.side, price)

        adj_order = Order(
            symbol=order.symbol,
            side=order.side,
            size=adj_size,
            id=order.id,
            metadata=order.metadata,
        )
        return self._exchange.place_order(adj_order, adj_price)

    def close_position(
        self, symbol: str, price: float, metadata: dict | None = None
    ) -> dict:
        position = self._exchange.portfolio.positions.get(symbol)
        if position is None:
            return self._exchange.close_position(symbol, price, metadata)

        # Clôturer un long = vendre (friction négative)
        # Clôturer un short = acheter (friction positive)
        close_side = "sell" if position.side == "long" else "buy"
        adj_price = self._fill_price(close_side, price)
        return self._exchange.close_position(symbol, adj_price, metadata)

    # ------------------------------------------------------------------ #
    # Modèle de prix                                                        #
    # ------------------------------------------------------------------ #

    def _fill_price(self, side: str, price: float) -> float:
        # Spread : moitié du spread total par côté
        half_spread = price * (self._cfg.spread_bps / 10_000) / 2

        # Slippage : bruit gaussien unilatéral (toujours défavorable)
        slip = abs(self._rng.gauss(0, price * self._cfg.slippage_sigma))

        spread_cost = half_spread
        slip_cost = slip

        if side == "buy":
            adj = price + spread_cost + slip_cost
        else:
            adj = price - spread_cost - slip_cost

        self.total_spread_cost += spread_cost
        self.total_slippage_cost += slip_cost

        return max(1e-8, adj)

    def friction_report(self) -> dict:
        return {
            "total_spread_cost": round(self.total_spread_cost, 4),
            "total_slippage_cost": round(self.total_slippage_cost, 4),
            "rejected_fills": self.rejected_fills,
        }
