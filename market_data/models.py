"""
market_data/models.py — Modeles de donnees normalises multi-exchange.

Toutes les donnees brutes de Binance, Hyperliquid et MEXC sont converties
vers ces structures avant d'entrer dans le systeme.

Principe : un seul modele, n sources.

NormalizedTrade         : un echange (tape) sur n'importe quel exchange
NormalizedOrderBook     : snapshot/update du book a un instant T
NormalizedLiquidityEvent: liquidation ou sweep detecte
NormalizedCandle        : chandelle OHLCV avec volumes directionnels
MarketEvent             : enveloppe unifiee pour le stream
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, Optional, Union

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

Exchange = Literal["binance", "hyperliquid", "mexc"]
EventType = Literal["trade", "orderbook", "candle", "liquidity"]


# ---------------------------------------------------------------------------
# Structures de base
# ---------------------------------------------------------------------------


@dataclass
class NormalizedTrade:
    """
    Un echange individuel (tape) sur le marche.
    side = cote du TAKER (celui qui traverse le book).
    """

    exchange: str
    symbol: str  # format unifie "BTCUSDT"
    timestamp_ms: int  # UTC epoch ms
    price: float
    size: float  # quantite en base asset
    side: str  # "buy" | "sell"
    trade_id: str = ""
    is_liquidation: bool = False
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def value_usd(self) -> float:
        return self.price * self.size

    @property
    def signed_size(self) -> float:
        """Positif pour buy, negatif pour sell (pour CVD)."""
        return self.size if self.side == "buy" else -self.size


@dataclass
class OrderBookLevel:
    """Un niveau du carnet d'ordres."""

    price: float
    size: float


@dataclass
class NormalizedOrderBook:
    """
    Snapshot du carnet d'ordres a un instant T.

    bids : [(price, size), ...] tries par prix DECROISSANT (meilleur bid en premier)
    asks : [(price, size), ...] tries par prix CROISSANT (meilleur ask en premier)
    is_snapshot : True pour snapshot complet, False pour update partiel
    """

    exchange: str
    symbol: str
    timestamp_ms: int
    bids: list[tuple[float, float]]  # (price, size) desc
    asks: list[tuple[float, float]]  # (price, size) asc
    sequence: int = 0
    is_snapshot: bool = True

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2.0
        return None

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_bps(self) -> Optional[float]:
        if self.best_bid and self.best_ask and self.best_bid > 0:
            return (self.best_ask - self.best_bid) / self.best_bid * 10_000.0
        return None

    def bid_depth(self, levels: int = 5) -> float:
        """Volume total en USDT sur les N premiers niveaux bid."""
        return sum(p * s for p, s in self.bids[:levels])

    def ask_depth(self, levels: int = 5) -> float:
        """Volume total en USDT sur les N premiers niveaux ask."""
        return sum(p * s for p, s in self.asks[:levels])

    def imbalance(self, levels: int = 5) -> float:
        """
        Desequilibre entre bids et asks.
        Range [-1, +1] : +1 = full buy pressure, -1 = full sell pressure.
        """
        b = self.bid_depth(levels)
        a = self.ask_depth(levels)
        total = b + a
        if total == 0:
            return 0.0
        return (b - a) / total

    def walls(
        self, min_size_usd: float = 100_000.0
    ) -> dict[str, list[tuple[float, float]]]:
        """
        Retourne les niveaux dont le volume depasse min_size_usd (murs de liquidite).
        {"bids": [(price, size_usd), ...], "asks": [...]}
        """
        bid_walls = [(p, p * s) for p, s in self.bids if p * s >= min_size_usd]
        ask_walls = [(p, p * s) for p, s in self.asks if p * s >= min_size_usd]
        return {"bids": bid_walls, "asks": ask_walls}


@dataclass
class NormalizedLiquidityEvent:
    """
    Evenement de liquidite exceptionnel : liquidation forcee, sweep, gros ordre.
    Ces evenements sont des signaux de comportement fort.
    """

    exchange: str
    symbol: str
    timestamp_ms: int
    event_type: str  # "liquidation" | "sweep" | "large_order"
    side: str  # "buy" | "sell" (direction du trade liquidant)
    price: float
    size: float  # quantite base asset
    value_usd: float = 0.0
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.value_usd == 0.0:
            self.value_usd = self.price * self.size


@dataclass
class NormalizedCandle:
    """
    Chandelle OHLCV avec volumes directionnels si disponibles.
    buy_volume / sell_volume = repartition taker (CVD par candle).
    """

    exchange: str
    symbol: str
    timestamp_ms: int  # open time UTC ms
    timeframe: str  # "1m" | "5m" | "15m" | "1h" | "4h" | "1d"
    open: float
    high: float
    low: float
    close: float
    volume: float  # volume total base asset
    buy_volume: float = 0.0  # taker buy volume (si dispo)
    sell_volume: float = 0.0
    trade_count: int = 0
    is_closed: bool = True

    @property
    def delta(self) -> float:
        """CVD de la candle : buy_volume - sell_volume."""
        return self.buy_volume - self.sell_volume

    @property
    def delta_pct(self) -> float:
        """Delta en % du volume total."""
        if self.volume == 0:
            return 0.0
        return self.delta / self.volume * 100.0

    @property
    def body_pct(self) -> float:
        """Taille du corps en % du range HL."""
        hl = self.high - self.low
        if hl == 0:
            return 0.0
        return abs(self.close - self.open) / hl * 100.0

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


# ---------------------------------------------------------------------------
# Enveloppe unifiee pour le stream
# ---------------------------------------------------------------------------

MarketData = Union[
    NormalizedTrade, NormalizedOrderBook, NormalizedLiquidityEvent, NormalizedCandle
]


@dataclass
class MarketEvent:
    """
    Enveloppe unifiee pour le stream multi-exchange.
    Permet de traiter tous les types d'evenements dans une seule file.
    """

    event_type: EventType
    exchange: str
    symbol: str
    timestamp_ms: int
    data: MarketData

    @classmethod
    def from_trade(cls, trade: NormalizedTrade) -> "MarketEvent":
        return cls("trade", trade.exchange, trade.symbol, trade.timestamp_ms, trade)

    @classmethod
    def from_orderbook(cls, book: NormalizedOrderBook) -> "MarketEvent":
        return cls("orderbook", book.exchange, book.symbol, book.timestamp_ms, book)

    @classmethod
    def from_candle(cls, candle: NormalizedCandle) -> "MarketEvent":
        return cls(
            "candle", candle.exchange, candle.symbol, candle.timestamp_ms, candle
        )

    @classmethod
    def from_liquidity(cls, event: NormalizedLiquidityEvent) -> "MarketEvent":
        return cls("liquidity", event.exchange, event.symbol, event.timestamp_ms, event)

    def as_dict(self) -> dict:
        """Serialisation pour stockage JSONL."""
        import dataclasses

        base = {
            "event_type": self.event_type,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "timestamp_ms": self.timestamp_ms,
        }
        d = dataclasses.asdict(self.data)
        d.pop("raw", None)
        base["data"] = d
        return base
