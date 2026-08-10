# Audit de Duplication — crypto_ai_terminal

**Date :** 2026-06-01 (mis à jour — audit complet ligne par ligne)  
**Méthodologie :** Glob + Read + comparaison API / imports actifs

---

## 1. strategy_factory/ (racine) vs quant_hedge_ai/strategy_factory/

### Fichiers racine
| Fichier | Rôle |
|---|---|
| `strategy_factory/backtester.py` | Shim de compatibilité → ré-exporte `FactoryBacktester` depuis `quant_hedge_ai` (ligne 5) |
| `strategy_factory/generator.py` | Stub v1 : `StrategyGenerator.generate(n)` retourne `n` genomes aléatoires |
| `strategy_factory/genome.py` | `StrategyGenome` avec attributs aléatoires (indicator/lookback/threshold/sl/tp) |
| `strategy_factory/genetic_evolution.py` | `GeneticEvolution` : sélection top-20 + crossover/mutation |
| `strategy_factory/reproduction.py` | `ReproductionEngine.crossover(g1, g2)` |
| `strategy_factory/evolution.py` | Thin wrapper autour de `GeneticEvolution` |
| `strategy_factory/alpha_vault.py` | Stub : liste en mémoire seulement, pas de persistance |
| `strategy_factory/backtest_profiler.py` | Script CLI standalone (Sharpe/max_dd simulés, argparse) |
| `strategy_factory/__init__.py` | Vide |

### Fichiers quant_hedge_ai/strategy_factory/
| Fichier | Rôle |
|---|---|
| `backtester.py` | `FactoryBacktester` → délègue à `BacktestLab` |
| `bot_doctor_validator.py` | Validation post-génération |
| `factory_core.py` | Orchestrateur principal : `StrategyFactory`, `StrategyFactoryReport` |
| `performance_analyzer.py` | Analyse perf des candidats |
| `strategy_generator.py` | `FactoryStrategyGenerator` → délègue à `GeneticOptimizer` + `StrategyGenerator` |
| `multi_timeframe_backtester.py` | Backtester MTF |
| `__init__.py` | Exporte `StrategyFactory`, `StrategyFactoryReport` |

### Analyse
- `strategy_factory/backtester.py` est **explicitement marqué DEPRECATED** (ligne 2) : c'est une couche de compatibilité ascendante correcte.
- Les autres fichiers racine (`genome.py`, `genetic_evolution.py`, `reproduction.py`, `evolution.py`, `alpha_vault.py`) sont des **stubs de première génération** — logique réelle migrée dans `quant_hedge_ai/agents/strategy/`. Aucune référence active trouvée hors de ce groupe.
- `backtest_profiler.py` est un **script CLI isolé**, pas de duplication fonctionnelle.

---

## 2. tracker_system/backtest/ vs tracker_system/backtesting/

| Répertoire | Fichiers | Rôle |
|---|---|---|
| `tracker_system/backtest/` | `backtest_engine.py` | `BacktestEngine` autonome : simule trading complet avec `safe_mode`, `use_auto_decisions` ; importe `binance_client`, `auto_orchestrator`, `safe_framework` |
| `tracker_system/backtesting/` | `auto_backtester.py`, `simulator.py`, `__init__.py` | Grid search sur paramètres TP/SL/trailing (`auto_backtester.py`) + `simulate_trade()` qui appelle `ExitEngine.check_path()` (`simulator.py`). **Utilisés activement** |

### Analyse
- Pas de duplication fonctionnelle directe : `backtest_engine.py` est un moteur **complet** (capital initial, exchange, decisions system) tandis que `backtesting/simulator.py` est un simulateur **unitaire** (relecture d'un price_path avec exit rules).
- `backtest_engine.py` importe des dépendances qui n'existent probablement plus à la racine (`auto_orchestrator`, `safe_framework`) → probable LEGACY.

---

## 3. tracker_system/engine/ vs tracker_system/exit_engine/

| Répertoire | Verdict |
|---|---|
| `tracker_system/engine/` | **ACTIF** — `ExitEngine`, `CompositeExitEngine`, `exit_factory.py`, règles TP/SL/trailing/breakeven |
| `tracker_system/exit_engine/` | **N'EXISTE PAS** — aucun fichier trouvé (glob retourne zéro résultat) |

Pas de duplication.

---

## 4. dashboard/ (racine) vs quant_hedge_ai/dashboard/

| Fichier | Contenu | Rôle |
|---|---|---|
| `dashboard/alert_dashboard.py` | `load_audit()` → lit `alerts_audit.jsonl`, normalise deux formats JSON | Lecteur d'audit alertes |
| `dashboard/__init__.py` | Vide | — |
| `quant_hedge_ai/dashboard/live_snapshot.py` | `write_snapshot()` → écriture atomique JSON (`tmp → rename`) | Snapshot live pour dashboards externes |
| `quant_hedge_ai/dashboard/__init__.py` | Vide | — |

### Analyse
Fonctions **orthogonales** : `alert_dashboard.py` lit un fichier JSONL d'audit ; `live_snapshot.py` écrit un JSON de snapshot d'état. Aucune duplication.

---

## 5. global_risk_gate.py (risk/) vs quant_hedge_ai/agents/risk/global_risk_gate.py

| Attribut | `risk/global_risk_gate.py` | `quant_hedge_ai/agents/risk/global_risk_gate.py` |
|---|---|---|
| **Classe** | `GlobalRiskGate` | `GlobalRiskGate` (même nom) |
| **API principale** | `async check(portfolio_agent, strategy_scoreboard, market_db)` → `RiskSnapshot` | `check(signal_result, ...)` → `GateResult` + `check_packet(packet, ...)` → `GateResult` |
| **Modèle** | 4 conditions systémiques ; niveaux `SAFE/WARNING/CRITICAL` ; cooldown 5 min ; `size_factor` dans snapshot | 5 conditions pré-trade ; blacklist régimes ; seuils adaptatifs (regret delta, ATE) ; intégration DecisionPacket |
| **Dépendances** | `portfolio_agent`, `strategy_scoreboard`, `market_db`, numpy, asyncio | `SessionGuard`, `DrawdownGuard`, `MarketRegimeClassifier`, event_bus |
| **Lignes** | ~230 | ~627 |
| **Utilisé dans** | Anciennement `main_v91.py` — aucune importation active détectée | `core/advisor_loop.py` ligne 737 |

### Analyse
Les deux fichiers partagent le même nom de classe mais ont des **API incompatibles** (async vs sync, granularité différente). La version `risk/` est l'ancienne version pour `main_v91.py` ; la version `quant_hedge_ai/` est la version canonique du pipeline décisionnel actuel.

---

## 6. Fichiers .py à la racine directe

Seul `__init__.py` existe à la racine (vide). Aucun script standalone supplémentaire.

---

## Tableau récapitulatif

| Fichier / Groupe | Statut | Justification |
|---|---|---|
| `strategy_factory/backtester.py` | **LEGACY** | Shim DEPRECATED ; ré-export vers qhai |
| `strategy_factory/genome.py` | **DELETE_CANDIDATE** | Stub v1 ; logique migrée dans `quant_hedge_ai/agents/strategy/` |
| `strategy_factory/genetic_evolution.py` | **DELETE_CANDIDATE** | Idem |
| `strategy_factory/reproduction.py` | **DELETE_CANDIDATE** | Idem |
| `strategy_factory/evolution.py` | **DELETE_CANDIDATE** | Thin wrapper sur stub ci-dessus |
| `strategy_factory/alpha_vault.py` | **DELETE_CANDIDATE** | Stub sans persistance ; non utilisé |
| `strategy_factory/generator.py` | **DELETE_CANDIDATE** | Stub v1 ; supplanté par `quant_hedge_ai/strategy_factory/strategy_generator.py` |
| `strategy_factory/backtest_profiler.py` | **LEGACY** | Script CLI isolé ; outil de benchmark offline |
| `tracker_system/backtest/backtest_engine.py` | **LEGACY** | Imports probablement brisés ; non câblé dans pipeline actif |
| `tracker_system/backtesting/` | **ACTIVE** | `auto_backtester` + `simulator` utilisés activement |
| `tracker_system/engine/` | **ACTIVE** | Source de vérité pour les règles de sortie |
| `dashboard/alert_dashboard.py` | **ACTIVE** | Lecteur audit alertes ; logique unique |
| `quant_hedge_ai/dashboard/live_snapshot.py` | **ACTIVE** | Snapshot live ; logique unique |
| `risk/global_risk_gate.py` | **LEGACY** | Ancienne version async pour main_v91 ; supplanté par qhai version |
| `quant_hedge_ai/agents/risk/global_risk_gate.py` | **ACTIVE** | Version canonique avec DecisionPacket ; utilisée dans advisor_loop |

---

## Actions prioritaires

1. **Supprimer `strategy_factory/` (sauf `backtest_profiler.py`)** — 6 fichiers DELETE_CANDIDATE. Vérifier préalablement avec `grep -r "from strategy_factory"` qu'aucun import actif ne subsiste (seul le shim DEPRECATED a été trouvé).

2. **Archiver `risk/global_risk_gate.py`** — même nom de classe, API incompatible avec la version active. Risque de confusion lors d'imports wildcards ou de refactorings.

3. **Vérifier `tracker_system/backtest/backtest_engine.py`** — les imports `auto_orchestrator` et `safe_framework` sont probablement brisés depuis la migration P5. Si les tests passent sans ce fichier, le déplacer dans `_ARCHIVE_2026/`.

4. **Ajouter un test d'import CI** sur `strategy_factory/backtester.py` avant suppression pour s'assurer que le shim n'est plus référencé.

---

## 1. `strategy_factory/` (racine) vs `quant_hedge_ai/strategy_factory/`

| Fichier | Emplacement 1 | Emplacement 2 | Verdict |
|---------|--------------|--------------|---------|
| `backtester.py` | `strategy_factory/backtester.py` (d84284b7) | `quant_hedge_ai/strategy_factory/backtester.py` (1d497de6) | **DIVERGE** — deux versions actives |
| `alpha_vault.py` | `strategy_factory/alpha_vault.py` | — | **SEUL RACINE** — pas de doublon |
| `backtest_profiler.py` | `strategy_factory/backtest_profiler.py` | — | **SEUL RACINE** |
| `evolution.py` | `strategy_factory/evolution.py` | — | **SEUL RACINE** |
| `generator.py` | `strategy_factory/generator.py` | — | **SEUL RACINE** |
| `genetic_evolution.py` | `strategy_factory/genetic_evolution.py` | — | **SEUL RACINE** |
| `genome.py` | `strategy_factory/genome.py` | — | **SEUL RACINE** |
| `reproduction.py` | `strategy_factory/reproduction.py` | — | **SEUL RACINE** |
| `bot_doctor_validator.py` | — | `quant_hedge_ai/strategy_factory/bot_doctor_validator.py` | **SEUL QHA** |
| `factory_core.py` | — | `quant_hedge_ai/strategy_factory/factory_core.py` | **SEUL QHA** |
| `multi_timeframe_backtester.py` | — | `quant_hedge_ai/strategy_factory/multi_timeframe_backtester.py` | **SEUL QHA** |
| `performance_analyzer.py` | — | `quant_hedge_ai/strategy_factory/performance_analyzer.py` | **SEUL QHA** |
| `strategy_generator.py` | — | `quant_hedge_ai/strategy_factory/strategy_generator.py` | **SEUL QHA** |

**Verdict global :** Les deux `strategy_factory/` sont complémentaires, pas des doublons réels.
La racine contient les modules génétiques/évolutionnaires ; QHA contient les modules de production.
`backtester.py` est le seul vrai doublon — vérifier lequel est importé dans `main_v91.py`.

**Action recommandée :** Fusionner en un seul dossier `quant_hedge_ai/strategy_factory/` et déplacer
les 8 fichiers racine. Vérifier et mettre à jour les imports de `strategy_factory.backtester`.

---

## 2. `tracker_system/backtesting/` vs `tracker_system/backtest/`

| Fichier | `backtesting/` | `backtest/` | Verdict |
|---------|---------------|------------|---------|
| `auto_backtester.py` | ✅ | — | **SEUL backtesting/** |
| `simulator.py` | ✅ | — | **SEUL backtesting/** |
| `backtest_engine.py` | — | ✅ | **SEUL backtest/** |

**Verdict global :** Pas de doublon — les deux dossiers couvrent des responsabilités différentes.
`backtesting/` = automation + simulation ; `backtest/` = moteur d'exécution.

**Action recommandée :** Aucune fusion nécessaire. Ajouter un `__init__.py` à `backtest/` s'il manque.
Clarifier les noms : renommer `backtest/` en `backtest_engine/` pour éviter la confusion.

---

## 3. `tracker_system/engine/` vs `tracker_system/exit_engine/`

| Fichier | `engine/` | `exit_engine/` | Verdict |
|---------|----------|--------------|---------|
| `composite_exit_engine.py` | ✅ | — | **SEUL engine/** |
| `exit_engine.py` | ✅ | — | **SEUL engine/** |
| `exit_factory.py` | ✅ | — | **SEUL engine/** |
| `exit_rules.py` | ✅ | — | **SEUL engine/** |
| *(vide)* | — | ✅ (vide) | — |

**Verdict global :** `tracker_system/exit_engine/` est **VIDE** (pas de fichiers .py).
C'est un dossier fantôme — vestige d'une refactorisation incomplète.

**Action recommandée :** Supprimer `tracker_system/exit_engine/` après confirmation
qu'aucun script externe ne pointe vers ce chemin.

---

## 4. `dashboard/` (racine) vs `quant_hedge_ai/dashboard/`

| Fichier | `dashboard/` | `quant_hedge_ai/dashboard/` | Verdict |
|---------|-------------|---------------------------|---------|
| `alert_dashboard.py` | ✅ | — | **SEUL racine** |
| `live_snapshot.py` | — | ✅ | **SEUL QHA** |

**Verdict global :** Pas de doublon réel. Les deux dossiers couvrent des fonctions différentes.
Le split est conceptuellement défendable (alerting vs snapshot live).

**Action recommandée :** Fusionner dans `quant_hedge_ai/dashboard/` pour regrouper
tout le dashboard sous QHA. Déplacer `alert_dashboard.py`.

---

## 5. `core/quant/` vs `terminal_core/quant/`

| Fichier | `core/quant/` | `terminal_core/quant/` | Verdict |
|---------|-------------|----------------------|---------|
| `logging_alerts.py` | ✅ (2d147fb9) | ✅ (5bc79e50) | **DIVERGE** — deux versions |

**Verdict global :** `logging_alerts.py` a divergé entre les deux stacks.
C'est le doublon le plus risqué : si les deux sont importés dans le même process,
les comportements de logging peuvent différer silencieusement.

**Action recommandée :** Consolider dans `core/quant/logging_alerts.py` comme source canonique.
Faire pointer `terminal_core/quant/logging_alerts.py` vers `core.quant.logging_alerts` (re-export).

---

## Résumé priorisé

| Priorité | Doublon | Action | Risque |
|----------|---------|--------|--------|
| 🔴 HAUTE | `core/quant/` vs `terminal_core/quant/` (`logging_alerts.py`) | Consolider dans `core/` | Divergence silencieuse de logging |
| 🟠 MOYENNE | `strategy_factory/backtester.py` (doublon divergé) | Déterminer lequel est actif et supprimer l'autre | Import ambigu |
| 🟡 BASSE | `tracker_system/exit_engine/` (vide) | Supprimer | Zéro risque mais pollution |
| 🟢 INFO | `tracker_system/backtesting/` vs `tracker_system/backtest/` | Renommer pour clarté | Aucun |
| 🟢 INFO | `dashboard/` racine vs `quant_hedge_ai/dashboard/` | Fusionner à terme | Aucun |
