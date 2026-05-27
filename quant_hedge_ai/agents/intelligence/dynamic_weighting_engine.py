"""
dynamic_weighting_engine.py — Dynamic Weighting Engine (P8)

Ajuste les poids de stratégies par performance relative tri-temporelle.
Appelé par StrategyAllocator après la rampe de régime, avant les pénalités.

Comportement :
  1. Score composite par stratégie = 50%×court(20) + 30%×moyen(50) + 20%×long
  2. Ajustement relatif : les stratégies au-dessus de la moyenne reçoivent
     un bonus de poids, les autres perdent. Cap asymétrique : +0.03/cycle
     (lent) vs -0.08/cycle (rapide), modulé par l'état du RiskGovernor.
  3. Redistribution proportionnelle au score composite (pas à poids égal).
  4. Baseline floor (0.05) pour chaque stratégie active.

Paramètres env :
  P8_DWE_BASELINE   : poids plancher (défaut 0.05)
  P8_DWE_UP_CAP     : bonus max/cycle (défaut 0.03)
  P8_DWE_DOWN_CAP   : malus max/cycle (défaut 0.08)
  P8_DWE_W_SHORT    : poids fenêtre courte (défaut 0.50)
  P8_DWE_W_MED      : poids fenêtre moyenne (défaut 0.30)
  P8_DWE_W_FULL     : poids historique complet (défaut 0.20)
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.dynamic_weighting_engine")

_BASELINE = float(os.getenv("P8_DWE_BASELINE", "0.05"))
_UP_CAP = float(os.getenv("P8_DWE_UP_CAP", "0.03"))
_DOWN_CAP = float(os.getenv("P8_DWE_DOWN_CAP", "0.08"))
_W_SHORT = float(os.getenv("P8_DWE_W_SHORT", "0.50"))
_W_MED = float(os.getenv("P8_DWE_W_MED", "0.30"))
_W_FULL = float(os.getenv("P8_DWE_W_FULL", "0.20"))

# Multiplicateur du cap selon état RiskGovernor
_RG_MULT: dict[str, float] = {
    "AGGRESSIVE": 1.6,
    "NORMAL": 1.0,
    "DEFENSIVE": 0.4,
    "RECOVERY": 0.5,
    "RISK_OFF": 0.0,
}

_SHORT_WINDOW = 20
_MED_WINDOW = 50


@dataclass
class StrategyPerf:
    """Historique de performance tri-temporel pour une stratégie."""

    strategy_id: str
    short: Deque[float] = field(default_factory=lambda: deque(maxlen=_SHORT_WINDOW))
    medium: Deque[float] = field(default_factory=lambda: deque(maxlen=_MED_WINDOW))
    _sum_full: float = 0.0
    _count_full: int = 0

    def record(self, pnl_pct: float, sharpe: float = 0.0) -> None:
        score = pnl_pct * 0.6 + sharpe * 0.4
        self.short.append(score)
        self.medium.append(score)
        self._sum_full += score
        self._count_full += 1

    def composite_score(self) -> float:
        s = sum(self.short) / len(self.short) if self.short else 0.0
        m = sum(self.medium) / len(self.medium) if self.medium else 0.0
        f = self._sum_full / self._count_full if self._count_full > 0 else 0.0
        return s * _W_SHORT + m * _W_MED + f * _W_FULL

    def sample_size(self) -> int:
        return self._count_full


class DynamicWeightingEngine:
    """
    Ajuste les poids de stratégies par performance relative tri-temporelle.

    Usage :
        dwe = DynamicWeightingEngine(strategy_ids)
        dwe.record("momentum", pnl_pct=1.2, sharpe=0.8)
        adjusted = dwe.adjust(current_weights, risk_state="NORMAL")
    """

    def __init__(self, strategy_ids: list[str]) -> None:
        self._strategy_ids = list(strategy_ids)
        self._perfs: dict[str, StrategyPerf] = {
            sid: StrategyPerf(strategy_id=sid) for sid in strategy_ids
        }

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record(self, strategy_id: str, pnl_pct: float, sharpe: float = 0.0) -> None:
        """Enregistre la performance d'un trade pour une stratégie."""
        if strategy_id in self._perfs:
            self._perfs[strategy_id].record(pnl_pct, sharpe)

    # ── Ajustement ────────────────────────────────────────────────────────────

    def adjust(
        self,
        weights: dict[str, float],
        risk_state: str = "NORMAL",
    ) -> dict[str, float]:
        """
        Ajuste weights selon la performance relative tri-temporelle.

        Ne modifie que les stratégies ayant ≥ 5 trades enregistrés.
        Retourne de nouveaux poids normalisés avec baseline floor.
        """
        mult = _RG_MULT.get(risk_state.upper(), 1.0)
        if mult == 0.0:
            return dict(weights)

        up_cap = _UP_CAP * mult
        down_cap = _DOWN_CAP * mult

        scores = {
            sid: self._perfs[sid].composite_score()
            for sid in self._strategy_ids
            if sid in weights
        }

        # Stratégies avec historique suffisant
        eligible = {
            sid: sc for sid, sc in scores.items() if self._perfs[sid].sample_size() >= 5
        }
        if not eligible:
            return dict(weights)

        mean_score = sum(eligible.values()) / len(eligible)

        w = dict(weights)
        redistributed = 0.0

        for sid, sc in eligible.items():
            relative = sc - mean_score
            if relative > 0:
                delta = min(relative * 0.1, up_cap)
            else:
                delta = max(relative * 0.1, -down_cap)
            old = w.get(sid, 0.0)
            w[sid] = max(0.0, old + delta)
            redistributed += delta

        # Redistribution proportionnelle au score composite des gagnants
        # (le capital libéré par les perdants va aux gagnants proportionnellement)
        losers_freed = sum(
            -delta
            for sid, sc in eligible.items()
            for delta in [
                max((mean_score - sc) * 0.1, -down_cap) if sc < mean_score else 0
            ]
            if delta > 0
        )
        if losers_freed > 0:
            winners = {
                sid: max(sc, 1e-9) for sid, sc in eligible.items() if sc >= mean_score
            }
            total_winner_score = sum(winners.values())
            if total_winner_score > 1e-9:
                for sid, sc in winners.items():
                    w[sid] += losers_freed * (sc / total_winner_score)

        # Baseline floor — stratégies avec poids non-nul en entrée seulement
        active_in_input = {
            sid
            for sid in self._strategy_ids
            if sid in weights and weights.get(sid, 0.0) > 1e-9
        }
        for sid in active_in_input:
            if sid in w:
                w[sid] = max(_BASELINE, w[sid])

        # Normalisation
        total = sum(w.values())
        if total > 1e-9:
            for sid in w:
                w[sid] /= total
        else:
            n = len(w)
            for sid in w:
                w[sid] = 1.0 / n if n > 0 else 0.0

        return w

    # ── Consultation ─────────────────────────────────────────────────────────

    def scores(self) -> dict[str, float]:
        """Score composite actuel par stratégie."""
        return {sid: round(p.composite_score(), 4) for sid, p in self._perfs.items()}

    def sample_sizes(self) -> dict[str, int]:
        return {sid: p.sample_size() for sid, p in self._perfs.items()}

    def summary(self) -> dict:
        return {
            "scores": self.scores(),
            "sample_sizes": self.sample_sizes(),
        }
