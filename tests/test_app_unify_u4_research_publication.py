from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.research_lab_reader import ResearchLabSnapshotReader
from observability.research_evidence_io import EvidenceReadError, read_evidence
from observability.research_lab_schema import (
    canonical_snapshot_bytes,
    validate_research_lab_snapshot,
)
from observability.research_publication_builder import (
    ResearchPublicationError,
    build_research_presentation,
    publish_research_presentation,
)
from tests.cross_stack.generate_research_publication_fixture import (
    NOW,
    prepare_evidence,
)


@pytest.fixture
def evidence(tmp_path):
    return prepare_evidence(tmp_path / "sources")


def build(evidence):
    return build_research_presentation(
        *evidence, generated_at_utc=NOW, builder_source_sha="c" * 40
    )


def rewrite(path, transform):
    doc = json.loads(path.read_bytes())
    transform(doc)
    raw = canonical_snapshot_bytes(doc) + b"\n"
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def readmission(evidence, *, diagnostic=False):
    selection, run, diag = evidence
    path = diag if diagnostic else run / "manifest.json"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rewrite(
        selection,
        lambda s: s.update(
            {"diagnostic_sha256" if diagnostic else "manifest_sha256": digest}
        ),
    )


def test_deterministic_source_values_provenance_and_no_mutation(evidence):
    selection, run, diag = evidence
    before = {
        p: p.read_bytes()
        for root in (run, diag.parent, selection.parent)
        for p in root.rglob("*")
        if p.is_file()
    }
    doc = build(evidence)
    assert doc == build(evidence)
    assert validate_research_lab_snapshot(doc)
    diagnostic = json.loads(diag.read_bytes())
    assert doc["population"]["n"] == 3
    assert doc["population"]["statistical_strength"] == "LOW_SAMPLE"
    assert (
        doc["performance"][0]["value"] == diagnostic["summary"]["net_realized_pnl_usd"]
    )
    assert (
        doc["costs"][0]["value"] == diagnostic["summary"]["closed_population_fees_usd"]
    )
    assert (
        doc["risk_stability"][0]["metric_name"]
        == "realized_close_to_close_max_drawdown"
    )
    assert doc["risk_stability"][1]["value"] is None
    assert all(p.read_bytes() == raw for p, raw in before.items())
    for artifact, path in zip(
        doc["provenance"]["source_artifacts"],
        (
            selection,
            run / "manifest.json",
            run / "metrics.json",
            run / "terminal_state.json",
            diag,
        ),
        strict=True,
    ):
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert "trade_attribution" not in canonical_snapshot_bytes(doc).decode()
    assert any("Candidate catalog NOT_AVAILABLE" in x for x in doc["limitations"])


def test_without_diagnostic_does_not_fabricate_fees_or_pnl(tmp_path):
    evidence = prepare_evidence(tmp_path / "sources", diagnostic=False)
    doc = build(evidence)
    assert doc["provenance"]["primary_context"]["diagnostic_run_id"] is None
    assert doc["costs"] == doc["attribution"] == []
    assert all(m["metric_name"] != "net_realized_pnl_usd" for m in doc["performance"])
    assert any("Diagnostic NOT_AVAILABLE" in s for s in doc["limitations"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("admission", "PENDING"),
        ("manifest_sha256", "0" * 64),
        ("research_run_id", "0" * 64),
        ("diagnostic_sha256", None),
        ("certification_ref", ""),
        ("schema_version", "unknown"),
    ],
)
def test_selection_fail_closed(evidence, field, value):
    rewrite(evidence[0], lambda d: d.update({field: value}))
    with pytest.raises(ResearchPublicationError):
        build(evidence)


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset_id", "0" * 64),
        ("source_boundary_id", "0" * 64),
        ("paper_epoch_id", "OTHER"),
        ("upstream_research_run_id", "0" * 64),
        ("diagnostic_config_hash", "0" * 64),
    ],
)
def test_diagnostic_context_fail_closed_even_when_hash_readmitted(
    evidence, field, value
):
    rewrite(evidence[2], lambda d: d.update({field: value}))
    readmission(evidence, diagnostic=True)
    with pytest.raises(ResearchPublicationError):
        build(evidence)


@pytest.mark.parametrize(
    "field,value",
    [
        ("n", 2),
        ("n", True),
        ("pnl_reconciliation", "FAIL"),
        ("fee_reconciliation", "FAIL"),
        ("evidence_status", "PARTIAL"),
        ("statistical_strength", "ADEQUATE"),
    ],
)
def test_diagnostic_summary_fail_closed(evidence, field, value):
    rewrite(evidence[2], lambda d: d["summary"].update({field: value}))
    readmission(evidence, diagnostic=True)
    with pytest.raises(ResearchPublicationError):
        build(evidence)


def test_corrupt_component_fails_before_atomic_replace(evidence, tmp_path):
    target = tmp_path / "presentation" / "snapshot.json"
    publish_research_presentation(
        target, *evidence, generated_at_utc=NOW, builder_source_sha="c" * 40
    )
    previous = target.read_bytes()
    (evidence[1] / "metrics.json").write_text("{}")
    with pytest.raises(ResearchPublicationError):
        publish_research_presentation(
            target, *evidence, generated_at_utc=NOW, builder_source_sha="c" * 40
        )
    assert target.read_bytes() == previous
    assert not list(target.parent.glob("*.tmp"))


def test_reject_output_overlap_and_symlink(evidence, tmp_path):
    for target in (evidence[0], evidence[1] / "manifest.json", evidence[2]):
        previous = target.read_bytes()
        with pytest.raises(ResearchPublicationError):
            publish_research_presentation(
                target, *evidence, generated_at_utc=NOW, builder_source_sha="c" * 40
            )
        assert target.read_bytes() == previous
    target = tmp_path / "alias.json"
    target.symlink_to(evidence[0])
    with pytest.raises(ResearchPublicationError):
        publish_research_presentation(
            target, *evidence, generated_at_utc=NOW, builder_source_sha="c" * 40
        )


@pytest.mark.parametrize(
    "raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b"[]", b"\xff"]
)
def test_strict_json(tmp_path, raw):
    p = tmp_path / "file.json"
    p.write_bytes(raw)
    with pytest.raises((EvidenceReadError, ValueError, UnicodeError)):
        read_evidence(p)


def test_read_bounds_symlink_fifo(tmp_path):
    p = tmp_path / "file.json"
    p.write_bytes(b'{"x":"123456"}')
    with pytest.raises(EvidenceReadError):
        read_evidence(p, limit=4)
    link = tmp_path / "link.json"
    link.symlink_to(p)
    with pytest.raises(EvidenceReadError):
        read_evidence(link)
    import os

    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(EvidenceReadError):
        read_evidence(fifo)


def test_invalid_enum_structures_return_false(evidence):
    doc = build(evidence)
    for field in ("research_state", "authority"):
        malformed = copy.deepcopy(doc)
        malformed[field] = []
        assert not validate_research_lab_snapshot(malformed)
    doc["performance"][0]["source_ref"] = {}
    assert not validate_research_lab_snapshot(doc)


def test_real_api_reads_presentation_only_and_fails_closed(evidence, tmp_path):
    target = tmp_path / "presentation" / "snapshot.json"
    publish_research_presentation(
        target, *evidence, generated_at_utc=NOW, builder_source_sha="c" * 40
    )
    previous = api_app.get_research_lab_reader()
    api_app._research_lab_reader = ResearchLabSnapshotReader(target)
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/research-lab")
            assert response.status_code == 200 and response.json() == build(evidence)
            # Removing raw Research evidence cannot affect this GET.
            evidence[0].unlink()
            assert client.get("/api/operator/v1/research-lab").status_code == 200
            target.write_text('{"research_state": [], "research_state": "AVAILABLE"}')
            assert client.get("/api/operator/v1/research-lab").status_code == 503
            assert client.post("/api/operator/v1/research-lab").status_code == 405
    finally:
        api_app._research_lab_reader = previous


def test_cli_explicit_inputs(evidence, tmp_path):
    target = tmp_path / "presentation" / "snapshot.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "observability.research_publication_builder",
            "--selection",
            str(evidence[0]),
            "--run",
            str(evidence[1]),
            "--diagnostic",
            str(evidence[2]),
            "--output",
            str(target),
            "--generated-at-utc",
            NOW,
            "--builder-source-sha",
            "c" * 40,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "RESEARCH_PRESENTATION_SHA256=" in result.stdout
    assert json.loads(target.read_bytes()) == build(evidence)


def test_production_imports_do_not_load_engines():
    script = "import sys; import observability.research_publication_builder; assert not any(x.startswith(('research_replay', 'research_diag', 'paper_trading', 'core.decision_packet', 'ccxt')) for x in sys.modules)"
    assert (
        subprocess.run([sys.executable, "-c", script], capture_output=True).returncode
        == 0
    )


def replace_metrics(evidence, transform):
    metrics_path = evidence[1] / "metrics.json"
    digest = rewrite(metrics_path, transform)
    metrics = json.loads(metrics_path.read_bytes())

    def update_manifest(doc):
        doc["metrics"] = metrics
        doc["components"]["metrics"]["sha256"] = digest
        doc["components"]["metrics"]["bytes"] = metrics_path.stat().st_size

    rewrite(evidence[1] / "manifest.json", update_manifest)
    readmission(evidence)


@pytest.mark.parametrize("status", ["POSITIVE_INFINITY", "UNDEFINED_ZERO_DENOMINATOR"])
def test_non_finite_profit_factor_stays_unavailable(evidence, status):
    replace_metrics(
        evidence, lambda d: d["profit_factor"].update({"status": status, "value": None})
    )
    metric = next(
        m for m in build(evidence)["performance"] if m["metric_name"] == "profit_factor"
    )
    assert metric["value"] is None and metric["evidence_status"] == "NOT_AVAILABLE"
    assert status in metric["reason"]


@pytest.mark.parametrize("value", [True, None, "1", 10**400])
def test_complete_metric_requires_finite_number(evidence, value):
    replace_metrics(evidence, lambda d: d["win_rate"].update({"value": value}))
    with pytest.raises(ResearchPublicationError):
        build(evidence)


def test_real_zero_preserved(evidence):
    replace_metrics(evidence, lambda d: d["expectancy_usd"].update({"value": 0}))
    metric = next(
        m
        for m in build(evidence)["performance"]
        if m["metric_name"] == "expectancy_usd"
    )
    assert metric["value"] == 0 and metric["evidence_status"] == "COMPLETE"


def test_empty_publication(tmp_path):
    from dataclasses import replace
    from research_replay.publication import publish_factual_result
    from tests.research_replay.test_rl_replay_01_publication import _result

    result = _result()
    identity = copy.deepcopy(result.research_run_identity)
    identity["population"]["closed_trade_count"] = 0
    metrics = copy.deepcopy(result.metrics)
    metrics["closed_trade_count"] = 0
    for metric in metrics.values():
        if isinstance(metric, dict) and "n" in metric:
            metric.update({"n": 0, "status": "NOT_AVAILABLE", "value": None})
    terminal = {**result.terminal_state, "closed_trade_count": 0}
    run_id = hashlib.sha256(canonical_snapshot_bytes(identity)).hexdigest()
    result = replace(
        result,
        research_run_id=run_id,
        research_run_identity=identity,
        metrics=metrics,
        terminal_state=terminal,
        lifecycle=(),
    )
    published = publish_factual_result(
        result, output_root=tmp_path / "sources", generated_at_utc=NOW
    )
    selection = tmp_path / "selection.json"
    from observability.research_publication_builder import SELECTION_SCHEMA

    selection.write_bytes(
        canonical_snapshot_bytes(
            {
                "schema_version": SELECTION_SCHEMA,
                "admission": "CERTIFIED",
                "certification_ref": "synthetic-test-only:empty",
                "research_run_id": run_id,
                "manifest_sha256": hashlib.sha256(
                    (published.run_path / "manifest.json").read_bytes()
                ).hexdigest(),
                "diagnostic_run_id": None,
                "diagnostic_sha256": None,
            }
        )
    )
    doc = build((selection, published.run_path, None))
    assert doc["research_state"] == "EMPTY" and doc["population"]["n"] == 0
    assert (
        doc["performance"]
        == doc["costs"]
        == doc["risk_stability"]
        == doc["attribution"]
        == []
    )


def test_identical_fixture_sources_produce_identical_presentation(tmp_path):
    first = prepare_evidence(tmp_path / "one")
    second = prepare_evidence(tmp_path / "two")
    assert build(first) == build(second)


def test_reader_rejects_oversized_presentation(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_bytes(b" " * (1024 * 1024 + 1))
    result = ResearchLabSnapshotReader(path).read()
    assert not result.ok


def test_output_size_bound(evidence):
    rewrite(evidence[0], lambda d: d.update({"certification_ref": "x" * 513}))
    with pytest.raises(ResearchPublicationError):
        build(evidence)


def test_presentation_size_bound(evidence):
    rewrite(
        evidence[2],
        lambda d: d["limitations"].update(
            {"oversized": {"status": "NOT_AVAILABLE", "reason": "x" * (600 * 1024)}}
        ),
    )
    readmission(evidence, diagnostic=True)
    with pytest.raises(ResearchPublicationError):
        build(evidence)


@pytest.mark.parametrize(
    "field,value",
    [("closed_trade_count", 3.0), ("decision_packet_component_sha256", "invalid")],
)
def test_diagnostic_identity_profile_even_when_readmitted(evidence, field, value):
    def mutate(diag):
        diag["diagnostic_run_identity"]["population"][field] = value
        diag["diagnostic_run_id"] = hashlib.sha256(
            canonical_snapshot_bytes(diag["diagnostic_run_identity"])
        ).hexdigest()

    rewrite(evidence[2], mutate)
    diag = json.loads(evidence[2].read_bytes())
    rewrite(
        evidence[0],
        lambda s: s.update({"diagnostic_run_id": diag["diagnostic_run_id"]}),
    )
    readmission(evidence, diagnostic=True)
    with pytest.raises(ResearchPublicationError):
        build(evidence)
