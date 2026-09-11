"""
decision_identity.py — durable upstream decision-identity persistence
(O-02W-PRE-T1-E REM-B-R1.1 Blocker A, tightened by REM-B-R1.2 Blocker B).

Causal objective: the same logical decision must retain the same causal
identity before, during, and after execution-component reconstruction, and
that identity must be RECONSTRUCTIBLE from durable state alone after a
process restart — not merely "provably persisted while the original
in-memory object/variable is still alive" (R1.1's gap, named explicitly by
MASTER review: "a new journal object can retrieve an ID already supplied by
the test" is not restart-reconstruction proof).

`order_intent_protocol.py`'s journal durably records the ORDER INTENT
(after REM-A authorization); this module durably records the DECISION
ITSELF, one step further upstream.

Causal ordering this module exists to prove/enforce (R1.2 tightened form):
  DECISION_ID_CREATED -> DECISION_RECORD_DURABLY_PERSISTED ->
  DECISION_RELOADED_OR_VERIFIED -> REM_A_ORDER_AUTHORIZATION ->
  ORDER_INTENT_BOUND_TO_DECISION -> ORDER_INTENT_DURABLY_PERSISTED ->
  SUBMISSION_STARTED -> EXCHANGE_MUTATION_ATTEMPT

`ExecutionEngine.create_order()`/`create_futures_order()` verify a
supplied `decision_id` was durably persisted here BEFORE proceeding —
an unpersisted (or merely in-memory) `decision_id` fails closed with zero
mutation calls, exactly like a missing one. Before submission, the built
`OrderIntent`'s digest is atomically BOUND to the decision — a second
attempt to bind the same `decision_id` to a different intent digest fails
closed (R1.2 Blocker B, §4.3).

Explicitly NOT implemented here (REM-C scope): full decision/packet
reconstruction, replay of strategy state, partial-fill lifecycle,
automatic resubmission after restart. This is identity-and-binding-only,
append-only, and durable — nothing more.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 2  # R1.2: canonical payload + digest + lifecycle + binding


class DecisionIdentityError(RuntimeError):
    """Raised when a decision identity cannot be durably persisted, or a
    lifecycle/binding transition is invalid — callers must fail closed
    (zero mutation calls) rather than proceed with an unpersisted,
    corrupted, or ambiguously-bound identity (spec §4)."""


def _canonical_payload_json(payload: dict) -> str:
    """Fixed key order, deterministic — the exact bytes the digest is
    computed over. Mirrors `order_intent_protocol.OrderIntent.canonical_json`."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _payload_digest(payload: dict) -> str:
    return hashlib.sha256(_canonical_payload_json(payload).encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    """Structural check only — does NOT recompute anything, just confirms
    `value` has the SHAPE a `hashlib.sha256(...).hexdigest()` output always
    has (64 lowercase hex characters). Used to reject a `payload_digest` or
    `bound_intent_digest` that is missing, the wrong type, or obviously
    malformed BEFORE any digest recomputation is attempted."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


# R1.3 (O-02W-PRE-T1-E REM-B-R1.3) — the exact set of lifecycle states a
# record must be in to be considered for execution eligibility at all. Any
# other value (missing, misspelled, from a future schema this code doesn't
# know about) is unrecognized and therefore ineligible — never silently
# treated as equivalent to a known state.
_RECOGNIZED_LIFECYCLE_STATES = {"CREATED", "BOUND"}

# Fields that may appear BOTH at the record's top level (used by
# `find_by_cycle_key`'s lookup) and inside the canonical `payload` (used by
# the digest). R1.3 Correction: these two copies must never be allowed to
# silently disagree — a record where they diverge is contradictory
# evidence, not usable for execution authority, even if the digest itself
# is internally self-consistent.
_DUPLICATED_PROVENANCE_FIELDS = ("namespace", "cycle", "symbol", "action")


class DecisionIdentityJournal:
    """Append-only JSONL durable authority for decision identities — the
    DECISION-level counterpart to `order_intent_protocol.OrderIntentJournal`
    (which records the ORDER INTENT, one causal step later). One record per
    write, never rewritten in place; a truncated/corrupt final line is
    tolerated (same durability contract as the order-intent journal), never
    fatal to prior valid records.

    Concurrency: a `threading.Lock` serializes writers within one process.
    This module makes the SAME explicit, honest single-writer-within-one-
    process claim as `OrderIntentJournal` did before REM-B-R1's Correction
    D added cross-process locking there — no cross-process guarantee is
    made or needed here, since this repo's actual decision-creation path
    (`core/advisor_loop.py`) runs as a single process (see CLAUDE.md
    stabilization window)."""

    def __init__(self, path: str | os.PathLike):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self._path.exists():
            self._path.touch()

    @property
    def path(self) -> Path:
        return self._path

    # ── durable append (I3-equivalent: durable-before-return) ─────────────
    # `_append_unlocked` (below `get`/lookup helpers) is the single append
    # implementation; every public writer (`persist`, `bind_intent`) holds
    # `self._lock` for its own check-then-write critical section and calls
    # it directly — there is no separate locked `_append` wrapper, to avoid
    # a second, redundant acquisition of the same non-reentrant lock.

    def persist(
        self,
        decision_id: str,
        *,
        namespace: str,
        cycle: Optional[int] = None,
        symbol: Optional[str] = None,
        action: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> dict:
        """Durably appends and fsyncs a CANONICAL decision-identity record
        BEFORE returning — callers MUST call this and have it return before
        the decision reaches REM-A authorization or execution (causal
        ordering, spec §4). Raises `DecisionIdentityError` (never silently
        substitutes a fallback identity) if `decision_id` is missing/blank
        — this is a fail-closed constructor, not a best-effort logger.

        `payload` (R1.2): the canonical, reconstructible evidence for this
        decision — whatever fields the caller has available (typically at
        minimum namespace/cycle/symbol/action). If omitted, a minimal
        payload is derived from the other keyword arguments so a digest can
        still be computed and later verified — but callers SHOULD pass a
        richer payload when available, since the payload (not the bare
        `decision_id`) is what R1.2 calls "the scientific evidence".

        R1.4 idempotence contract (O-02W-PRE-T1-E REM-B-R1.4): calling
        `persist()` again for a `decision_id` that ALREADY has a durable
        record is a DUPLICATE-DELIVERY replay, not a fresh creation.
        `persist()` NEVER appends a new record in that case — it either
        returns the existing effective record UNCHANGED (zero writes, the
        matching-payload case) or raises `DecisionIdentityError` with ZERO
        writes (an existing execution-ineligible record, a provenance
        mismatch, or a conflicting payload digest). In particular:

          - `persist()` MUST NEVER reset `lifecycle_state` (e.g. silently
            turning a durably `BOUND` decision back into `CREATED`);
          - `persist()` MUST NEVER clear `bound_intent_digest`;
          - `persist()` MUST NEVER silently promote a legacy
            (`schema_version != 2`) or corrupted (digest-mismatched,
            lifecycle-invalid, ...) existing record into fresh schema-v2
            authority merely by being called again with matching metadata.

        This closes the exact gap MASTER's R1.4 review demonstrated
        behaviorally: previously, a legacy record's absent
        `payload_digest` skipped the conflict check entirely (silently
        upgrading it to valid v2 `CREATED` authority), and even an
        IDENTICAL-digest duplicate call fell through to an unconditional
        append that reset `BOUND` back to `CREATED` and erased
        `bound_intent_digest` — both proven to reach a real mutation call.
        """
        if not decision_id or not str(decision_id).strip():
            raise DecisionIdentityError(
                "decision_id is required to persist a decision identity — "
                "refusing to silently substitute a fresh/fallback value "
                "(O-02W-PRE-T1-E REM-B-R1.1, Blocker A)"
            )
        decision_id = str(decision_id).strip()
        if payload is None:
            payload = {
                "namespace": str(namespace),
                "cycle": cycle,
                "symbol": symbol,
                "action": action,
            }
        digest = _payload_digest(payload)
        with self._lock:
            existing = self._latest_record_unlocked(decision_id)

            if existing is None:
                # I1 — first persistence: a never-seen valid decision id
                # creates exactly one valid v2 CREATED authority record.
                record = {
                    "schema_version": SCHEMA_VERSION,
                    "decision_id": decision_id,
                    "namespace": str(namespace),
                    "cycle": cycle,
                    "symbol": symbol,
                    "action": action,
                    "payload": payload,
                    "payload_digest": digest,
                    "lifecycle_state": "CREATED",
                    "bound_intent_digest": None,
                    "ts": time.time(),
                }
                self._append_unlocked(record)
                return record

            # I5/I6 — an existing record that is NOT strictly
            # execution-eligible (legacy schema, missing/malformed/
            # mismatched digest, unrecognized/invalid lifecycle state,
            # ...) must never be silently healed/upgraded into fresh
            # authority by a normal persist() call. Checked using the
            # SAME strict function `bind_intent`/`execution_ineligibility_
            # reason` use, so the three can never silently drift apart.
            ineligibility_reason = self._validate_record_for_execution(existing)
            if ineligibility_reason is not None:
                raise DecisionIdentityError(
                    f"decision_id={decision_id!r} already has a durable "
                    f"record that failed strict execution-eligibility "
                    f"validation ({ineligibility_reason}) — refusing to "
                    f"persist over it (would silently upgrade legacy/"
                    f"corrupted evidence into fresh authority, fail-closed, "
                    f"O-02W-PRE-T1-E REM-B-R1.4)"
                )

            # I7 — provenance consistency: the duplicated top-level fields
            # must agree with what is already durably recorded. Checked
            # BEFORE the payload-digest comparison so a provenance-only
            # mismatch is reported precisely, not folded into a generic
            # digest conflict.
            for field, candidate_value in (
                ("namespace", str(namespace)),
                ("cycle", cycle),
                ("symbol", symbol),
                ("action", action),
            ):
                if existing.get(field) != candidate_value:
                    raise DecisionIdentityError(
                        f"decision_id={decision_id!r} was already persisted "
                        f"with a DIFFERENT top-level {field}="
                        f"{existing.get(field)!r} (candidate: "
                        f"{candidate_value!r}) — refusing a conflicting "
                        f"duplicate record (fail-closed, R1.2 §4.5 / "
                        f"R1.4 I7)"
                    )

            existing_digest = existing.get("payload_digest")
            if existing_digest != digest:
                raise DecisionIdentityError(
                    f"decision_id={decision_id!r} was already persisted with a "
                    f"DIFFERENT canonical payload (digest {existing_digest!r} "
                    f"!= {digest!r}) — refusing a conflicting duplicate record "
                    f"(fail-closed, R1.2 §4.5)"
                )

            # I2/I3/I4/I8 — same logical decision replay: the durable
            # effective record already exists and matches exactly (same
            # provenance, same payload digest). Return it UNCHANGED —
            # ZERO append. This is what actually preserves a `BOUND`
            # lifecycle state and its `bound_intent_digest` across a
            # duplicate-delivery persist() call; appending here at all
            # (even with identical values) would still reset
            # `lifecycle_state` back to `CREATED`, which is the exact
            # defect this round closes.
            return existing

    def bind_intent(self, decision_id: str, intent_digest: str) -> dict:
        """Atomically binds this decision to the order-intent digest it is
        authorized to produce (R1.2 Blocker B, §4.3; hardened R1.3). Fail-
        closed rules:

          - unpersisted `decision_id` -> `DecisionIdentityError`, zero writes;
          - a record that fails STRICT execution-eligibility validation
            (legacy schema_version, missing/malformed/mismatched payload
            digest, contradictory provenance, unrecognized or structurally
            invalid lifecycle state — see `_validate_record_for_execution`)
            -> `DecisionIdentityError`, zero writes. R1.3 closes the exact
            gap MASTER's fail-before proof demonstrated: a legacy or
            corrupted record must NEVER be silently "upgraded" to BOUND —
            binding is refused BEFORE that append, not merely tolerated
            after the fact;
          - first bind for an otherwise-eligible decision -> appends a
            BOUND record;
          - replaying the SAME (decision_id, intent_digest) pair -> no-op,
            returns the existing BOUND record (idempotent, matches restart
            idempotence expectations — a retried bind is not an error);
          - binding the SAME decision_id to a DIFFERENT intent_digest ->
            `DecisionIdentityError`, zero writes (a persisted decision may
            authorize exactly one order intent under this module's model —
            REM-C may define an explicit versioned child-intent index for
            multi-intent decisions; this module does not silently allow it).
        """
        if not intent_digest or not _is_sha256_hex(intent_digest):
            raise DecisionIdentityError(
                "intent_digest must be a non-empty, well-formed SHA-256 hex "
                "digest to bind an order intent to a decision — refusing an "
                f"empty or malformed binding ({intent_digest!r})"
            )
        with self._lock:
            record = self._latest_record_unlocked(decision_id)
            if record is None:
                raise DecisionIdentityError(
                    f"cannot bind order intent: decision_id={decision_id!r} "
                    f"has no durably persisted record"
                )
            ineligibility_reason = self._validate_record_for_execution(record)
            if ineligibility_reason is not None:
                raise DecisionIdentityError(
                    f"decision_id={decision_id!r} failed strict execution-"
                    f"eligibility validation ({ineligibility_reason}) — "
                    f"refusing to bind an order intent to a legacy, "
                    f"corrupted, or otherwise invalid record (fail-closed, "
                    f"O-02W-PRE-T1-E REM-B-R1.3)"
                )
            existing_bound = record.get("bound_intent_digest")
            if existing_bound == intent_digest:
                return record  # idempotent replay — no new write needed
            if existing_bound is not None and existing_bound != intent_digest:
                raise DecisionIdentityError(
                    f"decision_id={decision_id!r} is already bound to intent "
                    f"digest {existing_bound!r} — refusing to rebind to a "
                    f"different intent digest {intent_digest!r} (fail-closed, "
                    f"R1.2 Blocker B §4.3)"
                )
            new_record = dict(record)
            new_record["lifecycle_state"] = "BOUND"
            new_record["bound_intent_digest"] = intent_digest
            new_record["ts"] = time.time()
            self._append_unlocked(new_record)
            return new_record

    def _append_unlocked(self, record: dict) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as exc:
            raise DecisionIdentityError(
                f"decision-identity journal write failed: {exc}"
            ) from exc

    # ── durable reads (restart reconstruction, R1.2 §4.4) ─────────────────

    def _read_all_records(self) -> list[dict]:
        records: list[dict] = []
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return records
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # Truncated/corrupt final line — tolerated, never fatal to
                # prior valid records (mirrors OrderIntentJournal's I5).
                continue
            if not isinstance(rec, dict) or not rec.get("decision_id"):
                continue
            records.append(rec)
        return records

    def _latest_by_decision_id_unlocked(self) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for rec in self._read_all_records():
            latest[rec["decision_id"]] = rec
        return latest

    def _latest_record_unlocked(self, decision_id: str) -> Optional[dict]:
        if not decision_id:
            return None
        return self._latest_by_decision_id_unlocked().get(str(decision_id).strip())

    def get(self, decision_id: str) -> Optional[dict]:
        """Read-only lookup of the latest record for one `decision_id` —
        replays the journal (no cached index) so restart/reconstruction
        always sees exactly what was durably written, nothing stale."""
        with self._lock:
            return self._latest_record_unlocked(decision_id)

    def is_persisted(self, decision_id: str) -> bool:
        """Read-only membership check — True iff a well-formed
        (schema-valid, digest-computable) record exists for this
        `decision_id`, regardless of lifecycle state. Legacy records
        missing required R1.2 fields (`payload`/`payload_digest`) are
        treated as NOT usable for restart reconstruction (see
        `recover_pending_decisions`) but are still accepted here for
        backward compatibility with R1.1's simpler persisted/unpersisted
        gate — R1.1 callers only ever wrote schema-2 records themselves, so
        this compatibility path only matters for genuinely legacy data."""
        rec = self.get(decision_id)
        return rec is not None

    @staticmethod
    def _validate_record_for_execution(record: dict) -> Optional[str]:
        """R1.3 (O-02W-PRE-T1-E REM-B-R1.3) — the SOLE strict-validity
        check for execution authority. Returns `None` if `record` satisfies
        every applicable invariant (spec §4, points 1-9), or a stable
        machine-readable reason string identifying the FIRST invariant
        violated. This is deliberately the ONLY place this logic lives —
        both `execution_ineligibility_reason` (the read-only query
        `ExecutionEngine` consults before mutating) and `bind_intent` (which
        must independently refuse to extend an ineligible record) call this
        same method, so the two can never silently drift apart.

        This function performs NO network I/O, NO journal I/O, and NO
        mutation — it is a pure function of one already-loaded record."""
        if record.get("schema_version") != SCHEMA_VERSION:
            return "LEGACY_SCHEMA_VERSION"

        decision_id = record.get("decision_id")
        if (
            not decision_id
            or not isinstance(decision_id, str)
            or not decision_id.strip()
        ):
            return "MISSING_OR_INVALID_DECISION_ID"

        payload = record.get("payload")
        if not isinstance(payload, dict) or not payload:
            return "MISSING_OR_INVALID_PAYLOAD"

        digest = record.get("payload_digest")
        if not _is_sha256_hex(digest):
            return "MISSING_OR_MALFORMED_PAYLOAD_DIGEST"

        if _payload_digest(payload) != digest:
            return "PAYLOAD_DIGEST_MISMATCH"

        for field in _DUPLICATED_PROVENANCE_FIELDS:
            if field in payload and payload[field] != record.get(field):
                return "PROVENANCE_INCONSISTENT"

        lifecycle_state = record.get("lifecycle_state")
        if lifecycle_state not in _RECOGNIZED_LIFECYCLE_STATES:
            return "UNRECOGNIZED_LIFECYCLE_STATE"

        bound_intent_digest = record.get("bound_intent_digest")
        if lifecycle_state == "CREATED":
            if bound_intent_digest is not None:
                return "CREATED_RECORD_UNEXPECTEDLY_BOUND"
        elif lifecycle_state == "BOUND":
            if not _is_sha256_hex(bound_intent_digest):
                return "BOUND_RECORD_INVALID_INTENT_DIGEST"

        return None

    def execution_ineligibility_reason(self, decision_id: str) -> Optional[str]:
        """R1.3 — the strict, fail-closed EXECUTION-AUTHORITY query.
        Returns `None` only when `decision_id`'s latest effective record
        satisfies every applicable invariant (spec §4, points 1-9) — schema
        version, exact non-empty id, well-typed canonical payload, a
        structurally valid digest that actually verifies, internally
        consistent duplicated provenance fields, a recognized and
        structurally valid lifecycle state. Otherwise returns a stable
        machine-readable reason string (`"NOT_PERSISTED"` for a missing
        record, or one of `_validate_record_for_execution`'s reasons for a
        record that exists but is legacy/incomplete/corrupted/
        contradictory/structurally invalid).

        THIS — never `is_persisted()` — is the method any execution-
        authority decision must consult. `is_persisted()` remains a pure
        historical/existence query; it must never be read as permission to
        mutate (R1.3, correcting the exact defect MASTER's fail-before
        proof demonstrated: a schema-v1 record with no canonical payload,
        digest, or lifecycle evidence previously made `is_persisted()`
        return `True` and was accepted by `ExecutionEngine` as execution
        authority)."""
        if not decision_id or not str(decision_id).strip():
            return "MISSING_DECISION_ID"
        record = self.get(decision_id)
        if record is None:
            return "NOT_PERSISTED"
        return self._validate_record_for_execution(record)

    def is_execution_eligible(self, decision_id: str) -> bool:
        """Convenience boolean wrapper over `execution_ineligibility_reason`
        — `True` iff that method returns `None`. Prefer
        `execution_ineligibility_reason` directly when the caller needs to
        distinguish MISSING/UNPERSISTED/INELIGIBLE for a typed denial
        (R1.3 spec §4 — "do not silently map corrupted evidence to
        ordinary absence")."""
        return self.execution_ineligibility_reason(decision_id) is None

    def recover_pending_decisions(
        self, *, namespace: Optional[str] = None
    ) -> dict[str, dict]:
        """R1.2 §4.4 — the restart-reconstruction entry point. Returns the
        latest, SCHEMA-VALID record for every `decision_id` this journal
        has ever durably recorded (optionally filtered to one namespace),
        keyed by `decision_id`. A caller with ONLY this journal's path (no
        retained in-memory `decision_id` variable, no retained coordinator
        or engine object) can call this after constructing a brand-new
        `DecisionIdentityJournal` instance and discover every recoverable
        decision from durable state alone.

        R1.3: uses the SAME strict `_validate_record_for_execution` check
        `execution_ineligibility_reason`/`bind_intent` use — ANY
        execution-ineligible record (legacy schema, missing/malformed/
        mismatched digest, contradictory provenance, unrecognized or
        structurally invalid lifecycle state) is excluded, not merely one
        missing `payload`/`payload_digest` outright. Historical records
        remain readable via `get()`/`is_persisted()` for audit purposes —
        they simply never appear here, since this method's contract is
        "recoverable enough to resume toward execution," not "ever
        existed"."""
        with self._lock:
            latest = self._latest_by_decision_id_unlocked()
        out: dict[str, dict] = {}
        for decision_id, rec in latest.items():
            if self._validate_record_for_execution(rec) is not None:
                continue  # execution-ineligible — fail closed, not recoverable
            if namespace is not None and rec.get("namespace") != namespace:
                continue
            out[decision_id] = rec
        return out

    def find_by_cycle_key(
        self, *, namespace: str, cycle: Optional[int], symbol: Optional[str]
    ) -> Optional[dict]:
        """Convenience recovery selector: find the latest recoverable
        decision matching (namespace, cycle, symbol) without needing to
        already know its `decision_id`. Returns `None` if no match, or if
        more than one distinct `decision_id` matches (ambiguous — fails
        closed rather than guessing which one a caller means)."""
        candidates = [
            rec
            for rec in self.recover_pending_decisions(namespace=namespace).values()
            if rec.get("cycle") == cycle and rec.get("symbol") == symbol
        ]
        if len(candidates) != 1:
            return None
        return candidates[0]

    def verify_digest(self, decision_id: str, payload: Optional[dict] = None) -> bool:
        """Recomputes the payload digest from either a caller-supplied
        `payload` (tamper check against durable state) or the durably
        stored payload itself (self-consistency check), and compares it
        against the durably stored `payload_digest`. Returns False for a
        missing/legacy record, a stored `payload` that no longer hashes to
        its own stored `payload_digest` (corruption), or a caller-supplied
        `payload` that disagrees (tampering) — never raises for this;
        callers decide whether False means "fail closed" or "quarantine"."""
        rec = self.get(decision_id)
        if rec is None or not rec.get("payload") or not rec.get("payload_digest"):
            return False
        target_payload = payload if payload is not None else rec["payload"]
        return _payload_digest(target_payload) == rec["payload_digest"]


_DEFAULT_DECISION_IDENTITY_JOURNAL_PATH = os.getenv(
    "DECISION_IDENTITY_JOURNAL_PATH", "databases/decision_identity_journal.jsonl"
)


def default_decision_identity_journal() -> DecisionIdentityJournal:
    """Resolved fresh on every call (DS-001/ADR-0008 — the env var itself
    is read once into the module constant above at import time, matching
    `order_intent_protocol.py`'s `_DEFAULT_ORDER_INTENT_JOURNAL_PATH`
    convention exactly, including root `conftest.py`'s DS-001 redirect for
    tests) but the `DecisionIdentityJournal` instance is constructed fresh
    each call — callers (ExecutionEngine, advisor_loop.py) are expected to
    cache their own instance the same way `ExecutionEngine.
    _get_order_intent_coordinator()` lazily caches its journal, not to
    call this function on every single decision."""
    return DecisionIdentityJournal(_DEFAULT_DECISION_IDENTITY_JOURNAL_PATH)
