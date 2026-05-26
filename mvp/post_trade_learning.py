"""
post_trade_learning.py — Post-Trade Learning MVP

"Le vrai edge."

Pour chaque trade fermé, répond à 4 questions :
  1. Pourquoi il a gagné ou perdu ?     → attribution causale
  2. Le modèle avait tort ?             → signal_error
  3. Le marché a changé ?               → regime_mismatch
  4. Mauvaise exécution ?               → execution_error

Et calcule les vrais KPIs institutionnels :
  - Expectancy         : E[PnL par trade] — le plus important
  - Sharpe (rolling)   : rendement / risque
  - Max drawdown       : pire période
  - Win rate           : secondaire mais utile
  - Regime performance : quel régime est profitable
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.json_logger import get_logger

_log = get_logger("mvp.post_trade_learning")
_LOG_PATH = Path("databases/mvp_trade_log.jsonl")
_STAT_PATH = Path("databases/mvp_kpi_state.json")


@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    direction: str
    signal_type: str  # momentum | mean_revert | breakout
    regime: str
    entry_price: float
    exit_price: float
    size_usd: float
    pnl_usd: float
    pnl_pct: float
    duration_minutes: float
    entry_score: float
    entry_confidence: float
    # Exécution
    expected_slippage_bps: float = 0.0
    actual_slippage_bps: float = 0.0
    fee_usd: float = 0.0
    # Attribution
    attribution: str = (
        "unknown"  # signal | regime | execution | market | lucky | unlucky
    )
    lesson: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class KPIReport:
    n_trades: int = 0
    win_rate: float = 0.0
    expectancy_usd: float = 0.0  # E[PnL] par trade en USD
    sharpe_rolling: float = 0.0  # Sharpe sur les 30 derniers trades
    max_drawdown_pct: float = 0.0  # pire drawdown observé
    avg_win_usd: float = 0.0
    avg_loss_usd: float = 0.0
    profit_factor: float = 0.0  # total_wins / total_losses
    avg_duration_min: float = 0.0
    best_regime: str = "unknown"
    worst_regime: str = "unknown"
    best_signal: str = "unknown"
    # Santé du système
    system_health: str = "OK"  # OK | DEGRADED | CRITICAL

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    def summary(self) -> str:
        return (
            f"Trades={self.n_trades} | WR={self.win_rate:.0%} | "
            f"Expectancy={self.expectancy_usd:+.2f}$ | Sharpe={self.sharpe_rolling:.2f} | "
            f"MaxDD={self.max_drawdown_pct:.1f}% | PF={self.profit_factor:.2f} | {self.system_health}"
        )


class PostTradeLearning:
    """
    Enregistre chaque trade, calcule les KPIs réels, attribue les causes,
    génère des leçons et alimente le SignalEngineMVP avec des outcomes labellisés.
    """

    ROLLING_WINDOW = 30  # KPIs sur les 30 derniers trades

    def __init__(self, signal_engine=None) -> None:
        self._signal_engine = signal_engine  # pour enregistrer les outcomes ML
        self._trades: deque[TradeRecord] = deque(maxlen=1000)
        self._regime_pnl: dict[str, list[float]] = defaultdict(list)
        self._signal_pnl: dict[str, list[float]] = defaultdict(list)
        self._equity_curve: deque[float] = deque(maxlen=500)
        self._load_history()
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────────────────────
    # API principale
    # ──────────────────────────────────────────────────────────────────────────

    def record(
        self,
        symbol: str,
        direction: str,
        signal_type: str,
        regime: str,
        entry_price: float,
        exit_price: float,
        size_usd: float,
        entry_score: float,
        entry_confidence: float,
        duration_minutes: float,
        expected_slippage_bps: float = 0.0,
        actual_slippage_bps: float = 0.0,
        fee_usd: float = 0.0,
        entry_features: dict | None = None,
    ) -> TradeRecord:
        """Enregistre un trade fermé et retourne son analyse complète."""
        pnl_pct = (
            ((exit_price - entry_price) / entry_price)
            if direction == "long"
            else ((entry_price - exit_price) / entry_price)
        )
        pnl_usd = size_usd * pnl_pct - fee_usd

        trade_id = f"{symbol.replace('/', '')}_{int(time.time())}"
        rec = TradeRecord(
            trade_id=trade_id,
            symbol=symbol,
            direction=direction,
            signal_type=signal_type,
            regime=regime,
            entry_price=entry_price,
            exit_price=exit_price,
            size_usd=size_usd,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            duration_minutes=duration_minutes,
            entry_score=entry_score,
            entry_confidence=entry_confidence,
            expected_slippage_bps=expected_slippage_bps,
            actual_slippage_bps=actual_slippage_bps,
            fee_usd=fee_usd,
        )

        # Attribution causale
        rec.attribution, rec.lesson = self._attribute(rec)

        # Enregistrement
        self._trades.append(rec)
        self._regime_pnl[regime].append(pnl_pct)
        self._signal_pnl[signal_type].append(pnl_pct)
        self._equity_curve.append(pnl_usd)

        # Feedback vers le SignalEngine pour entraîner LightGBM
        if self._signal_engine and entry_features:
            self._signal_engine.record_outcome(
                signal_type, entry_features, direction, pnl_pct
            )

        # Persistence
        self._persist(rec)

        _log.info(
            "[Learning] %s | %s | %s→ %.2f%% $%.2f | %s | %s",
            symbol,
            signal_type,
            direction,
            pnl_pct * 100,
            pnl_usd,
            rec.attribution,
            rec.lesson[:60] if rec.lesson else "",
        )

        return rec

    def kpis(self) -> KPIReport:
        """Calcule les KPIs sur les trades récents."""
        trades = list(self._trades)
        if not trades:
            return KPIReport()

        recent = trades[-self.ROLLING_WINDOW :]
        wins = [t for t in recent if t.pnl_usd > 0]
        losses = [t for t in recent if t.pnl_usd <= 0]

        win_rate = len(wins) / len(recent) if recent else 0.0

        avg_win = sum(t.pnl_usd for t in wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(t.pnl_usd for t in losses) / len(losses)) if losses else 0.0

        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        total_wins = sum(t.pnl_usd for t in wins)
        total_losses = abs(sum(t.pnl_usd for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

        sharpe = self._rolling_sharpe(recent)
        max_dd = self._max_drawdown(recent)
        avg_dur = sum(t.duration_minutes for t in recent) / len(recent)

        best_regime = self._best_regime()
        worst_regime = self._worst_regime()
        best_signal = self._best_signal()

        health = self._system_health(win_rate, sharpe, max_dd, expectancy)

        return KPIReport(
            n_trades=len(trades),
            win_rate=round(win_rate, 3),
            expectancy_usd=round(expectancy, 4),
            sharpe_rolling=round(sharpe, 3),
            max_drawdown_pct=round(max_dd * 100, 2),
            avg_win_usd=round(avg_win, 4),
            avg_loss_usd=round(avg_loss, 4),
            profit_factor=round(profit_factor, 2),
            avg_duration_min=round(avg_dur, 1),
            best_regime=best_regime,
            worst_regime=worst_regime,
            best_signal=best_signal,
            system_health=health,
        )

    def regime_win_rates(self) -> dict[str, float]:
        return {
            regime: sum(1 for p in pnls if p > 0) / len(pnls)
            for regime, pnls in self._regime_pnl.items()
            if len(pnls) >= 5
        }

    def recent_lessons(self, n: int = 5) -> list[str]:
        trades = list(self._trades)[-n:]
        return [f"[{t.signal_type}/{t.regime}] {t.lesson}" for t in trades if t.lesson]

    # ──────────────────────────────────────────────────────────────────────────
    # Attribution causale
    # ──────────────────────────────────────────────────────────────────────────

    def _attribute(self, rec: TradeRecord) -> tuple[str, str]:
        good_signal = rec.entry_score >= 65 and rec.entry_confidence >= 0.5
        good_execution = abs(rec.actual_slippage_bps - rec.expected_slippage_bps) < 15
        profitable = rec.pnl_pct > 0

        if profitable and good_signal and good_execution:
            return "validated", ""

        if profitable and not good_signal:
            return (
                "lucky",
                f"Signal faible (score={rec.entry_score:.0f}) mais trade rentable",
            )

        if not profitable:
            # Quelle composante est responsable ?
            slip_excess = rec.actual_slippage_bps - rec.expected_slippage_bps
            if slip_excess > 20:
                return (
                    "execution_error",
                    f"Slippage excessif: {rec.actual_slippage_bps:.0f}bps > attendu {rec.expected_slippage_bps:.0f}bps",
                )

            # Régime mal classifié ? (perte dans un régime habituellement profitable)
            regime_wr = self._regime_win_rate(rec.regime)
            if regime_wr is not None and regime_wr > 0.55 and not profitable:
                return (
                    "regime_mismatch",
                    f"Régime '{rec.regime}' normalement profitable (WR={regime_wr:.0%}) — revérifier classification",
                )

            if good_signal and not profitable:
                return (
                    "unlucky",
                    f"Bon signal (score={rec.entry_score:.0f}) mais marché adverse",
                )

            return (
                "signal_error",
                f"Score faible ({rec.entry_score:.0f}) en {rec.regime} — réviser seuils",
            )

        return "unknown", ""

    # ──────────────────────────────────────────────────────────────────────────
    # KPIs helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _rolling_sharpe(self, trades: list[TradeRecord]) -> float:
        if len(trades) < 5:
            return 0.0
        returns = [t.pnl_pct for t in trades]
        mean = sum(returns) / len(returns)
        std = (sum((r - mean) ** 2 for r in returns) / len(returns)) ** 0.5
        return (mean / std) * math.sqrt(252 * 24) if std > 0 else 0.0

    def _max_drawdown(self, trades: list[TradeRecord]) -> float:
        if not trades:
            return 0.0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            equity += t.pnl_usd
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def _best_regime(self) -> str:
        best, best_wr = "unknown", 0.0
        for r, pnls in self._regime_pnl.items():
            if len(pnls) < 5:
                continue
            wr = sum(1 for p in pnls if p > 0) / len(pnls)
            if wr > best_wr:
                best, best_wr = r, wr
        return best

    def _worst_regime(self) -> str:
        worst, worst_wr = "unknown", 1.0
        for r, pnls in self._regime_pnl.items():
            if len(pnls) < 5:
                continue
            wr = sum(1 for p in pnls if p > 0) / len(pnls)
            if wr < worst_wr:
                worst, worst_wr = r, wr
        return worst

    def _best_signal(self) -> str:
        best, best_exp = "unknown", float("-inf")
        for s, pnls in self._signal_pnl.items():
            if len(pnls) < 5:
                continue
            exp = sum(pnls) / len(pnls)
            if exp > best_exp:
                best, best_exp = s, exp
        return best

    def _regime_win_rate(self, regime: str) -> float | None:
        pnls = self._regime_pnl.get(regime, [])
        if len(pnls) < 5:
            return None
        return sum(1 for p in pnls if p > 0) / len(pnls)

    def _system_health(
        self, win_rate: float, sharpe: float, max_dd: float, expectancy: float
    ) -> str:
        if max_dd > 0.15 or expectancy < -10:
            return "CRITICAL"
        if win_rate < 0.35 or sharpe < -0.5 or max_dd > 0.08:
            return "DEGRADED"
        return "OK"

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────────

    def _persist(self, rec: TradeRecord) -> None:
        try:
            with _LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec.to_dict()) + "\n")
        except Exception as exc:
            _log.debug("[Learning] persist error: %s", exc)

    def _load_history(self) -> None:
        if not _LOG_PATH.exists():
            return
        try:
            loaded = 0
            with _LOG_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line.strip())
                        self._regime_pnl[d.get("regime", "unknown")].append(
                            d.get("pnl_pct", 0)
                        )
                        self._signal_pnl[d.get("signal_type", "unknown")].append(
                            d.get("pnl_pct", 0)
                        )
                        loaded += 1
                    except Exception:
                        continue
            if loaded:
                _log.info("[Learning] %d trades chargés depuis l'historique", loaded)
        except Exception as exc:
            _log.debug("[Learning] load error: %s", exc)
