from copy import deepcopy

import pytest

from sentinel_activity.canonical import LedgerError
from sentinel_activity.quests import project
from tests.sentinel_activity.builders import candidate
from tests.sentinel_activity.quest_builders import NARRATIVE, create_quests, prefix, step


def test_acceptance_and_decline_are_separate_from_completion(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 5)
    meta, events, projection = store.snapshot()
    assert len(events) == 5
    assert projection["quests"]["fixture-q"]["state"] == "PUBLISHED"
    assert projection["participations"]["fixture-q"] == {"fixture-a": "ACCEPTED", "fixture-b": "DECLINED"}
    assert projection == project(events, meta["policy"])
    for et, actor in NARRATIVE[5:]:
        store.append(step(store, et, actor), producer_id="fixture-" + actor)
    assert store.snapshot()[2]["quests"]["fixture-q"]["state"] == "COMPLETED"
    assert {e["source_kind"] for e in store.snapshot()[1]} == {"SIMULATED"}


@pytest.mark.parametrize("count,et,actor", [
    (1, "QUEST_APPROVED", "a"), (2, "QUEST_PUBLISHED", "operator"),
    (3, "QUEST_ACCEPTED", "reviewer"), (5, "WORK_STARTED", "b"),
    (6, "ARTIFACT_SUBMITTED", "b"), (7, "REVIEW_PASSED", "a"),
    (8, "QUEST_COMPLETED", "a"),
])
def test_wrong_actor_has_no_effect(tmp_path, count, et, actor):
    store = create_quests(tmp_path)
    prefix(store, count)
    before = store.snapshot()
    with pytest.raises(LedgerError, match="ACTOR_DENIED"):
        store.append(step(store, et, actor), producer_id="fixture-" + actor)
    assert store.snapshot() == before


@pytest.mark.parametrize("count,et,actor", [
    (1, "QUEST_PUBLISHED", "secretary"), (1, "QUEST_ACCEPTED", "a"),
    (3, "WORK_STARTED", "a"), (5, "ARTIFACT_SUBMITTED", "a"),
    (6, "REVIEW_PASSED", "reviewer"), (7, "QUEST_COMPLETED", "closer"),
    (9, "QUEST_FAILED", "closer"), (9, "QUEST_DECLINED", "b"),
])
def test_invalid_transition_fails_closed(tmp_path, count, et, actor):
    store = create_quests(tmp_path)
    prefix(store, count)
    with pytest.raises(LedgerError):
        store.append(step(store, et, actor), producer_id="fixture-" + actor)
    assert len(store.snapshot()[1]) == count


def test_rejected_quest_cannot_be_published(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 1)
    store.append(step(store, "QUEST_REJECTED", "operator"), producer_id="fixture-operator")
    event = step(store, "QUEST_PUBLISHED", "secretary")
    event["payload"]["approval_event_id"] = "fixture-nonexistent-approval"
    with pytest.raises(LedgerError, match="ILLEGAL_TRANSITION"):
        store.append(event, producer_id="fixture-secretary")


def test_failed_review_allows_new_explicit_attempt(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 7)
    old_submission = store.snapshot()[1][-1]["event_id"]
    store.append(step(store, "REVIEW_FAILED", "reviewer"), producer_id="fixture-reviewer")
    assert store.snapshot()[2]["quests"]["fixture-q"]["state"] == "CHANGES_REQUESTED"
    store.append(step(store, "WORK_STARTED", "a"), producer_id="fixture-a")
    store.append(step(store, "ARTIFACT_SUBMITTED", "a"), producer_id="fixture-a")
    event = step(store, "REVIEW_PASSED", "reviewer")
    event["payload"]["submission_event_id"] = old_submission
    with pytest.raises(LedgerError, match="EVIDENCE_INVALID"):
        store.append(event, producer_id="fixture-reviewer")
    store.append(step(store, "REVIEW_PASSED", "reviewer"), producer_id="fixture-reviewer")
    store.append(step(store, "QUEST_COMPLETED", "closer"), producer_id="fixture-closer")


def test_publication_must_reference_exact_approval(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 2)
    event = step(store, "QUEST_PUBLISHED", "secretary", authorization_ref="fixture:other-approval")
    with pytest.raises(LedgerError, match="EVIDENCE_INVALID"):
        store.append(event, producer_id="fixture-secretary")


def test_revision_and_accepted_worker_are_serialized(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 3)
    a = step(store, "QUEST_ACCEPTED", "a")
    b = step(store, "QUEST_ACCEPTED", "b", event_id="fixture-other")
    store.append(a, producer_id="fixture-a")
    with pytest.raises(LedgerError, match="REVISION_CONFLICT"):
        store.append(b, producer_id="fixture-b")
    with pytest.raises(LedgerError, match="ALREADY_ASSIGNED"):
        store.append(step(store, "QUEST_ACCEPTED", "b"), producer_id="fixture-b")


def test_self_review_guard_in_pure_replay(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 7)
    meta, events, _ = store.snapshot()
    forged = step(store, "REVIEW_PASSED", "reviewer")
    forged["producer_id"] = "fixture-reviewer"
    forged["actor_id"] = "fixture-a"
    with pytest.raises(LedgerError, match="SELF_REVIEW_DENIED"):
        project(events + [forged], meta["policy"])


def test_interrupt_is_recorded_without_inventing_terminal_state(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 6)
    last = store.snapshot()[1][-1]
    event = candidate("fixture-interruption", "RUN_INTERRUPTED", "fixture-a", quest="fixture-q",
                      cause=last["event_id"], payload={"code": "FIXTURE_INTERRUPTION", "related_event_id": last["event_id"]})
    store.append(event, producer_id="fixture-a")
    assert store.snapshot()[2]["quests"]["fixture-q"]["state"] == "IN_PROGRESS"


def test_reason_and_exact_artifact_evidence_required(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 7)
    event = step(store, "REVIEW_PASSED", "reviewer", evidence_refs=["fixture:unrelated"])
    with pytest.raises(LedgerError, match="EVIDENCE_INVALID"):
        store.append(event, producer_id="fixture-reviewer")
    event = step(store, "REVIEW_PASSED", "reviewer", reason_declared=None)
    with pytest.raises(LedgerError, match="SCHEMA_VIOLATION"):
        store.append(event, producer_id="fixture-reviewer")


def test_synthetic_approval_cannot_become_real(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 1)
    event = step(store, "QUEST_APPROVED", "operator", source_kind="OPERATOR_DECISION")
    with pytest.raises(LedgerError, match="PROVENANCE_DENIED"):
        store.append(event, producer_id="fixture-operator")


def test_projection_inputs_not_mutated(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 9)
    meta, events, _ = store.snapshot()
    before = deepcopy(events)
    project(events, meta["policy"])
    assert events == before
