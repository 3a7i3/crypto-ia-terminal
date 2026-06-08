"""
Edge Scoring System (ESS) — filtre de viabilité microstructurelle.

Classifie une stratégie selon sa capacité à survivre aux frictions réelles.
Produit un score, un verdict et le niveau de friction break-even.

Score = nombre de combinaisons (dataset × friction) où expectancy > 0
Verdict :
  VIABLE   >= 9/12 combinaisons positives
  MARGINAL  5-8/12
  DEAD     <  5/12
"""

from src.agent.codex_agent import CodexAgent
from src.backtest.engine import BacktestEngine
from src.backtest.walk_forward import sliding_windows
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.execution.enl import ENLConfig, NoisyExchange
from src.portfolio.portfolio_state import PortfolioState
from src.risk.kill_switch import KillSwitch
from src.runtime.run_context import RunContext

_FRICTION_LEVELS = [
    ("clean", ENLConfig.clean()),
    ("light", ENLConfig.light()),
    ("realistic", ENLConfig.realistic()),
    ("heavy", ENLConfig.heavy()),
]

_DATASETS = [
    ("BTC 4h", "BTCUSDT", "4h"),
    ("ETH 4h", "ETHUSDT", "4h"),
    ("SOL 1h", "SOLUSDT", "1h"),
]


class EdgeScorer:
    def __init__(self, balance: float = 10_000.0, window: int = 120, step: int = 15):
        self._balance = balance
        self._window = window
        self._step = step

    def score(
        self,
        strategy_factory,
        candles_by_dataset: dict[str, list[dict]],
        strategy_id: str = "UNKNOWN",
    ) -> dict:
        """
        strategy_factory : callable sans argument → StrategyInterface
        candles_by_dataset : {"BTC 4h": [...], "ETH 4h": [...], "SOL 1h": [...]}

        Retourne :
        {
          "score":       int,        # 0-12 combinaisons positives
          "verdict":     str,        # VIABLE / MARGINAL / DEAD
          "matrix":      dict,       # {dataset: {friction_label: expectancy}}
          "breakeven":   str | None, # premier niveau de friction où tout passe négatif
          "clean_avg":   float,      # expectancy clean (référence)
          "edge_buffer": float,      # écart clean - light
        }
        """
        matrix: dict[str, dict[str, float]] = {}
        positive = 0
        total = 0
        clean_exps: list[float] = []
        light_exps: list[float] = []
        realistic_exps: list[float] = []

        for ds_label, candles in candles_by_dataset.items():
            matrix[ds_label] = {}
            feeds = sliding_windows(candles, self._window, self._step)
            if not feeds:
                continue

            for fr_label, fr_config in _FRICTION_LEVELS:
                exp = self._avg_expectancy(
                    strategy_factory, feeds, fr_config, strategy_id
                )
                matrix[ds_label][fr_label] = round(exp, 4)
                total += 1
                if exp > 0:
                    positive += 1
                if fr_label == "clean":
                    clean_exps.append(exp)
                if fr_label == "light":
                    light_exps.append(exp)
                if fr_label == "realistic":
                    realistic_exps.append(exp)

        score = positive
        verdict = "VIABLE" if score >= 9 else "MARGINAL" if score >= 5 else "DEAD"

        clean_avg = sum(clean_exps) / len(clean_exps) if clean_exps else 0.0
        light_avg = sum(light_exps) / len(light_exps) if light_exps else 0.0
        real_avg = sum(realistic_exps) / len(realistic_exps) if realistic_exps else 0.0
        edge_buffer = clean_avg - light_avg

        # Ratio de survie : fraction de l'edge clean qui survit en realistic.
        # N'a de sens que si clean_avg > 0 (signal positif en conditions propres).
        # Si clean_avg <= 0, le ratio est indéfini → None.
        if clean_avg > 0:
            edge_survival_ratio = real_avg / clean_avg
        else:
            edge_survival_ratio = None

        # Break-even : premier niveau où la moyenne des datasets passe négative.
        # Si clean_avg = 0 (aucun trade généré), on marque "no_trades".
        if clean_avg == 0.0:
            breakeven = "no_trades"
        else:
            breakeven = None
            for fr_label, _ in _FRICTION_LEVELS:
                fr_avgs = [matrix[ds].get(fr_label, 0.0) for ds in matrix]
                if fr_avgs and sum(fr_avgs) / len(fr_avgs) <= 0:
                    breakeven = fr_label
                    break

        return {
            "score": score,
            "total": total,
            "verdict": verdict,
            "matrix": matrix,
            "breakeven": breakeven,
            "clean_avg": round(clean_avg, 4),
            "edge_buffer": round(edge_buffer, 4),
            "edge_survival_ratio": (
                round(edge_survival_ratio, 4)
                if edge_survival_ratio is not None
                else None
            ),
        }

    def _avg_expectancy(self, factory, feeds, config, strategy_id) -> float:
        exps = []
        for feed in feeds:
            feed.reset()
            portfolio = PortfolioState(balance=self._balance)
            exchange = VirtualExchange(portfolio)
            noisy = NoisyExchange(exchange, config)
            router = ExecutionRouter(noisy)
            agent = CodexAgent(factory(), KillSwitch())
            ctx = RunContext(strategy_id=strategy_id)
            r = BacktestEngine(agent, router, feed, portfolio, ctx).run()
            t = r["total_trades"]
            exps.append(r["total_pnl"] / t if t > 0 else 0.0)
        return sum(exps) / len(exps) if exps else 0.0
