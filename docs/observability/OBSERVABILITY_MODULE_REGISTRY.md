# Observability Module Registry

Mission O-01 · This is the human-readable counterpart of
`observability/operator/canonical_registry.DEFAULT_MODULE_REGISTRY`
(47 modules across 11 domains, generated from the same `ModuleDescriptor`
entries that ship in `observability/operator/domains/*.py` — no
transcription drift, this table is produced from the code). Every entry
records the forensic reuse decision behind it (mission §26): before any
new provider is added, its existing canonical/duplicate/legacy status is
documented here first.

## Status vocabulary

| Status | Meaning |
|---|---|
| `CANONICAL_EXISTING` | Correct, actively consumed, pre-existing source of truth for this concern. |
| `CANONICAL_NEW` | New contract introduced by O-01 itself (e.g. the freshness vocabulary, the OperatorSummary composer). |
| `PARTIAL` | Real and correctly scoped, but incomplete relative to the operator need (a field missing, a consumer not wired). |
| `PRESENTATION_ONLY` | Formats/exposes data with no independent computation of its own — or, when defective, computes something it should not (flagged explicitly). |
| `LEGACY` | Superseded, retained for audit/history, must not be treated as canonical. |
| `DUPLICATED` | A second, independently-maintained implementation of a concern that already has a canonical owner. |
| `UNUSED` | Implemented, often correctly, but zero live call sites found. |
| `FUTURE_PROVIDER` | No implementation exists yet; the gap is documented so it isn't silently invented. |
| `BLOCKED` | Exists and is even decision-active, but lives in a file O-01 is constitutionally forbidden to modify (S-02B.1 protected surface) — read-only forensic entry. |

## Domains

### A — SYSTEM HEALTH (Santé système)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `system_health.module_registry` | Registre central de statut par module (HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN) | `system/module_registry.py` | **CANONICAL_EXISTING** | system/kernel.py, core/advisor_loop.py, health/health_registry.py | module heartbeat/registration calls | — | Aucun contrat unifié BOOT vs SCIENTIFIC health; distinction reste implicite dans le code appelant. |
| `system_health.health_score` | Score composite de santé scientifique | `observability/health_score.py` | **CANONICAL_EXISTING** | core/advisor_loop.py:6749-6750, system/burn_in.py | MetricsSnapshot cadence | observability.metrics_collector.MetricsSnapshot | Aucune |
| `system_health.watchdog_root` | Watchdog de survie processus (boot health) | `watchdog_vps.py` | **CANONICAL_EXISTING** | scripts/systemd/crypto-watchdog.service | watchdog poll loop | — | Duplication connue: infra/monitoring/watchdog_vps.py existe (implémentation différente, non déployée par systemd) et doit être traitée comme LEGACY. |
| `system_health.watchdog_infra_duplicate` | Second watchdog non déployé (implémentation concurrente) | `infra/monitoring/watchdog_vps.py` | **DUPLICATED** | tests/test_stability_accelerated.py | n/a — non déployé | — | Non référencé par aucun fichier systemd; seul le watchdog racine est déployé. Ne pas traiter comme source canonique. |
| `system_health.health_registry_unused` | Runner générique de health checks par module | `health/health_registry.py` | **UNUSED** | — | n/a | — | Bien conçu mais zéro point d'import en dehors du fichier lui-même; jamais câblé au kernel ou à advisor_loop. Candidat à réactivation plutôt qu'à reconstruction. |
| `system_health.recovery_manager_unused` | Stratégies de recovery automatique sur changement de statut module | `health/recovery_manager.py` | **UNUSED** | — | n/a | system.module_registry | S'enregistre sur module_registry.on_status_change() à l'import, mais n'est lui-même jamais importé ailleurs — l'enregistrement ne s'exécute donc jamais en pratique. |
| `system_health.system_snapshot_bus_dead` | Bus d'événements pour SystemSnapshot | `observability/system_snapshot_event_bus.py` | **PARTIAL** | — | publish() appelé à chaque cycle notify | observability.system_snapshot | publish() est appelé (core/advisor_loop.py:7030,7613) mais aucun .subscribe() externe n'existe dans le dépôt — publication sans consommateur. |
| `system_health.daily_analyzer_snapshot_collision` | Second SystemSnapshot (vocabulaire GREEN/YELLOW/RED) sans lien avec le runtime live | `infra/monitoring/daily_analyzer.py` | **LEGACY** | core/bootstrap_integration.py, scripts/final_validation.py | n/a | — | Collision de nom avec observability.system_snapshot.SystemSnapshot (le seul canonique pour le runtime live); non câblé à advisor_loop.py ni à un service systemd. |

### B — MARKET STATE (État du marché)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `market_state.observation_pulse` | Collecteur de pouls marché découplé (spot+swap tickers) | `observation/market_observer.py` | **CANONICAL_EXISTING** | core/topk_scheduler.py | crypto-market-observer.timer (15 min) | — | Aucune — module correctement isolé (ADR-0016), zéro import moteur. |
| `market_state.regime_classifier` | Détection et lissage du régime de marché | `quant_hedge_ai/agents/intelligence/market_regime_classifier.py` | **PARTIAL** | core/advisor_loop.py, GlobalRiskGate, MetaStrategyEngine, RegretEngine | advisor loop cycle | — | confidence/entropy calculés mais non propagés à SystemSnapshot.market — seule la chaîne de régime brute atteint l'opérateur. |
| `market_state.exchange_monitor` | Connectivité/latence exchange (partagé avec system_health) | `supervision/exchange_monitor.py` | **CANONICAL_EXISTING** | core/advisor_loop.py | background ping thread | — | Aucune |

### C — DECISION PIPELINE (Pipeline décisionnel)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `decision_pipeline.decision_observation` | Contrat unifié de télémétrie de décision (ADR-0007) | `observability/decision_observation.py` | **CANONICAL_EXISTING** | DecisionEventBus subscribers: RejectionStore, decision_explainer, RegretScheduler | publication par cycle via DecisionEventBus | core.advisor_loop.analyze_symbol (producer of AnalysisResult) | Coexiste avec le pipeline dict legacy qui pilote encore réellement l'exécution (core/advisor_loop.py:1488 commentaire). |
| `decision_pipeline.decision_packet` | Machine à états scellée (hash-chain) pour le cycle de vie d'une décision | `core/decision_packet.py` | **PARTIAL** | governance/decision_trace.py, observability/decision_observation.py | transitions en temps réel | — | Piste candidate/shadow — n'est pas encore le pilote réel de l'exécution; taux de désaccord avec le pipeline legacy suivi mais non résolu. |
| `decision_pipeline.legacy_dict_pipeline` | Pipeline dict historique (blockers/trade_allowed) — pilote réel de l'exécution | `core/advisor_loop.py::analyze_symbol()` | **CANONICAL_EXISTING** | execution path in core/advisor_loop.py | per cycle | — | Pas de compteurs de candidats dédiés pour UNIVERSE/FEATURES; FILTERS et SIGNALS sont fusionnés dans gate/meta/no-trade plutôt que d'être des étapes nommées séparées. |
| `decision_pipeline.dip_parallel_stack` | Plateforme d'observabilité décisionnelle parallèle (graph causal, timeline, explainability) | `dip/core/observer.py, dip/modules/*` | **PARTIAL** | tools/instrumentation_validator.py, tools/live_observer_validator.py | n/a — non câblé au pipeline live | — | Stack complète et autonome, mais zéro import depuis core/advisor_loop.py ou core/advisor_runtime_adapters.py — ne pas confondre avec observability/*. |

### D — ATTRITION / REJECTIONS (Attrition / Refus)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `attrition.rejection_store` | Journal append-only des refus de candidats actionnables | `observability/rejection_store.py` | **CANONICAL_EXISTING** | visualization/decision_trace_service.py, tools/decision_trace.py, visualization/api/decision_api.py | daily JSONL rotation, fsync par écriture | observability.decision_event_bus | Ne persiste que les signaux actionnables refusés (trade_allowed=False, side actionnable) — HOLD exclu; tout dénominateur doit préciser ce périmètre. |
| `attrition.decision_trace_service` | Agrégation en lecture seule des refus (by_layer, by_regime, by_personality) | `visualization/decision_trace_service.py` | **CANONICAL_EXISTING** | tools/decision_trace.py, visualization/api/decision_api.py | RejectionStore JSONL | observability.rejection_store | Aucune écriture — présentation pure sur données canoniques. |
| `attrition.activity_tracker` | Ratio exécution/refus au niveau cycle + diagnostic de stagnation | `quant_hedge_ai/agents/intelligence/activity_tracker.py` | **CANONICAL_EXISTING** | chief_officer.py, system_intel_reporter.py, Telegram TRADING_STALLED alert | per advisor loop cycle | — | Alimenté par une chaîne 'blockers' séparée du pipeline legacy, pas directement dérivée de RejectionStore — deux comptages parallèles à réconcilier. |
| `attrition.no_trade_layer_stats_unused` | Compteur checked/rejected dédié à la couche no-trade | `quant_hedge_ai/agents/intelligence/no_trade_layer.py` | **UNUSED** | — | n/a | — | Calcul correct et non ambigu (rejection_rate) mais .stats() n'a aucun point d'appel dans le dépôt. |
| `attrition.gate_rejections_csv` | Second compteur indépendant, basé fichier, de chaque vérification du risk gate (pass et fail) | `quant_hedge_ai/agents/risk/global_risk_gate.py::_gate_csv_log()` | **DUPLICATED** | databases/gate_rejections.csv (offline analysis) | per gate check | — | Existe en parallèle de RejectionStore/metrics_bus decision_packet.rejected_by.* — trois comptages du même événement de gate à réconcilier avant de choisir une source canonique unique. |

### E — PORTFOLIO STATE (État du portefeuille)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `portfolio_state.wallet_sync` | Source unique de capital/équité paper (remplace 4 constantes historiquement divergentes) | `infra/wallet_sync.py` | **CANONICAL_EXISTING** | quant_hedge_ai/agents/execution/execution_engine.py::fetch_available_capital() | ledger read at call time | databases/paper_trades.jsonl | Aucune pour le capital lui-même. |
| `portfolio_state.mexc_simulator` | Livre de positions paper réel (prix de marché réels, remplissages simulés) | `paper_trading/mexc_simulator.py` | **CANONICAL_EXISTING** | paper_trading/paper_portfolio_view.py, PortfolioBrain via l'adaptateur | in-process, per cycle | — | Coexiste avec un second store de positions (pos_manager) alimentant PortfolioBrain.portfolio_health() de façon divergente — voir portfolio_state.portfolio_brain_duplicated ci-dessous. |
| `portfolio_state.portfolio_status_builder` | Vue portefeuille honnête, construite uniquement à partir de paper_portfolio_view | `paper_trading/portfolio_status.py::build_portfolio_status()` | **CANONICAL_EXISTING** | — | paper_portfolio_view snapshot | paper_trading.paper_portfolio_view | Aucune — conçu spécifiquement pour éviter la mésattribution constatée dans meta_engine.current_personality(). |
| `portfolio_state.portfolio_brain_duplicated` | Calcul d'exposition/free-capital à partir d'un second store de positions | `quant_hedge_ai/agents/risk/portfolio_brain.py::portfolio_health()` | **DUPLICATED** | core/advisor_loop.py:6785-6787, system/integrity_snapshot.py | pos_manager.get_open() snapshot | — | pos_manager diverge de MexcSimulator (souvent vide alors que des positions réelles-paper existent) — free_capital/exposure_pct hérités de ce calcul sont potentiellement incorrects tant que non réconciliés. |
| `portfolio_state.real_accounts_observer` | Observation lecture-seule des comptes exchange réels, isolée du sizing | `observability/real_accounts.py` | **CANONICAL_EXISTING** | core/advisor_loop.py (bloc texte séparé, jamais sommé) | poll per notify cycle | — | Aucune — garde-fou de séparation à préserver explicitement dans toute nouvelle présentation. |
| `portfolio_state.portfolio_api_static` | Endpoint REST retournant un snapshot portefeuille | `visualization/api/portfolio_api.py::load_portfolio_snapshot()` | **PRESENTATION_ONLY** | dashboard REST consumer (non confirmé) | n/a | — | 8 des 10 champs retournés sont codés en dur à 0.0; total_pnl_usd substitue silencieusement le PnL ouvert au PnL total. Ne pas traiter comme source canonique tant que non corrigé. |
| `portfolio_state.virtual_portfolio_legacy` | Ancien livre de positions simulées | `paper_trading/virtual_portfolio.py` | **LEGACY** | tests only | n/a | — | Zéro point d'appel en production — superseded par MexcSimulator, jamais supprimé. |

### F — EXECUTION STATE (État d'exécution)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `execution_state.execution_engine` | Point d'entrée gate/télémétrie pour toute tentative d'ordre | `quant_hedge_ai/agents/execution/execution_engine.py` | **CANONICAL_EXISTING** | core/advisor_loop.py | per order attempt | infra.wallet_sync | PAPER_TRADING_ENABLED/LIVE_TRADING_CONFIRMED lus via os.getenv() dispersés plutôt que centralisés dans config/feature_flags.py (fichier protégé, hors périmètre O-01). |
| `execution_state.trade_logger` | Journal SQLite de chaque tentative d'ordre (acceptée ou rejetée) | `quant_hedge_ai/agents/execution/trade_logger.py` | **CANONICAL_EXISTING** | execution_engine.create_order() | write per order attempt | — | Aucune |
| `execution_state.latency_monitor` | Latence de remplissage, timeouts, désynchronisation WS | `quant_hedge_ai/agents/execution/latency_monitor.py` | **PARTIAL** | — | per fill/reject/timeout event | — | Câblage vers les points d'appel live non entièrement confirmé dans cette passe forensique — à vérifier avant intégration. |
| `execution_state.execution_simulator` | Piste d'audit de remplissage structurée pour la couche de simulation (slippage, spread, latence, frais) | `execution_simulator/models.py + execution_simulator/simulator.py` | **CANONICAL_EXISTING** | paper_trading/engine.py::BurninSimulationEngine (offline P5 uniquement), execution_simulator/fill_error_metric.py | per simulated fill | — | Scopé au burn-in offline, pas à l'exécution live. |
| `execution_state.paper_trading_engine_duplicate` | Second moteur de paper trading, point d'entrée différent | `quant_hedge_ai/agents/execution/paper_trading_engine.py` | **DUPLICATED** | quant_hedge_ai/main_system.py, quant_hedge_ai/main_v91.py | n/a | — | Parallèle à MexcSimulator (le moteur réellement utilisé par advisor_loop.py) via un entrypoint différent (main_system.py/main_v91.py) — nécessite une décision d'autorité hors périmètre O-01. |
| `execution_state.unified_execution_health_gap` | Vue agrégée 'ordres tentés/acceptés/rejetés sur N derniers cycles' | `FUTURE_PROVIDER — aucun composant ne joint TradeLogger + ExecutionLatencyMonitor aujourd'hui` | **FUTURE_PROVIDER** | — | n/a | execution_state.trade_logger, execution_state.latency_monitor | Écart identifié par la passe forensique — pas de snapshot unique honnête équivalent à paper_trading/portfolio_status.py côté portefeuille. |

### G — DATA FRESHNESS (Fraîcheur des données)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `data_freshness.regret_repository_freshness` | Horloge de fraîcheur canonique pour le pipeline Regret v2 | `tools/regret_repository.py` | **CANONICAL_EXISTING** | tools/cri_calculator.py | self | — | Non exposé via l'API HTTP burnin_api.py aujourd'hui (BurnInSnapshot omet freshness/fresh/validity) — gap identifié par la passe forensique. |
| `data_freshness.vocabulary_gap` | Vocabulaire général FRESH/DEGRADED/STALE/UNKNOWN | `observability/operator/contracts.py::FreshnessStatus (nouveau, O-01)` | **CANONICAL_NEW** | all observability/operator/domains/* | n/a — enum | — | Premier vocabulaire unifié du dépôt; les précédents (DATA_STALE, REJECTED_STALE, horizon canonique) restent des concepts scopés à leur domaine et ne sont pas rétroactivement migrés par O-01. |

### H — REGRET STATE (État Regret)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `regret_state.regret_repository` | Couche de lecture canonique du dataset Regret v2 (MC-001/ADR-0018) | `tools/regret_repository.py` | **CANONICAL_EXISTING** | tools/cri_calculator.py, visualization/api/regret_api.py, visualization/api/burnin_api.py | self (last_canonical_evaluated_ts) | databases/regret/regret_horizons_*.jsonl | Aucune pour la sémantique elle-même. |
| `regret_state.regret_scheduler` | Producteur des évidences HORIZON_EVIDENCE | `observability/regret_scheduler.py` | **CANONICAL_EXISTING** | tools/regret_repository.py | self | — | layer_performance()/stats() implémentés correctement mais aucun point d'appel externe trouvé (UNUSED du point de vue observabilité, bien que le producteur HORIZON_EVIDENCE lui-même soit actif). |
| `regret_state.burnin_api_gap` | Exposition HTTP de l'état Regret à l'opérateur | `visualization/api/burnin_api.py::BurnInSnapshot` | **PARTIAL** | sdos_terminal/api/app.py GET /api/burnin | tools.regret_repository (non propagé) | regret_state.regret_repository | N'inclut pas freshness/fresh/last_canonical_evaluated_utc/canonical_horizon/validity/pending_candidate_count — ces champs existent seulement côté CLI (tools/cri_calculator.py), pas dans l'API HTTP consommée par le futur O-02. |
| `regret_state.v1_legacy` | Ancien moteur Regret (pré-v2) | `quant_hedge_ai/agents/intelligence/regret_engine.py` | **LEGACY** | visualization/api/burnin_api.py (fallback explicite, jamais silencieux) | n/a | — | Retiré de la certification depuis 2026-07-10 (ADR-0018); conservé pour l'audit historique uniquement. |

### I — ADAPTIVE LEARNING STATE (Apprentissage adaptatif)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `adaptive_learning.mistake_memory` | Blocage de trade basé sur des règles apprises d'erreurs passées | `quant_hedge_ai/agents/intelligence/mistake_memory.py (fichier protégé S-02B.1, lecture seule)` | **BLOCKED** | core/advisor_loop.py:1642-1670 (_cb_mistake_memory circuit breaker) | databases mistake_memory.jsonl ts field | — | Décisionnel-actif dès aujourd'hui (bloque des trades), sans flag de gouvernance explicite type FEATURE_AUTO_CALIBRATION; stats()/explain_last_mistakes() sont la seule surface observable actuelle, pas de is_learning_active/recommendation_count/applied_count. |
| `adaptive_learning.strategy_memory` | Sélection/blacklist de stratégies par régime | `quant_hedge_ai/ai_evolution/strategy_memory.py (fichier protégé S-02B.1, lecture seule)` | **BLOCKED** | core/advisor_loop.py:4157 (load_by_regime, décisionnel — classe/sélectionne les stratégies candidates) | databases/ai_evolution/strategy_memory.json mtime | — | Aucune méthode stats()/summary(); un observateur externe doit lire le JSON brut. Décisionnel-actif (mute usage_count et influence la sélection). |
| `adaptive_learning.meta_learner` | Sélection de paramètres de sortie (exit_type/tp/sl) par contexte appris | `tracker_system/meta_learner.py + tracker_system/meta_memory.py (fichiers protégés S-02B.1, lecture seule)` | **BLOCKED** | core/advisor_loop.py:1404-1418 (find_best, décisionnel), :4690-4729 (learn, tous les 5 trades) | dernière entrée meta_memory | — | find_best() est appliqué directement comme paramètre de sortie live — aucune séparation recommandation/application. summary()/len() sont la seule surface observable. |
| `adaptive_learning.regret_decision_feedback_precedent` | Seul précédent de gouvernance double opt-in pour un chemin d'apprentissage adaptatif | `config/feature_flags.py::FEATURE_AUTO_CALIBRATION, FEATURE_REGRET_DECISION_FEEDBACK (fichier protégé, lecture seule)` | **CANONICAL_EXISTING** | RegretEngine.get_threshold_delta() -> GlobalRiskGate.apply_regret_delta() | process config | — | Scope d'ADR-0007 confirmé restreint à ce chemin unique — ne couvre pas mistake_memory/strategy_memory/meta_learner malgré leur nature également adaptative. |

### J — DISK / I-O

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `disk_io.da01_attribution` | Pack d'attribution disque en lecture seule, déclenché manuellement | `scripts/claude-disk-attribution.py` | **CANONICAL_EXISTING** | audit_results/da01-first-attribution.json, .github/workflows/vps-audit.yml | self, on workflow_dispatch | — | On-demand uniquement, jamais planifié — pas de continuité entre deux audits. |
| `disk_io.disk_growth_pack` | Baseline immuable pour dériver la croissance de databases/ et logs/ entre deux snapshots | `scripts/claude-disk-growth.py` | **CANONICAL_EXISTING** | .github/workflows/vps-audit.yml | self, on workflow_dispatch | — | growth_computed toujours false au niveau du pack — la croissance doit être dérivée en diffant deux enveloppes hors du pack lui-même. |
| `disk_io.system_snapshot_gap` | Champ d'utilisation disque dans le snapshot opérateur continu | `FUTURE_PROVIDER — observability.system_snapshot.SystemSnapshot / observability.metrics_collector.MetricsSnapshot ne portent aucun champ disque` | **FUTURE_PROVIDER** | — | n/a | disk_io.da01_attribution | Écart identifié par la passe forensique: aucune structure opérateur continue ne porte de champ disque; seul market_observer.free_disk_gb() vérifie l'espace, en garde privée non rapportée. |

### K — OPERATOR SUMMARY (Synthèse opérateur)

| module_id | purpose | canonical_source | status | consumers | freshness_source | dependencies | known_debt |
|---|---|---|---|---|---|---|---|
| `operator_summary.composer` | Composition pure des 10 domaines en une synthèse opérateur, sans recalcul scientifique indépendant | `observability/operator/domains/operator_summary.py` | **CANONICAL_NEW** | future Telegram/dashboard/API presentation adapters (O-02+) | min(freshness des snapshots composés) | les 10 autres domaines observability.operator | Aucun score opaque — chaque champ reste traçable à un domaine nommé et à son propre status/freshness. |
