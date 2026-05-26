"""
confidence_scorer.py — Strategy Confidence Scoring (P8)

Score composite par stratégie :
  confidence = base × decay^t + winrate × 0.4 + sharpe_norm × 0.3
              + regime_consistency × 0.3

Propriétés clés :
  - Clamp [0.10, 0.92] : doute résiduel permanent, jamais dogmatique
  - Asymétrie : monte lentement (blend 30%), descend vite (immédiat)
  - Decay adaptatif selon la fréquence naturelle de la stratégie
  - Pénalité d'incertitude pour échantillon insuffisant (< 20 trades)
"""

from __future__ import annotations

import math
import os
from collections import deque
from dataclasses import dataclass

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.confidence_scorer")

_CONF_MIN = float(os.getenv("P8_CONF_MIN", "0.10"))
_CONF_MAX = float(os.getenv("P8_CONF_MAX", "0.92"))
_WINDOW = int(os.getenv("P8_CONF_WINDOW", "20"))
_DECAY_DEFAULT = float(os.getenv("P8_CONF_DECAY", "0.95"))
_RAMP_UP_BLEND = float(os.getenv("P8_CONF_RAMP_UP", "0.30"))
_UNCERTAINTY_PENALTY = float(os.getenv("P8_CONF_UNCERTAINTY_PENALTY", "0.10"))


@dataclass
class _TradeRecord:
    won: bool
    pnl_pct: float
    sharpe: float
    regime: str
    cycle: int


class StrategyConfidenceScorer:
    """
    Maintient et calcule le score de confiance pour une stratégie.
    Une instance par stratégie — stateful, non thread-safe.
    """

    def __init__(
        self,
        strategy_id: str,
        expected_trades_per_cycle: float = 1.0,
        base_confidence: float = 0.50,
    ) -> None:
        self.strategy_id = strategy_id
        self._expected_tpc = max(0.1, expected_trades_per_cycle)
        self._confidence: float = max(_CONF_MIN, min(_CONF_MAX, base_confidence))
        self._cycles_since_trade: int = 0
        self._history: deque[_TradeRecord] = deque(maxlen=_WINDOW)

    @property
    def confidence(self) -> float:
        return self._confidence

    def record_trade(
        self, won: bool, pnl_pct: float, sharpe: float, regime: str, cycle: int
    ) -> float:
        """Enregistre un trade et met à jour la confiance. Retourne le nouveau score."""
        self._cycles_since_trade = 0
        self._history.append(
            _TradeRecord(
                won=won, pnl_pct=pnl_pct, sharpe=sharpe, regime=regime, cycle=cycle
            )
        )
        new_conf = self._compute()
        self._apply_asymmetry(new_conf)
        return self._confidence

    def tick_cycle(self) -> float:
        """Applique le decay si aucun trade ce cycle. Retourne le score courant."""
        self._cycles_since_trade += 1
        decay = _DECAY_DEFAULT ** (1.0 / self._expected_tpc)
        self._confidence = max(_CONF_MIN, self._confidence * decay)
        return self._confidence

    def snapshot(self) -> dict:
        n = len(self._history)
        return {
            "strategy_id": self.strategy_id,
            "confidence": round(self._confidence, 4),
            "sample_size": n,
            "cycles_since_trade": self._cycles_since_trade,
            "win_rate": (
                round(sum(1 for r in self._history if r.won) / n, 3) if n > 0 else 0.0
            ),
            "avg_sharpe": (
                round(sum(r.sharpe for r in self._history) / n, 3) if n > 0 else 0.0
            ),
        }

    # ── Calcul interne ────────────────────────────────────────────────────────

    def _compute(self) -> float:
        n = len(self._history)
        if n < 5:
            return self._confidence

        records = list(self._history)
        winrate = sum(1 for r in records if r.won) / n
        avg_sharpe = sum(r.sharpe for r in records) / n
        sharpe_norm = max(0.0, min(1.0, avg_sharpe / 3.0))
        regime_c = self._regime_consistency(records)

        raw = winrate * 0.4 + sharpe_norm * 0.3 + regime_c * 0.3

        if n < _WINDOW:
            raw = max(_CONF_MIN, raw - _UNCERTAINTY_PENALTY)

        return max(_CONF_MIN, min(_CONF_MAX, raw))

    def _regime_consistency(self, records: list[_TradeRecord]) -> float:
        """
        Double terme :
          1. Corrélation wins × appartenance au régime dominant (spécialisation)
          2. Winrate max observé dans un régime (expertise contextuelle)
        Retourne la moyenne pondérée 50/50.
        """
        if len(records) < 5:
            return 0.5

        regime_counts: dict[str, int] = {}
        for r in records:
            regime_counts[r.regime] = regime_counts.get(r.regime, 0) + 1
        dominant = max(regime_counts, key=lambda k: regime_counts[k])

        wins_vec = [1.0 if r.won else 0.0 for r in records]
        dom_vec = [1.0 if r.regime == dominant else 0.0 for r in records]
        term1 = abs(_pearson(wins_vec, dom_vec))

        wr_by_regime: dict[str, list[bool]] = {}
        for r in records:
            wr_by_regime.setdefault(r.regime, []).append(r.won)
        term2 = max(
            (sum(ws) / len(ws) for ws in wr_by_regime.values() if ws), default=0.0
        )

        return 0.5 * term1 + 0.5 * term2

    def _apply_asymmetry(self, new_conf: float) -> None:
        if new_conf > self._confidence:
            self._confidence = (
                self._confidence + (new_conf - self._confidence) * _RAMP_UP_BLEND
            )
        else:
            self._confidence = new_conf
        self._confidence = max(_CONF_MIN, min(_CONF_MAX, self._confidence))


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = math.sqrt(sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y))
    return num / den if den > 1e-9 else 0.0
