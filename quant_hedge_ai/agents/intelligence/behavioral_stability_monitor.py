"""
behavioral_stability_monitor.py — Moniteur de stabilite comportementale.

Mesure en continu si le systeme derive, oscille ou converge.

Metriques surveillees :
  - Regime flip rate     : nb de changements de regime sur 10 cycles
  - Threshold variance   : variance du seuil effectif sur 20 cycles
  - Strategic entropy    : diversite de la distribution des strategies
  - Behavioral state     : STABLE / OSCILLATING / DRIFTING / FROZEN

Invariantes verifiees (system_invariants.py) :
  - MAX_REGIME_FLIPS_10C
  - MAX_CUMULATIVE_DELTA
  - MAX_SINGLE_STRATEGY_WEIGHT
  - MIN_PORTFOLIO_ENTROPY
  - MAX_CONSECUTIVE_IDLE_CYCLES

Usage :
    bsm = BehavioralStabilityMonitor()
    bsm.record_cycle(
        regime="sideways",
        threshold=66,
        strategy_name="sol_experimental",
        trade_executed=True,
    )
    report = bsm.report()
    violations = bsm.check_invariants()
"""

from __future__ import annotations

import math
import time
from collections import Counter, deque
from enum import Enum

from observability.json_logger import get_logger
from quant_hedge_ai.agents.intelligence.system_invariants import (
    MAX_CONSECUTIVE_IDLE_CYCLES,
    MAX_CUMULATIVE_DELTA,
    MAX_REGIME_FLIPS_10C,
    MIN_PORTFOLIO_ENTROPY,
    REGIME_FLIP_WINDOW,
    STRATEGY_ENTROPY_WINDOW,
    THRESHOLD_VAR_WINDOW,
)

_log = get_logger("quant_hedge_ai.agents.intelligence.behavioral_stability_monitor")


class BehavioralState(str, Enum):
    STABLE = "stable"
    OSCILLATING = "oscillating"  # trop de flips regime ou threshold instable
    DRIFTING = "drifting"  # threshold a derive loin du baseline
    FROZEN = "frozen"  # aucun trade depuis trop longtemps
    DEGRADED = "degraded"  # plusieurs violations simultanees


class BehavioralStabilityMonitor:
    """
    Detecte les derives systemiques du comportement adaptatif.

    Ne prend pas de decisions — observe et signale uniquement.
    """

    def __init__(self, threshold_baseline: int = 70) -> None:
        self._baseline = threshold_baseline

        # Fenetres glissantes
        self._regimes: deque[str] = deque(maxlen=REGIME_FLIP_WINDOW)
        self._thresholds: deque[int] = deque(maxlen=THRESHOLD_VAR_WINDOW)
        self._strategies: deque[str] = deque(maxlen=STRATEGY_ENTROPY_WINDOW)

        # Etat interne
        self._cycles_since_trade: int = 0
        self._total_cycles: int = 0
        self._violations_history: list[dict] = []

        # Stats instantanees (mises a jour a chaque record_cycle)
        self._last_flip_count: int = 0
        self._last_threshold_var: float = 0.0
        self._last_entropy: float = 1.0
        self._last_cumul_delta: int = 0
        self._last_state: BehavioralState = BehavioralState.STABLE
        self._last_ts: float = time.time()

        # V2 — Oscillation detector (fenetre 50 cycles)
        self._delta_window: deque[int] = deque(maxlen=50)
        self._accepted_scores: deque[int] = deque(maxlen=100)
        self._mismatch_count: int = 0

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record_cycle(
        self,
        regime: str,
        threshold: int,
        strategy_name: str = "",
        trade_executed: bool = False,
    ) -> None:
        """
        Appele a chaque cycle principal.

        Args:
            regime          : regime detecte ce cycle
            threshold       : seuil effectif utilise ce cycle
            strategy_name   : strategie qui a trade (vide si pas de trade)
            trade_executed  : True si un trade a ete execute
        """
        self._total_cycles += 1
        self._last_ts = time.time()

        self._regimes.append(regime)
        self._thresholds.append(threshold)

        if trade_executed and strategy_name:
            self._strategies.append(strategy_name)
            self._cycles_since_trade = 0
        else:
            self._cycles_since_trade += 1

        # Recalcul instantane
        self._last_flip_count = self._compute_flip_count()
        self._last_threshold_var = self._compute_threshold_variance()
        self._last_entropy = self._compute_entropy()
        self._last_cumul_delta = threshold - self._baseline
        self._last_state = self._compute_state()

    # ── Consultation ─────────────────────────────────────────────────────────

    def report(self) -> dict:
        """Dict complet pour COO briefing et Telegram."""
        violations = self.check_invariants()
        return {
            "state": self._last_state.value,
            "regime_flips_10c": self._last_flip_count,
            "threshold_variance": round(self._last_threshold_var, 2),
            "threshold_cumul_delta": self._last_cumul_delta,
            "portfolio_entropy": round(self._last_entropy, 3),
            "cycles_since_trade": self._cycles_since_trade,
            "total_cycles": self._total_cycles,
            "violations": violations,
            "n_violations": len(violations),
        }

    def check_invariants(self) -> list[str]:
        """
        Verifie les invariantes physiques.
        Retourne la liste des violations (vide = tout OK).
        """
        violations: list[str] = []

        if self._last_flip_count > MAX_REGIME_FLIPS_10C:
            violations.append(
                f"REGIME_INSTABLE: {self._last_flip_count} flips sur "
                f"{REGIME_FLIP_WINDOW} cycles (max={MAX_REGIME_FLIPS_10C})"
            )

        if abs(self._last_cumul_delta) > MAX_CUMULATIVE_DELTA:
            violations.append(
                f"THRESHOLD_DERIVE: delta={self._last_cumul_delta:+d} "
                f"vs baseline={self._baseline} (max=±{MAX_CUMULATIVE_DELTA})"
            )

        if len(self._strategies) >= 5 and self._last_entropy < MIN_PORTFOLIO_ENTROPY:
            top_strat, top_weight = self._top_strategy_weight()
            violations.append(
                f"CONCENTRATION: {top_strat} pese {top_weight:.0%} "
                f"(entropy={self._last_entropy:.2f} < {MIN_PORTFOLIO_ENTROPY})"
            )

        if self._cycles_since_trade >= MAX_CONSECUTIVE_IDLE_CYCLES:
            violations.append(
                f"CAPITAL_GELE: {self._cycles_since_trade} cycles sans trade "
                f"(max={MAX_CONSECUTIVE_IDLE_CYCLES})"
            )

        if violations:
            self._violations_history.append(
                {"ts": time.time(), "violations": violations}
            )
            if len(self._violations_history) > 200:
                self._violations_history = self._violations_history[-200:]

        return violations

    def behavioral_state(self) -> BehavioralState:
        return self._last_state

    # ── Calculs internes ──────────────────────────────────────────────────────

    def _compute_flip_count(self) -> int:
        """Nombre de changements de regime dans la fenetre glissante."""
        regimes = list(self._regimes)
        if len(regimes) < 2:
            return 0
        return sum(1 for i in range(1, len(regimes)) if regimes[i] != regimes[i - 1])

    def _compute_threshold_variance(self) -> float:
        """Variance du seuil effectif sur la fenetre."""
        vals = list(self._thresholds)
        if len(vals) < 3:
            return 0.0
        mean = sum(vals) / len(vals)
        return sum((v - mean) ** 2 for v in vals) / len(vals)

    def _compute_entropy(self) -> float:
        """
        Entropie de Shannon normalisee [0, 1] de la distribution des strategies.

        0 = une seule strategie (concentration maximale)
        1 = distribution parfaitement uniforme (diversite maximale)
        """
        strats = list(self._strategies)
        if not strats:
            return 1.0  # pas de trades = pas de concentration
        counts = Counter(strats)
        n = len(strats)
        k = len(counts)
        if k <= 1:
            return 0.0
        entropy = -sum((c / n) * math.log(c / n) for c in counts.values())
        max_entropy = math.log(k)
        return entropy / max_entropy if max_entropy > 0 else 1.0

    def _top_strategy_weight(self) -> tuple[str, float]:
        """Retourne (nom_strategie, poids) de la strategie dominante."""
        strats = list(self._strategies)
        if not strats:
            return ("none", 0.0)
        counts = Counter(strats)
        top = counts.most_common(1)[0]
        return (top[0], top[1] / len(strats))

    def _compute_state(self) -> BehavioralState:
        """
        Etat comportemental global.

        Priorite : DEGRADED > OSCILLATING > DRIFTING > FROZEN > STABLE
        """
        n_violations = 0

        is_oscillating = self._last_flip_count > MAX_REGIME_FLIPS_10C
        is_drifting = abs(self._last_cumul_delta) > MAX_CUMULATIVE_DELTA
        is_frozen = self._cycles_since_trade >= MAX_CONSECUTIVE_IDLE_CYCLES
        is_concentrated = (
            len(self._strategies) >= 5 and self._last_entropy < MIN_PORTFOLIO_ENTROPY
        )

        for flag in (is_oscillating, is_drifting, is_frozen, is_concentrated):
            if flag:
                n_violations += 1

        if n_violations >= 2:
            return BehavioralState.DEGRADED
        if is_oscillating:
            return BehavioralState.OSCILLATING
        if is_drifting:
            return BehavioralState.DRIFTING
        if is_frozen:
            return BehavioralState.FROZEN
        return BehavioralState.STABLE

    # ── Debug ─────────────────────────────────────────────────────────────────

    def summary_line(self) -> str:
        """Ligne de log courte pour debug."""
        return (
            f"BSM state={self._last_state.value} "
            f"flips={self._last_flip_count}/{MAX_REGIME_FLIPS_10C} "
            f"delta={self._last_cumul_delta:+d} "
            f"entropy={self._last_entropy:.2f} "
            f"idle={self._cycles_since_trade}c"
        )

    # ── V2 — Oscillation detector ──────────────────────────────────────────────

    def on_threshold_delta(self, delta: int) -> None:
        """Enregistrer le delta ATE du cycle courant (V2)."""
        self._delta_window.append(delta)

    def on_score_accepted(self, score: int) -> None:
        """Enregistrer un score accepté par le gate (V3 baseline)."""
        self._accepted_scores.append(score)

    def on_mismatch(self) -> None:
        """Incrémenter le compteur REGIME_MISMATCH (V3 baseline)."""
        self._mismatch_count += 1

    def _compute_threshold_flip_count(self) -> int:
        """Nombre de changements de direction du delta sur la fenêtre."""
        deltas = list(self._delta_window)
        if len(deltas) < 3:
            return 0
        flips = 0
        for i in range(2, len(deltas)):
            prev_diff = deltas[i - 1] - deltas[i - 2]
            curr_diff = deltas[i] - deltas[i - 1]
            if prev_diff != 0 and curr_diff != 0 and prev_diff * curr_diff < 0:
                flips += 1
        return flips

    @property
    def oscillation_score(self) -> str:
        """LOW / MED / HIGH selon flips threshold + flips régime."""
        thr_flips = self._compute_threshold_flip_count()
        reg_flips = self._last_flip_count
        if thr_flips > 8 or reg_flips > 4:
            return "HIGH"
        if thr_flips > 4 or reg_flips > 2:
            return "MED"
        return "LOW"

    # ── V3 — Log [BEHAVIOR] ────────────────────────────────────────────────────

    def behavior_log(self) -> str:
        """
        Ligne [BEHAVIOR] périodique — snapshot comportemental complet.

        Appeler toutes les N cycles pour tracer la stabilité à long terme.
        """
        thresholds = list(self._thresholds)
        avg_thr = round(sum(thresholds) / len(thresholds)) if thresholds else 0
        std_thr = round(math.sqrt(self._last_threshold_var), 1)

        regimes = list(self._regimes)
        if regimes:
            counts = Counter(regimes)
            total = len(regimes)
            regime_dist = " ".join(
                f"{r[:4].upper()}={c / total:.0%}"
                for r, c in sorted(counts.items(), key=lambda x: -x[1])[:3]
            )
            transitions = sum(
                1 for i in range(1, len(regimes)) if regimes[i] != regimes[i - 1]
            )
        else:
            regime_dist = "?"
            transitions = 0

        scores = list(self._accepted_scores)
        avg_score = round(sum(scores) / len(scores)) if scores else 0

        thr_flips = self._compute_threshold_flip_count()

        return (
            f"[BEHAVIOR] avg_thr={avg_thr} std={std_thr} flips={thr_flips} "
            f"| {regime_dist} | trans={transitions} "
            f"| avg_score={avg_score} mismatch={self._mismatch_count} "
            f"| state={self._last_state.value} osc={self.oscillation_score}"
        )
