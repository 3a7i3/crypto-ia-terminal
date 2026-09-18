"""Generate the WEB-02 real producer -> API PPL comparison fixture."""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.ppl_comparison_reader import (
    PplComparisonSnapshotReader,
)
from observability.ppl_comparison import write_ppl_comparison_snapshot
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ppl_shadow import (
    PPLShadowRuntime,
    ShadowEpochManifest,
)

FIXED_NOW = 1_700_000_000.0


class _ComparisonSim:
    def __init__(self, shadow: PPLShadowRuntime) -> None:
        self._lock = threading.Lock()
        # Deliberate raw source divergence used only to prove transport:
        # WEB-02 must display it, never repair it.
        self._capital = 99.99
        self._initial_capital = 100.0
        self._positions = {}
        self._closed = []
        self._shadow_observer = shadow


def generate_ppl_fixture(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    producer_dir = out_dir / "_producer" / "H_ppl_comparison"
    producer_dir.mkdir(parents=True, exist_ok=True)

    manifest = ShadowEpochManifest(
        paper_epoch_id="web02-cross-stack-epoch",
        created_at=FIXED_NOW - 100.0,
        initial_virtual_capital=100.0,
        code_sha="a" * 40,
        config_snapshot_hash="b" * 64,
    )
    shadow = PPLShadowRuntime(
        manifest=manifest,
        store=DurableEventStore(producer_dir / "ppl_store"),
    )
    assert shadow.bind_legacy_state(
        available_capital=100.0,
        open_positions=[],
    )

    artifact_path = producer_dir / "ppl_comparison_snapshot.json"
    artifact = write_ppl_comparison_snapshot(
        _ComparisonSim(shadow),
        path=artifact_path,
        cycle=17,
        process_instance_id="web02-cross-stack-process",
        source_sha="c" * 40,
        now_fn=lambda: FIXED_NOW,
    )

    previous = api_app.get_ppl_comparison_reader()
    api_app._ppl_comparison_reader = PplComparisonSnapshotReader(
        artifact_path,
        stale_after_s=90.0,
        now_fn=lambda: FIXED_NOW,
    )
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/ppl-comparison")
        body = response.json()
    finally:
        api_app._ppl_comparison_reader = previous

    cash = next(
        row
        for row in artifact["comparisons"]
        if row["domain"] == "accounting" and row["field"] == "free_cash"
    )
    result = {
        "http_status": response.status_code,
        "body": body,
        "_proof": {
            "producer_authority": artifact["authority"],
            "shadow_authority": artifact["ppl_source"]["authority"],
            "legacy_authority": artifact["legacy_source"]["authority"],
            "artifact_is_regular_file": artifact_path.is_file(),
            "raw_legacy_cash": cash["legacy"]["value"],
            "raw_ppl_cash": cash["ppl"]["value"],
            "producer_delta": cash["delta_ppl_minus_legacy"],
        },
    }
    (out_dir / "H_ppl_comparison.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    generate_ppl_fixture(out_dir)
    print("[cross-stack] Generated WEB-02 H_ppl_comparison fixture")


if __name__ == "__main__":
    main()
