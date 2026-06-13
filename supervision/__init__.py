"""Supervision — circuit breakers, alerts, monitoring, self-healing.

Public API:
  ComponentCircuitBreaker : 4-state CB with exponential backoff and fallback
  KillSwitch              : emergency halt mechanism
  AlertManager            : multi-channel alert dispatch
"""

from supervision.alert_manager import AlertManager
from supervision.circuit_breaker_robust import ComponentCircuitBreaker
from supervision.kill_switch import (  # legacy — préférer KillSwitchHardened
    TelegramKillSwitch,
)
from supervision.killswitch_hardened import KillSwitchHardened

__all__ = [
    "ComponentCircuitBreaker",
    "TelegramKillSwitch",
    "AlertManager",
    "KillSwitchHardened",
]
