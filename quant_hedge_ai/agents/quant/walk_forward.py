"""
Walk-Forward Validator — détecte l'overfitting des stratégies.

Principe :
    - Sépare les données en in-sample (entraînement) et out-of-sample (test)
    - Compare les métriques sur les deux périodes
    - Signale les stratégies dont la performance s'effondre hors-sample

Usage :
    validator = WalkForwardValidator()
    result = validator.validate(strategy, candles_2_years)
    if result.is_overfit:
        print(
            "Overfitting détecté — "
            f"Sharpe IS={result.sharpe_in:.2f} "
            f"OOS={result.sharpe_out:.2f}"
        )
"""

from __future__ import annotations

from dataclasses import dataclass, field

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.quant.walk_forward")


@dataclass
class WalkForwardResult:
    strategy: dict = field(default_factory=dict)
    n_candles: int = 0

    # In-sample (70%)
    sharpe_in: float = 0.0
    pnl_in: float = 0.0
    drawdown_in: float = 0.0
    win_rate_in: float = 0.0
    trades_in: int = 0

    # Out-of-sample (30%)
    sharpe_out: float = 0.0
    pnl_out: float = 0.0
    drawdown_out: float = 0.0
    win_rate_out: float = 0.0
    trades_out: int = 0

    # Verdict
    is_overfit: bool = False
    overfit_score: float = 0.0  # 0 = pas d'overfit, 1 = overfit total
    verdict: str = "unknown"

    def as_dict(self) -> dict:
        return {
            "n_candles": self.n_candles,
            "in_sample": {
                "sharpe": round(self.sharpe_in, 4),
                "pnl_pct": round(self.pnl_in, 4),
                "drawdown": round(self.drawdown_in, 4),
                "win_rate": round(self.win_rate_in, 4),
                "trades": self.trades_in,
            },
            "out_of_sample": {
                "sharpe": round(self.sharpe_out, 4),
                "pnl_pct": round(self.pnl_out, 4),
                "drawdown": round(self.drawdown_out, 4),
                "win_rate": round(self.win_rate_out, 4),
                "trades": self.trades_out,
            },
            "is_overfit": self.is_overfit,
            "overfit_score": round(self.overfit_score, 3),
            "verdict": self.verdict,
        }


class WalkForwardValidator:
    """
    Valide une stratégie sur données historiques réelles en séparant
    la période d'entraînement (in-sample) de la période de test (out-of-sample).

    Critères d'overfitting :
        - Sharpe OOS < Sharpe IS × decay_threshold (défaut 0.5)
        - PnL OOS négatif alors que PnL IS positif
        - Pas assez de trades OOS pour être statistiquement significatif
    """

    def __init__(
        self,
        train_ratio: float = 0.7,
        decay_threshold: float = 0.5,
        min_trades_oos: int = 5,
    ) -> None:
        self.train_ratio = train_ratio
        self.decay_threshold = decay_threshold
        self.min_trades_oos = min_trades_oos

    def validate(
        self,
        strategy: dict,
        candles: list[dict],
    ) -> WalkForwardResult:
        """
        Exécute le backtest en IS et OOS, retourne le WalkForwardResult.
        """
        from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab

        lab = BacktestLab()
        n = len(candles)
        split = int(n * self.train_ratio)

        in_sample = candles[:split]
        out_sample = candles[split:]

        result = WalkForwardResult(strategy=strategy, n_candles=n)

        # In-sample backtest
        r_in = lab.run_backtest(strategy, in_sample)
        result.sharpe_in = r_in["sharpe"]
        result.pnl_in = r_in["pnl"]
        result.drawdown_in = r_in["drawdown"]
        result.win_rate_in = r_in["win_rate"]
        result.trades_in = r_in["trades"]

        # Out-of-sample backtest
        r_out = lab.run_backtest(strategy, out_sample)
        result.sharpe_out = r_out["sharpe"]
        result.pnl_out = r_out["pnl"]
        result.drawdown_out = r_out["drawdown"]
        result.win_rate_out = r_out["win_rate"]
        result.trades_out = r_out["trades"]

        result.overfit_score, result.is_overfit, result.verdict = self._verdict(result)
        return result

    def _verdict(self, r: WalkForwardResult) -> tuple[float, bool, str]:
        """Calcule le score d'overfitting (0=ok, 1=overfit total) et le verdict."""
        score = 0.0
        reasons: list[str] = []

        # Critère 1 : dégradation du Sharpe IS → OOS
        if r.sharpe_in > 0.1:
            decay = r.sharpe_out / r.sharpe_in
            if decay < self.decay_threshold:
                score += 0.4
                reasons.append(f"Sharpe decay {decay:.1%} < {self.decay_threshold:.0%}")
        elif r.sharpe_in <= 0:
            score += 0.2
            reasons.append("Sharpe IS <= 0")

        # Critère 2 : PnL OOS négatif alors que IS positif
        if r.pnl_in > 1.0 and r.pnl_out < 0:
            score += 0.3
            reasons.append(f"PnL IS={r.pnl_in:.1f}% → OOS={r.pnl_out:.1f}%")

        # Critère 3 : pas assez de trades OOS
        if r.trades_out < self.min_trades_oos:
            score += 0.2
            reasons.append(f"Trades OOS={r.trades_out} < {self.min_trades_oos}")

        # Critère 4 : drawdown OOS >> drawdown IS
        if r.drawdown_in > 0 and r.drawdown_out > r.drawdown_in * 2:
            score += 0.1
            reasons.append(
                f"Drawdown IS={r.drawdown_in:.1%} → OOS={r.drawdown_out:.1%}"
            )

        score = min(score, 1.0)
        is_overfit = score >= 0.5

        if score < 0.2:
            verdict = "ROBUSTE"
        elif score < 0.4:
            verdict = "ACCEPTABLE"
        elif score < 0.6:
            verdict = "SUSPECT"
        else:
            verdict = "OVERFIT"

        if reasons:
            _log.debug(
                "[WalkForward] %s score=%.2f — %s",
                verdict,
                score,
                ", ".join(reasons),
            )

        return score, is_overfit, verdict

    def validate_batch(
        self,
        strategies: list[dict],
        candles: list[dict],
        verbose: bool = True,
    ) -> list[WalkForwardResult]:
        """Valide un lot de stratégies sur les mêmes données."""
        results = []
        for i, strategy in enumerate(strategies):
            r = self.validate(strategy, candles)
            results.append(r)
            if verbose and (i + 1) % 10 == 0:
                _log.info(
                    "[WalkForward] %d/%d stratégies validées",
                    i + 1,
                    len(strategies),
                )
        return results

    @staticmethod
    def summary(results: list[WalkForwardResult]) -> dict:
        """Résumé statistique d'un lot de résultats WalkForward."""
        if not results:
            return {}

        n = len(results)
        robust = sum(1 for r in results if r.verdict == "ROBUSTE")
        acceptable = sum(1 for r in results if r.verdict == "ACCEPTABLE")
        suspect = sum(1 for r in results if r.verdict == "SUSPECT")
        overfit = sum(1 for r in results if r.verdict == "OVERFIT")

        avg_sharpe_in = sum(r.sharpe_in for r in results) / n
        avg_sharpe_out = sum(r.sharpe_out for r in results) / n
        avg_decay = avg_sharpe_out / avg_sharpe_in if avg_sharpe_in > 0 else 0.0

        best = max(results, key=lambda r: r.sharpe_out)

        return {
            "total": n,
            "robust": robust,
            "acceptable": acceptable,
            "suspect": suspect,
            "overfit": overfit,
            "overfit_rate": round(overfit / n, 3),
            "avg_sharpe_in": round(avg_sharpe_in, 4),
            "avg_sharpe_out": round(avg_sharpe_out, 4),
            "sharpe_decay": round(avg_decay, 3),
            "best_sharpe_out": round(best.sharpe_out, 4),
            "best_strategy": best.strategy,
        }
