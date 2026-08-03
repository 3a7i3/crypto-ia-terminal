# AMPUTATION_PLAN.md — Proposition de classement, aucune suppression

> **Document généré automatiquement.** Régénérer via `python tools/amputation_plan.py`.
> Généré le 2026-08-01 — dépôt `348e83d`.

> ## ⚠ AUCUNE SUPPRESSION N'EST PROPOSÉE À CE STADE
> Ce document **classe**. Le passage du classement à l'action exige une
> validation humaine explicite, et — pour toute classe autre que `DEAD`
> à confiance `ÉLEVÉE` — une fenêtre d'observation supplémentaire.

## 1. Les trois sources de preuve

| Source | Nature | Ce qu'elle prouve |
|---|---|---|
| `artifacts/cartography.json` | statique (AST) | atteignabilité par import |
| `artifacts/prod_executed_modules.txt` | **exécution réelle** | 210 modules dont le `.pyc` a été écrit par le processus de production (PID 62316) |
| `artifacts/prod_deployed_files.txt` | déploiement | 1115 fichiers `.py` présents sur le VPS |

### Pourquoi l'analyse statique ne suffisait pas

**52 modules classés `ORPHAN` ou `TEST_ONLY` par l'analyse statique sont exécutés en production.** Une amputation fondée sur le seul graphe d'import aurait supprimé du code vivant, dont :

- `event_bus/bridge.py` (307 LOC) — classé `TEST_ONLY`, **exécuté**
- `governance/trading_authority.py` (303 LOC) — classé `ORPHAN`, **exécuté**
- `quant_hedge_ai/agents/quant/backtest_lab.py` (274 LOC) — classé `TEST_ONLY`, **exécuté**
- `paper_trading/engine.py` (271 LOC) — classé `TEST_ONLY`, **exécuté**
- `quant_hedge_ai/ai_evolution/evolution_engine.py` (244 LOC) — classé `TEST_ONLY`, **exécuté**
- `supervision/kill_switch.py` (240 LOC) — classé `ORPHAN`, **exécuté**
- `paper_trading/ledger.py` (239 LOC) — classé `TEST_ONLY`, **exécuté**
- `quant_hedge_ai/runtime/chaos_orchestrator.py` (230 LOC) — classé `TEST_ONLY`, **exécuté**

Cause mesurée : les `__init__.py` de package importent transitivement leurs sous-modules ; mon analyseur ne modélisait pas cet effet. **C'est la justification empirique de l'exigence de preuve d'exécution.**

## 2. Limites de la preuve d'exécution

| Limite | Conséquence |
|---|---|
| Un `.pyc` prouve **au moins un** import depuis le déploiement, pas un import à chaque cycle | `ACTIVE` ne signifie pas « utilisé en permanence » |
| Fenêtre d'observation courte (processus démarré le 2026-08-01 20:53) | des branches paresseuses n'ont pas encore été prises → **210 est une borne INFÉRIEURE** |
| CPython n'écrit pas de `.pyc` pour le script `__main__` | `core/advisor_loop.py` est exempté explicitement |
| Le code de production est le commit `f427895` (2026-07-20), le dépôt local est plus récent | l'appariement prod → dépôt est imparfait pour les modules récents |
| Aucune mesure des chemins d'erreur / de reprise | un module de recovery peut n'être chargé qu'en incident |

**Règle qui en découle** : aucun module ne peut passer en `DEAD` confiance `ÉLEVÉE`
sur la seule fenêtre actuelle. Une seconde mesure après **≥ 7 jours** de runtime
continu, incluant au moins un incident et un redémarrage, est requise.

## 3. Décompte

| Classe | Modules | dont PROUVÉ | dont ÉLEVÉE | dont MOYENNE |
|---|---:|---:|---:|---:|
| `TEST` | 324 | 324 | 0 | 0 |
| `LEGACY` | 285 | 0 | 201 | 84 |
| `ACTIVE` | 211 | 211 | 0 | 0 |
| `DEAD` | 127 | 0 | 109 | 18 |
| `TOOL` | 93 | 0 | 93 | 0 |
| `EXPERIMENTAL` | 64 | 0 | 64 | 0 |
| `ACTIVE-PROBABLE` | 11 | 0 | 0 | 11 |
| **TOTAL** | **1115** | | | |

## 4. Définition des classes

| Classe | Définition | Action proposée |
|---|---|---|
| `ACTIVE` | Exécution prouvée en production | **Aucune. Ne pas toucher.** |
| `ACTIVE-PROBABLE` | Atteignable par import, non encore exécuté | **Aucune.** Observer 7 jours de plus |
| `LEGACY` | Déployé, non exécuté, mais couvert par des tests ou importé hors runtime | Geler ; candidat à `docs/_historique/` après seconde mesure |
| `EXPERIMENTAL` | Appartient à un répertoire de recherche, non exécuté | Geler ; décision à prendre avec le protocole d'expérience |
| `TOOL` | Script autonome hors runtime | Conserver ; documenter dans un registre d'outils |
| `DEAD` | Déployé ou non, jamais exécuté, aucun importeur | **Candidat à mise en quarantaine** — jamais à suppression directe |
| `TEST` | Fichier de test | Hors périmètre |

### Procédure de quarantaine proposée (à valider)

Aucune suppression. Un module retenu serait déplacé vers `_quarantine/<chemin>`
avec un fichier `_quarantine/MANIFEST.json` enregistrant chemin d'origine, classe,
confiance, preuve et date. Critère de sortie de quarantaine : **30 jours de
runtime sans incident ni `ImportError`**. Réversible par un `git mv` inverse.

## 5. Classement complet


### DEAD — 127 modules

| Fichier | LOC | Confiance | Statut statique | Déployé | Exécuté | Dernier commit | Justification |
|---|---:|---|---|:-:|:-:|---|---|
| `tools/score_calibration_audit.py` | 1233 | MOYENNE | TEST_ONLY | non | non | 2026-07-29 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `tools/experiment_quality_audit.py` | 985 | MOYENNE | TEST_ONLY | non | non | 2026-07-30 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `system/provenance.py` | 910 | MOYENNE | TEST_ONLY | non | non | 2026-07-30 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `core/invariants.py` | 743 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-02 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `tools/chain_audit.py` | 721 | MOYENNE | TEST_ONLY | non | non | 2026-07-30 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `tools/protocol_efficacy_audit.py` | 680 | MOYENNE | TEST_ONLY | non | non | 2026-07-30 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `core/formal_proof.py` | 461 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-02 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `tools/runtime_cartographer.py` | 447 | MOYENNE | TOOL | non | non | UNTRACKED | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `infra/api/api_server.py` | 418 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `system/performance_metrics.py` | 380 | MOYENNE | TEST_ONLY | non | non | 2026-07-29 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `tools/init_order_audit.py` | 378 | MOYENNE | TEST_ONLY | non | non | 2026-07-29 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `risk/global_risk_gate.py` | 328 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `errors/incident_manager.py` | 324 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/telegram/exchange_sync.py` | 316 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `health/recovery_manager.py` | 315 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `supervision/telegram_kill_switch.py` | 315 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-26 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `governance/decision_router.py` | 307 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `health/health_registry.py` | 286 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `scripts/seed_decision_packets.py` | 283 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-11 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `metrics/robustness.py` | 274 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/market_radar/radar_core.py` | 273 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-26 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `monitoring/profiler.py` | 263 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `system/kernel.py` | 261 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-26 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `governance/ai_constraints.py` | 258 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `scripts/smoke_test_ci.py` | 238 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/automate_pipeline.py` | 231 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/agents/execution/execution_optimizer.py` | 228 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/market_radar/whale_tracker.py` | 222 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-26 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/market_radar/anomaly_detector.py` | 220 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-26 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/accounts/store.py` | 218 | MOYENNE | TEST_ONLY | non | non | 2026-07-31 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `quant_hedge_ai/agents/intelligence/regime_transition_predictor.py` | 218 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `visualization/renderers/radar.py` | 206 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/accounts/trade_collector.py` | 201 | MOYENNE | TEST_ONLY | non | non | 2026-08-01 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `observation/accounts/account_collector.py` | 199 | MOYENNE | TEST_ONLY | non | non | 2026-08-01 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `quant_hedge_ai/ai_evolution/model_degradation_monitor.py` | 199 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `scripts/bear_trend_audit.py` | 193 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-24 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `visualization/renderers/pipeline.py` | 191 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/market_radar/token_scanner.py` | 190 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-26 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `visualization/renderers/equity.py` | 189 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/agents/execution/optimal_timing_engine.py` | 187 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `signal/analysis/tune.py` | 183 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-02 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/agents/execution/slippage_predictor.py` | 177 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observability/telemetry.py` | 163 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/market_radar/social_scanner.py` | 163 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-26 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/accounts/order_reader.py` | 144 | MOYENNE | TEST_ONLY | non | non | 2026-08-01 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `visualization/renderers/timeline.py` | 144 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/strategy_factory/factory_core.py` | 143 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/accounts/transfer_collector.py` | 142 | MOYENNE | TEST_ONLY | non | non | 2026-08-01 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `scripts/quickstart.py` | 131 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-05 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `scripts/toxicity_report.py` | 130 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-24 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/monitoring/surveillance_continue.py` | 127 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/accounts/position_collector.py` | 124 | MOYENNE | TEST_ONLY | non | non | 2026-08-01 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `quant_hedge_ai/runtime/health_endpoint.py` | 124 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/accounts/_semantics.py` | 116 | MOYENNE | TEST_ONLY | non | non | 2026-08-01 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `scripts/crypto_market_scanner.py` | 113 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-13 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/accounts/_common.py` | 111 | MOYENNE | TEST_ONLY | non | non | 2026-08-01 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `signal/strategies/run_strategy_factory_batch.py` | 90 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/panels/panel_ci_report.py` | 88 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/strategy_lab/feature_cache.py` | 81 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `core/orchestration/orchestrate_all.py` | 76 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/visualization/ui_utils.py` | 75 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/visualization/visualization.py` | 74 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `docs/conf.py` | 73 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `scripts/crypto_terminal.py` | 70 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-13 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/accounts/__init__.py` | 69 | MOYENNE | TEST_ONLY | non | non | 2026-08-01 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `core/orchestration/orchestrate_and_test_panels.py` | 68 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/databases/strategy_scoreboard.py` | 59 | MOYENNE | ORPHAN | non | non | 2026-04-27 | absent du VPS : jamais déployé, donc jamais exécuté — mais peut servir hors production (outil local, CI) |
| `core/orchestration/send_orchestration_notification.py` | 54 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/strategy_lab/example_pipeline.py` | 54 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `market_data/metrics/__init__.py` | 51 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `tracker_system/sessions/__init__.py` | 50 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `scripts/generate_panel_screenshots.py` | 49 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/check_imports.py` | 36 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/api/api_rest.py` | 33 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/notifications/notify_selenium_report_discord.py` | 33 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/notifications/notify_selenium_report_slack.py` | 33 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `market_data/__init__.py` | 30 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-13 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `scripts/copy_docs_for_sphinx.py` | 26 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `core/orchestration/orchestrate_internal_panels.py` | 25 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `visualization/ves/contracts.py` | 24 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `scripts/minimal_test.py` | 22 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-05 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `core/runtime_state_machine.py` | 18 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-02 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `tracker_system/risk/__init__.py` | 17 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-05 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/agents/market/microstructure/__init__.py` | 9 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-05 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/agents/onchain/__init__.py` | 9 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-05 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/agents/research/__init__.py` | 8 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-28 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/features/__init__.py` | 6 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-05 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/agents/monitoring/__init__.py` | 5 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/liquidity_map/__init__.py` | 5 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/telegram/__init__.py` | 3 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `quant_hedge_ai/strategy_lab/__init__.py` | 2 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `core/orchestration/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `health/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/api/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/dashboards/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/monitoring/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/panels/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `infra/visualization/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `runtime/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `signal/analysis/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `signal/evolution/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `signal/strategies/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/telegram/quant_observer/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `terminal_core/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `terminal_core/quant/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `visualization/renderers/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `dashboard/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-01 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `metrics/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `monitor/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `monitoring/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `observation/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-15 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `reality_checks/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-29 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/agent/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/analytics/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/backtest/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/domain/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/engine/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/events/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/execution/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/journal/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/paper/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-04 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/portfolio/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/risk/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/runtime/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `src/storage/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-08 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |
| `tracker_system/sessions/schemas/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | déployé, jamais exécuté, aucun importeur, aucun `__main__` |

### LEGACY — 285 modules

| Fichier | LOC | Confiance | Statut statique | Déployé | Exécuté | Dernier commit | Justification |
|---|---:|---|---|:-:|:-:|---|---|
| `tools/live_observer_validator.py` | 1396 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/telegram/sim_bot.py` | 1207 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-12 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tools/instrumentation_validator.py` | 1102 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `scripts/vps_burn_in_collector.py` | 1029 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-03 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `core/initialization_contract.py` | 844 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-02 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `scripts/burnin_calibration_v3.py` | 694 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-30 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `signal/strategies/run_strategy_factory.py` | 659 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `tools/dataset_certifier.py` | 643 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/recovery_playbooks.py` | 634 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `signal/evolution/evolution_core.py` | 624 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 2 module(s), tous hors exécution production |
| `scripts/prelive_gate.py` | 565 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-30 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `scripts/sqlite_contamination_cleanup.py` | 495 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `certification/module_certifier.py` | 490 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/healing_actions.py` | 486 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `execution_simulator/fill_error_metric.py` | 477 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/tracker.py` | 469 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `market_data/metrics/flow.py` | 467 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `core/execution_trace.py` | 461 | MOYENNE | ORPHAN | oui | non | 2026-06-02 | importé par 1 module(s), tous hors exécution production |
| `system/burn_in.py` | 441 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/latency_baseline_monitor.py` | 432 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `runtime/advisor_main.py` | 427 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/decision_trace_service.py` | 420 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/liquidity_map/flow_analyzer.py` | 407 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `infra/monitoring/watchdog_vps.py` | 406 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/ops_watchdog_hardened.py` | 401 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `core/contracts.py` | 398 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/risk/order_sizer.py` | 390 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-02 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/ml/exit_predictor.py` | 382 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `observation/market_radar.py` | 381 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-19 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/escalation_engine.py` | 370 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/pending_order_tracker.py` | 370 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `cold_start/warmup_invariants.py` | 369 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/burnin_analytics.py` | 367 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-03 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `cold_start/warmup_scenarios.py` | 365 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `observation/market_observer.py` | 354 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-19 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/execution/trade_postmortem.py` | 354 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tools/throughput_probe.py` | 353 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-16 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/safety/safe_execution_framework.py` | 350 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/monitoring/prompt_doctor_agent.py` | 344 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `paper_trading/virtual_portfolio.py` | 342 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-03 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `cold_start/cold_start_manager.py` | 338 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/execution/trade_replay.py` | 338 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 2 module(s), tous hors exécution production |
| `supervision/proactive_alerts.py` | 337 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/renderers/snapshot.py` | 326 | MOYENNE | ORPHAN | oui | non | 2026-07-06 | importé par 2 module(s), tous hors exécution production |
| `infra/monitoring/daily_analyzer.py` | 325 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/quant/stress_test.py` | 313 | MOYENNE | ORPHAN | oui | non | 2026-05-05 | importé par 2 module(s), tous hors exécution production |
| `infra/stream_bus.py` | 311 | MOYENNE | ORPHAN | oui | non | 2026-06-13 | importé par 1 module(s), tous hors exécution production |
| `monitor/degradation_tracker.py` | 311 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `cold_start/warmup_state_machine.py` | 308 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `signal/evolution/evolution_memory.py` | 308 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `observation/horizon_evaluator.py` | 302 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-19 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/trade_tracker.py` | 302 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `runtime/runtime_coordinator.py` | 301 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `cold_start/market_warmup_estimator.py` | 300 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `market_data/replay_engine.py` | 300 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/analytics/advanced_metrics.py` | 299 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `reality_checks/reality_gap_analyzer.py` | 292 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/portfolio/multi_asset.py` | 292 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `crypto/tamper_evident_logs.py` | 288 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `core/warm_boot.py` | 285 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-31 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tools/exit_replay.py` | 282 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-19 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/runtime/fault_containment.py` | 281 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `certification/audit_trail_final.py` | 273 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/intelligence/auto_regime_detector.py` | 270 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `certification/final_gate.py` | 269 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `market_data/models.py` | 267 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/intelligence/weekly_report.py` | 267 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `risk/circuit_breaker.py` | 267 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `scripts/health_check.py` | 264 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `core/bootstrap_integration.py` | 261 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-12 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/sessions/session_analyzer.py` | 259 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 4 module(s), tous hors exécution production |
| `metrics/oos_metrics.py` | 257 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `market_data/connectors/mexc.py` | 256 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 1 module(s), tous hors exécution production |
| `src/storage/run_repository.py` | 255 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `watchdog_vps.py` | 250 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-04 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/market/historical_fetcher.py` | 248 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-13 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `market_data/connectors/hyperliquid.py` | 245 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 1 module(s), tous hors exécution production |
| `tracker_system/backtest/backtest_engine.py` | 242 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/quant/walk_forward.py` | 238 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tools/exit_audit.py` | 238 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-17 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `governance/risk_authorizer.py` | 236 | MOYENNE | ORPHAN | oui | non | 2026-05-08 | importé par 1 module(s), tous hors exécution production |
| `certification/doc_freeze.py` | 235 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `certification/operator_signoff.py` | 225 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `monitoring/metrics.py` | 225 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-23 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `core/orchestration/orchestrate_ecosystem.py` | 223 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `cold_start/warmup_report.py` | 222 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-03 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/api/models.py` | 222 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/equity_curve.py` | 221 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/p0_integration.py` | 221 | MOYENNE | ORPHAN | oui | non | 2026-05-05 | importé par 1 module(s), tous hors exécution production |
| `observability/live_topology.py` | 218 | MOYENNE | ORPHAN | oui | non | 2026-05-08 | importé par 1 module(s), tous hors exécution production |
| `system/invariant_checker.py` | 218 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `crypto/api_key_vault.py` | 216 | ÉLEVÉE | TEST_ONLY | oui | non | UNTRACKED | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/runtime_controller.py` | 216 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 3 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/risk/risk_dashboard_api.py` | 215 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `market_data/metrics/orderbook.py` | 211 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `runtime/lifecycle_manager.py` | 209 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `capital_deployment/phase_certifier.py` | 208 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `certification/live_kpi_auditor.py` | 207 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `governance/execution_approval.py` | 207 | MOYENNE | ORPHAN | oui | non | 2026-05-08 | importé par 1 module(s), tous hors exécution production |
| `system/strategy_metrics.py` | 207 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-03 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/strategy_score.py` | 207 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `certification/prerequisite_checker.py` | 206 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/walk_forward.py` | 206 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `crypto/audit_trail.py` | 203 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/onchain/blockchain_ingester.py` | 202 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `tracker_system/risk/portfolio_risk.py` | 202 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-11 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/execution/latency_monitor.py` | 201 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `scripts/preflight.py` | 201 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/paper/paper_runner.py` | 201 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-04 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `monitoring/pipeline_monitor.py` | 199 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/features/feature_store.py` | 199 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/market/microstructure/orderbook_analyzer.py` | 196 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `runtime/system_state_bus.py` | 196 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/health_endpoint.py` | 195 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_lab/market_db.py` | 193 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `certification/immutable_stamp.py` | 190 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/telegram/notifier.py` | 190 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `crypto/secure_channels.py` | 189 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/dependency_manager.py` | 189 | MOYENNE | ORPHAN | oui | non | 2026-05-08 | importé par 3 module(s), tous hors exécution production |
| `quant_hedge_ai/features/feature_materializer.py` | 188 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `tracker_system/sessions/session_report_builder.py` | 188 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 1 module(s), tous hors exécution production |
| `system/monte_carlo.py` | 187 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `cold_start/bypass_detector.py` | 185 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/boot_gate.py` | 183 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/sessions/session_validator.py` | 183 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 2 module(s), tous hors exécution production |
| `monitoring/logger.py` | 179 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/data/canonical_market_model.py` | 179 | MOYENNE | ORPHAN | oui | non | UNTRACKED | importé par 1 module(s), tous hors exécution production |
| `supervision/ops_watchdog.py` | 178 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `market_data/stream.py` | 177 | MOYENNE | ORPHAN | oui | non | 2026-06-13 | importé par 1 module(s), tous hors exécution production |
| `system/startup_sequence.py` | 177 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `cold_start/warmup_metrics.py` | 174 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/advisor_only_mode.py` | 173 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `infra/startup_cache.py` | 172 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/onchain/whale_behavior_classifier.py` | 172 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `cold_start/warmup_signer.py` | 171 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/data/data_unifier.py` | 169 | MOYENNE | ORPHAN | oui | non | UNTRACKED | importé par 1 module(s), tous hors exécution production |
| `tracker_system/risk/execution_reality.py` | 168 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/onchain/exchange_flow_tracker.py` | 165 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `supervision/notifications/ops_notifier.py` | 165 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/runtime_config.py` | 163 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `system/regime_validator.py` | 162 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/sessions/session_manager.py` | 160 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 5 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/market/microstructure/microstructure_engine.py` | 154 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `capital_deployment/phase_gate.py` | 152 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/core/event_writer.py` | 150 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `infra/notifications/notifications.py` | 149 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `src/analytics/edge_scorer.py` | 148 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/backtest/market_generator.py` | 148 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/risk/alert_system.py` | 148 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `crypto/decision_signer.py` | 147 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `metrics/stability_score.py` | 147 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/execution/paper_trading_engine.py` | 147 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `signal/analysis/analyze_strategy_niches.py` | 147 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/sessions/session_scoring.py` | 147 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 3 module(s), tous hors exécution production |
| `runtime/execution_context.py` | 142 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `system/alpha_kill_switch.py` | 138 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-03 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `infra/lazy_loader.py` | 133 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/sessions/session_labels.py` | 130 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 2 module(s), tous hors exécution production |
| `src/execution/enl.py` | 129 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `governance/confidence_gate.py` | 127 | MOYENNE | ORPHAN | oui | non | 2026-05-08 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/data/schema_normalizer.py` | 127 | MOYENNE | ORPHAN | oui | non | UNTRACKED | importé par 1 module(s), tous hors exécution production |
| `tracker_system/sessions/session_ranking.py` | 125 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 2 module(s), tous hors exécution production |
| `visualization/api/burnin_api.py` | 121 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-04 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/sessions/session_compare.py` | 120 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 1 module(s), tous hors exécution production |
| `market_data/connectors/base.py` | 119 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 4 module(s), tous hors exécution production |
| `src/agent/rsi_extreme_strategy.py` | 113 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/analytics/alpha_pipeline.py` | 113 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/engine/exit_rules.py` | 112 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/portfolio/__init__.py` | 109 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `src/paper/paper_metrics.py` | 109 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-04 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_factory/multi_timeframe_backtester.py` | 108 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/features/feature_validator.py` | 107 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `tracker_system/engine/composite_exit_engine.py` | 107 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_factory/bot_doctor_validator.py` | 102 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/market/microstructure/spread_predictor.py` | 101 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `visualization/api/timeline_api.py` | 101 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/engine/virtual_exchange.py` | 100 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tools/scan_load_probe.py` | 100 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-16 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/backtest/engine.py` | 99 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/analytics/bootstrap_stability.py` | 94 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/api/regret_api.py` | 92 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/renderers/base.py` | 92 | MOYENNE | ORPHAN | oui | non | 2026-07-06 | importé par 7 module(s), tous hors exécution production |
| `quant_hedge_ai/features/feature_registry.py` | 89 | MOYENNE | ORPHAN | oui | non | 2026-05-05 | importé par 1 module(s), tous hors exécution production |
| `src/paper/paper_report.py` | 89 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-04 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/analytics/regime_detector.py` | 86 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/api/scientific_api.py` | 86 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/paper/paper_position_manager.py` | 85 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-04 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/domain/trade_event.py` | 83 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/engine/decision_engine.py` | 80 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/backtest/mexc_feed.py` | 79 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/analytics/is_oos_splitter.py` | 77 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/bot_doctor.py` | 74 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/ves/router.py` | 72 | MOYENNE | ORPHAN | oui | non | 2026-07-06 | importé par 1 module(s), tous hors exécution production |
| `visualization/api/health_api.py` | 71 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/analytics/performance_breakdown.py` | 70 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/journal/trade_logger.py` | 69 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/analytics/replay_engine.py` | 66 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/api/datasets_api.py` | 64 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `infra/monitoring/supervise_all.py` | 60 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-29 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/agent/rsi_strategy.py` | 58 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `core/quant/logging_alerts.py` | 55 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_lab/strategy_db.py` | 55 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/api/__init__.py` | 54 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/whales/__init__.py` | 53 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `signal/analysis/clustering.py` | 53 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `dashboard/alert_dashboard.py` | 51 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-01 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `scripts/population_csv_validator.py` | 51 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `src/agent/sma_strategy.py` | 49 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `signal/analysis/automl_tuning.py` | 48 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `src/risk/regime_gate.py` | 48 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/agent/momentum_strategy.py` | 47 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `scripts/pareto_front.py` | 46 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `visualization/api/system_snapshot_source.py` | 46 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/ves/registry.py` | 46 | MOYENNE | ORPHAN | oui | non | 2026-07-06 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/strategy_factory/performance_analyzer.py` | 43 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `signal/analysis/sensitivity_analysis.py` | 43 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `visualization/api/pipeline_api.py` | 43 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `infra/visualization/timeline_animation.py` | 42 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/strategy_lab/signal_builder.py` | 42 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_lab/evolution_engine.py` | 39 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/analytics/significance_gate.py` | 39 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/backtest/metrics.py` | 38 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/sessions/schemas/metrics_schema.py` | 38 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 1 module(s), tous hors exécution production |
| `infra/config_utils.py` | 36 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `src/agent/breakout_strategy.py` | 36 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/paper/paper_gate.py` | 35 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-04 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/portfolio/portfolio_state.py` | 35 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/api/portfolio_api.py` | 35 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-05 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/events/event_bus.py` | 34 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-12 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/notifications/slack_notifier.py` | 34 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `scripts/export_latex_md.py` | 31 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/research/paper_analyzer.py` | 30 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/strategy_factory/strategy_generator.py` | 29 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `src/runtime/simulator.py` | 29 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/strategy/rl_trader.py` | 28 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `tracker_system/sessions/schemas/trade_schema.py` | 27 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 1 module(s), tous hors exécution production |
| `src/backtest/walk_forward.py` | 26 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `tracker_system/sessions/schemas/session_schema.py` | 26 | MOYENNE | ORPHAN | oui | non | 2026-05-14 | importé par 2 module(s), tous hors exécution production |
| `visualization/api/decision_api.py` | 26 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-06 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/quant/monte_carlo.py` | 25 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `cold_start/__init__.py` | 24 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_lab/parallel_engine.py` | 23 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/notifications/multi_notifier.py` | 23 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/research/strategy_researcher.py` | 22 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `quant_hedge_ai/strategy_lab/parameter_space.py` | 22 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/notifications/email_notifier.py` | 22 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/monitoring/performance_monitor.py` | 21 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/research/model_builder.py` | 20 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/market/volatility_agent.py` | 19 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `src/agent/codex_agent.py` | 19 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/runtime/run_context.py` | 19 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `supervision/custom_module.py` | 19 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/quant/portfolio_optimizer.py` | 18 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/strategy_lab/ranker.py` | 18 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_lab/batch_runner.py` | 17 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/research/feature_engineer.py` | 16 | MOYENNE | ORPHAN | oui | non | 2026-05-26 | importé par 1 module(s), tous hors exécution production |
| `src/risk/live_gate.py` | 16 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/market_radar/__init__.py` | 15 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/strategy_lab/backtest_launcher.py` | 14 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/backtest/data_feed.py` | 14 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_factory/backtester.py` | 13 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/strategy_lab/templates.py` | 13 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/domain/position.py` | 13 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/monitoring/system_monitor.py` | 12 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `market_data/connectors/__init__.py` | 11 | MOYENNE | ORPHAN | oui | non | 2026-06-13 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/strategy_lab/generator.py` | 11 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/domain/order.py` | 11 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/engine/execution_router.py` | 11 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/execution/liquidity_agent.py` | 10 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/market/orderflow_agent.py` | 10 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/execution/arbitrage_agent.py` | 9 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 2 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/market/regime_detector.py` | 9 | MOYENNE | ORPHAN | oui | non | 2026-05-05 | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/agents/risk/drawdown_guard.py` | 9 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `quant_hedge_ai/agents/risk/risk_monitor.py` | 9 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/risk/kill_switch.py` | 9 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/domain/signal.py` | 8 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `src/agent/strategy_interface.py` | 6 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-08 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `visualization/ves/__init__.py` | 6 | MOYENNE | ORPHAN | oui | non | 2026-07-06 | importé par 2 module(s), tous hors exécution production |
| `quant_hedge_ai/data/__init__.py` | 5 | MOYENNE | ORPHAN | oui | non | UNTRACKED | importé par 1 module(s), tous hors exécution production |
| `quant_hedge_ai/strategy_factory/__init__.py` | 5 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `terminal_core/quant/logging_alerts.py` | 5 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |
| `visualization/__init__.py` | 3 | MOYENNE | ORPHAN | oui | non | 2026-07-06 | importé par 1 module(s), tous hors exécution production |
| `core/quant/__init__.py` | 1 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-27 | atteignable uniquement depuis les tests : couvert par des tests mais absent du chemin de production |
| `infra/notifications/__init__.py` | 1 | MOYENNE | ORPHAN | oui | non | 2026-05-29 | importé par 1 module(s), tous hors exécution production |
| `supervision/notifications/__init__.py` | 1 | MOYENNE | ORPHAN | oui | non | 2026-04-27 | importé par 1 module(s), tous hors exécution production |

### EXPERIMENTAL — 64 modules

| Fichier | LOC | Confiance | Statut statique | Déployé | Exécuté | Dernier commit | Justification |
|---|---:|---|---|:-:|:-:|---|---|
| `dip/modules/decision_graph.py` | 659 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/cli.py` | 591 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/causal_tree.py` | 525 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `analysis/base.py` | 495 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-31 | appartient à `analysis/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/knowledge_base.py` | 469 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/decision_timeline.py` | 450 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/brain.py` | 447 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/ai_investigator.py` | 446 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `sdos_terminal/api/app.py` | 432 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | appartient à `sdos_terminal/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/counterfactual.py` | 424 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/core/store.py` | 419 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/decision_heatmap.py` | 403 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/decision_alert.py` | 399 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/explainability.py` | 399 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/decision_export.py` | 366 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `analysis/hypotheses.py` | 340 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-31 | appartient à `analysis/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/decision_replay.py` | 338 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `audit/decision_ledger.py` | 332 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-08 | appartient à `audit/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/decision_diff.py` | 307 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/audit_trail.py` | 305 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/decision_sankey.py` | 295 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `walk_forward/reporter.py` | 287 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | appartient à `walk_forward/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/audit_commits.py` | 241 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `analysis/regime_audit.py` | 239 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-07-31 | appartient à `analysis/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/surveillance.py` | 222 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/securite.py` | 220 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/evolution.py` | 211 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/dashboard/tableau_bord.py` | 197 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-28 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `walk_forward/engine.py` | 195 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | appartient à `walk_forward/`, répertoire de recherche ; déployé mais non exécuté |
| `walk_forward/walk_forward_loop.py` | 186 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | appartient à `walk_forward/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/resilience.py` | 182 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-06-13 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/performance.py` | 173 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `audit/trade_audit.py` | 163 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | appartient à `audit/`, répertoire de recherche ; déployé mais non exécuté |
| `audit/replay_engine.py` | 156 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | appartient à `audit/`, répertoire de recherche ; déployé mais non exécuté |
| `walk_forward/window_splitter.py` | 153 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-14 | appartient à `walk_forward/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/incidents/models.py` | 148 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-28 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/guerison.py` | 147 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/memoire.py` | 145 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `audit/decision_trace.py` | 135 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | appartient à `audit/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/core/observer.py` | 105 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `meta_learning/learner.py` | 101 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | appartient à `meta_learning/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/base.py` | 101 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `meta_learning/decision_engine.py` | 89 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | appartient à `meta_learning/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/incidents/store.py` | 89 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-26 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/bootstrap.py` | 84 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `meta_learning/memory.py` | 62 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | appartient à `meta_learning/`, répertoire de recherche ; déployé mais non exécuté |
| `meta_learning/similarity.py` | 54 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-05-05 | appartient à `meta_learning/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/__init__.py` | 24 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/tentacles/__init__.py` | 21 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-28 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/__init__.py` | 20 | ÉLEVÉE | TEST_ONLY | oui | non | 2026-04-28 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `audit/__init__.py` | 12 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-05 | appartient à `audit/`, répertoire de recherche ; déployé mais non exécuté |
| `meta_learning/__init__.py` | 12 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-25 | appartient à `meta_learning/`, répertoire de recherche ; déployé mais non exécuté |
| `S2/__init__.py` | 9 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-25 | appartient à `S2/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/__main__.py` | 7 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/incidents/__init__.py` | 4 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-28 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `pieuvre/dashboard/__init__.py` | 3 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-28 | appartient à `pieuvre/`, répertoire de recherche ; déployé mais non exécuté |
| `sdos_terminal/__init__.py` | 3 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | appartient à `sdos_terminal/`, répertoire de recherche ; déployé mais non exécuté |
| `ai_autonomous_loop/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-04-27 | appartient à `ai_autonomous_loop/`, répertoire de recherche ; déployé mais non exécuté |
| `analysis/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-28 | appartient à `analysis/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/core/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `dip/modules/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-06-30 | appartient à `dip/`, répertoire de recherche ; déployé mais non exécuté |
| `sdos_terminal/api/__init__.py` | 1 | ÉLEVÉE | ORPHAN | oui | non | 2026-07-06 | appartient à `sdos_terminal/`, répertoire de recherche ; déployé mais non exécuté |
| `project_os/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | appartient à `project_os/`, répertoire de recherche ; déployé mais non exécuté |
| `walk_forward/__init__.py` | 0 | ÉLEVÉE | ORPHAN | oui | non | 2026-05-14 | appartient à `walk_forward/`, répertoire de recherche ; déployé mais non exécuté |

### TOOL — 93 modules

| Fichier | LOC | Confiance | Statut statique | Déployé | Exécuté | Dernier commit | Justification |
|---|---:|---|---|:-:|:-:|---|---|
| `quant_hedge_ai/main_v91.py` | 1111 | ÉLEVÉE | TOOL | oui | non | 2026-06-12 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/data_verifier.py` | 971 | ÉLEVÉE | TOOL | oui | non | 2026-06-13 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/regret_audit.py` | 823 | ÉLEVÉE | TOOL | oui | non | 2026-06-23 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/boot_system_validator.py` | 734 | ÉLEVÉE | TOOL | oui | non | 2026-06-13 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `project_os/reporter.py` | 531 | ÉLEVÉE | TOOL | oui | non | 2026-05-14 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `project_os/dep_mapper.py` | 525 | ÉLEVÉE | TOOL | oui | non | 2026-05-14 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/audit_r2.py` | 505 | ÉLEVÉE | TOOL | oui | non | 2026-06-23 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/stream_bus_simulation.py` | 495 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `certification/p10_checker.py` | 471 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `quant_hedge_ai/bench_boot_constructors.py` | 451 | ÉLEVÉE | TOOL | oui | non | 2026-06-13 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/counterfactual_replay.py` | 444 | ÉLEVÉE | TOOL | oui | non | 2026-06-23 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `tools/generate_miniature.py` | 439 | ÉLEVÉE | TOOL | oui | non | 2026-05-31 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `project_os/doc_indexer.py` | 373 | ÉLEVÉE | TOOL | oui | non | 2026-05-14 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `project_os/scanner.py` | 356 | ÉLEVÉE | TOOL | oui | non | 2026-05-14 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `quant_hedge_ai/bench_session_contention.py` | 342 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/default_path_audit.py` | 338 | ÉLEVÉE | TOOL | oui | non | 2026-07-03 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/dashboard.py` | 316 | ÉLEVÉE | TOOL | oui | non | 2026-06-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `quant_hedge_ai/bench_ccxt_cold.py` | 313 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `quant_hedge_ai/fetch_audit.py` | 313 | ÉLEVÉE | TOOL | oui | non | 2026-06-13 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `quant_hedge_ai/bench_e2e_warmup.py` | 307 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `quant_hedge_ai/backtest_real.py` | 305 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/burnin_v2_report.py` | 290 | ÉLEVÉE | TOOL | oui | non | 2026-06-22 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/runtime_validator.py` | 283 | ÉLEVÉE | TOOL | oui | non | 2026-06-15 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S3/02_log_surveillance.py` | 279 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/chaos_test.py` | 276 | ÉLEVÉE | TOOL | oui | non | 2026-06-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `project_os/maturity.py` | 272 | ÉLEVÉE | TOOL | oui | non | 2026-05-14 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/validate_historical.py` | 272 | ÉLEVÉE | TOOL | oui | non | 2026-04-27 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `project_os/roadmap_state.py` | 268 | ÉLEVÉE | TOOL | oui | non | 2026-05-14 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/delta_sensitivity.py` | 268 | ÉLEVÉE | TOOL | oui | non | 2026-06-23 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `infra/multi_exchange_feed.py` | 265 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `tools/analyze_cycles.py` | 262 | ÉLEVÉE | TOOL | oui | non | 2026-05-06 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S3/05_s3_report.py` | 261 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `tools/runtime_tracer.py` | 255 | ÉLEVÉE | TOOL | oui | non | 2026-06-13 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `tools/decision_trace.py` | 250 | ÉLEVÉE | TOOL | oui | non | 2026-07-06 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `src/telegram/quant_observer/bot.py` | 244 | ÉLEVÉE | TOOL | oui | non | 2026-07-06 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S3/03_shadow_execution.py` | 242 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `core/main.py` | 239 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `reports/live_observer_report.py` | 238 | ÉLEVÉE | TOOL | oui | non | 2026-07-06 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/ONBOARDING_SCRIPT.py` | 236 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/migrate_to_structured_logger.py` | 234 | ÉLEVÉE | TOOL | oui | non | 2026-05-26 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/sqlite_contamination_audit.py` | 234 | ÉLEVÉE | TOOL | oui | non | 2026-07-03 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `project_os/debt_map.py` | 229 | ÉLEVÉE | TOOL | oui | non | 2026-05-14 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S3/04_resilience_test.py` | 225 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `quant_hedge_ai/main_system.py` | 224 | ÉLEVÉE | TOOL | oui | non | 2026-04-27 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S2/05_paper_tracker.py` | 220 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/performance_check.py` | 217 | ÉLEVÉE | TOOL | oui | non | 2026-06-28 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `quant_hedge_ai/bench_1h_limit.py` | 214 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S3/01_telegram_alerts.py` | 207 | ÉLEVÉE | TOOL | oui | non | 2026-05-26 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `core/launch_pieuvre.py` | 207 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/demo_p0_integration.py` | 196 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/replay_cli.py` | 193 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/run_all_tests.py` | 191 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `infra/notifications/notify_test_status.py` | 190 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/stress_test_cli.py` | 190 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S2/02_score_distribution.py` | 185 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/seed_strategy_memory.py` | 183 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S2/03_self_awareness_calibrator.py` | 180 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S2/04_conviction_calibrator.py` | 180 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/perp_universe_scan.py` | 176 | ÉLEVÉE | TOOL | oui | non | 2026-06-15 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `infra/monitoring/observer_logs.py` | 156 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/generate_audit_report.py` | 156 | ÉLEVÉE | TOOL | oui | non | 2026-04-27 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `S2/01_gate_logger.py` | 155 | ÉLEVÉE | TOOL | oui | non | 2026-05-25 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `src/telegram/bot_runner.py` | 152 | ÉLEVÉE | TOOL | oui | non | 2026-06-08 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `certification/hash_verifier.py` | 144 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/final_validation.py` | 134 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `paper_trading/sandbox_validator.py` | 132 | ÉLEVÉE | TOOL | oui | non | 2026-06-13 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/generate_ai_quant_lab_structure.py` | 129 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/cleanup_root.py` | 122 | ÉLEVÉE | TOOL | oui | non | 2026-06-08 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/generate_html_report.py` | 121 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/diagnostic_env.py` | 107 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/TEST_AUDIT_FR.py` | 106 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `paper_trading/status.py` | 98 | ÉLEVÉE | TOOL | oui | non | 2026-05-18 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `infra/panels/panel_selenium_test.py` | 94 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `infra/panels/panel_http_test.py` | 89 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `infra/visualization/visualize_strategy_ecosystem_all_gens.py` | 83 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/vps_data_sync.py` | 80 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/validate_trade_dataset.py` | 74 | ÉLEVÉE | TOOL | oui | non | 2026-06-14 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `infra/visualization/visualize_strategy_ecosystem.py` | 72 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/run_multi_simulations.py` | 64 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/export_excel_report.py` | 60 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/generate_report.py` | 57 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/plotly_matplotlib_compat.py` | 54 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/performance_benchmarks.py` | 53 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `lm_studio/status.py` | 52 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/panels_with_report.py` | 52 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `supervision/monitoring_profiler.py` | 52 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/generate_test_report.py` | 44 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/check_badges.py` | 38 | ÉLEVÉE | TOOL | oui | non | 2026-04-27 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `core/orchestration/orchestrate_panels_test.py` | 34 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/validate_population_csv.py` | 29 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/generate_coverage_report.py` | 19 | ÉLEVÉE | TOOL | oui | non | 2026-05-29 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `scripts/optimization_stack_validator.py` | 17 | ÉLEVÉE | TOOL | oui | non | 2026-05-05 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |
| `sdos_terminal/run.py` | 12 | ÉLEVÉE | TOOL | oui | non | 2026-07-06 | script autonome (`__main__`), jamais importé, non exécuté par le moteur — outil hors runtime |

### ACTIVE-PROBABLE — 11 modules

| Fichier | LOC | Confiance | Statut statique | Déployé | Exécuté | Dernier commit | Justification |
|---|---:|---|---|:-:|:-:|---|---|
| `quant_hedge_ai/persistent_warmup.py` | 426 | MOYENNE | ACTIVE | oui | non | 2026-05-05 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `infra/exchange_factory.py` | 402 | MOYENNE | ACTIVE | oui | non | 2026-06-13 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `core/perp_universe_service.py` | 367 | MOYENNE | ACTIVE | oui | non | 2026-06-24 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `tools/perp_universe_builder.py` | 365 | MOYENNE | ACTIVE | oui | non | 2026-06-18 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `tools/market_universe_ranker.py` | 364 | MOYENNE | ACTIVE | oui | non | 2026-06-15 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `quant_hedge_ai/agents/intelligence/decision_arbitrator.py` | 240 | MOYENNE | ACTIVE | oui | non | 2026-05-29 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `infra/live_exchange_reader.py` | 206 | MOYENNE | ACTIVE | oui | non | 2026-06-13 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `system/state_manager.py` | 200 | MOYENNE | ACTIVE | oui | non | 2026-05-08 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `dip/core/types.py` | 171 | MOYENNE | ACTIVE | oui | non | 2026-06-30 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `tools/regret_repository.py` | 102 | MOYENNE | ACTIVE | oui | non | 2026-07-21 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |
| `supervision/notifications/telegram_notifier.py` | 37 | MOYENNE | ACTIVE | oui | non | 2026-05-26 | atteignable par import mais non exécuté dans la fenêtre d'observation : branche paresseuse probablement non encore prise |

### ACTIVE — 211 modules

| Fichier | LOC | Confiance | Statut statique | Déployé | Exécuté | Dernier commit | Justification |
|---|---:|---|---|:-:|:-:|---|---|
| `core/advisor_loop.py` | 7815 | PROUVÉ | ENTRYPOINT | oui | non | 2026-07-31 | point d'entrée — CPython n'écrit pas de .pyc pour `__main__` |
| `capital_deployment/command_center_bot.py` | 1556 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-19 | .pyc présent sur le VPS : corps de module exécuté en production |
| `paper_trading/mexc_simulator.py` | 966 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/market/market_scanner.py` | 915 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-18 | .pyc présent sur le VPS : corps de module exécuté en production |
| `core/decision_packet.py` | 861 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/strategy_allocator.py` | 753 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/portfolio_brain.py` | 740 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/position_manager.py` | 706 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-18 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/self_awareness_engine.py` | 673 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-11 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/mistake_memory.py` | 663 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-18 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/global_risk_gate.py` | 646 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-21 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/live_signal_engine.py` | 608 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-06 | .pyc présent sur le VPS : corps de module exécuté en production |
| `paper_trading/dataset_validator.py` | 591 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-28 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/regret_scheduler.py` | 585 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-21 | .pyc présent sur le VPS : corps de module exécuté en production |
| `supervision/self_healing_bot.py` | 583 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/execution_engine.py` | 575 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-08 | .pyc présent sur le VPS : corps de module exécuté en production |
| `governance/auditor.py` | 574 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/conviction_engine.py` | 558 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-18 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/chief_officer.py` | 557 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-31 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` | 546 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-16 | .pyc présent sur le VPS : corps de module exécuté en production |
| `paper_trading/recorder.py` | 519 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-03 | .pyc présent sur le VPS : corps de module exécuté en production |
| `supervision/killswitch_hardened.py` | 518 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-12 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/black_box.py` | 510 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-18 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/strategy_probation.py` | 492 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/decision_observation.py` | 491 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-30 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/threat_radar.py` | 490 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/regret_engine.py` | 480 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-30 | .pyc présent sur le VPS : corps de module exécuté en production |
| `core/lifecycle.py` | 467 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/sweep_detector.py` | 461 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `capital_deployment/chart_server.py` | 437 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-28 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/sweep_outcome_tracker.py` | 437 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/autonomous/auto_decision_engine.py` | 435 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-18 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/meta_strategy_engine.py` | 434 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/ai_evolution/strategy_ranker.py` | 423 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `event_bus/events.py` | 388 | PROUVÉ | ACTIVE | oui | **oui** | 2026-04-28 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tools/cri_calculator.py` | 386 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-28 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/market_regime_classifier.py` | 382 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/decision_quality_engine.py` | 380 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/system_snapshot.py` | 375 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-31 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/executive_override.py` | 357 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/behavioral_stability_monitor.py` | 352 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-18 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/confidence_explainer.py` | 338 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-16 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/no_trade_layer.py` | 336 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `errors/error_bus.py` | 325 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-08 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/core/trade_tracker.py` | 322 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `supervision/performance_watchdog.py` | 318 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/rejection_store.py` | 310 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-30 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/integrity_rules.py` | 310 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `event_bus/bridge.py` | 307 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/decision_explainer.py` | 306 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-30 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/runtime/runtime_state_machine.py` | 305 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `governance/trading_authority.py` | 303 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/risk_governor.py` | 295 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/ai_advisor.py` | 294 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `supervision/exchange_monitor.py` | 294 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-13 | .pyc présent sur le VPS : corps de module exécuté en production |
| `scripts/data_quality.py` | 291 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-16 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/capital_allocation_engine.py` | 289 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/anomaly_governance.py` | 288 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `exchange_constraints/order_validator.py` | 287 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/metrics_collector.py` | 281 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `event_bus/bus.py` | 274 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/quant/backtest_lab.py` | 274 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `capital_deployment/emergency_stop_manager.py` | 271 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `paper_trading/engine.py` | 271 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-06-13 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/shadow_engine.py` | 271 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/forbidden_patterns_registry.py` | 271 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/real_accounts.py` | 270 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-20 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/correlation_monitor.py` | 266 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `infra/wallet_sync.py` | 262 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-06 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/behavioral_drift_detector.py` | 261 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/json_logger.py` | 258 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-03 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/module_registry.py` | 254 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-08 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/state_integrity.py` | 254 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/dashboard/builder.py` | 250 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `exchange_constraints/rate_limiter.py` | 246 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/ai_evolution/evolution_engine.py` | 244 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/alerting.py` | 242 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/activity_tracker.py` | 242 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-31 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/market/symbol_stability.py` | 242 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-18 | .pyc présent sur le VPS : corps de module exécuté en production |
| `scripts/shadow_execution.py` | 242 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-25 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/safety_auditor.py` | 242 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/state_machine.py` | 242 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-16 | .pyc présent sur le VPS : corps de module exécuté en production |
| `supervision/kill_switch.py` | 240 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `paper_trading/ledger.py` | 239 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/feature_engineer.py` | 233 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `scripts/telegram_alerts.py` | 233 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-30 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/performance_supervisor.py` | 232 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/runtime/chaos_orchestrator.py` | 230 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `capital_deployment/phase_kpi_tracker.py` | 228 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/metrics_bus.py` | 228 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-08 | .pyc présent sur le VPS : corps de module exécuté en production |
| `infra/mexc_reader.py` | 226 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/system_health_monitor.py` | 221 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/self_monitoring_loop.py` | 220 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `lm_studio/client.py` | 216 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/session_guard.py` | 211 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/portfolio_intelligence.py` | 209 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/ai_evolution/strategy_memory.py` | 208 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/health_score.py` | 207 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/dynamic_weighting_engine.py` | 207 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/heartbeat_system.py` | 203 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-08 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/system_snapshot_renderers.py` | 201 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-31 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/integrity_models.py` | 200 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/trade_logger.py` | 196 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `config/settings.py` | 193 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-06-13 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/position_reconciler.py` | 185 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `governance/decision_trace.py` | 183 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `supervision/circuit_breaker_robust.py` | 180 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `exchange_constraints/models.py` | 179 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `governance/authority_state.py` | 178 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `execution_simulator/models.py` | 177 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `risk/risk_limits.py` | 176 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/runtime/event_journal.py` | 174 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/decision_event_bus.py` | 169 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-30 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/meta_learner.py` | 169 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/confidence_scorer.py` | 166 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/adaptive_threshold_engine.py` | 165 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-31 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/config/settings.py` | 165 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `core/advisor_runtime_adapters.py` | 160 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-15 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/analytics/metrics.py` | 159 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/market/retry_policy.py` | 158 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/integrity_snapshot.py` | 157 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/analytics/score_drift_monitor.py` | 155 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `capital_deployment/operational_state.py` | 150 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-31 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/core/trade_logger.py` | 148 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-08 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/market/multi_timeframe_scanner.py` | 146 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `execution_simulator/simulator.py` | 145 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/main.py` | 145 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `config/parameter_audit.py` | 142 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-20 | .pyc présent sur le VPS : corps de module exécuté en production |
| `governance/status_dashboard.py` | 140 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/multi_timeframe_signal.py` | 140 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/regime_transition_smoother.py` | 139 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/signal_engine.py` | 137 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `capital_deployment/capital_throttle.py` | 135 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/market/ohlcv_validator.py` | 133 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/scheduler/auto_update.py` | 133 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `exchange_constraints/precision_rules.py` | 132 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `execution_simulator/config.py` | 129 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-13 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/core/boot_validator.py` | 129 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `execution_simulator/fill_simulator.py` | 127 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `execution_simulator/slippage.py` | 126 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/config/exit_config.py` | 125 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `exchange_constraints/binance_rules.py` | 122 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-13 | .pyc présent sur le VPS : corps de module exécuté en production |
| `crypto/blackbox_encryption.py` | 115 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `supervision/alert_manager.py` | 112 | PROUVÉ | ACTIVE | oui | **oui** | 2026-04-28 | .pyc présent sur le VPS : corps de module exécuté en production |
| `core/authority.py` | 109 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `core/topk_scheduler.py` | 101 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-17 | .pyc présent sur le VPS : corps de module exécuté en production |
| `execution_simulator/spread.py` | 101 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/capital_throttle.py` | 101 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `crypto/key_derivation.py` | 94 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `execution_simulator/latency.py` | 92 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-14 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/exposure_manager.py` | 91 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/backtesting/auto_backtester.py` | 90 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/system_snapshot_event_bus.py` | 76 | PROUVÉ | ACTIVE | oui | **oui** | 2026-07-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `lm_studio/ai_router.py` | 69 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/order_deduplicator.py` | 64 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/meta_memory.py` | 60 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/system_invariants.py` | 59 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-16 | .pyc présent sur le VPS : corps de module exécuté en production |
| `config/feature_flags.py` | 55 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-30 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/dashboard/live_snapshot.py` | 55 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/regime_detector.py` | 51 | PROUVÉ | ACTIVE | oui | **oui** | 2026-06-12 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/__init__.py` | 47 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-25 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/strategy/genetic_optimizer.py` | 46 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `exchange_constraints/__init__.py` | 40 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-13 | .pyc présent sur le VPS : corps de module exécuté en production |
| `governance/__init__.py` | 32 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-02 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/storage/loader.py` | 31 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/engine/exit_engine.py` | 29 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/engine/rules/breakeven.py` | 27 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/engine/rules/tp_sl.py` | 27 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/analytics/regime_analysis.py` | 26 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/backtesting/simulator.py` | 26 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `execution_simulator/__init__.py` | 24 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-13 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/analytics/mfe_mae.py` | 24 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/core/position_manager.py` | 24 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `paper_trading/__init__.py` | 23 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-06-13 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/config/__init__.py` | 23 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/engine/rules/trailing.py` | 22 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `supervision/__init__.py` | 21 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-12 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/strategy/strategy_generator.py` | 20 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/engine/exit_factory.py` | 18 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/runtime/__init__.py` | 17 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/storage/saver.py` | 16 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/core/__init__.py` | 15 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `lm_studio/__init__.py` | 13 | PROUVÉ | ACTIVE | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `event_bus/__init__.py` | 7 | PROUVÉ | ORPHAN | oui | **oui** | 2026-04-28 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/ai_evolution/__init__.py` | 7 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/intelligence/__init__.py` | 6 | PROUVÉ | ORPHAN | oui | **oui** | 2026-04-28 | .pyc présent sur le VPS : corps de module exécuté en production |
| `system/__init__.py` | 5 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-26 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/engine/rules/__init__.py` | 5 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/backtesting/__init__.py` | 4 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/engine/__init__.py` | 4 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/storage/__init__.py` | 4 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `config/__init__.py` | 3 | PROUVÉ | ORPHAN | oui | **oui** | 2026-06-12 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/analytics/__init__.py` | 3 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/dashboard/__init__.py` | 3 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `tracker_system/scheduler/__init__.py` | 3 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-05 | .pyc présent sur le VPS : corps de module exécuté en production |
| `capital_deployment/__init__.py` | 1 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `core/__init__.py` | 1 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `crypto/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `errors/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-08 | .pyc présent sur le VPS : corps de module exécuté en production |
| `infra/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `observability/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-08 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/execution/__init__.py` | 1 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/market/__init__.py` | 1 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/quant/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/risk/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/agents/strategy/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `risk/__init__.py` | 1 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `scripts/__init__.py` | 1 | PROUVÉ | TEST_ONLY | oui | **oui** | 2026-05-29 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/__init__.py` | 0 | PROUVÉ | ORPHAN | oui | **oui** | 2026-04-27 | .pyc présent sur le VPS : corps de module exécuté en production |
| `quant_hedge_ai/dashboard/__init__.py` | 0 | PROUVÉ | ORPHAN | oui | **oui** | 2026-05-06 | .pyc présent sur le VPS : corps de module exécuté en production |

## 6. Ce qui reste NON MESURÉ

| Question | Ce qu'il faudrait |
|---|---|
| Modules chargés uniquement en incident / recovery | seconde mesure après un incident réel |
| Modules chargés uniquement à certaines heures (radar 06:00, horizons 06:15) | mesure sur ≥ 24 h continues |
| Fréquence d'usage d'un module `ACTIVE` | compteurs d'appel, pas seulement d'import |
| Cohérence des paires de classes dupliquées actives | trace d'instances, pas d'imports |
| Modules du dépôt local absents du VPS et jamais exécutés localement | exécution d'une passe locale |
