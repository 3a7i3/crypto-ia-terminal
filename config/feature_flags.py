"""
config/feature_flags.py — Feature flags pour l'observabilité et les futures phases.

Toutes les features sont désactivables à chaud via variables d'environnement.
Défaut : toutes désactivées sauf FEATURE_REJECTION_STORE et FEATURE_DECISION_EXPLAINER
(actives dès que les modules sont importés et l'infrastructure prête).

Usage:
    from config.feature_flags import FEATURE_EVENT_BUS, FEATURE_REJECTION_STORE

    if FEATURE_EVENT_BUS:
        bus.publish(obs)
"""

from __future__ import annotations

import os


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").lower() in (
        "1",
        "true",
        "yes",
    )


# ── P0 — Infrastructure ────────────────────────────────────────────────────────
# Bus pub/sub — moteur publie une DecisionObservation, les listeners écoutent.
FEATURE_EVENT_BUS: bool = _flag("FEATURE_EVENT_BUS", default=True)

# ── P1 — Flow Explainability ──────────────────────────────────────────────────
# Message Telegram enrichi avec toutes les couches décisionnelles.
FEATURE_DECISION_EXPLAINER: bool = _flag("FEATURE_DECISION_EXPLAINER", default=True)

# ── P2 — Rejection Observatory ────────────────────────────────────────────────
# Persistance JSONL atomique de chaque signal refusé avec contexte complet.
FEATURE_REJECTION_STORE: bool = _flag("FEATURE_REJECTION_STORE", default=True)

# ── P3 — Regret Intelligence ──────────────────────────────────────────────────
# Évaluation multi-horizon (5m/15m/30m/1h/4h/12h/24h) des refus.
FEATURE_REGRET_SCHEDULER: bool = _flag("FEATURE_REGRET_SCHEDULER", default=True)

# ── P3.5 — Gel auto-calibration (DÉFAUT : GEL ACTIF = false désactive l'auto) ─
# FEATURE_AUTO_CALIBRATION=false (défaut) : get_threshold_delta() retourne 0.
# FEATURE_AUTO_CALIBRATION=true : comportement legacy — DÉCONSEILLÉ.
FEATURE_AUTO_CALIBRATION: bool = _flag("FEATURE_AUTO_CALIBRATION", default=False)

# ── P4-P7 — Réservés, désactivés ──────────────────────────────────────────────
FEATURE_ADAPTIVE_CALIBRATION: bool = _flag(
    "FEATURE_ADAPTIVE_CALIBRATION", default=False
)
FEATURE_STRATEGY_LAB: bool = _flag("FEATURE_STRATEGY_LAB", default=False)
FEATURE_AI_GOVERNANCE: bool = _flag("FEATURE_AI_GOVERNANCE", default=False)
FEATURE_DIGITAL_TWIN: bool = _flag("FEATURE_DIGITAL_TWIN", default=False)
