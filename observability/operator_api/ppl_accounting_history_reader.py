"""Bounded transport of a separately published accounting observation. No replay."""

import json
import math
import os
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

DEFAULT_PATH = Path(
    os.getenv(
        "PPL_ACCOUNTING_HISTORY_PATH",
        "/opt/crypto-ai-terminal/operator/presentation/ppl_accounting_history.json",
    )
)
KEYS = set(
    "schema_version product authority unit paper_epoch_id ppl_event_schema_version source_generated_at_utc source_snapshot_sha256 source_manifest_sha256 producer_source_sha epoch_code_sha config_snapshot_hash semantics last_sequence replay_validated checkpoint_verified samples allocation limitations".split()
)
AMOUNTS = (
    "available_cash",
    "realized_pnl",
    "reserved_principal",
    "unresolved_capital",
    "fees_paid",
)


def number(value):
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("invalid decimal representation")
    result = Decimal(value)
    if not result.is_finite() or not math.isfinite(float(result)):
        raise ValueError("nonfinite amount")
    return result


def timestamp(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("timezone required")
    return date.timestamp()


def validate_history(doc):
    try:
        if (
            set(doc) != KEYS
            or type(doc["schema_version"]) is not int
            or doc["schema_version"] != 1
        ):
            return False
        if (
            doc["product"] != "PPLAccountingHistory"
            or doc["authority"] != "DERIVED_OBSERVATION"
            or doc["unit"] != "PAPER_ACCOUNT_UNIT"
            or doc["ppl_event_schema_version"] != 2
            or doc["semantics"] != "PPL_V2_FLOAT_PROJECTOR_REALIZED_NET_ENTRY_EXIT_FEES"
            or doc["checkpoint_verified"] is not False
            or doc["replay_validated"] is not True
        ):
            return False
        if (
            not isinstance(doc["paper_epoch_id"], str)
            or not 1 <= len(doc["paper_epoch_id"]) <= 256
        ):
            return False
        for key, length in (
            ("source_snapshot_sha256", 64),
            ("source_manifest_sha256", 64),
            ("producer_source_sha", 40),
            ("epoch_code_sha", 40),
            ("config_snapshot_hash", 64),
        ):
            if not isinstance(doc[key], str) or not re.fullmatch(
                "[0-9a-f]{%d}" % length, doc[key]
            ):
                return False
        source_time = timestamp(doc["source_generated_at_utc"])
        samples = doc["samples"]
        if (
            not isinstance(samples, list)
            or not 1 <= len(samples) <= 1000
            or type(doc["last_sequence"]) is not int
            or doc["last_sequence"] != len(samples)
        ):
            return False
        ids, last_time = set(), -math.inf
        for seq, sample in enumerate(samples, 1):
            if set(sample) != set(AMOUNTS) | {
                "sequence",
                "event_id",
                "timestamp_utc",
                "open_positions",
            }:
                return False
            if type(sample["sequence"]) is not int or sample["sequence"] != seq:
                return False
            event_id = sample["event_id"]
            if (
                not isinstance(event_id, str)
                or not 1 <= len(event_id) <= 256
                or event_id in ids
            ):
                return False
            ids.add(event_id)
            observed = timestamp(sample["timestamp_utc"])
            if observed < last_time or observed > source_time:
                return False
            last_time = observed
            for key in AMOUNTS:
                amount = number(sample[key])
                if key != "realized_pnl" and amount < 0:
                    return False
            if (
                type(sample["open_positions"]) is not int
                or sample["open_positions"] < 0
            ):
                return False
        allocation = doc["allocation"]
        if allocation is not None:
            if (
                set(allocation) != {"denominator", "definition", "segments"}
                or allocation["definition"]
                != "AVAILABLE_PLUS_RESERVED_PLUS_UNRESOLVED_AT_COST"
            ):
                return False
            denominator = number(allocation["denominator"])
            if denominator <= 0 or len(allocation["segments"]) != 3:
                return False
            total, shares = Decimal(0), Decimal(0)
            for segment, key in zip(
                allocation["segments"],
                ("available_cash", "reserved_principal", "unresolved_capital"),
            ):
                if set(segment) != {"id", "amount", "share"} or segment["id"] != key:
                    return False
                amount, share = number(segment["amount"]), number(segment["share"])
                if (
                    amount != number(samples[-1][key])
                    or not 0 <= share <= 1
                    or abs(share - amount / denominator) > Decimal("1e-12")
                ):
                    return False
                total += amount
                shares += share
            if total != denominator or abs(shares - 1) > Decimal("1e-12"):
                return False
        return (
            isinstance(doc["limitations"], list)
            and 1 <= len(doc["limitations"]) <= 10
            and all(
                isinstance(x, str) and 0 < len(x) <= 512 for x in doc["limitations"]
            )
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        InvalidOperation,
        AttributeError,
    ):
        return False


def read_history(path=DEFAULT_PATH, *, now=None):
    try:
        with Path(path).open("rb") as f:
            raw = f.read(2_000_001)
        if len(raw) > 2_000_000:
            return None, "HISTORY_TOO_LARGE"
        doc = json.loads(raw)
        if not validate_history(doc):
            return None, "HISTORY_INVALID"
        age = (time.time() if now is None else now) - timestamp(
            doc["source_generated_at_utc"]
        )
        if age < -5:
            return None, "HISTORY_SOURCE_IN_FUTURE"
        return {
            **doc,
            "snapshot_age_s": max(0, age),
            "freshness_classification": "STALE" if age > 90 else "FRESH",
        }, None
    except FileNotFoundError:
        return None, "HISTORY_NOT_AVAILABLE"
    except (OSError, ValueError, TypeError):
        return None, "HISTORY_UNREADABLE"
