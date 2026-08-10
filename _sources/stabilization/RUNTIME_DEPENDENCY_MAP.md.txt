# RUNTIME DEPENDENCY MAP — Phase 0 Forensic Freeze
> Généré : 2026-05-28 | Méthode : AST static analysis + vérification réelle
> **FREEZE** — ne pas modifier avant Phase 1

---

## ENTRYPOINTS RUNTIME ACTIFS

> **PROBLEME IDENTIFIE :** 3 entrypoints concurrents = 3 états runtime possibles

| Entrypoint | Modules chargés | Status |
|------------|----------------|--------|
| `advisor_loop.py` | advisor_runtime_adapters + toute la chaîne quant | **PRODUCTION** — VPS actif |
| `capital_deployment/command_center_bot.py` | Telegram bot uniquement | **PRODUCTION** — VPS actif |
| `cold_start/cold_start_manager.py` | Protocole démarrage HMAC | Via advisor_loop |
| `quant_hedge_ai/main_v91.py` | Ensemble différent (arbitrage, weekly_report, proactive_alerts) | **ORPHELIN ACTIF** — lancé par qui? |
| `quant_hedge_ai/main_system.py` | Ensemble recherche (backtest, monte_carlo, orderflow) | OBSOLETE — v91 lab |
| `main.py` | evolution_core + visualization uniquement | OBSOLETE — pas le vrai entry |

**ACTION PHASE 1 :** Supprimer `main_system.py`, `main_v91.py`, `main.py` (root) — un seul entrypoint : `advisor_loop.py`

---

## CHAÎNE CRITIQUE : SIGNAL → EXECUTION

```
MarketScanner / MultiTimeframeScanner
  └─► FeatureEngineer
        └─► RegimeDetector + RegimeTransitionSmoother
              └─► ConvictionEngine + SelfAwarenessEngine
                    └─► NoTradeLayer + MetaStrategyEngine
                          └─► GlobalRiskGate + PortfolioBrain
                                └─► CapitalAllocationEngine + OrderSizer
                                      └─► ExecutionEngine
                                            └─► PositionManager + SubaccountManager
```

---

## MODULES RUNTIME ACTIFS (depuis advisor_loop.py — analyse statique)

### Niveau 1 — Imports directs advisor_loop.py
| Module | Fichier | Critique |
|--------|---------|---------|
| `advisor_runtime_adapters` | advisor_runtime_adapters.py | OUI — hub central |
| `capital_deployment.capital_throttle` | capital_deployment/capital_throttle.py | OUI |
| `capital_deployment.chart_server` | capital_deployment/chart_server.py | NON |
| `capital_deployment.command_center_bot` | capital_deployment/command_center_bot.py | OUI — Telegram |
| `capital_deployment.emergency_stop_manager` | capital_deployment/emergency_stop_manager.py | OUI |
| `capital_deployment.phase_kpi_tracker` | capital_deployment/phase_kpi_tracker.py | NON |
| `core.decision_packet` | core/decision_packet.py | OUI — struct centrale |
| `errors.error_bus` | errors/error_bus.py | OUI |
| `exchange_constraints.binance_rules` | exchange_constraints/binance_rules.py | OUI |
| `exchange_constraints.order_validator` | exchange_constraints/order_validator.py | OUI |
| `exchange_constraints.rate_limiter` | exchange_constraints/rate_limiter.py | OUI |
| `execution_simulator.config` | execution_simulator/config.py | OUI |
| `execution_simulator.models` | execution_simulator/models.py | OUI |
| `observability.heartbeat_system` | observability/heartbeat_system.py | OUI |
| `observability.json_logger` | observability/json_logger.py | OUI |
| `observability.metrics_bus` | observability/metrics_bus.py | OUI |
| `paper_trading.recorder` | paper_trading/recorder.py | OUI |
| `risk_limits` | risk_limits.py | OUI |
| `scripts.shadow_execution` | scripts/shadow_execution.py | NON |
| `scripts.telegram_alerts` | scripts/telegram_alerts.py | OUI |
| `supervision.circuit_breaker_robust` | supervision/circuit_breaker_robust.py | OUI |
| `system.module_registry` | system/module_registry.py | OUI |
| `system.position_reconciler` | system/position_reconciler.py | OUI |
| `system.safety_auditor` | system/safety_auditor.py | OUI |
| `system.state_machine` | system/state_machine.py | OUI |

### Niveau 2 — Via advisor_runtime_adapters.py
| Module | Critique |
|--------|---------|
| `quant_hedge_ai.agents.execution.execution_engine` | OUI |
| `quant_hedge_ai.agents.execution.live_signal_engine` | OUI |
| `quant_hedge_ai.agents.execution.position_manager` | OUI |
| `quant_hedge_ai.agents.execution.shadow_engine` | NON |
| `quant_hedge_ai.agents.intelligence.adaptive_threshold_engine` | NON |
| `quant_hedge_ai.agents.intelligence.ai_advisor` | OUI |
| `quant_hedge_ai.agents.intelligence.black_box` | OUI |
| `quant_hedge_ai.agents.intelligence.chief_officer` | OUI |
| `quant_hedge_ai.agents.intelligence.confidence_explainer` | NON |
| `quant_hedge_ai.agents.intelligence.conviction_engine` | OUI |
| `quant_hedge_ai.agents.intelligence.decision_quality_engine` | OUI |
| `quant_hedge_ai.agents.intelligence.feature_engineer` | OUI |
| `quant_hedge_ai.agents.intelligence.market_regime_classifier` | OUI |
| `quant_hedge_ai.agents.intelligence.meta_strategy_engine` | OUI |
| `quant_hedge_ai.agents.intelligence.mistake_memory` | OUI |
| `quant_hedge_ai.agents.intelligence.no_trade_layer` | OUI |
| `quant_hedge_ai.agents.intelligence.regime_detector` | OUI |
| `quant_hedge_ai.agents.intelligence.regime_transition_smoother` | NON |
| `quant_hedge_ai.agents.intelligence.regret_engine` | NON |
| `quant_hedge_ai.agents.intelligence.self_awareness_engine` | OUI |
| `quant_hedge_ai.agents.intelligence.threat_radar` | OUI |
| `quant_hedge_ai.agents.market.market_scanner` | OUI |
| `quant_hedge_ai.agents.market.multi_timeframe_scanner` | OUI |
| `quant_hedge_ai.agents.risk.capital_allocation_engine` | OUI |
| `quant_hedge_ai.agents.risk.executive_override` | OUI |
| `quant_hedge_ai.agents.risk.global_risk_gate` | OUI |
| `quant_hedge_ai.agents.risk.portfolio_brain` | OUI |
| `quant_hedge_ai.ai_evolution.strategy_memory` | NON |
| `quant_hedge_ai.ai_evolution.strategy_ranker` | NON |
| `supervision.exchange_monitor` | OUI |
| `supervision.performance_watchdog` | OUI |
| `supervision.self_healing_bot` | OUI |
| `supervision.telegram_kill_switch` | OUI |
| `tracker_system.core.trade_tracker` | OUI |
| `tracker_system.main` | OUI |
| `tracker_system.meta_learner` | NON |

---

## DUPLICATIONS CONFIRMEES (analyse AST réelle)

> Chaque doublon = source de vérité multiple = comportement non déterministe possible

| Module | Occurrences | Emplacements | Risque |
|--------|------------|-------------|--------|
| `regime_detector.py` | 3 | `_legacy/`, `agents/intelligence/`, `agents/market/` | CRITIQUE — quel régime est utilisé? |
| `feature_engineer.py` | 3 | `_legacy/`, `agents/intelligence/`, `agents/research/` | HAUT |
| `position_manager.py` | 2 | `agents/execution/`, `tracker_system/core/` | CRITIQUE — états position indépendants |
| `evolution_engine.py` | 2 | `ai_evolution/`, `strategy_lab/` | MOYEN |
| `execution_engine.py` | 1 (+ v2/) | root + fork `execution_v2/` actif | HAUT — fork non résolu |

**`execution_v2/__init__.py` exporte activement :** `SlippagePredictor`, `ExecutionOptimizer`, `OptimalTimingEngine`

**`intelligence/v2/__init__.py` exporte activement :** `HMMRegimeEngine`, `DecisionArbitrator`, `RegimeTransitionPredictor`

**`main_v91.py` utilise :** `regime_detector` de `agents/intelligence/` (pas `agents/market/`)
→ conflit silencieux possible si les deux sont instanciés concurremment

---

## PIPELINES PARALLELES (3 runtimes distincts)

| Pipeline | Entrypoint | Modules propres | Conflit avec Principal? |
|---------|-----------|----------------|------------------------|
| **Principal** | `advisor_loop.py` | toute la chaîne intelligence/risk | REFERENCE |
| **MVP** | `mvp/mvp_orchestrator.py` | risk_engine_mvp, signal_engine_mvp | NON importé par Principal ✓ |
| **Tracker** | `tracker_system/main.py` | auto_decision_engine, portfolio_risk | Importé par advisor_runtime_adapters — OK |
| **V91 Lab** | `quant_hedge_ai/main_v91.py` | arbitrage, weekly_report, proactive_alerts | ORPHELIN ACTIF — lancé comment? |

---

## RISQUES IMMEDIATS (à traiter avant Phase 1)

### R1 — `_legacy/__init__.py` importable
Le package `_legacy` est Python-importable. Contenu actuel = docstring uniquement (pas d'exports).
**Risque :** Un import accidentel futur est possible. Ajouter `raise ImportError` dans `__init__.py`.

### R2 — Fork `execution_v2/` actif
`execution_v2/__init__.py` exporte 6 classes. Aucun fichier runtime ne les importe (vérifié).
**Décision requise Phase 1 :** intégrer dans `execution_engine.py` ou supprimer.

### R3 — Deuxième source régime `intelligence/v2/`
`HMMRegimeEngine` existe mais n'est pas importé par `advisor_runtime_adapters`.
`DecisionArbitrator` est importé par `advisor_runtime_adapters.v2.decision_arbitrator`.
**Risque :** 2 arbitres de décision actifs simultanément.

### R4 — `regime_detector` dans `agents/market/` vs `agents/intelligence/`
`main_v91.py` utilise `agents/market/regime_detector`.
`advisor_runtime_adapters.py` utilise `agents/intelligence/regime_detector`.
**Risque :** Si les deux sont actifs, ils divergent silencieusement.

---

## MODULES ORPHELINS — CANDIDATS À SUPPRESSION (Phase 1)

> Méthode : non importés par la chaîne advisor_loop transitive
> **RÈGLE** : grep d'import obligatoire avant suppression

### Catégorie A — Anciens sprints / versions
| Module | Fichiers | Verdict |
|--------|---------|---------|
| `S2/` | 6 | SUPPRIMER — sprint obsolète |
| `S3/` | 5 | SUPPRIMER — sprint obsolète |
| `crypto_quant_v16/` | 3 | SUPPRIMER — ancienne version |
| `mvp/` | 8 | SUPPRIMER — prototype initial |

### Catégorie B — Scripts root dupliqués
| Module | Fichiers | Verdict |
|--------|---------|---------|
| `circuit_breaker.py` | 1 | VÉRIFIER — doublon de supervision/circuit_breaker_robust? |
| `global_risk_gate.py` | 1 | VÉRIFIER — doublon de quant_hedge_ai/agents/risk/global_risk_gate? |
| `evolution_core.py` | 1 | VÉRIFIER — usage? |
| `evolution_memory.py` | 1 | VÉRIFIER — usage? |

### Catégorie C — Outils standalone (conserver, isoler)
| Module | Fichiers | Verdict |
|--------|---------|---------|
| `api_rest.py` | 1 | ISOLER dans tools/ |
| `api_server.py` | 1 | ISOLER dans tools/ |
| `data_verifier.py` | 1 | ISOLER dans tools/ |
| `stress_test_cli.py` | 1 | ISOLER dans tests/ |
| `replay_cli.py` | 1 | ISOLER dans tools/ |
| `vps_data_sync.py` | 1 | ISOLER dans deploy/ |

### Catégorie D — Génération / export (supprimer)
| Module | Fichiers | Verdict |
|--------|---------|---------|
| `generate_ai_quant_lab_structure.py` | 1 | SUPPRIMER |
| `generate_coverage_report.py` | 1 | SUPPRIMER |
| `generate_html_report.py` | 1 | SUPPRIMER |
| `generate_report.py` | 1 | SUPPRIMER |
| `generate_test_report.py` | 1 | SUPPRIMER |
| `export_excel_report.py` | 1 | SUPPRIMER |
| `export_latex_md.py` | 1 | SUPPRIMER |
| `copy_docs_for_sphinx.py` | 1 | SUPPRIMER |
| `notify_selenium_report_discord.py` | 1 | SUPPRIMER |
| `notify_selenium_report_slack.py` | 1 | SUPPRIMER |

### Catégorie E — Inconnu / à investiguer
| Module | Fichiers | Verdict |
|--------|---------|---------|
| `pieuvre/` | 17 | VÉRIFIER — système 8 tentacules, utilisé en prod? |
| `market_data/` | 12 | VÉRIFIER — indépendant ou remplacé par quant_hedge_ai/agents/market? |
| `project_os/` | 9 | VÉRIFIER — usage? |
| `runtime/` | 9 | VÉRIFIER — usage? |
| `governance/` | 6 | VÉRIFIER — lié à meta_governance? |
| `terminal_core/` | 3 | VÉRIFIER — usage? |
| `meta_learning/` | 5 | VÉRIFIER — lié à tracker_system/meta_learner? |
| `anara_context/` | 0 | SUPPRIMER — dossier vide |

---

## MODULES À 0 FICHIERS (dossiers fantômes)
```
anara_context/     archive_results/    archives/     artifacts/
cache/             checkpoints/        config/       data/
databases/         deploy/             feedback_logs/ frontend/
install/           k8s/                logs/         reports/
results/           sim_summaries/      tickets/
```
**Action Phase 1 :** Vérifier contenu non-Python, supprimer si vide.

---

## STATISTIQUES
| Métrique | Valeur |
|---------|--------|
| Total top-level items | 140 |
| Modules runtime actifs (chaîne advisor_loop) | ~29 top-level |
| Modules runtime actifs (total fichiers) | ~120+ fichiers |
| Candidats suppression catégorie A | 4 modules |
| Candidats suppression catégorie D | 10 scripts |
| Dossiers fantômes (0 .py files) | 19 |
| Orphelins à investiguer | ~15 modules |

---

## PROCHAINE ÉTAPE — Phase 0.5
Instrumenter les modules actifs avec `logger.info(f"MODULE_ACTIVE={__file__}")` pour valider la carte statique contre le runtime réel.
