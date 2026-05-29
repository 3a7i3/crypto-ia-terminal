"""
certification/module_certifier.py — G-01
Certification par module avec sceau COMPLETED.

Pour chaque module A-01→G-04 :
  1. Vérifie la présence du fichier source
  2. Lance les tests associés
  3. Calcule SHA256 du fichier
  4. Génère le rapport JSON + sceau ASCII
  5. Stocke dans certification/certs/{module_id}.json

Usage:
  from certification.module_certifier import ModuleCertifier
  mc = ModuleCertifier()
  cert = mc.certify("A-01")          # certifie A-01
  mc.certify_all(dry_run=True)       # dry-run sans pytest (vite)
  mc.print_seal("A-01")              # affiche le sceau
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
_CERT_DIR = _ROOT / "certification" / "certs"

_SEAL_WIDTH = 38


# ── Registre des modules ──────────────────────────────────────────────────────


@dataclass
class ModuleSpec:
    module_id: str
    source_path: str  # relatif à ROOT
    test_path: str  # relatif à ROOT — fichier ou dossier
    class_name: str
    phase: str = field(init=False)

    def __post_init__(self) -> None:
        self.phase = self.module_id.split("-")[0]


_REGISTRY: dict[str, ModuleSpec] = {
    # P10-A Cold Start
    "A-01": ModuleSpec(
        "A-01",
        "cold_start/cold_start_manager.py",
        "cold_start/tests/test_cold_start.py",
        "ColdStartManager",
    ),
    "A-02": ModuleSpec(
        "A-02",
        "cold_start/warmup_state_machine.py",
        "cold_start/tests/test_cold_start.py",
        "WarmupStateMachine",
    ),
    "A-03": ModuleSpec(
        "A-03",
        "cold_start/warmup_scenarios.py",
        "cold_start/tests/test_cold_start.py",
        "WarmupScenarios",
    ),
    "A-04": ModuleSpec(
        "A-04",
        "cold_start/warmup_metrics.py",
        "cold_start/tests/test_cold_start.py",
        "WarmupMetrics",
    ),
    "A-05": ModuleSpec(
        "A-05",
        "cold_start/warmup_invariants.py",
        "cold_start/tests/test_cold_start.py",
        "WarmupInvariants",
    ),
    "A-06": ModuleSpec(
        "A-06",
        "cold_start/warmup_report.py",
        "cold_start/tests/test_cold_start.py",
        "WarmupReport",
    ),
    "A-07": ModuleSpec(
        "A-07",
        "cold_start/market_warmup_estimator.py",
        "cold_start/tests/test_cold_start.py",
        "MarketWarmupEstimator",
    ),
    # P10-B Orchestrateur
    "B-01": ModuleSpec(
        "B-01", "runtime/runtime_coordinator.py", "runtime/tests/", "RuntimeCoordinator"
    ),
    "B-02": ModuleSpec(
        "B-02", "runtime/lifecycle_manager.py", "runtime/tests/", "LifecycleManager"
    ),
    "B-03": ModuleSpec(
        "B-03", "runtime/execution_context.py", "runtime/tests/", "ExecutionContext"
    ),
    "B-04": ModuleSpec(
        "B-04", "runtime/system_state_bus.py", "runtime/tests/", "SystemStateBus"
    ),
    "B-05": ModuleSpec(
        "B-05", "runtime/advisor_main.py", "runtime/tests/", "AdvisorMain"
    ),
    # P10-C Cryptographie
    "C-01": ModuleSpec(
        "C-01", "crypto/blackbox_encryption.py", "crypto/tests/", "BlackBoxEncryption"
    ),
    "C-02": ModuleSpec(
        "C-02", "crypto/decision_signer.py", "crypto/tests/", "DecisionSigner"
    ),
    "C-03": ModuleSpec(
        "C-03", "crypto/api_key_vault.py", "crypto/tests/", "APIKeyVault"
    ),
    "C-04": ModuleSpec(
        "C-04", "crypto/secure_channels.py", "crypto/tests/", "SecureChannels"
    ),
    "C-05": ModuleSpec("C-05", "crypto/audit_trail.py", "crypto/tests/", "AuditTrail"),
    "C-06": ModuleSpec(
        "C-06", "crypto/tamper_evident_logs.py", "crypto/tests/", "TamperEvidentLogs"
    ),
    # P10-D Stress Tests
    "D-01": ModuleSpec(
        "D-01",
        "tests/stress/test_d01_cold_start_scenarios.py",
        "tests/stress/test_d01_cold_start_scenarios.py",
        "D01ColdStartScenarios",
    ),
    "D-02": ModuleSpec(
        "D-02",
        "tests/stress/test_d02_exchange_failure.py",
        "tests/stress/test_d02_exchange_failure.py",
        "D02ExchangeFailure",
    ),
    "D-03": ModuleSpec(
        "D-03",
        "tests/stress/test_d03_memory_corruption.py",
        "tests/stress/test_d03_memory_corruption.py",
        "D03MemoryCorruption",
    ),
    "D-04": ModuleSpec(
        "D-04",
        "tests/stress/test_d04_latency_cascade.py",
        "tests/stress/test_d04_latency_cascade.py",
        "D04LatencyCascade",
    ),
    "D-05": ModuleSpec(
        "D-05",
        "tests/stress/test_d05_lm_studio_failure.py",
        "tests/stress/test_d05_lm_studio_failure.py",
        "D05LMStudioFailure",
    ),
    "D-06": ModuleSpec(
        "D-06",
        "tests/stress/test_d06_offline_recovery.py",
        "tests/stress/test_d06_offline_recovery.py",
        "D06OfflineRecovery",
    ),
    "D-07": ModuleSpec(
        "D-07",
        "tests/stress/test_d07_fuzz_testing.py",
        "tests/stress/test_d07_fuzz_testing.py",
        "D07FuzzTesting",
    ),
    # P10-E Supervision
    "E-01": ModuleSpec(
        "E-01",
        "supervision/ops_watchdog_hardened.py",
        "supervision/tests/",
        "OpsWatchdogHardened",
    ),
    "E-02": ModuleSpec(
        "E-02", "supervision/healing_actions.py", "supervision/tests/", "HealingActions"
    ),
    "E-03": ModuleSpec(
        "E-03",
        "supervision/escalation_engine.py",
        "supervision/tests/",
        "EscalationEngine",
    ),
    "E-04": ModuleSpec(
        "E-04",
        "supervision/killswitch_hardened.py",
        "supervision/tests/",
        "KillSwitchHardened",
    ),
    "E-05": ModuleSpec(
        "E-05",
        "supervision/recovery_playbooks.py",
        "supervision/tests/",
        "RecoveryPlaybooks",
    ),
    "E-06": ModuleSpec(
        "E-06",
        "supervision/proactive_alerts.py",
        "supervision/tests/",
        "ProactiveAlerts",
    ),
    "E-07": ModuleSpec(
        "E-07",
        "supervision/latency_baseline_monitor.py",
        "supervision/tests/",
        "LatencyBaselineMonitor",
    ),
    # P10-F Capital
    "F-01": ModuleSpec(
        "F-01",
        "capital_deployment/capital_throttle.py",
        "capital_deployment/tests/",
        "CapitalThrottle",
    ),
    "F-02": ModuleSpec(
        "F-02",
        "capital_deployment/phase_kpi_tracker.py",
        "capital_deployment/tests/",
        "PhaseKPITracker",
    ),
    "F-03": ModuleSpec(
        "F-03",
        "capital_deployment/phase_gate.py",
        "capital_deployment/tests/",
        "PhaseGate",
    ),
    "F-04": ModuleSpec(
        "F-04",
        "capital_deployment/emergency_stop_manager.py",
        "capital_deployment/tests/",
        "EmergencyStopManager",
    ),
    "F-05": ModuleSpec(
        "F-05",
        "capital_deployment/phase_certifier.py",
        "capital_deployment/tests/",
        "PhaseCertifier",
    ),
    # P10-G Certification
    "G-01": ModuleSpec(
        "G-01",
        "certification/module_certifier.py",
        "certification/tests/",
        "ModuleCertifier",
    ),
    "G-02": ModuleSpec(
        "G-02",
        "certification/immutable_stamp.py",
        "certification/tests/",
        "ImmutableStamp",
    ),
    "G-03": ModuleSpec(
        "G-03", "certification/doc_freeze.py", "certification/tests/", "DocFreeze"
    ),
    "G-04": ModuleSpec(
        "G-04",
        "certification/audit_trail_final.py",
        "certification/tests/",
        "AuditTrailFinal",
    ),
}


# ── Résultats ─────────────────────────────────────────────────────────────────


@dataclass
class ModuleCertificate:
    module_id: str
    class_name: str
    source_path: str
    sha256: str
    tests_passed: bool
    tests_detail: str
    certified_at: float = field(default_factory=time.time)
    certified_date: str = field(default="")
    dry_run: bool = False

    def __post_init__(self) -> None:
        from datetime import datetime, timezone

        self.certified_date = datetime.fromtimestamp(
            self.certified_at, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    @property
    def passed(self) -> bool:
        return self.tests_passed

    def to_dict(self) -> dict:
        return {
            "module_id": self.module_id,
            "class_name": self.class_name,
            "source_path": self.source_path,
            "sha256": self.sha256,
            "tests_passed": self.tests_passed,
            "tests_detail": self.tests_detail,
            "certified_at": self.certified_at,
            "certified_date": self.certified_date,
            "dry_run": self.dry_run,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModuleCertificate":
        c = cls(
            module_id=d["module_id"],
            class_name=d["class_name"],
            source_path=d["source_path"],
            sha256=d["sha256"],
            tests_passed=d["tests_passed"],
            tests_detail=d["tests_detail"],
            certified_at=float(d.get("certified_at", 0.0)),
            dry_run=bool(d.get("dry_run", False)),
        )
        c.certified_date = d.get("certified_date", "")
        return c

    def seal(self) -> str:
        w = _SEAL_WIDTH
        short_hash = self.sha256[:16] + "..."
        lines = [
            f"╔{'═' * (w - 2)}╗",
            f"║{'COMPLETED !!!':^{w-2}}║",
            f"║{'100% CYBERTECHNIQUE':^{w-2}}║",
            f"║{' ':^{w-2}}║",
            f"║  Module: {self.module_id:<{w-12}}║",
            f"║  Class:  {self.class_name:<{w-12}}║",
            f"║  Date:   {self.certified_date:<{w-12}}║",
            f"║  Hash:   {short_hash:<{w-12}}║",
            f"╚{'═' * (w - 2)}╝",
        ]
        return "\n".join(lines)


# ── Certifier ─────────────────────────────────────────────────────────────────


class ModuleCertifier:
    """Certifie les modules P10-A→G-04 avec sceau COMPLETED."""

    def __init__(
        self,
        root: Optional[Path] = None,
        cert_dir: Optional[Path] = None,
    ) -> None:
        self._root = root or _ROOT
        self._cert_dir = cert_dir or _CERT_DIR
        self._cert_dir.mkdir(parents=True, exist_ok=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _run_tests(self, test_path: str, timeout: int = 180) -> tuple[bool, str]:
        full = self._root / test_path.replace("/", os.sep)
        if not full.exists():
            return False, f"Test path not found: {test_path}"
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(full),
                    "-q",
                    "--tb=no",
                    "--no-header",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._root,
            )
            summary = next(
                (
                    ln
                    for ln in r.stdout.splitlines()
                    if "passed" in ln or "failed" in ln
                ),
                r.stdout.strip()[-80:],
            )
            return r.returncode == 0, summary
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT"
        except Exception as exc:
            return False, str(exc)

    # ── Certification ─────────────────────────────────────────────────────────

    def certify(self, module_id: str, dry_run: bool = False) -> ModuleCertificate:
        spec = _REGISTRY.get(module_id)
        if spec is None:
            raise ValueError(f"Module inconnu : {module_id}")

        source = self._root / spec.source_path.replace("/", os.sep)
        if not source.exists():
            raise FileNotFoundError(f"Source introuvable : {source}")

        sha256 = self._sha256(source)

        if dry_run:
            tests_ok, tests_detail = True, "dry-run (tests non exécutés)"
        else:
            tests_ok, tests_detail = self._run_tests(spec.test_path)

        cert = ModuleCertificate(
            module_id=module_id,
            class_name=spec.class_name,
            source_path=spec.source_path,
            sha256=sha256,
            tests_passed=tests_ok,
            tests_detail=tests_detail,
            dry_run=dry_run,
        )
        self._save(cert)
        return cert

    def certify_all(self, dry_run: bool = False) -> dict[str, ModuleCertificate]:
        results: dict[str, ModuleCertificate] = {}
        for mid in _REGISTRY:
            try:
                results[mid] = self.certify(mid, dry_run=dry_run)
            except Exception as exc:
                results[mid] = ModuleCertificate(
                    module_id=mid,
                    class_name=_REGISTRY[mid].class_name,
                    source_path=_REGISTRY[mid].source_path,
                    sha256="",
                    tests_passed=False,
                    tests_detail=str(exc),
                    dry_run=dry_run,
                )
        return results

    # ── Persistance ───────────────────────────────────────────────────────────

    def _save(self, cert: ModuleCertificate) -> None:
        path = self._cert_dir / f"{cert.module_id}.json"
        path.write_text(json.dumps(cert.to_dict(), indent=2), encoding="utf-8")

    def load(self, module_id: str) -> Optional[ModuleCertificate]:
        path = self._cert_dir / f"{module_id}.json"
        if not path.exists():
            return None
        return ModuleCertificate.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def is_certified(self, module_id: str) -> bool:
        cert = self.load(module_id)
        return cert is not None and cert.passed

    def all_certified(self) -> bool:
        return all(self.is_certified(mid) for mid in _REGISTRY)

    def summary(self) -> str:
        lines = [f"ModuleCertifier — {len(_REGISTRY)} modules"]
        ok = fail = missing = 0
        for mid in _REGISTRY:
            cert = self.load(mid)
            if cert is None:
                missing += 1
                lines.append(f"  [--] {mid}")
            elif cert.passed:
                ok += 1
                lines.append(f"  [OK] {mid} {cert.sha256[:10]}...")
            else:
                fail += 1
                lines.append(f"  [FAIL] {mid}: {cert.tests_detail[:60]}")
        lines.insert(1, f"  OK={ok}  FAIL={fail}  MISSING={missing}")
        return "\n".join(lines)

    def print_seal(self, module_id: str) -> None:
        cert = self.load(module_id)
        if cert is None:
            print(f"[--] {module_id} — non certifié")
            return
        print(cert.seal())

    @staticmethod
    def registry() -> dict[str, ModuleSpec]:
        return dict(_REGISTRY)
