"""Politiques d'admission — Level A pur (Phase 5.2.4).

Level A = INV-001 seul :

    canonical_n_positions < hard_max

Fonction pure, indépendante de PortfolioBrain. Aucune exposition,
aucune corrélation, aucun hedge, aucun levier, aucune personality.

C'est un invariant mécanique — pas une version partielle cachée de
PortfolioBrain (correction opérateur Phase 5.2 §4). Les Level B (shadow
PortfolioBrain) et Level C (strict) arriveront plus tard, chacun dans
son propre module ; Level A ne doit jamais les importer.
"""

from __future__ import annotations

from paper_trading.admission_types import (
    AdmissionBlocker,
    AdmissionDecision,
    AdmissionLevel,
    AdmissionVerdict,
)

_CHECKED_BY = "evaluate_hard_portfolio_ceiling"


def evaluate_hard_portfolio_ceiling(
    canonical_n_positions: int,
    hard_max: int,
) -> AdmissionVerdict:
    """INV-001 seul : ``canonical_n_positions < hard_max``.

    Args:
        canonical_n_positions : nombre courant de positions ouvertes du
            portefeuille PAPER canonique (via ``paper_portfolio_view``).
        hard_max : plafond global de portefeuille (``PB_MAX_POSITIONS``).

    Returns:
        AdmissionVerdict Level A avec ``n_at_check`` et
        ``hard_max_at_check`` capturés pour permettre la re-vérification
        TOCTOU à la frontière d'écriture (P5-04).

    Explicitement hors périmètre :
      * INV-002 (``personality.max_positions``) — orthogonal, évalué ailleurs.
      * INV-003 / INV-004 (états OVER_LIMIT_*) — événements distincts
        produits par le simulateur ou la boucle de reload, portent leurs
        propres verdicts.
      * exposition / corrélation / levier — Level C uniquement.
    """
    if canonical_n_positions < 0:
        raise ValueError(f"canonical_n_positions négatif: {canonical_n_positions}")
    if hard_max < 0:
        raise ValueError(f"hard_max négatif: {hard_max}")

    if canonical_n_positions < hard_max:
        return AdmissionVerdict(
            decision=AdmissionDecision.APPROVED,
            level=AdmissionLevel.A,
            n_at_check=canonical_n_positions,
            hard_max_at_check=hard_max,
            blocker=AdmissionBlocker.NONE,
            reason="",
            checked_by=_CHECKED_BY,
        )
    return AdmissionVerdict(
        decision=AdmissionDecision.REJECTED,
        level=AdmissionLevel.A,
        n_at_check=canonical_n_positions,
        hard_max_at_check=hard_max,
        blocker=AdmissionBlocker.PORTFOLIO_HARD_CEILING,
        reason=f"Max positions atteint: {canonical_n_positions}/{hard_max}",
        checked_by=_CHECKED_BY,
    )


__all__ = ["evaluate_hard_portfolio_ceiling"]
