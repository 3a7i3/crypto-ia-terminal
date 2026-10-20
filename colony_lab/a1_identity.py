"""A1 identities for lab individuals, validated by the A1 code itself.

Every A1 rule (AS-01 … AS-13, their order and their rejection codes) comes from
``colony_lab.a1_ref``, an unchanged copy of the PR #374 validator. The lab adds
one rule after A1 has accepted a spec: no secret-shaped text
(``LAB_SECRET_TEXT_REJECTED``, J01 frozen profile). It registers nothing: the A1
registry is NON_DEPLOYED and the registrar is UNRESOLVED, so no registry state is
ever claimed here.
"""

from __future__ import annotations

import hashlib
from typing import Any

from colony_lab.a1_ref import capabilities as _caps
from colony_lab.a1_ref import spec as _spec
from colony_lab.a1_ref.canonical import AgentRegistryError
from sentinel_activity.canonical import LedgerError, canonical_bytes

SPEC_IDENTITY_FIELDS = _spec.SPEC_IDENTITY_FIELDS
SPEC_FIELDS = _spec.SPEC_FIELDS
F0, F1, F2 = (_caps.LEVEL_CAPABILITIES[level] for level in ("F0", "F1", "F2"))
LEVEL_CAPABILITIES = dict(_caps.LEVEL_CAPABILITIES)
RESERVED = _caps.RESERVED_CAPABILITIES
FORBIDDEN = _caps.FORBIDDEN_TOKENS
CLASS_MAX_LEVEL = dict(_caps.CLASS_MAX_LEVEL)
AUTHORITY_POLICY = {"authority_ceiling": "NO_RUNTIME_AUTHORITY", "human_decision": False,
                    "economic_status_grants_authority": False, "reputation_grants_authority": False,
                    "consensus_grants_authority": False}
EXECUTION_BINDING = {"status": "UNBOUND", "provider": None, "model": None, "credential_mode": "NONE"}
INDEPENDENCE_POLICY = {"own_work_review_forbidden": True, "independent_review_required": True}


class IdentityError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical(value: Any) -> bytes:
    """J01 canonical bytes for lab records (A1 encoding plus J01's secret refusal)."""
    try:
        return canonical_bytes(value, 65_536)
    except LedgerError as exc:
        code = "LAB_SECRET_TEXT_REJECTED" if exc.code == "SECRET_REJECTED" else "LAB_RECORD_NOT_CANONICAL"
        raise IdentityError(code) from None


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def agent_id(namespace: str, canonical_name: str, agent_class: str) -> str:
    return _spec.compute_agent_id(namespace, canonical_name, agent_class)


def agent_spec_id(spec: dict) -> str:
    return _spec.compute_agent_spec_id(spec)


def spec_artifact_hash(spec: dict) -> str:
    return _spec.compute_spec_artifact_hash(spec)


def classify_capability(token: Any) -> str | None:
    """A1 rejection code (forbidden → reserved → unknown), else None."""
    verdict = _caps.classify_capability_token(token)
    return None if verdict == _caps.ALLOWED else verdict


def check_spec(spec: Any) -> dict:
    """A1 validation (exact #374 code), then the lab's secret rule; returns the three identities."""
    try:
        identities = _spec.validate_agent_spec(spec)
    except AgentRegistryError as exc:
        raise IdentityError(exc.code) from None
    _canonical(spec)
    return {"agent_id": identities.agent_id, "agent_spec_id": identities.agent_spec_id,
            "spec_artifact_hash": identities.spec_artifact_hash}
