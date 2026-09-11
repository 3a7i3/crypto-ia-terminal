# WEB COCKPIT DATA MAP

Status: CANONICAL — R1.1 (WEB-DOC-01)
Basis: WEB COCKPIT DATA MAP R0.1 (accepted), revalidated against source at
commit `1c36ad33c2f9d6263d786aae96f5269f0ded23a5` (also current `origin/main`
and the original base of this document); corrected in R1.1 per MASTER review.
Scope: documentation only. This document changes no machine behavior.

**Parallel PR note (as of R1.1):** `PR #139` ("O-02W-PRE-T1-E REM-C R1:
execution-domain provenance and paper recovery honesty") is open, **draft,
unmerged**, based on the same `main` SHA as this document. Its content
(`ExecutionDomain` enum, `PositionReconciler` domain-compatibility gate,
`MexcSimulator._restore_positions()` evidence-honesty fixes) is described in
this document only as roadmap status (§20), never as canonical current-main
behavior. If #139 merges or moves, this document's basis does not
automatically follow — a future correction round must revalidate.

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
| **O-02W-E1** | Delivered as its own dedicated, ~2000-line contract — the Telegram observation-boundary review, covering per-identity analysis across multiple remediation rounds (R1/R1.1/R1.2). This is a standalone contract, not merely a pointer from the identity registry (that registry is one supporting citation among many inside it). | `docs/contracts/O-02W-E_TELEGRAM_OBSERVATION_BOUNDARY.md` (mission header self-identifies as "O-02W-E1"; `DOCUMENTATION_CONTRACT`) |

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
| Scientific capital | `infra/wallet_sync.py::get_scientific_capital()` — the sole decisional-capital accessor (sizing/risk/EV), pure function independent of exchange mode/state, pinned per ADR-0007/ADR-0018 | Governance | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` | Architecturally separate from real-account observation (see next row); never combined with it (ADR-0018) |
| Real-account balance | `observability/real_accounts.py::RealAccountsObserver` — passive, read-only (`fetch_balance`/`fetch_ticker` only, never places orders); flows into the canonical snapshot's `portfolio_state.real_account_equity_usd`/`real_account_free_usd`/`real_account_stale` when an observer instance is injected by the advisor process | Execution (observation only) | `SOURCE_PROVEN` (mechanism/wiring), `RUNTIME_UNKNOWN` (independent proof the VPS actually injects a live observer each cycle) | `SOURCE_READY` (as a display fact) | `WEB_READY_NOW` (snapshot fields exist) | Display-only by design — architecturally forbidden from sizing/risk (ADR-0007, ADR-0018); never merged with scientific capital |
| Paper equity | `infra/wallet_sync.py::WalletSync.get_balance()` — WALLET_PAPER_CAPITAL-based paper/scientific-capital semantics, published to the snapshot only when `mode == "PAPER"` | Scientific (paper domain) | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` | `PaperTradeRecorder` is a separate component: durable append-only trade-event history, not the equity accessor |
| Paper positions | `paper_trading.paper_portfolio_view.paper_portfolio_view()` reading `MexcSimulator._positions` — the snapshot builder's docstring states this module never iterates `_positions` directly and that position inventory is governed exclusively by this view function | Scientific (paper domain) | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` | `PositionManager` is a distinct, frequently-empty internal store and is **not** the producer of `paper_open_positions_count`/`open_positions[]`/unrealized PnL — do not conflate the two |
| Real positions observation | Not yet a governed snapshot producer; would require exchange-side `fetch_positions()` plus an execution-domain compatibility gate (PAPER vs REAL) to avoid comparing incompatible position stores | Execution | `RUNTIME_UNKNOWN` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | The domain-compatibility gate needed here is proposed, unmerged REM-C R1 scope (PR #139, `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN`) — see §9, §20 |
| Regret v2 | Regret analysis pipeline | Scientific | `DOCUMENTATION_CONTRACT` | `SOURCE_PARTIAL` | `NEEDS_HISTORY_READER` | Historical regret currently lives in append-only files |
| Runtime SHA | `observability/source_evidence.py` | System health | `SOURCE_PROVEN` (mechanism), `RUNTIME_UNKNOWN` (independent proof) | `SOURCE_PARTIAL` | `WEB_READY_NOW` (as self-reported value) | Independent (T-1) confirmation not yet available |
| Deployment evidence | `source_evidence.py` / deploy tags | System health | `DOCUMENTATION_CONTRACT` | `SOURCE_PARTIAL` | `NEEDS_SNAPSHOT_EXPOSURE` | T-1 mission (not started) owns the independent version |
| Liveness (advisor process) | T-1 (independent liveness publisher) | System health | `FUTURE_WORK` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | T-1 not started; snapshot age must never be used as a liveness proxy. Distinct from the health score (see §15): a healthy composite score is not proof of process liveness |
| Order intent — execution authorization | `DecisionPacket.is_actionable()` in the advisor loop's G8 block — decides *whether* to call `exec_engine.create_order()`/`create_futures_order()` at all | Execution authority | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` (as `decision_pipeline` telemetry) | Distinct from order-intent identity (next row) — this row is the gate, not the durable record |
| Order intent — durable identity/journal | `quant_hedge_ai/agents/execution/decision_identity.py::DecisionIdentityJournal` + `order_intent_protocol.py::OrderIntentJournal`/`OrderIntentCoordinator`, wired inside `ExecutionEngine.create_order()`/`create_futures_order()` (REM-B scope, present on current main) — provides durable pre-network decision/intent identity and idempotent duplicate protection | Execution | `SOURCE_PROVEN` for the two confirmed G8 call sites (`core/advisor_loop.py` calls into `exec_engine.create_order`/`create_futures_order`); `PARTIAL` — not exhaustively audited for every other potential caller in the file | `SOURCE_PARTIAL` | `NEEDS_API_EXPOSURE` | Explicitly does NOT cover (by its own docstring): full decision/packet reconstruction, replay of strategy state, partial-fill lifecycle, automatic resubmission after restart — that is REM-C scope |
| ACK | `order_intent_protocol.py` state machine — `ACKNOWLEDGED` is a distinct, non-terminal `IntentState`/`SubmissionOutcome`, never equated with FILLED in the reviewed source (REM-B scope, on current main) | Execution | `SOURCE_PROVEN` (state exists and is distinct), `RUNTIME_UNKNOWN` (real-exchange ACK path) | `SOURCE_PARTIAL` | `BLOCKED_BY_SCIENTIFIC_WORK` | Further truth-ladder labels (PARTIALLY_FILLED, FILLED, POSITION_APPLIED, CLOSED, REALIZED_PNL_FINAL, RESTART_RECONSTRUCTION) were not exhaustively located in this pass — treat as unverified rather than asserting a complete state matrix (§9) |
| Fills | Execution engine / exchange | Execution | `RUNTIME_UNKNOWN` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | Partial-fill lifecycle/fill-quantity reconciliation remains unimplemented on current main; proposed in unmerged REM-C R1 (PR #139) only partly (execution-domain provenance for reconciliation, not the fill engine itself) |
| Realized PnL | `PaperTradeRecorder` (paper, durable trade-event history) / execution ledger (real) | Scientific / Execution | `SOURCE_PROVEN` (paper), `RUNTIME_UNKNOWN` (real) | `SOURCE_READY` (paper) | `NEEDS_HISTORY_READER` (historical), `WEB_READY_NOW` (current snapshot value, paper) | — |

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

**Execution authorization is not the same layer as order-intent identity.**
`DecisionPacket.is_actionable()`/G8 decides *whether* to call
`ExecutionEngine.create_order()`/`create_futures_order()` at all — that is
authorization. Once that gate passes, a separate durable layer takes over
inside `ExecutionEngine`: `quant_hedge_ai/agents/execution/decision_identity.py`'s
`DecisionIdentityJournal` and `order_intent_protocol.py`'s `OrderIntentJournal`
/`OrderIntentCoordinator` persist the decision/intent identity before any
network mutation and provide idempotent duplicate protection. Both layers
are real and wired (REM-B scope, present on current main), but they answer
different questions: G8 asks "is this trade allowed to proceed", the
identity/journal layer asks "has this exact intent already been durably
recorded and can it be safely retried". Caller coverage for the
identity/journal layer is confirmed at the primary G8 execution call sites;
it has not been exhaustively audited across every other potential caller of
`create_order`/`create_futures_order` in `core/advisor_loop.py`, so it is
classified `SOURCE_PARTIAL` for full-file caller coverage, not because the
mechanism itself is incomplete.

---

## 9. Execution Truth Map

**Two distinct efforts must not be conflated: REM-B (present on current
main) and REM-C (proposed, unmerged).** REM-B delivered durable decision
identity (`DecisionIdentityJournal`) and durable pre-network order-intent
identity with idempotent duplicate protection (`OrderIntentJournal`/
`OrderIntentCoordinator`), wired inside `ExecutionEngine` — this is real,
current-main code, not future work. What remains open is the REM-C truth
ladder below: execution-domain provenance for reconciliation, fill-quantity
truth, and full crash-window/partial-fill recovery. REM-C R1 (PR #139) is
**open, draft, unmerged**, based on the same `main` SHA as this document —
its `ExecutionDomain` enum, `PositionReconciler` domain-compatibility gate,
and `MexcSimulator._restore_positions()` evidence-honesty fixes are not yet
part of canonical current-main behavior. Use `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN`
rather than "REM-C not started" — the roadmap has moved past zero, the code
has not yet landed on `main`.

| Stage | Classification | Notes |
|---|---|---|
| DECISION | `CANONICAL_NOW` | `DecisionPacket` + `is_actionable()`, live in the advisor loop |
| INTENT (durable identity) | `CANONICAL_NOW` for the confirmed G8 call sites (REM-B) | `DecisionIdentityJournal`/`OrderIntentJournal`/`OrderIntentCoordinator`, wired inside `ExecutionEngine`; not exhaustively audited for every caller (§8) |
| AUTHORIZATION | `CANONICAL_NOW` | Gate itself is the authorization step (§8) |
| SUBMISSION | `CANONICAL_NOW` (paper, via `MexcSimulator`) / `CANONICAL_NOW` for durable idempotent identity, `PARTIAL` for domain-safe reconciliation (real) — REM-B provides the former; REM-C R1 (unmerged) proposes the domain gate needed for the latter | ADR-0020 is REM-B scope, present on current main |
| ACKNOWLEDGED | `SOURCE_PROVEN` as a distinct state (REM-B, `order_intent_protocol.py`) for paper; `RUNTIME_UNKNOWN` for a real-exchange ACK path | `ACKNOWLEDGED` is never equated with `FILLED` in the reviewed source — they are distinct states in the intent state machine |
| ORDER OBSERVATION | `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` | Execution-domain provenance (needed to safely compare PAPER vs REAL position/order state) is proposed in PR #139, not on main |
| PARTIALLY_FILLED / FILLED | `RUNTIME_UNKNOWN` | Not confirmed as implemented, labeled state on current main in this revalidation pass; do not assert a complete state matrix without further evidence |
| POSITION | `CANONICAL_NOW` (paper, via `paper_portfolio_view()` reading `MexcSimulator._positions` — not `PositionManager`, §7) / `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` (real, domain-safe reconciliation) | — |
| CLOSE | `CANONICAL_NOW` (paper) / `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` (real) | — |
| REALIZED_PNL_FINAL | `CANONICAL_NOW` (paper, via `PaperTradeRecorder`) / `RUNTIME_UNKNOWN` (real) | — |
| RESTART_RECONSTRUCTION | `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` | PAPER-restart evidence-honesty fixes (avoiding fabricated zero-PnL/TP-SL on restart) are PR #139 scope, unmerged |

Do not imply REM-C R2/R3/R4-style completion anywhere: those remain fully
unstarted (canonical `ExecutionEvidence`/`FillRecord`, cumulative exchange
fill journal, partial-fill ingestion/deduplication, exchange fill polling,
real-exchange fee accounting, exchange adapter certification, resubmission
policy) per PR #139's own explicit deferral list.

---

## 10. Paper / Real / Shadow / Burn-in Map

| Component | Status | Evidence |
|---|---|---|
| `MexcSimulator` (`paper_trading/mexc_simulator.py`) | `ACTIVE`; also the authority for paper open positions/unrealized PnL via `paper_portfolio_view()` (§7) | Instantiated directly in the advisor loop bootstrap, gated on advisor-only/`PAPER_TRADING_ENABLED` |
| `PaperTradeRecorder` (`paper_trading/recorder.py`) | `ACTIVE` — durable append-only paper trade-event history and realized PnL; **not** the paper-equity accessor (that is `WalletSync.get_balance()`, §7) | Used as the entry/exit source of truth inside the advisor loop's paper bookkeeping |
| `PositionManager` (`quant_hedge_ai/agents/execution/position_manager.py`) | `SOURCE_REACHABLE` (registered as a lazy factory in the advisor runtime registry); **not** the producer of the snapshot's paper position fields — those come from `paper_portfolio_view()` reading `MexcSimulator._positions` directly (§7). `PositionManager` is a separate, frequently-empty internal store noted as a forensic divergence risk | Do not conflate with `MexcSimulator` as paper-position authority |
| Runtime `PaperTradingEngine` (`quant_hedge_ai/agents/execution/paper_trading_engine.py`) | `ACTIVE`, but in the alternate `quant_hedge_ai/main_system.py` / `main_v91.py` entry points and `system/burn_in.py` | Not found instantiated inside `core/advisor_loop.py`; treat as a separate runtime family (§20 dependency note) |
| `BurninSimulationEngine` (`paper_trading/engine.py`) | `DORMANT / ACTIVATION_UNCONFIRMED` | Only found in module docstring usage examples; no production call site found in `core/advisor_loop.py` or elsewhere. Its own docstring explicitly distinguishes it from the live `PaperTradingEngine` |
| `PaperLedger` (`paper_trading/ledger.py`) | `DORMANT / ACTIVATION_UNCONFIRMED` | Only known caller is `BurninSimulationEngine.__init__`, itself dormant |
| `ShadowTracker` (`scripts/shadow_execution.py`, "S3") | `SOURCE_REACHABLE` — imported and instantiated at advisor-loop bootstrap (`_shadow_s3`), called from the gate/decision path via `_shadow_s3.log_refused(...)` when a gate refuses a trade. `RUNTIME_UNKNOWN`: whether this path actually executes on the VPS (i.e. whether the availability guard is true there) is not provable from source alone — **not** a standalone/offline-only script as previously stated | Distinct from `ShadowExecutionEngine` below — do not conflate the two |
| `ShadowExecutionEngine` (`quant_hedge_ai/agents/execution/shadow_engine.py`) | `SOURCE_REACHABLE` — constructed at advisor-loop bootstrap via a lazy bootstrap-step factory registered alongside `PositionManager`. `RUNTIME_UNKNOWN`: whether this bootstrap step succeeds and executes meaningfully on the VPS is not provable from source alone | Distinct from `ShadowTracker`/S3 above |

None of these are described as active beyond what a traced runtime call
chain supports; `BurninSimulationEngine`/`PaperLedger` stay conservatively
`DORMANT / ACTIVATION_UNCONFIRMED`, and `ShadowTracker`/`ShadowExecutionEngine`
are `SOURCE_REACHABLE` with `RUNTIME_UNKNOWN` VPS-execution proof — a real
call site is not the same claim as independently proven production activity.

---

## 11. Panel Catalog

| Panel | Human question answered | Source | Current readiness | Visualization | Dependency | Future mission |
|---|---|---|---|---|---|---|
| SYSTEM | Is the observable system healthy? | O-02W-C manifest + source evidence | Partial (liveness unresolved) | Status tiles | T-1 | — |
| MARKETS | What markets is the machine watching? | Market state domain | Partial (universe_size missing) | Table | Universe-size producer | WEB-MARKET-01 |
| REGIMES | What regime is detected, how confident? | Regime classifier → market_state | Partial (confidence not wired) | Badge + trend | Regime-confidence transport | WEB-REGIME-01 |
| DECISIONS | What did the machine decide, and why? | DecisionPacket / decision_pipeline | Web ready (current cycle) | Timeline | History reader for past decisions | WEB-DECISION-01 |
| PORTFOLIO | What PAPER portfolio exists? What real-account balance is passively observed? | `paper_portfolio_view()`/`MexcSimulator` (paper positions), `WalletSync.get_balance()` (paper equity), `PaperTradeRecorder` (paper trade history), `RealAccountsObserver` (real balance, display-only) | Web ready (paper); real-account balance snapshot fields exist but VPS-live injection is `RUNTIME_UNKNOWN` | Table + chart | Real-position observation (not just balance) for a full REAL view | WEB-PORTFOLIO-01 |
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
EXECUTION (via `DecisionPacket`/G8, with durable intent identity via REM-B's
`OrderIntentJournal`/`OrderIntentCoordinator`) → ORDERS (paper, via
`MexcSimulator`) → POSITIONS (`paper_portfolio_view()` reading
`MexcSimulator._positions` — not `PositionManager`, §7) → P&L
(`PaperTradeRecorder`).

Unconfirmed / not fabricated: UNIVERSE sizing is not confirmed wired
end-to-end (§7); FILLS and the real-money ORDERS/POSITIONS/P&L joins are
`REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` per §9 and must not be shown as complete.

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
| order intent (durable identity) | Available for confirmed G8 call sites, both paper and real (REM-B: `DecisionIdentityJournal`/`OrderIntentJournal`) |
| submission | Available (paper, via `MexcSimulator`), `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` (domain-safe real submission) |
| ACK | Available as a distinct state (paper, `order_intent_protocol.py`), `RUNTIME_UNKNOWN` (real) |
| fill | `RUNTIME_UNKNOWN` — not confirmed implemented on current main |
| position | Available (paper, via `paper_portfolio_view()`), `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` (real) |
| close | Available (paper), `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` (real) |
| PnL | Available (paper, via `PaperTradeRecorder`), `RUNTIME_UNKNOWN` (real) |
| regret | `NEEDS_HISTORY_READER` |

Any future decision-trace panel must mark the fields not yet proven on
current main as unavailable rather than approximating them.

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
| Health score | `observability/health_score.py::HealthScore.compute()` — a documented, implemented composite (0-100): Memory 25pts, Reliability 25pts, Exchange 20pts, Trading 20pts, Performance 10pts, with CRITICAL/DEGRADED/HEALTHY/PERFECT thresholds. Wired into the canonical snapshot as `system_health.health_score` | `SOURCE_PROVEN`, `WEB_READY_NOW` |
| Exchange connectivity | Execution engine | `RUNTIME_UNKNOWN` |

**T-1 owns independent advisor-process liveness evidence and has not
started.** Snapshot age must never be used as a substitute for boot/process
liveness — a stale snapshot and a dead process are not the same signal,
and conflating them was a known documentation risk in prior drafts.
**The health score is not a liveness proof either** — it is a composite of
memory/reliability/exchange/trading/performance metrics that can be
computed from a stale or cached `MetricsSnapshot`; a healthy score is a
different fact from an independently proven live process, and the two must
never be conflated.

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
| WEB-PORTFOLIO-01 | Paper portfolio + performance panels, plus passive real-account balance display | `SOURCE_READY` (paper positions/equity, real-account balance display) | `WEB_READY_NOW` (current paper + real-balance snapshot fields), `NEEDS_HISTORY_READER` (trend) | History reader for trend view | None known for paper; real-account balance display already has snapshot fields but VPS-live injection is `RUNTIME_UNKNOWN` | Low |
| WEB-EXECUTION-01 | Execution truth map panel (paper first) | `SOURCE_PARTIAL` (REM-B durable identity/intent present; REM-C R1 domain-safe reconciliation and fill truth proposed, unmerged) | `NEEDS_API_EXPOSURE` | REM-C R1 merge for domain-safe real-position reconciliation; REM-C R2+ for fills/ACK truth | Real fills/ACK not implemented; REM-C R1 (PR #139) not yet merged | High if real-money scope is added prematurely |
| WEB-HUMAN-LAB-01 | Human research lab (§17) | Not started | Not started | Full schema/design | Entirely future | Medium (scope creep risk) |

`WEB-DECISION-02 — Promote DecisionPacket` is explicitly **not** included:
DecisionPacket is already the mandatory execution-authority gate (§8); no
promotion mission is needed or valid.

---

## 20. Dependency Map

| Dependency | What it gates | Status |
|---|---|---|
| **REM-B** | Durable decision identity, durable pre-network order-intent identity, idempotent duplicate protection | **Present on current main**, wired inside `ExecutionEngine` (`DecisionIdentityJournal`, `OrderIntentJournal`/`OrderIntentCoordinator`); caller coverage confirmed at the primary G8 execution call sites, not exhaustively audited elsewhere |
| **REM-C** | Execution-domain provenance for reconciliation, PAPER-restart evidence honesty (R1); fill-quantity truth, partial-fill lifecycle, crash-window recovery (R2+) | `REM_C_R1_IN_PROGRESS_NOT_ON_MAIN` — R0 forensic audit and R0.1 correction complete (accepted as basis); **R1 is in an open, draft, unmerged PR (#139)**, based on the same `main` SHA as this document; R2/R3/R4 not started |
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
5. **What PAPER portfolio exists?** — current positions from
   `paper_portfolio_view()` (reading `MexcSimulator._positions`) and equity
   from `WalletSync.get_balance()`, clearly labeled PAPER; a passive,
   display-only real-account balance from `RealAccountsObserver` may be
   shown alongside it, never combined with it.
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
- **Fill truth**: real-money fills, ACK-to-filled progression, and
  partial-fill lifecycle are not implemented on current main; REM-C R1
  (PR #139, unmerged) addresses domain-safe reconciliation and PAPER-restart
  evidence honesty, not the fill engine itself (§9).
- **Real-position reconciliation**: not implemented on current main; a
  domain-compatibility gate (PAPER vs REAL) is required before any
  real-position reconciliation can safely run, and is proposed, unmerged
  REM-C R1 scope (§7, §9, §20). Real-account **balance** (display-only,
  via `RealAccountsObserver`) is a separate, already-wired fact — do not
  conflate balance observation with position reconciliation.
- **Independent liveness**: T-1 not started; snapshot age must not be used
  as a substitute, and neither must the system health score (§15).
- **`BurninSimulationEngine` / `PaperLedger` activation status**: both
  conservatively classified `DORMANT / ACTIVATION_UNCONFIRMED`; no
  production call site found. Any future claim of activation needs fresh
  evidence, not inference from the presence of the class (§10).
- **Shadow component VPS-runtime proof**: `ShadowTracker`/S3 and
  `ShadowExecutionEngine` both have real bootstrap/call-site evidence
  (`SOURCE_REACHABLE`), but whether they actually execute on the live VPS
  is `RUNTIME_UNKNOWN` — a source-reachable call site is not proof of
  production activity (§10).
- **REM-C R1 merge status**: PR #139 is open, draft, and unmerged as of
  this document's R1.1 basis; its content must not be described as
  canonical current-main behavior until it merges and this document is
  revalidated (§9, §20).

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
