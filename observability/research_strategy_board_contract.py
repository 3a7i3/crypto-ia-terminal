"""Closed presentation contract for the Research strategy board; no engines."""

from __future__ import annotations

import math
import re
from datetime import datetime

CRITERIA = ("PERFORMANCE", "POPULATION", "VALIDATION", "STABILITY", "COSTS", "DRAWDOWN")
STATUSES = frozenset({"PASS", "FAIL", "PARTIAL", "NOT_AVAILABLE"})
EVIDENCE = frozenset(
    {"COMPLETE", "PARTIAL", "NOT_AVAILABLE", "NOT_APPLICABLE", "UNRESOLVED"}
)
STRENGTH = frozenset(
    {"DESCRIPTIVE_ONLY", "LOW_SAMPLE", "ADEQUATE_FOR_DECLARED_TEST", "NOT_EVALUATED"}
)
CLASSES = frozenset({"STRATEGY", "FEATURE", "CONFIG", "HYBRID"})
DOMAINS = frozenset(
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
MAX_ROWS = 100
MAX_BYTES = 1024 * 1024


def text(value, limit=2048):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def digest(value, length=64):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None
    )


def integer(value, maximum=2**53 - 1):
    return type(value) is int and 0 <= value <= maximum


def utc(value):
    if not text(value, 40):
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.tzinfo is not None
    except ValueError:
        return False


def keys(value, expected):
    return isinstance(value, dict) and set(value) == set(expected.split())


def enum(value, allowed):
    return isinstance(value, str) and value in allowed


def strings(value, *, maximum=32):
    return (
        isinstance(value, list)
        and len(value) <= maximum
        and all(text(x) for x in value)
        and len(set(value)) == len(value)
    )


def scalar(value):
    return (
        value is None
        or text(value, 256)
        or (type(value) in (int, float) and math.isfinite(value))
    )


def valid_metric(m):
    return (
        keys(
            m,
            "metric_name metric_semantics_version n value evidence_status statistical_strength baseline_value candidate_value delta derivation",
        )
        and text(m["metric_name"], 128)
        and text(m["metric_semantics_version"], 128)
        and integer(m["n"])
        and enum(m["evidence_status"], EVIDENCE)
        and enum(m["statistical_strength"], STRENGTH)
        and all(
            scalar(m[k])
            for k in ("value", "baseline_value", "candidate_value", "delta")
        )
        and text(m["derivation"])
        and (
            m["evidence_status"] in ("COMPLETE", "PARTIAL")
            or type(m["value"]) not in (int, float)
        )
    )


def valid_evaluation(e):
    if e is None:
        return True
    return (
        keys(
            e,
            "evaluation_run_id dataset_id source_boundary_id role method metric_semantics_version config_hash baseline_id source_code_sha run_status population_definition metrics generated_at_utc",
        )
        and all(
            digest(e[k])
            for k in (
                "evaluation_run_id",
                "dataset_id",
                "source_boundary_id",
                "config_hash",
                "baseline_id",
            )
        )
        and digest(e["source_code_sha"], 40)
        and enum(e["role"], {"DISCOVERY", "EVALUATION", "VALIDATION"})
        and enum(e["run_status"], {"COMPLETE", "PARTIAL", "BLOCKED", "FAILED"})
        and all(
            text(e[k], 256)
            for k in ("method", "population_definition", "metric_semantics_version")
        )
        and utc(e["generated_at_utc"])
        and isinstance(e["metrics"], list)
        and 0 < len(e["metrics"]) <= 32
        and all(valid_metric(m) for m in e["metrics"])
        and all(
            m["metric_semantics_version"] == e["metric_semantics_version"]
            for m in e["metrics"]
        )
        and len({m["metric_name"] for m in e["metrics"]}) == len(e["metrics"])
    )


def valid_row(row):
    if not keys(
        row,
        "candidate_id candidate_class label hypothesis rationale target_domains source_code_sha config_hash evaluation criteria ranking assessment_policy_id assessment_policy_ref limitations",
    ):
        return False
    if not (
        digest(row["candidate_id"])
        and enum(row["candidate_class"], CLASSES)
        and text(row["label"], 128)
        and text(row["hypothesis"])
        and text(row["rationale"])
        and strings(row["limitations"])
        and row["limitations"]
        and strings(row["target_domains"])
        and row["target_domains"]
        and all(enum(d, DOMAINS) for d in row["target_domains"])
        and (
            row["source_code_sha"] == "NOT_IMPLEMENTED"
            or digest(row["source_code_sha"], 40)
        )
        and (row["config_hash"] == "NOT_AVAILABLE" or digest(row["config_hash"]))
        and valid_evaluation(row["evaluation"])
    ):
        return False
    if (row["assessment_policy_id"] is None) != (row["assessment_policy_ref"] is None):
        return False
    if row["assessment_policy_id"] is not None and not (
        digest(row["assessment_policy_id"]) and text(row["assessment_policy_ref"], 512)
    ):
        return False
    criteria = row["criteria"]
    if (
        not isinstance(criteria, list)
        or len(criteria) != len(CRITERIA)
        or {c.get("criterion_id") for c in criteria if isinstance(c, dict)}
        != set(CRITERIA)
    ):
        return False
    metrics = (
        {m["metric_name"]: m for m in row["evaluation"]["metrics"]}
        if row["evaluation"]
        else {}
    )
    for c in criteria:
        if not (
            keys(c, "criterion_id status reason metric_refs")
            and enum(c["status"], STATUSES)
            and text(c["reason"])
            and strings(c["metric_refs"])
            and all(ref in metrics for ref in c["metric_refs"])
        ):
            return False
        if c["status"] != "NOT_AVAILABLE" and (
            row["assessment_policy_id"] is None or row["evaluation"] is None
        ):
            return False
        if c["status"] in ("PASS", "FAIL") and (
            not c["metric_refs"]
            or row["evaluation"]["run_status"] != "COMPLETE"
            or any(
                metrics[ref]["evidence_status"] != "COMPLETE" or metrics[ref]["n"] == 0
                for ref in c["metric_refs"]
            )
        ):
            return False
    rank = row["ranking"]
    if rank is not None:
        if not (
            keys(rank, "group_id position group_size metric_name ordering reason")
            and digest(rank["group_id"])
            and integer(rank["position"], MAX_ROWS)
            and 0 < rank["position"] <= rank["group_size"] <= MAX_ROWS
            and integer(rank["group_size"], MAX_ROWS)
            and enum(rank["ordering"], {"ASC", "DESC"})
            and text(rank["reason"])
            and text(rank["metric_name"], 128)
            and row["evaluation"] is not None
            and row["assessment_policy_id"] is not None
        ):
            return False
        metric = metrics.get(rank["metric_name"])
        if (
            not metric
            or metric["evidence_status"] != "COMPLETE"
            or type(metric["value"]) not in (int, float)
            or metric["n"] == 0
            or row["evaluation"]["run_status"] != "COMPLETE"
        ):
            return False
    return True


def comparison_identity(row):
    """Exact identity for admissible ranking cohorts; no metric calculations."""
    e, rank = row["evaluation"], row["ranking"]
    return {
        k: e[k]
        for k in (
            "dataset_id",
            "source_boundary_id",
            "role",
            "method",
            "metric_semantics_version",
            "config_hash",
            "baseline_id",
            "source_code_sha",
            "population_definition",
        )
    } | {
        "policy_id": row["assessment_policy_id"],
        "metric_name": rank["metric_name"],
        "ordering": rank["ordering"],
    }


def validate_strategy_board(doc):
    try:
        if not keys(
            doc,
            "schema_version product domain authority generated_at_utc builder_source_sha admission_ref catalog_state rows source_artifacts limitations",
        ):
            return False
        if not (
            doc["schema_version"] == "1.0.0"
            and doc["product"] == "ResearchStrategyBoardSnapshot"
            and doc["domain"] == "research_strategy_board"
            and doc["authority"] == "RESEARCH_NON_AUTHORITATIVE"
            and utc(doc["generated_at_utc"])
            and digest(doc["builder_source_sha"], 40)
            and text(doc["admission_ref"], 512)
            and enum(doc["catalog_state"], {"AVAILABLE", "EMPTY"})
            and strings(doc["limitations"])
            and doc["limitations"]
        ):
            return False
        rows = doc["rows"]
        if (
            not isinstance(rows, list)
            or len(rows) > MAX_ROWS
            or not all(valid_row(r) for r in rows)
            or len({r["candidate_id"] for r in rows}) != len(rows)
        ):
            return False
        if (doc["catalog_state"] == "EMPTY") != (len(rows) == 0):
            return False
        artifacts = doc["source_artifacts"]
        if (
            not isinstance(artifacts, list)
            or not 0 < len(artifacts) <= 1 + MAX_ROWS * 3
        ):
            return False
        refs = set()
        artifact_types = {}
        for a in artifacts:
            if not (
                keys(a, "artifact_ref artifact_type sha256")
                and text(a["artifact_ref"], 128)
                and text(a["artifact_type"], 128)
                and digest(a["sha256"])
                and a["artifact_ref"] not in refs
            ):
                return False
            refs.add(a["artifact_ref"])
            artifact_types[a["artifact_ref"]] = a["artifact_type"]
        if artifact_types.get("selection") != "RESEARCH_CERTIFIED_SELECTION":
            return False
        for r in rows:
            if artifact_types.get("candidate:" + r["candidate_id"]) != "RL_CANDIDATE":
                return False
            if (
                r["evaluation"] is not None
                and artifact_types.get(
                    "evaluation:" + r["evaluation"]["evaluation_run_id"]
                )
                != "RL_CANDIDATE_EVALUATION"
            ):
                return False
            if (
                r["assessment_policy_id"] is not None
                and artifact_types.get("assessment:" + r["candidate_id"])
                != "RESEARCH_STRATEGY_ASSESSMENT"
            ):
                return False
        from observability.research_lab_schema import snapshot_sha256

        cohorts = {}
        for r in rows:
            if r["ranking"] is None:
                continue
            rank = r["ranking"]
            if snapshot_sha256(comparison_identity(r)) != rank["group_id"]:
                return False
            members = cohorts.setdefault(rank["group_id"], [])
            if any(
                m["position"] == rank["position"]
                or m["group_size"] != rank["group_size"]
                for m in members
            ):
                return False
            members.append(rank)
            if len(members) > rank["group_size"]:
                return False
        return True
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError):
        return False
