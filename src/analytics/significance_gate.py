"""
src/analytics/significance_gate.py — C5 : Gate de significativité alpha.

Réducteur booléen sur distribution déjà estimée (BootstrapResult).
Ne consomme pas les trades comme analyseur — seulement pour le check volumétrique.

Règles (non négociables) :
  G1 : len(trades) >= 30        — volume minimum
  G2 : bootstrap.p_value < 0.05 — stabilité statistique
  G3 : bootstrap.ci_low > 0     — robustesse CI (condition alpha réelle)
"""

from __future__ import annotations

from src.analytics.bootstrap_stability import BootstrapResult
from src.domain.trade_event import TradeEvent

MIN_TRADES = 30
MAX_P_VALUE = 0.05


def is_alpha_significant(
    bootstrap_result: BootstrapResult,
    trades: list[TradeEvent],
) -> bool:
    """
    Retourne True uniquement si les trois conditions sont simultanément satisfaites.
    Entrée directe de BURNIN_CALIBRATION_V3.
    """
    if len(trades) < MIN_TRADES:
        return False

    if bootstrap_result.p_value >= MAX_P_VALUE:
        return False

    if bootstrap_result.ci_low <= 0:
        return False

    return True
