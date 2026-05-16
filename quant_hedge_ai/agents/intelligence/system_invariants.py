"""
system_invariants.py — Lois physiques immuables du système.

Ces constantes définissent les limites absolues que le système
ne peut jamais franchir, quelle que soit l'adaptation en cours.

Toute violation est signalée immédiatement au COO et au Telegram.

Règle de modification : changer une invariante nécessite une
décision explicite documentée (pas un hotfix).
"""

import os

# ── Adaptation du threshold (RegretEngine) ────────────────────────
# delta max appliqué par cycle : évite les sauts brutaux de seuil
MAX_THRESHOLD_DELTA: int = int(os.getenv("INV_MAX_DELTA", "2"))

# écart cumulé max vs baseline (ex: base=66, max drift=±8 → floor=58)
MAX_CUMULATIVE_DELTA: int = int(os.getenv("INV_MAX_CUMUL_DELTA", "8"))

# ── Stabilité du régime ───────────────────────────────────────────
# nb max de changements de régime sur une fenêtre glissante de 10 cycles
MAX_REGIME_FLIPS_10C: int = int(os.getenv("INV_MAX_FLIPS_10C", "3"))

# cycles consécutifs requis avant qu'un régime soit confirmé
MIN_REGIME_STABILITY_CYCLES: int = int(os.getenv("INV_MIN_STABILITY", "3"))

# ── Concentration stratégique ─────────────────────────────────────
# une stratégie ne peut pas représenter plus de X% des trades récents
MAX_SINGLE_STRATEGY_WEIGHT: float = float(os.getenv("INV_MAX_STRATEGY_WEIGHT", "0.60"))

# entropie de Shannon normalisée minimum sur la distribution des stratégies
# 0 = une seule stratégie, 1 = distribution parfaite
MIN_PORTFOLIO_ENTROPY: float = float(os.getenv("INV_MIN_ENTROPY", "0.30"))

# ── Inactivité du capital ─────────────────────────────────────────
# nombre max de cycles consécutifs sans trade avant alerte sur-filtrage
MAX_CONSECUTIVE_IDLE_CYCLES: int = int(os.getenv("INV_MAX_IDLE", "30"))

# ── Risque global ─────────────────────────────────────────────────
# drawdown maximum absolu avant VETO forcé (indépendant de l'Override)
MAX_DRAWDOWN_HARD: float = float(os.getenv("INV_MAX_DD", "0.15"))

# ── GO/NO-GO P5 ───────────────────────────────────────────────────
# win rate minimum sur 30 trades pour valider le passage en live
MIN_WIN_RATE_30T: float = float(os.getenv("INV_MIN_WIN_RATE", "0.35"))

# PnL cumulé minimum (ex: -5% sur le capital) pour GO
MIN_PNL_GO: float = float(os.getenv("INV_MIN_PNL_GO", "-0.05"))

# ── Planchers de confiance ────────────────────────────────────────
# confidence_score minimum d'une stratégie (StrategyRanker)
MIN_CONFIDENCE_SCORE: float = float(os.getenv("INV_MIN_CONFIDENCE", "0.10"))

# ── Fenêtres d'observation ────────────────────────────────────────
REGIME_FLIP_WINDOW: int = 10  # cycles pour compter les flips
THRESHOLD_VAR_WINDOW: int = 20  # cycles pour calculer la variance du seuil
STRATEGY_ENTROPY_WINDOW: int = 50  # trades pour calculer l'entropie
