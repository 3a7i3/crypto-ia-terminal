"""U4 offline presentation adapter for explicitly admitted Research publications.

Reads aggregate publication evidence only. Does not certify Research, select a
latest run, open a dataset/ledger, or import any scientific/runtime engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from observability.research_evidence_io import read_evidence
from observability.research_lab_schema import (
    canonical_snapshot_bytes,
    validate_research_lab_snapshot,
)
from observability.research_lab_snapshot import publish_research_lab_snapshot

SELECTION_SCHEMA = "app-unify-u4.research-selection.v1"


class ResearchPublicationError(ValueError):
    """Evidence cannot be admitted; the prior presentation stays untouched."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ResearchPublicationError(reason)


def _digest(value: Any, length: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(c in "0123456789abcdef" for c in value)
    )


def _n(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 2**53 - 1


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _identity(doc: dict, identity_key: str, id_key: str) -> dict:
    identity = doc[identity_key]
    _require(isinstance(identity, dict), "Missing run identity")
    _require(
        hashlib.sha256(canonical_snapshot_bytes(identity)).hexdigest() == doc[id_key],
        "Run identity digest mismatch",
    )
    return identity


def _metric(
    name: str, source: dict, unit: str, n: int, ref: str, derivation: str
) -> dict:
    _require(isinstance(source, dict), "Metric must be an object")
    status = source.get("status")
    _require(
        status
        in (
            "COMPLETE",
            "NOT_AVAILABLE",
            "POSITIVE_INFINITY",
            "UNDEFINED_ZERO_DENOMINATOR",
        ),
        "Unsupported source metric status",
    )
    _require(
        "n" not in source or (type(source["n"]) is int and source["n"] == n),
        "Metric population mismatch",
    )
    value = source.get("value")
    if status == "COMPLETE":
        _require(_number(value), "Complete metric requires a finite number")
        reason = None
        strength = "DESCRIPTIVE_ONLY"
    else:
        _require(value is None, "Unavailable metric must be null")
        reason = (
            source.get("reason")
            or f"Source metric status: {status}; no finite value published."
        )
        _require(
            isinstance(reason, str) and bool(reason.strip()), "Invalid metric reason"
        )
        strength = "NOT_EVALUATED"
    return {
        "metric_name": name,
        "value": value,
        "unit": unit,
        "evidence_status": "COMPLETE" if status == "COMPLETE" else "NOT_AVAILABLE",
        "statistical_strength": strength,
        "population_n": n,
        "derivation": derivation,
        "source_ref": ref,
        "reason": reason,
    }


def _scalar(
    name: str, value: Any, unit: str, n: int, ref: str, derivation: str
) -> dict:
    return _metric(
        name, {"status": "COMPLETE", "value": value}, unit, n, ref, derivation
    )


def _build(
    selection_path: Path,
    run_path: Path,
    diagnostic_path: Path | None,
    *,
    generated_at_utc: str,
    builder_source_sha: str,
) -> dict:
    selection, selection_hash = read_evidence(selection_path)
    _require(
        set(selection)
        == {
            "schema_version",
            "certification_ref",
            "admission",
            "research_run_id",
            "manifest_sha256",
            "diagnostic_run_id",
            "diagnostic_sha256",
        },
        "Invalid selection contract",
    )
    _require(
        selection["schema_version"] == SELECTION_SCHEMA
        and selection["admission"] == "CERTIFIED",
        "Explicit certified admission required",
    )
    ref = selection["certification_ref"]
    _require(
        isinstance(ref, str) and bool(ref.strip()) and len(ref) <= 512,
        "Certification reference required",
    )
    for key in ("research_run_id", "manifest_sha256"):
        _require(_digest(selection[key]), "Invalid selected identity/hash")
    _require(
        (selection["diagnostic_run_id"] is None)
        == (selection["diagnostic_sha256"] is None)
        == (diagnostic_path is None),
        "Diagnostic selection/path mismatch",
    )
    if diagnostic_path is not None:
        _require(
            _digest(selection["diagnostic_run_id"])
            and _digest(selection["diagnostic_sha256"]),
            "Invalid diagnostic selection",
        )
    manifest, manifest_hash = read_evidence(run_path / "manifest.json")
    _require(
        manifest_hash == selection["manifest_sha256"]
        and manifest["research_run_id"] == selection["research_run_id"],
        "Selected manifest mismatch",
    )
    _require(
        manifest["result_schema_version"] == "rl-replay-01.result.v1"
        and manifest["status"] == "COMPLETE"
        and manifest["run_kind"] == "FACTUAL_BASELINE"
        and manifest["derivation"] == "OFFLINE_FACTUAL_PPL_REPLAY",
        "Unsupported Research publication",
    )
    identity = _identity(manifest, "research_run_identity", "research_run_id")
    _require(
        identity["identity_schema"] == "rl-replay-01.run-identity.v1"
        and identity["run_kind"] == "FACTUAL_BASELINE"
        and identity["replay_method"] == "PPL_PROJECT_FACTUAL_V1",
        "Unsupported replay identity",
    )
    for key in (
        "dataset_id",
        "source_boundary_id",
        "paper_epoch_id",
        "research_replay_code_sha",
        "replay_config_hash",
        "population",
        "replay_method",
        "source_experiment_identity",
        "candidate_config_hash",
        "counterfactual_spec_digest",
    ):
        _require(manifest[key] == identity[key], f"Manifest identity mismatch: {key}")
    _require(
        _digest(manifest["dataset_id"])
        and _digest(manifest["source_boundary_id"])
        and _digest(manifest["research_replay_code_sha"], 40)
        and _digest(manifest["replay_config_hash"]),
        "Invalid provenance identities",
    )
    _require(
        manifest["candidate_config_hash"] is None
        and manifest["counterfactual_spec_digest"] is None,
        "Counterfactual publication outside U4 factual profile",
    )
    artifacts = [
        {
            "artifact_ref": "selection",
            "artifact_type": "RESEARCH_CERTIFIED_SELECTION",
            "sha256": selection_hash,
        },
        {
            "artifact_ref": "replay-manifest",
            "artifact_type": "RL_REPLAY_MANIFEST",
            "sha256": manifest_hash,
        },
    ]
    components = {}
    for name in ("metrics", "terminal_state"):
        doc, digest = read_evidence(run_path / f"{name}.json")
        meta = manifest["components"][name]
        _require(
            digest == meta["sha256"]
            and doc == manifest[name]
            and meta["record_count"] == 1
            and meta["bytes"] == (run_path / f"{name}.json").stat().st_size,
            "Publication component mismatch",
        )
        components[name] = doc
        artifacts.append(
            {
                "artifact_ref": f"replay-{name}",
                "artifact_type": "RL_REPLAY_AGGREGATE",
                "sha256": digest,
            }
        )
    metrics = components["metrics"]
    n = metrics["closed_trade_count"]
    _require(
        _n(n)
        and _n(manifest["population"]["closed_trade_count"])
        and _n(components["terminal_state"]["closed_trade_count"])
        and manifest["population"]["closed_trade_count"] == n
        and components["terminal_state"]["closed_trade_count"] == n
        and components["terminal_state"]["paper_epoch_id"]
        == manifest["paper_epoch_id"],
        "Closed population mismatch",
    )
    population = {
        "population_definition": "POSITION_CLOSED_FOR_PERFORMANCE",
        "n": n,
        "evidence_status": "COMPLETE",
        "statistical_strength": "DESCRIPTIVE_ONLY",
    }
    context = {
        **population,
        "dataset_id": manifest["dataset_id"],
        "source_boundary_id": manifest["source_boundary_id"],
        "paper_epoch_id": manifest["paper_epoch_id"],
        "research_run_id": manifest["research_run_id"],
        "diagnostic_run_id": selection["diagnostic_run_id"],
        "research_source_code_sha": manifest["research_replay_code_sha"],
        "research_config_hash": manifest["replay_config_hash"],
        "presentation_builder_source_sha": builder_source_sha,
    }
    performance = [
        _metric(
            name,
            metrics[name],
            unit,
            n,
            "replay-metrics",
            f"RL-REPLAY metrics.{name} (copied)",
        )
        for name, unit in (
            ("win_rate", "ratio"),
            ("profit_factor", "ratio"),
            ("expectancy_usd", "usd"),
            ("sharpe", "ratio"),
        )
    ]
    risk = [
        _metric(
            name,
            metrics[name],
            "ratio",
            n,
            "replay-metrics",
            f"RL-REPLAY metrics.{name} (copied)",
        )
        for name in (
            "realized_close_to_close_max_drawdown",
            "mark_to_market_max_drawdown",
        )
    ]
    limitations = [
        f"Certified selection reference: {ref}. Admission is supplied by Research governance; this adapter does not issue a certification.",
        "Descriptive Research evidence only; no causal or statistical adequacy claim.",
        "Candidate catalog NOT_AVAILABLE: zero published rows does not certify an empty registry.",
        "Publication is historical evidence, never live PAPER capital or a runtime/process status.",
        "Close-to-close drawdown is not mark-to-market drawdown.",
    ]
    for item in manifest["limitations"].values():
        if isinstance(item, dict) and isinstance(item.get("reason"), str):
            limitations.append(item["reason"])
    costs, attribution = [], []
    if diagnostic_path is None:
        limitations.append(
            "Diagnostic NOT_AVAILABLE: no diagnostic artifact admitted in this selection; closed-population fees and attribution are unavailable."
        )
    else:
        diag, digest = read_evidence(diagnostic_path)
        _require(
            digest == selection["diagnostic_sha256"]
            and diag["diagnostic_run_id"] == selection["diagnostic_run_id"],
            "Selected diagnostic mismatch",
        )
        di = _identity(diag, "diagnostic_run_identity", "diagnostic_run_id")
        _require(
            di["identity_schema"] == "rl-diag-01.run-identity.v1"
            and di["run_kind"] == "FACTUAL_PERFORMANCE_ATTRIBUTION"
            and di["diagnostic_method"] == "FACTUAL_PPL_PLUS_EXACT_PACKET_CONTEXT_V1",
            "Unsupported diagnostic identity",
        )
        for key in ("dataset_id", "source_boundary_id", "paper_epoch_id"):
            _require(
                diag[key] == di[key] == manifest[key],
                f"Diagnostic context mismatch: {key}",
            )
        _require(
            diag["upstream_research_run_id"]
            == di["upstream_research_run_id"]
            == manifest["research_run_id"]
            and di["research_replay_code_sha"] == manifest["research_replay_code_sha"]
            and _digest(di["research_diag_code_sha"], 40)
            and _digest(diag["diagnostic_config_hash"])
            and diag["diagnostic_config_hash"] == di["diagnostic_config_hash"],
            "Diagnostic upstream/config mismatch",
        )
        summary = diag["summary"]
        _require(
            di["population"]["definition"] == population["population_definition"]
            and di["population"]["closed_trade_count"] == n
            and type(summary["n"]) is int
            and summary["n"] == n
            and summary["paper_epoch_id"] == manifest["paper_epoch_id"]
            and summary["evidence_status"] == "COMPLETE"
            and summary["pnl_reconciliation"] == "PASS"
            and summary["fee_reconciliation"] == "PASS",
            "Diagnostic population/reconciliation mismatch",
        )
        _require(
            summary["statistical_strength"]
            in ("LOW_SAMPLE_DESCRIPTIVE_ONLY", "DESCRIPTIVE_ONLY"),
            "Unsupported diagnostic strength",
        )
        if summary["statistical_strength"] == "LOW_SAMPLE_DESCRIPTIVE_ONLY":
            population["statistical_strength"] = context["statistical_strength"] = (
                "LOW_SAMPLE"
            )
            limitations.append(
                "Diagnostic population is LOW_SAMPLE_DESCRIPTIVE_ONLY; no adequacy claim."
            )
        artifacts.append(
            {
                "artifact_ref": "diagnostic",
                "artifact_type": "RL_DIAG_RESULT",
                "sha256": digest,
            }
        )
        performance.insert(
            0,
            _scalar(
                "net_realized_pnl_usd",
                summary["net_realized_pnl_usd"],
                "usd",
                n,
                "diagnostic",
                "RL-DIAG closed summary (copied)",
            ),
        )
        costs = [
            _scalar(
                "closed_population_fees_usd",
                summary["closed_population_fees_usd"],
                "usd",
                n,
                "diagnostic",
                "RL-DIAG closed_population_fees_usd; excludes non-closed entry fees (copied)",
            )
        ]
        for dimension in ("by_symbol", "by_side", "by_regime", "by_conviction"):
            groups = diag["categorical_attribution"][dimension]
            _require(
                isinstance(groups, dict) and len(groups) <= 100,
                "Invalid/bounded attribution",
            )
            rows = []
            for label, group in sorted(groups.items()):
                group_n = group["n"]
                _require(_n(group_n) and group_n <= n, "Attribution population invalid")
                _require(
                    group.get("statistical_strength") == "DESCRIPTIVE_ONLY",
                    "Unsupported attribution strength",
                )
                rows.append(
                    {
                        "label": label,
                        "population_n": group_n,
                        "metrics": [
                            _scalar(
                                "net_realized_pnl_usd",
                                group["net_realized_pnl_usd"],
                                "usd",
                                group_n,
                                "diagnostic",
                                f"RL-DIAG {dimension}.{label} (copied)",
                            )
                        ],
                    }
                )
            _require(
                sum(row["population_n"] for row in rows) == n,
                "Attribution coverage mismatch",
            )
            attribution.append(
                {
                    "dimension": dimension,
                    "evidence_status": "COMPLETE",
                    "statistical_strength": "DESCRIPTIVE_ONLY",
                    "rows": rows,
                }
            )
        for item in diag["limitations"].values():
            if isinstance(item, dict) and isinstance(item.get("reason"), str):
                limitations.append(item["reason"])
    if n == 0:
        performance, risk, costs, attribution = [], [], [], []
        limitations.append(
            "Certified closed-performance population is empty; no performance metrics are presented."
        )
    snapshot = {
        "schema_version": "1.0.0",
        "product": "ResearchLabSnapshot",
        "domain": "research_lab",
        "authority": "RESEARCH_NON_AUTHORITATIVE",
        "generated_at_utc": generated_at_utc,
        "presentation_builder_source_sha": builder_source_sha,
        "research_state": "EMPTY" if n == 0 else "AVAILABLE",
        "provenance": {"primary_context": context, "source_artifacts": artifacts},
        "population": population,
        "performance": performance,
        "risk_stability": risk,
        "costs": costs,
        "attribution": attribution,
        "candidate_registry": {"candidate_count": 0, "rows": []},
        "limitations": list(dict.fromkeys(limitations)),
    }
    _require(
        validate_research_lab_snapshot(snapshot), "Presentation failed closed schema"
    )
    _require(
        len(canonical_snapshot_bytes(snapshot)) <= 512 * 1024,
        "Presentation exceeds byte limit",
    )
    pretty_bytes = (
        json.dumps(
            snapshot, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
        ).encode("utf-8")
        + b"\n"
    )
    _require(
        len(pretty_bytes) <= 1024 * 1024, "Pretty presentation exceeds API byte limit"
    )
    return snapshot


def build_research_presentation(
    selection_path: str | Path,
    run_path: str | Path,
    diagnostic_path: str | Path | None = None,
    *,
    generated_at_utc: str,
    builder_source_sha: str,
) -> dict:
    """Deterministic adaptation; all clock/SHA/selection inputs are explicit."""
    try:
        return _build(
            Path(selection_path),
            Path(run_path),
            Path(diagnostic_path) if diagnostic_path else None,
            generated_at_utc=generated_at_utc,
            builder_source_sha=builder_source_sha,
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        OverflowError,
        RecursionError,
    ) as exc:
        raise ResearchPublicationError("Research evidence admission failed") from exc


def publish_research_presentation(
    output: str | Path,
    selection_path: str | Path,
    run_path: str | Path,
    diagnostic_path: str | Path | None = None,
    *,
    generated_at_utc: str,
    builder_source_sha: str,
) -> str:
    """Only presentation output may change; source directories are protected."""
    target = Path(output).absolute()
    roots = [Path(run_path).resolve(), Path(selection_path).resolve().parent]
    if diagnostic_path:
        roots.append(Path(diagnostic_path).resolve().parent)
    _require(
        not any(p.is_symlink() for p in (target, *target.parents)),
        "Symlink output refused",
    )
    _require(
        not any(target.resolve().is_relative_to(root) for root in roots),
        "Output overlaps Research evidence",
    )
    snapshot = build_research_presentation(
        selection_path,
        run_path,
        diagnostic_path,
        generated_at_utc=generated_at_utc,
        builder_source_sha=builder_source_sha,
    )
    return publish_research_lab_snapshot(target, snapshot)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at-utc", required=True)
    parser.add_argument("--builder-source-sha", required=True)
    args = parser.parse_args()
    digest = publish_research_presentation(
        args.output,
        args.selection,
        args.run,
        args.diagnostic,
        generated_at_utc=args.generated_at_utc,
        builder_source_sha=args.builder_source_sha,
    )
    print(f"RESEARCH_PRESENTATION_SHA256={digest}")


if __name__ == "__main__":
    main()
