"""A1 identities recomputed by the lab equal the A1 golden vectors; refusals use A1 codes."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from colony_lab import a1_identity as a1
from colony_lab import a1_ref
from tests.colony_lab.builders import seal, spec

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
GOLDEN = json.loads((HERE / "a1_golden_FIXTURE_ONLY.json").read_text())


@pytest.mark.parametrize("name", sorted(GOLDEN["specs"]))
def test_lab_identities_equal_a1_golden_vectors(name):
    assert a1.check_spec(GOLDEN["specs"][name]) == GOLDEN["expected_identities"][name]


def test_capability_sets_match_the_a1_schema():
    schema = json.loads((ROOT / "docs/contracts/AGENT_ECON_A1_AGENT_SPEC_V1.schema.json").read_text())
    assert set(schema["properties"]["capabilities"]["items"]["enum"]) == a1.F2
    levels = {c["if"]["properties"]["maintenance_level"]["const"]: set(c["then"]["properties"]["capabilities"]
              ["items"]["enum"]) for c in schema["allOf"][:3]}
    assert levels == {name: set(caps) for name, caps in a1.LEVEL_CAPABILITIES.items()}
    ceilings = {}
    for clause in schema["allOf"][3:17]:
        cls = clause["if"]["properties"]["agent_class"]["const"]
        allowed = clause["then"]["properties"]["maintenance_level"]
        if allowed is not False:
            ceilings[cls] = max(allowed["enum"])
    assert ceilings == a1.CLASS_MAX_LEVEL


def test_lab_specs_validate_against_the_a1_schema():
    jsonschema = pytest.importorskip("jsonschema", reason="jsonschema is not in requirements-ci.txt")
    schema = json.loads((ROOT / "docs/contracts/AGENT_ECON_A1_AGENT_SPEC_V1.schema.json").read_text())
    for body in [spec(), *GOLDEN["specs"].values()]:
        jsonschema.Draft202012Validator(schema).validate(body)


@pytest.mark.parametrize("token,code", [
    ("SECRET_VALUE_READ", "FORBIDDEN_AUTHORITY_REQUESTED"), ("RUNTIME_DEPLOY", "FORBIDDEN_AUTHORITY_REQUESTED"),
    ("MERGE_AUTHORIZATION", "FORBIDDEN_AUTHORITY_REQUESTED"), ("PR_PREPARE", "RESERVED_CAPABILITY"),
    ("GOVERNANCE_REVIEW", "RESERVED_CAPABILITY"), ("COORDINATE_COLONY", "UNKNOWN_CAPABILITY"),
])
def test_capability_tokens_are_refused_in_contract_order(token, code):
    body = spec(caps=sorted(["DIAGNOSTIC_PRODUCE", token]))
    with pytest.raises(a1.IdentityError) as err:
        a1.check_spec(seal(body))
    assert err.value.code == code


@pytest.mark.parametrize("mutate,code", [
    (lambda s: s.update(agent_class="SENSOR"), "CLASS_LEVEL_INADMISSIBLE"),
    (lambda s: s.update(agent_class="GOVERNANCE"), "CLASS_LEVEL_INADMISSIBLE"),
    (lambda s: s.update(maintenance_level="F3"), "CLASS_LEVEL_INADMISSIBLE"),
    (lambda s: s.update(maintenance_level="F1"), "CAPABILITY_ABOVE_CEILING"),
    (lambda s: s["authority_policy"].update(human_decision=True), "AUTHORITY_POLICY_VIOLATION"),
    (lambda s: s["execution_binding"].update(credential_mode="API_KEY"), "BINDING_NOT_UNBOUND"),
    (lambda s: s["independence_policy"].update(own_work_review_forbidden=False), "INDEPENDENCE_POLICY_VIOLATION"),
    (lambda s: s["scope_policy"].update(artifact_domains=[]), "SPEC_SCHEMA_VIOLATION"),
    (lambda s: s["scope_policy"].update(repository_write_paths_future=["docs/"]), "SPEC_SCHEMA_VIOLATION"),
    (lambda s: s["capabilities"].remove("GITHUB_METADATA_READ")
     or s["scope_policy"].update(github_surfaces=["ISSUES"]), "SCOPE_CAPABILITY_INCOHERENT"),  # AS-13
    (lambda s: s.update(spec_revision=2), "SUPERSESSION_BREAK"),
    (lambda s: s.update(spec_revision=True), "SPEC_NUMERIC_AMBIGUITY"),
    (lambda s: s.update(capabilities=list(reversed(s["capabilities"]))), "SPEC_ARRAY_NOT_CANONICAL"),
    (lambda s: s.update(purpose=" padded purpose that is long enough "), "SPEC_TEXT_NOT_CANONICAL"),
])
def test_spec_ceilings_and_policies(mutate, code):
    body = spec()
    mutate(body)
    seal(body)
    with pytest.raises(a1.IdentityError) as err:
        a1.check_spec(body)
    assert err.value.code == code


def test_identity_is_recomputed_never_trusted():
    body = spec()
    forged = copy.deepcopy(body)
    forged["agent_id"] = "0" * 64
    with pytest.raises(a1.IdentityError, match="IDENTITY_MISMATCH"):
        a1.check_spec(forged)
    revised = copy.deepcopy(body)
    revised["display_name"] = "Sentinel One"
    with pytest.raises(a1.IdentityError, match="IDENTITY_MISMATCH"):
        a1.check_spec(revised)
    assert a1.check_spec(seal(revised))["agent_id"] == body["agent_id"]  # a revision keeps the individual


def test_secret_and_float_values_are_refused():
    body = spec()
    body["purpose"] = "Synthetic lab individual holding ghp_" + "a" * 36
    with pytest.raises(a1.IdentityError, match="LAB_SECRET_TEXT_REJECTED"):
        a1.check_spec(seal(body))  # lab rule, applied after A1 accepted the spec
    body = spec()
    body["spec_revision"] = 1.0
    with pytest.raises(a1.IdentityError, match="SPEC_NUMERIC_AMBIGUITY"):
        a1.check_spec(body)


def test_a1_rules_are_the_unchanged_pr374_code():
    root = Path(a1_ref.__file__).parent
    for name, pin in a1_ref.PROVENANCE["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == pin["sha256"], name
