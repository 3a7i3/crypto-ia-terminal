"""Freshness classification helper.

Freshness is source-specific (mission §28): this function classifies a
single age-vs-threshold pair. It never invents a threshold — callers
that don't have an evidence-backed threshold must pass
``degraded_threshold_s=None, stale_threshold_s=None`` and accept
``FreshnessStatus.UNKNOWN`` for anything but the "no data at all" case.
"""

from __future__ import annotations

from typing import Optional

from observability.operator.contracts import FreshnessStatus


def classify_freshness(
    age_seconds: Optional[float],
    *,
    fresh_threshold_s: Optional[float],
    stale_threshold_s: Optional[float],
) -> FreshnessStatus:
    """Classify freshness from an observed age.

    - ``age_seconds is None`` -> UNKNOWN (no observation exists yet).
    - Both thresholds ``None`` -> UNKNOWN (no evidence-backed threshold
      was ever defined for this source; mission §18 forbids inventing one).
    - ``age_seconds <= fresh_threshold_s`` -> FRESH.
    - ``fresh_threshold_s < age_seconds <= stale_threshold_s`` -> DEGRADED.
    - ``age_seconds > stale_threshold_s`` -> STALE.
    """
    if age_seconds is None:
        return FreshnessStatus.UNKNOWN
    if fresh_threshold_s is None or stale_threshold_s is None:
        return FreshnessStatus.UNKNOWN
    if stale_threshold_s < fresh_threshold_s:
        raise ValueError("stale_threshold_s must be >= fresh_threshold_s")
    if age_seconds < 0:
        raise ValueError("age_seconds must be non-negative")
    if age_seconds <= fresh_threshold_s:
        return FreshnessStatus.FRESH
    if age_seconds <= stale_threshold_s:
        return FreshnessStatus.DEGRADED
    return FreshnessStatus.STALE
