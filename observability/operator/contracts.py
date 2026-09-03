"""Base contracts shared by every canonical observability domain.

Deterministic, serialization-safe, no side effects. See
docs/observability/OPERATOR_OBSERVABILITY_ARCHITECTURE.md for the
architectural rationale and docs/observability/OPERATOR_DISPLAY_CONTRACT.md
for how presentation adapters (Telegram, dashboards, API) must consume
these contracts without reinterpreting them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
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

# Closed vocabulary for DomainSnapshot.status (mission remediation §5 —
# independent review). Without a closed set, OperatorSummary could only
# guess which free-text status strings mean "healthy" via an undocumented
# allowlist (e.g. "HEALTHY"/"PASSING", which no domain in this codebase
# actually emits) and could misclassify a legitimate but unrecognized
# healthy status (ACTIVE/AVAILABLE/NOMINAL/...) as needing attention.
# OK is the only member that represents "no attention needed" — see
# domains/operator_summary.py's _HEALTHY_STATUSES, which is tested against
# this exact set so the classification can never silently drift.
DOMAIN_STATUSES = frozenset({"OK", "DEGRADED", "ATTENTION_REQUIRED", "UNAVAILABLE"})


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

# UNKNOWN/UNAVAILABLE/NOT_APPLICABLE are "no observation exists" states:
# there is nothing to carry, so value must be None. EMPTY is deliberately
# NOT in this set — EMPTY means the source *was* successfully observed and
# the measured collection/string is genuinely empty, so it must carry that
# real (empty) value, not None. See ObservedValue.__post_init__ for the
# EMPTY-specific shape check this implies.
_NONE_REQUIRED_SEMANTICS = frozenset(
    {
        NullSemantics.UNKNOWN,
        NullSemantics.UNAVAILABLE,
        NullSemantics.NOT_APPLICABLE,
    }
)


def to_jsonable(value: Any) -> Any:
    """Recursively convert any contracts value into a JSON-safe structure,
    without reinterpreting it — the same "format, never reinterpret" rule
    OPERATOR_DISPLAY_CONTRACT.md imposes on presentation adapters applies
    here to serialization.

    Handles, in order: Enum -> ``.value``; ``datetime`` -> ISO-8601;
    ``None``/``str``/``int``/``float``/``bool`` as-is; any dataclass
    exposing its own ``to_dict()`` (``ObservedValue``, ``PercentageMetric``)
    -> that method's result, itself recursively converted; any other plain
    dataclass -> its fields, recursively converted; ``Mapping`` -> a dict
    with string keys; ``list``/``tuple``/``set``/``frozenset`` -> a list.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    to_dict_method = getattr(value, "to_dict", None)
    if callable(to_dict_method) and is_dataclass(value):
        return to_jsonable(to_dict_method())
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in value]
    raise TypeError(f"Cannot serialize value of type {type(value)!r} to a JSON-safe structure: {value!r}")


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
        if self.semantics in _NONE_REQUIRED_SEMANTICS and self.value is not None:
            raise ValueError(
                f"ObservedValue with semantics={self.semantics} must carry value=None, "
                f"got {self.value!r}"
            )
        if self.semantics == NullSemantics.PRESENT and self.value is None:
            raise ValueError(
                "ObservedValue with semantics=PRESENT must carry a non-None value; "
                "use NullSemantics.ZERO/FALSE/EMPTY for a present-but-empty value"
            )
        if self.semantics == NullSemantics.EMPTY:
            if self.value is None:
                raise ValueError(
                    "ObservedValue with semantics=EMPTY must carry the actual observed "
                    "empty value (e.g. '', [], {}, set()), not None — EMPTY means the "
                    "source was successfully observed and is genuinely empty, which is "
                    "a different state from UNKNOWN/UNAVAILABLE/NOT_APPLICABLE"
                )
            try:
                is_empty = len(self.value) == 0
            except TypeError as exc:
                raise ValueError(
                    "ObservedValue with semantics=EMPTY requires a sized value "
                    f"(str/list/tuple/dict/set/frozenset), got {type(self.value)!r}"
                ) from exc
            if not is_empty:
                raise ValueError(
                    "ObservedValue with semantics=EMPTY must carry an empty collection "
                    f"or string, got non-empty value {self.value!r}"
                )

    @property
    def is_available(self) -> bool:
        return self.semantics not in (NullSemantics.UNKNOWN, NullSemantics.UNAVAILABLE)

    def to_dict(self) -> Mapping[str, Any]:
        return {"value": to_jsonable(self.value), "semantics": self.semantics.value}


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
        if self.status not in DOMAIN_STATUSES:
            raise ValueError(
                f"Unknown status {self.status!r} for domain {self.domain!r}; "
                f"must be one of {sorted(DOMAIN_STATUSES)} (DomainSnapshot.status is a "
                "closed vocabulary so composers never have to guess which values mean "
                "'healthy' — see contracts.DOMAIN_STATUSES)"
            )

    def to_dict(self) -> Mapping[str, Any]:
        """Serialize the generic spine AND every field a concrete subclass
        adds (mission remediation §3): ``dataclasses.fields(self)`` walks
        the full inheritance chain, so a domain module never needs its own
        serializer — adding a field to a ``*Snapshot`` subclass is enough
        for it to appear here automatically."""
        return {f.name: to_jsonable(getattr(self, f.name)) for f in fields(self)}
