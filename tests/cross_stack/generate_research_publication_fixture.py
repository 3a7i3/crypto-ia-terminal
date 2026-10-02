"""Synthetic Research engines/publication -> U4 builder -> artifact -> real GET.

Scientific engines run ONLY in this isolated fixture generator, never in the
production adapter/API. All input ledger/packet evidence is synthetic test data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.research_lab_reader import ResearchLabSnapshotReader
from observability.research_lab_schema import canonical_snapshot_bytes
from observability.research_publication_builder import (
    SELECTION_SCHEMA,
    publish_research_presentation,
)
from research_diag import diagnose_factual_dataset
from research_replay.factual import replay_factual_dataset
from research_replay.publication import publish_factual_result
from tests.research_diag.test_rl_diag_01_factual import _build_dataset

NOW = "2026-10-02T00:00:00Z"


def prepare_evidence(
    root: Path, *, diagnostic: bool = True
) -> tuple[Path, Path, Path | None]:
    root.mkdir(parents=True, exist_ok=True)
    # Freeze fixture-only packet clocks, including the dataclass factory bound
    # at import time. No production code, ledger or clock configuration changes.
    from core.decision_packet import DecisionPacket

    class FixtureDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return cls(2026, 10, 2)

    def fixture_packet(**kwargs):
        return DecisionPacket(**kwargs, created_at=FixtureDateTime.utcnow())

    with (
        patch("core.decision_packet.datetime", FixtureDateTime),
        patch(
            "tests.research_diag.test_rl_diag_01_factual.DecisionPacket", fixture_packet
        ),
    ):
        dataset = _build_dataset(root)
    replay = replay_factual_dataset(dataset, replay_code_sha="a" * 40)
    published = publish_factual_result(
        replay, output_root=root / "research", generated_at_utc=NOW
    )
    diag_path = None
    diag_id = diag_hash = None
    if diagnostic:
        diag = diagnose_factual_dataset(
            dataset, replay_code_sha="a" * 40, diag_code_sha="b" * 40
        )
        raw = canonical_snapshot_bytes(diag.as_dict()) + b"\n"
        diag_path = root / "diagnostics" / diag.diagnostic_run_id / "result.json"
        diag_path.parent.mkdir(parents=True)
        diag_path.write_bytes(raw)
        diag_id, diag_hash = diag.diagnostic_run_id, hashlib.sha256(raw).hexdigest()
    selection = {
        "schema_version": SELECTION_SCHEMA,
        "certification_ref": "synthetic-test-only:U4-admission",
        "admission": "CERTIFIED",
        "research_run_id": replay.research_run_id,
        "manifest_sha256": hashlib.sha256(
            (published.run_path / "manifest.json").read_bytes()
        ).hexdigest(),
        "diagnostic_run_id": diag_id,
        "diagnostic_sha256": diag_hash,
    }
    selection_path = root / "admission" / "selection.json"
    selection_path.parent.mkdir(parents=True)
    selection_path.write_bytes(canonical_snapshot_bytes(selection) + b"\n")
    return selection_path, published.run_path, diag_path


def generate_research_publication_fixture(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    root = out / "_producer" / "N_research_publication"
    root.mkdir(parents=True, exist_ok=True)
    # Each call gets an isolated workspace; immutable runs are never overwritten.
    import tempfile

    evidence = Path(tempfile.mkdtemp(prefix="evidence-", dir=root))
    selection, run, diag = prepare_evidence(evidence)
    target = evidence / "presentation" / "research_lab_snapshot.json"
    digest = publish_research_presentation(
        target, selection, run, diag, generated_at_utc=NOW, builder_source_sha="c" * 40
    )
    previous = api_app.get_research_lab_reader()
    api_app._research_lab_reader = ResearchLabSnapshotReader(target)
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/research-lab")
    finally:
        api_app._research_lab_reader = previous
    result = {
        "http_status": response.status_code,
        "body": response.json(),
        "_proof": {
            "snapshot_sha256": digest,
            "builder_invoked": True,
            "fixture_is_synthetic": True,
            "manifest_sha256": hashlib.sha256(
                (run / "manifest.json").read_bytes()
            ).hexdigest(),
            "diagnostic_sha256": hashlib.sha256(diag.read_bytes()).hexdigest(),
        },
    }
    (out / "N_research_publication.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate_research_publication_fixture(args.out)
    print("[cross-stack] Generated U4 N_research_publication fixture")
