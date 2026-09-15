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
from typing import Any, Dict, Mapping, Optional

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
    if row["dominant_side"] not in {"LONG", "SHORT", "MIXED"}:
        return False
    if not _finite_number(row["dominance_pct"]):
        return False
    if not 0.0 <= float(row["dominance_pct"]) <= 100.0:
        return False
    if not isinstance(row["regime"], str):
        return False
    return True


def validate_market_snapshot(doc: Any) -> bool:
    """Closed-schema admission gate for producer-authored MARKET data."""

    if not isinstance(doc, dict):
        return False
    if set(doc) != _TOP_LEVEL_KEYS:
        return False
    if doc["schema_version"] != "1.0.0":
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
    if doc["source_updated_at_utc"] is not None and not isinstance(
        doc["source_updated_at_utc"], str
    ):
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
    return True


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
        if not self._path.exists():
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_MISSING",
                error_message=f"CryptoRadar MARKET snapshot not found: {self._path}",
            )
        if not self._path.is_file():
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_INVALID_PATH",
                error_message="CryptoRadar MARKET snapshot path is not a regular file.",
            )

        try:
            raw = self._path.read_text(encoding="utf-8")
            doc = json.loads(raw)
        except (OSError, UnicodeError) as exc:
            return MarketReadResult(
                ok=False,
                error_code="MARKET_SNAPSHOT_UNREADABLE",
                error_message=str(exc),
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
