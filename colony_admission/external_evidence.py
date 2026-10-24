"""Pure external-evidence byte readers. Structural claims never grant authority."""

import hashlib
import re
from dataclasses import dataclass, field

from . import formats as f

FAULT_MAX_LINES, FAULT_LINE_BYTES = 4096, 16384
HISTORY_MAX_LINES, HISTORY_LINE_BYTES = 4096, 1024
POLICY_MAX_BYTES = 65536
FAULT_KEYS = frozenset({"schema", "lab_id", "scope", "child_agent_id", "operation_sha256", "attempt",
                        "boot_id", "event", "step", "phase", "code", "data"})
HISTORY_KEYS = frozenset({"root_version", "root_sha256", "pin", "minimum_version"})
POLICY_KEYS = frozenset({"schema", "lab_id", "root", "root_sha256", "pin", "minimum_version"})
ROOT_KEYS = frozenset({"root_schema", "environment", "lab_id", "root_version", "issuers", "revoked_envelopes"})
DIRECTORIES = frozenset({"LEDGER_DIRECTORY", "OPERATION_LOG_DIRECTORY", "LAB_DIRECTORY",
                         "INDIVIDUALS_DIRECTORY", "HOME_DIRECTORY", "ADMISSION_DIRECTORY",
                         "ENVELOPE_DIRECTORY", "QUARANTINE_DIRECTORY", "TRUST_DIRECTORY"})
FILES = frozenset({"LEDGER", "OPERATION_LOG", "ADMISSION_ENTRY", "ENVELOPE_ENTRY", "TRUST_POLICY", "TRUST_HISTORY"})
SINGLETONS = (DIRECTORIES | FILES) - {"HOME_DIRECTORY", "QUARANTINE_DIRECTORY", "OPERATION_LOG",
                                     "ADMISSION_ENTRY", "ENVELOPE_ENTRY"}
TRUST_TARGETS = frozenset({"TRUST_POLICY", "TRUST_HISTORY", "TRUST_DIRECTORY"})
PHASES = frozenset({"PREPARE", "D1", "D2", "D3", "QUARANTINE", "SET_ASIDE", "TERMINATE", "ACK", "TRUST_INSTALL"})
COMPONENT = re.compile(r"[A-Za-z0-9_.:-]+\Z")
OBS_KEYS = frozenset({"inspection_schema", "status", "operation_sha256", "operation_entries", "legacy_entries",
                      "ledger_entries", "ledger_sha256", "entry", "failures", "accepted", "authenticity",
                      "authorization", "completeness", "provenance", "durability"})


@dataclass(frozen=True)
class HistoryClaim:
    root_version: int
    root_sha256: str
    pin: str
    minimum_version: int


@dataclass(frozen=True)
class TrustProjection:
    status: str
    code: str
    history: tuple[HistoryClaim, ...] = ()
    policy_bytes: bytes | None = None
    policy_sha256: str | None = None
    history_sha256: str | None = None
    root_sha256: str | None = None
    root_version: int | None = None
    minimum_version: int | None = None
    accepted: bool = field(default=False, init=False)
    provenance: str = field(default="NOT_EVALUATED", init=False)
    durability: str = field(default="NOT_EVALUATED", init=False)
    external_facts: str = field(default="NOT_EVALUATED", init=False)


@dataclass(frozen=True)
class TargetClaim:
    resource: str
    object_kind: str
    relative_path: str


@dataclass(frozen=True)
class FaultClaim:
    entry_sha256: str
    scope: str
    operation_sha256: str | None
    child_agent_id: str | None
    attempt: int | None
    step: str | None
    phase: str
    origin: str
    failure: str
    target: TargetClaim | None


@dataclass(frozen=True)
class TerminationClaim:
    entry_sha256: str
    fault_sha256: str
    operation_sha256: str
    child_agent_id: str
    attempt: int
    classification: str
    evidence: str


@dataclass(frozen=True)
class FaultProjection:
    status: str
    code: str
    entry_bytes: tuple[bytes, ...] = ()
    fault_claims: tuple[FaultClaim, ...] = ()
    termination_claims: tuple[TerminationClaim, ...] = ()
    pending_set_aside: tuple[str, ...] = ()
    ledger_fault_claim: bool | None = None
    trust_fault_claim: bool | None = None
    raw_sha256: str | None = None
    accepted: bool = field(default=False, init=False)
    provenance: str = field(default="NOT_EVALUATED", init=False)
    durability: str = field(default="NOT_EVALUATED", init=False)
    external_facts: str = field(default="NOT_EVALUATED", init=False)


def _lab(lab_id):
    f.require(type(lab_id) is str and f.NAME.fullmatch(lab_id))


def _lines(raw, max_lines, line_bytes):
    f.require(type(raw) is bytes)
    if len(raw) > max_lines * line_bytes:
        raise f.FormatError("EVIDENCE_LIMIT_REACHED")
    f.require(not raw or raw.endswith(b"\n"))
    lines = raw.split(b"\n")[:-1] if raw else []
    if len(lines) > max_lines or any(len(line) + 1 > line_bytes for line in lines):
        raise f.FormatError("EVIDENCE_LIMIT_REACHED")
    return lines


def _unique_strings(value, *, hexes=False, nonempty=False):
    f.require(type(value) is list and (not nonempty or bool(value)))
    f.require(all(f.hex64(x) if hexes else type(x) is str for x in value))
    f.require(value == sorted(set(value)))


def _root_shape(root, lab_id):
    """Lexical nested closure, deliberately not check_root or curve validation."""
    f.closed(root, ROOT_KEYS)
    f.require(root["root_schema"] == "colony-trust.root/0" and root["environment"] == "LAB_TEST")
    f.require(root["lab_id"] == lab_id and f.integer(root["root_version"], 1))
    _unique_strings(root["revoked_envelopes"], hexes=True)
    f.require(type(root["issuers"]) is list and bool(root["issuers"]))
    issuers, keys = set(), set()
    for issuer in root["issuers"]:
        f.closed(issuer, {"issuer_id", "issuer_kind", "scopes", "keys"})
        _lab(issuer["issuer_id"])
        f.require(issuer["issuer_id"] not in issuers)
        issuers.add(issuer["issuer_id"])
        f.require(issuer["issuer_kind"] in ("EXTERNAL_HUMAN", "EXTERNAL_REVIEW_PROCESS", "LAB_OPERATOR"))
        _unique_strings(issuer["scopes"], nonempty=True)
        f.require(all(scope in f.KINDS for scope in issuer["scopes"]))
        f.require(type(issuer["keys"]) is list and bool(issuer["keys"]))
        for key in issuer["keys"]:
            f.closed(key, {"key_id", "public_key", "status", "introduced_in_root", "retired_in_root"})
            f.require(f.hex64(key["key_id"]) and f.hex64(key["public_key"]) and key["key_id"] not in keys)
            keys.add(key["key_id"])
            f.require(key["status"] in ("ACTIVE", "RETIRED", "REVOKED"))
            f.require(f.integer(key["introduced_in_root"], 1))
            f.require(key["retired_in_root"] is None or f.integer(key["retired_in_root"], 1))


def project_installed_trust(policy_raw: bytes, history_raw: bytes, lab_id: str) -> TrustProjection:
    """Check structural head equality only; root semantics/provenance remain external."""
    try:
        _lab(lab_id)
        f.require(type(policy_raw) is bytes)
        if len(policy_raw) > POLICY_MAX_BYTES:
            raise f.FormatError("EVIDENCE_LIMIT_REACHED")
        lines = _lines(history_raw, HISTORY_MAX_LINES, HISTORY_LINE_BYTES)
        f.require(bool(lines))
        history, previous_version, previous_floor = [], 0, 0
        for line in lines:
            entry = f.loads(line)
            f.closed(entry, HISTORY_KEYS)
            version, floor = entry["root_version"], entry["minimum_version"]
            f.require(f.integer(version, 1) and f.integer(floor, 1) and floor <= version)
            f.require(version > previous_version and floor >= previous_floor)
            f.require(f.hex64(entry["root_sha256"]) and entry["pin"] == entry["root_sha256"])
            history.append(HistoryClaim(version, entry["root_sha256"], entry["pin"], floor))
            previous_version, previous_floor = version, floor
        policy = f.loads(policy_raw)
        f.closed(policy, POLICY_KEYS)
        f.require(policy["schema"] == "colony-admission.installed-trust/0" and policy["lab_id"] == lab_id)
        _root_shape(policy["root"], lab_id)
        f.require(f.hex64(policy["root_sha256"]) and policy["pin"] == policy["root_sha256"])
        f.require(f.digest(policy["root"]) == policy["root_sha256"])
        last = history[-1]
        f.require(f.integer(policy["minimum_version"], 1))
        f.require((policy["root"]["root_version"], policy["root_sha256"], policy["pin"], policy["minimum_version"])
                  == (last.root_version, last.root_sha256, last.pin, last.minimum_version))
        return TrustProjection("STRUCTURAL_MATCH", "STRUCTURAL_ONLY", tuple(history), policy_raw,
                               hashlib.sha256(policy_raw).hexdigest(), hashlib.sha256(history_raw).hexdigest(),
                               last.root_sha256, last.root_version, last.minimum_version)
    except (f.FormatError, TypeError, ValueError, KeyError, UnicodeError, RecursionError, OverflowError):
        return TrustProjection("UNAVAILABLE", "TRUST_CURRENT_UNAVAILABLE")


def _target(value, entry):
    f.closed(value, {"resource", "object_kind", "relative_path"})
    resource, kind, path = value["resource"], value["object_kind"], value["relative_path"]
    f.require(type(resource) is str and resource in DIRECTORIES | FILES | {"HOME_ENTRY"})
    f.require(kind in ("FILE", "DIRECTORY") and type(path) is str)
    f.require(resource not in DIRECTORIES or kind == "DIRECTORY")
    f.require(resource not in FILES or kind == "FILE")
    if path:
        f.require(all(part not in ("", ".", "..") and COMPONENT.fullmatch(part) for part in path.split("/")))
    if resource in SINGLETONS:
        f.require(path == "")
    child, operation = entry["child_agent_id"], entry["operation_sha256"]
    if resource == "OPERATION_LOG":
        f.require(path == child + ".log")
    elif resource == "HOME_DIRECTORY":
        f.require(path == child)
    elif resource == "HOME_ENTRY":
        f.require(path.startswith(child + "/"))
    elif resource == "ADMISSION_ENTRY":
        f.require(path == child + ".json")
    elif resource == "ENVELOPE_ENTRY":
        f.require(path.startswith(child + "/"))
    elif resource == "QUARANTINE_DIRECTORY":
        f.require(path in ("", operation, operation + "/" + str(entry["attempt"]), operation + "/terminal"))
    if entry["scope"] == "LAB":
        f.require(resource in TRUST_TARGETS)
    else:
        f.require(resource not in TRUST_TARGETS)
    return TargetClaim(resource, kind, path)


def _fault_entry_shape(entry, lab_id):
    f.closed(entry, FAULT_KEYS)
    f.require(entry["schema"] in ("colony-admission.fault-entry/0", "colony-admission.fault-entry/1"))
    f.require(entry["lab_id"] == lab_id)
    f.require(type(entry["boot_id"]) is str and f.BOOT.fullmatch(entry["boot_id"]))
    f.require(type(entry["code"]) is str and f.CODE.fullmatch(entry["code"]))
    f.require(type(entry["phase"]) is str and entry["phase"] in PHASES)
    scope, phase, step = entry["scope"], entry["phase"], entry["step"]
    if scope == "LAB":
        f.require(entry["event"] == "FAULT" and phase == "TRUST_INSTALL" and step is None)
        f.require(all(entry[k] is None for k in ("child_agent_id", "operation_sha256", "attempt")))
    else:
        f.require(scope == "OPERATION" and phase != "TRUST_INSTALL")
        f.require(f.hex64(entry["child_agent_id"]) and f.hex64(entry["operation_sha256"]))
        f.require(f.integer(entry["attempt"], 1))
    expected_step = phase if phase in ("D1", "D2", "D3") else "D3" if phase in ("QUARANTINE", "SET_ASIDE") else None
    f.require(step == expected_step)
    f.require(type(entry["event"]) is str and type(entry["data"]) is dict)


def _observation(obs, operation, status, count):
    f.closed(obs, OBS_KEYS)
    f.require(obs["inspection_schema"] == "colony-trust.operation-inspection/0")
    f.require(obs["status"] == status and obs["operation_sha256"] == operation)
    f.require(f.integer(obs["operation_entries"]) and obs["operation_entries"] == count)
    f.require(f.integer(obs["legacy_entries"]) and f.integer(obs["ledger_entries"]))
    f.require(count + obs["legacy_entries"] <= obs["ledger_entries"] <= 16384)
    f.require(f.hex64(obs["ledger_sha256"]) and obs["failures"] == [] and obs["accepted"] is False)
    f.require(all(obs[k] == "NOT_EVALUATED" for k in
                  ("authenticity", "authorization", "completeness", "provenance", "durability")))
    if count == 0:
        f.require(obs["entry"] is None and obs["legacy_entries"] == 0)
    else:
        item = obs["entry"]
        f.closed(item, {"ledger_schema", "issuer_id", "envelope_id", "envelope_sha256", "operation_sha256"})
        f.require(item["ledger_schema"] == "colony-trust.consumed/1" and item["operation_sha256"] == operation)
        _lab(item["issuer_id"])
        f.require(f.hex64(item["envelope_id"]) and f.hex64(item["envelope_sha256"]))


def _finding(entry):
    finding = entry["data"]["ledger_finding"]
    version = entry["schema"].rsplit("/", 1)[1]
    if version == "0":
        f.closed(finding, {"status", "operation_entries", "observation_sha256"})
        allowed = {"ABSENT_IN_VALID_LEDGER": 0, "CONSUMED_BY_OPERATION": 1}
    else:
        f.closed(finding, {"inspection_schema", "status", "operation_entries", "observation_sha256", "observation"})
        f.require(finding["inspection_schema"] == "colony-trust.operation-inspection/0")
        allowed = {"NO_OPERATION_ENTRY": 0, "OPERATION_ENTRY_PRESENT": 1}
    status, count = finding["status"], finding["operation_entries"]
    f.require(type(status) is str and status in allowed and f.integer(count) and count == allowed[status])
    f.require(f.hex64(finding["observation_sha256"]))
    if version == "1":
        _observation(finding["observation"], entry["operation_sha256"], status, count)
        f.require(f.digest(finding["observation"]) == finding["observation_sha256"])
    return "FAILED_CONSUMED" if count else "ABANDONED", "EMBEDDED_HISTORICAL" if version == "1" else "REFERENCE_UNRESOLVED"


def _directory_blocks(faults, child):
    for fault in faults:
        target = fault.target
        if fault.origin != "CONTROLLER" or fault.failure not in ("FSYNC", "RENAME") or target is None:
            continue
        if target.resource == "INDIVIDUALS_DIRECTORY" or \
                (target.resource == "QUARANTINE_DIRECTORY" and target.relative_path == "") or \
                (target.resource == "HOME_DIRECTORY" and target.relative_path == child):
            return True
    return False


def project_fault_log(raw: bytes, lab_id: str) -> FaultProjection:
    """Validate supplied fault-log claims only. No terminal override is authorized."""
    try:
        _lab(lab_id)
        lines = _lines(raw, FAULT_MAX_LINES, FAULT_LINE_BYTES)
        faults, terms, bindings, term_by_op, actions = [], [], {}, {}, {}
        fault_by_hash, faulty_children = {}, {}
        for line in lines:
            entry = f.loads(line)
            _fault_entry_shape(entry, lab_id)
            op, child, attempt = entry["operation_sha256"], entry["child_agent_id"], entry["attempt"]
            event, data = entry["event"], entry["data"]
            if op is not None:
                binding = (child, attempt)
                f.require(op not in bindings or bindings[op] == binding)
                f.require(child not in faulty_children or faulty_children[child] == op)
                bindings[op] = binding
            entry_hash = f.digest(entry)
            if event == "FAULT":
                if entry["phase"] == "SET_ASIDE" and op in term_by_op:
                    f.require(actions.get(op) == "PENDING")
                f.closed(data, {"origin", "failure", "target"})
                origin, failure = data["origin"], data["failure"]
                if origin == "SUPERVISOR":
                    f.require(entry["phase"] == "D3" and failure == "ADMIT" and data["target"] is None)
                    target = None
                else:
                    f.require(origin in ("CONTROLLER", "TRUST"))
                    target = _target(data["target"], entry)
                    if origin == "TRUST":
                        f.require(entry["phase"] == "D1" and failure == "CONSUMPTION_IO_UNKNOWN")
                        f.require(target == TargetClaim("LEDGER", "FILE", ""))
                    else:
                        f.require(failure in ("WRITE", "SHORT_WRITE", "FSYNC", "RENAME"))
                f.require(entry["code"] == "DURABILITY_UNKNOWN")
                claim = FaultClaim(entry_hash, entry["scope"], op, child, attempt, entry["step"],
                                   entry["phase"], origin, failure, target)
                faults.append(claim)
                fault_by_hash[entry_hash] = claim
                if target is not None and target.resource == "OPERATION_LOG":
                    faulty_children[child] = op
                if op in actions and actions[op] == "PENDING":
                    actions[op] = "FAULTED"
            elif event == "TERMINATED_EXTERNALLY":
                f.closed(data, {"fault_sha256", "ledger_finding"})
                f.require(entry["scope"] == "OPERATION" and entry["phase"] == "TERMINATE")
                f.require(entry["code"] == "OPERATOR_TERMINATED" and op not in term_by_op)
                f.require(f.hex64(data["fault_sha256"]) and data["fault_sha256"] in fault_by_hash)
                fault = fault_by_hash[data["fault_sha256"]]
                f.require(fault.operation_sha256 == op and fault.child_agent_id == child and fault.attempt == attempt)
                f.require(fault.target is not None and fault.target.resource == "OPERATION_LOG")
                classification, evidence = _finding(entry)
                claim = TerminationClaim(entry_hash, data["fault_sha256"], op, child, attempt, classification, evidence)
                terms.append(claim)
                term_by_op[op] = (claim, fault)
            elif event in ("SET_ASIDE_BEGIN", "SET_ASIDE_DONE"):
                f.closed(data, {"termination_sha256"})
                f.require(entry["scope"] == "OPERATION" and entry["phase"] == "SET_ASIDE")
                f.require(entry["code"] == "OPERATOR_SET_ASIDE" and op in term_by_op)
                term, fault = term_by_op[op]
                f.require(data["termination_sha256"] == term.entry_sha256 and fault.step == "D3")
                f.require(not _directory_blocks(faults, child))
                if event == "SET_ASIDE_BEGIN":
                    f.require(op not in actions)
                    actions[op] = "PENDING"
                else:
                    f.require(actions.get(op) == "PENDING")
                    actions[op] = "DONE"
            else:
                raise f.FormatError()
        return FaultProjection("STRUCTURAL_ONLY" if lines else "EMPTY", "STRUCTURAL_ONLY", tuple(lines),
                               tuple(faults), tuple(terms), tuple(sorted(op for op in actions if actions[op] != "DONE")),
                               any(x.target and x.target.resource in ("LEDGER", "LEDGER_DIRECTORY") for x in faults),
                               any(x.scope == "LAB" for x in faults), hashlib.sha256(raw).hexdigest())
    except (f.FormatError, TypeError, ValueError, KeyError, UnicodeError, RecursionError, OverflowError):
        return FaultProjection("CORRUPT", "FAULT_LOG_CORRUPT")
