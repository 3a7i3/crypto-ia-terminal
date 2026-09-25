from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research_replay.factual import FactualReplayResult, LifecycleRecord
from research_replay.publication import (
    PublicationError,
    RunExistsError,
    build_publication_payload,
    publish_factual_result,
)


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _result() -> FactualReplayResult:
    identity = {
        "identity_schema": "rl-replay-01.run-identity.v1",
        "run_kind": "FACTUAL_BASELINE",
        "dataset_id": "a" * 64,
        "source_boundary_id": "b" * 64,
        "paper_epoch_id": "TEST-EPOCH",
        "research_replay_code_sha": "c" * 40,
        "replay_method": "PPL_PROJECT_FACTUAL_V1",
        "replay_config_hash": "d" * 64,
        "population": {
            "component": "ppl_events",
            "event_count": 3,
            "first_sequence": 1,
            "last_sequence": 3,
            "closed_trade_count": 1,
        },
        "source_experiment_identity": {
            "ppl_birth_code_sha": "e" * 40,
            "ppl_semantic_config_snapshot_hash": "f" * 64,
            "experiment_config_file_sha256": "1" * 64,
            "experiment_config_snapshot_sha256": "2" * 64,
            "experiment_runtime_source_sha": "3" * 40,
            "ppl_stream_sha256": "4" * 64,
        },
        "candidate_config_hash": None,
        "counterfactual_spec_digest": None,
    }
    run_id = _sha(_canonical(identity))
    lifecycle = (
        LifecycleRecord(
            trade_id="T1",
            symbol="BTC/USDT",
            side="LONG",
            principal=100.0,
            open_event_id="event-2",
            open_sequence=2,
            opened_at=2.0,
            decision_id="packet-1",
            entry_price=100.0,
            entry_fee=0.1,
            resolution_status="CLOSED",
            resolution_event_id="event-3",
            resolution_sequence=3,
            resolved_at=3.0,
            exit_price=101.0,
            exit_fee=0.1,
            gross_pnl=1.0,
            net_realized_pnl=0.8,
            unresolved_reason=None,
        ),
    )
    terminal = {
        "paper_epoch_id": "TEST-EPOCH",
        "initial_virtual_capital": 1000.0,
        "source_event_count": 3,
        "last_source_sequence": 3,
        "available_cash": 1000.8,
        "reserved_principal": 0.0,
        "unresolved_capital": 0.0,
        "realized_pnl": 0.8,
        "fees_paid": 0.2,
        "open_position_count": 0,
        "closed_trade_count": 1,
        "unresolved_position_count": 0,
    }
    metrics = {
        "closed_trade_count": 1,
        "win_rate": {"status": "COMPLETE", "value": 1.0, "n": 1},
        "profit_factor": {"status": "POSITIVE_INFINITY", "value": None, "n": 1},
        "expectancy_usd": {"status": "COMPLETE", "value": 0.8, "n": 1},
        "realized_close_to_close_max_drawdown": {
            "status": "COMPLETE",
            "value": 0.0,
            "n": 1,
            "definition": "initial capital + cumulative closed-trade net realized PnL",
        },
        "mark_to_market_max_drawdown": {
            "status": "NOT_AVAILABLE",
            "value": None,
            "reason": "no certified mark trajectory",
        },
        "sharpe": {
            "status": "NOT_AVAILABLE",
            "value": None,
            "reason": "not defined",
        },
    }
    return FactualReplayResult(
        research_run_id=run_id,
        research_run_identity=identity,
        replay_config_hash="d" * 64,
        dataset_id="a" * 64,
        source_boundary_id="b" * 64,
        paper_epoch_id="TEST-EPOCH",
        terminal_state=terminal,
        lifecycle=lifecycle,
        metrics=metrics,
    )


def test_publication_payload_component_bytes_are_time_independent() -> None:
    result = _result()

    manifest_a, files_a = build_publication_payload(
        result,
        generated_at_utc="2026-09-25T00:00:00Z",
    )
    manifest_b, files_b = build_publication_payload(
        result,
        generated_at_utc="2026-09-25T01:00:00Z",
    )

    assert result.research_run_id == manifest_a["research_run_id"]
    assert result.research_run_id == manifest_b["research_run_id"]
    assert files_a["lifecycle.jsonl"] == files_b["lifecycle.jsonl"]
    assert files_a["terminal_state.json"] == files_b["terminal_state.json"]
    assert files_a["metrics.json"] == files_b["metrics.json"]
    assert files_a["manifest.json"] != files_b["manifest.json"]


def test_publication_writes_expected_immutable_layout(tmp_path: Path) -> None:
    result = _result()
    published = publish_factual_result(
        result,
        output_root=tmp_path,
        generated_at_utc="2026-09-25T00:00:00Z",
    )

    assert published.run_path == tmp_path / "runs" / result.research_run_id
    assert published.run_path.is_dir()

    expected_files = {
        "manifest.json",
        "lifecycle.jsonl",
        "terminal_state.json",
        "metrics.json",
    }
    assert {p.name for p in published.run_path.iterdir()} == expected_files

    manifest = json.loads(
        (published.run_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["research_run_id"] == result.research_run_id
    assert manifest["dataset_id"] == result.dataset_id
    assert manifest["source_boundary_id"] == result.source_boundary_id
    assert manifest["status"] == "COMPLETE"

    for logical, filename in (
        ("lifecycle", "lifecycle.jsonl"),
        ("terminal_state", "terminal_state.json"),
        ("metrics", "metrics.json"),
    ):
        raw = (published.run_path / filename).read_bytes()
        assert manifest["components"][logical]["sha256"] == _sha(raw)
        assert manifest["components"][logical]["bytes"] == len(raw)


def test_existing_run_is_never_overwritten(tmp_path: Path) -> None:
    result = _result()
    first = publish_factual_result(
        result,
        output_root=tmp_path,
        generated_at_utc="2026-09-25T00:00:00Z",
    )
    before = {
        p.name: p.read_bytes()
        for p in first.run_path.iterdir()
        if p.is_file()
    }

    with pytest.raises(RunExistsError, match="already exists"):
        publish_factual_result(
            result,
            output_root=tmp_path,
            generated_at_utc="2026-09-25T01:00:00Z",
        )

    after = {
        p.name: p.read_bytes()
        for p in first.run_path.iterdir()
        if p.is_file()
    }
    assert before == after


def test_tampered_research_run_id_is_rejected_before_publication(
    tmp_path: Path,
) -> None:
    result = _result()
    tampered = FactualReplayResult(
        research_run_id="0" * 64,
        research_run_identity=result.research_run_identity,
        replay_config_hash=result.replay_config_hash,
        dataset_id=result.dataset_id,
        source_boundary_id=result.source_boundary_id,
        paper_epoch_id=result.paper_epoch_id,
        terminal_state=result.terminal_state,
        lifecycle=result.lifecycle,
        metrics=result.metrics,
    )

    with pytest.raises(PublicationError, match="does not match"):
        publish_factual_result(
            tampered,
            output_root=tmp_path,
            generated_at_utc="2026-09-25T00:00:00Z",
        )

    runs = tmp_path / "runs"
    assert not runs.exists() or list(runs.iterdir()) == []


def test_manifest_records_explicit_counterfactual_limitation() -> None:
    result = _result()
    manifest, _ = build_publication_payload(
        result,
        generated_at_utc="2026-09-25T00:00:00Z",
    )

    limitation = manifest["limitations"]["general_strategy_counterfactual"]
    assert limitation["status"] == "NOT_AVAILABLE"
    assert "market trajectory" in limitation["reason"]
