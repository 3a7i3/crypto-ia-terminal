import json

import pytest
from fastapi.testclient import TestClient

from observability.market_stress.publication import build_publication
from observability.operator_api import app as api
from observability.operator_api.derivatives_stress_reader import DerivativesStressReader
from tests.market_stress.support import NOW, pilot

KW = dict(as_of=NOW, max_age_ms=5000, max_skew_ms=500, history_tolerance_ms=60_000, evidence_kind="SYNTHETIC")


def write(tmp_path, doc=None, raw=None):
    path = tmp_path / "stress.json"
    if raw is None:
        bindings, observations = pilot()
        raw = json.dumps(doc if doc is not None else build_publication(bindings, observations, **KW))
    path.write_text(raw, encoding="utf-8")
    return path


def test_freshness_is_projected_without_recomputing_values(tmp_path):
    p = write(tmp_path)
    fresh = DerivativesStressReader(p, now_fn=lambda: NOW.timestamp() + 0.1).read()
    stale = DerivativesStressReader(p, now_fn=lambda: NOW.timestamp() + 4.9).read()
    assert fresh.ok and fresh.snapshot["freshness_classification"] == "FRESH"
    assert stale.snapshot["freshness_classification"] == "STALE"
    assert fresh.snapshot["underlyings"] == stale.snapshot["underlyings"]


def test_unconfigured_missing_symlink_and_directory_are_typed(tmp_path, monkeypatch):
    monkeypatch.delenv("OPERATOR_DERIVATIVES_STRESS_PATH", raising=False)
    assert DerivativesStressReader().read().error_code == "DERIVATIVES_STRESS_NOT_CONFIGURED"
    assert DerivativesStressReader(tmp_path / "missing").read().error_code == "DERIVATIVES_STRESS_MISSING"
    link = tmp_path / "link.json"
    link.symlink_to(write(tmp_path))
    assert DerivativesStressReader(link).read().error_code == "DERIVATIVES_STRESS_INVALID_PATH"
    assert DerivativesStressReader(tmp_path).read().error_code == "DERIVATIVES_STRESS_INVALID_PATH"


@pytest.mark.parametrize("raw,code", [
    ('{"a":1,"a":2}', "MALFORMED_JSON"), ("{", "MALFORMED_JSON"), ('{"x":NaN}', "MALFORMED_JSON"),
    ("{}", "INVALID_SCHEMA"), ("x" * 4_000_001, "TOO_LARGE"),
])
def test_corrupt_artifacts_never_become_an_empty_market(tmp_path, raw, code):
    assert DerivativesStressReader(write(tmp_path, raw=raw)).read().error_code == "DERIVATIVES_STRESS_" + code


def test_future_publication_is_refused(tmp_path):
    assert DerivativesStressReader(write(tmp_path), now_fn=lambda: NOW.timestamp() - 1).read().error_code.endswith("FUTURE")


def test_api_is_get_only_no_store_and_503_when_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_derivatives_stress_reader", DerivativesStressReader(write(tmp_path), now_fn=lambda: NOW.timestamp() + 0.1))
    with TestClient(api.app) as client:
        ok = client.get("/api/operator/v1/derivatives-stress")
        assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
        assert ok.json()["product"] == "MarketDerivativesStress"
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)("/api/operator/v1/derivatives-stress").status_code == 405
    monkeypatch.setattr(api, "_derivatives_stress_reader", DerivativesStressReader(tmp_path / "nope"))
    with TestClient(api.app) as client:
        r = client.get("/api/operator/v1/derivatives-stress")
        assert r.status_code == 503 and r.json() == {"error_code": "DERIVATIVES_STRESS_MISSING"}
