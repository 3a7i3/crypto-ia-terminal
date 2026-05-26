"""
exposure_manager.py — Gestionnaire d'exposition dynamique par état (P7).

L'exposition maximale par trade et totale dépend de l'état RiskGovernor.
Empêche le dépassement via exposure_used tracker.
"""

from __future__ import annotations

import os

from observability.json_logger import get_logger
from quant_hedge_ai.agents.risk.risk_governor import RiskState

_log = get_logger("exposure_manager")
# Plafond d'exposition totale (% du capital) par état
_MAX_TOTAL_EXPOSURE: dict[RiskState, float] = {
    RiskState.NORMAL: float(os.getenv("EM_MAX_NORMAL", "0.20")),
    RiskState.DEFENSIVE: float(os.getenv("EM_MAX_DEFENSIVE", "0.10")),
    RiskState.RISK_OFF: 0.0,
    RiskState.RECOVERY: float(os.getenv("EM_MAX_RECOVERY", "0.05")),
    RiskState.AGGRESSIVE: float(os.getenv("EM_MAX_AGGRESSIVE", "0.30")),
}


class ExposureManager:
    """Stub léger — cap par symbole (utilisé par CapitalAllocationEngine)."""

    def cap(
        self, proposed: dict[str, float], max_per_symbol: float = 0.25
    ) -> dict[str, float]:
        capped = {k: min(max_per_symbol, float(v)) for k, v in proposed.items()}
        total = sum(capped.values()) or 1.0
        return {k: round(v / total, 4) for k, v in capped.items()}


class DynamicExposureManager:
    """Gère et borne l'exposition au capital selon l'état de risque (P7)."""

    def __init__(self, total_capital: float) -> None:
        self._capital = max(1.0, total_capital)
        self._exposure_used: float = 0.0

    def update_capital(self, capital: float) -> None:
        self._capital = max(1.0, capital)

    def can_add_exposure(self, amount_usd: float, state: RiskState) -> tuple[bool, str]:
        """Retourne (ok, raison_refus). Vérifie le plafond d'exposition par état."""
        if state == RiskState.RISK_OFF:
            return False, "exposure refusée — état RISK_OFF"
        max_total = _MAX_TOTAL_EXPOSURE[state] * self._capital
        if self._exposure_used + amount_usd > max_total:
            return (
                False,
                f"exposure_used={self._exposure_used:.0f}+{amount_usd:.0f}"
                f">{max_total:.0f} ({state.value})",
            )
        return True, ""

    def record_open(self, amount_usd: float) -> None:
        self._exposure_used = max(0.0, self._exposure_used + amount_usd)

    def record_close(self, amount_usd: float) -> None:
        self._exposure_used = max(0.0, self._exposure_used - amount_usd)

    def sync_from_positions(self, open_positions: list) -> None:
        """Resynchronise depuis la liste des positions ouvertes."""
        total = 0.0
        for p in open_positions:
            if hasattr(p, "get"):
                total += float(p.get("size_usd", 0) or 0)
            else:
                total += float(getattr(p, "size_usd", 0) or 0)
        self._exposure_used = max(0.0, total)

    @property
    def exposure_used(self) -> float:
        return self._exposure_used

    @property
    def exposure_used_pct(self) -> float:
        return self._exposure_used / self._capital if self._capital > 0 else 0.0

    def snapshot(self, state: RiskState) -> dict:
        max_total = _MAX_TOTAL_EXPOSURE[state] * self._capital
        return {
            "exposure_used_usd": round(self._exposure_used, 2),
            "exposure_used_pct": round(self.exposure_used_pct * 100, 1),
            "max_total_usd": round(max_total, 2),
            "headroom_usd": round(max(0.0, max_total - self._exposure_used), 2),
        }
