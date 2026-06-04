from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from system.strategy_metrics import StrategyAnalyzer, Trade

# Trades par bin en dessous desquels on ne classifie pas l'alpha
_MIN_RELIABLE = 10


@dataclass(frozen=True)
class ScoreBin:
    label: str
    min_score: int
    max_score: Optional[int] = None

    def contains(self, score: int) -> bool:
        if score < self.min_score:
            return False
        if self.max_score is None:
            return True
        return score <= self.max_score


class BurnInAnalytics:
    """Builds burn-in analytics from completed paper trades."""

    SCORE_BINS: tuple[ScoreBin, ...] = (
        ScoreBin("50-54", 50, 54),
        ScoreBin("55-59", 55, 59),
        ScoreBin("60-64", 60, 64),
        ScoreBin("65-69", 65, 69),
        ScoreBin("70+", 70, None),
    )

    def __init__(self, initial_capital: float = 10_000.0) -> None:
        self._initial_capital = float(initial_capital)

    def build_report(
        self,
        closed_trades: list[dict],
        *,
        generated_at: Optional[datetime] = None,
        window_hours: Optional[float] = None,
    ) -> dict:
        ts = generated_at or datetime.now(timezone.utc)
        summary = self._compute_summary(closed_trades)
        histogram = self._compute_score_histogram(closed_trades)
        tp_sl = self._compute_exit_reason_breakdown(closed_trades)
        symbol_breakdown = self._compute_symbol_breakdown(closed_trades)
        symbol_bin_matrix = self._compute_symbol_bin_matrix(closed_trades)
        equity_curve = self._compute_equity_curve(closed_trades)
        alpha_drift = self._compute_alpha_drift(closed_trades)
        ev_curve = self._compute_ev_curve(histogram)
        recommended_floor, floor_confidence = self._compute_recommended_floor(histogram)

        report = {
            "generated_at": ts.isoformat(),
            "window_hours": window_hours,
            "trades": summary["trades"],
            "wins": summary["wins"],
            "losses": summary["losses"],
            "win_rate": summary["win_rate"],
            "profit_factor": summary["profit_factor"],
            "expectancy": summary["expectancy"],
            "max_drawdown": summary["max_drawdown"],
            "sharpe": summary["sharpe"],
            "score_histogram": histogram,
            "tp_sl_breakdown": tp_sl,
            "symbol_breakdown": symbol_breakdown,
            "symbol_bin_matrix": symbol_bin_matrix,
            "equity_curve": equity_curve,
            "alpha_drift": alpha_drift,
            "expected_value_curve": ev_curve,
            "recommended_score_floor": recommended_floor,
            "score_floor_confidence": floor_confidence,
        }
        return report

    def _compute_summary(self, closed_trades: list[dict]) -> dict:
        if not closed_trades:
            return {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
                "max_drawdown": 0.0,
                "sharpe": 0.0,
            }

        trade_objs = [
            Trade(
                pnl=float(t.get("pnl_usd", 0.0) or 0.0),
                pnl_pct=self._normalize_pnl_pct(t.get("pnl_pct", 0.0)),
                duration_s=float(t.get("duration_s", 0.0) or 0.0),
                ts=float(t.get("close_ts", 0.0) or 0.0),
                regime=str(t.get("regime", "UNKNOWN")),
            )
            for t in closed_trades
        ]

        equity_curve = [self._initial_capital]
        equity = self._initial_capital
        for tr in trade_objs:
            equity += tr.pnl
            equity_curve.append(equity)

        analyzer = StrategyAnalyzer(initial_capital=self._initial_capital)
        metrics = analyzer.compute(trade_objs, equity_curve)

        wins = metrics.win_trades
        losses = metrics.loss_trades
        pf = 0.0 if metrics.profit_factor == float("inf") else metrics.profit_factor

        return {
            "trades": metrics.total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(metrics.win_rate * 100.0, 2),
            "profit_factor": round(float(pf), 4),
            "expectancy": round(float(metrics.expectancy), 4),
            "max_drawdown": round(float(metrics.max_drawdown_pct), 4),
            "sharpe": round(float(metrics.sharpe_ratio), 4),
        }

    def _compute_score_histogram(self, closed_trades: list[dict]) -> list[dict]:
        rows: list[dict] = []
        for score_bin in self.SCORE_BINS:
            subset = [
                t
                for t in closed_trades
                if score_bin.contains(self._safe_int(t.get("score", 0)))
            ]
            rows.append(
                {
                    "range": score_bin.label,
                    "score_floor": score_bin.min_score,
                    **self._subset_metrics(subset),
                }
            )
        return rows

    def _subset_metrics(self, subset: list[dict]) -> dict:
        if not subset:
            return {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
                "sharpe": 0.0,
                "alpha_class": "insufficient_data",
            }

        rets = [self._normalize_pnl_pct(t.get("pnl_pct", 0.0)) for t in subset]
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r <= 0]

        win_rate = len(wins) / len(rets) * 100.0 if rets else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        # profit_factor : 0.0 quand gross_loss=0 (convention "infini" — aucune perte)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        all_wins_no_loss = gross_loss == 0 and gross_profit > 0
        expectancy = sum(rets) / len(rets) if rets else 0.0

        # Sharpe par trade (mean/std des rendements par trade)
        sharpe = 0.0
        if len(rets) >= 2:
            mean_r = sum(rets) / len(rets)
            variance = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
            std_r = variance**0.5
            sharpe = round(mean_r / std_r, 4) if std_r > 0 else 0.0

        # Classification alpha
        n = len(rets)
        if n < _MIN_RELIABLE:
            alpha_class = "insufficient_data"
        elif expectancy > 0.05 and (profit_factor > 1.0 or all_wins_no_loss):
            alpha_class = "positive"
        elif expectancy > -0.1:
            alpha_class = "neutral"
        else:
            alpha_class = "negative"

        return {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(float(profit_factor), 4),
            "expectancy": round(float(expectancy), 4),
            "sharpe": round(float(sharpe), 4),
            "alpha_class": alpha_class,
        }

    def _compute_symbol_breakdown(self, closed_trades: list[dict]) -> list[dict]:
        buckets: dict[str, list[dict]] = {}
        for t in closed_trades:
            sym = str(t.get("symbol", "") or "UNKNOWN")
            buckets.setdefault(sym, []).append(t)

        rows = [
            {"symbol": sym, **self._subset_metrics(subset)}
            for sym, subset in buckets.items()
        ]
        rows.sort(key=lambda r: r["expectancy"], reverse=True)
        return rows

    def _compute_symbol_bin_matrix(self, closed_trades: list[dict]) -> dict:
        """
        Matrice {symbol → {bin_range → {trades, win_rate, expectancy, profit_factor}}}.

        Permet de répondre : "BTC alpha en 55-59, ETH neutre en 60-64, DOGE drag."
        Seules les cellules avec au moins 1 trade sont incluses.
        """
        matrix: dict[str, dict[str, dict]] = {}
        for score_bin in self.SCORE_BINS:
            bin_trades = [
                t
                for t in closed_trades
                if score_bin.contains(self._safe_int(t.get("score", 0)))
            ]
            seen_syms: dict[str, list[dict]] = {}
            for t in bin_trades:
                sym = str(t.get("symbol", "") or "UNKNOWN")
                seen_syms.setdefault(sym, []).append(t)

            for sym, subset in seen_syms.items():
                m = self._subset_metrics(subset)
                matrix.setdefault(sym, {})[score_bin.label] = {
                    "trades": m["trades"],
                    "win_rate": m["win_rate"],
                    "expectancy": m["expectancy"],
                    "profit_factor": m["profit_factor"],
                }
        return matrix

    def _compute_equity_curve(self, closed_trades: list[dict]) -> list[dict]:
        """Courbe de capital trade par trade, triée par close_ts."""
        sorted_trades = sorted(
            closed_trades, key=lambda t: float(t.get("close_ts", 0) or 0)
        )
        equity = self._initial_capital
        curve = []
        for i, t in enumerate(sorted_trades, 1):
            pnl = float(t.get("pnl_usd", 0.0) or 0.0)
            equity += pnl
            close_ts = float(t.get("close_ts", 0) or 0)
            ts_iso = (
                datetime.fromtimestamp(close_ts, tz=timezone.utc).isoformat()
                if close_ts > 0
                else ""
            )
            curve.append(
                {
                    "trade": i,
                    "equity": round(equity, 2),
                    "pnl_usd": round(pnl, 4),
                    "ts_iso": ts_iso,
                }
            )
        return curve

    def _compute_alpha_drift(self, closed_trades: list[dict]) -> dict:
        """
        Matrice {symbol → {semaine_ISO → {trades, expectancy, win_rate, PF}}}.

        Répond à : "BTC était rentable la semaine passée, l'est-il encore ?"
        Seules les cellules avec au moins 1 trade sont incluses.
        """
        weekly: dict[str, dict[str, list[dict]]] = {}
        for t in closed_trades:
            sym = str(t.get("symbol", "") or "UNKNOWN")
            close_ts = float(t.get("close_ts", 0) or 0)
            if close_ts > 0:
                dt = datetime.fromtimestamp(close_ts, tz=timezone.utc)
                iso_cal = dt.isocalendar()
                week_label = f"{iso_cal[0]}-W{iso_cal[1]:02d}"
            else:
                week_label = "unknown"
            weekly.setdefault(sym, {}).setdefault(week_label, []).append(t)

        result: dict[str, dict] = {}
        for sym, weeks in weekly.items():
            result[sym] = {}
            for week in sorted(weeks):
                m = self._subset_metrics(weeks[week])
                result[sym][week] = {
                    "trades": m["trades"],
                    "win_rate": m["win_rate"],
                    "expectancy": m["expectancy"],
                    "profit_factor": m["profit_factor"],
                }
        return result

    def _compute_ev_curve(self, histogram: list[dict]) -> list[dict]:
        """score_floor → expectancy pour chaque bin ayant au moins 1 trade."""
        return [
            {
                "score_floor": row["score_floor"],
                "range": row["range"],
                "expectancy": row["expectancy"],
                "alpha_class": row["alpha_class"],
            }
            for row in histogram
            if row["trades"] > 0
        ]

    def _compute_recommended_floor(
        self, histogram: list[dict]
    ) -> tuple[Optional[int], str]:
        """
        Retourne (score_floor, confidence) du meilleur bin alpha positif.

        Critères bin éligible : alpha_class == "positive"
        Sélection : meilleur ratio expectancy * profit_factor parmi éligibles.
        Confidence : basée sur N trades dans le bin retenu.
        """
        eligible = [r for r in histogram if r["alpha_class"] == "positive"]
        if not eligible:
            return None, "INSUFFICIENT_DATA"

        best = max(eligible, key=lambda r: r["expectancy"] * r["profit_factor"])
        n = best["trades"]
        if n >= 100:
            confidence = "HIGH"
        elif n >= 50:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return best["score_floor"], confidence

    def _compute_exit_reason_breakdown(self, closed_trades: list[dict]) -> dict:
        reasons = [str(t.get("exit_reason", "")).strip().lower() for t in closed_trades]
        counts = Counter(reason for reason in reasons if reason)
        tp = sum(v for k, v in counts.items() if "tp" in k or "take_profit" in k)
        sl = sum(v for k, v in counts.items() if "sl" in k or "stop_loss" in k)

        return {
            "tp_closes": tp,
            "sl_closes": sl,
            "other_closes": max(len(closed_trades) - tp - sl, 0),
            "raw": dict(counts),
        }

    @staticmethod
    def _normalize_pnl_pct(value: object) -> float:
        try:
            v = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return v * 100.0 if abs(v) < 1.0 else v

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
