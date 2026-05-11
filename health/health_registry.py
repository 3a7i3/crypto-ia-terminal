"""
Health Registry — standardized health checks per module.

Each module declares one or more HealthCheck functions.
The registry runs them on a schedule and aggregates results.

Usage:
    from health.health_registry import health_registry, HealthCheck

    # Module declares its checks at startup
    health_registry.register_check(
        module="risk_engine",
        name="drawdown_within_limit",
        check_fn=lambda: risk_engine.current_drawdown < 0.05,
        critical=True,
    )

    # Background runner evaluates all checks every N seconds
    health_registry.start()

    # Read results
    result = health_registry.check_module("risk_engine")
    all_results = health_registry.snapshot()
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from observability.metrics_bus import metrics_bus
from system.module_registry import ModuleStatus, module_registry


@dataclass
class HealthCheck:
    module: str
    name: str
    check_fn: Callable[[], bool]
    critical: bool = (
        False  # if True, failure marks module UNHEALTHY (not just DEGRADED)
    )
    timeout_sec: float = 5.0
    description: str = ""


@dataclass
class CheckResult:
    module: str
    name: str
    passed: bool
    critical: bool
    duration_ms: float
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def snapshot(self) -> dict:
        return {
            "module": self.module,
            "check": self.name,
            "passed": self.passed,
            "critical": self.critical,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "timestamp": self.timestamp,
        }


class HealthRegistry:
    """
    Runs health check functions for all registered modules.
    Aggregates pass/fail, updates module registry status accordingly.
    """

    POLL_INTERVAL_SEC = 20.0

    def __init__(self) -> None:
        self._checks: Dict[str, List[HealthCheck]] = {}  # module -> checks
        self._results: Dict[str, List[CheckResult]] = {}  # module -> latest results
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_check(
        self,
        module: str,
        name: str,
        check_fn: Callable[[], bool],
        critical: bool = False,
        timeout_sec: float = 5.0,
        description: str = "",
    ) -> None:
        check = HealthCheck(
            module=module,
            name=name,
            check_fn=check_fn,
            critical=critical,
            timeout_sec=timeout_sec,
            description=description,
        )
        with self._lock:
            self._checks.setdefault(module, []).append(check)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def run_check(self, check: HealthCheck) -> CheckResult:
        """Execute a single health check and return its result."""
        t0 = time.time()
        try:
            passed = check.check_fn()
            error = None
        except Exception:
            passed = False
            error = traceback.format_exc(limit=3)
        duration_ms = (time.time() - t0) * 1000

        result = CheckResult(
            module=check.module,
            name=check.name,
            passed=passed,
            critical=check.critical,
            duration_ms=duration_ms,
            error=error,
        )
        metrics_bus.record(
            check.module, f"health_check.{check.name}", 1.0 if passed else 0.0
        )
        return result

    def check_module(self, module: str) -> List[CheckResult]:
        """Run all checks for a given module immediately."""
        checks = self._checks.get(module, [])
        results = [self.run_check(c) for c in checks]

        with self._lock:
            self._results[module] = results

        self._apply_results(module, results)
        return results

    def check_all(self) -> Dict[str, List[CheckResult]]:
        """Run all checks for all modules."""
        with self._lock:
            modules = list(self._checks.keys())
        return {m: self.check_module(m) for m in modules}

    def _apply_results(self, module: str, results: List[CheckResult]) -> None:
        """Update module registry status based on check results."""
        if not results:
            return

        failed_critical = any(not r.passed and r.critical for r in results)
        failed_any = any(not r.passed for r in results)
        all_passed = all(r.passed for r in results)

        info = module_registry.get(module)
        if info is None:
            return

        if failed_critical:
            module_registry.set_status(
                module, ModuleStatus.UNHEALTHY, "critical health check failed"
            )
            failed_names = [r.name for r in results if not r.passed and r.critical]
            module_registry.report_error(
                module, f"critical checks failed: {failed_names}"
            )
        elif failed_any:
            module_registry.set_status(
                module, ModuleStatus.DEGRADED, "non-critical health check failed"
            )
        elif all_passed and info.status == ModuleStatus.DEGRADED:
            module_registry.set_status(
                module, ModuleStatus.HEALTHY, "all health checks passing"
            )

    # ------------------------------------------------------------------
    # Background runner
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="HealthRegistry.runner"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run_loop(self) -> None:
        while self._running:
            try:
                self.check_all()
            except Exception:
                pass
            time.sleep(self.POLL_INTERVAL_SEC)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def latest_results(self, module: str) -> List[CheckResult]:
        with self._lock:
            return list(self._results.get(module, []))

    def module_health(self, module: str) -> Dict[str, Any]:
        results = self.latest_results(module)
        if not results:
            return {"module": module, "status": "no_checks", "checks": []}

        all_passed = all(r.passed for r in results)
        any_critical_failed = any(not r.passed and r.critical for r in results)

        return {
            "module": module,
            "status": (
                "HEALTHY"
                if all_passed
                else ("UNHEALTHY" if any_critical_failed else "DEGRADED")
            ),
            "checks_total": len(results),
            "checks_passed": sum(1 for r in results if r.passed),
            "checks_failed": sum(1 for r in results if not r.passed),
            "checks": [r.snapshot() for r in results],
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            modules = list(self._checks.keys())
        return {
            "timestamp": time.time(),
            "modules_with_checks": len(modules),
            "results": {m: self.module_health(m) for m in modules},
        }


# Singleton
health_registry = HealthRegistry()

# ------------------------------------------------------------------
# Built-in system checks (registered at import time)
# ------------------------------------------------------------------

health_registry.register_check(
    module="state_manager",
    name="not_in_panic",
    check_fn=lambda: __import__(
        "system.state_manager", fromlist=["state_manager"]
    ).state_manager.state.name
    != "PANIC",
    critical=True,
    description="System must not be in PANIC state",
)

health_registry.register_check(
    module="module_registry",
    name="critical_modules_healthy",
    check_fn=lambda: __import__(
        "system.module_registry", fromlist=["module_registry"]
    ).module_registry.all_critical_healthy(),
    critical=True,
    description="All CRITICAL priority modules must be healthy",
)

health_registry.register_check(
    module="module_registry",
    name="health_score_above_threshold",
    check_fn=lambda: __import__(
        "system.module_registry", fromlist=["module_registry"]
    ).module_registry.system_health_score()
    >= 0.5,
    critical=False,
    description="Overall health score must be >= 0.5",
)
