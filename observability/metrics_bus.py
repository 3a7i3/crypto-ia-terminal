"""
Metrics Bus — event-driven metrics collection.

Modules push metrics; consumers subscribe to streams or pull snapshots.
No external dependency (no Prometheus, no InfluxDB) — pure Python ring buffer.

Usage:
    from observability.metrics_bus import metrics_bus

    # Push
    metrics_bus.record("execution_engine", "order_latency_ms", 14.2, tags={"symbol": "BTCUSDT"})
    metrics_bus.increment("signal_engine", "signals_generated")
    metrics_bus.gauge("risk_engine", "portfolio_exposure_pct", 42.7)

    # Read
    metrics_bus.latest("execution_engine", "order_latency_ms")
    metrics_bus.summary("execution_engine", "order_latency_ms", window_sec=300)
    metrics_bus.snapshot()
"""

from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class MetricPoint:
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSummary:
    module: str
    name: str
    count: int
    latest: float
    mean: float
    p50: float
    p95: float
    p99: float
    min: float
    max: float
    window_sec: float


class MetricSeries:
    """Ring buffer for a single metric time series."""

    MAX_POINTS = 10_000

    def __init__(self, module: str, name: str) -> None:
        self.module = module
        self.name = name
        self._points: deque[MetricPoint] = deque(maxlen=self.MAX_POINTS)
        self._lock = threading.Lock()

    def push(self, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            self._points.append(MetricPoint(value=value, tags=tags or {}))

    def latest(self) -> Optional[float]:
        with self._lock:
            return self._points[-1].value if self._points else None

    def window(self, seconds: float) -> List[MetricPoint]:
        cutoff = time.time() - seconds
        with self._lock:
            return [p for p in self._points if p.timestamp >= cutoff]

    def summary(self, window_sec: float = 300.0) -> MetricSummary:
        pts = self.window(window_sec)
        vals = [p.value for p in pts] if pts else [0.0]
        sorted_vals = sorted(vals)
        n = len(sorted_vals)

        def percentile(p: float) -> float:
            idx = max(0, int(p / 100 * n) - 1)
            return sorted_vals[idx]

        return MetricSummary(
            module=self.module,
            name=self.name,
            count=n,
            latest=sorted_vals[-1],
            mean=statistics.mean(vals),
            p50=percentile(50),
            p95=percentile(95),
            p99=percentile(99),
            min=sorted_vals[0],
            max=sorted_vals[-1],
            window_sec=window_sec,
        )


class MetricsBus:
    """
    Central metrics collector. Thread-safe.
    All modules push to it; dashboards and health checks pull from it.
    """

    def __init__(self) -> None:
        # (module, metric_name) -> MetricSeries
        self._series: Dict[Tuple[str, str], MetricSeries] = {}
        # module -> metric_name -> latest float (fast path)
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(dict)
        # module -> metric_name -> int (monotonic counters)
        self._counters: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._lock = threading.Lock()
        self._listeners: List[Callable[[str, str, float], None]] = []

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def record(
        self,
        module: str,
        metric: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a data point (latency, PnL, score, …)."""
        series = self._get_or_create(module, metric)
        series.push(value, tags)
        with self._lock:
            self._gauges[module][metric] = value
        self._notify(module, metric, value)

    def gauge(self, module: str, metric: str, value: float) -> None:
        """Set a gauge (current value, no history needed)."""
        with self._lock:
            self._gauges[module][metric] = value
        self._notify(module, metric, value)

    def increment(self, module: str, metric: str, delta: int = 1) -> None:
        """Increment a counter."""
        with self._lock:
            self._counters[module][metric] += delta

    def decrement(self, module: str, metric: str, delta: int = 1) -> None:
        with self._lock:
            self._counters[module][metric] = max(
                0, self._counters[module][metric] - delta
            )

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def latest(self, module: str, metric: str) -> Optional[float]:
        with self._lock:
            return self._gauges.get(module, {}).get(metric)

    def counter(self, module: str, metric: str) -> int:
        with self._lock:
            return self._counters.get(module, {}).get(metric, 0)

    def summary(
        self, module: str, metric: str, window_sec: float = 300.0
    ) -> Optional[MetricSummary]:
        series = self._series.get((module, metric))
        return series.summary(window_sec) if series else None

    def all_gauges(self, module: str) -> Dict[str, float]:
        with self._lock:
            return dict(self._gauges.get(module, {}))

    def all_counters(self, module: str) -> Dict[str, int]:
        with self._lock:
            return dict(self._counters.get(module, {}))

    def modules(self) -> List[str]:
        with self._lock:
            return list({m for m, _ in self._series.keys()} | set(self._gauges.keys()))

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[str, str, float], None]) -> None:
        """Called on every metric push: callback(module, metric_name, value)."""
        self._listeners.append(callback)

    def _notify(self, module: str, metric: str, value: float) -> None:
        for cb in self._listeners:
            try:
                cb(module, metric, value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            gauges = {m: dict(v) for m, v in self._gauges.items()}
            counters = {m: dict(v) for m, v in self._counters.items()}
        return {
            "timestamp": time.time(),
            "modules_reporting": self.modules(),
            "gauges": gauges,
            "counters": counters,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create(self, module: str, metric: str) -> MetricSeries:
        key = (module, metric)
        with self._lock:
            if key not in self._series:
                self._series[key] = MetricSeries(module, metric)
            return self._series[key]


# Singleton
metrics_bus = MetricsBus()
