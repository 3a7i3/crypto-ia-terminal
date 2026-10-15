"""Synthetic builders for AgentSpec / AgentRegistryEvent test material.

FIXTURE_ONLY / NOT_REGISTRY_DATA / NOT_OPERATOR_DATA / NOT_DEPLOYED.
Every identity is synthetic (``fixture_*``); no .github/agents profile is used.

``seal_*`` recompute identities so a single rule can be isolated; a test that
wants a self-inconsistent input simply mutates *after* sealing, and the package
under test always receives the invalid input exactly as built.
"""

from __future__ import annotations

import copy
from typing import Any

from agent_economy.agent_registry import (
    compute_agent_id,
    compute_agent_spec_id,
    compute_event_hash,
    compute_event_id,
    publication_json_bytes,
)
from agent_economy.agent_registry.spec import compute_spec_artifact_hash

SHA_A = "0123456789abcdef0123456789abcdef01234567"
SHA_B = "89abcdef0123456789abcdef0123456789abcdef"
ISSUE_REF = "github:issue:fixture-owner/fixture-repo#1"
COMMIT_REF = f"git:commit:{SHA_A}"
PR_REF = f"github:pr:fixture-owner/fixture-repo#2@{SHA_B}"
HASH_REF = "sha256:" + "ab" * 32


def seal_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Recompute agent_id and agent_spec_id in place and return the spec."""
    spec["agent_id"] = compute_agent_id(
        spec["namespace"], spec["canonical_name"], spec["agent_class"]
    )
    spec["agent_spec_id"] = compute_agent_spec_id(spec)
    return spec


def make_spec(
    *,
    canonical_name: str = "fixture_sensor_alpha",
    agent_class: str = "SENSOR",
    level: str = "F0",
    capabilities: list[str] | None = None,
    read_paths: list[str] | None = None,
    surfaces: list[str] | None = None,
    domains: list[str] | None = None,
    revision: int = 1,
    supersedes: str | None = None,
    display_name: str = "Fixture Sensor Alpha",
    purpose: str = "Synthetic fixture agent used only by tests, never registered.",
    created_from_ref: str = SHA_A,
    created_at_utc: str = "2026-10-04T00:00:00Z",
) -> dict[str, Any]:
    spec = {
        "agent_schema": "AGENT_SPEC_V1",
        "constitution_version": "AGENT_ECON_A0_FOREST_V1",
        "agent_id": "",
        "agent_spec_id": "",
        "spec_revision": revision,
        "namespace": "forest",
        "canonical_name": canonical_name,
        "display_name": display_name,
        "agent_class": agent_class,
        "maintenance_level": level,
        "purpose": purpose,
        "capabilities": (
            ["CI_READ", "REPOSITORY_READ"] if capabilities is None else capabilities
        ),
        "scope_policy": {
            "repository_read_paths": ["docs/"] if read_paths is None else read_paths,
            "repository_write_paths_future": [],
            "github_surfaces": (
                ["CHECK_RUNS", "WORKFLOW_RUNS"] if surfaces is None else surfaces
            ),
            "artifact_domains": [] if domains is None else domains,
        },
        "independence_policy": {
            "own_work_review_forbidden": True,
            "independent_review_required": True,
        },
        "authority_policy": {
            "authority_ceiling": "NO_RUNTIME_AUTHORITY",
            "human_decision": False,
            "economic_status_grants_authority": False,
            "reputation_grants_authority": False,
            "consensus_grants_authority": False,
        },
        "execution_binding": {
            "status": "UNBOUND",
            "provider": None,
            "model": None,
            "credential_mode": "NONE",
        },
        "supersedes_spec_id": supersedes,
        "created_from_ref": created_from_ref,
        "created_at_utc": created_at_utc,
    }
    return seal_spec(spec)


def make_scout_spec(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "canonical_name": "fixture_scout_beta",
        "agent_class": "SCOUT",
        "level": "F1",
        "capabilities": ["CANDIDATE_PROBLEM_PROPOSE", "REPOSITORY_SEARCH"],
        "read_paths": ["tests/"],
        "surfaces": [],
        "display_name": "Fixture Scout Beta",
    }
    params.update(overrides)
    return make_spec(**params)


def artifact(spec: dict[str, Any]) -> bytes:
    return publication_json_bytes(spec)


def seal_event(event: dict[str, Any]) -> dict[str, Any]:
    event["event_id"] = compute_event_id(event)
    event["event_hash"] = compute_event_hash(event)
    return event


def make_event(
    *,
    sequence: int,
    ordinal: int,
    spec: dict[str, Any],
    event_type: str,
    previous_state: str | None,
    new_state: str,
    reason_code: str,
    previous_event_hash: str,
    evidence_refs: list[str] | None = None,
    occurred_at_utc: str | None = None,
    reason_detail: str | None = None,
    spec_artifact_hash: str | None = None,
) -> dict[str, Any]:
    event = {
        "event_schema": "AGENT_REGISTRY_EVENT_V1",
        "event_id": "",
        "registry_sequence": sequence,
        "agent_transition_ordinal": ordinal,
        "agent_id": spec["agent_id"],
        "agent_spec_id": spec["agent_spec_id"],
        "spec_artifact_hash": (
            compute_spec_artifact_hash(spec)
            if spec_artifact_hash is None
            else spec_artifact_hash
        ),
        "event_type": event_type,
        "previous_state": previous_state,
        "new_state": new_state,
        "reason_code": reason_code,
        "reason_detail": reason_detail,
        "evidence_refs": [COMMIT_REF, ISSUE_REF] if evidence_refs is None else evidence_refs,
        "occurred_at_utc": (
            f"2026-10-04T00:00:{sequence:02d}Z"
            if occurred_at_utc is None
            else occurred_at_utc
        ),
        "previous_event_hash": previous_event_hash,
        "event_hash": "",
    }
    return seal_event(event)


class Lifecycle:
    """A reproducible 6-event, 2-agent registry history (synthetic)."""

    def __init__(self) -> None:
        self.spec_a1 = make_spec()
        self.spec_a2 = make_spec(
            revision=2,
            supersedes=self.spec_a1["agent_spec_id"],
            capabilities=["CI_READ", "GITHUB_METADATA_READ", "REPOSITORY_READ"],
            surfaces=["CHECK_RUNS", "ISSUES", "WORKFLOW_RUNS"],
            created_at_utc="2026-10-04T00:00:30Z",
        )
        self.spec_b1 = make_scout_spec()
        self.specs: dict[str, bytes] = {
            s["agent_spec_id"]: artifact(s)
            for s in (self.spec_a1, self.spec_a2, self.spec_b1)
        }
        e1 = make_event(
            sequence=1, ordinal=1, spec=self.spec_a1, event_type="AGENT_REGISTERED",
            previous_state=None, new_state="REGISTERED",
            reason_code="REGISTRATION_INITIAL", previous_event_hash="GENESIS",
        )
        e2 = make_event(
            sequence=2, ordinal=1, spec=self.spec_b1, event_type="AGENT_REGISTERED",
            previous_state=None, new_state="REGISTERED",
            reason_code="REGISTRATION_INITIAL", previous_event_hash=e1["event_hash"],
        )
        e3 = make_event(
            sequence=3, ordinal=2, spec=self.spec_a2, event_type="AGENT_SPEC_REVISED",
            previous_state="REGISTERED", new_state="REGISTERED",
            reason_code="SPEC_REVISION_ESCALATING", previous_event_hash=e2["event_hash"],
        )
        e4 = make_event(
            sequence=4, ordinal=3, spec=self.spec_a2, event_type="AGENT_SUSPENDED",
            previous_state="REGISTERED", new_state="SUSPENDED",
            reason_code="SUSPENSION_GOVERNANCE", previous_event_hash=e3["event_hash"],
            evidence_refs=[ISSUE_REF],
        )
        e5 = make_event(
            sequence=5, ordinal=4, spec=self.spec_a2, event_type="AGENT_REINSTATED",
            previous_state="SUSPENDED", new_state="REGISTERED",
            reason_code="REINSTATEMENT_GOVERNANCE", previous_event_hash=e4["event_hash"],
            evidence_refs=[COMMIT_REF, ISSUE_REF],
        )
        e6 = make_event(
            sequence=6, ordinal=2, spec=self.spec_b1, event_type="AGENT_RETIRED",
            previous_state="REGISTERED", new_state="RETIRED",
            reason_code="RETIREMENT_GOVERNANCE", previous_event_hash=e5["event_hash"],
            evidence_refs=[ISSUE_REF],
        )
        self.events: list[dict[str, Any]] = [e1, e2, e3, e4, e5, e6]

    def copy_events(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.events)

    def copy_specs(self) -> dict[str, bytes]:
        return dict(self.specs)


def rechain(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reseal ids/hashes and relink previous_event_hash (isolates one rule)."""
    previous = "GENESIS"
    for event in events:
        event["previous_event_hash"] = previous
        seal_event(event)
        previous = event["event_hash"]
    return events
