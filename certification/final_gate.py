"""
certification/final_gate.py — G-04
Gate finale go/no-go — combine G-01 + G-02 + G-03.

Génère certification/CERTIFIED_{phase}.json quand tout est vert.
Intègre avec hash_verifier.py (recompute hashes à la fin).

Usage :
  from certification.final_gate import FinalGate
  gate = FinalGate(phase="F-01", operator="Mathieu")
  result = gate.run()
  if result.go:
      gate.save_certificate()
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from certification.live_kpi_auditor import KPIAuditReport, LiveKPIAuditor
from certification.operator_signoff import OperatorSignoff, SignoffDecision
from certification.prerequisite_checker import PrerequisiteChecker, PrerequisiteReport

_ROOT = Path(__file__).parent.parent
_CERT_DIR = _ROOT / "certification"
_DEFAULT_SIGN_KEY = b"p10_final_gate_key"


@dataclass
class GateCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class FinalGateResult:
    phase: str
    prerequisite_ok: bool
    kpi_ok: bool
    signoff_ok: bool
    signoff_approved: bool
    gate_checks: list[GateCheck] = field(default_factory=list)
    certificate_path: Optional[Path] = None
    generated_at: float = field(default_factory=time.time)

    @property
    def go(self) -> bool:
        return (
            self.prerequisite_ok
            and self.kpi_ok
            and self.signoff_ok
            and self.signoff_approved
        )

    def summary(self) -> str:
        lines = [f"FinalGate [{self.phase}] — {'GO' if self.go else 'NO-GO'}"]
        checks = [
            ("Prérequis P10-A→F", self.prerequisite_ok),
            ("KPI live", self.kpi_ok),
            ("Signoff présent", self.signoff_ok),
            ("Signoff approuvé", self.signoff_approved),
        ]
        for name, ok in checks:
            mark = "OK" if ok else "FAIL"
            lines.append(f"  [{mark}] {name}")
        for c in self.gate_checks:
            mark = "OK" if c.passed else "FAIL"
            lines.append(f"  [{mark}] {c.name}")
            if c.detail and not c.passed:
                lines.append(f"        {c.detail}")
        if self.certificate_path:
            lines.append(f"  Certificat : {self.certificate_path}")
        return "\n".join(lines)


# ── Gate ──────────────────────────────────────────────────────────────────────


class FinalGate:
    """Gate finale de certification P10-G — combine G-01/G-02/G-03."""

    def __init__(
        self,
        phase: Optional[str] = None,
        operator: str = "operator",
        kpi_tracker: Optional[Any] = None,
        sign_key: bytes = _DEFAULT_SIGN_KEY,
        cert_dir: Optional[Path] = None,
    ) -> None:
        self._phase = phase or os.getenv("P10_PHASE", "F-01")
        self._operator = operator
        self._kpi_tracker = kpi_tracker
        self._sign_key = sign_key
        self._cert_dir = cert_dir or _CERT_DIR
        self._result: Optional[FinalGateResult] = None

    # ── Sous-checks ───────────────────────────────────────────────────────────

    def _run_prerequisites(self) -> tuple[bool, list[GateCheck]]:
        checker = PrerequisiteChecker(root=_ROOT)
        report = checker.run()
        checks: list[GateCheck] = []
        for pc in report.phase_checks:
            checks.append(
                GateCheck(
                    name=f"Modules {pc.phase} présents",
                    passed=pc.passed,
                    detail=f"Manquants : {pc.missing}" if pc.missing else "",
                )
            )
        checks.append(
            GateCheck(
                name="Imports P10-F",
                passed=report.imports_ok,
                detail=(
                    "; ".join(report.import_errors[:3]) if report.import_errors else ""
                ),
            )
        )
        return report.passed, checks

    def _run_kpi_audit(self) -> tuple[bool, list[GateCheck]]:
        auditor = LiveKPIAuditor(
            phase=self._phase,
            kpi_tracker=self._kpi_tracker,
        )
        report = auditor.audit()
        checks: list[GateCheck] = []
        if report.violations:
            for v in report.violations:
                checks.append(
                    GateCheck(
                        name=f"KPI {v.metric}",
                        passed=False,
                        detail=str(v),
                    )
                )
        else:
            snap = report.snapshot
            checks.append(
                GateCheck(
                    name="KPI live",
                    passed=True,
                    detail=(
                        f"WR={snap.win_rate:.1%} Sharpe={snap.sharpe_ratio:.2f} "
                        f"DD={snap.max_drawdown:.1%} trades={snap.total_trades}"
                    ),
                )
            )
        return report.passed, checks

    def _run_signoff(self) -> tuple[bool, bool, list[GateCheck]]:
        sf = OperatorSignoff(
            phase=self._phase,
            operator=self._operator,
            signoff_dir=self._cert_dir,
        )
        checks: list[GateCheck] = []
        signed = sf.is_signed()
        checks.append(
            GateCheck(
                name="Signoff opérateur signé",
                passed=signed,
                detail=(
                    "" if signed else f"Fichier attendu : signoff_{self._phase}.json"
                ),
            )
        )
        approved = False
        if signed:
            try:
                decision = sf.load()
                approved = decision.approved
                if not approved:
                    for v in decision.operational_violations:
                        checks.append(
                            GateCheck(name=f"Operational : {v}", passed=False)
                        )
                else:
                    checks.append(GateCheck(name="Critères opérationnels", passed=True))
            except Exception as exc:
                checks.append(
                    GateCheck(name="Lecture signoff", passed=False, detail=str(exc))
                )
        return signed, approved, checks

    # ── Certificat ────────────────────────────────────────────────────────────

    def save_certificate(
        self,
        prereq_report: Optional[PrerequisiteReport] = None,
        kpi_report: Optional[KPIAuditReport] = None,
        signoff: Optional[SignoffDecision] = None,
    ) -> Path:
        if self._result is None or not self._result.go:
            raise RuntimeError("FinalGate is NO-GO — certificat refusé")

        cert: dict[str, Any] = {
            "phase": self._phase,
            "operator": self._operator,
            "certified_at": time.time(),
            "go": True,
        }
        if kpi_report:
            cert["kpi_snapshot"] = kpi_report.snapshot.to_dict()
            cert["kpi_signature"] = kpi_report.signature
        if signoff:
            cert["signoff"] = signoff.to_dict()

        canonical = json.dumps(cert, sort_keys=True)
        cert["gate_signature"] = hmac.new(
            self._sign_key, canonical.encode(), hashlib.sha256
        ).hexdigest()

        self._cert_dir.mkdir(parents=True, exist_ok=True)
        path = self._cert_dir / f"CERTIFIED_{self._phase}.json"
        path.write_text(json.dumps(cert, indent=2), encoding="utf-8")
        self._result.certificate_path = path
        return path

    def verify_certificate(self, phase: Optional[str] = None) -> bool:
        target = phase or self._phase
        path = self._cert_dir / f"CERTIFIED_{target}.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sig = data.pop("gate_signature", "")
            canonical = json.dumps(data, sort_keys=True)
            expected = hmac.new(
                self._sign_key, canonical.encode(), hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(sig, expected)
        except Exception:
            return False

    # ── Run complet ───────────────────────────────────────────────────────────

    def run(self) -> FinalGateResult:
        all_checks: list[GateCheck] = []

        prereq_ok, prereq_checks = self._run_prerequisites()
        all_checks.extend(prereq_checks)

        kpi_ok, kpi_checks = self._run_kpi_audit()
        all_checks.extend(kpi_checks)

        signoff_ok, signoff_approved, sf_checks = self._run_signoff()
        all_checks.extend(sf_checks)

        self._result = FinalGateResult(
            phase=self._phase,
            prerequisite_ok=prereq_ok,
            kpi_ok=kpi_ok,
            signoff_ok=signoff_ok,
            signoff_approved=signoff_approved,
            gate_checks=all_checks,
        )
        return self._result
