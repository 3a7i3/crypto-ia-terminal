from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from core.decision_packet import (
    ConvictionLevel,
    DecisionPacket,
    DecisionSide,
    DecisionState,
    MarketRegime,
    ReasoningCategory,
)
from paper_trading.ledger_events import (
    LedgerEvent,
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
)
from research_diag import DiagnosticError, diagnose_factual_dataset


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
    return _canonical(
        {
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
    ) + b"\n"


def _events() -> list[LedgerEvent]:
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
        make_position_opened_event(
            event_id="event-2",
            paper_epoch_id="TEST-EPOCH",
            sequence=2,
            timestamp=2.0,
            trade_id="T1",
            symbol="BTC/USDT",
            side="LONG",
            principal=100.0,
            entry_price=100.0,
            entry_fee=0.1,
            decision_id="packet-1",
            schema_version=2,
            tp_price=120.0,
            sl_price=90.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
        make_position_closed_event(
            event_id="event-3",
            paper_epoch_id="TEST-EPOCH",
            sequence=3,
            timestamp=3.0,
            trade_id="T1",
            exit_price=110.0,
            exit_fee=0.1,
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="event-4",
            paper_epoch_id="TEST-EPOCH",
            sequence=4,
            timestamp=4.0,
            trade_id="T2",
            symbol="ETH/USDT",
            side="LONG",
            principal=100.0,
            entry_price=100.0,
            entry_fee=0.1,
            decision_id="packet-2",
            schema_version=2,
            tp_price=120.0,
            sl_price=90.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
        make_position_closed_event(
            event_id="event-5",
            paper_epoch_id="TEST-EPOCH",
            sequence=5,
            timestamp=5.0,
            trade_id="T2",
            exit_price=95.0,
            exit_fee=0.1,
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="event-6",
            paper_epoch_id="TEST-EPOCH",
            sequence=6,
            timestamp=6.0,
            trade_id="T3",
            symbol="SOL/USDT",
            side="SHORT",
            principal=100.0,
            entry_price=100.0,
            entry_fee=0.1,
            decision_id="packet-3",
            schema_version=2,
            tp_price=80.0,
            sl_price=110.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
        make_position_closed_event(
            event_id="event-7",
            paper_epoch_id="TEST-EPOCH",
            sequence=7,
            timestamp=7.0,
            trade_id="T3",
            exit_price=90.0,
            exit_fee=0.1,
            schema_version=2,
        ),
    ]


def _packet(
    *,
    packet_id: str,
    symbol: str,
    side: DecisionSide,
    regime: MarketRegime,
    conviction: ConvictionLevel,
    confidence: float,
    mtf: float,
    mtf_strength: float,
    regime_score: float,
    size_usd: float,
    conviction_score: float,
) -> dict[str, Any]:
    packet = DecisionPacket(
        packet_id=packet_id,
        symbol=symbol,
        side=side,
        confidence=confidence,
        regime=regime,
        conviction=conviction,
        entry_price=999.0,
        stop_loss=998.0,
        take_profit=1000.0,
        r_multiple=1.0,
        features={
            "mtf": mtf,
            "mtf_strength": mtf_strength,
            "regime": regime_score,
            "conviction_size_factor": 1.0 if conviction is ConvictionLevel.HIGH else 0.6,
            "os_size_usd": size_usd,
            "pb_capital_available": 400.0,
            "pb_exposure_pct": size_usd / 1000.0,
            "pb_symbol_pct": size_usd / 1000.0,
        },
        metadata={
            "trace_id": f"trace-{packet_id}",
            "signal_raw": "BUY" if side is DecisionSide.LONG else "SELL",
            "mtf_confirmed": True,
            "conviction_score": conviction_score,
            "conviction_size_factor": (
                1.0 if conviction is ConvictionLevel.HIGH else 0.6
            ),
            "conviction_dimensions": {
                "signal": confidence,
                "mtf": mtf / 40.0 * 100.0,
                "regime": 95.0 if regime is MarketRegime.TREND_BULL else 55.0,
                "memory": 50.0,
                "quality": 49.2,
            },
            "mtf_tfs": {
                "1d": "BUY" if side is DecisionSide.LONG else "SELL",
                "4h": "BUY",
                "1h": "BUY" if side is DecisionSide.LONG else "HOLD",
                "15m": "HOLD",
                "1m": "HOLD",
            },
        },
    )
    packet.add_reasoning(
        "live_signal_engine",
        "fixture signal",
        confidence_impact=1.0,
        category=ReasoningCategory.SIGNAL_QUALITY,
    )
    for state, actor in (
        (DecisionState.SIGNAL_GENERATED, "live_signal_engine"),
        (DecisionState.CONTEXT_ENRICHED, "conviction_engine"),
        (DecisionState.RISK_EVALUATED, "global_risk_gate"),
        (DecisionState.APPROVED, "portfolio_brain"),
        (DecisionState.EXECUTION_PENDING, "capital_engine"),
    ):
        packet.transition_to(state, actor, f"fixture {state.value}")
    return packet.to_dict()


def _packet_rows() -> list[dict[str, Any]]:
    return [
        _packet(
            packet_id="packet-1",
            symbol="BTC/USDT",
            side=DecisionSide.LONG,
            regime=MarketRegime.TREND_BULL,
            conviction=ConvictionLevel.HIGH,
            confidence=80.0,
            mtf=32.0,
            mtf_strength=0.65,
            regime_score=25.0,
            size_usd=37.5,
            conviction_score=75.0,
        ),
        _packet(
            packet_id="packet-2",
            symbol="ETH/USDT",
            side=DecisionSide.LONG,
            regime=MarketRegime.RANGE,
            conviction=ConvictionLevel.MEDIUM,
            confidence=70.0,
            mtf=23.0,
            mtf_strength=0.20,
            regime_score=12.0,
            size_usd=30.0,
            conviction_score=64.0,
        ),
        _packet(
            packet_id="packet-3",
            symbol="SOL/USDT",
            side=DecisionSide.SHORT,
            regime=MarketRegime.TREND_BULL,
            conviction=ConvictionLevel.HIGH,
            confidence=78.0,
            mtf=30.0,
            mtf_strength=0.55,
            regime_score=25.0,
            size_usd=37.5,
            conviction_score=74.0,
        ),
    ]


def _build_dataset(
    tmp_path: Path,
    *,
    drop_packet: bool = False,
    tamper_chain: bool = False,
) -> Path:
    events = _events()
    ppl_raw = b"".join(_event_line(event) for event in events)
    f00_manifest_raw = b'{"fixture":"manifest"}\n'
    f00_config_raw = b'{"fixture":"config"}\n'

    packets = _packet_rows()
    if drop_packet:
        packets = packets[:-1]
    if tamper_chain:
        packets[0]["state_history"][0]["reason"] = "tampered after hash"

    packet_raw = b"".join(
        _canonical(row) + b"\n"
        for row in sorted(packets, key=lambda row: row["packet_id"])
    )
    packet_digest = _sha(packet_raw)

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
                "status": "COMPLETE",
                "record_count": len(packets),
                "canonical_subset_sha256": packet_digest,
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
    (root / "optional").mkdir(parents=True)

    (root / "authoritative" / "ppl_events.jsonl").write_bytes(ppl_raw)
    (root / "authoritative" / "f00_experiment_manifest.json").write_bytes(
        f00_manifest_raw
    )
    (root / "authoritative" / "f00_experiment_config.json").write_bytes(
        f00_config_raw
    )
    (root / "optional" / "decision_packets.jsonl").write_bytes(packet_raw)

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
                "status": "COMPLETE",
                "record_count": len(packets),
                "canonical_subset_sha256": packet_digest,
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


def test_a4_reconciles_factual_pnl_and_context(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path)

    result = diagnose_factual_dataset(
        root,
        replay_code_sha="a" * 40,
        diag_code_sha="b" * 40,
    )

    assert result.summary["n"] == 3
    assert result.summary["wins"] == 2
    assert result.summary["losses"] == 1
    assert result.summary["terminal_realized_pnl_usd"] == pytest.approx(14.4)
    assert result.summary["terminal_fees_paid_usd"] == pytest.approx(0.6)
    assert result.summary["pnl_reconciliation"] == "PASS"
    assert result.summary["fee_reconciliation"] == "PASS"

    by_regime = result.categorical_attribution["by_regime"]
    assert by_regime["TREND_BULL"]["n"] == 2
    assert by_regime["RANGE"]["n"] == 1

    by_conviction = result.categorical_attribution["by_conviction"]
    assert by_conviction["HIGH"]["n"] == 2
    assert by_conviction["MEDIUM"]["n"] == 1

    assert result.numeric_context["features_mtf_strength"]["winner_mean"] is not None
    assert result.concentration["status"] == "COMPLETE"


def test_ppl_geometry_remains_authoritative_over_packet_geometry(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path)

    result = diagnose_factual_dataset(
        root,
        replay_code_sha="a" * 40,
        diag_code_sha="b" * 40,
    )

    t1 = next(row for row in result.trade_attribution if row["trade_id"] == "T1")
    assert t1["entry_price"] == pytest.approx(100.0)
    assert t1["tp_price"] == pytest.approx(120.0)
    assert t1["sl_price"] == pytest.approx(90.0)


def test_identical_inputs_produce_same_diagnostic_identity(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path)

    a = diagnose_factual_dataset(
        root,
        replay_code_sha="a" * 40,
        diag_code_sha="b" * 40,
    )
    b = diagnose_factual_dataset(
        root,
        replay_code_sha="a" * 40,
        diag_code_sha="b" * 40,
    )

    assert a.diagnostic_run_id == b.diagnostic_run_id
    assert a.diagnostic_run_identity == b.diagnostic_run_identity
    assert a.trade_attribution == b.trade_attribution
    assert a.categorical_attribution == b.categorical_attribution
    assert a.numeric_context == b.numeric_context


def test_changed_diag_code_changes_diag_identity_not_upstream_replay(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path)

    a = diagnose_factual_dataset(
        root,
        replay_code_sha="a" * 40,
        diag_code_sha="b" * 40,
    )
    b = diagnose_factual_dataset(
        root,
        replay_code_sha="a" * 40,
        diag_code_sha="c" * 40,
    )

    assert a.upstream_research_run_id == b.upstream_research_run_id
    assert a.diagnostic_run_id != b.diagnostic_run_id


def test_missing_packet_population_fails_closed(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, drop_packet=True)

    with pytest.raises(DiagnosticError, match="population mismatch"):
        diagnose_factual_dataset(
            root,
            replay_code_sha="a" * 40,
            diag_code_sha="b" * 40,
        )


def test_tampered_packet_hash_chain_fails_closed(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path, tamper_chain=True)

    with pytest.raises(DiagnosticError, match="hash chain invalid"):
        diagnose_factual_dataset(
            root,
            replay_code_sha="a" * 40,
            diag_code_sha="b" * 40,
        )
