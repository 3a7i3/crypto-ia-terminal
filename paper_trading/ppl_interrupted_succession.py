"""PPL-SUCCESSION-01 — succession after an interrupted, documentarily closed epoch.

Contract: docs/contracts/PPL_SUCCESSION_01_INTERRUPTED_PREDECESSOR.md.

This module is a distinct, versioned path.  It does NOT relax the normal
rotation gate (``EpochRotationQuiescence`` and the existing builders are
untouched).  It never turns an UNKNOWN into a number, never transfers capital,
and never accepts a boolean or a URL in place of verifiable bytes.

Nothing here starts a process, touches a network, reads ``PB_MAX_POSITIONS`` or
creates a real epoch.  All inputs are caller supplied bytes / explicit paths.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ledger_events import LedgerEventType
from paper_trading.paper_portfolio_ledger import project
from paper_trading.ppl_authority_runtime import (
    _SUCCESSOR_EPOCH_ROLE,
    _SUCCESSOR_MANIFEST_SCHEMA_VERSION,
    AuthorityEpochManifest,
    AuthorityManifestError,
    authority_manifest_sha256,
)

SUCCESSION_CONTRACT_VERSION = "PPL-SUCCESSION-INTERRUPTED-V1"
DECISION_SCHEMA = "PPL-SUCCESSION-OPERATOR-DECISION-V1"
DECISION_KIND = "INTERRUPTED_EXPERIMENT_DOCUMENTARY_CLOSURE"
CAPITAL_DECISION_SCHEMA = "PPL-SUCCESSION-CAPITAL-DECISION-V1"
CAPITAL_PROVENANCE_KIND = "OPERATOR_DECLARED_NOMINAL"
EXCLUSIVITY_SCHEMA = "PPL-SUCCESSION-EXCLUSIVITY-PROOF-V1"
UNKNOWN = "UNKNOWN"
FIN_STATUS_UNRESOLVED = "UNRESOLVED"
CAPITAL_TRANSFER_NONE = "NONE"

REQUIRED_EVIDENCE_ROLES = (
    "closure_dossier",
    "approved_archive",
    "closure_comment_body",
)
REQUIRED_EXCLUSIVITY_OBSERVATIONS = (
    "no_process_on_predecessor_store",
    "no_open_descriptor_on_predecessor_store",
    "no_store_lock_held",
    "former_host_stopped_control_plane",
    "successor_store_empty_or_absent",
    "no_environment_references_predecessor",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SuccessionRefusal(AuthorityManifestError):
    """The interrupted-predecessor succession path refuses the supplied proof."""


# ---------------------------------------------------------------- utilities


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.match(value))


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-finite JSON constant {name}")


def _load_object(raw: Any, what: str) -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise SuccessionRefusal(f"{what}: bytes are required (no flag, no URL)")
    try:
        value = json.loads(
            bytes(raw).decode("utf-8"),
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise SuccessionRefusal(f"{what}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SuccessionRefusal(f"{what}: JSON object required")
    return value


def _exact_fields(obj: Mapping[str, Any], expected: set[str], what: str) -> None:
    if set(obj) != expected:
        missing = sorted(expected - set(obj))
        extra = sorted(set(obj) - expected)
        raise SuccessionRefusal(
            f"{what}: fields mismatch (missing={missing}, unexpected={extra})"
        )


def _real_number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SuccessionRefusal(f"{what}: number required")
    number = float(value)
    if not math.isfinite(number):
        raise SuccessionRefusal(f"{what}: finite number required")
    return number


def _nonempty_str(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SuccessionRefusal(f"{what}: non-empty string required")
    return value


# ------------------------------------------------------------- the ledger


def _replay_predecessor_ledger(ledger_bytes: Any, epoch_id: str):
    if not isinstance(ledger_bytes, (bytes, bytearray)) or not ledger_bytes:
        raise SuccessionRefusal("predecessor ledger: bytes are required")
    raw = bytes(ledger_bytes)
    try:
        with tempfile.TemporaryDirectory(prefix="succession-ledger-") as tmp:
            store = DurableEventStore(tmp)
            store._ensure_directories()
            path = store._epoch_path(epoch_id)
            path.write_bytes(raw)
            events = store.load_epoch(epoch_id)
        state = project(events)
    except SuccessionRefusal:
        raise
    except Exception as exc:  # corruption, gaps, wrong epoch, bad payloads
        raise SuccessionRefusal(f"predecessor ledger failed replay: {exc}") from exc
    if state.paper_epoch_id != epoch_id:
        raise SuccessionRefusal("predecessor ledger epoch id mismatch")
    return events, state


# ------------------------------------------------------------ the record


@dataclass(frozen=True)
class InterruptedSuccessionRecord:
    contract_version: str
    predecessor_paper_epoch_id: str
    predecessor_dataset_id: str
    predecessor_ledger_sha256: str
    predecessor_event_count: int
    predecessor_last_sequence: int
    predecessor_opened_count: int
    predecessor_closed_count: int
    predecessor_unresolved_count: int
    predecessor_open_positions: int
    predecessor_unresolved_capital: float
    pending_order_count: str
    lifecycle_transitions_in_flight: str
    fin_status: str
    certified_equity: None
    operator_decision_sha256: str
    dataset_manifest_sha256: str
    dataset_tree_sha256: str
    evidence_sha256: tuple[tuple[str, str], ...]
    successor_paper_epoch_id: str
    successor_initial_virtual_capital: float
    capital_provenance_kind: str
    capital_decision_sha256: str
    predecessor_unresolved_capital_transfer: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "predecessor_paper_epoch_id": self.predecessor_paper_epoch_id,
            "predecessor_dataset_id": self.predecessor_dataset_id,
            "predecessor_ledger_sha256": self.predecessor_ledger_sha256,
            "predecessor_event_count": self.predecessor_event_count,
            "predecessor_last_sequence": self.predecessor_last_sequence,
            "predecessor_opened_count": self.predecessor_opened_count,
            "predecessor_closed_count": self.predecessor_closed_count,
            "predecessor_unresolved_count": self.predecessor_unresolved_count,
            "predecessor_open_positions": self.predecessor_open_positions,
            "predecessor_unresolved_capital": self.predecessor_unresolved_capital,
            "pending_order_count": self.pending_order_count,
            "lifecycle_transitions_in_flight": self.lifecycle_transitions_in_flight,
            "fin_status": self.fin_status,
            "certified_equity": self.certified_equity,
            "operator_decision_sha256": self.operator_decision_sha256,
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "dataset_tree_sha256": self.dataset_tree_sha256,
            "evidence_sha256": dict(self.evidence_sha256),
            "successor_paper_epoch_id": self.successor_paper_epoch_id,
            "successor_initial_virtual_capital": self.successor_initial_virtual_capital,
            "capital_provenance_kind": self.capital_provenance_kind,
            "capital_decision_sha256": self.capital_decision_sha256,
            "predecessor_unresolved_capital_transfer": (
                self.predecessor_unresolved_capital_transfer
            ),
        }

    @property
    def record_sha256(self) -> str:
        return _sha256(_canonical(self.as_dict()))


def _validate_native_dataset(
    dataset_files: Any,
    *,
    declared_dataset_id: str,
    predecessor_epoch: str,
    ledger_bytes: bytes,
) -> tuple[bytes, str]:
    """Run the *native* burn-in dataset validator on the supplied tree.

    ``dataset_files`` maps relative paths (``manifest.json``,
    ``authoritative/ppl_events.jsonl`` ...) to bytes: a verbatim copy of an
    export produced by ``research_data.paper_exporter``.  The tree is
    materialised in a private temporary directory named after its dataset id
    and checked by ``research_data.burn_in_finalization._validate_dataset``
    (schema/version, provenance, identity, boundary fingerprint, component
    digests, authoritative manifest/config copies).  Documents that merely agree
    with their own hashes are refused by that validator.  Returns the manifest
    bytes and a digest of the whole tree.
    """

    if not isinstance(dataset_files, Mapping) or not dataset_files:
        raise SuccessionRefusal("dataset files: a non-empty path->bytes mapping is required")
    clean: dict[str, bytes] = {}
    for rel, raw in dataset_files.items():
        parts = Path(rel).parts if isinstance(rel, str) else ()
        if (
            not parts
            or Path(rel).is_absolute()
            or any(part in ("", ".", "..") for part in parts)
            or "\\" in rel
        ):
            raise SuccessionRefusal(f"dataset files: unsafe path {rel!r}")
        if not isinstance(raw, (bytes, bytearray)):
            raise SuccessionRefusal(f"dataset file {rel}: bytes are required")
        clean["/".join(parts)] = bytes(raw)
    manifest_raw = clean.get("manifest.json")
    ppl_raw = clean.get("authoritative/ppl_events.jsonl")
    if not manifest_raw or ppl_raw is None:
        raise SuccessionRefusal("dataset files: manifest.json and the ledger are required")
    manifest = _load_object(manifest_raw, "dataset manifest")
    dataset_id = manifest.get("dataset_id")
    if not _is_sha256(dataset_id) or dataset_id != declared_dataset_id:
        raise SuccessionRefusal("dataset manifest dataset_id differs from the decision")
    if manifest.get("paper_epoch_id") != predecessor_epoch:
        raise SuccessionRefusal("dataset manifest epoch differs from the decision")
    if ppl_raw != bytes(ledger_bytes):
        raise SuccessionRefusal("dataset ledger bytes differ from the supplied ledger")

    from research_data.burn_in_finalization import (
        BurnInDatasetValidationError,
        _validate_dataset,
    )

    try:
        with tempfile.TemporaryDirectory(prefix="succession-dataset-") as tmp:
            root = Path(tmp) / dataset_id
            for rel, raw in clean.items():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            _validate_dataset(root)
    except BurnInDatasetValidationError as exc:
        raise SuccessionRefusal(f"dataset is not a valid native export: {exc}") from exc
    except SuccessionRefusal:
        raise
    except Exception as exc:  # any malformed document must refuse, never pass
        raise SuccessionRefusal(f"dataset native validation failed: {exc}") from exc
    tree = sorted((rel, _sha256(raw)) for rel, raw in clean.items())
    return manifest_raw, _sha256(_canonical(tree))


_DECISION_FIELDS = {
    "schema",
    "decision_kind",
    "predecessor_paper_epoch_id",
    "predecessor_ledger_sha256",
    "predecessor_dataset_id",
    "predecessor_event_count",
    "acknowledged_unknowns",
    "fin_status",
    "certified_equity",
    "unresolved_capital",
    "evidence_sha256",
    "decided_by",
    "decided_at_utc",
}
_UNKNOWN_FIELDS = {"pending_order_count", "lifecycle_transitions_in_flight"}


def verify_interruption_evidence(
    *,
    ledger_bytes: bytes,
    dataset_files: Mapping[str, bytes],
    operator_decision_bytes: bytes,
    evidence_artifacts: Mapping[str, bytes],
    successor_paper_epoch_id: str,
    capital_decision_bytes: bytes,
) -> InterruptedSuccessionRecord:
    """Verify every byte-level proof and build the immutable succession record.

    Every check refuses; nothing is repaired, defaulted or inferred.
    """

    decision = _load_object(operator_decision_bytes, "operator decision")
    _exact_fields(decision, _DECISION_FIELDS, "operator decision")
    if decision["schema"] != DECISION_SCHEMA:
        raise SuccessionRefusal("operator decision: unsupported schema")
    if decision["decision_kind"] != DECISION_KIND:
        raise SuccessionRefusal("operator decision: unsupported decision_kind")
    predecessor_epoch = _nonempty_str(
        decision["predecessor_paper_epoch_id"], "decision predecessor epoch"
    )
    _nonempty_str(decision["decided_by"], "decision decided_by")
    _nonempty_str(decision["decided_at_utc"], "decision decided_at_utc")
    if not _is_sha256(decision["predecessor_ledger_sha256"]):
        raise SuccessionRefusal("decision predecessor_ledger_sha256 invalid")
    if not _is_sha256(decision["predecessor_dataset_id"]):
        raise SuccessionRefusal("decision predecessor_dataset_id invalid")

    # UNKNOWN stays UNKNOWN: a number (even 0), None or a flag is refused here.
    unknowns = decision["acknowledged_unknowns"]
    if not isinstance(unknowns, dict) or set(unknowns) != _UNKNOWN_FIELDS:
        raise SuccessionRefusal("decision acknowledged_unknowns fields mismatch")
    for name in sorted(_UNKNOWN_FIELDS):
        value = unknowns[name]
        if not isinstance(value, str) or value != UNKNOWN:
            raise SuccessionRefusal(
                f"{name} must be the literal {UNKNOWN!r}; a measured or "
                "substituted value belongs to the normal quiescence gate"
            )
    if decision["fin_status"] != FIN_STATUS_UNRESOLVED:
        raise SuccessionRefusal("decision fin_status must be UNRESOLVED")
    if decision["certified_equity"] is not None:
        raise SuccessionRefusal("decision certified_equity must be null")
    claimed_unresolved_capital = _real_number(
        decision["unresolved_capital"], "decision unresolved_capital"
    )
    claimed_count = decision["predecessor_event_count"]
    if isinstance(claimed_count, bool) or not isinstance(claimed_count, int):
        raise SuccessionRefusal("decision predecessor_event_count must be an integer")

    # Ledger: bytes -> hash -> authoritative replay.
    ledger_sha = _sha256(bytes(ledger_bytes)) if isinstance(
        ledger_bytes, (bytes, bytearray)
    ) and ledger_bytes else ""
    if not ledger_sha:
        raise SuccessionRefusal("predecessor ledger: bytes are required")
    if ledger_sha != decision["predecessor_ledger_sha256"]:
        raise SuccessionRefusal("predecessor ledger hash differs from the decision")
    events, state = _replay_predecessor_ledger(ledger_bytes, predecessor_epoch)
    counts = {event_type: 0 for event_type in LedgerEventType}
    for event in events:
        counts[event.event_type] += 1
    if len(events) != claimed_count:
        raise SuccessionRefusal("decision event count differs from the ledger")
    if len(state.open_positions) != 0:
        raise SuccessionRefusal("predecessor ledger still has open positions")
    unresolved_capital = float(state.unresolved_capital)
    if unresolved_capital <= 0 or len(state.unresolved_positions) == 0:
        raise SuccessionRefusal(
            "this path represents an interrupted predecessor with unresolved "
            "positions; a clean predecessor uses the normal rotation gate"
        )
    if claimed_unresolved_capital != unresolved_capital:
        raise SuccessionRefusal(
            "decision unresolved_capital differs from the replayed ledger"
        )

    # Dataset: the native validator of the exporter's own contract.
    dataset_manifest_raw, dataset_tree_sha = _validate_native_dataset(
        dataset_files,
        declared_dataset_id=decision["predecessor_dataset_id"],
        predecessor_epoch=predecessor_epoch,
        ledger_bytes=bytes(ledger_bytes),
    )

    # Evidence artifacts: bytes whose sha256 equals the decision's citation.
    cited = decision["evidence_sha256"]
    if not isinstance(cited, dict) or set(cited) != set(REQUIRED_EVIDENCE_ROLES):
        raise SuccessionRefusal("decision evidence_sha256 roles mismatch")
    if not isinstance(evidence_artifacts, Mapping) or set(evidence_artifacts) != set(
        REQUIRED_EVIDENCE_ROLES
    ):
        raise SuccessionRefusal("evidence artifacts roles mismatch (bytes required)")
    for role in REQUIRED_EVIDENCE_ROLES:
        artifact = evidence_artifacts[role]
        if not isinstance(artifact, (bytes, bytearray)) or not artifact:
            raise SuccessionRefusal(f"evidence {role}: bytes are required")
        if not _is_sha256(cited[role]) or _sha256(bytes(artifact)) != cited[role]:
            raise SuccessionRefusal(f"evidence {role}: sha256 does not match")

    # Successor identity and capital: declared by the operator, never inherited.
    successor_epoch = _nonempty_str(successor_paper_epoch_id, "successor epoch id")
    if successor_epoch == predecessor_epoch:
        raise SuccessionRefusal("successor epoch must differ from the predecessor")
    capital_doc = _load_object(capital_decision_bytes, "capital decision")
    _exact_fields(
        capital_doc,
        {
            "schema",
            "successor_paper_epoch_id",
            "initial_virtual_capital",
            "provenance",
            "decided_by",
            "decided_at_utc",
        },
        "capital decision",
    )
    if capital_doc["schema"] != CAPITAL_DECISION_SCHEMA:
        raise SuccessionRefusal("capital decision: unsupported schema")
    if capital_doc["provenance"] != CAPITAL_PROVENANCE_KIND:
        raise SuccessionRefusal(
            "capital provenance must be OPERATOR_DECLARED_NOMINAL; predecessor "
            "cash/equity, wallet and API balances are refused"
        )
    if capital_doc["successor_paper_epoch_id"] != successor_epoch:
        raise SuccessionRefusal("capital decision targets another successor epoch")
    _nonempty_str(capital_doc["decided_by"], "capital decided_by")
    _nonempty_str(capital_doc["decided_at_utc"], "capital decided_at_utc")
    capital = _real_number(
        capital_doc["initial_virtual_capital"], "capital initial_virtual_capital"
    )
    if capital <= 0:
        raise SuccessionRefusal("initial_virtual_capital must be > 0")

    return InterruptedSuccessionRecord(
        contract_version=SUCCESSION_CONTRACT_VERSION,
        predecessor_paper_epoch_id=predecessor_epoch,
        predecessor_dataset_id=decision["predecessor_dataset_id"],
        predecessor_ledger_sha256=ledger_sha,
        predecessor_event_count=len(events),
        predecessor_last_sequence=int(events[-1].sequence),
        predecessor_opened_count=counts[LedgerEventType.POSITION_OPENED],
        predecessor_closed_count=counts[LedgerEventType.POSITION_CLOSED],
        predecessor_unresolved_count=counts[LedgerEventType.POSITION_UNRESOLVED],
        predecessor_open_positions=0,
        predecessor_unresolved_capital=unresolved_capital,
        pending_order_count=UNKNOWN,
        lifecycle_transitions_in_flight=UNKNOWN,
        fin_status=FIN_STATUS_UNRESOLVED,
        certified_equity=None,
        operator_decision_sha256=_sha256(bytes(operator_decision_bytes)),
        dataset_manifest_sha256=_sha256(dataset_manifest_raw),
        dataset_tree_sha256=dataset_tree_sha,
        evidence_sha256=tuple(sorted((r, cited[r]) for r in REQUIRED_EVIDENCE_ROLES)),
        successor_paper_epoch_id=successor_epoch,
        successor_initial_virtual_capital=capital,
        capital_provenance_kind=CAPITAL_PROVENANCE_KIND,
        capital_decision_sha256=_sha256(bytes(capital_decision_bytes)),
        predecessor_unresolved_capital_transfer=CAPITAL_TRANSFER_NONE,
    )


def build_interrupted_successor_manifest(
    *,
    record: InterruptedSuccessionRecord,
    created_at: float,
    code_sha: str,
    config_snapshot_hash: str,
) -> AuthorityEpochManifest:
    """Build the v4 successor manifest.  Existing builders are not involved.

    ``legacy_boundary_sha256``/``legacy_event_count`` carry the predecessor
    ledger fingerprint as a *reference only*; no predecessor event is imported.
    """

    if not isinstance(record, InterruptedSuccessionRecord):
        raise SuccessionRefusal("a verified InterruptedSuccessionRecord is required")
    return AuthorityEpochManifest(
        paper_epoch_id=record.successor_paper_epoch_id,
        created_at=created_at,
        initial_virtual_capital=record.successor_initial_virtual_capital,
        code_sha=code_sha,
        config_snapshot_hash=config_snapshot_hash,
        legacy_boundary_sha256=record.predecessor_ledger_sha256,
        legacy_event_count=record.predecessor_event_count,
        predecessor_authority_epoch_id=record.predecessor_paper_epoch_id,
        epoch_role=_SUCCESSOR_EPOCH_ROLE,
        manifest_schema_version=_SUCCESSOR_MANIFEST_SCHEMA_VERSION,
        interruption_succession_sha256=record.record_sha256,
    )


def verify_manifest_matches_record(
    manifest: AuthorityEpochManifest, record: InterruptedSuccessionRecord
) -> None:
    expected = build_interrupted_successor_manifest(
        record=record,
        created_at=manifest.created_at,
        code_sha=manifest.code_sha,
        config_snapshot_hash=manifest.config_snapshot_hash,
    )
    if expected != manifest:
        raise SuccessionRefusal("manifest does not match the succession record")


# ----------------------------------------------------- exclusivity / clearance


# Process-local key: a clearance can only be minted by ``issue_activation_
# clearance`` in this process.  It is never serialised, so a clearance cannot be
# reconstructed from fields, copied across processes or forged by duck typing.
_SEAL_KEY = secrets.token_bytes(32)

DEFAULT_CLEARANCE_MAX_AGE_S = 900.0
PURPOSE_BOOTSTRAP = "BOOTSTRAP"
PURPOSE_RESUME = "RESUME"


def _clearance_seal(
    *,
    paper_epoch_id: str,
    manifest_sha256: str,
    record_sha256: str,
    exclusivity_proof_sha256: str,
    successor_store_root: str,
    purpose: str,
    issued_at: float,
    max_age_s: float,
) -> str:
    raw = json.dumps(
        [
            "ACTIVATION-CLEARANCE-V2",
            paper_epoch_id,
            manifest_sha256,
            record_sha256,
            exclusivity_proof_sha256,
            successor_store_root,
            purpose,
            repr(float(issued_at)),
            repr(float(max_age_s)),
        ],
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hmac.new(_SEAL_KEY, raw, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ActivationClearance:
    """Result of the separate exclusivity proof, bound to epoch, manifest bytes,
    record, successor store root and a freshness policy.  ``seal`` authenticates
    all of them; use ``validate_clearance_for_use`` at the point of use."""

    paper_epoch_id: str
    manifest_sha256: str
    record_sha256: str
    exclusivity_proof_sha256: str
    successor_store_root: str
    purpose: str
    issued_at: float
    max_age_s: float
    seal: str = field(default="", repr=False)


def _authentic(clearance: object) -> ActivationClearance:
    if not isinstance(clearance, ActivationClearance):
        raise SuccessionRefusal("activation clearance: not an issued clearance")
    for name in (
        "paper_epoch_id",
        "manifest_sha256",
        "record_sha256",
        "exclusivity_proof_sha256",
        "successor_store_root",
        "purpose",
        "seal",
    ):
        if not isinstance(getattr(clearance, name), str) or not getattr(clearance, name):
            raise SuccessionRefusal(f"activation clearance: invalid {name}")
    for name in ("issued_at", "max_age_s"):
        value = getattr(clearance, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SuccessionRefusal(f"activation clearance: invalid {name}")
        if not math.isfinite(value):
            raise SuccessionRefusal(f"activation clearance: invalid {name}")
    if clearance.max_age_s <= 0:
        raise SuccessionRefusal("activation clearance: invalid max_age_s")
    expected = _clearance_seal(
        paper_epoch_id=clearance.paper_epoch_id,
        manifest_sha256=clearance.manifest_sha256,
        record_sha256=clearance.record_sha256,
        exclusivity_proof_sha256=clearance.exclusivity_proof_sha256,
        successor_store_root=clearance.successor_store_root,
        purpose=clearance.purpose,
        issued_at=clearance.issued_at,
        max_age_s=clearance.max_age_s,
    )
    if clearance.purpose not in (PURPOSE_BOOTSTRAP, PURPOSE_RESUME):
        raise SuccessionRefusal("activation clearance: invalid purpose")
    if not hmac.compare_digest(expected, clearance.seal):
        raise SuccessionRefusal("activation clearance: seal does not verify")
    return clearance


def validate_clearance_for_use(
    clearance: object,
    *,
    manifest: AuthorityEpochManifest,
    store_root: str | Path,
    now: float,
    resume: bool,
) -> ActivationClearance:
    """Validate a clearance where it is consumed; raises ``SuccessionRefusal``.

    Policy (explicit):
    * both purposes need an authentic clearance bound to this manifest bytes,
      record and successor store root, and fresh
      (``0 <= now - issued_at <= max_age_s``);
    * ``resume=False`` (first bootstrap) needs a ``BOOTSTRAP`` clearance and a
      successor store that holds no ledger yet;
    * ``resume=True`` (restart in a new process) needs a ``RESUME`` clearance,
      issued by ``issue_resume_clearance`` from fresh observations in *that*
      process; the birth event is verified by the caller and never recreated.
    A bootstrap clearance cannot authorise a resume and vice versa.
    """

    c = _authentic(clearance)
    if manifest.epoch_role != _SUCCESSOR_EPOCH_ROLE:
        raise SuccessionRefusal("clearance is only meaningful for the successor role")
    if (
        c.paper_epoch_id != manifest.paper_epoch_id
        or c.manifest_sha256 != authority_manifest_sha256(manifest)
        or c.record_sha256 != manifest.interruption_succession_sha256
    ):
        raise SuccessionRefusal("activation clearance is bound to another epoch/manifest/record")
    root = _resolve_root(store_root, "store root")
    if c.successor_store_root != str(root):
        raise SuccessionRefusal("activation clearance is bound to another store root")
    current = _real_number(now, "now")
    if c.purpose != (PURPOSE_RESUME if resume else PURPOSE_BOOTSTRAP):
        raise SuccessionRefusal("activation clearance has another purpose")
    age = current - c.issued_at
    if age < 0 or age > c.max_age_s:
        raise SuccessionRefusal("activation clearance is stale or from the future")
    if not resume and root.exists() and (not root.is_dir() or any(root.rglob("*.jsonl"))):
        raise SuccessionRefusal("successor store is not empty at bootstrap")
    return c


def _resolve_root(path: Any, what: str) -> Path:
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise SuccessionRefusal(f"{what}: path required")
    raw = Path(path)
    if raw.is_symlink():
        raise SuccessionRefusal(f"{what}: symbolic link refused")
    return raw.resolve()


def _verify_birth(manifest: AuthorityEpochManifest, successor_root: Path) -> None:
    """The successor store must hold exactly this manifest's birth (read-only)."""

    from paper_trading.durable_event_store import EpochNotFoundError
    from paper_trading.ppl_authority_runtime import _event_id

    try:
        events = DurableEventStore(successor_root).load_epoch(manifest.paper_epoch_id)
    except EpochNotFoundError as exc:
        raise SuccessionRefusal("resume: successor store has no birth event") from exc
    except Exception as exc:
        raise SuccessionRefusal(f"resume: successor store is unreadable: {exc}") from exc
    first = events[0] if events else None
    if (
        first is None
        or first.sequence != 1
        or first.event_type is not LedgerEventType.EPOCH_CREATED
        or first.paper_epoch_id != manifest.paper_epoch_id
        or first.event_id
        != _event_id(manifest, LedgerEventType.EPOCH_CREATED, "epoch")
        or first.timestamp != manifest.created_at
        or first.payload.get("initial_virtual_capital") != manifest.initial_virtual_capital
        or first.payload.get("code_sha") != manifest.code_sha
        or first.payload.get("config_snapshot_hash") != manifest.config_snapshot_hash
    ):
        raise SuccessionRefusal("resume: store birth event does not match this manifest")


def issue_activation_clearance(**kwargs: Any) -> ActivationClearance:
    """Bootstrap clearance (first birth): the successor store must be empty."""

    return _issue_clearance(purpose=PURPOSE_BOOTSTRAP, **kwargs)


def issue_resume_clearance(**kwargs: Any) -> ActivationClearance:
    """Resume clearance (restart in a new process, birth already persisted).

    Re-examines in the *current* process the same bindings and a fresh
    exclusivity proof (``purpose=RESUME``; the empty-successor-store
    observation is replaced by a read-only check that the store holds this
    manifest's birth event).  Nothing is written; ledgers stay untouched.
    """

    return _issue_clearance(purpose=PURPOSE_RESUME, **kwargs)


def _issue_clearance(
    *,
    purpose: str,
    manifest: AuthorityEpochManifest,
    record: InterruptedSuccessionRecord,
    proof_bytes: bytes,
    observation_artifacts: Mapping[str, bytes],
    predecessor_ledger_bytes_now: bytes,
    predecessor_store_root: str | Path,
    successor_store_root: str | Path,
    now: float,
    max_age_s: float = DEFAULT_CLEARANCE_MAX_AGE_S,
) -> ActivationClearance:
    """Verify the separate exclusivity proof; a documentary closure is not one."""

    verify_manifest_matches_record(manifest, record)
    manifest_sha = authority_manifest_sha256(manifest)

    proof = _load_object(proof_bytes, "exclusivity proof")
    _exact_fields(
        proof,
        {
            "schema",
            "successor_paper_epoch_id",
            "manifest_sha256",
            "record_sha256",
            "predecessor_ledger_sha256",
            "predecessor_store_root",
            "successor_store_root",
            "purpose",
            "observations",
        },
        "exclusivity proof",
    )
    if proof["schema"] != EXCLUSIVITY_SCHEMA:
        raise SuccessionRefusal("exclusivity proof: unsupported schema")
    if proof["purpose"] != purpose:
        raise SuccessionRefusal("exclusivity proof was issued for another purpose")
    if proof["successor_paper_epoch_id"] != manifest.paper_epoch_id:
        raise SuccessionRefusal("exclusivity proof targets another epoch")
    if proof["manifest_sha256"] != manifest_sha:
        raise SuccessionRefusal("exclusivity proof targets another manifest")
    if proof["record_sha256"] != record.record_sha256:
        raise SuccessionRefusal("exclusivity proof targets another succession record")

    predecessor_root = _resolve_root(predecessor_store_root, "predecessor store root")
    successor_root = _resolve_root(successor_store_root, "successor store root")
    if proof["predecessor_store_root"] != str(predecessor_root) or proof[
        "successor_store_root"
    ] != str(successor_root):
        raise SuccessionRefusal("exclusivity proof paths differ from the supplied roots")
    if (
        predecessor_root == successor_root
        or successor_root.is_relative_to(predecessor_root)
        or predecessor_root.is_relative_to(successor_root)
    ):
        raise SuccessionRefusal(
            "successor authority must use a store distinct from the predecessor's"
        )
    if purpose == PURPOSE_BOOTSTRAP:
        if successor_root.exists() and (
            not successor_root.is_dir() or any(successor_root.rglob("*.jsonl"))
        ):
            raise SuccessionRefusal("successor store is not empty")
        required = REQUIRED_EXCLUSIVITY_OBSERVATIONS
    else:
        _verify_birth(manifest, successor_root)
        required = tuple(
            n for n in REQUIRED_EXCLUSIVITY_OBSERVATIONS if n != "successor_store_empty_or_absent"
        )

    if not isinstance(predecessor_ledger_bytes_now, (bytes, bytearray)) or (
        _sha256(bytes(predecessor_ledger_bytes_now))
        != record.predecessor_ledger_sha256
        or proof["predecessor_ledger_sha256"] != record.predecessor_ledger_sha256
    ):
        raise SuccessionRefusal("predecessor ledger changed since the closure")

    observations = proof["observations"]
    if not isinstance(observations, dict) or set(observations) != set(required):
        raise SuccessionRefusal("exclusivity observations mismatch")
    if not isinstance(observation_artifacts, Mapping) or set(
        observation_artifacts
    ) != set(required):
        raise SuccessionRefusal("exclusivity observation artifacts mismatch (bytes required)")
    current = _real_number(now, "now")
    if isinstance(max_age_s, bool) or not isinstance(max_age_s, (int, float)):
        raise SuccessionRefusal("max_age_s must be a number")
    if not math.isfinite(max_age_s) or max_age_s <= 0:
        raise SuccessionRefusal("max_age_s must be a positive finite number")
    for name in required:
        item = observations[name]
        if not isinstance(item, dict):
            raise SuccessionRefusal(f"observation {name}: object required")
        _exact_fields(
            item,
            {"result", "observed_at", "observer", "method", "evidence_sha256"},
            f"observation {name}",
        )
        if item["result"] != "PASS":
            raise SuccessionRefusal(f"observation {name}: result is not PASS")
        _nonempty_str(item["observer"], f"observation {name} observer")
        _nonempty_str(item["method"], f"observation {name} method")
        observed_at = _real_number(item["observed_at"], f"observation {name} time")
        if observed_at > current or current - observed_at > max_age_s:
            raise SuccessionRefusal(f"observation {name}: stale or from the future")
        artifact = observation_artifacts[name]
        if (
            not isinstance(artifact, (bytes, bytearray))
            or not artifact
            or not _is_sha256(item["evidence_sha256"])
            or _sha256(bytes(artifact)) != item["evidence_sha256"]
        ):
            raise SuccessionRefusal(f"observation {name}: evidence bytes do not match")

    fields = {
        "paper_epoch_id": manifest.paper_epoch_id,
        "manifest_sha256": manifest_sha,
        "record_sha256": record.record_sha256,
        "exclusivity_proof_sha256": _sha256(bytes(proof_bytes)),
        "successor_store_root": str(successor_root),
        "purpose": purpose,
        "issued_at": current,
        "max_age_s": float(max_age_s),
    }
    return ActivationClearance(seal=_clearance_seal(**fields), **fields)


__all__ = [
    "ActivationClearance",
    "InterruptedSuccessionRecord",
    "SuccessionRefusal",
    "build_interrupted_successor_manifest",
    "issue_activation_clearance",
    "issue_resume_clearance",
    "validate_clearance_for_use",
    "verify_interruption_evidence",
    "verify_manifest_matches_record",
]
