#!/usr/bin/env python3
"""
p10_checker.py — Vérificateur unifié du Plan d'accréditation P10

Usage:
  python certification/p10_checker.py           # résumé toutes phases
  python certification/p10_checker.py --full    # détail complet
  python certification/p10_checker.py --phase A # vérification d'une phase
  python certification/p10_checker.py --phase G # gate finale
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

WORKSPACE = Path(__file__).parent.parent

C = {
    "OK": "\033[92m",
    "FAIL": "\033[91m",
    "WARN": "\033[93m",
    "INFO": "\033[96m",
    "DIM": "\033[90m",
    "BOLD": "\033[1m",
    "RESET": "\033[0m",
}


def ok(msg: str) -> str:
    return f"{C['OK']}[OK  ]{C['RESET']} {msg}"


def fail(msg: str) -> str:
    return f"{C['FAIL']}[FAIL]{C['RESET']} {msg}"


def warn(msg: str) -> str:
    return f"{C['WARN']}[WARN]{C['RESET']} {msg}"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PhaseResult:
    label: str
    title: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def score(self) -> str:
        p = sum(1 for c in self.checks if c.passed)
        return f"{p}/{len(self.checks)}"


# ── Helpers ───────────────────────────────────────────────────────────────────


def file_exists(rel_path: str) -> CheckResult:
    import os

    p = WORKSPACE / rel_path.replace("/", os.sep)
    return CheckResult(
        name=f"Fichier : {rel_path}",
        passed=p.exists(),
        detail="" if p.exists() else f"Introuvable : {p}",
    )


def files_present(paths: list[str], label: str) -> CheckResult:
    import os

    missing = [p for p in paths if not (WORKSPACE / p.replace("/", os.sep)).exists()]
    return CheckResult(
        name=label,
        passed=len(missing) == 0,
        detail=f"Manquants : {missing}" if missing else "",
    )


def run_pytest(args: list[str], timeout: int = 120) -> CheckResult:
    label = " ".join(args)
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", *args, "-q", "--tb=no", "--no-header"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=WORKSPACE,
        )
        passed = r.returncode == 0
        summary = next(
            (
                ln
                for ln in r.stdout.splitlines()
                if "passed" in ln or "failed" in ln or "error" in ln
            ),
            r.stdout.strip()[-120:] if r.stdout.strip() else "no output",
        )
        return CheckResult(name=f"pytest {label}", passed=passed, detail=summary)
    except subprocess.TimeoutExpired:
        return CheckResult(name=f"pytest {label}", passed=False, detail="TIMEOUT")
    except Exception as exc:
        return CheckResult(name=f"pytest {label}", passed=False, detail=str(exc))


def can_import(module: str) -> CheckResult:
    try:
        importlib.import_module(module)
        return CheckResult(name=f"import {module}", passed=True)
    except Exception as exc:
        return CheckResult(name=f"import {module}", passed=False, detail=str(exc))


# ── P10-A — Cold Start Protocol ───────────────────────────────────────────────


def check_phase_a() -> PhaseResult:
    phase = PhaseResult("A", "Cold Start Protocol")
    phase.checks.append(
        files_present(
            [
                "cold_start/cold_start_manager.py",
                "cold_start/warmup_state_machine.py",
                "cold_start/warmup_scenarios.py",
                "cold_start/warmup_metrics.py",
                "cold_start/warmup_invariants.py",
                "cold_start/warmup_report.py",
                "cold_start/market_warmup_estimator.py",
            ],
            "7 modules cold_start",
        )
    )
    phase.checks.append(
        run_pytest(["cold_start/tests/test_cold_start.py"], timeout=120)
    )
    return phase


# ── P10-B — Orchestrateur ─────────────────────────────────────────────────────


def check_phase_b() -> PhaseResult:
    phase = PhaseResult("B", "Orchestrateur / Runtime")
    phase.checks.append(
        files_present(
            [
                "runtime/runtime_coordinator.py",
                "runtime/lifecycle_manager.py",
                "runtime/execution_context.py",
                "runtime/system_state_bus.py",
                "runtime/advisor_main.py",
            ],
            "5 modules runtime",
        )
    )
    phase.checks.append(run_pytest(["runtime/tests/"], timeout=120))
    return phase


# ── P10-C — Cryptographie ─────────────────────────────────────────────────────


def check_phase_c() -> PhaseResult:
    phase = PhaseResult("C", "Cryptographie")
    phase.checks.append(
        files_present(
            [
                "crypto/key_derivation.py",
                "crypto/blackbox_encryption.py",
                "crypto/decision_signer.py",
                "crypto/api_key_vault.py",
                "crypto/secure_channels.py",
                "crypto/audit_trail.py",
                "crypto/tamper_evident_logs.py",
            ],
            "7 modules crypto",
        )
    )
    phase.checks.append(run_pytest(["crypto/tests/"], timeout=120))
    return phase


# ── P10-D — Stress Tests ──────────────────────────────────────────────────────


def check_phase_d() -> PhaseResult:
    phase = PhaseResult("D", "Stress Tests")
    phase.checks.append(
        files_present(
            [
                "tests/stress/test_d01_cold_start_scenarios.py",
                "tests/stress/test_d02_exchange_failure.py",
                "tests/stress/test_d03_memory_corruption.py",
                "tests/stress/test_d04_latency_cascade.py",
                "tests/stress/test_d05_lm_studio_failure.py",
                "tests/stress/test_d06_offline_recovery.py",
                "tests/stress/test_d07_fuzz_testing.py",
            ],
            "7 fichiers stress",
        )
    )
    phase.checks.append(run_pytest(["tests/stress/"], timeout=180))
    return phase


# ── P10-E — Supervision 24/7 ──────────────────────────────────────────────────


def check_phase_e() -> PhaseResult:
    phase = PhaseResult("E", "Supervision 24/7")
    phase.checks.append(
        files_present(
            [
                "supervision/ops_watchdog_hardened.py",
                "supervision/healing_actions.py",
                "supervision/escalation_engine.py",
                "supervision/killswitch_hardened.py",
                "supervision/recovery_playbooks.py",
                "supervision/proactive_alerts.py",
                "supervision/latency_baseline_monitor.py",
            ],
            "7 modules supervision",
        )
    )
    phase.checks.append(run_pytest(["supervision/tests/"], timeout=180))
    return phase


# ── P10-F — Montée en Capitale ────────────────────────────────────────────────


def check_phase_f() -> PhaseResult:
    phase = PhaseResult("F", "Montée en Capitale")
    phase.checks.append(
        files_present(
            [
                "capital_deployment/capital_throttle.py",
                "capital_deployment/phase_kpi_tracker.py",
                "capital_deployment/phase_gate.py",
                "capital_deployment/emergency_stop_manager.py",
                "capital_deployment/phase_certifier.py",
            ],
            "5 modules capital_deployment",
        )
    )
    for mod in [
        "capital_deployment.capital_throttle",
        "capital_deployment.phase_kpi_tracker",
        "capital_deployment.phase_gate",
        "capital_deployment.emergency_stop_manager",
        "capital_deployment.phase_certifier",
    ]:
        phase.checks.append(can_import(mod))
    phase.checks.append(run_pytest(["capital_deployment/tests/"], timeout=120))
    # Phase live — statut depuis CERTIFIED_{phase}.json
    import os

    p10_phase = os.getenv("P10_PHASE", "F-01")
    cert_path = WORKSPACE / "certification" / f"CERTIFIED_{p10_phase}.json"
    phase.checks.append(
        CheckResult(
            name=f"Certificat live {p10_phase}",
            passed=cert_path.exists(),
            detail=(
                ""
                if cert_path.exists()
                else f"Non disponible — validation live en cours ({p10_phase})"
            ),
        )
    )
    return phase


# ── P10-G — Certification Finale ─────────────────────────────────────────────


def check_phase_g(prev_phases: list[PhaseResult]) -> PhaseResult:
    phase = PhaseResult("G", "Certification Finale")

    # Prérequis : P10-A à P10-F tous passés (infra — sauf cert live)
    for p in prev_phases:
        infra_checks = [c for c in p.checks if "Certificat live" not in c.name]
        all_infra_ok = all(c.passed for c in infra_checks)
        phase.checks.append(
            CheckResult(
                name=f"P10-{p.label} infra [{p.title}]",
                passed=all_infra_ok,
                detail=(
                    f"{sum(1 for c in infra_checks if c.passed)}/{len(infra_checks)} checks"
                    if not all_infra_ok
                    else ""
                ),
            )
        )

    # G-01 prerequisite_checker
    phase.checks.append(
        files_present(
            [
                "certification/prerequisite_checker.py",
                "certification/live_kpi_auditor.py",
                "certification/operator_signoff.py",
                "certification/final_gate.py",
            ],
            "4 modules P10-G",
        )
    )
    phase.checks.append(run_pytest(["certification/tests/"], timeout=120))

    # hash_verifier
    phase.checks.append(file_exists("certification/hash_verifier.py"))

    # paper_trading stack
    phase.checks.append(
        files_present(
            [
                "paper_trading/engine.py",
                "paper_trading/ledger.py",
            ],
            "paper_trading stack",
        )
    )

    # Signoff opérateur présent pour phase courante
    import os

    p10_phase = os.getenv("P10_PHASE", "F-01")
    signoff_path = WORKSPACE / "certification" / f"signoff_{p10_phase}.json"
    phase.checks.append(
        CheckResult(
            name=f"Signoff opérateur {p10_phase}",
            passed=signoff_path.exists(),
            detail="" if signoff_path.exists() else "Requis avant certification finale",
        )
    )

    return phase


# ── Affichage ─────────────────────────────────────────────────────────────────


def print_phase(phase: PhaseResult, verbose: bool = False) -> None:
    if phase.passed:
        status = f"{C['OK']}[COMPLETED]{C['RESET']}"
    else:
        n_ok = sum(1 for c in phase.checks if c.passed)
        n = len(phase.checks)
        if n_ok == 0:
            status = f"{C['FAIL']}[PENDING  ]{C['RESET']}"
        else:
            status = f"{C['WARN']}[PARTIAL  ]{C['RESET']}"
    print(
        f"\n{C['BOLD']}P10-{phase.label} — {phase.title}{C['RESET']}  {status}  ({phase.score})"
    )
    if not verbose and phase.passed:
        return
    for c in phase.checks:
        line = ok(c.name) if c.passed else fail(c.name)
        print(f"  {line}")
        if c.detail and (not c.passed or verbose):
            for ln in c.detail.splitlines():
                print(f"      {C['DIM']}{ln}{C['RESET']}")


def print_summary(phases: list[PhaseResult]) -> None:
    print(f"\n{C['BOLD']}{'-'*58}{C['RESET']}")
    print(f"{C['BOLD']}  RECAPITULATIF P10  —  crypto_ai_terminal{C['RESET']}")
    print(f"{C['BOLD']}{'-'*58}{C['RESET']}")

    total_ok = total = 0
    for p in phases:
        color = (
            C["OK"]
            if p.passed
            else C["WARN"] if int(p.score.split("/")[0]) > 0 else C["FAIL"]
        )
        n_ok = sum(1 for c in p.checks if c.passed)
        n_tot = len(p.checks)
        total_ok += n_ok
        total += n_tot
        print(
            f"  {color}[{'OK' if p.passed else '--'}]{C['RESET']} P10-{p.label}  {p.title:<38}  {n_ok}/{n_tot}"
        )

    pct = int(total_ok / total * 100) if total else 0
    color = C["OK"] if pct == 100 else C["WARN"] if pct >= 70 else C["FAIL"]
    print(
        f"\n  {color}{C['BOLD']}Score global : {total_ok}/{total} ({pct}%){C['RESET']}"
    )
    if pct == 100:
        print(
            f"\n  {C['OK']}{C['BOLD']}ACCREDITATION COMPLETE — signature operateur requise (P10-G).{C['RESET']}"
        )
    else:
        print(
            f"\n  {C['WARN']}Phases incompletes — voir details ci-dessus.{C['RESET']}"
        )
    print()


# ── Entrypoint ────────────────────────────────────────────────────────────────

PHASE_MAP: dict[str, Callable[..., PhaseResult]] = {
    "A": check_phase_a,
    "B": check_phase_b,
    "C": check_phase_c,
    "D": check_phase_d,
    "E": check_phase_e,
    "F": check_phase_f,
}


def main() -> int:
    args = sys.argv[1:]
    verbose = "--full" in args or "-v" in args
    single: Optional[str] = None
    if "--phase" in args:
        idx = args.index("--phase")
        if idx + 1 < len(args):
            single = args[idx + 1].upper()

    print(f"\n{C['BOLD']}{'='*58}{C['RESET']}")
    print(f"{C['BOLD']}  P10 CERTIFICATION CHECKER  —  crypto_ai_terminal{C['RESET']}")
    print(f"{C['BOLD']}{'='*58}{C['RESET']}")

    if single and single != "G":
        fn = PHASE_MAP.get(single)
        if fn is None:
            print(f"Phase inconnue : {single}")
            return 1
        p = fn()
        print_phase(p, verbose=True)
        return 0 if p.passed else 1

    phases: list[PhaseResult] = []
    for key, fn in PHASE_MAP.items():
        t0 = time.monotonic()
        p = fn()
        elapsed = time.monotonic() - t0
        print_phase(p, verbose=verbose)
        if verbose:
            print(f"  {C['DIM']}({elapsed:.1f}s){C['RESET']}")
        phases.append(p)

    g = check_phase_g(phases)
    print_phase(g, verbose=verbose or single == "G")
    phases.append(g)

    print_summary(phases)
    return 0 if all(p.passed for p in phases) else 1


if __name__ == "__main__":
    sys.exit(main())
