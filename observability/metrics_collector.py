"""
metrics_collector.py — Collecte holistique des métriques de production (P12-B).

Agrège les métriques système, trading et fiabilité en un snapshot cohérent
écrit en JSONL toutes les N secondes.

Métriques collectées :
  Performance  : cycle_duration_ms, decision_latency_ms, execution_latency_ms,
                 reconciliation_latency_ms
  Système      : memory_mb, cpu_percent
  Trading      : capital, equity, drawdown_pct, open_positions
  Fiabilité    : error_rate, exception_count, reconciliation_failures, boot_gate_cleared

Usage :
    collector = MetricsCollector(capital_fn=lambda: pm.capital)
    with collector.measure_cycle():
        run_one_cycle()
    collector.record_exception()
    snapshot = collector.snapshot()
    collector.flush_to_jsonl(path)
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from observability.json_logger import get_logger
from observability.metrics_bus import metrics_bus

_log = get_logger("observability.metrics_collector")

_DEFAULT_METRICS_PATH = Path(
    os.getenv("P12_METRICS_PATH", "cache/startup/metrics.jsonl")
)
_DEFAULT_WINDOW_S = 300.0  # 5 min pour les moyennes mobiles


@dataclass
class MetricsSnapshot:
    ts: float = field(default_factory=time.time)

    # ── Performance ───────────────────────────────────────────────────────────
    cycle_duration_ms: float = 0.0
    decision_latency_ms: float = 0.0
    execution_latency_ms: float = 0.0
    reconciliation_latency_ms: float = 0.0

    # ── Système ───────────────────────────────────────────────────────────────
    memory_mb: float = 0.0
    cpu_percent: float = 0.0

    # ── Trading ───────────────────────────────────────────────────────────────
    capital: float = 0.0
    equity: float = 0.0
    drawdown_pct: float = 0.0
    open_positions: int = 0

    # ── Fiabilité ─────────────────────────────────────────────────────────────
    error_rate: float = 0.0  # erreurs / minute (5 min glissantes)
    exception_count: int = 0
    reconciliation_failures: int = 0
    boot_gate_cleared: bool = False

    # ── Dérivé ────────────────────────────────────────────────────────────────
    health_score: float = 100.0  # calculé par HealthScore (injecté après)

    def to_dict(self) -> dict:
        return asdict(self)


class MetricsCollector:
    """
    Collecteur de métriques de production.

    Fonctionne via :
      - context managers (measure_cycle, measure_decision, etc.)
      - callbacks injectés (capital_fn, equity_fn, positions_fn)
      - compteurs manuels (record_exception, record_reconciliation_failure)
    """

    def __init__(
        self,
        capital_fn: Optional[Callable[[], float]] = None,
        equity_fn: Optional[Callable[[], float]] = None,
        positions_fn: Optional[Callable[[], int]] = None,
        initial_capital: float = 0.0,
        window_s: float = _DEFAULT_WINDOW_S,
    ) -> None:
        self._capital_fn = capital_fn
        self._equity_fn = equity_fn
        self._positions_fn = positions_fn
        self._initial_capital = initial_capital
        self._window_s = window_s

        # Compteurs
        self._exception_count: int = 0
        self._reconciliation_failures: int = 0
        self._boot_gate_cleared: bool = False

        # Timestamps d'erreurs (pour error_rate)
        self._error_ts: deque[float] = deque(maxlen=10_000)

        # Dernières latences mesurées
        self._last_cycle_ms: float = 0.0
        self._last_decision_ms: float = 0.0
        self._last_execution_ms: float = 0.0
        self._last_reconciliation_ms: float = 0.0

        # High-watermark equity pour drawdown
        self._peak_equity: float = initial_capital

        self._lock = threading.Lock()

    # ── Context managers ──────────────────────────────────────────────────────

    @contextmanager
    def measure_cycle(self):
        """Mesure la durée totale d'un cycle advisor."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            ms = (time.monotonic() - t0) * 1000
            with self._lock:
                self._last_cycle_ms = ms
            metrics_bus.record("collector", "cycle_duration_ms", ms)

    @contextmanager
    def measure_decision(self):
        """Mesure la latence de décision (signal → order)."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            ms = (time.monotonic() - t0) * 1000
            with self._lock:
                self._last_decision_ms = ms
            metrics_bus.record("collector", "decision_latency_ms", ms)

    @contextmanager
    def measure_execution(self):
        """Mesure la latence d'exécution (order → exchange ack)."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            ms = (time.monotonic() - t0) * 1000
            with self._lock:
                self._last_execution_ms = ms
            metrics_bus.record("collector", "execution_latency_ms", ms)

    @contextmanager
    def measure_reconciliation(self):
        """Mesure la latence de réconciliation."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            ms = (time.monotonic() - t0) * 1000
            with self._lock:
                self._last_reconciliation_ms = ms
            metrics_bus.record("collector", "reconciliation_latency_ms", ms)

    # ── Compteurs manuels ────────────────────────────────────────────────────

    def record_exception(self, exc: Optional[Exception] = None) -> None:
        with self._lock:
            self._exception_count += 1
            self._error_ts.append(time.time())
        metrics_bus.increment("collector", "exception_count")
        if exc:
            _log.warning("[MetricsCollector] Exception enregistrée: %s", exc)

    def record_reconciliation_failure(self) -> None:
        with self._lock:
            self._reconciliation_failures += 1
            self._error_ts.append(time.time())
        metrics_bus.increment("collector", "reconciliation_failures")
        _log.warning("[MetricsCollector] Reconciliation failure")

    def set_boot_gate_cleared(self, cleared: bool) -> None:
        with self._lock:
            self._boot_gate_cleared = cleared
        metrics_bus.gauge("collector", "boot_gate_cleared", float(cleared))

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> MetricsSnapshot:
        """Prend un snapshot cohérent de toutes les métriques."""
        with self._lock:
            capital = self._capital_fn() if self._capital_fn else 0.0
            equity = self._equity_fn() if self._equity_fn else capital
            positions = self._positions_fn() if self._positions_fn else 0

            # Drawdown
            if equity > self._peak_equity:
                self._peak_equity = equity
            drawdown_pct = 0.0
            if self._peak_equity > 0:
                drawdown_pct = max(
                    0.0, (self._peak_equity - equity) / self._peak_equity * 100
                )

            # Error rate (erreurs / minute sur fenêtre glissante)
            now = time.time()
            cutoff = now - self._window_s
            recent_errors = sum(1 for t in self._error_ts if t >= cutoff)
            error_rate = recent_errors / (self._window_s / 60.0)

            snap = MetricsSnapshot(
                ts=now,
                cycle_duration_ms=self._last_cycle_ms,
                decision_latency_ms=self._last_decision_ms,
                execution_latency_ms=self._last_execution_ms,
                reconciliation_latency_ms=self._last_reconciliation_ms,
                memory_mb=_get_memory_mb(),
                cpu_percent=_get_cpu_percent(),
                capital=round(capital, 4),
                equity=round(equity, 4),
                drawdown_pct=round(drawdown_pct, 4),
                open_positions=positions,
                error_rate=round(error_rate, 4),
                exception_count=self._exception_count,
                reconciliation_failures=self._reconciliation_failures,
                boot_gate_cleared=self._boot_gate_cleared,
            )

        # Pousser les métriques trading sur le bus
        metrics_bus.gauge("collector", "capital", snap.capital)
        metrics_bus.gauge("collector", "equity", snap.equity)
        metrics_bus.gauge("collector", "drawdown_pct", snap.drawdown_pct)
        metrics_bus.gauge("collector", "memory_mb", snap.memory_mb)
        metrics_bus.gauge("collector", "open_positions", float(snap.open_positions))

        return snap

    def flush_to_jsonl(self, path: Path) -> None:
        """Appende le snapshot courant au fichier JSONL."""
        snap = self.snapshot()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(snap.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:
            _log.warning("[MetricsCollector] Flush JSONL échoué: %s", exc)

    def reset_counters(self) -> None:
        """Remet à zéro les compteurs (ex: après redémarrage de session)."""
        with self._lock:
            self._exception_count = 0
            self._reconciliation_failures = 0
            self._error_ts.clear()


# ── Helpers système ───────────────────────────────────────────────────────────


def _get_memory_mb() -> float:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def _get_cpu_percent() -> float:
    try:
        import psutil

        return psutil.cpu_percent(interval=None)
    except Exception:
        return 0.0
