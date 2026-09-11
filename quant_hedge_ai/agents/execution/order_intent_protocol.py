"""
order_intent_protocol.py — Deterministic identity, durable intent journal,
and idempotent submission/reconciliation coordinator
(O-02W-PRE-T1-E REM-B, docs/adr/00XX-deterministic-durable-idempotent-order-submission.md).

Causal objective (verbatim from the mission spec): one logical order
intention can produce at most one exchange submission, remains attributable
across process restarts, and can never be blindly resubmitted after an
ambiguous network result.

Scope: H3 (deterministic identity), H4 (durable-before-network), H5
(reconciliation after ambiguity), H6 (duplicate-invocation idempotence), and
the submission-identity/ambiguity portions of H9.

Explicitly OUT OF SCOPE (reserved for REM-C): partial-fill lifecycle, full
position reconstruction, PnL accounting, broad crash recovery, any automatic
resubmission policy after RECONCILED_NOT_FOUND_PENDING.

This module never performs pre-network authorization itself — every caller
MUST already hold an authorized `OrderAuthorizationResult`
(order_authorization.py, REM-A) before building an intent here. REM-A remains
the sole authority for "may this be submitted at all"; this module answers
only "has this exact logical intent already been (attempted to be)
submitted, and if not, submit it exactly once."
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

SCHEMA_VERSION = 1
_CLIENT_ID_PREFIX = "reb"  # rem-b


# ─────────────────────────────────────────────────────────────────────────
# 1. Deterministic canonical intent + identity (I1, I2, H3)
# ─────────────────────────────────────────────────────────────────────────


class MissingCausalIdentityError(ValueError):
    """Raised when an upstream causal identifier required for uniqueness is
    absent. REM-B fails closed here rather than substituting wall-clock time
    or a random UUID (spec §6.7)."""


def _norm_decimal_str(value: Any) -> str:
    """Canonical, locale-independent decimal string. `None` stays a
    sentinel string distinct from any real number so it never collides with
    a numeric field."""
    if value is None:
        return "null"
    d = Decimal(str(value))
    # normalize() strips trailing zeros but can produce exponent notation
    # for integers (e.g. 1E+2) — force plain notation for stability.
    normalized = d.normalize()
    text = format(normalized, "f")
    if text in ("-0", "-0.0"):
        text = "0"
    return text


@dataclass(frozen=True)
class OrderIntent:
    """Versioned canonical logical order intent (spec §6).

    Only immutable causal/execution fields. No wall-clock time, PID, random
    UUID, retry count, mutable status, exchange response, or secrets.
    """

    schema_version: int
    namespace: str  # experiment/execution namespace, e.g. "EXP-001"
    causal_id: str  # decision_id / packet_id / position close-generation id
    account_scope: str  # exchange + account label, never a secret/key
    symbol: str
    side: str  # "buy" | "sell"
    order_type: str  # "market" | "limit" | ...
    amount: str  # normalized authorized amount (canonical decimal string)
    price: Optional[str]  # normalized limit/trigger price, or None
    reduce_only: bool
    position_ref: Optional[str] = None  # position/close-generation identity

    def canonical_dict(self) -> dict:
        """Fixed field order, explicit null representation, normalized
        decimal strings — the exact payload the digest is computed over."""
        return {
            "schema_version": self.schema_version,
            "namespace": self.namespace,
            "causal_id": self.causal_id,
            "account_scope": self.account_scope,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "amount": self.amount,
            "price": self.price if self.price is not None else "null",
            "reduce_only": bool(self.reduce_only),
            "position_ref": self.position_ref if self.position_ref is not None else "null",
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_dict(), sort_keys=False, separators=(",", ":")
        )

    def full_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def client_order_id(self, *, max_len: int = 32) -> str:
        """Exchange-safe deterministic client order ID: version prefix +
        deterministic digest fragment, alnum-only, bounded length (most
        ccxt-reachable exchanges cap clientOrderId around 32-36 chars)."""
        digest = self.full_digest()
        prefix = f"{_CLIENT_ID_PREFIX}{self.schema_version}"
        remaining = max_len - len(prefix)
        if remaining <= 8:
            remaining = 8
        frag = digest[:remaining]
        cid = f"{prefix}{frag}"
        return cid[:max_len]


def build_order_intent(
    *,
    namespace: str,
    causal_id: Optional[str],
    account_scope: str,
    symbol: str,
    side: str,
    order_type: str,
    amount: Any,
    price: Any = None,
    reduce_only: bool = False,
    position_ref: Optional[str] = None,
) -> OrderIntent:
    """The only supported constructor. Fails closed (raises
    MissingCausalIdentityError) if `causal_id` is missing/blank rather than
    silently substituting time or a random value (spec §6.7)."""
    if not causal_id or not str(causal_id).strip():
        raise MissingCausalIdentityError(
            "causal_id is required to derive a deterministic order intent "
            "identity — refusing to substitute wall-clock time or a random "
            "value (O-02W-PRE-T1-E REM-B, I1/I2)."
        )
    side_norm = str(side).strip().lower()
    if side_norm not in ("buy", "sell"):
        raise ValueError(f"unsupported side: {side!r}")
    return OrderIntent(
        schema_version=SCHEMA_VERSION,
        namespace=str(namespace),
        causal_id=str(causal_id).strip(),
        account_scope=str(account_scope),
        symbol=str(symbol),
        side=side_norm,
        order_type=str(order_type),
        amount=_norm_decimal_str(amount),
        price=_norm_decimal_str(price) if price is not None else None,
        reduce_only=bool(reduce_only),
        position_ref=str(position_ref) if position_ref is not None else None,
    )


# ─────────────────────────────────────────────────────────────────────────
# 2. State machine (spec §7)
# ─────────────────────────────────────────────────────────────────────────


class IntentState(str, Enum):
    INTENT_RECORDED = "INTENT_RECORDED"
    SUBMISSION_STARTED = "SUBMISSION_STARTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXPLICITLY_REJECTED = "EXPLICITLY_REJECTED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    RECONCILED_FOUND = "RECONCILED_FOUND"
    RECONCILED_NOT_FOUND_PENDING = "RECONCILED_NOT_FOUND_PENDING"
    CANCELLED = "CANCELLED"
    COLLISION = "COLLISION"  # I7 — not in spec vocabulary explicitly but
    # required to represent a fail-closed identity collision without
    # reusing a generic FAILED bucket.


# Allowed forward transitions. Anything not listed here is rejected by
# `OrderIntentJournal.append_transition` (I10 — no silent state confusion).
_ALLOWED_TRANSITIONS: dict[IntentState, set[IntentState]] = {
    IntentState.INTENT_RECORDED: {
        IntentState.SUBMISSION_STARTED,
    },
    IntentState.SUBMISSION_STARTED: {
        IntentState.ACKNOWLEDGED,
        IntentState.EXPLICITLY_REJECTED,
        IntentState.RECONCILE_REQUIRED,
    },
    IntentState.RECONCILE_REQUIRED: {
        IntentState.RECONCILED_FOUND,
        IntentState.RECONCILED_NOT_FOUND_PENDING,
        IntentState.RECONCILE_REQUIRED,  # repeated failed lookup — stays
        IntentState.COLLISION,
    },
    IntentState.RECONCILED_NOT_FOUND_PENDING: {
        IntentState.RECONCILED_FOUND,  # a later lookup can still find it
        IntentState.RECONCILED_NOT_FOUND_PENDING,
        IntentState.COLLISION,
    },
    IntentState.ACKNOWLEDGED: {IntentState.CANCELLED},
    IntentState.EXPLICITLY_REJECTED: set(),
    IntentState.RECONCILED_FOUND: {IntentState.CANCELLED},
    IntentState.CANCELLED: set(),
    IntentState.COLLISION: set(),
}


class InvalidTransitionError(RuntimeError):
    pass


# ─────────────────────────────────────────────────────────────────────────
# 3. Typed results (spec §12)
# ─────────────────────────────────────────────────────────────────────────


class SubmissionOutcome(str, Enum):
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    ALREADY_RECORDED = "ALREADY_RECORDED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXPLICITLY_REJECTED = "EXPLICITLY_REJECTED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    RECONCILED_FOUND = "RECONCILED_FOUND"
    RECONCILED_NOT_FOUND_PENDING = "RECONCILED_NOT_FOUND_PENDING"
    IDENTITY_COLLISION = "IDENTITY_COLLISION"
    JOURNAL_FAILURE = "JOURNAL_FAILURE"
    UNSUPPORTED_ADAPTER_CAPABILITY = "UNSUPPORTED_ADAPTER_CAPABILITY"


@dataclass(frozen=True)
class SubmissionResult:
    outcome: SubmissionOutcome
    intent_digest: str
    client_order_id: str
    state: Optional[IntentState]
    exchange_order_id: Optional[str] = None
    detail: str = ""
    raw_evidence: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────
# 4. Durable append-only journal (spec §7)
# ─────────────────────────────────────────────────────────────────────────


class OrderIntentJournal:
    """Minimal append-only JSONL durable authority.

    One record per line, never rewritten in place — history is reconstructed
    by replaying the file and keeping, per `intent_digest`, the last valid
    (fully-parseable) record. A truncated/corrupt final line is skipped, not
    fatal (I5/R5 — tolerate a truncated final record without corrupting
    prior valid records).

    Concurrency: a single `threading.Lock` per journal instance serializes
    all readers/writers inside one process. This is NOT a cross-process
    lock — production deployment of this repo runs one execution process at
    a time (single VPS `advisor_loop.py` writer, see CLAUDE.md stabilization
    window); this module does not claim more than that. A second process
    pointed at the same journal path must not be run concurrently — this is
    an explicit single-writer requirement, not silently assumed safe.
    """

    def __init__(self, path: str | os.PathLike):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self._path.exists():
            self._path.touch()

    @property
    def path(self) -> Path:
        return self._path

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
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Truncated/corrupt final line — skip, don't raise (I5).
                continue
        return records

    def latest_by_digest(self) -> dict[str, dict]:
        """Reconstructs current state per intent digest by replaying the
        journal in order (last valid record wins) — this is how restart
        idempotence (I6) is achieved: no separate index, the journal itself
        is the source of truth."""
        with self._lock:
            latest: dict[str, dict] = {}
            for rec in self._read_all_records():
                digest = rec.get("intent_digest")
                if not digest:
                    continue
                latest[digest] = rec
            return latest

    def get(self, intent_digest: str) -> Optional[dict]:
        return self.latest_by_digest().get(intent_digest)

    def find_by_client_order_id(self, client_order_id: str) -> Optional[dict]:
        for rec in self.latest_by_digest().values():
            if rec.get("client_order_id") == client_order_id:
                return rec
        return None

    def append_transition(
        self,
        *,
        intent_digest: str,
        client_order_id: str,
        state: IntentState,
        canonical_payload: Optional[dict] = None,
        causal_refs: Optional[dict] = None,
        authorization_ref: Optional[str] = None,
        attempt: int = 1,
        exchange_order_id: Optional[str] = None,
        error_category: Optional[str] = None,
        reconciliation_evidence: Optional[dict] = None,
    ) -> dict:
        """Appends one record and durably syncs before returning (I3 —
        durable-before-network callers MUST call this and have it return
        before making the network mutation call).

        Validates the transition against `_ALLOWED_TRANSITIONS` using the
        current latest record for this digest, if any (I10 — contradictory
        transitions are rejected, never silently written).
        """
        import time

        with self._lock:
            existing = self.get(intent_digest)
            if existing is not None:
                prev_state = IntentState(existing["state"])
                if state != prev_state and state not in _ALLOWED_TRANSITIONS.get(
                    prev_state, set()
                ):
                    raise InvalidTransitionError(
                        f"invalid transition {prev_state.value} -> {state.value} "
                        f"for intent {intent_digest}"
                    )
                if canonical_payload is None:
                    canonical_payload = existing.get("canonical_payload")
                if causal_refs is None:
                    causal_refs = existing.get("causal_refs")
                if authorization_ref is None:
                    authorization_ref = existing.get("authorization_ref")

            record = {
                "schema_version": SCHEMA_VERSION,
                "intent_digest": intent_digest,
                "client_order_id": client_order_id,
                "canonical_payload": canonical_payload,
                "causal_refs": causal_refs,
                "authorization_ref": authorization_ref,
                "state": state.value,
                "attempt": attempt,
                "ts": time.time(),
                "exchange_order_id": exchange_order_id,
                "error_category": error_category,
                "reconciliation_evidence": reconciliation_evidence,
            }
            line = json.dumps(
                record, sort_keys=True, separators=(",", ":"), default=str
            )
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
            return record


# ─────────────────────────────────────────────────────────────────────────
# 5. Adapter capability declaration (spec §9)
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AdapterCapabilities:
    supports_client_order_id: bool
    client_order_id_param: Optional[str]  # e.g. "clientOrderId", "newClientOrderId"
    supports_lookup_by_client_order_id: bool


class ExchangeMutationOutcome(str, Enum):
    """What the raw exchange call actually told us — the coordinator maps
    this to a `SubmissionOutcome`."""

    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXPLICITLY_REJECTED = "EXPLICITLY_REJECTED"
    AMBIGUOUS = "AMBIGUOUS"  # timeout / connection reset / lost response /
    # malformed or unknown response — anything that isn't a clean ack or a
    # clean explicit rejection.


@dataclass(frozen=True)
class ExchangeMutationResult:
    outcome: ExchangeMutationOutcome
    exchange_order_id: Optional[str] = None
    error_category: Optional[str] = None
    raw: Optional[dict] = None


@dataclass(frozen=True)
class ReconciliationLookupResult:
    """Read-only result of querying the exchange by deterministic identity
    (spec §10). `matches` holds zero, one, or more candidate order dicts."""

    lookup_failed: bool
    matches: list[dict] = field(default_factory=list)
    error_category: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────
# 6. Coordinator — submission protocol (spec §8) + reconciliation (spec §10)
# ─────────────────────────────────────────────────────────────────────────


class OrderIntentCoordinator:
    """Enforces the durable-before-network, at-most-once submission
    protocol for a single mutation family (ExecutionEngine or
    PositionManager). One coordinator per journal; callers share a journal
    instance (or point at the same path) across mutation families to get a
    single cross-family idempotence surface (I8).

    This class does NOT perform REM-A authorization — callers must pass an
    already-authorized intent (build_order_intent(...) + a truthy
    `authorized` flag from order_authorization.authorize_order()). If a
    caller passes `authorized=False`, this returns AUTHORIZATION_DENIED and
    performs zero mutation calls, zero journal writes (I9).
    """

    def __init__(
        self,
        journal: OrderIntentJournal,
        capabilities: AdapterCapabilities,
    ):
        self._journal = journal
        self._capabilities = capabilities
        # Per-digest locks so two threads racing on the SAME intent
        # serialize, while different intents don't block each other.
        self._locks_guard = threading.Lock()
        self._digest_locks: dict[str, threading.Lock] = {}

    def _lock_for(self, digest: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._digest_locks.get(digest)
            if lock is None:
                lock = threading.Lock()
                self._digest_locks[digest] = lock
            return lock

    def submit(
        self,
        intent: OrderIntent,
        *,
        authorized: bool,
        authorization_ref: str,
        mutate: Callable[[OrderIntent, str], ExchangeMutationResult],
    ) -> SubmissionResult:
        """`mutate(intent, client_order_id)` is called AT MOST ONCE per
        logical intent, and only after SUBMISSION_STARTED is durably
        persisted (I3, I4). It must perform exactly one exchange mutation
        call and translate the raw result into an `ExchangeMutationResult`.
        """
        digest = intent.full_digest()
        client_order_id = intent.client_order_id()

        if not authorized:
            return SubmissionResult(
                outcome=SubmissionOutcome.AUTHORIZATION_DENIED,
                intent_digest=digest,
                client_order_id=client_order_id,
                state=None,
                detail="caller-supplied authorization was False; zero mutation calls",
            )

        if not self._capabilities.supports_client_order_id:
            return SubmissionResult(
                outcome=SubmissionOutcome.UNSUPPORTED_ADAPTER_CAPABILITY,
                intent_digest=digest,
                client_order_id=client_order_id,
                state=None,
                detail="adapter does not support a deterministic client order id",
            )

        with self._lock_for(digest):
            # I7 — collision detection: a different canonical payload
            # already recorded under this client_order_id but a DIFFERENT
            # digest is a fail-closed condition, checked before anything
            # else so a partial digest space clash can never proceed.
            existing_by_cid = self._journal.find_by_client_order_id(client_order_id)
            if existing_by_cid is not None and existing_by_cid.get("intent_digest") != digest:
                return SubmissionResult(
                    outcome=SubmissionOutcome.IDENTITY_COLLISION,
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.COLLISION,
                    detail=(
                        "client_order_id collision with a different canonical "
                        "payload — refusing to treat as the same order"
                    ),
                )

            existing = self._journal.get(digest)
            if existing is not None:
                return self._typed_result_from_record(existing, digest, client_order_id)

            try:
                self._journal.append_transition(
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.INTENT_RECORDED,
                    canonical_payload=intent.canonical_dict(),
                    causal_refs={
                        "namespace": intent.namespace,
                        "causal_id": intent.causal_id,
                        "position_ref": intent.position_ref,
                    },
                    authorization_ref=authorization_ref,
                )
            except Exception as exc:  # journal I/O failure — zero mutation calls
                return SubmissionResult(
                    outcome=SubmissionOutcome.JOURNAL_FAILURE,
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=None,
                    detail=f"journal write failed before any mutation: {exc}",
                )

            try:
                self._journal.append_transition(
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.SUBMISSION_STARTED,
                )
            except Exception as exc:
                return SubmissionResult(
                    outcome=SubmissionOutcome.JOURNAL_FAILURE,
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=None,
                    detail=f"journal write failed before mutation: {exc}",
                )

            # ── exactly one exchange mutation call ──────────────────────
            mutation = mutate(intent, client_order_id)

            if mutation.outcome == ExchangeMutationOutcome.ACKNOWLEDGED:
                self._journal.append_transition(
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.ACKNOWLEDGED,
                    exchange_order_id=mutation.exchange_order_id,
                )
                return SubmissionResult(
                    outcome=SubmissionOutcome.ACKNOWLEDGED,
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.ACKNOWLEDGED,
                    exchange_order_id=mutation.exchange_order_id,
                    raw_evidence=mutation.raw,
                    detail="exchange acknowledged submission",
                )
            elif mutation.outcome == ExchangeMutationOutcome.EXPLICITLY_REJECTED:
                self._journal.append_transition(
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.EXPLICITLY_REJECTED,
                    error_category=mutation.error_category,
                )
                return SubmissionResult(
                    outcome=SubmissionOutcome.EXPLICITLY_REJECTED,
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.EXPLICITLY_REJECTED,
                    raw_evidence=mutation.raw,
                    detail=mutation.error_category or "explicit exchange rejection",
                )
            else:  # AMBIGUOUS — never retried automatically (I5)
                self._journal.append_transition(
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.RECONCILE_REQUIRED,
                    error_category=mutation.error_category,
                )
                return SubmissionResult(
                    outcome=SubmissionOutcome.RECONCILE_REQUIRED,
                    intent_digest=digest,
                    client_order_id=client_order_id,
                    state=IntentState.RECONCILE_REQUIRED,
                    raw_evidence=mutation.raw,
                    detail=mutation.error_category or "ambiguous exchange result",
                )

    def _typed_result_from_record(
        self, record: dict, digest: str, client_order_id: str
    ) -> SubmissionResult:
        state = IntentState(record["state"])
        mapping = {
            IntentState.INTENT_RECORDED: SubmissionOutcome.ALREADY_RECORDED,
            IntentState.SUBMISSION_STARTED: SubmissionOutcome.ALREADY_RECORDED,
            IntentState.ACKNOWLEDGED: SubmissionOutcome.ACKNOWLEDGED,
            IntentState.EXPLICITLY_REJECTED: SubmissionOutcome.EXPLICITLY_REJECTED,
            IntentState.RECONCILE_REQUIRED: SubmissionOutcome.RECONCILE_REQUIRED,
            IntentState.RECONCILED_FOUND: SubmissionOutcome.RECONCILED_FOUND,
            IntentState.RECONCILED_NOT_FOUND_PENDING: (
                SubmissionOutcome.RECONCILED_NOT_FOUND_PENDING
            ),
            IntentState.COLLISION: SubmissionOutcome.IDENTITY_COLLISION,
            IntentState.CANCELLED: SubmissionOutcome.ALREADY_RECORDED,
        }
        return SubmissionResult(
            outcome=mapping.get(state, SubmissionOutcome.ALREADY_RECORDED),
            intent_digest=digest,
            client_order_id=client_order_id,
            state=state,
            exchange_order_id=record.get("exchange_order_id"),
            detail="duplicate invocation — returning existing recorded state, no re-submission",
        )

    # ── Reconciliation (spec §10) — read-only w.r.t. order creation ────────

    def reconcile(
        self,
        intent_digest: str,
        *,
        lookup: Callable[[str], ReconciliationLookupResult],
        verify_match: Optional[Callable[[dict, dict], bool]] = None,
    ) -> SubmissionResult:
        with self._lock_for(intent_digest):
            record = self._journal.get(intent_digest)
            if record is None:
                return SubmissionResult(
                    outcome=SubmissionOutcome.JOURNAL_FAILURE,
                    intent_digest=intent_digest,
                    client_order_id="",
                    state=None,
                    detail="no journal record for this digest — cannot reconcile",
                )
            state = IntentState(record["state"])
            client_order_id = record["client_order_id"]
            if state not in (
                IntentState.RECONCILE_REQUIRED,
                IntentState.RECONCILED_NOT_FOUND_PENDING,
            ):
                return self._typed_result_from_record(record, intent_digest, client_order_id)

            result = lookup(client_order_id)

            if result.lookup_failed:
                # Remain RECONCILE_REQUIRED — record the read failure, no mutation.
                self._journal.append_transition(
                    intent_digest=intent_digest,
                    client_order_id=client_order_id,
                    state=IntentState.RECONCILE_REQUIRED,
                    error_category="reconciliation_lookup_failed",
                )
                return SubmissionResult(
                    outcome=SubmissionOutcome.RECONCILE_REQUIRED,
                    intent_digest=intent_digest,
                    client_order_id=client_order_id,
                    state=IntentState.RECONCILE_REQUIRED,
                    detail="reconciliation lookup failed — remaining ambiguous",
                )

            if len(result.matches) == 0:
                self._journal.append_transition(
                    intent_digest=intent_digest,
                    client_order_id=client_order_id,
                    state=IntentState.RECONCILED_NOT_FOUND_PENDING,
                )
                return SubmissionResult(
                    outcome=SubmissionOutcome.RECONCILED_NOT_FOUND_PENDING,
                    intent_digest=intent_digest,
                    client_order_id=client_order_id,
                    state=IntentState.RECONCILED_NOT_FOUND_PENDING,
                    detail="no matching exchange order found — remains ambiguous, no resubmission",
                )

            if len(result.matches) > 1:
                self._journal.append_transition(
                    intent_digest=intent_digest,
                    client_order_id=client_order_id,
                    state=IntentState.COLLISION,
                    error_category="multiple_reconciliation_matches",
                    reconciliation_evidence={"matches": result.matches},
                )
                return SubmissionResult(
                    outcome=SubmissionOutcome.IDENTITY_COLLISION,
                    intent_digest=intent_digest,
                    client_order_id=client_order_id,
                    state=IntentState.COLLISION,
                    detail="multiple exchange orders matched deterministic identity — fail closed",
                )

            candidate = result.matches[0]
            canonical_payload = record.get("canonical_payload") or {}
            compatible = True
            if verify_match is not None:
                compatible = verify_match(canonical_payload, candidate)
            if not compatible:
                self._journal.append_transition(
                    intent_digest=intent_digest,
                    client_order_id=client_order_id,
                    state=IntentState.COLLISION,
                    error_category="reconciliation_payload_mismatch",
                    reconciliation_evidence={"candidate": candidate},
                )
                return SubmissionResult(
                    outcome=SubmissionOutcome.IDENTITY_COLLISION,
                    intent_digest=intent_digest,
                    client_order_id=client_order_id,
                    state=IntentState.COLLISION,
                    detail="matched order's payload is incompatible with authorized intent",
                )

            exchange_order_id = candidate.get("id") or candidate.get("order_id")
            self._journal.append_transition(
                intent_digest=intent_digest,
                client_order_id=client_order_id,
                state=IntentState.RECONCILED_FOUND,
                exchange_order_id=exchange_order_id,
                reconciliation_evidence={"candidate": candidate},
            )
            return SubmissionResult(
                outcome=SubmissionOutcome.RECONCILED_FOUND,
                intent_digest=intent_digest,
                client_order_id=client_order_id,
                state=IntentState.RECONCILED_FOUND,
                exchange_order_id=exchange_order_id,
                raw_evidence={"candidate": candidate},
                detail="reconciled — found exactly one matching exchange order",
            )
