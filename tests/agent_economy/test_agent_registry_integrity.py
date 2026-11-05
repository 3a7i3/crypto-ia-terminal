"""Append-only chain verification: AC-01 ... AC-06 and the history-dependent AE rules."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from agent_economy.agent_registry import integrity
from agent_economy.agent_registry.integrity import (
    NOT_CERTIFIABLE,
    STRUCTURALLY_VALID_CHAIN,
    verify_chain,
)
from agent_economy.agent_registry.spec import compute_spec_artifact_hash
from tests.agent_economy._builders import (
    COMMIT_REF,
    ISSUE_REF,
    Lifecycle,
    artifact,
    make_event,
    make_scout_spec,
    make_spec,
    rechain,
    seal_event,
    seal_spec,
)


def assert_not_certifiable(events, specs, code, *, position=None):
    result = verify_chain(events, specs)
    assert result.status == NOT_CERTIFIABLE, result
    assert result.failure_code == code, (result.failure_code, result.failure_detail)
    assert result.agent_facts == (), "no partial healthy state may be returned"
    if position is not None:
        assert result.failure_position == position
    return result


def test_lifecycle_is_a_structurally_valid_chain():
    lifecycle = Lifecycle()
    result = verify_chain(lifecycle.events, lifecycle.specs)
    assert result.status == STRUCTURALLY_VALID_CHAIN
    assert result.verified_event_count == 6 and result.last_registry_sequence == 6
    assert result.last_event_hash == lifecycle.events[-1]["event_hash"]
    by_agent = {fact.agent_id: fact for fact in result.agent_facts}
    a = by_agent[lifecycle.spec_a1["agent_id"]]
    b = by_agent[lifecycle.spec_b1["agent_id"]]
    assert (a.state, a.current_agent_spec_id, a.agent_transition_ordinal, a.last_registry_sequence) == (
        "REGISTERED", lifecycle.spec_a2["agent_spec_id"], 4, 5,
    )
    assert (b.state, b.agent_transition_ordinal, b.last_registry_sequence) == ("RETIRED", 2, 6)


def test_empty_sequence_is_valid_but_proves_nothing_about_completeness():
    result = verify_chain([], {})
    assert result.status == STRUCTURALLY_VALID_CHAIN and result.verified_event_count == 0
    assert result.agent_facts == () and result.last_event_hash is None


def test_verification_never_mutates_its_inputs():
    lifecycle = Lifecycle()
    events, specs = lifecycle.copy_events(), lifecycle.copy_specs()
    verify_chain(events, specs)
    assert events == lifecycle.events and specs == lifecycle.specs
    events[2]["reason_detail"] = "tampered"
    snapshot = copy.deepcopy(events)
    verify_chain(events, specs)
    assert events == snapshot


@pytest.mark.parametrize("bad", [None, "events", {"a": 1}, 5, iter([])])
def test_non_sequence_events_are_not_certifiable(bad):
    assert_not_certifiable(bad, {}, "EVENT_SCHEMA_VIOLATION")


def test_non_object_event_in_the_chain_is_not_certifiable():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[1] = "garbage"
    assert_not_certifiable(events, lifecycle.specs, "EVENT_SCHEMA_VIOLATION", position=2)


# --- AC-01 sequence, AC-02 chain, AC-03 ordinal ---------------------------------


def test_bad_sequence_is_rejected():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[2]["registry_sequence"] = 9
    seal_event(events[2])
    assert_not_certifiable(events, lifecycle.specs, "SEQUENCE_GAP_OR_DUPLICATE", position=3)


def test_duplicate_sequence_is_rejected():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[3]["registry_sequence"] = 3
    seal_event(events[3])
    assert_not_certifiable(events, lifecycle.specs, "SEQUENCE_GAP_OR_DUPLICATE", position=4)


def test_bad_ordinal_is_rejected():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[3]["agent_transition_ordinal"] = 5  # agent A is at ordinal 2 before event 4
    seal_event(events[3])
    assert_not_certifiable(events, lifecycle.specs, "ORDINAL_GAP", position=4)


def test_agent_registered_twice_is_an_ordinal_violation():
    lifecycle = Lifecycle()
    again = make_event(
        sequence=7, ordinal=1, spec=lifecycle.spec_a1, event_type="AGENT_REGISTERED",
        previous_state=None, new_state="REGISTERED", reason_code="REGISTRATION_INITIAL",
        previous_event_hash=lifecycle.events[-1]["event_hash"],
        evidence_refs=[COMMIT_REF, ISSUE_REF, "sha256:" + "0" * 64],
    )
    assert_not_certifiable(lifecycle.copy_events() + [again], lifecycle.specs, "ORDINAL_GAP", position=7)


def test_bad_previous_hash_is_rejected():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[2]["previous_event_hash"] = "0" * 64
    seal_event(events[2])
    assert_not_certifiable(events, lifecycle.specs, "CHAIN_BREAK", position=3)


def test_bad_event_hash_and_bad_event_id_are_rejected():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[1]["event_hash"] = "0" * 64
    assert_not_certifiable(events, lifecycle.specs, "EVENT_HASH_MISMATCH", position=2)
    events = lifecycle.copy_events()
    events[1]["event_id"] = "0" * 64
    assert_not_certifiable(events, lifecycle.specs, "EVENT_ID_MISMATCH", position=2)


def test_edited_event_breaks_its_own_hash_even_if_the_edit_is_innocent():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[0]["reason_detail"] = "late annotation"
    assert_not_certifiable(events, lifecycle.specs, "EVENT_HASH_MISMATCH", position=1)


def test_consistent_rewrite_of_one_event_breaks_the_next_link():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[1]["reason_detail"] = "rewritten and resealed"
    seal_event(events[1])  # self-consistent, but event 3 still points to the old hash
    assert_not_certifiable(events, lifecycle.specs, "CHAIN_BREAK", position=3)


def test_truncated_head_and_removed_middle_are_rejected():
    lifecycle = Lifecycle()
    assert_not_certifiable(lifecycle.copy_events()[1:], lifecycle.specs, "SEQUENCE_GAP_OR_DUPLICATE", position=1)
    events = lifecycle.copy_events()
    del events[2]
    assert_not_certifiable(events, lifecycle.specs, "SEQUENCE_GAP_OR_DUPLICATE", position=3)


def test_tail_truncation_is_undetectable_without_an_external_anchor():
    """A valid prefix is indistinguishable from a complete registry (A1 9.4)."""
    lifecycle = Lifecycle()
    for keep in range(0, 6):
        result = verify_chain(lifecycle.copy_events()[:keep], lifecycle.specs)
        assert result.status == STRUCTURALLY_VALID_CHAIN
    # which is exactly why the chain alone can never be AVAILABLE (see projection tests)


def test_reordered_chain_is_rejected():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[2], events[3] = events[3], events[2]
    assert_not_certifiable(events, lifecycle.specs, "SEQUENCE_GAP_OR_DUPLICATE", position=3)


def test_replayed_event_is_an_event_id_collision():
    lifecycle = Lifecycle()
    replay = copy.deepcopy(lifecycle.events[0])
    replay["registry_sequence"] = 7
    replay["previous_event_hash"] = lifecycle.events[-1]["event_hash"]
    replay["event_hash"] = ""
    from agent_economy.agent_registry import compute_event_hash

    replay["event_hash"] = compute_event_hash(replay)
    assert replay["event_id"] == lifecycle.events[0]["event_id"]
    assert_not_certifiable(lifecycle.copy_events() + [replay], lifecycle.specs, "EVENT_ID_COLLISION", position=7)


# --- AC-05 terminal / AE-05 transitions ---------------------------------------


def test_no_event_may_follow_retired():
    lifecycle = Lifecycle()
    last = lifecycle.events[-1]
    for kind, previous, new, reason in (
        ("AGENT_SPEC_REVISED", "REGISTERED", "REGISTERED", "SPEC_REVISION_REDUCING"),
        ("AGENT_SUSPENDED", "REGISTERED", "SUSPENDED", "SUSPENSION_GOVERNANCE"),
        ("AGENT_REINSTATED", "SUSPENDED", "REGISTERED", "REINSTATEMENT_GOVERNANCE"),
        ("AGENT_RETIRED", "REGISTERED", "RETIRED", "RETIREMENT_GOVERNANCE"),
    ):
        extra = make_event(
            sequence=7, ordinal=3, spec=lifecycle.spec_b1, event_type=kind,
            previous_state=previous, new_state=new, reason_code=reason,
            previous_event_hash=last["event_hash"], evidence_refs=[COMMIT_REF],
        )
        assert_not_certifiable(lifecycle.copy_events() + [extra], lifecycle.specs, "EVENT_AFTER_TERMINAL", position=7)


def test_revision_on_retired_agent_is_rejected_even_with_a_valid_new_spec():
    lifecycle = Lifecycle()
    revision = make_scout_spec(revision=2, supersedes=lifecycle.spec_b1["agent_spec_id"], display_name="Late revision")
    specs = lifecycle.copy_specs()
    specs[revision["agent_spec_id"]] = artifact(revision)
    extra = make_event(
        sequence=7, ordinal=3, spec=revision, event_type="AGENT_SPEC_REVISED",
        previous_state="REGISTERED", new_state="REGISTERED",
        reason_code="SPEC_REVISION_NON_ESCALATING",
        previous_event_hash=lifecycle.events[-1]["event_hash"],
    )
    assert_not_certifiable(lifecycle.copy_events() + [extra], specs, "EVENT_AFTER_TERMINAL", position=7)


def test_illegal_transition_against_the_projected_state():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    # agent A is SUSPENDED after event 4; a second suspension claims REGISTERED
    events[4] = make_event(
        sequence=5, ordinal=4, spec=lifecycle.spec_a2, event_type="AGENT_SUSPENDED",
        previous_state="REGISTERED", new_state="SUSPENDED", reason_code="SUSPENSION_INCIDENT",
        previous_event_hash=events[3]["event_hash"], evidence_refs=[ISSUE_REF],
    )
    rechain(events)
    assert_not_certifiable(events, lifecycle.specs, "ILLEGAL_TRANSITION", position=5)


def test_event_for_an_unregistered_agent_is_illegal():
    lifecycle = Lifecycle()
    spec = make_scout_spec(canonical_name="fixture_unregistered")
    specs = lifecycle.copy_specs()
    specs[spec["agent_spec_id"]] = artifact(spec)
    event = make_event(
        sequence=1, ordinal=2, spec=spec, event_type="AGENT_SUSPENDED",
        previous_state="REGISTERED", new_state="SUSPENDED", reason_code="SUSPENSION_INCIDENT",
        previous_event_hash="GENESIS", evidence_refs=[ISSUE_REF],
    )
    assert_not_certifiable([event], specs, "ORDINAL_GAP", position=1)
    event = make_event(
        sequence=1, ordinal=1, spec=spec, event_type="AGENT_REGISTERED",
        previous_state=None, new_state="REGISTERED", reason_code="REGISTRATION_INITIAL",
        previous_event_hash="GENESIS",
    )
    event["previous_state"] = "REGISTERED"
    seal_event(event)
    assert_not_certifiable([event], specs, "ILLEGAL_TRANSITION", position=1)


# --- AE-08 / AE-11 specs ------------------------------------------------------


def test_missing_referenced_spec_is_rejected():
    lifecycle = Lifecycle()
    specs = lifecycle.copy_specs()
    del specs[lifecycle.spec_a2["agent_spec_id"]]
    assert_not_certifiable(lifecycle.events, specs, "SPEC_REFERENCE_INVALID", position=3)
    assert_not_certifiable(lifecycle.events, {}, "SPEC_REFERENCE_INVALID", position=1)
    assert_not_certifiable(lifecycle.events, None, "SPEC_REFERENCE_INVALID", position=1)


def test_spec_artifact_hash_mismatch_rejected():
    lifecycle = Lifecycle()
    other_provenance = make_spec(created_at_utc="2026-10-05T00:00:00Z")
    assert other_provenance["agent_spec_id"] == lifecycle.spec_a1["agent_spec_id"]
    specs = lifecycle.copy_specs()
    specs[lifecycle.spec_a1["agent_spec_id"]] = artifact(other_provenance)  # same matter, other bytes
    result = assert_not_certifiable(lifecycle.events, specs, "SPEC_ARTIFACT_HASH_MISMATCH", position=1)
    assert "SHA-256" in result.failure_detail
    specs = lifecycle.copy_specs()
    specs[lifecycle.spec_a1["agent_spec_id"]] += b" "  # one byte appended
    assert_not_certifiable(lifecycle.events, specs, "SPEC_ARTIFACT_HASH_MISMATCH", position=1)


def test_wrong_spec_artifact_hash_in_the_event_is_rejected():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[0]["spec_artifact_hash"] = compute_spec_artifact_hash(make_spec(created_at_utc="2030-01-01T00:00:00Z"))
    rechain(events)
    assert_not_certifiable(events, lifecycle.specs, "SPEC_ARTIFACT_HASH_MISMATCH", position=1)


def test_hash_is_of_the_exact_bytes_not_of_the_parsed_content():
    lifecycle = Lifecycle()
    spec = lifecycle.spec_a1
    compact = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    events = lifecycle.copy_events()
    events[0]["spec_artifact_hash"] = hashlib.sha256(compact).hexdigest()
    rechain(events)
    specs = lifecycle.copy_specs()
    specs[spec["agent_spec_id"]] = compact  # hash-consistent, but not the AW-03 form
    result = assert_not_certifiable(events, specs, "SPEC_REFERENCE_INVALID", position=1)
    assert "publication form" in result.failure_detail


def test_two_artifacts_for_one_spec_id_are_a_provenance_conflict():
    lifecycle = Lifecycle()
    alternate = make_spec(created_from_ref="d" * 40)
    assert alternate["agent_spec_id"] == lifecycle.spec_a1["agent_spec_id"]
    events = lifecycle.copy_events()
    # event 4 (SUSPENDED, spec A2) re-binds A2 to a different artifact hash than event 3 did
    assert events[3]["agent_spec_id"] == lifecycle.spec_a2["agent_spec_id"]
    events[3]["spec_artifact_hash"] = compute_spec_artifact_hash(
        make_spec(
            revision=2, supersedes=lifecycle.spec_a1["agent_spec_id"],
            capabilities=["CI_READ", "GITHUB_METADATA_READ", "REPOSITORY_READ"],
            surfaces=["CHECK_RUNS", "ISSUES", "WORKFLOW_RUNS"], created_at_utc="2031-01-01T00:00:00Z",
        )
    )
    rechain(events)
    assert_not_certifiable(events, lifecycle.specs, "AGENT_SPEC_PROVENANCE_CONFLICT", position=4)


def test_invalid_published_spec_is_rejected_with_its_cause():
    broken = make_spec()
    broken["capabilities"] = ["REPOSITORY_READ", "CI_READ"]  # unsorted, ids recomputed
    seal_spec(broken)
    event = make_event(
        sequence=1, ordinal=1, spec=broken, event_type="AGENT_REGISTERED",
        previous_state=None, new_state="REGISTERED", reason_code="REGISTRATION_INITIAL",
        previous_event_hash="GENESIS",
    )
    result = assert_not_certifiable([event], {broken["agent_spec_id"]: artifact(broken)}, "SPEC_REFERENCE_INVALID", position=1)
    assert result.failure_cause == "SPEC_ARRAY_NOT_CANONICAL"


def test_artifact_must_be_for_the_event_agent_and_spec():
    lifecycle = Lifecycle()
    specs = lifecycle.copy_specs()
    specs[lifecycle.spec_a1["agent_spec_id"]] = artifact(lifecycle.spec_b1)  # other agent's bytes
    events = lifecycle.copy_events()
    events[0]["spec_artifact_hash"] = compute_spec_artifact_hash(lifecycle.spec_b1)
    rechain(events)
    assert_not_certifiable(events, specs, "SPEC_REFERENCE_INVALID", position=1)
    for garbage in (b"not json", b"[]", b"\xff\xfe", b'{"a": 1.5}', b'{"a": 1, "a": 2}', b'{"a": NaN}'):
        specs = lifecycle.copy_specs()
        specs[lifecycle.spec_a1["agent_spec_id"]] = garbage
        events = lifecycle.copy_events()
        events[0]["spec_artifact_hash"] = hashlib.sha256(garbage).hexdigest()
        rechain(events)
        assert_not_certifiable(events, specs, "SPEC_REFERENCE_INVALID", position=1)


def test_registration_requires_revision_one():
    lifecycle = Lifecycle()
    specs = lifecycle.copy_specs()
    event = make_event(
        sequence=1, ordinal=1, spec=lifecycle.spec_a2, event_type="AGENT_REGISTERED",
        previous_state=None, new_state="REGISTERED", reason_code="REGISTRATION_INITIAL",
        previous_event_hash="GENESIS",
    )
    assert_not_certifiable([event], specs, "SPEC_REFERENCE_INVALID", position=1)


# --- Supersession and revision classification ---------------------------------


def _revision_chain(lifecycle, new_spec, reason="SPEC_REVISION_ESCALATING", agent_spec=None):
    specs = lifecycle.copy_specs()
    specs[new_spec["agent_spec_id"]] = artifact(new_spec)
    base = lifecycle.copy_events()[:2]
    event = make_event(
        sequence=3, ordinal=2, spec=new_spec, event_type="AGENT_SPEC_REVISED",
        previous_state="REGISTERED", new_state="REGISTERED", reason_code=reason,
        previous_event_hash=base[1]["event_hash"],
    )
    return base + [event], specs


def test_broken_supersession_is_rejected():
    lifecycle = Lifecycle()
    a1 = lifecycle.spec_a1["agent_spec_id"]
    cases = {
        "wrong predecessor": make_spec(revision=2, supersedes=lifecycle.spec_b1["agent_spec_id"], display_name="Wrong parent"),
        "skipped revision": make_spec(revision=3, supersedes=a1, display_name="Skipped"),
        "revision repeated": make_spec(revision=1, supersedes=None, display_name="Replaces itself"),
    }
    for name, spec in cases.items():
        events, specs = _revision_chain(lifecycle, spec, "SPEC_REVISION_NON_ESCALATING")
        assert_not_certifiable(events, specs, "SUPERSESSION_BREAK", position=3)


def test_resubmitting_the_current_spec_as_a_revision_is_rejected():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()[:2]
    event = make_event(
        sequence=3, ordinal=2, spec=lifecycle.spec_a1, event_type="AGENT_SPEC_REVISED",
        previous_state="REGISTERED", new_state="REGISTERED", reason_code="SPEC_REVISION_NON_ESCALATING",
        previous_event_hash=events[1]["event_hash"],
    )
    assert_not_certifiable(events + [event], lifecycle.specs, "SUPERSESSION_BREAK", position=3)


def test_revision_of_another_agents_spec_is_rejected():
    lifecycle = Lifecycle()
    foreign = make_scout_spec(revision=2, supersedes=lifecycle.spec_b1["agent_spec_id"])
    base = lifecycle.copy_events()[:2]
    specs = lifecycle.copy_specs()
    specs[foreign["agent_spec_id"]] = artifact(foreign)
    event = make_event(
        sequence=3, ordinal=2, spec=foreign, event_type="AGENT_SPEC_REVISED",
        previous_state="REGISTERED", new_state="REGISTERED", reason_code="SPEC_REVISION_NON_ESCALATING",
        previous_event_hash=base[1]["event_hash"],
    )
    event["agent_id"] = lifecycle.spec_a1["agent_id"]  # claims agent A, spec belongs to agent B
    event["event_id"] = ""
    seal_event(event)
    assert_not_certifiable(base + [event], specs, "SPEC_REFERENCE_INVALID", position=3)


def test_revision_class_must_match_the_computed_classification():
    lifecycle = Lifecycle()
    for wrong in ("SPEC_REVISION_NON_ESCALATING", "SPEC_REVISION_REDUCING"):
        events = lifecycle.copy_events()
        events[2] = make_event(
            sequence=3, ordinal=2, spec=lifecycle.spec_a2, event_type="AGENT_SPEC_REVISED",
            previous_state="REGISTERED", new_state="REGISTERED", reason_code=wrong,
            previous_event_hash=events[1]["event_hash"],
        )
        rechain(events)
        result = assert_not_certifiable(events, lifecycle.specs, "REVISION_CLASS_MISMATCH", position=3)
        assert "SPEC_REVISION_ESCALATING" in result.failure_detail
    reducing = make_spec(
        revision=2, supersedes=lifecycle.spec_a1["agent_spec_id"],
        capabilities=["REPOSITORY_READ"], surfaces=[], created_at_utc="2026-10-04T00:01:00Z",
    )
    events, specs = _revision_chain(lifecycle, reducing, "SPEC_REVISION_REDUCING")
    assert verify_chain(events, specs).status == STRUCTURALLY_VALID_CHAIN
    events, specs = _revision_chain(lifecycle, reducing, "SPEC_REVISION_ESCALATING")
    assert_not_certifiable(events, specs, "REVISION_CLASS_MISMATCH", position=3)


def test_suspended_retired_and_reinstated_must_keep_the_current_spec():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[3] = make_event(
        sequence=4, ordinal=3, spec=lifecycle.spec_a1, event_type="AGENT_SUSPENDED",
        previous_state="REGISTERED", new_state="SUSPENDED", reason_code="SUSPENSION_GOVERNANCE",
        previous_event_hash=events[2]["event_hash"], evidence_refs=[ISSUE_REF],
    )
    rechain(events)
    assert_not_certifiable(events, lifecycle.specs, "SPEC_REFERENCE_INVALID", position=4)


# --- Revalidation semantics ----------------------------------------------------


def _counting_validator(monkeypatch, fail_on_call=None):
    calls = []
    real = integrity.validate_agent_spec

    def counting(spec):
        calls.append(spec["agent_spec_id"])
        if fail_on_call is not None and len(calls) == fail_on_call:
            from agent_economy.agent_registry import AgentRegistryError

            raise AgentRegistryError("CAPABILITY_ABOVE_CEILING", "constitution amended")
        return real(spec)

    monkeypatch.setattr(integrity, "validate_agent_spec", counting)
    return calls


def test_reinstatement_revalidates_the_current_spec(monkeypatch):
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()[:2]
    suspend = make_event(
        sequence=3, ordinal=2, spec=lifecycle.spec_a1, event_type="AGENT_SUSPENDED",
        previous_state="REGISTERED", new_state="SUSPENDED", reason_code="SUSPENSION_GOVERNANCE",
        previous_event_hash=events[1]["event_hash"], evidence_refs=[ISSUE_REF],
    )
    reinstate = make_event(
        sequence=4, ordinal=3, spec=lifecycle.spec_a1, event_type="AGENT_REINSTATED",
        previous_state="SUSPENDED", new_state="REGISTERED", reason_code="REINSTATEMENT_GOVERNANCE",
        previous_event_hash=suspend["event_hash"], evidence_refs=[COMMIT_REF],
    )
    chain = events + [suspend, reinstate]
    calls = _counting_validator(monkeypatch)
    assert verify_chain(chain, lifecycle.specs).status == STRUCTURALLY_VALID_CHAIN
    assert len(calls) == 3  # 2 registrations + the reinstatement; the suspension did not
    # the spec stops being valid under the schema in force: reinstatement is rejected
    _counting_validator(monkeypatch, fail_on_call=3)
    result = assert_not_certifiable(chain, lifecycle.specs, "SPEC_REFERENCE_INVALID", position=4)
    assert result.failure_cause == "CAPABILITY_ABOVE_CEILING"


def test_suspension_and_retirement_are_never_blocked_by_spec_revalidation(monkeypatch):
    lifecycle = Lifecycle()
    first = lifecycle.events[0]
    suspend = make_event(
        sequence=2, ordinal=2, spec=lifecycle.spec_a1, event_type="AGENT_SUSPENDED",
        previous_state="REGISTERED", new_state="SUSPENDED", reason_code="SUSPENSION_INCIDENT",
        previous_event_hash=first["event_hash"], evidence_refs=[ISSUE_REF],
    )
    retire = make_event(
        sequence=3, ordinal=3, spec=lifecycle.spec_a1, event_type="AGENT_RETIRED",
        previous_state="SUSPENDED", new_state="RETIRED", reason_code="RETIREMENT_GOVERNANCE",
        previous_event_hash=suspend["event_hash"], evidence_refs=[ISSUE_REF],
    )
    calls = _counting_validator(monkeypatch)
    result = verify_chain([first, suspend, retire], lifecycle.specs)
    assert result.status == STRUCTURALLY_VALID_CHAIN and len(calls) == 1
    assert result.agent_facts[0].state == "RETIRED"


# --- AC-06 timestamp regression -----------------------------------------------


def test_timestamp_regression_is_a_warning_and_never_a_failure_alone():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[2]["occurred_at_utc"] = "2020-01-01T00:00:00Z"
    rechain(events)
    result = verify_chain(events, lifecycle.specs)
    assert result.status == STRUCTURALLY_VALID_CHAIN  # registry_sequence is the order
    assert [(w.code, w.registry_sequence) for w in result.warnings] == [("TIMESTAMP_REGRESSION", 3)]
    # combined with a graver contradiction the failure is the graver one, warning kept as data
    events[4]["event_hash"] = "0" * 64
    failure = assert_not_certifiable(events, lifecycle.specs, "EVENT_HASH_MISMATCH", position=5)
    assert any(w.code == "TIMESTAMP_REGRESSION" for w in failure.warnings)


def test_ordering_ignores_timestamps_entirely():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    for index, event in enumerate(events):
        event["occurred_at_utc"] = f"2026-10-04T00:00:{59 - index:02d}Z"  # strictly decreasing
    rechain(events)
    result = verify_chain(events, lifecycle.specs)
    assert result.status == STRUCTURALLY_VALID_CHAIN and len(result.warnings) == 5


def test_every_failure_reports_the_offending_position_and_keeps_only_a_prefix_count():
    lifecycle = Lifecycle()
    for position in range(1, 7):
        events = lifecycle.copy_events()
        events[position - 1]["event_hash"] = "f" * 64
        result = assert_not_certifiable(events, lifecycle.specs, "EVENT_HASH_MISMATCH", position=position)
        assert result.verified_event_count == position - 1
