# ARCHITECTURE V2 — PHASE 0A : AS-IS (État des lieux)

> **Généré le 2026-06-07**
> **Objectif :** Cartographie exhaustive de l'existant avant toute migration.
> **Règle :** Aucun fichier n'est déplacé avant validation de ce document.

---

## 1. INVENTAIRE COMPLET DES MODULES (89 dossiers racine + sous-dossiers critiques)

Chaque module est documenté avec :
- **Responsabilité unique** (une phrase)
- **Domaine métier** (Market, Strategy, Execution, Portfolio, Risk, Governance, Intelligence, Simulation, Observability, Infrastructure, Learning, Platform)
- **Couche actuelle** (où il se situe dans le stack implicite)

---

### 1.1 — Noyau Système (Core OS)

| Module | Responsabilité | Domaine | Fichiers clés |
|--------|---------------|---------|---------------|
| `core/` | Machine d'état fondamentale, contrats, invariants, autorité, cycle de vie | **Platform** | `lifecycle.py`, `runtime_state_machine.py`, `invariants.py`, `contracts.py`, `authority.py`, `decision_packet.py`, `advisor_loop.py` |
| `system/` | Intégrité, kernel, burn-in, monte carlo, walk-forward, vérification invariants | **Platform** | `kernel.py`, `integrity_models.py`, `state_machine.py`, `monte_carlo.py`, `invariant_checker.py`, `startup_sequence.py`, `state_integrity.py` |
| `runtime/` | Coordinateur de runtime, contexte d'exécution, lifecycle manager, state bus | **Platform** | `runtime_coordinator.py`, `execution_context.py`, `lifecycle_manager.py`, `system_state_bus.py` |
| `event_bus/` | Bus d'événements distribué (bridge, bus, events) | **Platform** | `bridge.py`, `bus.py`, `events.py` |
| `terminal_core/` | Noyau terminal, logging alerts — contient un sous-dossier `quant/` dupliqué avec `core/quant/` | **Platform** | `quant/logging_alerts.py` |

**⚠️ Problèmes détectés :**
- **5 "cores"** : `core/`, `system/`, `runtime/`, `terminal_core/`, `quant_hedge_ai/` — 5 points d'entrée conceptuels
- `runtime/` (racine) vs `quant_hedge_ai/runtime/` vs `src/runtime/` — **3 runtimes**
- `terminal_core/quant/logging_alerts.py` est un **doublon de code** de `core/quant/logging_alerts.py`

---

### 1.2 — Governance & Safety

| Module | Responsabilité | Domaine | Fichiers clés |
|--------|---------------|---------|---------------|
| `governance/` | Contrôle souverain : contraintes AI, approbation, traçabilité, autorité | **Governance** | `decision_router.py`, `execution_approval.py`, `authority_state.py`, `trading_authority.py`, `risk_authorizer.py`, `ai_constraints.py`, `decision_trace.py` |
| `supervision/` | Watchdogs, auto-guérison, kill switches, escalade, recovery playbooks | **Governance** | `bot_doctor.py`, `kill_switch.py`, `killswitch_hardened.py`, `escalation_engine.py`, `healing_actions.py`, `self_healing_bot.py`, `ops_watchdog.py`, `exchange_monitor.py` |
| `audit/` | Ledger de décisions, traces, replay engine, trade audit | **Governance** | `decision_ledger.py`, `decision_trace.py`, `replay_engine.py`, `trade_audit.py` |
| `certification/` | Certifications (module peu fourni) | **Governance** | — |
| `reality_checks/` | Analyseur d'écart réalité vs simulation | **Governance** | `reality_gap_analyzer.py` |
| `risk/` | Circuit breaker, global risk gate, limites de risque | **Risk** | `circuit_breaker.py`, `global_risk_gate.py`, `risk_limits.py` |
| `src/risk/` | Kill switch, live gate, regime gate | **Risk** | `kill_switch.py`, `live_gate.py`, `regime_gate.py` |

**⚠️ Problèmes détectés :**
- **3 moteurs de risque** : `risk/` (racine), `src/risk/`, `quant_hedge_ai/agents/risk/`
- **2 bus d'événements** : `event_bus/` et `src/events/`
- `audit/` racine et `governance/` ont des fonctions d'audit qui se chevauchent (`decision_trace.py` existe dans les deux)
- `governance/` et `pieuvre/tentacles/audit_commits.py` — 3ème implémentation d'audit
- `supervision/` contient ses propres killswitches alors que `risk/` en a aussi — **doublon de responsabilité**

---

### 1.3 — Moteur Quant Principal

| Module | Responsabilité | Domaine | Fichiers clés |
|--------|---------------|---------|---------------|
| `quant_hedge_ai/` | **Hub principal** : agents, engine, strategy lab, evolution, market radar, features | **Multi-domaine** | `main_v91.py` |

#### 1.3.1 — Agents (quant_hedge_ai/agents/)

| Sous-module | Responsabilité | Domaine |
|-------------|---------------|---------|
| `execution/` | Exécution des ordres, live signal engine | **Execution** |
| `intelligence/` | Intelligence décisionnelle, regime detector | **Intelligence** |
| `market/` | Analyse de marché | **Market** |
| `monitoring/` | Supervision agents | **Observability** |
| `onchain/` | Données on-chain | **Market** |
| `portfolio/` | Gestion de portefeuille | **Portfolio** |
| `quant/` | Calculs quantitatifs | **Strategy** |
| `research/` | Recherche & exploration | **Strategy** |
| `risk/` | Gestion du risque (3ème moteur de risque) | **Risk** |
| `strategy/` | Stratégies de trading | **Strategy** |
| `whales/` | Tracking de baleines | **Market** |

#### 1.3.2 — Autres sous-modules

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `engine/decision_engine.py` | Moteur de décision central | **Intelligence** |
| `strategy_lab/` | Laboratoire de stratégies : génération, backtest, ranking, évolution | **Strategy** |
| `strategy_factory/` | Factory pattern pour stratégies (doublon avec `strategy_factory/` racine) | **Strategy** |
| `ai_evolution/` | Évolution AI : mutation, ranking, mémoire, degradation monitor | **Strategy** |
| `market_radar/` | Radar de marché : anomalies, whales tracking, social scanning | **Market** |
| `liquidity_map/` | Cartographie de liquidité et flux | **Market** |
| `features/` | Feature engineering : matérialiseur, registre, validateur | **Strategy** |
| `data/` | Unification des données, modèle canonique | **Platform** |
| `databases/` | SQLite market_data, scoreboard JSON | **Platform** |
| `runtime/` | État runtime, chaos orchestrator, fault containment (2ème runtime) | **Platform** |
| `dashboard/live_snapshot.py` | Dashboard live snapshot (2ème dashboard) | **Application** |

**⚠️ Problèmes détectés :**
- `strategy_factory/` (racine) **ET** `quant_hedge_ai/strategy_factory/` — deux implémentations parallèles
- `quant_hedge_ai/runtime/` — 2ème des 3 runtimes
- `quant_hedge_ai/dashboard/` — 2ème dashboard (vs `dashboard/` racine et `frontend/`)

---

### 1.4 — Source Engine (src/)

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `src/agent/` | Implémentations de stratégies concrètes (breakout, momentum, rsi, sma) | **Strategy** |
| `src/analytics/` | Pipeline alpha, edge scoring, regime detection | **Intelligence** |
| `src/backtest/` | Moteur de backtest (data feed, engine, metrics, walk-forward) | **Simulation** |
| `src/domain/` | Modèles métier : Order, Position, Signal, TradeEvent | **Platform** |
| `src/engine/` | Routeur d'exécution, exchange virtuel | **Execution** |
| `src/events/` | Event bus (2ème bus d'événements) | **Platform** |
| `src/execution/` | ENL (Execution Network Layer ?) | **Execution** |
| `src/journal/` | Trade logger | **Observability** |
| `src/paper/` | Paper trading complet (gate, metrics, positions, reports) | **Simulation** |
| `src/portfolio/` | État du portefeuille | **Portfolio** |
| `src/risk/` | Kill switch, live gate, regime gate (2ème moteur de risque) | **Risk** |
| `src/runtime/` | Contexte d'exécution, simulateur (3ème runtime) | **Platform** |
| `src/storage/` | Repository des runs | **Platform** |
| `src/telegram/` | Bot Telegram (trade notifier, portfolio bot, sim bot) | **Application** |

---

### 1.5 — Simulation & Backtesting

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `execution_simulator/` | Simulateur de fill, slippage, spread, latence | **Simulation** |
| `paper_trading/` | Simulateur MEXC, ledger, portefeuille virtuel | **Simulation** |
| `src/backtest/` | Moteur de backtest | **Simulation** |
| `src/paper/` | Paper trading complet | **Simulation** |
| `strategy_factory/backtester.py` | Backtest dans strategy factory | **Simulation** |
| `quant_hedge_ai/strategy_lab/backtest_launcher.py` | Backtest dans strategy lab | **Simulation** |
| `quant_hedge_ai/strategy_factory/backtester.py` | Backtest dans strategy factory (doublon) | **Simulation** |

**⚠️ Problèmes détectés :**
- **4 backtesters** différents (strategy_factory ×2, strategy_lab, src/backtest)
- **2 paper trading** (`paper_trading/` et `src/paper/`)

---

### 1.6 — Strategy Factory & Evolution

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `strategy_factory/` (racine) | Alpha vault, backtest, evolution, genetic, reproduction | **Strategy** |
| `quant_hedge_ai/strategy_factory/` | Factory core, backtester, multi-TF backtester, generator | **Strategy** |
| `quant_hedge_ai/strategy_lab/` | Labo complet : templates, generation, evolution, ranking, backtest | **Strategy** |
| `quant_hedge_ai/ai_evolution/` | Évolution AI : mutation, ranking, mémoire, degradation | **Strategy** |
| `signal/evolution/` | Evolution core + memory (3ème mécanisme d'évolution) | **Strategy** |

**⚠️ Problèmes détectés :**
- **5 modules d'évolution/génération de stratégies** — responsabilité éclatée
- `strategy_factory/` racine vs `quant_hedge_ai/strategy_factory/` — **doublon de code et de responsabilité**

---

### 1.7 — Market Intelligence

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `market_data/` | Stream, replay engine, modèles | **Market** |
| `signal/` | Analyse, évolution, stratégies batch | **Market** |
| `quant_hedge_ai/market_radar/` | Anomalies, whales, social, token scanner | **Market** |
| `quant_hedge_ai/liquidity_map/` | Cartographie de liquidité, flux | **Market** |
| `quant_hedge_ai/agents/whales/` | Tracking de baleines | **Market** |
| `quant_hedge_ai/agents/onchain/` | Données on-chain | **Market** |
| `quant_hedge_ai/agents/market/` | Analyse de marché | **Market** |
| `exchange_constraints/` | Règles Binance, rate limiter, validateur d'ordres | **Market** |

**⚠️ Problèmes détectés :**
- 8 modules différents pour l'intelligence de marché, sans contexte bounded
- `whales` existe dans `market_radar/whale_tracker.py` ET `agents/whales/` — **doublon fonctionnel**

---

### 1.8 — Capital & Déploiement

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `capital_deployment/` | Throttle, phase gates, KPI tracker, portfolio bot | **Portfolio** |
| `cold_start/` | Warmup state machine, invariants, bypass detector | **Platform** |

---

### 1.9 — Intelligence & Apprentissage

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `meta_learning/` | Moteur de décision, learner, mémoire, similarité | **Intelligence** |
| `ai_autonomous_loop/` | Boucle autonome (init seulement — `__init__.py` vide) | **Intelligence** |
| `lm_studio/` | Intégration LM Studio (LLM local) : router, client | **Intelligence** |
| `quant_hedge_ai/ai_evolution/` | Évolution AI, mutation, mémoire | **Intelligence** |
| `quant_hedge_ai/agents/intelligence/` | Intelligence décisionnelle | **Intelligence** |
| `src/analytics/` | Pipeline alpha, edge scoring | **Intelligence** |

**⚠️ Problèmes détectés :**
- `meta_learning/` et `ai_evolution/` ont des fonctions de mémoire/learning qui se recoupent
- `ai_autonomous_loop/` est quasiment vide — **module zombie**

---

### 1.10 — Observability & Monitoring

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `observability/` | Health score, heartbeat, JSON logger, telemetry, alerting | **Observability** |
| `monitoring/` | Logger, metrics, pipeline monitor, profiler | **Observability** |
| `health/` | Health registry, recovery manager | **Observability** |
| `metrics/` | (dossier vide ou quasi-vide) | **Observability** |

**⚠️ Problèmes détectés :**
- 4 modules pour l'observabilité : `observability/`, `monitoring/`, `health/`, `metrics/` — **doublon de responsabilité**
- `supervision/` fait aussi de la surveillance (watchdogs, alerts) — frontière floue avec observability

---

### 1.11 — Infrastructure

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `infra/` | APIs, dashboards, monitoring, notifications, panels, visualization | **Infrastructure** |
| `infra/api/` | REST API server | **Infrastructure** |
| `infra/dashboards/` | Dashboard init | **Infrastructure** |
| `infra/monitoring/` | Daily analyzer, surveillance, watchdog VPS | **Infrastructure** |
| `infra/notifications/` | Email, Discord, Slack, Telegram notifiers | **Infrastructure** |
| `infra/panels/` | Panel CI, Selenium, HTTP tests | **Infrastructure** |
| `infra/visualization/` | Visualisation stratégie, timeline animation | **Infrastructure** |

---

### 1.12 — Frontend & UI

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `frontend/` | React + TypeScript + Tailwind + Vite | **Application** |
| `dashboard/` | Alert dashboard Python (1 seul fichier : `alert_dashboard.py`) | **Application** |
| `crypto_quant_v16/` | UI v16 (semble être un bridge legacy) | **Application** |
| `quant_hedge_ai/dashboard/` | Live snapshot dashboard | **Application** |

**⚠️ Problèmes détectés :**
- **4 dashboards** — `dashboard/`, `frontend/`, `crypto_quant_v16/`, `quant_hedge_ai/dashboard/`

---

### 1.13 — Self-Healing (Pièuvre)

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `pieuvre/` | Brain, tentacules auto-réparation, incidents | **Governance** |
| `pieuvre/tentacles/` | Audit, évolution, guérison, mémoire, sécurité | **Governance** |
| `pieuvre/dashboard/` | Tableau de bord pièuvre | **Application** |
| `pieuvre/incidents/` | Modèles + store d'incidents | **Governance** |

---

### 1.14 — Support & Data

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `data/` | CSVs Bitcoin historiques (19d, 27d, 30d) | **Platform** |
| `config/` | Configuration Telegram | **Platform** |
| `scripts/` | Scripts VPS, tests, validation, onboarding | **Platform** |
| `tools/` | Analyse de cycles, market ranker, runtime tracer | **Platform** |
| `tickets/` | Système de tickets | **Platform** |
| `checkpoints/` | Points de restauration | **Platform** |
| `cache/` | Cache système | **Platform** |

---

### 1.15 — Documentation & Meta

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `docs/` | Documentation Sphinx, architecture, invariants, runbooks | **Platform** |
| `project_os/` | Scanner de projet, debt map, maturité, roadmap | **Platform** |
| `obsidian_vault/` | Base Obsidian (PKM) | **Platform** |
| `anara_context/` | Contexte Anara : 54 descripteurs de modules JSON | **Platform** |

---

### 1.16 — Tests & Qualité

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `tests/` | Tests globaux | **Platform** |
| `S2/` | Gate logger, score distribution, calibration | **Platform** |
| `S3/` | Telegram alerts, log surveillance, shadow exec | **Platform** |

---

### 1.17 — Historique, Logs, Archives

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `logs/` | Logs d'exécution | **Platform** |
| `feedback_logs/` | 80+ feedbacks JSON + rapports HTML | **Platform** |
| `errors/` | Erreurs capturées | **Platform** |
| `reports/` | Rapports générés | **Platform** |
| `results/` | Résultats d'exécution | **Platform** |
| `sim_summaries/` | Résumés de simulation | **Platform** |
| `archives/` | Archives générales | **Platform** |
| `archive_results/` | Résultats archivés | **Platform** |
| `artifacts/` | Artéfacts de build | **Platform** |

---

### 1.18 — Déploiement & CI

| Module | Responsabilité | Domaine |
|--------|---------------|---------|
| `deploy/` | Scripts de déploiement | **Platform** |
| `k8s/` | Kubernetes | **Platform** |
| `install/` | Scripts d'installation | **Platform** |
| `Dockerfile` | Image Docker | **Platform** |
| `docker-compose.yml` | Stack Docker complète | **Platform** |

---

### 1.19 — Fichiers racine (~150)

Trop nombreux pour être listés individuellement. Catégories principales :
- **Documentation** : README.md, ROADMAP.md, QUICKSTART.md, STACK_INDEX.md, etc.
- **Rapports de phase** : ~20 fichiers `*_REPORT.md`, `*_SUMMARY.md`
- **Launchers** : ~100 fichiers `.bat` / `.ps1` / `.sh`
- **Configuration** : `.coveragerc`, `pytest.ini`, `setup.cfg`, `codecov.yml`
- **Requirements** : `requirements.txt`, `requirements-dev.txt`, `requirements-ci.txt`, `requirements-vps.txt`

---

## 2. CLASSIFICATION DES DOUBLONS (5 catégories)

### 2.1 — Doublons de code (même logique copiée)

| Instance | Fichiers |
|----------|----------|
| `terminal_core/quant/logging_alerts.py` ≡ `core/quant/logging_alerts.py` | Copie exacte |
| `strategy_factory/` (racine) ≡ `quant_hedge_ai/strategy_factory/` | Deux implémentations parallèles de factory |
| `audit/decision_trace.py` ≡ `governance/decision_trace.py` | Même nom, logique probablement proche |

### 2.2 — Doublons de responsabilité (deux modules font le même métier)

| Instance | Modules |
|----------|---------|
| **3 moteurs de risque** | `risk/`, `src/risk/`, `quant_hedge_ai/agents/risk/` |
| **3 runtimes** | `runtime/`, `quant_hedge_ai/runtime/`, `src/runtime/` |
| **2 bus d'événements** | `event_bus/`, `src/events/` |
| **4 dashboards** | `dashboard/`, `frontend/`, `crypto_quant_v16/`, `quant_hedge_ai/dashboard/` |
| **2 paper trading** | `paper_trading/`, `src/paper/` |
| **4 systèmes d'observabilité** | `observability/`, `monitoring/`, `health/`, `metrics/` |

### 2.3 — Doublons d'orchestration (deux coordinateurs différents)

| Instance | Modules |
|----------|---------|
| **5 "cores"** | `core/`, `system/`, `runtime/`, `terminal_core/`, `quant_hedge_ai/` |
| **5 mécanismes d'évolution de stratégies** | `strategy_factory/`, `quant_hedge_ai/strategy_factory/`, `quant_hedge_ai/strategy_lab/`, `quant_hedge_ai/ai_evolution/`, `signal/evolution/` |
| **2 coordinateurs décisionnels** | `core/advisor_loop.py` et `meta_learning/decision_engine.py` |

### 2.4 — Doublons de données (même état stocké à deux endroits)

| Instance | Description |
|----------|-------------|
| `ConvictionLevel` | Dupliqué : `conviction_engine.ConvictionLevel` vs `core.decision_packet.ConvictionLevel` |
| `MarketRegime` | Formats incompatibles : `AdvancedRegimeDetector` (strings) vs `MarketRegime` (enum) vs `risk_gate` (strings legacy) |
| États runtime | 3 implémentations du runtime stockent potentiellement le même état |

### 2.5 — Doublons de gouvernance (deux décisions possibles pour une même action)

| Instance | Description |
|----------|-------------|
| Kill switches | `supervision/kill_switch.py`, `supervision/killswitch_hardened.py`, `risk/circuit_breaker.py`, `src/risk/kill_switch.py` |
| Approval | `governance/execution_approval.py` vs `governance/decision_router.py` — deux chemins d'approbation |
| Audit | `audit/`, `governance/`, `pieuvre/tentacles/audit_commits.py` — 3 visions de l'audit |

---

## 3. GRAPHE DE DÉPENDANCES (Qui dépend de qui)

### 3.1 — Dépendances critiques (A ne peut pas vivre sans B)

```
advisor_loop.py
├── core/lifecycle.py (machine d'état)
├── core/decision_packet.py (contrats)
├── quant_hedge_ai/agents/execution/live_signal_engine.py (signaux)
├── quant_hedge_ai/risk/global_risk_gate.py (gouvernance)
├── governance/execution_approval.py (approbation)
├── capital_deployment/capital_throttle.py (sizing)
└── observability/telemetry.py (traçabilité)
```

### 3.2 — Dépendances conceptuelles

```
CORE (machine d'état, invariants)
  ├── SYSTEM (intégrité, kernel, startup)
  ├── GOVERNANCE (approbation, traçabilité)
  │     ├── RISK (gates, limites)
  │     └── SUPERVISION (watchdogs)
  ├── EVENT_BUS (communication)
  └── QUANT_HEDGE_AI (hub principal)
        ├── AGENTS ×11 (spécialistes)
        ├── STRATEGY_LAB (génération)
        ├── AI_EVOLUTION (ranking)
        ├── MARKET_RADAR (détection)
        └── RUNTIME (chaos, fault)
              └── SRC (backtest, paper, execution)
```

### 3.3 — Dépendances problématiques (circulaires ou ambiguës)

| Dépendance | Problème |
|------------|----------|
| `core/` → `quant_hedge_ai/` → `core/` | Circulaire via advisor_loop |
| `governance/` → `risk/` → `governance/` | Qui gouverne le risque ? |
| `supervision/` → `pieuvre/` → `supervision/` | Deux auto-guérisons |
| `src/` → `quant_hedge_ai/` → `src/` | Chevauchement backtest/paper/risk |

---

## 4. FLUX PRINCIPAUX

### 4.1 — Flux de trading (signal → exécution)

```
MarketScanner → LiveSignalEngine → DecisionPacket
  → ConvictionEngine → GlobalRiskGate → ExecutionApproval
  → CapitalThrottle → OrderSizer → ExecutionSimulator
  → Exchange → TradeTracker → Observability
```

### 4.2 — Flux de feedback (trade → apprentissage)

```
TradeTracker → Metrics → RegretEngine
  → AdaptiveThreshold → GlobalRiskGate
  → MetaLearning → StrategyAllocator
```

### 4.3 — Flux de gouvernance (décision → trace)

```
SignalGeneration → RiskEvaluation → ExecutionApproval
  → DecisionLedger → AuditTrace → ReplayEngine
```

### 4.4 — Flux de simulation (backtest → validation)

```
StrategyLab → Backtester → PaperTrading
  → RealityChecks → StrategyRanking → AI_Evolution
```

---

## 5. ÉVÉNEMENTS PRODUITS/CONSOMMÉS

### 5.1 — Événements définis (event_bus/events.py)

Types d'événements identifiés dans le système :
- `TradeEvent` — ouverture/fermeture de position
- `OrderEvent` — création/annulation d'ordre
- `SignalEvent` — signal généré par le moteur
- `RiskEvent` — déclenchement de gate/limite
- `GovernanceEvent` — approbation/rejet
- `HealthEvent` — heartbeat, dégradation
- `SystemEvent` — startup, shutdown, erreur

### 5.2 — Problème de fragmentation

`event_bus/events.py` et `src/events/event_bus.py` définissent des événements.
Rien ne garantit qu'ils utilisent les mêmes contrats.
Un module pourrait écouter le mauvais bus.

---

## 6. API PUBLIQUES PAR MODULE (principales)

| Module | API publique |
|--------|-------------|
| `core/` | `Lifecycle`, `DecisionPacket`, `RuntimeStateMachine`, `Contract`, `Invariant` |
| `system/` | `Kernel`, `IntegrityModels`, `StartupSequence`, `StateIntegrity` |
| `governance/` | `DecisionRouter`, `ExecutionApproval`, `TradingAuthority` |
| `risk/` | `GlobalRiskGate`, `CircuitBreaker`, `RiskLimits` |
| `event_bus/` | `Bridge`, `Bus`, `Events` |
| `quant_hedge_ai/` | `main_v91`, `LiveSignalEngine`, `DecisionEngine`, `StrategyLab`, `AIEvolution` |
| `src/` | `BacktestEngine`, `PaperTrading`, `ExchangeRouter`, `TelegramBot` |
| `observability/` | `Telemetry`, `HealthScore`, `Heartbeat`, `MetricsCollector` |
| `capital_deployment/` | `CapitalThrottle`, `PhaseGate`, `PortfolioBot` |
| `execution_simulator/` | `FillSimulator`, `SlippageModel`, `LatencyModel` |
| `paper_trading/` | `PaperEngine`, `Ledger`, `VirtualPortfolio` |

---

## 7. INDICATEURS DE MATURITÉ PAR MODULE

Échelle : /10 pour chaque critère.

| Module | Resp. Unique | Couplage | Testabilité | Documentation | Cohérence DDD | Dette technique | **Score** |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `core/` | 9 | 7 | 8 | 8 | 9 | 6 | **7.8** |
| `system/` | 7 | 6 | 6 | 6 | 7 | 6 | **6.3** |
| `governance/` | 9 | 7 | 7 | 8 | 9 | 5 | **7.5** |
| `risk/` (racine) | 8 | 5 | 7 | 6 | 7 | 5 | **6.3** |
| `src/risk/` | 7 | 4 | 5 | 4 | 5 | 7 | **5.3** |
| `event_bus/` | 9 | 8 | 7 | 6 | 9 | 4 | **7.2** |
| `src/events/` | 7 | 5 | 5 | 3 | 6 | 7 | **5.5** |
| `quant_hedge_ai/` | 5 | 4 | 6 | 6 | 5 | 5 | **5.2** |
| `src/` | 6 | 4 | 6 | 5 | 5 | 5 | **5.2** |
| `strategy_factory/` | 8 | 4 | 5 | 4 | 7 | 7 | **5.8** |
| `strategy_lab/` | 8 | 7 | 8 | 8 | 7 | 4 | **7.0** |
| `observability/` | 7 | 6 | 5 | 5 | 6 | 6 | **5.8** |
| `monitoring/` | 6 | 5 | 4 | 4 | 5 | 7 | **5.2** |
| `supervision/` | 6 | 4 | 5 | 5 | 5 | 6 | **5.2** |
| `market_data/` | 8 | 6 | 5 | 5 | 7 | 5 | **6.0** |
| `execution_simulator/` | 9 | 8 | 7 | 7 | 8 | 4 | **7.2** |
| `paper_trading/` | 8 | 7 | 6 | 6 | 7 | 5 | **6.5** |
| `capital_deployment/` | 8 | 7 | 7 | 7 | 8 | 4 | **6.8** |
| `meta_learning/` | 8 | 6 | 6 | 6 | 7 | 5 | **6.3** |
| `pieuvre/` | 7 | 5 | 5 | 5 | 6 | 5 | **5.5** |

> **Moyenne globale : 6.2/10** — confirme le diagnostic : vision bonne, exécution correcte, mais la cohérence des frontières est le point faible.

---

## 8. SYNTHÈSE DES PROBLÈMES ARCHITECTURAUX

| # | Problème | Impact | Priorité |
|---|----------|--------|----------|
| 1 | 5 "cores" — pas de point d'entrée unique | **Critique** — onboarding impossible | 🔴 P0 |
| 2 | 3 runtimes — état dupliqué | **Haut** — bugs silencieux | 🔴 P0 |
| 3 | 3 moteurs de risque | **Haut** — décisions contradictoires | 🔴 P0 |
| 4 | 2 bus d'événements | **Haut** — perte d'événements | 🟠 P1 |
| 5 | 2 strategy factories | **Haut** — deux sources de vérité | 🟠 P1 |
| 6 | 4 dashboards | **Moyen** — maintenance ×4 | 🟠 P1 |
| 7 | 4 systèmes d'observabilité | **Moyen** — métriques éclatées | 🟡 P2 |
| 8 | 5 mécanismes d'évolution | **Moyen** — logique dispersée | 🟡 P2 |
| 9 | 4 backtesters | **Moyen** — résultats divergents | 🟡 P2 |
| 10 | Kill switches multiples | **Haut** — quel kill switch tue vraiment ? | 🟠 P1 |
| 11 | 3 visions de l'audit | **Moyen** — traces incomplètes | 🟡 P2 |
| 12 | 8 modules market intelligence | **Moyen** — pas de bounded context | 🟡 P2 |
| 13 | 150+ fichiers racine | **Faible** — bruit visuel | 🟢 P3 |
| 14 | `ai_autonomous_loop/` vide | **Faible** — module zombie | 🟢 P3 |

---

## 9. PROCHAINE ÉTAPE

Ce document constitue le **cliché complet AS-IS** de la Phase 0A.

**→ Passer à la Phase 0B : Architecture TO-BE** (Bounded Contexts, couches, contrats, règles de dépendance).
