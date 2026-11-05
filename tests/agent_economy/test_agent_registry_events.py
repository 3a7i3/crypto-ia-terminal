"""AgentRegistryEvent V1: event_id, event_hash and event-local rules."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agent_economy.agent_registry import events as ev
from agent_economy.agent_registry.canonical import AgentRegistryError
from agent_economy.agent_registry.events import (
    compute_event_hash,
    compute_event_id,
    validate_event,
)
from tests.agent_economy import _reference as ref
from tests.agent_economy._builders import (
    COMMIT_REF,
    HASH_REF,
    ISSUE_REF,
    PR_REF,
    Lifecycle,
    make_event,
    make_spec,
    seal_event,
)

ROOT = Path(__file__).resolve().parents[2]
EVENT_SCHEMA = json.loads(
    (ROOT / "docs" / "contracts" / "AGENT_ECON_A1_AGENT_REGISTRY_EVENT_V1.schema.json").read_text("utf-8")
)


def code_of(event) -> str:
    with pytest.raises(AgentRegistryError) as caught:
        validate_event(event)
    return caught.value.code


def registered(**overrides):
    spec = make_spec()
    kwargs = dict(
        sequence=1, ordinal=1, spec=spec, event_type="AGENT_REGISTERED", previous_state=None,
        new_state="REGISTERED", reason_code="REGISTRATION_INITIAL", previous_event_hash="GENESIS",
    )
    kwargs.update(overrides)
    return make_event(**kwargs)


def suspended(sequence=2, **overrides):
    kwargs = dict(
        sequence=sequence, ordinal=2, spec=make_spec(), event_type="AGENT_SUSPENDED",
        previous_state="REGISTERED", new_state="SUSPENDED", reason_code="SUSPENSION_INCIDENT",
        previous_event_hash="a" * 64, evidence_refs=[ISSUE_REF],
    )
    kwargs.update(overrides)
    return make_event(**kwargs)


def mutated(event, **changes):
    event = copy.deepcopy(event)
    event.update(changes)
    return event


def test_every_event_type_of_the_lifecycle_is_valid():
    lifecycle = Lifecycle()
    assert {e["event_type"] for e in lifecycle.events} == ev.EVENT_TYPES
    for event in lifecycle.events:
        validate_event(event)


def test_event_id_and_hash_match_the_independent_reference():
    for event in Lifecycle().events:
        assert compute_event_id(event) == ref.event_id(event) == event["event_id"]
        assert compute_event_hash(event) == ref.event_hash(event) == event["event_hash"]


def test_event_id_formula_excludes_exactly_the_contract_fields():
    base = suspended()
    changes_that_keep_the_id = {
        "registry_sequence": 99,
        "occurred_at_utc": "2031-01-01T00:00:00Z",
        "reason_detail": "free text detail",
        "spec_artifact_hash": "e" * 64,
        "previous_event_hash": "f" * 64,
        "event_hash": "0" * 64,
        "event_id": "1" * 64,
    }
    for field, value in changes_that_keep_the_id.items():
        assert compute_event_id(mutated(base, **{field: value})) == base["event_id"], field
    changes_that_alter_the_id = {
        "agent_id": "2" * 64,
        "agent_transition_ordinal": 3,
        "event_type": "AGENT_RETIRED",
        "previous_state": "SUSPENDED",
        "new_state": "REGISTERED",
        "agent_spec_id": "3" * 64,
        "evidence_refs": [HASH_REF],
        "reason_code": "SUSPENSION_GOVERNANCE",
    }
    assert set(changes_that_alter_the_id) == set(ev.EVENT_IDENTITY_FIELDS)
    for field, value in changes_that_alter_the_id.items():
        assert compute_event_id(mutated(base, **{field: value})) != base["event_id"], field


def test_event_hash_covers_every_other_field():
    base = suspended()
    assert set(ev.EVENT_FIELDS) - {"event_hash"} == set(base) - {"event_hash"}
    for field in ev.EVENT_FIELDS:
        if field == "event_hash":
            continue
        assert compute_event_hash(mutated(base, **{field: "changed"})) != base["event_hash"], field
    assert compute_event_hash(base) == base["event_hash"]
    # event_hash itself is excluded (no circularity)
    assert compute_event_hash(mutated(base, event_hash="0" * 64)) == base["event_hash"]


def test_spec_artifact_hash_is_covered_by_event_hash_but_not_event_id():
    base = suspended()
    other = mutated(base, spec_artifact_hash="9" * 64)
    assert compute_event_id(other) == base["event_id"]
    assert compute_event_hash(other) != base["event_hash"]
    assert code_of(other) == "EVENT_HASH_MISMATCH"


def test_genesis_literal_is_the_first_previous_hash():
    first = registered()
    assert first["previous_event_hash"] == "GENESIS" == ev.GENESIS
    validate_event(first)


NEGATIVE_EVENT_CASES = [
    ("AE-01 unknown field", lambda: {**registered(), "extra": 1}, "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 missing field", lambda: {k: v for k, v in registered().items() if k != "reason_detail"}, "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 not an object", lambda: [registered()], "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 wrong schema", lambda: seal_event(mutated(registered(), event_schema="V2")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 unknown event_type", lambda: seal_event(mutated(registered(), event_type="AGENT_ACTIVATED")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 unknown state ACTIVE", lambda: seal_event(mutated(registered(), new_state="ACTIVE")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 previous_state RETIRED", lambda: seal_event(mutated(suspended(), previous_state="RETIRED")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 unknown reason", lambda: seal_event(mutated(registered(), reason_code="WHIM")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 sequence 0", lambda: seal_event(mutated(registered(), registry_sequence=0)), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 sequence string", lambda: seal_event(mutated(registered(), registry_sequence="1")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 bad hash pattern", lambda: seal_event(mutated(registered(), spec_artifact_hash="XYZ")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 uppercase hash", lambda: seal_event(mutated(registered(), agent_id="A" * 64)), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 bad timestamp", lambda: seal_event(mutated(registered(), occurred_at_utc="2026-10-04")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 impossible timestamp", lambda: seal_event(mutated(registered(), occurred_at_utc="2026-02-30T00:00:00Z")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 long reason_detail", lambda: seal_event(mutated(registered(), reason_detail="x" * 1001)), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 non-NFC reason_detail", lambda: seal_event(mutated(registered(), reason_detail="é")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 padded reason_detail", lambda: seal_event(mutated(registered(), reason_detail=" x")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-01 previous hash malformed", lambda: seal_event(mutated(suspended(), previous_event_hash="genesis")), "EVENT_SCHEMA_VIOLATION"),
    ("AE-02 sequence bool", lambda: seal_event(mutated(registered(), registry_sequence=True)), "EVENT_NUMERIC_AMBIGUITY"),
    ("AE-02 ordinal bool", lambda: seal_event(mutated(registered(), agent_transition_ordinal=True)), "EVENT_NUMERIC_AMBIGUITY"),
    ("AE-02 sequence 1.0", lambda: mutated(registered(), registry_sequence=1.0), "EVENT_NUMERIC_AMBIGUITY"),
    ("AE-02 NaN", lambda: mutated(registered(), reason_detail=float("nan")), "EVENT_NUMERIC_AMBIGUITY"),
    ("AE-03 bad event_id", lambda: mutated(registered(), event_id="0" * 64), "EVENT_ID_MISMATCH"),
    ("AE-03 id stale after edit", lambda: mutated(registered(), evidence_refs=[COMMIT_REF]), "EVENT_ID_MISMATCH"),
    ("AE-04 bad event_hash", lambda: mutated(registered(), event_hash="0" * 64), "EVENT_HASH_MISMATCH"),
    ("AE-04 hash stale after edit", lambda: mutated(registered(), reason_detail="late edit"), "EVENT_HASH_MISMATCH"),
    ("AE-05 REGISTERED from state", lambda: seal_event(mutated(registered(), previous_state="SUSPENDED")), "ILLEGAL_TRANSITION"),
    ("AE-05 SUSPENDED from SUSPENDED", lambda: seal_event(mutated(suspended(), previous_state="SUSPENDED")), "ILLEGAL_TRANSITION"),
    ("AE-05 SUSPENDED leads to REGISTERED", lambda: seal_event(mutated(suspended(), new_state="REGISTERED")), "ILLEGAL_TRANSITION"),
    ("AE-05 REINSTATED from REGISTERED", lambda: seal_event(mutated(suspended(), event_type="AGENT_REINSTATED", previous_state="REGISTERED", new_state="REGISTERED", reason_code="REINSTATEMENT_GOVERNANCE", evidence_refs=[COMMIT_REF])), "ILLEGAL_TRANSITION"),
    ("AE-05 RETIRED does not retire", lambda: seal_event(mutated(suspended(), event_type="AGENT_RETIRED", new_state="REGISTERED", reason_code="RETIREMENT_GOVERNANCE")), "ILLEGAL_TRANSITION"),
    ("AE-05 revision changes state", lambda: seal_event(mutated(suspended(), event_type="AGENT_SPEC_REVISED", new_state="SUSPENDED", reason_code="SPEC_REVISION_REDUCING", previous_state="REGISTERED")), "ILLEGAL_TRANSITION"),
    ("AE-05 revision from absent", lambda: seal_event(mutated(registered(), event_type="AGENT_SPEC_REVISED", reason_code="SPEC_REVISION_REDUCING")), "ILLEGAL_TRANSITION"),
    ("AE-06 suspension with registration reason", lambda: seal_event(mutated(suspended(), reason_code="REGISTRATION_INITIAL")), "REASON_CODE_MISMATCH"),
    ("AE-06 registration with revision reason", lambda: seal_event(mutated(registered(), reason_code="SPEC_REVISION_REDUCING")), "REASON_CODE_MISMATCH"),
    ("AE-06 retirement with suspension reason", lambda: seal_event(mutated(suspended(), event_type="AGENT_RETIRED", new_state="RETIRED", reason_code="SUSPENSION_INCIDENT")), "REASON_CODE_MISMATCH"),
    ("AE-07 empty evidence", lambda: seal_event(mutated(registered(), evidence_refs=[])), "EVIDENCE_INVALID"),
    ("AE-07 unsorted evidence", lambda: seal_event(mutated(registered(), evidence_refs=[ISSUE_REF, COMMIT_REF])), "EVIDENCE_INVALID"),
    ("AE-07 duplicate evidence", lambda: seal_event(mutated(registered(), evidence_refs=[COMMIT_REF, COMMIT_REF])), "EVIDENCE_INVALID"),
    ("AE-07 free text evidence", lambda: seal_event(mutated(registered(), evidence_refs=["trust me"])), "EVIDENCE_INVALID"),
    ("AE-07 url evidence", lambda: seal_event(mutated(registered(), evidence_refs=["https://github.com/o/r/pull/1"])), "EVIDENCE_INVALID"),
    ("AE-07 bare issue number", lambda: seal_event(mutated(registered(), evidence_refs=["#12"])), "EVIDENCE_INVALID"),
    ("AE-07 PR without sha", lambda: seal_event(mutated(registered(), evidence_refs=["github:pr:o/r#2"])), "EVIDENCE_INVALID"),
    ("AE-07 short sha", lambda: seal_event(mutated(registered(), evidence_refs=["git:commit:abc"])), "EVIDENCE_INVALID"),
    ("AE-07 not a list item", lambda: seal_event(mutated(registered(), evidence_refs=[3])), "EVIDENCE_INVALID"),
    ("AE-07 too many", lambda: seal_event(mutated(registered(), evidence_refs=sorted(f"sha256:{i:064x}" for i in range(33)))), "EVIDENCE_INVALID"),
    ("AE-09 REGISTERED without anchor", lambda: seal_event(mutated(registered(), evidence_refs=[ISSUE_REF])), "SOURCE_ANCHOR_MISSING"),
    ("AE-09 REGISTERED with hash only", lambda: seal_event(mutated(registered(), evidence_refs=[HASH_REF])), "SOURCE_ANCHOR_MISSING"),
    ("AE-09 REINSTATED without anchor", lambda: seal_event(mutated(suspended(), event_type="AGENT_REINSTATED", previous_state="SUSPENDED", new_state="REGISTERED", reason_code="REINSTATEMENT_GOVERNANCE", evidence_refs=[ISSUE_REF])), "SOURCE_ANCHOR_MISSING"),
    ("AE-09 escalating revision without anchor", lambda: seal_event(mutated(suspended(), event_type="AGENT_SPEC_REVISED", previous_state="REGISTERED", new_state="REGISTERED", reason_code="SPEC_REVISION_ESCALATING", evidence_refs=[ISSUE_REF])), "SOURCE_ANCHOR_MISSING"),
    ("AC-03 REGISTERED ordinal 2", lambda: seal_event(mutated(registered(), agent_transition_ordinal=2)), "ORDINAL_GAP"),
    ("AC-03 SUSPENDED ordinal 1", lambda: seal_event(mutated(suspended(), agent_transition_ordinal=1)), "ORDINAL_GAP"),
    ("AC-02 GENESIS at sequence 2", lambda: seal_event(mutated(suspended(), previous_event_hash="GENESIS")), "CHAIN_BREAK"),
    ("AC-02 hash at sequence 1", lambda: seal_event(mutated(registered(), previous_event_hash="a" * 64)), "CHAIN_BREAK"),
]


@pytest.mark.parametrize("name,build,expected", NEGATIVE_EVENT_CASES, ids=[c[0] for c in NEGATIVE_EVENT_CASES])
def test_invalid_events_are_rejected_as_built(name, build, expected):
    event = build()
    snapshot = repr(event)
    assert code_of(event) == expected
    assert repr(event) == snapshot


def test_anchor_rules_accept_pr_at_sha_and_commit_refs():
    for refs in ([PR_REF], [COMMIT_REF], sorted([PR_REF, ISSUE_REF])):
        validate_event(registered(evidence_refs=refs))
    # non-escalating and reducing revisions, suspensions and retirements need no anchor
    for reason in ("SPEC_REVISION_NON_ESCALATING", "SPEC_REVISION_REDUCING"):
        validate_event(
            suspended(event_type="AGENT_SPEC_REVISED", new_state="REGISTERED", reason_code=reason, evidence_refs=[ISSUE_REF])
        )


def test_registered_is_not_an_active_or_running_state():
    assert ev.AGENT_STATES == {"REGISTERED", "SUSPENDED", "RETIRED"}
    assert not any(word in state.lower() for state in ev.AGENT_STATES for word in ("active", "running", "online"))


def test_patterns_and_vocabularies_match_the_event_schema():
    props = EVENT_SCHEMA["properties"]
    assert ev.PATTERN_SHA256 == props["event_id"]["pattern"] == props["event_hash"]["pattern"]
    assert ev.PATTERN_PREVIOUS_EVENT_HASH == props["previous_event_hash"]["pattern"]
    assert ev.PATTERN_EVIDENCE_REF == props["evidence_refs"]["items"]["pattern"]
    assert ev.PATTERN_OCCURRED_AT == props["occurred_at_utc"]["pattern"]
    assert set(EVENT_SCHEMA["required"]) == set(ev.EVENT_FIELDS)
    assert set(props["event_type"]["enum"]) == ev.EVENT_TYPES
    assert set(props["reason_code"]["enum"]) == ev.REASON_CODES
    assert set(props["new_state"]["enum"]) == ev.AGENT_STATES
    assert set(props["previous_state"]["enum"]) == {None, "REGISTERED", "SUSPENDED"}
    assert props["evidence_refs"]["maxItems"] == ev.MAX_EVIDENCE_REFS
    assert props["reason_detail"]["maxLength"] == ev.MAX_REASON_DETAIL
    assert props["event_schema"]["const"] == ev.EVENT_SCHEMA


def test_transition_table_matches_the_event_schema():
    schema_table = {}
    for clause in EVENT_SCHEMA["allOf"]:
        condition = clause["if"]["properties"]
        if "event_type" not in condition:
            continue
        then = clause["then"]["properties"]
        previous = then["previous_state"]
        if "type" in previous:
            previous_values = {None}
        elif "const" in previous:
            previous_values = {previous["const"]}
        else:
            previous_values = set(previous["enum"])
        new = then["new_state"]
        new_values = {new["const"]} if "const" in new else set(new["enum"])
        reasons = set(then["reason_code"]["enum"])
        schema_table[condition["event_type"]["const"]] = (previous_values, new_values, reasons)
        if condition["event_type"]["const"] == "AGENT_REGISTERED":
            assert then["agent_transition_ordinal"]["const"] == 1
        else:
            assert then["agent_transition_ordinal"]["minimum"] == 2
    code_table = {
        kind: (
            set(prev),
            {"REGISTERED", "SUSPENDED"} if new is None else set(new),
            set(reasons),
        )
        for kind, (prev, new, reasons) in ev.TRANSITIONS.items()
    }
    # For a revision the schema only lists the allowed states; that new_state equals
    # previous_state is the validator rule AE-05 (checked in the negative cases).
    assert ev.TRANSITIONS["AGENT_SPEC_REVISED"][1] is None
    assert code_table == schema_table


def test_published_event_schema_agrees_when_jsonschema_is_available():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(EVENT_SCHEMA)
    for event in Lifecycle().events:
        assert list(validator.iter_errors(event)) == []
    for name in (
        "AE-01 unknown field", "AE-01 unknown event_type", "AE-01 sequence 0",
        "AE-05 REGISTERED from state", "AE-05 SUSPENDED from SUSPENDED",
        "AE-06 suspension with registration reason", "AE-07 empty evidence",
        "AE-07 free text evidence", "AC-03 REGISTERED ordinal 2",
        "AC-03 SUSPENDED ordinal 1", "AC-02 GENESIS at sequence 2",
        "AC-02 hash at sequence 1",
    ):
        build = next(b for n, b, _ in NEGATIVE_EVENT_CASES if n == name)
        assert list(validator.iter_errors(build())), f"schema accepts {name}"
