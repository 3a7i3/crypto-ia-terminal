"""Read-side policy. Initial values are TEST values validated by nobody yet.

Changing a value changes what the reader reports (late, coverage, OI change); it
never rewrites stored observations. No purge exists in this lot: the disk budget
and retention days are only reported against the measured occupancy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from decimal import Decimal
import json
from pathlib import Path

from observability.market_stress import metrics


@dataclass(frozen=True)
class PositioningPolicy:
    late_after_ms: int = 120_000           # received - source time above this => LATE
    min_coverage: str = "0.8"              # share of expected points with comparable OI
    min_tolerance_ms: int = 60_000         # point tolerance = max(min_tolerance_ms, cadence)
    max_age_ms: int = 600_000              # freshness of the latest observation
    history_max_rows: int = 10_000         # hard bound of one history read
    disk_budget_bytes: int = 5_000_000_000  # HYPOTHESIS, reported only
    retention_days: int = 365              # HYPOTHESIS, reported only
    purge_enabled: bool = False            # must stay False in this lot

    def __post_init__(self):
        for name in ("late_after_ms", "min_tolerance_ms", "max_age_ms", "history_max_rows",
                     "disk_budget_bytes", "retention_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("POLICY_INVALID: %s" % name)
        coverage = metrics.number(self.min_coverage)
        if coverage is None or not Decimal(0) < coverage <= Decimal(1):
            raise ValueError("POLICY_INVALID: min_coverage")
        if self.history_max_rows < 1:
            raise ValueError("POLICY_INVALID: history_max_rows")
        if self.purge_enabled is not False:
            raise ValueError("POLICY_INVALID: purge is not available in this lot")

    @property
    def coverage(self) -> Decimal:
        return Decimal(self.min_coverage)

    def tolerance_ms(self, cadence_s):
        return max(self.min_tolerance_ms, cadence_s * 1000)

    def as_dict(self):
        return asdict(self)

    @classmethod
    def from_file(cls, path):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known - {"_comment"})
        if unknown:
            raise ValueError("POLICY_UNKNOWN_FIELD: %s" % unknown[0])
        return cls(**{k: v for k, v in raw.items() if k in known})
