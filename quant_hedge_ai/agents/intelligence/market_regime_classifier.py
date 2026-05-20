"""
market_regime_classifier.py — Classificateur de régime de marché adaptatif.

Traduit le régime détecté en configuration de trading concrète :
  - seuil de score minimum pour le gate (min_score)
  - facteur SL basé sur l'ATR (sl_factor_atr)
  - facteur TP basé sur l'ATR (tp_factor_atr)
  - facteur de taille de position (size_factor)
  - trailing stop actif ou non
  - confirmation MTF requise ou non

Consommateurs :
  - GlobalRiskGate  : effective_min_score() pour le seuil adaptatif
  - MetaStrategyEngine : compute_sl_pct() / compute_tp_pct() pour SL/TP ATR
  - RegretEngine    : via delta pour feedback de calibration

Supporte les deux formats de régime :
  - Format détecteur (AdvancedRegimeDetector) : "sideways", "bull_trend", ...
  - Format packet (MarketRegime enum)         : "RANGE", "TREND_BULL", ...
"""

from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass
from typing import Deque

logger = logging.getLogger(__name__)


# ── RegimePacket — sortie enrichie du classifieur ────────────────────────────


@dataclass
class RegimePacket:
    """
    Snapshot complet du régime de marché pour un cycle donné.

    Remplace le simple string renvoyé par AdvancedRegimeDetector.
    Consommé par AdaptiveThresholdEngine, RegimeTransitionSmoother,
    et tout composant qui a besoin du contexte régime.
    """

    regime: str
    confidence: float  # 0.0 → 1.0 (décroît sans confirmation)
    duration_cycles: int  # cycles consécutifs dans ce régime
    transition_from: str  # régime précédent (vide si inconnu)
    entropy: float  # 0.0 = stable, 1.0 = chaos total
    in_transition: bool = False  # True si changement récent (< stabilité)


# ── RegimeStateTracker — hystérésis + confidence + entropy ───────────────────


class RegimeStateTracker:
    """
    Suit l'évolution du régime dans le temps.

    Centralise la logique d'hystérésis (déjà dans advisor_loop._REGIME_STABILITY),
    de confidence decay et d'entropie. Émet des RegimePacket.

    Usage :
        tracker = RegimeStateTracker(stability=3, decay=0.97, history=10)

        # À chaque cycle :
        packet = tracker.update(observed_regime)
        # packet.regime         → régime stable (après hystérésis)
        # packet.confidence     → confiance décroissante sans confirmation
        # packet.entropy        → instabilité récente (flips / history)
    """

    def __init__(
        self,
        stability: int = 3,
        confidence_decay: float = 0.97,
        history_size: int = 10,
    ) -> None:
        self._stability = stability
        self._decay = confidence_decay
        self._history: Deque[str] = deque(maxlen=history_size)
        self._stable_regime: str = "unknown"
        self._votes: list[str] = []
        self._confidence: float = 0.5
        self._duration: int = 0
        self._prev_stable: str = ""
        self._in_transition: bool = False

    def update(self, observed: str) -> RegimePacket:
        """
        Intègre une observation et retourne le RegimePacket du cycle courant.

        Args:
            observed : régime brut du AdvancedRegimeDetector (ou HMM)
        """
        self._history.append(observed)
        self._votes.append(observed)
        if len(self._votes) > self._stability:
            self._votes = self._votes[-self._stability :]

        # ── Hystérésis : transition validée après N cycles identiques ────────
        changed = False
        if (
            len(self._votes) == self._stability
            and len(set(self._votes)) == 1
            and self._votes[0] != self._stable_regime
        ):
            self._prev_stable = self._stable_regime
            self._stable_regime = self._votes[0]
            self._duration = 0
            self._confidence = 0.5  # reset à la transition
            self._in_transition = True
            changed = True
            logger.info(
                "[RegimeStateTracker] Transition confirmée: %s → %s",
                self._prev_stable,
                self._stable_regime,
            )
        else:
            self._in_transition = False

        # ── Confidence decay + boost si confirmation ─────────────────────────
        if observed == self._stable_regime:
            # Confirmation → confidence monte vers 1.0
            self._confidence = min(
                1.0, self._confidence + (1.0 - self._confidence) * 0.1
            )
            self._duration += 1
        else:
            # Divergence → confidence décroît
            self._confidence *= self._decay

        # ── Entropie : fréquence des changements récents ─────────────────────
        history_list = list(self._history)
        flips = sum(
            1
            for i in range(1, len(history_list))
            if history_list[i] != history_list[i - 1]
        )
        entropy = flips / max(1, len(history_list) - 1)

        return RegimePacket(
            regime=self._stable_regime,
            confidence=round(self._confidence, 3),
            duration_cycles=self._duration,
            transition_from=self._prev_stable,
            entropy=round(entropy, 3),
            in_transition=self._in_transition,
        )


@dataclass(frozen=True)
class RegimeConfig:
    """Paramètres de calibration pour un régime de marché donné."""

    regime: str
    min_score: int  # seuil de score pour le gate
    sl_factor_atr: float  # SL = sl_factor_atr × ATR (en % du prix)
    tp_factor_atr: float  # TP = tp_factor_atr × ATR (en % du prix)
    size_factor: float  # multiplicateur de taille (relatif à la base)
    trail_active: bool  # trailing stop actif
    confirm_required: bool  # confirmation MTF requise
    description: str

    def compute_sl_pct(self, atr_pct: float, floor: float = 0.008) -> float:
        """
        SL en % du prix à partir de l'ATR.

        Args:
            atr_pct : ATR normalisé (ATR / prix), ex. 0.012 = 1.2%
            floor   : plancher de sécurité (défaut 0.8%)

        Returns:
            SL en fraction du prix (ex. 0.018 = 1.8%)
            0.0 si ATR ou facteur non disponible
        """
        if atr_pct <= 0 or self.sl_factor_atr <= 0:
            return 0.0
        return max(atr_pct * self.sl_factor_atr, floor)

    def compute_tp_pct(self, atr_pct: float) -> float:
        """TP en % du prix à partir de l'ATR."""
        if atr_pct <= 0 or self.tp_factor_atr <= 0:
            return 0.0
        return atr_pct * self.tp_factor_atr


# ── Configurations par régime ──────────────────────────────────────────────────
#
# min_score : seuil de score effectif pour ce régime
#   - TREND  : 72  — on veut de la certitude avant d'entrer dans un trend
#   - RANGE  : 66  — mean reversion accepte des setups plus incertains
#   - BEAR   : 68  — prudent mais pas paralysé
#   - VOLATILE: 68 — petite taille, seuil modéré
#   - UNKNOWN : 72 — prudence maximale
#
# sl_factor_atr : SL = N × ATR_5m
#   - RANGE : 1.5× — assez large pour éviter le bruit de range (sweeps liquidité)
#   - TREND : 2.0× — room pour laisser courir le trend
#   - VOLATILE: 1.8× — large car les swings sont amplifiés

_REGIME_CONFIGS: dict[str, RegimeConfig] = {
    # ── Format AdvancedRegimeDetector ─────────────────────────────────────────
    "bull_trend": RegimeConfig(
        regime="bull_trend",
        min_score=72,
        sl_factor_atr=2.0,
        tp_factor_atr=4.0,
        size_factor=1.0,
        trail_active=True,
        confirm_required=True,
        description="Trend haussier — taille pleine, SL ATR 2×, trailing actif",
    ),
    "bear_trend": RegimeConfig(
        regime="bear_trend",
        min_score=68,
        sl_factor_atr=1.5,
        tp_factor_atr=3.0,
        size_factor=0.6,
        trail_active=True,
        confirm_required=True,
        description="Trend baissier — taille réduite 60%, SL ATR 1.5×",
    ),
    "sideways": RegimeConfig(
        regime="sideways",
        min_score=int(os.getenv("REGIME_SIDEWAYS_MIN_SCORE", "66")),
        sl_factor_atr=1.5,
        tp_factor_atr=2.0,
        size_factor=0.7,
        trail_active=False,
        confirm_required=False,
        description="Range latéral — mean reversion, SL ATR 1.5×, optionnel",
    ),
    "high_volatility_regime": RegimeConfig(
        regime="high_volatility_regime",
        min_score=68,
        sl_factor_atr=1.8,
        tp_factor_atr=2.5,
        size_factor=0.3,
        trail_active=False,
        confirm_required=True,
        description="Haute volatilité — taille 30%, SL ATR 1.8×",
    ),
    "flash_crash": RegimeConfig(
        regime="flash_crash",
        min_score=999,
        sl_factor_atr=0.0,
        tp_factor_atr=0.0,
        size_factor=0.0,
        trail_active=False,
        confirm_required=True,
        description="Flash crash — aucun trade autorisé",
    ),
    "unknown": RegimeConfig(
        regime="unknown",
        min_score=72,
        sl_factor_atr=1.5,
        tp_factor_atr=2.5,
        size_factor=0.5,
        trail_active=False,
        confirm_required=True,
        description="Régime inconnu — paramètres conservateurs",
    ),
    # ── Format MarketRegime enum (DecisionPacket) ──────────────────────────────
    "TREND_BULL": RegimeConfig(
        regime="TREND_BULL",
        min_score=72,
        sl_factor_atr=2.0,
        tp_factor_atr=4.0,
        size_factor=1.0,
        trail_active=True,
        confirm_required=True,
        description="Trend haussier (packet) — taille pleine",
    ),
    "TREND_BEAR": RegimeConfig(
        regime="TREND_BEAR",
        min_score=68,
        sl_factor_atr=1.5,
        tp_factor_atr=3.0,
        size_factor=0.6,
        trail_active=True,
        confirm_required=True,
        description="Trend baissier (packet) — taille réduite 60%",
    ),
    "RANGE": RegimeConfig(
        regime="RANGE",
        min_score=66,
        sl_factor_atr=1.5,
        tp_factor_atr=2.0,
        size_factor=0.7,
        trail_active=False,
        confirm_required=False,
        description="Range latéral (packet) — mean reversion permissif",
    ),
    "VOLATILE": RegimeConfig(
        regime="VOLATILE",
        min_score=68,
        sl_factor_atr=1.8,
        tp_factor_atr=2.5,
        size_factor=0.3,
        trail_active=False,
        confirm_required=True,
        description="Volatil (packet) — taille mini 30%",
    ),
    "UNKNOWN": RegimeConfig(
        regime="UNKNOWN",
        min_score=72,
        sl_factor_atr=1.5,
        tp_factor_atr=2.5,
        size_factor=0.5,
        trail_active=False,
        confirm_required=True,
        description="Inconnu (packet) — conservateur",
    ),
}

_DEFAULT_CONFIG = _REGIME_CONFIGS["unknown"]


class MarketRegimeClassifier:
    """
    Traduit un régime détecté en configuration de trading concrète.

    Usage:
        clf = MarketRegimeClassifier()
        config = clf.get_config("sideways")
        # config.min_score              → 66
        # config.compute_sl_pct(0.012) → 0.018 (1.8%)

        # Seuil effectif avec feedback RegretEngine (delta=-2) :
        clf.effective_min_score("sideways", delta=-2) → 64
    """

    def get_config(self, regime: str) -> RegimeConfig:
        """Retourne la configuration pour le régime donné (les deux formats)."""
        cfg = _REGIME_CONFIGS.get(regime)
        if cfg is None:
            logger.debug(
                "[RegimeClassifier] Régime inconnu: %r → config par défaut", regime
            )
            return _DEFAULT_CONFIG
        return cfg

    def effective_min_score(
        self,
        regime: str,
        delta: int = 0,
        absolute_floor: int = int(os.getenv("REGIME_ABSOLUTE_FLOOR", "55")),
    ) -> int:
        """
        Seuil de score effectif = config.min_score + delta.

        Args:
            regime         : régime courant ("sideways", "RANGE", ...)
            delta          : ajustement RegretEngine (négatif = plus permissif)
            absolute_floor : plancher absolu de sécurité (défaut 55)

        Returns:
            Score minimum entier à utiliser pour ce cycle.
        """
        base = self.get_config(regime).min_score
        if base >= 999:  # flash_crash — inviolable
            return base
        return max(base + delta, absolute_floor)

    def log_config(self, regime: str, delta: int = 0) -> None:
        """Log la configuration active pour le régime."""
        cfg = self.get_config(regime)
        effective = self.effective_min_score(regime, delta)
        logger.info(
            "[RegimeClassifier] %s → min_score=%d (base=%d delta=%d) "
            "SL×%.1f TP×%.1f size×%.1f trail=%s confirm=%s",
            regime,
            effective,
            cfg.min_score,
            delta,
            cfg.sl_factor_atr,
            cfg.tp_factor_atr,
            cfg.size_factor,
            cfg.trail_active,
            cfg.confirm_required,
        )
