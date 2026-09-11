# ADR-0020 — Deterministic, durable and idempotent order submission (O-02W-PRE-T1-E REM-B)

Status: Accepted (implementation scope, not runtime certification)
Date: 2026-09-11
Supersedes: none. Extends ADR-0019 (pre-network order authorization, REM-A).

## Context

REM-A (ADR-0019) closed the pre-network authorization boundary: no
mutation call may reach the exchange with an invalid, un-authorized, or
balance-unchecked amount. It explicitly left out of scope: deterministic
order identity, durable intent-before-network journaling,
retry/reconciliation semantics, and the unwired `OrderDeduplicator`
time-window mechanism's inherent limits (a 30s window is not a durable,
restart-surviving, deterministic identity — it is a best-effort spam
guard, and remains one; REM-B does not replace it, it adds an orthogonal,
durable layer beneath it).

This mission (REM-B) closes the next causal gap: **one logical order
intention can still produce more than one exchange submission** if a
network call times out, the process restarts mid-flight, or the same
DecisionPacket/close instruction is delivered twice — because nothing
upstream of `create_order()` remembers, durably, "was this exact
intention already attempted?"

## Decision

Introduce `quant_hedge_ai/agents/execution/order_intent_protocol.py`:

1. **Canonical logical intent** (`OrderIntent`) — a versioned, immutable,
   causally-scoped representation (namespace, causal_id, account_scope,
   symbol, side, order_type, amount, price, reduce_only, position_ref).
   No wall-clock time, PID, random UUID, retry count, mutable status, or
   secret ever enters the canonical payload.

2. **Deterministic full digest** — SHA-256 over a fixed-field-order,
   locale-independent canonical JSON serialization. The same logical
   intention always produces the same digest (I1); a genuinely different
   decision (different `causal_id`, symbol, side, amount, price, or
   `reduce_only`) always produces a different one (I2).

3. **Exchange-safe client order ID** — a short, deterministic fragment of
   the full digest, prefixed with a schema version tag
   (`reb1<hex-fragment>`, ≤32 chars by default). The full digest and full
   canonical payload are always persisted locally; the short ID is only a
   transport identifier. A short-ID collision against a *different* full
   digest/payload is detected and fails closed (I7,
   `SubmissionOutcome.IDENTITY_COLLISION`) — never silently treated as the
   same order.

4. **Durable append-only journal** (`OrderIntentJournal`) — one minimal
   new authority, introduced because no existing durable order-cycle
   journal was found in this repository (the closest candidates,
   `src/journal/trade_logger.py` and `OrderDeduplicator`, are in-memory /
   time-window mechanisms, not durable-before-network authorities — see
   inventory below). JSONL, one record per state transition, fsync'd
   before returning. Reconstructing state means replaying the file and
   keeping, per intent digest, the last valid (parseable) record — a
   truncated final line from a crash mid-write is skipped, not fatal.
   Default production path: `databases/order_intent_journal.jsonl`
   (matches this repo's existing `databases/*.json(l)` runtime-state
   convention), overridable via `ORDER_INTENT_JOURNAL_PATH`.

   State vocabulary (closed): `INTENT_RECORDED` → `SUBMISSION_STARTED` →
   {`ACKNOWLEDGED` | `EXPLICITLY_REJECTED` | `RECONCILE_REQUIRED`} →
   (`RECONCILE_REQUIRED` only) {`RECONCILED_FOUND` |
   `RECONCILED_NOT_FOUND_PENDING` | `COLLISION`}. No generic `FAILED`
   state exists — an ambiguous outcome is never conflated with a proven
   failure or a proven success (I10). Invalid transitions raise
   `InvalidTransitionError` rather than being silently written.

   Concurrency: a single `threading.RLock` per journal instance
   serializes readers/writers within one process, plus a per-intent-digest
   lock in the coordinator so unrelated intents never block each other.
   This is **not** a cross-process lock. This repository runs one
   execution process at a time (single VPS `advisor_loop.py` writer per
   the CLAUDE.md stabilization window); running two processes against the
   same journal path concurrently is an explicit single-writer
   requirement, not silently assumed safe — documented here rather than
   pretending a thread lock covers it.

5. **Submission coordinator** (`OrderIntentCoordinator.submit`) —
   enforces: build intent → (caller already ran REM-A authorization) →
   canonicalize → derive identity → acquire per-digest lock → read journal
   → if already recorded, return existing typed state, zero new mutation
   calls (I4/I6) → persist `INTENT_RECORDED` (durable) → persist
   `SUBMISSION_STARTED` (durable, *before* the network call — I3) → call
   the exchange **exactly once** → classify the raw result into
   `ACKNOWLEDGED` / `EXPLICITLY_REJECTED` / `AMBIGUOUS` and persist the
   corresponding terminal or `RECONCILE_REQUIRED` state. A caller-supplied
   `mutate()` callable performs the actual exchange call — this module
   never imports `ccxt` or opens a socket itself.

6. **Reconciliation** (`OrderIntentCoordinator.reconcile`) — read-only
   with respect to order creation. For an intent in `RECONCILE_REQUIRED`
   or `RECONCILED_NOT_FOUND_PENDING`: exactly one match → verify
   compatibility → `RECONCILED_FOUND` (never resubmits); zero matches →
   `RECONCILED_NOT_FOUND_PENDING` (still ambiguous, still never
   resubmits — no time-delay-based "safe to retry" policy is introduced);
   more than one match, or a payload mismatch → fail closed
   (`IDENTITY_COLLISION`); a lookup failure leaves the intent in
   `RECONCILE_REQUIRED`, recording the read failure.

7. **Typed results** (`SubmissionOutcome`) distinguish authorization
   denial, already-recorded, acknowledged, explicitly rejected,
   reconcile-required, reconciled-found, not-found-but-ambiguous,
   identity collision, journal failure, and unsupported adapter
   capability — never a bare `None`/boolean standing in for more than one
   meaning.

8. **Adapter capability declaration** (`AdapterCapabilities`) — an
   adapter that cannot accept a deterministic client order ID fails
   closed (`UNSUPPORTED_ADAPTER_CAPABILITY`) rather than silently
   submitting without one.

## Integration

Both source-reachable mutation families are wired through the
coordinator **as an additive, backward-compatible path gated on an
explicit `decision_id` parameter**:

- `ExecutionEngine.create_order(..., decision_id=None)` →
  `_place_live_order(..., decision_id=None)`
- `ExecutionEngine.create_futures_order(..., decision_id=None)`
- `PositionManager._send_close_order` — always routed through the
  coordinator; the causal id is derived deterministically from
  `pos.order_id` (the same key this module already uses to index open
  positions) composed with the `CloseReason`, falling back to the same
  `symbol_opened_at` composite `PositionManager.add_position` already
  uses as a key when `order_id` is unset. `opened_at` is an immutable
  field set once at position construction — never "current time at
  submission" — so this fallback stays a stable per-position identity.

**Known limitation, stated explicitly (scope control, mission §16):**
`ExecutionEngine.create_order()`/`create_futures_order()` do not yet
have a `decision_id` supplied by their only current caller
(`core/advisor_loop.py`), which this mission does not modify. When
`decision_id` is omitted, these two call sites keep their pre-REM-B
behavior unchanged (direct `_with_retry(create_order, ...)` call) —
this is a deliberate fail-open-to-old-behavior choice, not a silent
gap: REM-B does not claim I4/I8 coverage for a caller that has not yet
been given a causal id to pass. Full closure of this requires plumbing
an existing DecisionPacket/decision id through `advisor_loop.py`, which
is explicitly out of this mission's scope control (§16: "avoid
modifying core/advisor_loop.py unless required to propagate an
existing causal ID... prefer fail-closed over deriving identity from
time" — no upstream causal id currently flows to this call site to
propagate). `PositionManager._send_close_order` has no such gap: its
causal id is derived entirely from state this module already owns.

## Existing-code inventory (mission §4, recorded for audit)

- `quant_hedge_ai/agents/execution/order_deduplicator.py` —
  `OrderDeduplicator`: in-memory, time-window (`< 30s`) duplicate guard.
  Not durable, not restart-surviving, not keyed on a deterministic
  logical identity (keyed on symbol/action/size proximity). Kept
  unchanged and untouched — it remains a complementary, orthogonal
  spam guard, not superseded by REM-B.
- `src/journal/trade_logger.py` — `TradeLogger`: in-memory event log
  (`_open_logs`, `_closed_trades`), no disk persistence, no
  submission-identity concept. Not a durable authority; not reused.
- No `PendingOrderTracker`, `clientOrderId`/`newClientOrderId`
  construction, or order-status state machine existed anywhere in the
  source tree before this mission (grep-verified, mission §4). REM-B
  introduces the first one.
- `order_authorization.py` (REM-A, ADR-0019) remains the sole
  pre-network authorization boundary; this module never re-implements
  or bypasses it (I9) — every `OrderIntentCoordinator.submit()` call
  requires a caller-supplied `authorized: bool` that REM-B treats as
  opaque.

## REM-C exclusions (explicit, not implemented here)

- Partial-fill lifecycle and fill-quantity reconciliation.
- Complete position reconstruction from journal + exchange state after a
  crash window.
- PnL accounting changes.
- Any automatic resubmission policy after `RECONCILED_NOT_FOUND_PENDING`
  (e.g. a time-based "safe to retry" rule) — deliberately not invented
  here; any future such policy requires separate proof and explicit
  operator authorization.
- Full `advisor_loop.py` causal-id plumbing for the spot/futures
  `ExecutionEngine` paths (see Known limitation above).

## Consequences

- Positive: a timeout, connection reset, or process restart between
  `SUBMISSION_STARTED` and a definitive exchange answer can no longer
  silently trigger a second real order for the `PositionManager` close
  path, and for any `ExecutionEngine` caller that supplies a
  `decision_id`.
- Negative / accepted debt: the `ExecutionEngine.create_order()` /
  `create_futures_order()` spot and futures-demo paths, as actually
  invoked by `core/advisor_loop.py` today, do not yet pass a
  `decision_id` and therefore do not yet get I4/I8 coverage — this is
  recorded as REMEDIATION_REQUIRED-relevant residual scope in the
  PRE-T1-E contract, not silently claimed closed.
- The single-writer, single-process durability assumption (§7 above) is
  a documented constraint, not a general multi-process guarantee.

---

## R1 correction round (MASTER review, 2026-09-11)

Eight blockers identified by MASTER review of the R0 round above, corrected
on top of R0's history (starting HEAD `8398c8ec88e445aca87981cc2683282d87a371ee`
— the corrected preflight point, one commit past the R1 mission's originally
cited `cc549a30...`, which was itself a `decision_id`-propagation fix I had
already pushed). No REM-C scope started; contract verdict stays
`REMEDIATION_REQUIRED`.

### Correction A — causal identity becomes mandatory, not optional

`ExecutionEngine.create_order()`/`create_futures_order()` previously fell
back to a legacy direct `self._exchange[.futures].create_order()` call
(no journal, no idempotence) whenever `decision_id` was `None`. Both now
fail closed with a typed `MISSING_CAUSAL_ID`-shaped denial (`mode:
"rejected"`, `denial_reason: "MISSING_CAUSAL_ID"`) — zero exchange
mutation calls, zero journal writes. `PositionManager._send_close_order()`
already derived an unconditional causal id (`pos.order_id` + `CloseReason`,
falling back to the same `symbol_opened_at` composite this module already
uses as its position dict key) — confirmed by inspection, no bypass
existed there, no change needed.

### Correction B — causal-ID (`trace_id`) provenance and stability

Traced completely (source-level, `core/advisor_loop.py`):

- **Created**: `_trace_id = new_trace_id()` (line 1288), exactly once per
  decision cycle — confirmed by AST: exactly one assignment site to
  `_trace_id` in the whole file.
- **`new_trace_id()`** = `str(uuid.uuid4())` (`observability/json_logger.py`)
  — a **random** value, not content-derived from the decision.
- **Exists on DecisionPacket**: `_dp.metadata["trace_id"] = _trace_id`
  (line 1711, mandatory per I-16).
- **Deterministic?** No — the VALUE is random. But it is **stable**: read
  once, never regenerated between decision creation and the
  `create_order()`/`create_futures_order()` call for that one execution
  attempt (confirmed: `r["trace_id"]` always traces back to the single
  `_trace_id` variable, never a fresh `new_trace_id()` call inline — the
  one OTHER `new_trace_id()` call site in the file is for an unrelated
  `_enl_dp` ENL-2 crash-audit record, never reaching execution).
- **Persisted?** Only in-memory (DecisionPacket metadata), not durably
  written to disk before the decision reaches execution.
- **Survives serialization/reconstruction?** **No** — this is the honest,
  named gap. Nothing in `advisor_loop.py` persists a DecisionPacket to
  disk before execution and nothing on process restart re-reads a prior
  in-flight decision to recover its `trace_id`. A crash between decision
  creation and the network mutation call cannot be reconciled by restart
  using `trace_id` alone.
- **Two distinct decisions share it?** No — each cycle generates a fresh
  UUID; Group A/L tests prove distinct causal ids never collapse.

**Conclusion**: neither pure Outcome 1 ("existing identifier proven fully
stable including across reconstruction") nor a full Outcome 2 rewrite. The
existing `trace_id` genuinely satisfies I1/I2/I4/I5 (stable identity for
one execution attempt; no regeneration at the retry/submission boundary,
because there is no retry loop calling `create_order()` twice within a
cycle). It does **not** provide restart-reconstruction of an in-flight
decision (a stronger form of I6) — that requires durably persisting the
*decision itself* before execution, which is a genuinely larger change
(a new pre-execution durable decision log) reserved for REM-C's
crash-window-recovery scope rather than invented here. Documented as
explicit residual scope below, not silently claimed solved.

### Correction C — exhaustive caller inventory

Fresh repository-wide search (`grep -rn` for `create_order`/
`create_futures_order`/`_send_close_order`, excluding tests):

| File | Reachability | Externally capable | Causal id | Protocol | Fail-closed w/o id | Proof |
|---|---|---|---|---|---|---|
| `core/advisor_loop.py` (×2) | source-reachable, real entrypoint | yes | yes (`trace_id`) | yes | n/a (always supplies id) | Group L |
| `quant_hedge_ai/agents/execution/execution_engine.py` (`_mutate_via_coordinator`) | internal, gated | yes | n/a (wrapper) | yes | n/a | Group A/N |
| `quant_hedge_ai/agents/execution/position_manager.py` (`_send_close_order`) | internal, gated | yes | yes (unconditional) | yes | n/a | Group I |
| `quant_hedge_ai/agents/risk/portfolio_brain.py`, `capital_allocation_engine.py` | docstring usage example (`...` ellipsis, not valid call syntax) | no | — | — | — | source inspection |
| `supervision/ops_watchdog.py` | docstring usage example | no | — | — | — | source inspection |
| `quant_hedge_ai/main_v91.py`, `quant_hedge_ai/main_system.py` | **source-reachable, real code**, documented as a *parallel/legacy entrypoint* (`observability/operator/domains/execution_state.py:170` — pre-existing governance debt, explicitly flagged "hors périmètre O-01") | yes, if `_live=True` | **no** | n/a | **yes, automatically** — Correction A's check lives inside `ExecutionEngine.create_order()` itself, so this caller cannot bypass it without being touched | Group N (`test_all_known_production_callers...`) |
| `scripts/smoke_test_ci.py` | CI smoke test only | no | — | — | — | — |

`main_v91.py`/`main_system.py` are deliberately **not modified** — out of
REM-B-R1 scope (not the production entrypoint; a separate, pre-existing
governance question) — but are automatically protected by Correction A's
fail-closed check regardless, since that check lives inside
`ExecutionEngine` itself, not in `advisor_loop.py`.

A mechanical AST test
(`test_execution_engine_create_order_calls_only_inside_coordinator_wrapper`,
`test_position_manager_create_order_calls_only_inside_coordinator_wrapper`)
fails if a NEW direct `X.create_order(...)` call site is added to either
production module outside the coordinator's `mutate()` closure — verified
load-bearing by temporarily reintroducing a fake bypass call and
confirming the test catches it. **Known limitation, disclosed honestly**:
this AST pattern only matches `X.create_order(...)` as a direct call
expression — it does NOT catch the specific pre-Correction-A bypass shape
`self._with_retry(self._exchange.create_order, ...)` (the method
reference passed *by reference* as an argument, not called directly),
which is exactly why a second, string-literal-based test
(`test_no_legacy_bypass_branch_remains_in_execution_engine`) was added
for that specific historical pattern, and why Correction A's own
*behavioral* tests (zero-mutation-calls proofs) — not the static
scanners — remain the actual authoritative proof, per spec §5's own
"do not rely on static tests alone."

### Correction D — inter-process-safe journal ownership

R0's journal used only a `threading.Lock`/`threading.RLock` — explicitly
documented as NOT cross-process-safe, but not actually enforced.
R1 adds `_CrossProcessLock` (`fcntl.flock`, `LOCK_EX`) wrapping the
check-and-register critical section (collision check, existing-state
check, `INTENT_RECORDED` + `SUBMISSION_STARTED` appends) — released
*before* the network mutation call, per spec §6.4, since the durable
`SUBMISSION_STARTED` record is what blocks every competitor from that
point on, not the lock itself.

**Platform**: POSIX-only (`fcntl`), matching this repo's documented
single-Linux-VPS production runtime. On any platform without `fcntl`, or
if `flock()` itself raises, submission fails closed with a typed
`LOCK_UNAVAILABLE` result — zero mutation calls, zero journal writes —
rather than silently degrading to the (cross-process-unsafe)
`threading.Lock`.

**Deliberately coarse-grained**: one lock file per journal (not
per-digest) — simpler to reason about correctly; this repo's actual
production shape is a single-writer VPS with low order volume, so
serializing all concurrent submissions through one journal is an
acceptable cost, not a scalability requirement this mission needs to
solve.

**Real `multiprocessing` tests** (not thread simulation):
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py::TestGroupK_RealCrossProcessSafety`
spawns actual `multiprocessing.Process` workers (separate OS processes,
separate interpreters), synchronized via `multiprocessing.Barrier`, racing
on the same journal file, counting mutation attempts via a process-safe
append-only counter file:

- 2 processes, same intent → exactly 1 mutation attempt (verified).
- 5 processes, same intent → exactly 1 mutation attempt (verified).
- 2 processes, 2 genuinely distinct intents → exactly 2 mutation attempts
  (proves the lock does not over-serialize unrelated intents into one).
- Lock failure (`flock` raises, or `fcntl` unavailable) → zero mutation
  calls, zero journal writes, typed `LOCK_UNAVAILABLE`.

**Fail-before proof for this correction is unusually strong**: run against
the R1 starting HEAD (`8398c8ec`, which had no cross-process lock at all),
the 2-process test did not merely produce "2 mutation attempts" — it threw
a real `InvalidTransitionError` (`INTENT_RECORDED -> ACKNOWLEDGED` attempted
twice for the same digest), a genuine manifestation of the exact race this
correction closes, not a synthetic/contrived failure.

### Correction E — adapter capability contract

R0's single hardcoded `AdapterCapabilities(supports_client_order_id=True,
client_order_id_param="clientOrderId", ...)` applied to **every**
`EXCHANGE_ID` this repo can be configured with — `mexc` (default),
`krakenfutures`, `binanceusdm` — despite this class's own docstring
describing itself as "multi-exchange." This was a genuine defect: CCXT's
raw client-order-id parameter name is not uniform across exchanges (the
Binance-family REST APIs use `newClientOrderId`, not `clientOrderId`); a
wrong parameter is typically silently ignored by the exchange, defeating
REM-B's deterministic-identity guarantee while the call still appears to
succeed.

`ccxt` is not installed in this development sandbox (`pip install ccxt`
failed on an unrelated system `cryptography` package conflict, not a
network issue) — the exact raw parameter names for `krakenfutures`/
`binanceusdm` could **not** be verified against the actual installed
library. Rather than guess and silently trust a plausible-but-unverified
name, `capabilities_for_exchange()` (new, `order_intent_protocol.py`,
shared by both `ExecutionEngine` and `PositionManager` — single source of
truth, I8) now returns:

| `EXCHANGE_ID` | `supports_client_order_id` | `client_order_id_param` | Status |
|---|---|---|---|
| `mexc` (default) | `True` | `"clientOrderId"` | Verified — this repo's default, REM-B's only end-to-end-tested exchange, `clientOrderId` is MEXC's documented spot-API parameter name |
| `krakenfutures` | `False` | `None` | **Unverified** — fails closed |
| `binanceusdm` | `False` | `None` | **Unverified** — fails closed |
| any other value | `False` | `None` | Unverified — fails closed |

An unsupported/unverified adapter denies before any mutation call
(`UNSUPPORTED_ADAPTER_CAPABILITY`, zero mutation calls) — proven both at
the protocol layer (`TestGroupM_AdapterCapabilityMatrix`) and through the
real `ExecutionEngine.create_futures_order()` call path with
`EXCHANGE_ID=krakenfutures`
(`test_execution_engine_uses_shared_capability_table_for_futures`).

**Fail-before proof**: against R1 starting HEAD `8398c8ec`, this exact
test produced a genuine behavioral mismatch — `result["mode"] ==
"futures_demo"` where `"futures_failed"` was required — proving the old
code genuinely allowed an unverified-adapter order through to a (mocked)
real mutation call.

Verifying the exact `krakenfutures`/`binanceusdm` parameter names against
a real `ccxt` install, and populating `supports_open_order_search`/
`supports_closed_order_search`/reconciliation-method wiring for `mexc`, is
left as an explicit, named follow-up (not fabricated here).

### Correction F — strengthened fail-before proof

R0's fail-before claim ("the whole test file fails to even *import*") was
correctly identified as weak. R1's new tests were run via `git worktree
add` against the exact R1 starting HEAD (`8398c8ec88e445aca87981cc2683282d87a371ee`)
with the CORRECTED test file copied in (production code unchanged):

- `test_two_processes_same_intent_at_most_one_mutation` — genuine runtime
  exception (`InvalidTransitionError`), not an import error.
- `test_execution_engine_uses_shared_capability_table_for_futures` — genuine
  value mismatch (`futures_demo` vs required `futures_failed`), not an
  import error.
- Several Group K/M tests DID fail via `AttributeError`/`ImportError` for
  genuinely-missing new symbols (`fcntl` attribute presence,
  `capabilities_for_exchange` not yet existing) — disclosed honestly as
  weaker (but still per-test runtime, not whole-file-collection) evidence,
  consistent with those specific corrections adding wholly new
  capabilities rather than fixing a pre-existing wrong behavior.
- Group N's AST bypass-detector tests passed unchanged on the old HEAD —
  disclosed honestly as NOT fail-before evidence for Correction C (their
  value is forward-looking regression protection, verified load-bearing
  separately by reintroducing a synthetic bypass on the current branch).

### Correction G — `tests/conftest.py` resolution

Root-caused: `tests/conftest.py`'s `ORDER_INTENT_JOURNAL_PATH` redirect
only applies to test files collected under `tests/` — `execution_engine.py`'s
module-level `_DEFAULT_ORDER_INTENT_JOURNAL_PATH` constant (frozen at
import time, DS-001/ADR-0008) therefore fell through to the REAL
production default (`databases/order_intent_journal.jsonl`) for every test
file OUTSIDE `tests/` (e.g.
`quant_hedge_ai/agents/execution/test_execution_engine_futures.py`) —
confirmed to have actually polluted that file with 54+ real JSONL records
during this session's own development. Root `conftest.py` already has an
established DS-001 pattern for exactly this class of problem
(`OBS_LOG_ROOT`, `BLACK_BOX_PATH`, `REJECTION_STORE_DIR`, etc. — env vars
set at MODULE level, before pytest collection, because the values freeze
at import). `ORDER_INTENT_JOURNAL_PATH` was added to that existing block
and the narrower `tests/conftest.py` deleted. No autouse fixture was
added (it is a plain `os.environ.setdefault(...)` call, identical in kind
to the ten other lines already in that block); it does not touch
`sys.path`, module caches, clocks, or any singleton beyond the one env
var. Verified via every full-suite run performed in this session since
the fix (repeatedly, including representative unrelated suites —
`supervision/tests/test_e04_killswitch.py`,
`tests/visualization/test_regret_api.py`): identical pre-existing failure
signatures before and after, and zero `databases/order_intent_journal.jsonl`
pollution in every run since.

## R1 files changed

- `quant_hedge_ai/agents/execution/order_intent_protocol.py` — `LockUnavailableError`,
  `_CrossProcessLock`, `OrderIntentJournal.cross_process_lock()`,
  `capabilities_for_exchange()`, `_ADAPTER_CAPABILITIES_BY_EXCHANGE`,
  new `SubmissionOutcome` members (`MISSING_CAUSAL_ID`,
  `INTENT_ALREADY_RECORDED`, `SUBMISSION_ALREADY_STARTED`,
  `RECONCILIATION_CONFLICT`, `LOCK_UNAVAILABLE`), `AdapterCapabilities`
  extended with `max_client_order_id_len`/`client_order_id_charset`/
  `supports_open_order_search`/`supports_closed_order_search`.
- `quant_hedge_ai/agents/execution/execution_engine.py` — Correction A
  (fail-closed on missing `decision_id`, both spot and futures paths),
  Correction E wiring (`capabilities_for_exchange(exch_id)` instead of a
  hardcoded constant), SEC-01 neutrality fix (gate-blocked response gains
  the same `order_intent_outcome`/`client_order_id` null keys the
  REM-B-rejected response has), exception classifier keyword fix
  (`"no permission"`/`"permission denied"` now `EXPLICITLY_REJECTED`).
- `quant_hedge_ai/agents/execution/position_manager.py` — Correction E
  wiring, same classifier keyword fix.
- `conftest.py` (root) — Correction G.
- `tests/conftest.py` — deleted (Correction G).
- `tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` — Groups K
  (real multiprocess), L (causal-id provenance), M (adapter capability
  matrix), N (caller inventory + bypass detection).
- `tests/test_pre_t1_e_rem_a_order_authorization.py`,
  `tests/test_pre_t1_e_order_cycle_safety.py`,
  `quant_hedge_ai/agents/execution/test_execution_engine.py`,
  `quant_hedge_ai/agents/execution/test_execution_engine_futures.py` —
  ~25 call sites updated to supply `decision_id`; several assertions that
  encoded now-fixed defects (H3 clientOrderId absence, H5 blind retry,
  SEC-01 key-set neutrality) rewritten to assert corrected behavior,
  historical docstrings preserved.

## Updated REM-C exclusions (still explicit, still not implemented)

Unchanged from R0, PLUS the new named gap from Correction B: durable
persistence of the DecisionPacket/intent itself BEFORE execution (needed
for true restart-reconstruction of an in-flight decision) is REM-C scope,
not invented here.

## R1 Consequences

- Positive: missing-identity external mutation is now impossible (fails
  closed, not merely undocumented); cross-process journal races are now
  actually prevented (not merely disclaimed); unverified exchange
  adapters cannot silently defeat identity/idempotence; a mechanical
  regression test exists for new direct bypass call sites.
- Negative / accepted debt: `trace_id`-based identity does not survive a
  process crash between decision creation and network mutation (no
  restart-reconstruction) — reserved for REM-C. `krakenfutures`/
  `binanceusdm` adapter capabilities remain unverified and therefore
  blocked from external submission until an operator confirms against
  the real `ccxt` package.
