"""Fixture-only quest narrative; roles are NOT A1 registrations."""

import hashlib

from sentinel_activity.canonical import parse_utc
from sentinel_activity.store import ActivityStore
from tests.sentinel_activity.builders import NOW, candidate

ARTIFACT_HASH = hashlib.sha256(b"synthetic artifact, not executed").hexdigest()
ROLE_ACTORS = {
    "sentinel": ("AGENT", "PROPOSER"), "operator": ("OPERATOR", "OPERATOR"),
    "secretary": ("SYSTEM", "SECRETARIAT"), "a": ("AGENT", "WORKER"),
    "b": ("AGENT", "WORKER"), "reviewer": ("AGENT", "REVIEWER"), "closer": ("SYSTEM", "CLOSER"),
}


def quest_policy():
    return {"version": "fixture-policy-quest", "producers": {
        "fixture-" + name: {"actor_id": "fixture-" + name, "actor_kind": kind,
                            "actor_version": None, "role": role}
        for name, (kind, role) in ROLE_ACTORS.items()}}


def create_quests(tmp_path):
    root = tmp_path / "j01-lab-quests"
    root.mkdir(mode=0o700)
    return ActivityStore.create(root, quest_policy(), ledger_id="fixture-quest-journal",
                                clock=lambda: parse_utc(NOW))


def step(store, event_type, actor, **overrides):
    _, events, projection = store.snapshot()
    q = projection["quests"].get("fixture-q")
    payload = {"expected_revision": q["revision"]} if q else {}
    if event_type == "QUEST_PROPOSED":
        payload = {"title": "Synthetic diagnostic", "scope": ["fixture:lab"],
                   "budget_units": 3, "acceptance_criteria": ["Synthetic artifact reviewed"]}
    elif event_type in {"QUEST_APPROVED", "QUEST_REJECTED"}:
        payload["proposal_event_id"] = q["proposal_event_id"]
    elif event_type == "QUEST_PUBLISHED":
        payload["approval_event_id"] = q["approval_event_id"]
    elif event_type == "WORK_STARTED":
        payload["attempt"] = q["attempt"] + 1
    elif event_type == "ARTIFACT_SUBMITTED":
        payload.update(attempt=q["attempt"], artifact_ref="fixture:artifact", artifact_sha256=ARTIFACT_HASH)
    elif event_type.startswith("REVIEW_"):
        payload["submission_event_id"] = q["submission_event_id"]
    elif event_type == "QUEST_COMPLETED":
        payload["review_event_id"] = q["review_event_id"]
    elif event_type == "QUEST_FAILED":
        payload["reason_code"] = "FIXTURE_FAILURE"
    event = candidate("fixture-e" + str(len(events) + 1), event_type, "fixture-" + actor,
                      ROLE_ACTORS[actor][0], "fixture-q", q["last_event_id"] if q else None, payload)
    if event_type in {"QUEST_APPROVED", "QUEST_REJECTED", "QUEST_PUBLISHED"}:
        event["authorization_ref"] = "fixture:publication-only"
    if event_type == "ARTIFACT_SUBMITTED":
        event["evidence_refs"] = ["fixture:artifact"]
    elif event_type.startswith("REVIEW_"):
        event["evidence_refs"] = ["fixture:sha256:" + ARTIFACT_HASH]
    event.update(overrides)
    return event


NARRATIVE = [
    ("QUEST_PROPOSED", "sentinel"), ("QUEST_APPROVED", "operator"),
    ("QUEST_PUBLISHED", "secretary"), ("QUEST_ACCEPTED", "a"), ("QUEST_DECLINED", "b"),
    ("WORK_STARTED", "a"), ("ARTIFACT_SUBMITTED", "a"), ("REVIEW_PASSED", "reviewer"),
    ("QUEST_COMPLETED", "closer"),
]


def prefix(store, count):
    for et, actor in NARRATIVE[:count]:
        store.append(step(store, et, actor), producer_id="fixture-" + actor)
