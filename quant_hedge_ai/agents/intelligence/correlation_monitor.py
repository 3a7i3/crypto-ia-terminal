"""
correlation_monitor.py — Strategy Correlation Monitor (P8)

Surveille la corrélation multi-dimensionnelle entre stratégies :
  - PnL    : corrélation des résultats (poids 0.4)
  - Signal : corrélation des signaux BUY/SELL (poids 0.3)
  - Drawdown : corrélation des baisses de capital (poids 0.3)

Fonctionnalités :
  - Seuils warn/action ajustés par régime
  - Lead-lag detection via cross-corrélation ±5 cycles
  - Corrélation négative forte (annulation mutuelle) aussi signalée
  - Pénalité progressive entre warn et action thresholds
  - Alerte de fusion structurelle si corrélation > action sur 3 régimes distincts
"""

from __future__ import annotations

import math
import os
from collections import deque
from dataclasses import dataclass
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.correlation_monitor")

_HISTORY_WINDOW = int(os.getenv("P8_CORR_WINDOW", "20"))
_LEAD_LAG_MAX = int(os.getenv("P8_CORR_LAG", "5"))
_FUSION_REGIMES_THRESHOLD = int(os.getenv("P8_CORR_FUSION_REGIMES", "3"))

# Seuils (warn, action) par régime — HIGH_VOL relâchés (corrélation naturellement haute)
_THRESHOLDS: dict[str, tuple[float, float]] = {
    "SIDEWAYS": (0.65, 0.80),
    "TREND_BULL": (0.70, 0.85),
    "TREND_BEAR": (0.70, 0.85),
    "HIGH_VOL": (0.80, 0.90),
    "CHOPPY": (0.65, 0.80),
    "UNKNOWN": (0.60, 0.75),
}
_DEFAULT_THRESHOLDS = (0.70, 0.85)


@dataclass
class _StrategyObs:
    pnl_pct: float
    signal: float  # +1 BUY, -1 SELL, 0 HOLD/neutre
    drawdown: float
    cycle: int
    regime: str


@dataclass
class CorrelationResult:
    strategy_a: str
    strategy_b: str
    corr_pnl: float
    corr_signal: float
    corr_drawdown: float
    max_lagged_corr: float
    composite_corr: float
    regime: str
    action: str  # "none" | "warn" | "reduce_weight" | "fusion_alert"
    weight_penalty: float  # 0.0–0.30 à appliquer à la stratégie la plus faible


class CorrelationMonitor:
    """
    Calcule les corrélations pairées inter-stratégies chaque cycle.
    Retourne les pénalités de poids à appliquer à l'allocateur.
    """

    def __init__(self) -> None:
        self._history: dict[str, deque[_StrategyObs]] = {}
        self._fusion_tracking: dict[str, set[str]] = {}  # "a::b" → set de régimes
        self._fusion_alerts: list[dict] = []

    def record(
        self,
        strategy_id: str,
        pnl_pct: float,
        signal: float,
        drawdown: float,
        cycle: int,
        regime: str,
    ) -> None:
        buf_size = max(_HISTORY_WINDOW, (_LEAD_LAG_MAX + 1) * 3)
        if strategy_id not in self._history:
            self._history[strategy_id] = deque(maxlen=buf_size)
        self._history[strategy_id].append(
            _StrategyObs(
                pnl_pct=pnl_pct,
                signal=signal,
                drawdown=drawdown,
                cycle=cycle,
                regime=regime,
            )
        )

    def get_weight_penalties(
        self, regime: str, strategy_scores: dict[str, float]
    ) -> dict[str, float]:
        """Retourne {strategy_id: penalty_fraction} pour l'allocateur."""
        penalties: dict[str, float] = {}
        for result in self._compute_all(regime, strategy_scores):
            if result.weight_penalty > 0:
                weaker = self._weaker(
                    result.strategy_a, result.strategy_b, strategy_scores
                )
                penalties[weaker] = max(
                    penalties.get(weaker, 0.0), result.weight_penalty
                )
        return penalties

    def fusion_alerts(self) -> list[dict]:
        return list(self._fusion_alerts)

    def snapshot(self) -> dict:
        return {
            "strategies_tracked": list(self._history.keys()),
            "fusion_alerts_count": len(self._fusion_alerts),
            "fusion_alerts": self._fusion_alerts[-5:],
        }

    # ── Calcul pairée ─────────────────────────────────────────────────────────

    def _compute_all(
        self, regime: str, strategy_scores: dict[str, float]
    ) -> list[CorrelationResult]:
        results = []
        ids = list(self._history.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                r = self._compute_pair(ids[i], ids[j], regime, strategy_scores)
                if r is not None:
                    results.append(r)
                    self._track_fusion(r)
        return results

    def _compute_pair(
        self,
        a: str,
        b: str,
        regime: str,
        scores: dict[str, float],
    ) -> Optional[CorrelationResult]:
        hist_a = {obs.cycle: obs for obs in self._history.get(a, [])}
        hist_b = {obs.cycle: obs for obs in self._history.get(b, [])}
        common = sorted(set(hist_a) & set(hist_b))[-_HISTORY_WINDOW:]
        if len(common) < 5:
            return None

        obs_a = [hist_a[c] for c in common]
        obs_b = [hist_b[c] for c in common]

        pnl_a = [o.pnl_pct for o in obs_a]
        pnl_b = [o.pnl_pct for o in obs_b]
        sig_a = [o.signal for o in obs_a]
        sig_b = [o.signal for o in obs_b]
        dd_a = [o.drawdown for o in obs_a]
        dd_b = [o.drawdown for o in obs_b]

        corr_pnl = _pearson(pnl_a, pnl_b)
        corr_signal = _pearson(sig_a, sig_b)
        corr_drawdown = _pearson(dd_a, dd_b)
        composite = (
            abs(corr_pnl) * 0.4 + abs(corr_signal) * 0.3 + abs(corr_drawdown) * 0.3
        )

        # Lead-lag : cross-corrélation ±_LEAD_LAG_MAX cycles
        max_lagged = composite
        for lag in range(1, _LEAD_LAG_MAX + 1):
            for shifted_a, shifted_b in [
                (pnl_a[lag:], pnl_b[:-lag]),
                (pnl_a[:-lag], pnl_b[lag:]),
            ]:
                if len(shifted_a) >= 5:
                    max_lagged = max(max_lagged, abs(_pearson(shifted_a, shifted_b)))

        warn_t, action_t = _THRESHOLDS.get(regime, _DEFAULT_THRESHOLDS)
        penalty_strength = max(
            0.0, min(1.0, (composite - warn_t) / max(action_t - warn_t, 0.01))
        )
        weight_penalty = round(penalty_strength * 0.30, 4)

        if composite >= action_t:
            action = "reduce_weight"
        elif composite >= warn_t:
            action = "warn"
        else:
            action = "none"

        # Corrélation négative forte = annulation mutuelle → aussi pénalisée
        if corr_pnl < -0.70:
            action = "reduce_weight"
            weight_penalty = max(weight_penalty, 0.20)

        if action in ("warn", "reduce_weight"):
            _log.info(
                "[CorrelMonitor] %s↔%s composite=%.2f lag_max=%.2f action=%s pen=%.2f",
                a,
                b,
                composite,
                max_lagged,
                action,
                weight_penalty,
            )

        return CorrelationResult(
            strategy_a=a,
            strategy_b=b,
            corr_pnl=round(corr_pnl, 3),
            corr_signal=round(corr_signal, 3),
            corr_drawdown=round(corr_drawdown, 3),
            max_lagged_corr=round(max_lagged, 3),
            composite_corr=round(composite, 3),
            regime=regime,
            action=action,
            weight_penalty=weight_penalty,
        )

    def _track_fusion(self, r: CorrelationResult) -> None:
        key = "::".join(sorted([r.strategy_a, r.strategy_b]))
        if key not in self._fusion_tracking:
            self._fusion_tracking[key] = set()
        _, action_t = _THRESHOLDS.get(r.regime, _DEFAULT_THRESHOLDS)
        if r.composite_corr >= action_t:
            self._fusion_tracking[key].add(r.regime)
        regimes_above = self._fusion_tracking[key]
        if len(regimes_above) >= _FUSION_REGIMES_THRESHOLD:
            alerted = {(a["strategy_a"], a["strategy_b"]) for a in self._fusion_alerts}
            if (r.strategy_a, r.strategy_b) not in alerted and (
                r.strategy_b,
                r.strategy_a,
            ) not in alerted:
                alert = {
                    "strategy_a": r.strategy_a,
                    "strategy_b": r.strategy_b,
                    "regimes": list(regimes_above),
                    "composite_corr": r.composite_corr,
                    "recommendation": (
                        "Redondance structurelle — envisager fusion ou suppression"
                    ),
                }
                self._fusion_alerts.append(alert)
                _log.warning(
                    "[CorrelMonitor] FUSION ALERT: %s ↔ %s sur régimes %s",
                    r.strategy_a,
                    r.strategy_b,
                    list(regimes_above),
                )

    @staticmethod
    def _weaker(a: str, b: str, scores: dict[str, float]) -> str:
        return a if scores.get(a, 0.0) <= scores.get(b, 0.0) else b


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = math.sqrt(sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y))
    return num / den if den > 1e-9 else 0.0
