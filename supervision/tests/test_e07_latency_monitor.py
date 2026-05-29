"""
supervision/tests/test_e07_latency_monitor.py — E-07 LatencyMonitor Permanent Baseline

Tests de certification :
  - Baseline établie sur 50+ échantillons
  - Alerte si déviation > 3σ
  - Historique 30 jours (rolling window)
  - Persistance JSON
  - p50/p95/p99 calculés correctement

Total : 12 tests
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from supervision.latency_baseline_monitor import (
    KNOWN_OPERATIONS,
    LatencyBaseline,
    LatencyBaselineMonitor,
    _percentile,
)


class TestBaselineEstablishment:
    def test_not_established_before_min_samples(self):
        """Baseline non établie avant 50 échantillons."""
        baseline = LatencyBaseline(min_samples=50)
        for _ in range(49):
            baseline.record("ohlcv_fetch", 100.0)
        assert not baseline.is_baseline_established("ohlcv_fetch")

    def test_established_after_min_samples(self):
        """Baseline établie après 50 échantillons."""
        baseline = LatencyBaseline(min_samples=50)
        for _ in range(50):
            baseline.record("ohlcv_fetch", 100.0)
        assert baseline.is_baseline_established("ohlcv_fetch")

    def test_known_operations_supported(self):
        """Les 4 opérations connues sont supportées."""
        baseline = LatencyBaseline()
        for op in KNOWN_OPERATIONS:
            baseline.record(op, 100.0)
        for op in KNOWN_OPERATIONS:
            assert op in baseline.operations()

    def test_unknown_operation_auto_registered(self):
        """Une opération inconnue est enregistrée automatiquement."""
        baseline = LatencyBaseline()
        baseline.record("custom_op", 200.0)
        assert "custom_op" in baseline.operations()


class TestAnomalyDetection:
    def _established_baseline(self, mean=100.0, n=60) -> LatencyBaseline:
        baseline = LatencyBaseline(min_samples=50)
        for _ in range(n):
            baseline.record("ohlcv_fetch", mean + (n % 5 - 2))  # légère variance
        return baseline

    def test_normal_latency_not_anomaly(self):
        """Latence normale (proche de la moyenne) → pas d'anomalie."""
        baseline = LatencyBaseline(min_samples=50)
        for _ in range(60):
            baseline.record("ohlcv_fetch", 100.0)
        # 102ms ~ 1σ de 100ms avec faible variance
        assert not baseline.is_anomaly("ohlcv_fetch", 102.0)

    def test_extreme_latency_is_anomaly(self):
        """Latence extrême (10x la moyenne) → anomalie 3σ."""
        baseline = LatencyBaseline(min_samples=50)
        for _ in range(60):
            baseline.record("ohlcv_fetch", 100.0)
        # 1000ms est très loin de la baseline 100ms
        assert baseline.is_anomaly("ohlcv_fetch", 1000.0, sigma_threshold=3.0)

    def test_no_anomaly_before_baseline_established(self):
        """Pas d'anomalie si baseline pas encore établie."""
        baseline = LatencyBaseline(min_samples=50)
        for _ in range(10):
            baseline.record("ohlcv_fetch", 100.0)
        assert not baseline.is_anomaly("ohlcv_fetch", 99999.0)

    def test_monitor_returns_anomaly_object(self):
        """LatencyBaselineMonitor.on_latency() retourne une LatencyAnomaly."""
        alerted = []
        monitor = LatencyBaselineMonitor(
            alert_fn=lambda a: alerted.append(a),
        )
        for _ in range(60):
            monitor.on_latency("ohlcv_fetch", 100.0)
        anomaly = monitor.on_latency("ohlcv_fetch", 5000.0)
        assert anomaly is not None
        assert anomaly.operation == "ohlcv_fetch"
        assert anomaly.deviation_sigma > 3.0
        assert len(alerted) >= 1


class TestStatistics:
    def test_stats_computed_correctly(self):
        """stats() calcule mean, std, p50, p95, p99."""
        baseline = LatencyBaseline(min_samples=10)
        values = [float(x) for x in range(10, 110, 10)]  # 10, 20, ..., 100
        for v in values:
            baseline.record("feature_calc", v)
        stats = baseline.stats("feature_calc")
        assert stats is not None
        assert abs(stats.mean_ms - 55.0) < 1.0
        assert stats.min_ms == 10.0
        assert stats.max_ms == 100.0
        assert stats.p50_ms > 0
        assert stats.p95_ms >= stats.p50_ms
        assert stats.p99_ms >= stats.p95_ms

    def test_percentile_utility(self):
        """_percentile() calcule correctement les percentiles."""
        values = sorted(range(1, 101))  # 1..100
        assert _percentile(values, 50) == pytest.approx(50.5, abs=1.0)
        assert _percentile(values, 95) == pytest.approx(95.5, abs=1.0)
        assert _percentile(values, 99) == pytest.approx(99.5, abs=1.0)

    def test_baseline_age_hours(self):
        """baseline_age_hours() retourne l'âge en heures."""
        baseline = LatencyBaseline(min_samples=10)
        for _ in range(10):
            baseline.record("lm_studio_call", 500.0)
        age = baseline.baseline_age_hours("lm_studio_call")
        # Juste établie → age < 1h
        assert age < 1.0


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        """save() + load() préserve les échantillons."""
        path = tmp_path / "baseline.json"
        baseline1 = LatencyBaseline(min_samples=50)
        for _ in range(55):
            baseline1.record("ohlcv_fetch", 150.0)
        baseline1.save(path)
        assert path.exists()

        baseline2 = LatencyBaseline(min_samples=50)
        baseline2.load(path)
        assert baseline2.is_baseline_established("ohlcv_fetch")

    def test_export_returns_dict(self):
        """export() retourne un dict avec les opérations."""
        baseline = LatencyBaseline()
        for _ in range(5):
            baseline.record("order_exec", 50.0)
        data = baseline.export()
        assert "operations" in data
        assert "order_exec" in data["operations"]
        assert "exported_at" in data

    def test_load_missing_file_silently(self, tmp_path):
        """Chargement d'un fichier absent → pas d'exception."""
        baseline = LatencyBaseline()
        baseline.load(tmp_path / "nonexistent.json")  # ne doit pas crasher
