"""Founder, descendant and lineage rules; no permission is ever inherited."""

import copy

import pytest

from colony_lab import a1_identity as a1
from colony_lab import lineage
from tests.colony_lab.builders import BUDGET, archivist_spec, founder, qualification, seal, spec


def child(parent_record, parent_spec, child_spec=None, **overrides):
    child_spec = child_spec or archivist_spec()
    args = {"parent_qualification": qualification(parent_record), "lab_permissions": ["GOVERNED_ARTIFACT_READ"],
            "budget": dict(BUDGET), "declared_diff": lineage.spec_diff(parent_spec, child_spec)}
    args.update(overrides)
    return lineage.make_descendant(parent_record, parent_spec, child_spec, **args), child_spec


def test_founder_record_keeps_a1_identities_and_claims_nothing_more():
    body, record = founder()
    assert record["agent_id"] == body["agent_id"] and record["agent_spec_id"] == body["agent_spec_id"]
    assert record["lineage"] == {"lineage_id": lineage.lineage_id(body["agent_id"]),
                                 "founder_agent_id": body["agent_id"], "parent_agent_id": None,
                                 "parent_agent_spec_id": None, "generation": 0}
    assert record["registry"] == {"availability": "NON_DEPLOYED", "state": "NOT_AVAILABLE"}
    assert record["credentials"] == "NONE" and record["operational_authority"] == "DENIED"
    assert record["memory"] == {"kind": "OWN_J01_JOURNAL", "inherits_parent_memory": False}
    lineage.verify_record(record, body)


def test_descendant_has_its_own_identity_lineage_and_declared_genotype():
    body, parent = founder()
    record, child_spec = child(parent, body)
    assert record["agent_id"] != parent["agent_id"]
    assert record["lineage"]["founder_agent_id"] == parent["agent_id"]
    assert record["lineage"]["parent_agent_id"] == parent["agent_id"] and record["lineage"]["generation"] == 1
    assert record["genotype"] == {"base_agent_spec_id": parent["agent_spec_id"],
                                  "declared_diff": ["agent_class", "capabilities", "scope_policy"]}
    lineage.verify_record(record, child_spec, parent, body)


@pytest.mark.parametrize("override,code", [
    ({"parent_qualification": None}, "QUALIFICATION_INVALID"),
    ({"lab_permissions": None}, "PERMISSIONS_NOT_DECLARED"),
    ({"lab_permissions": ["GOVERNED_ARTIFACT_READ", "REPOSITORY_READ"]}, "PERMISSION_OUTSIDE_SPEC"),
    ({"lab_permissions": ["SECRET_VALUE_READ"]}, "PERMISSION_NOT_GRANTABLE"),
    ({"declared_diff": ["capabilities"]}, "UNDECLARED_MUTATION"),
    ({"budget": {**BUDGET, "cpu_seconds": 10_000}}, "BUDGET_INVALID"),
    ({"budget": {**BUDGET, "runs": True}}, "BUDGET_INVALID"),
])
def test_descendant_refusals(override, code):
    body, parent = founder()
    with pytest.raises(lineage.LineageError) as err:
        child(parent, body, **override)
    assert err.value.code == code


@pytest.mark.parametrize("state", ["UNQUALIFIED", "IN_TRIAL", "FAILED", "REVOKED", "QUALIFIED"])
def test_no_descendant_before_the_parent_is_qualified(state):
    body, parent = founder()
    with pytest.raises(lineage.LineageError) as err:
        child(parent, body, parent_qualification=qualification(parent, state=state))
    assert err.value.code == "PARENT_NOT_QUALIFIED"


@pytest.mark.parametrize("reviewer,kind", [
    ("self", "EXTERNAL_REVIEW_PROCESS"), ("", "EXTERNAL_HUMAN"), ("someone", "PEER_AGENT"), ("someone", "SELF"),
    ("SELF", "EXTERNAL_REVIEW_PROCESS"), ("prefix", "EXTERNAL_HUMAN"), ("child", "EXTERNAL_REVIEW_PROCESS"),
    ("Fixture Reviewer", "EXTERNAL_HUMAN"),
])
def test_self_or_agent_qualification_is_refused(reviewer, kind):
    body, parent = founder()
    child_id = a1.agent_id("forest", "archivist_01", "DATA_STEWARD")
    reviewer = {"self": parent["agent_id"], "SELF": parent["agent_id"].upper(),
                "prefix": "fixture-ind-" + parent["agent_id"][:16], "child": "reviewer-" + child_id[:16]}.get(
        reviewer, reviewer)
    with pytest.raises(lineage.LineageError, match="SELF_QUALIFICATION_DENIED"):
        child(parent, body, parent_qualification=qualification(parent, reviewer=reviewer, kind=kind))


def test_qualification_of_another_spec_revision_is_refused():
    body, parent = founder()
    stale = qualification(parent)
    stale["agent_spec_id"] = "f" * 64
    with pytest.raises(lineage.LineageError, match="QUALIFICATION_NOT_FOR_THIS_SPEC"):
        child(parent, body, parent_qualification=stale)


def test_permissions_are_never_inherited_nor_escalated():
    body, parent = founder(permissions=["DIAGNOSTIC_PRODUCE"])
    with pytest.raises(lineage.LineageError, match="PERMISSION_ESCALATION"):
        child(parent, body)  # GOVERNED_ARTIFACT_READ is in the child's spec, not granted to the parent
    body, parent = founder()
    record, _ = child(parent, body, lab_permissions=[])
    assert record["lab_permissions"] == []  # nothing copied from the parent


def test_a_child_cannot_reuse_the_parent_identity():
    body, parent = founder()
    clone = copy.deepcopy(body)
    clone["display_name"] = "Sentinel Clone"
    with pytest.raises(lineage.LineageError, match="SAME_IDENTITY_AS_PARENT"):
        child(parent, body, child_spec=seal(clone), lab_permissions=["DIAGNOSTIC_PRODUCE"])


def test_coordinator_or_queen_names_grant_nothing():
    body = spec(name="reine_coordinatrice", display="Reine Coordinatrice")
    record = lineage.make_founder(body, lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=dict(BUDGET))
    assert record["operational_authority"] == "DENIED" and record["lab_permissions"] == ["DIAGNOSTIC_PRODUCE"]


@pytest.mark.parametrize("mutate,code", [
    (lambda r: r.update(lab_permissions=["DIAGNOSTIC_PRODUCE", "GOVERNED_ARTIFACT_READ", "REPOSITORY_READ"]),
     "RECORD_HASH_MISMATCH"),
    (lambda r: r.update(credentials="API_KEY"), "RECORD_HASH_MISMATCH"),
    (lambda r: r.pop("budget"), "RECORD_SCHEMA_VIOLATION"),
])
def test_tampered_records_are_refused(mutate, code):
    body, record = founder()
    mutate(record)
    with pytest.raises(lineage.LineageError) as err:
        lineage.verify_record(record, body)
    assert err.value.code == code


def test_rehashed_record_still_cannot_claim_authority_or_registry():
    body, record = founder()
    for field, value in (("operational_authority", "GRANTED"), ("registry", {"availability": "DEPLOYED",
                                                                              "state": "REGISTERED"})):
        forged = copy.deepcopy(record)
        forged[field] = value
        forged["record_hash"] = lineage._record_hash(forged)
        with pytest.raises(lineage.LineageError, match="RECORD_SCHEMA_VIOLATION"):
            lineage.verify_record(forged, body)
