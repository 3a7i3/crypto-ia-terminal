"""
Telemetry — unified system snapshot aggregator.

Single call to telemetry.snapshot() returns the full observable state:
  - system state machine
  - module registry (all health statuses)
  - live topology
  - metrics bus (gauges + counters)
  - heartbeat system
  - crisis level

Usage:
    from observability.telemetry import telemetry
    state = telemetry.snapshot()          # full dict
    print(telemetry.render_status_bar())  # one-line cockpit status
"""

from __future__ import annotations

import time
from enum import Enum, auto
from typing import Any, Dict

from observability.heartbeat_system import heartbeat_system
from observability.live_topology import live_topology
from observability.metrics_bus import metrics_bus
from system.module_registry import ModuleStatus, module_registry
from system.state_manager import SystemState, state_manager


class CrisisLevel(Enum):
    NORMAL = auto()
    WARNING = auto()
    DEGRADED = auto()
    CRITICAL = auto()
    PANIC = auto()


# Map system states to crisis levels
_STATE_CRISIS = {
    SystemState.BOOTING: CrisisLevel.WARNING,
    SystemState.SYNCING: CrisisLevel.WARNING,
    SystemState.READY: CrisisLevel.NORMAL,
    SystemState.TRADING: CrisisLevel.NORMAL,
    SystemState.RISK_OFF: CrisisLevel.WARNING,
    SystemState.DEGRADED: CrisisLevel.DEGRADED,
    SystemState.RECOVERY: CrisisLevel.DEGRADED,
    SystemState.SHUTDOWN: CrisisLevel.WARNING,
    SystemState.PANIC: CrisisLevel.PANIC,
}

_CRISIS_LABEL = {
    CrisisLevel.NORMAL: "[== NORMAL  ]",
    CrisisLevel.WARNING: "[/\\ WARNING ]",
    CrisisLevel.DEGRADED: "[** DEGRADED]",
    CrisisLevel.CRITICAL: "[!! CRITICAL]",
    CrisisLevel.PANIC: "[XX PANIC   ]",
}


class Telemetry:
    """Aggregates all observability data into a single snapshot."""

    def crisis_level(self) -> CrisisLevel:
        """Compute overall crisis level from state + health score."""
        state = state_manager.state
        base = _STATE_CRISIS.get(state, CrisisLevel.WARNING)
        score = module_registry.system_health_score()

        # Escalate based on health score
        if state == SystemState.PANIC:
            return CrisisLevel.PANIC
        if not module_registry.all_critical_healthy():
            return CrisisLevel.CRITICAL
        if score < 0.5:
            return CrisisLevel.CRITICAL
        if score < 0.8:
            return max(base, CrisisLevel.DEGRADED, key=lambda x: x.value)
        return base

    def snapshot(self) -> Dict[str, Any]:
        crisis = self.crisis_level()
        return {
            "timestamp": time.time(),
            "crisis_level": crisis.name,
            "system_state": state_manager.state.name,
            "is_trading": state_manager.is_trading_allowed,
            "is_execution_allowed": state_manager.is_execution_allowed,
            "health_score": round(module_registry.system_health_score(), 3),
            "all_critical_healthy": module_registry.all_critical_healthy(),
            "state_machine": state_manager.snapshot(),
            "modules": module_registry.snapshot(),
            "topology": live_topology.snapshot(),
            "heartbeats": heartbeat_system.snapshot(),
            "metrics": metrics_bus.snapshot(),
        }

    def render_status_bar(self) -> str:
        """
        One-line cockpit bar suitable for a dashboard header or terminal.

        Example:
          [■ NORMAL  ] TRADING | health=0.97 | 14/14 alive | flow: ✓exchange → ✓risk → ✓exec
        """
        crisis = self.crisis_level()
        state = state_manager.state
        score = module_registry.system_health_score()
        hb = heartbeat_system.snapshot()
        alive = hb["alive"]
        total = hb["monitored_modules"]
        flow = live_topology.render_flow()

        label = _CRISIS_LABEL[crisis]
        return (
            f"{label} {state.name:<10} | "
            f"health={score:.2f} | "
            f"{alive}/{total} alive | "
            f"flow: {flow}"
        )

    def render_module_panel(self) -> str:
        """
        Multi-line status panel showing each module with a colored indicator.

        Example:
          [✓ GREEN ] exchange_connector   hb=0.3s  lat=8ms
          [✓ GREEN ] risk_engine          hb=1.2s  lat=22ms
          [✗ RED   ] execution_engine     UNHEALTHY  errors=3
        """
        lines = ["", "  MODULE STATUS", "  " + "-" * 55]
        for info in module_registry.all_modules():
            icon = {
                ModuleStatus.HEALTHY: "OK",
                ModuleStatus.DEGRADED: "~~",
                ModuleStatus.UNHEALTHY: "XX",
                ModuleStatus.STARTING: "..",
                ModuleStatus.STOPPED: "--",
                ModuleStatus.DISABLED: "//",
            }.get(info.status, "??")

            color = {
                ModuleStatus.HEALTHY: "GREEN ",
                ModuleStatus.DEGRADED: "YELLOW",
                ModuleStatus.UNHEALTHY: "RED   ",
                ModuleStatus.STARTING: "CYAN  ",
                ModuleStatus.STOPPED: "GREY  ",
                ModuleStatus.DISABLED: "GREY  ",
            }.get(info.status, "WHITE ")

            hb_age = f"hb={info.heartbeat_age:.1f}s"
            lat = f"lat={info.latency_ms:.0f}ms" if info.latency_ms else ""
            err = f"errors={info.error_count}" if info.error_count else ""
            parts = [p for p in [hb_age, lat, err] if p]
            detail = "  ".join(parts)

            lines.append(f"  [{icon} {color}] {info.name:<30} {detail}")

        lines.append("")
        return "\n".join(lines)


# Singleton
telemetry = Telemetry()
