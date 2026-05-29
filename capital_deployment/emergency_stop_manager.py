"""
capital_deployment/emergency_stop_manager.py — F-06 Emergency Stop Manager

8 critères d'arrêt immédiat selon la spec P10-F :
  1. Drawdown > seuil phase + 50%
  2. 3 trades consécutifs en erreur technique
  3. API key compromise
  4. Perte de connexion exchange > 5 min
  5. AnomalyGovernance > 3 suspensions / heure
  6. BlackBox inaccessible > 2 cycles
  7. Signature invalide sur une décision
  8. KillSwitch déclenché (local ou Telegram)

N'importe quel critère → arrêt immédiat + appel halt_fn.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("capital_deployment.emergency_stop_manager")


class EmergencyCriteria(str, Enum):
    DRAWDOWN_EXCEEDED = "drawdown_exceeded"
    CONSECUTIVE_TECH_ERRORS = "consecutive_tech_errors"
    API_KEY_COMPROMISED = "api_key_compromised"
    EXCHANGE_CONNECTION_LOST = "exchange_connection_lost"
    ANOMALY_SUSPENSIONS = "anomaly_suspensions"
    BLACKBOX_INACCESSIBLE = "blackbox_inaccessible"
    INVALID_SIGNATURE = "invalid_signature"
    KILLSWITCH_TRIGGERED = "killswitch_triggered"


@dataclass
class EmergencyTrigger:
    criteria: EmergencyCriteria
    triggered_at: float
    details: str
    phase: str = ""

    def to_dict(self) -> dict:
        return {
            "criteria": self.criteria.value,
            "triggered_at": round(self.triggered_at, 3),
            "details": self.details,
            "phase": self.phase,
        }


# Phase drawdown limits (fraction). Emergency = limit * 1.5.
_PHASE_DRAWDOWN_LIMITS: dict[str, float] = {
    "F-01": 0.02,
    "F-02": 0.04,
    "F-03": 0.08,
    "F-04": 0.12,
    "F-05": 0.20,
}


class EmergencyStopManager:
    """
    Monitors all 8 F-06 emergency criteria.
    Any match → immediate halt + halt_fn() call (KillSwitch).

    State resets only via reset() after a human review.

    Usage:
        mgr = EmergencyStopManager(phase="F-01")
        trigger = mgr.check(metrics)
        if trigger:
            print(f"HALT: {trigger.criteria.value}")
    """

    def __init__(
        self,
        phase: str = "F-01",
        max_consecutive_errors: int = 3,
        max_exchange_downtime_s: float = 300.0,
        max_suspensions_per_hour: int = 3,
        max_blackbox_inaccessible_cycles: int = 2,
        halt_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._phase = phase
        # Drawdown emergency = phase_limit * 1.5
        self._drawdown_emergency = _PHASE_DRAWDOWN_LIMITS.get(phase, 0.02) * 1.5
        self._max_consec_errors = max_consecutive_errors
        self._max_exchange_downtime = max_exchange_downtime_s
        self._max_suspensions = max_suspensions_per_hour
        self._max_bb_cycles = max_blackbox_inaccessible_cycles
        self._halt_fn = halt_fn

        self._halted = False
        self._active_triggers: list[EmergencyTrigger] = []
        self._history: list[EmergencyTrigger] = []

        # Sliding window for AnomalyGovernance suspensions (1h)
        self._suspension_timestamps: list[float] = []

    # ── Vérification ────────────────────────────────────────────────────────────

    def check(self, metrics: dict) -> Optional[EmergencyTrigger]:
        """Check all 8 criteria. Returns the first triggered one (or None)."""
        triggers = self.check_all(metrics)
        return triggers[0] if triggers else None

    def check_all(self, metrics: dict) -> list[EmergencyTrigger]:
        """Check all 8 criteria. Returns every triggered one."""
        now = time.time()
        triggers: list[EmergencyTrigger] = []

        # 1. Drawdown exceeded
        dd = float(metrics.get("current_drawdown", 0.0))
        if dd > self._drawdown_emergency:
            triggers.append(
                EmergencyTrigger(
                    criteria=EmergencyCriteria.DRAWDOWN_EXCEEDED,
                    triggered_at=now,
                    details=f"drawdown {dd:.1%} > urgence {self._drawdown_emergency:.1%}",
                    phase=self._phase,
                )
            )

        # 2. Consecutive technical errors ≥ 3
        consec = int(metrics.get("consecutive_tech_errors", 0))
        if consec >= self._max_consec_errors:
            triggers.append(
                EmergencyTrigger(
                    criteria=EmergencyCriteria.CONSECUTIVE_TECH_ERRORS,
                    triggered_at=now,
                    details=f"{consec} erreurs techniques consécutives",
                    phase=self._phase,
                )
            )

        # 3. API key compromised
        if metrics.get("api_key_compromised", False):
            triggers.append(
                EmergencyTrigger(
                    criteria=EmergencyCriteria.API_KEY_COMPROMISED,
                    triggered_at=now,
                    details="Tentative d'accès non authentifié détectée",
                    phase=self._phase,
                )
            )

        # 4. Exchange down > 5 min
        down_s = float(metrics.get("exchange_down_s", 0.0))
        if down_s > self._max_exchange_downtime:
            triggers.append(
                EmergencyTrigger(
                    criteria=EmergencyCriteria.EXCHANGE_CONNECTION_LOST,
                    triggered_at=now,
                    details=f"Exchange inaccessible depuis {down_s:.0f}s (seuil {self._max_exchange_downtime:.0f}s)",
                    phase=self._phase,
                )
            )

        # 5. AnomalyGovernance suspensions > 3/h
        self._suspension_timestamps = [
            t for t in self._suspension_timestamps if now - t < 3600.0
        ]
        new_susp = int(metrics.get("new_anomaly_suspensions", 0))
        for _ in range(new_susp):
            self._suspension_timestamps.append(now)
        if len(self._suspension_timestamps) > self._max_suspensions:
            triggers.append(
                EmergencyTrigger(
                    criteria=EmergencyCriteria.ANOMALY_SUSPENSIONS,
                    triggered_at=now,
                    details=f"{len(self._suspension_timestamps)} suspensions AnomalyGovernance en 1h",
                    phase=self._phase,
                )
            )

        # 6. BlackBox inaccessible > 2 cycles
        bb_cycles = int(metrics.get("blackbox_inaccessible_cycles", 0))
        if bb_cycles > self._max_bb_cycles:
            triggers.append(
                EmergencyTrigger(
                    criteria=EmergencyCriteria.BLACKBOX_INACCESSIBLE,
                    triggered_at=now,
                    details=f"BlackBox inaccessible {bb_cycles} cycles consécutifs",
                    phase=self._phase,
                )
            )

        # 7. Signature invalide sur une décision
        if metrics.get("invalid_signature_detected", False):
            triggers.append(
                EmergencyTrigger(
                    criteria=EmergencyCriteria.INVALID_SIGNATURE,
                    triggered_at=now,
                    details="Signature Ed25519 invalide détectée sur une décision",
                    phase=self._phase,
                )
            )

        # 8. KillSwitch déclenché
        if metrics.get("killswitch_triggered", False):
            triggers.append(
                EmergencyTrigger(
                    criteria=EmergencyCriteria.KILLSWITCH_TRIGGERED,
                    triggered_at=now,
                    details="KillSwitch déclenché (local ou Telegram)",
                    phase=self._phase,
                )
            )

        if triggers:
            self._active_triggers.extend(triggers)
            self._history.extend(triggers)
            if not self._halted:
                self._halted = True
                reason = "; ".join(t.criteria.value for t in triggers)
                _log.critical("[EmergencyStop] HALT %s — %s", self._phase, reason)
                if self._halt_fn:
                    try:
                        self._halt_fn(reason)
                    except Exception as exc:
                        _log.error("[EmergencyStop] halt_fn error: %s", exc)

        return triggers

    # ── Contrôle manuel ──────────────────────────────────────────────────────────

    def trigger_stop(self, reason: str) -> None:
        """Programmatic emergency stop (e.g., operator command)."""
        t = EmergencyTrigger(
            criteria=EmergencyCriteria.KILLSWITCH_TRIGGERED,
            triggered_at=time.time(),
            details=f"Stop manuel: {reason}",
            phase=self._phase,
        )
        self._active_triggers.append(t)
        self._history.append(t)
        if not self._halted:
            self._halted = True
            _log.critical("[EmergencyStop] Stop manuel: %s", reason)
            if self._halt_fn:
                try:
                    self._halt_fn(reason)
                except Exception:
                    pass

    def reset(self) -> None:
        """Reset after human review. Clears active state, preserves history."""
        self._active_triggers.clear()
        self._suspension_timestamps.clear()
        self._halted = False
        _log.info("[EmergencyStop] Reset après révision humaine")

    # ── État ─────────────────────────────────────────────────────────────────────

    def is_emergency_active(self) -> bool:
        return self._halted

    def active_triggers(self) -> list[dict]:
        return [t.to_dict() for t in self._active_triggers]

    def history(self, n: int = 20) -> list[dict]:
        return [t.to_dict() for t in self._history[-n:]]

    def criteria_count(self) -> int:
        """Number of distinct emergency criteria defined (always 8)."""
        return len(EmergencyCriteria)
