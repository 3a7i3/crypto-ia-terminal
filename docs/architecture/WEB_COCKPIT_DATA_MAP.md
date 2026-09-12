# WEB COCKPIT DATA MAP

Status: CANONICAL — R1.3 (WEB-DOC-01)
Basis: WEB COCKPIT DATA MAP R0.1 (accepted), revalidated against source at
commit `1c36ad33c2f9d6263d786aae96f5269f0ded23a5` (original base of this
document); corrected in R1.1, R1.2, and R1.3 per MASTER review. As of R1.3
this branch has been synchronized (normal merge, no rebase) with certified
main at `524a2f78d5de3a041105e8fc330c7f451e36f53c`, which merged REM-C R1
(PR #139, its own R1/R1.1/R1.2/R1.3 rounds, certified HEAD
`6e3fcc8e7441f434edca261cc60b298032c07989`).
Scope: documentation only. This document changes no machine behavior.

**REM-C R1 status (as of R1.3): MERGED / CERTIFIED ON MAIN.** `PR #139` is
closed and merged (merge commit `524a2f78d5de3a041105e8fc330c7f451e36f53c`).
Its content (`ExecutionDomain` provenance, domain/account-safe
`PositionReconciler` semantics, the canonical `PositionManager` API
correction, PAPER restart/recovery evidence honesty, the BootGate
fail-closed fix, and R1.3's provenance/certified-performance evidence
semantics) is now canonical current-main behavior and is described as such
throughout this document (§9, §20). REM-C R2/R3/R4 remain not started.

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
| Regime (label) — source | `core/advisor_loop.py::_adaptive_regime` — a smoothed, N-cycle-consecutive-vote-filtered `AdvancedRegimeDetector` output; this is the actual technical source cited by the canonical operator metric dictionary. `anara_context/modules/*.json` files are static dashboard/documentation metadata (module_id, display_name, key_metrics, etc.) — not executable logic, not a runtime data path, and must never be described as runtime authority | Scientific | `SOURCE_PROVEN` | `SOURCE_READY` | — | `market_state.py`'s `MarketStateSnapshot`/`compose_market_state_snapshot()` models this as a domain concept, but see next row for whether it is actually transported |
| Regime (label) — global Web exposure | `observability/operator_snapshot_builder.py` has **zero references** to `market_state`, `MarketStateSnapshot`, or `compose_market_state_snapshot()` — the domain module is never invoked by the canonical snapshot builder. No `docs/contracts/O-02W-D2_OPERATOR_WEB_COCKPIT.md` contract exists. A regime string does reach the frontend, but only **nested per-record**: `OpenPosition.regime` (`frontend/src/types.ts`, portfolio domain) and `PerSymbolDecision.regime` (decision-pipeline domain), rendered per-row in `PortfolioView.tsx`/`DecisionsView.tsx` | Scientific | `SOURCE_READY` (label itself) | `NOT_CURRENTLY_EXPOSED` as a global panel; `WEB_READY_NOW` only for the narrower per-position/per-symbol regime string already riding inside PORTFOLIO/DECISIONS | `NEEDS_SNAPSHOT_EXPOSURE` for a global Market/Regime domain; a per-symbol regime string inside an existing panel is **not** proof that a global REGIME panel/domain exists (§11, §19, §22) |
| Regime confidence | Computed by `quant_hedge_ai/agents/intelligence/market_regime_classifier.py`'s `RegimeStateTracker` (class at line 56), wired through `core/advisor_runtime_adapters.py` into `core/advisor_loop.py`: constructed at `core/advisor_loop.py:5563-5565` (`_regime_tracker: Any = _profile_bootstrap_step("regime_state_tracker", runtime.RegimeStateTracker)`) and invoked in the main per-cycle loop at `core/advisor_loop.py:6914-6919` (`_rpkt = _regime_tracker.update(_obs)`, "P6 — RegimeStateTracker" block) — a genuine construct-and-invoke production call chain, not merely an import or test-only reference. The canonical snapshot field `market_state.regime_confidence` (`observability/operator/domains/market_state.py`) is a separate object that is never populated from `RegimePacket.confidence` — the `market_state` domain module itself is not invoked by the snapshot builder at all (see row above) | Scientific | `SOURCE_PROVEN` (construction and invocation confirmed in the production call graph; VPS runtime execution itself remains `RUNTIME_UNKNOWN` per §3) | `NEEDS_SNAPSHOT_EXPOSURE` | The computation is real and reachable from the main cycle; the gap is that neither `market_state` (the domain that would carry `regime_confidence`) nor `RegimePacket.confidence` specifically is wired into the snapshot builder's output — do not describe the snapshot field itself as the producer, and do not describe the tracker as merely "referenced" — it is constructed and called |
| Universe size | `market_state.universe_size` domain field | Scientific | `SOURCE_PROVEN` (field), `RUNTIME_UNKNOWN` (population) | `SOURCE_UNSAFE` | `NEEDS_SNAPSHOT_EXPOSURE` | No confirmed producer (field comment: "INCONCLUSIVE, no confirmed producer found") |
| DecisionPacket actionability | `DecisionPacket.is_actionable()` | Execution authority | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` (as `decision_pipeline` telemetry) | — |
| Blockers | Legacy `trade_allowed` / blockers list | Analysis/gating input (not authority) | `LEGACY` | `SOURCE_READY` | `WEB_READY_NOW` | Superseded as authority by DecisionPacket; kept for observability and TYPE-A-DISAGREEMENT auditing |
| Scientific capital | `infra/wallet_sync.py::get_scientific_capital()` — the sole decisional-capital accessor (sizing/risk/EV), pure function independent of exchange mode/state, pinned per ADR-0007/ADR-0018 | Governance | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` | Architecturally separate from real-account observation (see next row); never combined with it (ADR-0018) |
| Real-account balance | `observability/real_accounts.py::RealAccountsObserver` — passive, read-only (`fetch_balance`/`fetch_ticker` only, never places orders); flows into the canonical snapshot's `portfolio_state.real_account_equity_usd`/`real_account_free_usd`/`real_account_stale` when an observer instance is injected by the advisor process | Execution (observation only) | `SOURCE_PROVEN` (mechanism/wiring), `RUNTIME_UNKNOWN` (independent proof the VPS actually injects a live observer each cycle) | `SOURCE_READY` (as a display fact) | `WEB_READY_NOW` (snapshot fields exist) | Display-only by design — architecturally forbidden from sizing/risk (ADR-0007, ADR-0018); never merged with scientific capital |
| Paper equity | `infra/wallet_sync.py::WalletSync.get_balance()` — WALLET_PAPER_CAPITAL-based paper/scientific-capital semantics, published to the snapshot only when `mode == "PAPER"` | Scientific (paper domain) | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` | `PaperTradeRecorder` is a separate component: durable append-only trade-event history, not the equity accessor |
| Paper positions | `paper_trading.paper_portfolio_view.paper_portfolio_view()` reading `MexcSimulator._positions` — the snapshot builder's docstring states this module never iterates `_positions` directly and that position inventory is governed exclusively by this view function | Scientific (paper domain) | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` | `PositionManager` is a distinct, frequently-empty internal store and is **not** the producer of `paper_open_positions_count`/`open_positions[]`/unrealized PnL — do not conflate the two |
| Paper restored-position provenance | `MexcSimulator._restore_positions()` (REM-C R1.3, merged): a restored position's `personality` field always stays `"restored"` regardless of evidence completeness; `restored_evidence_gaps` carries completeness separately. The snapshot builder derives a three-tier `tp_sl_source` from that gap list: `"original"` (never restored), `"restored_default"` (reconstructed on incomplete evidence), `"restored_original"` (durably recovered, complete evidence) | Scientific (paper domain) | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` | **RESTORED != EVIDENCE_COMPLETE**: never present all restored positions as reconstructed defaults, and never infer "not restored" merely from an evidence-complete `personality` — check `tp_sl_source`/`restored_evidence_gaps` explicitly |
| Real positions observation | Not yet a governed snapshot producer for actual position content; the execution-domain compatibility gate needed to safely compare PAPER vs REAL position stores is now merged (REM-C R1, `system/position_reconciler.py`'s domain-safe `PositionReconciler`), but this gates *reconciliation safety*, not the missing exchange-side `fetch_positions()` truth itself | Execution | `RUNTIME_UNKNOWN` (real position content) | `SOURCE_UNSAFE` (real position content itself; the domain-safety gate is `SOURCE_READY`) | `BLOCKED_BY_SCIENTIFIC_WORK` | REM-C R1 (merged, current main) supplies the domain-safety gate; real-money order-observation/fill/position truth (REM-C R2/R3) remains not started — see §9, §20 |
| Regret v2 — current state | `observability/operator/domains/regret_state.py`'s `RegretStateSnapshot`/`compose_regret_state_snapshot()` (pending counts, horizon status, freshness) is consumed by `operator_summary.py`, but `observability/operator_snapshot_builder.py` has **zero references** to `regret_state`/`RegretStateSnapshot` — this current-state structure exists at the domain-composition layer but is not wired into the canonical snapshot | Scientific | `SOURCE_PROVEN` (domain structure exists and is composed) | `SOURCE_PARTIAL` (not wired to the transported snapshot) | `NEEDS_SNAPSHOT_EXPOSURE` | Distinct from historical events (next row); `frontend/src/views/NotExposedView.tsx` explicitly documents the regret endpoint as intentionally not exposed today |
| Regret v2 — historical events | Regret analysis pipeline, append-only (`regret_analysis.jsonl` or similar) | Scientific | `DOCUMENTATION_CONTRACT` | `SOURCE_PARTIAL` | `NEEDS_HISTORY_READER` | Event-level timeline/history; requires a governed history reader/projection, distinct from the current-state row above |
| Runtime SHA | `observability/source_evidence.py` | System health | `SOURCE_PROVEN` (mechanism), `RUNTIME_UNKNOWN` (independent proof) | `SOURCE_PARTIAL` | `WEB_READY_NOW` (as self-reported value) | Independent (T-1) confirmation not yet available |
| Deployment evidence — transport | `observability/source_evidence.py`'s `DeploymentEvidence` (embedded in the evidence envelope) → validated in `observability/operator_api/reader.py` (`_validate_deployment_evidence`, checked against `snapshot.get("deployment_evidence")`) → typed in `frontend/src/types.ts` (`DeploymentEvidenceStatus`, `DeploymentEvidence`, `deployment_evidence` field on the snapshot type) | System health | `SOURCE_PROVEN` (full chain traced) | `SOURCE_PARTIAL` (self-reported; independent T-1 confirmation not yet available) | `WEB_READY_NOW` (schema/typed transport confirmed snapshot→API→client) | Confirmed **not yet rendered**: no `frontend/src/views/*.tsx` file references `deployment_evidence` or "deployment" — transport-ready is not the same claim as visually presented; a UI gap, not a transport gap |
| Liveness (advisor process) | T-1 (independent liveness publisher) | System health | `FUTURE_WORK` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | T-1 not started; snapshot age must never be used as a liveness proxy. Distinct from the health score (see §15): a healthy composite score is not proof of process liveness |
| Order intent — execution authorization | `DecisionPacket.is_actionable()` in the advisor loop's G8 block — decides *whether* to call `exec_engine.create_order()`/`create_futures_order()` at all | Execution authority | `SOURCE_PROVEN` | `SOURCE_READY` | `WEB_READY_NOW` (as `decision_pipeline` telemetry) | Distinct from order-intent identity (next row) — this row is the gate, not the durable record |
| Order intent — durable identity/journal (**externally reachable execution only**) | `quant_hedge_ai/agents/execution/decision_identity.py::DecisionIdentityJournal` + `order_intent_protocol.py::OrderIntentJournal`/`OrderIntentCoordinator`, wired inside `ExecutionEngine`'s live-submission path (`_place_live_order`) and inside `create_futures_order()` (testnet, always gated). **`create_order()`'s PAPER branch (`self._live` false or no exchange) does not traverse this protocol at all** — it returns a plain simulated dict; passing a `decision_id` argument alone does not route paper mode through REM-B (confirmed by the method's own docstring) | Execution | `SOURCE_PROVEN` for the live/testnet call sites; explicitly **not applicable** to the `MexcSimulator` paper path | `SOURCE_PARTIAL` | `NEEDS_API_EXPOSURE` | Explicitly does NOT cover (by its own docstring): full decision/packet reconstruction, replay of strategy state, partial-fill lifecycle, automatic resubmission after restart — that is REM-C scope. Do not describe this journal as PAPER execution truth |
| ACK (**externally reachable execution only**) | `order_intent_protocol.py` state machine — `ACKNOWLEDGED` is a distinct, non-terminal `IntentState`/`SubmissionOutcome`, produced only on the live/testnet submission path (`_place_live_order`, `create_futures_order`). `MexcSimulator`'s paper fill path never produces `ACKNOWLEDGED` — grepping the simulator module for it returns zero hits. Never equated with FILLED in the reviewed source | Execution | `SOURCE_PROVEN` (state exists and is distinct, live/testnet path), `RUNTIME_UNKNOWN` (real-exchange ACK on a live account) | `SOURCE_PARTIAL` | `BLOCKED_BY_SCIENTIFIC_WORK` | `ACKNOWLEDGED` is a REM-B externally-reachable-submission concept, **not** a PAPER-simulator order state. PAPER's own execution state (simulated fill) is tracked separately by `MexcSimulator`/`PaperTradeRecorder`, not by this state machine. Further truth-ladder labels (PARTIALLY_FILLED, FILLED, POSITION_APPLIED, CLOSED, RESTART_RECONSTRUCTION) remain `RUNTIME_UNKNOWN`/unimplemented on current main (§9) |
| Fills | Execution engine / exchange | Execution | `RUNTIME_UNKNOWN` | `SOURCE_UNSAFE` | `BLOCKED_BY_SCIENTIFIC_WORK` | Partial-fill lifecycle/fill-quantity reconciliation, order-observation truth, and fill-based position reconstruction do not exist anywhere on current main (confirmed absent by direct search of `quant_hedge_ai/agents/execution/` and `system/`); REM-C R1 (merged, current main) does not implement any of these — its scope was execution-domain provenance for reconciliation, the `PositionManager` API fix, and PAPER-restart evidence honesty only; fill truth is REM-C R2/R3, not started (§9) |
| Realized PnL — historical (paper) | `PaperTradeRecorder` (durable, append-only paper trade-event history in `paper_trades.jsonl`); R1.3 additionally separates the **certified** subset (`is_win is not None`, not `pnl_fee_evidence_incomplete`) from the raw `total_closed` count in `PaperTradeRecorder.summary()` — `win_rate`/`target_30_trades`/`go_live_ready` are computed only over the certified subset, with `certified_closed`/`excluded_unevidenced_count` reported alongside the raw total | Scientific | `SOURCE_PROVEN` | `SOURCE_READY` | `NEEDS_HISTORY_READER` | Schema/transport for this history exists; no governed history reader exists yet to serve it to the Web. Any future history reader/panel must surface the certified/excluded split, not just a raw win rate — an unknown-outcome or fee-evidence-incomplete trade must never be silently counted as a certified performance observation |
| Realized PnL — current canonical snapshot value | `observability/operator_snapshot_builder.py:673` explicitly sets `paper_realized_pnl_usd=unavailable()` — a bare, hardcoded non-value, not a computation gap awaiting wiring. The field/API/typed-client schema chain does exist (`frontend/src/types.ts` carries `paper_realized_pnl_usd: ObservedValue<number>`), riding the same generic `ObservedValue` passthrough as other portfolio fields | Scientific | `SOURCE_PARTIAL` (schema/plumbing exists; the value itself is not currently materialized — not a stronger claim than that) | `WEB_READY_NOW` for the field/schema transport (snapshot → API → typed client all understand and carry the explicit `unavailable`/`ObservedValue` semantic); the *value* is not available | **`SCHEMA_READY != VALUE_AVAILABLE`**: do not describe current-snapshot paper realized PnL as unexposed/`NEEDS_SNAPSHOT_EXPOSURE` — the transport is ready and correctly reports `unavailable`; equally, never describe the number itself as ready or display a fabricated figure |

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
authorization. Once that gate passes, a separate durable layer can take
over inside `ExecutionEngine`, but **only on the externally reachable
execution path**: `quant_hedge_ai/agents/execution/decision_identity.py`'s
`DecisionIdentityJournal` and `order_intent_protocol.py`'s `OrderIntentJournal`
/`OrderIntentCoordinator` persist the decision/intent identity before any
network mutation and provide idempotent duplicate protection, on
`_place_live_order` (real) and `create_futures_order` (testnet, always
gated). **`create_order()`'s PAPER branch does not call into this layer at
all** — confirmed by direct inspection of its control flow: when
`self._live` is false or no exchange is configured, it returns a plain
simulated-fill dict, never touching `OrderIntentCoordinator`. Supplying a
`decision_id` argument does not change this; the method's own docstring
states this explicitly. So: G8 asks "is this trade allowed to proceed" for
both PAPER and REAL; the identity/journal layer asks "has this exact
*externally reachable* intent already been durably recorded and can it be
safely retried" — a question that only applies once execution actually
reaches, or is capable of reaching, a real or testnet exchange. PAPER
execution state (simulated fills) is tracked separately by `MexcSimulator`/
`PaperTradeRecorder`, never by `OrderIntentJournal`/`ACKNOWLEDGED`. Caller
coverage for the identity/journal layer, on the paths where it does apply,
is confirmed at the primary G8-driven live/testnet call sites; it has not
been exhaustively audited across every other potential caller in
`core/advisor_loop.py`, so it is classified `SOURCE_PARTIAL` for full-file
caller coverage, not because the mechanism itself is incomplete.

---

## 9. Execution Truth Map

**Two distinct efforts must not be conflated: REM-B (present on current
main) and REM-C (R1 merged/certified on main; R2/R3/R4 not started).**
REM-B delivered durable decision identity (`DecisionIdentityJournal`) and
durable pre-network order-intent identity with idempotent duplicate
protection (`OrderIntentJournal`/`OrderIntentCoordinator`), wired inside
`ExecutionEngine` **on the externally reachable execution path only** (live
and testnet submission) — this does not describe PAPER/`MexcSimulator`
behavior (§8). **REM-C R1 is MERGED / CERTIFIED ON MAIN** — merge commit
`524a2f78d5de3a041105e8fc330c7f451e36f53c` (certified R1 implementation
HEAD `6e3fcc8e7441f434edca261cc60b298032c07989`, from PR #139) — and is
narrowly scoped to: `ExecutionDomain` provenance, domain/account-safe
`PositionReconciler` behavior, the canonical `PositionManager` API
correction (`get_open_positions()` → `get_open()`), PAPER restart/recovery
evidence honesty (including the R1.3 provenance/certified-performance
semantics, §7), and the associated BootGate fail-closed guard fix. **R1
does not implement order-observation truth, partial-fill truth, filled
truth, real close truth, `REALIZED_PNL_FINAL`, exchange fill polling, or
fill-based position reconstruction** — `docs/adr/0021-execution-domain-provenance-and-paper-recovery-honesty.md`
explicitly defers all of these to REM-C R2/R3/R4, and direct search of
`quant_hedge_ai/agents/execution/` and `system/` on current main confirms
none of these concepts exist yet anywhere in the codebase. Do not call R1
"in progress" — it is merged; reserve "not started" for R2/R3/R4.

| Stage | Classification | Notes |
|---|---|---|
| DECISION | `CANONICAL_NOW` | `DecisionPacket` + `is_actionable()`, live in the advisor loop, applies to both PAPER and REAL |
| DURABLE EXTERNAL INTENT/SUBMISSION IDENTITY | `CANONICAL_NOW` (REM-B) for the live/testnet call sites only | `DecisionIdentityJournal`/`OrderIntentJournal`/`OrderIntentCoordinator`, wired inside `ExecutionEngine`'s live/testnet path; **does not apply to `create_order()`'s PAPER branch** (§8); not exhaustively audited for every caller |
| AUTHORIZATION | `CANONICAL_NOW` | Gate itself is the authorization step (§8) |
| SUBMISSION — PAPER | `CANONICAL_NOW` | `MexcSimulator` simulated fill; entirely separate from the REM-B identity/journal protocol |
| SUBMISSION — REAL/TESTNET | `CANONICAL_NOW` for durable idempotent identity (REM-B) and for domain-safe reconciliation (REM-C R1, merged) | ADR-0020 (REM-B) and ADR-0021 (REM-C R1) both present on current main |
| ACKNOWLEDGED | `SOURCE_PROVEN` as a distinct state (REM-B, `order_intent_protocol.py`), **externally-reachable-submission only — never produced by `MexcSimulator`'s paper path** (zero hits on direct search) | `!= FILLED`; `!=` any PAPER-simulator state |
| ORDER OBSERVATION | `RUNTIME_UNKNOWN`; **not** R1 scope | REM-C R2/R4 dependency, not started — confirmed absent from current main, explicitly deferred by ADR-0021 |
| PARTIALLY_FILLED | `RUNTIME_UNKNOWN`; **not** R1 scope | REM-C R2/R3 dependency, not started — confirmed absent from current main, explicitly deferred by ADR-0021 |
| FILLED | `RUNTIME_UNKNOWN`; **not** R1 scope | REM-C R2/R3 dependency, not started — confirmed absent from current main, explicitly deferred by ADR-0021 |
| POSITION FROM VERIFIED FILLS | `RUNTIME_UNKNOWN`; **not** R1 scope | REM-C R3 dependency, not started (real). Paper positions are `CANONICAL_NOW` via `paper_portfolio_view()` reading `MexcSimulator._positions` — not `PositionManager`, §7 — and are unaffected by this row |
| REAL CLOSE / REALIZED_PNL_FINAL | `RUNTIME_UNKNOWN`; **not** R1 scope | REM-C R3/R4 dependency, not started (real). Paper close/realized-PnL-history is `CANONICAL_NOW` via `PaperTradeRecorder` (with the R1.3 certified/excluded split, §7), though the *current-snapshot* paper realized-PnL value is `unavailable()` today (transport is `WEB_READY_NOW`, §7) |
| PAPER RESTART HONESTY | `CANONICAL_NOW` | Avoiding fabricated zero-PnL/TP-SL on restart, plus the R1.3 provenance (`tp_sl_source` three-tier) and certified-performance semantics — REM-C R1, merged/certified on main (§7) |

Do not imply REM-C R1 implements the fill engine, order observation, or
real close/PnL truth in any form — those rows stay `RUNTIME_UNKNOWN` and
are REM-C R2/R3/R4 scope. Do not imply REM-C R2/R3/R4-style completion
anywhere: those remain fully unstarted (canonical `ExecutionEvidence`/
`FillRecord`, cumulative exchange fill journal, partial-fill ingestion/
deduplication, exchange fill polling, real-exchange fee accounting,
exchange adapter certification, resubmission policy, TESTNET/real exchange
reconciliation certification).

---

## 10. Paper / Real / Shadow / Burn-in Map

**Terminology note:** none of the rows below use bare `ACTIVE`. Every
component in this table has only source-level evidence (a real constructor
or call site inside `core/advisor_loop.py` or a sibling entrypoint) — no
component here has independent T-1/liveness proof, a systemd unit tied to
its specific class, or a cited VPS log excerpt. `SOURCE_REACHABLE`/`WIRED`
means the call chain is real and traced; `RUNTIME_UNKNOWN` means whether it
actually executes on the deployed VPS is not provable from source alone.
This distinction (source call chain != production runtime proof) is the
project's own stated evidence standard (§3) and is applied uniformly here.

| Component | Status | Evidence |
|---|---|---|
| `MexcSimulator` (`paper_trading/mexc_simulator.py`) | `SOURCE_REACHABLE`/`WIRED` (init-time log statement in source, not an independent VPS log); `RUNTIME_UNKNOWN` for VPS execution; also the authority for paper open positions/unrealized PnL via `paper_portfolio_view()`, and for restored-position provenance (`tp_sl_source`/`restored_evidence_gaps`, REM-C R1.3) (§7) | Instantiated directly in the advisor loop bootstrap, gated on advisor-only/`PAPER_TRADING_ENABLED` |
| `PaperTradeRecorder` (`paper_trading/recorder.py`) | `SOURCE_REACHABLE`/`WIRED`; `RUNTIME_UNKNOWN` for VPS execution — only referenced in advisor-loop comments as "source de vérité entry/exit", no independent proof artifact found; durable append-only paper trade-event history, now with the R1.3 certified/excluded split in `summary()` (§7); **not** the paper-equity accessor (that is `WalletSync.get_balance()`, §7) | Used as the entry/exit source of truth inside the advisor loop's paper bookkeeping |
| `PositionManager` (`quant_hedge_ai/agents/execution/position_manager.py`) | `SOURCE_REACHABLE` (registered as a lazy factory in the advisor runtime registry); its `get_open()` API naming is now the canonical, merged name (REM-C R1 fixed the reconciler's stale `get_open_positions()` call site); **still not** the producer of the snapshot's paper position fields — those come from `paper_portfolio_view()` reading `MexcSimulator._positions` directly (§7). `PositionManager` is a separate, frequently-empty internal store noted as a forensic divergence risk | Do not conflate with `MexcSimulator` as paper-position authority |
| Runtime `PaperTradingEngine` (`quant_hedge_ai/agents/execution/paper_trading_engine.py`) | `SOURCE_REACHABLE`/`WIRED` in the alternate `quant_hedge_ai/main_system.py` / `main_v91.py` entry points and `system/burn_in.py`; `RUNTIME_UNKNOWN` for VPS execution — no systemd unit or log ties this specific class to the deployed process | Not found instantiated inside `core/advisor_loop.py`; treat as a separate runtime family (§20 dependency note) |
| `BurninSimulationEngine` (`paper_trading/engine.py`) | `DORMANT / ACTIVATION_UNCONFIRMED` | Only found in module docstring usage examples; no production call site found in `core/advisor_loop.py` or elsewhere. Its own docstring explicitly distinguishes it from the live `PaperTradingEngine` |
| `PaperLedger` (`paper_trading/ledger.py`) | `DORMANT / ACTIVATION_UNCONFIRMED` | Only known caller is `BurninSimulationEngine.__init__`, itself dormant |
| `ShadowTracker` (`scripts/shadow_execution.py`, "S3") | `SOURCE_REACHABLE`/`WIRED` — imported and instantiated at advisor-loop bootstrap (`_shadow_s3`), called from the gate/decision path via `_shadow_s3.log_refused(...)` when a gate refuses a trade. `RUNTIME_UNKNOWN`: whether this path actually executes on the VPS (i.e. whether the availability guard is true there) is not provable from source alone — **not** a standalone/offline-only script as previously stated | Distinct from `ShadowExecutionEngine` below — do not conflate the two |
| `ShadowExecutionEngine` (`quant_hedge_ai/agents/execution/shadow_engine.py`) | `SOURCE_REACHABLE`/`WIRED` — constructed at advisor-loop bootstrap via a lazy bootstrap-step factory registered alongside `PositionManager`. `RUNTIME_UNKNOWN`: whether this bootstrap step succeeds and executes meaningfully on the VPS is not provable from source alone | Distinct from `ShadowTracker`/S3 above |

None of these are described as active beyond what a traced runtime call
chain supports; `BurninSimulationEngine`/`PaperLedger` stay conservatively
`DORMANT / ACTIVATION_UNCONFIRMED`, and every other row is `SOURCE_REACHABLE`/
`WIRED` with `RUNTIME_UNKNOWN` VPS-execution proof — a real call site is not
the same claim as independently proven production activity, for any
component in this table.

---

## 11. Panel Catalog

| Panel | Human question answered | Source | Current readiness | Visualization | Dependency | Future mission |
|---|---|---|---|---|---|---|
| SYSTEM | Is the observable system healthy? | O-02W-C manifest + source evidence, including `deployment_evidence` (transport `WEB_READY_NOW`, §7) | Partial (liveness unresolved; `deployment_evidence` is transport-ready but not yet rendered in any view — a UI gap, not a transport gap) | Status tiles | T-1; rendering `deployment_evidence` in a view | — |
| MARKETS | What markets is the machine watching? | Market state domain | Partial (universe_size missing) | Table | Universe-size producer | WEB-MARKET-01 |
| REGIMES | What regime is detected globally, how confident? | `advisor_loop._adaptive_regime` (label, source-ready) / `RegimeStateTracker`→`RegimePacket.confidence` (confidence, constructed+invoked in production but not propagated to the snapshot) | **Not currently exposed as a global panel** — neither the label nor confidence is wired into the canonical snapshot via `market_state`; only a narrower per-position/per-symbol regime string already rides inside PORTFOLIO/DECISIONS | Badge + trend (future) | Wiring `market_state`/`RegimePacket.confidence` into the snapshot builder | WEB-REGIME-01 |
| DECISIONS | What did the machine decide, and why? | DecisionPacket / decision_pipeline | Web ready (current cycle) | Timeline | History reader for past decisions | WEB-DECISION-01 |
| PORTFOLIO | What PAPER portfolio exists? What real-account balance is passively observed? | `paper_portfolio_view()`/`MexcSimulator` (paper positions), `WalletSync.get_balance()` (paper equity), `PaperTradeRecorder` (paper trade history), `RealAccountsObserver` (real balance, display-only) | Web ready (paper); real-account balance snapshot fields exist but VPS-live injection is `RUNTIME_UNKNOWN` | Table + chart | Real-position observation (not just balance) for a full REAL view | WEB-PORTFOLIO-01 |
| PERFORMANCE | How is paper performance trending? | `PaperTradeRecorder` history (durable, `SCHEMA_READY` but current-snapshot realized PnL is `unavailable()` — §7) | Needs history reader | Chart | Governed JSONL projection | WEB-PORTFOLIO-01 |
| REGRET | Was a good trade missed or refused? (current state); what happened historically? (events) | `regret_state.py`'s `RegretStateSnapshot` (current state, not wired to snapshot) / Regret v2 pipeline JSONL (historical events) | Current state needs snapshot exposure; historical events need a history reader — two distinct gaps, not one | Table (current status tile + historical table) | Snapshot exposure (current state) + governed projection (history) | WEB-REGRET-01 |
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
EXECUTION (via `DecisionPacket`/G8 — PAPER does not traverse REM-B's
`OrderIntentJournal`/`OrderIntentCoordinator`, §8) → ORDERS (paper, via
`MexcSimulator`) → POSITIONS (`paper_portfolio_view()` reading
`MexcSimulator._positions` — not `PositionManager`, §7) → P&L (historical,
via `PaperTradeRecorder`; the *current-snapshot* realized-PnL value is
`unavailable()`, §7).

Unconfirmed / not fabricated: UNIVERSE sizing is not confirmed wired
end-to-end (§7); regime label/confidence are not exposed as a global panel
— only a per-position/per-symbol regime string exists today (§7); FILLS
and the real-money ORDERS/POSITIONS/P&L joins are `RUNTIME_UNKNOWN` and are
REM-C R2/R3/R4 scope, not started (§9) — must not be shown as complete or
as R1 deliverables (R1 is merged, but its scope was domain provenance and
PAPER-restart honesty, not fill/order/close truth).

---

## 13. Decision Trace

The eventual per-decision trace an operator should see, and its current
honesty status:

| Field | Status |
|---|---|
| `trace_id` | Available (execution_trace.py) |
| `decision_id` | Available |
| signal | Available |
| regime | Label source-ready; global panel not currently exposed — only a per-position/per-symbol regime string exists; confidence computed (constructed+invoked in production) but not propagated to the snapshot (§7) |
| blockers | Available (legacy, telemetry) |
| actionability | Available (`is_actionable()`) |
| order intent — PAPER | Available: `MexcSimulator` simulated order, no REM-B journal involved (§8) |
| order intent — durable external identity | Available only on the live/testnet call sites (REM-B: `DecisionIdentityJournal`/`OrderIntentJournal`); does not apply to PAPER |
| submission | Available (paper, via `MexcSimulator`); domain-safe real submission reconciliation now `CANONICAL_NOW` (REM-C R1, merged) — fill/ACK-to-filled truth itself remains `RUNTIME_UNKNOWN` (REM-C R2/R3, not started) |
| ACK | Available as a distinct state on the live/testnet path only (`order_intent_protocol.py`); never produced by `MexcSimulator`; `RUNTIME_UNKNOWN` for a real-exchange outcome |
| fill | `RUNTIME_UNKNOWN` — not confirmed implemented on current main; not REM-C R1 scope |
| position | Available (paper, via `paper_portfolio_view()`, with restored-provenance tiers §7); `RUNTIME_UNKNOWN` (real, from verified fills) — REM-C R3 scope, not started |
| close | Available (paper); `RUNTIME_UNKNOWN` (real) — REM-C R3/R4 scope, not started |
| PnL — historical | `PaperTradeRecorder` (paper, `SOURCE_READY`, certified/excluded split, needs history reader); `RUNTIME_UNKNOWN` (real) |
| PnL — current snapshot value | Transport `WEB_READY_NOW` (typed field, explicit `unavailable` semantic); value itself `unavailable()` today (paper) — never show a fabricated number (§7) |
| regret — current state | `NEEDS_SNAPSHOT_EXPOSURE` — `RegretStateSnapshot` exists but is not wired to the canonical snapshot (§7) |
| regret — historical events | `NEEDS_HISTORY_READER` |

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
| Deployment evidence | `source_evidence.py` + deploy tags | Self-reported; full schema/typed transport confirmed (`WEB_READY_NOW`, §7), but not currently rendered in any React view — a UI gap, not a transport gap; T-1 owns the independent (non-self-reported) version |
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
| WEB-REGIME-01 | Global regime + confidence panel (label and confidence are both currently only per-position/per-symbol, never a global domain) | `SOURCE_READY` (label, `_adaptive_regime`), `SOURCE_PROVEN`/construct-and-invoke-confirmed (confidence, `RegimeStateTracker`, not propagated) | `NEEDS_SNAPSHOT_EXPOSURE` for both — `market_state` domain is not wired into the snapshot builder at all | Wiring `market_state`/`compose_market_state_snapshot()` and `RegimePacket.confidence` into the snapshot builder | Neither label nor confidence reaches the Web as a global fact today; only nested per-record strings do | Low |
| WEB-DATA-01 | Data explorer, snapshot/dataset browsing | `SOURCE_READY` (manifests) | `NEEDS_API_EXPOSURE` | Manifest API routes | None known | Low |
| WEB-REGRET-01 | Regret v2 panel — current state AND historical events (two distinct gaps) | `SOURCE_READY` (current-state domain structure, `RegretStateSnapshot`), `SOURCE_PARTIAL` (historical pipeline) | `NEEDS_SNAPSHOT_EXPOSURE` (current state — not wired to the canonical snapshot), `NEEDS_HISTORY_READER` (historical events) | Snapshot exposure for current state; governed history reader for events | N thresholds (see CLAUDE.md) still unmet for historical statistical validity; current-state exposure has no statistical blocker, only wiring | Medium (statistical validity for history); Low (current state) |
| WEB-MARKET-01 | Market/universe panel | `SOURCE_UNSAFE` (universe_size) | `NEEDS_SNAPSHOT_EXPOSURE` | Universe-size producer | No confirmed producer | Medium |
| WEB-PORTFOLIO-01 | Paper portfolio + performance panels, plus passive real-account balance display | `SOURCE_READY` (paper positions/equity, real-account balance display) | `WEB_READY_NOW` (current paper + real-balance snapshot fields), `NEEDS_HISTORY_READER` (trend) | History reader for trend view | None known for paper; real-account balance display already has snapshot fields but VPS-live injection is `RUNTIME_UNKNOWN` | Low |
| WEB-EXECUTION-01 | Execution truth map panel (paper first) | `SOURCE_READY` (REM-B: durable external intent/submission identity, ACK state; REM-C R1: domain provenance/reconciliation/PAPER-restart recovery honesty — both merged/certified on current main); `SOURCE_UNSAFE` (REM-C R2/R3/R4: order-observation/fill/position/real-PnL truth — not started, unscoped) | `NEEDS_API_EXPOSURE` for what's merged (REM-B + REM-C R1); `BLOCKED_BY_SCIENTIFIC_WORK` for fills/order-observation/real-close truth | REM-C R2/R3/R4 (fully unscoped, not started) for fills/order-observation/real-close truth | Real fills/order-observation truth not implemented and not yet scoped by any mission | High if real-money fill/PnL scope is added prematurely — remains fully blocked on REM-C R2/R3/R4, none of which exist |
| WEB-HUMAN-LAB-01 | Human research lab (§17) | Not started | Not started | Full schema/design | Entirely future | Medium (scope creep risk) |

`WEB-DECISION-02 — Promote DecisionPacket` is explicitly **not** included:
DecisionPacket is already the mandatory execution-authority gate (§8); no
promotion mission is needed or valid.

---

## 20. Dependency Map

| Dependency | What it gates | Status |
|---|---|---|
| **REM-B** | Durable decision identity, durable pre-network order-intent identity, idempotent duplicate protection | **Present on current main**, wired inside `ExecutionEngine` (`DecisionIdentityJournal`, `OrderIntentJournal`/`OrderIntentCoordinator`); caller coverage confirmed at the primary G8 execution call sites, not exhaustively audited elsewhere |
| **REM-C** | Execution-domain provenance for reconciliation, PAPER-restart evidence honesty, restored-provenance/certified-performance semantics (R1); fill-quantity truth, partial-fill lifecycle, crash-window recovery, order-observation/real-close/real-PnL truth (R2+) | R0 forensic audit: complete. R0.1 correction: complete. **R1: MERGED / CERTIFIED ON MAIN** — merge commit `524a2f78d5de3a041105e8fc330c7f451e36f53c` (certified implementation HEAD `6e3fcc8e7441f434edca261cc60b298032c07989`, PR #139, its own R1/R1.1/R1.2/R1.3 rounds). R2/R3/R4: not started |
| **T-1** | Independent advisor-process liveness, independent deployment/SHA confirmation | Not started (explicitly, per O-02W-E and O-02W-B contracts) |
| **Runtime observation** | Any claim that a component is "active" in production, beyond a traced call chain | Confirmed only where a real runtime call site was found (§10, §12); otherwise `RUNTIME_UNKNOWN` |
| **F-00** | A separate, later scientific measurement pass, gated on its own criteria | **DEFINED / REFERENCED IN GOVERNANCE — NOT STARTED.** Explicitly not O-02W-B, C, D, or E, and not any cockpit-implementation mission. |

---

## 21. Simple Cockpit MVP

The smallest useful cockpit, using only currently trustworthy facts:

1. **Is the observable system healthy?** — API readiness, snapshot
   freshness, self-reported runtime SHA (with the caveat that independent
   T-1 liveness is not yet available).
2. **What markets/regimes are visible?** — only the per-position/
   per-symbol regime string already riding inside PORTFOLIO/DECISIONS
   (sourced from `advisor_loop._adaptive_regime`); a global regime/confidence
   panel is not currently exposed (no `market_state` wiring into the
   snapshot) and must not be presented as if it existed.
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
- **Global regime/confidence not exposed**: `market_state`/
  `compose_market_state_snapshot()` is never invoked by
  `operator_snapshot_builder.py` — neither the regime label nor
  `RegimeStateTracker`'s confidence (constructed and invoked in the
  production call graph at `core/advisor_loop.py:5563-5565`/`:6914-6919`)
  reaches the canonical snapshot as a global fact. Only a narrower
  per-position/per-symbol regime string, riding inside the
  PORTFOLIO/DECISIONS domains, is currently transported. Do not treat that
  narrower fact as proof that a global REGIME panel/domain exists (§7,
  §11, §19).
- **`paper_realized_pnl_usd` current value vs transport**: the snapshot
  field/API/typed-client schema chain fully exists (`WEB_READY_NOW` for
  transport) and correctly reports `unavailable()` — this is not a
  transport gap. The *value itself* is not materialized
  (`operator_snapshot_builder.py:673`). Historical realized PnL exists
  durably in `PaperTradeRecorder`/`paper_trades.jsonl` (`SOURCE_READY`,
  now with a certified/excluded split per R1.3) but needs a governed
  history reader. `SCHEMA_READY != VALUE_AVAILABLE` (§7).
- **Historical paper-trade reader**: no governed projection over
  `paper_trades.jsonl` exists yet; the API must not read it directly (§14).
- **Fill truth**: real-money fills, order-observation truth, ACK-to-filled
  progression, and partial-fill lifecycle are not implemented on current
  main. REM-C R1 (merged, certified on main) addressed domain-safe
  reconciliation, the `PositionManager` API fix, and PAPER-restart
  evidence honesty only — it did not implement or propose the fill engine;
  that is REM-C R2/R3/R4, not started (§9).
- **Real-position reconciliation**: the domain-compatibility gate (PAPER
  vs REAL) needed for safe reconciliation is now merged (REM-C R1,
  `PositionReconciler`), but actual real-money position *content* (from
  verified fills) is still not implemented — that is REM-C R3, not started
  (§7, §9, §20). Real-account **balance** (display-only, via
  `RealAccountsObserver`) remains a separate, already-wired fact — do not
  conflate balance observation with position reconciliation.
- **Independent liveness**: T-1 not started; snapshot age must not be used
  as a substitute, and neither must the system health score (§15). REM-C
  R1 merging does not itself mean T-1 has started — no runtime/VPS
  certification is implied by a merge.
- **`BurninSimulationEngine` / `PaperLedger` activation status**: both
  conservatively classified `DORMANT / ACTIVATION_UNCONFIRMED`; no
  production call site found. Any future claim of activation needs fresh
  evidence, not inference from the presence of the class (§10).
- **Shadow component VPS-runtime proof**: `ShadowTracker`/S3 and
  `ShadowExecutionEngine` both have real bootstrap/call-site evidence
  (`SOURCE_REACHABLE`), but whether they actually execute on the live VPS
  is `RUNTIME_UNKNOWN` — a source-reachable call site is not proof of
  production activity (§10).
- **REM-B/PAPER conflation risk**: REM-B's durable order-intent identity
  and `ACKNOWLEDGED` state apply only to `ExecutionEngine`'s externally
  reachable (live/testnet) submission path. `create_order()`'s PAPER branch
  never calls into this protocol, regardless of whether a `decision_id` is
  supplied. Any future panel or contract must keep PAPER's simulated
  execution state (`MexcSimulator`/`PaperTradeRecorder`) and REM-B's
  external-submission identity/ACK protocol as two separate facts (§8, §9).
- **Deployment evidence rendering**: full schema/typed transport is
  confirmed (`WEB_READY_NOW`), but no current React view renders
  `deployment_evidence` — a UI gap only, not a scientific or transport gap
  (§7, §15).
- **Regret current state vs historical events**: a current-state structure
  (`RegretStateSnapshot`) exists at the domain-composition layer but is not
  wired into the canonical snapshot (`NEEDS_SNAPSHOT_EXPOSURE`); historical
  event-level regret data is separately gated on a governed history reader
  (`NEEDS_HISTORY_READER`). These are two distinct gaps and must not be
  collapsed into one readiness state (§7, §11, §19).
- **Restored-position provenance and certified-performance semantics**:
  since REM-C R1.3, a restored paper position's `personality` always stays
  `"restored"` (evidence completeness is carried separately via
  `restored_evidence_gaps`/`tp_sl_source`'s three tiers), and
  `PaperTradeRecorder.summary()` separates a certified performance subset
  from the raw closed-trade count. Any future panel/history reader must
  preserve these distinctions — never present all restored TP/SL as
  reconstructed defaults, and never count an unknown-outcome or
  fee-evidence-incomplete trade as a certified performance observation
  (§7, §9, §10).

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
