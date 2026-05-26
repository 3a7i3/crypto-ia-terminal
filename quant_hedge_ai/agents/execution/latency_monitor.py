"""
latency_monitor.py — Execution Latency & Exchange Failure Monitor (Idée #4).

Logger :
  - temps signal → ordre (calculé par ShadowEngine ou déclaré manuellement)
  - temps ordre → fill
  - reject rate
  - API timeout rate
  - WebSocket desync events

Parce que souvent la stratégie gagne mais l'exécution perd.

Usage:
    monitor = ExecutionLatencyMonitor()

    with monitor.measure("signal_to_order"):
        order = build_order(signal)

    monitor.record_fill(order_id, fill_latency_ms=45.0)
    monitor.record_reject(order_id, reason="insufficient funds")
    monitor.record_timeout(endpoint="create_order")
    monitor.record_ws_desync(symbol="BTCUSDT", lag_ms=1200)

    print(monitor.report())
"""

from __future__ import annotations

import contextlib
import json
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.execution.latency_monitor")
_LOG_PATH = Path("databases/latency/latency_log.jsonl")
_WINDOW = 500  # taille du ring buffer pour chaque métrique


@dataclass
class LatencyEvent:
    event_type: str  # signal_to_order | order_to_fill | reject | timeout | ws_desync
    value_ms: float  # latence en ms (ou 0 pour reject/timeout sans durée)
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "value_ms": round(self.value_ms, 3),
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class ExecutionLatencyMonitor:
    """
    Collecte et agrège les métriques de latence et d'échec d'exécution.
    Thread-safe (lecture seule des deques est safe, écriture dans append).
    """

    def __init__(
        self,
        log_path: Path | None = None,
        persist: bool = True,
        alert_threshold_ms: float = 500.0,
    ) -> None:
        self._log_path = log_path or _LOG_PATH
        self._persist = persist
        self._alert_threshold_ms = alert_threshold_ms

        # Ring buffers par type
        self._signal_to_order: deque[float] = deque(maxlen=_WINDOW)
        self._order_to_fill: deque[float] = deque(maxlen=_WINDOW)
        self._rejects: deque[dict] = deque(maxlen=_WINDOW)
        self._timeouts: deque[dict] = deque(maxlen=_WINDOW)
        self._ws_desyncs: deque[dict] = deque(maxlen=_WINDOW)

        self._total_orders: int = 0
        self._total_fills: int = 0

    # ── Mesures ────────────────────────────────────────────────────────────────

    @contextlib.contextmanager
    def measure(self, phase: str, **meta) -> Generator[None, None, None]:
        """Context manager qui mesure la durée d'un bloc de code."""
        t0 = time.perf_counter()
        yield
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.record_latency(phase, elapsed_ms, metadata=meta)

    def record_latency(
        self, phase: str, ms: float, metadata: dict | None = None
    ) -> None:
        metadata = metadata or {}
        event = LatencyEvent(event_type=phase, value_ms=ms, metadata=metadata)

        if phase == "signal_to_order":
            self._signal_to_order.append(ms)
            self._total_orders += 1
        elif phase == "order_to_fill":
            self._order_to_fill.append(ms)
            self._total_fills += 1

        if ms > self._alert_threshold_ms:
            _log.warning(
                "[LatencyMonitor] ⚠️ %s LENT: %.1fms (seuil=%.0fms)",
                phase,
                ms,
                self._alert_threshold_ms,
            )

        self._persist_event(event)

    def record_fill(self, order_id: str, fill_latency_ms: float) -> None:
        self.record_latency(
            "order_to_fill", fill_latency_ms, metadata={"order_id": order_id}
        )

    def record_reject(self, order_id: str, reason: str = "") -> None:
        entry = {"order_id": order_id, "reason": reason, "ts": time.time()}
        self._rejects.append(entry)
        _log.warning("[LatencyMonitor] REJECT order=%s raison=%s", order_id, reason)
        self._persist_event(LatencyEvent("reject", 0.0, metadata=entry))

    def record_timeout(self, endpoint: str = "", extra: str = "") -> None:
        entry = {"endpoint": endpoint, "extra": extra, "ts": time.time()}
        self._timeouts.append(entry)
        _log.warning("[LatencyMonitor] TIMEOUT endpoint=%s", endpoint)
        self._persist_event(LatencyEvent("timeout", 0.0, metadata=entry))

    def record_ws_desync(self, symbol: str = "", lag_ms: float = 0.0) -> None:
        entry = {"symbol": symbol, "lag_ms": lag_ms, "ts": time.time()}
        self._ws_desyncs.append(entry)
        if lag_ms > 500:
            _log.warning("[LatencyMonitor] WS DESYNC %s lag=%.0fms", symbol, lag_ms)
        self._persist_event(LatencyEvent("ws_desync", lag_ms, metadata=entry))

    # ── Rapport ────────────────────────────────────────────────────────────────

    def report(self) -> dict:
        def _stats(data: deque[float]) -> dict:
            lst = list(data)
            if not lst:
                return {"n": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
            lst_sorted = sorted(lst)
            n = len(lst)
            p50 = statistics.median(lst)
            p95 = lst_sorted[min(n - 1, int(0.95 * n))]
            return {
                "n": n,
                "avg": round(statistics.mean(lst), 2),
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "max": round(max(lst), 2),
            }

        total_submitted = self._total_orders + len(self._rejects)
        reject_rate = len(self._rejects) / max(1, total_submitted) * 100
        timeout_rate = len(self._timeouts) / max(1, total_submitted) * 100
        fill_rate = self._total_fills / max(1, total_submitted) * 100

        return {
            "signal_to_order_ms": _stats(self._signal_to_order),
            "order_to_fill_ms": _stats(self._order_to_fill),
            "reject_rate_pct": round(reject_rate, 2),
            "timeout_rate_pct": round(timeout_rate, 2),
            "fill_rate_pct": round(fill_rate, 2),
            "total_orders": self._total_orders,
            "total_fills": self._total_fills,
            "total_rejects": len(self._rejects),
            "total_timeouts": len(self._timeouts),
            "ws_desyncs_recent": list(self._ws_desyncs)[-5:],
        }

    def summary_text(self) -> str:
        r = self.report()
        sto = r["signal_to_order_ms"]
        otf = r["order_to_fill_ms"]
        return (
            f"Latence sig->ord: avg={sto['avg']}ms p95={sto['p95']}ms | "
            f"ord->fill: avg={otf['avg']}ms p95={otf['p95']}ms | "
            f"reject={r['reject_rate_pct']}% timeout={r['timeout_rate_pct']}%"
        )

    # ── Persistance ────────────────────────────────────────────────────────────

    def _persist_event(self, event: LatencyEvent) -> None:
        if not self._persist:
            return
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.as_dict()) + "\n")
        except Exception as exc:
            _log.debug("[LatencyMonitor] Persist error: %s", exc)
