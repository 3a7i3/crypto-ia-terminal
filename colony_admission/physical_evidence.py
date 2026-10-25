"""Pure bounded physical comparisons. These facts never grant authority."""

import hashlib
import json
from dataclasses import dataclass, field, replace

from . import formats as f
from .oplog import LogProjection

NE = "NOT_EVALUATED"
STATEMENT_FIELDS = frozenset({"statement_schema", "subject_agent_id", "subject_agent_spec_id",
    "issuer_kind", "issuer_id", "issuer_root_version", "qualification_record_sha256",
    "historical_record_path", "historical_record_sha256", "evidence", "criteria_sha256",
    "subject_code_sha256", "evaluator_code_sha256", "verified_at_source_sha", "scope",
    "campaign_replayed", "campaign_evidence_sha256", "historical_signature_claimed"})


@dataclass(frozen=True)
class MetadataStamp:
    resource: str
    device: int
    inode: int
    mode: int
    uid: int
    nlink: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True)
class FileFact:
    role: str
    relative_path: str
    parent_resource: str
    presence: str
    comparison: str = NE
    size_bytes: int | None = None
    raw_sha256: str | None = None
    record_sha256: str | None = None


@dataclass(frozen=True)
class D1Fact:
    operation_entries: int | None = None
    frozen_hash_match: str = NE
    envelope_binding: str = NE


@dataclass(frozen=True)
class D2Fact:
    material_state: str = NE
    files: tuple[FileFact, ...] = ()


@dataclass(frozen=True)
class D3Fact:
    identity_state: str = NE
    layout_state: str = NE
    usage_content: str = NE
    files: tuple[FileFact, ...] = ()


@dataclass(frozen=True)
class OperationEvidence:
    child_agent_id: str
    operation_sha256: str
    attempt: int
    latest: bool
    log: LogProjection
    d1: D1Fact
    d2: D2Fact
    d3: D3Fact
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class LedgerCoverage:
    status: str = NE
    total_entries: int | None = None
    legacy_entries: int | None = None
    matched_entries: int | None = None
    unbound_entries: int | None = None


@dataclass(frozen=True)
class Limits:
    operations: int = 256
    logs: int = 256
    per_log_bytes: int = f.MAX_LOG
    log_bytes: int = 32 * 1024 * 1024
    ledger_bytes: int = 16 * 1024 * 1024
    ledger_entries: int = 16384
    record_bytes: int = 65536
    envelope_bytes: int = 16384
    item_references: int = 252
    content_bytes: int = 32 * 1024 * 1024
    home_entries: int = 16
    journal_entries: int = 4
    descriptors: int = 4096
    reached: tuple[str, ...] = ()


@dataclass(frozen=True)
class PhysicalEvidence:
    status: str
    blockers: tuple[str, ...]
    sources: tuple = ()
    metadata_sources: tuple[MetadataStamp, ...] = ()
    operations: tuple[OperationEvidence, ...] = ()
    pending_operations: tuple[str, ...] = ()
    ledger_bytes: bytes | None = None
    ledger_coverage: LedgerCoverage = field(default_factory=LedgerCoverage)
    limits: Limits = field(default_factory=Limits)
    schema: str = field(default="colony-admission.physical-evidence/0", init=False)
    accepted: bool = field(default=False, init=False)
    authenticity: str = field(default=NE, init=False)
    authorization: str = field(default=NE, init=False)
    completeness: str = field(default=NE, init=False)
    durability: str = field(default=NE, init=False)
    rotation: str = field(default=NE, init=False)
    attestations: str = field(default=NE, init=False)
    population: str = field(default=NE, init=False)
    ceilings: str = field(default=NE, init=False)
    recovery: str = field(default=NE, init=False)


def unique(codes):
    return tuple(dict.fromkeys(codes))


def storage_bytes(value):
    """Supervisor._dump profile, without importing or invoking that IO writer."""
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=1) + "\n").encode()


def _integer(token):
    value = f._number(token)
    f.require(str(value) == token)
    return value


def record_loads(raw):
    # Reuse the strict lexical parser after lossless whitespace/key-order normalization.
    # Its pair/number/depth rules run on the original bytes first.
    f.require(type(raw) is bytes and len(raw) <= 65536)
    f._depth(raw)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=f._pairs,
                       parse_int=_integer, parse_float=f._reject, parse_constant=f._reject)
    return f.loads(f.canonical(value))


def frozen_material(op):
    """Visible frozen bindings only; neither registrar validation nor qualification."""
    p = op["birth_plan"]
    parent, q, a = p["parent"], p["qualification"], p["admission"]
    f.require(f.hex64(parent.get("agent_spec_id")))
    subject = {"agent_id": op["parent_agent_id"], "agent_spec_id": parent["agent_spec_id"]}
    child = {"agent_id": op["child_agent_id"], "agent_spec_id": op["child_agent_spec_id"]}
    for key, expected in {"child_agent_id": child["agent_id"], "child_agent_spec_id": child["agent_spec_id"],
        "parent_agent_id": subject["agent_id"], "policy_sha256": op["policy_sha256"],
        "parent_qualification_sha256": f.digest(q), "budget": op["budget"],
        "lab_permissions": op["permissions"], "declared_diff": op["declared_diff"]}.items():
        f.require(key in a and f.canonical(a[key]) == f.canonical(expected))
    f.require(q.get("agent_id") == subject["agent_id"] and q.get("agent_spec_id") == subject["agent_spec_id"])
    for obj, prefix in ((a, "admitter"), (q, "reviewer")):
        f.require(type(obj.get(prefix + "_id")) is str and bool(f.NAME.fullmatch(obj[prefix + "_id"])))
        f.require(type(obj.get(prefix + "_kind")) is str)
    for role, kind, target in (("admission", "colony-registrar.admission/0", child),
            ("qualification", "colony-lab.qualification/0", subject),
            ("statement", "colony-admission.attestation-statement/0", subject)):
        matches = [x for x in op["items"] if x["role"] == "DECISION" and x["kind"] == kind
                   and x["subject"] == target]
        f.require(len(matches) == 1)
        f.require(all(matches[0][key] == op["presented"][role][key]
                      for key in ("record_sha256", "envelope_sha256")))
    return subject, child


def d2_paths(op):
    child, p = op["child_agent_id"], op["presented"]
    a, q = p["admission"]["record_sha256"], p["qualification"]["record_sha256"]
    return (("admission", f"registrar-admissions/{child}.json", 65536),
            ("admission_envelope", f"admission-envelopes/{child}/admission-{a}.envelope.json", 16384),
            ("qualification_envelope", f"admission-envelopes/{child}/birth-qualification-{q}.envelope.json", 16384),
            ("statement", f"admission-envelopes/{child}/statement-{q}.json", 16384),
            ("statement_envelope", f"admission-envelopes/{child}/statement-{q}.envelope.json", 16384))


def compare_d2(op, material, envelope_shape):
    """material contains only acquired bytes/absence and derived parent resources."""
    subject, child = frozen_material(op)
    plan, presented = op["birth_plan"], op["presented"]
    facts, decoded, errors = [], {}, []
    for role, path, _ in d2_paths(op):
        raw, parent = material[path]
        if raw is None:
            facts.append(FileFact(role, path, parent, "ABSENT"))
            continue
        record_hash, match = None, False
        try:
            value = record_loads(raw)
            record_hash = f.digest(value)
            decoded[role] = value
            if role == "admission":
                match = f.canonical(value) == f.canonical(plan["admission"])
            elif role == "statement":
                q = plan["qualification"]
                match = (type(value) is dict and set(value) == STATEMENT_FIELDS
                    and value["statement_schema"] == "colony-admission.attestation-statement/0"
                    and value["subject_agent_id"] == subject["agent_id"]
                    and value["subject_agent_spec_id"] == subject["agent_spec_id"]
                    and value["qualification_record_sha256"] == f.digest(q)
                    and value["issuer_id"] == q["reviewer_id"] and value["issuer_kind"] == q["reviewer_kind"]
                    and f.integer(value["issuer_root_version"], 1)
                    and record_hash == presented["statement"]["record_sha256"])
            else:
                name = role.removesuffix("_envelope")
                q = plan["admission"] if name == "admission" else plan["qualification"]
                issuer = q["admitter_id"] if name == "admission" else q["reviewer_id"]
                kind = {"admission": "colony-registrar.admission/0", "qualification": "colony-lab.qualification/0",
                        "statement": "colony-admission.attestation-statement/0"}[name]
                purpose = {"admission": "BIRTH_ADMITTED", "qualification": "QUALIFICATION_ATTESTED",
                           "statement": "QUALIFICATION_STATEMENT_ATTESTED"}[name]
                match = (envelope_shape(value) is None and record_hash == presented[name]["envelope_sha256"]
                    and value["record_sha256"] == presented[name]["record_sha256"]
                    and value["subject"] == (child if name == "admission" else subject)
                    and value["lab_id"] == op["lab_id"] and value["issuer_id"] == issuer
                    and value["record_kind"] == kind and value["purpose"] == purpose)
        except (f.FormatError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            pass
        if not match:
            errors.append("STORED_FILE_DIVERGENT")
        facts.append(FileFact(role, path, parent, "PRESENT",
            ("CANONICAL_MATCH" if role == "admission" else "DIGEST_BINDING_MATCH") if match else "MISMATCH",
            len(raw), hashlib.sha256(raw).hexdigest(), record_hash))
    statement = decoded.get("statement")
    if type(statement) is dict and "issuer_root_version" in statement:
        for role in ("qualification_envelope", "statement_envelope"):
            envelope = decoded.get(role)
            if type(envelope) is dict and "root_version" in envelope:
                if f.canonical(statement["issuer_root_version"]) != f.canonical(envelope["root_version"]):
                    errors.append("STORED_FILE_DIVERGENT")
                    facts = [replace(x, comparison="MISMATCH") if x.role == "statement" else x for x in facts]
    if any(x.comparison == "MISMATCH" for x in facts):
        state = "DIVERGENT"
    else:
        count = sum(x.presence == "PRESENT" for x in facts)
        state = "MATERIAL_MATCH" if count == 5 else "PARTIAL" if count else "ABSENT"
    return D2Fact(state, tuple(facts)), decoded, errors


def compare_d1(op, log, row, envelope=None, *, latest=True, completed_d2=False, envelope_available=False):
    errors = []
    count = row["operation_entries"]
    if row["status"] not in ("NO_OPERATION_ENTRY", "OPERATION_ENTRY_PRESENT"):
        errors.append("LEDGER_UNAVAILABLE")
    state = "ABSENT" if count == 0 else NE
    binding = "NOT_AVAILABLE_BEFORE_D2" if latest and not completed_d2 and not envelope_available else NE
    if not latest:
        binding = "SUPERSEDED_NOT_EVALUATED"
    if count == 1:
        e = row["entry"]
        state = "MATCH" if (e["operation_sha256"] == f.digest(op)
            and e["envelope_sha256"] == op["presented"]["admission"]["envelope_sha256"]) else "MISMATCH"
        if state == "MISMATCH":
            errors.append("LEDGER_ENVELOPE_MISMATCH")
        if envelope is not None:
            if (type(envelope) is dict and envelope.get("issuer_id") == e["issuer_id"]
                    and envelope.get("envelope_id") == e["envelope_id"]
                    and f.digest(envelope) == e["envelope_sha256"] and state == "MATCH"):
                binding = "MATCH"
            else:
                binding = NE
                errors.append("LEDGER_ENVELOPE_MISMATCH")
    consumed = log.last_completed_step not in (None, "D0") or log.terminal_claim in ("COMMITTED", "FAILED_CONSUMED")
    unconsumed = log.terminal_claim in ("REFUSED", "ABANDONED") or (not consumed and log.pending_step != "D1")
    if (consumed and count != 1) or (unconsumed and count != 0):
        errors.append("OPERATION_STATE_INCONSISTENT")
    return D1Fact(count, state, binding), errors


def compare_d3(op, log, material, home_present, layout):
    complete = log.last_completed_step == "D3"
    d2_done = log.last_completed_step in ("D2", "D3")
    errors, facts, matches, prefixes = [], [], 0, 0
    expected = {"spec.json": op["birth_plan"]["child_spec"], "record.json": op["birth_plan"]["record"],
                "birth_qualification.json": op["birth_plan"]["qualification"]}
    if not complete:
        expected["usage.json"] = {"runs": 0}
    for name, value in expected.items():
        path = f"individuals/{op['child_agent_id']}/{name}"
        raw, parent = material[path]
        if raw is None:
            facts.append(FileFact(name, path, parent, "ABSENT"))
            continue
        wanted = storage_bytes(value)
        match = raw == wanted
        matches += match
        prefixes += bool(not match and wanted.startswith(raw))
        facts.append(FileFact(name, path, parent, "PRESENT", "BYTES_MATCH" if match else "MISMATCH",
                              len(raw), hashlib.sha256(raw).hexdigest(), f.digest(value) if match else None))
    count = sum(x.presence == "PRESENT" for x in facts)
    if count > matches:
        if log.terminal_claim == "FAILED_CONSUMED" and count == matches + prefixes:
            identity = "TERMINAL_PREFIX"
            errors.append("ACTION_EVIDENCE_NOT_EVALUATED")
        else:
            identity = "DIVERGENT"
            errors.append("STORED_FILE_DIVERGENT")
    elif not home_present:
        identity = "ABSENT"
    elif count != len(expected):
        identity = "PARTIAL"
    else:
        identity = "IDENTITY_MATCH" if complete else "INITIAL_MATCH"
    if home_present and not d2_done:
        errors.append("OPERATION_STATE_INCONSISTENT")
    elif home_present and not log.d3_started:
        errors.append("HOME_ORIGIN_NOT_EVALUATED")
    if complete and (identity != "IDENTITY_MATCH"):
        errors.append("OPERATION_STATE_INCONSISTENT")
    if complete and layout != "OBSERVED":
        errors.append("D3_LAYOUT_INCOMPLETE")
    if identity == "INITIAL_MATCH" and layout != "OBSERVED":
        identity = "PARTIAL"
    usage = NE if complete else next(("INITIAL_MATCH" if x.comparison == "BYTES_MATCH" else
        "ABSENT" if x.presence == "ABSENT" else "DIVERGENT" for x in facts if x.role == "usage.json"), NE)
    return D3Fact(identity, layout, usage, tuple(facts)), errors
