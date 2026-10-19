"""Fixture producer bindings, not real-world authentication or A1 membership."""

from sentinel_activity.canonical import canonical_bytes, require, strict_loads
from sentinel_activity.contracts import identifier

ROLES = frozenset({"PROPOSER", "OPERATOR", "SECRETARIAT", "WORKER", "REVIEWER", "CLOSER", "OBSERVER"})


def validate_policy(policy: dict) -> dict:
    raw = canonical_bytes(policy, 16_384)
    require(type(policy) is dict and set(policy) == {"version", "producers"}, "POLICY_MISMATCH")
    require(identifier(policy["version"]), "POLICY_MISMATCH")
    producers = policy["producers"]
    require(type(producers) is dict and 1 <= len(producers) <= 16, "POLICY_MISMATCH")
    actors = set()
    for producer_id, binding in producers.items():
        require(identifier(producer_id) and producer_id.startswith("fixture-"), "POLICY_MISMATCH")
        require(type(binding) is dict and set(binding) == {"actor_id", "actor_kind", "actor_version", "role"},
                "POLICY_MISMATCH")
        actor = binding["actor_id"]
        require(identifier(actor) and actor.startswith("fixture-") and actor not in actors, "POLICY_MISMATCH")
        actors.add(actor)
        require(type(binding["actor_kind"]) is str and binding["actor_kind"] in {"AGENT", "SYSTEM", "OPERATOR"},
                "POLICY_MISMATCH")
        require(binding["actor_version"] is None or identifier(binding["actor_version"]), "POLICY_MISMATCH")
        require(type(binding["role"]) is str and binding["role"] in ROLES, "POLICY_MISMATCH")
        require((binding["role"] == "OPERATOR") == (binding["actor_kind"] == "OPERATOR"), "POLICY_MISMATCH")
    return strict_loads(raw)


def admit(event: dict, producer_id: str, policy: dict) -> None:
    require(type(producer_id) is str and producer_id in policy["producers"], "ACTOR_DENIED")
    binding = policy["producers"][producer_id]
    require(all(event[key] == binding[key] for key in ("actor_id", "actor_kind", "actor_version")), "ACTOR_DENIED")
    require(event["source_kind"] == "SIMULATED", "PROVENANCE_DENIED")
    require(all(ref.startswith("fixture:") for ref in event["evidence_refs"]), "PROVENANCE_DENIED")
    require(event["authorization_ref"] is None or event["authorization_ref"].startswith("fixture:"),
            "PROVENANCE_DENIED")
    if "artifact_ref" in event["payload"]:
        require(event["payload"]["artifact_ref"].startswith("fixture:"), "PROVENANCE_DENIED")
