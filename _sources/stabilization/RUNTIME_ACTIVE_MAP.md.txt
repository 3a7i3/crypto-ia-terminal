# RUNTIME ACTIVE MAP — Phase 0.5
> Généré : 2026-05-28 16:41 | Méthode : import réel (dry-run)
> Env : PAPER_TRADING=true, DRY_RUN=true, mocks exchange

## Résumé
| Catégorie | Importables | Total | Taux |
|-----------|------------|-------|------|
| Production | 45 | 45 | 100% |
| Optionnel | 8 | 8 | 100% |

## Interprétation
Un module FAIL signifie qu'il ne peut pas être importé dans le process courant.
Causes possibles : connexion exchange requise, dépendance absente, SyntaxError.


### Modules Production — 45/45 importables

| Module | Status | Dépendances chargées |
|--------|--------|---------------------|
| `observability.json_logger` | OK | +2 modules |
| `observability.heartbeat_system` | OK | +5 modules |
| `observability.metrics_bus` | OK | +0 modules |
| `errors.error_bus` | OK | +2 modules |
| `core.decision_packet` | OK | +2 modules |
| `risk_limits` | OK | +1 modules |
| `exchange_constraints.binance_rules` | OK | +6 modules |
| `exchange_constraints.order_validator` | OK | +0 modules |
| `exchange_constraints.rate_limiter` | OK | +0 modules |
| `execution_simulator.config` | OK | +8 modules |
| `execution_simulator.models` | OK | +0 modules |
| `paper_trading.recorder` | OK | +4 modules |
| `supervision.circuit_breaker_robust` | OK | +4 modules |
| `system.state_machine` | OK | +1 modules |
| `system.module_registry` | OK | +0 modules |
| `system.safety_auditor` | OK | +0 modules |
| `system.position_reconciler` | OK | +1 modules |
| `capital_deployment.capital_throttle` | OK | +2 modules |
| `capital_deployment.emergency_stop_manager` | OK | +1 modules |
| `cold_start.cold_start_manager` | OK | +8 modules |
| `quant_hedge_ai.agents.intelligence.regime_detector` | OK | +5 modules |
| `quant_hedge_ai.agents.intelligence.feature_engineer` | OK | +0 modules |
| `quant_hedge_ai.agents.intelligence.conviction_engine` | OK | +1 modules |
| `quant_hedge_ai.agents.intelligence.no_trade_layer` | OK | +1 modules |
| `quant_hedge_ai.agents.intelligence.self_awareness_engine` | OK | +1 modules |
| `quant_hedge_ai.agents.intelligence.meta_strategy_engine` | OK | +1 modules |
| `quant_hedge_ai.agents.intelligence.market_regime_classifier` | OK | +1 modules |
| `quant_hedge_ai.agents.intelligence.black_box` | OK | +1 modules |
| `quant_hedge_ai.agents.intelligence.chief_officer` | OK | +1 modules |
| `quant_hedge_ai.agents.intelligence.mistake_memory` | OK | +1 modules |
| `quant_hedge_ai.agents.intelligence.threat_radar` | OK | +1 modules |
| `quant_hedge_ai.agents.risk.global_risk_gate` | OK | +2 modules |
| `quant_hedge_ai.agents.risk.portfolio_brain` | OK | +1 modules |
| `quant_hedge_ai.agents.risk.capital_allocation_engine` | OK | +1 modules |
| `quant_hedge_ai.agents.risk.executive_override` | OK | +1 modules |
| `quant_hedge_ai.agents.execution.execution_engine` | OK | +5 modules |
| `quant_hedge_ai.agents.execution.position_manager` | OK | +1 modules |
| `quant_hedge_ai.agents.execution.live_signal_engine` | OK | +1 modules |
| `quant_hedge_ai.agents.market.market_scanner` | OK | +4 modules |
| `quant_hedge_ai.agents.market.multi_timeframe_scanner` | OK | +1 modules |
| `supervision.self_healing_bot` | OK | +1 modules |
| `supervision.telegram_kill_switch` | OK | +1 modules |
| `supervision.exchange_monitor` | OK | +1 modules |
| `supervision.performance_watchdog` | OK | +1 modules |
| `tracker_system.core.trade_tracker` | OK | +25 modules |

### Modules Optionnels — 8/8 importables

| Module | Status | Dépendances chargées |
|--------|--------|---------------------|
| `quant_hedge_ai.agents.intelligence.v2.decision_arbitrator` | OK | +4 modules |
| `quant_hedge_ai.agents.execution.execution_v2` | OK | +4 modules |
| `quant_hedge_ai.ai_evolution.strategy_memory` | OK | +8 modules |
| `quant_hedge_ai.ai_evolution.strategy_ranker` | OK | +1 modules |
| `lm_studio.ai_router` | OK | +3 modules |
| `capital_deployment.command_center_bot` | OK | +1 modules |
| `scripts.telegram_alerts` | OK | +2 modules |
| `scripts.shadow_execution` | OK | +1 modules |

## Concordance Statique vs Runtime
| Métrique | Phase 0 (statique) | Phase 0.5 (runtime) |
|---------|-------------------|---------------------|
| Modules production analysés | 45 | 45 |
| Importables | — | 45 (100%) |
| Modules optionnels | 8 | 8 importables |