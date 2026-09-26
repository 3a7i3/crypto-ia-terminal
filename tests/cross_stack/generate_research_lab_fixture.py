"""Generate WEB-RL Research Lab cross-stack evidence through the real path.

deterministic fixture evidence
    -> publish_research_lab_snapshot
    -> atomic presentation artifact
    -> ResearchLabSnapshotReader
    -> real FastAPI GET /api/operator/v1/research-lab

The fixture values are synthetic test evidence only. No Research metric engine,
PPL ledger, advisor, exchange, runtime or candidate promotion is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.research_lab_reader import ResearchLabSnapshotReader
from observability.research_lab_snapshot import publish_research_lab_snapshot


def _metric(
    name: str,
    value,
    *,
    unit: str = "usd",
    evidence_status: str = "COMPLETE",
    statistical_strength: str = "LOW_SAMPLE",
    population_n: int = 13,
    reason: str | None = None,
) -> dict:
    return {
        "metric_name": name,
        "value": value,
        "unit": unit,
        "evidence_status": evidence_status,
        "statistical_strength": statistical_strength,
        "population_n": population_n,
        "derivation": "cross-stack fixture producer-authored value",
        "source_ref": "diag-a4",
        "reason": reason,
    }


def _snapshot() -> dict:
    artifact = {
        "artifact_ref": "diag-a4",
        "artifact_type": "RL_DIAG_RESULT",
        "sha256": "6" * 64,
    }
    return {
        "schema_version": "1.0.0",
        "product": "ResearchLabSnapshot",
        "domain": "research_lab",
        "authority": "RESEARCH_NON_AUTHORITATIVE",
        "generated_at_utc": "2026-09-26T01:00:00Z",
        "presentation_builder_source_sha": "b" * 40,
        "research_state": "AVAILABLE",
        "provenance": {
            "primary_context": {
                "dataset_id": "1" * 64,
                "source_boundary_id": "2" * 64,
                "paper_epoch_id": "F00-EPOCH-01-20260920T084335Z",
                "research_run_id": "3" * 64,
                "diagnostic_run_id": "4" * 64,
                "research_source_code_sha": "a" * 40,
                "research_config_hash": "5" * 64,
                "presentation_builder_source_sha": "b" * 40,
                "population_definition": "POSITION_CLOSED_FOR_PERFORMANCE",
                "n": 13,
                "evidence_status": "COMPLETE",
                "statistical_strength": "LOW_SAMPLE",
            },
            "source_artifacts": [artifact],
        },
        "population": {
            "population_definition": "POSITION_CLOSED_FOR_PERFORMANCE",
            "n": 13,
            "evidence_status": "COMPLETE",
            "statistical_strength": "LOW_SAMPLE",
        },
        "performance": [
            _metric("net_realized_pnl_usd", 1.863570581569077),
            _metric("profit_factor", 3.49943849831141, unit="ratio"),
            _metric(
                "annualized_sharpe",
                None,
                unit="ratio",
                evidence_status="NOT_AVAILABLE",
                statistical_strength="NOT_EVALUATED",
                reason="No certified time-series/annualized return basis.",
            ),
        ],
        "risk_stability": [
            _metric(
                "mark_to_market_maxdd",
                None,
                unit="ratio",
                evidence_status="NOT_AVAILABLE",
                statistical_strength="NOT_EVALUATED",
                reason="No authoritative mark-to-market path.",
            )
        ],
        "costs": [
            _metric("fees_usd", 0.26),
            _metric(
                "funding_usd",
                None,
                evidence_status="NOT_AVAILABLE",
                statistical_strength="NOT_EVALUATED",
                reason="No certified funding stream.",
            ),
        ],
        "attribution": [
            {
                "dimension": "packet_regime",
                "evidence_status": "COMPLETE",
                "statistical_strength": "LOW_SAMPLE",
                "rows": [
                    {
                        "label": "TREND_BULL",
                        "population_n": 9,
                        "metrics": [
                            _metric(
                                "net_realized_pnl_usd",
                                1.9707128645572642,
                                population_n=9,
                            )
                        ],
                    },
                    {
                        "label": "RANGE",
                        "population_n": 4,
                        "metrics": [
                            _metric(
                                "net_realized_pnl_usd",
                                -0.10714228298818732,
                                population_n=4,
                            )
                        ],
                    },
                ],
            }
        ],
        "candidate_registry": {"candidate_count": 0, "rows": []},
        "limitations": [
            "N=13 / LOW_SAMPLE",
            "No causal inference",
            "No authoritative mark-to-market path",
        ],
    }


def generate_research_lab_fixture(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    producer_dir = out_dir / "_producer" / "I_research_lab"
    producer_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = producer_dir / "research_lab_snapshot.json"
    snapshot = _snapshot()
    digest = publish_research_lab_snapshot(artifact_path, snapshot)

    previous = api_app.get_research_lab_reader()
    api_app._research_lab_reader = ResearchLabSnapshotReader(path=artifact_path)
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/research-lab")
        body = response.json()
    finally:
        api_app._research_lab_reader = previous

    result = {
        "http_status": response.status_code,
        "body": body,
        "_proof": {
            "producer_authority": snapshot["authority"],
            "artifact_is_regular_file": artifact_path.is_file(),
            "snapshot_sha256": digest,
            "research_state": snapshot["research_state"],
            "population_n": snapshot["population"]["n"],
            "candidate_count": snapshot["candidate_registry"]["candidate_count"],
        },
    }
    (out_dir / "I_research_lab.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    generate_research_lab_fixture(args.out)
    print("[cross-stack] Generated WEB-RL I_research_lab fixture")


if __name__ == "__main__":
    main()
