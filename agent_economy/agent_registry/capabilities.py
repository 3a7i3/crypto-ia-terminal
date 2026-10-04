"""Closed capability catalogue, classes and levels (A0 sections 4-6, catalog).

Four disjoint classifications, never collapsed into one generic "unknown":
ALLOWED, RESERVED_CAPABILITY, FORBIDDEN_AUTHORITY_REQUESTED, UNKNOWN_CAPABILITY.
Declaring a capability proves nothing and authorizes nothing.
"""

from __future__ import annotations

ALLOWED = "ALLOWED"
RESERVED_CAPABILITY = "RESERVED_CAPABILITY"
FORBIDDEN_AUTHORITY_REQUESTED = "FORBIDDEN_AUTHORITY_REQUESTED"
UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"

# --- Catalogue V1 (catalog section 2): 14 non-authoritative capabilities ---
F0_CAPABILITIES = frozenset(
    {
        "CI_READ",
        "GITHUB_METADATA_READ",
        "GOVERNED_ARTIFACT_READ",
        "REPOSITORY_READ",
        "REPOSITORY_SEARCH",
        "STATIC_ANALYSIS",
    }
)
F1_ONLY_CAPABILITIES = frozenset({"CANDIDATE_PROBLEM_PROPOSE"})
F2_ONLY_CAPABILITIES = frozenset(
    {
        "ACCEPTANCE_CRITERIA_DRAFT_PREPARE",
        "BOUNTY_DRAFT_PREPARE",
        "DIAGNOSTIC_PRODUCE",
        "PROBLEM_CHARACTERIZE",
        "PROBLEM_DEDUPLICATE",
        "PROBLEM_VERIFY",
        "SCOPE_DRAFT_PREPARE",
    }
)

# Cumulative ceilings F0 -> F1 -> F2 (A0 section 4).
LEVEL_CAPABILITIES: dict[str, frozenset[str]] = {
    "F0": F0_CAPABILITIES,
    "F1": F0_CAPABILITIES | F1_ONLY_CAPABILITIES,
    "F2": F0_CAPABILITIES | F1_ONLY_CAPABILITIES | F2_ONLY_CAPABILITIES,
}
CATALOG_V1 = LEVEL_CAPABILITIES["F2"]

LEVEL_RANK = {"F0": 0, "F1": 1, "F2": 2}
ADMISSIBLE_LEVELS = frozenset(LEVEL_RANK)
# F3 / F4 are KNOWN RESERVED vocabulary: rejected, never "unknown".
RESERVED_LEVELS = frozenset({"F3", "F4"})

# --- Reserved capabilities (catalog section 3): F3 / F4 ---
RESERVED_CAPABILITIES = frozenset(
    {
        "SOURCE_EDIT_ISOLATED",
        "TEST_RUN_ISOLATED",
        "BRANCH_PREPARE",
        "PR_PREPARE",
        "TEST_REVIEW",
        "SECURITY_REVIEW",
        "DATA_PROVENANCE_REVIEW",
        "STATISTICAL_REVIEW",
        "ARCHITECTURE_REVIEW",
        "GOVERNANCE_REVIEW",
    }
)

# --- Forbidden (catalog section 4): Forbidden Authority Set (24) + Human Gate (6) ---
FORBIDDEN_AUTHORITY_SET = frozenset(
    {
        "MAIN_MERGE",
        "RUNTIME_DEPLOY",
        "ADVISOR_RESTART",
        "SYSTEMD_MUTATE",
        "ACTIVE_EPOCH_MUTATE",
        "PPL_AUTHORITY_WRITE",
        "FIN_AUTHORITY_WRITE",
        "TRADING_CONFIG_MUTATE",
        "RISK_MUTATE",
        "SIZING_MUTATE",
        "PB_MAX_POSITIONS_MUTATE",
        "SECRET_VALUE_READ",
        "EXCHANGE_WRITE",
        "TESTNET_ENABLE",
        "LIVE_ENABLE",
        "HUMAN_DECISION",
        "RESEARCH_PROMOTION_EXECUTE",
        "AUTHORITY_DELEGATE",
        "AIC_BUY_AUTHORITY",
        "REPUTATION_GRANT_AUTHORITY",
        "AGENT_REGISTRY_MUTATE",
        "CONSENSUS_AUTHORITY_ASSERT",
        "GOVERNANCE_GATE_BYPASS",
        "EVIDENCE_MUTATE",
    }
)
HUMAN_GATE = frozenset(
    {
        "HUMAN_ACCEPT",
        "HUMAN_REJECT",
        "MERGE_AUTHORIZATION",
        "DEPLOY_AUTHORIZATION",
        "EPOCH_AUTHORIZATION",
        "PROMOTION_AUTHORIZATION",
    }
)
FORBIDDEN_TOKENS = FORBIDDEN_AUTHORITY_SET | HUMAN_GATE


def classify_capability_token(token: object) -> str:
    """Classify a capability token (catalog section 1; forbidden first).

    Non-string tokens are UNKNOWN_CAPABILITY: there is no permissive fallback.
    Draft names of earlier designs (e.g. ``AGENT_REGISTRY_WRITE``) are not
    aliases and are therefore UNKNOWN_CAPABILITY too (A0 section 6).
    """
    if not isinstance(token, str):
        return UNKNOWN_CAPABILITY
    if token in FORBIDDEN_TOKENS:
        return FORBIDDEN_AUTHORITY_REQUESTED
    if token in RESERVED_CAPABILITIES:
        return RESERVED_CAPABILITY
    if token in CATALOG_V1:
        return ALLOWED
    return UNKNOWN_CAPABILITY


# --- Classes (catalog section 6) ---
AGENT_CLASSES = frozenset(
    {
        "CURATOR",
        "DATA_STEWARD",
        "ENGINEER",
        "FORENSIC",
        "GOVERNANCE",
        "RESEARCH",
        "REVIEWER",
        "SCOUT",
        "SECURITY",
        "SENSOR",
        "SRE",
        "STRATEGY",
        "TEST_VERIFIER",
        "UX",
    }
)
# Maximum admissible maintenance level per class in V1.
CLASS_MAX_LEVEL: dict[str, str] = {
    "SENSOR": "F0",
    "SCOUT": "F1",
    "CURATOR": "F2",
    "FORENSIC": "F2",
    "DATA_STEWARD": "F2",
    "SECURITY": "F2",
    "SRE": "F2",
    "RESEARCH": "F1",
    "STRATEGY": "F1",
}
# Recognized vocabulary with no admissible level in V1 (depend on F3/F4).
RESERVED_CLASSES = frozenset(AGENT_CLASSES - set(CLASS_MAX_LEVEL))

# --- Scope vocabularies ---
GITHUB_SURFACES = frozenset(
    {"BRANCHES", "CHECK_RUNS", "COMMITS", "ISSUES", "PULL_REQUESTS", "WORKFLOW_RUNS"}
)
ARTIFACT_DOMAINS = frozenset(
    {
        "CI_ARTIFACTS",
        "GOVERNANCE_DOCUMENTS",
        "OPERATOR_API_PROJECTIONS",
        "PAPER_CERTIFIED_EXPORTS",
        "RESEARCH_DATASETS_IMMUTABLE",
        "RESEARCH_PUBLICATIONS",
    }
)

# Capabilities that require a non-empty read-path list, github surface list,
# artifact-domain list (and forbid the list when no such capability exists).
REPOSITORY_PATH_CAPABILITIES = frozenset(
    {"REPOSITORY_READ", "REPOSITORY_SEARCH", "STATIC_ANALYSIS"}
)
GITHUB_SURFACE_CAPABILITIES: dict[str, frozenset[str]] = {
    "CI_READ": frozenset({"CHECK_RUNS", "WORKFLOW_RUNS"}),
    "GITHUB_METADATA_READ": frozenset(
        {"BRANCHES", "COMMITS", "ISSUES", "PULL_REQUESTS"}
    ),
}
ARTIFACT_DOMAIN_CAPABILITIES = frozenset({"GOVERNED_ARTIFACT_READ"})
