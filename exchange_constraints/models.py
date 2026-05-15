"""
exchange_constraints/models.py — Dataclasses pour les contraintes d'exchange.

SymbolInfo       : regles de precision + limites + filtres Binance complets
ValidationResult : resultat d'une validation (accept/reject + ajustements + warnings)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SymbolInfo:
    """
    Regles completes d'un symbole Binance USDT-M Futures.

    Filtres Binance couverts :
      LOT_SIZE        -> step_size, min_qty, max_qty
      PRICE_FILTER    -> tick_size
      MIN_NOTIONAL    -> min_notional
      PERCENT_PRICE   -> percent_price_up, percent_price_down
      MARKET_LOT_SIZE -> market_step_size, market_min_qty, market_max_qty
    """

    symbol: str
    base_asset: str
    quote_asset: str

    # LOT_SIZE (pour limit orders)
    step_size: float  # ex: 0.001 pour BTC
    min_qty: float  # ex: 0.001
    max_qty: float  # ex: 1000.0

    # PRICE_FILTER
    tick_size: float  # ex: 0.10 pour BTC/USDT

    # MIN_NOTIONAL
    min_notional: float  # ex: 5.0 USDT

    # PERCENT_PRICE — filtres sur la deviation par rapport au mark price
    # prix_ordre doit etre dans [mark * percent_price_down, mark * percent_price_up]
    percent_price_up: float = 1.05  # defaut Binance : mark * 1.05
    percent_price_down: float = 0.95  # defaut Binance : mark * 0.95

    # MARKET_LOT_SIZE (regles specifiques aux market orders, souvent differentes)
    market_step_size: Optional[float] = None  # None = memes que LOT_SIZE
    market_min_qty: Optional[float] = None
    market_max_qty: Optional[float] = None

    # Futures specifique
    leverage_max: int = 125  # levier maximum autorise
    contract_size: float = 1.0  # taille d'un contrat en base asset
    settlement_asset: str = "USDT"  # actif de reglement

    # Metadata
    price_precision: int = 2
    qty_precision: int = 3
    is_active: bool = True

    def __post_init__(self) -> None:
        if self.step_size <= 0:
            raise ValueError(f"step_size must be > 0, got {self.step_size}")
        if self.tick_size <= 0:
            raise ValueError(f"tick_size must be > 0, got {self.tick_size}")
        if self.min_qty <= 0:
            raise ValueError(f"min_qty must be > 0, got {self.min_qty}")
        if self.min_qty > self.max_qty:
            raise ValueError(f"min_qty ({self.min_qty}) > max_qty ({self.max_qty})")
        if self.min_notional < 0:
            raise ValueError(f"min_notional must be >= 0")
        if not 0 < self.percent_price_down <= 1.0:
            raise ValueError(
                f"percent_price_down must be in (0, 1], got {self.percent_price_down}"
            )
        if self.percent_price_up < 1.0:
            raise ValueError(
                f"percent_price_up must be >= 1.0, got {self.percent_price_up}"
            )

    @property
    def effective_market_step(self) -> float:
        return (
            self.market_step_size
            if self.market_step_size is not None
            else self.step_size
        )

    @property
    def effective_market_min_qty(self) -> float:
        return self.market_min_qty if self.market_min_qty is not None else self.min_qty

    @property
    def effective_market_max_qty(self) -> float:
        return self.market_max_qty if self.market_max_qty is not None else self.max_qty


@dataclass
class ValidationResult:
    """
    Resultat d'une validation d'ordre.

    Si is_valid=False : rejection_reason explique pourquoi.
    Si is_valid=True  : adjusted_size/adjusted_price sont les valeurs
                        apres arrondis (a utiliser pour l'ordre reel).
    warnings : liste d'ajustements significatifs (non bloquants).
    """

    is_valid: bool
    rejection_reason: Optional[str] = None
    adjusted_size: Optional[float] = None
    adjusted_price: Optional[float] = None
    warnings: list = field(default_factory=list)

    # Contexte
    original_size: float = 0.0
    original_price: float = 0.0
    symbol: str = ""
    order_type: str = "market"

    @property
    def size_was_adjusted(self) -> bool:
        if self.adjusted_size is None or self.original_size == 0:
            return False
        return abs(self.adjusted_size - self.original_size) > 1e-12

    @property
    def price_was_adjusted(self) -> bool:
        if self.adjusted_price is None or self.original_price == 0:
            return False
        return abs(self.adjusted_price - self.original_price) > 1e-12

    @property
    def size_adjustment_pct(self) -> float:
        """Variation relative de la taille en %."""
        if not self.size_was_adjusted or self.original_size == 0:
            return 0.0
        return (self.adjusted_size - self.original_size) / self.original_size * 100.0

    @classmethod
    def accept(
        cls,
        symbol: str,
        original_size: float,
        original_price: float,
        adjusted_size: float,
        adjusted_price: float,
        order_type: str = "market",
        warnings: list | None = None,
    ) -> "ValidationResult":
        return cls(
            is_valid=True,
            adjusted_size=adjusted_size,
            adjusted_price=adjusted_price,
            original_size=original_size,
            original_price=original_price,
            symbol=symbol,
            order_type=order_type,
            warnings=warnings or [],
        )

    @classmethod
    def reject(
        cls,
        symbol: str,
        reason: str,
        original_size: float = 0.0,
        original_price: float = 0.0,
        order_type: str = "market",
    ) -> "ValidationResult":
        return cls(
            is_valid=False,
            rejection_reason=reason,
            original_size=original_size,
            original_price=original_price,
            symbol=symbol,
            order_type=order_type,
        )
