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
        `decision_id`) is what R1.2 calls "the scientific evidence"."""
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
            if (
                existing is not None
                and existing.get("payload_digest")
                and existing["payload_digest"] != digest
            ):
                raise DecisionIdentityError(
                    f"decision_id={decision_id!r} was already persisted with a "
                    f"DIFFERENT canonical payload (digest {existing['payload_digest']!r} "
                    f"!= {digest!r}) — refusing a conflicting duplicate record "
                    f"(fail-closed, R1.2 §4.5)"
                )
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

    def bind_intent(self, decision_id: str, intent_digest: str) -> dict:
        """Atomically binds this decision to the order-intent digest it is
        authorized to produce (R1.2 Blocker B, §4.3). Fail-closed rules:

          - unpersisted `decision_id` -> `DecisionIdentityError`, zero writes;
          - first bind for this decision -> appends a BOUND record;
          - replaying the SAME (decision_id, intent_digest) pair -> no-op,
            returns the existing BOUND record (idempotent, matches restart
            idempotence expectations — a retried bind is not an error);
          - binding the SAME decision_id to a DIFFERENT intent_digest ->
            `DecisionIdentityError`, zero writes (a persisted decision may
            authorize exactly one order intent under this module's model —
            REM-C may define an explicit versioned child-intent index for
            multi-intent decisions; this module does not silently allow it).
        """
        if not intent_digest:
            raise DecisionIdentityError(
                "intent_digest is required to bind an order intent to a "
                "decision — refusing an empty binding"
            )
        with self._lock:
            record = self._latest_record_unlocked(decision_id)
            if record is None:
                raise DecisionIdentityError(
                    f"cannot bind order intent: decision_id={decision_id!r} "
                    f"has no durably persisted record"
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

        A record missing `payload`/`payload_digest` (a genuinely legacy,
        pre-R1.2 record) is excluded — it cannot be reconstructed with
        digest-verifiable evidence, so it fails closed here rather than
        being silently treated as recoverable."""
        with self._lock:
            latest = self._latest_by_decision_id_unlocked()
        out: dict[str, dict] = {}
        for decision_id, rec in latest.items():
            if not rec.get("payload") or not rec.get("payload_digest"):
                continue  # legacy/incomplete record — fail closed, not recoverable
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
