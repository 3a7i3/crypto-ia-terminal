# WEB COCKPIT DATA MAP

Status: CANONICAL — R1 (WEB-DOC-01)
Basis: WEB COCKPIT DATA MAP R0.1 (accepted), revalidated against source at
commit `1c36ad33c2f9d6263d786aae96f5269f0ded23a5`.
Scope: documentation only. This document changes no machine behavior.

---

## 1. Purpose

This document is the translation map between **machine facts** (what the
trading research system actually computes, decides, and records) and
**human visualization** (what the Web cockpit shows an operator).

It exists so that every number, badge, or status shown in the cockpit can be
traced back, in a few seconds, to the component that produced it, and so
that the cockpit's design stays bounded by what the machine can honestly
prove today.

It is the single reference for:

1. What facts does the machine produce?
2. Which component owns each fact?
3. Is that fact scientifically trustworthy?
4. Is it already Web-exposed?
5. Which cockpit panel should display it?
6. What future bounded mission is required if it is not ready?

---

## 2. Architectural Principles

- **The machine owns scientific truth.** All scientific and trading facts
  (regime, decisions, PnL, regret) are computed inside the Python research
  system, never inside the browser.
- **Snapshot/API transports truth.** A governed snapshot, read through a
  read-only API, is the only channel that carries machine facts to the Web.
- **The frontend renders truth.** React formats and displays what the API
  gives it; it does not compute, infer, or reinterpret scientific values.
- **UI does not redefine scientific semantics.** A field's meaning is fixed
  by the domain that produces it, not by the panel that shows it.
- **`UNKNOWN` must stay `UNKNOWN`.** When a value is not yet reliably
  produced, the cockpit must show that honestly instead of inferring or
  guessing a number.
- **PAPER and REAL must remain visibly separate** in every view that could
  show either, with no ambiguous merged state.
- **Observation is not execution authority.** Nothing the Web cockpit shows
  or will show (including any future control surface) can itself authorize
  a trade; per ADR-0007, only the decision engine decides.

---

## 3. Evidence Vocabulary

Every factual claim in this document (and in any Web-facing contract that
follows it) must be tagged with one of these evidence classes:

| Class | Meaning |
|---|---|
| `SOURCE_PROVEN` | Directly read in the current source at the cited file:line; the call chain from producer to consumer was traced, not assumed. |
| `DOCUMENTATION_CONTRACT` | Stated as normative in an accepted contract/ADR; treated as binding even where the implementing code is elsewhere or partial. |
| `DERIVED_BY_TRACE` | Inferred by following call sites, factories, or registries (e.g. a lazy-factory registration), not a single direct read. |
| `RUNTIME_UNKNOWN` | The code path exists, but there is no evidence (logs, deployment record, T-1 liveness) that it is actually executing on the live VPS. |
| `FUTURE_WORK` | Not implemented; scoped for a later bounded mission. |
| `LEGACY` | Superseded by a newer mechanism but still present in code, kept for observability/telemetry/back-compat, not for authority. |
| `UNRESOLVED` | A conflict or gap was found during revalidation and is not yet settled; see §22. |

A claim must never be upgraded silently — e.g. "a call site exists"
(`SOURCE_PROVEN`/`DERIVED_BY_TRACE`) must never be written as "running in
production" (`RUNTIME_UNKNOWN` unless T-1 liveness evidence says otherwise).
Likewise "a snapshot field exists" must never be written as "Web ready"
unless both source and transport readiness are confirmed (§6).

---

## 4. Readiness Vocabulary

Two axes are tracked **independently** for every fact. A fact can be fully
ready on one axis and not the other; conflating them is the single most
common documentation error this project has made historically.

### Scientific Source Readiness

| Value | Meaning |
|---|---|
| `SOURCE_READY` | The producing component is implemented, wired into a real runtime call chain, and the value's semantics are settled. |
| `SOURCE_PARTIAL` | Implemented but with known gaps (e.g. not centralized, some paths untested, semantics still evolving). |
| `SOURCE_UNSAFE` | Not implemented, dormant, or too unreliable to expose even internally. |

### Web Transport Readiness

| Value | Meaning |
|---|---|
| `WEB_READY_NOW` | Already flows through snapshot → API → React today. |
| `NEEDS_SNAPSHOT_EXPOSURE` | Source exists but the canonical snapshot (O-02W-C) does not yet serialize it. |
| `NEEDS_API_EXPOSURE` | Snapshot carries it, but no API route/field exposes it yet. |
| `NEEDS_HISTORY_READER` | The fact lives only in an append-only file (e.g. JSONL); a governed history-reader/projection is required before the Web can see it — the frontend/API must never read the raw file directly. |
| `BLOCKED_BY_SCIENTIFIC_WORK` | Web transport is not the blocker; the underlying scientific/engineering work must land first. |

**Worked example:** `paper_trades.jsonl` can be `SOURCE_READY` (the paper
trading engine reliably writes it) while simultaneously
`NEEDS_HISTORY_READER` for the Web axis. This must never be read as
"React may read the JSONL file directly" — it may not, ever (§7, §23).

---

## 5. Existing Web Foundation

The following are **already delivered**, not future work. They form the
current, working Web foundation this document builds on.

| ID | What it delivered | Evidence |
|---|---|---|
| **O-02W-B** | The certified normative contract governing the whole canonical operator architecture: process boundary map, source-to-exposure matrix, common value contract, portfolio/trade API contracts. | `docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md` (`DOCUMENTATION_CONTRACT`) |
| **O-02W-C** | The canonical snapshot **producer**: builds and writes the operator snapshot, runtime manifest, process identity, and source/deployment evidence. Wired into the live advisor loop (bootstrap + per-cycle write). | `observability/operator_snapshot_builder.py`; `observability/operator_runtime_manifest.py`; `observability/process_identity.py`; `observability/source_evidence.py`; `observability/operator_boot_coordinator.py`; called from `core/advisor_loop.py` (bootstrap ~L5588-5621, per-cycle write ~L8052-8135) (`SOURCE_PROVEN`) |
| **O-02W-D1** | The read-only operator API: `GET /api/operator/v1/snapshot`, structured validation, no writes, no JSONL access, no direct import of the trading engine. | `observability/operator_api/app.py`, `reader.py` (`SafeSnapshotReader`), `paths.py` (`SOURCE_PROVEN`) |
| **O-02W-D2** | The React polling client: a single serialized snapshot-polling hook with monotonic sequencing, plus client-side structural validation mirroring the server. | `frontend/src/lib/snapshotClient.ts`, `snapshotValidation.ts`, `observedValue.ts`, `types.ts`; CI gate `.github/workflows/frontend-ci.yml` (`SOURCE_PROVEN`) |
| **O-02W-D3** | Cross-stack compatibility verification: a CI gate proving the O-02W-C producer's output travels unchanged through the real D1 API and is accepted by the real D2 client. | `.github/workflows/cross-stack-compat.yml`; `tests/cross_stack/*` (`SOURCE_PROVEN`) |
| **O-02W-E1** | A Telegram-identity-registry cutover pointer (dated 2026-09-10), referenced inline rather than as a standalone contract. Scope should be treated conservatively pending a dedicated contract file. | `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md` (`DOCUMENTATION_CONTRACT`, narrow) |

---

## 6. Machine → Web Architecture

The approved pipeline, and the only one this document authorizes:

```
AUTHORITATIVE MACHINE SOURCE
        │  (core/advisor_loop.py, decision_packet.py,
        │   paper_trading/*, execution/*)
        ▼
CANONICAL SNAPSHOT / GOVERNED PROJECTION      ← O-02W-C
        │  (observability/operator_snapshot_builder.py
        │   + operator_runtime_manifest.py)
        ▼
READ-ONLY OPERATOR API                        ← O-02W-D1
        │  (observability/operator_api/*,
        │   GET /api/operator/v1/snapshot, never mutates)
        ▼
WEB COCKPIT                                   ← O-02W-D2 / D3
           (frontend/src/lib/snapshotClient.ts + views)
```

Not authorized, now or by implication of anything in this document:

- a competing/second API surface;
- direct frontend or API-layer reads of the database, the JSONL ledgers, or
  the exchange;
- frontend scientific recomputation of any value the machine already owns.

---

## 7. Authority Map

| Fact | Authority owner | Domain | Evidence class | Source readiness | Web readiness | Dependency |
|---|---|---|---|---|---|---|
| Regime | Regime classifier modules (`anara_context/modules/*`) | Scientific | `DERIVED_BY_TRACE` | `SOURCE_PARTIAL` | `WEB_READY_NOW` (basic regime label) | — |
| Regime confidence | `market_state.regime_confidence` domain field | Scientific | `SOURCE_PROVEN` (field), `RUNTIME_UNKNOWN` (population) | `SOURCE_PARTIAL` | `NEEDS_SNAPSHOT_EXPOSURE` | Field modeled `None`/`UNAVAILABLE` by default (`observability/operator/domains/market_state.py`); not confirmed wired into the snapshot builder output |
| Universe size | `market_state.universe_size` domain field | Scientific | `SOURCE_PROVEN` (field), `RUNTIME_UNKNOWN` (population) | `SOURCE_UNSAFE` | `NEEDS_SNAPSHOT_EXPOSURE` | No confirmed producer (field comment: "INCONCLUSIVE, no confirmed producer found") |
| DecisionPacket actionability | `DecisionPacket.is_actionable()` | Execution authority | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` (as `decision_pipeline` telemetry) | — |
| Blockers | Legacy `trade_allowed` / blockers list | Analysis/gating input (not authority) | `LEGACY` | `SOURCE_READY` | `WEB_READY_NOW` | Superseded as authority by DecisionPacket; kept for observability and TYPE-A-DISAGREEMENT auditing |
| Scientific capital (`WALLET_PAPER_CAPITAL`) | Sizing configuration, pinned per ADR-0007 | Governance | `DOCUMENTATION_CONTRACT` | `SOURCE_READY` | `WEB_READY_NOW` | — |
| Real-account balance | Exchange account state (out of scope for Web read) | Execution | `RUNTIME_UNKNOWN` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | REM-C / real-account observation not certified |
| Paper equity | `PaperTradeRecorder` / paper ledger | Scientific (paper domain) | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` | — |
| Paper positions | `PositionManager` (paper mode) | Scientific (paper domain) | `DERIVED_BY_TRACE` | `SOURCE_READY` | `WEB_READY_NOW` | Registered as a lazy factory in the advisor runtime |
| Real positions observation | Exchange / execution engine | Execution | `RUNTIME_UNKNOWN` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | REM-C dependency (§9, §10) |
| Regret v2 | Regret analysis pipeline | Scientific | `DOCUMENTATION_CONTRACT` | `SOURCE_PARTIAL` | `NEEDS_HISTORY_READER` | Historical regret currently lives in append-only files |
| Runtime SHA | `observability/source_evidence.py` | System health | `SOURCE_PROVEN` (mechanism), `RUNTIME_UNKNOWN` (independent proof) | `SOURCE_PARTIAL` | `WEB_READY_NOW` (as self-reported value) | Independent (T-1) confirmation not yet available |
| Deployment evidence | `source_evidence.py` / deploy tags | System health | `DOCUMENTATION_CONTRACT` | `SOURCE_PARTIAL` | `NEEDS_SNAPSHOT_EXPOSURE` | T-1 mission (not started) owns the independent version |
| Liveness (advisor process) | T-1 (independent liveness publisher) | System health | `FUTURE_WORK` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | T-1 not started; snapshot age must never be used as a liveness proxy |
| Order intent | Advisor loop G8 block | Execution | `SOURCE_PROVEN` | `SOURCE_READY` (paper), `SOURCE_UNSAFE` (real) | `NEEDS_API_EXPOSURE` | REM-C for durable pre-execution intent persistence |
| ACK | Execution engine / exchange response | Execution | `RUNTIME_UNKNOWN` | `SOURCE_PARTIAL` | `BLOCKED_BY_SCIENTIFIC_WORK` | REM-C |
| Fills | Execution engine / exchange | Execution | `RUNTIME_UNKNOWN` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | REM-C explicitly excludes fill-quantity reconciliation today |
| Realized PnL | `PaperTradeRecorder` (paper) / execution ledger (real) | Scientific / Execution | `SOURCE_PROVEN` (paper), `RUNTIME_UNKNOWN` (real) | `SOURCE_READY` (paper) | `NEEDS_HISTORY_READER` (historical), `WEB_READY_NOW` (current snapshot value, paper) | — |

---

## 8. Decision Authority Model

The corrected, current architecture — revalidated against source at the
starting SHA — is:

> **`DecisionPacket.is_actionable()` is the mandatory execution-authorization
> gate.** (`core/decision_packet.py`, `is_actionable()`)

It is consumed in the advisor loop's G8 block as the local variable
`_effective_trade_allowed`: when no packet is available, this is forced to
`False` (fail-closed, the "G8-E guard"); otherwise it takes the value of
`packet.is_actionable()`. Order submission is gated on this variable
together with the raw signal's actionability, safe-mode state, and
protection blocks. This is enforced structurally by invariant **A-15**
(`core/invariants.py`), which checks at the source-text level that the
G8-E fail-closed guard has not been silently removed — a scoped guarantee
against regression, not a runtime assertion.

> **Legacy `trade_allowed` / blockers are analysis and gating inputs, not
> execution authority.** They remain in the result payload for
> observability and are compared against the packet's verdict by a passive
> governance auditor (TYPE-A-DISAGREEMENT check) to detect drift between the
> legacy and authoritative paths.

`DecisionPacket` must never be described as a shadow-only authority — it is
the real, load-bearing gate in the live advisor loop.

**`DecisionObservation`** (`observability/decision_observation.py`) is a
separate, frozen, primitives-only telemetry record produced *after*
`analyze_symbol()` and published to a `DecisionEventBus`. It references a
packet's ID as a plain string but is not the packet and carries no
authorization method. It is consistent with ADR-0007: it observes and
records, it never gates.

---

## 9. Execution Truth Map

| Stage | Classification | Notes |
|---|---|---|
| DECISION | `CANONICAL_NOW` | `DecisionPacket` + `is_actionable()`, live in the advisor loop |
| INTENT | `CANONICAL_NOW` (paper) / `PARTIAL` (real) | Order-submission branch entered once `_effective_trade_allowed` and other gates pass |
| AUTHORIZATION | `CANONICAL_NOW` | Gate itself is the authorization step (§8) |
| SUBMISSION | `CANONICAL_NOW` (paper, via `MexcSimulator`) / `REM_C_DEPENDENCY` (real, durable/idempotent submission) | ADR-0020 scopes durable/idempotent real submission; explicitly notes REM-C exclusions |
| ACK | `REM_C_DEPENDENCY` | No confirmed live call chain independent of REM-C scope |
| ORDER OBSERVATION | `REM_C_DEPENDENCY` | Same |
| FILL | `REM_C_DEPENDENCY` | ADR-0020 explicitly excludes "partial-fill lifecycle and fill-quantity reconciliation" as REM-C scope, not yet implemented |
| POSITION | `CANONICAL_NOW` (paper, via `PositionManager`) / `REM_C_DEPENDENCY` (real) | — |
| CLOSE | `CANONICAL_NOW` (paper) / `REM_C_DEPENDENCY` (real) | — |
| PNL | `CANONICAL_NOW` (paper, via `PaperTradeRecorder`) / `REM_C_DEPENDENCY` (real) | — |

Do not imply REM-C R2/R3-style completion anywhere: as of the starting
SHA, REM-C is a named future remediation scope (fill-quantity
reconciliation, partial-fill lifecycle, crash-window durable decision
persistence) with **no REM-C scope started** — every ADR-0020 reference to
it is paired with that disclaimer.

---

## 10. Paper / Real / Shadow / Burn-in Map

| Component | Status | Evidence |
|---|---|---|
| `MexcSimulator` (`paper_trading/mexc_simulator.py`) | `ACTIVE` | Instantiated directly in the advisor loop bootstrap, gated on advisor-only/`PAPER_TRADING_ENABLED` |
| `PaperTradeRecorder` (`paper_trading/recorder.py`) | `ACTIVE` | Used as the entry/exit source of truth inside the advisor loop's paper bookkeeping |
| `PositionManager` (`quant_hedge_ai/agents/execution/position_manager.py`) | `ACTIVE` | Registered as a lazy factory in the advisor runtime registry |
| Runtime `PaperTradingEngine` (`quant_hedge_ai/agents/execution/paper_trading_engine.py`) | `ACTIVE`, but in the alternate `quant_hedge_ai/main_system.py` / `main_v91.py` entry points and `system/burn_in.py` | Not found instantiated inside `core/advisor_loop.py`; treat as a separate runtime family (§20 dependency note) |
| `BurninSimulationEngine` (`paper_trading/engine.py`) | `DORMANT / ACTIVATION_UNCONFIRMED` | Only found in module docstring usage examples; no production call site found in `core/advisor_loop.py` or elsewhere. Its own docstring explicitly distinguishes it from the live `PaperTradingEngine` |
| `PaperLedger` (`paper_trading/ledger.py`) | `DORMANT / ACTIVATION_UNCONFIRMED` | Only known caller is `BurninSimulationEngine.__init__`, itself dormant |
| `ShadowTracker` (`scripts/shadow_execution.py`) | `STANDALONE_SCRIPT` | Instantiated only within its own script; not part of the advisor loop's runtime call chain — an offline/manual tool |
| `ShadowExecutionEngine` (`quant_hedge_ai/agents/execution/shadow_engine.py`) | `ACTIVE` | Registered as a lazy factory in the advisor runtime registry alongside `PositionManager` |

None of these are described as active beyond what a traced runtime call
chain supports; `BurninSimulationEngine` in particular stays conservatively
`DORMANT / ACTIVATION_UNCONFIRMED` per the current evidence.

---

## 11. Panel Catalog

| Panel | Human question answered | Source | Current readiness | Visualization | Dependency | Future mission |
|---|---|---|---|---|---|---|
| SYSTEM | Is the observable system healthy? | O-02W-C manifest + source evidence | Partial (liveness unresolved) | Status tiles | T-1 | — |
| MARKETS | What markets is the machine watching? | Market state domain | Partial (universe_size missing) | Table | Universe-size producer | WEB-MARKET-01 |
| REGIMES | What regime is detected, how confident? | Regime classifier → market_state | Partial (confidence not wired) | Badge + trend | Regime-confidence transport | WEB-REGIME-01 |
| DECISIONS | What did the machine decide, and why? | DecisionPacket / decision_pipeline | Web ready (current cycle) | Timeline | History reader for past decisions | WEB-DECISION-01 |
| PORTFOLIO | What PAPER portfolio exists? | PositionManager / PaperTradeRecorder | Web ready | Table + chart | Real-position observation for REAL view | WEB-PORTFOLIO-01 |
| PERFORMANCE | How is paper performance trending? | PaperTradeRecorder history | Needs history reader | Chart | Governed JSONL projection | WEB-PORTFOLIO-01 |
| REGRET | Was a good trade missed or refused? | Regret v2 pipeline | Needs history reader | Table | Governed projection | WEB-REGRET-01 |
| DATA | What datasets/snapshots exist, how fresh? | Snapshot manifests, data quality gates | Partial | Table | Data explorer (§14) | WEB-DATA-01 |
| HUMAN LAB *(future)* | What would a human have chosen? | Not yet built | Not started | — | HumanDecisionEvent design | WEB-HUMAN-LAB-01 |
| COMMAND AUTHORITY *(future)* | Can an operator safely act from the Web? | Not yet built | Not started | — | Authenticated command chain (§18) | WEB-EXECUTION-01 |

---

## 12. Pipeline Visualization

```
MARKET DATA → UNIVERSE → INDICATORS → STRATEGIES → SIGNALS → FILTERS
    → RISK → PORTFOLIO → EXECUTION → ORDERS → FILLS → POSITIONS → P&L
```

Confirmed joins (paper path): SIGNALS → FILTERS → RISK → PORTFOLIO →
EXECUTION (via `DecisionPacket`/G8) → ORDERS (paper, via `MexcSimulator`) →
POSITIONS (`PositionManager`) → P&L (`PaperTradeRecorder`).

Unconfirmed / not fabricated: UNIVERSE sizing is not confirmed wired
end-to-end (§7); FILLS and the real-money ORDERS/POSITIONS/P&L joins are
`REM_C_DEPENDENCY` per §9 and must not be shown as complete.

---

## 13. Decision Trace

The eventual per-decision trace an operator should see, and its current
honesty status:

| Field | Status |
|---|---|
| `trace_id` | Available (execution_trace.py) |
| `decision_id` | Available |
| signal | Available |
| regime | Available (confidence: see §7) |
| blockers | Available (legacy, telemetry) |
| actionability | Available (`is_actionable()`) |
| order intent | Available (paper), `REM_C_DEPENDENCY` (real) |
| submission | Available (paper), `REM_C_DEPENDENCY` (real) |
| ACK | `REM_C_DEPENDENCY` |
| fill | `REM_C_DEPENDENCY` |
| position | Available (paper), `REM_C_DEPENDENCY` (real) |
| close | Available (paper), `REM_C_DEPENDENCY` (real) |
| PnL | Available (paper), `REM_C_DEPENDENCY` (real) |
| regret | `NEEDS_HISTORY_READER` |

Any future decision-trace panel must mark the REM-C-dependent fields as
unavailable rather than approximating them.

---

## 14. Data Explorer

Future read-only access, planned for:

- snapshot families (current + rolling history);
- manifests;
- decision evidence;
- rejections;
- paper trades (historical);
- regret v2 (historical);
- integrity/data-quality evidence;
- dataset time range, count, and freshness.

**The frontend never reads raw files directly, under any circumstance.**
Historical JSONL exposure (paper trades, regret, decision history) requires
a governed history-reader/projection component sitting between the raw
files and the API — this component does not exist yet (§4, `NEEDS_HISTORY_READER`).

---

## 15. System Health

| Fact | Owner | Notes |
|---|---|---|
| API readiness | O-02W-D1 (`operator_api/app.py`) | Self-reporting only |
| Advisor-process liveness | **T-1** (independent) | Not started; must never be inferred from snapshot age |
| Runtime SHA | `source_evidence.py` (O-02W-C) | Self-reported; independent confirmation is T-1 scope |
| Deployment evidence | `source_evidence.py` + deploy tags | Self-reported; T-1 owns the independent version |
| Snapshot freshness | O-02W-C timestamp | Available |
| Process instance | `process_identity.py` | Available |
| Data freshness | Snapshot manifest | Available |
| Health score | Not yet defined as a single composite | `FUTURE_WORK` |
| Exchange connectivity | Execution engine | `RUNTIME_UNKNOWN` |

**T-1 owns independent advisor-process liveness evidence and has not
started.** Snapshot age must never be used as a substitute for boot/process
liveness — a stale snapshot and a dead process are not the same signal,
and conflating them was a known documentation risk in prior drafts.

---

## 16. Telegram → Web Relationship

- **Telegram**: mobile observation and alerts. Retains permanent value for
  critical alerts regardless of Web cockpit maturity.
- **Web**: rich investigation and visualization, for deeper analysis than a
  chat interface supports.

This document does not authorize retiring Telegram in any form; the two
channels serve different operator needs and both remain useful
indefinitely.

---

## 17. Future Human Research Lab (architecture only)

Conceptual flow, no implementation authorized by this document:

```
SNAPSHOT → EXPERIMENT PRESENTATION → HUMAN CHOICE
   → HumanDecisionEvent → durable receipt → outcome comparison
```

Two modes to design for, later:

- **BLIND** — the human chooses without seeing the machine's decision.
- **ASSISTED** — the human sees the machine's decision and reasoning before
  choosing.

This is exploratory architecture for a future bounded mission
(WEB-HUMAN-LAB-01); no HumanDecisionEvent schema, storage, or UI exists
today.

---

## 18. Future Web Command Authority (architecture only)

**A UI button is never execution authority.** Any future control surface
must route through an explicit authorization chain, never directly to the
trading engine:

```
HUMAN CLICK → REQUEST → AUTHENTICATED SESSION → COMMAND INTENT
   → AUTHORIZATION → MACHINE ACTION → RESULT → AUDIT EVIDENCE
```

This document authorizes no trading-control capability of any kind. Any
future implementation must still satisfy ADR-0007: only the decision engine
decides; a Web command can at most request, never directly cause, an
action, and only after passing the same authorization gates as any other
trigger.

---

## 19. Future Mission Map

| Mission | Scope | Source readiness | Web readiness | Dependency | Blocker | Risk |
|---|---|---|---|---|---|---|
| WEB-DECISION-01 | Historical decision trace panel | `SOURCE_PARTIAL` | `NEEDS_HISTORY_READER` | History reader | None known | Low |
| WEB-REGIME-01 | Regime + confidence exposure | `SOURCE_PARTIAL` | `NEEDS_SNAPSHOT_EXPOSURE` | Confidence wiring into snapshot builder | Confidence not proven live-wired | Low |
| WEB-DATA-01 | Data explorer, snapshot/dataset browsing | `SOURCE_READY` (manifests) | `NEEDS_API_EXPOSURE` | Manifest API routes | None known | Low |
| WEB-REGRET-01 | Regret v2 panel | `SOURCE_PARTIAL` | `NEEDS_HISTORY_READER` | History reader | N thresholds (see CLAUDE.md) still unmet | Medium (statistical validity) |
| WEB-MARKET-01 | Market/universe panel | `SOURCE_UNSAFE` (universe_size) | `NEEDS_SNAPSHOT_EXPOSURE` | Universe-size producer | No confirmed producer | Medium |
| WEB-PORTFOLIO-01 | Paper portfolio + performance panels | `SOURCE_READY` (paper) | `WEB_READY_NOW` (current), `NEEDS_HISTORY_READER` (trend) | History reader for trend view | None known | Low |
| WEB-EXECUTION-01 | Execution truth map panel (paper first) | `SOURCE_PARTIAL` | `NEEDS_API_EXPOSURE` | REM-C for real-money stages | Real fills/ACK not implemented | High if real-money scope is added prematurely |
| WEB-HUMAN-LAB-01 | Human research lab (§17) | Not started | Not started | Full schema/design | Entirely future | Medium (scope creep risk) |

`WEB-DECISION-02 — Promote DecisionPacket` is explicitly **not** included:
DecisionPacket is already the mandatory execution-authority gate (§8); no
promotion mission is needed or valid.

---

## 20. Dependency Map

| Dependency | What it gates | Status |
|---|---|---|
| **REM-C** | Real-money ACK, fills, partial-fill reconciliation, crash-window durable decision persistence | Not started; ADR-0020 carries repeated "no REM-C scope started" disclaimers |
| **T-1** | Independent advisor-process liveness, independent deployment/SHA confirmation | Not started (explicitly, per O-02W-E and O-02W-B contracts) |
| **Runtime observation** | Any claim that a component is "active" in production, beyond a traced call chain | Confirmed only where a real runtime call site was found (§10, §12); otherwise `RUNTIME_UNKNOWN` |
| **F-00** | A separate, later scientific measurement pass, gated on its own criteria | **DEFINED / REFERENCED IN GOVERNANCE — NOT STARTED.** Explicitly not O-02W-B, C, D, or E, and not any cockpit-implementation mission. |

---

## 21. Simple Cockpit MVP

The smallest useful cockpit, using only currently trustworthy facts:

1. **Is the observable system healthy?** — API readiness, snapshot
   freshness, self-reported runtime SHA (with the caveat that independent
   T-1 liveness is not yet available).
2. **What markets/regimes are visible?** — regime label (without asserting
   a confidence figure that isn't reliably wired yet).
3. **What did the machine decide?** — current-cycle `DecisionPacket`
   actionability and its inputs, from the live snapshot.
4. **Why was it accepted/refused?** — blockers/legacy `trade_allowed` shown
   as gating-input telemetry, alongside the authoritative packet verdict.
5. **What PAPER portfolio exists?** — current positions and equity from
   `PositionManager` / `PaperTradeRecorder`, clearly labeled PAPER.
6. **What evidence supports the display?** — every value tagged with its
   evidence class per §3, visible on hover or in a details view.

Do not overload the MVP with historical trends, regret analysis, or any
real-money view — those require the history reader and REM-C respectively.

---

## 22. Known Data Gaps

- **`universe_size` producer**: modeled in the domain schema, no confirmed
  wiring to a live value (§7).
- **`regime_confidence` transport**: computed by regime classifier modules,
  but not confirmed wired into the canonical snapshot (§7).
- **Historical paper-trade reader**: no governed projection over
  `paper_trades.jsonl` exists yet; the API must not read it directly (§14).
- **Fill truth**: real-money fills and ACKs are REM-C-dependent and not
  implemented (§9).
- **Position authority/provenance for real accounts**: not implemented;
  paper positions are `SOURCE_READY`, real positions are not (§7, §10).
- **Independent liveness**: T-1 not started; snapshot age must not be used
  as a substitute (§15).
- **Execution-health aggregation**: no single composite health score exists
  today (§15).
- **`BurninSimulationEngine` / `PaperLedger` activation status**: both
  conservatively classified `DORMANT / ACTIVATION_UNCONFIRMED`; no
  production call site found. Any future claim of activation needs fresh
  evidence, not inference from the presence of the class (§10).
- **O-02W-E1 scope**: referenced only inline from
  `TELEGRAM_IDENTITY_REGISTRY.md`, no standalone contract found; treat its
  scope conservatively until a dedicated contract exists (§5).

---

## 23. Governance Rules for Future Web PRs

- One panel = one bounded mission, where practical.
- No scientific logic in React — formatting and display only.
- No direct JSONL access, from the frontend or from the API layer.
- No exchange access from the frontend or from the API reader.
- No mutation capability until separately, explicitly authorized (see §18).
- Every displayed value needs provenance (source owner + evidence class).
- `UNKNOWN` is always preferable to invented certainty.

---

*This document supersedes prior informal cockpit-mapping notes. It does not
introduce, remove, or modify any runtime behavior, API route, snapshot
field, or frontend component. Governance context (ADR-0007 observer
passivity, the Scientific Debt Rule, and the active Stabilization Window)
in `CLAUDE.md` remains authoritative over any development this document's
future-mission map may eventually motivate.*
