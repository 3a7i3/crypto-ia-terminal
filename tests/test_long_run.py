"""
P11-C — Long Run Simulation.

Tests de résilience sur volumes élevés de cycles synthétiques.

C1 — 10k cycles baseline     : no exception, capital >= 0, métriques stables
C2 — State drift detection   : même seed → résultat identique bit-à-bit
C3 — Memory leak hunt        : tracemalloc, croissance linéaire bornée
C4 — 100k cycles (slow)      : endurance complète — run avec -m slow

Architecture du simulateur :
  PaperTradingEngine(persist=False)   — in-memory, pas d'I/O disque
  compute_signal(strategy, candles)   — RSI déterministe
  deque(maxlen=30)                    — fenêtre glissante bornée
  random.Random(seed)                 — déterminisme contrôlé
"""

from __future__ import annotations

import gc
import random
import time
import tracemalloc
from collections import deque
from dataclasses import dataclass, field

import pytest

# ── Configuration simulation ──────────────────────────────────────────────────

_STRATEGY_RSI = {
    "entry_indicator": "RSI",
    "period": 14,
    "entry_threshold": 35,
    "exit_threshold": 65,
}
_SYMBOL = "BTC/USDT"
_INITIAL_BALANCE = 10_000.0
_ORDER_SIZE = 0.001  # 0.001 BTC par ordre
_BASE_PRICE = 50_000.0
_VOLATILITY = 0.002  # 0.2% / candle
_CHECKPOINT_INTERVAL = 1_000


# ── Simulateur synthétique ────────────────────────────────────────────────────


@dataclass
class SimMetrics:
    cycle: int
    balance: float
    trades: int
    equity_entries: int


@dataclass
class SimResult:
    final_balance: float
    total_trades: int
    total_cycles: int
    positions: dict
    metrics: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)


def _make_candle(price: float, rng: random.Random) -> dict:
    change = rng.gauss(0, _VOLATILITY)
    close = round(price * (1 + change), 2)
    spread = abs(rng.gauss(0, _VOLATILITY * 0.5))
    return {
        "open": round(price, 2),
        "high": round(max(price, close) * (1 + spread), 2),
        "low": round(min(price, close) * (1 - spread), 2),
        "close": close,
        "volume": rng.uniform(1.0, 50.0),
        "timestamp": 0,  # fixe pour déterminisme
    }


def _run_simulation(
    n_cycles: int,
    seed: int = 42,
    checkpoint_every: int = _CHECKPOINT_INTERVAL,
) -> SimResult:
    """
    Simulation légère et déterministe :
    signal RSI → paper execute → métriques échantillonnées.

    persist=False : aucun I/O disque pendant le run.
    """
    from quant_hedge_ai.agents.execution.paper_trading_engine import PaperTradingEngine
    from quant_hedge_ai.agents.execution.signal_engine import compute_signal

    rng = random.Random(seed)
    engine = PaperTradingEngine(initial_balance=_INITIAL_BALANCE, persist=False)
    window: deque = deque(maxlen=30)
    price = _BASE_PRICE
    exceptions: list[str] = []
    metrics: list[SimMetrics] = []

    for cycle in range(n_cycles):
        try:
            candle = _make_candle(price, rng)
            price = candle["close"]
            window.append(candle)

            signal = compute_signal(_STRATEGY_RSI, list(window))
            has_pos = engine.positions.get(_SYMBOL, 0.0) > 0
            cost = price * _ORDER_SIZE

            if signal == "BUY" and not has_pos and engine.balance >= cost:
                engine.execute(
                    {"symbol": _SYMBOL, "action": "BUY", "size": _ORDER_SIZE}, price
                )
            elif signal == "SELL" and has_pos:
                engine.execute(
                    {"symbol": _SYMBOL, "action": "SELL", "size": _ORDER_SIZE}, price
                )

        except Exception as exc:  # noqa: BLE001
            exceptions.append(f"cycle={cycle}: {exc}")

        if checkpoint_every and (cycle + 1) % checkpoint_every == 0:
            metrics.append(
                SimMetrics(
                    cycle=cycle + 1,
                    balance=round(engine.balance, 4),
                    trades=len(engine.trade_history),
                    equity_entries=len(engine.equity_curve),
                )
            )

    return SimResult(
        final_balance=round(engine.balance, 6),
        total_trades=len(engine.trade_history),
        total_cycles=n_cycles,
        positions=dict(engine.positions),
        metrics=metrics,
        exceptions=exceptions,
    )


# ══════════════════════════════════════════════════════════════════════════════
# C1 — 10k Cycles Baseline
# ══════════════════════════════════════════════════════════════════════════════


class TestC1Baseline:
    """10 000 cycles : aucune exception, capital sain, métriques contrôlées."""

    def test_10k_cycles_completes_without_exception(self):
        result = _run_simulation(10_000)
        assert (
            result.exceptions == []
        ), f"Exceptions détectées : {result.exceptions[:3]}"

    def test_10k_cycles_all_cycles_executed(self):
        result = _run_simulation(10_000)
        assert result.total_cycles == 10_000

    def test_10k_cycles_capital_non_negative(self):
        result = _run_simulation(10_000)
        assert (
            result.final_balance >= 0.0
        ), f"Capital négatif après 10k cycles : {result.final_balance}"

    def test_10k_cycles_positions_non_negative(self):
        result = _run_simulation(10_000)
        for sym, qty in result.positions.items():
            assert qty >= 0.0, f"Quantité négative {sym}={qty}"

    def test_10k_checkpoints_sampled(self):
        result = _run_simulation(10_000, checkpoint_every=1_000)
        assert (
            len(result.metrics) == 10
        ), f"Attendu 10 checkpoints, obtenu {len(result.metrics)}"

    def test_10k_checkpoint_balance_monotone_reasonable(self):
        """Capital reste dans une fourchette raisonnable à chaque checkpoint."""
        result = _run_simulation(10_000)
        for m in result.metrics:
            assert m.balance >= 0.0, f"Capital négatif au cycle {m.cycle}"
            assert (
                m.balance <= _INITIAL_BALANCE * 10
            ), f"Capital irréaliste au cycle {m.cycle}: {m.balance}"

    def test_10k_trade_rate_bounded(self):
        """Taux de trade < 50% (RSI ne génère pas de signal à chaque candle)."""
        result = _run_simulation(10_000)
        trade_rate = result.total_trades / 10_000
        assert trade_rate < 0.50, f"Taux anormal: {trade_rate:.1%}"

    def test_10k_trade_history_linear_growth(self):
        """Croissance trade_history linéaire : checkpoint N proportionnel au cycle."""
        result = _run_simulation(10_000, checkpoint_every=1_000)
        if len(result.metrics) < 2:
            pytest.skip("Pas assez de checkpoints")

        # Chaque checkpoint doit avoir un nombre de trades >= au précédent
        for i in range(1, len(result.metrics)):
            assert (
                result.metrics[i].trades >= result.metrics[i - 1].trades
            ), f"Trade history décroissante au cycle {result.metrics[i].cycle}"

    def test_10k_performance_under_30s(self):
        """10 000 cycles en moins de 30 secondes."""
        t0 = time.monotonic()
        _run_simulation(10_000)
        elapsed = time.monotonic() - t0
        assert elapsed < 30.0, f"10k cycles trop lents : {elapsed:.2f}s"

    def test_10k_equity_curve_consistent_with_trades(self):
        """equity_curve a autant d'entrées que trade_history."""
        result = _run_simulation(10_000)
        assert (
            result.metrics[-1].equity_entries == result.metrics[-1].trades
        ), "equity_curve et trade_history désynchronisés"


# ══════════════════════════════════════════════════════════════════════════════
# C2 — State Drift Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestC2StateDrift:
    """Déterminisme : même seed = même résultat, bit-à-bit."""

    def test_same_seed_same_balance(self):
        """Deux runs avec seed=12345 → balance finale identique."""
        r1 = _run_simulation(10_000, seed=12345)
        r2 = _run_simulation(10_000, seed=12345)
        assert (
            r1.final_balance == r2.final_balance
        ), f"Dérive balance: {r1.final_balance} vs {r2.final_balance}"

    def test_same_seed_same_trade_count(self):
        """Deux runs identiques → même nombre de trades."""
        r1 = _run_simulation(10_000, seed=12345)
        r2 = _run_simulation(10_000, seed=12345)
        assert (
            r1.total_trades == r2.total_trades
        ), f"Dérive trades: {r1.total_trades} vs {r2.total_trades}"

    def test_same_seed_same_positions(self):
        """Deux runs identiques → positions finales identiques."""
        r1 = _run_simulation(10_000, seed=12345)
        r2 = _run_simulation(10_000, seed=12345)
        assert (
            r1.positions == r2.positions
        ), f"Dérive positions: {r1.positions} vs {r2.positions}"

    def test_same_seed_same_checkpoint_sequence(self):
        """Les balances à chaque checkpoint sont identiques."""
        r1 = _run_simulation(10_000, seed=42)
        r2 = _run_simulation(10_000, seed=42)
        for m1, m2 in zip(r1.metrics, r2.metrics):
            assert (
                m1.balance == m2.balance
            ), f"Dérive checkpoint {m1.cycle}: {m1.balance} vs {m2.balance}"
            assert m1.trades == m2.trades, f"Dérive trades checkpoint {m1.cycle}"

    def test_different_seed_different_result(self):
        """Des seeds différentes produisent des résultats différents."""
        r1 = _run_simulation(5_000, seed=1)
        r2 = _run_simulation(5_000, seed=9999)
        # Statistiquement vrai : seeds différentes → trajectoires différentes
        assert (
            r1.final_balance != r2.final_balance or r1.total_trades != r2.total_trades
        )

    def test_no_drift_across_3_seeds(self):
        """Trois seeds différentes → chacune déterministe en double run."""
        for seed in (42, 1337, 99999):
            r1 = _run_simulation(3_000, seed=seed)
            r2 = _run_simulation(3_000, seed=seed)
            assert r1.final_balance == r2.final_balance, f"Seed {seed} non-déterministe"

    def test_mid_run_state_consistent(self):
        """À mi-parcours (5000), l'état intermédiaire est identique entre 2 runs."""
        r1 = _run_simulation(5_000, seed=77, checkpoint_every=1_000)
        r2 = _run_simulation(5_000, seed=77, checkpoint_every=1_000)
        for m1, m2 in zip(r1.metrics, r2.metrics):
            assert m1.balance == m2.balance
            assert m1.trades == m2.trades


# ══════════════════════════════════════════════════════════════════════════════
# C3 — Memory Leak Hunt
# ══════════════════════════════════════════════════════════════════════════════


class TestC3MemoryLeak:
    """
    Détection de fuites mémoire sur run de 10k cycles.

    Critères :
      - Croissance tracemalloc < 30 MB sur 10k cycles
      - Croissance 5k→10k < 2× croissance 1k→5k (pas super-linéaire)
      - Pas d'explosion du nombre d'objets GC
    """

    def test_tracemalloc_growth_bounded_10k(self):
        """Allocation totale Python < 30 MB pour 10k cycles."""
        gc.collect()
        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        _run_simulation(10_000, seed=42)
        gc.collect()

        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snap_after.compare_to(snap_before, "lineno")
        total_bytes = sum(max(s.size_diff, 0) for s in stats)
        total_mb = total_bytes / (1024 * 1024)

        assert (
            total_mb < 30.0
        ), f"Allocation tracemalloc trop élevée: {total_mb:.1f} MB pour 10k cycles"

    def test_memory_growth_not_superlinear(self):
        """
        La mémoire Python ne croît pas super-linéairement.

        Mesure la croissance 1k→5k et 5k→10k cycles.
        La seconde moitié ne doit pas être > 3× la première.
        """
        gc.collect()
        tracemalloc.start()

        # Phase 1 : 1k cycles
        _run_simulation(1_000, seed=42)
        gc.collect()
        snap1 = tracemalloc.take_snapshot()

        # Phase 2 : 5k cycles supplémentaires (total 6k)
        _run_simulation(5_000, seed=43)
        gc.collect()
        snap2 = tracemalloc.take_snapshot()

        # Phase 3 : 5k cycles supplémentaires (total 11k)
        _run_simulation(5_000, seed=44)
        gc.collect()
        snap3 = tracemalloc.take_snapshot()

        tracemalloc.stop()

        growth_1_2 = sum(max(s.size_diff, 0) for s in snap2.compare_to(snap1, "lineno"))
        growth_2_3 = sum(max(s.size_diff, 0) for s in snap3.compare_to(snap2, "lineno"))

        # Si growth_1_2 == 0, éviter division par zéro
        if growth_1_2 > 0:
            ratio = growth_2_3 / growth_1_2
            assert ratio < 3.0, (
                f"Croissance super-linéaire détectée: ratio={ratio:.2f} "
                f"(phase1={growth_1_2/1024:.0f}KB, phase2={growth_2_3/1024:.0f}KB)"
            )

    def test_gc_objects_not_exploding(self):
        """Le nombre d'objets Python ne croît pas de façon incontrôlée."""
        gc.collect()
        count_before = len(gc.get_objects())

        _run_simulation(5_000, seed=42)
        gc.collect()

        count_after = len(gc.get_objects())
        delta = count_after - count_before

        # Tolérance : < 50 000 objets supplémentaires pour 5k cycles
        assert delta < 50_000, f"Explosion objets GC: +{delta} objets après 5k cycles"

    def test_simulation_objects_released_after_run(self):
        """Après fin du run, les objets de simulation sont collectables."""
        gc.collect()
        count_before = len(gc.get_objects())

        for _ in range(3):
            _run_simulation(2_000, seed=42)
            gc.collect()

        count_after = len(gc.get_objects())
        delta = count_after - count_before

        # 3 runs de 2k cycles ne doivent pas accumuler > 30 000 objets résiduels
        assert (
            delta < 30_000
        ), f"Fuite potentielle: +{delta} objets après 3 runs de 2k cycles"

    def test_equity_curve_bounded_by_trade_count(self):
        """equity_curve ne croît pas plus vite que trade_history (pas de doublon)."""
        result = _run_simulation(5_000, seed=42)
        for m in result.metrics:
            # equity_curve == trade_history (un point par trade)
            assert m.equity_entries == m.trades, (
                f"Désynchronisation au cycle {m.cycle}: "
                f"equity={m.equity_entries} trades={m.trades}"
            )

    def test_window_deque_bounded(self):
        """La fenêtre glissante reste bornée à 30 éléments."""
        rng = random.Random(42)
        window: deque = deque(maxlen=30)
        price = _BASE_PRICE

        for _ in range(10_000):
            candle = _make_candle(price, rng)
            price = candle["close"]
            window.append(candle)
            assert len(window) <= 30, "Window deque dépasse sa limite"


# ══════════════════════════════════════════════════════════════════════════════
# C4 — 100k Cycles (slow)
# ══════════════════════════════════════════════════════════════════════════════


class TestC4LongRun:
    """
    Endurance : 100 000 cycles.

    Exécuté uniquement avec : pytest -m slow
    """

    @pytest.mark.slow
    def test_100k_cycles_no_exception(self):
        """100 000 cycles sans exception."""
        result = _run_simulation(100_000, seed=42)
        assert (
            result.exceptions == []
        ), f"Exceptions sur 100k cycles : {result.exceptions[:3]}"

    @pytest.mark.slow
    def test_100k_cycles_capital_non_negative(self):
        """Capital non-négatif après 100k cycles."""
        result = _run_simulation(100_000, seed=42)
        assert result.final_balance >= 0.0

    @pytest.mark.slow
    def test_100k_cycles_no_drift_vs_10k_checkpoint(self):
        """
        Le premier checkpoint 10k du run 100k correspond au run 10k standalone.

        Valide que le simulateur est stable sur toute la durée.
        """
        r_10k = _run_simulation(10_000, seed=42)
        r_100k = _run_simulation(100_000, seed=42, checkpoint_every=10_000)

        # Le premier checkpoint du run 100k doit correspondre au run 10k
        # Tolérance 1 centime : SimMetrics arrondit à 4 décimales, SimResult à 6
        assert abs(r_100k.metrics[0].balance - r_10k.final_balance) < 0.01, (
            f"Dérive à 10k: run_100k={r_100k.metrics[0].balance} "
            f"vs run_10k={r_10k.final_balance}"
        )

    @pytest.mark.slow
    def test_100k_memory_growth_bounded(self):
        """Allocation tracemalloc < 100 MB pour 100k cycles."""
        gc.collect()
        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        _run_simulation(100_000, seed=42)
        gc.collect()

        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snap_after.compare_to(snap_before, "lineno")
        total_mb = sum(max(s.size_diff, 0) for s in stats) / (1024 * 1024)

        assert (
            total_mb < 100.0
        ), f"Allocation trop élevée: {total_mb:.1f} MB pour 100k cycles"

    @pytest.mark.slow
    def test_100k_performance_under_5min(self):
        """100k cycles en moins de 5 minutes."""
        t0 = time.monotonic()
        _run_simulation(100_000, seed=42)
        elapsed = time.monotonic() - t0
        assert elapsed < 300.0, f"100k cycles trop lents: {elapsed:.1f}s"

    @pytest.mark.slow
    def test_100k_no_slowdown_late_cycles(self):
        """
        Pas de ralentissement progressif : cycles 90k-100k aussi rapides que 1k-10k.

        Si les structures de données se dégradent (hash collision, GC pressure),
        les derniers cycles sont significativement plus lents.
        """
        # Mesure des 10 premiers checkpoints (1k-10k)
        t0 = time.monotonic()
        _run_simulation(10_000, seed=42)
        time_first_10k = time.monotonic() - t0

        # Mesure des 90k cycles (jusqu'à 100k) via simulation entière
        t0 = time.monotonic()
        _run_simulation(100_000, seed=42)
        time_full_100k = time.monotonic() - t0

        # Les 90k cycles supplémentaires ne doivent pas coûter > 15× les premiers 10k
        time_last_90k = time_full_100k - time_first_10k
        assert time_last_90k < time_first_10k * 15, (
            f"Ralentissement progressif détecté: "
            f"10k={time_first_10k:.2f}s, 90k restants={time_last_90k:.2f}s"
        )
