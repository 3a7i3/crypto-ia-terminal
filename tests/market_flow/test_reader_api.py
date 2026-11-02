"""Reader and GET route for the Flux artifact. Fixture file only; nothing configured by default."""

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from observability.market_flow.artifact import validate_artifact  # noqa: E402
from observability.operator_api import app as api  # noqa: E402
from observability.operator_api.market_flow_reader import MarketFlowReader  # noqa: E402

GOLDEN = Path(__file__).resolve().parents[2] / "observability/market_flow/fixtures/market_flow_artifact_synthetic.json"
URL = "/api/operator/v1/market-flow"


@pytest.fixture(autouse=True)
def restore():
    yield
    api.configure_market_flow_reader(None)


def test_unconfigured_reader_is_a_typed_error_not_an_empty_population(monkeypatch):
    monkeypatch.delenv("OPERATOR_MARKET_FLOW_PATH", raising=False)
    r = MarketFlowReader().read()
    assert (r.ok, r.error_code) == (False, "MARKET_FLOW_NOT_CONFIGURED")
    api.configure_market_flow_reader(None)
    res = TestClient(api.app).get(URL)
    assert res.status_code == 503 and res.json() == {"error_code": "MARKET_FLOW_NOT_CONFIGURED"}
    assert res.headers["cache-control"] == "no-store"


def test_fixture_is_served_unchanged_and_labelled_synthetic_without_a_freshness_claim():
    api.configure_market_flow_reader(str(GOLDEN))
    res = TestClient(api.app).get(URL)
    body = res.json()
    assert res.status_code == 200 and body["state_label"] == "SYNTHETIC"
    assert body["serving"] == {"freshness_classification": "NOT_ASSESSED_SYNTHETIC"}
    served = {k: v for k, v in body.items() if k != "serving"}
    assert served == json.loads(GOLDEN.read_text())  # the reader recomputes nothing
    assert validate_artifact(served)


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(score="9"), "MARKET_FLOW_INVALID_SCHEMA"),
    (lambda d: d.update(synthetic=False), "MARKET_FLOW_INVALID_SCHEMA"),
    (lambda d: d.pop("bars"), "MARKET_FLOW_INVALID_SCHEMA"),
])
def test_invalid_artifacts_are_refused(tmp_path, mutate, code):
    doc = json.loads(GOLDEN.read_text())
    mutate(doc)
    p = tmp_path / "a.json"
    p.write_text(json.dumps(doc))
    assert MarketFlowReader(str(p)).read().error_code == code


def test_missing_malformed_duplicate_key_large_and_symlink_paths_are_typed(tmp_path):
    assert MarketFlowReader(str(tmp_path / "none.json")).read().error_code == "MARKET_FLOW_MISSING"
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert MarketFlowReader(str(bad)).read().error_code == "MARKET_FLOW_MALFORMED_JSON"
    dup = tmp_path / "dup.json"
    dup.write_text('{"a":1,"a":2}')
    assert MarketFlowReader(str(dup)).read().error_code == "MARKET_FLOW_MALFORMED_JSON"
    nan = tmp_path / "nan.json"
    nan.write_text('{"a":NaN}')
    assert MarketFlowReader(str(nan)).read().error_code == "MARKET_FLOW_MALFORMED_JSON"
    link = tmp_path / "link.json"
    link.symlink_to(GOLDEN)
    assert MarketFlowReader(str(link)).read().error_code == "MARKET_FLOW_INVALID_PATH"
    big = tmp_path / "big.json"
    big.write_bytes(b" " * 4_000_001)
    assert MarketFlowReader(str(big)).read().error_code == "MARKET_FLOW_TOO_LARGE"


def test_route_is_get_only_and_reader_has_no_writer_or_exchange_import():
    c = TestClient(api.app)
    for method in (c.post, c.put, c.delete, c.patch):
        assert method(URL).status_code == 405
    src = (Path(__file__).resolve().parents[2] / "observability/operator_api/market_flow_reader.py").read_text()
    assert not any(w in src for w in ("socket", "requests", "urllib", "http.client", "write(", "write_text"))
