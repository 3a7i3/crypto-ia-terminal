"""
monitoring/metrics.py — Metriques en memoire, thread-safe.

Trois types :
  Counter   : monotonique, inc(n=1)
  Gauge     : valeur courante, set/inc/dec
  Histogram : distribution de valeurs, percentiles p50/p95/p99

Usage :
    registry = MetricsRegistry()

    trades = registry.counter("trades_processed")
    trades.inc()

    latency = registry.histogram("fill_latency_ms", buckets=[10, 50, 100, 500])
    latency.observe(75.0)
    print(latency.p95)

    snap = registry.snapshot()  # dict JSON-serialisable
"""

from __future__ import annotations

import math
import statistics
import threading
from typing import Optional

# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------


class Counter:
    """Compteur monotonique thread-safe."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._value: int = 0
        self._lock = threading.Lock()

    def inc(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError(f"Counter.inc requires n >= 0, got {n}")
        with self._lock:
            self._value += n

    @property
    def value(self) -> int:
        return self._value

    def snapshot(self) -> dict:
        return {"type": "counter", "name": self.name, "value": self._value}


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------


class Gauge:
    """Jauge a valeur flottante thread-safe (peut monter et descendre)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._value: float = 0.0
        self._lock = threading.Lock()

    def set(self, v: float) -> None:
        with self._lock:
            self._value = v

    def inc(self, v: float = 1.0) -> None:
        with self._lock:
            self._value += v

    def dec(self, v: float = 1.0) -> None:
        with self._lock:
            self._value -= v

    @property
    def value(self) -> float:
        return self._value

    def snapshot(self) -> dict:
        return {"type": "gauge", "name": self.name, "value": round(self._value, 6)}


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


class Histogram:
    """
    Histogramme thread-safe.
    Stocke toutes les observations en memoire — adapte aux volumes < 1M points.
    """

    def __init__(self, name: str, buckets: Optional[list[float]] = None) -> None:
        self.name = name
        self._buckets = sorted(buckets or [1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0])
        self._observations: list[float] = []
        self._lock = threading.Lock()

    def observe(self, v: float) -> None:
        with self._lock:
            self._observations.append(v)

    def _percentile(self, p: float) -> float:
        data = sorted(self._observations)
        n = len(data)
        if n == 0:
            return 0.0
        idx = p / 100.0 * (n - 1)
        lo = int(math.floor(idx))
        hi = min(lo + 1, n - 1)
        return data[lo] + (idx - lo) * (data[hi] - data[lo])

    @property
    def count(self) -> int:
        return len(self._observations)

    @property
    def mean(self) -> float:
        with self._lock:
            return statistics.mean(self._observations) if self._observations else 0.0

    @property
    def p50(self) -> float:
        with self._lock:
            return self._percentile(50)

    @property
    def p95(self) -> float:
        with self._lock:
            return self._percentile(95)

    @property
    def p99(self) -> float:
        with self._lock:
            return self._percentile(99)

    @property
    def maximum(self) -> float:
        with self._lock:
            return max(self._observations) if self._observations else 0.0

    def bucket_counts(self) -> dict[str, int]:
        """Nombre d'observations dans chaque bucket (style Prometheus)."""
        with self._lock:
            result = {}
            for b in self._buckets:
                result[f"le_{b}"] = sum(1 for x in self._observations if x <= b)
            result["le_inf"] = len(self._observations)
        return result

    def snapshot(self) -> dict:
        with self._lock:
            obs = self._observations
            mean = statistics.mean(obs) if obs else 0.0
            maximum = max(obs) if obs else 0.0
            return {
                "type": "histogram",
                "name": self.name,
                "count": len(obs),
                "mean": round(mean, 4),
                "p50": round(self._percentile(50), 4),
                "p95": round(self._percentile(95), 4),
                "p99": round(self._percentile(99), 4),
                "max": round(maximum, 4),
            }


# ---------------------------------------------------------------------------
# MetricsRegistry
# ---------------------------------------------------------------------------


class MetricsRegistry:
    """
    Registre central thread-safe de toutes les metriques.

    Utilisation idempotente : appeler counter("name") deux fois retourne
    le meme objet — pas de duplication.
    """

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name)
            return self._counters[name]

    def gauge(self, name: str) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name)
            return self._gauges[name]

    def histogram(self, name: str, buckets: Optional[list[float]] = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, buckets)
            return self._histograms[name]

    def snapshot(self) -> dict:
        """Retourne toutes les metriques en dict JSON-serialisable."""
        return {
            "counters": {n: m.snapshot() for n, m in self._counters.items()},
            "gauges": {n: m.snapshot() for n, m in self._gauges.items()},
            "histograms": {n: m.snapshot() for n, m in self._histograms.items()},
        }

    def reset(self) -> None:
        """Vide toutes les metriques (utile entre tests)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
