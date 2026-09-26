from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

import pytest

from paper_trading.ledger_events import (
    LedgerEvent,
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
)
from research_replay.factual import (
    DatasetValidationError,
    ReplayError,
    replay_factual_dataset,
    validate_dataset,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


def _event_line(event: LedgerEvent) -> bytes:
    value = {
        "event_id": event.event_id,
        "paper_epoch_id": event.paper_epoch_id,
        "sequence": event.sequence,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "trade_id": event.trade_id,
        "decision_id": event.decision_id,
        "payload": _jsonable(event.payload),
        "schema_version": event.schema_version,
    }
    return _canonical(value) + b"\n"


def _open(
    *,
    seq: int,
    trade_id: str,
    side: str,
    entry: float,
    fee: float = 1.0,
) -> LedgerEvent:
    return make_position_opened_event(
        event_id=f"event-{seq}",
        paper_epoch_id="TEST-EPOCH",
        sequence=seq,
        timestamp=float(seq),
        trade_id=trade_id,
        symbol="BTC/USDT",
        side=side,
        principal=100.0,
        entry_price=entry,
        entry_fee=fee,
        decision_id=f"packet-{trade_id}",
        schema_version=2,
        tp_price=150.0,
        sl_price=50.0,
        timeout_at=float(seq + 100),
        recovery_eligible_until=float(seq + 110),
    )


def _closed_population() -> list[LedgerEvent]:
    return [
        make_epoch_created_event(
            event_id="event-1",
            paper_epoch_id="TEST-EPOCH",
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=1000.0,
            code_sha="1" * 40,
            config_snapshot_hash="2" * 64,
            schema_version=2,
        ),
        _open(seq=2, trade_id="T1", side="LONG", entry=100.0),
        make_position_closed_event(
            event_id="event-3",
            paper_epoch_id="TEST-EPOCH",
            sequence=3,
            timestamp=3.0,
            trade_id="T1",
            exit_price=110.0,
            exit_fee=1.0,
            schema_version=2,
        ),
        _open(seq=4, trade_id="T2", side="SHORT", entry=100.0),
        make_position_closed_event(
            event_id="event-5",
            paper_epoch_id="TEST-EPOCH",
            sequence=5,
            timestamp=5.0,
            trade_id="T2",
            exit_price=90.0,
            exit_fee=1.0,
            schema_version=2,
        ),
        _open(seq=6, trade_id="T3", side="LONG", entry=100.0),
        make_position_closed_event(
            event_id="event-7",
            paper_epoch_id="TEST-EPOCH",
            sequence=7,
            timestamp=7.0,
            trade_id="T3",
            exit_price=95.0,
            exit_fee=1.0,
            schema_version=2,
        ),
    ]


def _unresolved_population() -> list[LedgerEvent]:
    return [
        make_epoch_created_event(
            event_id="event-1",
            paper_epoch_id="TEST-EPOCH",
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=1000.0,
            code_sha="1" * 40,
            config_snapshot_hash="2" * 64,
            schema_version=2,
        ),
        _open(seq=2, trade_id="U1", side="LONG", entry=100.0),
        make_position_unresolved_event(
            event_id="event-3",
            paper_epoch_id="TEST-EPOCH",
            sequence=3,
            timestamp=3.0,
            trade_id="U1",
            reason="missing certified close evidence",
            schema_version=2,
        ),
    ]


def _build_dataset(tmp_path: Path, events: list[LedgerEvent]) -> Path:
    ppl_raw = b"".join(_event_line(event) for event in events)
    f00_manifest_raw = b'{"fixture":"manifest"}\n'
    f00_config_raw = b'{"fixture":"config"}\n'

    boundary_doc = {
        "identity_schema": "fixture-boundary-v1",
        "source_domain": "PAPER",
        "source_authority": "PPL_AUTHORITY",
        "paper_epoch_id": "TEST-EPOCH",
        "ppl_birth_code_sha": "1" * 40,
        "ppl_semantic_config_snapshot_hash": "2" * 64,
        "experiment_config_file_sha256": _sha(f00_config_raw),
        "experiment_config_snapshot_sha256": "3" * 64,
        "experiment_runtime_source_sha": "4" * 40,
        "ppl_stream_sha256": _sha(ppl_raw),
    }
    source_boundary_id = _sha(_canonical(boundary_doc))

    dataset_identity = {
        "dataset_schema_version": "fixture-v1",
        "derivation": "PAPER_EXPORT",
        "source_boundary_id": source_boundary_id,
        "research_exporter_code_sha": "5" * 40,
        "components": [
            {
                "name": "authoritative_core",
                "status": "COMPLETE",
                "source_boundary_id": source_boundary_id,
            },
            {
                "name": "decision_packets",
                "status": "NOT_INCLUDED",
                "record_count": 0,
                "canonical_subset_sha256": None,
            },
            {
                "name": "decision_identity_records",
                "status": "NOT_INCLUDED",
                "record_count": 0,
                "canonical_subset_sha256": None,
            },
        ],
    }
    dataset_id = _sha(_canonical(dataset_identity))
    root = tmp_path / "datasets" / dataset_id
    (root / "authoritative").mkdir(parents=True)

    (root / "authoritative" / "ppl_events.jsonl").write_bytes(ppl_raw)
    (root / "authoritative" / "f00_experiment_manifest.json").write_bytes(
        f00_manifest_raw
    )
    (root / "authoritative" / "f00_experiment_config.json").write_bytes(
        f00_config_raw
    )

    manifest = {
        "dataset_schema_version": "fixture-v1",
        "dataset_id": dataset_id,
        "source_boundary_id": source_boundary_id,
        "derivation": "PAPER_EXPORT",
        "source_domain": "PAPER",
        "source_authority": "PPL_AUTHORITY",
        "paper_epoch_id": "TEST-EPOCH",
        "source_boundary_identity": boundary_doc,
        "dataset_identity": dataset_identity,
        "components": {
            "ppl_events": {
                "authority_class": "AUTHORITATIVE_CORE",
                "status": "COMPLETE",
                "record_count": len(events),
                "sha256": _sha(ppl_raw),
            },
            "f00_experiment_manifest": {
                "authority_class": "AUTHORITATIVE_CORE",
                "status": "COMPLETE",
                "record_count": 1,
                "sha256": _sha(f00_manifest_raw),
            },
            "f00_experiment_config": {
                "authority_class": "AUTHORITATIVE_CORE",
                "status": "COMPLETE",
                "record_count": 1,
                "sha256": _sha(f00_config_raw),
                "snapshot_sha256": "3" * 64,
            },
            "decision_packets": {
                "authority_class": "OPTIONAL_CERTIFIED",
                "status": "NOT_INCLUDED",
                "record_count": 0,
            },
            "decision_identity_records": {
                "authority_class": "OPTIONAL_CERTIFIED",
                "status": "NOT_INCLUDED",
                "record_count": 0,
            },
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return root


def test_valid_dataset_replays_exact_factual_state(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _closed_population())

    result = replay_factual_dataset(root, replay_code_sha="a" * 40)

    assert result.terminal_state["source_event_count"] == 7
    assert result.terminal_state["closed_trade_count"] == 3
    assert result.terminal_state["open_position_count"] == 0
    assert result.terminal_state["unresolved_position_count"] == 0
    assert result.terminal_state["fees_paid"] == pytest.approx(6.0)
    assert result.terminal_state["realized_pnl"] == pytest.approx(9.0)
    assert result.terminal_state["available_cash"] == pytest.approx(1009.0)

    assert result.metrics["closed_trade_count"] == 3
    assert result.metrics["win_rate"]["value"] == pytest.approx(2 / 3)
    assert result.metrics["profit_factor"]["value"] == pytest.approx(16 / 7)
    assert result.metrics["expectancy_usd"]["value"] == pytest.approx(3.0)
    assert result.metrics["mark_to_market_max_drawdown"]["status"] == "NOT_AVAILABLE"
    assert result.metrics["sharpe"]["status"] == "NOT_AVAILABLE"


def test_identical_replay_is_deterministic(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _closed_population())

    a = replay_factual_dataset(root, replay_code_sha="a" * 40)
    b = replay_factual_dataset(root, replay_code_sha="a" * 40)

    assert a.research_run_id == b.research_run_id
    assert a.research_run_identity == b.research_run_identity
    assert a.lifecycle == b.lifecycle
    assert a.metrics == b.metrics
    assert a.terminal_state == b.terminal_state


def test_absolute_dataset_path_does_not_change_run_identity(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path / "left", _closed_population())
    copied = tmp_path / "right" / root.name
    copied.parent.mkdir(parents=True)
    shutil.copytree(root, copied)

    left = replay_factual_dataset(root, replay_code_sha="a" * 40)
    right = replay_factual_dataset(copied, replay_code_sha="a" * 40)

    assert left.research_run_id == right.research_run_id


def test_changed_replay_config_changes_run_identity(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _closed_population())

    baseline = replay_factual_dataset(root, replay_code_sha="a" * 40)
    changed = replay_factual_dataset(
        root,
        replay_code_sha="a" * 40,
        replay_config={
            "schema_version": 1,
            "metric_semantics_version": "TEST_CHANGED",
            "population": "POSITION_CLOSED_FOR_PERFORMANCE",
            "drawdown": "REALIZED_CLOSE_TO_CLOSE",
            "financial_interpretation": "PPL_NATIVE",
            "counterfactual": "DISABLED",
        },
    )

    assert baseline.replay_config_hash != changed.replay_config_hash
    assert baseline.research_run_id != changed.research_run_id


def test_component_corruption_is_rejected(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _closed_population())
    ppl = root / "authoritative" / "ppl_events.jsonl"
    ppl.write_bytes(ppl.read_bytes() + b"\n")

    with pytest.raises(DatasetValidationError, match="component digest mismatch"):
        validate_dataset(root)


def test_duplicate_manifest_key_is_rejected(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _closed_population())
    (root / "manifest.json").write_text(
        '{"dataset_id":"a","dataset_id":"b"}\n',
        encoding="utf-8",
    )

    with pytest.raises(DatasetValidationError, match="duplicate JSON key"):
        validate_dataset(root)


def test_unresolved_trade_is_not_zero_pnl_close(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _unresolved_population())

    result = replay_factual_dataset(root, replay_code_sha="a" * 40)

    assert result.terminal_state["closed_trade_count"] == 0
    assert result.terminal_state["unresolved_position_count"] == 1
    assert result.metrics["closed_trade_count"] == 0
    assert result.metrics["win_rate"]["status"] == "NOT_AVAILABLE"
    assert result.metrics["win_rate"]["value"] is None
    assert result.metrics["profit_factor"]["status"] == "NOT_AVAILABLE"
    assert result.metrics["expectancy_usd"]["status"] == "NOT_AVAILABLE"
    assert result.lifecycle[0].resolution_status == "UNRESOLVED"
    assert result.lifecycle[0].net_realized_pnl is None


def test_invalid_replay_code_sha_is_rejected(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _closed_population())

    with pytest.raises(ReplayError, match="40-char Git SHA"):
        replay_factual_dataset(root, replay_code_sha="not-a-sha")


def test_source_boundary_identity_tampering_is_rejected(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _closed_population())
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_boundary_identity"]["paper_epoch_id"] = "TAMPERED"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DatasetValidationError, match="source_boundary_id"):
        validate_dataset(root)


def test_dataset_identity_tampering_is_rejected(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, _closed_population())
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_identity"]["research_exporter_code_sha"] = "f" * 40
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DatasetValidationError, match="dataset_id"):
        validate_dataset(root)
