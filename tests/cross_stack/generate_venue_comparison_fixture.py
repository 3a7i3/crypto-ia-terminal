"""Synthetic venue responses -> pure builder -> bounded reader -> real GET route."""

import argparse
import json
from pathlib import Path
from fastapi.testclient import TestClient
from observability.market_venues.publication import build_publication
from observability.operator_api import app as api
from observability.operator_api.venue_comparison_reader import VenueComparisonReader
from tests.market_venues.support import NOW, pilot


def generate_venue_comparison_fixture(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bindings, observations = pilot()
    previous = api._venue_comparison_reader
    try:
        for name, items, age in [
            ("S_market_venues", observations, 0.1),
            ("S_market_venues_stale", observations, 60),
            ("S_market_venues_unresolved", [], 0.1),
        ]:
            doc = build_publication(
                bindings,
                items,
                as_of=NOW,
                max_age_ms=5000,
                max_skew_ms=100,
                evidence_kind="SYNTHETIC",
            )
            path = out_dir / "_producer" / name / "venues.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
            api._venue_comparison_reader = VenueComparisonReader(
                path, now_fn=lambda: NOW.timestamp() + age
            )
            with TestClient(api.app) as client:
                response = client.get("/api/operator/v1/venue-comparison")
            result = {"http_status": response.status_code, "body": response.json()}
            assert response.status_code == 200
            (out_dir / (name + ".json")).write_text(
                json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
            )
    finally:
        api._venue_comparison_reader = previous


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    generate_venue_comparison_fixture(p.parse_args().out)
