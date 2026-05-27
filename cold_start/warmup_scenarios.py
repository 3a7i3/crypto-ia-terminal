"""
warmup_scenarios.py — 12 scénarios de démarrage critique (P10)

Chaque scénario décrit une condition de boot difficile avec :
  - description du contexte
  - état initial injecté (snapshot)
  - comportement attendu du ColdStartManager
  - invariant critique à vérifier

Ces scénarios sont utilisés dans les tests (cold_start/tests/test_scenarios.py)
et comme documentation des conditions réelles que le système doit survivre.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColdStartScenario:
    id: str  # CS-01 → CS-12
    name: str
    description: str
    initial_snapshot: dict  # état injecté dans ColdStartManager
    expected_behavior: str  # ce que le manager doit faire
    must_not_reach_live: bool = False  # True si LIVE_READY ne doit PAS être atteint
    must_fail: bool = False  # True si FAILED est le seul résultat correct
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "must_not_reach_live": self.must_not_reach_live,
            "must_fail": self.must_fail,
            "tags": self.tags,
        }


def _base_snapshot(**overrides: Any) -> dict:
    """Snapshot de référence — système sain."""
    base = {
        "capital_total": 10_000.0,
        "symbols_ready": 80,
        "symbols_total": 100,
        "avg_feature_confidence": 0.85,
        "regime_stability": 0.80,
        "regime_last_updated_ts": time.time() - 60,
        "risk_governor_state": "NORMAL",
        "risk_sync": True,
        "hard_limits_ok": True,
        "probation_consistent": True,
        "evolution_memory_loaded": True,
        "transition_cache_populated": True,
        "strategy_weights": {
            "scalp": 0.20,
            "momentum": 0.25,
            "mean_reversion": 0.25,
            "breakout": 0.15,
            "grid": 0.15,
        },
        "shadow_cycles_completed": 0,
        "open_positions_unknown": False,
        "kill_switch_safe_mode": False,
        "anomaly_count": 0,
        "dwe_sample_coverage": 0.80,
    }
    base.update(overrides)
    return base


# ── 12 scénarios ─────────────────────────────────────────────────────────────

SCENARIOS: list[ColdStartScenario] = [
    ColdStartScenario(
        id="CS-01",
        name="Premier boot complet",
        description=(
            "État totalement vide. Aucune mémoire, aucun cache, aucun historique. "
            "Le système démarre de zéro sur un exchange inconnu."
        ),
        initial_snapshot=_base_snapshot(
            evolution_memory_loaded=False,
            transition_cache_populated=False,
            symbols_ready=0,
            avg_feature_confidence=0.0,
            regime_stability=0.0,
            shadow_cycles_completed=0,
            dwe_sample_coverage=0.0,
        ),
        expected_behavior=(
            "Doit rester en FETCHING_MARKET_DATA jusqu'à 60% des symboles. "
            "Ne doit PAS atteindre LIVE_READY avant shadow_cycles_completed >= 10."
        ),
        must_not_reach_live=True,
        tags=["fresh_start", "empty_state"],
    ),
    ColdStartScenario(
        id="CS-02",
        name="Reboot après crash",
        description=(
            "Le process s'est terminé brutalement pendant un cycle actif. "
            "Mémoire partielle : probation states incohérents, "
            "transition cache présent mais potentiellement périmé."
        ),
        initial_snapshot=_base_snapshot(
            probation_consistent=False,
            transition_cache_populated=True,
            evolution_memory_loaded=True,
            regime_last_updated_ts=time.time() - 300,  # 5 min
        ),
        expected_behavior=(
            "Doit détecter l'incohérence probation via l'invariant. "
            "Doit passer par VALIDATING_RISK avec score réduit avant de progresser. "
            "Ne doit pas bloquer définitivement si l'incohérence se résout."
        ),
        must_not_reach_live=False,
        tags=["crash_recovery", "partial_state"],
    ),
    ColdStartScenario(
        id="CS-03",
        name="Exchange indisponible",
        description=(
            "L'exchange principal ne répond pas. 0 symboles avec données. "
            "Peut être temporaire (maintenance) ou permanent (clé API révoquée)."
        ),
        initial_snapshot=_base_snapshot(
            symbols_ready=0,
            symbols_total=100,
            avg_feature_confidence=0.0,
            regime_stability=0.0,
        ),
        expected_behavior=(
            "Doit rester bloqué en FETCHING_MARKET_DATA jusqu'au timeout (120s). "
            "Après timeout → FAILED avec raison claire."
        ),
        must_fail=True,
        tags=["exchange_down", "no_data"],
    ),
    ColdStartScenario(
        id="CS-04",
        name="1 timeframe manquante",
        description=(
            "Le scanner 4h échoue systématiquement. Seulement 1h et 1d disponibles. "
            "Les features multi-TF sont incomplètes → faux régime possible."
        ),
        initial_snapshot=_base_snapshot(
            symbols_ready=70,
            avg_feature_confidence=0.55,  # en dessous du seuil BUILDING_FEATURES (0.70)
            regime_stability=0.50,
        ),
        expected_behavior=(
            "avg_feature_confidence trop bas pour passer BUILDING_FEATURES. "
            "Doit rester bloqué à cet état. Pas de LIVE_READY."
        ),
        must_not_reach_live=True,
        tags=["incomplete_data", "partial_features"],
    ),
    ColdStartScenario(
        id="CS-05",
        name="Drift detector sans historique",
        description=(
            "BehavioralDriftDetector initialisé mais sans aucune baseline. "
            "Peut produire des faux positifs de dérive immédiatement."
        ),
        initial_snapshot=_base_snapshot(
            anomaly_count=2,
            regime_stability=0.65,
        ),
        expected_behavior=(
            "anomaly_count réduit le warmup_score. "
            "Doit progresser lentement — attendre stabilisation avant SHADOW_MODE."
        ),
        must_not_reach_live=True,
        tags=["drift_detector", "false_positive"],
    ),
    ColdStartScenario(
        id="CS-06",
        name="Portfolio snapshot corrompu",
        description=(
            "databases/positions_snapshot.json contient du JSON invalide. "
            "Sizing basé sur ce snapshot serait faux."
        ),
        initial_snapshot=_base_snapshot(
            open_positions_unknown=True,
        ),
        expected_behavior=(
            "inv_no_unknown_positions échoue → invariant critique. "
            "Doit transitionner vers FAILED immédiatement."
        ),
        must_fail=True,
        tags=["corrupted_data", "positions"],
    ),
    ColdStartScenario(
        id="CS-07",
        name="Warm boot avec cache obsolète",
        description=(
            "startup_cache.py charge des configs depuis 48h. "
            "Le régime détecté à l'époque ne correspond plus au marché actuel."
        ),
        initial_snapshot=_base_snapshot(
            regime_last_updated_ts=time.time() - 48 * 3600,  # 48h
            regime_stability=0.30,
        ),
        expected_behavior=(
            "inv_regime_not_stale avertit (non critique). "
            "regime_stability bas → bloqué en STABILIZING_REGIMES. "
            "Doit attendre re-stabilisation régime."
        ),
        must_not_reach_live=True,
        tags=["stale_cache", "old_regime"],
    ),
    ColdStartScenario(
        id="CS-08",
        name="Transition cache vide",
        description=(
            "Premier boot ou cache purgé. _p8_transition_cache = None. "
            "L'allocateur ne peut pas faire de pré-positionnement régime."
        ),
        initial_snapshot=_base_snapshot(
            transition_cache_populated=False,
        ),
        expected_behavior=(
            "transition_cache_populated=False réduit légèrement le score. "
            "Ne doit pas bloquer — le système peut démarrer sans transition cache. "
            "Doit atteindre LIVE_READY si les autres métriques sont bonnes."
        ),
        must_not_reach_live=False,
        tags=["empty_cache", "first_boot"],
    ),
    ColdStartScenario(
        id="CS-09",
        name="Reboot pendant trade ouvert",
        description=(
            "Le système redémarre alors qu'une position est ouverte sur l'exchange "
            "mais n'est pas enregistrée dans le snapshot local."
        ),
        initial_snapshot=_base_snapshot(
            open_positions_unknown=True,
            hard_limits_ok=True,
        ),
        expected_behavior=(
            "inv_no_unknown_positions échoue (critique). "
            "FAILED immédiat — ne jamais trader avec des positions inconnues."
        ),
        must_fail=True,
        tags=["open_position", "inconsistency"],
    ),
    ColdStartScenario(
        id="CS-10",
        name="API latency extrême",
        description=(
            "L'exchange répond mais avec 15-30s de latence. "
            "Les données arrivent mais très lentement — timeout cascade possible."
        ),
        initial_snapshot=_base_snapshot(
            symbols_ready=30,  # seulement 30% à temps
            avg_feature_confidence=0.60,
            regime_stability=0.40,
        ),
        expected_behavior=(
            "Progression lente mais possible si les symboles arrivent progressivement. "
            "Ne doit pas FAIL si les données arrivent avant timeout. "
            "Doit logger la dégradation de couverture."
        ),
        must_not_reach_live=True,  # couverture insuffisante
        tags=["high_latency", "slow_data"],
    ),
    ColdStartScenario(
        id="CS-11",
        name="LM Studio indisponible",
        description=(
            "Le service LM Studio local (port :1234) ne répond pas. "
            "L'AIAdvisor doit basculer sur les règles heuristiques (fallback)."
        ),
        initial_snapshot=_base_snapshot(
            avg_feature_confidence=0.80,
            regime_stability=0.75,
            # LM Studio indisponible → avg_feature_confidence légèrement réduit
            # (le fallback est moins précis mais fonctionnel)
        ),
        expected_behavior=(
            "Doit progresser normalement avec le fallback rules. "
            "avg_feature_confidence légèrement plus bas mais suffisant. "
            "Doit atteindre LIVE_READY avec un score réduit mais acceptable."
        ),
        must_not_reach_live=False,
        tags=["lm_studio_down", "fallback"],
    ),
    ColdStartScenario(
        id="CS-12",
        name="Reprise après 72h offline",
        description=(
            "Le système était arrêté depuis 72h. "
            "Régime périmé, DWE sans nouvelles données, probation states gelés. "
            "Le marché a potentiellement changé de régime plusieurs fois."
        ),
        initial_snapshot=_base_snapshot(
            regime_last_updated_ts=time.time() - 72 * 3600,
            regime_stability=0.10,
            dwe_sample_coverage=0.0,  # compteurs DWE expirés
            transition_cache_populated=False,
            evolution_memory_loaded=True,  # mémoire chargée mais obsolète
        ),
        expected_behavior=(
            "Régime périmé → avertissement inv_regime_not_stale. "
            "regime_stability très bas → bloqué en STABILIZING_REGIMES longtemps. "
            "DWE coverage nul → warmup_score réduit. "
            "Doit reconstruire la confiance progressivement — pas de raccourci."
        ),
        must_not_reach_live=True,
        tags=["long_downtime", "stale_everything"],
    ),
]

# Index par ID pour accès rapide
SCENARIOS_BY_ID: dict[str, ColdStartScenario] = {s.id: s for s in SCENARIOS}


def get_scenario(scenario_id: str) -> ColdStartScenario:
    """Récupère un scénario par son ID (ex: 'CS-01')."""
    if scenario_id not in SCENARIOS_BY_ID:
        raise ValueError(f"Scénario inconnu: {scenario_id}")
    return SCENARIOS_BY_ID[scenario_id]
