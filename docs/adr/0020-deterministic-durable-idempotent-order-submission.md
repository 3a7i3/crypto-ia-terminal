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

---

## R1.1 correction round (MASTER review, 2026-09-11)

Three remaining blockers from R1, starting HEAD `cf9a9e74d8d699e6ca315af274da6d7bbef275d9`.

### Blocker A — durable upstream decision identity

**Investigation** (full trace, `core/advisor_loop.py`): `_trace_id = new_trace_id()`
(a random UUID) is created exactly once per decision cycle, stored on
`DecisionPacket.metadata["trace_id"]`, never regenerated before reaching
execution — R1's Correction B had already established all of this. The
one gap R1 named but did not close: `_trace_id` was never durably
persisted BEFORE execution, only held in process memory.

**Fix**: new module `quant_hedge_ai/agents/execution/decision_identity.py`
— a minimal, narrowly-scoped append-only `DecisionIdentityJournal`
(fsync-before-return, same durability contract as `OrderIntentJournal`:
truncated final record tolerated, earlier valid records survive). This is
the explicit fallback spec §4 describes ("if no canonical decision
persistence exists, implement the minimum append-only decision-identity
persistence necessary for REM-B") — confirmed no canonical decision
persistence exists in this repository before execution (the various
observability/audit logs record decisions only after an attempt, or
asynchronously).

`core/advisor_loop.py`'s `analyze_symbol()` now calls
`default_decision_identity_journal().persist(_trace_id, ...)`
IMMEDIATELY after `_trace_id` is created — before any authorization or
execution logic runs (source-proven: the `persist()` call site is within
2000 characters of the `_trace_id` assignment, before
`set_trace_id(_trace_id)`'s only downstream use).

`ExecutionEngine._decision_id_is_durably_persisted()` gates BOTH mutation
paths (spot and futures): a `decision_id` that is merely non-empty is no
longer sufficient — it must be found in the durable decision-identity
journal. Missing OR unpersisted fails closed with a typed denial
(`MISSING_CAUSAL_ID` / `UNPERSISTED_CAUSAL_ID`), zero mutation calls.

**Causal ordering proven** (not merely asserted): `DECISION_ID_CREATED ->
DECISION_PERSISTED -> REM_A_AUTHORIZATION -> ORDER_INTENT_RECORDED ->
SUBMISSION_STARTED -> EXCHANGE_MUTATION`. A restart-simulation test
(`test_restart_cannot_convert_one_decision_into_a_second_order_identity`)
persists a decision id, submits successfully, reconstructs a BRAND NEW
`ExecutionEngine` instance (simulating a process restart), and resubmits
the SAME decision_id — the reconstructed coordinator recognizes the
already-ACKNOWLEDGED intent and performs zero further mutation calls.

**Legacy/missing identity**: any caller (including
`quant_hedge_ai/main_v91.py`/`main_system.py`, R1's named unmodified
parallel entrypoint) that supplies a `decision_id` never durably
persisted fails closed — the SAME code path as a genuinely missing one,
per spec §3 invariant 5 ("Missing persisted ID → typed fail-closed
denial and zero mutation calls").

**`PositionManager` scope note**: `PositionManager._send_close_order`'s
causal id (`pos.order_id` + `CloseReason`, falling back to a
`symbol_opened_at` composite) is derived from already-durable position
state (a previously-acknowledged exchange order id, or an immutable
position-creation timestamp) tracked by `PositionManager` itself — not
requiring a SEPARATE persistence step, since the position object it's
derived from is already the durable record. Left unchanged.

**Fail-before proof** (behavioral, against `cf9a9e74`, NOT an import
error): a standalone script constructing the OLD `ExecutionEngine` and
calling `create_order(..., decision_id="never-persisted-anywhere")` (a
bare string, never recorded anywhere) reached a REAL mutation call —
`mode: "live"`, `mock_exchange.create_order.called: True`. On the
corrected branch, the identical call returns `mode: "rejected"`,
`denial_reason: "UNPERSISTED_CAUSAL_ID"`, zero mutation calls.

**Correction to a prior claim**: while investigating whether any existing
persistence/reconciliation infrastructure could be reused for this
blocker, `system/pending_order_tracker.py::PendingOrderTracker` was found
to actually EXIST as a class (contradicting R0's ADR claim that "no
`PendingOrderTracker` class/module exists anywhere") — but confirmed via
`grep -rn "PendingOrderTracker("` to never be instantiated anywhere in
production code, and keyed by exchange-assigned `order_id` (not
`clientOrderId`) with in-memory-only state, so it could not have served
either this blocker's decision-identity requirement or Blocker B's
reconciliation-certification requirement. B9's original resolution (REM-B
built its own journal) stands; only the precise phrasing of "does not
exist" is corrected to "exists but is never wired into any production
code path."

### Blocker B — real adapter reconciliation capability

**Finding**: R1 authorized MEXC's external submission on the strength of
a documented, plausible `clientOrderId` parameter name alone — but
`OrderIntentCoordinator.reconcile()` accepted an arbitrary caller-supplied
`lookup` callable with no certification that any REAL adapter implements
matching semantics. A test fake accepting `"clientOrderId"` is not proof
an adapter supports reconciliation.

**Capability matrix** (repository-wide search:
`grep -rln "fetch_order\|fetch_open_orders\|fetch_closed_orders"`):

| Exchange | Configured | Submission param | Reconciliation evidence | Verdict |
|---|---|---|---|---|
| `mexc` | Yes (default) | `clientOrderId` (documented, general knowledge — NOT verified against a pinned `ccxt` install; `ccxt` uninstallable in this sandbox) | No in-repo pinned implementation of order lookup-by-clientOrderId found. `market_data/connectors/mexc.py`/`infra/mexc_reader.py` only fetch order BOOKS. `PendingOrderTracker` exists but is unwired and keyed by exchange `order_id`, not `clientOrderId`. | `SUBMIT_ONLY_RECONCILIATION_UNVERIFIED` |
| `krakenfutures` | Yes | Unverified | Unverified | `UNSUPPORTED` |
| `binanceusdm` | Yes | Unverified | Unverified | `UNSUPPORTED` |
| any other | N/A | — | — | `UNSUPPORTED` |

**MEXC verdict, precisely**: per spec §5's explicit rule — "Only
`SUBMIT_AND_RECONCILE_VERIFIED` may authorize an externally capable
submission during PRE-T1" — `SUBMIT_ONLY_RECONCILIATION_UNVERIFIED`, despite
its name, does NOT authorize external submission either. MEXC is
downgraded from R1's submission-authorized status.
`AdapterCapabilities.supports_client_order_id` is now a DERIVED property
(`verdict == SUBMIT_AND_RECONCILE_VERIFIED`), not an independently settable
field — eliminating the possibility of a future capability entry
accidentally authorizing submission without the matching verdict.

**Reconciliation ownership**: `OrderIntentCoordinator.reconcile()` now
checks `self._capabilities.verdict == SUBMIT_AND_RECONCILE_VERIFIED`
BEFORE invoking the caller-supplied `lookup` — a production caller cannot
inject a permissive `lookup` to bypass this; `reconcile()` is gated on the
SAME capability object the coordinator was constructed with, never one
the caller substitutes at call time. Tests inject a fake
`SUBMIT_AND_RECONCILE_VERIFIED` capability (documented as
"test fixture — certified for hermetic testing only" in its `evidence`
field) to exercise the authorized path without promoting the real,
unverified MEXC entry.

**Runtime impact**: zero. `reconcile()` was never called from any
production path (`grep -rn "\.reconcile("` finds only
`core/advisor_loop.py`'s UNRELATED `_position_reconciler.reconcile()`,
a different, pre-existing reconciler). This downgrade affects only a
hypothetical future live-submission path, already blocked by
`PAPER_TRADING_ENABLED=true` (CLAUDE.md stabilization window).

**Fail-before proof** (behavioral): against `cf9a9e74`,
`capabilities_for_exchange("mexc").supports_client_order_id` was `True`
with `supports_lookup_by_client_order_id: True` — the exact
over-authorization this blocker corrects.

### Blocker C — complete mutation-bypass detection

**Finding**: R1's detector matched `X.create_order(...)` only when the
attribute access was the direct `.func` of a `Call` node — missing the
exact historical bypass shape `_with_retry(exchange.create_order, ...)`
(the method reference passed BY REFERENCE as a bare argument).

**Fix**: `_mutation_references()` (replacing the R1 scanner) records ANY
syntactic `ast.Attribute` access named after a mutation method — Layers
1-3 (direct call, reference-passed-to-wrapper, assigned-to-alias) collapse
into one AST node shape and are caught uniformly; Layer 4 (`getattr(X,
"create_order")` with a literal string) is matched separately; Layer 5
(wrapper delegation) falls out naturally from per-function attribution;
Layer 6 is the allowlist comparison in each test.

**Bounded detection model, stated explicitly** (spec §7's own
requirement — "do not claim perfect static detection"): does NOT catch
attribute names built from string concatenation/formatting at runtime,
`importlib`-based dynamic imports, `setattr`-based monkeypatching, or any
reflection beyond a literal `getattr(X, "name")` call. Combined with an
independent repository-wide `grep` (a completely different, non-AST
detection method) corroborating the same call sites.

**Fail-before proof** (behavioral): the OLD scanner's exact logic, run
against a synthetic fixture reproducing `_with_retry(exchange.
create_order, ...)`, returns an EMPTY set (misses it entirely). The NEW
scanner, run against the identical fixture, correctly attributes the
reference to its enclosing function. Verified additionally (this branch)
by reintroducing a synthetic bypass into a copy of the real
`execution_engine.py` and confirming the new scanner catches it.

## R1.1 files changed

- `quant_hedge_ai/agents/execution/decision_identity.py` (new) —
  `DecisionIdentityJournal`, `DecisionIdentityError`,
  `default_decision_identity_journal()`.
- `quant_hedge_ai/agents/execution/order_intent_protocol.py` —
  `AdapterCapabilityVerdict` enum; `AdapterCapabilities.verdict`
  (replacing independent `supports_client_order_id`/
  `supports_lookup_by_client_order_id` fields with derived properties);
  MEXC downgraded to `SUBMIT_ONLY_RECONCILIATION_UNVERIFIED`;
  `reconcile()` capability-gated before invoking `lookup`.
- `quant_hedge_ai/agents/execution/execution_engine.py` —
  `_get_decision_identity_journal()`, `_decision_id_is_durably_persisted()`;
  both mutation paths gated on it; `MISSING_CAUSAL_ID`/
  `UNPERSISTED_CAUSAL_ID` distinguished.
- `core/advisor_loop.py` — durably persists `_trace_id` immediately at
  creation, before any downstream logic.
- `conftest.py` (root) — `DECISION_IDENTITY_JOURNAL_PATH` DS-001 entry.
- `tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` — Groups O
  (durable decision identity), rewritten Group N (layered bypass
  detector), updated Group M (MEXC downgrade).
- `tests/test_pre_t1_e_order_cycle_safety.py`,
  `tests/test_pre_t1_e_rem_a_order_authorization.py`,
  `quant_hedge_ai/agents/execution/test_execution_engine.py`,
  `quant_hedge_ai/agents/execution/test_execution_engine_futures.py` —
  test-only capability/decision-identity fixture injection (mirroring the
  existing fake-exchange pattern) so tests targeting OTHER behavior are
  not broken by the stricter real gates; `.ci/ruff_baseline.json`
  regenerated (958, 2 genuine fixes + 1 pre-existing line-shift).

## Updated REM-C exclusions (still explicit, still not implemented)

Unchanged from R1, PLUS: verification of `krakenfutures`/`binanceusdm`
exact CCXT parameter names and reconciliation methods against a real
`ccxt` install remains an explicit, named follow-up (not REM-C, but not
done here either — deliberately fails closed instead of guessed).

## R1.1 Consequences

- Positive: a decision's causal identity is now durably established
  BEFORE it can authorize a real mutation, closing the restart-
  reconstruction gap R1 named but left open; no adapter can be granted
  external-submission authority without a certified reconciliation
  contract; the mutation-bypass detector catches the exact historical
  bypass shape it previously missed.
- Negative / accepted debt: MEXC's real-world submission capability is
  now fully deny-closed pending an operator verifying `krakenfutures`/
  `binanceusdm`/`mexc` reconciliation against the real `ccxt` package —
  zero live impact today (paper-only stabilization window), but a
  necessary follow-up before ANY future live-trading authorization.

## R1.2 final safety correction round (2026-09-11)

Starting HEAD: `e5d81deb8439f553c23c09b9f1653505d94de5b3` (verified:
local/remote/GitHub PR metadata all matched; base `092bb88f...` unchanged;
working tree clean). MASTER's R1.2 review named exactly two remaining
blockers.

### Blocker A — every non-fully-verified adapter must fail closed

**Classification (R1.3 correction, MASTER review): `ALREADY_SATISFIED_AT_R1_1 — REVALIDATED_IN_R1_2`.**
R1.2 did NOT implement this production boundary — it was already fully
implemented and in force as of R1.1's Blocker B fix. R1.2's contribution
was exclusively the 16-test proof below, run against the R1.1 head with
zero production-code change. The implementation round is **R1.1**; the
revalidation round is **R1.2**. (R1.3, this section's own round, corrects
an earlier draft of this document that could be read as implying R1.2
itself closed the boundary — it did not; R1.2 only proved it was already
closed.)

**Investigation finding, not a code defect**: re-reading
`OrderIntentCoordinator.submit()` (the actual production submission path)
showed this invariant was **already fully enforced by R1.1**. `submit()`'s
very first gate after the authorization check is
`if not self._capabilities.supports_client_order_id: return
UNSUPPORTED_ADAPTER_CAPABILITY` — and `supports_client_order_id` is a
DERIVED property, `True` only when `verdict ==
SUBMIT_AND_RECONCILE_VERIFIED`. Since R1.1's Blocker B downgraded MEXC to
`SUBMIT_ONLY_RECONCILIATION_UNVERIFIED` (a verdict this property
explicitly treats as `False` despite its name), and no other exchange
holds any capability-table entry, EVERY exchange this repository can be
configured with (`mexc`, `krakenfutures`, `binanceusdm`, any unknown
`EXCHANGE_ID` value, any alias/typo) already reaches this gate and is
denied before any mutation call, with zero `SUBMISSION_STARTED` journal
writes. `reconcile()`'s own capability gate (R1.1) already prevents a
caller-supplied `lookup` from being invoked for an uncertified adapter,
and `capabilities_for_exchange()` (the SOLE production authority, read
fresh on every call from the shared table) has no parameter allowing a
caller to override it.

**Proof, not a fix**: 16 new tests
(`TestGroupP_R12_AdapterFailClosed` in
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py`) exercise this
invariant end-to-end — MEXC spot (`ExecutionEngine.create_order`), MEXC
futures (`create_futures_order`), MEXC position close
(`PositionManager._send_close_order`), Kraken Futures, Binance USD-M,
an unregistered exchange id, four plausible MEXC aliases
(`mexc-spot`/`mexc_v2`/`MEXC2`/`mexcfutures`), a directly-constructed
`SUBMIT_ONLY_RECONCILIATION_UNVERIFIED` capability (proving the RULE, not
just today's MEXC data), a caller-supplied permissive `lookup` (proven
never invoked), source-level proof that no production call site accepts a
caller-supplied capability override, a `SUBMIT_AND_RECONCILE_VERIFIED`
fake submitting exactly once (never twice on a duplicate call), an
ambiguous result on a verified fake entering reconciliation without
resubmission, zero journal transitions for a denied adapter, and a naive
3-attempt retry wrapper denied on every attempt. **All 16 pass unmodified
against the R1.1 head** (`e5d81deb`) — the fail-before proof for this
blocker is therefore a NEGATIVE result: no behavioral gap existed. No
production code was changed for Blocker A in this round.

### Blocker B — genuine causal reconstruction after process restart

R1.1's `DecisionIdentityJournal` proved a `decision_id`, once durably
written, is still found by `is_persisted()` after a fresh journal
instance is constructed — but MASTER's review correctly identified this
as insufficient: it proves only "a decision with this id once existed",
not that its canonical payload is reconstructible, nor that it stays
bound to exactly one authorized order intent, using a stable recovery
selector rather than a retained in-memory `decision_id` variable.

**Fail-before proof (behavioral, not import/collection failure)**: of 30
new tests in `TestGroupQ_R12_CausalReconstruction`, 14 fail against the
R1.1 head (`e5d81deb`) with `AttributeError` — `bind_intent`,
`recover_pending_decisions`, `find_by_cycle_key`, `verify_digest`, `get`
did not exist on `DecisionIdentityJournal`; the remaining 16 (duplicate-
delivery idempotence, basic persistence) already passed, being genuinely
unaffected by this blocker.

**Fix**: `decision_identity.py` rewritten, `SCHEMA_VERSION` bumped to 2:

- `persist()` now computes and durably stores a canonical `payload` (the
  fields the caller has available — namespace/cycle/symbol/action by
  default, or a caller-supplied richer payload) plus its SHA-256
  `payload_digest` — the reconstructible evidence R1.2 requires, not
  merely an opaque id. A `persist()` call for a `decision_id` already
  recorded with a DIFFERENT payload digest now raises
  `DecisionIdentityError` (conflicting duplicate, fails closed); the SAME
  payload digest (genuine duplicate delivery) remains idempotent, as R1.1
  already required.
- New `bind_intent(decision_id, intent_digest)`: atomically binds a
  persisted decision to the exact `OrderIntent.full_digest()` it
  authorizes. Fails closed (`DecisionIdentityError`, zero journal writes)
  for an unpersisted `decision_id`; replaying the identical
  `(decision_id, intent_digest)` pair is idempotent (a retried submission
  attempt is not an error); binding the same `decision_id` to a
  DIFFERENT `intent_digest` raises — one persisted decision authorizes
  exactly one order intent under this module's model (REM-C may define an
  explicit versioned child-intent index if multi-intent decisions are
  ever needed; this module does not silently allow it).
- New `get(decision_id)`, `recover_pending_decisions(namespace=...)`,
  `find_by_cycle_key(namespace=, cycle=, symbol=)`, `verify_digest(...)`:
  the R1.2 §4.4 restart-reconstruction surface. A caller holding ONLY the
  journal's durable path (no retained `decision_id` variable, coordinator,
  or engine object) can construct a brand-new `DecisionIdentityJournal`
  and recover every recoverable decision, verify its payload's integrity,
  and locate one by a stable (namespace, cycle, symbol) selector instead
  of an already-known id. A record missing `payload`/`payload_digest` (a
  genuinely legacy, pre-R1.2 record) is excluded from
  `recover_pending_decisions()` — fails closed for reconstruction — while
  `is_persisted()` still honors it, preserving R1.1 backward
  compatibility for data written before this schema version.
- `ExecutionEngine._bind_decision_to_intent()` (new): called from both
  `_place_live_order()` and `create_futures_order()` immediately after
  `build_order_intent(...)`, before the mutation call. A binding failure
  (conflicting rebind, or a decision that somehow became unpersisted
  between the earlier `_decision_id_is_durably_persisted` check and this
  point) returns a typed `DECISION_INTENT_BINDING_FAILED` denial with
  zero mutation calls, exactly like `MISSING_CAUSAL_ID`/
  `UNPERSISTED_CAUSAL_ID`. Tightens the causal ordering to:
  `DECISION_ID_CREATED -> DECISION_RECORD_DURABLY_PERSISTED ->
  REM_A_ORDER_AUTHORIZATION -> ORDER_INTENT_BOUND_TO_DECISION ->
  ORDER_INTENT_DURABLY_PERSISTED -> SUBMISSION_STARTED ->
  EXCHANGE_MUTATION_ATTEMPT`.

All 30 Group Q tests pass on R1.2's head, including a full end-to-end
restart-reconstruction proof (`test_restart_reconstructs_pending_decision_using_only_durable_state`
— a decision is persisted inside a nested scope whose locals, including
the `decision_id` variable and the `DecisionIdentityJournal` instance
itself, are explicitly discarded; recovery afterward uses only the
durable path plus a `(namespace, cycle, symbol)` selector) and a combined
Blocker-A/B restart proof
(`test_restart_with_binding_preserves_binding_and_causes_no_resubmission`)
showing a brand-new `ExecutionEngine`, given the same `decision_id`,
recovers the same binding and causes zero further exchange mutation
calls.

### R1.2 test-fixture updates

The 4 existing `_certify_mexc_for_test` helpers (in
`tests/test_pre_t1_e_order_cycle_safety.py`,
`tests/test_pre_t1_e_rem_a_order_authorization.py`,
`quant_hedge_ai/agents/execution/test_execution_engine.py`,
`quant_hedge_ai/agents/execution/test_execution_engine_futures.py`) each
gained one additional `monkeypatch.setattr(_EE,
"_bind_decision_to_intent", lambda self, decision_id, intent: None)` line
— mirroring the existing `_decision_id_is_durably_persisted` bypass — so
tests targeting OTHER behavior (sizing, symbol conversion, SEC-01 gate,
etc.) are not broken by the new binding gate. Dedicated Group Q tests
exercise the real, un-bypassed binding gate directly.

### R1.2 verification

Targeted suite (REM-A/REM-B/order-cycle-safety/PRE-T1-D/PRE-T1-C/
execution-engine/position-manager/advisor-loop-smoke): 528 tests, 527
pass, 1 pre-existing unrelated `ccxt`-not-installed environment failure
(reproduces identically on `origin/main`, confirmed via a disposable
worktree — see the R1.1 CI-triage precedent in PR #138's history for the
same class of failure). Ruff baseline gate: 958/958, 0 new (1 genuine
unused-import fix in `decision_identity.py` itself). `git diff --check`:
clean. No `databases/order_intent_journal.jsonl` or
`databases/decision_identity_journal.jsonl` pollution.

### R1.2 safety confirmations

No real/testnet exchange call, no live trading, no deployment, no VPS
access, no secrets touched, no REM-C scope started. PR remains **draft**,
**unmerged**, no force-push, no rebase, no squash, no amend of previously
reviewed commits.

## R1.3 legacy execution ineligibility correction (2026-09-11)

Starting HEAD: `5bfe1a89ecdc4414dd7452386681a75615b20d74` (verified:
local/remote/GitHub PR metadata all matched; base `092bb88f...` unchanged;
working tree clean). MASTER's R1.3 review identified that R1.2's
decision-identity gate, while genuinely closing the restart-reconstruction
gap, conflated two DIFFERENT questions: "does a record exist for this
`decision_id`?" (historical/existence) and "is this record valid enough to
authorize a real mutation?" (execution authority). `ExecutionEngine`'s
mutation gate used `DecisionIdentityJournal.is_persisted()` — the former —
to answer the latter.

### `is_persisted(` call-site inventory (complete repository grep)

| File:Line | Classification |
|---|---|
| `decision_identity.py:266` (now shifted) — the `def is_persisted(...)` definition | Historical/existence query (by design) |
| `execution_engine.py` — inside `_decision_id_is_durably_persisted()`, called from both mutation gates (`_place_live_order`, `create_futures_order`) | **EXECUTION-AUTHORITY DECISION** — the exact defect. Confirmed behaviorally (see fail-before proof below), not merely by code reading. |
| `tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` — 12 call sites (Groups O/Q) | Test assertions verifying `is_persisted()`'s own existence-membership semantics, including an explicit R1.1-backward-compatibility test for legacy records |

### Fail-before proof (behavioral, exact starting HEAD `5bfe1a89`, real mutation counters)

**Scenario A — legacy authority.** A hand-crafted schema-v1 record
(`{"schema_version": 1, "decision_id": "legacy-dec-A1", "namespace": ..., "cycle": 1, "symbol": "BTC/USDT", "ts": 0.0}`
— no `payload`, no `payload_digest`, no `lifecycle_state`, no
`bound_intent_digest`) was written directly to a temp journal file.
```
STEP 2 — is_persisted('legacy-dec-A1'): True
STEP 3 — create_order() result mode: live
STEP 3 — mock_exchange.create_order.call_count: 1
STEP 4 — final record after execution: {"bound_intent_digest": "5ef7c05e...", "lifecycle_state": "BOUND", "schema_version": 1, ...}
```
Confirmed: `is_persisted()` returned `True`; `ExecutionEngine.create_order()`
accepted the id and reached the certified fake exchange's `create_order()`
exactly once; `bind_intent()` extended the record to `BOUND` while it was
STILL `schema_version: 1` — never upgraded to schema-v2-valid.

**Scenario B — corrupted v2 authority.** A genuine schema-v2 record was
persisted, then a second line was appended reusing the same `decision_id`
with its `payload.symbol` mutated WITHOUT recomputing `payload_digest`.
```
STEP 1 — verify_digest('corrupt-dec-B1'): False
STEP 2 — create_order() result mode: live
STEP 3 — mock_exchange.create_order.call_count: 1
```
Confirmed: `verify_digest()` correctly detected the corruption, but the
R1.2 execution gate accepted the record anyway and reached the fake
exchange's `create_order()` exactly once.

Neither proof used an absent symbol, `AttributeError`, an import/
collection failure, or source inspection alone — both are genuine
behavioral acceptances with a real (fake-exchange) mutation counter
reaching `1`.

### Architectural correction

`decision_identity.py` gained:

- `_is_sha256_hex(value)` — structural-only check (64 lowercase hex
  characters) for `payload_digest`/`bound_intent_digest`, used before any
  digest recomputation is attempted;
- `_validate_record_for_execution(record)` (static, pure, no I/O) — the
  SOLE strict-validity function, checking in order: `schema_version == 2`;
  exact non-empty `decision_id`; well-typed non-empty `payload`; a
  structurally valid stored `payload_digest`; the recomputed digest
  matches; duplicated provenance fields (`namespace`/`cycle`/`symbol`/
  `action`) agree between the record's top level and `payload`; a
  recognized lifecycle state (`CREATED`/`BOUND`); `CREATED` implies
  unbound; `BOUND` implies a structurally valid `bound_intent_digest`.
  Returns `None` (eligible) or a stable machine-readable reason string;
- `execution_ineligibility_reason(decision_id)` — the read-only
  EXECUTION-AUTHORITY query (`None`, `"NOT_PERSISTED"`, or one of
  `_validate_record_for_execution`'s reasons);
- `is_execution_eligible(decision_id)` — boolean convenience wrapper;
- `is_persisted()` is now explicitly documented as historical/existence-
  only and is no longer read by any execution gate;
- `bind_intent()` now calls `_validate_record_for_execution()` BEFORE its
  existing bind logic — a legacy or corrupted record raises
  `DecisionIdentityError` with ZERO journal writes, closing exactly the
  "silent upgrade to BOUND" gap Scenario A demonstrated. `intent_digest`
  itself is now also validated for SHA-256 hex shape;
- `recover_pending_decisions()` tightened to exclude every
  execution-ineligible record (via the same strict function), not merely
  ones missing `payload`/`payload_digest` outright.

`execution_engine.py` gained `_decision_execution_denial_reason(decision_id)`
— the ACTUAL execution gate for both `_place_live_order()` (spot/live
`create_order()`) and `create_futures_order()`, replacing the
`is_persisted()`-backed `_decision_id_is_durably_persisted()` check at
both call sites. Returns `None` (proceed), `MISSING_CAUSAL_ID` (falsy
id), `UNPERSISTED_CAUSAL_ID` (no record at all), or `INELIGIBLE_CAUSAL_ID`
(a record exists but fails strict validation — the precise reason is
logged via `_log.warning`, never silently discarded, satisfying spec §4's
"do not silently map corrupted evidence to ordinary absence").
`_decision_id_is_durably_persisted()` itself is RETAINED (its existence-
only semantics are still occasionally useful for audit/observability
tooling) but its docstring now explicitly forbids using it to gate a
mutation, and neither mutation path reads it anymore.

### Pass-after (permanent regression tests)

14 new tests, `TestGroupR_R13_LegacyExecutionIneligibility` in
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py`: legacy v1
rejected before spot/futures mutation (2); corrupted v2 rejected before
spot/futures mutation (2); direct `bind_intent()` refusal with zero
append for legacy/corrupted records (2); valid v2 `CREATED` binds exactly
once, replay is idempotent, rebind-to-different-intent is rejected (3);
valid v2 record still reaches a certified fake adapter exactly once (1);
historical existence lookup finds legacy evidence without granting
execution authority (1); restart reconstruction excludes every
ineligible record (1); no default journal pollution (1); no network/
exchange calls from the new gate/helpers (1). Two test-only helper
builders (`_build_spot_engine`/`_build_futures_engine`) inject FRESH,
temp-path-scoped `DecisionIdentityJournal`/`OrderIntentJournal`/
`OrderIntentCoordinator` instances directly into the engine's private
cache attributes, rather than relying on `monkeypatch.setenv()` for the
journal-path env vars — those module constants freeze at import time
(documented DS-001 pattern, root `conftest.py`), so a per-test env
monkeypatch cannot actually redirect them; direct instance injection is
the correct, genuinely isolated approach and was verified necessary by
the initial 4 test failures this exact mistake produced during
development (fixed before this round's final commit).

For every invalid-record test: result is `"rejected"`; `denial_reason` is
`"INELIGIBLE_CAUSAL_ID"`; the fake exchange's `create_order` call count is
`0`; the order-intent journal's line count is unchanged (`0`); the
decision journal's line count is unchanged (no spurious append); no
`SUBMISSION_STARTED` state exists anywhere in the order-intent journal.
None of the 4 existing `_certify_mexc_for_test` monkeypatch helpers
(across `test_execution_engine.py`, `test_execution_engine_futures.py`,
`test_pre_t1_e_order_cycle_safety.py`, `test_pre_t1_e_rem_a_order_authorization.py`)
were changed to bypass `_validate_record_for_execution`/
`execution_ineligibility_reason` themselves — they only bypass
`_decision_execution_denial_reason` (mirroring the pre-existing
`_decision_id_is_durably_persisted` bypass pattern) for tests that target
OTHER behavior; Group R's tests exercise the REAL, un-bypassed strict
gate directly, so the production correction is never itself weakened by
a fixture.

### Blocker A documentation correction (R1.3, per MASTER's explicit instruction)

R1.2's phrasing risked being read as implying R1.2 itself corrected the
adapter fail-closed production boundary. It did not: that boundary was
**implemented in R1.1** (via `OrderIntentCoordinator.submit()`'s
`supports_client_order_id` gate, itself derived from
`AdapterCapabilityVerdict.SUBMIT_AND_RECONCILE_VERIFIED`) and **only
revalidated in R1.2** (via the 16 `TestGroupP_R12_AdapterFailClosed`
tests, which pass unmodified against the R1.1 head, with zero production
code changed). The required classification, applied verbatim to this ADR,
the order-cycle-safety contract, and the PR description:
`ALREADY_SATISFIED_AT_R1_1 — REVALIDATED_IN_R1_2`. The 16-test proof, the
zero-mutation evidence, and the exact source anchor
(`if not self._capabilities.supports_client_order_id: return
UNSUPPORTED_ADAPTER_CAPABILITY` in `OrderIntentCoordinator.submit()`,
where `supports_client_order_id` is `True` ONLY when `verdict ==
SUBMIT_AND_RECONCILE_VERIFIED`) are all preserved unchanged from R1.2's
section above — only the attribution wording is corrected here and in
§22.3 of the contract.

### R1.3 verification

Targeted suite (REM-B protocol file/order-cycle-safety/REM-A
authorization/execution-engine/execution-engine-futures): 314 tests, 313
pass, 1 pre-existing unrelated `ccxt`-not-installed environment failure
(same class already confirmed pre-existing on `origin/main` in R1.1/R1.2).
Ruff baseline gate, `git diff --check`, and journal-pollution checks: see
final report. No REM-C scope started; no real/testnet exchange call; no
deployment; no VPS or secret access.

### R1.3 safety confirmations

No real/testnet exchange call, no live trading, no deployment, no VPS
access, no secrets touched, no REM-C scope started, no O-02W-E2/T-1/F-00
scope started. PR remains **draft**, **unmerged**, no force-push, no
rebase, no squash, no amend of previously reviewed commits.

## R1.4 persist() idempotence — legacy upgrade closure and binding permanence (2026-09-11)

Starting HEAD: `015f701574c099ae35f37bab3980e49d7edda35d` (verified:
local/remote/GitHub PR metadata all matched; base `092bb88f...` unchanged;
working tree clean). R1.3 correctly separated historical existence from
execution authority in `bind_intent()`/`execution_ineligibility_reason()`
— but MASTER's R1.4 review found `DecisionIdentityJournal.persist()`
itself still had two related authority-reset defects.

### `persist(` production call-site inventory

Repository-wide grep for `.persist(` confirms exactly ONE production
(non-test) call site: `core/advisor_loop.py:1308`, inside
`analyze_symbol()`, immediately after `_trace_id = new_trace_id()`
(line 1288) — classified as **first creation only**: `new_trace_id()`
generates a fresh random UUID on every call, so under the current call
pattern this site can never actually invoke `persist()` twice for the
SAME `decision_id` (no outer caller can force id reuse; a caller-level
retry of `analyze_symbol()` itself would regenerate a new id anyway).
`ExecutionEngine` itself NEVER calls `.persist()` (confirmed by grep —
only `is_persisted()`, `execution_ineligibility_reason()`, and
`bind_intent()`). All other `.persist(` matches are either
`RejectionStore.persist()` (`observability/rejection_store.py`,
`tests/test_rejection_store.py` — an unrelated class with an unrelated
method of the same name) or the ~35 test-only call sites in
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py`. Despite no
current production path triggering a duplicate `persist()` call, the
public API contract must still be safe against future retry/duplicate-
delivery callers — which is exactly what R1.4 closes.

### Fail-before proof (behavioral, real mutation counters, exact starting HEAD)

**Scenario A (legacy upgrade through persist())**: a hand-crafted
schema-v1 legacy record (`is_persisted()` → `True`,
`is_execution_eligible()` → `False`, 1 journal line) was passed to the
PUBLIC `persist()` API with metadata compatible with the legacy record.
Result: `persist()` returned normally (no exception), appended a SECOND
line (a brand-new valid schema-v2 `CREATED` record), and
`is_execution_eligible()` flipped to `True`. Through the real
`ExecutionEngine.create_order()` path (certified fake exchange, no
network): `mode="live"`, `denial_reason=None`,
**`mock_exchange.create_order.call_count == 1`**. Root cause: the OLD
conflict check (`existing.get("payload_digest") and
existing["payload_digest"] != digest`) is a no-op when `existing` has NO
`payload_digest` key at all (exactly a legacy record's shape) — so
`persist()` fell through to an unconditional append.

**Scenario B (bound decision reset through persist())**: a genuine
schema-v2 decision `D` was persisted and bound to intent digest `A`
(`lifecycle_state="BOUND"`, `bound_intent_digest=A`, 2 journal lines).
Calling `persist(D, ...)` again with the IDENTICAL canonical provenance
(a duplicate-delivery replay) appended a THIRD line resetting
`lifecycle_state` back to `"CREATED"` and `bound_intent_digest` to
`None`. `bind_intent(D, B)` with `B != A` — which R1.3 correctly rejects
when the durable binding is intact — then SUCCEEDED (no exception),
overwriting the binding to `B`. Root cause: the OLD digest-conflict
check only raised when digests DIFFERED; an IDENTICAL digest fell
through the same unconditional-append path as Scenario A, with no
early-return for "nothing changed, do nothing."

Neither proof used `AttributeError`, an absent method, a collection
failure, or a mock that bypasses the production gate — both used real
`DecisionIdentityJournal`/`ExecutionEngine` instances against temp-path
journals, with `MagicMock`-based fake exchanges whose `create_order`
call counter is the actual evidence.

### Precise root cause

`persist()`'s existing-record handling had two independent gaps in the
SAME code path: (1) the conflict check was skipped entirely (not merely
under-triggered) when the existing record had no `payload_digest` — the
exact shape of ANY legacy or otherwise-malformed record; (2) even when
the check correctly did NOT trigger (matching digest — the legitimate
duplicate-delivery case), the function had no early-return and fell
through to the SAME unconditional append that a genuinely new decision
uses — silently resetting lifecycle state regardless of whether anything
had actually changed.

### Fix — final `persist()` semantics

`persist()` now branches into exactly three cases per call, matching the
R1.4 spec's pseudocode:

1. **`existing is None`** (I1 — first persistence): validate and append
   exactly as before — one valid `CREATED` record.
2. **`existing` exists**: it is first validated with the SAME strict
   `_validate_record_for_execution()` function `bind_intent()` and
   `execution_ineligibility_reason()` use.
   - If `existing` is NOT execution-eligible (I5/I6 — legacy schema,
     corrupted digest, invalid lifecycle, ...): raise
     `DecisionIdentityError`, **zero append**. A legacy or corrupted
     record can no longer be silently promoted into fresh v2 authority
     merely by calling `persist()` again — the same rule `bind_intent()`
     already enforced for BINDING now applies to PERSISTING too.
   - If `existing` IS eligible but a duplicated top-level provenance
     field (`namespace`/`cycle`/`symbol`/`action`) disagrees with the
     candidate (I7): raise `DecisionIdentityError`, **zero append** —
     checked before the payload-digest comparison so this specific
     conflict is reported precisely.
   - If the recomputed candidate digest disagrees with the existing
     stored digest: raise `DecisionIdentityError`, **zero append**
     (unchanged conflict rule from R1.2).
   - Otherwise (I2/I3/I4/I8 — genuine duplicate-delivery replay, same
     provenance, same payload): **return the existing record UNCHANGED,
     zero append.** This is the change that actually fixes Scenario B —
     there is no code path left that appends a new record for an
     unchanged, already-persisted decision, so `lifecycle_state` and
     `bound_intent_digest` can never be reset by a duplicate `persist()`
     call.

`persist()` MUST NEVER reset `lifecycle_state`, MUST NEVER clear
`bound_intent_digest`, MUST NEVER silently upgrade legacy/corrupted
evidence — all three are now structurally impossible: every branch either
appends a genuinely NEW record for a genuinely NEW decision, or raises
with zero writes, or returns the untouched existing record.

### Pass-after (permanent regression tests)

14 new tests, `TestGroupS_R14_PersistIdempotence` in
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py`: identical
duplicate `CREATED` persist is zero-append/idempotent (1); duplicate
persist after `BOUND` preserves state/digest/line-count (3); different
bind after duplicate persist remains rejected (1); legacy record +
persist raises with zero append and remains ineligible (2); corrupted v2
+ persist raises with zero append and remains ineligible (2); same-id
different-payload and provenance-disagreement both remain rejected (2);
end-to-end spot and futures proofs that duplicate persist cannot produce
a second mutation (2); restart/new-journal-instance binding permanence
(1). Both fail-before scripts re-run against the fixed code confirm the
exact required pass-after transitions (see final report).

### R1.4 verification

Targeted suite (REM-B protocol file/order-cycle-safety/REM-A
authorization/execution-engine/execution-engine-futures): 328 tests, 327
pass, 1 pre-existing unrelated `ccxt`-not-installed environment failure
(same class already confirmed pre-existing across R1.1/R1.2/R1.3). Ruff
baseline gate: 958/958, 0 new. `git diff --check`: clean. No
`databases/order_intent_journal.jsonl` or
`databases/decision_identity_journal.jsonl` pollution. Exactly 2 files
changed: `decision_identity.py` (production) and
`tests/test_pre_t1_e_rem_b_idempotent_order_protocol.py` (tests) —
`execution_engine.py` was NOT modified; the fail-before investigation
confirmed the defect was entirely contained in `persist()` itself, with
no production-code change needed at any `ExecutionEngine` call site.

### R1.4 does not regress R1.3

All R1.3 properties revalidated in the same test run: legacy/corrupted
direct `bind_intent()` rejection, strict
`execution_ineligibility_reason()`, spot/futures zero mutation,
`recover_pending_decisions()` exclusion, historical `is_persisted()`
semantics unchanged (still existence-only, never execution authority),
and Blocker A's attribution remains
`ALREADY_SATISFIED_AT_R1_1 — REVALIDATED_IN_R1_2` (unchanged, not
rewritten).

### R1.4 safety confirmations

No real/testnet exchange call, no live trading, no deployment, no VPS
access, no secrets touched, no REM-C scope started, no O-02W-E2/T-1/F-00
scope started. PR remains **draft**, **unmerged**, no force-push, no
rebase, no squash, no amend of previously reviewed commits.
