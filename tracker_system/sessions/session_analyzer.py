from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

from tracker_system.sessions.schemas.metrics_schema import (
    DRIFT_PF_DROP_RATIO,
    DRIFT_Z_SCORE_THRESHOLD,
    PAYOFF_RATIO_TARGET,
    label_expectancy,
    label_stability,
)


class SessionAnalyzer:
    """Transforme les trades d'une session en intelligence exploitable."""

    def analyze(self, trades: list[dict]) -> dict[str, Any]:
        if not trades:
            return {"error": "aucun trade"}

        pnl_usd = [float(t.get("pnl_usd", 0.0)) for t in trades]
        pnl_pct = [float(t.get("pnl_pct", 0.0)) for t in trades]
        wins = [t for t in trades if float(t.get("pnl_usd", 0.0)) > 0]
        losses = [t for t in trades if float(t.get("pnl_usd", 0.0)) <= 0]

        winrate = len(wins) / len(trades)
        avg_win_pct = (
            statistics.mean(float(t.get("pnl_pct", 0.0)) for t in wins) if wins else 0.0
        )
        avg_loss_pct = (
            statistics.mean(float(t.get("pnl_pct", 0.0)) for t in losses)
            if losses
            else 0.0
        )

        expectancy = self._expectancy(winrate, avg_win_pct, avg_loss_pct)
        payoff_ratio = self._payoff_ratio(avg_win_pct, avg_loss_pct)
        recovery_factor = self._recovery_factor(pnl_usd)
        profit_factor = self._profit_factor(pnl_pct)
        streaks = self._streak_analysis(trades)
        regime_matrix = self._regime_performance_matrix(trades)
        stability = self._signal_stability_index(trades)
        trade_quality = self._trade_quality_score(
            expectancy, profit_factor, stability, recovery_factor
        )
        drift = self._drift_events(trades, profit_factor)

        return {
            "summary": {
                "trades": len(trades),
                "winrate": round(winrate, 4),
                "avg_win_pct": round(avg_win_pct, 4),
                "avg_loss_pct": round(avg_loss_pct, 4),
                "pnl_total_usd": round(sum(pnl_usd), 4),
            },
            "expectancy": {
                "value": round(expectancy, 4),
                "label": label_expectancy(expectancy),
            },
            "payoff_ratio": {
                "value": round(payoff_ratio, 4),
                "target": PAYOFF_RATIO_TARGET,
                "ok": payoff_ratio >= PAYOFF_RATIO_TARGET,
            },
            "profit_factor": round(profit_factor, 4),
            "recovery_factor": (
                round(recovery_factor, 4) if recovery_factor != float("inf") else "inf"
            ),
            "streaks": streaks,
            "regime_matrix": regime_matrix,
            "signal_stability": {
                "index": round(stability, 4),
                "label": label_stability(stability),
            },
            "trade_quality_score": round(trade_quality, 4),
            "drift_events": drift,
        }

    # ── KPIs ──────────────────────────────────────────────────────────────

    def _expectancy(self, winrate: float, avg_win: float, avg_loss: float) -> float:
        return (winrate * avg_win) + ((1 - winrate) * avg_loss)

    def _payoff_ratio(self, avg_win: float, avg_loss: float) -> float:
        if avg_loss == 0.0:
            return float("inf")
        return abs(avg_win / avg_loss)

    def _profit_factor(self, pnl_pct: list[float]) -> float:
        gross_win = sum(p for p in pnl_pct if p > 0)
        gross_loss = abs(sum(p for p in pnl_pct if p < 0))
        return gross_win / gross_loss if gross_loss > 0 else float("inf")

    def _recovery_factor(self, pnl_usd: list[float]) -> float:
        total = sum(pnl_usd)
        equity, peak, max_dd = 0.0, 0.0, 0.0
        for p in pnl_usd:
            equity += p
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        if max_dd == 0.0:
            return float("inf")
        return total / max_dd

    def _streak_analysis(self, trades: list[dict]) -> dict[str, Any]:
        streaks: list[tuple[str, int]] = []  # (type, length)
        current_type = None
        current_len = 0

        for t in trades:
            kind = "win" if float(t.get("pnl_usd", 0.0)) > 0 else "loss"
            if kind == current_type:
                current_len += 1
            else:
                if current_type is not None:
                    streaks.append((current_type, current_len))
                current_type = kind
                current_len = 1
        if current_type is not None:
            streaks.append((current_type, current_len))

        win_streaks = [l for t, l in streaks if t == "win"]
        loss_streaks = [l for t, l in streaks if t == "loss"]

        return {
            "max_win_streak": max(win_streaks) if win_streaks else 0,
            "max_loss_streak": max(loss_streaks) if loss_streaks else 0,
            "avg_win_streak": (
                round(statistics.mean(win_streaks), 2) if win_streaks else 0.0
            ),
            "avg_loss_streak": (
                round(statistics.mean(loss_streaks), 2) if loss_streaks else 0.0
            ),
        }

    def _regime_performance_matrix(self, trades: list[dict]) -> dict[str, Any]:
        regimes: dict[str, list[dict]] = {}
        for t in trades:
            regime = str(t.get("regime", "unknown"))
            regimes.setdefault(regime, []).append(t)

        matrix: dict[str, Any] = {}
        for regime, rtrades in regimes.items():
            wins = [t for t in rtrades if float(t.get("pnl_usd", 0.0)) > 0]
            losses = [t for t in rtrades if float(t.get("pnl_usd", 0.0)) <= 0]
            pnl_pcts = [float(t.get("pnl_pct", 0.0)) for t in rtrades]
            wr = len(wins) / len(rtrades)
            avg_win = (
                statistics.mean(float(t.get("pnl_pct", 0.0)) for t in wins)
                if wins
                else 0.0
            )
            avg_loss = (
                statistics.mean(float(t.get("pnl_pct", 0.0)) for t in losses)
                if losses
                else 0.0
            )
            gross_win = sum(p for p in pnl_pcts if p > 0)
            gross_loss = abs(sum(p for p in pnl_pcts if p < 0))
            pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
            exp = self._expectancy(wr, avg_win, avg_loss)
            matrix[regime] = {
                "trades": len(rtrades),
                "winrate": round(wr, 4),
                "profit_factor": round(pf, 4) if pf != float("inf") else "inf",
                "expectancy": round(exp, 4),
                "recommendation": _regime_recommendation(exp, pf),
            }
        return matrix

    def _signal_stability_index(self, trades: list[dict]) -> float:
        scores = [
            float(t.get("score", 0.5)) for t in trades if t.get("score") is not None
        ]
        if len(scores) < 2:
            return 1.0
        mean_s = sum(scores) / len(scores)
        std = math.sqrt(sum((x - mean_s) ** 2 for x in scores) / len(scores))
        return 1.0 / (1.0 + std)

    def _trade_quality_score(
        self, expectancy: float, profit_factor: float, stability: float, recovery: float
    ) -> float:
        pf = min(profit_factor, 10.0)
        rec = min(recovery if recovery != float("inf") else 10.0, 10.0)
        dd_norm = 1.0 / (rec + 1.0)
        return (expectancy * pf * stability) / (dd_norm + 1.0)

    def _drift_events(
        self, trades: list[dict], baseline_pf: float
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        # Rolling profit factor drift (window=20)
        if len(trades) >= 20:
            pnl_pcts = [float(t.get("pnl_pct", 0.0)) for t in trades]
            for i in range(20, len(trades)):
                window = pnl_pcts[i - 20 : i]
                gw = sum(p for p in window if p > 0)
                gl = abs(sum(p for p in window if p < 0))
                rolling_pf = gw / gl if gl > 0 else float("inf")
                if baseline_pf > 0 and rolling_pf < baseline_pf * DRIFT_PF_DROP_RATIO:
                    events.append(
                        {
                            "type": "performance_drift",
                            "trade_index": i,
                            "rolling_pf": round(rolling_pf, 4),
                            "baseline_pf": round(baseline_pf, 4),
                            "severity": "high",
                            "action": "reduce_exposure",
                        }
                    )
                    break  # une seule alerte par session

        # Score z-score drift
        scores = [
            float(t.get("score", 0.5)) for t in trades if t.get("score") is not None
        ]
        if len(scores) >= 5:
            mean_s = sum(scores) / len(scores)
            std_s = math.sqrt(sum((x - mean_s) ** 2 for x in scores) / len(scores))
            if std_s > 0:
                for i, s in enumerate(scores):
                    z = abs((s - mean_s) / std_s)
                    if z > DRIFT_Z_SCORE_THRESHOLD:
                        events.append(
                            {
                                "type": "score_drift",
                                "trade_index": i,
                                "z_score": round(z, 4),
                                "score": round(s, 4),
                                "severity": "medium",
                                "action": "monitor",
                            }
                        )

        return events


def _regime_recommendation(expectancy: float, pf: float) -> str:
    if expectancy > 0.5 and (pf == float("inf") or pf >= 1.5):
        return "augmenter sizing"
    if expectancy < 0.0 or (pf != float("inf") and pf < 1.0):
        return "bloquer"
    return "maintenir"


def analyze_session(session_dir: Path) -> dict[str, Any]:
    """Raccourci : charge les trades d'un répertoire et retourne l'analyse complète."""
    from tracker_system.sessions.session_manager import load_session_trades

    trades = load_session_trades(session_dir)
    return SessionAnalyzer().analyze(trades)
