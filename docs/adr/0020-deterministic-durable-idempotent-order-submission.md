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
