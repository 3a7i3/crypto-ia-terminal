"""
decision_identity.py — durable upstream decision-identity persistence
(O-02W-PRE-T1-E REM-B-R1.1, Blocker A).

Causal objective: the same logical decision must retain the same causal
identity before, during, and after execution-component reconstruction.
`order_intent_protocol.py`'s journal durably records the ORDER INTENT
(after REM-A authorization); this module durably records the DECISION
ITSELF, one step further upstream — closing the gap R1's Correction B
investigation named explicitly: `trace_id` (the causal id propagated into
`decision_id`) was stable in-memory for one execution attempt but was
never durably persisted BEFORE execution, so a crash between decision
creation and network mutation could not be reconciled by restart.

Investigation summary (full detail: docs/adr/0020-...md R1.1 section):
- `core/advisor_loop.py`'s `_trace_id = new_trace_id()` (a random UUID)
  is created exactly once per decision cycle, stored on
  `DecisionPacket.metadata["trace_id"]`, and never regenerated before
  reaching `ExecutionEngine.create_order()`/`create_futures_order()`.
- No canonical decision/packet persistence exists in this repository that
  durably records a decision's identity BEFORE it reaches execution (the
  various observability/audit logs record decisions only AFTER an
  execution attempt, or asynchronously, not durably-before-network).
- Per spec §4's explicit fallback ("If no canonical decision persistence
  exists: implement the minimum append-only decision-identity persistence
  necessary for REM-B"), this module is that minimum: it does NOT persist
  the full decision (strategy inputs, signal state, etc.) — only the
  identity record needed to prove a `decision_id` was durably established
  before it could reach execution, and to let journal reconstruction
  associate an in-flight order intent with its originating decision.

Causal ordering this module exists to prove/enforce:
  DECISION_ID_CREATED -> DECISION_PERSISTED -> REM_A_AUTHORIZATION ->
  ORDER_INTENT_RECORDED -> SUBMISSION_STARTED -> EXCHANGE_MUTATION

`ExecutionEngine.create_order()`/`create_futures_order()` verify a
supplied `decision_id` was durably persisted here BEFORE proceeding —
an unpersisted (or merely in-memory) `decision_id` fails closed with zero
mutation calls, exactly like a missing one (I1/I5 of the invariant list).

Explicitly NOT implemented here (REM-C scope): full decision/packet
reconstruction, replay of strategy state, partial-fill lifecycle. This is
identity-only, append-only, and durable — nothing more.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 1


class DecisionIdentityError(RuntimeError):
    """Raised when a decision identity cannot be durably persisted —
    callers must fail closed (zero mutation calls) rather than proceed
    with an unpersisted identity (spec §4/§3 invariant 5, 8)."""


class DecisionIdentityJournal:
    """Minimal append-only JSONL durable authority for decision
    identities — the DECISION-level counterpart to
    `order_intent_protocol.OrderIntentJournal` (which records the ORDER
    INTENT, one causal step later). One record per `persist()` call, never
    rewritten in place; a truncated/corrupt final line is tolerated (same
    durability contract as the order-intent journal), never fatal.

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

    def persist(
        self,
        decision_id: str,
        *,
        namespace: str,
        cycle: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> None:
        """Durably appends and fsyncs a decision-identity record BEFORE
        returning — callers MUST call this and have it return before the
        decision reaches REM-A authorization or execution (causal
        ordering, spec §4). Raises `DecisionIdentityError` (never silently
        substitutes a fallback identity) if `decision_id` is missing/blank
        — this is a fail-closed constructor, not a best-effort logger."""
        if not decision_id or not str(decision_id).strip():
            raise DecisionIdentityError(
                "decision_id is required to persist a decision identity — "
                "refusing to silently substitute a fresh/fallback value "
                "(O-02W-PRE-T1-E REM-B-R1.1, Blocker A)"
            )
        record = {
            "schema_version": SCHEMA_VERSION,
            "decision_id": str(decision_id).strip(),
            "namespace": str(namespace),
            "cycle": cycle,
            "symbol": symbol,
            "ts": time.time(),
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        with self._lock:
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as exc:
                raise DecisionIdentityError(
                    f"decision-identity journal write failed: {exc}"
                ) from exc

    def is_persisted(self, decision_id: str) -> bool:
        """Read-only membership check — replays the journal (same pattern
        as `OrderIntentJournal.latest_by_digest`) rather than maintaining
        a separate index, so restart/reconstruction always sees exactly
        what was durably written, nothing cached or stale."""
        if not decision_id:
            return False
        target = str(decision_id).strip()
        with self._lock:
            try:
                text = self._path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return False
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # Truncated/corrupt final line — tolerated, not fatal
                # (mirrors OrderIntentJournal's I5 durability contract).
                continue
            if rec.get("decision_id") == target:
                return True
        return False


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
