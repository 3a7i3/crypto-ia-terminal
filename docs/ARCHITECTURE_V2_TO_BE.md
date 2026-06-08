# ARCHITECTURE V2 — PHASE 0B : TO-BE (Architecture Cible)

> **Généré le 2026-06-07**
> **Objectif :** Architecture cible de référence. Toute décision future (ajout de module, refactorisation) sera évaluée par rapport à ce document.
> **Principe :** DDD avec Bounded Contexts stricts. 4 couches. Communication inter-contextes par événements et contrats uniquement.

---

## 1. LES 4 COUCHES

```
┌──────────────────────────────────────────────────────────────────┐
│                        APPLICATIONS                              │
│  Terminal, Dashboards, Telegram Bots, API REST, Frontend React   │
└──────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                          DOMAINS                                 │
│  9 Bounded Contexts métier — toute la logique de trading         │
└──────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                           CORE                                   │
│  Machine d'état, Contrats, Invariants, Event Bus, Autorité       │
└──────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                         PLATFORM                                 │
│  Infra, Observability, Déploiement, CI/CD, Stockage              │
└──────────────────────────────────────────────────────────────────┘
```

**Règles de dépendance strictes :**
- **Applications** → dépend de **Domains** et **Core** (jamais l'inverse)
- **Domains** → dépend de **Core** (jamais l'inverse)
- **Core** → dépend de **Platform** (pour la persistence, logging, etc.)
- **Platform** → ne dépend de personne (couche la plus basse)
- **Inter-domaines** → communication par événements uniquement, pas d'imports directs

---

## 2. LES 9 BOUNDED CONTEXTS (Domaines Métier)

### 2.1 — Market Intelligence
**Responsabilité :** Tout ce qui concerne la perception du marché.
**Ce qui entre :** market_data, on-chain, exchange, social
**Ce qui sort :** MarketSnapshot, Anomaly, WhaleAlert, LiquidityMap, RegimeClassification

```
domains/market/
├── radar/              # Détection d'anomalies, tokens, social scanning
├── liquidity/          # Cartographie de liquidité, flux, profondeur
├── whales/             # Tracking de baleines (on-chain + exchange)
├── onchain/            # Données on-chain, indicateurs
├── sentiment/          # Analyse de sentiment (social, news)
├── regime/             # Classification de régime de marché
├── data/               # Stream, modèles canoniques, replay
└── constraints/        # Règles exchange, rate limiting, validation
```

**Provenance des fichiers :**
- `quant_hedge_ai/market_radar/` → `domains/market/radar/`
- `quant_hedge_ai/liquidity_map/` → `domains/market/liquidity/`
- `quant_hedge_ai/agents/whales/` → `domains/market/whales/`
- `market_radar/whale_tracker.py` → Fusionné dans `domains/market/whales/`
- `quant_hedge_ai/agents/onchain/` → `domains/market/onchain/`
- `quant_hedge_ai/agents/market/` → Distribué dans radar/sentiment
- `market_data/` → `domains/market/data/`
- `exchange_constraints/` → `domains/market/constraints/`
- `signal/` (partiellement) → Distribué dans radar/regime

---

### 2.2 — Strategy
**Responsabilité :** Génération, évolution, validation, et ranking des stratégies.
**Ce qui entre :** MarketSnapshot, PerformanceMetrics
**Ce qui sort :** StrategyInstance, Signal, StrategyRanking

```
domains/strategy/
├── factory/            # Génération de stratégies (alpha vault, templates)
├── lab/                # Laboratoire : batch testing, parameter space
├── evolution/          # Mutation, genetic evolution, ranking
├── features/           # Feature engineering, registre, matérialisation
├── validation/         # Validation, probation, walk-forward
├── backtesting/        # Backtest engine (unique, dédupliqué)
└── repository/         # Stockage des stratégies, scoreboard
```

**Provenance des fichiers :**
- `strategy_factory/` (racine) + `quant_hedge_ai/strategy_factory/` → Fusionnés dans `domains/strategy/factory/`
- `quant_hedge_ai/strategy_lab/` → `domains/strategy/lab/`
- `quant_hedge_ai/ai_evolution/` → `domains/strategy/evolution/`
- `signal/evolution/` → Fusionné dans `domains/strategy/evolution/`
- `quant_hedge_ai/features/` → `domains/strategy/features/`
- `src/agent/` → `domains/strategy/factory/` (stratégies concrètes)
- `backtesters` multiples → Unifiés dans `domains/strategy/backtesting/`

---

### 2.3 — Execution
**Responsabilité :** Tout ce qui transforme un signal en ordre exécuté.
**Ce qui entre :** Signal, OrderRequest
**Ce qui sort :** Fill, ExecutionReport, OrderState

```
domains/execution/
├── router/             # Acheminement des ordres vers les exchanges
├── orders/             # Cycle de vie des ordres, validation
├── fills/              # Fill simulation réaliste, slippage, spread
├── latency/            # Modèles de latence
├── exchange/           # Connecteurs exchange (MEXC, Binance, etc.)
└── reconciliation/     # Réconciliation post-trade, pending orders
```

**Provenance des fichiers :**
- `execution_simulator/` → `domains/execution/fills/` + `domains/execution/latency/`
- `src/engine/` → `domains/execution/router/`
- `src/execution/` → `domains/execution/orders/`
- `quant_hedge_ai/agents/execution/` → Distribué dans router/orders
- `system/pending_order_tracker.py` + `system/position_reconciler.py` → `domains/execution/reconciliation/`

---

### 2.4 — Risk
**Responsabilité :** Moteur de risque UNIQUE. Toutes les décisions de risque passent par ici.
**Ce qui entre :** Signal, PortfolioState, MarketRegime
**Ce qui sort :** RiskAssessment, Go/NoGo, SizeLimit

```
domains/risk/
├── engine/             # GlobalRiskGate, RiskLimits — le cœur unique
├── circuit_breaker/    # Circuit breakers, kill switches
├── regime_gate/        # Filtrage par régime de marché
├── exposure/           # Exposition, concentration, corrélation
└── policies/           # Règles métier de risque (configurables)
```

**Provenance des fichiers :**
- `risk/` → `domains/risk/engine/`
- `src/risk/` → Fusionné dans `domains/risk/circuit_breaker/` + `regime_gate/`
- `quant_hedge_ai/agents/risk/` → Fusionné dans `domains/risk/engine/`
- `supervision/kill_switch*.py` → `domains/risk/circuit_breaker/` (les kill switches sont du risk, pas de la supervision)

**⚠️ Règle impérative :** Après migration, un seul moteur de risque. Tout module qui veut du risque passe par `domains/risk/engine/`.

---

### 2.5 — Portfolio
**Responsabilité :** Gestion du portefeuille, sizing, exposition, déploiement du capital.
**Ce qui entre :** RiskAssessment, Fill, MarketState
**Ce qui sort :** OrderSize, PortfolioState, AllocationDecision

```
domains/portfolio/
├── state/              # État du portefeuille, positions
├── sizing/             # Order sizing (Kelly, EV, vol-targeting)
├── deployment/         # Capital throttle, phase gates, KPI tracking
├── rebalancing/        # Rééquilibrage, diversification
└── reporting/          # PnL, equity curve, performance attribution
```

**Provenance des fichiers :**
- `capital_deployment/` → `domains/portfolio/deployment/`
- `src/portfolio/` → `domains/portfolio/state/`
- `quant_hedge_ai/agents/portfolio/` → Distribué dans sizing/deployment
- `system/equity_curve.py` → `domains/portfolio/reporting/`
- `system/strategy_metrics.py` → `domains/portfolio/reporting/`

---

### 2.6 — Governance
**Responsabilité :** Contrôle souverain, approbation, traçabilité, audit.
**Ce qui entre :** Tout événement décisionnel
**Ce qui sort :** Approval/Rejection, DecisionTrace, AuditLog

```
domains/governance/
├── approval/           # Execution approval, decision router
├── authority/          # Trading authority, AI constraints
├── trace/              # Decision trace, decision ledger
├── audit/              # Audit engine, replay
├── certification/      # Phase certification
└── policies/           # Governance policies
```

**Provenance des fichiers :**
- `governance/` → Distribué dans approval/authority/trace
- `audit/` → `domains/governance/audit/`
- `certification/` → `domains/governance/certification/`
- `pieuvre/tentacles/audit_commits.py` → Fusionné dans `domains/governance/audit/`
- `reality_checks/` → `domains/governance/audit/` (le gap analysis est de l'audit)

---

### 2.7 — Intelligence
**Responsabilité :** Apprentissage, feedback loops, méta-décisions, adaptation.
**Ce qui entre :** TradeResult, PerformanceMetrics, MarketRegime
**Ce qui sort :** AdaptiveThreshold, StrategyAllocation, RegretDelta

```
domains/intelligence/
├── meta_learning/      # Learner, mémoire, similarité
├── feedback/           # Regret engine, feedback loops
├── adaptation/         # Adaptive threshold, drift detection
├── allocation/         # Strategy allocator, weighting
└── llm/                # Intégration LLM (LM Studio)
```

**Provenance des fichiers :**
- `meta_learning/` → `domains/intelligence/meta_learning/`
- `quant_hedge_ai/agents/intelligence/` → `domains/intelligence/adaptation/`
- `src/analytics/` → Distribué dans feedback/adaptation
- `lm_studio/` → `domains/intelligence/llm/`
- `ai_autonomous_loop/` → Supprimé (module zombie, `__init__.py` vide)

---

### 2.8 — Simulation
**Responsabilité :** Backtesting, paper trading, replay, simulation d'exécution.
**Ce qui entre :** StrategyInstance, MarketData, SimulationConfig
**Ce qui sort :** SimulationResult, TradeRecord, PerformanceReport

```
domains/simulation/
├── backtest/           # Moteur de backtest (unique)
├── paper/              # Paper trading, portefeuille virtuel
├── replay/             # Replay engine, resimulation
├── sandbox/            # Environnement isolé pour tests
└── fills/              # Fill simulation (délégation vers execution/fills)
```

**Provenance des fichiers :**
- `paper_trading/` → `domains/simulation/paper/`
- `src/paper/` → Fusionné dans `domains/simulation/paper/`
- `src/backtest/` → `domains/simulation/backtest/`
- `strategy_factory/backtester.py` + `quant_hedge_ai/strategy_factory/backtester.py` + `quant_hedge_ai/strategy_lab/backtest_launcher.py` → Unifiés dans `domains/simulation/backtest/`

---

### 2.9 — Supervision
**Responsabilité :** Watchdogs, auto-guérison, escalade, résilience.
**Ce qui entre :** HealthEvents, Anomalies, Errors
**Ce qui sort :** EscalationLevel, HealingAction, RecoveryState

```
domains/supervision/
├── watchdogs/          # Performance watchdog, ops watchdog, exchange monitor
├── healing/            # Auto-guérison, recovery playbooks, bot doctor
├── escalation/         # Escalation engine, alert manager
└── pieuvre/            # Système pieuvre autonome (brain + tentacules)
```

**Provenance des fichiers :**
- `supervision/` → Distribué dans watchdogs/healing/escalation
- `pieuvre/` → `domains/supervision/pieuvre/`

---

## 3. LA COUCHE CORE

```
core/
├── contracts/          # DecisionPacket, SignalResult, OrderRequest — tous les types canoniques
├── kernel/             # Machine d'état, lifecycle, invariants
├── authority/          # Authority, signatures, identity
├── event_bus/          # Bus d'événements (UNIQUE pour tout le système)
├── startup/            # Bootstrap, warm boot, séquence de démarrage
└── integrity/          # Burn-in, monte carlo, walk-forward, vérification invariants
```

**Provenance des fichiers :**
- `core/` → Distribué dans contracts/kernel/authority
- `system/` → `core/startup/` + `core/integrity/`
- `runtime/` (racine) + `quant_hedge_ai/runtime/` + `src/runtime/` → Unifiés dans `core/kernel/`
- `event_bus/` → `core/event_bus/` (fusionné avec `src/events/`)
- `terminal_core/` → Supprimé (doublon de `core/`)
- `cold_start/` → `core/startup/`

---

## 4. LA COUCHE PLATFORM

```
platform/
├── observability/      # Telemetry, metrics, logging, health, heartbeat
├── infrastructure/     # API REST, notifications (email/Discord/Slack/Telegram)
├── storage/            # Bases de données, repositories, cache
├── deployment/         # Docker, K8s, scripts VPS, CI/CD
├── config/             # Configuration centralisée
└── security/           # (future) Auth, encryption
```

**Provenance des fichiers :**
- `observability/` + `monitoring/` + `health/` + `metrics/` → Unifiés dans `platform/observability/`
- `infra/` → `platform/infrastructure/`
- `databases/` → `platform/storage/`
- `deploy/` + `k8s/` + `install/` → `platform/deployment/`
- `config/` → `platform/config/`

---

## 5. LA COUCHE APPLICATIONS

```
applications/
├── terminal/           # Terminal de trading, CLI, TUI
├── dashboard/          # Dashboards (Streamlit, Panel, etc.)
├── telegram/           # Bots Telegram
├── api/                # API REST
└── frontend/           # React/TypeScript (frontend/)
```

**Provenance des fichiers :**
- `frontend/` → `applications/frontend/`
- `dashboard/` + `crypto_quant_v16/` + `quant_hedge_ai/dashboard/` → Unifiés dans `applications/dashboard/`
- `src/telegram/` + `infra/notifications/` (Telegram) → `applications/telegram/`
- `infra/api/` → `applications/api/`

---

## 6. RÈGLES DE DÉPENDANCE ENTRE CONTEXTES

| De → Vers | Market | Strategy | Execution | Risk | Portfolio | Governance | Intelligence | Simulation | Supervision |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Market** | - | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Strategy** | ✅ | - | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Execution** | ✅ | ❌ | - | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Risk** | ✅ | ❌ | ✅ | - | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Portfolio** | ✅ | ❌ | ✅ | ✅ | - | ❌ | ❌ | ❌ | ❌ |
| **Governance** | ❌ | ❌ | ✅ | ✅ | ✅ | - | ❌ | ❌ | ❌ |
| **Intelligence** | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | - | ❌ | ❌ |
| **Simulation** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | - | ❌ |
| **Supervision** | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | - |

✅ = peut dépendre (par événements ou contrats)
❌ = interdit (dépendance directe interdite)

**Règle d'or :** Les dépendances directes traversant les contextes sont interdites. Toute communication inter-contexte passe par `core/event_bus/` ou par des interfaces définies dans `core/contracts/`.

---

## 7. CONTRATS CANONIQUES (core/contracts/)

Fichier unique de référence pour tous les types partagés :

```python
# core/contracts/types.py

# ── Signal ──
class Signal:
    symbol: str
    side: Literal["BUY", "SELL", "FLAT"]
    score: float
    regime: MarketRegime
    timestamp: datetime

# ── Ordre ──
class OrderRequest:
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    order_type: Literal["MARKET", "LIMIT", "STOP_LIMIT"]
    price: Optional[Decimal]
    stop_price: Optional[Decimal]

class Fill:
    order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    price: Decimal
    fee: Decimal
    timestamp: datetime

# ── Risque ──
class RiskAssessment:
    approved: bool
    max_size: Decimal
    reason: Optional[str]
    metadata: dict

# ── Événements ──
class TradeEvent:
    event_type: Literal["OPEN", "CLOSE", "UPDATE"]
    symbol: str
    position_id: str
    # ... etc.

class OrderEvent: ...
class SignalEvent: ...
class RiskEvent: ...
class GovernanceEvent: ...
class HealthEvent: ...

# ── Régime ──
class MarketRegime(Enum):
    TREND_BULL = "TREND_BULL"
    TREND_BEAR = "TREND_BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOL = "HIGH_VOL"
    CHOPPY = "CHOPPY"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"

# ── Conviction ──
class ConvictionLevel(Enum):
    SKIP = "SKIP"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
```

**⚠️ Règle :** Ces types sont la source unique de vérité. Toute duplication d'enum ou de classe de contrat est un bug architectural.

---

## 8. STRUCTURE FINALE DU PROJET

```
crypto_ai_terminal/
│
├── core/                        # Couche Core
│   ├── contracts/               # Types canoniques, enums, dataclasses
│   │   ├── __init__.py
│   │   ├── types.py             # Signal, OrderRequest, Fill, RiskAssessment, etc.
│   │   └── events.py            # TradeEvent, OrderEvent, SignalEvent, etc.
│   ├── kernel/                  # Machine d'état, lifecycle
│   │   ├── lifecycle.py
│   │   ├── runtime_state_machine.py
│   │   ├── invariants.py
│   │   └── authority.py
│   ├── event_bus/               # Bus d'événements unique
│   │   ├── bus.py
│   │   └── bridge.py
│   ├── startup/                 # Bootstrap, warm boot, cold start
│   │   ├── bootstrap.py
│   │   ├── warm_boot.py
│   │   └── cold_start_manager.py
│   └── integrity/               # Burn-in, monte carlo, walk-forward
│       ├── burn_in.py
│       ├── monte_carlo.py
│       └── walk_forward.py
│
├── domains/                     # Couche Domaines (9 Bounded Contexts)
│   ├── market/                  # 2.1 — Market Intelligence
│   │   ├── radar/
│   │   ├── liquidity/
│   │   ├── whales/
│   │   ├── onchain/
│   │   ├── sentiment/
│   │   ├── regime/
│   │   ├── data/
│   │   └── constraints/
│   ├── strategy/                # 2.2 — Strategy
│   │   ├── factory/
│   │   ├── lab/
│   │   ├── evolution/
│   │   ├── features/
│   │   ├── validation/
│   │   ├── backtesting/
│   │   └── repository/
│   ├── execution/               # 2.3 — Execution
│   │   ├── router/
│   │   ├── orders/
│   │   ├── fills/
│   │   ├── latency/
│   │   ├── exchange/
│   │   └── reconciliation/
│   ├── risk/                    # 2.4 — Risk (moteur unique)
│   │   ├── engine/
│   │   ├── circuit_breaker/
│   │   ├── regime_gate/
│   │   ├── exposure/
│   │   └── policies/
│   ├── portfolio/               # 2.5 — Portfolio
│   │   ├── state/
│   │   ├── sizing/
│   │   ├── deployment/
│   │   ├── rebalancing/
│   │   └── reporting/
│   ├── governance/              # 2.6 — Governance
│   │   ├── approval/
│   │   ├── authority/
│   │   ├── trace/
│   │   ├── audit/
│   │   ├── certification/
│   │   └── policies/
│   ├── intelligence/            # 2.7 — Intelligence
│   │   ├── meta_learning/
│   │   ├── feedback/
│   │   ├── adaptation/
│   │   ├── allocation/
│   │   └── llm/
│   ├── simulation/              # 2.8 — Simulation
│   │   ├── backtest/
│   │   ├── paper/
│   │   ├── replay/
│   │   ├── sandbox/
│   │   └── fills/
│   └── supervision/             # 2.9 — Supervision
│       ├── watchdogs/
│       ├── healing/
│       ├── escalation/
│       └── pieuvre/
│
├── platform/                    # Couche Platform
│   ├── observability/           # Telemetry, metrics, logging, health
│   │   ├── telemetry.py
│   │   ├── metrics.py
│   │   ├── logging.py
│   │   ├── health.py
│   │   └── heartbeat.py
│   ├── infrastructure/          # API, notifications
│   │   ├── api/
│   │   ├── notifications/
│   │   └── panels/
│   ├── storage/                 # Bases de données
│   │   ├── databases/
│   │   └── cache/
│   ├── deployment/              # Docker, K8s, scripts
│   │   └── ...
│   └── config/                  # Configuration centralisée
│       └── ...
│
├── applications/                # Couche Applications
│   ├── frontend/                # React/TypeScript
│   ├── dashboard/               # Dashboards unifiés
│   ├── telegram/                # Bots Telegram
│   ├── api/                     # API REST
│   └── terminal/                # CLI/TUI
│
├── docs/                        # Documentation
├── tests/                       # Tests globaux
├── scripts/                     # Scripts utilitaires
├── data/                        # Données statiques
├── config/                      # Configuration runtime
├── tools/                       # Outils d'analyse
│
├── logs/                        # Logs (runtime)
├── feedback_logs/               # Feedbacks (runtime)
├── errors/                      # Erreurs (runtime)
├── reports/                     # Rapports générés (runtime)
├── results/                     # Résultats (runtime)
├── archives/                    # Archives
├── artifacts/                   # Artéfacts build
├── checkpoints/                 # Points de restauration
│
└── [fichiers racine]            # README.md, ROADMAP.md, requirements.txt, Dockerfile, etc.
```

---

## 9. ORDRE DES MIGRATIONS (Phase 0C)

L'ordre est critique : on commence par le bas de la pyramide.

### Étape 1 : Platform (fondation)
1. `observability/` + `monitoring/` + `health/` + `metrics/` → `platform/observability/`
2. `infra/` → `platform/infrastructure/`
3. `databases/` → `platform/storage/`
4. `deploy/` + `k8s/` + `install/` → `platform/deployment/`

### Étape 2 : Core (contrats et noyau)
5. **Créer** `core/contracts/types.py` — tous les types canoniques
6. **Fusionner** `event_bus/` + `src/events/` → `core/event_bus/`
7. **Unifier** `runtime/` + `quant_hedge_ai/runtime/` + `src/runtime/` → `core/kernel/`
8. `system/` → `core/startup/` + `core/integrity/`
9. `cold_start/` → `core/startup/`
10. `terminal_core/` → Supprimer (doublon de `core/`)

### Étape 3 : Domaines (métier)
11. `domains/market/` — fusion de 8 modules market
12. `domains/risk/` — fusion des 3 moteurs de risque
13. `domains/strategy/` — fusion des 5 mécanismes d'évolution
14. `domains/execution/` — fusion des modules d'exécution
15. `domains/portfolio/` — fusion des modules portfolio
16. `domains/governance/` — fusion governance + audit + certification + reality_checks
17. `domains/intelligence/` — fusion des modules d'intelligence
18. `domains/simulation/` — fusion des 4 backtesters + 2 paper trading
19. `domains/supervision/` — supervision + pièuvre

### Étape 4 : Applications (interfaces)
20. `frontend/` → `applications/frontend/`
21. Fusion des 4 dashboards → `applications/dashboard/`
22. `src/telegram/` + notifs Telegram → `applications/telegram/`
23. `infra/api/` → `applications/api/`

### Étape 5 : Nettoyage racine
24. Déplacer les ~150 fichiers racine : rapports → `docs/reports/`, launchers → `scripts/launchers/`
25. Supprimer `ai_autonomous_loop/` (module zombie)

---

## 10. SHIMS TEMPORAIRES

Pour chaque migration, on crée un shim :

```python
# Ancien emplacement : quant_hedge_ai/strategy_factory/__init__.py
# Devient un shim :
"""
⚠️ DEPRECATED — Ce module a migré vers domains/strategy/factory/
Ce shim sera supprimé quand plus aucun import ne l'utilisera.
"""
from domains.strategy.factory import *  # noqa
import warnings
warnings.warn(
    "quant_hedge_ai.strategy_factory est déprécié. Utilisez domains.strategy.factory.",
    DeprecationWarning,
    stacklevel=2,
)
```

**Critères de suppression d'un shim :**
1. Aucun import dans le code source ne référence l'ancien chemin
2. Tous les tests passent avec le nouveau chemin
3. Le shim a existé pendant au moins 2 semaines (période de transition)

---

## 11. VALIDATION FINALE

Checklist post-migration :
- [ ] Tous les tests passent (`pytest tests/`)
- [ ] `grep -r "from risk import"` ne retourne rien (tout passe par `domains/risk/engine/`)
- [ ] `grep -r "from strategy_factory"` ne retourne rien
- [ ] `grep -r "from src.events"` ne retourne rien
- [ ] `grep -r "from src.risk"` ne retourne rien
- [ ] Le `advisor_loop.py` importe depuis les nouveaux chemins
- [ ] La racine contient < 30 fichiers
- [ ] Aucun dossier zombie (vide)
- [ ] `ARCHITECTURE_V2_TO_BE.md` est le document de référence pour toute nouvelle PR

---

## 12. GOUVERNANCE ARCHITECTURALE (pour l'avenir)

**Règles pour tout nouveau module :**
1. À quel Bounded Context appartient-il ? (obligatoire)
2. Est-ce un nouveau concept ou une variation d'un existant ?
3. Quels événements produit-il ? Consomme-t-il ?
4. Respecte-t-il les règles de dépendance de la matrice (§6) ?

**Check automatique (future CI) :**
- Un linter d'architecture qui vérifie que `domains/market/` n'importe jamais `domains/execution/`
- Un détecteur de doublons d'enums/classes dans `core/contracts/`

---

---

## 13. GRILLE DE RESPONSABILITÉ (Module Responsibility Card)

Pour chaque module migré, remplir cette fiche avant de commencer la migration.
Un module dont la fiche est incomplète n'est pas prêt à migrer.

```
Nom        :
Mission    : (une seule phrase — si deux phrases, c'est deux modules)
Entrées    : (types canoniques depuis core/contracts/)
Sorties    : (types canoniques depuis core/contracts/)
Événements produits  :
Événements consommés :
API publique : (liste des fonctions/classes exportées)
État interne : (None | fichier | DB | mémoire)
Peut être appelé par : (liste des Bounded Contexts autorisés)
Ne peut PAS être appelé par : (liste explicite des BC interdits)
```

**Signal d'alarme :** si "Mission" dépasse une phrase, le module doit être découpé.
**Signal d'alarme :** si "Peut être appelé par" = "tout le monde", le module est une boîte noire globale.

---

## 14. TAXONOMIE DES DOUBLONS

Les doublons se résolvent différemment selon leur catégorie. Identifier la bonne catégorie avant d'agir.

| Catégorie | Description | Résolution |
|-----------|------------|-----------|
| **Doublon de code** | Même logique copiée dans 2 fichiers différents | Extraire dans `core/contracts/` ou module partagé — supprimer l'un |
| **Doublon de responsabilité** | 2 modules font le même métier (ex: 3 kill switches) | Choisir le plus complet, écrire un shim pour les autres, supprimer les shims au bout de 2 semaines |
| **Doublon d'orchestration** | 2 coordinateurs différents pour le même flux (ex: 5 machines d'états) | Unifier dans `core/kernel/` — un seul état souverain |
| **Doublon de données** | Même état stocké en 2 endroits (ex: positions dans VirtualPortfolio + MexcSimulator) | Désigner 1 source de vérité, les autres écoutent via event bus |
| **Doublon de gouvernance** | 2 chemins possibles pour prendre la même décision | Créer un seul point de décision dans `domains/governance/approval/`, supprimer le bypass |

**Règle :** Identifier la catégorie → appliquer la résolution correspondante. Ne jamais résoudre un doublon de données comme un doublon de code.

---

## 15. RADAR DE MATURITÉ (Module Maturity Score)

À remplir pour chaque module lors de la Phase 0A (AS-IS). Permet de prioriser les migrations.
Score < 5 = candidat prioritaire à la refonte. Score ≥ 8 = stable, migrer en dernier.

| Critère | Description | Note /10 |
|---------|------------|---------|
| **Responsabilité unique** | Le module fait exactement une chose | /10 |
| **Couplage** | Peu de dépendances directes vers d'autres modules | /10 |
| **Testabilité** | Tests unitaires présents et isolés | /10 |
| **Documentation** | Fiche de responsabilité complète | /10 |
| **Cohérence DDD** | Appartient clairement à un seul Bounded Context | /10 |
| **Dette technique** | Absence de TODO, FIXME, DEPRECATED non traités | /10 |

**Score composite = moyenne des 6 critères.**

Exemple de radar module `risk/circuit_breaker.py` :
```
Responsabilité unique : 7/10  (fait du circuit-breaking ET du kill-switch)
Couplage             : 4/10  (importe supervision/, governance/, risk/)
Testabilité          : 6/10  (tests présents mais dépendants de l'état global)
Documentation        : 3/10  (aucune fiche de responsabilité)
Cohérence DDD        : 5/10  (entre Risk et Supervision)
Dette technique      : 5/10  (2 TODO ouverts)
Score composite      : 5.0/10 → candidat migration prioritaire
```

---

## 16. GRAPHE DE DÉPENDANCES (Phase 0A obligatoire)

Avant toute migration, construire le graphe : **A ne peut pas vivre sans B**.

Différent de "A importe B" — c'est une dépendance existentielle.

```
Exemple :
advisor_loop → peut vivre sans quant_hedge_ai.dashboard (visualisation)
advisor_loop → ne peut PAS vivre sans core.authority (gouvernance)
advisor_loop → ne peut PAS vivre sans domains.risk.engine (sécurité)
```

**Ordre de migration = ordre inverse du graphe de dépendance.**
Les modules sans dépendants (feuilles du graphe) migrent en premier.
Les modules dont tout dépend (racines) migrent en dernier.

**Outil recommandé :**
```bash
python -m pydeps <module> --noshow --max-bacon 3
# ou
grep -rn "from <module> import" . --include="*.py" | sort | uniq
```

---

> **Ce document est la constitution architecturale du projet.**
> Toute modification doit passer par une PR documentée qui met à jour ce fichier.
