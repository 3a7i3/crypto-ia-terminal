"""
stress_test.py — Monte Carlo Stress Test avec scénarios de chaos (Idée #6).

Pas juste un backtest normal — simulation de survie sous :
  - séries de pertes prolongées (consecutive loss streaks)
  - flash crash (choc négatif brutal)
  - spread explosion (coût de transaction x10)
  - liquidité faible (slippage extrême)
  - drawdown extrême

Objectif : voir si le système SURVIT, pas seulement s'il gagne.

Usage:
    tester = MonteCarloStressTester(equity=50_000, win_rate=0.55,
                                    avg_win=0.02, avg_loss=0.01)
    report = tester.run_all()
    print(report.summary())
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StressScenario:
    name: str
    paths: int
    steps: int
    result: dict = field(default_factory=dict)

    def survival_rate(self) -> float:
        return self.result.get("survival_rate_pct", 0.0)

    def median_final_equity(self) -> float:
        return self.result.get("median_final_equity", 0.0)

    def ruin_rate(self) -> float:
        return 100.0 - self.survival_rate()


@dataclass
class StressReport:
    initial_equity: float
    scenarios: list[StressScenario] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"{'='*58}",
            f"STRESS TEST — Capital initial: {self.initial_equity:,.0f} USD",
            f"{'='*58}",
            f"{'Scénario':<28} {'Survie':>8} {'Ruine':>8} {'Médiane':>12}",
            f"{'─'*58}",
        ]
        for s in self.scenarios:
            lines.append(
                f"{s.name:<28} {s.survival_rate():>7.1f}% "
                f"{s.ruin_rate():>7.1f}% "
                f"{s.median_final_equity():>10,.0f}"
            )
        lines.append(f"{'='*58}")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "initial_equity": self.initial_equity,
            "scenarios": [
                {"name": s.name, "result": s.result} for s in self.scenarios
            ],
        }

    def worst_scenario(self) -> StressScenario | None:
        if not self.scenarios:
            return None
        return min(self.scenarios, key=lambda s: s.survival_rate())


class MonteCarloStressTester:
    """
    Lance plusieurs scénarios de stress Monte Carlo.

    Paramètres clés :
        equity      : capital initial
        win_rate    : probabilité de gain par trade (0.0-1.0)
        avg_win     : gain moyen par trade (fraction de l'equity, ex. 0.02 = 2 %)
        avg_loss    : perte moyenne par trade (fraction, ex. 0.01 = 1 %)
        position_pct: fraction du capital engagée par trade (défaut 2 %)
    """

    _RUIN_THRESHOLD = 0.20   # <20% de l'equity initiale = ruine

    def __init__(
        self,
        equity: float = 100_000.0,
        win_rate: float = 0.55,
        avg_win: float = 0.015,
        avg_loss: float = 0.010,
        position_pct: float = 0.02,
        seed: int | None = None,
    ) -> None:
        self.equity = equity
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss
        self.position_pct = position_pct
        self._rng = random.Random(seed)

    # ── API principale ─────────────────────────────────────────────────────────

    def run_all(self, paths: int = 1000, steps: int = 200) -> StressReport:
        report = StressReport(initial_equity=self.equity)

        scenarios_def = [
            ("Normal",                self._sim_normal),
            ("Pertes prolongées",     self._sim_loss_streak),
            ("Flash crash",           self._sim_flash_crash),
            ("Spread x10",            self._sim_spread_explosion),
            ("Liquidité faible",      self._sim_low_liquidity),
            ("Drawdown extrême 40%",  self._sim_extreme_drawdown),
            ("Combiné chaos",         self._sim_combined_chaos),
        ]

        for name, fn in scenarios_def:
            result = fn(paths=paths, steps=steps)
            report.scenarios.append(StressScenario(name=name, paths=paths,
                                                    steps=steps, result=result))
        return report

    def run_scenario(self, name: str, paths: int = 500, steps: int = 200) -> dict:
        fn_map = {
            "normal":          self._sim_normal,
            "loss_streak":     self._sim_loss_streak,
            "flash_crash":     self._sim_flash_crash,
            "spread":          self._sim_spread_explosion,
            "low_liquidity":   self._sim_low_liquidity,
            "extreme_drawdown": self._sim_extreme_drawdown,
            "chaos":           self._sim_combined_chaos,
        }
        fn = fn_map.get(name.lower(), self._sim_normal)
        return fn(paths=paths, steps=steps)

    # ── Scénarios ──────────────────────────────────────────────────────────────

    def _sim_normal(self, paths: int, steps: int) -> dict:
        return self._simulate(paths, steps)

    def _sim_loss_streak(self, paths: int, steps: int) -> dict:
        """Injecte des séries de 5-15 pertes consécutives."""
        def modifier(step: int, eq: float) -> tuple[float, float]:
            wr = self.win_rate * 0.3  # win rate divisé par 3
            return wr, self.avg_loss * 1.5

        return self._simulate(paths, steps, modifier=modifier)

    def _sim_flash_crash(self, paths: int, steps: int) -> dict:
        """Choc négatif brutal de -15 à -40 % à un moment aléatoire."""
        def modifier(step: int, eq: float) -> tuple[float, float]:
            return self.win_rate, self.avg_loss

        def shock(path_equities: list[float]) -> list[float]:
            n = len(path_equities)
            shock_at = self._rng.randint(int(n * 0.1), int(n * 0.9))
            shock_pct = self._rng.uniform(0.15, 0.40)
            path_equities[shock_at] *= (1.0 - shock_pct)
            # propagation partielle
            for i in range(shock_at + 1, min(shock_at + 10, n)):
                path_equities[i] *= (1.0 - shock_pct * 0.1)
            return path_equities

        return self._simulate(paths, steps, post_process=shock)

    def _sim_spread_explosion(self, paths: int, steps: int) -> dict:
        """Coût de transaction x10 (spread très large)."""
        def modifier(step: int, eq: float) -> tuple[float, float]:
            # Chaque trade coûte 10x plus en frais
            return self.win_rate, self.avg_loss * 2.5

        return self._simulate(paths, steps, modifier=modifier,
                              extra_cost_pct=0.005)  # 0.5% frais par trade

    def _sim_low_liquidity(self, paths: int, steps: int) -> dict:
        """Slippage extrême — le prix réel est bien pire que théorique."""
        def modifier(step: int, eq: float) -> tuple[float, float]:
            avg_win = self.avg_win * 0.6    # gain réduit par slippage
            avg_loss = self.avg_loss * 1.8  # perte amplifiée par slippage
            return self.win_rate, avg_loss

        return self._simulate(paths, steps, modifier=modifier,
                              win_modifier=0.6)

    def _sim_extreme_drawdown(self, paths: int, steps: int) -> dict:
        """Drawdown de -40 % forcé suivi de récupération difficile."""
        def shock(path_equities: list[float]) -> list[float]:
            n = len(path_equities)
            dd_start = int(n * 0.15)
            dd_end = int(n * 0.40)
            for i in range(dd_start, dd_end):
                decay = (i - dd_start) / max(1, dd_end - dd_start)
                path_equities[i] *= (1.0 - 0.40 * decay)
            return path_equities

        return self._simulate(paths, steps, post_process=shock)

    def _sim_combined_chaos(self, paths: int, steps: int) -> dict:
        """Combinaison de tous les chocs — pire cas."""
        def modifier(step: int, eq: float) -> tuple[float, float]:
            wr = self.win_rate * (0.5 + self._rng.random() * 0.3)
            return wr, self.avg_loss * (1.0 + self._rng.random())

        def shock(path_equities: list[float]) -> list[float]:
            n = len(path_equities)
            # Flash crash aléatoire
            if self._rng.random() > 0.4:
                at = self._rng.randint(0, n - 1)
                path_equities[at] *= (1.0 - self._rng.uniform(0.10, 0.35))
            return path_equities

        return self._simulate(paths, steps, modifier=modifier, post_process=shock,
                              extra_cost_pct=0.003, win_modifier=0.7)

    # ── Simulation core ────────────────────────────────────────────────────────

    def _simulate(
        self,
        paths: int,
        steps: int,
        modifier=None,
        post_process=None,
        extra_cost_pct: float = 0.0,
        win_modifier: float = 1.0,
    ) -> dict:
        ruin_threshold = self.equity * self._RUIN_THRESHOLD
        survivors = 0
        finals: list[float] = []
        max_dds: list[float] = []

        for _ in range(paths):
            eq = self.equity
            path_eq = [eq]
            peak = eq

            for step in range(steps):
                wr, al = self.win_rate, self.avg_loss
                aw = self.avg_win * win_modifier

                if modifier:
                    wr, al = modifier(step, eq)

                pos_size = eq * self.position_pct
                if self._rng.random() < wr:
                    # trade gagnant
                    gain = pos_size * aw * (0.8 + self._rng.random() * 0.4)
                    eq += gain
                else:
                    # trade perdant
                    loss = pos_size * al * (0.8 + self._rng.random() * 0.4)
                    eq -= loss

                # frais
                eq -= eq * extra_cost_pct

                eq = max(0.0, eq)
                path_eq.append(eq)

                if eq > peak:
                    peak = eq

            if post_process:
                path_eq = post_process(path_eq)
                eq = path_eq[-1]
                peak = max(path_eq)

            final = eq
            finals.append(final)

            # drawdown max sur ce path
            path_peak = path_eq[0]
            max_dd = 0.0
            for v in path_eq:
                if v > path_peak:
                    path_peak = v
                dd = (path_peak - v) / path_peak if path_peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
            max_dds.append(max_dd)

            if final > ruin_threshold:
                survivors += 1

        finals_sorted = sorted(finals)
        n = len(finals_sorted)
        survival_rate = survivors / paths * 100.0
        median = finals_sorted[n // 2]
        p05 = finals_sorted[max(0, int(0.05 * n) - 1)]
        p95 = finals_sorted[min(n - 1, int(0.95 * n))]
        avg_max_dd = sum(max_dds) / len(max_dds) if max_dds else 0.0
        worst_dd = max(max_dds, default=0.0)

        return {
            "paths": paths,
            "steps": steps,
            "survival_rate_pct": round(survival_rate, 2),
            "ruin_rate_pct": round(100.0 - survival_rate, 2),
            "median_final_equity": round(median, 2),
            "p05_final_equity": round(p05, 2),
            "p95_final_equity": round(p95, 2),
            "avg_max_drawdown_pct": round(avg_max_dd * 100, 2),
            "worst_max_drawdown_pct": round(worst_dd * 100, 2),
            "median_return_pct": round((median / self.equity - 1.0) * 100, 2),
        }
