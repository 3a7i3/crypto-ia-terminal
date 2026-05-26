"""
Ordered boot sequence for the system.
Reads the dependency graph, starts modules in topological order,
validates each step, and transitions system state accordingly.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional

from observability.json_logger import get_logger
from system.dependency_manager import dependency_manager
from system.module_registry import ModulePriority, ModuleStatus, module_registry
from system.runtime_controller import ModuleStartError, runtime_controller
from system.state_manager import SystemState, state_manager

_log = get_logger("system.startup_sequence")


class StepResult:
    def __init__(
        self,
        module: str,
        success: bool,
        duration_sec: float,
        error: Optional[str] = None,
    ):
        self.module = module
        self.success = success
        self.duration_sec = duration_sec
        self.error = error

    def __repr__(self) -> str:
        status = "OK" if self.success else f"FAIL({self.error})"
        return f"StepResult({self.module}, {status}, {self.duration_sec:.2f}s)"


class StartupSequence:
    """
    Executes the boot sequence in dependency order.
    Critical module failures abort the boot entirely.
    Non-critical failures are logged and skipped.
    """

    def __init__(self) -> None:
        self._results: List[StepResult] = []
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def before_boot(self, fn: Callable) -> None:
        self._pre_hooks.append(fn)

    def after_boot(self, fn: Callable) -> None:
        self._post_hooks.append(fn)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """
        Execute full startup sequence.
        Returns True if all critical modules started successfully.
        """
        _log.info("=" * 60)
        _log.info("[StartupSequence] Beginning system boot")
        _log.info("=" * 60)

        # Must already be in BOOTING state
        if state_manager.state != SystemState.BOOTING:
            _log.error(
                f"[StartupSequence] Cannot boot from state {state_manager.state.name}"
            )
            return False

        self._run_hooks(self._pre_hooks, "pre-boot")

        order = dependency_manager.startup_order()
        _log.info(f"[StartupSequence] Startup order ({len(order)} modules): {order}")

        failed_critical = False
        for module_name in order:
            info = module_registry.get(module_name)
            if info is None:
                _log.debug(
                    f"[StartupSequence] Skipping unregistered module: {module_name}"
                )
                continue
            if info.status == ModuleStatus.DISABLED:
                _log.warning(
                    f"[StartupSequence] Skipping disabled module: {module_name}"
                )
                continue

            result = self._start_one(module_name, info.priority)
            self._results.append(result)

            if not result.success and info.priority == ModulePriority.CRITICAL:
                _log.critical(
                    f"[StartupSequence] Critical module failed to start: {module_name}"
                )
                failed_critical = True
                break

        if failed_critical:
            _log.critical("[StartupSequence] Boot ABORTED — critical module failure")
            state_manager.force_panic("boot failed: critical module could not start")
            return False

        # Transition to SYNCING (connecting to exchanges)
        state_manager.transition(SystemState.SYNCING, "boot sequence complete")
        _log.info("[StartupSequence] All modules started — transitioning to SYNCING")

        self._run_hooks(self._post_hooks, "post-boot")
        self._print_summary()
        return True

    def _start_one(self, name: str, priority: ModulePriority) -> StepResult:
        tag = f"[{priority.name}]"
        _log.info(f"[StartupSequence] {tag} Starting: {name}")
        t0 = time.time()
        try:
            runtime_controller.start_module(name)
            duration = time.time() - t0
            _log.info(f"[StartupSequence] {tag} OK: {name} ({duration:.2f}s)")
            return StepResult(name, True, duration)
        except ModuleStartError as e:
            duration = time.time() - t0
            _log.error(
                f"[StartupSequence] {tag} FAILED: {name} — {e} ({duration:.2f}s)"
            )
            return StepResult(name, False, duration, str(e))

    def _run_hooks(self, hooks: List[Callable], label: str) -> None:
        for fn in hooks:
            try:
                fn()
            except Exception as e:
                _log.warning(f"[StartupSequence] {label} hook error: {e}")

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _print_summary(self) -> None:
        ok = [r for r in self._results if r.success]
        fail = [r for r in self._results if not r.success]
        total_time = sum(r.duration_sec for r in self._results)
        _log.info("-" * 60)
        _log.info(
            f"[StartupSequence] Boot summary: {len(ok)} OK / {len(fail)} FAILED / {total_time:.2f}s total"
        )
        if fail:
            for r in fail:
                _log.warning(f"  FAILED: {r.module} — {r.error}")
        _log.info("-" * 60)

    def results(self) -> List[StepResult]:
        return list(self._results)

    def snapshot(self) -> dict:
        return {
            "steps_total": len(self._results),
            "steps_ok": sum(1 for r in self._results if r.success),
            "steps_failed": sum(1 for r in self._results if not r.success),
            "failed_modules": [r.module for r in self._results if not r.success],
            "total_boot_time_sec": round(sum(r.duration_sec for r in self._results), 2),
        }


# Singleton
startup_sequence = StartupSequence()
