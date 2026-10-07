"""Offline accounting presentation from one captured PPL comparator + manifest.

Never imported by the API. No runtime instances, stores, or exchange clients.
Amounts follow the existing float PPL projector; this is not FIN certification.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal

from observability.operator_api.ppl_comparison_reader import (
    validate_ppl_comparison_snapshot,
)
from paper_trading.ledger_events import LedgerEvent, LedgerEventType
from paper_trading.paper_portfolio_ledger import project


def build_history(
    snapshot_bytes: bytes, manifest_bytes: bytes, *, producer_sha: str
) -> dict:
    snapshot = json.loads(snapshot_bytes)
    manifest = json.loads(manifest_bytes)
    if not validate_ppl_comparison_snapshot(snapshot):
        raise ValueError("invalid comparator snapshot")
    epoch = snapshot["paper_epoch_id"]
    if (
        manifest.get("paper_epoch_id") != epoch
        or manifest.get("ppl_event_schema_version") != 2
        or manifest.get("epoch_role") != "BURN_IN_EXPERIMENT"
        or manifest.get("manifest_schema_version") != 3
        or snapshot["ppl_source"]["authority"] != "PAPER_AUTHORITY"
        or snapshot["ppl_source"]["last_error"] is not None
        or snapshot["shadow_status"] != "ACTIVE"
    ):
        raise ValueError("unproven authority/epoch/schema boundary")
    raw = snapshot["ppl_events"]
    if not 1 <= len(raw) <= 1000:
        raise ValueError("supported bounded history requires 1..1000 events")
    first = raw[0]
    for key in ("code_sha", "config_snapshot_hash", "initial_virtual_capital"):
        if first["payload"].get(key) != manifest.get(key):
            raise ValueError("manifest/epoch event mismatch: " + key)
    if first["timestamp"] != manifest.get("created_at"):
        raise ValueError("manifest creation timestamp mismatch")
    samples, events = [], []
    last_time = -math.inf
    source_time = datetime.fromisoformat(
        snapshot["generated_at_utc"].replace("Z", "+00:00")
    ).timestamp()
    for row in raw:
        if row["timestamp"] < last_time or row["timestamp"] > source_time:
            raise ValueError("event time regression or event beyond snapshot boundary")
        last_time = row["timestamp"]
        events.append(
            LedgerEvent(
                event_id=row["event_id"],
                paper_epoch_id=epoch,
                sequence=row["sequence"],
                event_type=LedgerEventType(row["event_type"]),
                timestamp=row["timestamp"],
                trade_id=row["trade_id"],
                decision_id=row["decision_id"],
                payload=row["payload"],
                schema_version=2,
            )
        )
        state = project(events)
        samples.append(
            {
                "sequence": row["sequence"],
                "event_id": row["event_id"],
                "timestamp_utc": datetime.fromtimestamp(
                    row["timestamp"], timezone.utc
                ).isoformat(),
                "available_cash": repr(state.available_cash),
                "realized_pnl": repr(state.realized_pnl),
                "reserved_principal": repr(state.reserved_principal),
                "unresolved_capital": repr(state.unresolved_capital),
                "fees_paid": repr(state.fees_paid),
                "open_positions": len(state.open_positions),
            }
        )
    last = samples[-1]
    amounts = [
        Decimal(last[k])
        for k in ("available_cash", "reserved_principal", "unresolved_capital")
    ]
    total = sum(amounts, Decimal(0))
    allocation = None
    if total > 0 and all(x >= 0 for x in amounts):
        allocation = {
            "denominator": str(total),
            "definition": "AVAILABLE_PLUS_RESERVED_PLUS_UNRESOLVED_AT_COST",
            "segments": [
                {"id": key, "amount": str(amount), "share": str(amount / total)}
                for key, amount in zip(
                    ("available_cash", "reserved_principal", "unresolved_capital"),
                    amounts,
                )
            ],
        }
    return {
        "schema_version": 1,
        "product": "PPLAccountingHistory",
        "authority": "DERIVED_OBSERVATION",
        "unit": "PAPER_ACCOUNT_UNIT",
        "paper_epoch_id": epoch,
        "ppl_event_schema_version": 2,
        "source_generated_at_utc": snapshot["generated_at_utc"],
        "source_snapshot_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "producer_source_sha": producer_sha,
        "epoch_code_sha": manifest["code_sha"],
        "config_snapshot_hash": manifest["config_snapshot_hash"],
        "semantics": "PPL_V2_FLOAT_PROJECTOR_REALIZED_NET_ENTRY_EXIT_FEES",
        "last_sequence": len(samples),
        "replay_validated": True,
        "checkpoint_verified": False,
        "samples": samples,
        "allocation": allocation,
        "limitations": [
            "Historical captured prefix; not a live collector.",
            "No independently published final accounting checkpoint in AUTHORITY_STATUS.",
            "No mark-to-market, funding evidence, or FIN certification.",
            "Accounting unit only; no FX or exchange balance inference.",
            "Unresolved principal is not certified recoverable value.",
        ],
    }
