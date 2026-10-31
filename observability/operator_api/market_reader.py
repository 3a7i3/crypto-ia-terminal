"""Strict read-only reader for the WEB-01 CryptoRadar MARKET artifact.

The Operator API never reads DecisionPacket JSONL here. It consumes only the
atomic presentation artifact produced by ``observability.market_radar_snapshot``.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from observability.operator_api.path_probe import probe_artifact_path

DEFAULT_MARKET_SNAPSHOT_PATH = Path(
    os.getenv("RADAR_MARKET_SNAPSHOT_PATH", "databases/cryptoradar_market_snapshot.json")
)


def _env_stale_after_s() -> float:
    raw = os.getenv("RADAR_MARKET_STALE_AFTER_S", "90")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 90.0
    return value if math.isfinite(value) and value > 0 else 90.0


DEFAULT_STALE_AFTER_S = _env_stale_after_s()

_TOP_LEVEL_KEYS = {
    "schema_version",
    "product",
    "domain",
    "authority",
    "mode",
    "generated_at_utc",
    "source_updated_at_utc",
    "window_hours",
    "min_confidence",
    "packets_observed",
    "market_regime",
    "universe_size",
    "actionable_count",
    "watchlist_count",
    "top_opportunities",
}

_ROW_KEYS = {
    "symbol",
    "avg_confidence",
    "max_confidence",
    "n_signals",
    "dominant_side",
    "dominance_pct",
    "regime",
}

_FORBIDDEN_ROW_KEYS = {
    "entry",
    "entry_price",
    "sl",
    "stop_loss",
    "tp",
    "take_profit",
    "r_multiple",
    "trade_allowed",
    "is_actionable",
    "order",
    "position",
}


@dataclass(frozen=True)
class MarketReadResult:
    ok: bool
    snapshot: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    snapshot_age_s: Optional[float] = None
    freshness_classification: Optional[str] = None


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _parse_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _valid_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if set(row) != _ROW_KEYS:
        return False
    if _FORBIDDEN_ROW_KEYS.intersection(row):
        return False
    if not isinstance(row["symbol"], str) or not row["symbol"].strip():
        return False
    if not _finite_number(row["avg_confidence"]):
        return False
    if not _finite_number(row["max_confidence"]):
        return False
    if not _non_negative_int(row["n_signals"]):
        return False
    if row["dominant_side"] not in ("LONG", "SHORT", "MIXED"):
        return False
    if not _finite_number(row["dominance_pct"]):
        return False
    if not 0.0 <= float(row["dominance_pct"]) <= 100.0:
        return False
    if not isinstance(row["regime"], str):
        return False
    return True


def _valid_catalogue(doc: Dict[str, Any]) -> bool:
    catalogue = doc.get("catalogue")
    if not isinstance(catalogue, dict) or set(catalogue) != {"population", "rows", "qualified_rows", "coverage"}:
        return False
    if catalogue["population"] != "ALL_OBSERVED_PACKETS":
        return False
    rows, qualified = catalogue["rows"], catalogue["qualified_rows"]
    if not isinstance(rows, list) or not isinstance(qualified, list):
        return False
    if not all(_valid_row(row) for row in rows + qualified):
        return False
    if any(row["n_signals"] <= 0 for row in rows + qualified):
        return False
    if len(rows) != doc["universe_size"] or len(qualified) != doc["actionable_count"]:
        return False
    symbols = {row["symbol"] for row in rows}
    if len(symbols) != len(rows) or len({row["symbol"] for row in qualified}) != len(qualified):
        return False
    if not {row["symbol"] for row in qualified}.issubset(symbols):
        return False
    if qualified[:len(doc["top_opportunities"])] != doc["top_opportunities"]:
        return False
    if sum(row["n_signals"] for row in rows) != doc["packets_observed"]:
        return False
    all_counts = {row["symbol"]: row["n_signals"] for row in rows}
    if any(row["n_signals"] > all_counts[row["symbol"]] for row in qualified):
        return False
    coverage = catalogue["coverage"]
    expected = {"start_at_utc", "end_at_utc", "input_packets", "included_packets", "outside_window_packets", "future_packets", "unresolved_timestamp_packets"}
    if not isinstance(coverage, dict) or set(coverage) != expected:
        return False
    counts = expected - {"start_at_utc", "end_at_utc"}
    if not all(_non_negative_int(coverage[key]) for key in counts):
        return False
    if coverage["included_packets"] != doc["packets_observed"]:
        return False
    if coverage["input_packets"] != sum(coverage[key] for key in counts - {"input_packets"}):
        return False
    start, end = _parse_utc(coverage["start_at_utc"]), _parse_utc(coverage["end_at_utc"])
    if start is None or end is None or (end - start).total_seconds() != doc["window_hours"] * 3600:
        return False
    if end != _parse_utc(doc["generated_at_utc"]):
        return False
    source = _parse_utc(doc["source_updated_at_utc"])
    return (source is None if not rows else source is not None and start <= source <= end)


def validate_market_snapshot(doc: Any) -> bool:
    """Closed-schema admission gate for producer-authored MARKET data."""

    if not isinstance(doc, dict):
        return False
    version = doc.get("schema_version")
    if version not in ("1.0.0", "1.1.0"):
        return False
    if set(doc) != _TOP_LEVEL_KEYS | ({"catalogue"} if version == "1.1.0" else set()):
        return False
    if doc["product"] != "CryptoRadar":
        return False
    if doc["domain"] != "market":
        return False
    if doc["authority"] != "OBSERVATIONAL_TELEMETRY":
        return False
    if doc["mode"] != "OBSERVATION":
        return False
    if _parse_utc(doc["generated_at_utc"]) is None:
        return False
    if doc["source_updated_at_utc"] is not None and _parse_utc(
        doc["source_updated_at_utc"]
    ) is None:
        return False
    if not _non_negative_int(doc["window_hours"]) or doc["window_hours"] <= 0:
        return False
    if not _finite_number(doc["min_confidence"]):
        return False
    if not _non_negative_int(doc["packets_observed"]):
        return False
    if doc["market_regime"] is not None and not isinstance(doc["market_regime"], str):
        return False
    for key in ("universe_size", "actionable_count", "watchlist_count"):
        if not _non_negative_int(doc[key]):
            return False
    opportunities = doc["top_opportunities"]
    if not isinstance(opportunities, list):
        return False
    if not all(_valid_row(row) for row in opportunities):
        return False
    if len(opportunities) > doc["actionable_count"] or doc["actionable_count"] > doc["universe_size"]:
        return False
    if len({row["symbol"] for row in opportunities}) != len(opportunities):
        return False
    return _valid_catalogue(doc) if version == "1.1.0" else True


class MarketSnapshotReader:
    def __init__(
        self,
        path: Path = DEFAULT_MARKET_SNAPSHOT_PATH,
        *,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        now_fn=time.time,
    ) -> None:
        self._path = Path(path)
        self._stale_after_s = float(stale_after_s)
        self._now_fn = now_fn
        if not math.isfinite(self._stale_after_s) or self._stale_after_s <= 0:
            raise ValueError("stale_after_s must be finite and > 0")

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> MarketReadResult:
        failure = probe_artifact_path(self._path)
        if failure == "MISSING":
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_MISSING",
                error_message="CryptoRadar MARKET snapshot not found.",
            )
        if failure == "INVALID_PATH":
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_INVALID_PATH",
                error_message="CryptoRadar MARKET snapshot path is not a regular file.",
            )
        if failure == "UNREADABLE":
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_UNREADABLE",
                error_message="CryptoRadar MARKET snapshot could not be read.",
            )

        try:
            raw = self._path.read_text(encoding="utf-8")
            doc = json.loads(raw)
        except (OSError, UnicodeError):
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_UNREADABLE",
                error_message="CryptoRadar MARKET snapshot could not be read.",
            )
        except json.JSONDecodeError as exc:
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_MALFORMED_JSON",
                error_message=str(exc),
            )

        if not validate_market_snapshot(doc):
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_INVALID_SCHEMA",
                error_message="CryptoRadar MARKET snapshot failed the closed schema/authority contract.",
            )

        generated = _parse_utc(doc["generated_at_utc"])
        assert generated is not None  # admitted by validate_market_snapshot
        generated_ts = generated.timestamp()
        age = max(0.0, float(self._now_fn()) - generated_ts)
        freshness = "STALE" if age > self._stale_after_s else "FRESH"

        return MarketReadResult(
            ok=True,
            snapshot=dict(doc),
            snapshot_age_s=age,
            freshness_classification=freshness,
        )


__all__ = [
    "DEFAULT_MARKET_SNAPSHOT_PATH",
    "DEFAULT_STALE_AFTER_S",
    "MarketReadResult",
    "MarketSnapshotReader",
    "validate_market_snapshot",
]
