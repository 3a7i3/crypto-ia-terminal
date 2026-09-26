"""WEB-RL-01 pure Research Lab presentation schema and validator.

No filesystem writes, runtime/PPL/exchange imports, or Research-engine imports.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
PRODUCT = "ResearchLabSnapshot"
DOMAIN = "research_lab"
AUTHORITY = "RESEARCH_NON_AUTHORITATIVE"

EVIDENCE_STATUSES = frozenset(
    {"COMPLETE", "PARTIAL", "NOT_AVAILABLE", "NOT_APPLICABLE", "UNRESOLVED"}
)
STATISTICAL_STRENGTH = frozenset(
    {"DESCRIPTIVE_ONLY", "LOW_SAMPLE", "ADEQUATE_FOR_DECLARED_TEST", "NOT_EVALUATED"}
)
RESEARCH_STATES = frozenset({"AVAILABLE", "EMPTY"})
CANDIDATE_CLASSES = frozenset({"CONFIG", "STRATEGY", "FEATURE", "HYBRID"})
CANDIDATE_STATES = frozenset(
    {
        "CANDIDATE",
        "REPLAYED",
        "SHADOW_READY",
        "QUALIFIED",
        "PROMOTED_TO_NEW_EPOCH",
        "REJECTED",
        "DORMANT",
        "RETIRED",
    }
)

_TOP_KEYS = {
    "schema_version",
    "product",
    "domain",
    "authority",
    "generated_at_utc",
    "presentation_builder_source_sha",
    "research_state",
    "provenance",
    "population",
    "performance",
    "risk_stability",
    "costs",
    "attribution",
    "candidate_registry",
    "limitations",
}
_PROVENANCE_KEYS = {"primary_context", "source_artifacts"}
_CONTEXT_KEYS = {
    "dataset_id",
    "source_boundary_id",
    "paper_epoch_id",
    "research_run_id",
    "diagnostic_run_id",
    "research_source_code_sha",
    "research_config_hash",
    "presentation_builder_source_sha",
    "population_definition",
    "n",
    "evidence_status",
    "statistical_strength",
}
_ARTIFACT_KEYS = {"artifact_ref", "artifact_type", "sha256"}
_POPULATION_KEYS = {
    "population_definition",
    "n",
    "evidence_status",
    "statistical_strength",
}
_METRIC_KEYS = {
    "metric_name",
    "value",
    "unit",
    "evidence_status",
    "statistical_strength",
    "population_n",
    "derivation",
    "source_ref",
    "reason",
}
_ATTRIBUTION_KEYS = {
    "dimension",
    "evidence_status",
    "statistical_strength",
    "rows",
}
_ATTRIBUTION_ROW_KEYS = {"label", "population_n", "metrics"}
_CANDIDATE_REGISTRY_KEYS = {"candidate_count", "rows"}
_CANDIDATE_ROW_KEYS = {
    "candidate_id",
    "candidate_class",
    "target_domains",
    "lifecycle_state",
    "parent_evidence_refs",
    "source_code_sha",
    "config_hash",
    "hypothesis_summary",
    "evaluation_status",
    "known_limitations",
}


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _sha40(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 40:
        return False
    return all(ch in "0123456789abcdef" for ch in value)


def _sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_artifact(row: Any) -> bool:
    return (
        isinstance(row, dict)
        and set(row) == _ARTIFACT_KEYS
        and _nonempty(row["artifact_ref"])
        and _nonempty(row["artifact_type"])
        and _sha256(row["sha256"])
    )


def _valid_context(doc: Any, *, builder_sha: str) -> bool:
    if not isinstance(doc, dict) or set(doc) != _CONTEXT_KEYS:
        return False
    if not _sha256(doc["dataset_id"]):
        return False
    if not _sha256(doc["source_boundary_id"]):
        return False
    if doc["paper_epoch_id"] is not None and not _nonempty(doc["paper_epoch_id"]):
        return False
    if not _sha256(doc["research_run_id"]):
        return False
    if doc["diagnostic_run_id"] is not None and not _sha256(doc["diagnostic_run_id"]):
        return False
    if not _sha40(doc["research_source_code_sha"]):
        return False
    if doc["research_config_hash"] is not None and not _sha256(doc["research_config_hash"]):
        return False
    if doc["presentation_builder_source_sha"] != builder_sha:
        return False
    if not _nonempty(doc["population_definition"]):
        return False
    if not _nonnegative_int(doc["n"]):
        return False
    if doc["evidence_status"] not in EVIDENCE_STATUSES:
        return False
    if doc["statistical_strength"] not in STATISTICAL_STRENGTH:
        return False
    return True


def _valid_population(doc: Any, *, context: Mapping[str, Any]) -> bool:
    if not isinstance(doc, dict) or set(doc) != _POPULATION_KEYS:
        return False
    return (
        doc["population_definition"] == context["population_definition"]
        and doc["n"] == context["n"]
        and doc["evidence_status"] in EVIDENCE_STATUSES
        and doc["statistical_strength"] in STATISTICAL_STRENGTH
    )


def _valid_metric(
    metric: Any,
    *,
    artifact_refs: set[str],
    default_population_n: int,
) -> bool:
    if not isinstance(metric, dict) or set(metric) != _METRIC_KEYS:
        return False
    if not _nonempty(metric["metric_name"]):
        return False
    if not _nonempty(metric["unit"]):
        return False
    if metric["evidence_status"] not in EVIDENCE_STATUSES:
        return False
    if metric["statistical_strength"] not in STATISTICAL_STRENGTH:
        return False
    if not _nonnegative_int(metric["population_n"]):
        return False
    if metric["population_n"] > default_population_n:
        return False
    if not _nonempty(metric["derivation"]):
        return False
    if metric["source_ref"] not in artifact_refs:
        return False
    if metric["reason"] is not None and not _nonempty(metric["reason"]):
        return False

    value = metric["value"]
    status = metric["evidence_status"]
    if status in {"NOT_AVAILABLE", "NOT_APPLICABLE", "UNRESOLVED"}:
        return value is None and _nonempty(metric["reason"])
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return _finite_number(value)
    return isinstance(value, str) and bool(value.strip())


def _valid_metric_list(
    values: Any,
    *,
    artifact_refs: set[str],
    default_population_n: int,
) -> bool:
    if not isinstance(values, list):
        return False
    names: set[str] = set()
    for metric in values:
        if not _valid_metric(
            metric,
            artifact_refs=artifact_refs,
            default_population_n=default_population_n,
        ):
            return False
        name = metric["metric_name"]
        if name in names:
            return False
        names.add(name)
    return True


def _valid_attribution(
    values: Any,
    *,
    artifact_refs: set[str],
    default_population_n: int,
) -> bool:
    if not isinstance(values, list):
        return False
    dimensions: set[str] = set()
    for section in values:
        if not isinstance(section, dict) or set(section) != _ATTRIBUTION_KEYS:
            return False
        if not _nonempty(section["dimension"]) or section["dimension"] in dimensions:
            return False
        dimensions.add(section["dimension"])
        if section["evidence_status"] not in EVIDENCE_STATUSES:
            return False
        if section["statistical_strength"] not in STATISTICAL_STRENGTH:
            return False
        rows = section["rows"]
        if not isinstance(rows, list):
            return False
        labels: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != _ATTRIBUTION_ROW_KEYS:
                return False
            if not _nonempty(row["label"]) or row["label"] in labels:
                return False
            labels.add(row["label"])
            if not _nonnegative_int(row["population_n"]):
                return False
            if row["population_n"] > default_population_n:
                return False
            if not _valid_metric_list(
                row["metrics"],
                artifact_refs=artifact_refs,
                default_population_n=row["population_n"],
            ):
                return False
    return True


def _valid_candidate_registry(doc: Any, *, artifact_refs: set[str]) -> bool:
    if not isinstance(doc, dict) or set(doc) != _CANDIDATE_REGISTRY_KEYS:
        return False
    if not _nonnegative_int(doc["candidate_count"]):
        return False
    rows = doc["rows"]
    if not isinstance(rows, list) or len(rows) != doc["candidate_count"]:
        return False
    candidate_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != _CANDIDATE_ROW_KEYS:
            return False
        candidate_id = row["candidate_id"]
        if not _sha256(candidate_id) or candidate_id in candidate_ids:
            return False
        candidate_ids.add(candidate_id)
        if row["candidate_class"] not in CANDIDATE_CLASSES:
            return False
        if (
            not isinstance(row["target_domains"], list)
            or not row["target_domains"]
            or any(not _nonempty(value) for value in row["target_domains"])
            or len(row["target_domains"]) != len(set(row["target_domains"]))
        ):
            return False
        if row["lifecycle_state"] not in CANDIDATE_STATES:
            return False
        refs = row["parent_evidence_refs"]
        if (
            not isinstance(refs, list)
            or any(ref not in artifact_refs for ref in refs)
            or len(refs) != len(set(refs))
        ):
            return False
        if row["source_code_sha"] != "NOT_IMPLEMENTED" and not _sha40(
            row["source_code_sha"]
        ):
            return False
        if row["config_hash"] != "NOT_AVAILABLE" and not _sha256(row["config_hash"]):
            return False
        if not _nonempty(row["hypothesis_summary"]):
            return False
        if not _nonempty(row["evaluation_status"]):
            return False
        limitations = row["known_limitations"]
        if (
            not isinstance(limitations, list)
            or any(not _nonempty(value) for value in limitations)
        ):
            return False
    return True


def validate_research_lab_snapshot(doc: Any) -> bool:
    """Closed-schema admission gate for WEB-RL Research presentation data."""

    if not isinstance(doc, dict) or set(doc) != _TOP_KEYS:
        return False
    if doc["schema_version"] != SCHEMA_VERSION:
        return False
    if doc["product"] != PRODUCT:
        return False
    if doc["domain"] != DOMAIN:
        return False
    if doc["authority"] != AUTHORITY:
        return False
    if _parse_utc(doc["generated_at_utc"]) is None:
        return False

    builder_sha = doc["presentation_builder_source_sha"]
    if not _sha40(builder_sha):
        return False
    if doc["research_state"] not in RESEARCH_STATES:
        return False

    provenance = doc["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_KEYS:
        return False
    if not _valid_context(provenance["primary_context"], builder_sha=builder_sha):
        return False

    artifacts = provenance["source_artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        return False
    if not all(_valid_artifact(row) for row in artifacts):
        return False
    refs = [row["artifact_ref"] for row in artifacts]
    if len(refs) != len(set(refs)):
        return False
    artifact_refs = set(refs)

    context = provenance["primary_context"]
    if not _valid_population(doc["population"], context=context):
        return False

    n = context["n"]
    for key in ("performance", "risk_stability", "costs"):
        if not _valid_metric_list(
            doc[key],
            artifact_refs=artifact_refs,
            default_population_n=n,
        ):
            return False

    if not _valid_attribution(
        doc["attribution"],
        artifact_refs=artifact_refs,
        default_population_n=n,
    ):
        return False
    if not _valid_candidate_registry(
        doc["candidate_registry"],
        artifact_refs=artifact_refs,
    ):
        return False

    limitations = doc["limitations"]
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not _nonempty(value) for value in limitations)
    ):
        return False

    if doc["research_state"] == "EMPTY":
        if n != 0:
            return False
        if any(doc[key] for key in ("performance", "risk_stability", "costs", "attribution")):
            return False
        if doc["candidate_registry"]["candidate_count"] != 0:
            return False
    return True


def canonical_snapshot_bytes(doc: Mapping[str, Any]) -> bytes:
    """Canonical bytes for deterministic publication checks."""

    return json.dumps(
        doc,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def snapshot_sha256(doc: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_snapshot_bytes(doc)).hexdigest()



__all__ = [
    "AUTHORITY",
    "DOMAIN",
    "PRODUCT",
    "SCHEMA_VERSION",
    "canonical_snapshot_bytes",
    "snapshot_sha256",
    "validate_research_lab_snapshot",
]
