"""APP-UNIFY U2 real-path cross-stack fixture.

Builds deterministic canonical PPL events, the governed burn-in config document,
publishes through the real BurnInStatusSnapshot producer, reads through the real
Operator API route, and writes only that HTTP response for the frontend gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from observability import burn_in_status_snapshot as burn
from observability.operator_api import app as api_app
from observability.operator_api.burn_in_status_reader import BurnInStatusSnapshotReader
from paper_trading import durable_event_store as ppl_wire
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
)
from scripts import burn_in_experiment_config_freeze as burn_freeze


EPOCH = "BURN-IN-EPOCH-CROSS-STACK"
SOURCE_SHA = "c" * 40
NOW = 1_800_000_400.0


def _config() -> dict:
    payload = {
        "snapshot_schema": "BURN_IN_EXPERIMENT_CONFIG_V1",
        "paper_epoch_id": EPOCH,
        "runtime_source_sha": SOURCE_SHA,
        "parameters": {
            "PB_MAX_POSITIONS": {"value": "2"},
            "PAPER_PORTFOLIO_BRAIN_LEVEL": {"value": "a"},
            "MEXC_SIM_MAX_POSITION_USD": {"value": "10"},
            "MEXC_SIM_MAX_AGE_H": {"value": "8"},
            "PAPER_LIFECYCLE_AUTHORITY": {"value": "PPL_AUTHORITY"},
        },
    }
    return {**payload, "snapshot_sha256": burn_freeze.snapshot_sha256(payload)}


def _events(config_hash: str):
    t0 = 1_800_000_000.0
    return (
        make_epoch_created_event(
            event_id="x1", paper_epoch_id=EPOCH, sequence=1, timestamp=t0,
            initial_virtual_capital=1000.0, code_sha=SOURCE_SHA,
            config_snapshot_hash=config_hash, schema_version=2,
        ),
        make_position_opened_event(
            event_id="x2", paper_epoch_id=EPOCH, sequence=2, timestamp=t0 + 10,
            trade_id="cross-closed", symbol="BTC/USDT", side="LONG",
            principal=10.0, entry_price=100.0, entry_fee=0.01,
            decision_id="cross-open-btc", schema_version=2, tp_price=110.0,
            sl_price=95.0, timeout_at=t0 + 200, recovery_eligible_until=t0 + 300,
        ),
        make_position_closed_event(
            event_id="x3", paper_epoch_id=EPOCH, sequence=3, timestamp=t0 + 70,
            trade_id="cross-closed", exit_price=105.0, exit_fee=0.01,
            decision_id="cross-close-btc", schema_version=2,
        ),
        make_position_opened_event(
            event_id="x4", paper_epoch_id=EPOCH, sequence=4, timestamp=t0 + 100,
            trade_id="cross-open", symbol="ETH/USDT", side="SHORT",
            principal=10.0, entry_price=200.0, entry_fee=0.01,
            decision_id="cross-open-eth", schema_version=2, tp_price=190.0,
            sl_price=205.0, timeout_at=t0 + 500, recovery_eligible_until=t0 + 900,
        ),
        make_position_opened_event(
            event_id="x5", paper_epoch_id=EPOCH, sequence=5, timestamp=t0 + 120,
            trade_id="cross-unresolved", symbol="SOL/USDT", side="LONG",
            principal=10.0, entry_price=50.0, entry_fee=0.01,
            schema_version=2, tp_price=55.0, sl_price=48.0,
            timeout_at=t0 + 500, recovery_eligible_until=t0 + 900,
        ),
        make_position_unresolved_event(
            event_id="x6", paper_epoch_id=EPOCH, sequence=6, timestamp=t0 + 180,
            trade_id="cross-unresolved", reason="RECOVERY_PRICE_UNAVAILABLE",
            schema_version=2,
        ),
    )


def generate(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    producer = out_dir / "_producer" / "J_burn_in"
    store = producer / "ppl"
    epochs = store / "epochs"
    epochs.mkdir(parents=True, exist_ok=True)

    config = _config()
    events = _events(config["snapshot_sha256"])
    raw = b"".join(ppl_wire._canonical_line(event) for event in events)
    digest = hashlib.sha256(EPOCH.encode("utf-8")).hexdigest()
    epoch_path = epochs / f"{digest}.jsonl"
    epoch_path.write_bytes(raw)

    config_path = producer / "burn-in-config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    artifact = producer / "burn_in_status_snapshot.json"
    produced = burn.write_burn_in_status_snapshot(
        artifact,
        store_root=store,
        paper_epoch_id=EPOCH,
        config_path=config_path,
        now_fn=lambda: NOW,
        scientific_t0_utc="2027-01-15T08:00:05Z",
        scientific_t0_source="CROSS_STACK_GOVERNANCE_FIXTURE",
    )

    prior = api_app.get_burn_in_status_reader()
    api_app._burn_in_status_reader = BurnInStatusSnapshotReader(
        path=artifact,
        stale_after_s=60.0,
        now_fn=lambda: NOW + 5.0,
    )
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/burn-in")
    finally:
        api_app._burn_in_status_reader = prior

    result = {
        "http_status": response.status_code,
        "body": response.json(),
        "_proof": {
            "producer_authority": produced["authority"],
            "artifact_is_regular_file": artifact.is_file() and not artifact.is_symlink(),
            "ppl_lock_created": (store / ".ppl-event-store.lock").exists(),
            "lifecycle_total": produced["lifecycle_counts"]["total"],
            "history_rows": len(produced["lifecycle_history"]),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "J_burn_in.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = generate(Path(args.out))
    if result["http_status"] != 200:
        raise SystemExit("Burn-in cross-stack fixture did not produce HTTP 200")
    print("APP_UNIFY_U2_CROSS_STACK_FIXTURE=PASS")


if __name__ == "__main__":
    main()
