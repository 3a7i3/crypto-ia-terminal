"""
certification/audit_trail_final.py — G-04
Piste d'audit finale du processus de certification P10 complet.

Collecte :
  - Certificats de chaque module (G-01)
  - Sceaux immuables (G-02)
  - Gel documentaire (G-03)
  - Snapshot KPI live (P10-F)
  - Signoff opérateur (G-03 support)

Génère certification/AUDIT_TRAIL.json et l'inscrit dans la BlackBox.

Usage:
  from certification.audit_trail_final import AuditTrailFinal
  audit = AuditTrailFinal()
  trail = audit.compile()
  audit.save(trail)
  audit.store_in_blackbox(trail)
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

from certification.doc_freeze import DocFreeze
from certification.immutable_stamp import ImmutableStamp
from certification.module_certifier import _REGISTRY, ModuleCertifier

_ROOT = Path(__file__).parent.parent
_TRAIL_FILE = _ROOT / "certification" / "AUDIT_TRAIL.json"
_DEFAULT_KEY = b"p10_audit_trail_key_v1"


@dataclass
class AuditSection:
    name: str
    passed: bool
    count_ok: int
    count_total: int
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "count_ok": self.count_ok,
            "count_total": self.count_total,
            "details": self.details[:20],
        }


@dataclass
class AuditTrail:
    sections: list[AuditSection] = field(default_factory=list)
    compiled_at: float = field(default_factory=time.time)
    compiled_date: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        from datetime import datetime, timezone

        self.compiled_date = datetime.fromtimestamp(
            self.compiled_at, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")

    @property
    def complete(self) -> bool:
        return all(s.passed for s in self.sections)

    def _canonical(self) -> dict:
        return {
            "sections": [s.to_dict() for s in self.sections],
            "compiled_at": round(self.compiled_at, 3),
        }

    def sign(self, key: bytes = _DEFAULT_KEY) -> "AuditTrail":
        canonical = json.dumps(self._canonical(), sort_keys=True)
        self.signature = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return self

    def verify_signature(self, key: bytes = _DEFAULT_KEY) -> bool:
        if not self.signature:
            return False
        canonical = json.dumps(self._canonical(), sort_keys=True)
        expected = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_dict(self) -> dict:
        d = self._canonical()
        d["compiled_date"] = self.compiled_date
        d["complete"] = self.complete
        d["signature"] = self.signature
        return d

    def summary(self) -> str:
        status = "COMPLETE" if self.complete else "INCOMPLET"
        lines = [f"AuditTrail P10 — {status} — {self.compiled_date}"]
        for s in self.sections:
            mark = "OK" if s.passed else "FAIL"
            lines.append(f"  [{mark}] {s.name}: {s.count_ok}/{s.count_total}")
            for d in s.details[:3]:
                lines.append(f"        {d}")
        if self.signature:
            lines.append(f"  sig={self.signature[:16]}...")
        return "\n".join(lines)


# ── Compiler ──────────────────────────────────────────────────────────────────


class AuditTrailFinal:
    """Compile la piste d'audit finale et l'inscrit dans la BlackBox."""

    def __init__(
        self,
        root: Optional[Path] = None,
        trail_file: Optional[Path] = None,
        sign_key: bytes = _DEFAULT_KEY,
        certifier: Optional[ModuleCertifier] = None,
        stamper: Optional[ImmutableStamp] = None,
        doc_freeze: Optional[DocFreeze] = None,
    ) -> None:
        self._root = root or _ROOT
        self._trail_file = trail_file or _TRAIL_FILE
        self._key = sign_key
        self._mc = certifier or ModuleCertifier(root=self._root)
        self._stamp = stamper or ImmutableStamp(root=self._root)
        self._df = doc_freeze or DocFreeze(root=self._root)

    # ── Sections ──────────────────────────────────────────────────────────────

    def _section_modules(self) -> AuditSection:
        total = len(_REGISTRY)
        ok = 0
        details: list[str] = []
        for mid in _REGISTRY:
            cert = self._mc.load(mid)
            if cert and cert.passed:
                ok += 1
            else:
                details.append(f"Non certifié : {mid}")
        return AuditSection(
            name="Certifications modules (G-01)",
            passed=ok == total,
            count_ok=ok,
            count_total=total,
            details=details[:10],
        )

    def _section_stamps(self) -> AuditSection:
        results = self._stamp.verify_all()
        ok = sum(1 for passed, _ in results.values() if passed)
        details = [
            f"{mid}: {reason}"
            for mid, (passed, reason) in results.items()
            if not passed
        ]
        return AuditSection(
            name="Sceaux immuables (G-02)",
            passed=len(details) == 0,
            count_ok=ok,
            count_total=len(results),
            details=details[:10],
        )

    def _section_doc_freeze(self) -> AuditSection:
        ok, drifts = self._df.verify()
        m = self._df.load_manifest()
        total = len(m.docs) if m else 0
        return AuditSection(
            name="Gel documentaire (G-03)",
            passed=ok,
            count_ok=total - len(drifts),
            count_total=total,
            details=drifts[:10],
        )

    def _section_live_kpi(self) -> AuditSection:
        p10_phase = os.getenv("P10_PHASE", "F-01")
        cert_path = self._root / "certification" / f"CERTIFIED_{p10_phase}.json"
        passed = cert_path.exists()
        return AuditSection(
            name=f"Validation live P10-F ({p10_phase})",
            passed=passed,
            count_ok=1 if passed else 0,
            count_total=1,
            details=(
                []
                if passed
                else [f"CERTIFIED_{p10_phase}.json absent — validation live en cours"]
            ),
        )

    def _section_operator_signoff(self) -> AuditSection:
        p10_phase = os.getenv("P10_PHASE", "F-01")
        signoff_path = self._root / "certification" / f"signoff_{p10_phase}.json"
        passed = signoff_path.exists()
        return AuditSection(
            name=f"Signoff opérateur ({p10_phase})",
            passed=passed,
            count_ok=1 if passed else 0,
            count_total=1,
            details=[] if passed else ["Signoff opérateur non signé"],
        )

    # ── Compile & save ────────────────────────────────────────────────────────

    def compile(self) -> AuditTrail:
        trail = AuditTrail(
            sections=[
                self._section_modules(),
                self._section_stamps(),
                self._section_doc_freeze(),
                self._section_live_kpi(),
                self._section_operator_signoff(),
            ]
        )
        trail.sign(self._key)
        return trail

    def save(self, trail: AuditTrail) -> Path:
        self._trail_file.parent.mkdir(parents=True, exist_ok=True)
        self._trail_file.write_text(
            json.dumps(trail.to_dict(), indent=2),
            encoding="utf-8",
        )
        return self._trail_file

    def store_in_blackbox(self, trail: AuditTrail) -> bool:
        bb_path = self._root / "databases" / "black_box.jsonl"
        try:
            entry = {
                "type": "P10_AUDIT_TRAIL",
                "ts": trail.compiled_at,
                "complete": trail.complete,
                "sections": len(trail.sections),
                "signature": trail.signature,
                "summary": trail.summary()[:500],
            }
            with open(bb_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            return True
        except Exception:
            return False

    def load(self) -> Optional[AuditTrail]:
        if not self._trail_file.exists():
            return None
        data = json.loads(self._trail_file.read_text(encoding="utf-8"))
        trail = AuditTrail(
            sections=[
                AuditSection(
                    **{
                        k: v
                        for k, v in s.items()
                        if k in AuditSection.__dataclass_fields__
                    }
                )
                for s in data.get("sections", [])
            ],
            compiled_at=float(data.get("compiled_at", 0.0)),
        )
        trail.compiled_date = data.get("compiled_date", "")
        trail.signature = data.get("signature", "")
        return trail
