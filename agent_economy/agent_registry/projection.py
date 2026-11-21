"""Pure deterministic registry projection and availability (A1 sections 7, 9.2).

``project_registry`` is a pure function of (ordered events, exact published spec
artifacts). It exposes only contract facts per agent: ``agent_id``,
``current_agent_spec_id``, ``state`` (REGISTERED / SUSPENDED / RETIRED),
``agent_transition_ordinal`` and ``last_registry_sequence``. It never exposes
running / active / online / healthy / authorized / provider / model, and never a
count of "live" agents.

AVAILABLE is UNREACHABLE in A1 SOURCE: it requires an authenticated registrar
and an independent completeness / anti-rollback anchor, both UNRESOLVED
(Q1, Q2). The function therefore has no parameter that can attest either, and a
locally valid hash chain is reported as UNKNOWN with a prefix-only diagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .integrity import (
    NOT_CERTIFIABLE as CHAIN_NOT_CERTIFIABLE,
    STRUCTURALLY_VALID_CHAIN,
    ChainWarning,
    verify_chain,
)

# Four-value registry availability (A1 section 7.3).
NON_DEPLOYED = "NON_DEPLOYED"
UNKNOWN = "UNKNOWN"
NOT_CERTIFIABLE = "NOT_CERTIFIABLE"
AVAILABLE = "AVAILABLE"
AVAILABILITY_VALUES = frozenset({NON_DEPLOYED, UNKNOWN, NOT_CERTIFIABLE, AVAILABLE})

PREFIX_ONLY_UNCERTIFIED = "PREFIX_ONLY_UNCERTIFIED"


@dataclass(frozen=True)
class AgentProjection:
    """Contract facts of one agent, labelled as an uncertified prefix view."""

    agent_id: str
    current_agent_spec_id: str
    state: str
    agent_transition_ordinal: int
    last_registry_sequence: int
    evidence_label: str = PREFIX_ONLY_UNCERTIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "current_agent_spec_id": self.current_agent_spec_id,
            "state": self.state,
            "agent_transition_ordinal": self.agent_transition_ordinal,
            "last_registry_sequence": self.last_registry_sequence,
            "evidence_label": self.evidence_label,
        }


@dataclass(frozen=True)
class PrefixDiagnostic:
    """AP-06: a labelled diagnostic of the verified prefix, never a state."""

    label: str
    verified_event_count: int
    last_registry_sequence: int | None
    agent_facts: tuple[AgentProjection, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "verified_event_count": self.verified_event_count,
            "last_registry_sequence": self.last_registry_sequence,
            "agent_facts": [fact.to_dict() for fact in self.agent_facts],
        }


@dataclass(frozen=True)
class RegistryProjection:
    availability: str
    chain_status: str | None
    # Served states: always None in A1 SOURCE because AVAILABLE is unreachable.
    # None means "unknown", never "zero agents".
    agent_states: tuple[AgentProjection, ...] | None
    prefix_diagnostic: PrefixDiagnostic | None
    failure_code: str | None = None
    failure_detail: str | None = None
    failure_position: int | None = None
    warnings: tuple[ChainWarning, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "availability": self.availability,
            "chain_status": self.chain_status,
            "agent_states": (
                None
                if self.agent_states is None
                else [state.to_dict() for state in self.agent_states]
            ),
            "prefix_diagnostic": (
                None if self.prefix_diagnostic is None else self.prefix_diagnostic.to_dict()
            ),
            "failure_code": self.failure_code,
            "failure_detail": self.failure_detail,
            "failure_position": self.failure_position,
            "warnings": [
                {"code": w.code, "registry_sequence": w.registry_sequence, "detail": w.detail}
                for w in self.warnings
            ],
        }


def project_registry(
    events: Sequence[Mapping[str, Any]] | None,
    specs: Mapping[str, bytes] | None = None,
) -> RegistryProjection:
    """Project the registry from events and exact spec artifacts (AP-01 ... AP-06).

    * ``events is None``: no registry/artifact exists -> NON_DEPLOYED (not "0 agents").
    * events not a list/tuple (unreadable): UNKNOWN.
    * any AS/AE/AC violation: NOT_CERTIFIABLE, no state served ("last good state"
      is never served as truth).
    * structurally valid chain: UNKNOWN (completeness and registrar unattested),
      with a PREFIX_ONLY_UNCERTIFIED diagnostic.
    """
    if events is None:
        return RegistryProjection(NON_DEPLOYED, None, None, None)
    if not isinstance(events, (list, tuple)):
        return RegistryProjection(UNKNOWN, None, None, None, failure_code="UNREADABLE")

    verification = verify_chain(events, specs)
    if verification.status == CHAIN_NOT_CERTIFIABLE:
        return RegistryProjection(
            availability=NOT_CERTIFIABLE,
            chain_status=verification.status,
            agent_states=None,
            prefix_diagnostic=PrefixDiagnostic(
                PREFIX_ONLY_UNCERTIFIED,
                verification.verified_event_count,
                verification.last_registry_sequence,
                (),
            ),
            failure_code=verification.failure_code,
            failure_detail=verification.failure_detail,
            failure_position=verification.failure_position,
            warnings=verification.warnings,
        )

    if verification.status != STRUCTURALLY_VALID_CHAIN:  # pragma: no cover
        raise AssertionError("unexpected chain status")
    facts = tuple(
        AgentProjection(
            agent_id=fact.agent_id,
            current_agent_spec_id=fact.current_agent_spec_id,
            state=fact.state,
            agent_transition_ordinal=fact.agent_transition_ordinal,
            last_registry_sequence=fact.last_registry_sequence,
        )
        for fact in verification.agent_facts
    )
    return RegistryProjection(
        availability=UNKNOWN,  # AVAILABLE needs Q1 + Q2; unreachable here
        chain_status=verification.status,
        agent_states=None,
        prefix_diagnostic=PrefixDiagnostic(
            PREFIX_ONLY_UNCERTIFIED,
            verification.verified_event_count,
            verification.last_registry_sequence,
            facts,
        ),
        warnings=verification.warnings,
    )
