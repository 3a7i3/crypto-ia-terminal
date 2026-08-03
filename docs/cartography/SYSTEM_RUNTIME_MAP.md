# SYSTEM_RUNTIME_MAP.md — Cartographie du système vivant
> **Document généré automatiquement.** Ne pas éditer à la main.
> Source : `artifacts/cartography.json` — régénérer via
> `python tools/runtime_cartographer.py && python tools/cartography_report.py`
> Généré le 2026-08-01 — commit `348e83d`

> **Portée de la mesure.** Graphe d'import statique (AST), imports paresseux
> inclus. `ACTIVE` signifie **atteignable par import** depuis le point d'entrée
> runtime, **pas** « exécuté ». Prouver l'exécution exige une trace runtime
> (`sys.settrace`/coverage sur le VPS) — **NON MESURÉ** en J1-J2.

## 1. Points d'entrée

| Point d'entrée | Source de la déclaration | Existe ? |
|---|---|---|
| `core.advisor_loop` | `scripts/deploy_vps.sh` (mode `core`) | oui |
| `advisor_loop.py` | `scripts/crypto_advisor.service` (systemd) | **NON — fichier absent** |

## 2. Volumétrie mesurée

| Mesure | Valeur | % du total |
|---|---:|---:|
| `modules_total` | 1115 | 100.0% |
| `modules_runtime_reachable` | 170 | 15.2% |
| `modules_tool` | 94 | 8.4% |
| `modules_test_only` | 279 | 25.0% |
| `modules_orphan` | 248 | 22.2% |
| `modules_test` | 324 | 29.1% |

### Bornes de la mesure de joignabilité

La résolution stricte (nom pointé complet uniquement) donne une borne
**inférieure**. La résolution avec repli sur les imports par nom nu — nécessaire
car le dépôt en contient (voir CONTRADICTION-02) — est **sur-inclusive** quand
un basename est ambigu, et donne donc une borne **supérieure**.

| Borne | Modules atteignables |
|---|---:|
| Inférieure (résolution stricte) | 102 |
| Supérieure (repli nom nu) | 170 |

Nombre de basenames ambigus mesurés : **1**.

## 3. Modules atteignables par le runtime

| Module | Fichier | LOC | Dernier commit |
|---|---|---:|---|
| `capital_deployment.capital_throttle` | `capital_deployment/capital_throttle.py` | 135 | 2026-05-29 |
| `capital_deployment.chart_server` | `capital_deployment/chart_server.py` | 437 | 2026-05-28 |
| `capital_deployment.command_center_bot` | `capital_deployment/command_center_bot.py` | 1556 | 2026-07-19 |
| `capital_deployment.emergency_stop_manager` | `capital_deployment/emergency_stop_manager.py` | 271 | 2026-05-29 |
| `capital_deployment.operational_state` | `capital_deployment/operational_state.py` | 150 | 2026-05-31 |
| `capital_deployment.phase_kpi_tracker` | `capital_deployment/phase_kpi_tracker.py` | 228 | 2026-05-29 |
| `config.feature_flags` | `config/feature_flags.py` | 55 | 2026-06-30 |
| `config.parameter_audit` | `config/parameter_audit.py` | 142 | 2026-06-20 |
| `core.advisor_loop` | `core/advisor_loop.py` | 7815 | 2026-07-31 |
| `core.advisor_runtime_adapters` | `core/advisor_runtime_adapters.py` | 160 | 2026-06-15 |
| `core.authority` | `core/authority.py` | 109 | 2026-06-02 |
| `core.decision_packet` | `core/decision_packet.py` | 861 | 2026-06-02 |
| `core.lifecycle` | `core/lifecycle.py` | 467 | 2026-06-02 |
| `core.perp_universe_service` | `core/perp_universe_service.py` | 367 | 2026-06-24 |
| `core.topk_scheduler` | `core/topk_scheduler.py` | 101 | 2026-07-17 |
| `crypto.blackbox_encryption` | `crypto/blackbox_encryption.py` | 115 | 2026-05-29 |
| `crypto.key_derivation` | `crypto/key_derivation.py` | 94 | 2026-05-29 |
| `dip.core.types` | `dip/core/types.py` | 171 | 2026-06-30 |
| `errors.error_bus` | `errors/error_bus.py` | 325 | 2026-05-08 |
| `event_bus.bus` | `event_bus/bus.py` | 274 | 2026-05-26 |
| `event_bus.events` | `event_bus/events.py` | 388 | 2026-04-28 |
| `exchange_constraints.binance_rules` | `exchange_constraints/binance_rules.py` | 122 | 2026-06-13 |
| `exchange_constraints.models` | `exchange_constraints/models.py` | 179 | 2026-05-14 |
| `exchange_constraints.order_validator` | `exchange_constraints/order_validator.py` | 287 | 2026-05-14 |
| `exchange_constraints.precision_rules` | `exchange_constraints/precision_rules.py` | 132 | 2026-05-14 |
| `exchange_constraints.rate_limiter` | `exchange_constraints/rate_limiter.py` | 246 | 2026-05-14 |
| `execution_simulator.config` | `execution_simulator/config.py` | 129 | 2026-06-13 |
| `execution_simulator.fill_simulator` | `execution_simulator/fill_simulator.py` | 127 | 2026-05-14 |
| `execution_simulator.latency` | `execution_simulator/latency.py` | 92 | 2026-05-14 |
| `execution_simulator.models` | `execution_simulator/models.py` | 177 | 2026-05-14 |
| `execution_simulator.simulator` | `execution_simulator/simulator.py` | 145 | 2026-05-14 |
| `execution_simulator.slippage` | `execution_simulator/slippage.py` | 126 | 2026-05-14 |
| `execution_simulator.spread` | `execution_simulator/spread.py` | 101 | 2026-05-14 |
| `governance.auditor` | `governance/auditor.py` | 574 | 2026-06-02 |
| `infra.exchange_factory` | `infra/exchange_factory.py` | 402 | 2026-06-13 |
| `infra.live_exchange_reader` | `infra/live_exchange_reader.py` | 206 | 2026-06-13 |
| `infra.mexc_reader` | `infra/mexc_reader.py` | 226 | 2026-06-02 |
| `infra.wallet_sync` | `infra/wallet_sync.py` | 262 | 2026-07-06 |
| `lm_studio` | `lm_studio/__init__.py` | 13 | 2026-05-05 |
| `lm_studio.ai_router` | `lm_studio/ai_router.py` | 69 | 2026-05-29 |
| `lm_studio.client` | `lm_studio/client.py` | 216 | 2026-05-29 |
| `observability.alerting` | `observability/alerting.py` | 242 | 2026-05-29 |
| `observability.decision_event_bus` | `observability/decision_event_bus.py` | 169 | 2026-06-30 |
| `observability.decision_explainer` | `observability/decision_explainer.py` | 306 | 2026-06-30 |
| `observability.decision_observation` | `observability/decision_observation.py` | 491 | 2026-06-30 |
| `observability.health_score` | `observability/health_score.py` | 207 | 2026-05-29 |
| `observability.heartbeat_system` | `observability/heartbeat_system.py` | 203 | 2026-05-08 |
| `observability.json_logger` | `observability/json_logger.py` | 258 | 2026-07-03 |
| `observability.metrics_bus` | `observability/metrics_bus.py` | 228 | 2026-05-08 |
| `observability.metrics_collector` | `observability/metrics_collector.py` | 281 | 2026-05-29 |
| `observability.real_accounts` | `observability/real_accounts.py` | 270 | 2026-07-20 |
| `observability.regret_scheduler` | `observability/regret_scheduler.py` | 585 | 2026-07-21 |
| `observability.rejection_store` | `observability/rejection_store.py` | 310 | 2026-06-30 |
| `observability.system_snapshot` | `observability/system_snapshot.py` | 375 | 2026-07-31 |
| `observability.system_snapshot_event_bus` | `observability/system_snapshot_event_bus.py` | 76 | 2026-07-05 |
| `observability.system_snapshot_renderers` | `observability/system_snapshot_renderers.py` | 201 | 2026-07-31 |
| `paper_trading.dataset_validator` | `paper_trading/dataset_validator.py` | 591 | 2026-07-28 |
| `paper_trading.mexc_simulator` | `paper_trading/mexc_simulator.py` | 966 | 2026-07-14 |
| `paper_trading.recorder` | `paper_trading/recorder.py` | 519 | 2026-07-03 |
| `quant_hedge_ai.agents.execution.execution_engine` | `quant_hedge_ai/agents/execution/execution_engine.py` | 575 | 2026-07-08 |
| `quant_hedge_ai.agents.execution.live_signal_engine` | `quant_hedge_ai/agents/execution/live_signal_engine.py` | 608 | 2026-06-06 |
| `quant_hedge_ai.agents.execution.multi_timeframe_signal` | `quant_hedge_ai/agents/execution/multi_timeframe_signal.py` | 140 | 2026-05-26 |
| `quant_hedge_ai.agents.execution.order_deduplicator` | `quant_hedge_ai/agents/execution/order_deduplicator.py` | 64 | 2026-05-26 |
| `quant_hedge_ai.agents.execution.position_manager` | `quant_hedge_ai/agents/execution/position_manager.py` | 706 | 2026-06-18 |
| `quant_hedge_ai.agents.execution.shadow_engine` | `quant_hedge_ai/agents/execution/shadow_engine.py` | 271 | 2026-05-29 |
| `quant_hedge_ai.agents.execution.signal_engine` | `quant_hedge_ai/agents/execution/signal_engine.py` | 137 | 2026-05-29 |
| `quant_hedge_ai.agents.execution.trade_logger` | `quant_hedge_ai/agents/execution/trade_logger.py` | 196 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.activity_tracker` | `quant_hedge_ai/agents/intelligence/activity_tracker.py` | 242 | 2026-05-31 |
| `quant_hedge_ai.agents.intelligence.adaptive_threshold_engine` | `quant_hedge_ai/agents/intelligence/adaptive_threshold_engine.py` | 165 | 2026-05-31 |
| `quant_hedge_ai.agents.intelligence.ai_advisor` | `quant_hedge_ai/agents/intelligence/ai_advisor.py` | 294 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.behavioral_drift_detector` | `quant_hedge_ai/agents/intelligence/behavioral_drift_detector.py` | 261 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.behavioral_stability_monitor` | `quant_hedge_ai/agents/intelligence/behavioral_stability_monitor.py` | 352 | 2026-06-18 |
| `quant_hedge_ai.agents.intelligence.black_box` | `quant_hedge_ai/agents/intelligence/black_box.py` | 510 | 2026-06-18 |
| `quant_hedge_ai.agents.intelligence.chief_officer` | `quant_hedge_ai/agents/intelligence/chief_officer.py` | 557 | 2026-05-31 |
| `quant_hedge_ai.agents.intelligence.confidence_explainer` | `quant_hedge_ai/agents/intelligence/confidence_explainer.py` | 338 | 2026-05-16 |
| `quant_hedge_ai.agents.intelligence.confidence_scorer` | `quant_hedge_ai/agents/intelligence/confidence_scorer.py` | 166 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.conviction_engine` | `quant_hedge_ai/agents/intelligence/conviction_engine.py` | 558 | 2026-06-18 |
| `quant_hedge_ai.agents.intelligence.correlation_monitor` | `quant_hedge_ai/agents/intelligence/correlation_monitor.py` | 266 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.decision_arbitrator` | `quant_hedge_ai/agents/intelligence/decision_arbitrator.py` | 240 | 2026-05-29 |
| `quant_hedge_ai.agents.intelligence.decision_quality_engine` | `quant_hedge_ai/agents/intelligence/decision_quality_engine.py` | 380 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.dynamic_weighting_engine` | `quant_hedge_ai/agents/intelligence/dynamic_weighting_engine.py` | 207 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.feature_engineer` | `quant_hedge_ai/agents/intelligence/feature_engineer.py` | 233 | 2026-05-05 |
| `quant_hedge_ai.agents.intelligence.forbidden_patterns_registry` | `quant_hedge_ai/agents/intelligence/forbidden_patterns_registry.py` | 271 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.market_regime_classifier` | `quant_hedge_ai/agents/intelligence/market_regime_classifier.py` | 382 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.meta_strategy_engine` | `quant_hedge_ai/agents/intelligence/meta_strategy_engine.py` | 434 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.mistake_memory` | `quant_hedge_ai/agents/intelligence/mistake_memory.py` | 663 | 2026-06-18 |
| `quant_hedge_ai.agents.intelligence.no_trade_layer` | `quant_hedge_ai/agents/intelligence/no_trade_layer.py` | 336 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.performance_supervisor` | `quant_hedge_ai/agents/intelligence/performance_supervisor.py` | 232 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.regime_detector` | `quant_hedge_ai/agents/intelligence/regime_detector.py` | 51 | 2026-06-12 |
| `quant_hedge_ai.agents.intelligence.regime_transition_smoother` | `quant_hedge_ai/agents/intelligence/regime_transition_smoother.py` | 139 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.regret_engine` | `quant_hedge_ai/agents/intelligence/regret_engine.py` | 480 | 2026-06-30 |
| `quant_hedge_ai.agents.intelligence.self_awareness_engine` | `quant_hedge_ai/agents/intelligence/self_awareness_engine.py` | 673 | 2026-07-11 |
| `quant_hedge_ai.agents.intelligence.self_monitoring_loop` | `quant_hedge_ai/agents/intelligence/self_monitoring_loop.py` | 220 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.strategy_allocator` | `quant_hedge_ai/agents/intelligence/strategy_allocator.py` | 753 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.strategy_probation` | `quant_hedge_ai/agents/intelligence/strategy_probation.py` | 492 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.sweep_detector` | `quant_hedge_ai/agents/intelligence/sweep_detector.py` | 461 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.sweep_outcome_tracker` | `quant_hedge_ai/agents/intelligence/sweep_outcome_tracker.py` | 437 | 2026-05-26 |
| `quant_hedge_ai.agents.intelligence.system_intel_reporter` | `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` | 546 | 2026-07-16 |
| `quant_hedge_ai.agents.intelligence.system_invariants` | `quant_hedge_ai/agents/intelligence/system_invariants.py` | 59 | 2026-05-16 |
| `quant_hedge_ai.agents.intelligence.threat_radar` | `quant_hedge_ai/agents/intelligence/threat_radar.py` | 490 | 2026-05-26 |
| `quant_hedge_ai.agents.market.market_scanner` | `quant_hedge_ai/agents/market/market_scanner.py` | 915 | 2026-06-18 |
| `quant_hedge_ai.agents.market.multi_timeframe_scanner` | `quant_hedge_ai/agents/market/multi_timeframe_scanner.py` | 146 | 2026-05-26 |
| `quant_hedge_ai.agents.market.ohlcv_validator` | `quant_hedge_ai/agents/market/ohlcv_validator.py` | 133 | 2026-05-26 |
| `quant_hedge_ai.agents.market.retry_policy` | `quant_hedge_ai/agents/market/retry_policy.py` | 158 | 2026-05-26 |
| `quant_hedge_ai.agents.market.symbol_stability` | `quant_hedge_ai/agents/market/symbol_stability.py` | 242 | 2026-06-18 |
| `quant_hedge_ai.agents.risk.anomaly_governance` | `quant_hedge_ai/agents/risk/anomaly_governance.py` | 288 | 2026-05-26 |
| `quant_hedge_ai.agents.risk.capital_allocation_engine` | `quant_hedge_ai/agents/risk/capital_allocation_engine.py` | 289 | 2026-05-26 |
| `quant_hedge_ai.agents.risk.capital_throttle` | `quant_hedge_ai/agents/risk/capital_throttle.py` | 101 | 2026-05-26 |
| `quant_hedge_ai.agents.risk.executive_override` | `quant_hedge_ai/agents/risk/executive_override.py` | 357 | 2026-05-26 |
| `quant_hedge_ai.agents.risk.exposure_manager` | `quant_hedge_ai/agents/risk/exposure_manager.py` | 91 | 2026-05-26 |
| `quant_hedge_ai.agents.risk.global_risk_gate` | `quant_hedge_ai/agents/risk/global_risk_gate.py` | 646 | 2026-07-21 |
| `quant_hedge_ai.agents.risk.portfolio_brain` | `quant_hedge_ai/agents/risk/portfolio_brain.py` | 740 | 2026-06-02 |
| `quant_hedge_ai.agents.risk.portfolio_intelligence` | `quant_hedge_ai/agents/risk/portfolio_intelligence.py` | 209 | 2026-05-26 |
| `quant_hedge_ai.agents.risk.risk_governor` | `quant_hedge_ai/agents/risk/risk_governor.py` | 295 | 2026-05-26 |
| `quant_hedge_ai.agents.risk.session_guard` | `quant_hedge_ai/agents/risk/session_guard.py` | 211 | 2026-05-26 |
| `quant_hedge_ai.agents.risk.system_health_monitor` | `quant_hedge_ai/agents/risk/system_health_monitor.py` | 221 | 2026-05-26 |
| `quant_hedge_ai.ai_evolution.strategy_memory` | `quant_hedge_ai/ai_evolution/strategy_memory.py` | 208 | 2026-05-26 |
| `quant_hedge_ai.ai_evolution.strategy_ranker` | `quant_hedge_ai/ai_evolution/strategy_ranker.py` | 423 | 2026-05-26 |
| `quant_hedge_ai.dashboard.live_snapshot` | `quant_hedge_ai/dashboard/live_snapshot.py` | 55 | 2026-05-26 |
| `quant_hedge_ai.persistent_warmup` | `quant_hedge_ai/persistent_warmup.py` | 426 | 2026-05-05 |
| `quant_hedge_ai.runtime.runtime_state_machine` | `quant_hedge_ai/runtime/runtime_state_machine.py` | 305 | 2026-06-02 |
| `risk.risk_limits` | `risk/risk_limits.py` | 176 | 2026-05-29 |
| `scripts.data_quality` | `scripts/data_quality.py` | 291 | 2026-07-16 |
| `scripts.shadow_execution` | `scripts/shadow_execution.py` | 242 | 2026-05-25 |
| `scripts.telegram_alerts` | `scripts/telegram_alerts.py` | 233 | 2026-06-30 |
| `supervision.alert_manager` | `supervision/alert_manager.py` | 112 | 2026-04-28 |
| `supervision.circuit_breaker_robust` | `supervision/circuit_breaker_robust.py` | 180 | 2026-05-26 |
| `supervision.exchange_monitor` | `supervision/exchange_monitor.py` | 294 | 2026-06-13 |
| `supervision.killswitch_hardened` | `supervision/killswitch_hardened.py` | 518 | 2026-06-12 |
| `supervision.notifications.telegram_notifier` | `supervision/notifications/telegram_notifier.py` | 37 | 2026-05-26 |
| `supervision.performance_watchdog` | `supervision/performance_watchdog.py` | 318 | 2026-05-26 |
| `supervision.self_healing_bot` | `supervision/self_healing_bot.py` | 583 | 2026-05-26 |
| `system.integrity_models` | `system/integrity_models.py` | 200 | 2026-05-29 |
| `system.integrity_rules` | `system/integrity_rules.py` | 310 | 2026-05-29 |
| `system.integrity_snapshot` | `system/integrity_snapshot.py` | 157 | 2026-05-29 |
| `system.module_registry` | `system/module_registry.py` | 254 | 2026-05-08 |
| `system.position_reconciler` | `system/position_reconciler.py` | 185 | 2026-05-26 |
| `system.safety_auditor` | `system/safety_auditor.py` | 242 | 2026-05-26 |
| `system.state_integrity` | `system/state_integrity.py` | 254 | 2026-05-29 |
| `system.state_machine` | `system/state_machine.py` | 242 | 2026-06-16 |
| `system.state_manager` | `system/state_manager.py` | 200 | 2026-05-08 |
| `tools.cri_calculator` | `tools/cri_calculator.py` | 386 | 2026-07-28 |
| `tools.market_universe_ranker` | `tools/market_universe_ranker.py` | 364 | 2026-06-15 |
| `tools.perp_universe_builder` | `tools/perp_universe_builder.py` | 365 | 2026-06-18 |
| `tools.regret_repository` | `tools/regret_repository.py` | 102 | 2026-07-21 |
| `tracker_system.analytics.metrics` | `tracker_system/analytics/metrics.py` | 159 | 2026-05-14 |
| `tracker_system.analytics.mfe_mae` | `tracker_system/analytics/mfe_mae.py` | 24 | 2026-05-05 |
| `tracker_system.analytics.regime_analysis` | `tracker_system/analytics/regime_analysis.py` | 26 | 2026-05-05 |
| `tracker_system.analytics.score_drift_monitor` | `tracker_system/analytics/score_drift_monitor.py` | 155 | 2026-05-14 |
| `tracker_system.autonomous.auto_decision_engine` | `tracker_system/autonomous/auto_decision_engine.py` | 435 | 2026-05-18 |
| `tracker_system.backtesting.auto_backtester` | `tracker_system/backtesting/auto_backtester.py` | 90 | 2026-05-05 |
| `tracker_system.backtesting.simulator` | `tracker_system/backtesting/simulator.py` | 26 | 2026-05-05 |
| `tracker_system.config.exit_config` | `tracker_system/config/exit_config.py` | 125 | 2026-05-14 |
| `tracker_system.config.settings` | `tracker_system/config/settings.py` | 165 | 2026-05-14 |
| `tracker_system.core.boot_validator` | `tracker_system/core/boot_validator.py` | 129 | 2026-05-26 |
| `tracker_system.core.position_manager` | `tracker_system/core/position_manager.py` | 24 | 2026-05-05 |
| `tracker_system.core.trade_logger` | `tracker_system/core/trade_logger.py` | 148 | 2026-05-08 |
| `tracker_system.core.trade_tracker` | `tracker_system/core/trade_tracker.py` | 322 | 2026-05-14 |
| `tracker_system.dashboard.builder` | `tracker_system/dashboard/builder.py` | 250 | 2026-05-14 |
| `tracker_system.engine.exit_engine` | `tracker_system/engine/exit_engine.py` | 29 | 2026-05-05 |
| `tracker_system.engine.exit_factory` | `tracker_system/engine/exit_factory.py` | 18 | 2026-05-05 |
| `tracker_system.engine.rules.breakeven` | `tracker_system/engine/rules/breakeven.py` | 27 | 2026-05-05 |
| `tracker_system.engine.rules.tp_sl` | `tracker_system/engine/rules/tp_sl.py` | 27 | 2026-05-05 |
| `tracker_system.engine.rules.trailing` | `tracker_system/engine/rules/trailing.py` | 22 | 2026-05-05 |
| `tracker_system.main` | `tracker_system/main.py` | 145 | 2026-05-14 |
| `tracker_system.meta_learner` | `tracker_system/meta_learner.py` | 169 | 2026-05-05 |
| `tracker_system.meta_memory` | `tracker_system/meta_memory.py` | 60 | 2026-05-05 |
| `tracker_system.scheduler.auto_update` | `tracker_system/scheduler/auto_update.py` | 133 | 2026-05-05 |
| `tracker_system.storage.loader` | `tracker_system/storage/loader.py` | 31 | 2026-05-05 |
| `tracker_system.storage.saver` | `tracker_system/storage/saver.py` | 16 | 2026-05-05 |

## 4. Répertoires présentés comme « base Research OS »

Vérification de la vitalité réelle de chaque répertoire.

| Répertoire | Modules | ACTIVE | ORPHAN | TEST_ONLY | Dernier commit du package |
|---|---:|---:|---:|---:|---|
| `research/` | 0 | 0 | 0 | 0 | — (aucun module Python) |
| `experiments/` | 0 | 0 | 0 | 0 | — (aucun module Python) |
| `walk_forward/` | 5 | 0 | 1 | 4 | 2026-05-14 |
| `meta_learning/` | 5 | 0 | 1 | 4 | 2026-05-25 |
| `execution_simulator/` | 9 | 7 | 1 | 1 | 2026-06-13 |
| `ai_autonomous_loop/` | 1 | 0 | 1 | 0 | 2026-04-27 |
| `project_os/` | 9 | 0 | 1 | 0 | 2026-05-14 |
| `audit/` | 5 | 0 | 2 | 3 | 2026-05-08 |
| `governance/` | 11 | 1 | 10 | 0 | 2026-06-02 |
| `observability/` | 18 | 15 | 3 | 0 | 2026-07-31 |
| `tools/` | 21 | 4 | 0 | 12 | 2026-07-30 |

## 5. Flow runtime mesuré

Voir `DECISION_PATH.md` pour le détail fonction/fichier/ligne.

```
Market Data      infra/multi_exchange_feed.py, exchange_factory
      |
      v
Scanner          core/advisor_loop.py  (scanners: dict)
      |
      v
Features         FeatureEngineer -> features: dict
      |
      v
Signal           engine.evaluate()            advisor_loop.py:1459
      |
      v
Decision         trade_allowed = AND(12)      advisor_loop.py:1983
      |
      +--> REVOCATION 1  risk_governor         advisor_loop.py:5626
      +--> REVOCATION 2  safety_auditor        advisor_loop.py:5658
      +--> REVOCATION 3  (non nomme)           advisor_loop.py:5734
      +--> REVOCATION 4  decision_packet       advisor_loop.py:5808
      |
      v
Risk / Sizing    order_size_usd (mute par EO, conviction, arbitrage)
      |
      v
Execution        execution_engine / MexcSimulator
      |
      v
Logging          paper_trades.jsonl, black_box.jsonl, decision_packets
      |
      v
Replay           NON MESURE - aucun moteur de rejeu deterministe identifie
```
