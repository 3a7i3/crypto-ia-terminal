"""
health_score.py — Score de santé composite (0-100) du système (P12-B).

Le score agrège 5 dimensions :
  Mémoire      (25 pts) : usage mémoire vs seuil critique
  Fiabilité    (25 pts) : error_rate, exception_count, reconciliation_failures
  Exchange     (20 pts) : boot_gate_cleared, reconciliation_failures
  Trading      (20 pts) : drawdown, positions valides
  Performance  (10 pts) : latences cycle/décision/exécution

Score < 50 → CRITICAL
Score < 75 → DEGRADED
Score >= 75 → HEALTHY
Score == 100 → PERFECT

Usage :
    from observability.health_score import HealthScore, HealthLevel
    scorer = HealthScore()
    snap = collector.snapshot()
    snap.health_score = scorer.compute(snap)
    level = scorer.level(snap.health_score)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from observability.metrics_collector import MetricsSnapshot

# ── Seuils configurables ──────────────────────────────────────────────────────

# Mémoire
_MEM_WARN_MB = 500.0
_MEM_CRIT_MB = 1_000.0

# Error rate (erreurs / minute)
_ERR_RATE_WARN = 1.0
_ERR_RATE_CRIT = 5.0

# Drawdown
_DD_WARN_PCT = 5.0
_DD_CRIT_PCT = 15.0

# Latences (ms)
_CYCLE_WARN_MS = 1_000.0
_CYCLE_CRIT_MS = 5_000.0
_EXEC_WARN_MS = 500.0
_EXEC_CRIT_MS = 2_000.0


class HealthLevel(str, Enum):
    PERFECT = "PERFECT"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


@dataclass
class HealthBreakdown:
    """Détail des contributions au score."""

    total: float
    memory: float
    reliability: float
    exchange: float
    trading: float
    performance: float
    level: HealthLevel


class HealthScore:
    """
    Calcule un score de santé composite à partir d'un MetricsSnapshot.

    Méthode : somme pondérée de 5 composantes, chacune normalisée [0, max_pts].
    """

    def compute(self, snap: MetricsSnapshot) -> float:
        """Retourne le score total [0.0, 100.0]."""
        return round(self._breakdown(snap).total, 2)

    def level(self, score: float) -> HealthLevel:
        if score == 100.0:
            return HealthLevel.PERFECT
        if score >= 75.0:
            return HealthLevel.HEALTHY
        if score >= 50.0:
            return HealthLevel.DEGRADED
        return HealthLevel.CRITICAL

    def breakdown(self, snap: MetricsSnapshot) -> HealthBreakdown:
        return self._breakdown(snap)

    # ── Calculs internes ─────────────────────────────────────────────────────

    def _breakdown(self, snap: MetricsSnapshot) -> HealthBreakdown:
        mem = self._score_memory(snap)
        rel = self._score_reliability(snap)
        exc = self._score_exchange(snap)
        trd = self._score_trading(snap)
        prf = self._score_performance(snap)
        total = mem + rel + exc + trd + prf
        return HealthBreakdown(
            total=round(total, 2),
            memory=round(mem, 2),
            reliability=round(rel, 2),
            exchange=round(exc, 2),
            trading=round(trd, 2),
            performance=round(prf, 2),
            level=self.level(total),
        )

    def _score_memory(self, snap: MetricsSnapshot) -> float:
        """25 pts — mémoire en dessous du seuil critique."""
        mb = snap.memory_mb
        if mb <= 0:
            return 25.0  # pas de donnée → pas de pénalité
        if mb >= _MEM_CRIT_MB:
            return 0.0
        if mb >= _MEM_WARN_MB:
            # Dégradation linéaire entre WARN et CRIT
            ratio = (mb - _MEM_WARN_MB) / (_MEM_CRIT_MB - _MEM_WARN_MB)
            return round(25.0 * (1 - ratio * 0.8), 2)
        return 25.0

    def _score_reliability(self, snap: MetricsSnapshot) -> float:
        """25 pts — error_rate + exceptions + reconciliation."""
        pts = 25.0

        # Error rate (max -15 pts)
        rate = snap.error_rate
        if rate >= _ERR_RATE_CRIT:
            pts -= 15.0
        elif rate >= _ERR_RATE_WARN:
            ratio = (rate - _ERR_RATE_WARN) / (_ERR_RATE_CRIT - _ERR_RATE_WARN)
            pts -= 15.0 * ratio

        # Exception count (max -5 pts)
        if snap.exception_count >= 10:
            pts -= 5.0
        elif snap.exception_count > 0:
            pts -= min(5.0, snap.exception_count * 0.5)

        # Reconciliation failures (max -5 pts)
        if snap.reconciliation_failures >= 3:
            pts -= 5.0
        elif snap.reconciliation_failures > 0:
            pts -= snap.reconciliation_failures * 1.5

        return max(0.0, pts)

    def _score_exchange(self, snap: MetricsSnapshot) -> float:
        """20 pts — boot gate + reconciliation."""
        pts = 20.0

        # Boot gate non levé → -15 pts
        if not snap.boot_gate_cleared:
            pts -= 15.0

        # Failures récentes → -5 pts
        if snap.reconciliation_failures >= 1:
            pts -= min(5.0, snap.reconciliation_failures * 2.0)

        return max(0.0, pts)

    def _score_trading(self, snap: MetricsSnapshot) -> float:
        """20 pts — drawdown + cohérence positions."""
        pts = 20.0

        # Drawdown (max -15 pts)
        dd = snap.drawdown_pct
        if dd >= _DD_CRIT_PCT:
            pts -= 15.0
        elif dd >= _DD_WARN_PCT:
            ratio = (dd - _DD_WARN_PCT) / (_DD_CRIT_PCT - _DD_WARN_PCT)
            pts -= 15.0 * ratio

        # Positions négatives → -5 pts
        if snap.open_positions < 0:
            pts -= 5.0

        return max(0.0, pts)

    def _score_performance(self, snap: MetricsSnapshot) -> float:
        """10 pts — latences cycle + exécution."""
        pts = 10.0

        # Cycle duration (max -5 pts)
        cyc = snap.cycle_duration_ms
        if cyc > 0:
            if cyc >= _CYCLE_CRIT_MS:
                pts -= 5.0
            elif cyc >= _CYCLE_WARN_MS:
                ratio = (cyc - _CYCLE_WARN_MS) / (_CYCLE_CRIT_MS - _CYCLE_WARN_MS)
                pts -= 5.0 * ratio

        # Execution latency (max -5 pts)
        exc = snap.execution_latency_ms
        if exc > 0:
            if exc >= _EXEC_CRIT_MS:
                pts -= 5.0
            elif exc >= _EXEC_WARN_MS:
                ratio = (exc - _EXEC_WARN_MS) / (_EXEC_CRIT_MS - _EXEC_WARN_MS)
                pts -= 5.0 * ratio

        return max(0.0, pts)
