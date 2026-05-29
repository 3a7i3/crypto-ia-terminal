"""
certification/live_kpi_auditor.py — G-02
Audit des KPI live P10-F.

Lit PhaseKPITracker + PhaseCertifier, valide les critères minimum de la phase
courante, et produit un rapport signé HMAC-SHA256.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).parent.parent

# Critères minimum par phase (doit correspondre à PHASE_CRITERIA dans phase_kpi_tracker.py)
_MIN_CRITERIA: dict[str, dict[str, float]] = {
    "F-01": {"win_rate": 0.45, "sharpe_ratio": 1.0, "max_drawdown": 0.02},
    "F-02": {"win_rate": 0.45, "sharpe_ratio": 1.2, "max_drawdown": 0.04},
    "F-03": {"win_rate": 0.45, "sharpe_ratio": 1.5, "max_drawdown": 0.08},
    "F-04": {"win_rate": 0.45, "sharpe_ratio": 1.5, "max_drawdown": 0.12},
    "F-05": {"win_rate": 0.40, "sharpe_ratio": 1.2, "max_drawdown": 0.20},
}

_DEFAULT_SIGN_KEY = b"p10_kpi_audit_key"


@dataclass
class KPISnapshot:
    phase: str
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "win_rate": round(self.win_rate, 6),
            "sharpe_ratio": round(self.sharpe_ratio, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "total_trades": self.total_trades,
            "timestamp": self.timestamp,
        }


@dataclass
class KPIViolation:
    metric: str
    actual: float
    required: float

    @property
    def delta(self) -> float:
        return self.actual - self.required

    def __str__(self) -> str:
        return (
            f"{self.metric}: {self.actual:.4f} < requis {self.required:.4f} "
            f"(delta {self.delta:+.4f})"
        )


@dataclass
class KPIAuditReport:
    phase: str
    snapshot: KPISnapshot
    violations: list[KPIViolation] = field(default_factory=list)
    signature: str = ""
    audit_ts: float = field(default_factory=time.time)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0

    def sign(self, key: bytes = _DEFAULT_SIGN_KEY) -> "KPIAuditReport":
        canonical = json.dumps(self.snapshot.to_dict(), sort_keys=True)
        self.signature = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return self

    def verify(self, key: bytes = _DEFAULT_SIGN_KEY) -> bool:
        if not self.signature:
            return False
        canonical = json.dumps(self.snapshot.to_dict(), sort_keys=True)
        expected = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"KPIAuditReport [{self.phase}] — {status}"]
        snap = self.snapshot
        lines.append(
            f"  win_rate={snap.win_rate:.2%}  sharpe={snap.sharpe_ratio:.3f}  "
            f"drawdown={snap.max_drawdown:.2%}  trades={snap.total_trades}"
        )
        for v in self.violations:
            lines.append(f"  [FAIL] {v}")
        if self.signature:
            lines.append(f"  sig={self.signature[:16]}...")
        return "\n".join(lines)


# ── Auditor ───────────────────────────────────────────────────────────────────


class LiveKPIAuditor:
    """Lit le PhaseKPITracker actif et audite les KPI live de la phase courante."""

    def __init__(
        self,
        phase: Optional[str] = None,
        kpi_tracker: Optional[Any] = None,
        sign_key: bytes = _DEFAULT_SIGN_KEY,
    ) -> None:
        self._phase = phase or os.getenv("P10_PHASE", "F-01")
        self._tracker = kpi_tracker
        self._sign_key = sign_key

    # ── Lecture snapshot ──────────────────────────────────────────────────────

    def _read_snapshot(self) -> KPISnapshot:
        if self._tracker is not None:
            snap = self._tracker.snapshot()
            return KPISnapshot(
                phase=self._phase,
                win_rate=float(snap.get("win_rate", 0.0)),
                sharpe_ratio=float(snap.get("sharpe_ratio", 0.0)),
                max_drawdown=float(snap.get("max_drawdown", 0.0)),
                total_trades=int(snap.get("total_trades", 0)),
            )
        # Fallback : lire depuis databases/kpi_snapshot.json si présent
        kpi_path = _ROOT / "databases" / "kpi_snapshot.json"
        if kpi_path.exists():
            try:
                data = json.loads(kpi_path.read_text(encoding="utf-8"))
                return KPISnapshot(
                    phase=self._phase,
                    win_rate=float(data.get("win_rate", 0.0)),
                    sharpe_ratio=float(data.get("sharpe_ratio", 0.0)),
                    max_drawdown=float(data.get("max_drawdown", 0.0)),
                    total_trades=int(data.get("total_trades", 0)),
                )
            except Exception:
                pass
        # Snapshot vide — phase non démarrée
        return KPISnapshot(
            phase=self._phase,
            win_rate=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            total_trades=0,
        )

    # ── Validation critères ───────────────────────────────────────────────────

    def _check_violations(self, snap: KPISnapshot) -> list[KPIViolation]:
        criteria = _MIN_CRITERIA.get(self._phase, {})
        violations: list[KPIViolation] = []

        if snap.win_rate < criteria.get("win_rate", 0.0):
            violations.append(
                KPIViolation("win_rate", snap.win_rate, criteria["win_rate"])
            )

        if snap.sharpe_ratio < criteria.get("sharpe_ratio", 0.0):
            violations.append(
                KPIViolation(
                    "sharpe_ratio", snap.sharpe_ratio, criteria["sharpe_ratio"]
                )
            )

        # drawdown : violation si dépasse le max autorisé
        dd = abs(snap.max_drawdown)
        max_dd = criteria.get("max_drawdown", 1.0)
        if dd > max_dd:
            violations.append(KPIViolation("max_drawdown", dd, max_dd))

        return violations

    # ── Audit complet ─────────────────────────────────────────────────────────

    def audit(self) -> KPIAuditReport:
        snapshot = self._read_snapshot()
        violations = self._check_violations(snapshot)
        report = KPIAuditReport(
            phase=self._phase,
            snapshot=snapshot,
            violations=violations,
        )
        report.sign(self._sign_key)
        return report

    def audit_for_phase(self, phase: str) -> KPIAuditReport:
        """Audite une phase spécifique (utile pour valider F-01 depuis F-02)."""
        original = self._phase
        self._phase = phase
        try:
            return self.audit()
        finally:
            self._phase = original
