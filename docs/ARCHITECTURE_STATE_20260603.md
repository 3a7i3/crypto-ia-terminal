# ARCHITECTURE STATE — 2026-06-03

> Snapshot de l'état réel du système à la date du rapport.  
> Ce document représente ce qui est **implémenté et testé**, pas ce qui est prévu.

---

## 1. VUE D'ENSEMBLE

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CRYPTO AI TERMINAL                             │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │  GOVERNANCE  │   │   CORE PIPELINE  │   │   PAPER TRADING    │  │
│  │  G0 → G8-E   │──▶│  advisor_loop   │──▶│  VirtualPortfolio  │  │
│  │  (certifié)  │   │  (VPS actif)    │   │  MexcSimulator     │  │
│  └──────────────┘   └──────────────────┘   └────────────────────┘  │
│          │                   │                       │              │
│  ┌───────▼───────┐  ┌────────▼────────┐  ┌──────────▼──────────┐  │
│  │ GovernanceKer │  │  DecisionPacket │  │  infra/mexc_reader  │  │
│  │ nel (ATC)     │  │  (lifecycle S4) │  │  (read-only)        │  │
│  │ Z3 proofs     │  │  DPSS + STI     │  │  ccxt MEXC          │  │
│  └───────────────┘  └─────────────────┘  └─────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  RISK LAYERS                                                  │  │
│  │  GlobalRiskGate → PortfolioBrain → ExecutiveOverride         │  │
│  │  SessionGuard → OrderSizer → DrawdownGuard                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. COUCHE GOUVERNANCE (G0→G8-E)

### État : CERTIFIÉ — 160 tests passés, 1 xfail (dette connue)

| Gate | Identifiant | Module | Statut | Tests |
|------|------------|--------|--------|-------|
| G0 | Trace Integrity | `observability/json_logger.py` | ✅ HARD + Z3 | I-16, test_z3 |
| G1 | Runtime Authority (ATC) | `core/authority.py` | ✅ HARD + Z3 | I-15 Layer 1-2 |
| G2 | Authority State | `governance/authority_state.py` | ✅ HARD | I-15 Layer 1 |
| G3 | Status Dashboard | `governance/status_dashboard.py` | ✅ Opérationnel | — |
| G4 | Decision Trace | `governance/decision_trace.py` | ✅ Opérationnel | — |
| G5 | Kelly Gate | `quant_hedge_ai/agents/risk/order_sizer.py` | ✅ HARD + Z3 | test_z3 |
| G8-D | Pipeline Sync | `core/advisor_loop.py` | ✅ HARD + Z3 | test_z3 |
| G8-E | Packet Presence | `core/advisor_loop.py` | ✅ HARD + Z3 | test_z3 |

### Authority Levels (TRADING_POLICY)

| Niveau | can_trade | can_fetch_data | size_factor |
|--------|-----------|---------------|------------|
| EMERGENCY | ✗ | ✗ | 0.0 |
| SAFE_MODE | ✗ | ✗ | 0.0 |
| RESTRICTED | ✗ | ✓ | 0.0 |
| WARNING | ✓ | ✓ | 0.5 |
| CLEAR | ✓ | ✓ | 1.0 |

---

## 3. COUCHE CORE

### RuntimeStateMachine (RSM)

```
États :  NORMAL → DEGRADED → CRITICAL → SAFE_MODE
                     ↑              ↓
                  RECOVERY ←────────┘

Politiques :
  NORMAL    → can_trade=True,  size_factor=1.0
  DEGRADED  → can_trade=True,  size_factor=0.5
  CRITICAL  → can_trade=False, size_factor=0.0
  SAFE_MODE → can_trade=False, can_fetch=False, size_factor=0.0
  RECOVERY  → can_trade=False, size_factor=0.0
```

**Module :** `quant_hedge_ai/runtime/runtime_state_machine.py`  
**Re-export :** `core/runtime_state_machine.py`  
**Thread-safe :** Oui (threading.Lock)

### GovernanceKernel (ATC)

```python
# core/authority.py
init_authority(rsm)     # Obligatoire au boot — une seule fois
get_authority()         # Lève RuntimeError si non-initialisé
get_authority().can_trade()         # → bool
get_authority().can_place_order()   # can_trade AND NOT RECOVERY
get_authority().size_factor()       # → float [0.0, 1.0]
get_authority().snapshot()          # → dict pour observabilité
```

**Invariant ATC :** Impossible d'appeler le pipeline sans autorité initialisée.

### DecisionPacket Lifecycle (S4)

```
CREATED
  ↓
SIGNAL_GENERATED
  ↓
CONTEXT_ENRICHED
  ↓ (optionnel)       ↓ (court-circuit)
REGIME_VALIDATED  →  RISK_EVALUATED
                          ↓
                      APPROVED
                          ↓
                    EXECUTION_PENDING
                          ↓
                       EXECUTED
                          ↓
                       MONITORED
                          ↓
                         CLOSED
                          ↓
                  POSTMORTEM_ANALYZED  (terminal nominal)

États terminaux exceptionnels (depuis tout état non-terminal) :
  REJECTED / EXPIRED / CANCELLED / FAILED / VETOED
```

**Source unique :** `core/lifecycle.py` (ALLOWED_TRANSITIONS)  
**Hash chain :** SHA-256 sur chaque StateTransition — audit trail inviolable

### CheckPriority (SEP — ordre lexicographique strict)

```
P10  G1_RUNTIME_AUTHORITY     RSM.can_trade() + GovernanceKernel
P20  G4_GLOBAL_RISK_GATE      gate_result.allowed
P30  I14_CONVICTION           conviction fail-closed
P31  I14_PORTFOLIO_BRAIN      portfolio_brain fail-closed
P32  I14_AWARENESS            awareness fail-closed
P33  I14_NO_TRADE             no_trade_layer fail-closed
P34  I14_MISTAKE_MEMORY       mistake_memory fail-closed
P35  I14_EXEC_OVERRIDE        executive_override fail-closed
P36  I14_THREAT_RADAR         threat_radar fail-closed
P40  G8_D_PIPELINE_SYNC       sync trade_allowed → packet.reject()
P50  G8_E_PACKET_PRESENCE     _dp is not None
P60  G0_TRACE_ID              trace_id présent dans metadata
P70  G8_C_PACKET_ACTIONABLE   packet.is_actionable()
```

### EIC v2 (Execution Initialization Contract)

```
VALIDITY = AST_OK ∧ IMPORT_GRAPH_OK ∧ RUNTIME_PARITY_OK

Tier 1 — IMPORT_SAFE     : constantes, dataclasses, getLogger(), env read
Tier 2 — RUNTIME_INIT    : makedirs, load_dotenv, basicConfig → dans main()
Tier 3 — GATE_REQUIRED   : compute_features(), exchange I/O → après can_trade()

Violations documentées (KNOWN_SIDE_EFFECTS, compliant=False) :
  - os.makedirs("logs")           @ core/advisor_loop.py:59
  - load_dotenv(override=True)    @ core/advisor_loop.py:167
  - logging.basicConfig(...)      @ core/advisor_loop.py:175
```

---

## 4. COUCHE RISK

### GlobalRiskGate

**Module :** `quant_hedge_ai/agents/risk/global_risk_gate.py`  
**5 conditions pré-trade :**
1. Session non halted (SessionGuard)
2. Drawdown session acceptable (DrawdownGuard)
3. Score signal suffisant (LiveSignalEngine)
4. Signal confirmé multi-timeframes
5. Régime de marché non blacklisté

**API décision :** `check_packet(packet)` — applique RISK_EVALUATED → APPROVED ou REJECTED  
**Invariant :** I-07 HARD — gate blocked = trade impossible

### PortfolioBrain

**Module :** `quant_hedge_ai/agents/risk/portfolio_brain.py`  
**8 checks :**
1. Exposition totale (notionnel/capital)
2. Corrélation BTC/ETH/SOL
3. Concentration par actif
4. Regime exposure cap
5. Futures leverage cap
6. Capital fragmentation
7. Opportunity ranking global
8. Direction cap (max positions LONG ou SHORT simultanées)

**API décision :** `approve_packet(packet)` — RISK_EVALUATED → APPROVED ou REJECTED  
**Tests :** 15 passés (test_portfolio_brain.py)

### OrderSizer

**Module :** `quant_hedge_ai/agents/risk/order_sizer.py`  
**Invariant A-02 :** Ne lève jamais SessionHaltedError — uniquement clamping dans [min_size, max_size]  
**Sizing :** Kelly fraction × conviction_factor × drawdown_factor × portfolio_factor  
**Tests :** 86 passés (test_order_sizer.py)

### SessionGuard

**Invariants HARD :**
- I-02 : Drawdown session > seuil → SessionHaltedError
- I-03 : N pertes consécutives > seuil → SessionHaltedError
- I-12 : Order > EXEC_MAX_ORDER_USD → OrderTooLargeError

### ExecutiveOverride

**Module :** `quant_hedge_ai/agents/risk/executive_override.py`  
**Invariant I-08 HARD :** AgentVote(veto=True) = terminal, indépendant du score agrégé  
**5 niveaux :** de VETO complet à APPROVE avec taille réduite

---

## 5. COUCHE INTELLIGENCE

### ConvictionEngine

**Module :** `quant_hedge_ai/agents/intelligence/conviction_engine.py`  
**Niveaux :** VERY_HIGH(100%) → HIGH(75%) → MEDIUM(50%) → LOW(25%) → MINIMAL(0%) → SKIP  
**I-14 :** `blocks_trade()` = True si MINIMAL ou SKIP  
**Tests :** intégrés test_constitution_i14

### SelfAwarenessEngine

**Module :** `quant_hedge_ai/agents/intelligence/self_awareness_engine.py`  
**4 niveaux dérive :** OPTIMAL → SUBOPTIMAL → DEGRADED → CRITICAL  
**Tests :** 3 passés (test_self_awareness_resume.py)

---

## 6. COUCHE OBSERVABILITÉ

### GovernanceAuditor

**Module :** `governance/auditor.py`  
**Rôle :** Agent observateur indépendant — vérifie cohérence inter-couches, anomalies systémiques  
**Severities :** INFO / WARNING / CRITICAL / FATAL  
**Statut :** Créé — intégration advisor_loop NON CONFIRMÉE

### JSON Logger + Trace ID

**Module :** `observability/json_logger.py`  
**new_trace_id()** → UUID4 unique par cycle  
**set_trace_id(tid)** → contexte thread-local propagé  
**I-16 :** Absence de trace_id → décision REJECTED

---

## 7. COUCHE SIMULATION

### VirtualPortfolio

**Module :** `paper_trading/virtual_portfolio.py`  
**Capital :** $100 (configurable `VIRTUAL_CAPITAL_USD`)  
**Position :** 15% du capital, plafond $20  
**Fees :** 0.10% taker MEXC  
**Surveillance TP/SL :** Thread dédié, intervalle 60s  
**Prix :** fetch_ticker MEXC live via MexcReader  
**Notifications :** TelegramAlert.info() sur open/close/TP/SL/PnL

### MexcSimulator

**Module :** `paper_trading/mexc_simulator.py`  
**Types d'ordre :** MARKET / LIMIT / STOP_LIMIT  
**Slippage :** 0.05% (configurable `MEXC_SIM_SLIP`)  
**Fees :** 0.10% taker (configurable `MEXC_SIM_FEE`)  
**Solde initial :** API MEXC ou `MEXC_SIM_CAPITAL`  
**KPIs 7 jours :** PnL%, Sharpe, Max Drawdown, Win Rate  
**Statut :** Créé — câblage advisor_loop NON CONFIRMÉ

### MexcReader

**Module :** `infra/mexc_reader.py`  
**Mode :** READ-ONLY structurel (pas de méthode d'ordre)  
**Endpoints :** spot + futures USDT  
**Auth :** `MEXC_API_KEY` + `MEXC_API_SECRET` (optionnel — graceful degradation)  
**Statut :** Disponible — clés VPS à configurer

---

## 8. COUCHE INFRA/VPS

### advisor_loop (VPS principal)

**Fichier :** `core/advisor_loop.py`  
**VPS :** 34.171.188.99  
**Mode :** P10 F-01 — RUNNING (observation multi-symboles)  
**Symboles :** BTC/USDT, ETH/USDT, SOL/USDT, DOGE/USDT  
**Interval :** 300s (5 min)

### Watchdog VPS

**Module :** `watchdog_vps.py`  
**Comportement :** Vérifie toutes les 60s si advisor_loop tourne, restart si mort  
**Cooldown :** 120s minimum entre deux restarts  
**Statut :** Disponible localement — déploiement systemd VPS REQUIS

### ExchangeFactory

**Module :** `infra/exchange_factory.py`  
**Exchanges supportés :** Binance, Bybit, OKX, Kraken, MEXC  
**Modes :** live / testnet / futures_demo / paper  

---

## 9. INVENTORY INVARIANTS (SYSTEM_INVARIANTS.md)

| ID | Condition | Enforcement | Statut |
|----|-----------|-------------|--------|
| I-01 | Size ≤ 0 = alert + auto-heal | SOFT | ✅ |
| I-02 | Drawdown session = HALT | HARD | ✅ |
| I-03 | Pertes consécutives = HALT | HARD | ✅ |
| I-04 | Dupliqué 30s = BLOCK | HARD | ✅ |
| I-05 | Cache stale = NONE | SOFT | ✅ |
| I-06 | Signal timestamp ≠ None | SOFT | ✅ |
| I-07 | Gate blocked = trade impossible | HARD | ✅ |
| I-08 | VETO = terminal | HARD | ✅ |
| I-09 | Size dans [min,max] | SOFT | ✅ |
| I-10 | DrawdownGuard factor ≥ 0.1 | SOFT | ✅ |
| I-11 | trace_id présent par cycle | HARD | ✅ |
| I-12 | Order > MAX = REJECT | HARD | ✅ |
| I-13 | SAFE_MODE centralisé | HARD | ✅ |
| I-14 | Exception agent → REJECTED (Layer 1-2) | HARD | ✅ Layer 1-2 / ⚠️ Layer 3 DETTE |
| I-15 | can_trade=False → aucun ordre (Layer 1-2) | HARD | ✅ Layer 1-2 / ⚠️ Layer 3 DETTE |
| I-16 | trace_id obligatoire (Layer 1-2) | HARD | ✅ Layer 1-2 / ⚠️ Layer 3 DETTE |

---

## 10. ÉTAT PAR PHASE PROJET

| Phase | Statut | Notes |
|-------|--------|-------|
| P0 — Core Engine | ✅ COMPLÉTÉ | RSM, DecisionPacket, Lifecycle |
| P2 — Operational Closure | ✅ FERMÉ 2026-05-13 | exchange_constraints, rate_limiter, simulator |
| P5 — Limited Live | ✅ LIVRÉ 2026-05-14 | paper_trading/, sandbox, risk_limits |
| P10-A — Cold Start | ✅ CERTIFIÉ (7/7) | HMAC, bypass detector, 3 régimes |
| P10-F — Architecture | ✅ CERTIFIÉ | 3 états RUNNING/DEGRADED/HALTED |
| P11-B — Restart Safety | ✅ 38 tests | WarmupSM, StartupCache, TamperLog |
| P12-D — Burn-In Engine | ✅ LIVRÉ | BurnInEngine, InvariantChecker |
| P13 — Capital Réel | ⏳ EN OBSERVATION | Gel archi + burn-in 7/30j |
| P3 Buffer | ⏳ EN OBSERVATION | missed_win_rate >= 55% + N>=30 avant 60→58 |
| W23 — LiveReader + Ranker | ✅ LIVRÉ | LiveExchangeReader, MarketUniverseRanker |
| Governance G0→G8-E | ✅ CERTIFIÉ | 388 tests, Z3 proofs, xfail I-14 Layer 3 |
| MEXC Paper Trading | ⚠️ PARTIEL | Modules livrés, câblage advisor_loop à confirmer |

---

## 11. COMPOSANTS EN ATTENTE DE CONFIRMATION

> Ces composants sont créés mais leur intégration dans la boucle principale n'a pas été vérifiée dans cette session.

| Composant | Fichier | Action requise |
|-----------|---------|---------------|
| VirtualPortfolio | `paper_trading/virtual_portfolio.py` | Vérifier instantiation + `vp.open_position()` dans advisor_loop |
| MexcSimulator | `paper_trading/mexc_simulator.py` | Vérifier câblage |
| GovernanceAuditor | `governance/auditor.py` | Vérifier appel `auditor.audit_cycle()` dans advisor_loop |
| watchdog_vps | `watchdog_vps.py` | Déployer comme service systemd sur VPS |
| MEXC clés | — | Configurer `MEXC_API_KEY` + `MEXC_API_SECRET` sur VPS |

---

## 12. PREUVES FORMELLES Z3 (core/formal_proof.py)

| Property ID | Description | Statut |
|-------------|-------------|--------|
| G0 | executed=True ⟹ trace_id=True | ✅ PROVED (UNSAT) |
| G1 | executed=True ⟹ safe_mode=False | ✅ PROVED (UNSAT) |
| G5 | execution_pending=True ⟹ kelly>0 | ✅ PROVED (UNSAT) |
| G8-D | trade_allowed ↔ packet_actionable | ✅ PROVED (UNSAT) |
| G8-E | executed=True ⟹ dp_none=False | ✅ PROVED (UNSAT) |
| S3 | execution_pending=True ⟹ allocation>0 | ✅ PROVED (UNSAT) |
| P04 | EXECUTED ⟹ G0∧G1∧G5∧G8-E∧S3∧chain_valid∧trade_allowed | ✅ PROVED (UNSAT) |
| R3 | engine_configured ∧ result=None ⟹ blocked (fail-closed) | ✅ PROVED (UNSAT) |

---

*Snapshot 2026-06-03. Vérifier git log pour les changements ultérieurs.*
