"""Synthetic store -> read-only reader -> real GET route (no network). Lot 2 Plateformes & levier."""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from observability.operator_api import app as api
from observability.operator_api.derivatives_positioning_reader import DerivativesPositioningReader
from tests.derivatives_positioning.positioning_fixture import AS_OF_MS, build


def generate_derivatives_positioning_fixture(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    producer = out_dir / "_producer" / "S_derivatives_positioning"
    data, roster = build(producer / "state", producer / "roster.json")
    previous = api._derivatives_positioning_reader
    try:
        for name, age_s in (("S_derivatives_positioning", 0), ("S_derivatives_positioning_stale", 3_600)):
            api._derivatives_positioning_reader = DerivativesPositioningReader(
                str(data), str(roster), now_fn=lambda a=age_s: AS_OF_MS / 1000 + a)
            with TestClient(api.app) as client:
                response = client.get("/api/operator/v1/derivatives-positioning")
            assert response.status_code == 200, response.text
            (out_dir / (name + ".json")).write_text(
                json.dumps({"http_status": 200, "body": response.json()}, indent=2, sort_keys=True), encoding="utf-8")
    finally:
        api._derivatives_positioning_reader = previous


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    generate_derivatives_positioning_fixture(p.parse_args().out)
