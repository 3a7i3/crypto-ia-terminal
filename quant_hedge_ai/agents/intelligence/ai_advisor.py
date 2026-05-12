"""
ai_advisor.py — Conseil IA par signal de trading.

Génère une explication textuelle pour chaque opportunité détectée par
LiveSignalEngine. Utilise LM Studio en local quand disponible, sinon produit
une analyse déterministe basée sur les composants du signal.

Usage:
    advisor = AIAdvisor()
    advice = advisor.explain(signal_result)
    print(advice.text)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from quant_hedge_ai.agents.execution.live_signal_engine import SignalResult

logger = logging.getLogger(__name__)

_LM_STUDIO_MAX_TOKENS = int(os.getenv("LM_STUDIO_MAX_TOKENS", "160"))
_LM_STUDIO_MIN_SCORE = int(os.getenv("LM_STUDIO_MIN_SCORE", "70"))

_SYSTEM_PROMPT = (
    "Tu es un analyste quantitatif expert en trading de crypto-monnaies. "
    "Tu analyses des signaux algorithmiques et fournis des conseils concis, "
    "précis et actionnables en français. Tu mentionnes toujours les risques."
)

_REGIME_DESCRIPTIONS = {
    "bull_trend":             "tendance haussière confirmée",
    "bear_trend":             "tendance baissière confirmée",
    "sideways":               "marché latéral / range",
    "high_volatility_regime": "haute volatilité",
    "flash_crash":            "krach éclair — risque extrême",
    "unknown":                "régime indéterminé",
}

_SIGNAL_ICONS = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}


@dataclass
class Advice:
    """Résultat d'une analyse AIAdvisor."""

    symbol: str
    signal: str
    score: int
    regime: str
    text: str                              # explication textuelle principale
    risk_level: str = "medium"             # low | medium | high | extreme
    confidence: str = "moderate"           # low | moderate | high
    source: str = "deterministic"          # deterministic | lm_studio
    components_summary: str = ""

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "signal": self.signal,
            "score": self.score,
            "regime": self.regime,
            "text": self.text,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "source": self.source,
        }

    def short(self) -> str:
        icon = _SIGNAL_ICONS.get(self.signal, "⚪")
        return (
            f"{icon} [{self.symbol}] {self.signal} | score={self.score} "
            f"| régime={self.regime} | risque={self.risk_level}\n{self.text}"
        )


class AIAdvisor:
    """
    Génère des conseils textuels pour chaque signal LiveSignalEngine.

    Priorité :
      1. LM Studio local (si disponible et use_lm_studio=True)
      2. Analyse déterministe (toujours disponible)
    """

    def __init__(self, use_lm_studio: bool = True, mode: str = "auto") -> None:
        self.use_lm_studio = use_lm_studio
        self.mode = mode  # "auto" | "lm_studio" | "deterministic"

    # ── API principale ─────────────────────────────────────────────────────────

    def explain(self, result: SignalResult) -> Advice:
        """Génère un conseil pour un SignalResult."""
        risk = self._assess_risk(result)
        confidence = self._assess_confidence(result)
        components_summary = self._summarize_components(result.components)

        text, source = self._generate_text(result, risk, confidence, components_summary)

        advice = Advice(
            symbol=result.symbol,
            signal=result.signal,
            score=result.score,
            regime=result.regime,
            text=text,
            risk_level=risk,
            confidence=confidence,
            source=source,
            components_summary=components_summary,
        )
        self._emit_event(advice, result)
        return advice

    def explain_batch(self, results: list[SignalResult]) -> list[Advice]:
        """Génère des conseils pour une liste de signaux."""
        advices = []
        for r in results:
            try:
                advices.append(self.explain(r))
            except Exception as exc:
                logger.warning("[AIAdvisor] Erreur %s: %s", r.symbol, exc)
        return advices

    # ── Génération de texte ────────────────────────────────────────────────────

    def _generate_text(
        self, result: SignalResult, risk: str, confidence: str, components_summary: str
    ) -> tuple[str, str]:
        """Retourne (texte, source)."""
        should_use_lm_studio = (
            self.use_lm_studio
            and self.mode != "deterministic"
            and self._should_use_lm_studio(result)
        )
        if should_use_lm_studio:
            try:
                text = self._ask_lm_studio(result, risk, confidence)
                return text, "lm_studio"
            except Exception as exc:
                logger.debug("[AIAdvisor] LM Studio indisponible: %s — fallback déterministe", exc)

        return self._deterministic_advice(result, risk, confidence, components_summary), "deterministic"

    def _should_use_lm_studio(self, result: SignalResult) -> bool:
        if getattr(result, "signal", "HOLD") == "HOLD":
            return False
        if not getattr(result, "actionable", True):
            return False
        if int(getattr(result, "score", 0)) < _LM_STUDIO_MIN_SCORE:
            return False
        return True

    def _ask_lm_studio(self, result: SignalResult, risk: str, confidence: str) -> str:
        from lm_studio.ai_router import AIRouter
        router = AIRouter(mode=self.mode if self.mode != "deterministic" else "auto")
        prompt = self._build_prompt(result, risk, confidence)
        return router.ask(
            prompt,
            system=_SYSTEM_PROMPT,
            max_tokens=_LM_STUDIO_MAX_TOKENS,
            temperature=0.3,
        )

    def _build_prompt(self, result: SignalResult, risk: str, confidence: str) -> str:
        regime_desc = _REGIME_DESCRIPTIONS.get(result.regime, result.regime)
        comps = result.components
        return (
            f"Analyse ce signal de trading et donne un conseil en 3-4 phrases :\n\n"
            f"Symbole : {result.symbol}\n"
            f"Signal : {result.signal} (score {result.score}/100)\n"
            f"Régime de marché : {regime_desc}\n"
            f"Signal MTF confirmé : {'oui' if result.confirmed else 'non'} "
            f"(force {result.strength:.0%})\n"
            f"Composants : MTF={comps.get('mtf', 0):.1f}/40, "
            f"Régime={comps.get('regime', 0):.1f}/25, "
            f"Qualité données={comps.get('data_quality', 0):.1f}/15, "
            f"Mémoire={comps.get('memory', 0):.1f}/20\n"
            f"Niveau de risque estimé : {risk}\n"
            f"Confiance : {confidence}\n\n"
            f"Donne ton analyse en commençant par la recommandation principale, "
            f"puis explique les points forts et les risques à surveiller."
        )

    def _deterministic_advice(
        self,
        result: SignalResult,
        risk: str,
        confidence: str,
        components_summary: str,
    ) -> str:
        regime_desc = _REGIME_DESCRIPTIONS.get(result.regime, result.regime)
        signal_word = {"BUY": "achat", "SELL": "vente", "HOLD": "neutre"}.get(
            result.signal, result.signal
        )
        confirmation = (
            f"confirmé sur {result.strength:.0%} des timeframes"
            if result.confirmed
            else "non confirmé multi-timeframes"
        )

        lines = [
            f"Signal {signal_word} sur {result.symbol} (score {result.score}/100) "
            f"en régime {regime_desc}.",
            f"Le signal est {confirmation}.",
        ]

        # Points forts
        strengths = []
        comps = result.components
        if comps.get("mtf", 0) >= 25:
            strengths.append("alignement multi-timeframes solide")
        if comps.get("regime", 0) >= 20:
            strengths.append(f"régime {result.regime} favorable")
        if comps.get("memory", 0) >= 15:
            strengths.append("stratégie mémorisée performante sur ce régime")
        if comps.get("data_quality", 0) >= 12:
            strengths.append("qualité des données excellente")
        if strengths:
            lines.append("Points forts : " + ", ".join(strengths) + ".")

        # Risques
        risks = []
        if risk in ("high", "extreme"):
            risks.append(f"risque {risk} — réduire la taille de position")
        if not result.confirmed:
            risks.append("signal non confirmé sur tous les TF")
        if result.regime in ("flash_crash", "high_volatility_regime"):
            risks.append("régime volatile — stops serrés recommandés")
        if result.score < 75:
            risks.append("score modéré — attendre confirmation supplémentaire")
        if risks:
            lines.append("Risques : " + ", ".join(risks) + ".")

        return " ".join(lines)

    # ── Évaluation du risque ──────────────────────────────────────────────────

    def _assess_risk(self, result: SignalResult) -> str:
        if result.regime == "flash_crash":
            return "extreme"
        if result.regime == "high_volatility_regime":
            return "high"
        if not result.confirmed or result.score < 60:
            return "high"
        if result.score >= 85 and result.confirmed:
            return "low"
        if result.score >= 70:
            return "medium"
        return "high"

    def _assess_confidence(self, result: SignalResult) -> str:
        if result.score >= 85 and result.confirmed and result.strength >= 0.7:
            return "high"
        if result.score >= 70 and result.confirmed:
            return "moderate"
        return "low"

    def _summarize_components(self, components: dict) -> str:
        parts = []
        for key, label in (
            ("mtf", "MTF"),
            ("regime", "Régime"),
            ("data_quality", "Qualité"),
            ("memory", "Mémoire"),
        ):
            if key in components:
                parts.append(f"{label}={components[key]:.1f}")
        return " | ".join(parts)

    def _emit_event(self, advice: Advice, result: SignalResult) -> None:
        try:
            from event_bus.bus import EventBus
            from event_bus.events import NewBestStrategyEvent
            if result.signal in ("BUY", "SELL") and result.score >= 80:
                EventBus.get().emit(
                    NewBestStrategyEvent(
                        regime=result.regime,
                        sharpe=result.strength * 3.0,
                        drawdown=0.0,
                        strategy_name=f"LSE_{result.symbol}_{result.signal}",
                        source="ai_advisor",
                    )
                )
        except Exception as exc:
            logger.warning("[AIAdvisor] Erreur emission evenement evolution: %s", exc)
