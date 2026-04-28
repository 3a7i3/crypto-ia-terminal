"""Validation et nettoyage des bougies OHLCV avant utilisation."""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_PRICE_FIELDS = ("open", "high", "low", "close")
_MAX_PRICE_RATIO = 10.0  # high/low > 10x → spike suspect


@dataclass
class ValidationReport:
    total: int = 0
    valid: int = 0
    dropped: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)

    @property
    def real_ratio(self) -> float:
        live = self.source_counts.get("ccxt_live", 0)
        return live / self.total if self.total else 0.0

    def log(self, symbol: str = "") -> None:
        prefix = f"[{symbol}] " if symbol else ""
        if self.dropped:
            logger.warning(
                "%sOHLCV validation: %d/%d bougies valides, %d rejetées — %s",
                prefix, self.valid, self.total, self.dropped, self.reasons,
            )
        else:
            logger.debug(
                "%sOHLCV validation: %d/%d OK (source: %s)",
                prefix, self.valid, self.total, self.source_counts,
            )


def _check_candle(c: dict) -> str | None:
    """Retourne la raison du rejet ou None si valide."""
    for field_name in _PRICE_FIELDS + ("volume",):
        val = c.get(field_name)
        if val is None:
            return f"missing_{field_name}"
        try:
            val = float(val)
        except (TypeError, ValueError):
            return f"non_numeric_{field_name}"
        if math.isnan(val) or math.isinf(val):
            return f"nan_inf_{field_name}"

    o = float(c["open"])
    h = float(c["high"])
    l = float(c["low"])
    cl = float(c["close"])
    v = float(c["volume"])

    if o <= 0 or cl <= 0 or h <= 0 or l <= 0:
        return "non_positive_price"
    if v < 0:
        return "negative_volume"
    if h < max(o, cl) * 0.9999:
        return "high_below_oc"
    if l > min(o, cl) * 1.0001:
        return "low_above_oc"
    if l > 0 and h / l > _MAX_PRICE_RATIO:
        return "price_spike"

    return None


def validate_candles(
    candles: list[dict],
    symbol: str = "",
) -> tuple[list[dict], ValidationReport]:
    """
    Filtre les bougies invalides et retourne (bougies_valides, rapport).

    Usage:
        clean, report = validate_candles(raw_candles, symbol="BTCUSDT")
        if report.dropped:
            report.log(symbol)
    """
    valid: list[dict] = []
    reasons: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    for c in candles:
        src = c.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

        issue = _check_candle(c)
        if issue is None:
            valid.append(c)
        else:
            reasons[issue] = reasons.get(issue, 0) + 1

    report = ValidationReport(
        total=len(candles),
        valid=len(valid),
        dropped=len(candles) - len(valid),
        reasons=reasons,
        source_counts=source_counts,
    )
    report.log(symbol)
    return valid, report


def is_series_fresh(candles: list[dict], max_age_seconds: float = 3600.0) -> bool:
    """Vérifie si la dernière bougie est récente (< max_age_seconds)."""
    if not candles:
        return False
    try:
        from datetime import datetime, timezone
        last_ts = candles[-1].get("timestamp", "")
        if not last_ts:
            return True
        dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age <= max_age_seconds
    except Exception:
        return True
