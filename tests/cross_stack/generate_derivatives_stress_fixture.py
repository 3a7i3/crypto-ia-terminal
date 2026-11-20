"""Synthetic observations -> pure builder -> bounded reader -> real GET route (no network)."""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from observability.market_stress.publication import build_publication
from observability.operator_api import app as api
from observability.operator_api.derivatives_stress_reader import DerivativesStressReader
from tests.market_stress.support import NOW, pilot

KW = dict(as_of=NOW, max_age_ms=5000, max_skew_ms=500, history_tolerance_ms=60_000, evidence_kind="SYNTHETIC")


def generate_derivatives_stress_fixture(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bindings, observations = pilot()
    previous = api._derivatives_stress_reader
    try:
        for name, items, age in [
            ("S_derivatives_stress", observations, 0.1),
            ("S_derivatives_stress_stale", observations, 60),
            ("S_derivatives_stress_partial", observations[:4], 0.1),
            ("S_derivatives_stress_unresolved", [], 0.1),
        ]:
            doc = build_publication(bindings, items, **KW)
            path = out_dir / "_producer" / name / "derivatives_stress.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
            api._derivatives_stress_reader = DerivativesStressReader(path, now_fn=lambda a=age: NOW.timestamp() + a)
            with TestClient(api.app) as client:
                response = client.get("/api/operator/v1/derivatives-stress")
            assert response.status_code == 200
            (out_dir / (name + ".json")).write_text(
                json.dumps({"http_status": response.status_code, "body": response.json()}, indent=2, sort_keys=True),
                encoding="utf-8")
    finally:
        api._derivatives_stress_reader = previous


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    generate_derivatives_stress_fixture(p.parse_args().out)
