"""Tests for the system safety auditor."""

from __future__ import annotations

from system.module_registry import ModulePriority, ModuleRegistry, ModuleStatus
from system.safety_auditor import SafetyMode, SystemSafetyAuditor


def test_healthy_required_module_returns_normal() -> None:
    registry = ModuleRegistry()
    registry.register("risk_gate", priority=ModulePriority.CRITICAL)
    registry.heartbeat("risk_gate")

    verdict = SystemSafetyAuditor(required_modules={"risk_gate"}).inspect(registry)

    assert verdict.mode == SafetyMode.NORMAL
    assert verdict.ok is True
    assert verdict.block_new_trades is False


def test_missing_required_module_forces_risk_off() -> None:
    registry = ModuleRegistry()

    verdict = SystemSafetyAuditor(required_modules={"risk_gate"}).inspect(registry)

    assert verdict.mode == SafetyMode.RISK_OFF
    assert verdict.block_new_trades is True
    assert verdict.issues[0].module == "risk_gate"


def test_degraded_critical_module_blocks_new_trades() -> None:
    registry = ModuleRegistry()
    registry.register("execution_engine", priority=ModulePriority.CRITICAL)
    registry.heartbeat("execution_engine")
    registry.set_status("execution_engine", ModuleStatus.DEGRADED, "test")

    verdict = SystemSafetyAuditor(critical_modules={"execution_engine"}).inspect(
        registry
    )

    assert verdict.mode == SafetyMode.RISK_OFF
    assert verdict.block_new_trades is True
    assert verdict.issues[0].severity == "HIGH"


def test_degraded_optional_module_degrades_without_trade_block() -> None:
    registry = ModuleRegistry()
    registry.register("dashboard", priority=ModulePriority.LOW)
    registry.heartbeat("dashboard")
    registry.set_status("dashboard", ModuleStatus.DEGRADED, "test")

    verdict = SystemSafetyAuditor().inspect(registry)

    assert verdict.mode == SafetyMode.DEGRADED
    assert verdict.block_new_trades is False


def test_critical_circuit_breaker_degraded_blocks_new_trades() -> None:
    class FakeCircuitBreakers:
        def snapshot_all(self) -> list[dict]:
            return [{"name": "global_risk_gate", "state": "degraded"}]

    registry = ModuleRegistry()
    registry.register("global_risk_gate", priority=ModulePriority.CRITICAL)
    registry.heartbeat("global_risk_gate")

    verdict = SystemSafetyAuditor(critical_modules={"global_risk_gate"}).inspect(
        registry, circuit_breaker_registry=FakeCircuitBreakers()
    )

    assert verdict.mode == SafetyMode.RISK_OFF
    assert verdict.block_new_trades is True
