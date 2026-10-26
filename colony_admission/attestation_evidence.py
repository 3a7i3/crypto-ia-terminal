"""Immutable 3B facts projected from a single owner's detached acquisition.

These comparisons confer no admission, qualification or operational authority.
Only the acquisition owner can establish the origin and stability of inputs.
"""

from dataclasses import dataclass, field, replace

from . import _attestation_core as c
from . import _attestation_statement as s
from . import formats as f
from . import physical_evidence as p

NE = p.NE


@dataclass(frozen=True)
class NeedFact:
    key: c.Key
    namespaces: tuple[str, ...]
    envelope_sha256s: tuple[str, ...]


@dataclass(frozen=True)
class EnvelopeFact:
    namespace: str
    presence: str
    expected_sha256s: tuple[str, ...] = ()
    observed_sha256: str | None = None


@dataclass(frozen=True)
class ItemFact:
    key: c.Key
    roles: tuple[str, ...]
    namespaces: tuple[str, ...]
    expected_record_sha256: str
    observed_record_sha256: str
    envelopes: tuple[EnvelopeFact, ...]
    presence: str
    integrity: str = NE
    authenticity: str = NE
    issuer_authorization: str = NE
    genuine_but_revoked: bool | str = NE
    consumption: str = NE
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)


@dataclass(frozen=True)
class QualificationFact:
    namespace: str
    qualification_record_sha256: str | None
    statement: s.StatementFact = field(default_factory=s.StatementFact)
    scientific: s.StatementFact = field(default_factory=s.StatementFact)


@dataclass(frozen=True)
class ConsumptionFact:
    namespace: str
    status: str = NE
    comparison: str = NE
    codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationAttestations:
    child_agent_id: str
    operation_sha256: str
    attempt: int
    latest: bool
    source_state: str
    branch: tuple[str, ...] = ()
    needs: tuple[NeedFact, ...] = ()
    items: tuple[ItemFact, ...] = ()
    qualifications: tuple[QualificationFact, ...] = ()
    consumptions: tuple[ConsumptionFact, ...] = ()
    decision_partition: str = NE
    branch_structure: str = NE
    branch_attestations: str = NE
    statements: str = NE
    scientific_bindings: str = NE
    known_identity_exclusions: str = NE
    blockers: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    authorization: str = field(default=NE, init=False)
    completeness: str = field(default=NE, init=False)
    population: str = field(default=NE, init=False)
    ceilings: str = field(default=NE, init=False)
    durability: str = field(default=NE, init=False)
    rotation: str = field(default=NE, init=False)
    recovery: str = field(default=NE, init=False)
    source_revision_provenance: str = field(default=NE, init=False)
    population_partition: str = field(default=NE, init=False)
    global_identity_exclusions: str = field(default=NE, init=False)


@dataclass(frozen=True)
class AttestationLimits(p.Limits):
    branch_nodes: int = 9
    checkout_bytes: int = 32 * 1024 * 1024
    checkout_file_bytes: int = 16 * 1024 * 1024
    checkout_files: int = 4096
    checkout_entries: int = 8192


@dataclass(frozen=True)
class AttestationEvidence:
    status: str
    blockers: tuple[str, ...]
    sources: tuple = ()
    metadata_sources: tuple[p.MetadataStamp, ...] = ()
    operations: tuple[OperationAttestations, ...] = ()
    physical_operations: tuple[p.OperationEvidence, ...] = ()
    pending_operations: tuple[str, ...] = ()
    ledger_bytes: bytes | None = None
    ledger_coverage: p.LedgerCoverage = field(default_factory=p.LedgerCoverage)
    limits: AttestationLimits = field(default_factory=AttestationLimits)
    schema: str = field(default="colony-admission.attestation-evidence/0", init=False)
    accepted: bool = field(default=False, init=False)
    authorization: str = field(default=NE, init=False)
    completeness: str = field(default=NE, init=False)
    population: str = field(default=NE, init=False)
    ceilings: str = field(default=NE, init=False)
    durability: str = field(default=NE, init=False)
    rotation: str = field(default=NE, init=False)
    recovery: str = field(default=NE, init=False)
    source_revision_provenance: str = field(default=NE, init=False)
    decision_partition: str = field(default=NE, init=False)
    branch_structure: str = field(default=NE, init=False)
    branch_attestations: str = field(default=NE, init=False)
    statements: str = field(default=NE, init=False)
    scientific_bindings: str = field(default=NE, init=False)
    known_identity_exclusions: str = field(default=NE, init=False)
    population_partition: str = field(default=NE, init=False)
    global_identity_exclusions: str = field(default=NE, init=False)


def aggregate(values):
    """A contradiction dominates a missing prerequisite; no empty subset PASS."""
    values = tuple(values)
    return "FAIL" if "FAIL" in values else "PASS" if values and all(x == "PASS" for x in values) else NE


def historical(op_bytes, source_state=NE):
    op = c.operation(op_bytes)
    return OperationAttestations(op["child_agent_id"], f.digest(op), op["attempt"], False,
        source_state, blockers=("HISTORICAL_ATTESTATIONS_NOT_EVALUATED",))


def _envelopes(required, envelopes):
    facts = []
    for namespace in required.namespaces:
        raw, digest = envelopes.get(namespace), None
        presence = "ABSENT" if raw is None else "DIVERGENT"
        if raw is not None:
            try:
                digest = f.digest(c.decode(raw, 16384))
                if required.envelope_sha256s == (digest,):
                    presence = "PRESENT_MATCH"
            except (c.CoreError, ValueError, TypeError, UnicodeError, RecursionError):
                pass
        facts.append(EnvelopeFact(namespace, presence, required.envelope_sha256s, digest))
    return tuple(facts)


def _candidate_consumption(op, raw, snapshots):
    namespace = op["child_agent_id"] + "/admission"
    if raw is None:
        return ConsumptionFact(namespace, codes=("EVIDENCE_NOT_STORED",))
    try:
        envelope = c.decode(raw, 16384)
        c.need(c.trust._envelope_shape(envelope) is None, "LEDGER_ENVELOPE_MISMATCH")
        digest, operation_digest = f.digest(envelope), f.digest(op)
        c.need(digest == op["presented"]["admission"]["envelope_sha256"], "LEDGER_ENVELOPE_MISMATCH")
        rows = []
        for op_raw, _, row_raw in snapshots:
            current = c.operation(op_raw)
            row = c.decode(row_raw)
            c.need(row.get("operation_sha256") == f.digest(current), "LEDGER_OPERATION_MISMATCH")
            if f.digest(current) == operation_digest:
                rows.append(row)
            entry = row.get("entry")
            if type(entry) is dict and (entry.get("issuer_id"), entry.get("envelope_id")) == (
                    envelope["issuer_id"], envelope["envelope_id"]):
                if entry.get("operation_sha256") != operation_digest:
                    return ConsumptionFact(namespace, "CONSUMED_BY_OTHER_OPERATION", "FAIL",
                                           ("LEDGER_ENVELOPE_MISMATCH",))
        c.need(len(rows) == 1, "LEDGER_OPERATION_MISMATCH")
        row = rows[0]
        if row.get("status") == "NO_OPERATION_ENTRY":
            c.need(type(row.get("operation_entries")) is int and row["operation_entries"] == 0,
                   "LEDGER_UNAVAILABLE")
            return ConsumptionFact(namespace, "NOT_CONSUMED", "PASS")
        c.need(row.get("status") == "OPERATION_ENTRY_PRESENT" and type(row.get("operation_entries")) is int
               and row["operation_entries"] == 1, "LEDGER_UNAVAILABLE")
        entry = row["entry"]
        c.need(entry.get("ledger_schema") == c.trust.OPERATION_LEDGER_SCHEMA
               and entry.get("operation_sha256") == operation_digest
               and entry.get("envelope_sha256") == digest
               and entry.get("issuer_id") == envelope["issuer_id"]
               and entry.get("envelope_id") == envelope["envelope_id"], "LEDGER_ENVELOPE_MISMATCH")
        return ConsumptionFact(namespace, "CONSUMED_BY_THIS_OPERATION", "PASS")
    except c.CoreError as exc:
        return ConsumptionFact(namespace, comparison="FAIL", codes=(str(exc),))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return ConsumptionFact(namespace, comparison="FAIL", codes=("LEDGER_UNAVAILABLE",))


def _qualification(namespace, statement_raw, q_raw, envelopes, artifacts, subject_digest, evaluator_digest):
    fact = s.statement(statement_raw, q_raw, envelopes.get(namespace + "/qualification"),
                       envelopes.get(namespace + "/statement"))
    scientific = s.StatementFact(codes=("EVIDENCE_NOT_STORED",) if fact.status == NE else ())
    digest = None
    try:
        if q_raw is not None:
            digest = f.digest(c.decode(q_raw))
        if fact.status == "PASS":
            statement = c.decode(statement_raw, 16384)
            paths = (s.CRITERIA_PATH, s.EVIDENCE_PATH) + ((s.HISTORY_PATH,) if statement["scope"] == s.PRESENT else ())
            selected = {path: artifacts.get(path) for path in paths}
            scientific = s.scientific_bindings(statement_raw, q_raw, selected, subject_digest, evaluator_digest)
    except (c.CoreError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        scientific = s.StatementFact("FAIL", ("SCIENTIFIC_DIVERGENCE",))
    return QualificationFact(namespace, digest, fact, scientific)


def _exclusions(branch, partition, op, envelopes):
    if branch.status != "PASS":
        return ("FAIL", ()) if any(x in branch.codes for x in (
            "SELF_ADMISSION_DENIED", "SELF_QUALIFICATION_DENIED")) else (NE, ())
    excluded = branch.agent_ids + (op["child_agent_id"],)
    states, codes = [], []
    for required in partition.needs:
        for namespace in required.namespaces:
            raw = envelopes.get(namespace)
            if raw is None:
                states.append(NE)
                continue
            try:
                envelope = c.decode(raw, 16384)
                c.need(c.trust._envelope_shape(envelope) is None, "FROZEN_ITEM_DIVERGENT")
                issuer = envelope["issuer_id"]
                if any(agent[:16] in issuer for agent in excluded):
                    states.append("FAIL")
                    codes.append("SELF_ADMISSION_DENIED" if required.key.kind == c.ADM
                                 else "SELF_QUALIFICATION_DENIED")
                else:
                    states.append("PASS")
            except (c.CoreError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                states.append(NE)
    return aggregate(states), p.unique(codes)


def project(op_bytes, nodes, statement_raw, envelopes, operation_snapshots, root_bytes, *,
            root_pin, minimum_version, lab_id, policy_bytes, policy_pin, artifacts=None,
            subject_digest=None, evaluator_digest=None, latest=True, source_state=NE,
            ledger_complete=True):
    """Project the whole named local proof; never qualify a partially valid branch."""
    if not latest:
        return historical(op_bytes, source_state)
    op = c.operation(op_bytes)
    branch = c.branch(op_bytes, nodes, policy_bytes, policy_pin)
    partition = c.decision_partition(op_bytes, nodes, branch, statement_raw, policy_bytes, policy_pin)
    codes = list(branch.codes + partition.codes)
    items, qualifications, consumptions = [], [], []
    excluded, exclusion_codes = _exclusions(branch, partition, op, envelopes)
    codes.extend(exclusion_codes)
    if branch.status == "PASS":
        qualifications.append(_qualification(op["child_agent_id"], statement_raw,
            f.canonical(op["birth_plan"]["qualification"]), envelopes, artifacts or {},
            subject_digest, evaluator_digest))
        consumptions.append(_candidate_consumption(op, envelopes.get(op["child_agent_id"] + "/admission"),
                                                   operation_snapshots))
        if not ledger_complete and consumptions[-1].status == "NOT_CONSUMED":
            # An unbound ledger row could consume this envelope under an
            # uninventoried operation. Absence of this operation is insufficient.
            consumptions[-1] = replace(consumptions[-1], status=NE, comparison=NE,
                                      codes=("LEDGER_OPERATION_UNBOUND",))
        for node in sorted(nodes, key=lambda n: n.agent_id):
            if c.decode(node.record_bytes)["role"] == "FOUNDER":
                continue
            qualifications.append(_qualification(node.agent_id, node.statement_bytes, node.qualification_bytes,
                envelopes, artifacts or {}, subject_digest, evaluator_digest))
            status, errors = c.ancestor_commit(node, operation_snapshots, envelopes.get(node.agent_id + "/admission"))
            consumptions.append(ConsumptionFact(node.agent_id + "/admission",
                "ANCESTOR_CONSUMED" if status == "PASS" else NE, status, errors))
    consumption_by_namespace = {x.namespace: x for x in consumptions}
    for required in partition.needs:
        envelope_facts = _envelopes(required, envelopes)
        fact = c.item_fact(required, tuple(envelopes.get(x) for x in required.namespaces), root_bytes,
            pin_sha256=root_pin, minimum_version=minimum_version, lab_id=lab_id)
        consumptions_for_item = [consumption_by_namespace[n].status for n in required.namespaces
                                 if n in consumption_by_namespace]
        consumption = consumptions_for_item[0] if len(set(consumptions_for_item)) == 1 else NE
        frozen_roles = tuple(sorted({x["role"] for x in op["items"] if c.Key(x["kind"], x["subject"]["agent_id"],
            x["subject"]["agent_spec_id"], x["record_sha256"]) == required.key}))
        items.append(ItemFact(required.key, frozen_roles, required.namespaces, required.key.record_sha256,
            required.key.record_sha256, envelope_facts, fact.presence, fact.integrity, fact.authenticity,
            fact.issuer_authorization, fact.genuine_but_revoked, consumption, fact.codes))
        codes.extend(fact.codes)
    statement_status = aggregate(x.statement.status for x in qualifications)
    scientific_status = aggregate(x.scientific.status for x in qualifications)
    for q in qualifications:
        codes.extend(q.statement.codes + q.scientific.codes)
    for consumption in consumptions:
        codes.extend(consumption.codes)
    item_states = [aggregate((x.integrity, x.authenticity, x.issuer_authorization)) for x in items]
    complete = aggregate((branch.status, partition.status, excluded, statement_status, scientific_status,
                          aggregate(item_states), aggregate(x.comparison for x in consumptions)))
    if complete != "PASS" and not codes:
        codes.append("ATTESTATION_MISSING")
    return OperationAttestations(op["child_agent_id"], f.digest(op), op["attempt"], True, source_state,
        branch.agent_ids, tuple(NeedFact(n.key, n.namespaces, n.envelope_sha256s) for n in partition.needs),
        tuple(items), tuple(qualifications), tuple(consumptions), partition.status, branch.status, complete,
        statement_status, scientific_status, excluded, p.unique(codes))
