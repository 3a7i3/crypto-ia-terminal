"""
confidence_explainer.py -- Confidence Score Explainability (Idée #7).

Au lieu de :
    signal_score = 83

Donne :
    83 =
    + trend alignment        (+32 / 40)
    + volume confirmation    (+18 / 25)
    + data quality           (+13 / 15)
    - macro risk             (-8)
    - session weakness       (-5)

Usage:
    explainer = ConfidenceExplainer()
    explanation = explainer.explain(signal_result)
    print(explanation.render())
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from quant_hedge_ai.agents.execution.live_signal_engine import SignalResult

# -- Seuils d'évaluation par composant -----------------------------------------

_COMPONENT_MAX = {
    "mtf": 40.0,
    "regime": 25.0,
    "data_quality": 15.0,
    "memory": 20.0,
}

_COMPONENT_LABELS = {
    "mtf": "Alignement multi-timeframes",
    "regime": "Régime de marché",
    "data_quality": "Qualité des données",
    "memory": "Mémoire stratégique (Sharpe)",
}

_REGIME_SENTIMENT = {
    "bull_trend": ("positif", 0),
    "bear_trend": ("négatif", -3),
    "sideways": ("neutre", -2),
    "high_volatility_regime": ("risqué", -5),
    "flash_crash": ("extrême", -15),
    "unknown": ("indéterminé", -8),
}


@dataclass
class ComponentBreakdown:
    name: str
    label: str
    value: float
    max_value: float
    pct: float  # valeur / max en %
    rating: str  # excellent | bon | moyen | faible | bloquant
    contribution: str  # "+32/40" ou "-8"
    note: str = ""


@dataclass
class ScoreExplanation:
    symbol: str
    score: int
    signal: str
    regime: str
    components: list[ComponentBreakdown]
    bonuses: list[tuple[str, int]]  # [(label, points)]
    penalties: list[tuple[str, int]]  # [(label, points)]
    verdict: str
    confidence_level: str  # low | moderate | high | exceptional
    one_liner: str

    def render(self) -> str:
        def _safe(s: str) -> str:
            return s.encode("ascii", errors="replace").decode("ascii")

        lines = [
            f"{'-'*52}",
            f"SCORE EXPLAINER -- {self.symbol} | {self.signal} | {self.score}/100",
            f"{'-'*52}",
        ]

        # Composants principaux
        lines.append("Components:")
        for c in self.components:
            bar = self._bar(c.pct)
            lines.append(
                f"  {_safe(c.label):<32} {c.contribution:>8}  {bar}  [{c.rating}]"
            )
            if c.note:
                lines.append(f"    -> {_safe(c.note)}")

        if self.bonuses:
            lines.append("Bonuses:")
            for label, pts in self.bonuses:
                lines.append(f"  + {_safe(label):<36} +{pts}")

        if self.penalties:
            lines.append("Penalties:")
            for label, pts in self.penalties:
                lines.append(f"  - {_safe(label):<36} {pts}")

        lines += [
            f"{'-'*52}",
            f"Verdict    : {_safe(self.verdict)}",
            f"Confidence : {self.confidence_level}",
            f"{'-'*52}",
            f"  {_safe(self.one_liner)}",
            f"{'-'*52}",
        ]
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "signal": self.signal,
            "regime": self.regime,
            "components": [
                {
                    "name": c.name,
                    "label": c.label,
                    "value": c.value,
                    "max_value": c.max_value,
                    "pct": c.pct,
                    "rating": c.rating,
                    "contribution": c.contribution,
                    "note": c.note,
                }
                for c in self.components
            ],
            "bonuses": [{"label": lbl, "pts": p} for lbl, p in self.bonuses],
            "penalties": [{"label": lbl, "pts": p} for lbl, p in self.penalties],
            "verdict": self.verdict,
            "confidence_level": self.confidence_level,
            "one_liner": self.one_liner,
        }

    @staticmethod
    def _bar(pct: float, width: int = 10) -> str:
        filled = int(pct / 100.0 * width)
        return "#" * filled + "." * (width - filled)


class ConfidenceExplainer:
    """
    Décompose un SignalResult en explication détaillée composant par composant.

    Chaque composant est évalué, annoté, et des bonus/pénalités contextuels
    sont ajoutés selon le régime, la confirmation MTF, et la force du signal.
    """

    def explain(self, result: SignalResult) -> ScoreExplanation:
        comps = result.components or {}
        components = [
            self._explain_component(k, comps.get(k, 0.0)) for k in _COMPONENT_MAX
        ]

        bonuses = self._compute_bonuses(result)
        penalties = self._compute_penalties(result)

        confidence = self._confidence_level(result)
        verdict = self._verdict(result, confidence)
        one_liner = self._one_liner(result, components, bonuses, penalties)

        return ScoreExplanation(
            symbol=result.symbol,
            score=result.score,
            signal=result.signal,
            regime=result.regime,
            components=components,
            bonuses=bonuses,
            penalties=penalties,
            verdict=verdict,
            confidence_level=confidence,
            one_liner=one_liner,
        )

    def explain_batch(self, results: list[SignalResult]) -> list[ScoreExplanation]:
        return [self.explain(r) for r in results]

    # -- Composants ------------------------------------------------------------

    def _explain_component(self, name: str, value: float) -> ComponentBreakdown:
        max_v = _COMPONENT_MAX.get(name, 100.0)
        pct = min(100.0, value / max_v * 100.0) if max_v > 0 else 0.0
        rating = self._rate(pct)
        contribution = f"+{value:.1f}/{max_v:.0f}"
        note = self._component_note(name, value, pct)

        return ComponentBreakdown(
            name=name,
            label=_COMPONENT_LABELS.get(name, name),
            value=round(value, 2),
            max_value=max_v,
            pct=round(pct, 1),
            rating=rating,
            contribution=contribution,
            note=note,
        )

    def _component_note(self, name: str, value: float, pct: float) -> str:
        if name == "mtf":
            if pct >= 75:
                return "Signal aligné sur tous les timeframes"
            if pct >= 50:
                return "Alignement partiel -- attendre confirmation"
            return "Divergence multi-timeframes détectée"

        if name == "regime":
            if pct >= 80:
                return "Régime très favorable au signal directionnel"
            if pct >= 50:
                return "Régime modérément favorable"
            return "Régime défavorable -- réduire le sizing"

        if name == "data_quality":
            if pct >= 80:
                return "Données OHLCV valides et complètes"
            if pct >= 50:
                return "Quelques gaps dans les données"
            return "Données manquantes -- signal peu fiable"

        if name == "memory":
            if pct >= 75:
                return "Sharpe élevé mémorisé sur ce régime"
            if pct >= 40:
                return "Performances passées modérées"
            return "Pas de mémoire ou historique négatif"

        return ""

    # -- Bonus / pénalités -----------------------------------------------------

    def _compute_bonuses(self, result: SignalResult) -> list[tuple[str, int]]:
        bonuses = []
        if result.confirmed and result.strength >= 0.8:
            bonuses.append(("Confirmation MTF forte (>=80 %)", 5))
        if result.score >= 90:
            bonuses.append(("Score exceptionnel >=90", 3))
        if result.regime == "bull_trend" and result.signal == "BUY":
            bonuses.append(("Signal dans le sens du régime haussier", 4))
        if result.regime == "bear_trend" and result.signal == "SELL":
            bonuses.append(("Signal dans le sens du régime baissier", 4))
        return bonuses

    def _compute_penalties(self, result: SignalResult) -> list[tuple[str, int]]:
        penalties = []
        if result.regime == "flash_crash":
            penalties.append(("Régime flash_crash -- risque extrême", -15))
        elif result.regime == "high_volatility_regime":
            penalties.append(("Haute volatilité -- slippage accru", -5))
        if not result.confirmed:
            penalties.append(("Signal non confirmé tous TF", -8))
        _min_score = int(os.getenv("SIGNAL_MIN_SCORE", "70"))
        if result.score < _min_score:
            penalties.append((f"Score sous le seuil minimum ({_min_score})", -6))
        if result.regime == "unknown":
            penalties.append(("Régime indéterminé -- incertitude macro", -8))
        return penalties

    # -- Évaluations -----------------------------------------------------------

    @staticmethod
    def _rate(pct: float) -> str:
        if pct >= 85:
            return "excellent"
        if pct >= 65:
            return "bon"
        if pct >= 40:
            return "moyen"
        if pct >= 20:
            return "faible"
        return "bloquant"

    @staticmethod
    def _confidence_level(result: SignalResult) -> str:
        if result.score >= 90 and result.confirmed and result.strength >= 0.8:
            return "exceptional"
        if result.score >= 80 and result.confirmed:
            return "high"
        if result.score >= 70:
            return "moderate"
        return "low"

    @staticmethod
    def _verdict(result: SignalResult, confidence: str) -> str:
        if result.regime == "flash_crash":
            return "DANGER -- Rester en dehors du marché"
        if not result.actionable:
            return "HOLD -- Signal insuffisant pour entrer"
        if confidence == "exceptional":
            return "FORT -- Conditions optimales réunies"
        if confidence == "high":
            return "OK -- Signal solide, sizing normal"
        if confidence == "moderate":
            return "PRUDENT -- Signal valide, sizing réduit recommandé"
        return "FAIBLE -- Attendre une meilleure configuration"

    @staticmethod
    def _one_liner(
        result: SignalResult,
        components: list[ComponentBreakdown],
        bonuses: list[tuple[str, int]],
        penalties: list[tuple[str, int]],
    ) -> str:
        # Best by absolute value (most points contributed), worst by pct
        best = max(components, key=lambda c: c.value, default=None)
        worst = min(components, key=lambda c: c.pct, default=None)
        parts = []
        if best:
            parts.append(f"force: {best.label.lower()}")
        if worst and worst.pct < 50:
            parts.append(f"faiblesse: {worst.label.lower()}")
        if penalties:
            parts.append(f"risque: {penalties[0][0].lower()}")
        return (
            "Score " + str(result.score) + "/100 -- " + " | ".join(parts)
            if parts
            else f"Score {result.score}/100"
        )
