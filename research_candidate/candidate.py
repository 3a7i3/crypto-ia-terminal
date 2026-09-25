"""RL-CANDIDATE-01 deterministic candidate and evaluation contracts.

Pure Research-side validation and identity construction.
No runtime/PPL/exchange imports and no production mutation.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

CANDIDATE_SCHEMA = "RL_CANDIDATE_V1"
CANDIDATE_IDENTITY_SCHEMA = "rl-candidate-01.identity.v1"
EVALUATION_IDENTITY_SCHEMA = "rl-candidate-01.evaluation-identity.v1"
CANDIDATE_EVENT_IDENTITY_SCHEMA = "rl-candidate-01.event-identity.v1"
PROMOTION_REQUEST_SCHEMA = "RL_CANDIDATE_PROMOTION_REQUEST_V1"
PROMOTION_REQUEST_IDENTITY_SCHEMA = "rl-candidate-01.promotion-request-identity.v1"

CANDIDATE_CLASSES = frozenset({"CONFIG", "STRATEGY", "FEATURE", "HYBRID"})
TARGET_DOMAINS = frozenset(
    {
        "SIGNAL",
        "STRATEGY",
        "REGIME",
        "GATE",
        "RISK",
        "SIZING",
        "EXECUTION",
        "FEATURE_PIPELINE",
        "RESEARCH_ONLY",
    }
)
CONFIG_IDENTITY_KINDS = frozenset(
    {"EXPERIMENT_CONFIG_SNAPSHOT", "PROJECTED_MATERIAL_CONFIG", "NOT_AVAILABLE"}
)
EVIDENCE_ROLES = frozenset({"DISCOVERY", "EVALUATION", "VALIDATION"})
CONFIG_OPS = frozenset({"CONFIG_SET", "CONFIG_ADD", "CONFIG_REMOVE"})
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CandidateValidationError(ValueError):
    """A candidate/evaluation contract is invalid or ambiguous."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CandidateValidationError(
            f"canonical JSON serialization failed: {exc}"
        ) from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise CandidateValidationError(f"{key} must be an object")
    return value


def _list(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise CandidateValidationError(f"{key} must be a list")
    return value


def _string(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise CandidateValidationError(f"{key} must be a non-empty string")
    return value


def _sha40_value(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA40.fullmatch(value):
        raise CandidateValidationError(f"{field} must be a lowercase 40-char Git SHA")
    return value


def _sha256_value(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise CandidateValidationError(f"{field} must be a lowercase SHA-256")
    return value


def _sorted_unique_strings(
    value: Any,
    *,
    field: str,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise CandidateValidationError(f"{field} must be a list of non-empty strings")
    if nonempty and not value:
        raise CandidateValidationError(f"{field} must not be empty")
    if len(set(value)) != len(value):
        raise CandidateValidationError(f"{field} contains duplicates")
    if value != sorted(value):
        raise CandidateValidationError(f"{field} must be sorted")
    return value


def _utc_timestamp(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CandidateValidationError(f"{field} must be an ISO-8601 UTC string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateValidationError(f"{field} is not valid ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise CandidateValidationError(f"{field} must be UTC")
    return value


def _validate_parents(
    parents: Mapping[str, Any],
    *,
    evidence_catalog: Mapping[str, set[str]] | None,
) -> None:
    required = (
        "dataset_ids",
        "source_boundary_ids",
        "research_run_ids",
        "diagnostic_run_ids",
    )
    for key in required:
        _sorted_unique_strings(
            parents.get(key),
            field=f"parents.{key}",
            nonempty=(key == "dataset_ids"),
        )

    if not parents["research_run_ids"] and not parents["diagnostic_run_ids"]:
        raise CandidateValidationError(
            "parents requires at least one research_run_id or diagnostic_run_id"
        )

    for key in ("dataset_ids", "source_boundary_ids", "research_run_ids", "diagnostic_run_ids"):
        for value in parents[key]:
            _sha256_value(value, field=f"parents.{key}")

    if "paper_epoch_ids" in parents:
        _sorted_unique_strings(parents["paper_epoch_ids"], field="parents.paper_epoch_ids")

    if "artifact_digests" in parents:
        digests = _mapping(parents, "artifact_digests")
        for name, digest in digests.items():
            if not isinstance(name, str) or not name:
                raise CandidateValidationError("artifact digest name must be non-empty")
            _sha256_value(digest, field=f"parents.artifact_digests.{name}")

    if evidence_catalog is not None:
        mapping = {
            "dataset_ids": "dataset_ids",
            "source_boundary_ids": "source_boundary_ids",
            "research_run_ids": "research_run_ids",
            "diagnostic_run_ids": "diagnostic_run_ids",
            "paper_epoch_ids": "paper_epoch_ids",
        }
        for key, catalog_key in mapping.items():
            for value in parents.get(key, []):
                if value not in evidence_catalog.get(catalog_key, set()):
                    raise CandidateValidationError(
                        f"unknown parent evidence {key}: {value}"
                    )


def _validate_lineage(
    lineage: Mapping[str, Any],
    *,
    known_candidate_ids: set[str] | None,
) -> None:
    for key in ("supersedes_candidate_ids", "derived_from_candidate_ids"):
        values = _sorted_unique_strings(
            lineage.get(key),
            field=f"lineage.{key}",
        )
        for candidate_id in values:
            _sha256_value(candidate_id, field=f"lineage.{key}")
            if known_candidate_ids is not None and candidate_id not in known_candidate_ids:
                raise CandidateValidationError(
                    f"lineage references unknown candidate_id {candidate_id}"
                )


def _validate_baseline(baseline: Mapping[str, Any]) -> None:
    _sha40_value(baseline.get("source_code_sha"), field="baseline.source_code_sha")
    kind = _string(baseline, "config_identity_kind")
    if kind not in CONFIG_IDENTITY_KINDS:
        raise CandidateValidationError(f"unsupported config_identity_kind {kind!r}")

    config_hash = baseline.get("config_hash")
    if kind == "NOT_AVAILABLE":
        if config_hash != "NOT_AVAILABLE":
            raise CandidateValidationError(
                "baseline.config_hash must be NOT_AVAILABLE when config identity is unavailable"
            )
    else:
        _sha256_value(config_hash, field="baseline.config_hash")

    strategy_id = _string(baseline, "strategy_id")
    if strategy_id != "NOT_AVAILABLE" and not strategy_id.strip():
        raise CandidateValidationError("baseline.strategy_id is invalid")

    _string(baseline, "baseline_semantics_version")
    _string(baseline, "baseline_population_definition")

    if "paper_epoch_id" in baseline:
        _string(baseline, "paper_epoch_id")


def _validate_config_component(component: Mapping[str, Any]) -> None:
    kind = _string(component, "kind")
    if kind not in CONFIG_OPS:
        raise CandidateValidationError(f"unsupported CONFIG operation {kind!r}")
    _string(component, "path")
    _string(component, "value_type")
    materiality = _string(component, "materiality")
    if materiality not in TARGET_DOMAINS - {"RESEARCH_ONLY"}:
        raise CandidateValidationError(f"invalid CONFIG materiality {materiality!r}")

    if kind == "CONFIG_SET" and (
        "old_value" not in component or "new_value" not in component
    ):
        raise CandidateValidationError("CONFIG_SET requires old_value and new_value")
    if kind == "CONFIG_ADD" and "new_value" not in component:
        raise CandidateValidationError("CONFIG_ADD requires new_value")
    if kind == "CONFIG_REMOVE" and "old_value" not in component:
        raise CandidateValidationError("CONFIG_REMOVE requires old_value")


def _validate_code_component(
    component: Mapping[str, Any],
    *,
    baseline_source_sha: str,
) -> None:
    if _string(component, "kind") != "CODE_PATCH":
        raise CandidateValidationError("STRATEGY component must be CODE_PATCH")
    baseline = _sha40_value(
        component.get("baseline_source_sha"),
        field="proposal.CODE_PATCH.baseline_source_sha",
    )
    if baseline != baseline_source_sha:
        raise CandidateValidationError(
            "CODE_PATCH baseline_source_sha does not match candidate baseline"
        )

    proposed = _string(component, "proposed_source_sha")
    patch = _string(component, "patch_sha256")
    paths = _sorted_unique_strings(
        component.get("changed_paths"),
        field="proposal.CODE_PATCH.changed_paths",
        nonempty=True,
    )
    if any(path.startswith("/") or ".." in path.split("/") for path in paths):
        raise CandidateValidationError("CODE_PATCH changed_paths must be repo-relative")

    if proposed == "NOT_IMPLEMENTED":
        if patch != "NOT_IMPLEMENTED":
            raise CandidateValidationError(
                "NOT_IMPLEMENTED source requires NOT_IMPLEMENTED patch digest"
            )
    else:
        _sha40_value(proposed, field="proposal.CODE_PATCH.proposed_source_sha")
        _sha256_value(patch, field="proposal.CODE_PATCH.patch_sha256")

    domain = _string(component, "semantic_domain")
    if domain not in TARGET_DOMAINS - {"RESEARCH_ONLY"}:
        raise CandidateValidationError(f"invalid CODE_PATCH semantic_domain {domain!r}")


def _validate_feature_component(component: Mapping[str, Any]) -> None:
    if _string(component, "kind") != "FEATURE_SPEC":
        raise CandidateValidationError("FEATURE component must be FEATURE_SPEC")
    for field in (
        "feature_name",
        "feature_semantic_version",
        "missing_value_policy",
        "intended_consumer",
    ):
        _string(component, field)
    _sha256_value(
        component.get("derivation_spec_sha256"),
        field="proposal.FEATURE_SPEC.derivation_spec_sha256",
    )
    if not isinstance(component.get("input_schema"), dict):
        raise CandidateValidationError("FEATURE_SPEC input_schema must be an object")
    if not isinstance(component.get("output_schema"), dict):
        raise CandidateValidationError("FEATURE_SPEC output_schema must be an object")
    if not isinstance(component.get("affects_population_or_capital"), bool):
        raise CandidateValidationError(
            "FEATURE_SPEC affects_population_or_capital must be boolean"
        )


def _validate_proposal(
    candidate_class: str,
    proposal: Mapping[str, Any],
    *,
    baseline_source_sha: str,
) -> None:
    components = _list(proposal, "components")
    if not components or any(not isinstance(item, dict) for item in components):
        raise CandidateValidationError("proposal.components must contain objects")

    canonical = [canonical_json_bytes(item) for item in components]
    if canonical != sorted(canonical):
        raise CandidateValidationError(
            "proposal.components must be sorted by canonical component JSON bytes"
        )
    if len(set(canonical)) != len(canonical):
        raise CandidateValidationError("proposal.components contains duplicates")

    kinds = {str(item.get("kind")) for item in components}
    for component in components:
        kind = component.get("kind")
        if kind in CONFIG_OPS:
            _validate_config_component(component)
        elif kind == "CODE_PATCH":
            _validate_code_component(
                component,
                baseline_source_sha=baseline_source_sha,
            )
        elif kind == "FEATURE_SPEC":
            _validate_feature_component(component)
        else:
            raise CandidateValidationError(f"unsupported proposal component kind {kind!r}")

    if candidate_class == "CONFIG" and not kinds <= CONFIG_OPS:
        raise CandidateValidationError("CONFIG candidate may contain only CONFIG operations")
    if candidate_class == "STRATEGY" and kinds != {"CODE_PATCH"}:
        raise CandidateValidationError("STRATEGY candidate requires CODE_PATCH only")
    if candidate_class == "FEATURE" and kinds != {"FEATURE_SPEC"}:
        raise CandidateValidationError("FEATURE candidate requires FEATURE_SPEC only")
    if candidate_class == "HYBRID" and len(kinds) < 2:
        raise CandidateValidationError("HYBRID candidate requires at least two component kinds")


def _validate_hypothesis(hypothesis: Mapping[str, Any]) -> None:
    for field in (
        "question",
        "rationale",
        "mechanism",
        "primary_metric",
        "expected_direction",
    ):
        _string(hypothesis, field)
    for field in (
        "guardrail_metrics",
        "minimum_evidence_requirements",
        "falsification_conditions",
    ):
        _sorted_unique_strings(
            hypothesis.get(field),
            field=f"hypothesis.{field}",
            nonempty=True,
        )


def dataset_requirement_id(requirement_without_id: Mapping[str, Any]) -> str:
    value = dict(requirement_without_id)
    value.pop("requirement_id", None)
    return sha256_json(value)


def _validate_dataset_requirement(
    requirement: Mapping[str, Any],
    *,
    parent_dataset_ids: set[str],
) -> None:
    kind = _string(requirement, "kind")
    role = _string(requirement, "evidence_role")
    if role not in EVIDENCE_ROLES:
        raise CandidateValidationError(f"unsupported evidence role {role!r}")
    _string(requirement, "source_domain")
    _string(requirement, "source_authority")

    if kind == "EXACT_DATASET":
        _sha256_value(requirement.get("dataset_id"), field="dataset_requirement.dataset_id")
        _sha256_value(
            requirement.get("source_boundary_id"),
            field="dataset_requirement.source_boundary_id",
        )
    elif kind == "FUTURE_DATASET_REQUIREMENT":
        expected = dataset_requirement_id(requirement)
        actual = _sha256_value(
            requirement.get("requirement_id"),
            field="dataset_requirement.requirement_id",
        )
        if actual != expected:
            raise CandidateValidationError("future dataset requirement_id mismatch")
        _string(requirement, "required_relation")
        if not isinstance(requirement.get("required_source_config_binding"), dict):
            raise CandidateValidationError(
                "future dataset required_source_config_binding must be an object"
            )
        if not isinstance(requirement.get("minimum_conditions"), dict):
            raise CandidateValidationError(
                "future dataset minimum_conditions must be an object"
            )
        if "dataset_id" in requirement:
            raise CandidateValidationError(
                "future dataset requirement must not invent a dataset_id"
            )
    else:
        raise CandidateValidationError(f"unsupported dataset requirement kind {kind!r}")


def _validate_evaluation_plan(
    evaluation_plan: Mapping[str, Any],
    *,
    parent_dataset_ids: set[str],
) -> None:
    methods = _sorted_unique_strings(
        evaluation_plan.get("evaluation_methods"),
        field="evaluation_plan.evaluation_methods",
        nonempty=True,
    )
    allowed_methods = {
        "FACTUAL_BINDING_CHECK",
        "OFFLINE_REPLAY",
        "DESCRIPTIVE_COMPARISON",
        "COUNTERFACTUAL_REPLAY",
        "SHADOW",
        "NEW_PAPER_EPOCH",
    }
    if not set(methods) <= allowed_methods:
        raise CandidateValidationError("evaluation_plan has unsupported evaluation method")

    requirements = _list(evaluation_plan, "dataset_requirements")
    if not requirements or any(not isinstance(item, dict) for item in requirements):
        raise CandidateValidationError("evaluation_plan.dataset_requirements must be non-empty")
    for requirement in requirements:
        _validate_dataset_requirement(
            requirement,
            parent_dataset_ids=parent_dataset_ids,
        )

    for field in (
        "population_definition",
        "primary_metric_semantics",
        "minimum_sample_evidence_requirement",
        "comparison_baseline",
        "missing_evidence_behavior",
        "determinism_requirements",
    ):
        _string(evaluation_plan, field)

    guardrails = evaluation_plan.get("guardrail_metric_semantics")
    if not isinstance(guardrails, dict) or not guardrails:
        raise CandidateValidationError(
            "evaluation_plan.guardrail_metric_semantics must be non-empty"
        )

    policy = _mapping(evaluation_plan, "data_reuse_policy")
    discovery = _sorted_unique_strings(
        policy.get("discovery_dataset_ids"),
        field="evaluation_plan.data_reuse_policy.discovery_dataset_ids",
        nonempty=True,
    )
    if not set(discovery) <= parent_dataset_ids:
        raise CandidateValidationError(
            "data_reuse_policy discovery datasets must be parent datasets"
        )
    allow = policy.get("allow_discovery_as_validation")
    if not isinstance(allow, bool):
        raise CandidateValidationError(
            "data_reuse_policy.allow_discovery_as_validation must be boolean"
        )
    if allow and not isinstance(policy.get("justification"), str):
        raise CandidateValidationError(
            "allowing discovery as validation requires a justification"
        )

    for requirement in requirements:
        if (
            requirement.get("kind") == "EXACT_DATASET"
            and requirement.get("dataset_id") in discovery
            and requirement.get("evidence_role") == "VALIDATION"
            and not allow
        ):
            raise CandidateValidationError(
                "discovery evidence cannot silently be reused as validation"
            )


def _validate_promotion_policy(policy: Mapping[str, Any]) -> None:
    _string(policy, "version")
    if policy.get("target_environment") != "PAPER_NEW_EPOCH":
        raise CandidateValidationError(
            "candidate promotion target must be PAPER_NEW_EPOCH"
        )
    if policy.get("new_epoch_only") is not True:
        raise CandidateValidationError("promotion_policy.new_epoch_only must be true")
    if policy.get("requires_operator_authorization") is not True:
        raise CandidateValidationError(
            "promotion_policy.requires_operator_authorization must be true"
        )


def candidate_identity_document(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_identity_schema": CANDIDATE_IDENTITY_SCHEMA,
        "candidate_class": candidate["candidate_class"],
        "target_domains": list(candidate["target_domains"]),
        "parents": candidate["parents"],
        "lineage": candidate["lineage"],
        "baseline": candidate["baseline"],
        "proposal": candidate["proposal"],
        "hypothesis_identity": candidate["hypothesis"],
        "evaluation_plan_identity": candidate["evaluation_plan"],
        "promotion_policy_version": candidate["promotion_policy"]["version"],
    }


def compute_candidate_id(candidate: Mapping[str, Any]) -> str:
    return sha256_json(candidate_identity_document(candidate))


def validate_candidate(
    candidate: Mapping[str, Any],
    *,
    evidence_catalog: Mapping[str, set[str]] | None = None,
    known_candidate_ids: set[str] | None = None,
) -> str:
    if candidate.get("candidate_schema") != CANDIDATE_SCHEMA:
        raise CandidateValidationError("unsupported candidate_schema")

    candidate_class = _string(candidate, "candidate_class")
    if candidate_class not in CANDIDATE_CLASSES:
        raise CandidateValidationError(f"unsupported candidate_class {candidate_class!r}")

    domains = _sorted_unique_strings(
        candidate.get("target_domains"),
        field="target_domains",
        nonempty=True,
    )
    if not set(domains) <= TARGET_DOMAINS:
        raise CandidateValidationError("target_domains contains unsupported value")
    if "RESEARCH_ONLY" in domains and len(domains) != 1:
        raise CandidateValidationError(
            "RESEARCH_ONLY cannot be combined with runtime-affecting domains"
        )

    parents = _mapping(candidate, "parents")
    _validate_parents(parents, evidence_catalog=evidence_catalog)

    lineage = _mapping(candidate, "lineage")
    _validate_lineage(lineage, known_candidate_ids=known_candidate_ids)

    baseline = _mapping(candidate, "baseline")
    _validate_baseline(baseline)

    proposal = _mapping(candidate, "proposal")
    _validate_proposal(
        candidate_class,
        proposal,
        baseline_source_sha=baseline["source_code_sha"],
    )

    hypothesis = _mapping(candidate, "hypothesis")
    _validate_hypothesis(hypothesis)

    evaluation_plan = _mapping(candidate, "evaluation_plan")
    _validate_evaluation_plan(
        evaluation_plan,
        parent_dataset_ids=set(parents["dataset_ids"]),
    )

    limitations = _sorted_unique_strings(
        candidate.get("known_limitations"),
        field="known_limitations",
        nonempty=True,
    )
    if not limitations:
        raise CandidateValidationError("known_limitations must not be empty")

    promotion_policy = _mapping(candidate, "promotion_policy")
    _validate_promotion_policy(promotion_policy)

    _utc_timestamp(candidate.get("created_at_utc"), field="created_at_utc")

    expected = compute_candidate_id(candidate)
    actual = _sha256_value(candidate.get("candidate_id"), field="candidate_id")
    if actual != expected:
        raise CandidateValidationError(
            f"candidate_id mismatch: expected={expected}, actual={actual}"
        )
    return actual


def evaluation_run_identity(
    *,
    candidate: Mapping[str, Any],
    dataset_id: str,
    source_boundary_id: str,
    satisfied_dataset_requirement_id: str,
    dataset_evidence_role: str,
    evaluation_engine_code_sha: str,
    evaluation_method_version: str,
    evaluation_config_hash: str,
    population_definition: str,
    metric_semantics_version: str,
) -> dict[str, Any]:
    candidate_id = _sha256_value(candidate.get("candidate_id"), field="candidate_id")
    _sha256_value(dataset_id, field="dataset_id")
    _sha256_value(source_boundary_id, field="source_boundary_id")
    _sha256_value(
        satisfied_dataset_requirement_id,
        field="satisfied_dataset_requirement_id",
    )
    if dataset_evidence_role not in EVIDENCE_ROLES:
        raise CandidateValidationError("unsupported dataset_evidence_role")
    _sha40_value(evaluation_engine_code_sha, field="evaluation_engine_code_sha")
    _sha256_value(evaluation_config_hash, field="evaluation_config_hash")

    return {
        "evaluation_identity_schema": EVALUATION_IDENTITY_SCHEMA,
        "candidate_id": candidate_id,
        "dataset_id": dataset_id,
        "source_boundary_id": source_boundary_id,
        "satisfied_dataset_requirement_id": satisfied_dataset_requirement_id,
        "dataset_evidence_role": dataset_evidence_role,
        "evaluation_engine_code_sha": evaluation_engine_code_sha,
        "evaluation_method_version": evaluation_method_version,
        "evaluation_config_hash": evaluation_config_hash,
        "population_definition": population_definition,
        "baseline": candidate["baseline"],
        "metric_semantics_version": metric_semantics_version,
    }


def compute_evaluation_run_id(**kwargs: Any) -> str:
    return sha256_json(evaluation_run_identity(**kwargs))
