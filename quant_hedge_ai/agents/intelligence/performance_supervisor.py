"""
performance_supervisor.py — Performance Supervisor (P9)

Calcule en temps réel les métriques de performance de trading.

Métriques disponibles :
  sharpe(window)    : Sharpe glissant sur les N derniers trades
  profit_factor()   : somme gains / somme pertes absolues
  max_drawdown()    : drawdown maximal depuis le pic sur la fenêtre
  compare_shadow()  : comparaison réel vs Shadow Engine (en sigma)

Seuils d'alerte (env vars) :
  P9_SHARPE_WARN   : Sharpe < 0.5 → WARNING
  P9_PF_WARN       : Profit Factor < 1.0 → WARNING
  P9_DD_WARN       : Max drawdown > 15% → WARNING
  P9_SHADOW_SIGMA  : écart > 2σ → alerte désalignement shadow
"""

from __future__ import annotations

import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.performance_supervisor")

_SHARPE_WARN_DEFAULT = 0.5
_PF_WARN_DEFAULT = 1.0
_DD_WARN_DEFAULT = 0.15
_SHADOW_SIGMA_DEFAULT = 2.0
_WINDOW_MAX = 200


@dataclass
class TradeRecord:
    pnl_pct: float
    shadow_pnl_pct: Optional[float]
    ts: float = field(default_factory=time.time)


@dataclass
class PerformanceSnapshot:
    cycle: int
    sharpe_20: float
    sharpe_50: float
    sharpe_100: float
    profit_factor: float
    max_drawdown: float
    shadow_deviation_sigma: float
    trade_count: int
    alerts: List[str]
    ts: float = field(default_factory=time.time)


class PerformanceSupervisor:
    """
    Surveille les métriques de performance en temps réel.

    Usage :
        ps = PerformanceSupervisor()
        ps.record_trade(pnl_pct=1.2, shadow_pnl_pct=1.0)
        snap = ps.snapshot(cycle=42)
        if snap.alerts:
            log.warning("[P9/Perf] %s", snap.alerts)
    """

    def __init__(self) -> None:
        self._sharpe_warn = float(
            os.getenv("P9_SHARPE_WARN", str(_SHARPE_WARN_DEFAULT))
        )
        self._pf_warn = float(os.getenv("P9_PF_WARN", str(_PF_WARN_DEFAULT)))
        self._dd_warn = float(os.getenv("P9_DD_WARN", str(_DD_WARN_DEFAULT)))
        self._shadow_sigma = float(
            os.getenv("P9_SHADOW_SIGMA", str(_SHADOW_SIGMA_DEFAULT))
        )

        self._trades: Deque[TradeRecord] = deque(maxlen=_WINDOW_MAX)
        self._history: List[PerformanceSnapshot] = []

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record_trade(
        self,
        pnl_pct: float,
        shadow_pnl_pct: Optional[float] = None,
    ) -> None:
        """Enregistre le résultat d'un trade (réel + shadow optionnel)."""
        self._trades.append(TradeRecord(pnl_pct=pnl_pct, shadow_pnl_pct=shadow_pnl_pct))

    # ── Métriques ─────────────────────────────────────────────────────────────

    def sharpe(self, window: int = 20) -> float:
        """
        Sharpe annualisé glissant sur les `window` derniers trades.
        Hypothèse : 252 trading days, ≈ 1 trade/jour.
        Retourne 0.0 si insuffisamment de données.
        """
        trades = list(self._trades)[-window:]
        if len(trades) < 3:
            return 0.0
        returns = [t.pnl_pct for t in trades]
        mean_r = sum(returns) / len(returns)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / len(returns))
        if std_r < 1e-8:
            return 0.0
        return round((mean_r / std_r) * math.sqrt(252), 4)

    def profit_factor(self, window: int = 100) -> float:
        """
        Profit Factor = sum(gains) / sum(|pertes|).
        Retourne 0.0 si aucune perte, inf si aucun gain.
        """
        trades = list(self._trades)[-window:]
        if not trades:
            return 0.0
        gains = sum(t.pnl_pct for t in trades if t.pnl_pct > 0)
        losses = sum(-t.pnl_pct for t in trades if t.pnl_pct < 0)
        if losses < 1e-8:
            return float("inf") if gains > 0 else 0.0
        return round(gains / losses, 4)

    def max_drawdown(self, window: int = 100) -> float:
        """
        Max drawdown en % depuis le pic. Valeur positive (ex: 0.12 = 12%).
        """
        trades = list(self._trades)[-window:]
        if len(trades) < 2:
            return 0.0
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for t in trades:
            equity *= 1.0 + t.pnl_pct / 100.0
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 4)

    def compare_shadow(self, window: int = 50) -> float:
        """
        Écart entre returns réels et shadow en nombre de sigma.
        0.0 si pas de données shadow.
        """
        trades = [
            t for t in list(self._trades)[-window:] if t.shadow_pnl_pct is not None
        ]
        if len(trades) < 5:
            return 0.0
        deltas = [
            t.pnl_pct - t.shadow_pnl_pct for t in trades  # type: ignore[operator]
        ]
        mean_d = sum(deltas) / len(deltas)
        std_d = math.sqrt(sum((d - mean_d) ** 2 for d in deltas) / len(deltas))
        if std_d < 1e-8:
            return 0.0
        return round(abs(mean_d) / std_d, 3)

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self, cycle: int = 0) -> PerformanceSnapshot:
        """Calcule toutes les métriques et détecte les alertes."""
        s20 = self.sharpe(20)
        s50 = self.sharpe(50)
        s100 = self.sharpe(100)
        pf = self.profit_factor()
        dd = self.max_drawdown()
        shadow_dev = self.compare_shadow()

        alerts: List[str] = []
        if len(self._trades) >= 20 and s20 < self._sharpe_warn:
            alerts.append(f"Sharpe(20)={s20:.2f} < seuil={self._sharpe_warn}")
        if pf < self._pf_warn and len(self._trades) >= 10:
            alerts.append(f"ProfitFactor={pf:.2f} < seuil={self._pf_warn}")
        if dd > self._dd_warn:
            alerts.append(f"MaxDrawdown={dd:.1%} > seuil={self._dd_warn:.1%}")
        if shadow_dev > self._shadow_sigma:
            alerts.append(
                f"Shadow désalignement {shadow_dev:.1f}σ > seuil={self._shadow_sigma}σ"
            )

        if alerts:
            _log.warning(
                "[P9/Perf] cycle=%d alertes=%s sharpe20=%.2f pf=%.2f dd=%.1%%",
                cycle,
                alerts,
                s20,
                pf,
                dd * 100,
            )

        snap = PerformanceSnapshot(
            cycle=cycle,
            sharpe_20=s20,
            sharpe_50=s50,
            sharpe_100=s100,
            profit_factor=pf,
            max_drawdown=dd,
            shadow_deviation_sigma=shadow_dev,
            trade_count=len(self._trades),
            alerts=alerts,
        )
        self._history.append(snap)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        return snap

    # ── Consultation ─────────────────────────────────────────────────────────

    def last_snapshot(self) -> Optional[PerformanceSnapshot]:
        return self._history[-1] if self._history else None

    def summary(self) -> dict:
        snap = self.last_snapshot()
        if snap is None:
            return {"trade_count": 0, "sharpe_20": 0.0, "profit_factor": 0.0}
        return {
            "trade_count": snap.trade_count,
            "sharpe_20": snap.sharpe_20,
            "sharpe_50": snap.sharpe_50,
            "profit_factor": snap.profit_factor,
            "max_drawdown": snap.max_drawdown,
            "shadow_deviation_sigma": snap.shadow_deviation_sigma,
            "alerts": snap.alerts,
        }
