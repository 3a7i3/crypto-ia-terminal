"""Pure quest/participation replay. Fixture roles convey no real authority."""

from __future__ import annotations

import json

from sentinel_activity.canonical import require
from sentinel_activity.contracts import QUEST_TYPES

TERMINAL = frozenset({"REJECTED", "COMPLETED", "FAILED"})
ROLES = {
    "QUEST_PROPOSED": "PROPOSER", "QUEST_APPROVED": "OPERATOR", "QUEST_REJECTED": "OPERATOR",
    "QUEST_PUBLISHED": "SECRETARIAT", "QUEST_ACCEPTED": "WORKER", "QUEST_DECLINED": "WORKER",
    "WORK_STARTED": "WORKER", "ARTIFACT_SUBMITTED": "WORKER", "REVIEW_PASSED": "REVIEWER",
    "REVIEW_FAILED": "REVIEWER", "QUEST_COMPLETED": "CLOSER", "QUEST_FAILED": "CLOSER",
}


def projection_bytes(projection: dict) -> bytes:
    """Internal aggregate, not a single event: separate 4 MiB cache budget."""
    raw = json.dumps(projection, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode()
    require(len(raw) <= 4 * 1024 * 1024, "BUDGET_EXCEEDED")
    return raw


def project(events: list[dict], policy: dict) -> dict:
    quests, participations = {}, {}
    for event in events:
        et, qid, actor = event["event_type"], event["quest_id"], event["actor_id"]
        payload = event["payload"]
        if et not in QUEST_TYPES:
            require(qid is None or qid in quests, "ILLEGAL_TRANSITION")
            continue
        role = policy["producers"][event["producer_id"]]["role"]
        require(role == ROLES[et], "ACTOR_DENIED")
        require(event["reason_declared"] is not None, "SCHEMA_VIOLATION")
        if et != "QUEST_PROPOSED":
            require(bool(event["evidence_refs"]), "EVIDENCE_INVALID")
        if et == "QUEST_PROPOSED":
            require(qid not in quests and event["causation_event_id"] is None, "ILLEGAL_TRANSITION")
            require(all(scope.startswith("fixture:") for scope in payload["scope"]), "PROVENANCE_DENIED")
            quests[qid] = {
                "state": "PROPOSED", "revision": 1, "proposal_event_id": event["event_id"],
                "approval_event_id": None, "authorization_ref": None, "worker": None, "attempt": 0,
                "submission_event_id": None, "review_event_id": None, "artifact_sha256": None,
                "last_event_id": event["event_id"], "correlation_id": event["correlation_id"],
                "budget_units": payload["budget_units"],
            }
            participations[qid] = {}
            continue
        require(qid in quests, "ILLEGAL_TRANSITION")
        q = quests[qid]
        require(q["state"] not in TERMINAL, "ILLEGAL_TRANSITION")
        require(payload["expected_revision"] == q["revision"], "REVISION_CONFLICT")
        require(event["correlation_id"] == q["correlation_id"] and
                event["causation_event_id"] == q["last_event_id"], "CAUSATION_INVALID")
        state = q["state"]
        if et in {"QUEST_APPROVED", "QUEST_REJECTED"}:
            require(state == "PROPOSED", "ILLEGAL_TRANSITION")
            require(payload["proposal_event_id"] == q["proposal_event_id"], "EVIDENCE_INVALID")
            require(event["authorization_ref"] is not None, "EVIDENCE_INVALID")
            q["state"] = "APPROVED" if et == "QUEST_APPROVED" else "REJECTED"
            if et == "QUEST_APPROVED":
                q["approval_event_id"] = event["event_id"]
                q["authorization_ref"] = event["authorization_ref"]
        elif et == "QUEST_PUBLISHED":
            require(state == "APPROVED", "ILLEGAL_TRANSITION")
            require(payload["approval_event_id"] == q["approval_event_id"] and
                    event["authorization_ref"] == q["authorization_ref"], "EVIDENCE_INVALID")
            q["state"] = "PUBLISHED"
        elif et in {"QUEST_ACCEPTED", "QUEST_DECLINED"}:
            require(state in {"PUBLISHED", "IN_PROGRESS", "CHANGES_REQUESTED"}, "ILLEGAL_TRANSITION")
            require(actor not in participations[qid], "ILLEGAL_TRANSITION")
            if et == "QUEST_ACCEPTED":
                require(state == "PUBLISHED" and q["worker"] is None, "ALREADY_ASSIGNED")
                q["worker"] = actor
                participations[qid][actor] = "ACCEPTED"
            else:
                participations[qid][actor] = "DECLINED"
        elif et == "WORK_STARTED":
            require(actor == q["worker"], "ACTOR_DENIED")
            require(state in {"PUBLISHED", "CHANGES_REQUESTED"}, "ILLEGAL_TRANSITION")
            require(payload["attempt"] == q["attempt"] + 1, "ILLEGAL_TRANSITION")
            require(payload["attempt"] <= q["budget_units"], "BUDGET_EXCEEDED")
            q.update(state="IN_PROGRESS", attempt=payload["attempt"], submission_event_id=None,
                     review_event_id=None, artifact_sha256=None)
        elif et == "ARTIFACT_SUBMITTED":
            require(actor == q["worker"], "ACTOR_DENIED")
            require(state == "IN_PROGRESS" and payload["attempt"] == q["attempt"], "ILLEGAL_TRANSITION")
            require(payload["artifact_ref"] in event["evidence_refs"], "EVIDENCE_INVALID")
            q.update(state="SUBMITTED", submission_event_id=event["event_id"],
                     artifact_sha256=payload["artifact_sha256"])
        elif et in {"REVIEW_PASSED", "REVIEW_FAILED"}:
            require(actor != q["worker"], "SELF_REVIEW_DENIED")
            require(state == "SUBMITTED", "ILLEGAL_TRANSITION")
            require(payload["submission_event_id"] == q["submission_event_id"], "EVIDENCE_INVALID")
            require("fixture:sha256:" + q["artifact_sha256"] in event["evidence_refs"], "EVIDENCE_INVALID")
            q.update(state="REVIEW_PASSED" if et == "REVIEW_PASSED" else "CHANGES_REQUESTED",
                     review_event_id=event["event_id"])
        elif et == "QUEST_COMPLETED":
            require(state == "REVIEW_PASSED" and payload["review_event_id"] == q["review_event_id"],
                    "ILLEGAL_TRANSITION")
            require(actor != q["worker"], "SELF_REVIEW_DENIED")
            q["state"] = "COMPLETED"
        elif et == "QUEST_FAILED":
            q["state"] = "FAILED"
        q["revision"] += 1
        q["last_event_id"] = event["event_id"]
    result = {"quests": quests, "participations": participations}
    projection_bytes(result)
    return result
