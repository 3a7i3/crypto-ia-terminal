"""
monitoring/pipeline_monitor.py — Monitoring haut niveau du pipeline P2/P3.

Couche de facade qui combine logger structure + metriques pour instrumenter
les etapes cles du pipeline sans disperser le code de monitoring dans
chaque module metier.

Etapes instrumentees :
  record_trade_processed()   : execution_simulator — un fill complete
  record_fold_completed()    : walk_forward — un fold OOS valide
  record_error()             : tout composant — erreur capturee
  record_simulation_run()    : resume d'un batch de simulation
  record_replay_event()      : market_data — un evenement de replay

Usage :
    mon = PipelineMonitor()                        # sink=stderr par defaut
    mon = PipelineMonitor(sink=null_sink())        # silencieux (tests)
    mon = PipelineMonitor(sink=file_sink(f))       # vers fichier JSONL

    mon.record_trade_processed("BTCUSDT", latency_ms=75, slippage_bps=2.1)
    mon.record_fold_completed(fold_idx=3, n_trades=45, sharpe=1.4, duration_s=0.12)
    mon.record_error("walk_forward", "ValueError", "optimizer crashed on fold 2")

    snap = mon.snapshot()   # dict complet pour le reporter
"""

from __future__ import annotations

import time
from typing import Optional

from monitoring.logger import Sink, StructuredLogger, null_sink
from monitoring.metrics import MetricsRegistry


class PipelineMonitor:
    """
    Point d'entree unique pour le monitoring du pipeline.

    sink  : callable(LogRecord) — si None, logs silencieux (null_sink)
    level : niveau minimum de log ("DEBUG" / "INFO" / "WARNING" / ...)
    """

    def __init__(
        self,
        sink: Optional[Sink] = None,
        level: str = "INFO",
    ) -> None:
        self._logger = StructuredLogger(
            "pipeline", sink=sink if sink is not None else null_sink(), level=level
        )
        self._metrics = MetricsRegistry()
        self._start_time = time.monotonic()

        # Metriques pre-creees
        self._trades_total = self._metrics.counter("trades_processed_total")
        self._fills_rejected = self._metrics.counter("fills_rejected_total")
        self._errors_total = self._metrics.counter("errors_total")
        self._folds_total = self._metrics.counter("folds_completed_total")
        self._replay_events = self._metrics.counter("replay_events_total")

        self._latency_h = self._metrics.histogram(
            "fill_latency_ms", buckets=[5, 10, 25, 50, 100, 200, 500, 1000]
        )
        self._slippage_h = self._metrics.histogram(
            "slippage_bps", buckets=[0.1, 0.5, 1, 2, 5, 10, 20, 50]
        )
        self._fold_duration_h = self._metrics.histogram(
            "fold_duration_s", buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10]
        )
        self._fold_sharpe_g = self._metrics.gauge("last_fold_sharpe")
        self._fold_n_trades_g = self._metrics.gauge("last_fold_n_trades")

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def record_trade_processed(
        self,
        symbol: str,
        latency_ms: float,
        slippage_bps: float,
        fill_ratio: float = 1.0,
        is_rejected: bool = False,
    ) -> None:
        """Enregistre un fill (ou rejet) de l'execution_simulator."""
        self._trades_total.inc()
        if is_rejected:
            self._fills_rejected.inc()
        else:
            self._latency_h.observe(latency_ms)
            self._slippage_h.observe(slippage_bps)

        self._logger.debug(
            "trade_processed",
            symbol=symbol,
            latency_ms=round(latency_ms, 2),
            slippage_bps=round(slippage_bps, 4),
            fill_ratio=round(fill_ratio, 4),
            is_rejected=is_rejected,
        )

    def record_fold_completed(
        self,
        fold_idx: int,
        n_trades: int,
        sharpe: float,
        duration_s: float,
        is_profitable: bool = False,
    ) -> None:
        """Enregistre la completion d'un fold OOS du walk-forward."""
        self._folds_total.inc()
        self._fold_sharpe_g.set(sharpe)
        self._fold_n_trades_g.set(float(n_trades))
        self._fold_duration_h.observe(duration_s)

        self._logger.info(
            "fold_completed",
            fold_idx=fold_idx,
            n_trades=n_trades,
            sharpe=round(sharpe, 4),
            duration_s=round(duration_s, 4),
            is_profitable=is_profitable,
        )

    def record_error(
        self,
        component: str,
        error_type: str,
        message: str,
    ) -> None:
        """Enregistre une erreur depuis n'importe quel composant."""
        self._errors_total.inc()
        self._logger.error(
            "error",
            component=component,
            error_type=error_type,
            message=message,
        )

    def record_replay_event(self, event_type: str, symbol: str) -> None:
        """Enregistre un evenement du replay engine."""
        self._replay_events.inc()
        self._logger.debug("replay_event", event_type=event_type, symbol=symbol)

    def record_simulation_run(
        self,
        n_fills: int,
        mean_slippage_bps: float,
        mean_latency_ms: float,
        n_rejected: int = 0,
    ) -> None:
        """Resume d'un batch de simulation complet."""
        elapsed = time.monotonic() - self._start_time
        self._logger.info(
            "simulation_run_complete",
            n_fills=n_fills,
            n_rejected=n_rejected,
            mean_slippage_bps=round(mean_slippage_bps, 4),
            mean_latency_ms=round(mean_latency_ms, 2),
            elapsed_s=round(elapsed, 3),
        )

    def record_degradation_alert(
        self,
        fold_idx: int,
        metric: str,
        severity: str,
        message: str,
    ) -> None:
        """Alerte de degradation emise par le DegradationTracker."""
        self._errors_total.inc()
        level = "critical" if severity == "critical" else "warning"
        log_fn = self._logger.critical if level == "critical" else self._logger.warning
        log_fn(
            "degradation_alert",
            fold_idx=fold_idx,
            metric=metric,
            severity=severity,
            message=message,
        )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Retourne toutes les metriques + uptime en dict JSON-serialisable."""
        elapsed = time.monotonic() - self._start_time
        snap = self._metrics.snapshot()
        snap["uptime_s"] = round(elapsed, 3)
        return snap

    def reset(self) -> None:
        """Remet le moniteur a zero (utile entre tests)."""
        self._metrics.reset()
        self._start_time = time.monotonic()
        # Re-creer les references pre-cachees
        self.__init__(level="INFO")
