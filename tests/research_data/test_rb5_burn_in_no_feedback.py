"""RB4/RB5 integrated proof over isolated synthetic burn-in sources only."""

from __future__ import annotations

import copy
import hashlib
import os
import subprocess
import sys
from dataclasses import replace

import pytest

from research_candidate import (
    RegistryError,
    canonical_json_bytes,
    compute_candidate_id,
    compute_candidate_config_hash,
    compute_promotion_request_id,
    dataset_requirement_id,
    validate_promotion_request,
)
from research_data.burn_in_finalization import (
    BurnInDatasetValidationError,
    BurnInQuiescence,
    BurnInQuiescenceError,
    FinalDesignationExistsError,
    designate_final_burn_in_dataset,
)
from research_data.burn_in_research import BurnInResearchWorkspace
from research_data.paper_exporter import export_paper_dataset
from research_replay.factual import DatasetValidationError, replay_factual_dataset
from tests.research_candidate import test_rl_candidate_01_registry as candidates
from tests.research_data import test_rl_data_01_exporter as fixtures
from tests.research_diag import test_rl_diag_01_factual as diagnostics

SHA = "a" * 40
WHEN = "2026-09-26T05:00:00Z"
MATERIAL_CONFIG = {"PB_MAX_POSITIONS": {"value": "2", "value_type": "int"}}


def _capture(tmp_path, monkeypatch, *, packets=True):
    monkeypatch.setattr(fixtures, "EPOCH", "BURN-IN-SYNTHETIC-RB5")
    files = fixtures._fixture(tmp_path / "paper")
    fixtures._promote_fixture_identity_to_burn_in(files)
    packet = diagnostics._packet_rows()[0]
    packet["metadata"]["trace_id"] = "trace-1"
    packet["created_cycle_id"] = "7"
    fixtures._write_jsonl(files["packets_path"], [packet])
    request = fixtures._request(files, tmp_path / "capture")
    if not packets:
        request = replace(request, decision_packet_paths=(), decision_identity_journal_path=None)
    return files, export_paper_dataset(request)


def _candidate(capture, replay, diag):
    candidate = candidates._candidate()
    candidate["parents"] = {
        "dataset_ids": [capture.dataset_id],
        "source_boundary_ids": [capture.source_boundary_id],
        "research_run_ids": [replay.research_run_id],
        "diagnostic_run_ids": [diag.diagnostic_run_id],
        "paper_epoch_ids": [capture.manifest["paper_epoch_id"]],
    }
    candidate["baseline"].update(
        paper_epoch_id=capture.manifest["paper_epoch_id"],
        baseline_population_definition="SYNTHETIC_BURN_IN_CLOSED",
        source_code_sha=capture.manifest["source_boundary_identity"]["experiment_runtime_source_sha"],
        config_hash=capture.manifest["source_boundary_identity"]["experiment_config_snapshot_sha256"],
    )
    candidate["proposal"]["components"] = [{
        "kind": "CONFIG_SET", "path": "PB_MAX_POSITIONS", "old_value": "2",
        "new_value": "3", "value_type": "int", "materiality": "SIZING",
    }]
    candidate["candidate_config_hash"] = compute_candidate_config_hash(MATERIAL_CONFIG, candidate["proposal"])
    requirements = candidate["evaluation_plan"]["dataset_requirements"]
    for requirement in requirements:
        if requirement["kind"] == "EXACT_DATASET":
            requirement.update(
                dataset_id=capture.dataset_id, source_boundary_id=capture.source_boundary_id
            )
            requirement["requirement_id"] = dataset_requirement_id(requirement)
        else:
            requirement["required_source_config_binding"]["candidate_config_hash"] = candidate["candidate_config_hash"]
            requirement["requirement_id"] = dataset_requirement_id(requirement)
    requirements.sort(key=canonical_json_bytes)
    candidate["evaluation_plan"]["data_reuse_policy"]["discovery_dataset_ids"] = [capture.dataset_id]
    candidate["candidate_id"] = compute_candidate_id(candidate)
    return candidate


def test_burn_in_replay_diagnostics_candidate_and_future_epoch_boundary(tmp_path, monkeypatch):
    files, capture = _capture(tmp_path, monkeypatch)
    paper_before = fixtures._tree_bytes(files["source"])
    capture_before = fixtures._tree_bytes(capture.dataset_path)
    a = BurnInResearchWorkspace(capture.dataset_path, tmp_path / "research-a", (files["source"],))
    b = BurnInResearchWorkspace(capture.dataset_path, tmp_path / "research-b", (files["source"],))
    r1, d1, p1 = a.replay_and_diagnose(code_sha=SHA, generated_at_utc=WHEN)
    r2, d2, p2 = b.replay_and_diagnose(code_sha=SHA, generated_at_utc="2026-09-27T05:00:00Z")
    assert r1.research_run_id == r2.research_run_id
    assert r1.metrics == r2.metrics
    assert d1.as_dict() == d2.as_dict()
    assert p1.manifest["components"] == p2.manifest["components"]
    assert p1.manifest["publication_provenance"] != p2.manifest["publication_provenance"]
    for name in ("lifecycle.jsonl", "metrics.json", "terminal_state.json"):
        assert (p1.run_path / name).read_bytes() == (p2.run_path / name).read_bytes()
    assert r1.metrics["sharpe"]["status"] == "NOT_AVAILABLE"
    assert replay_factual_dataset(capture.dataset_path, replay_code_sha="b" * 40).research_run_id != r1.research_run_id
    assert replay_factual_dataset(capture.dataset_path, replay_code_sha=SHA, replay_config={"version": "OTHER"}).research_run_id != r1.research_run_id

    candidate = _candidate(capture, r1, d1)
    catalog = {key: set(value) for key, value in candidate["parents"].items()}
    published = a.publish_candidate(
        candidate, evidence_catalog=catalog, baseline_material_config=MATERIAL_CONFIG
    )
    assert published.path.is_relative_to(a.output_root)
    request = candidates._promotion_request(candidate)
    request["baseline_epoch"] = capture.manifest["paper_epoch_id"]
    request["target_source_sha"] = candidate["baseline"]["source_code_sha"]
    request["promotion_request_id"] = compute_promotion_request_id(request)
    assert validate_promotion_request(
        request, candidate=candidate, candidate_state="QUALIFIED",
        baseline_material_config=MATERIAL_CONFIG,
    ) == request["promotion_request_id"]
    same_epoch = copy.deepcopy(request)
    same_epoch["requested_new_epoch"]["paper_epoch_id"] = request["baseline_epoch"]
    same_epoch["promotion_request_id"] = compute_promotion_request_id(same_epoch)
    with pytest.raises(RegistryError, match="new PAPER epoch"):
        validate_promotion_request(
            same_epoch, candidate=candidate, candidate_state="QUALIFIED",
            baseline_material_config=MATERIAL_CONFIG,
        )
    for status in ("AUTHORIZED", "EXECUTED"):
        with pytest.raises(RegistryError, match="cannot record AUTHORIZED or EXECUTED"):
            validate_promotion_request(
                {**request, "status": status}, candidate=candidate, candidate_state="QUALIFIED",
                baseline_material_config=MATERIAL_CONFIG,
            )
    final = designate_final_burn_in_dataset(
        dataset_path=capture.dataset_path, designation_root=tmp_path / "final",
        quiescence=BurnInQuiescence(True, 0, 0), designated_at_utc=WHEN,
        protected_roots=(files["source"],),
    )
    assert final.document["designation"] == "FINAL_BURN_IN_DATASET"
    assert "F00" not in d1.limitations["packet_os_size_usd"]["reason"]
    bad_candidate = copy.deepcopy(candidate)
    bad_candidate["baseline"]["config_hash"] = "f" * 64
    bad_candidate["candidate_id"] = compute_candidate_id(bad_candidate)
    with pytest.raises(BurnInDatasetValidationError, match="bind to this burn-in"):
        a.publish_candidate(bad_candidate, evidence_catalog=catalog, baseline_material_config=MATERIAL_CONFIG)
    assert fixtures._tree_bytes(files["source"]) == paper_before
    assert fixtures._tree_bytes(capture.dataset_path) == capture_before


@pytest.mark.parametrize("target", ["paper", "dataset", "symlink", "nested_symlink", "undeclared"])
def test_workspace_rejects_unsafe_research_destinations(tmp_path, monkeypatch, target):
    files, capture = _capture(tmp_path, monkeypatch)
    before = fixtures._tree_bytes(files["source"])
    root = tmp_path / "output"
    protected = (files["source"],)
    if target == "paper":
        root = files["source"] / "results"
    elif target == "dataset":
        root = capture.dataset_path / "results"
    elif target == "symlink":
        root.symlink_to(files["source"], target_is_directory=True)
    elif target == "nested_symlink":
        root.mkdir()
        (root / "runs").symlink_to(files["source"], target_is_directory=True)
    else:
        protected = ()
    workspace = BurnInResearchWorkspace(capture.dataset_path, root, protected)
    with pytest.raises(BurnInDatasetValidationError):
        workspace.replay_and_diagnose(code_sha=SHA, generated_at_utc=WHEN)
    assert fixtures._tree_bytes(files["source"]) == before


@pytest.mark.parametrize("stopped,pending,inflight", [("false", 0, 0), (1, 0, 0), (True, False, 0), (True, -1, 0), (True, 0, 0.0)])
def test_quiescence_evidence_requires_exact_types(stopped, pending, inflight):
    with pytest.raises(BurnInQuiescenceError):
        BurnInQuiescence(stopped, pending, inflight)


def test_final_designation_cannot_supersede_an_epoch_with_a_later_capture(tmp_path, monkeypatch):
    files, capture = _capture(tmp_path, monkeypatch, packets=False)
    kwargs = dict(designation_root=tmp_path / "final", quiescence=BurnInQuiescence(True, 0, 0), designated_at_utc=WHEN)
    first = designate_final_burn_in_dataset(dataset_path=capture.dataset_path, **kwargs)
    before = first.designation_path.read_bytes()
    fixtures._append_closed_lifecycle(files)
    later = export_paper_dataset(fixtures._burn_in_capture_request(files, tmp_path / "later", extracted_at=WHEN))
    with pytest.raises(FinalDesignationExistsError):
        designate_final_burn_in_dataset(dataset_path=later.dataset_path, **kwargs)
    assert first.designation_path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("ppl_birth_code_sha", "f" * 40), ("experiment_runtime_source_sha", "f" * 40), ("ppl_semantic_config_snapshot_hash", "f" * 64)])
def test_rehashed_false_provenance_cannot_be_finalized_or_replayed(tmp_path, monkeypatch, field, value):
    _, capture = _capture(tmp_path, monkeypatch)
    manifest = copy.deepcopy(capture.manifest)
    manifest["source_boundary_identity"][field] = value
    boundary = hashlib.sha256(fixtures._canonical(manifest["source_boundary_identity"])).hexdigest()
    manifest["source_boundary_id"] = boundary
    manifest["dataset_identity"]["source_boundary_id"] = boundary
    manifest["dataset_identity"]["components"][0]["source_boundary_id"] = boundary
    manifest["dataset_id"] = hashlib.sha256(fixtures._canonical(manifest["dataset_identity"])).hexdigest()
    renamed = capture.dataset_path.with_name(manifest["dataset_id"])
    capture.dataset_path.rename(renamed)
    fixtures._write_json(renamed / "manifest.json", manifest)
    with pytest.raises(DatasetValidationError, match="fingerprint mismatch"):
        replay_factual_dataset(renamed, replay_code_sha=SHA)


def test_test_process_does_not_rewrite_external_decision_identity_journal(tmp_path):
    sentinel = tmp_path / "runtime" / "decision_identity.jsonl"
    sentinel.parent.mkdir()
    sentinel.write_bytes(b'{"evidence":"synthetic immutable external journal"}\n')
    before = sentinel.read_bytes()
    env = {**os.environ, "DECISION_IDENTITY_JOURNAL_PATH": str(sentinel)}
    probe = """
import conftest, os
from pathlib import Path
p = Path(os.environ['DECISION_IDENTITY_JOURNAL_PATH'])
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text('isolated test write')
print(p)
"""
    result = subprocess.run([sys.executable, "-c", probe], env=env, check=True, capture_output=True, text=True)
    assert str(sentinel) != result.stdout.strip()
    assert sentinel.read_bytes() == before


def test_burn_in_diagnostics_do_not_invent_missing_decision_evidence(tmp_path, monkeypatch):
    from research_diag import DiagnosticError

    files, capture = _capture(tmp_path, monkeypatch, packets=False)
    output = tmp_path / "research"
    workspace = BurnInResearchWorkspace(capture.dataset_path, output, (files["source"],))
    with pytest.raises(DiagnosticError, match="must be COMPLETE"):
        workspace.replay_and_diagnose(code_sha=SHA, generated_at_utc=WHEN)
    assert not output.exists()


def test_finalizer_rejects_nested_output_symlink(tmp_path, monkeypatch):
    from research_data.burn_in_finalization import BurnInFinalizationError

    files, capture = _capture(tmp_path, monkeypatch)
    before = fixtures._tree_bytes(files["source"])
    output = tmp_path / "final"
    output.mkdir()
    (output / "finalizations").symlink_to(files["source"], target_is_directory=True)
    with pytest.raises(BurnInFinalizationError, match="symlink"):
        designate_final_burn_in_dataset(
            dataset_path=capture.dataset_path, designation_root=output,
            quiescence=BurnInQuiescence(True, 0, 0), designated_at_utc=WHEN,
            protected_roots=(files["source"],),
        )
    assert fixtures._tree_bytes(files["source"]) == before
