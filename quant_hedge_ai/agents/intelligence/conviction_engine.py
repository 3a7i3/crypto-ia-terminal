"""
conviction_engine.py — Conviction Engine

Pas juste BUY / SELL.

Le bot mesure sa CONVICTION avant d'agir.

4 niveaux :
  MINIMAL      [0-40]   → taille 0% (ignoré)
  LOW          [40-59]  → taille 30% — surveillance
  MEDIUM       [60-74]  → taille 60% — trade standard
  HIGH         [75-89]  → taille 100% — trade confiant
  EXCEPTIONAL  [90-100] → taille 150% — opportunité rare

La conviction est calculée depuis 6 dimensions :
  1. Score signal (0-100)
  2. Alignement MTF (1h/4h/1d convergent ?)
  3. Régime favorable pour la stratégie
  4. Mémoire historique (Sharpe passé pour ce régime)
  5. Qualité des données (nb bougies, volume, fraîcheur)
  6. Consensus personnalité/signal (le mode actuel valide l'action)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ConvictionLevel(str, Enum):
    MINIMAL     = "minimal"
    LOW         = "low"
    MEDIUM      = "medium"
    HIGH        = "high"
    EXCEPTIONAL = "exceptional"


@dataclass
class ConvictionResult:
    level:          ConvictionLevel
    score:          float           # [0, 100]
    size_factor:    float           # multiplicateur taille [0.0, 1.5]
    dimensions:     dict            # détail par dimension
    notes:          list            # explications

    def summary(self) -> str:
        return (
            f"[{self.level.value.upper()}] "
            f"conviction={self.score:.0f}/100 "
            f"size×{self.size_factor:.2f}"
        )

    def blocks_trade(self) -> bool:
        return self.level == ConvictionLevel.MINIMAL


# ── Mapping niveau → facteur taille ───────────────────────────────────────────

_SIZE_FACTORS = {
    ConvictionLevel.MINIMAL:     0.0,
    ConvictionLevel.LOW:         float(os.getenv("CONV_SIZE_LOW",         "0.3")),
    ConvictionLevel.MEDIUM:      float(os.getenv("CONV_SIZE_MEDIUM",      "0.6")),
    ConvictionLevel.HIGH:        float(os.getenv("CONV_SIZE_HIGH",        "1.0")),
    ConvictionLevel.EXCEPTIONAL: float(os.getenv("CONV_SIZE_EXCEPTIONAL", "1.5")),
}

_LEVEL_THRESHOLDS = [
    (float(os.getenv("CONV_THRESH_EXCEPTIONAL", "90")), ConvictionLevel.EXCEPTIONAL),
    (float(os.getenv("CONV_THRESH_HIGH",         "75")), ConvictionLevel.HIGH),
    (float(os.getenv("CONV_THRESH_MEDIUM",        "60")), ConvictionLevel.MEDIUM),
    (float(os.getenv("CONV_THRESH_LOW",           "40")), ConvictionLevel.LOW),
    (0.0,                                                  ConvictionLevel.MINIMAL),
]


def _score_to_level(score: float) -> ConvictionLevel:
    for threshold, level in _LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return ConvictionLevel.MINIMAL


class ConvictionEngine:
    """
    Calcule la conviction du bot sur un signal donné.

    Usage :
        engine = ConvictionEngine()
        result = engine.evaluate(signal, features, candles, regime, memory_sharpe, personality)
        effective_size = base_size * result.size_factor
    """

    # Poids des dimensions [somme = 100]
    W_SIGNAL    = float(os.getenv("CONV_W_SIGNAL",    "30"))  # score brut du signal
    W_MTF       = float(os.getenv("CONV_W_MTF",       "25"))  # alignement multi-timeframe
    W_REGIME    = float(os.getenv("CONV_W_REGIME",    "20"))  # régime favorable
    W_MEMORY    = float(os.getenv("CONV_W_MEMORY",    "15"))  # historique Sharpe
    W_QUALITY   = float(os.getenv("CONV_W_QUALITY",   "10"))  # qualité données

    def evaluate(
        self,
        signal,                             # SignalResult
        features:       dict,
        candles:        list,
        regime:         str,
        memory_sharpe:  Optional[float]  = None,
        personality_name: str            = "unknown",
    ) -> ConvictionResult:

        dims  = {}
        notes = []

        # ── Dim 1 : Score signal brut ──────────────────────────────────────────
        sig_score = float(getattr(signal, "score", 0))
        d_signal  = min(100.0, sig_score)
        dims["signal"] = d_signal
        if sig_score >= 85:
            notes.append(f"Signal fort: {sig_score:.0f}/100")
        elif sig_score < 60:
            notes.append(f"Signal faible: {sig_score:.0f}/100")

        # ── Dim 2 : Alignement MTF ─────────────────────────────────────────────
        components = getattr(signal, "components", {})
        mtf_raw    = float(components.get("mtf", 0))   # max 40pts
        d_mtf      = (mtf_raw / 40) * 100
        dims["mtf"] = d_mtf
        confirmed  = getattr(signal, "confirmed", False)
        if confirmed:
            d_mtf = min(100.0, d_mtf + 15)
            notes.append("MTF confirmé sur 3 timeframes")
        elif d_mtf < 50:
            notes.append(f"Alignement MTF faible: {d_mtf:.0f}/100")

        # ── Dim 3 : Adéquation régime ──────────────────────────────────────────
        sig_action = getattr(signal, "signal", "HOLD")
        d_regime   = self._regime_score(regime, sig_action, personality_name)
        dims["regime"] = d_regime
        if d_regime >= 80:
            notes.append(f"Régime favorable: {regime}")
        elif d_regime < 40:
            notes.append(f"Régime défavorable pour {sig_action}: {regime}")

        # ── Dim 4 : Mémoire Sharpe ─────────────────────────────────────────────
        if memory_sharpe is not None and memory_sharpe > 0:
            d_memory = min(100.0, (memory_sharpe / 3.0) * 100)
            if memory_sharpe >= 2.0:
                notes.append(f"Excellent historique Sharpe={memory_sharpe:.2f}")
            elif memory_sharpe < 0.5:
                notes.append(f"Historique faible Sharpe={memory_sharpe:.2f}")
        else:
            d_memory = 50.0  # neutre si inconnu
        dims["memory"] = d_memory

        # ── Dim 5 : Qualité données ────────────────────────────────────────────
        d_quality = self._data_quality_score(candles, features)
        dims["quality"] = d_quality
        if d_quality < 50:
            notes.append(f"Données de faible qualité: {d_quality:.0f}/100")

        # ── Score composite ────────────────────────────────────────────────────
        composite = (
            d_signal  * self.W_SIGNAL  / 100 +
            d_mtf     * self.W_MTF     / 100 +
            d_regime  * self.W_REGIME  / 100 +
            d_memory  * self.W_MEMORY  / 100 +
            d_quality * self.W_QUALITY / 100
        )

        # Bonus : force du signal (strength)
        strength = float(getattr(signal, "strength", 0.5))
        if strength >= 0.8:
            composite = min(100.0, composite + 5)
            notes.append(f"Signal très fort (strength={strength:.0%})")

        # Malus : HOLD
        if sig_action == "HOLD":
            composite = min(composite, 35.0)

        level       = _score_to_level(composite)
        size_factor = _SIZE_FACTORS[level]

        result = ConvictionResult(
            level=level,
            score=round(composite, 1),
            size_factor=size_factor,
            dimensions=dims,
            notes=notes,
        )

        logger.info("[Conviction] %s | dims=%s", result.summary(),
                    {k: f"{v:.0f}" for k, v in dims.items()})
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _regime_score(regime: str, action: str, personality: str) -> float:
        """Score [0-100] : le régime est-il favorable pour cette action ?"""
        matrix = {
            # (regime, action) → score
            ("bull_trend",             "BUY"):  95,
            ("bull_trend",             "SELL"): 20,
            ("bear_trend",             "SELL"): 90,
            ("bear_trend",             "BUY"):  15,
            ("sideways",               "BUY"):  55,
            ("sideways",               "SELL"): 55,
            ("high_volatility_regime", "BUY"):  40,
            ("high_volatility_regime", "SELL"): 40,
            ("flash_crash",            "BUY"):   5,
            ("flash_crash",            "SELL"):  5,
            ("unknown",                "BUY"):  45,
            ("unknown",                "SELL"): 45,
        }
        return float(matrix.get((regime, action.upper()), 50))

    @staticmethod
    def _data_quality_score(candles: list, features: dict) -> float:
        """Score [0-100] : qualité des données disponibles."""
        if not candles:
            return 0.0
        score = 0.0

        # Quantité de bougies
        n = len(candles)
        score += min(40.0, n / 200 * 40)

        # Volume non nul
        valid_vol = sum(1 for c in candles[-20:] if float(c.get("volume", 0)) > 0)
        score += (valid_vol / 20) * 30

        # Features disponibles
        key_features = ["momentum", "realized_volatility", "trend_strength", "atr"]
        present = sum(1 for k in key_features if k in features and features[k] is not None)
        score += (present / len(key_features)) * 30

        return min(100.0, score)
