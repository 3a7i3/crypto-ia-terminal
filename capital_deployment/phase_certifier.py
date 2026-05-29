"""
capital_deployment/phase_certifier.py — Phase Certification

Signs each completed phase with HMAC-SHA256.
Certification is immutable and verifiable after reload.

Usage:
    certifier = PhaseCertifier()
    cert = certifier.certify("F-01", kpi_tracker, force=True)
    certifier.save(path)
    certifier2 = PhaseCertifier()
    certifier2.load(path)
    assert certifier2.is_certified("F-01")
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from capital_deployment.capital_throttle import PHASE_ORDER
from capital_deployment.phase_kpi_tracker import PHASE_CRITERIA, PhaseKPITracker
from observability.json_logger import get_logger

_log = get_logger("capital_deployment.phase_certifier")

_DEFAULT_KEY = os.getenv("P10_CERT_KEY", "p10_phase_certifier_default_key").encode()
_CERT_PATH = Path(os.getenv("P10_CERT_PATH", "cache/startup/phase_certifications.json"))


@dataclass
class PhaseCertification:
    phase: str
    certified_at: float
    duration_days: float
    final_win_rate: float
    final_sharpe: float
    final_max_drawdown: float
    total_trades: int
    unsigned_decisions: int
    hmac_sig: str = ""

    def _canonical(self) -> str:
        return json.dumps(
            {
                "phase": self.phase,
                "certified_at": round(self.certified_at, 3),
                "duration_days": round(self.duration_days, 3),
                "final_win_rate": round(self.final_win_rate, 6),
                "final_sharpe": round(self.final_sharpe, 6),
                "final_max_drawdown": round(self.final_max_drawdown, 6),
                "total_trades": self.total_trades,
                "unsigned_decisions": self.unsigned_decisions,
            },
            sort_keys=True,
        )

    def sign(self, key: bytes) -> "PhaseCertification":
        self.hmac_sig = hmac.new(
            key, self._canonical().encode(), hashlib.sha256
        ).hexdigest()
        return self

    def verify(self, key: bytes) -> bool:
        if not self.hmac_sig:
            return False
        expected = hmac.new(key, self._canonical().encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.hmac_sig)

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "certified_at": round(self.certified_at, 3),
            "duration_days": round(self.duration_days, 3),
            "final_win_rate": round(self.final_win_rate, 4),
            "final_sharpe": round(self.final_sharpe, 3),
            "final_max_drawdown": round(self.final_max_drawdown, 4),
            "total_trades": self.total_trades,
            "unsigned_decisions": self.unsigned_decisions,
            "hmac_sig": self.hmac_sig,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PhaseCertification":
        c = cls(
            phase=str(d["phase"]),
            certified_at=float(d["certified_at"]),
            duration_days=float(d["duration_days"]),
            final_win_rate=float(d["final_win_rate"]),
            final_sharpe=float(d["final_sharpe"]),
            final_max_drawdown=float(d["final_max_drawdown"]),
            total_trades=int(d["total_trades"]),
            unsigned_decisions=int(d.get("unsigned_decisions", 0)),
        )
        c.hmac_sig = str(d.get("hmac_sig", ""))
        return c


class PhaseCertifier:
    """
    Issues HMAC-SHA256 signed certifications for each deployment phase.

    Usage:
        certifier = PhaseCertifier(key=b"my_secret")
        cert = certifier.certify("F-01", tracker, force=True)
        certifier.save(path)
    """

    def __init__(
        self,
        key: bytes = _DEFAULT_KEY,
        cert_path: Optional[Path] = None,
    ) -> None:
        self._key = key
        self._cert_path = cert_path or _CERT_PATH
        self._certifications: dict[str, PhaseCertification] = {}

    def certify(
        self,
        phase: str,
        kpi_tracker: PhaseKPITracker,
        force: bool = False,
    ) -> PhaseCertification:
        """
        Certify a phase. Raises ValueError if criteria not met unless force=True.
        """
        snap = kpi_tracker.snapshot()
        violations = snap.violations(phase)

        if violations and not force:
            raise ValueError(f"Phase {phase} non certifiable: {violations}")

        cert = PhaseCertification(
            phase=phase,
            certified_at=time.time(),
            duration_days=snap.days_elapsed,
            final_win_rate=snap.win_rate,
            final_sharpe=snap.sharpe,
            final_max_drawdown=snap.max_drawdown,
            total_trades=snap.total_trades,
            unsigned_decisions=snap.unsigned_decisions,
        )
        cert.sign(self._key)
        self._certifications[phase] = cert
        _log.info(
            "[PhaseCertifier] %s certifiée — Sharpe=%.2f DD=%.1f%% trades=%d",
            phase,
            snap.sharpe,
            snap.max_drawdown * 100,
            snap.total_trades,
        )
        return cert

    def verify(self, phase: str) -> bool:
        cert = self._certifications.get(phase)
        return cert is not None and cert.verify(self._key)

    def is_certified(self, phase: str) -> bool:
        return self.verify(phase)

    def all_certified_to(self, phase: str) -> bool:
        """True if all phases up to and including `phase` are certified and valid."""
        if phase not in PHASE_ORDER:
            return False
        idx = PHASE_ORDER.index(phase)
        return all(self.is_certified(p) for p in PHASE_ORDER[: idx + 1])

    def get(self, phase: str) -> Optional[PhaseCertification]:
        return self._certifications.get(phase)

    def certified_phases(self) -> list[str]:
        return [p for p in PHASE_ORDER if self.is_certified(p)]

    def save(self, path: Optional[Path] = None) -> None:
        target = path or self._cert_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "saved_at": time.time(),
                "certifications": {
                    p: c.to_dict() for p, c in self._certifications.items()
                },
            }
            target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.warning("[PhaseCertifier] Erreur sauvegarde: %s", exc)

    def load(self, path: Optional[Path] = None) -> None:
        target = path or self._cert_path
        try:
            if not target.exists():
                return
            data = json.loads(target.read_text(encoding="utf-8"))
            for phase, cert_data in data.get("certifications", {}).items():
                self._certifications[phase] = PhaseCertification.from_dict(cert_data)
            _log.info(
                "[PhaseCertifier] %d certifications chargées depuis %s",
                len(self._certifications),
                target,
            )
        except Exception as exc:
            _log.warning("[PhaseCertifier] Erreur chargement: %s", exc)
