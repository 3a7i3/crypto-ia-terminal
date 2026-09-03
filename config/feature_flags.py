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

# ── P3.5 — Frontière constitutionnelle observation/décision ─────────────────
# Le flag maître reste false par défaut. FEATURE_AUTO_CALIBRATION ne suffit
# jamais, à lui seul, à autoriser un résultat de regret à modifier un seuil.
FEATURE_REGRET_DECISION_FEEDBACK: bool = _flag(
    "FEATURE_REGRET_DECISION_FEEDBACK", default=False
)

# Compatibilité du calcul legacy; double opt-in requis avec le flag maître.
# FEATURE_AUTO_CALIBRATION=false (défaut) : get_threshold_delta() retourne 0.
# FEATURE_AUTO_CALIBRATION=true seul : toujours passif.
FEATURE_AUTO_CALIBRATION: bool = _flag("FEATURE_AUTO_CALIBRATION", default=False)

# ── S-02B.1 — Frontière mémoire adaptative / méta-apprentissage vs décision ──
# LEARNING != AUTHORITY (ADR S-02B.1). MistakeMemory, MetaLearner et
# StrategyMemoryStore peuvent en permanence observer, enregistrer, apprendre
# et proposer. Ce flag maître, false par défaut, est la seule chose qui peut
# transformer une de leurs recommandations en effet réel sur une décision
# live (blocage de trade, TP/SL/trailing, score/personnalité). Défaut off,
# fail-closed : un import cassé ou une variable absente/malformée reste
# passif, jamais actif.
FEATURE_ADAPTIVE_DECISION_FEEDBACK: bool = _flag(
    "FEATURE_ADAPTIVE_DECISION_FEEDBACK", default=False
)


def adaptive_decision_feedback_enabled() -> bool:
    """Résolveur public de la valeur EFFECTIVE de FEATURE_ADAPTIVE_DECISION_FEEDBACK.

    La constante de module `FEATURE_ADAPTIVE_DECISION_FEEDBACK` ci-dessus est
    résolue une seule fois, à l'import de ce module — donc potentiellement
    AVANT que l'appelant n'ait chargé son `.env` (`load_dotenv()`). Un module
    déjà présent dans `sys.modules` ne ré-exécute pas son corps à un import
    ultérieur, donc cette constante resterait figée sur une valeur obsolète
    même si le `.env` définit ensuite la variable.

    Cette fonction relit `os.environ` à CHAQUE appel (via `_flag`, jamais mis
    en cache) : elle donne donc la valeur effective correcte quand elle est
    appelée après le chargement de la configuration, sans dépendre de l'ordre
    d'import. Fail-closed comme `_flag()` : absent, "false", ou une valeur
    malformée résolvent tous à False ; seul "true"/"1"/"yes" (insensible à la
    casse) résout à True.
    """
    return _flag("FEATURE_ADAPTIVE_DECISION_FEEDBACK", default=False)


# ── P4-P7 — Réservés, désactivés ──────────────────────────────────────────────
FEATURE_ADAPTIVE_CALIBRATION: bool = _flag(
    "FEATURE_ADAPTIVE_CALIBRATION", default=False
)
FEATURE_STRATEGY_LAB: bool = _flag("FEATURE_STRATEGY_LAB", default=False)
FEATURE_AI_GOVERNANCE: bool = _flag("FEATURE_AI_GOVERNANCE", default=False)
FEATURE_DIGITAL_TWIN: bool = _flag("FEATURE_DIGITAL_TWIN", default=False)
