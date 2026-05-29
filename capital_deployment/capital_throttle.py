"""
capital_deployment/capital_throttle.py — F-01 Capital Throttle

Enforce capital limits per deployment phase.
Blocks position sizing above phase capital ceiling.

F-01: max 1% du capital total, plafonné à 100 EUR absolument.
F-02: 5%, F-03: 25%, F-04: 50%, F-05: 100%.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("capital_deployment.capital_throttle")

PHASE_CONFIGS: dict[str, dict] = {
    "F-01": {"capital_pct": 0.01, "max_capital_eur": 100.0, "min_duration_days": 7},
    "F-02": {"capital_pct": 0.05, "max_capital_eur": None, "min_duration_days": 14},
    "F-03": {"capital_pct": 0.25, "max_capital_eur": None, "min_duration_days": 21},
    "F-04": {"capital_pct": 0.50, "max_capital_eur": None, "min_duration_days": 30},
    "F-05": {"capital_pct": 1.00, "max_capital_eur": None, "min_duration_days": 0},
}

PHASE_ORDER = ["F-01", "F-02", "F-03", "F-04", "F-05"]


@dataclass
class PhaseAllocation:
    phase: str
    total_capital: float
    allocated_capital: float
    capital_pct: float
    min_duration_days: int
    started_at: float = field(default_factory=time.time)

    def days_elapsed(self) -> float:
        return (time.time() - self.started_at) / 86400.0

    def time_requirement_met(self) -> bool:
        return self.days_elapsed() >= self.min_duration_days

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "total_capital": round(self.total_capital, 2),
            "allocated_capital": round(self.allocated_capital, 2),
            "capital_pct": self.capital_pct,
            "min_duration_days": self.min_duration_days,
            "days_elapsed": round(self.days_elapsed(), 3),
            "time_requirement_met": self.time_requirement_met(),
        }


class CapitalThrottle:
    """
    Enforce capital limits per deployment phase.

    Usage:
        throttle = CapitalThrottle(total_capital=10_000.0, phase="F-01")
        safe_size = throttle.throttled_size(500.0)   # → 100.0 (F-01 cap)
    """

    def __init__(
        self,
        total_capital: float,
        phase: str = "F-01",
        started_at: Optional[float] = None,
    ) -> None:
        if phase not in PHASE_CONFIGS:
            raise ValueError(f"Phase inconnue: {phase}. Valides: {list(PHASE_CONFIGS)}")
        if total_capital <= 0:
            raise ValueError(f"total_capital doit être > 0, reçu: {total_capital}")

        self._total_capital = total_capital
        self._phase = phase
        cfg = PHASE_CONFIGS[phase]

        raw = total_capital * cfg["capital_pct"]
        cap = cfg.get("max_capital_eur")
        if cap is not None:
            raw = min(raw, cap)

        self._allocation = PhaseAllocation(
            phase=phase,
            total_capital=total_capital,
            allocated_capital=raw,
            capital_pct=cfg["capital_pct"],
            min_duration_days=cfg["min_duration_days"],
            started_at=started_at or time.time(),
        )

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def allocated_capital(self) -> float:
        return self._allocation.allocated_capital

    def max_single_position(self, max_pct_of_phase: float = 0.20) -> float:
        """Max single position = 20% of phase capital by default."""
        return self._allocation.allocated_capital * max_pct_of_phase

    def is_within_limit(self, order_size: float) -> bool:
        return 0 < order_size <= self._allocation.allocated_capital

    def throttled_size(self, requested: float) -> float:
        """Clamp requested order size to phase capital ceiling."""
        if requested <= 0:
            return 0.0
        return min(requested, self._allocation.allocated_capital)

    def allocation(self) -> PhaseAllocation:
        return self._allocation

    def advance_to(self, next_phase: str, certified: bool = False) -> "CapitalThrottle":
        """Return a new throttle for the next phase. Requires certified=True."""
        if not certified:
            raise PermissionError(
                f"Avancement vers {next_phase} refusé — phase {self._phase} non certifiée."
            )
        if next_phase not in PHASE_CONFIGS:
            raise ValueError(f"Phase cible inconnue: {next_phase}")
        return CapitalThrottle(self._total_capital, next_phase)

    def next_phase(self) -> Optional[str]:
        idx = PHASE_ORDER.index(self._phase)
        if idx + 1 < len(PHASE_ORDER):
            return PHASE_ORDER[idx + 1]
        return None
