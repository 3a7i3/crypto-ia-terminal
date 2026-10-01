"""Closed presentation contract for APP-UNIFY-01 U2 BurnInStatusSnapshot.

This module is intentionally presentation-only: it imports no PPL store,
projection, execution, risk, sizing, exchange, or advisor runtime code.  Both
producer and Operator API reader use this closed schema so the API can validate
an atomic artifact without acquiring authority over the underlying PPL stream.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
PRODUCT = "BurnInStatusSnapshot"
DOMAIN = "burn_in"
AUTHORITY = "PPL_AUTHORITY_PRESENTATION"
MODE = "READ_ONLY"

TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "product",
        "domain",
        "authority",
        "mode",
        "generated_at_utc",
        "source_updated_at_utc",
        "paper_epoch_id",
        "epoch_created_at_utc",
        "source_code_sha",
        "config_snapshot_hash",
        "ppl_stream_sha256",
        "scientific_t0",
        "event_count",
        "last_sequence",
        "event_counts",
        "lifecycle_counts",
        "last_event",
        "open_lifecycles",
        "lifecycle_history",
        "history_order",
        "frozen_config",
        "finalization",
    }
)

EVENT_COUNT_KEYS = frozenset(
    {
        "EPOCH_CREATED",
        "POSITION_OPENED",
        "POSITION_CLOSED",
        "POSITION_UNRESOLVED",
        "RECOVERY_COMPLETED",
    }
)
LIFECYCLE_COUNT_KEYS = frozenset({"open", "closed", "unresolved", "total"})
LAST_EVENT_KEYS = frozenset(
    {"sequence", "event_type", "timestamp_utc", "trade_id", "decision_id"}
)
SCIENTIFIC_T0_KEYS = frozenset({"status", "value_utc", "source"})
OPEN_LIFECYCLE_KEYS = frozenset(
    {
        "trade_id",
        "decision_id",
        "symbol",
        "side",
        "principal_usd",
        "entry_price",
        "entry_fee_usd",
        "opened_sequence",
        "opened_at_utc",
        "age_seconds",
        "tp_price",
        "sl_price",
        "timeout_at_utc",
        "recovery_eligible_until_utc",
        "deadline_state",
    }
)
HISTORY_ROW_KEYS = frozenset(
    {
        "trade_id",
        "open_decision_id",
        "terminal_decision_id",
        "symbol",
        "side",
        "principal_usd",
        "entry_price",
        "entry_fee_usd",
        "opened_sequence",
        "opened_at_utc",
        "status",
        "terminal_sequence",
        "terminal_at_utc",
        "exit_price",
        "exit_fee_usd",
        "gross_pnl_usd",
        "net_realized_pnl_usd",
        "unresolved_reason",
        "duration_seconds",
    }
)
FROZEN_CONFIG_KEYS = frozenset(
    {
        "snapshot_schema",
        "snapshot_sha256",
        "runtime_source_sha",
        "pb_max_positions",
        "paper_portfolio_brain_level",
        "mexc_sim_max_position_usd",
        "mexc_sim_max_age_h",
        "paper_lifecycle_authority",
    }
)
FINALIZATION_KEYS = frozenset({"state", "reason"})

EVENT_TYPES = EVENT_COUNT_KEYS
SIDES = frozenset({"LONG", "SHORT"})
LIFECYCLE_STATUSES = frozenset({"OPEN", "CLOSED", "UNRESOLVED"})
DEADLINE_STATES = frozenset(
    {"BEFORE_TIMEOUT", "RECOVERY_WINDOW", "RECOVERY_EXPIRED", "NOT_AVAILABLE"}
)


def _plain(value: Any) -> bool:
    return isinstance(value, dict)


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str]) -> bool:
    return frozenset(value) == expected


def _string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nullable_string(value: Any) -> bool:
    return value is None or _string(value)


def _finite(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _nullable_finite(value: Any) -> bool:
    return value is None or _finite(value)


def _non_negative_int(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and value >= 0
    )


def _non_negative_number(value: Any) -> bool:
    return _finite(value) and float(value) >= 0.0


def _utc(value: Any) -> bool:
    if not _string(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _nullable_utc(value: Any) -> bool:
    return value is None or _utc(value)


def _sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value)


def _source_sha(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 40:
        return False
    return all(ch in "0123456789abcdef" for ch in value.lower())


def _valid_scientific_t0(value: Any) -> bool:
    if not _plain(value) or not _exact_keys(value, SCIENTIFIC_T0_KEYS):
        return False
    if value["status"] == "PRESENT":
        return _utc(value["value_utc"]) and _string(value["source"])
    if value["status"] == "NOT_AVAILABLE":
        return value["value_utc"] is None and value["source"] is None
    return False


def _valid_open_lifecycle(value: Any) -> bool:
    if not _plain(value) or not _exact_keys(value, OPEN_LIFECYCLE_KEYS):
        return False
    if not _string(value["trade_id"]):
        return False
    if not _nullable_string(value["decision_id"]):
        return False
    if not _string(value["symbol"]) or value["side"] not in SIDES:
        return False
    for key in ("principal_usd", "entry_price", "entry_fee_usd"):
        if not _finite(value[key]):
            return False
    if not _non_negative_int(value["opened_sequence"]) or value["opened_sequence"] < 1:
        return False
    if not _utc(value["opened_at_utc"]):
        return False
    if not _non_negative_number(value["age_seconds"]):
        return False
    for key in ("tp_price", "sl_price"):
        if not _nullable_finite(value[key]):
            return False
    if not _nullable_utc(value["timeout_at_utc"]):
        return False
    if not _nullable_utc(value["recovery_eligible_until_utc"]):
        return False
    if value["deadline_state"] not in DEADLINE_STATES:
        return False
    return True


def _valid_history_row(value: Any) -> bool:
    if not _plain(value) or not _exact_keys(value, HISTORY_ROW_KEYS):
        return False
    if not _string(value["trade_id"]):
        return False
    if not _nullable_string(value["open_decision_id"]):
        return False
    if not _nullable_string(value["terminal_decision_id"]):
        return False
    if not _string(value["symbol"]) or value["side"] not in SIDES:
        return False
    for key in ("principal_usd", "entry_price", "entry_fee_usd"):
        if not _finite(value[key]):
            return False
    if not _non_negative_int(value["opened_sequence"]) or value["opened_sequence"] < 1:
        return False
    if not _utc(value["opened_at_utc"]):
        return False
    if value["status"] not in LIFECYCLE_STATUSES:
        return False
    if value["terminal_sequence"] is not None and (
        not _non_negative_int(value["terminal_sequence"])
        or value["terminal_sequence"] < 1
    ):
        return False
    if not _nullable_utc(value["terminal_at_utc"]):
        return False
    for key in (
        "exit_price",
        "exit_fee_usd",
        "gross_pnl_usd",
        "net_realized_pnl_usd",
        "duration_seconds",
    ):
        if not _nullable_finite(value[key]):
            return False
    if value["duration_seconds"] is not None and value["duration_seconds"] < 0:
        return False
    if not _nullable_string(value["unresolved_reason"]):
        return False

    if value["status"] == "OPEN":
        return all(
            value[key] is None
            for key in (
                "terminal_sequence",
                "terminal_at_utc",
                "exit_price",
                "exit_fee_usd",
                "gross_pnl_usd",
                "net_realized_pnl_usd",
                "unresolved_reason",
                "duration_seconds",
            )
        )
    if value["status"] == "CLOSED":
        return (
            value["terminal_sequence"] is not None
            and value["terminal_at_utc"] is not None
            and value["exit_price"] is not None
            and value["exit_fee_usd"] is not None
            and value["gross_pnl_usd"] is not None
            and value["net_realized_pnl_usd"] is not None
            and value["unresolved_reason"] is None
            and value["duration_seconds"] is not None
        )
    return (
        value["terminal_sequence"] is not None
        and value["terminal_at_utc"] is not None
        and value["exit_price"] is None
        and value["exit_fee_usd"] is None
        and value["gross_pnl_usd"] is None
        and value["net_realized_pnl_usd"] is None
        and _string(value["unresolved_reason"])
        and value["duration_seconds"] is not None
    )


def _valid_frozen_config(value: Any) -> bool:
    if not _plain(value) or not _exact_keys(value, FROZEN_CONFIG_KEYS):
        return False
    if value["snapshot_schema"] != "BURN_IN_EXPERIMENT_CONFIG_V1":
        return False
    if not _sha256(value["snapshot_sha256"]):
        return False
    if not _source_sha(value["runtime_source_sha"]):
        return False
    for key in (
        "pb_max_positions",
        "paper_portfolio_brain_level",
        "mexc_sim_max_position_usd",
        "mexc_sim_max_age_h",
        "paper_lifecycle_authority",
    ):
        if not _string(value[key]):
            return False
    return True


def validate_burn_in_status_snapshot(doc: Any) -> bool:
    """Strict admission gate for producer-authored U2 presentation data."""

    if not _plain(doc) or not _exact_keys(doc, TOP_LEVEL_KEYS):
        return False
    if doc["schema_version"] != SCHEMA_VERSION:
        return False
    if doc["product"] != PRODUCT or doc["domain"] != DOMAIN:
        return False
    if doc["authority"] != AUTHORITY or doc["mode"] != MODE:
        return False
    if not _utc(doc["generated_at_utc"]) or not _utc(doc["source_updated_at_utc"]):
        return False
    if not _string(doc["paper_epoch_id"]):
        return False
    if not _utc(doc["epoch_created_at_utc"]):
        return False
    if not _source_sha(doc["source_code_sha"]):
        return False
    if not _sha256(doc["config_snapshot_hash"]):
        return False
    if not _sha256(doc["ppl_stream_sha256"]):
        return False
    if not _valid_scientific_t0(doc["scientific_t0"]):
        return False
    if not _non_negative_int(doc["event_count"]) or doc["event_count"] < 1:
        return False
    if not _non_negative_int(doc["last_sequence"]) or doc["last_sequence"] < 1:
        return False

    event_counts = doc["event_counts"]
    if not _plain(event_counts) or not _exact_keys(event_counts, EVENT_COUNT_KEYS):
        return False
    if not all(_non_negative_int(value) for value in event_counts.values()):
        return False
    if sum(event_counts.values()) != doc["event_count"]:
        return False

    lifecycle_counts = doc["lifecycle_counts"]
    if not _plain(lifecycle_counts) or not _exact_keys(
        lifecycle_counts, LIFECYCLE_COUNT_KEYS
    ):
        return False
    if not all(_non_negative_int(value) for value in lifecycle_counts.values()):
        return False
    if (
        lifecycle_counts["open"]
        + lifecycle_counts["closed"]
        + lifecycle_counts["unresolved"]
        != lifecycle_counts["total"]
    ):
        return False
    if lifecycle_counts["total"] != event_counts["POSITION_OPENED"]:
        return False

    last_event = doc["last_event"]
    if not _plain(last_event) or not _exact_keys(last_event, LAST_EVENT_KEYS):
        return False
    if last_event["sequence"] != doc["last_sequence"]:
        return False
    if last_event["event_type"] not in EVENT_TYPES:
        return False
    if not _utc(last_event["timestamp_utc"]):
        return False
    if not _nullable_string(last_event["trade_id"]):
        return False
    if not _nullable_string(last_event["decision_id"]):
        return False

    if not isinstance(doc["open_lifecycles"], list):
        return False
    if not all(_valid_open_lifecycle(row) for row in doc["open_lifecycles"]):
        return False
    if len(doc["open_lifecycles"]) != lifecycle_counts["open"]:
        return False

    if not isinstance(doc["lifecycle_history"], list):
        return False
    if not all(_valid_history_row(row) for row in doc["lifecycle_history"]):
        return False
    if len(doc["lifecycle_history"]) != lifecycle_counts["total"]:
        return False
    trade_ids = [row["trade_id"] for row in doc["lifecycle_history"]]
    if len(trade_ids) != len(set(trade_ids)):
        return False
    if doc["history_order"] != "OPEN_SEQUENCE_DESC":
        return False

    if not _valid_frozen_config(doc["frozen_config"]):
        return False
    if doc["frozen_config"]["snapshot_sha256"] != doc["config_snapshot_hash"]:
        return False
    if doc["frozen_config"]["runtime_source_sha"] != doc["source_code_sha"]:
        return False

    finalization = doc["finalization"]
    if not _plain(finalization) or not _exact_keys(finalization, FINALIZATION_KEYS):
        return False
    if finalization["state"] != "NOT_AVAILABLE":
        return False
    if not _string(finalization["reason"]):
        return False
    return True


__all__ = [
    "AUTHORITY",
    "DOMAIN",
    "MODE",
    "PRODUCT",
    "SCHEMA_VERSION",
    "validate_burn_in_status_snapshot",
]
