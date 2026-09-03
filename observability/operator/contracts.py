"""Base contracts shared by every canonical observability domain.

Deterministic, serialization-safe, no side effects. See
docs/observability/OPERATOR_OBSERVABILITY_ARCHITECTURE.md for the
architectural rationale and docs/observability/OPERATOR_DISPLAY_CONTRACT.md
for how presentation adapters (Telegram, dashboards, API) must consume
these contracts without reinterpreting them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, Mapping, Optional, TypeVar

SCHEMA_VERSION = "1.0.0"

DOMAIN_IDS = frozenset(
    {
        "system_health",
        "market_state",
        "decision_pipeline",
        "attrition",
        "portfolio_state",
        "execution_state",
        "data_freshness",
        "regret_state",
        "adaptive_learning",
        "disk_io",
        "operator_summary",
    }
)


class FreshnessStatus(str, Enum):
    """Canonical freshness vocabulary (mission §28 — domain-specific, never
    a single global "snapshot age" reused across unrelated domains)."""

    FRESH = "FRESH"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class NullSemantics(str, Enum):
    """Distinguishes *why* a value is absent or zero (mission §27).

    0 rejected trades != rejection dataset unavailable.
    0 API balance != API account unreachable.
    No canonical Regret event yet != fresh Regret with zero events.
    """

    PRESENT = "PRESENT"
    ZERO = "ZERO"
    FALSE = "FALSE"
    EMPTY = "EMPTY"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


T = TypeVar("T")

_ABSENT_SEMANTICS = frozenset(
    {
        NullSemantics.UNKNOWN,
        NullSemantics.UNAVAILABLE,
        NullSemantics.NOT_APPLICABLE,
        NullSemantics.EMPTY,
    }
)


@dataclass(frozen=True)
class ObservedValue(Generic[T]):
    """A value paired with explicit null/unknown semantics.

    A bare ``None`` or ``0`` can never distinguish "measured and it's
    zero" from "we don't know" or "the source isn't reachable" — this
    wrapper makes that distinction a first-class, testable field instead
    of a convention someone has to remember.
    """

    value: Optional[T]
    semantics: NullSemantics = NullSemantics.PRESENT

    def __post_init__(self) -> None:
        if self.semantics in _ABSENT_SEMANTICS and self.value is not None:
            raise ValueError(
                f"ObservedValue with semantics={self.semantics} must carry value=None, "
                f"got {self.value!r}"
            )
        if self.semantics == NullSemantics.PRESENT and self.value is None:
            raise ValueError(
                "ObservedValue with semantics=PRESENT must carry a non-None value; "
                "use NullSemantics.ZERO/FALSE/EMPTY for a present-but-empty value"
            )

    @property
    def is_available(self) -> bool:
        return self.semantics not in (NullSemantics.UNKNOWN, NullSemantics.UNAVAILABLE)

    def to_dict(self) -> Mapping[str, Any]:
        return {"value": self.value, "semantics": self.semantics.value}


def observed(value: T) -> ObservedValue[T]:
    """Wrap a genuinely-measured value (may be 0/False/empty-collection)."""
    if value == 0 and not isinstance(value, bool):
        return ObservedValue(value=0, semantics=NullSemantics.ZERO)
    if value is False:
        return ObservedValue(value=False, semantics=NullSemantics.FALSE)
    if isinstance(value, (str, list, tuple, dict, frozenset, set)) and len(value) == 0:
        return ObservedValue(value=value, semantics=NullSemantics.EMPTY)
    return ObservedValue(value=value, semantics=NullSemantics.PRESENT)


def unknown() -> ObservedValue[Any]:
    """No observation exists yet (not the same as a stale one)."""
    return ObservedValue(value=None, semantics=NullSemantics.UNKNOWN)


def unavailable() -> ObservedValue[Any]:
    """The source could not be reached / read this cycle."""
    return ObservedValue(value=None, semantics=NullSemantics.UNAVAILABLE)


def not_applicable() -> ObservedValue[Any]:
    """The field has no meaning in this context (e.g. real-account equity
    when no real account is configured)."""
    return ObservedValue(value=None, semantics=NullSemantics.NOT_APPLICABLE)


def stale(value: T) -> ObservedValue[T]:
    """A last-known value that is known to be outdated. Callers must not
    treat this as a fresh observation (mission §27/§28: stale != healthy)."""
    return ObservedValue(value=value, semantics=NullSemantics.STALE)


@dataclass(frozen=True)
class PercentageMetric:
    """A ratio with an explicit, non-ambiguous numerator/denominator
    (mission §9 — never display a percentage without defining both)."""

    numerator: int
    denominator: int
    numerator_label: str
    denominator_label: str

    def __post_init__(self) -> None:
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("numerator/denominator must be non-negative")
        if self.numerator > self.denominator:
            raise ValueError("numerator cannot exceed denominator")

    @property
    def ratio(self) -> Optional[float]:
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    @property
    def pct(self) -> Optional[float]:
        r = self.ratio
        return None if r is None else round(r * 100, 2)

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "numerator_label": self.numerator_label,
            "denominator_label": self.denominator_label,
            "pct": self.pct,
        }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DomainSnapshot:
    """Base contract every canonical domain snapshot extends.

    Not every field makes sense for every domain (mission §17) — domains
    are free to leave ``source_version``/``evidence`` minimal, but the
    identity/provenance/freshness spine is mandatory everywhere.
    """

    domain: str
    observed_at_utc: datetime
    source: str
    freshness: FreshnessStatus
    status: str
    schema_version: str = SCHEMA_VERSION
    source_version: Optional[str] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.domain not in DOMAIN_IDS:
            raise ValueError(f"Unknown domain id: {self.domain!r}")
        if self.observed_at_utc.tzinfo is None:
            raise ValueError("observed_at_utc must be timezone-aware (UTC)")

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "domain": self.domain,
            "observed_at_utc": self.observed_at_utc.isoformat(),
            "source": self.source,
            "source_version": self.source_version,
            "freshness": self.freshness.value,
            "status": self.status,
            "evidence": dict(self.evidence),
        }
