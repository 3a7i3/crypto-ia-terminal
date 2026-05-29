"""
certification/prerequisite_checker.py — G-01
Vérification automatisée des prérequis P10-A→F avant certification finale.

Vérifie :
- Présence de tous les modules requis sur disque
- Importabilité des modules P10-F capital_deployment
- Présence des suites de tests
- Présence des artefacts runtime (checkpoints, databases)
"""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent

# ── Modules requis par phase ──────────────────────────────────────────────────

_PHASE_MODULES: dict[str, list[str]] = {
    "P10-A": [
        "cold_start/cold_start_manager.py",
        "cold_start/warmup_state_machine.py",
        "cold_start/warmup_scenarios.py",
        "cold_start/warmup_metrics.py",
        "cold_start/warmup_invariants.py",
        "cold_start/warmup_report.py",
        "cold_start/market_warmup_estimator.py",
    ],
    "P10-B": [
        "runtime/runtime_coordinator.py",
        "runtime/lifecycle_manager.py",
        "runtime/execution_context.py",
        "runtime/system_state_bus.py",
        "runtime/advisor_main.py",
    ],
    "P10-C": [
        "crypto/key_derivation.py",
        "crypto/blackbox_encryption.py",
        "crypto/decision_signer.py",
        "crypto/api_key_vault.py",
        "crypto/secure_channels.py",
        "crypto/audit_trail.py",
        "crypto/tamper_evident_logs.py",
    ],
    "P10-D": [
        "tests/stress/test_d01_cold_start_scenarios.py",
        "tests/stress/test_d02_exchange_failure.py",
        "tests/stress/test_d03_memory_corruption.py",
        "tests/stress/test_d04_latency_cascade.py",
        "tests/stress/test_d05_lm_studio_failure.py",
        "tests/stress/test_d06_offline_recovery.py",
        "tests/stress/test_d07_fuzz_testing.py",
    ],
    "P10-E": [
        "supervision/ops_watchdog_hardened.py",
        "supervision/healing_actions.py",
        "supervision/escalation_engine.py",
        "supervision/killswitch_hardened.py",
        "supervision/recovery_playbooks.py",
        "supervision/proactive_alerts.py",
        "supervision/latency_baseline_monitor.py",
    ],
    "P10-F": [
        "capital_deployment/capital_throttle.py",
        "capital_deployment/phase_kpi_tracker.py",
        "capital_deployment/phase_gate.py",
        "capital_deployment/emergency_stop_manager.py",
        "capital_deployment/phase_certifier.py",
    ],
}

# Modules P10-F devant être importables (pas juste présents sur disque)
_F_IMPORTABLE = [
    "capital_deployment.capital_throttle",
    "capital_deployment.phase_kpi_tracker",
    "capital_deployment.phase_gate",
    "capital_deployment.emergency_stop_manager",
    "capital_deployment.phase_certifier",
]

# Artefacts runtime attendus
_RUNTIME_ARTIFACTS = [
    "databases",
    "checkpoints",
    "logs",
    "cache/startup",
]


# ── Résultats ─────────────────────────────────────────────────────────────────


@dataclass
class PhaseCheck:
    phase: str
    files_ok: int
    files_total: int
    missing: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.missing) == 0


@dataclass
class PrerequisiteReport:
    phase_checks: list[PhaseCheck] = field(default_factory=list)
    import_errors: list[str] = field(default_factory=list)
    artifact_errors: list[str] = field(default_factory=list)

    @property
    def all_phases_ok(self) -> bool:
        return all(c.passed for c in self.phase_checks)

    @property
    def imports_ok(self) -> bool:
        return len(self.import_errors) == 0

    @property
    def artifacts_ok(self) -> bool:
        return len(self.artifact_errors) == 0

    @property
    def passed(self) -> bool:
        return self.all_phases_ok and self.imports_ok and self.artifacts_ok

    def summary(self) -> str:
        lines = []
        for c in self.phase_checks:
            mark = "OK" if c.passed else "FAIL"
            lines.append(
                f"  [{mark}] {c.phase} — {c.files_ok}/{c.files_total} fichiers"
            )
            for m in c.missing:
                lines.append(f"        manquant : {m}")
        if self.import_errors:
            lines.append("  [FAIL] Imports P10-F :")
            for e in self.import_errors:
                lines.append(f"        {e}")
        if self.artifact_errors:
            lines.append("  [WARN] Artefacts runtime :")
            for a in self.artifact_errors:
                lines.append(f"        {a}")
        status = "PASS" if self.passed else "FAIL"
        lines.insert(0, f"PrerequisiteChecker — {status}")
        return "\n".join(lines)


# ── Checker ───────────────────────────────────────────────────────────────────


class PrerequisiteChecker:
    """Vérifie tous les prérequis P10-A→F avant la certification finale."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root or _ROOT

    # ── Checks individuels ────────────────────────────────────────────────────

    def check_phase_files(self, phase: str) -> PhaseCheck:
        modules = _PHASE_MODULES.get(phase, [])
        missing = [
            m for m in modules if not (self._root / m.replace("/", os.sep)).exists()
        ]
        return PhaseCheck(
            phase=phase,
            files_ok=len(modules) - len(missing),
            files_total=len(modules),
            missing=missing,
        )

    def check_f_imports(self) -> list[str]:
        errors: list[str] = []
        for mod in _F_IMPORTABLE:
            try:
                importlib.import_module(mod)
            except Exception as exc:
                errors.append(f"{mod}: {exc}")
        return errors

    def check_runtime_artifacts(self) -> list[str]:
        missing: list[str] = []
        for artifact in _RUNTIME_ARTIFACTS:
            p = self._root / artifact.replace("/", os.sep)
            if not p.exists():
                missing.append(artifact)
        return missing

    # ── Run complet ───────────────────────────────────────────────────────────

    def run(self) -> PrerequisiteReport:
        report = PrerequisiteReport()
        for phase in _PHASE_MODULES:
            report.phase_checks.append(self.check_phase_files(phase))
        report.import_errors = self.check_f_imports()
        report.artifact_errors = self.check_runtime_artifacts()
        return report

    def run_phase(self, phase: str) -> PhaseCheck:
        return self.check_phase_files(phase)
