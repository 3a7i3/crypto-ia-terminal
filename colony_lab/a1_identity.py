"""A1 identities for lab individuals, computed exactly as the A1 contract says.

docs/contracts/AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT.md §2 and AW-03. The
schema in docs/contracts stays the authority for the full spec shape; this
module recomputes identities and enforces the capability ceilings the lab
relies on. It registers nothing: the A1 registry is NON_DEPLOYED and the
registrar is UNRESOLVED, so no registry state is ever claimed here.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sentinel_activity.canonical import LedgerError, canonical_bytes

AGENT_IDENTITY_SCHEMA = "agent-econ.a1.agent-identity.v1"
AGENT_SPEC_IDENTITY_SCHEMA = "agent-econ.a1.agent-spec-identity.v1"
SPEC_IDENTITY_FIELDS = (
    "agent_schema", "constitution_version", "agent_id", "spec_revision", "namespace", "canonical_name",
    "display_name", "agent_class", "maintenance_level", "purpose", "capabilities", "scope_policy",
    "independence_policy", "authority_policy", "execution_binding", "supersedes_spec_id",
)
SPEC_FIELDS = SPEC_IDENTITY_FIELDS + ("agent_spec_id", "created_from_ref", "created_at_utc")

F0 = frozenset({"CI_READ", "GITHUB_METADATA_READ", "GOVERNED_ARTIFACT_READ", "REPOSITORY_READ",
                "REPOSITORY_SEARCH", "STATIC_ANALYSIS"})
F1 = F0 | {"CANDIDATE_PROBLEM_PROPOSE"}
F2 = F1 | {"PROBLEM_VERIFY", "PROBLEM_DEDUPLICATE", "PROBLEM_CHARACTERIZE", "DIAGNOSTIC_PRODUCE",
           "BOUNTY_DRAFT_PREPARE", "SCOPE_DRAFT_PREPARE", "ACCEPTANCE_CRITERIA_DRAFT_PREPARE"}
LEVEL_CAPABILITIES = {"F0": F0, "F1": F1, "F2": F2}
RESERVED = frozenset({"SOURCE_EDIT_ISOLATED", "TEST_RUN_ISOLATED", "BRANCH_PREPARE", "PR_PREPARE",
                      "TEST_REVIEW", "SECURITY_REVIEW", "DATA_PROVENANCE_REVIEW", "STATISTICAL_REVIEW",
                      "ARCHITECTURE_REVIEW", "GOVERNANCE_REVIEW"})
FORBIDDEN = frozenset({
    "MAIN_MERGE", "RUNTIME_DEPLOY", "ADVISOR_RESTART", "SYSTEMD_MUTATE", "ACTIVE_EPOCH_MUTATE",
    "PPL_AUTHORITY_WRITE", "FIN_AUTHORITY_WRITE", "TRADING_CONFIG_MUTATE", "RISK_MUTATE", "SIZING_MUTATE",
    "PB_MAX_POSITIONS_MUTATE", "SECRET_VALUE_READ", "EXCHANGE_WRITE", "TESTNET_ENABLE", "LIVE_ENABLE",
    "HUMAN_DECISION", "RESEARCH_PROMOTION_EXECUTE", "AUTHORITY_DELEGATE", "AIC_BUY_AUTHORITY",
    "REPUTATION_GRANT_AUTHORITY", "AGENT_REGISTRY_MUTATE", "CONSENSUS_AUTHORITY_ASSERT",
    "GOVERNANCE_GATE_BYPASS", "EVIDENCE_MUTATE",
    "HUMAN_ACCEPT", "HUMAN_REJECT", "MERGE_AUTHORIZATION", "DEPLOY_AUTHORIZATION", "EPOCH_AUTHORIZATION",
    "PROMOTION_AUTHORIZATION",
})
CLASS_MAX_LEVEL = {"SENSOR": "F0", "SCOUT": "F1", "CURATOR": "F2", "FORENSIC": "F2", "DATA_STEWARD": "F2",
                   "SECURITY": "F2", "SRE": "F2", "RESEARCH": "F1", "STRATEGY": "F1"}
_LEVEL_ORDER = ("F0", "F1", "F2")
AUTHORITY_POLICY = {"authority_ceiling": "NO_RUNTIME_AUTHORITY", "human_decision": False,
                    "economic_status_grants_authority": False, "reputation_grants_authority": False,
                    "consensus_grants_authority": False}
EXECUTION_BINDING = {"status": "UNBOUND", "provider": None, "model": None, "credential_mode": "NONE"}
INDEPENDENCE_POLICY = {"own_work_review_forbidden": True, "independent_review_required": True}


class IdentityError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_CANONICAL_CODES = {"NUMERIC_AMBIGUITY": "SPEC_NUMERIC_AMBIGUITY", "TEXT_NOT_CANONICAL": "SPEC_TEXT_NOT_CANONICAL",
                    "SECRET_REJECTED": "SPEC_TEXT_NOT_CANONICAL"}


def _canonical(value: Any) -> bytes:
    """J01 canonical bytes (same encoding as A1 §3, plus J01's secret refusal)."""
    try:
        return canonical_bytes(value, 65_536)
    except LedgerError as exc:
        raise IdentityError(_CANONICAL_CODES.get(exc.code, "SPEC_SCHEMA_VIOLATION")) from None


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def agent_id(namespace: str, canonical_name: str, agent_class: str) -> str:
    return _sha({"agent_identity_schema": AGENT_IDENTITY_SCHEMA, "namespace": namespace,
                 "canonical_name": canonical_name, "agent_class": agent_class})


def agent_spec_id(spec: dict) -> str:
    document = {"agent_spec_identity_schema": AGENT_SPEC_IDENTITY_SCHEMA}
    document.update({name: spec[name] for name in SPEC_IDENTITY_FIELDS})
    return _sha(document)


def publication_bytes(spec: dict) -> bytes:
    """AW-03 bytes: sorted keys, indent=2, trailing newline (canonical rules checked first)."""
    _canonical(spec)
    return (json.dumps(spec, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode()


def spec_artifact_hash(spec: dict) -> str:
    return hashlib.sha256(publication_bytes(spec)).hexdigest()


def classify_capability(token: Any) -> str | None:
    """Rejection code in the contract's order (forbidden → reserved → unknown), else None."""
    if token in FORBIDDEN:
        return "FORBIDDEN_AUTHORITY_REQUESTED"
    if token in RESERVED:
        return "RESERVED_CAPABILITY"
    if token not in F2:
        return "UNKNOWN_CAPABILITY"
    return None


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def check_spec(spec: Any) -> dict:
    """Identity and ceiling checks the lab depends on; returns the three A1 identities."""
    if type(spec) is not dict or set(spec) != set(SPEC_FIELDS):
        raise IdentityError("SPEC_SCHEMA_VIOLATION")
    _canonical(spec)
    if any(text != text.strip() for text in _strings(spec)):
        raise IdentityError("SPEC_TEXT_NOT_CANONICAL")  # AS-03: no edge whitespace
    if spec["namespace"] != "forest" or spec["agent_schema"] != "AGENT_SPEC_V1":
        raise IdentityError("SPEC_SCHEMA_VIOLATION")
    level, cls = spec["maintenance_level"], spec["agent_class"]
    if cls not in CLASS_MAX_LEVEL or level not in _LEVEL_ORDER or \
            _LEVEL_ORDER.index(level) > _LEVEL_ORDER.index(CLASS_MAX_LEVEL[cls]):
        raise IdentityError("CLASS_LEVEL_INADMISSIBLE")
    caps = spec["capabilities"]
    if type(caps) is not list or not caps or caps != sorted(set(caps)):
        raise IdentityError("SPEC_ARRAY_NOT_CANONICAL")
    for token in caps:
        code = classify_capability(token)
        if code is not None:
            raise IdentityError(code)
        if token not in LEVEL_CAPABILITIES[level]:
            raise IdentityError("CAPABILITY_ABOVE_CEILING")
    if spec["authority_policy"] != AUTHORITY_POLICY:
        raise IdentityError("AUTHORITY_POLICY_VIOLATION")
    if spec["execution_binding"] != EXECUTION_BINDING:
        raise IdentityError("BINDING_NOT_UNBOUND")
    if spec["independence_policy"] != INDEPENDENCE_POLICY:
        raise IdentityError("INDEPENDENCE_POLICY_VIOLATION")
    _check_scope_coupling(set(caps), spec["scope_policy"])
    expected_agent = agent_id(spec["namespace"], spec["canonical_name"], cls)
    if spec["agent_id"] != expected_agent or spec["agent_spec_id"] != agent_spec_id(spec):
        raise IdentityError("IDENTITY_MISMATCH")
    return {"agent_id": expected_agent, "agent_spec_id": spec["agent_spec_id"],
            "spec_artifact_hash": spec_artifact_hash(spec)}


def _check_scope_coupling(caps: set, scope: Any) -> None:
    keys = {"repository_read_paths", "repository_write_paths_future", "github_surfaces", "artifact_domains"}
    if type(scope) is not dict or set(scope) != keys or any(type(v) is not list for v in scope.values()):
        raise IdentityError("SPEC_SCHEMA_VIOLATION")
    for name, values in scope.items():
        if values != sorted(set(values)):
            raise IdentityError("SPEC_ARRAY_NOT_CANONICAL")
    coupling = (
        ("repository_read_paths", {"REPOSITORY_READ", "REPOSITORY_SEARCH", "STATIC_ANALYSIS"}),
        ("github_surfaces", {"CI_READ", "GITHUB_METADATA_READ"}),
        ("artifact_domains", {"GOVERNED_ARTIFACT_READ"}),
    )
    if scope["repository_write_paths_future"] or any(bool(scope[name]) != bool(caps & needs)
                                                     for name, needs in coupling):
        raise IdentityError("SCOPE_CAPABILITY_INCOHERENT")
