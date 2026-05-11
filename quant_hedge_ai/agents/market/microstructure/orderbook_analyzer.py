"""
orderbook_analyzer.py — Order Book Intelligence

Analyse l'order book en temps réel pour détecter :
- Imbalance bid/ask (pression directionnelle)
- Murs de liquidité (support/résistance cachés)
- Spoofing probable (ordres fantômes)
- Pression agressive (taker flow)
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OrderBookSignal:
    symbol: str
    timestamp: float

    # Imbalance
    imbalance: float = 0.0              # [-1, +1] : -1 forte pression sell, +1 forte pression buy
    imbalance_slope: float = 0.0        # variation d'imbalance sur les 5 dernières snapshots

    # Liquidité
    bid_depth_usd: float = 0.0
    ask_depth_usd: float = 0.0
    liquidity_ratio: float = 1.0        # bid_depth / ask_depth

    # Murs
    nearest_bid_wall_pct: float = 0.0   # distance % au prochain mur bid
    nearest_ask_wall_pct: float = 0.0   # distance % au prochain mur ask

    # Spoofing
    spoofing_score: float = 0.0         # [0,1] probabilité de spoofing

    # Spread
    spread_bps: float = 0.0
    spread_widening: bool = False

    # Signal synthétique
    directional_pressure: float = 0.0  # [-1,+1] combinaison imbalance + walls + slope

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class OrderBookAnalyzer:
    """
    Analyse un order book (format ccxt) et produit un OrderBookSignal.
    Maintient un historique court pour calculer les slopes et détecter spoofing.
    """

    WALL_MULTIPLIER = 5.0       # un niveau est un "mur" si volume > 5x la moyenne
    SPOOF_DISAPPEAR_RATIO = 0.7 # un ordre "fantôme" si 70% de son volume disparaît en <2s

    def __init__(self, history_size: int = 20) -> None:
        self._history: dict[str, deque] = {}  # symbol → deque[OrderBookSignal]
        self._prev_levels: dict[str, dict] = {}
        self._history_size = history_size

    def analyze(self, symbol: str, orderbook: dict[str, Any]) -> OrderBookSignal:
        """
        Analyse un snapshot d'order book et retourne un signal enrichi.
        orderbook format: {"bids": [[price, qty], ...], "asks": [[price, qty], ...]}
        """
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        sig = OrderBookSignal(symbol=symbol, timestamp=time.time())

        if not bids or not asks:
            return sig

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid = (best_bid + best_ask) / 2.0

        # Spread
        sig.spread_bps = (best_ask - best_bid) / mid * 10000 if mid else 0.0

        # Profondeurs (en USD, top 20 niveaux)
        sig.bid_depth_usd = sum(float(b[0]) * float(b[1]) for b in bids[:20])
        sig.ask_depth_usd = sum(float(a[0]) * float(a[1]) for a in asks[:20])
        total = sig.bid_depth_usd + sig.ask_depth_usd
        sig.imbalance = (sig.bid_depth_usd - sig.ask_depth_usd) / total if total else 0.0
        sig.liquidity_ratio = sig.bid_depth_usd / sig.ask_depth_usd if sig.ask_depth_usd else 1.0

        # Murs de liquidité
        bid_wall = self._find_wall(bids, mid, side="bid")
        ask_wall = self._find_wall(asks, mid, side="ask")
        sig.nearest_bid_wall_pct = abs(mid - bid_wall) / mid if bid_wall else 0.0
        sig.nearest_ask_wall_pct = abs(ask_wall - mid) / mid if ask_wall else 0.0

        # Spoofing (comparaison avec snapshot précédent)
        sig.spoofing_score = self._detect_spoofing(symbol, bids, asks)

        # Slope d'imbalance sur historique
        hist = self._history.get(symbol, deque())
        if len(hist) >= 3:
            recent_imbalances = [s.imbalance for s in list(hist)[-3:]]
            sig.imbalance_slope = recent_imbalances[-1] - recent_imbalances[0]

        # Spread widening
        if hist:
            prev_spread = list(hist)[-1].spread_bps
            sig.spread_widening = sig.spread_bps > prev_spread * 1.5

        # Pression directionnelle synthétique
        sig.directional_pressure = self._compute_directional_pressure(sig)

        # Stocker dans l'historique
        if symbol not in self._history:
            self._history[symbol] = deque(maxlen=self._history_size)
        self._history[symbol].append(sig)

        # Sauvegarder niveaux pour détection spoofing
        self._prev_levels[symbol] = {
            "bids": {float(b[0]): float(b[1]) for b in bids[:30]},
            "asks": {float(a[0]): float(a[1]) for a in asks[:30]},
        }

        return sig

    def history(self, symbol: str, n: int = 10) -> list[OrderBookSignal]:
        hist = self._history.get(symbol, deque())
        return list(hist)[-n:]

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _find_wall(self, levels: list, mid: float, side: str) -> float:
        """Trouve le premier mur de liquidité (niveau avec volume exceptionnel)."""
        if not levels:
            return 0.0
        qtys = [float(lvl[1]) for lvl in levels[:20]]
        if not qtys:
            return 0.0
        avg_qty = sum(qtys) / len(qtys)
        threshold = avg_qty * self.WALL_MULTIPLIER
        for price, qty in levels[:20]:
            if float(qty) >= threshold:
                return float(price)
        return 0.0

    def _detect_spoofing(self, symbol: str, bids: list, asks: list) -> float:
        """
        Estime la probabilité de spoofing en comparant avec le snapshot précédent.
        Un gros ordre qui disparaît sans exécution = signal de spoofing.
        """
        prev = self._prev_levels.get(symbol)
        if not prev:
            return 0.0

        prev_bids = prev.get("bids", {})
        current_bids = {float(b[0]): float(b[1]) for b in bids[:30]}

        ghost_orders = 0
        total_checked = 0
        for price, prev_qty in prev_bids.items():
            if prev_qty < 1.0:
                continue
            total_checked += 1
            current_qty = current_bids.get(price, 0.0)
            if current_qty < prev_qty * (1 - self.SPOOF_DISAPPEAR_RATIO):
                ghost_orders += 1

        if total_checked == 0:
            return 0.0
        return min(ghost_orders / total_checked, 1.0)

    def _compute_directional_pressure(self, sig: OrderBookSignal) -> float:
        """Combine imbalance, slope et walls en un score directionnel [-1, +1]."""
        pressure = sig.imbalance * 0.5
        pressure += sig.imbalance_slope * 0.3
        # Asymétrie des murs : mur bid proche = support fort (signal +)
        if sig.nearest_bid_wall_pct > 0 and sig.nearest_ask_wall_pct > 0:
            wall_bias = (sig.nearest_ask_wall_pct - sig.nearest_bid_wall_pct) / (
                sig.nearest_ask_wall_pct + sig.nearest_bid_wall_pct
            )
            pressure += wall_bias * 0.2
        return max(-1.0, min(1.0, pressure))
