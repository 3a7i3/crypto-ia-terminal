"""Statut de portefeuille honnête — source de données pour le reporting.

Corrige le mensonge du label ``META-STRATEGY: <personality>`` (Phase 2 §5,
critère de réussite P2) : ce label présentait la personality du DERNIER
signal traité comme si elle était la politique globale du portefeuille.

``build_portfolio_status`` produit une structure de niveau PORTEFEUILLE,
construite depuis la vue canonique (``paper_portfolio_view``), jamais
depuis ``meta_engine.current_personality()`` :

    current_positions       nombre réel de positions ouvertes
    hard_position_limit      plafond global (PB_MAX_POSITIONS)
    admission_state          OPEN | SATURATED | OVER_LIMIT
    positions_by_personality ventilation par personality d'ouverture
    positions_by_regime      ventilation par régime d'ouverture

Fonction pure, passive : elle observe et décrit, ne décide rien
(ADR-0007). Le reporting Telegram consomme ``to_dict()`` /
``render_portfolio_block()``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class AdmissionState(str, Enum):
    """État d'admission observable du portefeuille.

    * OPEN       — ``n < hard_max`` : de nouvelles entrées sont possibles.
    * SATURATED  — ``n == hard_max`` : plein, plus d'entrée jusqu'à fermeture.
    * OVER_LIMIT — ``n > hard_max`` : au-dessus du plafond (restore ou
      resserrement de politique). Aucune fermeture forcée (ADR-0007),
      nouvelles entrées bloquées.
    """

    OPEN = "OPEN"
    SATURATED = "SATURATED"
    OVER_LIMIT = "OVER_LIMIT"


@dataclass(frozen=True)
class PortfolioStatus:
    current_positions: int
    hard_position_limit: int
    admission_state: AdmissionState
    positions_by_personality: dict = field(default_factory=dict)
    positions_by_regime: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "current_positions": self.current_positions,
            "hard_position_limit": self.hard_position_limit,
            "admission_state": self.admission_state.value,
            "positions_by_personality": dict(self.positions_by_personality),
            "positions_by_regime": dict(self.positions_by_regime),
        }


def _admission_state(n: int, hard_max: int) -> AdmissionState:
    if n > hard_max:
        return AdmissionState.OVER_LIMIT
    if n == hard_max:
        return AdmissionState.SATURATED
    return AdmissionState.OPEN


def build_portfolio_status(
    view: Iterable,
    hard_max: int,
) -> PortfolioStatus:
    """Construit le statut honnête depuis la vue canonique.

    Args:
        view : itérable de ``PositionView`` (paper_portfolio_view).
        hard_max : plafond global (PB_MAX_POSITIONS).
    """
    if hard_max < 0:
        raise ValueError(f"hard_max négatif: {hard_max}")

    positions = list(view)
    n = len(positions)
    by_personality = Counter(
        (getattr(p, "personality", "") or "unknown") for p in positions
    )
    by_regime = Counter(
        (getattr(p, "regime", "") or "unknown") for p in positions
    )
    return PortfolioStatus(
        current_positions=n,
        hard_position_limit=hard_max,
        admission_state=_admission_state(n, hard_max),
        positions_by_personality=dict(by_personality),
        positions_by_regime=dict(by_regime),
    )


_STATE_MARK = {
    AdmissionState.OPEN: "",
    AdmissionState.SATURATED: " — SATURATED",
    AdmissionState.OVER_LIMIT: " ⚠ LIMIT EXCEEDED",
}


def render_portfolio_block(status: PortfolioStatus) -> str:
    """Rendu Telegram honnête du statut portefeuille.

    Ne présente jamais une personality de signal comme politique globale :
    la ligne POSITIONS porte le compteur réel vs le plafond, et la
    ventilation par personality est explicitement un décompte de positions
    ouvertes — pas une « stratégie active ».
    """
    lines = [
        "PORTFOLIO",
        f"  Positions: {status.current_positions} / {status.hard_position_limit}"
        f"{_STATE_MARK[status.admission_state]}",
    ]
    if status.positions_by_personality:
        vent = " | ".join(
            f"{name}:{cnt}"
            for name, cnt in sorted(status.positions_by_personality.items())
        )
        lines.append(f"  Par personality: {vent}")
    if status.positions_by_regime:
        vent = " | ".join(
            f"{name}:{cnt}"
            for name, cnt in sorted(status.positions_by_regime.items())
        )
        lines.append(f"  Par régime: {vent}")
    return "\n".join(lines)


__all__ = [
    "AdmissionState",
    "PortfolioStatus",
    "build_portfolio_status",
    "render_portfolio_block",
]
