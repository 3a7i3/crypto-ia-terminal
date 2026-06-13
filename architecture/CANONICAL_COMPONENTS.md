# CANONICAL COMPONENTS — crypto_ai_terminal
**Établi : 2026-06-11 | Mis à jour : 2026-06-12 | Phase P1 — VERROUILLÉ**

## Règle d'architecture

> Une responsabilité → une interface publique → une implémentation canonique → plusieurs extensions possibles via plugins ou stratégies.

Toute nouvelle implémentation d'une responsabilité listée ici constitue une violation d'architecture.
Toute revue de code doit vérifier qu'aucune implémentation concurrente n'est introduite.

---

## Pipeline d'exécution canonique

```
──────────────────────────── RUNTIME LIVE ──────────────────────────────

Signal d'entrée (prix, volume, indicateurs)
        │
        ▼
AdvancedRegimeDetector          quant_hedge_ai/agents/intelligence/regime_detector.py
        │ régime (bull/bear/sideways/high_vol/flash_crash)
        ▼
DecisionEngine + Decision Layer quant_hedge_ai/engine/decision_engine.py
        │ TradeGateDecision (STOP_TRADING / ALLOW / REDUCE_RISK)
        ▼
GlobalRiskGate (5 vérifications) quant_hedge_ai/agents/risk/global_risk_gate.py
        │ allowed=True requis
        ▼
KillSwitchHardened              supervision/killswitch_hardened.py
        │ is_halted()=False requis, état persistant
        ▼
ExecutionEngine                 quant_hedge_ai/agents/execution/execution_engine.py
        │ SessionGuard + OrderDeduplicator + OrderValidator
        ▼
CCXT (live) / paper mode
        │
        ▼
Runtime EventBus (singleton)    event_bus/bus.py
        │ OrderFilledEvent, PositionOpenedEvent, ...

──────────────────────────── SIMULATION ────────────────────────────────

BacktestEngine / SimBot
        │
        ▼
VirtualExchange                 src/engine/virtual_exchange.py
        │
        ▼
SimEventBus (instance locale)   src/events/event_bus.py
        │ TRADE_OPENED, TRADE_CLOSED (dict-based, isolation par run)
```

---

## Tableau de progression P1 — ÉTAT FINAL

| Verticale        | Canonique défini | Runtime câblé | Tests intégration  | Dette P2               |
|------------------|:----------------:|:-------------:|:------------------:|------------------------|
| Decision Layer   | ✅               | ✅            | ✅ 18 tests DL-01→05 | Renommage `trade_gate.py` |
| Event Bus        | ✅               | ✅            | ✅ garde-fou CI     | —                       |
| Execution Engine | ✅               | ✅            | ✅ risk gate vérifié | `ExecutionEngineProtocol` |
| Kill Switch      | ✅               | ✅            | ✅ 7 tests restart  | `KillSwitchAuthority`   |
| Regime Detector  | ✅               | ✅            | ✅ (bug bear corrigé) | Shim à supprimer       |

---

## Table des composants canoniques

| Responsabilité       | Implémentation canonique    | Chemin                                                     | Statut P1      |
|----------------------|-----------------------------|------------------------------------------------------------|----------------|
| Runtime Event Bus    | `EventBus`                  | `event_bus/bus.py`                                         | ✅ Verrouillé   |
| Simulation Event Bus | `SimEventBus`               | `src/events/event_bus.py`                                  | ✅ Verrouillé   |
| Kill Switch          | `KillSwitchHardened`        | `supervision/killswitch_hardened.py`                       | ✅ Verrouillé   |
| Execution Engine     | `ExecutionEngine`           | `quant_hedge_ai/agents/execution/execution_engine.py`      | ✅ Verrouillé   |
| Paper Mode (runtime) | `PaperTradingEngine`        | `quant_hedge_ai/agents/execution/paper_trading_engine.py`  | ✅ Verrouillé   |
| Burn-in Simulation   | `BurninSimulationEngine`    | `paper_trading/engine.py`                                  | ✅ Verrouillé   |
| Regime Detector      | `AdvancedRegimeDetector`    | `quant_hedge_ai/agents/intelligence/regime_detector.py`    | ✅ Verrouillé   |
| Decision Engine      | `DecisionEngine`            | `quant_hedge_ai/engine/decision_engine.py`                 | ✅ Verrouillé   |
| Feature Pipeline     | `FeatureMaterializer`       | `quant_hedge_ai/features/`                                 | ✅ Verrouillé   |
| Runtime State        | `RuntimeStateMachine`       | `system/state_machine.py`                                  | ✅ Canonique    |
| Global Risk Gate     | `GlobalRiskGate`            | `quant_hedge_ai/agents/risk/global_risk_gate.py`           | ✅ Canonique    |
| Configuration        | —                           | À créer : `config/settings.py`                             | ❌ P2           |

---

## Détail par verticale

---

### Event Bus

**Décision architecturale (2026-06-12) :** deux bus légitimes, scopes distincts.

| Bus | Implémentation | Cycle de vie | API événements | Garde-fou |
|---|---|---|---|---|
| Runtime | `event_bus/bus.py::EventBus` | Singleton process | `BaseEvent` typé | — |
| Simulation | `src/events/event_bus.py::SimEventBus` | Instance par run | `dict {"type": ...}` | `test_structural_sim_bus.py` |

**Invariant garanti par CI :**
> `SimEventBus` n'est jamais importé dans `quant_hedge_ai/`, `supervision/`, `pieuvre/`, `infra/`, `core/`, `event_bus/`.

**Composants legacy supprimés / clarifiés :**
- `supervision/telegram_kill_switch.py` → remplacé par `KillSwitchHardened` dans le runtime

**Dette P2 :** aucune (séparation fondée, pas cosmétique).

---

### Kill Switch

**Décision architecturale (2026-06-12) :** `KillSwitchHardened` est l'implémentation canonique du runtime.

**Propriétés vérifiées par tests :**

| Invariant | Test | Statut |
|---|---|---|
| KS-01 Persistance restart | `test_killswitch_restart_persistence.py` | ✅ |
| KS-02 Autorité unique | imports vérifiés | ✅ |
| KS-03 Compatibilité API | `is_execution_allowed()` ajouté | ✅ |
| KS-04 Cycle STOP→HALT→RESUME | test intégration | ✅ |

**Points d'entrée runtime (après promotion) :**
- `core/advisor_runtime_adapters.py` → `KillSwitchHardened as TelegramKillSwitch`
- `quant_hedge_ai/main_v91.py` → `KillSwitchHardened()`

**Composants legacy conservés (simulation/test) :**
- `src/risk/kill_switch.py` — stub minimal pour les tests de simulation (`src/`)
- `supervision/kill_switch.py` — variante legacy, non importée par le runtime
- `supervision/telegram_kill_switch.py` — non importée par le runtime (remplacée)

**Dette P2 — KS-P2-01 :**
> Introduire un `KillSwitchAuthority` qui centralise les 5 sources de blocage
> (KillSwitch, RuntimeStateMachine, SelfAwarenessEngine, ExecutiveOverride, GlobalRiskGate)
> et expose la liste des bloqueurs actifs. Améliore la lisibilité opérationnelle,
> n'est pas une condition de sécurité.

---

### Execution Engine

**Canonique :** `quant_hedge_ai/agents/execution/execution_engine.py::ExecutionEngine`

**Clarification (2026-06-12) :**

| Composant | Fichier | Scope | Statut |
|---|---|---|---|
| `ExecutionEngine` | `quant_hedge_ai/agents/execution/execution_engine.py` | Runtime live/paper | ✅ Canonique |
| `PaperTradingEngine` | `quant_hedge_ai/agents/execution/paper_trading_engine.py` | Mode paper boucle principale | ✅ Canonique |
| `BurninSimulationEngine` | `paper_trading/engine.py` | Burn-in P5, observation | ✅ Distinct (renommé) |

**Risk gate non contournable (vérifié) :**
```
SessionGuard → OrderDeduplicator → OrderValidator → OrderRateLimiter
```
Toutes lèvent une exception si elles échouent. Aucun ordre possible sans passer la chaîne.

**Dette P2 — EXE-P2-01 :**
> Introduire `ExecutionEngineProtocol` (ABC/Protocol) quand plusieurs
> implémentations devront être substituables (live, paper, replay).
> Aujourd'hui duck-typed — acceptable tant qu'une seule implémentation existe.

---

### Regime Detector

**Canonique :** `quant_hedge_ai/agents/intelligence/regime_detector.py::AdvancedRegimeDetector`
- 5 régimes : `bull_trend`, `bear_trend`, `sideways`, `high_volatility`, `flash_crash`
- Bug `bear_trend` corrigé (logique inversée)

**Shim de rétro-compatibilité (à supprimer P2) :**
- `quant_hedge_ai/agents/market/regime_detector.py` — 9 lignes, re-exporte `AdvancedRegimeDetector as RegimeDetector`

**Legacy archivé :**
- `src/analytics/regime_detector.py` — 3 régimes, 0 import production

---

### Decision Layer

**Canonique :** `quant_hedge_ai/engine/decision_engine.py::DecisionEngine`

**18 tests d'intégration (DL-01→DL-05) :** vérifient que `STOP_TRADING` se propage à la `state_machine`, que la réduction de risque influence la taille des ordres, que le garde-fou 5 trades est respecté, et que le câblage `advisor_loop` est opérationnel.

**Dette cosmétique (non bloquante) :** renommage `decision_engine.py` → `trade_gate.py` différé à P2.

---

## Processus d'ajout d'un nouveau composant

Avant de créer une nouvelle implémentation d'une responsabilité existante :

1. Vérifier si la responsabilité est déjà couverte dans ce document.
2. Si oui : utiliser le canonique ou créer un plugin/stratégies.
3. Si non : ajouter l'entrée dans ce document **avant** d'écrire le code.
4. Enregistrer le module dans `architecture/modules_registry.yaml`.

**Un composant non enregistré = dette technique par défaut.**

---

## Composants sans doublon (ne pas modifier sans revue)

| Composant | Chemin | Note |
|---|---|---|
| Portfolio Brain | `quant_hedge_ai/agents/risk/portfolio_brain.py` | Monolithe 740L, à splitter P2 |
| Market Scanner | `quant_hedge_ai/agents/market/market_scanner.py` | Monolithe 829L, à splitter P2 |
| Global Risk Gate | `quant_hedge_ai/agents/risk/global_risk_gate.py` | Canonique unique |
| Governance | `governance/` | Canonique unique |
| Audit Trail | `governance/audit_trail.py` | Canonique unique |
| Error Bus | `errors/error_bus.py` | Canonique unique |
| Heartbeat | `observability/heartbeat_system.py` | Canonique unique |

---

## Backlog P2

| Référence | Description | Déclencheur |
|---|---|---|
| EXE-P2-01 | `ExecutionEngineProtocol` (ABC) | Quand ≥2 implémentations substituables |
| KS-P2-01 | `KillSwitchAuthority` centralisant les 5 sources de blocage | Avant P3 live |
| RD-P2-01 | Supprimer le shim `agents/market/regime_detector.py` | Après migration imports directs |
| DL-P2-01 | Renommer `decision_engine.py` → `trade_gate.py` | Après stabilisation P2 |
| CFG-P2-01 | Créer `config/settings.py` (Pydantic BaseSettings) | Avant live réel |
