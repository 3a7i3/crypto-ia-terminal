"""
advisor_only_mode.py — Mode V9_ADVISOR_ONLY=true (Phase 8).

Quand cette variable est activée, le système :
  - Analyse les marchés normalement (scan, régime, signal)
  - Génère les conseils AIAdvisor
  - Envoie les alertes Telegram proactives
  - N'exécute AUCUN ordre (ni paper, ni live)

Utile pour :
  - Observer le système en conditions réelles sans risque
  - Valider les signaux avant de passer en mode trading
  - Audit / backtesting des conseils

Usage:
    from quant_hedge_ai.advisor_only_mode import AdvisorOnlyMode

    mode = AdvisorOnlyMode.from_env()
    if mode.active:
        result = mode.process_signal(signal_result, features)
        # result.advice contient le conseil texte
        # Aucun ordre n'est passé
    else:
        # Mode normal : passer par GlobalRiskGate + OrderSizer + PaperTradingEngine
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_ENV_KEY = "V9_ADVISOR_ONLY"


@dataclass
class AdvisorResult:
    """Résultat d'un cycle en mode advisor-only."""

    signal: str                  # BUY | SELL | HOLD
    score: int
    regime: str
    advice_text: str
    risk_level: str
    confidence: str
    alerted: bool = False        # True si alerte Telegram envoyée
    blocked_reason: str = ""     # "advisor_only" si mode actif
    components: dict = field(default_factory=dict)

    @property
    def would_trade(self) -> bool:
        """Signal qui aurait déclenché un trade si le mode était désactivé."""
        return self.signal in ("BUY", "SELL") and self.score >= 70

    def as_dict(self) -> dict:
        return {
            "signal": self.signal,
            "score": self.score,
            "regime": self.regime,
            "advice_text": self.advice_text,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "alerted": self.alerted,
            "blocked_reason": self.blocked_reason,
            "would_trade": self.would_trade,
        }


class AdvisorOnlyMode:
    """
    Encapsule la logique du mode observation-seule.

    Quand active=True :
      - process_signal() génère le conseil et envoie l'alerte
      - Retourne AdvisorResult avec blocked_reason="advisor_only"
      - N'interagit jamais avec PaperTradingEngine / ExecutionEngine
    """

    def __init__(
        self,
        active: bool = False,
        advisor=None,
        alerts=None,
    ) -> None:
        self.active = active
        self._advisor = advisor
        self._alerts = alerts
        self._cycle_count = 0
        self._would_trade_count = 0

        if self.active:
            logger.warning(
                "[AdvisorOnlyMode] MODE ACTIF — aucun ordre ne sera exécuté."
            )

    @classmethod
    def from_env(
        cls,
        advisor=None,
        alerts=None,
    ) -> "AdvisorOnlyMode":
        """Lit V9_ADVISOR_ONLY depuis l'environnement."""
        active_str = os.getenv(_ENV_KEY, "false").lower()
        active = active_str in ("true", "1", "yes", "on")
        return cls(active=active, advisor=advisor, alerts=alerts)

    # ── API principale ─────────────────────────────────────────────────────────

    def process_signal(self, signal_result, features: dict | None = None) -> AdvisorResult:
        """
        Traite un signal en mode advisor-only.

        Génère le conseil AIAdvisor, envoie l'alerte si actionable,
        mais ne passe AUCUN ordre.
        """
        self._cycle_count += 1
        advice = self._get_advice(signal_result)
        alerted = False

        if self._alerts is not None and getattr(signal_result, "actionable", False):
            alerted = self._alerts.on_signal_opportunity(signal_result, advice)

        result = AdvisorResult(
            signal=getattr(signal_result, "signal", "HOLD"),
            score=getattr(signal_result, "score", 0),
            regime=getattr(signal_result, "regime", "unknown"),
            advice_text=getattr(advice, "text", "") if advice else "",
            risk_level=getattr(advice, "risk_level", "unknown") if advice else "unknown",
            confidence=getattr(advice, "confidence", "low") if advice else "low",
            alerted=alerted,
            blocked_reason="advisor_only" if self.active else "",
            components=getattr(signal_result, "components", {}),
        )

        if result.would_trade:
            self._would_trade_count += 1
            logger.info(
                "[AdvisorOnly] Signal %s score=%d AURAIT tradé (cycle %d, total=%d)",
                result.signal, result.score, self._cycle_count, self._would_trade_count,
            )

        return result

    def summary(self) -> dict:
        """Résumé de l'activité du mode advisor-only."""
        return {
            "active": self.active,
            "cycles_processed": self._cycle_count,
            "would_trade_count": self._would_trade_count,
            "would_trade_rate": (
                round(self._would_trade_count / self._cycle_count, 3)
                if self._cycle_count > 0 else 0.0
            ),
        }

    # ── Internals ─────────────────────────────────────────────────────────────

    def _get_advice(self, signal_result):
        if self._advisor is None:
            return None
        try:
            return self._advisor.explain(signal_result)
        except Exception as exc:
            logger.debug("[AdvisorOnly] Erreur advice: %s", exc)
            return None
