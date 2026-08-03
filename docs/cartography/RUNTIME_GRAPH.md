# RUNTIME_GRAPH.md — Graphe réel des imports
> **Document généré automatiquement.** Ne pas éditer à la main.
> Source : `artifacts/cartography.json` — régénérer via
> `python tools/runtime_cartographer.py && python tools/cartography_report.py`
> Généré le 2026-08-01 — commit `348e83d`

> **Portée de la mesure.** Graphe d'import statique (AST), imports paresseux
> inclus. `ACTIVE` signifie **atteignable par import** depuis le point d'entrée
> runtime, **pas** « exécuté ». Prouver l'exécution exige une trace runtime
> (`sys.settrace`/coverage sur le VPS) — **NON MESURÉ** en J1-J2.

## 1. Mesures globales

| Mesure | Valeur |
|---|---:|
| `modules_total` | 1115 |
| `modules_runtime_reachable` | 170 |
| `modules_test_only` | 279 |
| `modules_tool` | 94 |
| `modules_orphan` | 248 |
| `modules_test` | 324 |
| `import_cycles` | 3 |
| `isolated_modules` | 153 |
| `ambiguous_bare_imports` | 1 |

## 2. Cycles d'import

**3 cycles mesurés.**

| # | Composante fortement connexe | Statut des membres |
|---|---|---|
| 1 | `core.decision_packet` ↔ `core.lifecycle` | ACTIVE |
| 2 | `lm_studio` ↔ `lm_studio.ai_router` | ACTIVE |
| 3 | `tracker_system.main` ↔ `tracker_system.scheduler.auto_update` | ACTIVE |

## 3. Modules les plus dépendus (couplage entrant)

| Module | Statut | Importé par | LOC |
|---|---|---:|---:|
| `observability.json_logger` | ACTIVE | 193 | 258 |
| `dip.core.types` | ACTIVE | 44 | 171 |
| `core.decision_packet` | ACTIVE | 22 | 861 |
| `dip.core.store` | TEST_ONLY | 20 | 419 |
| `src.domain.trade_event` | TEST_ONLY | 19 | 83 |
| `tracker_system.config.settings` | ACTIVE | 19 | 165 |
| `dip.modules.decision_graph` | TEST_ONLY | 17 | 659 |
| `event_bus.bus` | ACTIVE | 15 | 274 |
| `event_bus.events` | ACTIVE | 15 | 388 |
| `pieuvre.incidents.models` | TEST_ONLY | 15 | 148 |
| `quant_hedge_ai.runtime.runtime_state_machine` | ACTIVE | 15 | 305 |
| `tools.cri_calculator` | ACTIVE | 15 | 386 |
| `cold_start.warmup_state_machine` | TEST_ONLY | 14 | 308 |
| `observability.metrics_bus` | ACTIVE | 14 | 228 |
| `visualization.api.models` | TEST_ONLY | 14 | 222 |
| `execution_simulator.models` | ACTIVE | 13 | 177 |
| `quant_hedge_ai.agents.execution.live_signal_engine` | ACTIVE | 13 | 608 |
| `system.module_registry` | ACTIVE | 13 | 254 |
| `tracker_system.storage.loader` | ACTIVE | 13 | 31 |
| `cold_start.warmup_signer` | TEST_ONLY | 12 | 171 |
| `quant_hedge_ai.agents.market.ohlcv_validator` | ACTIVE | 12 | 133 |
| `src.domain.signal` | TEST_ONLY | 12 | 8 |
| `src.risk.kill_switch` | TEST_ONLY | 12 | 9 |
| `tracker_system.core.trade_tracker` | ACTIVE | 12 | 322 |
| `market_data.models` | TEST_ONLY | 11 | 267 |

## 4. Modules les plus couplants (couplage sortant)

| Module | Statut | Importe | dont paresseux | LOC |
|---|---|---:|---:|---:|
| `core.advisor_loop` | ENTRYPOINT | 81 | 134 | 7815 |
| `quant_hedge_ai.main_v91` | TOOL | 54 | 6 | 1111 |
| `core.advisor_runtime_adapters` | ACTIVE | 37 | 38 | 160 |
| `quant_hedge_ai.main_system` | TOOL | 26 | 0 | 224 |
| `src.telegram.sim_bot` | TEST_ONLY | 25 | 6 | 1207 |
| `tests.integration.test_p4_pipeline` | TEST | 17 | 2 | 407 |
| `dip.cli` | TEST_ONLY | 15 | 18 | 591 |
| `pieuvre.brain` | TEST_ONLY | 13 | 4 | 447 |
| `scripts.boot_system_validator` | TOOL | 13 | 14 | 734 |
| `tests.root.test_boot_system` | TEST | 13 | 15 | 766 |
| `tests.test_phase_a_replay_invariants` | TEST | 13 | 5 | 565 |
| `tests.test_enl` | TEST | 12 | 0 | 166 |
| `tests.test_run_context` | TEST | 12 | 1 | 203 |
| `tests.test_regime` | TEST | 11 | 2 | 195 |
| `tests.test_regime_gate` | TEST | 11 | 0 | 114 |
| `visualization.api` | TEST_ONLY | 11 | 0 | 54 |
| `core.invariants` | ORPHAN | 10 | 28 | 743 |
| `scripts.smoke_test_ci` | ORPHAN | 10 | 13 | 238 |
| `tests.stress.test_stress_volume` | TEST | 10 | 1 | 464 |
| `cold_start.tests.test_cold_start` | TEST | 9 | 157 | 1411 |
| `crypto.tests.test_crypto` | TEST | 9 | 71 | 947 |
| `infra.automate_pipeline` | ORPHAN | 9 | 6 | 231 |
| `pieuvre.tentacles` | ORPHAN | 9 | 0 | 21 |
| `src.analytics.edge_scorer` | TEST_ONLY | 9 | 0 | 148 |
| `system.burn_in` | TEST_ONLY | 9 | 2 | 441 |

## 5. Modules isolés — aucun importeur, aucun `__main__`

**153 modules mesurés.**

- `S2` — `S2/__init__.py` (9 LOC, dernier commit 2026-05-25)
- `ai_autonomous_loop` — `ai_autonomous_loop/__init__.py` (1 LOC, dernier commit 2026-04-27)
- `analysis` — `analysis/__init__.py` (1 LOC, dernier commit 2026-06-28)
- `audit` — `audit/__init__.py` (12 LOC, dernier commit 2026-05-05)
- `audit.decision_ledger` — `audit/decision_ledger.py` (332 LOC, dernier commit 2026-05-08)
- `config` — `config/__init__.py` (3 LOC, dernier commit 2026-06-12)
- `core.formal_proof` — `core/formal_proof.py` (461 LOC, dernier commit 2026-06-02)
- `core.invariants` — `core/invariants.py` (743 LOC, dernier commit 2026-06-02)
- `core.orchestration` — `core/orchestration/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `core.orchestration.orchestrate_all` — `core/orchestration/orchestrate_all.py` (76 LOC, dernier commit 2026-05-29)
- `core.orchestration.orchestrate_and_test_panels` — `core/orchestration/orchestrate_and_test_panels.py` (68 LOC, dernier commit 2026-05-29)
- `core.orchestration.orchestrate_internal_panels` — `core/orchestration/orchestrate_internal_panels.py` (25 LOC, dernier commit 2026-05-29)
- `core.orchestration.send_orchestration_notification` — `core/orchestration/send_orchestration_notification.py` (54 LOC, dernier commit 2026-05-29)
- `core.runtime_state_machine` — `core/runtime_state_machine.py` (18 LOC, dernier commit 2026-06-02)
- `crypto` — `crypto/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `dashboard` — `dashboard/__init__.py` (0 LOC, dernier commit 2026-06-01)
- `dip` — `dip/__init__.py` (24 LOC, dernier commit 2026-06-30)
- `dip.__main__` — `dip/__main__.py` (7 LOC, dernier commit 2026-06-30)
- `dip.bootstrap` — `dip/bootstrap.py` (84 LOC, dernier commit 2026-06-30)
- `dip.core` — `dip/core/__init__.py` (1 LOC, dernier commit 2026-06-30)
- `dip.modules` — `dip/modules/__init__.py` (1 LOC, dernier commit 2026-06-30)
- `docs.conf` — `docs/conf.py` (73 LOC, dernier commit 2026-04-27)
- `errors` — `errors/__init__.py` (1 LOC, dernier commit 2026-05-08)
- `errors.incident_manager` — `errors/incident_manager.py` (324 LOC, dernier commit 2026-05-08)
- `event_bus` — `event_bus/__init__.py` (7 LOC, dernier commit 2026-04-28)
- `exchange_constraints` — `exchange_constraints/__init__.py` (40 LOC, dernier commit 2026-06-13)
- `execution_simulator` — `execution_simulator/__init__.py` (24 LOC, dernier commit 2026-06-13)
- `governance` — `governance/__init__.py` (32 LOC, dernier commit 2026-06-02)
- `governance.ai_constraints` — `governance/ai_constraints.py` (258 LOC, dernier commit 2026-05-08)
- `governance.decision_router` — `governance/decision_router.py` (307 LOC, dernier commit 2026-05-08)
- `health` — `health/__init__.py` (1 LOC, dernier commit 2026-05-08)
- `health.health_registry` — `health/health_registry.py` (286 LOC, dernier commit 2026-05-08)
- `health.recovery_manager` — `health/recovery_manager.py` (315 LOC, dernier commit 2026-05-08)
- `infra` — `infra/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `infra.api` — `infra/api/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `infra.api.api_rest` — `infra/api/api_rest.py` (33 LOC, dernier commit 2026-05-29)
- `infra.api.api_server` — `infra/api/api_server.py` (418 LOC, dernier commit 2026-07-06)
- `infra.automate_pipeline` — `infra/automate_pipeline.py` (231 LOC, dernier commit 2026-05-29)
- `infra.check_imports` — `infra/check_imports.py` (36 LOC, dernier commit 2026-05-29)
- `infra.dashboards` — `infra/dashboards/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `infra.monitoring` — `infra/monitoring/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `infra.monitoring.surveillance_continue` — `infra/monitoring/surveillance_continue.py` (127 LOC, dernier commit 2026-05-29)
- `infra.notifications.notify_selenium_report_discord` — `infra/notifications/notify_selenium_report_discord.py` (33 LOC, dernier commit 2026-05-29)
- `infra.notifications.notify_selenium_report_slack` — `infra/notifications/notify_selenium_report_slack.py` (33 LOC, dernier commit 2026-05-29)
- `infra.panels` — `infra/panels/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `infra.panels.panel_ci_report` — `infra/panels/panel_ci_report.py` (88 LOC, dernier commit 2026-05-29)
- `infra.visualization` — `infra/visualization/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `infra.visualization.ui_utils` — `infra/visualization/ui_utils.py` (75 LOC, dernier commit 2026-05-29)
- `infra.visualization.visualization` — `infra/visualization/visualization.py` (74 LOC, dernier commit 2026-05-29)
- `market_data` — `market_data/__init__.py` (30 LOC, dernier commit 2026-06-13)
- `market_data.metrics` — `market_data/metrics/__init__.py` (51 LOC, dernier commit 2026-05-14)
- `meta_learning` — `meta_learning/__init__.py` (12 LOC, dernier commit 2026-05-25)
- `metrics` — `metrics/__init__.py` (0 LOC, dernier commit 2026-05-14)
- `metrics.robustness` — `metrics/robustness.py` (274 LOC, dernier commit 2026-05-14)
- `monitor` — `monitor/__init__.py` (0 LOC, dernier commit 2026-05-14)
- `monitoring` — `monitoring/__init__.py` (0 LOC, dernier commit 2026-05-14)
- `monitoring.profiler` — `monitoring/profiler.py` (263 LOC, dernier commit 2026-05-14)
- `observability` — `observability/__init__.py` (1 LOC, dernier commit 2026-05-08)
- `observability.telemetry` — `observability/telemetry.py` (163 LOC, dernier commit 2026-05-08)
- `observation` — `observation/__init__.py` (0 LOC, dernier commit 2026-07-15)
- `pieuvre.incidents` — `pieuvre/incidents/__init__.py` (4 LOC, dernier commit 2026-04-28)
- `pieuvre.tentacles` — `pieuvre/tentacles/__init__.py` (21 LOC, dernier commit 2026-04-28)
- `project_os` — `project_os/__init__.py` (0 LOC, dernier commit 2026-05-14)
- `quant_hedge_ai` — `quant_hedge_ai/__init__.py` (0 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.agents` — `quant_hedge_ai/agents/__init__.py` (1 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.agents.execution.execution_optimizer` — `quant_hedge_ai/agents/execution/execution_optimizer.py` (228 LOC, dernier commit 2026-05-29)
- `quant_hedge_ai.agents.execution.optimal_timing_engine` — `quant_hedge_ai/agents/execution/optimal_timing_engine.py` (187 LOC, dernier commit 2026-05-29)
- `quant_hedge_ai.agents.execution.slippage_predictor` — `quant_hedge_ai/agents/execution/slippage_predictor.py` (177 LOC, dernier commit 2026-05-29)
- `quant_hedge_ai.agents.intelligence.regime_transition_predictor` — `quant_hedge_ai/agents/intelligence/regime_transition_predictor.py` (218 LOC, dernier commit 2026-05-29)
- `quant_hedge_ai.agents.market.microstructure` — `quant_hedge_ai/agents/market/microstructure/__init__.py` (9 LOC, dernier commit 2026-05-05)
- `quant_hedge_ai.agents.monitoring` — `quant_hedge_ai/agents/monitoring/__init__.py` (5 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.agents.onchain` — `quant_hedge_ai/agents/onchain/__init__.py` (9 LOC, dernier commit 2026-05-05)
- `quant_hedge_ai.agents.quant` — `quant_hedge_ai/agents/quant/__init__.py` (1 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.agents.research` — `quant_hedge_ai/agents/research/__init__.py` (8 LOC, dernier commit 2026-04-28)
- `quant_hedge_ai.agents.risk` — `quant_hedge_ai/agents/risk/__init__.py` (1 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.agents.strategy` — `quant_hedge_ai/agents/strategy/__init__.py` (1 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.ai_evolution.model_degradation_monitor` — `quant_hedge_ai/ai_evolution/model_degradation_monitor.py` (199 LOC, dernier commit 2026-05-29)
- `quant_hedge_ai.features` — `quant_hedge_ai/features/__init__.py` (6 LOC, dernier commit 2026-05-05)
- `quant_hedge_ai.liquidity_map` — `quant_hedge_ai/liquidity_map/__init__.py` (5 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.market_radar.anomaly_detector` — `quant_hedge_ai/market_radar/anomaly_detector.py` (220 LOC, dernier commit 2026-05-26)
- `quant_hedge_ai.market_radar.radar_core` — `quant_hedge_ai/market_radar/radar_core.py` (273 LOC, dernier commit 2026-05-26)
- `quant_hedge_ai.market_radar.social_scanner` — `quant_hedge_ai/market_radar/social_scanner.py` (163 LOC, dernier commit 2026-05-26)
- `quant_hedge_ai.market_radar.token_scanner` — `quant_hedge_ai/market_radar/token_scanner.py` (190 LOC, dernier commit 2026-05-26)
- `quant_hedge_ai.market_radar.whale_tracker` — `quant_hedge_ai/market_radar/whale_tracker.py` (222 LOC, dernier commit 2026-05-26)
- `quant_hedge_ai.runtime` — `quant_hedge_ai/runtime/__init__.py` (17 LOC, dernier commit 2026-05-29)
- `quant_hedge_ai.runtime.health_endpoint` — `quant_hedge_ai/runtime/health_endpoint.py` (124 LOC, dernier commit 2026-05-29)
- `quant_hedge_ai.strategy_factory.factory_core` — `quant_hedge_ai/strategy_factory/factory_core.py` (143 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.strategy_lab` — `quant_hedge_ai/strategy_lab/__init__.py` (2 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.strategy_lab.example_pipeline` — `quant_hedge_ai/strategy_lab/example_pipeline.py` (54 LOC, dernier commit 2026-04-27)
- `quant_hedge_ai.strategy_lab.feature_cache` — `quant_hedge_ai/strategy_lab/feature_cache.py` (81 LOC, dernier commit 2026-04-27)
- `reality_checks` — `reality_checks/__init__.py` (0 LOC, dernier commit 2026-05-29)
- `risk` — `risk/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `risk.global_risk_gate` — `risk/global_risk_gate.py` (328 LOC, dernier commit 2026-05-29)
- `runtime` — `runtime/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `scripts.bear_trend_audit` — `scripts/bear_trend_audit.py` (193 LOC, dernier commit 2026-06-24)
- `scripts.copy_docs_for_sphinx` — `scripts/copy_docs_for_sphinx.py` (26 LOC, dernier commit 2026-05-29)
- `scripts.crypto_market_scanner` — `scripts/crypto_market_scanner.py` (113 LOC, dernier commit 2026-06-13)
- `scripts.crypto_terminal` — `scripts/crypto_terminal.py` (70 LOC, dernier commit 2026-06-13)
- `scripts.generate_panel_screenshots` — `scripts/generate_panel_screenshots.py` (49 LOC, dernier commit 2026-04-27)
- `scripts.minimal_test` — `scripts/minimal_test.py` (22 LOC, dernier commit 2026-05-05)
- `scripts.quickstart` — `scripts/quickstart.py` (131 LOC, dernier commit 2026-05-05)
- `scripts.seed_decision_packets` — `scripts/seed_decision_packets.py` (283 LOC, dernier commit 2026-05-11)
- `scripts.smoke_test_ci` — `scripts/smoke_test_ci.py` (238 LOC, dernier commit 2026-04-27)
- `scripts.toxicity_report` — `scripts/toxicity_report.py` (130 LOC, dernier commit 2026-06-24)
- `sdos_terminal` — `sdos_terminal/__init__.py` (3 LOC, dernier commit 2026-07-06)
- `sdos_terminal.api` — `sdos_terminal/api/__init__.py` (1 LOC, dernier commit 2026-07-06)
- `sdos_terminal.api.app` — `sdos_terminal/api/app.py` (432 LOC, dernier commit 2026-07-06)
- `signal.analysis` — `signal/analysis/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `signal.analysis.tune` — `signal/analysis/tune.py` (183 LOC, dernier commit 2026-06-02)
- `signal.evolution` — `signal/evolution/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `signal.strategies` — `signal/strategies/__init__.py` (1 LOC, dernier commit 2026-05-29)
- `signal.strategies.run_strategy_factory_batch` — `signal/strategies/run_strategy_factory_batch.py` (90 LOC, dernier commit 2026-05-29)
- `src` — `src/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.agent` — `src/agent/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.analytics` — `src/analytics/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.backtest` — `src/backtest/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.domain` — `src/domain/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.engine` — `src/engine/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.events` — `src/events/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.execution` — `src/execution/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.journal` — `src/journal/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.paper` — `src/paper/__init__.py` (0 LOC, dernier commit 2026-06-04)
- `src.portfolio` — `src/portfolio/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.risk` — `src/risk/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.runtime` — `src/runtime/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.storage` — `src/storage/__init__.py` (0 LOC, dernier commit 2026-06-08)
- `src.telegram` — `src/telegram/__init__.py` (3 LOC, dernier commit 2026-06-08)
- `src.telegram.exchange_sync` — `src/telegram/exchange_sync.py` (316 LOC, dernier commit 2026-06-08)
- `src.telegram.quant_observer` — `src/telegram/quant_observer/__init__.py` (1 LOC, dernier commit 2026-07-06)
- `supervision` — `supervision/__init__.py` (21 LOC, dernier commit 2026-06-12)
- `supervision.telegram_kill_switch` — `supervision/telegram_kill_switch.py` (315 LOC, dernier commit 2026-05-26)
- `system` — `system/__init__.py` (5 LOC, dernier commit 2026-05-26)
- `system.kernel` — `system/kernel.py` (261 LOC, dernier commit 2026-05-26)
- `terminal_core` — `terminal_core/__init__.py` (1 LOC, dernier commit 2026-04-27)
- `terminal_core.quant` — `terminal_core/quant/__init__.py` (1 LOC, dernier commit 2026-04-27)
- `tracker_system.analytics` — `tracker_system/analytics/__init__.py` (3 LOC, dernier commit 2026-05-05)
- `tracker_system.backtesting` — `tracker_system/backtesting/__init__.py` (4 LOC, dernier commit 2026-05-05)
- `tracker_system.core` — `tracker_system/core/__init__.py` (15 LOC, dernier commit 2026-05-05)
- `tracker_system.dashboard` — `tracker_system/dashboard/__init__.py` (3 LOC, dernier commit 2026-05-05)
- `tracker_system.engine` — `tracker_system/engine/__init__.py` (4 LOC, dernier commit 2026-05-05)
- `tracker_system.engine.rules` — `tracker_system/engine/rules/__init__.py` (5 LOC, dernier commit 2026-05-05)
- `tracker_system.risk` — `tracker_system/risk/__init__.py` (17 LOC, dernier commit 2026-05-05)
- `tracker_system.scheduler` — `tracker_system/scheduler/__init__.py` (3 LOC, dernier commit 2026-05-05)
- `tracker_system.sessions` — `tracker_system/sessions/__init__.py` (50 LOC, dernier commit 2026-05-14)
- `tracker_system.sessions.schemas` — `tracker_system/sessions/schemas/__init__.py` (0 LOC, dernier commit 2026-05-14)
- `tracker_system.storage` — `tracker_system/storage/__init__.py` (4 LOC, dernier commit 2026-05-05)
- `visualization.renderers` — `visualization/renderers/__init__.py` (1 LOC, dernier commit 2026-07-06)
- `visualization.renderers.equity` — `visualization/renderers/equity.py` (189 LOC, dernier commit 2026-07-06)
- `visualization.renderers.pipeline` — `visualization/renderers/pipeline.py` (191 LOC, dernier commit 2026-07-06)
- `visualization.renderers.radar` — `visualization/renderers/radar.py` (206 LOC, dernier commit 2026-07-06)
- `visualization.renderers.timeline` — `visualization/renderers/timeline.py` (144 LOC, dernier commit 2026-07-06)
- `visualization.ves.contracts` — `visualization/ves/contracts.py` (24 LOC, dernier commit 2026-07-06)
- `walk_forward` — `walk_forward/__init__.py` (0 LOC, dernier commit 2026-05-14)

## 6. Doublons de nom de classe (plusieurs vérités)

**69 noms de classe définis à plusieurs endroits (hors tests).**

| Classe | Définitions | Statuts |
|---|---|---|
| `CheckResult` | `certification/p10_checker.py:49`<br>`core/execution_trace.py:89`<br>`health/health_registry.py:51`<br>`scripts/boot_system_validator.py:54`<br>`scripts/runtime_validator.py:62`<br>`tools/instrumentation_validator.py:61` | TOOL, ORPHAN, ORPHAN, TOOL, TOOL, TEST_ONLY |
| `TradeRecord` | `capital_deployment/phase_kpi_tracker.py:67`<br>`observation/accounts/trade_collector.py:39`<br>`quant_hedge_ai/agents/execution/trade_postmortem.py:28`<br>`quant_hedge_ai/agents/intelligence/performance_supervisor.py:40` | ACTIVE, TEST_ONLY, TEST_ONLY, ACTIVE |
| `AuditTrail` | `certification/audit_trail_final.py:61`<br>`crypto/audit_trail.py:90`<br>`dip/modules/audit_trail.py:46` | TEST_ONLY, TEST_ONLY, TEST_ONLY |
| `Alert` | `dip/modules/decision_alert.py:41`<br>`observability/alerting.py:51`<br>`supervision/alert_manager.py:15` | TEST_ONLY, ACTIVE, ACTIVE |
| `ValidationResult` | `exchange_constraints/models.py:100`<br>`paper_trading/dataset_validator.py:100`<br>`tracker_system/sessions/session_validator.py:17` | ACTIVE, ACTIVE, ORPHAN |
| `MarketSnapshot` | `execution_simulator/models.py:53`<br>`observability/system_snapshot.py:92`<br>`quant_hedge_ai/data/canonical_market_model.py:15` | ACTIVE, ACTIVE, ORPHAN |
| `GateResult` | `governance/confidence_gate.py:74`<br>`quant_hedge_ai/agents/risk/global_risk_gate.py:158`<br>`scripts/prelive_gate.py:112` | ORPHAN, ACTIVE, TEST_ONLY |
| `HealthSnapshot` | `observability/system_snapshot.py:47`<br>`system/burn_in.py:72`<br>`visualization/api/models.py:16` | ACTIVE, TEST_ONLY, TEST_ONLY |
| `PortfolioSnapshot` | `observability/system_snapshot.py:56`<br>`quant_hedge_ai/agents/risk/portfolio_brain.py:64`<br>`visualization/api/models.py:69` | ACTIVE, ACTIVE, TEST_ONLY |
| `Position` | `quant_hedge_ai/agents/execution/position_manager.py:60`<br>`quant_hedge_ai/agents/risk/portfolio_intelligence.py:38`<br>`src/domain/position.py:7` | ACTIVE, ACTIVE, TEST_ONLY |
| `StrategyRanker` | `quant_hedge_ai/ai_evolution/strategy_ranker.py:140`<br>`quant_hedge_ai/engine/decision_engine.py:8`<br>`quant_hedge_ai/strategy_lab/ranker.py:2` | ACTIVE, TEST_ONLY, TEST_ONLY |
| `SystemState` | `quant_hedge_ai/runtime/runtime_state_machine.py:35`<br>`scripts/burnin_calibration_v3.py:113`<br>`system/state_manager.py:15` | ACTIVE, TEST_ONLY, ACTIVE |
| `TelegramAlert` | `S3/01_telegram_alerts.py:55`<br>`scripts/telegram_alerts.py:70` | TOOL, ACTIVE |
| `ShadowTracker` | `S3/03_shadow_execution.py:32`<br>`scripts/shadow_execution.py:32` | TOOL, ACTIVE |
| `Trade` | `analysis/base.py:16`<br>`system/strategy_metrics.py:25` | TEST_ONLY, TEST_ONLY |
| `DecisionRecord` | `audit/decision_ledger.py:74`<br>`quant_hedge_ai/agents/intelligence/decision_quality_engine.py:52` | ORPHAN, ACTIVE |
| `DecisionTrace` | `audit/decision_trace.py:12`<br>`visualization/decision_trace_service.py:76` | TEST_ONLY, TEST_ONLY |
| `ReplayEngine` | `audit/replay_engine.py:131`<br>`market_data/replay_engine.py:70` | TEST_ONLY, TEST_ONLY |
| `CapitalThrottle` | `capital_deployment/capital_throttle.py:59`<br>`quant_hedge_ai/agents/risk/capital_throttle.py:18` | ACTIVE, ACTIVE |
| `KPISnapshot` | `capital_deployment/phase_kpi_tracker.py:78`<br>`certification/live_kpi_auditor.py:35` | ACTIVE, TEST_ONLY |
| `ModuleSpec` | `certification/module_certifier.py:42`<br>`quant_hedge_ai/bench_boot_constructors.py:43` | TEST_ONLY, TOOL |
| `MarketRegime` | `core/decision_packet.py:43`<br>`src/domain/trade_event.py:26` | ACTIVE, TEST_ONLY |
| `ConvictionLevel` | `core/decision_packet.py:51`<br>`quant_hedge_ai/agents/intelligence/conviction_engine.py:46` | ACTIVE, ACTIVE |
| `DecisionState` | `core/decision_packet.py:105`<br>`observability/system_snapshot.py:14` | ACTIVE, ACTIVE |
| `StateTransition` | `core/decision_packet.py:247`<br>`system/state_manager.py:87` | ACTIVE, ACTIVE |
| `InvariantViolation` | `core/invariants.py:25`<br>`system/invariant_checker.py:31` | ORPHAN, TEST_ONLY |
| `Severity` | `dip/core/types.py:54`<br>`pieuvre/incidents/models.py:12` | ACTIVE, TEST_ONLY |
| `IntegrityReport` | `dip/modules/audit_trail.py:54`<br>`system/integrity_models.py:117` | TEST_ONLY, ACTIVE |
| `AuditReport` | `dip/modules/audit_trail.py:63`<br>`tools/score_calibration_audit.py:365` | TEST_ONLY, TEST_ONLY |
| `AlertRule` | `dip/modules/decision_alert.py:32`<br>`observability/alerting.py:66` | TEST_ONLY, ACTIVE |
| `DriftReport` | `dip/modules/knowledge_base.py:71`<br>`quant_hedge_ai/agents/intelligence/behavioral_drift_detector.py:54` | TEST_ONLY, ACTIVE |
| `Incident` | `errors/incident_manager.py:56`<br>`pieuvre/incidents/models.py:87` | ORPHAN, TEST_ONLY |
| `SystemSnapshot` | `infra/monitoring/daily_analyzer.py:19`<br>`observability/system_snapshot.py:173` | TEST_ONLY, ACTIVE |
| `Tick` | `infra/stream_bus.py:26`<br>`scripts/stream_bus_simulation.py:23` | ORPHAN, TOOL |
| `LatestSnapshot` | `infra/stream_bus.py:34`<br>`scripts/stream_bus_simulation.py:31` | ORPHAN, TOOL |
| `StreamBus` | `infra/stream_bus.py:77`<br>`scripts/stream_bus_simulation.py:64` | ORPHAN, TOOL |
| `SweepEvent` | `market_data/metrics/flow.py:218`<br>`quant_hedge_ai/agents/intelligence/sweep_detector.py:89` | TEST_ONLY, ACTIVE |
| `SweepDetector` | `market_data/metrics/flow.py:230`<br>`quant_hedge_ai/agents/intelligence/sweep_detector.py:146` | TEST_ONLY, ACTIVE |
| `DecisionEngine` | `meta_learning/decision_engine.py:13`<br>`quant_hedge_ai/engine/decision_engine.py:33` | TEST_ONLY, TEST_ONLY |
| `MetaLearner` | `meta_learning/learner.py:11`<br>`tracker_system/meta_learner.py:43` | TEST_ONLY, ACTIVE |

## 7. Répartition par package racine

| Package | ACTIVE | ORPHAN | TOOL | TEST_ONLY | TEST | TOTAL |
|---|---:|---:|---:|---:|---:|---:|
| `tests` | 0 | 0 | 0 | 0 | 249 | 249 |
| `quant_hedge_ai` | 62 | 68 | 9 | 38 | 29 | 206 |
| `scripts` | 3 | 13 | 43 | 7 | 10 | 76 |
| `tracker_system` | 25 | 23 | 0 | 16 | 0 | 64 |
| `src` | 0 | 17 | 2 | 44 | 0 | 63 |
| `infra` | 4 | 21 | 7 | 5 | 2 | 39 |
| `supervision` | 7 | 4 | 1 | 13 | 10 | 35 |
| `system` | 9 | 5 | 0 | 14 | 0 | 28 |
| `core` | 7 | 9 | 3 | 8 | 0 | 27 |
| `visualization` | 0 | 12 | 0 | 13 | 0 | 25 |
| `dip` | 1 | 6 | 0 | 16 | 0 | 23 |
| `tools` | 4 | 0 | 5 | 12 | 0 | 21 |
| `certification` | 0 | 0 | 2 | 8 | 9 | 19 |
| `observability` | 15 | 3 | 0 | 0 | 0 | 18 |
| `pieuvre` | 0 | 4 | 0 | 13 | 0 | 17 |
| `capital_deployment` | 6 | 0 | 0 | 3 | 6 | 15 |
| `observation` | 0 | 1 | 0 | 12 | 0 | 13 |
| `cold_start` | 0 | 0 | 0 | 10 | 2 | 12 |
| `signal` | 0 | 10 | 0 | 2 | 0 | 12 |
| `governance` | 1 | 10 | 0 | 0 | 0 | 11 |
| `market_data` | 0 | 7 | 0 | 4 | 0 | 11 |
| `crypto` | 2 | 1 | 0 | 5 | 2 | 10 |
| `execution_simulator` | 7 | 1 | 0 | 1 | 0 | 9 |
| `paper_trading` | 3 | 0 | 2 | 4 | 0 | 9 |
| `project_os` | 0 | 1 | 7 | 0 | 1 | 9 |
| `runtime` | 0 | 1 | 0 | 5 | 3 | 9 |
| `S2` | 0 | 1 | 5 | 0 | 0 | 6 |
| `exchange_constraints` | 5 | 1 | 0 | 0 | 0 | 6 |
| `S3` | 0 | 0 | 5 | 0 | 0 | 5 |
| `audit` | 0 | 2 | 0 | 3 | 0 | 5 |
| `meta_learning` | 0 | 1 | 0 | 4 | 0 | 5 |
| `monitoring` | 0 | 2 | 0 | 3 | 0 | 5 |
| `walk_forward` | 0 | 1 | 0 | 4 | 0 | 5 |
| `analysis` | 0 | 1 | 0 | 3 | 0 | 4 |
| `config` | 2 | 1 | 0 | 1 | 0 | 4 |
| `event_bus` | 2 | 1 | 0 | 1 | 0 | 4 |
| `lm_studio` | 3 | 0 | 1 | 0 | 0 | 4 |
| `metrics` | 0 | 2 | 0 | 2 | 0 | 4 |
| `risk` | 1 | 2 | 0 | 1 | 0 | 4 |
| `sdos_terminal` | 0 | 3 | 1 | 0 | 0 | 4 |
| `errors` | 1 | 2 | 0 | 0 | 0 | 3 |
| `health` | 0 | 3 | 0 | 0 | 0 | 3 |
| `terminal_core` | 0 | 3 | 0 | 0 | 0 | 3 |
| `dashboard` | 0 | 1 | 0 | 1 | 0 | 2 |
| `monitor` | 0 | 1 | 0 | 1 | 0 | 2 |
| `reality_checks` | 0 | 1 | 0 | 1 | 0 | 2 |
| `ai_autonomous_loop` | 0 | 1 | 0 | 0 | 0 | 1 |
| `conftest` | 0 | 0 | 0 | 0 | 1 | 1 |
| `docs` | 0 | 1 | 0 | 0 | 0 | 1 |
| `reports` | 0 | 0 | 1 | 0 | 0 | 1 |
| `watchdog_vps` | 0 | 0 | 0 | 1 | 0 | 1 |
