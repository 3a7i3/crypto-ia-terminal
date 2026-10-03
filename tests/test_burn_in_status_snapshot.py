from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from observability.burn_in_status_contract import validate_burn_in_status_snapshot
from observability import burn_in_status_snapshot as burn
from paper_trading import durable_event_store as ppl_wire
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
)
from scripts import burn_in_experiment_config_freeze as burn_freeze


EPOCH = "BURN-IN-EPOCH-TEST"
SOURCE_SHA = "a" * 40


def _config_payload() -> dict:
    return {
        "snapshot_schema": "BURN_IN_EXPERIMENT_CONFIG_V1",
        "paper_epoch_id": EPOCH,
        "runtime_source_sha": SOURCE_SHA,
        "parameters": {
            "PB_MAX_POSITIONS": {"value": "2"},
            "PAPER_PORTFOLIO_BRAIN_LEVEL": {"value": "a"},
            "MEXC_SIM_MAX_POSITION_USD": {"value": "10"},
            "MEXC_SIM_MAX_AGE_H": {"value": "8"},
            "PAPER_LIFECYCLE_AUTHORITY": {"value": "PPL_AUTHORITY"},
            "API_SECRET": {"value": "must-never-leak"},
        },
    }


def _config_doc() -> dict:
    payload = _config_payload()
    return {**payload, "snapshot_sha256": burn_freeze.snapshot_sha256(payload)}


def _events(config_hash: str):
    return (
        make_epoch_created_event(
            event_id="e1",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=50.0,
            initial_virtual_capital=1000.0,
            code_sha=SOURCE_SHA,
            config_snapshot_hash=config_hash,
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="e2",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=100.0,
            trade_id="trade-closed",
            symbol="BTC/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            decision_id="decision-open-1",
            schema_version=2,
            tp_price=110.0,
            sl_price=95.0,
            timeout_at=200.0,
            recovery_eligible_until=300.0,
        ),
        make_position_closed_event(
            event_id="e3",
            paper_epoch_id=EPOCH,
            sequence=3,
            timestamp=150.0,
            trade_id="trade-closed",
            exit_price=110.0,
            exit_fee=0.01,
            decision_id="decision-close-1",
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="e4",
            paper_epoch_id=EPOCH,
            sequence=4,
            timestamp=160.0,
            trade_id="trade-open",
            symbol="ETH/USDT",
            side="SHORT",
            principal=10.0,
            entry_price=200.0,
            entry_fee=0.01,
            decision_id="decision-open-2",
            schema_version=2,
            tp_price=190.0,
            sl_price=205.0,
            timeout_at=220.0,
            recovery_eligible_until=280.0,
        ),
        make_position_opened_event(
            event_id="e5",
            paper_epoch_id=EPOCH,
            sequence=5,
            timestamp=170.0,
            trade_id="trade-unresolved",
            symbol="SOL/USDT",
            side="LONG",
            principal=10.0,
            entry_price=50.0,
            entry_fee=0.01,
            schema_version=2,
            tp_price=55.0,
            sl_price=48.0,
            timeout_at=230.0,
            recovery_eligible_until=290.0,
        ),
        make_position_unresolved_event(
            event_id="e6",
            paper_epoch_id=EPOCH,
            sequence=6,
            timestamp=180.0,
            trade_id="trade-unresolved",
            reason="RECOVERY_PRICE_UNAVAILABLE",
            schema_version=2,
        ),
    )


def _snapshot(now: float = 250.0):
    config = _config_doc()
    events = _events(config["snapshot_sha256"])
    raw = b"".join(ppl_wire._canonical_line(event) for event in events)
    return burn.build_burn_in_status_snapshot(
        events=events,
        config_document=config,
        ppl_stream_sha256=hashlib.sha256(raw).hexdigest(),
        now_fn=lambda: now,
        scientific_t0_utc="1970-01-01T00:01:00Z",
        scientific_t0_source="TEST_GOVERNANCE_ARTIFACT",
    )


def test_builder_is_deterministic_and_reconciles_lifecycle_history():
    first = _snapshot()
    second = _snapshot()
    assert first == second
    assert validate_burn_in_status_snapshot(first)

    assert first["event_count"] == 6
    assert first["last_sequence"] == 6
    assert first["event_counts"]["POSITION_OPENED"] == 3
    assert first["event_counts"]["POSITION_CLOSED"] == 1
    assert first["event_counts"]["POSITION_UNRESOLVED"] == 1
    assert first["lifecycle_counts"] == {
        "open": 1,
        "closed": 1,
        "unresolved": 1,
        "total": 3,
    }

    rows = {row["trade_id"]: row for row in first["lifecycle_history"]}
    closed = rows["trade-closed"]
    assert closed["status"] == "CLOSED"
    assert closed["gross_pnl_usd"] == pytest.approx(1.0)
    assert closed["net_realized_pnl_usd"] == pytest.approx(0.98)
    assert closed["duration_seconds"] == 50.0
    assert closed["open_decision_id"] == "decision-open-1"
    assert closed["terminal_decision_id"] == "decision-close-1"

    unresolved = rows["trade-unresolved"]
    assert unresolved["status"] == "UNRESOLVED"
    assert unresolved["net_realized_pnl_usd"] is None
    assert unresolved["exit_price"] is None
    assert unresolved["unresolved_reason"] == "RECOVERY_PRICE_UNAVAILABLE"

    open_row = rows["trade-open"]
    assert open_row["status"] == "OPEN"
    assert open_row["duration_seconds"] is None

    active = first["open_lifecycles"][0]
    assert active["trade_id"] == "trade-open"
    assert active["age_seconds"] == 90.0
    assert active["deadline_state"] == "RECOVERY_WINDOW"


def test_deadline_state_changes_only_from_producer_clock():
    assert _snapshot(now=200.0)["open_lifecycles"][0]["deadline_state"] == "BEFORE_TIMEOUT"
    assert _snapshot(now=250.0)["open_lifecycles"][0]["deadline_state"] == "RECOVERY_WINDOW"
    assert _snapshot(now=300.0)["open_lifecycles"][0]["deadline_state"] == "RECOVERY_EXPIRED"


def test_t0_is_explicit_or_not_available_never_epoch_inferred():
    config = _config_doc()
    events = _events(config["snapshot_sha256"])
    raw = b"".join(ppl_wire._canonical_line(event) for event in events)
    snapshot = burn.build_burn_in_status_snapshot(
        events=events,
        config_document=config,
        ppl_stream_sha256=hashlib.sha256(raw).hexdigest(),
        now_fn=lambda: 250.0,
    )
    assert snapshot["scientific_t0"] == {
        "status": "NOT_AVAILABLE",
        "value_utc": None,
        "source": None,
    }
    assert snapshot["epoch_created_at_utc"] != snapshot["scientific_t0"]["value_utc"]


def test_config_identity_mismatch_fails_closed():
    config = _config_doc()
    events = _events("b" * 64)
    raw = b"".join(ppl_wire._canonical_line(event) for event in events)
    with pytest.raises(burn.BurnInStatusError, match="config hash mismatch"):
        burn.build_burn_in_status_snapshot(
            events=events,
            config_document=config,
            ppl_stream_sha256=hashlib.sha256(raw).hexdigest(),
            now_fn=lambda: 250.0,
        )


def test_only_whitelisted_config_material_is_published():
    snapshot = _snapshot()
    blob = json.dumps(snapshot)
    assert "must-never-leak" not in blob
    assert "API_SECRET" not in blob
    assert snapshot["frozen_config"]["pb_max_positions"] == "2"
    assert snapshot["frozen_config"]["mexc_sim_max_age_h"] == "8"


def test_read_stable_epoch_is_read_only_and_canonical(tmp_path: Path):
    config = _config_doc()
    events = _events(config["snapshot_sha256"])
    raw = b"".join(ppl_wire._canonical_line(event) for event in events)

    store = tmp_path / "ppl"
    epochs = store / "epochs"
    epochs.mkdir(parents=True)
    digest = hashlib.sha256(EPOCH.encode()).hexdigest()
    path = epochs / f"{digest}.jsonl"
    path.write_bytes(raw)

    before = sorted(str(p.relative_to(store)) for p in store.rglob("*"))
    loaded_path, loaded_raw, loaded_events = burn.read_stable_epoch(store, EPOCH)
    after = sorted(str(p.relative_to(store)) for p in store.rglob("*"))

    assert loaded_path == path
    assert loaded_raw == raw
    assert loaded_events == events
    assert before == after
    assert not (store / ".ppl-event-store.lock").exists()


def test_atomic_writer_publishes_closed_document(tmp_path: Path):
    config = _config_doc()
    events = _events(config["snapshot_sha256"])
    raw = b"".join(ppl_wire._canonical_line(event) for event in events)

    store = tmp_path / "ppl"
    epochs = store / "epochs"
    epochs.mkdir(parents=True)
    digest = hashlib.sha256(EPOCH.encode()).hexdigest()
    (epochs / f"{digest}.jsonl").write_bytes(raw)

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    out = tmp_path / "burn_in_status_snapshot.json"

    produced = burn.write_burn_in_status_snapshot(
        out,
        store_root=store,
        paper_epoch_id=EPOCH,
        config_path=config_path,
        now_fn=lambda: 250.0,
    )
    assert json.loads(out.read_text(encoding="utf-8")) == produced
    assert validate_burn_in_status_snapshot(produced)
    assert not out.with_name(out.name + ".tmp").exists()
