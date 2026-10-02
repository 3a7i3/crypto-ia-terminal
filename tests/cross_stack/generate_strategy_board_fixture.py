"""Synthetic immutable candidate publications -> passive board -> real API.

Predeclared fixture verdicts/ranks exercise transport, never scientific scoring.
No registry transitions, runtime promotion or strategy execution are performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from observability.operator_api import app as api_app
from observability.operator_api.research_strategy_board_reader import (
    ResearchStrategyBoardReader,
)
from observability.research_lab_schema import canonical_snapshot_bytes, snapshot_sha256
from observability.research_strategy_board_builder import (
    ASSESSMENT_SCHEMA,
    SELECTION_SCHEMA,
    publish_strategy_board,
)
from observability.research_strategy_board_contract import CRITERIA, comparison_identity
from research_candidate import compute_candidate_id, publish_candidate
from tests.research_candidate.test_rl_candidate_01_registry import (
    _candidate,
    _evaluation_result,
)

NOW = "2026-10-02T00:00:00Z"


def write_source(root: Path, relative: str, doc: dict) -> dict:
    raw = canonical_snapshot_bytes(doc) + b"\n"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}


def prepare_strategy_evidence(root: Path) -> tuple[Path, Path]:
    evidence = root / "evidence"
    rows = []
    for i, label in enumerate(
        (
            "Momentum · test synthétique",
            "Reversion · test synthétique",
            "PnL seul · sans verdict",
            "Hypothèse · non évaluée",
        )
    ):
        candidate = _candidate(candidate_config_hash="NOT_AVAILABLE")
        candidate.update(candidate_class="STRATEGY", target_domains=["STRATEGY"])
        candidate["proposal"] = {
            "components": [
                {
                    "kind": "CODE_PATCH",
                    "baseline_source_sha": "a" * 40,
                    "proposed_source_sha": "c" * 40,
                    "patch_sha256": str(i + 1) * 64,
                    "changed_paths": ["signal/strategies/synthetic_fixture.py"],
                    "semantic_domain": "STRATEGY",
                }
            ]
        }
        candidate["hypothesis"]["question"] = "Hypothèse synthétique : " + label
        candidate["candidate_id"] = compute_candidate_id(candidate)
        publication = publish_candidate(evidence / "registry", candidate)
        path = publication.path
        selected = {
            "candidate_id": candidate["candidate_id"],
            "label": label,
            "candidate": {
                "path": str(path.relative_to(evidence)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            "evaluation": None,
            "assessment": None,
        }
        if i < 3:
            evaluation = _evaluation_result(candidate)
            metric = evaluation["metrics"][0]
            if i == 1:
                metric.update(value=-1.0, candidate_value=-1.0, delta=-2.0)
            selected["evaluation"] = write_source(
                evidence, f"evaluations/{i}.json", evaluation
            )
            if i < 2:
                criteria = [
                    {
                        "criterion_id": key,
                        "status": "NOT_AVAILABLE",
                        "reason": "Preuve non publiée dans cette fixture synthétique.",
                        "metric_refs": [],
                    }
                    for key in CRITERIA
                ]
                criteria[0].update(
                    status="PASS" if i == 0 else "FAIL",
                    reason="Verdict synthétique prépublié ; ne certifie pas une stratégie réelle.",
                    metric_refs=[metric["metric_name"]],
                )
                criteria[1].update(
                    status="PARTIAL",
                    reason="N=13 : échantillon synthétique faible.",
                    metric_refs=[metric["metric_name"]],
                )
                rank = {
                    "group_id": "0" * 64,
                    "position": i + 1,
                    "group_size": 2,
                    "metric_name": metric["metric_name"],
                    "ordering": "DESC",
                    "reason": "Rang déclaré dans une cohorte synthétique uniquement.",
                }
                policy_id = snapshot_sha256(
                    {"policy": "SYNTHETIC_TRANSPORT_TEST_ONLY_V1"}
                )
                context = {
                    "dataset_id": evaluation["dataset_id"],
                    "source_boundary_id": evaluation["source_boundary_id"],
                    "role": evaluation["dataset_evidence_role"],
                    "method": evaluation["evaluation_run_identity"][
                        "evaluation_method_version"
                    ],
                    "metric_semantics_version": "METRICS_V1",
                    "config_hash": "7" * 64,
                    "baseline_id": snapshot_sha256(candidate["baseline"]),
                    "source_code_sha": "b" * 40,
                    "population_definition": "POSITION_CLOSED_FOR_PERFORMANCE",
                }
                rank["group_id"] = snapshot_sha256(
                    comparison_identity(
                        {
                            "evaluation": context,
                            "ranking": rank,
                            "assessment_policy_id": policy_id,
                        }
                    )
                )
                assessment = {
                    "schema_version": ASSESSMENT_SCHEMA,
                    "candidate_id": candidate["candidate_id"],
                    "evaluation_run_id": evaluation["evaluation_run_id"],
                    "policy_id": policy_id,
                    "policy_ref": "SYNTHETIC_TEST_ONLY:declared-verdicts",
                    "criteria": criteria,
                    "ranking": rank,
                }
                selected["assessment"] = write_source(
                    evidence, f"assessments/{i}.json", assessment
                )
        rows.append(selected)
    selection = root / "admission" / "selection.json"
    write_source(
        root,
        "admission/selection.json",
        {
            "schema_version": SELECTION_SCHEMA,
            "admission": "CERTIFIED",
            "certification_ref": "SYNTHETIC_TEST_ONLY:board-admission",
            "candidates": rows,
        },
    )
    return selection, evidence


def generate_strategy_board_fixture(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="strategy-board-", dir=out))
    selection, evidence = prepare_strategy_evidence(root)
    target = root / "presentation" / "strategy_board.json"
    sha = publish_strategy_board(
        target, selection, evidence, generated_at_utc=NOW, builder_source_sha="d" * 40
    )
    previous = api_app._research_strategy_board_reader
    api_app._research_strategy_board_reader = ResearchStrategyBoardReader(target)
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/research-strategies")
    finally:
        api_app._research_strategy_board_reader = previous
    result = {
        "http_status": response.status_code,
        "body": response.json(),
        "_proof": {
            "snapshot_sha256": sha,
            "fixture_is_synthetic": True,
            "immutable_candidate_publisher_invoked": True,
            "builder_invoked": True,
        },
    }
    (out / "O_research_strategies.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    generate_strategy_board_fixture(parser.parse_args().out)
