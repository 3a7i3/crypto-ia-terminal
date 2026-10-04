"""AgentSpec V1: deterministic identities and fail-closed validation.

Implements A1 sections 2.1, 2.2, 3.2, 4, 10 and rules AS-01 ... AS-13. Both the
rules the JSON Schema encodes (S) and the validator-only rules (V) are checked
here without any schema library. The caller's input is never mutated or
"helpfully" corrected: an invalid spec is rejected as received.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import (
    AgentRegistryError,
    compile_schema_pattern,
    find_float,
    is_pure_int,
    iter_strings,
    parse_utc_timestamp,
    sha256_hex,
    sha256_hex_of_bytes,
    text_violation,
    publication_json_bytes,
)
from .capabilities import (
    ADMISSIBLE_LEVELS,
    AGENT_CLASSES,
    ALLOWED,
    ARTIFACT_DOMAIN_CAPABILITIES,
    ARTIFACT_DOMAINS,
    CLASS_MAX_LEVEL,
    GITHUB_SURFACE_CAPABILITIES,
    GITHUB_SURFACES,
    LEVEL_CAPABILITIES,
    LEVEL_RANK,
    REPOSITORY_PATH_CAPABILITIES,
    RESERVED_CLASSES,
    RESERVED_LEVELS,
    classify_capability_token,
)

AGENT_SCHEMA = "AGENT_SPEC_V1"
CONSTITUTION_VERSION = "AGENT_ECON_A0_FOREST_V1"
NAMESPACE = "forest"
AGENT_IDENTITY_SCHEMA = "agent-econ.a1.agent-identity.v1"
AGENT_SPEC_IDENTITY_SCHEMA = "agent-econ.a1.agent-spec-identity.v1"

SPEC_FIELDS = (
    "agent_schema",
    "constitution_version",
    "agent_id",
    "agent_spec_id",
    "spec_revision",
    "namespace",
    "canonical_name",
    "display_name",
    "agent_class",
    "maintenance_level",
    "purpose",
    "capabilities",
    "scope_policy",
    "independence_policy",
    "authority_policy",
    "execution_binding",
    "supersedes_spec_id",
    "created_from_ref",
    "created_at_utc",
)
# Material identity fields (A1 section 2.2): everything except agent_spec_id
# itself and the provenance fields created_from_ref / created_at_utc.
SPEC_IDENTITY_FIELDS = (
    "agent_schema",
    "constitution_version",
    "agent_id",
    "spec_revision",
    "namespace",
    "canonical_name",
    "display_name",
    "agent_class",
    "maintenance_level",
    "purpose",
    "capabilities",
    "scope_policy",
    "independence_policy",
    "authority_policy",
    "execution_binding",
    "supersedes_spec_id",
)
PROVENANCE_FIELDS = ("agent_spec_id", "created_from_ref", "created_at_utc")

SCOPE_FIELDS = (
    "repository_read_paths",
    "repository_write_paths_future",
    "github_surfaces",
    "artifact_domains",
)
INDEPENDENCE_FIELDS = ("own_work_review_forbidden", "independent_review_required")
AUTHORITY_FIELDS = (
    "authority_ceiling",
    "human_decision",
    "economic_status_grants_authority",
    "reputation_grants_authority",
    "consensus_grants_authority",
)
BINDING_FIELDS = ("status", "provider", "model", "credential_mode")

MAX_SPEC_REVISION = 1_000_000

# Patterns copied verbatim from AGENT_ECON_A1_AGENT_SPEC_V1.schema.json (a test
# compares them to the schema file so they cannot drift silently).
PATTERN_SHA256 = "^[0-9a-f]{64}$"
PATTERN_SHA40 = "^[0-9a-f]{40}$"
PATTERN_CANONICAL_NAME = "^[a-z][a-z0-9_]{2,63}$"
PATTERN_DISPLAY_NAME = "^\\S(.*\\S)?$"
PATTERN_PURPOSE = "^\\S(.|\\n)*\\S$"
PATTERN_READ_PATH = (
    "^(?!/)(?!.*//)(?!(.*/)?\\.{1,2}(/|$))(?!(.*/)?\\.env)(?!.*\\.(pem|key|p12|pfx)$)"
    "(?!(.*/)?(id_rsa|id_ed25519)[^/]*$)(?!(.*/)?secrets?(/|$))"
    "[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*/?$"
)
PATTERN_CREATED_AT = (
    "^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):"
    "[0-5][0-9]:[0-5][0-9](\\.[0-9]{1,6})?Z$"
)

_SHA256 = compile_schema_pattern(PATTERN_SHA256)
_SHA40 = compile_schema_pattern(PATTERN_SHA40)
_CANONICAL_NAME = compile_schema_pattern(PATTERN_CANONICAL_NAME)
_DISPLAY_NAME = compile_schema_pattern(PATTERN_DISPLAY_NAME)
_PURPOSE = compile_schema_pattern(PATTERN_PURPOSE)
_READ_PATH = compile_schema_pattern(PATTERN_READ_PATH)
_CREATED_AT = compile_schema_pattern(PATTERN_CREATED_AT)


@dataclass(frozen=True)
class SpecIdentities:
    """Recomputed identities of a validated spec."""

    agent_id: str
    agent_spec_id: str
    spec_artifact_hash: str


def _fail(code: str, detail: str, **kwargs: Any) -> AgentRegistryError:
    return AgentRegistryError(code, detail, **kwargs)


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------


def compute_agent_id(namespace: str, canonical_name: str, agent_class: str) -> str:
    """A1 section 2.1: independent of revision, level, capabilities, provenance."""
    return sha256_hex(
        {
            "agent_identity_schema": AGENT_IDENTITY_SCHEMA,
            "namespace": namespace,
            "canonical_name": canonical_name,
            "agent_class": agent_class,
        }
    )


def compute_agent_spec_id(spec: dict[str, Any]) -> str:
    """A1 section 2.2: material identity, provenance and agent_spec_id excluded."""
    missing = [name for name in SPEC_IDENTITY_FIELDS if name not in spec]
    if missing:
        raise _fail(
            "SPEC_SCHEMA_VIOLATION", f"missing identity fields: {sorted(missing)}"
        )
    document: dict[str, Any] = {
        "agent_spec_identity_schema": AGENT_SPEC_IDENTITY_SCHEMA
    }
    for name in SPEC_IDENTITY_FIELDS:
        document[name] = spec[name]
    return sha256_hex(document)


def compute_spec_artifact_bytes(spec: dict[str, Any]) -> bytes:
    """AW-03 publication bytes of the whole spec, provenance included."""
    return publication_json_bytes(spec)


def compute_spec_artifact_hash(spec: dict[str, Any]) -> str:
    """A1 section 2.3: SHA-256 of the exact published artifact bytes."""
    return sha256_hex_of_bytes(compute_spec_artifact_bytes(spec))


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _check_keys(obj: Any, expected: tuple[str, ...], where: str) -> None:
    if not isinstance(obj, dict):
        raise _fail("SPEC_SCHEMA_VIOLATION", f"{where} must be an object")
    missing = sorted(set(expected) - set(obj))
    unknown = sorted(set(obj) - set(expected))
    if missing:
        raise _fail("SPEC_SCHEMA_VIOLATION", f"{where}: missing fields {missing}")
    if unknown:
        raise _fail("SPEC_SCHEMA_VIOLATION", f"{where}: unknown fields {unknown}")


def _check_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _fail("SPEC_SCHEMA_VIOLATION", f"{field} must be a string")
    return value


def _check_array_canonical(name: str, value: list[str]) -> None:
    """AS-04: sorted ascending by code point and unique; rejected, never fixed."""
    if len(set(value)) != len(value):
        raise _fail("SPEC_ARRAY_NOT_CANONICAL", f"{name} contains duplicates")
    if value != sorted(value):
        raise _fail("SPEC_ARRAY_NOT_CANONICAL", f"{name} is not sorted")


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _fail("SPEC_SCHEMA_VIOLATION", f"{field} must be a list of strings")
    return value


def _validate_scalars(spec: dict[str, Any]) -> None:
    if spec["agent_schema"] != AGENT_SCHEMA:
        raise _fail("SPEC_SCHEMA_VIOLATION", "agent_schema must be AGENT_SPEC_V1")
    if spec["constitution_version"] != CONSTITUTION_VERSION:
        raise _fail(
            "SPEC_SCHEMA_VIOLATION", "constitution_version must be the A0 forest V1"
        )
    for field in ("agent_id", "agent_spec_id"):
        if not _SHA256.fullmatch(_check_string(spec[field], field)):
            raise _fail("SPEC_SCHEMA_VIOLATION", f"{field} must be lowercase sha256")
    revision = spec["spec_revision"]
    if not is_pure_int(revision):
        raise _fail("SPEC_SCHEMA_VIOLATION", "spec_revision must be an integer")
    if not 1 <= revision <= MAX_SPEC_REVISION:
        raise _fail("SPEC_SCHEMA_VIOLATION", "spec_revision out of range")
    if spec["namespace"] != NAMESPACE:
        raise _fail("SPEC_SCHEMA_VIOLATION", "namespace must be 'forest'")
    if not _CANONICAL_NAME.fullmatch(_check_string(spec["canonical_name"], "name")):
        raise _fail("SPEC_SCHEMA_VIOLATION", "canonical_name violates its grammar")
    display = _check_string(spec["display_name"], "display_name")
    if not 1 <= len(display) <= 80 or not _DISPLAY_NAME.fullmatch(display):
        raise _fail("SPEC_SCHEMA_VIOLATION", "display_name violates its grammar")
    purpose = _check_string(spec["purpose"], "purpose")
    if not 20 <= len(purpose) <= 600 or not _PURPOSE.fullmatch(purpose):
        raise _fail("SPEC_SCHEMA_VIOLATION", "purpose violates its grammar")
    if not _SHA40.fullmatch(_check_string(spec["created_from_ref"], "created_from_ref")):
        raise _fail("SPEC_SCHEMA_VIOLATION", "created_from_ref must be a 40-hex sha")
    created_at = _check_string(spec["created_at_utc"], "created_at_utc")
    if not _CREATED_AT.fullmatch(created_at) or parse_utc_timestamp(created_at) is None:
        raise _fail("SPEC_SCHEMA_VIOLATION", "created_at_utc is not ISO-8601 UTC")


def _validate_constants(spec: dict[str, Any]) -> None:
    independence = spec["independence_policy"]  # AS-10
    for field in INDEPENDENCE_FIELDS:
        if independence[field] is not True:
            raise _fail("INDEPENDENCE_POLICY_VIOLATION", f"{field} must be true")
    authority = spec["authority_policy"]  # AS-08
    if authority["authority_ceiling"] != "NO_RUNTIME_AUTHORITY":
        raise _fail(
            "AUTHORITY_POLICY_VIOLATION", "authority_ceiling must be NO_RUNTIME_AUTHORITY"
        )
    for field in AUTHORITY_FIELDS[1:]:
        if authority[field] is not False:
            raise _fail("AUTHORITY_POLICY_VIOLATION", f"{field} must be false")
    binding = spec["execution_binding"]  # AS-09
    if binding["status"] != "UNBOUND":
        raise _fail("BINDING_NOT_UNBOUND", "execution_binding.status must be UNBOUND")
    if binding["provider"] is not None or binding["model"] is not None:
        raise _fail("BINDING_NOT_UNBOUND", "provider and model must be null")
    if binding["credential_mode"] != "NONE":
        raise _fail("BINDING_NOT_UNBOUND", "credential_mode must be NONE")


def _validate_capabilities(spec: dict[str, Any]) -> list[str]:
    capabilities = _string_list(spec["capabilities"], "capabilities")
    if not 1 <= len(capabilities) <= len(LEVEL_CAPABILITIES["F2"]):
        raise _fail("SPEC_SCHEMA_VIOLATION", "capabilities must be non-empty and bounded")
    for token in capabilities:  # AS-05: forbidden, reserved, unknown stay distinct
        classification = classify_capability_token(token)
        if classification != ALLOWED:
            raise _fail(
                classification, f"capability {token!r} is {classification}"
            )
    _check_array_canonical("capabilities", capabilities)  # AS-04
    return capabilities


def _validate_scope(spec: dict[str, Any]) -> dict[str, list[str]]:
    scope = spec["scope_policy"]
    paths = _string_list(scope["repository_read_paths"], "repository_read_paths")
    surfaces = _string_list(scope["github_surfaces"], "github_surfaces")
    domains = _string_list(scope["artifact_domains"], "artifact_domains")
    future = scope["repository_write_paths_future"]
    if not isinstance(future, list) or future:
        raise _fail(
            "SPEC_SCHEMA_VIOLATION", "repository_write_paths_future must be []"
        )
    if len(paths) > 64:
        raise _fail("SPEC_SCHEMA_VIOLATION", "too many repository_read_paths")
    for name, values in (
        ("repository_read_paths", paths),
        ("github_surfaces", surfaces),
        ("artifact_domains", domains),
    ):
        _check_array_canonical(name, values)  # AS-04
    for path in paths:
        if not _READ_PATH.fullmatch(path):
            raise _fail("SPEC_SCHEMA_VIOLATION", f"repository path {path!r} is invalid")
    for surface in surfaces:
        if surface not in GITHUB_SURFACES:
            raise _fail("SPEC_SCHEMA_VIOLATION", f"unknown github surface {surface!r}")
    for domain in domains:
        if domain not in ARTIFACT_DOMAINS:
            raise _fail("SPEC_SCHEMA_VIOLATION", f"unknown artifact domain {domain!r}")
    return {
        "repository_read_paths": paths,
        "github_surfaces": surfaces,
        "artifact_domains": domains,
    }


def _validate_class_and_level(spec: dict[str, Any]) -> tuple[str, str]:
    agent_class = _check_string(spec["agent_class"], "agent_class")
    level = _check_string(spec["maintenance_level"], "maintenance_level")
    if agent_class not in AGENT_CLASSES:
        raise _fail("SPEC_SCHEMA_VIOLATION", f"unknown agent_class {agent_class!r}")
    if level in RESERVED_LEVELS:
        raise _fail(
            "CLASS_LEVEL_INADMISSIBLE",
            f"maintenance_level {level} is RESERVED (F3/F4)",
            classification="RESERVED_LEVEL",
        )
    if level not in ADMISSIBLE_LEVELS:
        raise _fail("SPEC_SCHEMA_VIOLATION", f"unknown maintenance_level {level!r}")
    if agent_class in RESERVED_CLASSES:
        raise _fail(
            "CLASS_LEVEL_INADMISSIBLE",
            f"agent_class {agent_class} is RESERVED in V1",
            classification="RESERVED_CLASS",
        )
    if LEVEL_RANK[level] > LEVEL_RANK[CLASS_MAX_LEVEL[agent_class]]:
        raise _fail(
            "CLASS_LEVEL_INADMISSIBLE",
            f"{agent_class} may not exceed {CLASS_MAX_LEVEL[agent_class]}",
            classification="LEVEL_ABOVE_CLASS_MAXIMUM",
        )
    return agent_class, level


def _validate_scope_coupling(capabilities: list[str], scope: dict[str, list[str]]) -> None:
    declared = set(capabilities)
    # S: a scope list is non-empty iff the corresponding capability is declared.
    for name, required, values in (
        (
            "repository_read_paths",
            bool(declared & REPOSITORY_PATH_CAPABILITIES),
            scope["repository_read_paths"],
        ),
        (
            "github_surfaces",
            bool(declared & set(GITHUB_SURFACE_CAPABILITIES)),
            scope["github_surfaces"],
        ),
        (
            "artifact_domains",
            bool(declared & ARTIFACT_DOMAIN_CAPABILITIES),
            scope["artifact_domains"],
        ),
    ):
        if required and not values:
            raise _fail(
                "SPEC_SCHEMA_VIOLATION", f"{name} must be non-empty for the capabilities"
            )
        if not required and values:
            raise _fail(
                "SPEC_SCHEMA_VIOLATION", f"{name} must be empty without its capability"
            )
    # V (AS-13): github surfaces must be allowed by a declared github capability.
    allowed_surfaces: set[str] = set()
    for capability, surfaces in GITHUB_SURFACE_CAPABILITIES.items():
        if capability in declared:
            allowed_surfaces |= surfaces
    extra = set(scope["github_surfaces"]) - allowed_surfaces
    if extra:
        raise _fail(
            "SCOPE_CAPABILITY_INCOHERENT",
            f"github surfaces {sorted(extra)} are not allowed by the declared capabilities",
        )


def validate_agent_spec(spec: Any) -> SpecIdentities:
    """Validate a complete AgentSpec V1 (AS-01 ... AS-13). Raises on any violation.

    Returns the recomputed identities; ``spec`` is never modified. Checks run in
    a fixed order so the failure code is deterministic.
    """
    try:
        return _validate_agent_spec(spec)
    except RecursionError as exc:
        raise _fail("SPEC_SCHEMA_VIOLATION", "spec nesting is too deep") from exc


def _validate_agent_spec(spec: Any) -> SpecIdentities:
    _check_keys(spec, SPEC_FIELDS, "spec")
    _check_keys(spec["scope_policy"], SCOPE_FIELDS, "scope_policy")
    _check_keys(spec["independence_policy"], INDEPENDENCE_FIELDS, "independence_policy")
    _check_keys(spec["authority_policy"], AUTHORITY_FIELDS, "authority_policy")
    _check_keys(spec["execution_binding"], BINDING_FIELDS, "execution_binding")

    path = find_float(spec)  # AS-02: 1.0 is a float and is ambiguous
    if path is not None:
        raise _fail("SPEC_NUMERIC_AMBIGUITY", f"float at {path}")
    if isinstance(spec["spec_revision"], bool):
        raise _fail("SPEC_NUMERIC_AMBIGUITY", "spec_revision is a bool, not an integer")

    for where, text in iter_strings(spec):  # AS-03
        violation = text_violation(
            text, allow_newline=where == "$.purpose"
        )
        if violation:
            raise _fail("SPEC_TEXT_NOT_CANONICAL", f"{where}: {violation}")

    _validate_scalars(spec)
    _validate_constants(spec)
    capabilities = _validate_capabilities(spec)
    scope = _validate_scope(spec)
    agent_class, level = _validate_class_and_level(spec)
    ceiling = LEVEL_CAPABILITIES[level]
    above = sorted(set(capabilities) - ceiling)
    if above:  # AS-06
        raise _fail(
            "CAPABILITY_ABOVE_CEILING", f"{above} exceed the {level} capability set"
        )
    _validate_scope_coupling(capabilities, scope)  # S coupling + AS-13

    supersedes = spec["supersedes_spec_id"]  # AS-12 (local relation)
    if supersedes is not None and (
        not isinstance(supersedes, str) or not _SHA256.fullmatch(supersedes)
    ):
        raise _fail("SPEC_SCHEMA_VIOLATION", "supersedes_spec_id must be null or sha256")
    if (spec["spec_revision"] == 1) != (supersedes is None):
        raise _fail(
            "SUPERSESSION_BREAK", "spec_revision 1 holds iff supersedes_spec_id is null"
        )

    expected_agent_id = compute_agent_id(spec["namespace"], spec["canonical_name"], agent_class)
    if spec["agent_id"] != expected_agent_id:  # AS-11
        raise _fail("IDENTITY_MISMATCH", "agent_id does not match its recomputation")
    expected_spec_id = compute_agent_spec_id(spec)
    if spec["agent_spec_id"] != expected_spec_id:
        raise _fail("IDENTITY_MISMATCH", "agent_spec_id does not match its recomputation")

    return SpecIdentities(
        agent_id=expected_agent_id,
        agent_spec_id=expected_spec_id,
        spec_artifact_hash=compute_spec_artifact_hash(spec),
    )


# ---------------------------------------------------------------------------
# Revision classification (A1 section 10)
# ---------------------------------------------------------------------------


def classify_revision(previous: dict[str, Any], new: dict[str, Any]) -> str:
    """Deterministic reason_code of a spec revision, between two valid specs.

    Precedence: increase > reduction > neutral. Repository paths compare by exact
    string (two directory prefixes are never compared by inclusion).
    """
    old_scope, new_scope = previous["scope_policy"], new["scope_policy"]
    pairs = (
        (set(previous["capabilities"]), set(new["capabilities"])),
        (
            set(old_scope["repository_read_paths"]),
            set(new_scope["repository_read_paths"]),
        ),
        (set(old_scope["github_surfaces"]), set(new_scope["github_surfaces"])),
        (set(old_scope["artifact_domains"]), set(new_scope["artifact_domains"])),
    )
    old_rank = LEVEL_RANK[previous["maintenance_level"]]
    new_rank = LEVEL_RANK[new["maintenance_level"]]
    if new_rank > old_rank or any(not new_set <= old_set for old_set, new_set in pairs):
        return "SPEC_REVISION_ESCALATING"
    if new_rank < old_rank or any(new_set < old_set for old_set, new_set in pairs):
        return "SPEC_REVISION_REDUCING"
    return "SPEC_REVISION_NON_ESCALATING"


__all__ = [
    "SpecIdentities",
    "classify_revision",
    "compute_agent_id",
    "compute_agent_spec_id",
    "compute_spec_artifact_bytes",
    "compute_spec_artifact_hash",
    "validate_agent_spec",
]
