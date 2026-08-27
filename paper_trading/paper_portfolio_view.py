"""Adaptateur PAPER → contrat PortfolioBrain.

Traduit ``MexcSimulator._positions`` (source de vérité paper) en
``list[PositionView]`` compatible avec le contrat lu par
``PortfolioBrain._snapshot`` / ``_correlation_risk`` / ``_weighted_leverage``.

Cet adaptateur est PASSIF : il ne mute rien, ne décide rien. Il rend
observable pour PortfolioBrain ce que le simulateur détient réellement,
sans coupler le simulateur au brain (Q1/Q5 de Phase 3, ADR-0007).

Différences de contrat traitées ici :

  * ``qty_usd`` (MexcPosition) → ``size_usd`` (contrat brain)
  * ``OrderSide.{BUY,SELL}``   → ``PortfolioSide.{LONG,SHORT}``
  * ``leverage`` absent         → défaut 1 (paper spot-like)
  * ``regime`` None             → ``"unknown"`` (coalesce)
  * ``closed`` absent           → dérivé via ``MexcPosition.is_open``
    (les positions fermées sont exclues de la vue)

Le champ ``pos_id`` est conservé (utile pour l'invariant d'identité P3
au commit suivant) même s'il n'est pas lu par PortfolioBrain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:  # pragma: no cover
    from paper_trading.mexc_simulator import MexcSimulator


class PortfolioSide(str, Enum):
    LONG = "long"
    SHORT = "short"


_MEXC_SIDE_TO_PORTFOLIO = {
    "BUY": PortfolioSide.LONG,
    "SELL": PortfolioSide.SHORT,
}


@dataclass(frozen=True)
class PositionView:
    """Vue immuable d'une position paper conforme au contrat PortfolioBrain."""

    symbol: str
    size_usd: float
    regime: str
    pnl_usd: float
    side: PortfolioSide
    leverage: int = 1
    closed: bool = False
    pos_id: str = ""
    # Personality de la position (portée par MexcPosition.personality).
    # Non lue par PortfolioBrain — sert au reporting honnête (portfolio_status).
    personality: str = ""


def _map_side(raw_side: object) -> PortfolioSide:
    """Mappe l'``OrderSide`` MexcSimulator vers le vocabulaire portefeuille.

    Accepte un enum ``OrderSide`` ou une chaîne — robustesse face à un
    ``value`` ou un ``name``.
    """
    key = getattr(raw_side, "value", raw_side)
    key = str(key).upper()
    try:
        return _MEXC_SIDE_TO_PORTFOLIO[key]
    except KeyError as exc:
        raise ValueError(f"Unknown MexcSimulator side: {raw_side!r}") from exc


def _position_to_view(pos: object) -> PositionView:
    return PositionView(
        symbol=str(pos.symbol),
        size_usd=float(pos.qty_usd),
        regime=(getattr(pos, "regime", None) or "unknown"),
        pnl_usd=float(getattr(pos, "pnl_usd", 0.0) or 0.0),
        side=_map_side(pos.side),
        leverage=1,
        closed=False,
        pos_id=str(getattr(pos, "pos_id", "") or ""),
        personality=str(getattr(pos, "personality", "") or ""),
    )


def paper_portfolio_view(simulator: "MexcSimulator | None") -> List[PositionView]:
    """Snapshot immuable des positions PAPER OUVERTES de ``simulator``.

    Ordre déterministe (tri alphabétique du symbole) : requis par P3
    (identity hash stable) et CT-07 (contract stability).

    Le simulateur peut muter en concurrence pendant la construction : le
    pire cas observable est un snapshot légèrement stale, jamais une
    corruption. L'invariant TOCTOU est géré au niveau écriture par
    l'``AdmissionVerdict`` (commit suivant).
    """
    if simulator is None:
        return []
    raw = getattr(simulator, "_positions", None) or {}
    return [
        _position_to_view(raw[sym])
        for sym in sorted(raw.keys())
        if getattr(raw[sym], "is_open", True)
    ]


__all__ = ["PortfolioSide", "PositionView", "paper_portfolio_view"]
