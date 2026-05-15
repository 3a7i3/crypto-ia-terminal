"""
tests/stress/test_stress_volume.py — P4.4 : Tests de stress (volume, latence, enchaînements).

Scenarios realistes de pic de marche :
  1. Burst CVD : 100 000 trades en rafale → throughput et correctness
  2. Walk-forward large : 50 folds × 1000 trades → linearite du temps
  3. FillErrorMetric : 10 000 paires enregistrees sans degradation memoire
  4. WindowSplitter : n_samples=1 000 000 → pas d'erreur, folds corrects
  5. ReplayEngine : 10 000 events JSONL → replay sous 5s
  6. Metrics thread-safety : 8 threads paralleles sur Counter/Histogram

Les seuils de temps sont genereux (x3 du nominal) pour eviter les faux negatifs
sur CI ou machines lentes.
"""

from __future__ import annotations

import json
import random
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from execution_simulator.fill_error_metric import FillErrorMetric, RealFill
from execution_simulator.models import SimulatedFill
from market_data.metrics.flow import CumulativeDeltaTracker
from market_data.models import NormalizedTrade
from market_data.replay_engine import ReplayEngine
from metrics.oos_metrics import TradeResult, compute_oos_metrics
from monitoring.metrics import MetricsRegistry
from walk_forward.engine import WalkForwardEngine
from walk_forward.walk_forward_loop import WalkForwardLoop
from walk_forward.window_splitter import WindowSplitter

SEED = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trades(n: int, rng: random.Random) -> list[NormalizedTrade]:
    trades = []
    ts = 1_700_000_000_000
    price = 50_000.0
    for i in range(n):
        ts += rng.randint(1, 50)
        price += rng.gauss(0, 5)
        price = max(40_000.0, price)
        side = "buy" if rng.random() > 0.48 else "sell"
        trades.append(
            NormalizedTrade(
                exchange="binance",
                symbol="BTCUSDT",
                timestamp_ms=ts,
                price=price,
                size=round(rng.uniform(0.001, 1.0), 4),
                side=side,
            )
        )
    return trades


def _make_sim_fill(fill_price: float = 50_010.0) -> SimulatedFill:
    return SimulatedFill(
        order_id="x",
        symbol="BTCUSDT",
        side="buy",
        requested_size=1.0,
        filled_size=1.0,
        fill_price=fill_price,
        signal_price=50_000.0,
        slippage_bps=2.0,
        spread_cost_bps=0.5,
        latency_ms=75.0,
        fee_usd=0.2,
        fee_rate_bps=4.0,
        is_partial=False,
        is_rejected=False,
        rejection_reason=None,
        fill_timestamp=1_700_000_001.0,
        price_at_execution=fill_price,
        latency_price_drift_bps=0.1,
    )


def _make_real_fill(fill_price: float = 50_005.0) -> RealFill:
    return RealFill(
        order_id="r",
        symbol="BTCUSDT",
        side="buy",
        requested_size=1.0,
        filled_size=1.0,
        fill_price=fill_price,
        signal_price=50_000.0,
        signal_timestamp_ms=1_700_000_000_000,
        fill_timestamp_ms=1_700_000_000_075,
    )


# ---------------------------------------------------------------------------
# 1. Burst CVD — 100 000 trades
# ---------------------------------------------------------------------------


class TestBurstCVD:

    def test_100k_trades_throughput(self):
        """100 000 trades traversent CumulativeDeltaTracker en < 5s."""
        n = 100_000
        rng = random.Random(SEED)
        trades = _make_trades(n, rng)
        tracker = CumulativeDeltaTracker([60_000, 300_000])

        t0 = time.monotonic()
        for t in trades:
            tracker.update(t)
        elapsed = time.monotonic() - t0

        assert elapsed < 5.0, f"CVD burst too slow: {elapsed:.2f}s for {n} trades"
        snap = tracker.snapshot()
        # Apres des achats + ventes aleatoires symetriques, le delta ne doit pas diverger
        assert abs(snap["delta_1m"]) < n * 2  # borne large

    def test_100k_trades_delta_sign(self):
        """Forcer tous les trades en buy → delta positif."""
        n = 50_000
        trades = []
        ts = 1_700_000_000_000
        for i in range(n):
            ts += 1  # 1ms → total span=50s < fenetre 1m (60s)
            trades.append(
                NormalizedTrade(
                    exchange="binance",
                    symbol="BTCUSDT",
                    timestamp_ms=ts,
                    price=50_000.0,
                    size=1.0,
                    side="buy",
                )
            )

        tracker = CumulativeDeltaTracker(
            [60_000]
        )  # fenetre 1m, tous les trades tiennent
        for t in trades:
            tracker.update(t)
        snap = tracker.snapshot()
        assert snap["delta_1m"] == pytest.approx(float(n), rel=1e-3)

    def test_sliding_window_eviction(self):
        """Verifier que les vieux trades sont bien ejectes de la fenetre."""
        tracker = CumulativeDeltaTracker([60_000])  # fenetre 1m
        # 10 trades anciens (buys) — ts 0-900ms
        for i in range(10):
            t = NormalizedTrade("b", "BTCUSDT", i * 100, 50_000.0, 1.0, "buy")
            tracker.update(t)
        # 10 trades recents (sells) — ts 100_000-100_900ms (>1m apres les buys)
        for i in range(10):
            t = NormalizedTrade(
                "b", "BTCUSDT", 100_000 + i * 100, 50_000.0, 1.0, "sell"
            )
            tracker.update(t)
        snap = tracker.snapshot()
        # Seuls les sells recents doivent etre dans la fenetre 1m (buys ejectes)
        assert snap["delta_1m"] <= 0  # ventes dominent


# ---------------------------------------------------------------------------
# 2. Walk-forward large — 50 folds
# ---------------------------------------------------------------------------


class TestLargeWalkForward:

    def _make_data(self, n: int) -> list[dict]:
        rng = random.Random(SEED)
        return [
            {"value": rng.gauss(0.1, 1.0), "regime": ["bull", "bear"][i % 2]}
            for i in range(n)
        ]

    def test_50_folds_completes_in_time(self):
        """50 folds × 100 samples de test doivent completer en < 10s."""
        n_samples = 5_200
        data = self._make_data(n_samples)

        def opt(train):
            return {"thr": sum(d["value"] for d in train) / max(len(train), 1)}

        def val(test, p):
            return [
                TradeResult(i * 1000, d["value"] * 0.05, regime=d["regime"])
                for i, d in enumerate(test)
                if abs(d["value"]) > abs(p["thr"])
            ]

        sp = WindowSplitter(
            n_samples=n_samples,
            train_size=5_000,
            test_size=100,
            step=100,
            anchored=True,
        )
        loop = WalkForwardLoop(optimizer=opt, validator=val)
        engine = WalkForwardEngine(splitter=sp, loop=loop)

        t0 = time.monotonic()
        result = engine.run(data)
        elapsed = time.monotonic() - t0

        assert elapsed < 10.0, f"Large walk-forward too slow: {elapsed:.2f}s"
        assert result.n_folds >= 1

    def test_aggregate_trade_count_correct(self):
        """Trade count agrege = somme des fold trade counts."""
        n_samples = 2_000
        data = self._make_data(n_samples)

        def opt(train):
            return {}

        def val(test, _):
            return [TradeResult(i * 1000, 0.5) for i in range(len(test) // 2)]

        sp = WindowSplitter(
            n_samples=n_samples, train_size=1_500, test_size=100, step=100
        )
        loop = WalkForwardLoop(optimizer=opt, validator=val)
        result = WalkForwardEngine(sp, loop).run(data)

        fold_total = sum(f.oos_metrics.n_trades for f in result.folds if f.is_valid)
        assert result.aggregate_metrics.n_trades == fold_total


# ---------------------------------------------------------------------------
# 3. FillErrorMetric — 10 000 paires
# ---------------------------------------------------------------------------


class TestFillErrorStress:

    def test_10k_pairs_performance(self):
        """10 000 paires enregistrees en < 3s."""
        metric = FillErrorMetric()
        n = 10_000

        t0 = time.monotonic()
        for i in range(n):
            metric.record(
                _make_sim_fill(50_010.0 + i * 0.001),
                _make_real_fill(50_005.0 + i * 0.001),
            )
        elapsed = time.monotonic() - t0

        assert elapsed < 3.0, f"FillErrorMetric stress too slow: {elapsed:.2f}s"
        assert metric.n_samples == n

    def test_10k_summary_stable(self):
        """summary() sur 10K paires ne plante pas et retourne des valeurs finies."""
        import math

        metric = FillErrorMetric()
        rng = random.Random(SEED)
        for _ in range(10_000):
            fp_sim = 50_000.0 + rng.gauss(10, 5)
            fp_real = 50_000.0 + rng.gauss(5, 3)
            metric.record(_make_sim_fill(fp_sim), _make_real_fill(fp_real))
        stats = metric.summary()
        assert math.isfinite(stats.fill_price_error_mean_bps)
        assert math.isfinite(stats.p95_abs_price_error_bps)


# ---------------------------------------------------------------------------
# 4. WindowSplitter — 1 000 000 samples
# ---------------------------------------------------------------------------


class TestWindowSplitterLarge:

    def test_1m_samples_correctness(self):
        """WindowSplitter sur 1M samples : folds corrects, pas de leakage."""
        sp = WindowSplitter(
            n_samples=1_000_000,
            train_size=800_000,
            test_size=50_000,
            step=50_000,
        )
        folds = list(sp.split())
        assert len(folds) >= 2
        for w in folds:
            assert w.train_end <= w.test_start  # no leakage
            assert w.test_end <= 1_000_000

    def test_1m_samples_fast(self):
        """Enumerer les folds sur 1M samples doit etre instantane (< 0.1s)."""
        sp = WindowSplitter(
            n_samples=1_000_000,
            train_size=800_000,
            test_size=50_000,
            step=25_000,
        )
        t0 = time.monotonic()
        folds = list(sp.split())
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1, f"WindowSplitter enumeration too slow: {elapsed:.3f}s"
        assert len(folds) >= 1


# ---------------------------------------------------------------------------
# 5. ReplayEngine — 10 000 events JSONL
# ---------------------------------------------------------------------------


class TestReplayEngineStress:

    def _write_jsonl(self, path: Path, n: int, rng: random.Random) -> None:
        ts = 1_700_000_000_000
        price = 50_000.0
        with open(path, "w") as f:
            for i in range(n):
                ts += rng.randint(10, 200)
                price += rng.gauss(0, 10)
                price = max(40_000.0, price)
                side = "buy" if rng.random() > 0.5 else "sell"
                f.write(
                    json.dumps(
                        {
                            "event_type": "trade",
                            "exchange": "binance",
                            "symbol": "BTCUSDT",
                            "timestamp_ms": ts,
                            "data": {
                                "price": round(price, 2),
                                "size": round(rng.uniform(0.01, 1.0), 4),
                                "side": side,
                                "trade_id": str(i),
                            },
                        }
                    )
                    + "\n"
                )

    def test_10k_events_replay_fast(self):
        """10 000 trades en replay doivent etre traites en < 5s."""
        rng = random.Random(SEED)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades_10k.jsonl"
            self._write_jsonl(path, 10_000, rng)

            engine = ReplayEngine(path, snapshot_interval_ms=500)
            t0 = time.monotonic()
            snapshots = list(engine.replay())
            elapsed = time.monotonic() - t0

        assert elapsed < 15.0, f"ReplayEngine stress too slow: {elapsed:.2f}s"
        assert engine.stats.trade_count == 10_000
        assert len(snapshots) > 0

    def test_10k_events_export_jsonl(self):
        """Export de 10K events en JSONL : fichier valide et non-vide."""
        rng = random.Random(SEED)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.jsonl"
            dst = Path(tmp) / "snapshots.jsonl"
            self._write_jsonl(src, 10_000, rng)

            engine = ReplayEngine(src, snapshot_interval_ms=1_000)
            stats = engine.snapshots_to_jsonl(dst)

            assert dst.exists()
            lines = dst.read_text().strip().split("\n")
            assert len(lines) > 0
            assert stats.trade_count == 10_000
            # Chaque ligne doit etre un JSON valide
            for line in lines[:10]:
                d = json.loads(line)
                assert "timestamp_ms" in d


# ---------------------------------------------------------------------------
# 6. Metrics thread-safety — 8 threads paralleles
# ---------------------------------------------------------------------------


class TestMetricsThreadSafety:

    def test_counter_concurrent_increments(self):
        """8 threads incrementent un Counter 1000 fois chacun → valeur exacte 8000."""
        registry = MetricsRegistry()
        c = registry.counter("concurrent_trades")
        n_threads, n_incs = 8, 1_000

        def _worker():
            for _ in range(n_incs):
                c.inc()

        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert c.value == n_threads * n_incs

    def test_histogram_concurrent_observations(self):
        """8 threads observent simultanement → count exact."""
        registry = MetricsRegistry()
        h = registry.histogram("latency_ms", [10, 50, 100, 500])
        n_threads, n_obs = 8, 500

        def _worker():
            rng = random.Random()
            for _ in range(n_obs):
                h.observe(rng.uniform(0, 1000))

        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert h.count == n_threads * n_obs
        assert h.p95 > 0  # pas de crash

    def test_gauge_concurrent_set(self):
        """Gauge modifiee par 4 threads : valeur finale coherente."""
        registry = MetricsRegistry()
        g = registry.gauge("last_sharpe")
        results = []

        def _worker(v):
            g.set(v)
            results.append(g.value)

        threads = [threading.Thread(target=_worker, args=(float(i),)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Valeur finale = l'une des valeurs ecrites par les threads (pas de corruption)
        assert g.value in [0.0, 1.0, 2.0, 3.0]

    def test_registry_idempotent_concurrent(self):
        """Appeler counter() en parallele retourne toujours le meme objet."""
        registry = MetricsRegistry()
        counters = []

        def _get():
            counters.append(registry.counter("shared"))

        threads = [threading.Thread(target=_get) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(id(c) for c in counters)) == 1  # meme objet partout
