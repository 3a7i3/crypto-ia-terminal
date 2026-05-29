"""
certification/operator_signoff.py — G-03
Signature opérateur pour la certification P10-G.

Génère un formulaire de décision structuré, l'enregistre avec HMAC-SHA256,
et persiste dans certification/signoff_{phase}.json.

Usage :
  from certification.operator_signoff import OperatorSignoff
  sf = OperatorSignoff(phase="F-01", operator="Mathieu")
  sf.sign_phase(kpi_ok=True, mode="TESTNET", comments="F-01 validé 7j continus")
  sf.save()
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).parent.parent
_SIGNOFF_DIR = _ROOT / "certification"
_DEFAULT_SIGN_KEY = b"p10_operator_signoff_key"


class OperatingMode(str, Enum):
    TESTNET = "TESTNET"
    LIVE = "LIVE"
    UNKNOWN = "UNKNOWN"


@dataclass
class SignoffDecision:
    phase: str
    operator: str
    mode: OperatingMode
    kpi_ok: bool
    shadow_days: float
    paper_sharpe: float
    paper_max_dd: float
    paper_win_rate: float
    killswitch_tested: bool
    risk_limits_loaded: bool
    failed_unresolved: int
    comments: str
    signed_at: float = field(default_factory=time.time)
    signature: str = ""

    # ── Sérialisation canonique ───────────────────────────────────────────────

    def _canonical(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "operator": self.operator,
            "mode": self.mode.value,
            "kpi_ok": self.kpi_ok,
            "shadow_days": round(self.shadow_days, 2),
            "paper_sharpe": round(self.paper_sharpe, 4),
            "paper_max_dd": round(self.paper_max_dd, 4),
            "paper_win_rate": round(self.paper_win_rate, 4),
            "killswitch_tested": self.killswitch_tested,
            "risk_limits_loaded": self.risk_limits_loaded,
            "failed_unresolved": self.failed_unresolved,
            "comments": self.comments,
            "signed_at": round(self.signed_at, 3),
        }

    def sign(self, key: bytes = _DEFAULT_SIGN_KEY) -> "SignoffDecision":
        canonical = json.dumps(self._canonical(), sort_keys=True)
        self.signature = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return self

    def verify(self, key: bytes = _DEFAULT_SIGN_KEY) -> bool:
        if not self.signature:
            return False
        canonical = json.dumps(self._canonical(), sort_keys=True)
        expected = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_dict(self) -> dict[str, Any]:
        d = self._canonical()
        d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignoffDecision":
        return cls(
            phase=data["phase"],
            operator=data["operator"],
            mode=OperatingMode(data.get("mode", "UNKNOWN")),
            kpi_ok=bool(data.get("kpi_ok", False)),
            shadow_days=float(data.get("shadow_days", 0.0)),
            paper_sharpe=float(data.get("paper_sharpe", 0.0)),
            paper_max_dd=float(data.get("paper_max_dd", 0.0)),
            paper_win_rate=float(data.get("paper_win_rate", 0.0)),
            killswitch_tested=bool(data.get("killswitch_tested", False)),
            risk_limits_loaded=bool(data.get("risk_limits_loaded", False)),
            failed_unresolved=int(data.get("failed_unresolved", 0)),
            comments=str(data.get("comments", "")),
            signed_at=float(data.get("signed_at", 0.0)),
            signature=str(data.get("signature", "")),
        )

    # ── Validation opérationnelle ─────────────────────────────────────────────

    @property
    def operational_violations(self) -> list[str]:
        violations = []
        if self.shadow_days < 7.0:
            violations.append(f"shadow_days={self.shadow_days:.1f} < 7.0 requis")
        if self.paper_sharpe < 0.8:
            violations.append(f"paper_sharpe={self.paper_sharpe:.3f} < 0.8 requis")
        if self.paper_max_dd > 0.08:
            violations.append(f"paper_max_dd={self.paper_max_dd:.2%} > 8% autorisé")
        if self.paper_win_rate < 0.52:
            violations.append(f"paper_win_rate={self.paper_win_rate:.2%} < 52% requis")
        if not self.killswitch_tested:
            violations.append("KillSwitch non testé en conditions réelles")
        if not self.risk_limits_loaded:
            violations.append("risk_limits non chargés")
        if self.failed_unresolved > 0:
            violations.append(f"{self.failed_unresolved} FAILED non résolu(s)")
        return violations

    @property
    def approved(self) -> bool:
        return len(self.operational_violations) == 0 and self.kpi_ok


# ── Signoff manager ───────────────────────────────────────────────────────────


class OperatorSignoff:
    """Interface de signature opérateur pour la certification P10-G."""

    def __init__(
        self,
        phase: Optional[str] = None,
        operator: str = "operator",
        sign_key: bytes = _DEFAULT_SIGN_KEY,
        signoff_dir: Optional[Path] = None,
    ) -> None:
        self._phase = phase or os.getenv("P10_PHASE", "F-01")
        self._operator = operator
        self._sign_key = sign_key
        self._dir = signoff_dir or _SIGNOFF_DIR
        self._decision: Optional[SignoffDecision] = None

    @property
    def decision(self) -> Optional[SignoffDecision]:
        return self._decision

    def sign_phase(
        self,
        *,
        kpi_ok: bool,
        mode: str = "TESTNET",
        shadow_days: float = 0.0,
        paper_sharpe: float = 0.0,
        paper_max_dd: float = 0.0,
        paper_win_rate: float = 0.0,
        killswitch_tested: bool = False,
        risk_limits_loaded: bool = False,
        failed_unresolved: int = 0,
        comments: str = "",
    ) -> SignoffDecision:
        self._decision = SignoffDecision(
            phase=self._phase,
            operator=self._operator,
            mode=(
                OperatingMode(mode)
                if mode in OperatingMode.__members__
                else OperatingMode.UNKNOWN
            ),
            kpi_ok=kpi_ok,
            shadow_days=shadow_days,
            paper_sharpe=paper_sharpe,
            paper_max_dd=paper_max_dd,
            paper_win_rate=paper_win_rate,
            killswitch_tested=killswitch_tested,
            risk_limits_loaded=risk_limits_loaded,
            failed_unresolved=failed_unresolved,
            comments=comments,
        )
        self._decision.sign(self._sign_key)
        return self._decision

    def save(self) -> Path:
        if self._decision is None:
            raise RuntimeError("Appelle sign_phase() avant save()")
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"signoff_{self._phase}.json"
        path.write_text(
            json.dumps(self._decision.to_dict(), indent=2),
            encoding="utf-8",
        )
        return path

    def load(self, phase: Optional[str] = None) -> SignoffDecision:
        target = phase or self._phase
        path = self._dir / f"signoff_{target}.json"
        if not path.exists():
            raise FileNotFoundError(f"Pas de signoff pour {target} : {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        decision = SignoffDecision.from_dict(data)
        if phase is None:
            self._decision = decision
        return decision

    def is_signed(self, phase: Optional[str] = None) -> bool:
        target = phase or self._phase
        path = self._dir / f"signoff_{target}.json"
        if not path.exists():
            return False
        try:
            d = SignoffDecision.from_dict(json.loads(path.read_text(encoding="utf-8")))
            return d.verify(self._sign_key)
        except Exception:
            return False
