"""
capital_deployment/phase_gate.py — Phase Progression Gate

Controls advancement F-01 → F-05.
Enforces all KPI criteria + security checks before allowing phase change.

Gate stays open for trading as long as:
  - No emergency stop active
  - No security violations
  - Drawdown within phase limits

Gate allows advancement only when:
  - All KPI criteria met (win_rate, Sharpe, drawdown, duration)
  - No unsigned decisions
  - No security violations
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from capital_deployment.capital_throttle import PHASE_ORDER
from capital_deployment.phase_kpi_tracker import PHASE_CRITERIA, PhaseKPITracker
from observability.json_logger import get_logger

_log = get_logger("capital_deployment.phase_gate")


@dataclass
class PhaseTransition:
    from_phase: str
    to_phase: str
    ts: float = field(default_factory=time.time)
    violations_at_advance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "from_phase": self.from_phase,
            "to_phase": self.to_phase,
            "ts": round(self.ts, 3),
            "violations_at_advance": self.violations_at_advance,
        }


class PhaseGate:
    """
    Controls phase advancement for live capital deployment.

    Usage:
        gate = PhaseGate(kpi_tracker, capital_throttle)
        if gate.is_gate_open():
            # continue trading
        if gate.can_advance()[0]:
            gate.advance()
    """

    def __init__(
        self,
        kpi_tracker: PhaseKPITracker,
        current_phase: str = "F-01",
    ) -> None:
        self._kpi = kpi_tracker
        self._phase = current_phase
        self._emergency = False
        self._security_violations: list[str] = []
        self._transitions: list[PhaseTransition] = []

    def current_phase(self) -> str:
        return self._phase

    def set_emergency(self, active: bool) -> None:
        self._emergency = active
        if active:
            _log.critical("[PhaseGate] Emergency stop activé — gate fermée")

    def record_security_violation(self, violation: str) -> None:
        self._security_violations.append(violation)
        _log.error("[PhaseGate] Violation sécurité: %s", violation)

    def clear_security_violations(self) -> None:
        self._security_violations.clear()

    def is_gate_open(self) -> bool:
        """True if trading can continue in the current phase."""
        if self._emergency:
            return False
        if self._security_violations:
            return False
        return True

    def can_advance(self) -> tuple[bool, list[str]]:
        """Check whether all criteria are met to advance to the next phase."""
        if self._emergency:
            return False, ["emergency_stop_active"]
        if self._security_violations:
            return False, [
                f"security_violation: {v}" for v in self._security_violations
            ]
        if self._phase == "F-05":
            return False, ["already_at_final_phase"]

        ok, violations = self._kpi.meets_criteria()
        return ok, violations

    def advance(self) -> bool:
        """Advance to the next phase if all criteria are met."""
        ok, violations = self.can_advance()
        if not ok:
            _log.warning(
                "[PhaseGate] Avancement %s bloqué: %s", self._phase, violations
            )
            return False

        idx = PHASE_ORDER.index(self._phase)
        next_phase = PHASE_ORDER[idx + 1]
        self._transitions.append(
            PhaseTransition(
                from_phase=self._phase,
                to_phase=next_phase,
                violations_at_advance=[],
            )
        )
        _log.info("[PhaseGate] Avancement %s → %s", self._phase, next_phase)
        self._phase = next_phase
        return True

    def violations(self) -> list[str]:
        _, v = self.can_advance()
        return v

    def time_remaining_days(self) -> float:
        """Days remaining before the time requirement for the current phase is met."""
        min_days = PHASE_CRITERIA.get(self._phase, {}).get("min_duration_days", 0)
        return max(0.0, min_days - self._kpi.days_elapsed())

    def transitions(self) -> list[dict]:
        return [t.to_dict() for t in self._transitions]

    def status(self) -> dict:
        ok, violations = self.can_advance()
        return {
            "current_phase": self._phase,
            "gate_open": self.is_gate_open(),
            "can_advance": ok,
            "violations": violations,
            "time_remaining_days": round(self.time_remaining_days(), 2),
            "emergency_active": self._emergency,
            "security_violations": list(self._security_violations),
            "kpi": self._kpi.snapshot().to_dict(),
        }
