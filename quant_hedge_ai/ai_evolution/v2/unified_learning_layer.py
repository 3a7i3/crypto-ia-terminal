"""
unified_learning_layer.py — Unified Feedback & Learning Layer

Fusionne DecisionQualityEngine + RegretEngine + MistakeMemory en un
cerveau d'apprentissage unique avec attribution causale complète.

Pour chaque trade fermé, attribue la performance aux :
- signal (bonne/mauvaise analyse)
- régime (mauvaise classification)
- exécution (slippage, timing)
- risk (sizing trop grand/petit)
- marché (événement imprévisible)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LEARNING_LOG = Path("databases/unified_learning.jsonl")


class LearningCategory(str, Enum):
    VALIDATED = "validated"         # bon signal, bon exécution, bon résultat
    UNLUCKY = "unlucky"             # bon signal, mauvais résultat (marché)
    LUCKY = "lucky"                 # mauvais signal, bon résultat (chance)
    MISTAKE_SIGNAL = "mistake_signal"
    MISTAKE_REGIME = "mistake_regime"
    MISTAKE_EXECUTION = "mistake_execution"
    MISTAKE_SIZING = "mistake_sizing"


@dataclass
class LearningEvent:
    trade_id: str
    symbol: str
    timestamp_open: float
    timestamp_close: float
    side: str
    pnl_pct: float
    pnl_usd: float

    # Contexte au moment de la décision
    features_at_entry: dict[str, float] = field(default_factory=dict)
    regime_at_entry: str = "unknown"
    conviction_at_entry: float = 0.5
    arbitration_score: float = 0.0

    # Exécution
    expected_slippage_bps: float = 0.0
    actual_slippage_bps: float = 0.0
    execution_timing_score: float = 0.5

    # Attribution
    category: LearningCategory = LearningCategory.VALIDATED
    attribution: dict[str, float] = field(default_factory=dict)   # composante → part de la perf
    lessons: list[str] = field(default_factory=list)

    def was_profitable(self) -> bool:
        return self.pnl_pct > 0

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items()}
        d["category"] = self.category.value
        return d


class UnifiedLearningLayer:
    """
    Cerveau d'apprentissage central.
    - Enregistre chaque trade avec son contexte complet
    - Attribue causalement la performance
    - Génère des règles d'auto-amélioration
    - Alerte sur les patterns de dégradation
    """

    def __init__(self) -> None:
        self._events: list[LearningEvent] = []
        self._rules: list[dict] = []
        self._regime_performance: dict[str, list[float]] = {}
        self._feature_importance: dict[str, float] = {}
        _LEARNING_LOG.parent.mkdir(parents=True, exist_ok=True)

    def record_trade_closed(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        pnl_pct: float,
        pnl_usd: float,
        timestamp_open: float,
        timestamp_close: float,
        context: dict[str, Any] | None = None,
    ) -> LearningEvent:
        """Enregistre un trade fermé et effectue l'attribution causale."""
        ctx = context or {}
        event = LearningEvent(
            trade_id=trade_id,
            symbol=symbol,
            timestamp_open=timestamp_open,
            timestamp_close=timestamp_close,
            side=side,
            pnl_pct=pnl_pct,
            pnl_usd=pnl_usd,
            features_at_entry=ctx.get("features", {}),
            regime_at_entry=ctx.get("regime", "unknown"),
            conviction_at_entry=ctx.get("conviction", 0.5),
            arbitration_score=ctx.get("arbitration_score", 0.0),
            expected_slippage_bps=ctx.get("expected_slippage_bps", 0.0),
            actual_slippage_bps=ctx.get("actual_slippage_bps", 0.0),
            execution_timing_score=ctx.get("timing_score", 0.5),
        )
        event.category = self._classify(event, ctx)
        event.attribution = self._attribute(event, ctx)
        event.lessons = self._extract_lessons(event)

        self._events.append(event)
        self._update_regime_stats(event)
        self._update_feature_importance(event)
        self._persist(event)

        if event.category in (LearningCategory.MISTAKE_SIGNAL, LearningCategory.MISTAKE_REGIME):
            self._generate_rule(event)

        logger.info("[Learning] Trade %s clôturé → %s (PnL: %.2f%%)", trade_id, event.category.value, pnl_pct * 100)
        return event

    def regime_win_rate(self, regime: str) -> float | None:
        perf = self._regime_performance.get(regime, [])
        if not perf:
            return None
        return sum(1 for p in perf if p > 0) / len(perf)

    def top_lessons(self, n: int = 10) -> list[str]:
        lessons: dict[str, int] = {}
        for event in self._events:
            for lesson in event.lessons:
                lessons[lesson] = lessons.get(lesson, 0) + 1
        return sorted(lessons, key=lessons.get, reverse=True)[:n]

    def active_rules(self) -> list[dict]:
        return [r for r in self._rules if r.get("active", True)]

    def feature_importance_report(self) -> dict[str, float]:
        return dict(sorted(self._feature_importance.items(), key=lambda x: x[1], reverse=True))

    def recent_events(self, n: int = 20) -> list[dict]:
        return [e.to_dict() for e in self._events[-n:]]

    # ------------------------------------------------------------------
    # Attribution causale
    # ------------------------------------------------------------------

    def _classify(self, event: LearningEvent, ctx: dict) -> LearningCategory:
        profitable = event.was_profitable()
        conviction_ok = event.conviction_at_entry >= 0.5
        arb_ok = event.arbitration_score >= 0.3
        good_signal = conviction_ok and arb_ok

        if profitable and good_signal:
            return LearningCategory.VALIDATED
        if profitable and not good_signal:
            return LearningCategory.LUCKY
        if not profitable and not good_signal:
            slippage_excess = event.actual_slippage_bps - event.expected_slippage_bps
            if slippage_excess > 20:
                return LearningCategory.MISTAKE_EXECUTION
            regime_mismatch = ctx.get("regime_mismatch", False)
            if regime_mismatch:
                return LearningCategory.MISTAKE_REGIME
            return LearningCategory.MISTAKE_SIGNAL
        # bon signal, mauvais résultat
        return LearningCategory.UNLUCKY

    def _attribute(self, event: LearningEvent, ctx: dict) -> dict[str, float]:
        pnl = event.pnl_pct
        attribution = {
            "signal": 0.0,
            "regime": 0.0,
            "execution": 0.0,
            "market": 0.0,
            "risk": 0.0,
        }
        if abs(pnl) < 1e-6:
            return attribution
        # Exécution : slippage excès
        slip_excess = event.actual_slippage_bps - event.expected_slippage_bps
        if slip_excess > 5:
            attribution["execution"] = min(-slip_excess / 10000 / abs(pnl), 0.5) if pnl < 0 else 0.0
        # Signal : conviction vs résultat
        attribution["signal"] = event.conviction_at_entry * (1 if pnl > 0 else -1) * 0.4
        # Régime : match régime vs résultat
        if ctx.get("regime_mismatch"):
            attribution["regime"] = -0.3
        # Marché : résidu
        total_attributed = sum(abs(v) for v in attribution.values())
        attribution["market"] = max(0.0, 1.0 - total_attributed)
        return attribution

    def _extract_lessons(self, event: LearningEvent) -> list[str]:
        lessons = []
        if event.category == LearningCategory.MISTAKE_SIGNAL:
            feat = event.features_at_entry
            rsi = feat.get("rsi_14", 50)
            if rsi > 75:
                lessons.append(f"Éviter long avec RSI>{rsi:.0f} en régime {event.regime_at_entry}")
            if rsi < 25:
                lessons.append(f"Éviter short avec RSI<{rsi:.0f} en régime {event.regime_at_entry}")
        if event.category == LearningCategory.MISTAKE_REGIME:
            lessons.append(f"Régime '{event.regime_at_entry}' mal classifié — réviser HMM")
        if event.category == LearningCategory.MISTAKE_EXECUTION:
            lessons.append(f"Slippage excessif: {event.actual_slippage_bps:.1f}bps > attendu {event.expected_slippage_bps:.1f}bps")
        return lessons

    def _generate_rule(self, event: LearningEvent) -> None:
        feat = event.features_at_entry
        rule = {
            "id": f"rule_{len(self._rules)+1}",
            "source_trade": event.trade_id,
            "category": event.category.value,
            "regime": event.regime_at_entry,
            "side": event.side,
            "features": {k: v for k, v in feat.items() if k in ("rsi_14", "atr_pct", "ob_imbalance")},
            "lesson": event.lessons[0] if event.lessons else "",
            "active": True,
            "created_at": time.time(),
        }
        self._rules.append(rule)

    def _update_regime_stats(self, event: LearningEvent) -> None:
        self._regime_performance.setdefault(event.regime_at_entry, []).append(event.pnl_pct)

    def _update_feature_importance(self, event: LearningEvent) -> None:
        for feat, val in event.features_at_entry.items():
            current = self._feature_importance.get(feat, 0.5)
            # Approximation : features corrélées au profit sont importantes
            if event.was_profitable() and abs(val) > 0.3:
                self._feature_importance[feat] = min(current * 1.02, 1.0)
            elif not event.was_profitable() and abs(val) > 0.5:
                self._feature_importance[feat] = max(current * 0.99, 0.1)

    def _persist(self, event: LearningEvent) -> None:
        try:
            with _LEARNING_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as exc:
            logger.debug("[Learning] persist error: %s", exc)
