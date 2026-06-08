# ARCHITECTURE — crypto_ai_terminal

> Version : 1.0 | Date : 2026-06-01
> Source de vérité : ce fichier + `docs/SYSTEM_INVARIANTS.md` + `core/invariants.py`

---

## 1. Pipeline décisionnel — flux nominal

```
                    ┌─────────────────────────────────────────────────────┐
                    │              CYCLE advisor_loop                      │
                    │  (trace_id unique · RuntimeStateMachine · heartbeat) │
                    └───────────────────────┬─────────────────────────────┘
                                            │  DecisionPacket(CREATED)
                                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  COUCHE 1 — SIGNAL                                                       │
│  LiveSignalEngine + FeatureEngineer + RegimeDetector                     │
│  Responsabilité : générer le signal brut, calculer les features ML        │
│  Sortie : packet.side, packet.confidence, packet.features, packet.regime  │
│  State : CREATED → SIGNAL_GENERATED → CONTEXT_ENRICHED                   │
└───────────────────────────┬────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  COUCHE 2 — INTELLIGENCE (agents/intelligence/)                          │
│  AIAdvisor · DecisionArbitrator · ConvictionEngine · NoTradeLayer        │
│  SelfAwarenessEngine · MistakeMemory · MetaStrategyEngine                │
│  Responsabilité : enrichir le packet, voter, calculer la conviction       │
│  Sortie : packet.conviction, packet.reasoning[], AgentVote[]              │
│  State : CONTEXT_ENRICHED → REGIME_VALIDATED → RISK_EVALUATED            │
│  INVARIANT : un veto (AgentVote.veto=True) est terminal immédiatement    │
└───────────────────────────┬────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  COUCHE 3 — RISK GATE                                                    │
│  GlobalRiskGate · SessionGuard · DrawdownGuard · OrderDeduplicator       │
│  Responsabilité : SEUL module autorisé à rejeter (GateResult.allowed)    │
│  Sortie : packet → APPROVED ou REJECTED                                  │
│  State : RISK_EVALUATED → APPROVED | REJECTED                            │
│  INVARIANT : GlobalRiskGate ne calcule pas de taille                     │
└───────────────────────────┬────────────────────────────────────────────┘
                            │  (si APPROVED)
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  COUCHE 4 — PORTFOLIO BRAIN                                              │
│  PortfolioBrain · CapitalAllocationEngine · ExposureManager              │
│  Responsabilité : 8 checks portefeuille (exposition/corr/concentration)  │
│  Sortie : allocation_pct, peut rejeter via packet.reject()               │
│  INVARIANT : PortfolioBrain ne connaît pas le sizing individuel          │
└───────────────────────────┬────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  COUCHE 5 — ORDER SIZER                                                  │
│  OrderSizer · DrawdownGuard · KellyCriterion                             │
│  Responsabilité : calculer la taille en USD. NE REJETTE JAMAIS.          │
│  Sortie : packet.features["os_size_usd"] dans [min_size, max_size]       │
│  INVARIANT : OrderSizer ne lève pas SessionHaltedError                   │
└───────────────────────────┬────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  COUCHE 6 — EXÉCUTION                                                    │
│  ExecutionEngine · PaperTradingEngine · ShadowEngine                     │
│  Responsabilité : engager le capital. Ne décide pas du signal.           │
│  State : APPROVED → EXECUTION_PENDING → EXECUTED                         │
│  INVARIANT : ExecutionEngine n'importe pas LiveSignalEngine              │
└───────────────────────────┬────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  COUCHE 7 — POST-TRADE                                                   │
│  PositionManager · TradeLogger · PostmortemAnalyzer · DecisionQuality    │
│  State : EXECUTED → MONITORED → CLOSED → POSTMORTEM_ANALYZED            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Fault Containment Zones

```
┌────────────────────────────────────────────────────────────────┐
│  ZONE EXECUTION   — timeout 200ms — échec = reject silencieux  │
│    ExecutionEngine, OrderDeduplicator, PositionManager         │
├────────────────────────────────────────────────────────────────┤
│  ZONE RISK        — timeout 100ms — échec = ordre REJETÉ       │
│    SessionGuard, DrawdownGuard, RiskMonitor                    │
├────────────────────────────────────────────────────────────────┤
│  ZONE AI_SCORING  — timeout 500ms — échec = fallback HOLD      │
│    LiveSignalEngine, FeatureEngineer, RegimeDetector           │
├────────────────────────────────────────────────────────────────┤
│  ZONE MONITORING  — timeout 2s   — échec = silencieux          │
│    LatencyMonitor, MetricsBus, ErrorBus, EventJournal          │
├────────────────────────────────────────────────────────────────┤
│  ZONE DASHBOARD   — timeout 5s   — échec = totalement ignoré   │
│    Telegram, Streamlit, dashboard_positions.py                 │
└────────────────────────────────────────────────────────────────┘
```

Règle : une panne dans la zone N ne peut jamais bloquer la zone N-1 (priorité supérieure).
Voir `quant_hedge_ai/runtime/fault_containment.py`.

---

## 3. Machine d'état runtime (5 états)

```
NORMAL ──(≥3 err/60s)──► DEGRADED ──(≥7 err/60s)──► CRITICAL ──(≥10 err/60s)──► SAFE_MODE
  ▲                          │                           │                            │
  │                    (0 err + 30s)              (0 err + 30s)               (0 err + 60s)
  │                          ▼                           ▼                            ▼
  └──────────────────── RECOVERY ◄─────────────────────────────────────────────────────
                             │
                      (60s stable)
                             ▼
                           NORMAL
```

| État | can_trade | can_fetch | size_factor |
|------|-----------|-----------|-------------|
| NORMAL | ✅ | ✅ | 1.0 |
| DEGRADED | ✅ | ✅ | **0.5** |
| CRITICAL | ❌ | ✅ | 0.0 |
| SAFE_MODE | ❌ | ❌ | 0.0 |
| RECOVERY | ❌ | ✅ | 0.0 |

Source : `quant_hedge_ai/runtime/runtime_state_machine.py`
Re-export : `core/runtime_state_machine.py`

---

## 4. Invariants architecturaux (résumé)

Les invariants sont exécutables via `core/invariants.py::verify_architecture()`.
Voir `docs/SYSTEM_INVARIANTS.md` pour les invariants runtime (I-01..I-12).

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| A-01 | DecisionPacket.lifecycle_state mutable uniquement via `transition_to()` | RuntimeError |
| A-02 | OrderSizer calcule uniquement — jamais de rejet | Inspection source |
| A-03 | GlobalRiskGate expose `check()` → GateResult | Interface check |
| A-04 | ExecutionEngine n'importe pas LiveSignalEngine | Inspection source |
| A-05 | SAFE_MODE : can_trade=False, can_fetch=False, size_factor=0.0 | Assertion |
| A-06 | DEGRADED : can_trade=True, size_factor=0.5 | Assertion |
| A-07 | DecisionPacket expose `seal()` et `is_sealed()` | Interface check |
| A-08 | Transition depuis état terminal lève RuntimeError | Comportement attendu |

---

## 5. Fichiers canoniques

| Rôle | Fichier |
|------|---------|
| Colonne vertébrale décisionnel | `core/decision_packet.py` |
| Types partagés inter-stacks | `core/contracts.py` |
| Machine d'état runtime | `quant_hedge_ai/runtime/runtime_state_machine.py` |
| Invariants architecturaux | `core/invariants.py` |
| Isolation des pannes | `quant_hedge_ai/runtime/fault_containment.py` |
| Journal des transitions | `quant_hedge_ai/runtime/event_journal.py` |
| Orchestration principale | `core/advisor_loop.py` |
| Logger canonique | `observability/json_logger.py` |

---

## 6. Convention d'import

```python
# Types partagés → toujours depuis core
from core.decision_packet import DecisionPacket, DecisionState, DecisionSide
from core.contracts import GateResult, TradeSignal
from core.runtime_state_machine import RuntimeStateMachine, SystemState

# Agents → depuis leur namespace propre
from quant_hedge_ai.agents.risk.global_risk_gate import GlobalRiskGate
from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

# Observabilité → depuis observability/
from observability.json_logger import get_logger
```

**Règle :** jamais `from quant_hedge_ai.agents.execution import *`.
**Règle :** jamais de pandas/numpy/torch dans `core/decision_packet.py` ou `core/contracts.py`.

---

## 7. Règles de nommage pour les nouveaux modules

| Couche | Préfixe/Suffixe attendu | Exemple |
|--------|------------------------|---------|
| Agent décisionnel | `*_engine.py`, `*_layer.py` | `conviction_engine.py` |
| Gate / garde | `*_guard.py`, `*_gate.py` | `session_guard.py` |
| Orchestrateur | `*_advisor.py`, `*_loop.py` | `ai_advisor.py` |
| Mémoire / apprentissage | `*_memory.py`, `*_brain.py` | `mistake_memory.py` |
| Dashboard | `dashboard_*.py` | `dashboard_risk.py` |
| Test | `test_*.py` | `test_invariants.py` |

**Règle :** un nouveau module doit répondre aux 7 questions du Layer Governance Checklist
(`docs/` → `Layer Governance Checklist`) avant d'être fusionné.

---

## 8. Chantiers ouverts

Voir [docs/DUPLICATION_AUDIT.md](DUPLICATION_AUDIT.md) pour les doublons identifiés.
Voir [docs/INTELLIGENCE_SPLIT_PROPOSAL.md](INTELLIGENCE_SPLIT_PROPOSAL.md) pour la restructuration d'`intelligence/`.
