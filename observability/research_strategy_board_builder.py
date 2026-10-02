"""Offline adapter of admitted candidate/evaluation/assessment artifacts.

No directory discovery, evaluation engine, ranking algorithm or runtime action.
Assessment verdicts and ranks must already be published by Research governance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from observability.research_lab_schema import snapshot_sha256
from observability.research_evidence_io import read_evidence
from observability.research_strategy_board_contract import (
    CRITERIA,
    MAX_BYTES,
    MAX_ROWS,
    keys,
    text,
    digest,
    validate_strategy_board,
)
from research_candidate.candidate import (
    validate_candidate,
    validate_evaluation_result,
    evaluation_run_identity,
)

SELECTION_SCHEMA = "app-unify.research-strategy-selection.v1"
ASSESSMENT_SCHEMA = "research-strategy-assessment.v1"


class StrategyBoardError(ValueError):
    """Admission failed; no output or source modification is allowed."""


def require(condition, reason):
    if not condition:
        raise StrategyBoardError(reason)


def _source(root, selected, artifacts, ref, kind):
    require(
        keys(selected, "path sha256")
        and text(selected["path"], 512)
        and digest(selected["sha256"]),
        "Invalid artifact selection",
    )
    relative = Path(selected["path"])
    require(
        not relative.is_absolute() and ".." not in relative.parts,
        "Artifact path must stay inside evidence root",
    )
    path = root / relative
    require(path.resolve().is_relative_to(root.resolve()), "Evidence path escaped root")
    doc, sha = read_evidence(path)
    require(sha == selected["sha256"], "Selected artifact digest mismatch")
    artifacts.append({"artifact_ref": ref, "artifact_type": kind, "sha256": sha})
    return doc


def _build(selection_path, root, *, generated_at_utc, builder_source_sha):
    selection, sha = read_evidence(selection_path)
    require(
        keys(selection, "schema_version admission certification_ref candidates"),
        "Invalid closed selection",
    )
    require(
        selection["schema_version"] == SELECTION_SCHEMA
        and selection["admission"] == "CERTIFIED"
        and text(selection["certification_ref"], 512),
        "Explicit Research admission required",
    )
    require(
        isinstance(selection["candidates"], list)
        and len(selection["candidates"]) <= MAX_ROWS,
        "Candidate selection exceeds limit",
    )
    artifacts = [
        {
            "artifact_ref": "selection",
            "artifact_type": "RESEARCH_CERTIFIED_SELECTION",
            "sha256": sha,
        }
    ]
    rows = []
    for selected in selection["candidates"]:
        require(
            keys(selected, "candidate_id label candidate evaluation assessment")
            and digest(selected["candidate_id"])
            and text(selected["label"], 128),
            "Invalid candidate selection",
        )
        candidate_id = selected["candidate_id"]
        c = _source(
            root,
            selected["candidate"],
            artifacts,
            "candidate:" + candidate_id,
            "RL_CANDIDATE",
        )
        require(validate_candidate(c) == candidate_id, "Candidate identity mismatch")
        code_components = [
            item for item in c["proposal"]["components"] if item["kind"] == "CODE_PATCH"
        ]
        # Multiple code patches cannot silently identify one source version.
        proposed = {item["proposed_source_sha"] for item in code_components}
        require(len(proposed) <= 1, "Ambiguous strategy source version")
        source_sha = next(iter(proposed), "NOT_IMPLEMENTED")
        evaluation = None
        if selected["evaluation"] is not None:
            source = _source(
                root,
                selected["evaluation"],
                artifacts,
                "pending-evaluation:" + candidate_id,
                "RL_CANDIDATE_EVALUATION",
            )
            evaluation_id = validate_evaluation_result(source, candidate=c)
            artifacts[-1]["artifact_ref"] = "evaluation:" + evaluation_id
            identity = source["evaluation_run_identity"]
            # Verify the declared dataset requirement/method binding against the
            # candidate, not just an internally self-consistent identity digest.
            requirement = next(
                (
                    r
                    for r in c["evaluation_plan"]["dataset_requirements"]
                    if r["requirement_id"]
                    == identity["satisfied_dataset_requirement_id"]
                ),
                None,
            )
            require(
                requirement is not None and requirement["kind"] == "EXACT_DATASET",
                "Future dataset binding outside initial board profile",
            )
            checked = evaluation_run_identity(
                candidate=c,
                dataset_id=source["dataset_id"],
                source_boundary_id=source["source_boundary_id"],
                satisfied_dataset_requirement_id=identity[
                    "satisfied_dataset_requirement_id"
                ],
                dataset_evidence_role=source["dataset_evidence_role"],
                dataset_source_domain=requirement["source_domain"],
                dataset_source_authority=requirement["source_authority"],
                evaluation_engine_code_sha=identity["evaluation_engine_code_sha"],
                evaluation_method_version=identity["evaluation_method_version"],
                evaluation_config_hash=identity["evaluation_config_hash"],
                population_definition=identity["population_definition"],
                metric_semantics_version=identity["metric_semantics_version"],
            )
            require(
                checked == identity
                and identity["population_definition"]
                == c["evaluation_plan"]["population_definition"],
                "Evaluation plan binding mismatch",
            )
            metrics = []
            for metric in source["metrics"]:
                require(
                    metric["metric_semantics_version"]
                    == identity["metric_semantics_version"],
                    "Metric semantics mismatch",
                )
                metrics.append(
                    {
                        k: metric[k]
                        for k in (
                            "metric_name",
                            "metric_semantics_version",
                            "n",
                            "value",
                            "evidence_status",
                            "statistical_strength",
                            "baseline_value",
                            "candidate_value",
                            "delta",
                            "derivation",
                        )
                    }
                )
            evaluation = {
                "evaluation_run_id": evaluation_id,
                "dataset_id": source["dataset_id"],
                "source_boundary_id": source["source_boundary_id"],
                "role": source["dataset_evidence_role"],
                "method": identity["evaluation_method_version"],
                "metric_semantics_version": identity["metric_semantics_version"],
                "config_hash": identity["evaluation_config_hash"],
                "baseline_id": snapshot_sha256(c["baseline"]),
                "source_code_sha": identity["evaluation_engine_code_sha"],
                "run_status": source["run_status"],
                "population_definition": identity["population_definition"],
                "metrics": metrics,
                "generated_at_utc": source["generated_at_utc"],
            }
        criteria = [
            {
                "criterion_id": key,
                "status": "NOT_AVAILABLE",
                "reason": "Aucun verdict de critère publié pour cette évaluation.",
                "metric_refs": [],
            }
            for key in CRITERIA
        ]
        ranking = policy_id = policy_ref = None
        if selected["assessment"] is not None:
            assessment = _source(
                root,
                selected["assessment"],
                artifacts,
                "assessment:" + candidate_id,
                "RESEARCH_STRATEGY_ASSESSMENT",
            )
            require(
                keys(
                    assessment,
                    "schema_version candidate_id evaluation_run_id policy_id policy_ref criteria ranking",
                ),
                "Invalid assessment contract",
            )
            require(
                assessment["schema_version"] == ASSESSMENT_SCHEMA
                and assessment["candidate_id"] == candidate_id
                and evaluation is not None
                and assessment["evaluation_run_id"] == evaluation["evaluation_run_id"],
                "Assessment evaluation binding mismatch",
            )
            criteria, ranking = assessment["criteria"], assessment["ranking"]
            policy_id, policy_ref = assessment["policy_id"], assessment["policy_ref"]
            require(
                digest(policy_id) and text(policy_ref, 512),
                "Declared assessment policy required",
            )
        limitations = list(
            dict.fromkeys(
                c["known_limitations"]
                + (source["known_limitations"] if evaluation else [])
                + [
                    "Étape du registre et activation runtime NOT_AVAILABLE : aucun journal d'état n'est admis dans ce tableau."
                ]
            )
        )
        rows.append(
            {
                "candidate_id": candidate_id,
                "candidate_class": c["candidate_class"],
                "label": selected["label"],
                "hypothesis": c["hypothesis"]["question"],
                "rationale": c["hypothesis"]["rationale"],
                "target_domains": c["target_domains"],
                "source_code_sha": source_sha,
                "config_hash": c["candidate_config_hash"],
                "evaluation": evaluation,
                "criteria": criteria,
                "ranking": ranking,
                "assessment_policy_id": policy_id,
                "assessment_policy_ref": policy_ref,
                "limitations": limitations,
            }
        )
    rows.sort(key=lambda row: row["candidate_id"])
    doc = {
        "schema_version": "1.0.0",
        "product": "ResearchStrategyBoardSnapshot",
        "domain": "research_strategy_board",
        "authority": "RESEARCH_NON_AUTHORITATIVE",
        "generated_at_utc": generated_at_utc,
        "builder_source_sha": builder_source_sha,
        "admission_ref": selection["certification_ref"],
        "catalog_state": "AVAILABLE" if rows else "EMPTY",
        "rows": rows,
        "source_artifacts": artifacts,
        "limitations": [
            "Admission fournie par la gouvernance Research ; ce builder ne certifie ni n'authentifie une admission.",
            "Verdicts et rangs recopiés depuis des assessments explicitement admis ; aucun seuil ou classement calculé par l'app.",
            "Comparaison limitée aux cohortes exactes publiées. Aucun classement global entre cohortes.",
            "Résultats descriptifs/historiques, jamais une autorisation de trader ou de promouvoir.",
        ],
    }
    require(validate_strategy_board(doc), "Invalid strategy presentation")
    payload = (
        json.dumps(
            doc, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
        ).encode()
        + b"\n"
    )
    require(len(payload) <= MAX_BYTES, "Presentation byte limit exceeded")
    return doc


def build_strategy_board(
    selection_path, evidence_root, *, generated_at_utc, builder_source_sha
):
    try:
        return _build(
            Path(selection_path),
            Path(evidence_root),
            generated_at_utc=generated_at_utc,
            builder_source_sha=builder_source_sha,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        UnicodeError,
        OverflowError,
        RecursionError,
        StopIteration,
    ) as exc:
        raise StrategyBoardError("Research strategy evidence admission failed") from exc


def publish_strategy_board(
    output, selection_path, evidence_root, *, generated_at_utc, builder_source_sha
):
    target, root, selection = Path(output), Path(evidence_root), Path(selection_path)
    require(
        not any(
            p.is_symlink() for p in (target.absolute(), *target.absolute().parents)
        ),
        "Symlink output refused",
    )
    require(
        not target.resolve().is_relative_to(root.resolve())
        and not target.resolve().is_relative_to(selection.resolve().parent),
        "Output overlaps evidence",
    )
    doc = build_strategy_board(
        selection,
        root,
        generated_at_utc=generated_at_utc,
        builder_source_sha=builder_source_sha,
    )
    # Reuse the atomic byte writer pattern, while keeping this domain separate
    # from the WEB-RL 1.0.0 envelope (no schema substitution).
    import os
    import tempfile

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix="." + target.name + ".", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(
                json.dumps(
                    doc, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
                ).encode()
                + b"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
    from observability.research_lab_schema import snapshot_sha256

    return snapshot_sha256(doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at-utc", required=True)
    parser.add_argument("--builder-source-sha", required=True)
    args = parser.parse_args()
    print(
        "RESEARCH_STRATEGY_BOARD_SHA256="
        + publish_strategy_board(
            args.output,
            args.selection,
            args.evidence_root,
            generated_at_utc=args.generated_at_utc,
            builder_source_sha=args.builder_source_sha,
        )
    )


if __name__ == "__main__":
    main()
