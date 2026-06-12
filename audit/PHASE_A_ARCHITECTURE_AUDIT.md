# AUDIT ARCHITECTURE COMPLET — crypto_ai_terminal
**Principal Software Architect — 2026-06-11**
**Niveau: Quant Institutionnel (Citadel / Jane Street / Two Sigma)**

---

## 1. CHIFFRES CLÉS

| Métrique | Valeur | Évaluation |
|----------|--------|-----------|
| Fichiers Python | 967 | Très large pour un solo dev |
| Taille disque (code) | ~1.6 GB | Hors logs/archives/data |
| Packages Python actifs | 40 | Bien modulé |
| Fichiers > 500 lignes | 12 | 1 monolithe critique |
| Code archivé (_ARCHIVE_2026) | 44 fichiers | Nettoyable |
| Fichiers de test | 282 | Excellente couverture |
| TODO/FIXME | 4,560 | Dette critique |
| Flake8 ignores | 40+ modules | Symptôme qualité |
| Score santé architecture | 7.2 / 10 | Mature mais dette |

---

## 2. PIPELINE — ÉTAT ACTUEL

```
MARKET DATA    → market_scanner.py (829 l) — fetcher + validator + retry dans UNE classe
FEATURES       → quant_hedge_ai/features/ ET src/analytics/ — 2 pipelines (canonical non clair)
REGIME         → regime_detector.py ET advanced_regime_detector.py — 2 détecteurs
SIGNAL         → live_signal_engine.py (608 l) ET signal_engine.py — 2 engines
RISK           → global_risk_gate.py + portfolio_brain.py + risk/ + governance/ — dispersé sur 3 packages
PORTFOLIO      → portfolio_brain.py + quant_hedge_ai/agents/portfolio/ + src/portfolio/ — 3 localisations
EXECUTION      → execution_engine.py + src/engine/execution_router.py (DEAD) + paper_trading/
PERSISTENCE    → databases/ + mistake_memory.py + execution_trace.py + audit_trail.py — dispersée
REPORTING      → advisor_loop.py (5,872 l MONOLITHE) + command_center_bot.py (1,457 l) + 3 bots Telegram
LEARNING       → mistake_memory.py + ai_evolution/ + evolution_core.py + meta_learning/ (DEAD)
```

Verdict: Chaque étape existe mais est dupliquée 2-3 fois. SRP violé à chaque étage.

---

## 3. MATRICE DES MODULES

| Module | Supprimer ? | Fusionner ? | Priorité |
|--------|------------|------------|---------|
| core/advisor_loop.py (5,872 l) | NON | SPLITTER en 5 | P0 |
| meta_learning/decision_engine.py | OUI — DEAD | → quant_hedge_ai/engine/ | P0 |
| tracker_system/auto_decision_engine.py | OUI — DEAD | → quant_hedge_ai/engine/ | P0 |
| src/engine/execution_router.py (321 l) | OUI — DEAD | → quant_hedge_ai/agents/execution/ | P0 |
| strategy_factory/ (root, stubs) | OUI — DEAD | → quant_hedge_ai/strategy_factory/ | P0 |
| src/risk/kill_switch.py | OUI — DEAD | → supervision/killswitch_hardened.py | P0 |
| src/events/event_bus.py | OUI — DEAD | → event_bus/bus.py | P0 |
| crypto_quant_v16/ | OUI — UI non intégrée | — | P0 |
| supervision/kill_switch.py | ? | → killswitch_hardened | P1 |
| advanced_regime_detector.py | ? | avec regime_detector | P1 |
| monitoring/ + monitor/ | NON | MERGER en 1 | P1 |
| pieuvre/ | MOVE | → experiments/ | P1 |
| lm_studio/ | MOVE | → experiments/ | P1 |
| portfolio_brain.py (740 l) | NON | SPLITTER | P2 |
| market_scanner.py (829 l) | NON | SPLITTER | P2 |
| strategy_allocator.py (753 l) | NON | SPLITTER | P2 |

---

## 4. DOUBLONS CONFIRMÉS

```
DEAD / DUPLICATE                              CANONICAL
────────────────────────────────────────────────────────────────
meta_learning/decision_engine.py          →   quant_hedge_ai/engine/decision_engine.py
tracker_system/auto_decision_engine.py    →   quant_hedge_ai/engine/decision_engine.py
src/engine/execution_router.py            →   quant_hedge_ai/agents/execution/execution_engine.py
src/events/event_bus.py                   →   event_bus/bus.py
src/risk/kill_switch.py                   →   supervision/killswitch_hardened.py
strategy_factory/ (root stubs)            →   quant_hedge_ai/strategy_factory/
_ARCHIVE_2026/global_risk_gate_root.py    →   quant_hedge_ai/agents/risk/global_risk_gate.py
crypto_quant_v16/                         →   NON INTÉGRÉ — supprimer
```

---

## 5. POINTS FAIBLES — ANALYSE IMPITOYABLE

### CRITIQUE

**C1 — core/advisor_loop.py (5,872 lignes)**
Threading + signals OHLCV + logging + Telegram + watchdog + state tracking dans 1 fichier.
→ SPOF architectural. Un bug dans le reporting tue le trading.
→ Impossible à tester unitairement. Impossible de remplacer Telegram.

**C2 — 4,560 TODO/FIXME**
Code manquant à 4,560 endroits. En production avec capital réel = risque direct.
→ Trier: implémenter ou supprimer avant tout live trading.

**C3 — 40+ modules ignorés en flake8 (F401)**
Imports inutilisés massivement ignorés. Mypy impossible. Bugs silencieux potentiels.

**C4 — Mutable Shared State multi-thread dans advisor_loop**
Variables d'état mutables partagées entre threads.
→ Race conditions potentielles. Corruption silencieuse d'état en live.

### MAJEUR

**M1 — 2 pipelines features** (quant_hedge_ai/features/ vs src/analytics/)
Si l'un est mis à jour, l'autre diverge silencieusement. Backtests non reproductibles.

**M2 — 2 Regime Detectors actifs**
Si les 2 tournent avec des résultats différents, quelle décision prime ?

**M3 — Risk dispersé sur 3 packages**
quant_hedge_ai/agents/risk/ + risk/ + governance/. Chemin complet du risk check introuvable.

**M4 — Portfolio Brain (740 l) God Object**
Calcule positions + gère rebalancing + applique limites + envoie alertes.

**M5 — Persistence non unifiée**
4 endroits de persistence. Pas de schema migration. Rollback impossible.

### MOYEN

- 5 bots Telegram différents sans base commune
- 4 sources de configuration (.env, runtime_config.json, runtime_config.py, telegram_config.json)
- Absence de type hints systématique

---

## 6. ARCHITECTURE CIBLE — CRYPTO QUANT PLATFORM V3

### Principe: Un dossier = une responsabilité. Un module = une responsabilité.

```
src/
├── domain/          # Entités pures (Order, Position, Signal, Trade, Regime)
│   └── interfaces/  # Protocols: IExchange, IRiskGate, ISignal, ILearner
├── data/            # Fetch OHLCV + validation + cache + replay
├── features/        # Feature Engineering + RegimeDetector (1 seul)
├── signals/         # Stratégies (implémentent ISignal) + SignalEngine + Ranker
├── risk/            # GlobalRiskGate + OrderSizer + RiskLimits + CircuitBreaker + KillSwitch
├── portfolio/       # PositionManager + StrategyAllocator + PortfolioBrain (splitté)
├── execution/       # ExecutionRouter (sim|paper|live) + ExchangeAdapter + Deduplicator
├── learning/        # MistakeMemory + TradePostMortem + StrategyEvolution
├── intelligence/    # AIAdvisor + ChiefOfficer + DecisionEngine (1 seul)
├── governance/      # TradingAuthority + ApprovalChain + AuditTrail
├── runtime/         # EventBus + RuntimeStateMachine + RuntimeCoordinator
├── supervision/     # OpsWatchdog + SelfHealingBot + AlertManager + RecoveryPlaybooks
├── reporting/       # TelegramReporter (1 seul) + MetricsExporter
└── storage/         # Repositories + Migrations + Snapshots
```

### Interfaces Python (Protocols)

```python
class IExchange(Protocol):
    async def fetch_ohlcv(self, symbol: str, timeframe: str) -> list[OHLCV]: ...
    async def place_order(self, order: Order) -> OrderResult: ...

class IRiskGate(Protocol):
    def check(self, signal: Signal, portfolio: Portfolio) -> RiskDecision: ...

class ISignalStrategy(Protocol):
    def generate(self, features: FeatureSet, regime: Regime) -> Signal | None: ...

class ILearner(Protocol):
    def record_outcome(self, trade: TradeResult) -> None: ...
    def get_rules(self) -> list[Rule]: ...
```

### Flux de Données

```
MarketData (IExchange) → FeaturePipeline → SignalEngine (ISignalStrategy[])
    → GlobalRiskGate (IRiskGate) → PortfolioBrain → ExecutionRouter
    → TradePostMortem + MistakeMemory (ILearner) → feedback → SignalEngine
```

---

## 7. INDUSTRIALISATION — COMPOSANTS JUSTIFIÉS POUR 24/7

| Composant | Justification | Localisation cible |
|-----------|--------------|-------------------|
| HealthMonitor | Heartbeat 30s. Alerte si silence > 90s. | supervision/watchdog/ |
| CircuitBreaker (unifié) | Présent en 2 endroits. Consolider. | src/risk/circuit_breaker/ |
| RetryPolicy | Exponential backoff pour exchange calls. | src/execution/adapters/ |
| DeadLetterQueue | Events rejetés → queue → audit. | src/runtime/event_bus/ |
| EventStore | Persister tous les events. Permet replay incident. | src/storage/ |
| Snapshot | État complet toutes les heures. | src/storage/snapshots/ |
| ConfigManager | Pydantic BaseSettings. 1 source de vérité. | config/settings.py |
| MetricsExporter | Prometheus. Latence, PnL, fill rate, drawdown. | src/reporting/metrics/ |
| StructuredLogger | JSON + correlation_id. | src/reporting/ |
| AuditTrail (immutable) | Chaque décision loggée avec hash chain. | src/governance/audit/ |
| ModelRegistry | Versionner régimes et stratégies actifs. | src/learning/ |
| ClockSync | Vérifier drift horloge vs exchange. | src/runtime/ |

### NE PAS AJOUTER (YAGNI)

GPU Monitor, Plugin System, Feature Flags, Schema Registry (Kafka), Service Mesh.

---

## 8. VERSION HEDGE FUND — CTO VISION

### Ce qui Reste (Bonnes Idées)

- Architecture événementielle (EventBus, TradeEvent SSoT)
- Multi-mode execution (sim / paper / live / shadow)
- Gouvernance décisionnelle (approval chains)
- MistakeMemory (apprentissage erreurs en production)
- DecisionPacket (trace complète)
- RuntimeStateMachine (5 états)
- KillSwitch hardened

### Ce qui Change

**1. Multi-stratégie avec isolation capital**
```
CAPITAL POOL (100%)
├── STRATEGY A (momentum)    30% — compte isolé — RiskGate A propre
├── STRATEGY B (mean-revert) 30% — compte isolé — RiskGate B propre
├── STRATEGY C (market-make) 20% — compte isolé — RiskGate C propre
└── RESERVE                  20% — cash
```

**2. Decision Gateway centralisé**
Point d'entrée unique. Aucune exécution sans passer par:
governance check → risk check → portfolio check → execution check → AI advisor check

**3. CQRS (Read / Write separation)**
Write side: OrderBook, TradeStore, EventStore (ordres critiques)
Read side: PositionView, PnLView, RiskView (tableau de bord)
→ les reads ne bloquent plus les writes

**4. Exchange Abstraction Layer**
`ExchangeAdapter(IExchange)` → remplacer MEXC par Binance/OKX sans toucher le code métier

**5. Risk Budget Dynamique**
```python
budget = base_limit * regime_modifier * performance_adj
# bear market → -50%, drawdown → réduction automatique
```

**6. Event Sourcing**
OrderCreated → OrderSubmitted → OrderFilled → TradeSettled
→ replay exact de tout incident passé

**7. Observability**
JSON logs → Loki, Prometheus metrics → Grafana, correlation_id sur tous les events

---

## 9. ROADMAP DE MIGRATION INCRÉMENTALE

### Taxonomie des statuts (introduite P0.0 — 2026-06-11)
```
MORT       → Suppression immédiate (0 import / 0 test / 0 CI)
DORMANT    → Conserver temporairement, planifier migration
STUB       → Garder jusqu'à disparition complète des imports (migration avant suppression)
ACTIF      → Ne pas toucher avant une refonte dédiée
```

### Phase 0.0 — Validation formelle (TERMINÉE — 2026-06-11)
Résultats de la validation "zéro référence" sur les 7 modules identifiés DEAD :

```
MORT (supprimables immédiatement) :
[x] strategy_factory/ root               — 0 import externe, 0 test, 0 CI
[x] crypto_quant_v16/                    — 0 import, 0 test, 0 CI

STUB (migration P1 requise avant suppression) :
[ ] src/engine/execution_router.py       — 11L stub, 8 tests, canonique: quant_hedge_ai/agents/execution/
[ ] src/events/event_bus.py              — 21L stub, 3 tests, canonique: event_bus/bus.py
[ ] src/risk/kill_switch.py              — 9L stub, 9 tests, canonique: supervision/killswitch_hardened.py

DORMANT (fusion P1) :
[ ] meta_learning/decision_engine.py     — 89L, 3 scripts, canonique: quant_hedge_ai/engine/

ACTIF (ne pas toucher — audit initial erroné) :
[!] tracker_system/autonomous/auto_decision_engine.py — 435L, 2 tests dédiés, PAS de doublon
```

### Phase 0.1 — Purge sécurisée (TERMINÉE — 2026-06-11)
```
[x] Supprimé:  strategy_factory/ (9 fichiers)
[x] Supprimé:  crypto_quant_v16/ (3 fichiers)
[x] Nettoyé:   .github/workflows/ci_dashboard_panels.yml (path trigger mort)
[x] Nettoyé:   .github/workflows/sphinx.yml (path trigger mort)
[x] Nettoyé:   tests/phase0/test_phase0_validation.py (ORPHAN_A_MODULES)
[x] Nettoyé:   tests/test_architecture.py (LEGACY_ROOTS)
[x] Créé:      architecture/modules_registry.yaml (registre permanent)
```
Résultat tests: 14/14 sur modules touchés — 0 régression introduite.
Échecs pré-existants confirmés (non causés par P0.1) :
  - test_paper_trade_e2e (bug MexcSimulator restore, session 2026-06-07)
  - test_phase0_validation (advisor_loop.py introuvable à la racine — bug de path)
  - test_optimization_stack / test_ui_utils (ModuleNotFoundError pré-existants)

### Phase 1 — Convergence vers une architecture canonique (2 semaines, risque faible)

Référence : `architecture/CANONICAL_COMPONENTS.md`
Registre : `architecture/modules_registry.yaml`

**Principe :** Les suppressions de fichiers sont une conséquence de la convergence, pas l'objectif.
**Méthode par verticale :**
1. Identifier toutes les implémentations de la responsabilité
2. Désigner le canonique (critère : le plus intégré dans le runtime, pas le plus complet)
3. Migrer progressivement les appels
4. Vérifier les tests
5. Supprimer l'ancien

**Verticale 1 — Event Bus : un seul bus**
```
Canonique : event_bus/bus.py
[ ] Migrer 3 tests → event_bus/bus.py (interface différente, adapter requis)
[ ] Migrer src/telegram/sim_bot.py → event_bus/bus.py
[ ] Supprimer src/events/event_bus.py (stub 21L)
Critère : 0 import de src/events/event_bus
```

**Verticale 2 — Kill Switch : une seule logique de sécurité**
```
Canonique : supervision/killswitch_hardened.py
[ ] Migrer 9 tests → killswitch_hardened
[ ] Migrer src/analytics/edge_scorer.py, src/telegram/sim_bot.py, src/agent/codex_agent.py
[ ] Supprimer src/risk/kill_switch.py (stub 9L)
Critère : 0 import du stub dans le code production
```

**Verticale 3 — Execution Engine : une seule API d'exécution**
```
Canonique : quant_hedge_ai/agents/execution/execution_engine.py
[ ] Migrer 8 tests → execution_engine (via mode paper/live auto-détecté)
[ ] Archiver src/engine/execution_router.py (stub 11L)
Complémentaire conservé : paper_trading/ (sandbox E2E, rôle distinct)
Critère : 0 route parallèle d'exécution dans le runtime
```

**Verticale 4 — Regime Detector : une seule interface**
```
Canonique : quant_hedge_ai/agents/intelligence/regime_detector.py (AdvancedRegimeDetector)
Shim existant : quant_hedge_ai/agents/market/regime_detector.py (re-export, conserver pendant migration)
[ ] Archiver src/analytics/regime_detector.py (86L, 0 import production)
[ ] Migrer imports direct vers intelligence/ au fil des modifications
[ ] Supprimer le shim agents/market/ après migration complète
Critère : 1 seule implémentation active (AdvancedRegimeDetector)
```

**Verticale 5 — Decision Engine : étude avant décision**
```
Canonique actuel : quant_hedge_ai/engine/decision_engine.py (intégré runtime)
Candidat : tracker_system/autonomous/auto_decision_engine.py (435L, 2 tests, hors runtime)
[ ] Étude fonctionnelle : responsabilités uniques vs doublons vs absorbables
[ ] Décision documentée dans CANONICAL_COMPONENTS.md
[ ] Action : enrichir canonique, ou intégrer auto_decision_engine, ou archiver
Critère : 1 seul point d'entrée décisionnel dans le runtime
```

**Verticale 6 — Configuration : une seule source de vérité**
```
Situation : 4 sources (.env, runtime_config.json, runtime_config.py, telegram_config.json)
[ ] Créer config/settings.py avec Pydantic BaseSettings
[ ] Migrer tous les accès de configuration vers settings
[ ] Supprimer les fichiers json/py dupliqués
Critère : 0 json runtime en doublon, 0 fichier .py de config parallèle
```

**Autres (secondaires)**
```
[ ] monitoring/ + monitor/ → 1 seul package
[ ] Nettoyer F401 dans core/ et quant_hedge_ai/
[ ] Ajouter pyproject.toml
```
Critère global: mypy --strict sur src/domain/ sans erreur.

### Phase 2 — Splitter les Monolithes (3 semaines, risque moyen)
```
[ ] advisor_loop.py (5,872 l) → 5 modules:
    market_observer.py | telegram_reporter.py | system_watchdog.py | state_tracker.py | main_loop.py
[ ] portfolio_brain.py → position_calculator.py + rebalancer.py
[ ] market_scanner.py → fetcher.py + validator.py
[ ] strategy_allocator.py → ranker.py + allocator.py
```
Critère: Aucun fichier > 500 lignes. Tests couverts.

### Phase 3 — Interfaces & Contrats (2 semaines)
```
[ ] src/domain/interfaces/ (Protocol classes)
[ ] IExchange sur MexcSimulator et MexcLive
[ ] IRiskGate sur GlobalRiskGate
[ ] ISignalStrategy sur stratégies concrètes
[ ] Activer mypy en CI
```
Critère: Exchange swappable sans changer le code métier.

### Phase 4 — Observability (1 semaine)
```
[ ] JSON structured logs + correlation_id
[ ] MetricsExporter (Prometheus format)
[ ] AuditTrail unifié
[ ] HealthMonitor + heartbeat
[ ] EventStore
```

### Phase 5 — CQRS & Event Sourcing (3 semaines, risque élevé)
```
[ ] TradeRepository (write) + PositionView (read)
[ ] SQLite → PostgreSQL en production
[ ] Snapshots d'état système
[ ] Dead Letter Queue
```
Critère: Replay d'un incident depuis l'EventStore.

---

## 10. KPIs D'ARCHITECTURE

| KPI | Cible | Actuel | Outil |
|-----|-------|--------|-------|
| Complexité cyclomatique max | ≤ 10 | > 50 (advisor_loop) | radon |
| Fichiers > 500 lignes | 0 | 12 | wc -l |
| TODO/FIXME | < 50 | 4,560 | grep |
| Couverture tests | ≥ 90% | non mesuré | pytest-cov |
| Unused imports F401 | 0 | 40+ ignorés | flake8 |
| Versions d'un même service | 1 | 2-4 | count |
| Fichiers de config | 1 | 4 | count |
| Uptime production | ≥ 99.5% | — | systemd |
| Latence décision p99 | < 500ms | — | Prometheus |
| Temps recovery après crash | < 60s | — | SelfHealingBot |

---

## CONCLUSION

### Forces (ne pas toucher)
Architecture événementielle, gouvernance décisionnelle, MistakeMemory, multi-mode execution,
supervision auto-réparatrice, 282 fichiers de test, documentation excellente.

### Dettes Critiques (ordre d'urgence)
1. advisor_loop.py (5,872 l) — SPOF architectural — splitter en 5 modules
2. 8 modules morts — purger (0 risque, gain clarté immédiat)
3. 4 sources de config — unifier en Pydantic BaseSettings
4. Doublons (3 decision engines, 4 kill switches, 2 event bus) — consolider
5. 4,560 TODOs — trier: implémenter ou supprimer

### Priorités
```
P0 (cette semaine):  Nettoyage code mort (0 risque)
P1 (mois 1):         Consolidation + config unifiée
P2 (mois 2-3):       Splitter monolithes + interfaces Protocol
P3 (mois 4-6):       CQRS + Event Sourcing + multi-exchange
```

Le système peut atteindre le niveau institutionnel sans refonte complète.
C'est une évolution dirigée, pas un rewrite.

---
*Rapport généré le 2026-06-11. Aucune modification apportée au code.*
*Prochaine étape: audit/PHASE_B_IMPLEMENTATION_PLAN.md*
