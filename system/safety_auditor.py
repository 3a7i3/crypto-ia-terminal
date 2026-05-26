"""Safety audit layer for silent module failures.

The auditor does not restart components and does not place orders. It reads the
existing observability surfaces (module registry, heartbeat records, circuit
breakers) and returns one compact verdict that callers can use to block new
trades, degrade mode, or escalate to an operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from system.module_registry import (
    ModulePriority,
    ModuleRegistry,
    ModuleStatus,
    module_registry,
)


class SafetyMode(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    RISK_OFF = "risk_off"


@dataclass(frozen=True)
class SafetyIssue:
    module: str
    severity: str
    reason: str
    action: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "module": self.module,
            "severity": self.severity,
            "reason": self.reason,
            "action": self.action,
        }


@dataclass(frozen=True)
class SafetyVerdict:
    mode: SafetyMode
    block_new_trades: bool
    issues: tuple[SafetyIssue, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.mode == SafetyMode.NORMAL and not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "ok": self.ok,
            "block_new_trades": self.block_new_trades,
            "issues": [issue.as_dict() for issue in self.issues],
        }


class SystemSafetyAuditor:
    """Build a single safety verdict from runtime health signals."""

    def __init__(
        self,
        required_modules: Iterable[str] = (),
        critical_modules: Iterable[str] = (),
        max_error_count: int = 3,
    ) -> None:
        self.required_modules = set(required_modules)
        self.critical_modules = set(critical_modules) | self.required_modules
        self.max_error_count = max_error_count

    def inspect(
        self,
        registry: ModuleRegistry = module_registry,
        heartbeat: Any = None,
        circuit_breaker_registry: Any = None,
    ) -> SafetyVerdict:
        issues: list[SafetyIssue] = []

        modules = {info.name: info for info in registry.all_modules()}
        for name in sorted(self.required_modules):
            if name not in modules:
                issues.append(
                    SafetyIssue(
                        module=name,
                        severity="CRITICAL",
                        reason="required module is not registered",
                        action="register the module or disable the requirement",
                    )
                )

        for info in modules.values():
            critical = (
                info.priority == ModulePriority.CRITICAL
                or info.name in self.critical_modules
            )
            if info.status in {ModuleStatus.UNHEALTHY, ModuleStatus.DISABLED}:
                issues.append(
                    SafetyIssue(
                        module=info.name,
                        severity="CRITICAL" if critical else "HIGH",
                        reason=f"module status is {info.status.name}",
                        action=(
                            "block new trades until health recovers"
                            if critical
                            else "degrade optional workflows"
                        ),
                    )
                )
            elif info.status == ModuleStatus.DEGRADED:
                issues.append(
                    SafetyIssue(
                        module=info.name,
                        severity="HIGH" if critical else "MEDIUM",
                        reason="module is degraded",
                        action="inspect last_error and circuit breaker state",
                    )
                )

            if not info.is_alive and info.status not in {
                ModuleStatus.STOPPED,
                ModuleStatus.DISABLED,
            }:
                issues.append(
                    SafetyIssue(
                        module=info.name,
                        severity="CRITICAL" if critical else "HIGH",
                        reason="heartbeat timeout in module registry",
                        action="restart or isolate the module",
                    )
                )

            if info.error_count > self.max_error_count:
                issues.append(
                    SafetyIssue(
                        module=info.name,
                        severity="HIGH" if critical else "MEDIUM",
                        reason=f"error_count={info.error_count}",
                        action="route recent exceptions through ErrorBus audit",
                    )
                )

        if heartbeat is not None:
            for name in heartbeat.dead_modules():
                issues.append(
                    SafetyIssue(
                        module=name,
                        severity="HIGH",
                        reason="heartbeat monitor marks module dead",
                        action="verify process liveness and registry status",
                    )
                )

        if circuit_breaker_registry is not None:
            issues.extend(self._inspect_circuit_breakers(circuit_breaker_registry))

        return self._verdict(issues)

    def _inspect_circuit_breakers(self, registry: Any) -> list[SafetyIssue]:
        issues: list[SafetyIssue] = []
        try:
            snapshots = registry.snapshot_all()
        except Exception as exc:
            return [
                SafetyIssue(
                    module="circuit_breaker_registry",
                    severity="HIGH",
                    reason=f"snapshot failed: {exc}",
                    action="inspect circuit breaker registry",
                )
            ]

        for snap in snapshots:
            name = str(snap.get("name", "unknown"))
            state = str(snap.get("state", "unknown"))
            critical = name in self.critical_modules
            if state in {"degraded", "disabled"}:
                issues.append(
                    SafetyIssue(
                        module=name,
                        severity="CRITICAL" if critical else "HIGH",
                        reason=f"circuit breaker is {state}",
                        action=(
                            "use fallback and block critical order flow"
                            if critical
                            else "keep component isolated until recovery"
                        ),
                    )
                )
            elif state == "unstable":
                issues.append(
                    SafetyIssue(
                        module=name,
                        severity="MEDIUM",
                        reason="circuit breaker is unstable",
                        action="respect backoff and monitor next recovery",
                    )
                )
        return issues

    def _verdict(self, issues: list[SafetyIssue]) -> SafetyVerdict:
        block = any(
            issue.severity == "CRITICAL"
            or (
                issue.module in self.critical_modules
                and issue.severity in {"HIGH", "CRITICAL"}
            )
            for issue in issues
        )
        if block:
            mode = SafetyMode.RISK_OFF
        elif issues:
            mode = SafetyMode.DEGRADED
        else:
            mode = SafetyMode.NORMAL
        return SafetyVerdict(
            mode=mode,
            block_new_trades=block,
            issues=tuple(issues),
        )


def audit_system_safety(
    required_modules: Iterable[str] = (),
    critical_modules: Iterable[str] = (),
    heartbeat: Any = None,
    circuit_breaker_registry: Any = None,
) -> SafetyVerdict:
    """Convenience wrapper for one-off checks from scripts or dashboards."""
    auditor = SystemSafetyAuditor(
        required_modules=required_modules,
        critical_modules=critical_modules,
    )
    return auditor.inspect(
        heartbeat=heartbeat,
        circuit_breaker_registry=circuit_breaker_registry,
    )
