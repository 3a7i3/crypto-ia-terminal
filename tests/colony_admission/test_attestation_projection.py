"""Detached LAB_TEST projection proofs: each missing or contradictory fact blocks."""

import copy
import dataclasses

import pytest

from colony_admission import _attestation_core as c
from colony_admission import _attestation_statement as s
from colony_admission import attestation_evidence as a
from colony_admission import formats as f
from colony_lab import lineage
from colony_lab.qualification import sentinel_spec
from colony_registrar import registrar as reg
from tests.colony_admission import test_attestation_core as helpers
from tests.colony_lab import builders as b
from tests.colony_trust.keys import ADMITTER, LAB, OPERATOR, REVIEWER, pin, root


@pytest.fixture
def complete():
    artifacts = {path: (helpers.ROOT / path).read_bytes() for path in (
        s.CRITERIA_PATH, s.EVIDENCE_PATH, s.HISTORY_PATH)}
    criteria = c.decode(artifacts[s.CRITERIA_PATH])
    spec = sentinel_spec(criteria["subject"])
    parent = lineage.make_founder(spec, lab_permissions=criteria["subject"]["lab_permissions"], budget=dict(b.BUDGET))
    q = c.decode(artifacts[s.HISTORY_PATH])
    q.update(reviewer_kind="EXTERNAL_REVIEW_PROCESS", reviewer_id=REVIEWER)
    st = helpers.statement(q, s.PRESENT)
    st.update(historical_record_path=s.HISTORY_PATH, historical_record_sha256=s.HISTORY_PIN,
              campaign_replayed=False, campaign_evidence_sha256=None)
    policy = reg.load_policy()[0]
    policy_bytes, policy_pin = f.canonical(policy), f.digest(policy)
    child_spec = b.spec(name="fixture_projection_child")
    child = lineage.make_descendant(parent, spec, child_spec, parent_qualification=q,
        lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=dict(b.BUDGET), declared_diff=lineage.spec_diff(spec, child_spec))
    admission = helpers.admission(child, parent, q, policy_pin)
    op = helpers.make_operation(parent, child, child_spec, q, admission, st)
    current_root = root()
    current_root["issuers"][1]["scopes"] = sorted((c.QUAL, c.STATEMENT))
    envelopes = {}
    records = ((c.IND, parent, parent["agent_id"], "individual", OPERATOR, "operator-1"),
               (c.ADM, admission, child["agent_id"], "admission", ADMITTER, "admitter-1"),
               (c.QUAL, q, child["agent_id"], "qualification", REVIEWER, "reviewer-1"),
               (c.STATEMENT, st, child["agent_id"], "statement", REVIEWER, "reviewer-1"))
    op["items"] = []
    for kind, record, namespace, role, issuer, key in records:
        envelope = helpers.signed(record, kind, issuer, label=role, key_label=key)
        envelopes[namespace + "/" + role] = f.canonical(envelope)
        op["items"].append(helpers.item(kind, record, env=f.digest(envelope)))
        if role != "individual":
            op["presented"][role]["envelope_sha256"] = f.digest(envelope)
    helpers.sort_items(op)
    nodes = (c.Node(parent["agent_id"], f.canonical(parent), f.canonical(spec)),)
    row = {"status": "NO_OPERATION_ENTRY", "operation_sha256": f.digest(op), "operation_entries": 0, "entry": None}
    return dict(op_bytes=f.canonical(op), nodes=nodes, statement_raw=f.canonical(st), envelopes=envelopes,
        operation_snapshots=((f.canonical(op), None, f.canonical(row)),), root_bytes=f.canonical(current_root),
        root_pin=pin(current_root), minimum_version=1, lab_id=LAB, policy_bytes=policy_bytes, policy_pin=policy_pin,
        artifacts=artifacts, subject_digest=s.SUBJECT_PIN, evaluator_digest=s.EVALUATOR_PIN, source_state="OPEN")


def test_complete_current_profile_has_only_local_pass_and_immutable_public_data(complete):
    result = a.project(**complete)
    assert result.blockers == ()
    assert result.branch_attestations == result.decision_partition == result.statements == "PASS"
    assert result.scientific_bindings == result.known_identity_exclusions == "PASS"
    assert result.consumptions[0].status == "NOT_CONSUMED"
    assert result.accepted is False
    assert result.authorization == result.population == result.ceilings == result.source_revision_provenance == a.NE
    assert all(x.integrity == x.authenticity == x.issuer_authorization == "PASS" for x in result.items)
    assert not any(hasattr(n, "record_bytes") for n in result.needs)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.items[0].authenticity = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.accepted = True
    serialized = dataclasses.asdict(result)
    assert not any(type(x) is bytes for x in serialized.values())
    complete["envelopes"].clear()
    complete["artifacts"].clear()
    assert result.blockers == ()  # no references to mutable caller mappings


@pytest.mark.parametrize("role", ["individual", "admission", "qualification", "statement"])
def test_missing_any_envelope_leaves_proof_incomplete(complete, role):
    namespace = next(n for n in complete["envelopes"] if n.endswith("/" + role))
    del complete["envelopes"][namespace]
    result = a.project(**complete)
    assert result.branch_attestations != "PASS" and "ATTESTATION_MISSING" in result.blockers
    missing = next(i for i in result.items if namespace in i.namespaces)
    assert missing.authenticity == missing.genuine_but_revoked == a.NE


@pytest.mark.parametrize("change", ["statement", "source", "subject_digest", "evaluator_digest", "empty_snapshot"])
def test_semantic_bindings_and_ledger_are_required(complete, change):
    if change == "statement":
        st = c.decode(complete["statement_raw"])
        st["issuer_root_version"] = True
        complete["statement_raw"] = f.canonical(st)
    elif change == "source":
        complete["artifacts"][s.EVIDENCE_PATH] += b"\n"
    elif change == "empty_snapshot":
        complete["operation_snapshots"] = ()
    else:
        complete[change] = "f" * 64
    result = a.project(**complete)
    assert result.branch_attestations != "PASS" and result.blockers


def test_revoked_envelope_is_genuine_but_never_complete(complete):
    envelope = c.decode(next(iter(complete["envelopes"].values())))
    current = c.decode(complete["root_bytes"])
    current["revoked_envelopes"] = [envelope["envelope_id"]]
    complete.update(root_bytes=f.canonical(current), root_pin=pin(current))
    result = a.project(**complete)
    item = next(i for i in result.items if i.genuine_but_revoked is True)
    assert item.integrity == item.issuer_authorization == "PASS"
    assert result.branch_attestations == "FAIL"


def test_individual_issuer_identity_is_excluded_even_with_valid_signature(complete):
    op = c.operation(complete["op_bytes"])
    parent = c.decode(complete["nodes"][0].record_bytes)
    issuer = "operator-" + parent["agent_id"][:16]
    current = c.decode(complete["root_bytes"])
    current["issuers"][2]["issuer_id"] = issuer
    envelope = helpers.signed(parent, c.IND, issuer, label="self-individual", key_label="operator-1")
    complete["envelopes"][parent["agent_id"] + "/individual"] = f.canonical(envelope)
    next(x for x in op["items"] if x["kind"] == c.IND)["envelope_sha256"] = f.digest(envelope)
    row = {"status": "NO_OPERATION_ENTRY", "operation_entries": 0, "entry": None, "operation_sha256": f.digest(op)}
    complete.update(op_bytes=f.canonical(op), root_bytes=f.canonical(current), root_pin=pin(current),
                    operation_snapshots=((f.canonical(op), None, f.canonical(row)),))
    result = a.project(**complete)
    assert all(i.integrity == i.authenticity == i.issuer_authorization == "PASS" for i in result.items)
    assert result.known_identity_exclusions == result.branch_attestations == "FAIL"
    assert result.blockers == ("SELF_QUALIFICATION_DENIED",)


def test_unknown_profile_keeps_trust_facts_but_no_scientific_pass(complete):
    op, st = c.operation(complete["op_bytes"]), c.decode(complete["statement_raw"])
    q = op["birth_plan"]["qualification"]
    q["criteria_sha256"] = "dcc3fe71909117ee2501ff3c5d2f8866f5343123929af40e06484a8ebf713ef7"
    st.update(criteria_sha256=q["criteria_sha256"], qualification_record_sha256=f.digest(q))
    admission = op["birth_plan"]["admission"]
    admission["parent_qualification_sha256"] = f.digest(q)
    child = op["child_agent_id"]
    op["items"] = [x for x in op["items"] if x["kind"] == c.IND]
    for role, kind, record, issuer, label in (("admission", c.ADM, admission, ADMITTER, "admitter-1"),
            ("qualification", c.QUAL, q, REVIEWER, "reviewer-1"),
            ("statement", c.STATEMENT, st, REVIEWER, "reviewer-1")):
        envelope = helpers.signed(record, kind, issuer, label="unknown-" + role, key_label=label)
        complete["envelopes"][child + "/" + role] = f.canonical(envelope)
        op["items"].append(helpers.item(kind, record, env=f.digest(envelope)))
        op["presented"][role] = {"record_sha256": f.digest(record), "envelope_sha256": f.digest(envelope)}
    helpers.sort_items(op)
    row = {"status": "NO_OPERATION_ENTRY", "operation_entries": 0, "entry": None, "operation_sha256": f.digest(op)}
    complete.update(op_bytes=f.canonical(op), statement_raw=f.canonical(st),
                    operation_snapshots=((f.canonical(op), None, f.canonical(row)),))
    result = a.project(**complete)
    assert result.scientific_bindings == a.NE
    assert result.blockers == ("SCIENTIFIC_PROFILE_UNSUPPORTED",)
    assert result.branch_structure == result.decision_partition == result.statements == "PASS"
    assert all(i.integrity == i.authenticity == i.issuer_authorization == "PASS" for i in result.items)
    assert result.branch_attestations == a.NE


def test_historical_operation_never_reuses_current_objects(complete):
    complete.update(latest=False)
    result = a.project(**complete)
    assert not result.latest
    assert result.blockers == ("HISTORICAL_ATTESTATIONS_NOT_EVALUATED",)
    assert result.items == result.branch == result.qualifications == result.consumptions == ()
    assert result.branch_attestations == result.statements == result.scientific_bindings == a.NE


@pytest.mark.parametrize("mode", ["this", "other", "wrong_envelope", "conflict", "boolean_count"])
def test_consumption_requires_exact_single_operation_entry(complete, mode):
    op = c.operation(complete["op_bytes"])
    namespace = op["child_agent_id"] + "/admission"
    envelope = c.decode(complete["envelopes"][namespace])
    entry = {"ledger_schema": c.trust.OPERATION_LEDGER_SCHEMA, "issuer_id": envelope["issuer_id"],
        "envelope_id": envelope["envelope_id"], "envelope_sha256": f.digest(envelope), "operation_sha256": f.digest(op)}
    row = {"status": "OPERATION_ENTRY_PRESENT", "operation_sha256": f.digest(op), "operation_entries": 1,
           "entry": entry}
    if mode == "other":
        other = copy.deepcopy(op)
        other["attempt"] = 2
        row.update(operation_sha256=f.digest(other))
        row["entry"]["operation_sha256"] = f.digest(other)
        snapshots = ((f.canonical(op), None, f.canonical({"status": "NO_OPERATION_ENTRY",
            "operation_sha256": f.digest(op), "operation_entries": 0, "entry": None})),
            (f.canonical(other), "COMMITTED", f.canonical(row)))
    else:
        if mode == "wrong_envelope":
            row["entry"]["envelope_sha256"] = "f" * 64
        elif mode == "conflict":
            row["status"] = "CONFLICT"
        elif mode == "boolean_count":
            row["operation_entries"] = True
        snapshots = ((f.canonical(op), None, f.canonical(row)),)
    complete["operation_snapshots"] = snapshots
    result = a.project(**complete)
    if mode == "this":
        assert result.consumptions[0].status == "CONSUMED_BY_THIS_OPERATION"
        assert result.branch_attestations == "PASS"
    else:
        assert result.consumptions[0].comparison == "FAIL"
        assert result.branch_attestations == "FAIL"


@pytest.mark.parametrize("values,expected", [([], a.NE), (["PASS"], "PASS"), ([a.NE, "PASS"], a.NE),
                                           ([a.NE, "FAIL"], "FAIL"), (["PASS", "FAIL"], "FAIL")])
def test_fail_dominates_missing_prerequisites_without_empty_pass(values, expected):
    assert a.aggregate(values) == expected


def test_unbound_ledger_cannot_establish_candidate_envelope_not_consumed(complete):
    complete['ledger_complete'] = False
    result = a.project(**complete)
    assert result.consumptions[0].status == a.NE
    assert result.branch_attestations == a.NE
    assert 'LEDGER_OPERATION_UNBOUND' in result.blockers
