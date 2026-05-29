"""
execution_context.py — Contexte d'exécution partagé (B-03)

Porte le contexte d'un cycle : cycle_id, régime, capital, flags système.
Immutable pendant un cycle via freeze(). Cohérence interne vérifiable.
Chiffrement mémoire : to_signed_dict() garantit l'intégrité HMAC de chaque contexte sérialisé.
"""

from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from cold_start.warmup_signer import sign
from observability.json_logger import get_logger

_log = get_logger("runtime.execution_context")

_CAPITAL_COHERENCE_TOL = 0.01


@dataclass
class ExecutionContext:
    """
    Contexte d'exécution courant partagé entre tous les composants d'un cycle.

    Invariant fondamental :
        abs(capital_total - (capital_used + capital_available)) <= 0.01

    Usage :
        ctx = ExecutionContext.new_cycle(prev_ctx)
        frozen = ctx.freeze()          # copie immuable pour le cycle
        coordinator.run_cycle(frozen)
    """

    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    current_regime: str = "UNKNOWN"
    regime_prob: float = 0.0
    risk_governor_state: str = "NORMAL"
    strategy_allocations: dict = field(default_factory=dict)
    capital_total: float = 0.0
    capital_used: float = 0.0
    capital_available: float = 0.0
    shadow_mode: bool = False
    safe_mode: bool = False
    kill_switch: bool = False
    started_at: float = field(default_factory=time.time)

    # ── Cohérence ─────────────────────────────────────────────────────────────

    def is_coherent(self) -> bool:
        """Vérifie que capital_total ≈ capital_used + capital_available (±0.01)."""
        expected = self.capital_used + self.capital_available
        return abs(self.capital_total - expected) <= _CAPITAL_COHERENCE_TOL

    def coherence_error(self) -> str:
        """Retourne la description de l'incohérence, ou '' si cohérent."""
        if self.is_coherent():
            return ""
        diff = abs(self.capital_total - (self.capital_used + self.capital_available))
        return (
            f"capital_total={self.capital_total:.2f} "
            f"≠ used({self.capital_used:.2f}) + available({self.capital_available:.2f}) "
            f"— écart={diff:.4f}"
        )

    # ── Immutabilité ─────────────────────────────────────────────────────────

    def freeze(self) -> "ExecutionContext":
        """
        Retourne une copie profonde destinée à un cycle.
        Convention : ne pas modifier la copie retournée.
        """
        return copy.deepcopy(self)

    # ── Sérialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "current_regime": self.current_regime,
            "regime_prob": round(self.regime_prob, 4),
            "risk_governor_state": self.risk_governor_state,
            "strategy_allocations": dict(self.strategy_allocations),
            "capital_total": round(self.capital_total, 2),
            "capital_used": round(self.capital_used, 2),
            "capital_available": round(self.capital_available, 2),
            "shadow_mode": self.shadow_mode,
            "safe_mode": self.safe_mode,
            "kill_switch": self.kill_switch,
            "started_at": round(self.started_at, 3),
        }

    def to_signed_dict(self) -> dict:
        """Sérialise avec signature HMAC — intégrité vérifiable."""
        d = self.to_dict()
        d["signature"] = sign(d)
        return d

    # ── Constructeurs ─────────────────────────────────────────────────────────

    @classmethod
    def from_snapshot(cls, snap: dict) -> "ExecutionContext":
        """Reconstruit un ExecutionContext depuis un snapshot brut (advisor_loop / tests)."""
        capital_total = float(snap.get("capital_total", 0.0))
        capital_used = float(snap.get("capital_used", 0.0))
        capital_available = float(
            snap.get("capital_available", capital_total - capital_used)
        )
        return cls(
            cycle_id=str(snap.get("cycle_id", str(uuid.uuid4())[:12])),
            current_regime=str(snap.get("current_regime", "UNKNOWN")),
            regime_prob=float(snap.get("regime_prob", 0.0)),
            risk_governor_state=str(snap.get("risk_governor_state", "NORMAL")),
            strategy_allocations=dict(snap.get("strategy_allocations", {})),
            capital_total=capital_total,
            capital_used=capital_used,
            capital_available=capital_available,
            shadow_mode=bool(snap.get("shadow_mode", False)),
            safe_mode=bool(snap.get("safe_mode", False)),
            kill_switch=bool(snap.get("kill_switch", False)),
            started_at=float(snap.get("started_at", time.time())),
        )

    @classmethod
    def new_cycle(
        cls,
        prev: Optional["ExecutionContext"] = None,
        **overrides: Any,
    ) -> "ExecutionContext":
        """
        Crée un nouveau contexte de cycle.
        Hérite de prev si fourni, génère un nouveau cycle_id et started_at.
        """
        base: dict = prev.to_dict() if prev else {}
        base.update(overrides)
        base["cycle_id"] = str(uuid.uuid4())[:12]
        base["started_at"] = time.time()
        return cls.from_snapshot(base)
