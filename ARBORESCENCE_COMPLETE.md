# 🌳 ARBORESCENCE COMPLÈTE — Crypto IA Quant Terminal

> **Graphe de géolocalisation des modules** — Chaque dossier = un nœud de valeur dans l'écosystème.
> Généré le 2026-06-07 | Mode : ACT

---

## 🧭 CARTE GLOBALE (Niveau 0 — Root)

```
crypto_ai_terminal/
│
├── 🔴 Noyau Système (Core OS)
│   ├── core/                    # Cerveau central : contrats, machine d'état, bootstrap
│   ├── system/                  # Intégrité, kernel, invariants, séquence de démarrage
│   ├── runtime/                 # (vide — redondance avec quant_hedge_ai/runtime ?)
│   ├── event_bus/               # Bus d'événements distribué (bridge, bus, events)
│   └── health/                  # Registre de santé + recovery manager
│
├── 🟠 Moteur Quant Principal (v9.1)
│   └── quant_hedge_ai/          # Le hub principal : agents, engine, strategy_lab, evolution
│       ├── agents/              # 🧠 Tous les agents spécialisés
│       │   ├── execution/       # Exécution des ordres, live signal
│       │   ├── intelligence/    # Intelligence décisionnelle
│       │   ├── market/          # Analyse de marché
│       │   ├── monitoring/      # Supervision
│       │   ├── onchain/         # Données on-chain
│       │   ├── portfolio/       # Gestion de portefeuille
│       │   ├── quant/           # Calculs quantitatifs
│       │   ├── research/        # Recherche & exploration
│       │   ├── risk/            # Gestion du risque
│       │   ├── strategy/        # Stratégies de trading
│       │   └── whales/          # Tracking de baleines
│       ├── engine/              # Moteur de décision
│       ├── strategy_lab/        # Labo de stratégies (génération, backtest, ranking)
│       ├── strategy_factory/    # Factory pattern pour stratégies
│       ├── ai_evolution/        # Évolution AI (mutation, ranking, mémoire)
│       ├── dashboard/           # Dashboard live snapshot
│       ├── liquidity_map/       # Cartographie de liquidité
│       ├── market_radar/        # Radar de marché (anomalies, whales, social)
│       ├── features/            # Feature engineering (matérialiseur, registre, validateur)
│       ├── data/                # Unification des données, modèle canonique
│       ├── databases/           # SQLite market_data, scoreboard JSON
│       ├── runtime/             # État runtime, chaos orchestrator, fault containment
│       └── tests/               # Tests unitaires
│
├── 🟡 Moteur Crypto Quant v16
│   └── crypto_quant_v16/        # UI uniquement (bridge vers dashboard v16 ?)
│
├── 🟢 Terminal Core
│   └── terminal_core/           # Noyau terminal, logging alerts
│
├── 🔵 Source Engine (src/)
│   ├── agent/                   # Implémentations de stratégies concrètes
│   │   ├── breakout_strategy.py
│   │   ├── momentum_strategy.py
│   │   ├── rsi_strategy.py / rsi_extreme_strategy.py
│   │   └── sma_strategy.py
│   ├── analytics/               # Pipeline alpha, edge scoring, regime detection
│   ├── backtest/                # Moteur de backtest (data feed, engine, metrics, walk-forward)
│   ├── domain/                  # Modèles métier : Order, Position, Signal, TradeEvent
│   ├── engine/                  # Routeur d'exécution, exchange virtuel
│   ├── events/                  # Event bus
│   ├── execution/               # ENL (Execution Network Layer ?)
│   ├── journal/                 # Trade logger
│   ├── paper/                   # Paper trading complet (gate, metrics, positions, reports)
│   ├── portfolio/               # État du portefeuille
│   ├── risk/                    # Kill switch, live gate, regime gate
│   ├── runtime/                 # Contexte d'exécution, simulateur
│   ├── storage/                 # Repository des runs
│   └── telegram/                # Bot Telegram (trade notifier, portfolio bot, sim bot)
│
├── 🟣 Governance & Safety
│   ├── governance/              # Contrôle souverain : contraintes AI, approbation, traçabilité
│   ├── supervision/             # Watchdogs, auto-guérison, kill switches, escalade
│   ├── reality_checks/          # Analyseur d'écart réalité vs simulation
│   ├── audit/                   # Ledger de décisions, traces, rejeu
│   └── risk/                    # Circuit breaker, global risk gate, limites
│
├── 🟤 Capital & Déploiement
│   ├── capital_deployment/      # Throttle, phase gates, KPI tracker, portfolio bot
│   │   ├── static/              # Assets statiques dashboard
│   │   └── tests/               # Tests unitaires capital
│   ├── paper_trading/           # Simulateur MEXC, ledger, portefeuille virtuel
│   └── cold_start/              # (vide ou non exploré)
│
├── ⚪ Infra & Déploiement
│   ├── infra/                   # APIs, dashboards, monitoring, notifications, panels
│   │   ├── api/                 # REST API server
│   │   ├── dashboards/          # Dashboard init
│   │   ├── monitoring/          # Daily analyzer, surveillance, watchdog VPS
│   │   ├── notifications/       # Email, Discord, Slack, Telegram notifiers
│   │   ├── panels/              # Panel CI, Selenium, HTTP tests
│   │   └── visualization/       # Visualisation stratégie, timeline animation
│   ├── k8s/                     # Kubernetes
│   ├── deploy/                  # Scripts de déploiement
│   └── docker-compose.yml       # Stack Docker complète
│
├── 🟠 Strategy Factory (legacy doublon ?)
│   └── strategy_factory/        # Alpha vault, backtest, evolution, genetic, reproduction
│       ⚠️ DOUBLON : voir quant_hedge_ai/strategy_factory/ et quant_hedge_ai/strategy_lab/
│
├── 🟡 Signal & Marché
│   ├── signal/                  # Analyse, évolution, stratégies batch
│   │   ├── analysis/            # AutoML tuning, clustering, sensitivity
│   │   ├── evolution/           # Evolution core + memory
│   │   └── strategies/          # Scripts batch de factory
│   ├── market_data/             # Stream, replay engine, modèles
│   ├── exchange_constraints/    # Règles Binance, rate limiter, validateur d'ordres
│   └── execution_simulator/     # Simulateur de fill, slippage, spread, latence
│
├── 🟢 Intelligence Avancée
│   ├── meta_learning/           # Moteur de décision, learner, mémoire, similarité
│   ├── ai_autonomous_loop/      # Boucle autonome (init seulement)
│   └── lm_studio/               # Intégration LM Studio (LLM local)
│
├── 🔴 Observabilité
│   ├── observability/           # Health score, heartbeat, JSON logger, telemetry
│   ├── monitoring/              # Logger, metrics, pipeline monitor, profiler
│   └── metrics/                 # (vide ?)
│
├── 🟣 Pièuvre (Self-Healing OS)
│   └── pieuvre/                 # Brain, tentacules auto-réparation
│       ├── tentacles/           # Audit, évolution, guérison, mémoire, sécurité
│       ├── dashboard/           # Tableau de bord pièuvre
│       └── incidents/           # Modèles + store d'incidents
│
├── 🌐 Frontend
│   └── frontend/                # React + TypeScript + Tailwind + Vite
│       └── src/
│           ├── components/      # Composants UI
│           ├── hooks/           # Hooks React
│           ├── lib/             # Utilitaires
│           └── views/           # Pages/Vues
│
├── 📁 Data & Config
│   ├── data/                    # CSVs Bitcoin (19d, 27d, 30d)
│   ├── config/                  # Configuration Telegram
│   ├── batch_configs.json       # Configurations batch
│   ├── strategy_factory_config.ini
│   └── alpha_vault_export.json  # Exports alpha vault
│
├── 📊 Project OS (Meta-gestion)
│   └── project_os/              # Scanner de projet, debt map, maturité, roadmap
│
├── 🧪 Tests & Qualité
│   ├── tests/                   # Tests globaux
│   ├── S2/                      # Gate logger, score distribution, calibration
│   └── S3/                      # Telegram alerts, log surveillance, shadow exec
│
├── 📚 Documentation
│   ├── docs/                    # Documentation Sphinx, architecture, invariants, runbooks
│   │   ├── audit/               # Audits
│   │   ├── checklists/          # Checklists de validation
│   │   ├── ci/                  # CI/CD docs
│   │   ├── deployment/          # Guides déploiement
│   │   ├── divers/              # Divers
│   │   ├── evolution/           # Suivi évolution
│   │   ├── modules/             # Docs par module
│   │   ├── notifications/       # Notifications setup
│   │   ├── onboarding/          # Guides onboarding
│   │   ├── runbooks/            # Runbooks opérationnels
│   │   ├── stabilization/       # Rapports stabilisation
│   │   └── v91/                 # Documentation v9.1
│   ├── obsidian_vault/          # Base Obsidian (PKM)
│   └── anara_context/           # Contexte Anara (schémas JSON, lifecycle)
│       └── modules/             # 50+ descripteurs de modules en JSON
│
├── 📝 Logs & Exécution
│   ├── logs/                    # Logs d'exécution
│   ├── feedback_logs/           # 80+ feedbacks JSON + rapports HTML
│   ├── errors/                  # Erreurs capturées
│   ├── checkpoints/             # Points de restauration
│   └── archive_results/         # Résultats archivés
│
├── 🔧 Scripts & Tools
│   ├── scripts/                 # Scripts VPS, tests, validation, onboarding
│   ├── tools/                   # Analyse de cycles, market ranker, runtime tracer
│   └── *.bat / *.ps1            # Launchers : dashboards, API, tests, install
│
├── 📦 Archives
│   ├── archives/                # Archives générales
│   ├── artifacts/               # Artéfacts de build
│   └── cache/                   # Cache système
│
├── 🎟️ Tickets
│   └── tickets/                 # Système de tickets
│
├── 🔐 Certification & Audit
│   ├── certification/           # Certifications
│   └── audit/                   # Traces d'audit (doublon ? voir audit/ racine)
│
├── 📈 Résultats & Rapports
│   ├── reports/                 # Rapports générés
│   ├── results/                 # Résultats d'exécution
│   └── sim_summaries/           # Résumés de simulation
│
├── 🐳 Conteneurisation
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── k8s/
│
├── 🛡️ CI/CD & Qualité
│   ├── .gitlab-ci.yml
│   ├── .pre-commit-config.yaml
│   ├── codecov.yml
│   ├── .coveragerc
│   ├── setup.cfg
│   └── pytest.ini
│
└── 📄 Fichiers racine (150+)
    ├── README.md, ROADMAP.md, QUICKSTART.md...
    ├── *_REPORT.md (20+ rapports de phase)
    ├── *_SUMMARY.md (résumés de complétion)
    ├── *_AUDIT.md (audits techniques)
    └── *.bat / *.ps1 / *.sh (150+ launchers & scripts)
```

---

## 🔥 CLASSIFICATION PAR VALEUR

### Tier S — Cœurs Critiques (Ne pas toucher sans plan)

| Module | Rôle | Fichiers clés |
|--------|------|---------------|
| `core/` | Machine d'état fondamentale, contrats, invariants | `lifecycle.py`, `runtime_state_machine.py`, `invariants.py`, `authority.py` |
| `system/` | Intégrité, kernel, burn-in, monte carlo | `kernel.py`, `integrity_models.py`, `state_machine.py`, `monte_carlo.py` |
| `quant_hedge_ai/` | Hub principal : agents, evolutions, stratégies | `main_v91.py`, `agents/*/`, `strategy_lab/`, `ai_evolution/` |
| `governance/` | Approval chain, decision trace, risk authorizer | `decision_router.py`, `execution_approval.py`, `authority_state.py` |

### Tier A — Moteurs Métier (Valeur directe)

| Module | Rôle |
|--------|------|
| `src/` | Backtest, paper trading, exécution, analytics |
| `strategy_factory/` | Génération/évolution de stratégies |
| `meta_learning/` | Apprentissage par renforcement |
| `pieuvre/` | Auto-guérison, résilience |
| `reality_checks/` | Vérification écart réel/simu |
| `capital_deployment/` | Déploiement progressif du capital |
| `execution_simulator/` | Simulation réaliste fills + slippage |

### Tier B — Infrastructure Critique

| Module | Rôle |
|--------|------|
| `supervision/` | Watchdogs, escalade, kill switches |
| `observability/` | Health score, telemetry, heartbeat |
| `event_bus/` | Communication inter-modules |
| `exchange_constraints/` | Règles exchanges, rate limiting |
| `health/` | Health registry, recovery |
| `monitoring/` | Pipeline monitor, profiler |

### Tier C — Support & Data

| Module | Rôle |
|--------|------|
| `market_data/` | Stream, modèles de données marché |
| `data/` | CSVs Bitcoin historiques |
| `infra/` | APIs, dashboards, notifications |
| `scripts/` | Scripts VPS, validation, onboarding |
| `tools/` | Analyse de cycles, ranker |

### Tier D — UI & Frontend

| Module | Rôle |
|--------|------|
| `frontend/` | React + TypeScript + Tailwind |
| `dashboard/` | Alert dashboard Python |
| `crypto_quant_v16/` | UI v16 |

### Tier E — Documentation & Meta

| Module | Rôle |
|--------|------|
| `docs/` | Documentation Sphinx complète |
| `anara_context/` | Schémas JSON des 50+ modules |
| `project_os/` | Debt map, maturité, scanner |
| `obsidian_vault/` | Base de connaissance |

### Tier F — Historique & Logs

| Module | Rôle |
|--------|------|
| `feedback_logs/` | 80+ feedbacks JSON + HTML |
| `logs/` | Logs runtime |
| `errors/` | Erreurs |
| `archives/` | Archives |
| `tickets/` | Tickets |

### ⚠️ Doublons & Redondances Détectés

| Dossier 1 | Dossier 2 | Note |
|-----------|-----------|------|
| `strategy_factory/` (racine) | `quant_hedge_ai/strategy_factory/` | Deux implémentations parallèles |
| `audit/` (racine) | `governance/` + `pieuvre/tentacles/audit_commits.py` | Fonctions d'audit dispersées |
| `runtime/` (racine) | `quant_hedge_ai/runtime/` | État runtime dupliqué |
| `core/quant/` | `terminal_core/quant/` | Même fichier `logging_alerts.py` |
| `dashboard/` (racine) | `quant_hedge_ai/dashboard/` | Deux dashboards |
| `src/risk/` | `risk/` (racine) | Deux systèmes de risk management |
| `src/events/` | `event_bus/` (racine) | Deux bus d'événements |

---

## 🧬 FLUX DE VALEUR (Graphe de Dépendances)

```
                    ┌──────────────────────────────────┐
                    │        CORE (Machine d'État)      │
                    │   contrats, invariants, autorité   │
                    └──────────┬───────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
   │  GOVERNANCE   │  │   SYSTEM      │  │   PIÈUVRE     │
   │  (approbation)│  │  (intégrité)  │  │ (auto-guérison)│
   └───────┬───────┘  └───────┬───────┘  └───────┬───────┘
           │                  │                  │
           └──────────────────┼──────────────────┘
                              │
                              ▼
               ┌──────────────────────────┐
               │   QUANT_HEDGE_AI (v9.1)  │
               │   Agents + Engine + Lab  │
               └──────────┬───────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                  ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ STRATEGY_LAB  │ │ AI_EVOLUTION  │ │ MARKET_RADAR  │
│ (génération)  │ │ (ranking)     │ │ (détection)   │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                  │
        └─────────────────┼──────────────────┘
                          │
                          ▼
               ┌──────────────────────────┐
               │        SRC ENGINE        │
               │  Backtest + Paper + Exec │
               └──────────┬───────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                  ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ EXECUTION     │ │ CAPITAL_DEPLOY│ │ OBSERVABILITY │
│ SIMULATOR     │ │ (phase gates) │ │ (telemetry)   │
└───────────────┘ └───────────────┘ └───────────────┘
```

---

## 📊 STATISTIQUES GLOBALES

| Métrique | Valeur |
|----------|--------|
| Dossiers totaux (niveau 1) | **89** |
| Fichiers racine | **150+** |
| Sous-dossiers dans `quant_hedge_ai/` | **18** (agents × 11 + engine + strategy_lab + ...) |
| Sous-dossiers dans `src/` | **14** (agent + analytics + backtest + ...) |
| Modules Anara décrits | **54** JSON |
| Feedbacks enregistrés | **80+** |
| Launchers (.bat/.ps1) | **100+** à la racine |
| Doublons identifiés | **7 paires** |
| Branches S2/S3 | **2** (calibration + surveillance) |

---

## 🎯 RECOMMANDATIONS

1. **Fusionner les doublons** : `strategy_factory/` racine ↔ `quant_hedge_ai/strategy_factory/`, `audit/` ↔ `governance/`
2. **Nettoyer la racine** : 150+ fichiers → déplacer les rapports dans `docs/reports/`, scripts dans `scripts/`
3. **Unifier `runtime/`** : Un seul state machine (choisir entre `core/` + `system/` ou `quant_hedge_ai/runtime/`)
4. **Consolider `src/` vs `core/`** : Chevauchement conceptuel — définir clairement qui fait quoi
5. **Archiver `crypto_quant_v16/`** : Semble n'être qu'un bridge UI — fusionner dans `dashboard/` ou `frontend/`
