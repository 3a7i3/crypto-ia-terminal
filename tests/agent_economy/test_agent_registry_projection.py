"""Pure projection and availability: AP-01 ... AP-06, AVAILABLE unreachable."""

from __future__ import annotations

import ast
import copy
import dataclasses
import inspect
import json
import random

import pytest

from agent_economy.agent_registry import projection as projection_module
from agent_economy.agent_registry.projection import (
    AVAILABILITY_VALUES,
    AVAILABLE,
    NON_DEPLOYED,
    NOT_CERTIFIABLE,
    PREFIX_ONLY_UNCERTIFIED,
    UNKNOWN,
    AgentProjection,
    PrefixDiagnostic,
    RegistryProjection,
    project_registry,
)
from tests.agent_economy._builders import Lifecycle, rechain

FORBIDDEN_WORDS = (
    "running", "active", "online", "healthy", "authorized", "authorised",
    "provider", "model", "agent_count", "agents_count", "alive", "live",
)


def all_field_names(cls) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


def test_availability_vocabulary_is_the_four_value_model():
    assert AVAILABILITY_VALUES == {"NON_DEPLOYED", "UNKNOWN", "NOT_CERTIFIABLE", "AVAILABLE"}


def test_absent_registry_is_non_deployed_not_zero_agents():
    result = project_registry(None)
    assert result.availability == NON_DEPLOYED
    assert result.agent_states is None and result.prefix_diagnostic is None
    assert result.chain_status is None


def test_unreadable_registry_is_unknown():
    for bad in ("events.jsonl", {"a": 1}, 7, iter([])):
        result = project_registry(bad)
        assert result.availability == UNKNOWN and result.agent_states is None


def test_empty_registry_is_unknown_not_zero():
    result = project_registry([], {})
    assert result.availability == UNKNOWN
    assert result.agent_states is None  # "unknown", never an empty (zero) list
    assert result.prefix_diagnostic.label == PREFIX_ONLY_UNCERTIFIED
    assert result.prefix_diagnostic.verified_event_count == 0


def test_valid_chain_is_unknown_with_a_prefix_only_diagnostic_never_available():
    lifecycle = Lifecycle()
    result = project_registry(lifecycle.events, lifecycle.specs)
    assert result.availability == UNKNOWN != AVAILABLE
    assert result.chain_status == "STRUCTURALLY_VALID_CHAIN"
    assert result.agent_states is None
    diagnostic = result.prefix_diagnostic
    assert diagnostic.label == PREFIX_ONLY_UNCERTIFIED
    assert diagnostic.verified_event_count == 6 and diagnostic.last_registry_sequence == 6
    states = {f.agent_id: f for f in diagnostic.agent_facts}
    assert states[lifecycle.spec_a1["agent_id"]].state == "REGISTERED"
    assert states[lifecycle.spec_b1["agent_id"]].state == "RETIRED"  # retired is not absent
    assert all(f.evidence_label == PREFIX_ONLY_UNCERTIFIED for f in diagnostic.agent_facts)


def test_corruption_makes_the_registry_not_certifiable_and_serves_no_state():
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[4]["event_hash"] = "0" * 64
    result = project_registry(events, lifecycle.specs)
    assert result.availability == NOT_CERTIFIABLE
    assert result.agent_states is None
    assert result.prefix_diagnostic.agent_facts == ()  # no "last good state" served as truth
    assert result.prefix_diagnostic.verified_event_count == 4
    assert result.failure_code == "EVENT_HASH_MISMATCH" and result.failure_position == 5
    assert "agent_states\": null" in json.dumps(result.to_dict())


@pytest.mark.parametrize("index", range(6))
def test_any_single_event_corruption_never_yields_a_healthy_projection(index):
    lifecycle = Lifecycle()
    events = lifecycle.copy_events()
    events[index]["reason_detail"] = "tampered"
    result = project_registry(events, lifecycle.specs)
    assert result.availability == NOT_CERTIFIABLE
    assert result.agent_states is None and result.prefix_diagnostic.agent_facts == ()


def test_available_is_unreachable_whatever_the_input():
    lifecycle = Lifecycle()
    rng = random.Random(20261004)
    scenarios = [None, [], "x", lifecycle.copy_events()]
    scenarios += [lifecycle.copy_events()[:k] for k in range(1, 6)]
    for _ in range(200):  # random single mutations of the valid chain
        events = lifecycle.copy_events()
        victim = rng.choice(events)
        field = rng.choice(sorted(victim))
        victim[field] = rng.choice([None, 0, "", "0" * 64, [], True, "GENESIS"])
        if rng.random() < 0.5:
            rechain(events)
        scenarios.append(events)
    for events in scenarios:
        for specs in (lifecycle.specs, {}, None):
            assert project_registry(events, specs).availability != AVAILABLE


def test_nothing_can_attest_registrar_or_completeness():
    parameters = inspect.signature(project_registry).parameters
    assert list(parameters) == ["events", "specs"]
    tree = ast.parse(inspect.getsource(projection_module))
    loads = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "AVAILABLE" and isinstance(node.ctx, ast.Load)
    ]
    vocabulary = next(
        node for node in tree.body
        if isinstance(node, ast.Assign) and node.targets[0].id == "AVAILABILITY_VALUES"
    )
    inside_vocabulary = {id(n) for n in ast.walk(vocabulary.value)}
    assert loads and all(id(node) in inside_vocabulary for node in loads), (
        "AVAILABLE may only appear in the availability vocabulary, never as a returned value"
    )


def test_projection_exposes_only_contract_facts_never_liveness():
    for cls in (AgentProjection, PrefixDiagnostic, RegistryProjection):
        names = all_field_names(cls)
        for word in FORBIDDEN_WORDS:
            assert not any(word in name for name in names), (cls.__name__, word)
    assert all_field_names(AgentProjection) == {
        "agent_id", "current_agent_spec_id", "state", "agent_transition_ordinal",
        "last_registry_sequence", "evidence_label",
    }
    lifecycle = Lifecycle()
    rendered = json.dumps(project_registry(lifecycle.events, lifecycle.specs).to_dict()).lower()
    for word in ("running", "online", "healthy", "authorized", "provider", "alive"):
        assert word not in rendered
    assert '"active"' not in rendered and "agent_count" not in rendered


def test_projection_is_pure_deterministic_and_does_not_mutate():
    lifecycle = Lifecycle()
    events, specs = lifecycle.copy_events(), lifecycle.copy_specs()
    first = project_registry(events, specs).to_dict()
    second = project_registry(copy.deepcopy(events), dict(specs)).to_dict()
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert events == lifecycle.events and specs == lifecycle.specs


def test_agent_facts_are_ordered_by_agent_id():
    lifecycle = Lifecycle()
    facts = project_registry(lifecycle.events, lifecycle.specs).prefix_diagnostic.agent_facts
    assert [f.agent_id for f in facts] == sorted(f.agent_id for f in facts)


def test_registered_is_not_running_or_authorized():
    lifecycle = Lifecycle()
    fact = project_registry(lifecycle.events[:1], lifecycle.specs).prefix_diagnostic.agent_facts[0]
    assert fact.state == "REGISTERED"
    assert not hasattr(fact, "running") and not hasattr(fact, "authorized")
    # nothing in the verified spec grants anything: ceiling constants stay NO_RUNTIME_AUTHORITY
    spec = lifecycle.spec_a1
    assert spec["authority_policy"]["authority_ceiling"] == "NO_RUNTIME_AUTHORITY"
    assert spec["execution_binding"] == {
        "status": "UNBOUND", "provider": None, "model": None, "credential_mode": "NONE",
    }


def test_reinstated_agent_returns_to_registered_not_to_a_live_state():
    lifecycle = Lifecycle()
    facts = project_registry(lifecycle.events[:4], lifecycle.specs).prefix_diagnostic.agent_facts
    a = next(f for f in facts if f.agent_id == lifecycle.spec_a1["agent_id"])
    assert a.state == "SUSPENDED"
    facts = project_registry(lifecycle.events[:5], lifecycle.specs).prefix_diagnostic.agent_facts
    a = next(f for f in facts if f.agent_id == lifecycle.spec_a1["agent_id"])
    assert a.state == "REGISTERED"


def test_tail_truncation_stays_unknown():
    lifecycle = Lifecycle()
    for keep in range(0, 7):
        assert project_registry(lifecycle.copy_events()[:keep], lifecycle.specs).availability == UNKNOWN
