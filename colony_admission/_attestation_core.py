"""Private 3B comparisons over detached data. No acquisition or admission API.

These functions are building blocks for a future single-owner acquisition. A
local PASS is never a complete scan, a qualification, or permission to act.
"""

from dataclasses import dataclass, field

from colony_lab import lineage
from colony_lab.a1_identity import IdentityError
from colony_registrar import registrar as reg
from colony_trust import trust

from . import formats as f
from .physical_evidence import NE, record_loads, unique

IND = "colony-lab.individual/0"
QUAL = "colony-lab.qualification/0"
ADM = "colony-registrar.admission/0"
STATEMENT = "colony-admission.attestation-statement/0"


class CoreError(ValueError):
    """Fixed diagnostic code only; never include submitted contents."""


def need(condition, code):
    if not condition:
        raise CoreError(code)


def decode(raw, limit=65536):
    need(type(raw) is bytes and len(raw) <= limit, "SOURCE_LIMIT")
    try:
        value = record_loads(raw)
        need(type(value) is dict, "STORED_FILE_DIVERGENT")
        return value
    except (f.FormatError, ValueError, TypeError, UnicodeError, RecursionError):
        raise CoreError("STORED_FILE_DIVERGENT") from None


def operation(raw):
    need(type(raw) is bytes and len(raw) < f.MAX_LINE, "SOURCE_LIMIT")
    value = f.loads(raw)
    f.validate_operation(value)
    return value


@dataclass(frozen=True, order=True)
class Key:
    kind: str
    agent_id: str
    agent_spec_id: str
    record_sha256: str


@dataclass(frozen=True)
class Need:
    key: Key
    record_bytes: bytes
    namespaces: tuple[str, ...]
    envelope_sha256s: tuple[str, ...] = ()


@dataclass(frozen=True)
class Node:
    agent_id: str
    record_bytes: bytes
    spec_bytes: bytes
    qualification_bytes: bytes | None = None
    admission_bytes: bytes | None = None
    statement_bytes: bytes | None = None


@dataclass(frozen=True)
class Branch:
    status: str = NE
    agent_ids: tuple[str, ...] = ()  # founder -> parent, only after full verification
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    population: str = field(default=NE, init=False)
    ceilings: str = field(default=NE, init=False)


@dataclass(frozen=True)
class Partition:
    status: str
    needs: tuple[Need, ...] = ()
    codes: tuple[str, ...] = ()
    population_partition: str = field(default=NE, init=False)
    accepted: bool = field(default=False, init=False)


@dataclass(frozen=True)
class Item:
    key: Key
    presence: str
    integrity: str = NE
    authenticity: str = NE
    issuer_authorization: str = NE
    genuine_but_revoked: bool | str = NE
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)


def policy(raw, pin):
    """Caller acquires g0 bytes or provides detached operator bytes; no load_policy."""
    try:
        return reg.check_policy(decode(raw), pin)
    except reg.RegistrarError as exc:
        raise CoreError(exc.code) from None


def _admission(a, q, child, parent, selected_policy, policy_pin, excluded):
    # Pure adaptation of Registrar._check_admission + _check_admitted bindings.
    need(type(a) is dict and set(a) == reg.ADMISSION_FIELDS
         and a["admission_schema"] == reg.ADMISSION_SCHEMA, "ADMISSION_INVALID")
    expected = {"child_agent_id": child["agent_id"], "child_agent_spec_id": child["agent_spec_id"],
        "parent_agent_id": parent["agent_id"], "policy_sha256": policy_pin,
        "parent_qualification_sha256": f.digest(q), "budget": child["budget"],
        "lab_permissions": child["lab_permissions"], "declared_diff": child["genotype"]["declared_diff"]}
    need(all(f.canonical(a[k]) == f.canonical(v) for k, v in expected.items()),
         "ADMISSION_NOT_FOR_THIS_BIRTH")
    issuer = a["admitter_id"]
    need(type(issuer) is str and bool(lineage._REVIEWER_ID.fullmatch(issuer))
         and a["admitter_kind"] in selected_policy["admitter_kinds"]
         and not any(agent[:16] in issuer for agent in excluded), "SELF_ADMISSION_DENIED")
    lineage.check_qualification(q, parent, also_excluded=frozenset(excluded))
    need(q["criteria_sha256"] in selected_policy["admissible_parent_criteria_sha256"],
         "PARENT_CRITERIA_NOT_ADMISSIBLE")
    need(all(child["budget"][k] <= parent["budget"][k] for k in child["budget"]), "BUDGET_ESCALATION")


def branch(operation_bytes, nodes, policy_bytes, policy_pin):
    """Verify the whole parental branch; never return a positive prefix."""
    try:
        selected = policy(policy_bytes, policy_pin)
        op = operation(operation_bytes)
        need(op["policy_sha256"] == policy_pin, "POLICY_CONTEXT_MISMATCH")
        need(type(nodes) is tuple and len(nodes) <= 9, "BRANCH_DEPTH_LIMIT")
        need(all(type(n) is Node and f.hex64(n.agent_id) for n in nodes), "BRANCH_DIVERGENT")
        by_id = {n.agent_id: n for n in nodes}
        need(len(by_id) == len(nodes), "BRANCH_DIVERGENT")
        chain, visited = [], set()
        agent = op["parent_agent_id"]
        while True:
            need(agent not in visited, "BRANCH_CYCLE")
            need(len(chain) < 9, "BRANCH_DEPTH_LIMIT")
            visited.add(agent)
            need(agent in by_id, "BRANCH_INCOMPLETE")
            n = by_id[agent]
            record, spec = decode(n.record_bytes), decode(n.spec_bytes)
            need(record.get("agent_id") == agent, "BRANCH_DIVERGENT")
            chain.append((n, record, spec))
            if record.get("role") == "FOUNDER":
                break
            need(record.get("role") == "DESCENDANT", "BRANCH_DIVERGENT")
            agent = record["lineage"]["parent_agent_id"]
            need(f.hex64(agent), "BRANCH_DIVERGENT")
        need(visited == set(by_id), "BRANCH_DIVERGENT")
        chain.reverse()
        excluded = visited | {op["child_agent_id"]}
        need(op["child_agent_id"] not in visited, "BRANCH_DIVERGENT")
        previous, previous_spec = None, None
        for n, record, spec in chain:
            lineage.verify_record(record, spec, previous, previous_spec)
            if previous is not None:
                need(n.admission_bytes is not None and n.qualification_bytes is not None, "BRANCH_INCOMPLETE")
                _admission(decode(n.admission_bytes), decode(n.qualification_bytes), record, previous,
                           selected, policy_pin, excluded)
            previous, previous_spec = record, spec
        plan = op["birth_plan"]
        need(f.canonical(plan["parent"]) == f.canonical(previous), "BRANCH_DIVERGENT")
        lineage.verify_record(plan["record"], plan["child_spec"], previous, previous_spec)
        need(f.canonical(op["declared_diff"]) == f.canonical(plan["record"]["genotype"]["declared_diff"]),
             "BRANCH_DIVERGENT")
        _admission(plan["admission"], plan["qualification"], plan["record"], previous,
                   selected, policy_pin, excluded)
        need(plan["record"]["lineage"]["generation"] <= selected["max_generation"], "BRANCH_DEPTH_LIMIT")
        return Branch("PASS", tuple(n.agent_id for n, _, _ in chain))
    except (CoreError, lineage.LineageError, reg.RegistrarError, IdentityError) as exc:
        code = str(exc) if isinstance(exc, CoreError) else exc.code
        return Branch(NE if code == "BRANCH_INCOMPLETE" else "FAIL", codes=(code,))
    except (f.FormatError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return Branch("FAIL", codes=("BRANCH_DIVERGENT",))


def key(kind, record):
    fields = trust.KINDS[kind].subject
    return Key(kind, record[fields[0]], record[fields[1]], f.digest(record))


def _add(needs, kind, record, namespace, envelope_digest=None):
    k = key(kind, record)
    need(f.hex64(k.agent_id) and f.hex64(k.agent_spec_id), "FROZEN_ITEM_DIVERGENT")
    old = needs.get(k)
    raw = f.canonical(record)
    if old:
        need(old.record_bytes == raw, "FROZEN_ITEM_DIVERGENT")
    needs[k] = Need(k, raw, tuple(sorted(set((old.namespaces if old else ()) + (namespace,)))),
        tuple(sorted(set((old.envelope_sha256s if old else ()) + ((envelope_digest,) if envelope_digest else ())))))


def decision_partition(operation_bytes, nodes, branch_fact, statement_bytes, policy_bytes, policy_pin):
    """Derive needs before comparing PREPARED, independent of its DECISION roles.

No missing statement is reconstructed from an envelope or from its digest.
The caller supplies only this operation's acquired objects, never current bytes
substituted for a historical attempt.
"""
    try:
        selected = policy(policy_bytes, policy_pin)
        op = operation(operation_bytes)
        cap = min(252, 4 * selected["max_population"] - 4)
        need(len(op["items"]) <= cap, "SOURCE_LIMIT")
        # Recompute the branch rather than trusting an invented PASS object.
        actual = branch(operation_bytes, nodes, policy_bytes, policy_pin)
        if actual.status != "PASS":
            return Partition(actual.status, codes=actual.codes)
        need(actual == branch_fact, "BRANCH_DIVERGENT")
        plan, needs = op["birth_plan"], {}
        child = op["child_agent_id"]
        need(statement_bytes is not None, "EVIDENCE_NOT_STORED")
        records = {"admission": plan["admission"], "qualification": plan["qualification"],
                   "statement": decode(statement_bytes, 16384)}
        for role, kind in (("admission", ADM), ("qualification", QUAL), ("statement", STATEMENT)):
            record = records[role]
            need(f.digest(record) == op["presented"][role]["record_sha256"], "FROZEN_ITEM_DIVERGENT")
            _add(needs, kind, record, child + "/" + role, op["presented"][role]["envelope_sha256"])
        by_id = {n.agent_id: n for n in nodes}
        for agent in actual.agent_ids:
            n = by_id[agent]
            _add(needs, IND, decode(n.record_bytes), agent + "/individual")
            if decode(n.record_bytes)["role"] == "FOUNDER":
                continue
            need(n.statement_bytes is not None, "ATTESTATION_MISSING")
            for kind, raw, role in ((ADM, n.admission_bytes, "admission"),
                                   (QUAL, n.qualification_bytes, "qualification"),
                                   (STATEMENT, n.statement_bytes, "statement")):
                _add(needs, kind, decode(raw, 16384 if kind == STATEMENT else 65536), agent + "/" + role)
        need(len(needs) <= cap, "SOURCE_LIMIT")
        frozen, codes = {}, []
        for item in op["items"]:
            k = Key(item["kind"], item["subject"]["agent_id"], item["subject"]["agent_spec_id"], item["record_sha256"])
            if item["role"] == "POPULATION":
                if k in needs:
                    codes.append("DECISION_ROLE_MISMATCH")
                continue
            frozen[k] = item["envelope_sha256"]
        if set(needs) - set(frozen):
            codes.append("ATTESTATION_MISSING")
        if set(frozen) - set(needs):
            codes.append("ATTESTATION_UNEXPECTED")
        for k in set(needs) & set(frozen):
            n = needs[k]
            if n.envelope_sha256s and n.envelope_sha256s != (frozen[k],):
                codes.append("FROZEN_ITEM_DIVERGENT")
            needs[k] = Need(k, n.record_bytes, n.namespaces, (frozen[k],))
        return Partition("FAIL" if codes else "PASS", tuple(needs[k] for k in sorted(needs)), unique(codes))
    except CoreError as exc:
        return Partition(NE if str(exc) in ("BRANCH_INCOMPLETE", "EVIDENCE_NOT_STORED", "ATTESTATION_MISSING")
                         else "FAIL", codes=(str(exc),))
    except (f.FormatError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return Partition("FAIL", codes=("FROZEN_ITEM_DIVERGENT",))


def item_fact(required, envelopes, root_bytes, *, pin_sha256, minimum_version, lab_id):
    """All acquired copies for one K must name one frozen envelope, never a bundle/spend."""
    k = required.key
    if (type(envelopes) is not tuple or len(envelopes) != len(required.namespaces)
            or not envelopes or any(raw is None for raw in envelopes)):
        return Item(k, "ABSENT", codes=("ATTESTATION_MISSING",))
    try:
        need(type(envelopes) is tuple, "FROZEN_ITEM_DIVERGENT")
        decoded = tuple(decode(raw, 16384) for raw in envelopes)
        hashes = {f.digest(e) for e in decoded}
        need(len(hashes) == 1 and len(required.envelope_sha256s) == 1
             and hashes == set(required.envelope_sha256s), "FROZEN_ITEM_DIVERGENT")
        record = decode(required.record_bytes)
        need(key(k.kind, record) == k, "FROZEN_ITEM_DIVERGENT")
        verdict = trust.classify_envelope(decoded[0], record, decode(root_bytes),
            pin_sha256=pin_sha256, minimum_version=minimum_version, lab_id=lab_id,
            record_kind=k.kind, subject={"agent_id": k.agent_id, "agent_spec_id": k.agent_spec_id})
        return Item(k, "PRESENT_MATCH", verdict["integrity"], verdict["authenticity"], verdict["authorization"],
                    verdict["genuine_but_revoked"], tuple(verdict["failures"]))
    except CoreError as exc:
        return Item(k, "DIVERGENT", integrity="FAIL", codes=(str(exc),))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return Item(k, "DIVERGENT", integrity="FAIL", codes=("FROZEN_ITEM_DIVERGENT",))


def ancestor_commit(node, operation_snapshots, admission_envelope_bytes):
    """Match a node to exactly one inventoried COMMITTED and its /1 snapshot.

Snapshots are (canonical operation bytes, projected terminal, canonical ledger
observation bytes). Only the acquisition owner may provide these snapshots.
No ledger path, lookup, new lock or consumption is performed here.
"""
    try:
        record, q, admission = decode(node.record_bytes), decode(node.qualification_bytes), decode(node.admission_bytes)
        envelope = decode(admission_envelope_bytes, 16384)
        need(trust._envelope_shape(envelope) is None, "ANCESTOR_COMMIT_UNPROVEN")
        need(envelope["record_kind"] == ADM and envelope["record_sha256"] == f.digest(admission)
             and envelope["issuer_id"] == admission["admitter_id"]
             and envelope["subject"] == {"agent_id": record["agent_id"], "agent_spec_id": record["agent_spec_id"]},
             "ANCESTOR_COMMIT_UNPROVEN")
        need(type(operation_snapshots) is tuple and len(operation_snapshots) <= 256, "SOURCE_LIMIT")
        matches = []
        for op_bytes, terminal, ledger_bytes in operation_snapshots:
            op = operation(op_bytes)
            plan = op["birth_plan"]
            if op["child_agent_id"] != node.agent_id or terminal != "COMMITTED":
                continue
            if (f.canonical(plan["record"]) == f.canonical(record)
                    and f.canonical(plan["admission"]) == f.canonical(admission)
                    and f.canonical(plan["qualification"]) == f.canonical(q)):
                matches.append((op, terminal, decode(ledger_bytes)))
        need(len(matches) == 1, "ANCESTOR_COMMIT_UNPROVEN")
        op, terminal, row = matches[0]
        need(terminal == "COMMITTED" and envelope["lab_id"] == op["lab_id"], "ANCESTOR_COMMIT_UNPROVEN")
        need(row["status"] == "OPERATION_ENTRY_PRESENT" and type(row["operation_entries"]) is int
             and row["operation_entries"] == 1,
             "ANCESTOR_COMMIT_UNPROVEN")
        e = row["entry"]
        need(e.get("ledger_schema") == trust.OPERATION_LEDGER_SCHEMA, "ANCESTOR_COMMIT_UNPROVEN")
        need(e["issuer_id"] == envelope["issuer_id"] and e["envelope_id"] == envelope["envelope_id"]
             and e["operation_sha256"] == f.digest(op) and row["operation_sha256"] == f.digest(op)
             and e["envelope_sha256"] == f.digest(envelope)
             and op["presented"]["admission"]["envelope_sha256"] == f.digest(envelope),
             "ANCESTOR_COMMIT_UNPROVEN")
        return "PASS", ()
    except (CoreError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return NE, ("ANCESTOR_COMMIT_UNPROVEN",)
