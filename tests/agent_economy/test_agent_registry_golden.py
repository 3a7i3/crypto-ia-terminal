"""Golden vectors: FIXTURE_ONLY / NOT_REGISTRY_DATA / NOT_OPERATOR_DATA / NOT_DEPLOYED.

Expected values live in fixtures/golden_vectors_FIXTURE_ONLY.json and were produced by
the independent stdlib reference (tests/agent_economy/_reference.py) from the certified
formulas; the package under test must reproduce them byte for byte on every machine.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from agent_economy.agent_registry import (
    compute_agent_id,
    compute_agent_spec_id,
    compute_event_hash,
    compute_event_id,
    compute_spec_artifact_hash,
    project_registry,
    publication_json_bytes,
    validate_agent_spec,
    verify_chain,
)
from tests.agent_economy import _reference as ref

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURE_DIR / "golden_vectors_FIXTURE_ONLY.json").read_text("utf-8"))
HEX64 = re.compile(r"[0-9a-f]{64}")


def artifacts():
    return {
        spec["agent_spec_id"]: publication_json_bytes(spec) for spec in GOLDEN["specs"].values()
    }


def test_fixture_is_explicitly_marked_and_synthetic():
    assert GOLDEN["fixture_semantics"] == [
        "FIXTURE_ONLY", "NOT_REGISTRY_DATA", "NOT_OPERATOR_DATA", "NOT_DEPLOYED",
    ]
    readme = (FIXTURE_DIR / "README_FIXTURE_ONLY.md").read_text("utf-8")
    for marker in GOLDEN["fixture_semantics"]:
        assert marker in readme
    legacy = {p.name.removesuffix(".agent.md") for p in (ROOT / ".github" / "agents").glob("*.agent.md")}
    for spec in GOLDEN["specs"].values():
        assert spec["canonical_name"].startswith("fixture_")
        assert spec["canonical_name"].replace("_", "-") not in legacy
        assert spec["canonical_name"] not in legacy
    assert {p.name for p in FIXTURE_DIR.iterdir()} == {
        "README_FIXTURE_ONLY.md", "golden_vectors_FIXTURE_ONLY.json",
    }, "fixtures must hold only the marked vectors"


@pytest.mark.parametrize("key", sorted(GOLDEN["specs"]))
def test_identity_vectors_match_reference_and_package(key):
    spec = GOLDEN["specs"][key]
    expected = GOLDEN["expected_identities"][key]
    for value in expected.values():
        assert HEX64.fullmatch(value)
    # independent reference, from the contract formulas
    assert ref.agent_id(spec["namespace"], spec["canonical_name"], spec["agent_class"]) == expected["agent_id"]
    assert ref.agent_spec_id(spec) == expected["agent_spec_id"]
    assert ref.artifact_hash(spec) == expected["spec_artifact_hash"]
    # package under test
    assert compute_agent_id(spec["namespace"], spec["canonical_name"], spec["agent_class"]) == expected["agent_id"]
    assert compute_agent_spec_id(spec) == expected["agent_spec_id"]
    assert compute_spec_artifact_hash(spec) == expected["spec_artifact_hash"]
    identities = validate_agent_spec(copy.deepcopy(spec))
    assert (identities.agent_id, identities.agent_spec_id, identities.spec_artifact_hash) == (
        expected["agent_id"], expected["agent_spec_id"], expected["spec_artifact_hash"],
    )
    assert hashlib.sha256(publication_json_bytes(spec)).hexdigest() == expected["spec_artifact_hash"]


def test_revision_shares_agent_id_but_not_spec_id_or_artifact():
    ids = GOLDEN["expected_identities"]
    assert ids["a1"]["agent_id"] == ids["a2"]["agent_id"] != ids["b1"]["agent_id"]
    assert len({ids[k]["agent_spec_id"] for k in ids}) == 3
    assert len({ids[k]["spec_artifact_hash"] for k in ids}) == 3


def test_event_vectors_match_reference_and_package():
    events = GOLDEN["events"]
    chain = GOLDEN["expected_chain"]
    assert [e["event_id"] for e in events] == chain["event_ids"]
    assert [e["event_hash"] for e in events] == chain["event_hashes"]
    assert chain["final_event_hash"] == events[-1]["event_hash"]
    previous = "GENESIS"
    for event in events:
        assert event["previous_event_hash"] == previous
        assert ref.event_id(event) == compute_event_id(event) == event["event_id"]
        assert ref.event_hash(event) == compute_event_hash(event) == event["event_hash"]
        assert HEX64.fullmatch(event["event_id"]) and HEX64.fullmatch(event["event_hash"])
        previous = event["event_hash"]
    assert len(set(chain["event_ids"])) == len(set(chain["event_hashes"])) == 6


def test_multi_event_chain_verifies_against_exact_artifacts():
    result = verify_chain(copy.deepcopy(GOLDEN["events"]), artifacts())
    assert result.status == "STRUCTURALLY_VALID_CHAIN"
    assert result.last_event_hash == GOLDEN["expected_chain"]["final_event_hash"]
    assert result.verified_event_count == 6


def test_projection_vector():
    projection = project_registry(copy.deepcopy(GOLDEN["events"]), artifacts())
    expected = GOLDEN["expected_projection"]
    assert projection.availability == expected["availability"] == "UNKNOWN"
    assert projection.chain_status == expected["chain_status"]
    assert projection.agent_states is None
    assert projection.prefix_diagnostic.label == expected["label"]
    assert projection.prefix_diagnostic.verified_event_count == expected["verified_event_count"]
    actual = [
        {
            "agent_id": f.agent_id,
            "current_agent_spec_id": f.current_agent_spec_id,
            "state": f.state,
            "agent_transition_ordinal": f.agent_transition_ordinal,
            "last_registry_sequence": f.last_registry_sequence,
        }
        for f in projection.prefix_diagnostic.agent_facts
    ]
    assert actual == expected["agents"]


def test_golden_vectors_are_deterministic_across_runs():
    first = json.dumps(project_registry(copy.deepcopy(GOLDEN["events"]), artifacts()).to_dict(), sort_keys=True)
    second = json.dumps(project_registry(copy.deepcopy(GOLDEN["events"]), artifacts()).to_dict(), sort_keys=True)
    assert first == second
    assert hashlib.sha256(first.encode()).hexdigest() == hashlib.sha256(second.encode()).hexdigest()


def test_any_single_byte_change_in_any_artifact_or_event_breaks_certification():
    events = GOLDEN["events"]
    for spec_id, raw in artifacts().items():
        for offset in (0, len(raw) // 2, len(raw) - 2):
            tampered = dict(artifacts())
            data = bytearray(raw)
            data[offset] ^= 0x01
            tampered[spec_id] = bytes(data)
            assert verify_chain(copy.deepcopy(events), tampered).status == "NOT_CERTIFIABLE"
    for index in range(len(events)):
        mutated = copy.deepcopy(events)
        mutated[index]["occurred_at_utc"] = "2026-10-04T23:59:59Z"
        assert verify_chain(mutated, artifacts()).status == "NOT_CERTIFIABLE"
