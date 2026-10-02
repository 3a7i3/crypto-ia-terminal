"""Source-only admission and presentation boundary, with synthetic evidence."""

import hashlib
import json
import shutil

import pytest
from fastapi.testclient import TestClient
from observability.operator_api import app as api_app
from observability.operator_api.research_strategy_board_reader import (
    ResearchStrategyBoardReader,
)
from observability.research_strategy_board_builder import (
    StrategyBoardError,
    build_strategy_board,
    publish_strategy_board,
)
from observability.research_strategy_board_contract import validate_strategy_board
from tests.cross_stack.generate_strategy_board_fixture import (
    NOW,
    generate_strategy_board_fixture,
    prepare_strategy_evidence,
)

KWARGS = {"generated_at_utc": NOW, "builder_source_sha": "d" * 40}


@pytest.fixture
def admitted(tmp_path):
    selection, evidence = prepare_strategy_evidence(tmp_path)
    return selection, evidence


def source_bytes(root):
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_deterministic_exact_metrics_sources_immutable(admitted):
    selection, evidence = admitted
    before = source_bytes(evidence)
    doc = build_strategy_board(selection, evidence, **KWARGS)
    assert doc == build_strategy_board(selection, evidence, **KWARGS)
    assert validate_strategy_board(doc)
    assert before == source_bytes(evidence)
    for row in doc["rows"]:
        if row["evaluation"]:
            selected = next(
                x
                for x in json.loads(selection.read_text())["candidates"]
                if x["candidate_id"] == row["candidate_id"]
            )
            metric = json.loads(
                (evidence / selected["evaluation"]["path"]).read_text()
            )["metrics"][0]
            assert row["evaluation"]["metrics"][0] == {
                k: v
                for k, v in metric.items()
                if k not in ("dataset_id", "population_definition")
            }


def test_positive_pnl_without_assessment_never_infers_green_or_rank(admitted):
    doc = build_strategy_board(*admitted, **KWARGS)
    row = next(r for r in doc["rows"] if r["label"].startswith("PnL seul"))
    assert row["evaluation"]["metrics"][0]["value"] > 0
    assert {c["status"] for c in row["criteria"]} == {"NOT_AVAILABLE"}
    assert row["ranking"] is row["assessment_policy_id"] is None
    row = next(r for r in doc["rows"] if r["label"].startswith("Hypothèse"))
    assert row["evaluation"] is None


@pytest.mark.parametrize(
    "key,value", [("admission", "PENDING"), ("certification_ref", ""), ("extra", True)]
)
def test_selection_fail_closed(admitted, key, value):
    selection, evidence = admitted
    doc = json.loads(selection.read_text())
    doc[key] = value
    selection.write_text(json.dumps(doc))
    with pytest.raises(StrategyBoardError):
        build_strategy_board(selection, evidence, **KWARGS)


@pytest.mark.parametrize(
    "attack",
    [
        "bytes",
        "digest",
        "escape",
        "absolute",
        "symlink",
        "identity",
        "assessment_binding",
        "delta",
    ],
)
def test_evidence_tampering_rejected(admitted, attack, tmp_path):
    selection, evidence = admitted
    selected = json.loads(selection.read_text())
    row = selected["candidates"][0]
    ref = row["candidate"]
    path = evidence / ref["path"]
    if attack == "bytes":
        path.write_bytes(path.read_bytes() + b" ")
    elif attack == "digest":
        ref["sha256"] = "f" * 64
    elif attack == "escape":
        ref["path"] = "../outside.json"
    elif attack == "absolute":
        ref["path"] = str(path.absolute())
    elif attack == "symlink":
        other = tmp_path / "outside.json"
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
    else:
        ref = row["assessment"] if attack == "assessment_binding" else row["evaluation"]
        path = evidence / ref["path"]
        doc = json.loads(path.read_text())
        if attack == "assessment_binding":
            doc["evaluation_run_id"] = "e" * 64
        elif attack == "identity":
            doc["evaluation_run_identity"]["dataset_id"] = "e" * 64
        else:
            doc["metrics"][0]["delta"] = 999
        path.write_text(json.dumps(doc))
        ref["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    selection.write_text(json.dumps(selected))
    with pytest.raises(StrategyBoardError):
        build_strategy_board(selection, evidence, **KWARGS)


@pytest.mark.parametrize(
    "attack",
    [
        "unknown",
        "nonfinite",
        "unsafe_n",
        "missing_metric",
        "rank_duplicate",
        "rank_hash",
        "cohort_code",
        "cohort_baseline",
        "false_available",
        "fabricated_pass",
        "source_missing",
        "zero_population_verdict",
        "metric_semantics",
        "artifact_type",
    ],
)
def test_closed_reader_contract_rejects_misleading_board(admitted, attack):
    doc = build_strategy_board(*admitted, **KWARGS)
    ranked = [r for r in doc["rows"] if r["ranking"]]
    r = ranked[0]
    if attack == "unknown":
        r["criteria"][0]["status"] = "WINNER"
    elif attack == "nonfinite":
        r["evaluation"]["metrics"][0]["value"] = float("nan")
    elif attack == "unsafe_n":
        r["evaluation"]["metrics"][0]["n"] = 2**53
    elif attack == "missing_metric":
        r["criteria"][0]["metric_refs"] = ["not_published"]
    elif attack == "rank_duplicate":
        ranked[1]["ranking"]["position"] = r["ranking"]["position"]
    elif attack == "rank_hash":
        r["ranking"]["group_id"] = "e" * 64
    elif attack == "cohort_code":
        r["evaluation"]["source_code_sha"] = "e" * 40
    elif attack == "cohort_baseline":
        r["evaluation"]["baseline_id"] = "e" * 64
    elif attack == "false_available":
        doc["catalog_state"] = "EMPTY"
    elif attack == "fabricated_pass":
        r = next(x for x in doc["rows"] if x["evaluation"] is None)
        r["criteria"][0]["status"] = "PASS"
    elif attack == "zero_population_verdict":
        r["evaluation"]["metrics"][0]["n"] = 0
        r["ranking"] = None
    elif attack == "metric_semantics":
        r["evaluation"]["metrics"][0]["metric_semantics_version"] = "CHANGED"
    elif attack == "artifact_type":
        doc["source_artifacts"][0]["artifact_type"] = "UNADMITTED_SELECTION"
    else:
        doc["source_artifacts"] = doc["source_artifacts"][:1]
    assert not validate_strategy_board(doc)


def test_explicit_empty_is_not_missing_or_global_empty(admitted):
    selection, evidence = admitted
    doc = json.loads(selection.read_text())
    doc["candidates"] = []
    selection.write_text(json.dumps(doc))
    result = build_strategy_board(selection, evidence, **KWARGS)
    assert result["catalog_state"] == "EMPTY" and result["rows"] == []


def test_failed_publication_preserves_existing_target(admitted, tmp_path):
    selection, evidence = admitted
    target = tmp_path / "presentation" / "board.json"
    publish_strategy_board(target, selection, evidence, **KWARGS)
    before = target.read_bytes()
    selection.write_text("{}")
    with pytest.raises(StrategyBoardError):
        publish_strategy_board(target, selection, evidence, **KWARGS)
    assert target.read_bytes() == before


@pytest.mark.parametrize("location", ["source", "admission", "symlink"])
def test_output_cannot_replace_source_or_follow_symlink(admitted, tmp_path, location):
    selection, evidence = admitted
    target = (
        evidence / "board.json"
        if location == "source"
        else selection.parent / "board.json"
    )
    if location == "symlink":
        target = tmp_path / "linked"
        target.symlink_to(selection)
    with pytest.raises(StrategyBoardError):
        publish_strategy_board(target, selection, evidence, **KWARGS)


def test_real_producer_reader_api_chain(tmp_path):
    result = generate_strategy_board_fixture(tmp_path)
    assert result["http_status"] == 200
    assert validate_strategy_board(result["body"])


def test_financial_clarity_uses_actual_producer_for_nonzero_tiny_delta(tmp_path):
    from tests.cross_stack.generate_financial_clarity_fixture import (
        generate_financial_clarity_fixture,
    )

    result = generate_financial_clarity_fixture(tmp_path)
    assert result["http_status"] == 200
    assert (
        result["body"]["reconciliation"]["unreconciled_capital"]
        == "0.0000000000224174531618"
    )


def test_api_only_reads_presentation_and_missing_is_503(
    admitted, tmp_path, monkeypatch
):
    selection, evidence = admitted
    target = tmp_path / "presentation" / "board.json"
    publish_strategy_board(target, selection, evidence, **KWARGS)
    shutil.rmtree(evidence)
    selection.unlink()
    monkeypatch.setattr(
        api_app, "_research_strategy_board_reader", ResearchStrategyBoardReader(target)
    )
    with TestClient(api_app.app) as client:
        assert client.get("/api/operator/v1/research-strategies").status_code == 200
        assert client.post("/api/operator/v1/research-strategies").status_code == 405
        target.unlink()
        response = client.get("/api/operator/v1/research-strategies")
        assert response.status_code == 503
        assert response.json() == {"error_code": "RESEARCH_STRATEGY_BOARD_MISSING"}


@pytest.mark.parametrize(
    "payload", [b'{"x":1,"x":2}', b'{"x":NaN}', b"x" * (1024 * 1024 + 1), b"{}"]
)
def test_bad_artifact_never_becomes_empty_success(tmp_path, payload):
    path = tmp_path / "board.json"
    path.write_bytes(payload)
    result = ResearchStrategyBoardReader(path).read()
    assert not result.ok and result.snapshot is None
