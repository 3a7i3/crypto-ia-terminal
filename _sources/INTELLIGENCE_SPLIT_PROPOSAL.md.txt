# INTELLIGENCE SPLIT — Proposition de restructuration

> Statut : **PROPOSITION** (non exécutée) | Date : 2026-06-01
> Précondition : 0 import cassé après migration | Auteur : audit arborescence

---

## Contexte

`quant_hedge_ai/agents/intelligence/` contient **36+ fichiers** couvrant 4 responsabilités distinctes.
**20 fichiers** dans le codebase importent depuis ce dossier, dont `core/advisor_loop.py` (15 imports)
et `quant_hedge_ai/main_v91.py` (6 imports).

Déplacer des fichiers casserait immédiatement la production. La stratégie proposée est
un **split progressif via re-exports** : les anciens chemins d'import restent valides.

---

## Découpage proposé

### Groupe 1 — `decision/` (4 fichiers)
Modules qui rendent des verdicts d'achat/vente.

| Fichier source | Nouveau chemin | Raison |
|---------------|----------------|--------|
| `conviction_engine.py` | `decision/conviction_engine.py` | Niveau de conviction |
| `confidence_explainer.py` | `decision/confidence_explainer.py` | Explainability |
| `decision_arbitrator.py` | `decision/decision_arbitrator.py` | Agrégation votes |
| `no_trade_layer.py` | `decision/no_trade_layer.py` | Rejet intelligent |

### Groupe 2 — `learning/` (5 fichiers)
Modules qui apprennent des erreurs passées.

| Fichier source | Nouveau chemin | Raison |
|---------------|----------------|--------|
| `mistake_memory.py` | `learning/mistake_memory.py` | Mémoire erreurs |
| `regret_engine.py` | `learning/regret_engine.py` | Trades non-pris |
| `decision_quality_engine.py` | `learning/decision_quality_engine.py` | Qualité décision |
| `meta_strategy_engine.py` | `learning/meta_strategy_engine.py` | Méta-stratégie |
| `dynamic_weighting_engine.py` | `learning/dynamic_weighting_engine.py` | Poids adaptatifs |

### Groupe 3 — `governance/` (7 fichiers)
Modules de supervision et de gouvernance opérationnelle.

| Fichier source | Nouveau chemin | Raison |
|---------------|----------------|--------|
| `chief_officer.py` | `governance/chief_officer.py` | Copilote IA |
| `threat_radar.py` | `governance/threat_radar.py` | 12e couche décision |
| `self_awareness_engine.py` | `governance/self_awareness_engine.py` | Dérive comportementale |
| `proactive_alerts.py` | `governance/proactive_alerts.py` | Alertes proactives |
| `weekly_report.py` | `governance/weekly_report.py` | Rapport hebdo |
| `performance_supervisor.py` | `governance/performance_supervisor.py` | Supervision perf |
| `self_monitoring_loop.py` | `governance/self_monitoring_loop.py` | Boucle auto-monitoring |

### Groupe 4 — Rester dans `intelligence/` (fichiers transverses)
Ces fichiers ont trop de dépendances croisées pour être déplacés maintenant.

| Fichier | Raison de rester |
|---------|-----------------|
| `ai_advisor.py` | Orchestrateur central — importe des 3 autres groupes |
| `black_box.py` | Boîte noire système entier |
| `feature_engineer.py` | Partagé par execution/ et intelligence/ |
| `regime_detector.py` | Partagé par market/ et intelligence/ |
| `behavioral_drift_detector.py` | Dépend de self_awareness |
| `behavioral_stability_monitor.py` | Dépend de behavioral_drift |
| `market_regime_classifier.py` | Proche de regime_detector |
| `activity_tracker.py` | Transverse |
| `adaptive_threshold_engine.py` | Transverse |
| `confidence_scorer.py` | Transverse |
| `correlation_monitor.py` | Transverse |

---

## Stratégie de migration — 4 phases

### Phase 1 — Préparer les nouveaux dossiers (SAFE)
```bash
# Créer les dossiers avec __init__.py vide
mkdir -p decision/ learning/ governance/
touch decision/__init__.py learning/__init__.py governance/__init__.py
```

### Phase 2 — Copier (pas déplacer) les fichiers
```bash
# Copier sans supprimer les originaux
cp quant_hedge_ai/agents/intelligence/conviction_engine.py decision/
cp quant_hedge_ai/agents/intelligence/confidence_explainer.py decision/
# ... etc
```

### Phase 3 — Re-exports dans les `__init__.py` source
Ajouter dans `quant_hedge_ai/agents/intelligence/__init__.py` :
```python
# Re-exports de compatibilité (à supprimer dans 3 mois)
from decision.conviction_engine import ConvictionEngine  # noqa: F401
from decision.decision_arbitrator import DecisionArbitrator, AgentVote  # noqa: F401
```
Les anciens imports comme `from quant_hedge_ai.agents.intelligence.decision_arbitrator import AgentVote`
continuent de fonctionner via les re-exports.

### Phase 4 — Migration progressive des imports (sur 2-3 semaines)
Fichier par fichier, mettre à jour les imports dans `advisor_loop.py` et `main_v91.py`.
Vérifier les tests après chaque fichier.

---

## Commandes de vérification

```bash
# Avant toute migration : baseline
python -m pytest tests/ -x -q 2>&1 | tail -5

# Vérifier un module spécifique
python -c "from quant_hedge_ai.agents.intelligence.decision_arbitrator import AgentVote; print('OK')"

# Compter les imports à migrer pour un fichier donné
grep -rn "conviction_engine" --include="*.py" | grep -v "test_" | grep -v "__pycache__"

# Après migration : vérifier zéro régression
python -m pytest tests/ -q 2>&1 | tail -5
```

---

## Priorité recommandée

| Ordre | Fichier | Raison |
|-------|---------|--------|
| 1 | `decision_arbitrator.py` → `decision/` | Importé seulement par `advisor_loop.py` |
| 2 | `conviction_engine.py` → `decision/` | Importé par 2 fichiers |
| 3 | `regret_engine.py` → `learning/` | Importé par 1 fichier |
| 4 | `mistake_memory.py` → `learning/` | Importé par 1 fichier |
| 5+ | Autres | En fonction des test results |

**NE PAS migrer en premier :** `confidence_explainer.py`, `regime_detector.py`, `feature_engineer.py`
(trop de dépendances croisées).

---

## Critères de succès

- ✅ `python -m pytest tests/ -q` : même nombre de tests passants qu'avant
- ✅ `python -c "from core.advisor_loop import *"` : pas d'ImportError
- ✅ `python quant_hedge_ai/main_v91.py --dry-run` : démarre sans erreur
- ✅ Aucun `from intelligence.xxx` dans les fichiers migrés (imports mis à jour)
