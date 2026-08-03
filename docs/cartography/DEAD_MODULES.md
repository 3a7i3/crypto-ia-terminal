# DEAD_MODULES.md — Classement de tous les modules
> **Document généré automatiquement.** Ne pas éditer à la main.
> Source : `artifacts/cartography.json` — régénérer via
> `python tools/runtime_cartographer.py && python tools/cartography_report.py`
> Généré le 2026-08-01 — commit `348e83d`

> **Portée de la mesure.** Graphe d'import statique (AST), imports paresseux
> inclus. `ACTIVE` signifie **atteignable par import** depuis le point d'entrée
> runtime, **pas** « exécuté ». Prouver l'exécution exige une trace runtime
> (`sys.settrace`/coverage sur le VPS) — **NON MESURÉ** en J1-J2.

**Aucun fichier n'a été supprimé.** Ce document classe, il n'ampute pas.

## Définition des statuts

| Statut | Définition **mesurée** |
|---|---|
| `ENTRYPOINT` | Point d'entrée runtime déclaré |
| `ACTIVE` | Atteignable par import depuis l'`ENTRYPOINT` |
| `TOOL` | Contient `__main__`, importé par aucun module — script autonome |
| `TEST_ONLY` | Atteignable depuis les tests, **jamais** depuis le runtime |
| `ORPHAN` | Ni runtime, ni test, ni script autonome |
| `TEST` | Fichier de test lui-même |

`ORPHAN` **n'est pas** synonyme de « supprimable » : un module peut être chargé
par un chemin que l'analyse statique ne voit pas (`importlib`, plugin, entrée
systemd distincte). Toute suppression exige une contre-vérification par trace.

## Décompte

| Statut | Modules |
|---|---|
| `ENTRYPOINT` | 1 |
| `ACTIVE` | 169 |
| `TOOL` | 94 |
| `TEST_ONLY` | 279 |
| `ORPHAN` | 248 |
| `TEST` | 324 |
| **TOTAL** | **1115** |

## ENTRYPOINT — 1 modules

| Module | Fichier | LOC | Dernier commit | Importé par | Justification |
|---|---|---:|---|---:|---|
| `core.advisor_loop` | `core/advisor_loop.py` | 7815 | 2026-07-31 | 9 | point d'entrée runtime déclaré |

## ACTIVE — 169 modules

| Module | Fichier | LOC | Dernier commit | Importé par | Justification |
|---|---|---:|---|---:|---|
| `capital_deployment.command_center_bot` | `capital_deployment/command_center_bot.py` | 1556 | 2026-07-19 | 3 | atteignable par import depuis le point d'entrée runtime |
| `paper_trading.mexc_simulator` | `paper_trading/mexc_simulator.py` | 966 | 2026-07-14 | 6 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.market.market_scanner` | `quant_hedge_ai/agents/market/market_scanner.py` | 915 | 2026-06-18 | 10 | atteignable par import depuis le point d'entrée runtime |
| `core.decision_packet` | `core/decision_packet.py` | 861 | 2026-06-02 | 22 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.strategy_allocator` | `quant_hedge_ai/agents/intelligence/strategy_allocator.py` | 753 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.portfolio_brain` | `quant_hedge_ai/agents/risk/portfolio_brain.py` | 740 | 2026-06-02 | 6 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.execution.position_manager` | `quant_hedge_ai/agents/execution/position_manager.py` | 706 | 2026-06-18 | 7 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.self_awareness_engine` | `quant_hedge_ai/agents/intelligence/self_awareness_engine.py` | 673 | 2026-07-11 | 8 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.mistake_memory` | `quant_hedge_ai/agents/intelligence/mistake_memory.py` | 663 | 2026-06-18 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.global_risk_gate` | `quant_hedge_ai/agents/risk/global_risk_gate.py` | 646 | 2026-07-21 | 7 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.execution.live_signal_engine` | `quant_hedge_ai/agents/execution/live_signal_engine.py` | 608 | 2026-06-06 | 13 | atteignable par import depuis le point d'entrée runtime |
| `paper_trading.dataset_validator` | `paper_trading/dataset_validator.py` | 591 | 2026-07-28 | 6 | atteignable par import depuis le point d'entrée runtime |
| `observability.regret_scheduler` | `observability/regret_scheduler.py` | 585 | 2026-07-21 | 3 | atteignable par import depuis le point d'entrée runtime |
| `supervision.self_healing_bot` | `supervision/self_healing_bot.py` | 583 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.execution.execution_engine` | `quant_hedge_ai/agents/execution/execution_engine.py` | 575 | 2026-07-08 | 11 | atteignable par import depuis le point d'entrée runtime |
| `governance.auditor` | `governance/auditor.py` | 574 | 2026-06-02 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.conviction_engine` | `quant_hedge_ai/agents/intelligence/conviction_engine.py` | 558 | 2026-06-18 | 6 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.chief_officer` | `quant_hedge_ai/agents/intelligence/chief_officer.py` | 557 | 2026-05-31 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.system_intel_reporter` | `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` | 546 | 2026-07-16 | 4 | atteignable par import depuis le point d'entrée runtime |
| `paper_trading.recorder` | `paper_trading/recorder.py` | 519 | 2026-07-03 | 9 | atteignable par import depuis le point d'entrée runtime |
| `supervision.killswitch_hardened` | `supervision/killswitch_hardened.py` | 518 | 2026-06-12 | 5 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.black_box` | `quant_hedge_ai/agents/intelligence/black_box.py` | 510 | 2026-06-18 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.strategy_probation` | `quant_hedge_ai/agents/intelligence/strategy_probation.py` | 492 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `observability.decision_observation` | `observability/decision_observation.py` | 491 | 2026-06-30 | 11 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.threat_radar` | `quant_hedge_ai/agents/intelligence/threat_radar.py` | 490 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.regret_engine` | `quant_hedge_ai/agents/intelligence/regret_engine.py` | 480 | 2026-06-30 | 3 | atteignable par import depuis le point d'entrée runtime |
| `core.lifecycle` | `core/lifecycle.py` | 467 | 2026-06-02 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.sweep_detector` | `quant_hedge_ai/agents/intelligence/sweep_detector.py` | 461 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `capital_deployment.chart_server` | `capital_deployment/chart_server.py` | 437 | 2026-05-28 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.sweep_outcome_tracker` | `quant_hedge_ai/agents/intelligence/sweep_outcome_tracker.py` | 437 | 2026-05-26 | 1 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.autonomous.auto_decision_engine` | `tracker_system/autonomous/auto_decision_engine.py` | 435 | 2026-05-18 | 4 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.meta_strategy_engine` | `quant_hedge_ai/agents/intelligence/meta_strategy_engine.py` | 434 | 2026-05-26 | 4 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.persistent_warmup` | `quant_hedge_ai/persistent_warmup.py` | 426 | 2026-05-05 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.ai_evolution.strategy_ranker` | `quant_hedge_ai/ai_evolution/strategy_ranker.py` | 423 | 2026-05-26 | 1 | atteignable par import depuis le point d'entrée runtime |
| `infra.exchange_factory` | `infra/exchange_factory.py` | 402 | 2026-06-13 | 1 | atteignable par import depuis le point d'entrée runtime |
| `event_bus.events` | `event_bus/events.py` | 388 | 2026-04-28 | 15 | atteignable par import depuis le point d'entrée runtime |
| `tools.cri_calculator` | `tools/cri_calculator.py` | 386 | 2026-07-28 | 15 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.market_regime_classifier` | `quant_hedge_ai/agents/intelligence/market_regime_classifier.py` | 382 | 2026-05-26 | 6 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.decision_quality_engine` | `quant_hedge_ai/agents/intelligence/decision_quality_engine.py` | 380 | 2026-05-26 | 1 | atteignable par import depuis le point d'entrée runtime |
| `observability.system_snapshot` | `observability/system_snapshot.py` | 375 | 2026-07-31 | 5 | atteignable par import depuis le point d'entrée runtime |
| `core.perp_universe_service` | `core/perp_universe_service.py` | 367 | 2026-06-24 | 2 | atteignable par import depuis le point d'entrée runtime |
| `tools.perp_universe_builder` | `tools/perp_universe_builder.py` | 365 | 2026-06-18 | 4 | atteignable par import depuis le point d'entrée runtime |
| `tools.market_universe_ranker` | `tools/market_universe_ranker.py` | 364 | 2026-06-15 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.executive_override` | `quant_hedge_ai/agents/risk/executive_override.py` | 357 | 2026-05-26 | 4 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.behavioral_stability_monitor` | `quant_hedge_ai/agents/intelligence/behavioral_stability_monitor.py` | 352 | 2026-06-18 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.confidence_explainer` | `quant_hedge_ai/agents/intelligence/confidence_explainer.py` | 338 | 2026-05-16 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.no_trade_layer` | `quant_hedge_ai/agents/intelligence/no_trade_layer.py` | 336 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `errors.error_bus` | `errors/error_bus.py` | 325 | 2026-05-08 | 4 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.core.trade_tracker` | `tracker_system/core/trade_tracker.py` | 322 | 2026-05-14 | 12 | atteignable par import depuis le point d'entrée runtime |
| `supervision.performance_watchdog` | `supervision/performance_watchdog.py` | 318 | 2026-05-26 | 1 | atteignable par import depuis le point d'entrée runtime |
| `observability.rejection_store` | `observability/rejection_store.py` | 310 | 2026-06-30 | 2 | atteignable par import depuis le point d'entrée runtime |
| `system.integrity_rules` | `system/integrity_rules.py` | 310 | 2026-05-29 | 2 | atteignable par import depuis le point d'entrée runtime |
| `observability.decision_explainer` | `observability/decision_explainer.py` | 306 | 2026-06-30 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.runtime.runtime_state_machine` | `quant_hedge_ai/runtime/runtime_state_machine.py` | 305 | 2026-06-02 | 15 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.risk_governor` | `quant_hedge_ai/agents/risk/risk_governor.py` | 295 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.ai_advisor` | `quant_hedge_ai/agents/intelligence/ai_advisor.py` | 294 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `supervision.exchange_monitor` | `supervision/exchange_monitor.py` | 294 | 2026-06-13 | 1 | atteignable par import depuis le point d'entrée runtime |
| `scripts.data_quality` | `scripts/data_quality.py` | 291 | 2026-07-16 | 10 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.capital_allocation_engine` | `quant_hedge_ai/agents/risk/capital_allocation_engine.py` | 289 | 2026-05-26 | 4 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.anomaly_governance` | `quant_hedge_ai/agents/risk/anomaly_governance.py` | 288 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `exchange_constraints.order_validator` | `exchange_constraints/order_validator.py` | 287 | 2026-05-14 | 4 | atteignable par import depuis le point d'entrée runtime |
| `observability.metrics_collector` | `observability/metrics_collector.py` | 281 | 2026-05-29 | 5 | atteignable par import depuis le point d'entrée runtime |
| `event_bus.bus` | `event_bus/bus.py` | 274 | 2026-05-26 | 15 | atteignable par import depuis le point d'entrée runtime |
| `capital_deployment.emergency_stop_manager` | `capital_deployment/emergency_stop_manager.py` | 271 | 2026-05-29 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.execution.shadow_engine` | `quant_hedge_ai/agents/execution/shadow_engine.py` | 271 | 2026-05-29 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.forbidden_patterns_registry` | `quant_hedge_ai/agents/intelligence/forbidden_patterns_registry.py` | 271 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `observability.real_accounts` | `observability/real_accounts.py` | 270 | 2026-07-20 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.correlation_monitor` | `quant_hedge_ai/agents/intelligence/correlation_monitor.py` | 266 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `infra.wallet_sync` | `infra/wallet_sync.py` | 262 | 2026-07-06 | 9 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.behavioral_drift_detector` | `quant_hedge_ai/agents/intelligence/behavioral_drift_detector.py` | 261 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `observability.json_logger` | `observability/json_logger.py` | 258 | 2026-07-03 | 193 | atteignable par import depuis le point d'entrée runtime |
| `system.module_registry` | `system/module_registry.py` | 254 | 2026-05-08 | 13 | atteignable par import depuis le point d'entrée runtime |
| `system.state_integrity` | `system/state_integrity.py` | 254 | 2026-05-29 | 2 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.dashboard.builder` | `tracker_system/dashboard/builder.py` | 250 | 2026-05-14 | 3 | atteignable par import depuis le point d'entrée runtime |
| `exchange_constraints.rate_limiter` | `exchange_constraints/rate_limiter.py` | 246 | 2026-05-14 | 3 | atteignable par import depuis le point d'entrée runtime |
| `observability.alerting` | `observability/alerting.py` | 242 | 2026-05-29 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.activity_tracker` | `quant_hedge_ai/agents/intelligence/activity_tracker.py` | 242 | 2026-05-31 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.market.symbol_stability` | `quant_hedge_ai/agents/market/symbol_stability.py` | 242 | 2026-06-18 | 3 | atteignable par import depuis le point d'entrée runtime |
| `scripts.shadow_execution` | `scripts/shadow_execution.py` | 242 | 2026-05-25 | 1 | atteignable par import depuis le point d'entrée runtime |
| `system.safety_auditor` | `system/safety_auditor.py` | 242 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `system.state_machine` | `system/state_machine.py` | 242 | 2026-06-16 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.decision_arbitrator` | `quant_hedge_ai/agents/intelligence/decision_arbitrator.py` | 240 | 2026-05-29 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.feature_engineer` | `quant_hedge_ai/agents/intelligence/feature_engineer.py` | 233 | 2026-05-05 | 10 | atteignable par import depuis le point d'entrée runtime |
| `scripts.telegram_alerts` | `scripts/telegram_alerts.py` | 233 | 2026-06-30 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.performance_supervisor` | `quant_hedge_ai/agents/intelligence/performance_supervisor.py` | 232 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `capital_deployment.phase_kpi_tracker` | `capital_deployment/phase_kpi_tracker.py` | 228 | 2026-05-29 | 8 | atteignable par import depuis le point d'entrée runtime |
| `observability.metrics_bus` | `observability/metrics_bus.py` | 228 | 2026-05-08 | 14 | atteignable par import depuis le point d'entrée runtime |
| `infra.mexc_reader` | `infra/mexc_reader.py` | 226 | 2026-06-02 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.system_health_monitor` | `quant_hedge_ai/agents/risk/system_health_monitor.py` | 221 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.self_monitoring_loop` | `quant_hedge_ai/agents/intelligence/self_monitoring_loop.py` | 220 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `lm_studio.client` | `lm_studio/client.py` | 216 | 2026-05-29 | 8 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.session_guard` | `quant_hedge_ai/agents/risk/session_guard.py` | 211 | 2026-05-26 | 6 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.portfolio_intelligence` | `quant_hedge_ai/agents/risk/portfolio_intelligence.py` | 209 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.ai_evolution.strategy_memory` | `quant_hedge_ai/ai_evolution/strategy_memory.py` | 208 | 2026-05-26 | 7 | atteignable par import depuis le point d'entrée runtime |
| `observability.health_score` | `observability/health_score.py` | 207 | 2026-05-29 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.dynamic_weighting_engine` | `quant_hedge_ai/agents/intelligence/dynamic_weighting_engine.py` | 207 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `infra.live_exchange_reader` | `infra/live_exchange_reader.py` | 206 | 2026-06-13 | 4 | atteignable par import depuis le point d'entrée runtime |
| `observability.heartbeat_system` | `observability/heartbeat_system.py` | 203 | 2026-05-08 | 2 | atteignable par import depuis le point d'entrée runtime |
| `observability.system_snapshot_renderers` | `observability/system_snapshot_renderers.py` | 201 | 2026-07-31 | 3 | atteignable par import depuis le point d'entrée runtime |
| `system.integrity_models` | `system/integrity_models.py` | 200 | 2026-05-29 | 3 | atteignable par import depuis le point d'entrée runtime |
| `system.state_manager` | `system/state_manager.py` | 200 | 2026-05-08 | 10 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.execution.trade_logger` | `quant_hedge_ai/agents/execution/trade_logger.py` | 196 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `system.position_reconciler` | `system/position_reconciler.py` | 185 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `supervision.circuit_breaker_robust` | `supervision/circuit_breaker_robust.py` | 180 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `exchange_constraints.models` | `exchange_constraints/models.py` | 179 | 2026-05-14 | 5 | atteignable par import depuis le point d'entrée runtime |
| `execution_simulator.models` | `execution_simulator/models.py` | 177 | 2026-05-14 | 13 | atteignable par import depuis le point d'entrée runtime |
| `risk.risk_limits` | `risk/risk_limits.py` | 176 | 2026-05-29 | 1 | atteignable par import depuis le point d'entrée runtime |
| `dip.core.types` | `dip/core/types.py` | 171 | 2026-06-30 | 44 | atteignable par import depuis le point d'entrée runtime |
| `observability.decision_event_bus` | `observability/decision_event_bus.py` | 169 | 2026-06-30 | 3 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.meta_learner` | `tracker_system/meta_learner.py` | 169 | 2026-05-05 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.confidence_scorer` | `quant_hedge_ai/agents/intelligence/confidence_scorer.py` | 166 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.adaptive_threshold_engine` | `quant_hedge_ai/agents/intelligence/adaptive_threshold_engine.py` | 165 | 2026-05-31 | 2 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.config.settings` | `tracker_system/config/settings.py` | 165 | 2026-05-14 | 19 | atteignable par import depuis le point d'entrée runtime |
| `core.advisor_runtime_adapters` | `core/advisor_runtime_adapters.py` | 160 | 2026-06-15 | 2 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.analytics.metrics` | `tracker_system/analytics/metrics.py` | 159 | 2026-05-14 | 8 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.market.retry_policy` | `quant_hedge_ai/agents/market/retry_policy.py` | 158 | 2026-05-26 | 4 | atteignable par import depuis le point d'entrée runtime |
| `system.integrity_snapshot` | `system/integrity_snapshot.py` | 157 | 2026-05-29 | 3 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.analytics.score_drift_monitor` | `tracker_system/analytics/score_drift_monitor.py` | 155 | 2026-05-14 | 2 | atteignable par import depuis le point d'entrée runtime |
| `capital_deployment.operational_state` | `capital_deployment/operational_state.py` | 150 | 2026-05-31 | 2 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.core.trade_logger` | `tracker_system/core/trade_logger.py` | 148 | 2026-05-08 | 7 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.market.multi_timeframe_scanner` | `quant_hedge_ai/agents/market/multi_timeframe_scanner.py` | 146 | 2026-05-26 | 4 | atteignable par import depuis le point d'entrée runtime |
| `execution_simulator.simulator` | `execution_simulator/simulator.py` | 145 | 2026-05-14 | 4 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.main` | `tracker_system/main.py` | 145 | 2026-05-14 | 3 | atteignable par import depuis le point d'entrée runtime |
| `config.parameter_audit` | `config/parameter_audit.py` | 142 | 2026-06-20 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.execution.multi_timeframe_signal` | `quant_hedge_ai/agents/execution/multi_timeframe_signal.py` | 140 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.regime_transition_smoother` | `quant_hedge_ai/agents/intelligence/regime_transition_smoother.py` | 139 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.execution.signal_engine` | `quant_hedge_ai/agents/execution/signal_engine.py` | 137 | 2026-05-29 | 8 | atteignable par import depuis le point d'entrée runtime |
| `capital_deployment.capital_throttle` | `capital_deployment/capital_throttle.py` | 135 | 2026-05-29 | 6 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.market.ohlcv_validator` | `quant_hedge_ai/agents/market/ohlcv_validator.py` | 133 | 2026-05-26 | 12 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.scheduler.auto_update` | `tracker_system/scheduler/auto_update.py` | 133 | 2026-05-05 | 3 | atteignable par import depuis le point d'entrée runtime |
| `exchange_constraints.precision_rules` | `exchange_constraints/precision_rules.py` | 132 | 2026-05-14 | 4 | atteignable par import depuis le point d'entrée runtime |
| `execution_simulator.config` | `execution_simulator/config.py` | 129 | 2026-06-13 | 4 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.core.boot_validator` | `tracker_system/core/boot_validator.py` | 129 | 2026-05-26 | 1 | atteignable par import depuis le point d'entrée runtime |
| `execution_simulator.fill_simulator` | `execution_simulator/fill_simulator.py` | 127 | 2026-05-14 | 3 | atteignable par import depuis le point d'entrée runtime |
| `execution_simulator.slippage` | `execution_simulator/slippage.py` | 126 | 2026-05-14 | 3 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.config.exit_config` | `tracker_system/config/exit_config.py` | 125 | 2026-05-14 | 4 | atteignable par import depuis le point d'entrée runtime |
| `exchange_constraints.binance_rules` | `exchange_constraints/binance_rules.py` | 122 | 2026-06-13 | 4 | atteignable par import depuis le point d'entrée runtime |
| `crypto.blackbox_encryption` | `crypto/blackbox_encryption.py` | 115 | 2026-05-29 | 4 | atteignable par import depuis le point d'entrée runtime |
| `supervision.alert_manager` | `supervision/alert_manager.py` | 112 | 2026-04-28 | 6 | atteignable par import depuis le point d'entrée runtime |
| `core.authority` | `core/authority.py` | 109 | 2026-06-02 | 4 | atteignable par import depuis le point d'entrée runtime |
| `tools.regret_repository` | `tools/regret_repository.py` | 102 | 2026-07-21 | 1 | atteignable par import depuis le point d'entrée runtime |
| `core.topk_scheduler` | `core/topk_scheduler.py` | 101 | 2026-07-17 | 2 | atteignable par import depuis le point d'entrée runtime |
| `execution_simulator.spread` | `execution_simulator/spread.py` | 101 | 2026-05-14 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.capital_throttle` | `quant_hedge_ai/agents/risk/capital_throttle.py` | 101 | 2026-05-26 | 2 | atteignable par import depuis le point d'entrée runtime |
| `crypto.key_derivation` | `crypto/key_derivation.py` | 94 | 2026-05-29 | 5 | atteignable par import depuis le point d'entrée runtime |
| `execution_simulator.latency` | `execution_simulator/latency.py` | 92 | 2026-05-14 | 3 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.risk.exposure_manager` | `quant_hedge_ai/agents/risk/exposure_manager.py` | 91 | 2026-05-26 | 3 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.backtesting.auto_backtester` | `tracker_system/backtesting/auto_backtester.py` | 90 | 2026-05-05 | 7 | atteignable par import depuis le point d'entrée runtime |
| `observability.system_snapshot_event_bus` | `observability/system_snapshot_event_bus.py` | 76 | 2026-07-05 | 1 | atteignable par import depuis le point d'entrée runtime |
| `lm_studio.ai_router` | `lm_studio/ai_router.py` | 69 | 2026-05-29 | 5 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.execution.order_deduplicator` | `quant_hedge_ai/agents/execution/order_deduplicator.py` | 64 | 2026-05-26 | 7 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.meta_memory` | `tracker_system/meta_memory.py` | 60 | 2026-05-05 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.system_invariants` | `quant_hedge_ai/agents/intelligence/system_invariants.py` | 59 | 2026-05-16 | 1 | atteignable par import depuis le point d'entrée runtime |
| `config.feature_flags` | `config/feature_flags.py` | 55 | 2026-06-30 | 2 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.dashboard.live_snapshot` | `quant_hedge_ai/dashboard/live_snapshot.py` | 55 | 2026-05-26 | 1 | atteignable par import depuis le point d'entrée runtime |
| `quant_hedge_ai.agents.intelligence.regime_detector` | `quant_hedge_ai/agents/intelligence/regime_detector.py` | 51 | 2026-06-12 | 7 | atteignable par import depuis le point d'entrée runtime |
| `supervision.notifications.telegram_notifier` | `supervision/notifications/telegram_notifier.py` | 37 | 2026-05-26 | 8 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.storage.loader` | `tracker_system/storage/loader.py` | 31 | 2026-05-05 | 13 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.engine.exit_engine` | `tracker_system/engine/exit_engine.py` | 29 | 2026-05-05 | 9 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.engine.rules.breakeven` | `tracker_system/engine/rules/breakeven.py` | 27 | 2026-05-05 | 2 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.engine.rules.tp_sl` | `tracker_system/engine/rules/tp_sl.py` | 27 | 2026-05-05 | 6 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.analytics.regime_analysis` | `tracker_system/analytics/regime_analysis.py` | 26 | 2026-05-05 | 1 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.backtesting.simulator` | `tracker_system/backtesting/simulator.py` | 26 | 2026-05-05 | 2 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.analytics.mfe_mae` | `tracker_system/analytics/mfe_mae.py` | 24 | 2026-05-05 | 1 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.core.position_manager` | `tracker_system/core/position_manager.py` | 24 | 2026-05-05 | 4 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.engine.rules.trailing` | `tracker_system/engine/rules/trailing.py` | 22 | 2026-05-05 | 3 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.engine.exit_factory` | `tracker_system/engine/exit_factory.py` | 18 | 2026-05-05 | 6 | atteignable par import depuis le point d'entrée runtime |
| `tracker_system.storage.saver` | `tracker_system/storage/saver.py` | 16 | 2026-05-05 | 7 | atteignable par import depuis le point d'entrée runtime |
| `lm_studio` | `lm_studio/__init__.py` | 13 | 2026-05-05 | 5 | atteignable par import depuis le point d'entrée runtime |

## TOOL — 94 modules

| Module | Fichier | LOC | Dernier commit | Importé par | Justification |
|---|---|---:|---|---:|---|
| `quant_hedge_ai.main_v91` | `quant_hedge_ai/main_v91.py` | 1111 | 2026-06-12 | 0 | script autonome (__main__), jamais importé |
| `scripts.data_verifier` | `scripts/data_verifier.py` | 971 | 2026-06-13 | 0 | script autonome (__main__), jamais importé |
| `scripts.regret_audit` | `scripts/regret_audit.py` | 823 | 2026-06-23 | 0 | script autonome (__main__), jamais importé |
| `scripts.boot_system_validator` | `scripts/boot_system_validator.py` | 734 | 2026-06-13 | 0 | script autonome (__main__), jamais importé |
| `project_os.reporter` | `project_os/reporter.py` | 531 | 2026-05-14 | 0 | script autonome (__main__), jamais importé |
| `project_os.dep_mapper` | `project_os/dep_mapper.py` | 525 | 2026-05-14 | 0 | script autonome (__main__), jamais importé |
| `scripts.audit_r2` | `scripts/audit_r2.py` | 505 | 2026-06-23 | 0 | script autonome (__main__), jamais importé |
| `scripts.stream_bus_simulation` | `scripts/stream_bus_simulation.py` | 495 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `certification.p10_checker` | `certification/p10_checker.py` | 471 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `quant_hedge_ai.bench_boot_constructors` | `quant_hedge_ai/bench_boot_constructors.py` | 451 | 2026-06-13 | 0 | script autonome (__main__), jamais importé |
| `tools.runtime_cartographer` | `tools/runtime_cartographer.py` | 447 | UNTRACKED | 0 | script autonome (__main__), jamais importé |
| `scripts.counterfactual_replay` | `scripts/counterfactual_replay.py` | 444 | 2026-06-23 | 0 | script autonome (__main__), jamais importé |
| `tools.generate_miniature` | `tools/generate_miniature.py` | 439 | 2026-05-31 | 0 | script autonome (__main__), jamais importé |
| `project_os.doc_indexer` | `project_os/doc_indexer.py` | 373 | 2026-05-14 | 0 | script autonome (__main__), jamais importé |
| `project_os.scanner` | `project_os/scanner.py` | 356 | 2026-05-14 | 0 | script autonome (__main__), jamais importé |
| `quant_hedge_ai.bench_session_contention` | `quant_hedge_ai/bench_session_contention.py` | 342 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `scripts.default_path_audit` | `scripts/default_path_audit.py` | 338 | 2026-07-03 | 0 | script autonome (__main__), jamais importé |
| `scripts.dashboard` | `scripts/dashboard.py` | 316 | 2026-06-29 | 0 | script autonome (__main__), jamais importé |
| `quant_hedge_ai.bench_ccxt_cold` | `quant_hedge_ai/bench_ccxt_cold.py` | 313 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `quant_hedge_ai.fetch_audit` | `quant_hedge_ai/fetch_audit.py` | 313 | 2026-06-13 | 0 | script autonome (__main__), jamais importé |
| `quant_hedge_ai.bench_e2e_warmup` | `quant_hedge_ai/bench_e2e_warmup.py` | 307 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `quant_hedge_ai.backtest_real` | `quant_hedge_ai/backtest_real.py` | 305 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `scripts.burnin_v2_report` | `scripts/burnin_v2_report.py` | 290 | 2026-06-22 | 0 | script autonome (__main__), jamais importé |
| `scripts.runtime_validator` | `scripts/runtime_validator.py` | 283 | 2026-06-15 | 0 | script autonome (__main__), jamais importé |
| `S3.02_log_surveillance` | `S3/02_log_surveillance.py` | 279 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `scripts.chaos_test` | `scripts/chaos_test.py` | 276 | 2026-06-29 | 0 | script autonome (__main__), jamais importé |
| `project_os.maturity` | `project_os/maturity.py` | 272 | 2026-05-14 | 0 | script autonome (__main__), jamais importé |
| `scripts.validate_historical` | `scripts/validate_historical.py` | 272 | 2026-04-27 | 0 | script autonome (__main__), jamais importé |
| `project_os.roadmap_state` | `project_os/roadmap_state.py` | 268 | 2026-05-14 | 0 | script autonome (__main__), jamais importé |
| `scripts.delta_sensitivity` | `scripts/delta_sensitivity.py` | 268 | 2026-06-23 | 0 | script autonome (__main__), jamais importé |
| `infra.multi_exchange_feed` | `infra/multi_exchange_feed.py` | 265 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `tools.analyze_cycles` | `tools/analyze_cycles.py` | 262 | 2026-05-06 | 0 | script autonome (__main__), jamais importé |
| `S3.05_s3_report` | `S3/05_s3_report.py` | 261 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `tools.runtime_tracer` | `tools/runtime_tracer.py` | 255 | 2026-06-13 | 0 | script autonome (__main__), jamais importé |
| `tools.decision_trace` | `tools/decision_trace.py` | 250 | 2026-07-06 | 0 | script autonome (__main__), jamais importé |
| `src.telegram.quant_observer.bot` | `src/telegram/quant_observer/bot.py` | 244 | 2026-07-06 | 0 | script autonome (__main__), jamais importé |
| `S3.03_shadow_execution` | `S3/03_shadow_execution.py` | 242 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `core.main` | `core/main.py` | 239 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `reports.live_observer_report` | `reports/live_observer_report.py` | 238 | 2026-07-06 | 0 | script autonome (__main__), jamais importé |
| `scripts.ONBOARDING_SCRIPT` | `scripts/ONBOARDING_SCRIPT.py` | 236 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.migrate_to_structured_logger` | `scripts/migrate_to_structured_logger.py` | 234 | 2026-05-26 | 0 | script autonome (__main__), jamais importé |
| `scripts.sqlite_contamination_audit` | `scripts/sqlite_contamination_audit.py` | 234 | 2026-07-03 | 0 | script autonome (__main__), jamais importé |
| `project_os.debt_map` | `project_os/debt_map.py` | 229 | 2026-05-14 | 0 | script autonome (__main__), jamais importé |
| `S3.04_resilience_test` | `S3/04_resilience_test.py` | 225 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `quant_hedge_ai.main_system` | `quant_hedge_ai/main_system.py` | 224 | 2026-04-27 | 0 | script autonome (__main__), jamais importé |
| `S2.05_paper_tracker` | `S2/05_paper_tracker.py` | 220 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `scripts.performance_check` | `scripts/performance_check.py` | 217 | 2026-06-28 | 0 | script autonome (__main__), jamais importé |
| `quant_hedge_ai.bench_1h_limit` | `quant_hedge_ai/bench_1h_limit.py` | 214 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `S3.01_telegram_alerts` | `S3/01_telegram_alerts.py` | 207 | 2026-05-26 | 0 | script autonome (__main__), jamais importé |
| `core.launch_pieuvre` | `core/launch_pieuvre.py` | 207 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.demo_p0_integration` | `scripts/demo_p0_integration.py` | 196 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `scripts.replay_cli` | `scripts/replay_cli.py` | 193 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.run_all_tests` | `scripts/run_all_tests.py` | 191 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `infra.notifications.notify_test_status` | `infra/notifications/notify_test_status.py` | 190 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.stress_test_cli` | `scripts/stress_test_cli.py` | 190 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `S2.02_score_distribution` | `S2/02_score_distribution.py` | 185 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `scripts.seed_strategy_memory` | `scripts/seed_strategy_memory.py` | 183 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `S2.03_self_awareness_calibrator` | `S2/03_self_awareness_calibrator.py` | 180 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `S2.04_conviction_calibrator` | `S2/04_conviction_calibrator.py` | 180 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `scripts.perp_universe_scan` | `scripts/perp_universe_scan.py` | 176 | 2026-06-15 | 0 | script autonome (__main__), jamais importé |
| `infra.monitoring.observer_logs` | `infra/monitoring/observer_logs.py` | 156 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.generate_audit_report` | `scripts/generate_audit_report.py` | 156 | 2026-04-27 | 0 | script autonome (__main__), jamais importé |
| `S2.01_gate_logger` | `S2/01_gate_logger.py` | 155 | 2026-05-25 | 0 | script autonome (__main__), jamais importé |
| `src.telegram.bot_runner` | `src/telegram/bot_runner.py` | 152 | 2026-06-08 | 0 | script autonome (__main__), jamais importé |
| `certification.hash_verifier` | `certification/hash_verifier.py` | 144 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.final_validation` | `scripts/final_validation.py` | 134 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `paper_trading.sandbox_validator` | `paper_trading/sandbox_validator.py` | 132 | 2026-06-13 | 0 | script autonome (__main__), jamais importé |
| `scripts.generate_ai_quant_lab_structure` | `scripts/generate_ai_quant_lab_structure.py` | 129 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.cleanup_root` | `scripts/cleanup_root.py` | 122 | 2026-06-08 | 0 | script autonome (__main__), jamais importé |
| `scripts.generate_html_report` | `scripts/generate_html_report.py` | 121 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.diagnostic_env` | `scripts/diagnostic_env.py` | 107 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.TEST_AUDIT_FR` | `scripts/TEST_AUDIT_FR.py` | 106 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `paper_trading.status` | `paper_trading/status.py` | 98 | 2026-05-18 | 0 | script autonome (__main__), jamais importé |
| `infra.panels.panel_selenium_test` | `infra/panels/panel_selenium_test.py` | 94 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `infra.panels.panel_http_test` | `infra/panels/panel_http_test.py` | 89 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `infra.visualization.visualize_strategy_ecosystem_all_gens` | `infra/visualization/visualize_strategy_ecosystem_all_gens.py` | 83 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.vps_data_sync` | `scripts/vps_data_sync.py` | 80 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.validate_trade_dataset` | `scripts/validate_trade_dataset.py` | 74 | 2026-06-14 | 0 | script autonome (__main__), jamais importé |
| `infra.visualization.visualize_strategy_ecosystem` | `infra/visualization/visualize_strategy_ecosystem.py` | 72 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.run_multi_simulations` | `scripts/run_multi_simulations.py` | 64 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.export_excel_report` | `scripts/export_excel_report.py` | 60 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.generate_report` | `scripts/generate_report.py` | 57 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.plotly_matplotlib_compat` | `scripts/plotly_matplotlib_compat.py` | 54 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `scripts.performance_benchmarks` | `scripts/performance_benchmarks.py` | 53 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `lm_studio.status` | `lm_studio/status.py` | 52 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `scripts.panels_with_report` | `scripts/panels_with_report.py` | 52 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `supervision.monitoring_profiler` | `supervision/monitoring_profiler.py` | 52 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `scripts.generate_test_report` | `scripts/generate_test_report.py` | 44 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.check_badges` | `scripts/check_badges.py` | 38 | 2026-04-27 | 0 | script autonome (__main__), jamais importé |
| `core.orchestration.orchestrate_panels_test` | `core/orchestration/orchestrate_panels_test.py` | 34 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.validate_population_csv` | `scripts/validate_population_csv.py` | 29 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `scripts.generate_coverage_report` | `scripts/generate_coverage_report.py` | 19 | 2026-05-29 | 0 | script autonome (__main__), jamais importé |
| `scripts.optimization_stack_validator` | `scripts/optimization_stack_validator.py` | 17 | 2026-05-05 | 0 | script autonome (__main__), jamais importé |
| `sdos_terminal.run` | `sdos_terminal/run.py` | 12 | 2026-07-06 | 0 | script autonome (__main__), jamais importé |

## TEST_ONLY — 279 modules

| Module | Fichier | LOC | Dernier commit | Importé par | Justification |
|---|---|---:|---|---:|---|
| `tools.live_observer_validator` | `tools/live_observer_validator.py` | 1396 | 2026-07-06 | 2 | atteignable uniquement depuis les tests |
| `tools.score_calibration_audit` | `tools/score_calibration_audit.py` | 1233 | 2026-07-29 | 1 | atteignable uniquement depuis les tests |
| `src.telegram.sim_bot` | `src/telegram/sim_bot.py` | 1207 | 2026-06-12 | 2 | atteignable uniquement depuis les tests |
| `tools.instrumentation_validator` | `tools/instrumentation_validator.py` | 1102 | 2026-07-06 | 1 | atteignable uniquement depuis les tests |
| `scripts.vps_burn_in_collector` | `scripts/vps_burn_in_collector.py` | 1029 | 2026-06-03 | 1 | atteignable uniquement depuis les tests |
| `tools.experiment_quality_audit` | `tools/experiment_quality_audit.py` | 985 | 2026-07-30 | 1 | atteignable uniquement depuis les tests |
| `system.provenance` | `system/provenance.py` | 910 | 2026-07-30 | 7 | atteignable uniquement depuis les tests |
| `core.initialization_contract` | `core/initialization_contract.py` | 844 | 2026-06-02 | 1 | atteignable uniquement depuis les tests |
| `tools.chain_audit` | `tools/chain_audit.py` | 721 | 2026-07-30 | 1 | atteignable uniquement depuis les tests |
| `scripts.burnin_calibration_v3` | `scripts/burnin_calibration_v3.py` | 694 | 2026-07-30 | 2 | atteignable uniquement depuis les tests |
| `tools.protocol_efficacy_audit` | `tools/protocol_efficacy_audit.py` | 680 | 2026-07-30 | 1 | atteignable uniquement depuis les tests |
| `dip.modules.decision_graph` | `dip/modules/decision_graph.py` | 659 | 2026-06-30 | 17 | atteignable uniquement depuis les tests |
| `tools.dataset_certifier` | `tools/dataset_certifier.py` | 643 | 2026-06-30 | 1 | atteignable uniquement depuis les tests |
| `supervision.recovery_playbooks` | `supervision/recovery_playbooks.py` | 634 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `dip.cli` | `dip/cli.py` | 591 | 2026-06-30 | 2 | atteignable uniquement depuis les tests |
| `scripts.prelive_gate` | `scripts/prelive_gate.py` | 565 | 2026-07-30 | 1 | atteignable uniquement depuis les tests |
| `dip.modules.causal_tree` | `dip/modules/causal_tree.py` | 525 | 2026-06-30 | 10 | atteignable uniquement depuis les tests |
| `analysis.base` | `analysis/base.py` | 495 | 2026-07-31 | 8 | atteignable uniquement depuis les tests |
| `scripts.sqlite_contamination_cleanup` | `scripts/sqlite_contamination_cleanup.py` | 495 | 2026-07-06 | 1 | atteignable uniquement depuis les tests |
| `certification.module_certifier` | `certification/module_certifier.py` | 490 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `supervision.healing_actions` | `supervision/healing_actions.py` | 486 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `execution_simulator.fill_error_metric` | `execution_simulator/fill_error_metric.py` | 477 | 2026-05-14 | 3 | atteignable uniquement depuis les tests |
| `dip.modules.knowledge_base` | `dip/modules/knowledge_base.py` | 469 | 2026-06-30 | 5 | atteignable uniquement depuis les tests |
| `tracker_system.tracker` | `tracker_system/tracker.py` | 469 | 2026-05-05 | 3 | atteignable uniquement depuis les tests |
| `market_data.metrics.flow` | `market_data/metrics/flow.py` | 467 | 2026-05-14 | 5 | atteignable uniquement depuis les tests |
| `dip.modules.decision_timeline` | `dip/modules/decision_timeline.py` | 450 | 2026-06-30 | 4 | atteignable uniquement depuis les tests |
| `pieuvre.brain` | `pieuvre/brain.py` | 447 | 2026-05-26 | 4 | atteignable uniquement depuis les tests |
| `dip.modules.ai_investigator` | `dip/modules/ai_investigator.py` | 446 | 2026-06-30 | 1 | atteignable uniquement depuis les tests |
| `system.burn_in` | `system/burn_in.py` | 441 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `supervision.latency_baseline_monitor` | `supervision/latency_baseline_monitor.py` | 432 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `runtime.advisor_main` | `runtime/advisor_main.py` | 427 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `dip.modules.counterfactual` | `dip/modules/counterfactual.py` | 424 | 2026-06-30 | 5 | atteignable uniquement depuis les tests |
| `visualization.decision_trace_service` | `visualization/decision_trace_service.py` | 420 | 2026-07-06 | 4 | atteignable uniquement depuis les tests |
| `dip.core.store` | `dip/core/store.py` | 419 | 2026-06-30 | 20 | atteignable uniquement depuis les tests |
| `infra.monitoring.watchdog_vps` | `infra/monitoring/watchdog_vps.py` | 406 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `dip.modules.decision_heatmap` | `dip/modules/decision_heatmap.py` | 403 | 2026-06-30 | 4 | atteignable uniquement depuis les tests |
| `supervision.ops_watchdog_hardened` | `supervision/ops_watchdog_hardened.py` | 401 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `dip.modules.decision_alert` | `dip/modules/decision_alert.py` | 399 | 2026-06-30 | 4 | atteignable uniquement depuis les tests |
| `dip.modules.explainability` | `dip/modules/explainability.py` | 399 | 2026-06-30 | 6 | atteignable uniquement depuis les tests |
| `core.contracts` | `core/contracts.py` | 398 | 2026-05-26 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.risk.order_sizer` | `quant_hedge_ai/agents/risk/order_sizer.py` | 390 | 2026-06-02 | 4 | atteignable uniquement depuis les tests |
| `tracker_system.ml.exit_predictor` | `tracker_system/ml/exit_predictor.py` | 382 | 2026-05-08 | 1 | atteignable uniquement depuis les tests |
| `observation.market_radar` | `observation/market_radar.py` | 381 | 2026-07-19 | 2 | atteignable uniquement depuis les tests |
| `system.performance_metrics` | `system/performance_metrics.py` | 380 | 2026-07-29 | 4 | atteignable uniquement depuis les tests |
| `tools.init_order_audit` | `tools/init_order_audit.py` | 378 | 2026-07-29 | 1 | atteignable uniquement depuis les tests |
| `supervision.escalation_engine` | `supervision/escalation_engine.py` | 370 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `system.pending_order_tracker` | `system/pending_order_tracker.py` | 370 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `cold_start.warmup_invariants` | `cold_start/warmup_invariants.py` | 369 | 2026-05-29 | 5 | atteignable uniquement depuis les tests |
| `system.burnin_analytics` | `system/burnin_analytics.py` | 367 | 2026-06-03 | 2 | atteignable uniquement depuis les tests |
| `dip.modules.decision_export` | `dip/modules/decision_export.py` | 366 | 2026-06-30 | 3 | atteignable uniquement depuis les tests |
| `cold_start.warmup_scenarios` | `cold_start/warmup_scenarios.py` | 365 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `observation.market_observer` | `observation/market_observer.py` | 354 | 2026-07-19 | 6 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.execution.trade_postmortem` | `quant_hedge_ai/agents/execution/trade_postmortem.py` | 354 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `tools.throughput_probe` | `tools/throughput_probe.py` | 353 | 2026-07-16 | 1 | atteignable uniquement depuis les tests |
| `tracker_system.safety.safe_execution_framework` | `tracker_system/safety/safe_execution_framework.py` | 350 | 2026-05-05 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.monitoring.prompt_doctor_agent` | `quant_hedge_ai/agents/monitoring/prompt_doctor_agent.py` | 344 | 2026-05-05 | 2 | atteignable uniquement depuis les tests |
| `paper_trading.virtual_portfolio` | `paper_trading/virtual_portfolio.py` | 342 | 2026-06-03 | 1 | atteignable uniquement depuis les tests |
| `analysis.hypotheses` | `analysis/hypotheses.py` | 340 | 2026-07-31 | 2 | atteignable uniquement depuis les tests |
| `cold_start.cold_start_manager` | `cold_start/cold_start_manager.py` | 338 | 2026-05-29 | 10 | atteignable uniquement depuis les tests |
| `dip.modules.decision_replay` | `dip/modules/decision_replay.py` | 338 | 2026-06-30 | 4 | atteignable uniquement depuis les tests |
| `supervision.proactive_alerts` | `supervision/proactive_alerts.py` | 337 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `infra.monitoring.daily_analyzer` | `infra/monitoring/daily_analyzer.py` | 325 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `monitor.degradation_tracker` | `monitor/degradation_tracker.py` | 311 | 2026-05-14 | 4 | atteignable uniquement depuis les tests |
| `cold_start.warmup_state_machine` | `cold_start/warmup_state_machine.py` | 308 | 2026-05-29 | 14 | atteignable uniquement depuis les tests |
| `signal.evolution.evolution_memory` | `signal/evolution/evolution_memory.py` | 308 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `dip.modules.decision_diff` | `dip/modules/decision_diff.py` | 307 | 2026-06-30 | 2 | atteignable uniquement depuis les tests |
| `event_bus.bridge` | `event_bus/bridge.py` | 307 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `dip.modules.audit_trail` | `dip/modules/audit_trail.py` | 305 | 2026-06-30 | 4 | atteignable uniquement depuis les tests |
| `observation.horizon_evaluator` | `observation/horizon_evaluator.py` | 302 | 2026-07-19 | 1 | atteignable uniquement depuis les tests |
| `tracker_system.trade_tracker` | `tracker_system/trade_tracker.py` | 302 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `runtime.runtime_coordinator` | `runtime/runtime_coordinator.py` | 301 | 2026-05-29 | 4 | atteignable uniquement depuis les tests |
| `cold_start.market_warmup_estimator` | `cold_start/market_warmup_estimator.py` | 300 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `market_data.replay_engine` | `market_data/replay_engine.py` | 300 | 2026-05-14 | 4 | atteignable uniquement depuis les tests |
| `tracker_system.analytics.advanced_metrics` | `tracker_system/analytics/advanced_metrics.py` | 299 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `dip.modules.decision_sankey` | `dip/modules/decision_sankey.py` | 295 | 2026-06-30 | 2 | atteignable uniquement depuis les tests |
| `reality_checks.reality_gap_analyzer` | `reality_checks/reality_gap_analyzer.py` | 292 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `tracker_system.portfolio.multi_asset` | `tracker_system/portfolio/multi_asset.py` | 292 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `crypto.tamper_evident_logs` | `crypto/tamper_evident_logs.py` | 288 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `walk_forward.reporter` | `walk_forward/reporter.py` | 287 | 2026-05-14 | 3 | atteignable uniquement depuis les tests |
| `core.warm_boot` | `core/warm_boot.py` | 285 | 2026-05-31 | 3 | atteignable uniquement depuis les tests |
| `tools.exit_replay` | `tools/exit_replay.py` | 282 | 2026-07-19 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.runtime.fault_containment` | `quant_hedge_ai/runtime/fault_containment.py` | 281 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.quant.backtest_lab` | `quant_hedge_ai/agents/quant/backtest_lab.py` | 274 | 2026-05-26 | 10 | atteignable uniquement depuis les tests |
| `certification.audit_trail_final` | `certification/audit_trail_final.py` | 273 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `paper_trading.engine` | `paper_trading/engine.py` | 271 | 2026-06-13 | 1 | atteignable uniquement depuis les tests |
| `tracker_system.intelligence.auto_regime_detector` | `tracker_system/intelligence/auto_regime_detector.py` | 270 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `certification.final_gate` | `certification/final_gate.py` | 269 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `market_data.models` | `market_data/models.py` | 267 | 2026-05-14 | 11 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.intelligence.weekly_report` | `quant_hedge_ai/agents/intelligence/weekly_report.py` | 267 | 2026-05-26 | 2 | atteignable uniquement depuis les tests |
| `risk.circuit_breaker` | `risk/circuit_breaker.py` | 267 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `scripts.health_check` | `scripts/health_check.py` | 264 | 2026-06-29 | 3 | atteignable uniquement depuis les tests |
| `core.bootstrap_integration` | `core/bootstrap_integration.py` | 261 | 2026-06-12 | 2 | atteignable uniquement depuis les tests |
| `metrics.oos_metrics` | `metrics/oos_metrics.py` | 257 | 2026-05-14 | 8 | atteignable uniquement depuis les tests |
| `src.storage.run_repository` | `src/storage/run_repository.py` | 255 | 2026-06-08 | 2 | atteignable uniquement depuis les tests |
| `watchdog_vps` | `watchdog_vps.py` | 250 | 2026-07-04 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.market.historical_fetcher` | `quant_hedge_ai/agents/market/historical_fetcher.py` | 248 | 2026-06-13 | 3 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.ai_evolution.evolution_engine` | `quant_hedge_ai/ai_evolution/evolution_engine.py` | 244 | 2026-05-26 | 4 | atteignable uniquement depuis les tests |
| `tracker_system.backtest.backtest_engine` | `tracker_system/backtest/backtest_engine.py` | 242 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.audit_commits` | `pieuvre/tentacles/audit_commits.py` | 241 | 2026-05-26 | 2 | atteignable uniquement depuis les tests |
| `analysis.regime_audit` | `analysis/regime_audit.py` | 239 | 2026-07-31 | 2 | atteignable uniquement depuis les tests |
| `paper_trading.ledger` | `paper_trading/ledger.py` | 239 | 2026-05-14 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.quant.walk_forward` | `quant_hedge_ai/agents/quant/walk_forward.py` | 238 | 2026-05-26 | 5 | atteignable uniquement depuis les tests |
| `tools.exit_audit` | `tools/exit_audit.py` | 238 | 2026-07-17 | 2 | atteignable uniquement depuis les tests |
| `certification.doc_freeze` | `certification/doc_freeze.py` | 235 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.runtime.chaos_orchestrator` | `quant_hedge_ai/runtime/chaos_orchestrator.py` | 230 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `certification.operator_signoff` | `certification/operator_signoff.py` | 225 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `monitoring.metrics` | `monitoring/metrics.py` | 225 | 2026-05-23 | 3 | atteignable uniquement depuis les tests |
| `core.orchestration.orchestrate_ecosystem` | `core/orchestration/orchestrate_ecosystem.py` | 223 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `cold_start.warmup_report` | `cold_start/warmup_report.py` | 222 | 2026-07-03 | 1 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.surveillance` | `pieuvre/tentacles/surveillance.py` | 222 | 2026-05-26 | 2 | atteignable uniquement depuis les tests |
| `visualization.api.models` | `visualization/api/models.py` | 222 | 2026-07-06 | 14 | atteignable uniquement depuis les tests |
| `system.equity_curve` | `system/equity_curve.py` | 221 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.securite` | `pieuvre/tentacles/securite.py` | 220 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `observation.accounts.store` | `observation/accounts/store.py` | 218 | 2026-07-31 | 1 | atteignable uniquement depuis les tests |
| `system.invariant_checker` | `system/invariant_checker.py` | 218 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `crypto.api_key_vault` | `crypto/api_key_vault.py` | 216 | UNTRACKED | 1 | atteignable uniquement depuis les tests |
| `market_data.metrics.orderbook` | `market_data/metrics/orderbook.py` | 211 | 2026-05-14 | 3 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.evolution` | `pieuvre/tentacles/evolution.py` | 211 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `runtime.lifecycle_manager` | `runtime/lifecycle_manager.py` | 209 | 2026-05-29 | 4 | atteignable uniquement depuis les tests |
| `capital_deployment.phase_certifier` | `capital_deployment/phase_certifier.py` | 208 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `certification.live_kpi_auditor` | `certification/live_kpi_auditor.py` | 207 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `system.strategy_metrics` | `system/strategy_metrics.py` | 207 | 2026-06-03 | 8 | atteignable uniquement depuis les tests |
| `system.strategy_score` | `system/strategy_score.py` | 207 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `certification.prerequisite_checker` | `certification/prerequisite_checker.py` | 206 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `system.walk_forward` | `system/walk_forward.py` | 206 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `crypto.audit_trail` | `crypto/audit_trail.py` | 203 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `tracker_system.risk.portfolio_risk` | `tracker_system/risk/portfolio_risk.py` | 202 | 2026-05-11 | 2 | atteignable uniquement depuis les tests |
| `observation.accounts.trade_collector` | `observation/accounts/trade_collector.py` | 201 | 2026-08-01 | 2 | atteignable uniquement depuis les tests |
| `scripts.preflight` | `scripts/preflight.py` | 201 | 2026-06-29 | 2 | atteignable uniquement depuis les tests |
| `src.paper.paper_runner` | `src/paper/paper_runner.py` | 201 | 2026-06-04 | 1 | atteignable uniquement depuis les tests |
| `monitoring.pipeline_monitor` | `monitoring/pipeline_monitor.py` | 199 | 2026-05-14 | 1 | atteignable uniquement depuis les tests |
| `observation.accounts.account_collector` | `observation/accounts/account_collector.py` | 199 | 2026-08-01 | 1 | atteignable uniquement depuis les tests |
| `runtime.system_state_bus` | `runtime/system_state_bus.py` | 196 | 2026-05-29 | 5 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.health_endpoint` | `quant_hedge_ai/health_endpoint.py` | 195 | 2026-05-26 | 2 | atteignable uniquement depuis les tests |
| `walk_forward.engine` | `walk_forward/engine.py` | 195 | 2026-05-14 | 5 | atteignable uniquement depuis les tests |
| `config.settings` | `config/settings.py` | 193 | 2026-06-13 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.market_db` | `quant_hedge_ai/strategy_lab/market_db.py` | 193 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `certification.immutable_stamp` | `certification/immutable_stamp.py` | 190 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `src.telegram.notifier` | `src/telegram/notifier.py` | 190 | 2026-06-08 | 2 | atteignable uniquement depuis les tests |
| `crypto.secure_channels` | `crypto/secure_channels.py` | 189 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `system.monte_carlo` | `system/monte_carlo.py` | 187 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `walk_forward.walk_forward_loop` | `walk_forward/walk_forward_loop.py` | 186 | 2026-05-14 | 5 | atteignable uniquement depuis les tests |
| `cold_start.bypass_detector` | `cold_start/bypass_detector.py` | 185 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `system.boot_gate` | `system/boot_gate.py` | 183 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.resilience` | `pieuvre/tentacles/resilience.py` | 182 | 2026-06-13 | 2 | atteignable uniquement depuis les tests |
| `monitoring.logger` | `monitoring/logger.py` | 179 | 2026-05-14 | 2 | atteignable uniquement depuis les tests |
| `supervision.ops_watchdog` | `supervision/ops_watchdog.py` | 178 | 2026-05-26 | 4 | atteignable uniquement depuis les tests |
| `cold_start.warmup_metrics` | `cold_start/warmup_metrics.py` | 174 | 2026-05-27 | 5 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.runtime.event_journal` | `quant_hedge_ai/runtime/event_journal.py` | 174 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.performance` | `pieuvre/tentacles/performance.py` | 173 | 2026-05-26 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.advisor_only_mode` | `quant_hedge_ai/advisor_only_mode.py` | 173 | 2026-05-26 | 2 | atteignable uniquement depuis les tests |
| `infra.startup_cache` | `infra/startup_cache.py` | 172 | 2026-05-29 | 6 | atteignable uniquement depuis les tests |
| `cold_start.warmup_signer` | `cold_start/warmup_signer.py` | 171 | 2026-05-29 | 12 | atteignable uniquement depuis les tests |
| `tracker_system.risk.execution_reality` | `tracker_system/risk/execution_reality.py` | 168 | 2026-05-05 | 2 | atteignable uniquement depuis les tests |
| `supervision.notifications.ops_notifier` | `supervision/notifications/ops_notifier.py` | 165 | 2026-05-26 | 5 | atteignable uniquement depuis les tests |
| `audit.trade_audit` | `audit/trade_audit.py` | 163 | 2026-05-05 | 3 | atteignable uniquement depuis les tests |
| `system.regime_validator` | `system/regime_validator.py` | 162 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `audit.replay_engine` | `audit/replay_engine.py` | 156 | 2026-05-05 | 3 | atteignable uniquement depuis les tests |
| `walk_forward.window_splitter` | `walk_forward/window_splitter.py` | 153 | 2026-05-14 | 6 | atteignable uniquement depuis les tests |
| `capital_deployment.phase_gate` | `capital_deployment/phase_gate.py` | 152 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `tracker_system.core.event_writer` | `tracker_system/core/event_writer.py` | 150 | 2026-05-05 | 2 | atteignable uniquement depuis les tests |
| `pieuvre.incidents.models` | `pieuvre/incidents/models.py` | 148 | 2026-04-28 | 15 | atteignable uniquement depuis les tests |
| `src.analytics.edge_scorer` | `src/analytics/edge_scorer.py` | 148 | 2026-06-08 | 2 | atteignable uniquement depuis les tests |
| `src.backtest.market_generator` | `src/backtest/market_generator.py` | 148 | 2026-06-08 | 9 | atteignable uniquement depuis les tests |
| `tracker_system.risk.alert_system` | `tracker_system/risk/alert_system.py` | 148 | 2026-05-14 | 2 | atteignable uniquement depuis les tests |
| `crypto.decision_signer` | `crypto/decision_signer.py` | 147 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `metrics.stability_score` | `metrics/stability_score.py` | 147 | 2026-05-14 | 3 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.guerison` | `pieuvre/tentacles/guerison.py` | 147 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.execution.paper_trading_engine` | `quant_hedge_ai/agents/execution/paper_trading_engine.py` | 147 | 2026-05-26 | 7 | atteignable uniquement depuis les tests |
| `signal.analysis.analyze_strategy_niches` | `signal/analysis/analyze_strategy_niches.py` | 147 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.memoire` | `pieuvre/tentacles/memoire.py` | 145 | 2026-05-26 | 2 | atteignable uniquement depuis les tests |
| `observation.accounts.order_reader` | `observation/accounts/order_reader.py` | 144 | 2026-08-01 | 1 | atteignable uniquement depuis les tests |
| `observation.accounts.transfer_collector` | `observation/accounts/transfer_collector.py` | 142 | 2026-08-01 | 1 | atteignable uniquement depuis les tests |
| `runtime.execution_context` | `runtime/execution_context.py` | 142 | 2026-05-29 | 5 | atteignable uniquement depuis les tests |
| `system.alpha_kill_switch` | `system/alpha_kill_switch.py` | 138 | 2026-06-03 | 2 | atteignable uniquement depuis les tests |
| `audit.decision_trace` | `audit/decision_trace.py` | 135 | 2026-05-05 | 3 | atteignable uniquement depuis les tests |
| `infra.lazy_loader` | `infra/lazy_loader.py` | 133 | 2026-05-29 | 3 | atteignable uniquement depuis les tests |
| `src.execution.enl` | `src/execution/enl.py` | 129 | 2026-06-08 | 4 | atteignable uniquement depuis les tests |
| `observation.accounts.position_collector` | `observation/accounts/position_collector.py` | 124 | 2026-08-01 | 1 | atteignable uniquement depuis les tests |
| `visualization.api.burnin_api` | `visualization/api/burnin_api.py` | 121 | 2026-07-04 | 2 | atteignable uniquement depuis les tests |
| `observation.accounts._semantics` | `observation/accounts/_semantics.py` | 116 | 2026-08-01 | 1 | atteignable uniquement depuis les tests |
| `src.agent.rsi_extreme_strategy` | `src/agent/rsi_extreme_strategy.py` | 113 | 2026-06-08 | 3 | atteignable uniquement depuis les tests |
| `src.analytics.alpha_pipeline` | `src/analytics/alpha_pipeline.py` | 113 | 2026-06-08 | 3 | atteignable uniquement depuis les tests |
| `tracker_system.engine.exit_rules` | `tracker_system/engine/exit_rules.py` | 112 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `observation.accounts._common` | `observation/accounts/_common.py` | 111 | 2026-08-01 | 2 | atteignable uniquement depuis les tests |
| `src.paper.paper_metrics` | `src/paper/paper_metrics.py` | 109 | 2026-06-04 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_factory.multi_timeframe_backtester` | `quant_hedge_ai/strategy_factory/multi_timeframe_backtester.py` | 108 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `tracker_system.engine.composite_exit_engine` | `tracker_system/engine/composite_exit_engine.py` | 107 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_factory.bot_doctor_validator` | `quant_hedge_ai/strategy_factory/bot_doctor_validator.py` | 102 | 2026-04-27 | 2 | atteignable uniquement depuis les tests |
| `meta_learning.learner` | `meta_learning/learner.py` | 101 | 2026-05-05 | 6 | atteignable uniquement depuis les tests |
| `pieuvre.tentacles.base` | `pieuvre/tentacles/base.py` | 101 | 2026-05-26 | 9 | atteignable uniquement depuis les tests |
| `visualization.api.timeline_api` | `visualization/api/timeline_api.py` | 101 | 2026-07-06 | 1 | atteignable uniquement depuis les tests |
| `src.engine.virtual_exchange` | `src/engine/virtual_exchange.py` | 100 | 2026-06-08 | 10 | atteignable uniquement depuis les tests |
| `tools.scan_load_probe` | `tools/scan_load_probe.py` | 100 | 2026-07-16 | 1 | atteignable uniquement depuis les tests |
| `src.backtest.engine` | `src/backtest/engine.py` | 99 | 2026-06-08 | 8 | atteignable uniquement depuis les tests |
| `src.analytics.bootstrap_stability` | `src/analytics/bootstrap_stability.py` | 94 | 2026-06-08 | 5 | atteignable uniquement depuis les tests |
| `visualization.api.regret_api` | `visualization/api/regret_api.py` | 92 | 2026-07-06 | 2 | atteignable uniquement depuis les tests |
| `meta_learning.decision_engine` | `meta_learning/decision_engine.py` | 89 | 2026-05-05 | 5 | atteignable uniquement depuis les tests |
| `pieuvre.incidents.store` | `pieuvre/incidents/store.py` | 89 | 2026-05-26 | 5 | atteignable uniquement depuis les tests |
| `src.paper.paper_report` | `src/paper/paper_report.py` | 89 | 2026-06-04 | 1 | atteignable uniquement depuis les tests |
| `src.analytics.regime_detector` | `src/analytics/regime_detector.py` | 86 | 2026-06-08 | 7 | atteignable uniquement depuis les tests |
| `visualization.api.scientific_api` | `visualization/api/scientific_api.py` | 86 | 2026-07-06 | 1 | atteignable uniquement depuis les tests |
| `src.paper.paper_position_manager` | `src/paper/paper_position_manager.py` | 85 | 2026-06-04 | 1 | atteignable uniquement depuis les tests |
| `src.domain.trade_event` | `src/domain/trade_event.py` | 83 | 2026-06-08 | 19 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.engine.decision_engine` | `quant_hedge_ai/engine/decision_engine.py` | 80 | 2026-04-27 | 2 | atteignable uniquement depuis les tests |
| `src.backtest.mexc_feed` | `src/backtest/mexc_feed.py` | 79 | 2026-06-08 | 3 | atteignable uniquement depuis les tests |
| `src.analytics.is_oos_splitter` | `src/analytics/is_oos_splitter.py` | 77 | 2026-06-08 | 6 | atteignable uniquement depuis les tests |
| `supervision.bot_doctor` | `supervision/bot_doctor.py` | 74 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `visualization.api.health_api` | `visualization/api/health_api.py` | 71 | 2026-07-05 | 2 | atteignable uniquement depuis les tests |
| `src.analytics.performance_breakdown` | `src/analytics/performance_breakdown.py` | 70 | 2026-06-08 | 2 | atteignable uniquement depuis les tests |
| `observation.accounts` | `observation/accounts/__init__.py` | 69 | 2026-08-01 | 4 | atteignable uniquement depuis les tests |
| `src.journal.trade_logger` | `src/journal/trade_logger.py` | 69 | 2026-06-08 | 3 | atteignable uniquement depuis les tests |
| `src.analytics.replay_engine` | `src/analytics/replay_engine.py` | 66 | 2026-06-08 | 1 | atteignable uniquement depuis les tests |
| `visualization.api.datasets_api` | `visualization/api/datasets_api.py` | 64 | 2026-07-06 | 1 | atteignable uniquement depuis les tests |
| `meta_learning.memory` | `meta_learning/memory.py` | 62 | 2026-05-05 | 5 | atteignable uniquement depuis les tests |
| `infra.monitoring.supervise_all` | `infra/monitoring/supervise_all.py` | 60 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `src.agent.rsi_strategy` | `src/agent/rsi_strategy.py` | 58 | 2026-06-08 | 6 | atteignable uniquement depuis les tests |
| `core.quant.logging_alerts` | `core/quant/logging_alerts.py` | 55 | 2026-04-27 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.strategy_db` | `quant_hedge_ai/strategy_lab/strategy_db.py` | 55 | 2026-04-27 | 6 | atteignable uniquement depuis les tests |
| `meta_learning.similarity` | `meta_learning/similarity.py` | 54 | 2026-05-05 | 3 | atteignable uniquement depuis les tests |
| `visualization.api` | `visualization/api/__init__.py` | 54 | 2026-07-06 | 4 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.whales` | `quant_hedge_ai/agents/whales/__init__.py` | 53 | 2026-04-27 | 2 | atteignable uniquement depuis les tests |
| `dashboard.alert_dashboard` | `dashboard/alert_dashboard.py` | 51 | 2026-06-01 | 1 | atteignable uniquement depuis les tests |
| `src.agent.sma_strategy` | `src/agent/sma_strategy.py` | 49 | 2026-06-08 | 8 | atteignable uniquement depuis les tests |
| `src.risk.regime_gate` | `src/risk/regime_gate.py` | 48 | 2026-06-08 | 2 | atteignable uniquement depuis les tests |
| `src.agent.momentum_strategy` | `src/agent/momentum_strategy.py` | 47 | 2026-06-08 | 2 | atteignable uniquement depuis les tests |
| `tracker_system` | `tracker_system/__init__.py` | 47 | 2026-05-25 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.strategy.genetic_optimizer` | `quant_hedge_ai/agents/strategy/genetic_optimizer.py` | 46 | 2026-05-05 | 4 | atteignable uniquement depuis les tests |
| `visualization.api.system_snapshot_source` | `visualization/api/system_snapshot_source.py` | 46 | 2026-07-05 | 4 | atteignable uniquement depuis les tests |
| `visualization.api.pipeline_api` | `visualization/api/pipeline_api.py` | 43 | 2026-07-05 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.signal_builder` | `quant_hedge_ai/strategy_lab/signal_builder.py` | 42 | 2026-04-27 | 5 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.evolution_engine` | `quant_hedge_ai/strategy_lab/evolution_engine.py` | 39 | 2026-04-27 | 1 | atteignable uniquement depuis les tests |
| `src.analytics.significance_gate` | `src/analytics/significance_gate.py` | 39 | 2026-06-08 | 3 | atteignable uniquement depuis les tests |
| `src.backtest.metrics` | `src/backtest/metrics.py` | 38 | 2026-06-08 | 2 | atteignable uniquement depuis les tests |
| `src.agent.breakout_strategy` | `src/agent/breakout_strategy.py` | 36 | 2026-06-08 | 3 | atteignable uniquement depuis les tests |
| `src.paper.paper_gate` | `src/paper/paper_gate.py` | 35 | 2026-06-04 | 1 | atteignable uniquement depuis les tests |
| `src.portfolio.portfolio_state` | `src/portfolio/portfolio_state.py` | 35 | 2026-06-08 | 10 | atteignable uniquement depuis les tests |
| `visualization.api.portfolio_api` | `visualization/api/portfolio_api.py` | 35 | 2026-07-05 | 2 | atteignable uniquement depuis les tests |
| `src.events.event_bus` | `src/events/event_bus.py` | 34 | 2026-06-12 | 4 | atteignable uniquement depuis les tests |
| `supervision.notifications.slack_notifier` | `supervision/notifications/slack_notifier.py` | 34 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `src.runtime.simulator` | `src/runtime/simulator.py` | 29 | 2026-06-08 | 1 | atteignable uniquement depuis les tests |
| `src.backtest.walk_forward` | `src/backtest/walk_forward.py` | 26 | 2026-06-08 | 3 | atteignable uniquement depuis les tests |
| `visualization.api.decision_api` | `visualization/api/decision_api.py` | 26 | 2026-07-06 | 1 | atteignable uniquement depuis les tests |
| `cold_start` | `cold_start/__init__.py` | 24 | 2026-05-27 | 1 | atteignable uniquement depuis les tests |
| `paper_trading` | `paper_trading/__init__.py` | 23 | 2026-06-13 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.parallel_engine` | `quant_hedge_ai/strategy_lab/parallel_engine.py` | 23 | 2026-04-27 | 1 | atteignable uniquement depuis les tests |
| `supervision.notifications.multi_notifier` | `supervision/notifications/multi_notifier.py` | 23 | 2026-05-26 | 3 | atteignable uniquement depuis les tests |
| `tracker_system.config` | `tracker_system/config/__init__.py` | 23 | 2026-05-05 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.parameter_space` | `quant_hedge_ai/strategy_lab/parameter_space.py` | 22 | 2026-04-27 | 5 | atteignable uniquement depuis les tests |
| `supervision.notifications.email_notifier` | `supervision/notifications/email_notifier.py` | 22 | 2026-04-27 | 1 | atteignable uniquement depuis les tests |
| `pieuvre` | `pieuvre/__init__.py` | 20 | 2026-04-28 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.strategy.strategy_generator` | `quant_hedge_ai/agents/strategy/strategy_generator.py` | 20 | 2026-04-27 | 4 | atteignable uniquement depuis les tests |
| `src.agent.codex_agent` | `src/agent/codex_agent.py` | 19 | 2026-06-08 | 11 | atteignable uniquement depuis les tests |
| `src.runtime.run_context` | `src/runtime/run_context.py` | 19 | 2026-06-08 | 8 | atteignable uniquement depuis les tests |
| `supervision.custom_module` | `supervision/custom_module.py` | 19 | 2026-04-27 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.ranker` | `quant_hedge_ai/strategy_lab/ranker.py` | 18 | 2026-04-27 | 3 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.batch_runner` | `quant_hedge_ai/strategy_lab/batch_runner.py` | 17 | 2026-04-27 | 1 | atteignable uniquement depuis les tests |
| `src.risk.live_gate` | `src/risk/live_gate.py` | 16 | 2026-06-08 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.backtest_launcher` | `quant_hedge_ai/strategy_lab/backtest_launcher.py` | 14 | 2026-04-27 | 5 | atteignable uniquement depuis les tests |
| `src.backtest.data_feed` | `src/backtest/data_feed.py` | 14 | 2026-06-08 | 11 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_factory.backtester` | `quant_hedge_ai/strategy_factory/backtester.py` | 13 | 2026-04-27 | 2 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.templates` | `quant_hedge_ai/strategy_lab/templates.py` | 13 | 2026-04-27 | 5 | atteignable uniquement depuis les tests |
| `src.domain.position` | `src/domain/position.py` | 13 | 2026-06-08 | 6 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_lab.generator` | `quant_hedge_ai/strategy_lab/generator.py` | 11 | 2026-04-27 | 5 | atteignable uniquement depuis les tests |
| `src.domain.order` | `src/domain/order.py` | 11 | 2026-06-08 | 9 | atteignable uniquement depuis les tests |
| `src.engine.execution_router` | `src/engine/execution_router.py` | 11 | 2026-06-08 | 10 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.risk.drawdown_guard` | `quant_hedge_ai/agents/risk/drawdown_guard.py` | 9 | 2026-04-27 | 6 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.risk.risk_monitor` | `quant_hedge_ai/agents/risk/risk_monitor.py` | 9 | 2026-04-27 | 3 | atteignable uniquement depuis les tests |
| `src.risk.kill_switch` | `src/risk/kill_switch.py` | 9 | 2026-06-08 | 12 | atteignable uniquement depuis les tests |
| `src.domain.signal` | `src/domain/signal.py` | 8 | 2026-06-08 | 12 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.ai_evolution` | `quant_hedge_ai/ai_evolution/__init__.py` | 7 | 2026-04-27 | 2 | atteignable uniquement depuis les tests |
| `src.agent.strategy_interface` | `src/agent/strategy_interface.py` | 6 | 2026-06-08 | 10 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.strategy_factory` | `quant_hedge_ai/strategy_factory/__init__.py` | 5 | 2026-04-27 | 2 | atteignable uniquement depuis les tests |
| `capital_deployment` | `capital_deployment/__init__.py` | 1 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |
| `core` | `core/__init__.py` | 1 | 2026-05-29 | 2 | atteignable uniquement depuis les tests |
| `core.quant` | `core/quant/__init__.py` | 1 | 2026-04-27 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.execution` | `quant_hedge_ai/agents/execution/__init__.py` | 1 | 2026-04-27 | 1 | atteignable uniquement depuis les tests |
| `quant_hedge_ai.agents.market` | `quant_hedge_ai/agents/market/__init__.py` | 1 | 2026-04-27 | 1 | atteignable uniquement depuis les tests |
| `scripts` | `scripts/__init__.py` | 1 | 2026-05-29 | 1 | atteignable uniquement depuis les tests |

## ORPHAN — 248 modules

| Module | Fichier | LOC | Dernier commit | Importé par | Justification |
|---|---|---:|---|---:|---|
| `core.invariants` | `core/invariants.py` | 743 | 2026-06-02 | 0 | aucun importeur, aucun __main__ |
| `signal.strategies.run_strategy_factory` | `signal/strategies/run_strategy_factory.py` | 659 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `signal.evolution.evolution_core` | `signal/evolution/evolution_core.py` | 624 | 2026-05-29 | 2 | importé par 2 module(s), tous hors runtime |
| `core.execution_trace` | `core/execution_trace.py` | 461 | 2026-06-02 | 1 | importé par 1 module(s), tous hors runtime |
| `core.formal_proof` | `core/formal_proof.py` | 461 | 2026-06-02 | 0 | aucun importeur, aucun __main__ |
| `sdos_terminal.api.app` | `sdos_terminal/api/app.py` | 432 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `infra.api.api_server` | `infra/api/api_server.py` | 418 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.liquidity_map.flow_analyzer` | `quant_hedge_ai/liquidity_map/flow_analyzer.py` | 407 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.execution.trade_replay` | `quant_hedge_ai/agents/execution/trade_replay.py` | 338 | 2026-05-26 | 2 | importé par 2 module(s), tous hors runtime |
| `audit.decision_ledger` | `audit/decision_ledger.py` | 332 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `risk.global_risk_gate` | `risk/global_risk_gate.py` | 328 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `visualization.renderers.snapshot` | `visualization/renderers/snapshot.py` | 326 | 2026-07-06 | 2 | importé par 2 module(s), tous hors runtime |
| `errors.incident_manager` | `errors/incident_manager.py` | 324 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `src.telegram.exchange_sync` | `src/telegram/exchange_sync.py` | 316 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `health.recovery_manager` | `health/recovery_manager.py` | 315 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `supervision.telegram_kill_switch` | `supervision/telegram_kill_switch.py` | 315 | 2026-05-26 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.quant.stress_test` | `quant_hedge_ai/agents/quant/stress_test.py` | 313 | 2026-05-05 | 2 | importé par 2 module(s), tous hors runtime |
| `infra.stream_bus` | `infra/stream_bus.py` | 311 | 2026-06-13 | 1 | importé par 1 module(s), tous hors runtime |
| `governance.decision_router` | `governance/decision_router.py` | 307 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `governance.trading_authority` | `governance/trading_authority.py` | 303 | 2026-06-02 | 2 | importé par 2 module(s), tous hors runtime |
| `health.health_registry` | `health/health_registry.py` | 286 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `scripts.seed_decision_packets` | `scripts/seed_decision_packets.py` | 283 | 2026-05-11 | 0 | aucun importeur, aucun __main__ |
| `metrics.robustness` | `metrics/robustness.py` | 274 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.market_radar.radar_core` | `quant_hedge_ai/market_radar/radar_core.py` | 273 | 2026-05-26 | 0 | aucun importeur, aucun __main__ |
| `monitoring.profiler` | `monitoring/profiler.py` | 263 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `system.kernel` | `system/kernel.py` | 261 | 2026-05-26 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.sessions.session_analyzer` | `tracker_system/sessions/session_analyzer.py` | 259 | 2026-05-14 | 4 | importé par 4 module(s), tous hors runtime |
| `governance.ai_constraints` | `governance/ai_constraints.py` | 258 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `market_data.connectors.mexc` | `market_data/connectors/mexc.py` | 256 | 2026-05-14 | 1 | importé par 1 module(s), tous hors runtime |
| `market_data.connectors.hyperliquid` | `market_data/connectors/hyperliquid.py` | 245 | 2026-05-14 | 1 | importé par 1 module(s), tous hors runtime |
| `supervision.kill_switch` | `supervision/kill_switch.py` | 240 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `scripts.smoke_test_ci` | `scripts/smoke_test_ci.py` | 238 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `governance.risk_authorizer` | `governance/risk_authorizer.py` | 236 | 2026-05-08 | 1 | importé par 1 module(s), tous hors runtime |
| `infra.automate_pipeline` | `infra/automate_pipeline.py` | 231 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.execution.execution_optimizer` | `quant_hedge_ai/agents/execution/execution_optimizer.py` | 228 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.market_radar.whale_tracker` | `quant_hedge_ai/market_radar/whale_tracker.py` | 222 | 2026-05-26 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.p0_integration` | `tracker_system/p0_integration.py` | 221 | 2026-05-05 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.market_radar.anomaly_detector` | `quant_hedge_ai/market_radar/anomaly_detector.py` | 220 | 2026-05-26 | 0 | aucun importeur, aucun __main__ |
| `observability.live_topology` | `observability/live_topology.py` | 218 | 2026-05-08 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.intelligence.regime_transition_predictor` | `quant_hedge_ai/agents/intelligence/regime_transition_predictor.py` | 218 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `system.runtime_controller` | `system/runtime_controller.py` | 216 | 2026-05-26 | 3 | importé par 3 module(s), tous hors runtime |
| `quant_hedge_ai.agents.risk.risk_dashboard_api` | `quant_hedge_ai/agents/risk/risk_dashboard_api.py` | 215 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `governance.execution_approval` | `governance/execution_approval.py` | 207 | 2026-05-08 | 1 | importé par 1 module(s), tous hors runtime |
| `visualization.renderers.radar` | `visualization/renderers/radar.py` | 206 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.onchain.blockchain_ingester` | `quant_hedge_ai/agents/onchain/blockchain_ingester.py` | 202 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.execution.latency_monitor` | `quant_hedge_ai/agents/execution/latency_monitor.py` | 201 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.ai_evolution.model_degradation_monitor` | `quant_hedge_ai/ai_evolution/model_degradation_monitor.py` | 199 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.features.feature_store` | `quant_hedge_ai/features/feature_store.py` | 199 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `pieuvre.dashboard.tableau_bord` | `pieuvre/dashboard/tableau_bord.py` | 197 | 2026-04-28 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.market.microstructure.orderbook_analyzer` | `quant_hedge_ai/agents/market/microstructure/orderbook_analyzer.py` | 196 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `scripts.bear_trend_audit` | `scripts/bear_trend_audit.py` | 193 | 2026-06-24 | 0 | aucun importeur, aucun __main__ |
| `visualization.renderers.pipeline` | `visualization/renderers/pipeline.py` | 191 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.market_radar.token_scanner` | `quant_hedge_ai/market_radar/token_scanner.py` | 190 | 2026-05-26 | 0 | aucun importeur, aucun __main__ |
| `system.dependency_manager` | `system/dependency_manager.py` | 189 | 2026-05-08 | 3 | importé par 3 module(s), tous hors runtime |
| `visualization.renderers.equity` | `visualization/renderers/equity.py` | 189 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.features.feature_materializer` | `quant_hedge_ai/features/feature_materializer.py` | 188 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `tracker_system.sessions.session_report_builder` | `tracker_system/sessions/session_report_builder.py` | 188 | 2026-05-14 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.execution.optimal_timing_engine` | `quant_hedge_ai/agents/execution/optimal_timing_engine.py` | 187 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `governance.decision_trace` | `governance/decision_trace.py` | 183 | 2026-06-02 | 1 | importé par 1 module(s), tous hors runtime |
| `signal.analysis.tune` | `signal/analysis/tune.py` | 183 | 2026-06-02 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.sessions.session_validator` | `tracker_system/sessions/session_validator.py` | 183 | 2026-05-14 | 2 | importé par 2 module(s), tous hors runtime |
| `quant_hedge_ai.data.canonical_market_model` | `quant_hedge_ai/data/canonical_market_model.py` | 179 | UNTRACKED | 1 | importé par 1 module(s), tous hors runtime |
| `governance.authority_state` | `governance/authority_state.py` | 178 | 2026-06-02 | 3 | importé par 3 module(s), tous hors runtime |
| `market_data.stream` | `market_data/stream.py` | 177 | 2026-06-13 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.execution.slippage_predictor` | `quant_hedge_ai/agents/execution/slippage_predictor.py` | 177 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `system.startup_sequence` | `system/startup_sequence.py` | 177 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.onchain.whale_behavior_classifier` | `quant_hedge_ai/agents/onchain/whale_behavior_classifier.py` | 172 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.data.data_unifier` | `quant_hedge_ai/data/data_unifier.py` | 169 | UNTRACKED | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.onchain.exchange_flow_tracker` | `quant_hedge_ai/agents/onchain/exchange_flow_tracker.py` | 165 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `observability.telemetry` | `observability/telemetry.py` | 163 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.market_radar.social_scanner` | `quant_hedge_ai/market_radar/social_scanner.py` | 163 | 2026-05-26 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.runtime_config` | `quant_hedge_ai/runtime_config.py` | 163 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `tracker_system.sessions.session_manager` | `tracker_system/sessions/session_manager.py` | 160 | 2026-05-14 | 5 | importé par 5 module(s), tous hors runtime |
| `quant_hedge_ai.agents.market.microstructure.microstructure_engine` | `quant_hedge_ai/agents/market/microstructure/microstructure_engine.py` | 154 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `infra.notifications.notifications` | `infra/notifications/notifications.py` | 149 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `tracker_system.sessions.session_scoring` | `tracker_system/sessions/session_scoring.py` | 147 | 2026-05-14 | 3 | importé par 3 module(s), tous hors runtime |
| `visualization.renderers.timeline` | `visualization/renderers/timeline.py` | 144 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.strategy_factory.factory_core` | `quant_hedge_ai/strategy_factory/factory_core.py` | 143 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `governance.status_dashboard` | `governance/status_dashboard.py` | 140 | 2026-06-02 | 1 | importé par 1 module(s), tous hors runtime |
| `scripts.quickstart` | `scripts/quickstart.py` | 131 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `scripts.toxicity_report` | `scripts/toxicity_report.py` | 130 | 2026-06-24 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.sessions.session_labels` | `tracker_system/sessions/session_labels.py` | 130 | 2026-05-14 | 2 | importé par 2 module(s), tous hors runtime |
| `governance.confidence_gate` | `governance/confidence_gate.py` | 127 | 2026-05-08 | 1 | importé par 1 module(s), tous hors runtime |
| `infra.monitoring.surveillance_continue` | `infra/monitoring/surveillance_continue.py` | 127 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.data.schema_normalizer` | `quant_hedge_ai/data/schema_normalizer.py` | 127 | UNTRACKED | 1 | importé par 1 module(s), tous hors runtime |
| `tracker_system.sessions.session_ranking` | `tracker_system/sessions/session_ranking.py` | 125 | 2026-05-14 | 2 | importé par 2 module(s), tous hors runtime |
| `quant_hedge_ai.runtime.health_endpoint` | `quant_hedge_ai/runtime/health_endpoint.py` | 124 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.sessions.session_compare` | `tracker_system/sessions/session_compare.py` | 120 | 2026-05-14 | 1 | importé par 1 module(s), tous hors runtime |
| `market_data.connectors.base` | `market_data/connectors/base.py` | 119 | 2026-05-26 | 4 | importé par 4 module(s), tous hors runtime |
| `scripts.crypto_market_scanner` | `scripts/crypto_market_scanner.py` | 113 | 2026-06-13 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.portfolio` | `quant_hedge_ai/agents/portfolio/__init__.py` | 109 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.features.feature_validator` | `quant_hedge_ai/features/feature_validator.py` | 107 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `dip.core.observer` | `dip/core/observer.py` | 105 | 2026-06-30 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.market.microstructure.spread_predictor` | `quant_hedge_ai/agents/market/microstructure/spread_predictor.py` | 101 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `visualization.renderers.base` | `visualization/renderers/base.py` | 92 | 2026-07-06 | 7 | importé par 7 module(s), tous hors runtime |
| `signal.strategies.run_strategy_factory_batch` | `signal/strategies/run_strategy_factory_batch.py` | 90 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.features.feature_registry` | `quant_hedge_ai/features/feature_registry.py` | 89 | 2026-05-05 | 1 | importé par 1 module(s), tous hors runtime |
| `infra.panels.panel_ci_report` | `infra/panels/panel_ci_report.py` | 88 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `dip.bootstrap` | `dip/bootstrap.py` | 84 | 2026-06-30 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.strategy_lab.feature_cache` | `quant_hedge_ai/strategy_lab/feature_cache.py` | 81 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `core.orchestration.orchestrate_all` | `core/orchestration/orchestrate_all.py` | 76 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.visualization.ui_utils` | `infra/visualization/ui_utils.py` | 75 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.visualization.visualization` | `infra/visualization/visualization.py` | 74 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `docs.conf` | `docs/conf.py` | 73 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `visualization.ves.router` | `visualization/ves/router.py` | 72 | 2026-07-06 | 1 | importé par 1 module(s), tous hors runtime |
| `scripts.crypto_terminal` | `scripts/crypto_terminal.py` | 70 | 2026-06-13 | 0 | aucun importeur, aucun __main__ |
| `core.orchestration.orchestrate_and_test_panels` | `core/orchestration/orchestrate_and_test_panels.py` | 68 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.databases.strategy_scoreboard` | `quant_hedge_ai/databases/strategy_scoreboard.py` | 59 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `core.orchestration.send_orchestration_notification` | `core/orchestration/send_orchestration_notification.py` | 54 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.strategy_lab.example_pipeline` | `quant_hedge_ai/strategy_lab/example_pipeline.py` | 54 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `signal.analysis.clustering` | `signal/analysis/clustering.py` | 53 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `market_data.metrics` | `market_data/metrics/__init__.py` | 51 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `scripts.population_csv_validator` | `scripts/population_csv_validator.py` | 51 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `tracker_system.sessions` | `tracker_system/sessions/__init__.py` | 50 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `scripts.generate_panel_screenshots` | `scripts/generate_panel_screenshots.py` | 49 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `signal.analysis.automl_tuning` | `signal/analysis/automl_tuning.py` | 48 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `scripts.pareto_front` | `scripts/pareto_front.py` | 46 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `visualization.ves.registry` | `visualization/ves/registry.py` | 46 | 2026-07-06 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.strategy_factory.performance_analyzer` | `quant_hedge_ai/strategy_factory/performance_analyzer.py` | 43 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `signal.analysis.sensitivity_analysis` | `signal/analysis/sensitivity_analysis.py` | 43 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `infra.visualization.timeline_animation` | `infra/visualization/timeline_animation.py` | 42 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `exchange_constraints` | `exchange_constraints/__init__.py` | 40 | 2026-06-13 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.sessions.schemas.metrics_schema` | `tracker_system/sessions/schemas/metrics_schema.py` | 38 | 2026-05-14 | 1 | importé par 1 module(s), tous hors runtime |
| `infra.check_imports` | `infra/check_imports.py` | 36 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.config_utils` | `infra/config_utils.py` | 36 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `infra.api.api_rest` | `infra/api/api_rest.py` | 33 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.notifications.notify_selenium_report_discord` | `infra/notifications/notify_selenium_report_discord.py` | 33 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.notifications.notify_selenium_report_slack` | `infra/notifications/notify_selenium_report_slack.py` | 33 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `governance` | `governance/__init__.py` | 32 | 2026-06-02 | 0 | aucun importeur, aucun __main__ |
| `scripts.export_latex_md` | `scripts/export_latex_md.py` | 31 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `market_data` | `market_data/__init__.py` | 30 | 2026-06-13 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.research.paper_analyzer` | `quant_hedge_ai/agents/research/paper_analyzer.py` | 30 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.strategy_factory.strategy_generator` | `quant_hedge_ai/strategy_factory/strategy_generator.py` | 29 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.strategy.rl_trader` | `quant_hedge_ai/agents/strategy/rl_trader.py` | 28 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `tracker_system.sessions.schemas.trade_schema` | `tracker_system/sessions/schemas/trade_schema.py` | 27 | 2026-05-14 | 1 | importé par 1 module(s), tous hors runtime |
| `scripts.copy_docs_for_sphinx` | `scripts/copy_docs_for_sphinx.py` | 26 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.sessions.schemas.session_schema` | `tracker_system/sessions/schemas/session_schema.py` | 26 | 2026-05-14 | 2 | importé par 2 module(s), tous hors runtime |
| `core.orchestration.orchestrate_internal_panels` | `core/orchestration/orchestrate_internal_panels.py` | 25 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.quant.monte_carlo` | `quant_hedge_ai/agents/quant/monte_carlo.py` | 25 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `dip` | `dip/__init__.py` | 24 | 2026-06-30 | 0 | aucun importeur, aucun __main__ |
| `execution_simulator` | `execution_simulator/__init__.py` | 24 | 2026-06-13 | 0 | aucun importeur, aucun __main__ |
| `visualization.ves.contracts` | `visualization/ves/contracts.py` | 24 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.research.strategy_researcher` | `quant_hedge_ai/agents/research/strategy_researcher.py` | 22 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `scripts.minimal_test` | `scripts/minimal_test.py` | 22 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `pieuvre.tentacles` | `pieuvre/tentacles/__init__.py` | 21 | 2026-04-28 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.monitoring.performance_monitor` | `quant_hedge_ai/agents/monitoring/performance_monitor.py` | 21 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `supervision` | `supervision/__init__.py` | 21 | 2026-06-12 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.research.model_builder` | `quant_hedge_ai/agents/research/model_builder.py` | 20 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `quant_hedge_ai.agents.market.volatility_agent` | `quant_hedge_ai/agents/market/volatility_agent.py` | 19 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `core.runtime_state_machine` | `core/runtime_state_machine.py` | 18 | 2026-06-02 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.quant.portfolio_optimizer` | `quant_hedge_ai/agents/quant/portfolio_optimizer.py` | 18 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.runtime` | `quant_hedge_ai/runtime/__init__.py` | 17 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.risk` | `tracker_system/risk/__init__.py` | 17 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.research.feature_engineer` | `quant_hedge_ai/agents/research/feature_engineer.py` | 16 | 2026-05-26 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.market_radar` | `quant_hedge_ai/market_radar/__init__.py` | 15 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `tracker_system.core` | `tracker_system/core/__init__.py` | 15 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `audit` | `audit/__init__.py` | 12 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `meta_learning` | `meta_learning/__init__.py` | 12 | 2026-05-25 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.monitoring.system_monitor` | `quant_hedge_ai/agents/monitoring/system_monitor.py` | 12 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `market_data.connectors` | `market_data/connectors/__init__.py` | 11 | 2026-06-13 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.execution.liquidity_agent` | `quant_hedge_ai/agents/execution/liquidity_agent.py` | 10 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `quant_hedge_ai.agents.market.orderflow_agent` | `quant_hedge_ai/agents/market/orderflow_agent.py` | 10 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `S2` | `S2/__init__.py` | 9 | 2026-05-25 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.execution.arbitrage_agent` | `quant_hedge_ai/agents/execution/arbitrage_agent.py` | 9 | 2026-04-27 | 2 | importé par 2 module(s), tous hors runtime |
| `quant_hedge_ai.agents.market.microstructure` | `quant_hedge_ai/agents/market/microstructure/__init__.py` | 9 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.market.regime_detector` | `quant_hedge_ai/agents/market/regime_detector.py` | 9 | 2026-05-05 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.agents.onchain` | `quant_hedge_ai/agents/onchain/__init__.py` | 9 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.research` | `quant_hedge_ai/agents/research/__init__.py` | 8 | 2026-04-28 | 0 | aucun importeur, aucun __main__ |
| `dip.__main__` | `dip/__main__.py` | 7 | 2026-06-30 | 0 | aucun importeur, aucun __main__ |
| `event_bus` | `event_bus/__init__.py` | 7 | 2026-04-28 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.intelligence` | `quant_hedge_ai/agents/intelligence/__init__.py` | 6 | 2026-04-28 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.features` | `quant_hedge_ai/features/__init__.py` | 6 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `visualization.ves` | `visualization/ves/__init__.py` | 6 | 2026-07-06 | 2 | importé par 2 module(s), tous hors runtime |
| `quant_hedge_ai.agents.monitoring` | `quant_hedge_ai/agents/monitoring/__init__.py` | 5 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.data` | `quant_hedge_ai/data/__init__.py` | 5 | UNTRACKED | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.liquidity_map` | `quant_hedge_ai/liquidity_map/__init__.py` | 5 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `system` | `system/__init__.py` | 5 | 2026-05-26 | 0 | aucun importeur, aucun __main__ |
| `terminal_core.quant.logging_alerts` | `terminal_core/quant/logging_alerts.py` | 5 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `tracker_system.engine.rules` | `tracker_system/engine/rules/__init__.py` | 5 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `pieuvre.incidents` | `pieuvre/incidents/__init__.py` | 4 | 2026-04-28 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.backtesting` | `tracker_system/backtesting/__init__.py` | 4 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.engine` | `tracker_system/engine/__init__.py` | 4 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.storage` | `tracker_system/storage/__init__.py` | 4 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `config` | `config/__init__.py` | 3 | 2026-06-12 | 0 | aucun importeur, aucun __main__ |
| `pieuvre.dashboard` | `pieuvre/dashboard/__init__.py` | 3 | 2026-04-28 | 1 | importé par 1 module(s), tous hors runtime |
| `sdos_terminal` | `sdos_terminal/__init__.py` | 3 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `src.telegram` | `src/telegram/__init__.py` | 3 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.analytics` | `tracker_system/analytics/__init__.py` | 3 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.dashboard` | `tracker_system/dashboard/__init__.py` | 3 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.scheduler` | `tracker_system/scheduler/__init__.py` | 3 | 2026-05-05 | 0 | aucun importeur, aucun __main__ |
| `visualization` | `visualization/__init__.py` | 3 | 2026-07-06 | 1 | importé par 1 module(s), tous hors runtime |
| `quant_hedge_ai.strategy_lab` | `quant_hedge_ai/strategy_lab/__init__.py` | 2 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `ai_autonomous_loop` | `ai_autonomous_loop/__init__.py` | 1 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `analysis` | `analysis/__init__.py` | 1 | 2026-06-28 | 0 | aucun importeur, aucun __main__ |
| `core.orchestration` | `core/orchestration/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `crypto` | `crypto/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `dip.core` | `dip/core/__init__.py` | 1 | 2026-06-30 | 0 | aucun importeur, aucun __main__ |
| `dip.modules` | `dip/modules/__init__.py` | 1 | 2026-06-30 | 0 | aucun importeur, aucun __main__ |
| `errors` | `errors/__init__.py` | 1 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `health` | `health/__init__.py` | 1 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `infra` | `infra/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.api` | `infra/api/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.dashboards` | `infra/dashboards/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.monitoring` | `infra/monitoring/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.notifications` | `infra/notifications/__init__.py` | 1 | 2026-05-29 | 1 | importé par 1 module(s), tous hors runtime |
| `infra.panels` | `infra/panels/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `infra.visualization` | `infra/visualization/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `observability` | `observability/__init__.py` | 1 | 2026-05-08 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents` | `quant_hedge_ai/agents/__init__.py` | 1 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.quant` | `quant_hedge_ai/agents/quant/__init__.py` | 1 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.risk` | `quant_hedge_ai/agents/risk/__init__.py` | 1 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.agents.strategy` | `quant_hedge_ai/agents/strategy/__init__.py` | 1 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `risk` | `risk/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `runtime` | `runtime/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `sdos_terminal.api` | `sdos_terminal/api/__init__.py` | 1 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `signal.analysis` | `signal/analysis/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `signal.evolution` | `signal/evolution/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `signal.strategies` | `signal/strategies/__init__.py` | 1 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `src.telegram.quant_observer` | `src/telegram/quant_observer/__init__.py` | 1 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `supervision.notifications` | `supervision/notifications/__init__.py` | 1 | 2026-04-27 | 1 | importé par 1 module(s), tous hors runtime |
| `terminal_core` | `terminal_core/__init__.py` | 1 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `terminal_core.quant` | `terminal_core/quant/__init__.py` | 1 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `visualization.renderers` | `visualization/renderers/__init__.py` | 1 | 2026-07-06 | 0 | aucun importeur, aucun __main__ |
| `dashboard` | `dashboard/__init__.py` | 0 | 2026-06-01 | 0 | aucun importeur, aucun __main__ |
| `metrics` | `metrics/__init__.py` | 0 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `monitor` | `monitor/__init__.py` | 0 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `monitoring` | `monitoring/__init__.py` | 0 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `observation` | `observation/__init__.py` | 0 | 2026-07-15 | 0 | aucun importeur, aucun __main__ |
| `project_os` | `project_os/__init__.py` | 0 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai` | `quant_hedge_ai/__init__.py` | 0 | 2026-04-27 | 0 | aucun importeur, aucun __main__ |
| `quant_hedge_ai.dashboard` | `quant_hedge_ai/dashboard/__init__.py` | 0 | 2026-05-06 | 2 | importé par 2 module(s), tous hors runtime |
| `reality_checks` | `reality_checks/__init__.py` | 0 | 2026-05-29 | 0 | aucun importeur, aucun __main__ |
| `src` | `src/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.agent` | `src/agent/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.analytics` | `src/analytics/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.backtest` | `src/backtest/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.domain` | `src/domain/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.engine` | `src/engine/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.events` | `src/events/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.execution` | `src/execution/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.journal` | `src/journal/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.paper` | `src/paper/__init__.py` | 0 | 2026-06-04 | 0 | aucun importeur, aucun __main__ |
| `src.portfolio` | `src/portfolio/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.risk` | `src/risk/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.runtime` | `src/runtime/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `src.storage` | `src/storage/__init__.py` | 0 | 2026-06-08 | 0 | aucun importeur, aucun __main__ |
| `tracker_system.sessions.schemas` | `tracker_system/sessions/schemas/__init__.py` | 0 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
| `walk_forward` | `walk_forward/__init__.py` | 0 | 2026-05-14 | 0 | aucun importeur, aucun __main__ |
