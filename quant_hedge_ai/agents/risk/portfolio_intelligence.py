"""
portfolio_intelligence.py — Portfolio Intelligence (P9)

Surveille la concentration et l'exposition nette du portefeuille.

Métriques :
  concentration_by_exchange()  : fraction USD par exchange
  concentration_by_strategy()  : fraction USD par stratégie
  net_exposure()               : (longs - shorts) / total, [-1, 1]

Seuils d'alerte :
  P9_CONC_WARN  : concentration > 60% sur un exchange/stratégie → WARNING
  P9_CONC_CRIT  : > 80% → réduction forcée suggérée
  P9_EXPO_WARN  : exposition nette absolue > 80% → WARNING

Actions :
  - Alerte WARNING : loggée, retournée via get_alerts()
  - Alerte CRITICAL : suggestion de réduction de position
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.risk.portfolio_intelligence")

_CONC_WARN_DEFAULT = 0.60
_CONC_CRIT_DEFAULT = 0.80
_EXPO_WARN_DEFAULT = 0.80


@dataclass
class Position:
    symbol: str
    exchange: str
    strategy: str
    side: str  # "long" | "short"
    size_usd: float
    ts: float = field(default_factory=time.time)


class PortfolioIntelligence:
    """
    Surveille concentration et exposition nette du portefeuille.

    Usage :
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "momentum", "long", 5000.0)
        pi.record_position("ETH/USDT", "binance", "scalp", "short", 1000.0)
        alerts = pi.get_alerts()
        for a in alerts: log.warning("[P9/Port] %s", a)
    """

    def __init__(self) -> None:
        self._conc_warn = float(os.getenv("P9_CONC_WARN", str(_CONC_WARN_DEFAULT)))
        self._conc_crit = float(os.getenv("P9_CONC_CRIT", str(_CONC_CRIT_DEFAULT)))
        self._expo_warn = float(os.getenv("P9_EXPO_WARN", str(_EXPO_WARN_DEFAULT)))
        self._positions: Dict[str, Position] = {}

    # ── Gestion des positions ─────────────────────────────────────────────────

    def record_position(
        self,
        symbol: str,
        exchange: str,
        strategy: str,
        side: str,
        size_usd: float,
    ) -> None:
        """Enregistre ou met à jour une position ouverte."""
        self._positions[symbol] = Position(
            symbol=symbol,
            exchange=exchange,
            strategy=strategy,
            side=side.lower(),
            size_usd=abs(size_usd),
        )

    def close_position(self, symbol: str) -> bool:
        """Ferme une position. Retourne True si la position existait."""
        if symbol in self._positions:
            del self._positions[symbol]
            return True
        return False

    # ── Métriques ─────────────────────────────────────────────────────────────

    def concentration_by_exchange(self) -> Dict[str, float]:
        """Fraction du total USD par exchange. {} si portefeuille vide."""
        total = self._total_usd()
        if total < 1e-8:
            return {}
        result: Dict[str, float] = {}
        for pos in self._positions.values():
            result[pos.exchange] = result.get(pos.exchange, 0.0) + pos.size_usd
        return {k: round(v / total, 4) for k, v in result.items()}

    def concentration_by_strategy(self) -> Dict[str, float]:
        """Fraction du total USD par stratégie."""
        total = self._total_usd()
        if total < 1e-8:
            return {}
        result: Dict[str, float] = {}
        for pos in self._positions.values():
            result[pos.strategy] = result.get(pos.strategy, 0.0) + pos.size_usd
        return {k: round(v / total, 4) for k, v in result.items()}

    def net_exposure(self) -> float:
        """
        Exposition nette = (longs - shorts) / total.
        Plage : [-1.0, 1.0]. 0 = neutre.
        """
        total = self._total_usd()
        if total < 1e-8:
            return 0.0
        longs = sum(p.size_usd for p in self._positions.values() if p.side == "long")
        shorts = sum(p.size_usd for p in self._positions.values() if p.side == "short")
        return round((longs - shorts) / total, 4)

    # ── Alertes ───────────────────────────────────────────────────────────────

    def get_alerts(self) -> List[str]:
        """
        Retourne la liste des alertes actives.
        Appeler chaque cycle pour détecter les dépassements.
        """
        alerts: List[str] = []

        # Concentration exchange
        for exchange, frac in self.concentration_by_exchange().items():
            if frac >= self._conc_crit:
                msg = (
                    f"CRITICAL: exchange={exchange} concentration={frac:.0%} "
                    f">= {self._conc_crit:.0%} — réduction forcée suggérée"
                )
                alerts.append(msg)
                _log.warning("[P9/Port] %s", msg)
            elif frac >= self._conc_warn:
                msg = (
                    f"WARN: exchange={exchange} concentration={frac:.0%} "
                    f">= {self._conc_warn:.0%}"
                )
                alerts.append(msg)
                _log.info("[P9/Port] %s", msg)

        # Concentration stratégie
        for strategy, frac in self.concentration_by_strategy().items():
            if frac >= self._conc_crit:
                msg = (
                    f"CRITICAL: strategy={strategy} concentration={frac:.0%} "
                    f">= {self._conc_crit:.0%} — réduction forcée suggérée"
                )
                alerts.append(msg)
                _log.warning("[P9/Port] %s", msg)
            elif frac >= self._conc_warn:
                msg = (
                    f"WARN: strategy={strategy} concentration={frac:.0%} "
                    f">= {self._conc_warn:.0%}"
                )
                alerts.append(msg)
                _log.info("[P9/Port] %s", msg)

        # Exposition nette
        expo = abs(self.net_exposure())
        if expo >= self._expo_warn:
            direction = "long" if self.net_exposure() > 0 else "short"
            msg = (
                f"WARN: exposition nette {direction}={expo:.0%} "
                f">= {self._expo_warn:.0%}"
            )
            alerts.append(msg)
            _log.warning("[P9/Port] %s", msg)

        return alerts

    # ── Consultation ─────────────────────────────────────────────────────────

    def position_count(self) -> int:
        return len(self._positions)

    def total_usd(self) -> float:
        return round(self._total_usd(), 2)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def summary(self) -> dict:
        return {
            "position_count": self.position_count(),
            "total_usd": self.total_usd(),
            "net_exposure": self.net_exposure(),
            "by_exchange": self.concentration_by_exchange(),
            "by_strategy": self.concentration_by_strategy(),
            "active_alerts": len(self.get_alerts()),
        }

    # ── Helper ────────────────────────────────────────────────────────────────

    def _total_usd(self) -> float:
        return sum(p.size_usd for p in self._positions.values())
