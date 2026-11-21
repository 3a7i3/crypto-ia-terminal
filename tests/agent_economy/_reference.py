"""Independent stdlib-only reference of the certified A1 formulas.

It deliberately does NOT import agent_economy: golden vectors are recomputed
from the contract text (A1 sections 2.1, 2.2, 2.3, 3.1, 8.3, 8.6, AW-03), so a
bug shared with the implementation cannot validate itself.
FIXTURE_ONLY / NOT_REGISTRY_DATA / NOT_OPERATOR_DATA / NOT_DEPLOYED.
"""

from __future__ import annotations

import hashlib
import json


def canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def agent_id(namespace, canonical_name, agent_class) -> str:
    return sha(
        {
            "agent_identity_schema": "agent-econ.a1.agent-identity.v1",
            "namespace": namespace,
            "canonical_name": canonical_name,
            "agent_class": agent_class,
        }
    )


SPEC_ID_FIELDS = (
    "agent_schema constitution_version agent_id spec_revision namespace canonical_name "
    "display_name agent_class maintenance_level purpose capabilities scope_policy "
    "independence_policy authority_policy execution_binding supersedes_spec_id"
).split()


def agent_spec_id(spec) -> str:
    document = {"agent_spec_identity_schema": "agent-econ.a1.agent-spec-identity.v1"}
    document.update({name: spec[name] for name in SPEC_ID_FIELDS})
    return sha(document)


def artifact_bytes(spec) -> bytes:
    return (
        json.dumps(spec, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")


def artifact_hash(spec) -> str:
    return hashlib.sha256(artifact_bytes(spec)).hexdigest()


def event_id(event) -> str:
    fields = (
        "agent_id agent_transition_ordinal event_type previous_state new_state "
        "agent_spec_id evidence_refs reason_code"
    ).split()
    document = {"agent_event_identity_schema": "agent-econ.a1.agent-event-identity.v1"}
    document.update({name: event[name] for name in fields})
    return sha(document)


def event_hash(event) -> str:
    return sha({k: v for k, v in event.items() if k != "event_hash"})
