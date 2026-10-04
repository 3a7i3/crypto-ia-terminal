"""AgentSpec V1: identities, capability classification, AS-01 ... AS-13."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from agent_economy.agent_registry import capabilities as caps
from agent_economy.agent_registry import spec as spec_module
from agent_economy.agent_registry.canonical import AgentRegistryError
from agent_economy.agent_registry.spec import (
    classify_revision,
    compute_agent_id,
    compute_agent_spec_id,
    compute_spec_artifact_bytes,
    compute_spec_artifact_hash,
    validate_agent_spec,
)
from tests.agent_economy._builders import make_scout_spec, make_spec, seal_spec

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs" / "contracts"
SPEC_SCHEMA = json.loads((CONTRACTS / "AGENT_ECON_A1_AGENT_SPEC_V1.schema.json").read_text("utf-8"))
CATALOG_MD = (CONTRACTS / "AGENT_ECON_A1_CAPABILITY_CATALOG.md").read_text("utf-8")

ALL_F2_CAPABILITIES = sorted(caps.CATALOG_V1)


def code_of(spec) -> str:
    with pytest.raises(AgentRegistryError) as caught:
        validate_agent_spec(spec)
    return caught.value.code


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_valid_f0_f1_f2_specs_are_accepted():
    sensor = make_spec()
    scout = make_scout_spec()
    curator = make_spec(
        canonical_name="fixture_curator_gamma",
        agent_class="CURATOR",
        level="F2",
        capabilities=ALL_F2_CAPABILITIES,
        read_paths=["docs/", "tests/agent_economy/fixtures/a.json"],
        surfaces=sorted(caps.GITHUB_SURFACES),
        domains=sorted(caps.ARTIFACT_DOMAINS),
        display_name="Fixture Curator Gamma",
    )
    for spec in (sensor, scout, curator):
        identities = validate_agent_spec(spec)
        assert identities.agent_id == spec["agent_id"]
        assert identities.agent_spec_id == spec["agent_spec_id"]
        assert identities.spec_artifact_hash == compute_spec_artifact_hash(spec)


def test_purpose_may_contain_a_newline_but_other_text_may_not():
    spec = make_spec(purpose="Synthetic fixture purpose.\nSecond line of the purpose.")
    validate_agent_spec(spec)
    spec = make_spec()
    spec["display_name"] = "Fixture\nSensor"
    assert code_of(seal_spec(spec)) == "SPEC_TEXT_NOT_CANONICAL"


def test_validation_does_not_mutate_the_caller_input():
    valid = make_scout_spec()
    before = copy.deepcopy(valid)
    validate_agent_spec(valid)
    assert valid == before
    invalid = make_spec()
    invalid["capabilities"] = ["REPOSITORY_READ", "CI_READ"]  # unsorted
    before = copy.deepcopy(invalid)
    assert code_of(invalid) == "SPEC_ARRAY_NOT_CANONICAL"
    assert invalid == before and invalid["capabilities"] == ["REPOSITORY_READ", "CI_READ"]


def test_a_non_object_or_empty_object_is_rejected():
    for bad in (None, [], "spec", 1, {}):
        assert code_of(bad) == "SPEC_SCHEMA_VIOLATION"


# ---------------------------------------------------------------------------
# Identity: agent_id
# ---------------------------------------------------------------------------


def test_agent_id_is_deterministic_and_matches_the_contract_formula():
    expected = hashlib.sha256(
        json.dumps(
            {
                "agent_identity_schema": "agent-econ.a1.agent-identity.v1",
                "namespace": "forest",
                "canonical_name": "fixture_sensor_alpha",
                "agent_class": "SENSOR",
            },
            ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert compute_agent_id("forest", "fixture_sensor_alpha", "SENSOR") == expected
    assert compute_agent_id("forest", "fixture_sensor_alpha", "SENSOR") == expected


def test_agent_id_ignores_revision_level_capabilities_and_provenance():
    first = make_spec()
    second = make_spec(
        revision=2,
        supersedes=first["agent_spec_id"],
        level="F0",
        capabilities=["GITHUB_METADATA_READ", "REPOSITORY_READ"],
        surfaces=["ISSUES"],
        display_name="Another display name",
        purpose="A different purpose text that is still long enough to be valid.",
        created_from_ref="f" * 40,
        created_at_utc="2030-01-01T00:00:00Z",
    )
    assert first["agent_id"] == second["agent_id"]
    assert first["agent_spec_id"] != second["agent_spec_id"]
    # the same logical fields under a different (future) spec schema keep the id
    future = copy.deepcopy(first)
    future["agent_schema"] = "AGENT_SPEC_V2"
    assert compute_agent_id(future["namespace"], future["canonical_name"], future["agent_class"]) == first["agent_id"]


def test_agent_id_changes_with_namespace_name_or_class():
    base = compute_agent_id("forest", "fixture_sensor_alpha", "SENSOR")
    assert compute_agent_id("other", "fixture_sensor_alpha", "SENSOR") != base
    assert compute_agent_id("forest", "fixture_sensor_beta", "SENSOR") != base
    assert compute_agent_id("forest", "fixture_sensor_alpha", "SCOUT") != base


# ---------------------------------------------------------------------------
# Identity: agent_spec_id and the artifact hash (R1.1)
# ---------------------------------------------------------------------------


def test_spec_id_same_material_different_provenance_is_the_same_id():
    one = make_spec(created_from_ref="a" * 40, created_at_utc="2026-10-04T00:00:00Z")
    two = make_spec(created_from_ref="b" * 40, created_at_utc="2031-05-06T07:08:09.5Z")
    assert one["agent_spec_id"] == two["agent_spec_id"]
    assert compute_agent_spec_id(one) == compute_agent_spec_id(two)
    one["agent_spec_id"] = "0" * 64  # the id itself is excluded (no circularity)
    assert compute_agent_spec_id(one) == two["agent_spec_id"]


MATERIAL_MUTATIONS = {
    "agent_schema": lambda s: s.update(agent_schema="AGENT_SPEC_V2"),
    "constitution_version": lambda s: s.update(constitution_version="AGENT_ECON_A0_FOREST_V2"),
    "agent_id": lambda s: s.update(agent_id="1" * 64),
    "spec_revision": lambda s: s.update(spec_revision=2),
    "namespace": lambda s: s.update(namespace="other"),
    "canonical_name": lambda s: s.update(canonical_name="fixture_other"),
    "display_name": lambda s: s.update(display_name="Renamed"),
    "agent_class": lambda s: s.update(agent_class="SCOUT"),
    "maintenance_level": lambda s: s.update(maintenance_level="F1"),
    "purpose": lambda s: s.update(purpose="A changed purpose of sufficient length here."),
    "capabilities": lambda s: s.update(capabilities=["REPOSITORY_READ"]),
    "scope_policy": lambda s: s["scope_policy"].update(repository_read_paths=["tests/"]),
    "independence_policy": lambda s: s["independence_policy"].update(own_work_review_forbidden=False),
    "authority_policy": lambda s: s["authority_policy"].update(human_decision=True),
    "execution_binding": lambda s: s["execution_binding"].update(status="BOUND"),
    "supersedes_spec_id": lambda s: s.update(supersedes_spec_id="2" * 64),
}


@pytest.mark.parametrize("field", sorted(MATERIAL_MUTATIONS))
def test_spec_id_changes_for_every_material_field(field):
    spec = make_spec()
    mutated = copy.deepcopy(spec)
    MATERIAL_MUTATIONS[field](mutated)
    assert compute_agent_spec_id(mutated) != compute_agent_spec_id(spec)


def test_material_field_list_is_exactly_the_contract_list():
    expected = {
        "agent_schema", "constitution_version", "agent_id", "spec_revision", "namespace",
        "canonical_name", "display_name", "agent_class", "maintenance_level", "purpose",
        "capabilities", "scope_policy", "independence_policy", "authority_policy",
        "execution_binding", "supersedes_spec_id",
    }
    assert set(spec_module.SPEC_IDENTITY_FIELDS) == expected
    assert set(spec_module.SPEC_FIELDS) - expected == {
        "agent_spec_id", "created_from_ref", "created_at_utc",
    }
    assert set(MATERIAL_MUTATIONS) == expected


def test_spec_artifact_hash_exact_bytes():
    spec = make_spec()
    expected_bytes = (
        json.dumps(spec, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    assert compute_spec_artifact_bytes(spec) == expected_bytes
    assert compute_spec_artifact_hash(spec) == hashlib.sha256(expected_bytes).hexdigest()
    # provenance AND the agent_spec_id itself are inside the hashed bytes
    for needle in (spec["created_from_ref"], spec["created_at_utc"], spec["agent_spec_id"]):
        assert needle.encode() in expected_bytes
    assert expected_bytes.endswith(b"\n") and not expected_bytes.endswith(b"\n\n")


def test_spec_artifact_hash_provenance_sensitive():
    one = make_spec(created_at_utc="2026-10-04T00:00:00Z")
    two = make_spec(created_at_utc="2026-10-04T00:00:01Z")
    three = make_spec(created_from_ref="c" * 40)
    assert one["agent_spec_id"] == two["agent_spec_id"] == three["agent_spec_id"]
    hashes = {compute_spec_artifact_hash(s) for s in (one, two, three)}
    assert len(hashes) == 3
    material_change = make_spec(display_name="Different")
    assert compute_spec_artifact_hash(material_change) not in hashes


# ---------------------------------------------------------------------------
# Capability classification (four distinct outcomes)
# ---------------------------------------------------------------------------


def test_capability_sets_are_disjoint_and_sized_as_the_catalog():
    sets = {
        "catalog": caps.CATALOG_V1,
        "reserved": caps.RESERVED_CAPABILITIES,
        "forbidden": caps.FORBIDDEN_AUTHORITY_SET,
        "human_gate": caps.HUMAN_GATE,
    }
    assert [len(sets[k]) for k in sets] == [14, 10, 24, 6]
    names = list(sets)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            assert not (sets[left] & sets[right]), (left, right)


@pytest.mark.parametrize(
    "token,expected",
    [
        ("REPOSITORY_READ", caps.ALLOWED),
        ("PROBLEM_VERIFY", caps.ALLOWED),
        ("SOURCE_EDIT_ISOLATED", caps.RESERVED_CAPABILITY),  # F3 is known vocabulary
        ("BRANCH_PREPARE", caps.RESERVED_CAPABILITY),
        ("GOVERNANCE_REVIEW", caps.RESERVED_CAPABILITY),  # F4 too
        ("MAIN_MERGE", caps.FORBIDDEN_AUTHORITY_REQUESTED),
        ("EVIDENCE_MUTATE", caps.FORBIDDEN_AUTHORITY_REQUESTED),
        ("HUMAN_ACCEPT", caps.FORBIDDEN_AUTHORITY_REQUESTED),  # human gate: forbidden
        ("PROMOTION_AUTHORIZATION", caps.FORBIDDEN_AUTHORITY_REQUESTED),
        ("TELEPORT", caps.UNKNOWN_CAPABILITY),
        ("AGENT_REGISTRY_WRITE", caps.UNKNOWN_CAPABILITY),  # draft name, not an alias
        ("GATE_NEUTRALIZE", caps.UNKNOWN_CAPABILITY),
        ("repository_read", caps.UNKNOWN_CAPABILITY),  # case matters
        ("REPOSITORY_READ ", caps.UNKNOWN_CAPABILITY),
        ("", caps.UNKNOWN_CAPABILITY),
        (None, caps.UNKNOWN_CAPABILITY),
        (7, caps.UNKNOWN_CAPABILITY),
    ],
)
def test_capability_classification_never_collapses(token, expected):
    assert caps.classify_capability_token(token) == expected


@pytest.mark.parametrize(
    "token,code",
    [
        ("TELEPORT", "UNKNOWN_CAPABILITY"),
        ("AGENT_REGISTRY_WRITE", "UNKNOWN_CAPABILITY"),
        ("SOURCE_EDIT_ISOLATED", "RESERVED_CAPABILITY"),
        ("SECURITY_REVIEW", "RESERVED_CAPABILITY"),
        ("RUNTIME_DEPLOY", "FORBIDDEN_AUTHORITY_REQUESTED"),
        ("HUMAN_REJECT", "FORBIDDEN_AUTHORITY_REQUESTED"),
        ("AGENT_REGISTRY_MUTATE", "FORBIDDEN_AUTHORITY_REQUESTED"),
    ],
)
def test_spec_rejects_each_capability_class_with_its_own_code(token, code):
    spec = make_spec()
    spec["capabilities"] = sorted(["REPOSITORY_READ", "CI_READ", token])
    assert code_of(seal_spec(spec)) == code


def test_forbidden_is_not_reported_as_unknown_and_reserved_is_not_unknown():
    spec = make_spec()
    spec["capabilities"] = ["MAIN_MERGE"]
    assert code_of(seal_spec(spec)) != "UNKNOWN_CAPABILITY"
    spec["capabilities"] = ["PR_PREPARE"]
    assert code_of(seal_spec(spec)) != "UNKNOWN_CAPABILITY"


def test_f0_is_read_only_and_ceilings_are_cumulative():
    assert caps.LEVEL_CAPABILITIES["F0"] <= caps.LEVEL_CAPABILITIES["F1"] <= caps.LEVEL_CAPABILITIES["F2"]
    assert all(c.endswith(("_READ", "_SEARCH", "_ANALYSIS")) for c in caps.LEVEL_CAPABILITIES["F0"])
    sensor = make_spec(capabilities=["CANDIDATE_PROBLEM_PROPOSE"], read_paths=[], surfaces=[])
    assert code_of(sensor) == "CAPABILITY_ABOVE_CEILING"
    scout = make_scout_spec(capabilities=["CANDIDATE_PROBLEM_PROPOSE", "PROBLEM_VERIFY"])
    assert code_of(scout) == "CAPABILITY_ABOVE_CEILING"


# ---------------------------------------------------------------------------
# Negative table (AS-01 ... AS-13): each case builds the invalid input and
# validates it exactly as built.
# ---------------------------------------------------------------------------


def _set(path, value, reseal=False):
    def mutate(spec):
        target = spec
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return seal_spec(spec) if reseal else spec

    return mutate


def _drop(key):
    def mutate(spec):
        del spec[key]
        return spec

    return mutate


def _extra(spec):
    spec["surprise"] = 1
    return spec


def _extra_nested(spec):
    spec["scope_policy"]["extra"] = []
    return spec


def _paths(*paths):
    def mutate(spec):
        spec["scope_policy"]["repository_read_paths"] = list(paths)
        return seal_spec(spec)

    return mutate


NEGATIVE_CASES = [
    # AS-01 schema (S rules)
    ("AS-01 unknown field", _extra, "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 unknown nested field", _extra_nested, "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 missing field", _drop("purpose"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 missing explicit null", _drop("supersedes_spec_id"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 wrong agent_schema", _set(["agent_schema"], "AGENT_SPEC_V2"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 wrong constitution", _set(["constitution_version"], "X"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 other namespace", _set(["namespace"], "other", True), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 bad canonical_name", _set(["canonical_name"], "Bad-Name", True), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 short canonical_name", _set(["canonical_name"], "ab", True), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 long display_name", _set(["display_name"], "x" * 81, True), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 short purpose", _set(["purpose"], "too short", True), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 unknown class enum", _set(["agent_class"], "WIZARD", True), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 unknown level enum", _set(["maintenance_level"], "F9", True), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 level F5 (human is not F5)", _set(["maintenance_level"], "F5", True), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 branch name as ref", _set(["created_from_ref"], "main"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 short sha ref", _set(["created_from_ref"], "abc1234"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 uppercase sha ref", _set(["created_from_ref"], "A" * 40), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 created_at no Z", _set(["created_at_utc"], "2026-10-04T00:00:00"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 created_at impossible date", _set(["created_at_utc"], "2026-02-31T00:00:00Z"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 agent_id uppercase", _set(["agent_id"], "A" * 64), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 revision 0", _set(["spec_revision"], 0), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 revision string", _set(["spec_revision"], "1"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 revision too large", _set(["spec_revision"], 1_000_001), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 write paths not empty", _set(["scope_policy", "repository_write_paths_future"], ["docs/"]), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 capabilities empty", _set(["capabilities"], []), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 capabilities not a list", _set(["capabilities"], "CI_READ"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 unknown github surface", _set(["scope_policy", "github_surfaces"], ["CHECK_RUNS", "SECRETS"]), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 unknown artifact domain", _set(["scope_policy", "artifact_domains"], ["VPS_LOGS"]), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 absolute path", _paths("/etc/passwd"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 parent path", _paths("../x"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 inner parent path", _paths("docs/../x"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 double slash", _paths("docs//x"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 glob star", _paths("docs/*"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 glob question", _paths("docs/a?"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 glob bracket", _paths("docs/[a]"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 backslash", _paths("docs\\x"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 dot env", _paths(".env"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 dot env nested", _paths("cfg/.env.local"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 pem key", _paths("keys/server.pem"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 id_rsa", _paths("home/id_rsa"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 id_ed25519.pub", _paths("home/id_ed25519.pub"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 secrets dir", _paths("config/secrets/"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 secret file", _paths("config/secret"), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 empty path", _paths(""), "SPEC_SCHEMA_VIOLATION"),
    ("AS-01 coupling: read cap without paths", _paths(), "SPEC_SCHEMA_VIOLATION"),
    (
        "AS-01 coupling: surfaces without github cap",
        lambda s: (s.update(capabilities=["REPOSITORY_READ"]), seal_spec(s))[1],
        "SPEC_SCHEMA_VIOLATION",
    ),
    (
        "AS-01 coupling: domains without cap",
        _set(["scope_policy", "artifact_domains"], ["CI_ARTIFACTS"], True),
        "SPEC_SCHEMA_VIOLATION",
    ),
    (
        "AS-01 coupling: paths without read cap",
        lambda s: (s.update(capabilities=["CI_READ"]), seal_spec(s))[1],
        "SPEC_SCHEMA_VIOLATION",
    ),
    # AS-02 numbers
    ("AS-02 revision bool", _set(["spec_revision"], True), "SPEC_NUMERIC_AMBIGUITY"),
    ("AS-02 revision 1.0", _set(["spec_revision"], 1.0), "SPEC_NUMERIC_AMBIGUITY"),
    ("AS-02 revision float", _set(["spec_revision"], 2.5), "SPEC_NUMERIC_AMBIGUITY"),
    ("AS-02 NaN anywhere", _set(["scope_policy", "github_surfaces"], [float("nan")]), "SPEC_NUMERIC_AMBIGUITY"),
    ("AS-02 Infinity", _set(["display_name"], float("inf")), "SPEC_NUMERIC_AMBIGUITY"),
    # AS-03 text
    ("AS-03 non-NFC display", _set(["display_name"], "Café Sensor", True), "SPEC_TEXT_NOT_CANONICAL"),
    ("AS-03 non-NFC purpose", _set(["purpose"], "Un agent de test sans autorité réelle: éé", True), "SPEC_TEXT_NOT_CANONICAL"),
    ("AS-03 control char", _set(["purpose"], "Synthetic purpose with a \x00 control.", True), "SPEC_TEXT_NOT_CANONICAL"),
    ("AS-03 tab in display", _set(["display_name"], "Fixture\tSensor", True), "SPEC_TEXT_NOT_CANONICAL"),
    ("AS-03 trailing space display", _set(["display_name"], "Fixture Sensor ", True), "SPEC_TEXT_NOT_CANONICAL"),
    ("AS-03 leading space purpose", _set(["purpose"], " Synthetic purpose text long enough.", True), "SPEC_TEXT_NOT_CANONICAL"),
    ("AS-03 trailing newline purpose", _set(["purpose"], "Synthetic purpose text long enough.\n", True), "SPEC_TEXT_NOT_CANONICAL"),
    ("AS-03 CRLF purpose", _set(["purpose"], "Synthetic purpose.\r\nSecond line is fine here.", True), "SPEC_TEXT_NOT_CANONICAL"),
    # AS-04 arrays (never re-sorted)
    ("AS-04 unsorted capabilities", _set(["capabilities"], ["REPOSITORY_READ", "CI_READ"], True), "SPEC_ARRAY_NOT_CANONICAL"),
    ("AS-04 duplicate capabilities", _set(["capabilities"], ["CI_READ", "CI_READ", "REPOSITORY_READ"], True), "SPEC_ARRAY_NOT_CANONICAL"),
    ("AS-04 unsorted paths", _paths("tests/", "docs/"), "SPEC_ARRAY_NOT_CANONICAL"),
    ("AS-04 duplicate paths", _paths("docs/", "docs/"), "SPEC_ARRAY_NOT_CANONICAL"),
    ("AS-04 unsorted surfaces", _set(["scope_policy", "github_surfaces"], ["WORKFLOW_RUNS", "CHECK_RUNS"], True), "SPEC_ARRAY_NOT_CANONICAL"),
    ("AS-04 duplicate surfaces", _set(["scope_policy", "github_surfaces"], ["CHECK_RUNS", "CHECK_RUNS"], True), "SPEC_ARRAY_NOT_CANONICAL"),
    # AS-06 / AS-07 ceilings
    ("AS-06 F0 with proposal", _set(["capabilities"], ["CANDIDATE_PROBLEM_PROPOSE"], True), "CAPABILITY_ABOVE_CEILING"),
    ("AS-07 reserved level F3", _set(["maintenance_level"], "F3", True), "CLASS_LEVEL_INADMISSIBLE"),
    ("AS-07 reserved level F4", _set(["maintenance_level"], "F4", True), "CLASS_LEVEL_INADMISSIBLE"),
    ("AS-07 reserved class ENGINEER", _set(["agent_class"], "ENGINEER", True), "CLASS_LEVEL_INADMISSIBLE"),
    ("AS-07 reserved class GOVERNANCE", _set(["agent_class"], "GOVERNANCE", True), "CLASS_LEVEL_INADMISSIBLE"),
    ("AS-07 reserved class REVIEWER", _set(["agent_class"], "REVIEWER", True), "CLASS_LEVEL_INADMISSIBLE"),
    ("AS-07 reserved class TEST_VERIFIER", _set(["agent_class"], "TEST_VERIFIER", True), "CLASS_LEVEL_INADMISSIBLE"),
    ("AS-07 reserved class UX", _set(["agent_class"], "UX", True), "CLASS_LEVEL_INADMISSIBLE"),
    ("AS-07 SENSOR above F0", lambda s: seal_spec(s) if s.update(maintenance_level="F1", capabilities=["CANDIDATE_PROBLEM_PROPOSE", "REPOSITORY_READ"]) is None else s, "CLASS_LEVEL_INADMISSIBLE"),
    # AS-08 authority constants
    ("AS-08 ceiling", _set(["authority_policy", "authority_ceiling"], "RUNTIME_AUTHORITY", True), "AUTHORITY_POLICY_VIOLATION"),
    ("AS-08 human_decision", _set(["authority_policy", "human_decision"], True, True), "AUTHORITY_POLICY_VIOLATION"),
    ("AS-08 economic", _set(["authority_policy", "economic_status_grants_authority"], True, True), "AUTHORITY_POLICY_VIOLATION"),
    ("AS-08 reputation", _set(["authority_policy", "reputation_grants_authority"], True, True), "AUTHORITY_POLICY_VIOLATION"),
    ("AS-08 consensus", _set(["authority_policy", "consensus_grants_authority"], True, True), "AUTHORITY_POLICY_VIOLATION"),
    ("AS-08 string false", _set(["authority_policy", "human_decision"], "false", True), "AUTHORITY_POLICY_VIOLATION"),
    ("AS-08 zero is not false", _set(["authority_policy", "human_decision"], 0, True), "AUTHORITY_POLICY_VIOLATION"),
    # AS-09 binding
    ("AS-09 status", _set(["execution_binding", "status"], "BOUND", True), "BINDING_NOT_UNBOUND"),
    ("AS-09 provider", _set(["execution_binding", "provider"], "acme", True), "BINDING_NOT_UNBOUND"),
    ("AS-09 model", _set(["execution_binding", "model"], "m-1", True), "BINDING_NOT_UNBOUND"),
    ("AS-09 credential", _set(["execution_binding", "credential_mode"], "ENV", True), "BINDING_NOT_UNBOUND"),
    # AS-10 independence
    ("AS-10 own review allowed", _set(["independence_policy", "own_work_review_forbidden"], False, True), "INDEPENDENCE_POLICY_VIOLATION"),
    ("AS-10 independent review off", _set(["independence_policy", "independent_review_required"], False, True), "INDEPENDENCE_POLICY_VIOLATION"),
    # AS-11 identity recomputation (not resealed on purpose)
    ("AS-11 bad agent_id", _set(["agent_id"], "0" * 64), "IDENTITY_MISMATCH"),
    ("AS-11 bad agent_spec_id", _set(["agent_spec_id"], "0" * 64), "IDENTITY_MISMATCH"),
    ("AS-11 stale id after edit", _set(["display_name"], "Edited after sealing"), "IDENTITY_MISMATCH"),
    ("AS-11 class edited, id stale", _set(["agent_class"], "SCOUT"), "IDENTITY_MISMATCH"),
    # AS-12 supersession (local relation)
    ("AS-12 revision 2 without predecessor", _set(["spec_revision"], 2, True), "SUPERSESSION_BREAK"),
    ("AS-12 revision 1 with predecessor", _set(["supersedes_spec_id"], "3" * 64, True), "SUPERSESSION_BREAK"),
    # AS-13 capability <-> scope mapping
    (
        "AS-13 CI_READ with ISSUES",
        _set(["scope_policy", "github_surfaces"], ["CHECK_RUNS", "ISSUES"], True),
        "SCOPE_CAPABILITY_INCOHERENT",
    ),
    (
        "AS-13 metadata read with CHECK_RUNS only",
        lambda s: seal_spec(s) if s.update(capabilities=["GITHUB_METADATA_READ", "REPOSITORY_READ"]) is None or s["scope_policy"].update(github_surfaces=["CHECK_RUNS"]) is None else s,
        "SCOPE_CAPABILITY_INCOHERENT",
    ),
]


@pytest.mark.parametrize("name,build,expected", NEGATIVE_CASES, ids=[c[0] for c in NEGATIVE_CASES])
def test_invalid_specs_are_rejected_as_built(name, build, expected):
    spec = build(make_spec())
    before = copy.deepcopy(spec)
    assert code_of(spec) == expected
    assert repr(spec) == repr(before), "validation must not fix or reorder the input"


def test_reserved_level_and_class_carry_an_explicit_classification():
    spec = _set(["maintenance_level"], "F3", True)(make_spec())
    with pytest.raises(AgentRegistryError) as caught:
        validate_agent_spec(spec)
    assert caught.value.classification == "RESERVED_LEVEL"
    spec = _set(["agent_class"], "ENGINEER", True)(make_spec())
    with pytest.raises(AgentRegistryError) as caught:
        validate_agent_spec(spec)
    assert caught.value.classification == "RESERVED_CLASS"


def test_every_authority_token_is_rejected_even_at_every_level():
    for token in sorted(caps.FORBIDDEN_TOKENS):
        for kind, builder in (("F0", make_spec), ("F1", make_scout_spec)):
            spec = builder()
            spec["capabilities"] = sorted(spec["capabilities"] + [token])
            assert code_of(seal_spec(spec)) == "FORBIDDEN_AUTHORITY_REQUESTED", (kind, token)
    for token in sorted(caps.RESERVED_CAPABILITIES):
        spec = make_scout_spec()
        spec["capabilities"] = sorted(spec["capabilities"] + [token])
        assert code_of(seal_spec(spec)) == "RESERVED_CAPABILITY", token


# ---------------------------------------------------------------------------
# Revision classification (A1 section 10)
# ---------------------------------------------------------------------------


def test_revision_classification_precedence():
    base = make_spec(capabilities=["CI_READ", "REPOSITORY_READ"], read_paths=["docs/"])

    def revise(**kwargs):
        return make_spec(revision=2, supersedes=base["agent_spec_id"], **kwargs)

    assert classify_revision(base, revise(display_name="Renamed")) == "SPEC_REVISION_NON_ESCALATING"
    assert classify_revision(base, revise(read_paths=["docs/", "tests/"])) == "SPEC_REVISION_ESCALATING"
    assert classify_revision(base, revise(read_paths=["tests/"])) == "SPEC_REVISION_ESCALATING"  # replaced path is an increase
    assert classify_revision(base, revise(read_paths=["docs/x.md"])) == "SPEC_REVISION_ESCALATING"
    assert classify_revision(base, revise(capabilities=["CI_READ", "GITHUB_METADATA_READ", "REPOSITORY_READ"], surfaces=["CHECK_RUNS", "ISSUES"])) == "SPEC_REVISION_ESCALATING"
    assert classify_revision(base, revise(capabilities=["CI_READ", "REPOSITORY_READ"], surfaces=["CHECK_RUNS"])) == "SPEC_REVISION_REDUCING"
    scout = make_scout_spec()
    lower = make_scout_spec(level="F0", capabilities=["REPOSITORY_SEARCH"], revision=2, supersedes=scout["agent_spec_id"])
    assert classify_revision(scout, lower) == "SPEC_REVISION_REDUCING"
    assert classify_revision(lower, scout) == "SPEC_REVISION_ESCALATING"
    mixed = revise(read_paths=["tests/"], capabilities=["CI_READ", "REPOSITORY_READ"])
    assert classify_revision(base, mixed) == "SPEC_REVISION_ESCALATING"  # increase beats reduction


# ---------------------------------------------------------------------------
# Drift guards: code <-> JSON Schema <-> catalog markdown
# ---------------------------------------------------------------------------


def test_patterns_are_verbatim_from_the_schema():
    props = SPEC_SCHEMA["properties"]
    assert spec_module.PATTERN_SHA256 == props["agent_id"]["pattern"] == props["agent_spec_id"]["pattern"]
    assert spec_module.PATTERN_SHA40 == props["created_from_ref"]["pattern"]
    assert spec_module.PATTERN_CANONICAL_NAME == props["canonical_name"]["pattern"]
    assert spec_module.PATTERN_DISPLAY_NAME == props["display_name"]["pattern"]
    assert spec_module.PATTERN_PURPOSE == props["purpose"]["pattern"]
    assert spec_module.PATTERN_CREATED_AT == props["created_at_utc"]["pattern"]
    assert spec_module.PATTERN_READ_PATH == props["scope_policy"]["properties"]["repository_read_paths"]["items"]["pattern"]


def test_vocabularies_match_the_schema():
    props = SPEC_SCHEMA["properties"]
    assert set(props["capabilities"]["items"]["enum"]) == caps.CATALOG_V1
    assert set(props["agent_class"]["enum"]) == caps.AGENT_CLASSES
    assert set(props["maintenance_level"]["enum"]) == caps.ADMISSIBLE_LEVELS
    scope = props["scope_policy"]["properties"]
    assert set(scope["github_surfaces"]["items"]["enum"]) == caps.GITHUB_SURFACES
    assert set(scope["artifact_domains"]["items"]["enum"]) == caps.ARTIFACT_DOMAINS
    assert props["namespace"]["const"] == spec_module.NAMESPACE
    assert props["agent_schema"]["const"] == spec_module.AGENT_SCHEMA
    assert props["constitution_version"]["const"] == spec_module.CONSTITUTION_VERSION
    assert set(SPEC_SCHEMA["required"]) == set(spec_module.SPEC_FIELDS)
    assert props["spec_revision"]["maximum"] == spec_module.MAX_SPEC_REVISION


def _schema_conditionals():
    by_level, by_class = {}, {}
    for clause in SPEC_SCHEMA["allOf"]:
        condition = clause["if"].get("properties", {})
        if "maintenance_level" in condition:
            level = condition["maintenance_level"]["const"]
            by_level[level] = set(clause["then"]["properties"]["capabilities"]["items"]["enum"])
        if "agent_class" in condition:
            klass = condition["agent_class"]["const"]
            then = clause["then"]["properties"]["maintenance_level"]
            by_class[klass] = None if then is False else set(then["enum"])
    return by_level, by_class


def test_level_and_class_ceilings_match_the_schema():
    by_level, by_class = _schema_conditionals()
    assert by_level == {k: set(v) for k, v in caps.LEVEL_CAPABILITIES.items()}
    assert set(by_class) == caps.AGENT_CLASSES
    for klass in caps.AGENT_CLASSES:
        if klass in caps.RESERVED_CLASSES:
            assert by_class[klass] is None, klass
        else:
            maximum = caps.LEVEL_RANK[caps.CLASS_MAX_LEVEL[klass]]
            assert by_class[klass] == {lvl for lvl, rank in caps.LEVEL_RANK.items() if rank <= maximum}, klass


def test_scope_coupling_matches_the_schema():
    couplings = {}
    for clause in SPEC_SCHEMA["allOf"]:
        condition = clause["if"]
        branches = condition.get("anyOf", [condition])
        if "capabilities" not in branches[0].get("properties", {}):
            continue
        tokens = {
            branch["properties"]["capabilities"]["contains"]["const"] for branch in branches
        }
        (field,) = clause["then"]["properties"]["scope_policy"]["properties"]
        couplings[field] = tokens
    assert couplings == {
        "repository_read_paths": set(caps.REPOSITORY_PATH_CAPABILITIES),
        "github_surfaces": set(caps.GITHUB_SURFACE_CAPABILITIES),
        "artifact_domains": set(caps.ARTIFACT_DOMAIN_CAPABILITIES),
    }


def _catalog_section(start: str, end: str) -> str:
    return CATALOG_MD.split(start, 1)[1].split(end, 1)[0]


def test_vocabularies_match_the_catalog_markdown():
    allowed = re.findall(r"^\| `([A-Z_]+)` \| F[012] \|", _catalog_section("## 2.", "## 3."), re.M)
    reserved = re.findall(r"^\| `([A-Z_]+)` \| F[34] \|", _catalog_section("## 3.", "## 4."), re.M)
    assert len(allowed) == 14 and len(reserved) == 10
    assert set(allowed) == caps.CATALOG_V1
    assert set(reserved) == caps.RESERVED_CAPABILITIES
    blocks = re.findall(r"```text\n(.*?)```", _catalog_section("## 4.", "## 5."), re.S)
    forbidden = set(re.findall(r"[A-Z][A-Z_0-9]+", blocks[0]))
    human = set(re.findall(r"[A-Z][A-Z_0-9]+", blocks[1]))
    assert forbidden == caps.FORBIDDEN_AUTHORITY_SET and len(forbidden) == 24
    assert human == caps.HUMAN_GATE and len(human) == 6
    levels = {
        name: level
        for name, level in re.findall(r"^\| `([A-Z_]+)` \| (F[012]) \|", _catalog_section("## 2.", "## 3."), re.M)
    }
    for name, level in levels.items():
        lowest = min(lvl for lvl in caps.LEVEL_CAPABILITIES if name in caps.LEVEL_CAPABILITIES[lvl])
        assert lowest == level, name


def test_class_ceilings_match_the_catalog_markdown():
    rows = re.findall(r"^\| `([A-Z_]+)` \| (F[012]|— réservé) \|", _catalog_section("## 6.", "## 7."), re.M)
    assert {name for name, _ in rows} == caps.AGENT_CLASSES
    for name, maximum in rows:
        if maximum == "— réservé":
            assert name in caps.RESERVED_CLASSES
        else:
            assert caps.CLASS_MAX_LEVEL[name] == maximum


# Cases the JSON Schema (S rules) must also reject; the V rules it cannot express
# (sorting, NFC, floats-as-integers, identity recomputation, AS-13 mapping) are not listed.
SCHEMA_ALSO_REJECTS = {
    "AS-01 unknown field",
    "AS-01 unknown nested field",
    "AS-01 missing field",
    "AS-01 wrong agent_schema",
    "AS-01 other namespace",
    "AS-01 bad canonical_name",
    "AS-01 unknown class enum",
    "AS-01 unknown level enum",
    "AS-01 branch name as ref",
    "AS-01 write paths not empty",
    "AS-01 capabilities empty",
    "AS-01 absolute path",
    "AS-01 glob star",
    "AS-01 dot env",
    "AS-01 secrets dir",
    "AS-01 coupling: read cap without paths",
    "AS-01 coupling: surfaces without github cap",
    "AS-01 coupling: domains without cap",
    "AS-07 reserved level F3",
    "AS-07 reserved class ENGINEER",
    "AS-07 SENSOR above F0",
    "AS-06 F0 with proposal",
    "AS-08 ceiling",
    "AS-08 human_decision",
    "AS-09 provider",
    "AS-10 own review allowed",
    "AS-12 revision 2 without predecessor",
}


def test_published_json_schema_agrees_when_jsonschema_is_available():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(SPEC_SCHEMA)
    for spec in (make_spec(), make_scout_spec()):
        assert list(validator.iter_errors(spec)) == []
    builders = {name: build for name, build, _ in NEGATIVE_CASES}
    assert SCHEMA_ALSO_REJECTS <= set(builders)
    for name in sorted(SCHEMA_ALSO_REJECTS):
        spec = builders[name](make_spec())
        assert list(validator.iter_errors(spec)), f"schema accepts {name}"
        assert code_of(spec)  # and so does the validator
