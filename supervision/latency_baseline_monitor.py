"""
supervision/latency_baseline_monitor.py — E-07 LatencyMonitor Permanent Baseline

Baseline de latence permanente pour chaque opération critique.

Opérations surveillées :
  - ohlcv_fetch    : fetch OHLCV par exchange
  - feature_calc   : calcul features par symbole
  - lm_studio_call : appel LM Studio par décision
  - order_exec     : exécution ordre par exchange

Garanties :
  - Baseline établie sur 50+ échantillons (configurable)
  - Alerte si déviation > 3σ de la baseline
  - Historique conservé 30 jours (rolling window)
  - Persistance JSON sur disque (survit aux redémarrages)
  - p50/p95/p99 calculés

Usage :
    monitor = LatencyBaselineMonitor.from_default()
    monitor.on_latency("ohlcv_fetch", 250.0)  # 250ms
    if alert := monitor.on_latency("ohlcv_fetch", 5000.0):  # 5s — anomalie
        print(alert)
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("supervision.latency_baseline_monitor")

_BASELINE_PATH = Path(
    os.getenv("P10_LATENCY_BASELINE_PATH", "cache/startup/latency_baseline.json")
)
_MIN_SAMPLES = int(os.getenv("P10_LATENCY_MIN_SAMPLES", "50"))
_RETENTION_DAYS = int(os.getenv("P10_LATENCY_RETENTION_DAYS", "30"))
_DEFAULT_SIGMA = float(os.getenv("P10_LATENCY_SIGMA", "3.0"))

KNOWN_OPERATIONS = [
    "ohlcv_fetch",
    "feature_calc",
    "lm_studio_call",
    "order_exec",
]


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass
class LatencyStats:
    operation: str
    count: int
    mean_ms: float
    std_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    baseline_established: bool
    baseline_established_at: float
    last_updated: float

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "count": self.count,
            "mean_ms": round(self.mean_ms, 2),
            "std_ms": round(self.std_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "baseline_established": self.baseline_established,
            "baseline_established_at": round(self.baseline_established_at, 3),
            "last_updated": round(self.last_updated, 3),
        }


@dataclass
class LatencyAnomaly:
    operation: str
    latency_ms: float
    baseline_mean_ms: float
    baseline_std_ms: float
    deviation_sigma: float
    threshold_sigma: float
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "latency_ms": round(self.latency_ms, 2),
            "baseline_mean_ms": round(self.baseline_mean_ms, 2),
            "baseline_std_ms": round(self.baseline_std_ms, 2),
            "deviation_sigma": round(self.deviation_sigma, 2),
            "threshold_sigma": self.threshold_sigma,
            "ts": round(self.ts, 3),
        }


# ── Baseline par opération ────────────────────────────────────────────────────


class _OperationBaseline:
    """Gère les échantillons de latence pour une opération."""

    def __init__(
        self,
        operation: str,
        min_samples: int = _MIN_SAMPLES,
        retention_days: int = _RETENTION_DAYS,
    ) -> None:
        self.operation = operation
        self.min_samples = min_samples
        self.retention_s = retention_days * 86400

        # (timestamp, latency_ms)
        self._samples: deque[tuple[float, float]] = deque()
        self._baseline_established_at: float = 0.0

    def record(self, latency_ms: float) -> None:
        now = time.time()
        self._samples.append((now, latency_ms))
        self._prune_old()
        if (
            self._baseline_established_at == 0.0
            and len(self._samples) >= self.min_samples
        ):
            self._baseline_established_at = now

    def is_baseline_established(self) -> bool:
        return len(self._samples) >= self.min_samples

    def stats(self) -> Optional[LatencyStats]:
        values = [v for _, v in self._samples]
        if not values:
            return None
        n = len(values)
        mean = statistics.mean(values)
        std = statistics.stdev(values) if n >= 2 else 0.0
        sorted_vals = sorted(values)
        p50 = _percentile(sorted_vals, 50)
        p95 = _percentile(sorted_vals, 95)
        p99 = _percentile(sorted_vals, 99)

        if self.is_baseline_established() and self._baseline_established_at == 0.0:
            self._baseline_established_at = time.time()

        return LatencyStats(
            operation=self.operation,
            count=n,
            mean_ms=mean,
            std_ms=std,
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            min_ms=min(values),
            max_ms=max(values),
            baseline_established=self.is_baseline_established(),
            baseline_established_at=self._baseline_established_at,
            last_updated=self._samples[-1][0] if self._samples else 0.0,
        )

    def is_anomaly(
        self, latency_ms: float, sigma_threshold: float
    ) -> tuple[bool, float]:
        """
        Retourne (is_anomaly, deviation_in_sigma).
        Nécessite une baseline établie.
        """
        if not self.is_baseline_established():
            return False, 0.0
        values = [v for _, v in self._samples]
        mean = statistics.mean(values)
        std = statistics.stdev(values) if len(values) >= 2 else 0.0
        if std < 0.001:
            # All values identical: any meaningful deviation is anomalous
            deviation_abs = abs(latency_ms - mean)
            synthetic_sigma = deviation_abs / max(mean * 0.01, 1.0)
            return synthetic_sigma >= sigma_threshold, synthetic_sigma
        deviation = abs(latency_ms - mean) / std
        return deviation >= sigma_threshold, deviation

    def to_serializable(self) -> dict:
        return {
            "operation": self.operation,
            "samples": list(self._samples),
            "baseline_established_at": self._baseline_established_at,
        }

    def from_serializable(self, data: dict) -> None:
        samples = data.get("samples", [])
        self._samples = deque(
            [(float(ts), float(v)) for ts, v in samples],
        )
        self._baseline_established_at = float(data.get("baseline_established_at", 0.0))
        self._prune_old()

    def baseline_age_hours(self) -> float:
        """Âge de l'établissement de la baseline en heures."""
        if self._baseline_established_at == 0.0:
            return float("inf")
        return (time.time() - self._baseline_established_at) / 3600.0

    def _prune_old(self) -> None:
        cutoff = time.time() - self.retention_s
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()


# ── Monitor principal ─────────────────────────────────────────────────────────


class LatencyBaseline:
    """
    Gère les baselines de latence pour plusieurs opérations.
    Peut être sauvegardée et rechargée depuis un fichier JSON.
    """

    def __init__(
        self,
        operations: Optional[list[str]] = None,
        min_samples: int = _MIN_SAMPLES,
        retention_days: int = _RETENTION_DAYS,
    ) -> None:
        self._min_samples = min_samples
        self._operations: dict[str, _OperationBaseline] = {}
        for op in operations or KNOWN_OPERATIONS:
            self._operations[op] = _OperationBaseline(op, min_samples, retention_days)

    def record(self, operation: str, latency_ms: float) -> None:
        """Enregistre une mesure de latence."""
        if operation not in self._operations:
            self._operations[operation] = _OperationBaseline(
                operation, self._min_samples
            )
        self._operations[operation].record(latency_ms)

    def is_anomaly(
        self,
        operation: str,
        latency_ms: float,
        sigma_threshold: float = _DEFAULT_SIGMA,
    ) -> bool:
        op = self._operations.get(operation)
        if op is None:
            return False
        is_anom, _ = op.is_anomaly(latency_ms, sigma_threshold)
        return is_anom

    def stats(self, operation: str) -> Optional[LatencyStats]:
        op = self._operations.get(operation)
        return op.stats() if op else None

    def is_baseline_established(self, operation: str) -> bool:
        op = self._operations.get(operation)
        return op.is_baseline_established() if op else False

    def baseline_age_hours(self, operation: str) -> float:
        op = self._operations.get(operation)
        return op.baseline_age_hours() if op else float("inf")

    def operations(self) -> list[str]:
        return list(self._operations.keys())

    def export(self) -> dict:
        return {
            "exported_at": time.time(),
            "operations": {
                name: op.to_serializable() for name, op in self._operations.items()
            },
        }

    def save(self, path: Optional[Path] = None) -> None:
        target = path or _BASELINE_PATH
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(self.export(), indent=2), encoding="utf-8")
            _log.debug("[LatencyBaseline] Sauvegardé → %s", target)
        except Exception as exc:
            _log.warning("[LatencyBaseline] Erreur sauvegarde: %s", exc)

    def load(self, path: Optional[Path] = None) -> None:
        target = path or _BASELINE_PATH
        try:
            if not target.exists():
                return
            data = json.loads(target.read_text(encoding="utf-8"))
            for name, op_data in data.get("operations", {}).items():
                if name not in self._operations:
                    self._operations[name] = _OperationBaseline(name, self._min_samples)
                self._operations[name].from_serializable(op_data)
            _log.info(
                "[LatencyBaseline] Rechargée depuis %s (%d opérations)",
                target,
                len(self._operations),
            )
        except Exception as exc:
            _log.warning("[LatencyBaseline] Erreur chargement: %s", exc)


class LatencyBaselineMonitor:
    """
    Surveille les latences en temps réel et alerte sur les anomalies 3σ.
    """

    def __init__(
        self,
        baseline: Optional[LatencyBaseline] = None,
        alert_fn: Optional[Callable[[LatencyAnomaly], None]] = None,
        sigma_threshold: float = _DEFAULT_SIGMA,
        auto_save_interval_s: float = 300.0,  # sauvegarde toutes les 5 min
    ) -> None:
        self._baseline = baseline or LatencyBaseline()
        self._alert_fn = alert_fn
        self._sigma = sigma_threshold
        self._anomalies: list[LatencyAnomaly] = []
        self._auto_save = auto_save_interval_s
        self._last_save = time.time()

    @classmethod
    def from_default(
        cls,
        alert_fn: Optional[Callable[[LatencyAnomaly], None]] = None,
    ) -> "LatencyBaselineMonitor":
        """Crée un monitor avec la baseline par défaut, rechargée si disponible."""
        baseline = LatencyBaseline()
        baseline.load()
        return cls(baseline=baseline, alert_fn=alert_fn)

    def on_latency(self, operation: str, latency_ms: float) -> Optional[LatencyAnomaly]:
        """
        Enregistre une latence et retourne une anomalie si 3σ dépassé.
        À appeler après chaque opération mesurée.
        """
        self._baseline.record(operation, latency_ms)
        self._maybe_save()

        if not self._baseline.is_baseline_established(operation):
            return None

        op = self._baseline._operations.get(operation)
        if op is None:
            return None

        is_anom, deviation = op.is_anomaly(latency_ms, self._sigma)
        if not is_anom:
            return None

        st = op.stats()
        if st is None:
            return None

        anomaly = LatencyAnomaly(
            operation=operation,
            latency_ms=latency_ms,
            baseline_mean_ms=st.mean_ms,
            baseline_std_ms=st.std_ms,
            deviation_sigma=deviation,
            threshold_sigma=self._sigma,
        )
        self._anomalies.append(anomaly)
        if len(self._anomalies) > 500:
            self._anomalies = self._anomalies[-500:]

        _log.warning(
            "[LatencyMonitor] ANOMALIE %s — %.0fms (baseline %.0f±%.0fms, %.1fσ)",
            operation,
            latency_ms,
            st.mean_ms,
            st.std_ms,
            deviation,
        )

        if self._alert_fn:
            try:
                self._alert_fn(anomaly)
            except Exception as exc:
                _log.debug("[LatencyMonitor] alert_fn erreur: %s", exc)

        return anomaly

    def stats(self, operation: str) -> Optional[LatencyStats]:
        return self._baseline.stats(operation)

    def baseline_age_hours(self, operation: str) -> float:
        return self._baseline.baseline_age_hours(operation)

    def export_baseline(self) -> dict:
        return self._baseline.export()

    def recent_anomalies(self, n: int = 10) -> list[dict]:
        return [a.to_dict() for a in self._anomalies[-n:]]

    def is_baseline_established(self, operation: str) -> bool:
        return self._baseline.is_baseline_established(operation)

    def save_baseline(self, path: Optional[Path] = None) -> None:
        self._baseline.save(path)

    def _maybe_save(self) -> None:
        if self._auto_save > 0 and time.time() - self._last_save > self._auto_save:
            self._baseline.save()
            self._last_save = time.time()


# ── Utilitaires ───────────────────────────────────────────────────────────────


def _percentile(sorted_values: list[float], p: float) -> float:
    """Percentile via interpolation linéaire."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac
