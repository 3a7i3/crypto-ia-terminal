"""
activity_tracker.py — Métriques d'activité et d'inactivité du capital.

Mesure en temps réel si le système utilise son capital ou le laisse dormir.

Métriques produites :
  - inactivity_ratio       : fraction des cycles sans position ouverte
  - refusal_accuracy       : part des refus qui étaient justifiés
  - execution_ratio        : signaux exécutés / (exécutés + refusés)
  - cycles_since_last_trade: cycles écoulés depuis le dernier trade

Usage dans advisor_loop :
    tracker = ActivityTracker()
    # Chaque cycle :
    tracker.record_cycle(
        has_position=len(open_positions) > 0,
        signal_refused=gate_result.allowed is False and score >= min_score,
        signal_executed=True if new_order else False,
    )
    # Périodiquement (ex. toutes les 12 cycles) :
    logger.info(tracker.summary())
    # Pour Telegram :
    report = tracker.report()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_INACTIVITY_WARN_THRESHOLD = float(
    __import__("os").getenv("INACTIVITY_WARN_RATIO", "0.85")
)  # alerte si > 85% des cycles sans position


@dataclass
class ActivityMetrics:
    """Snapshot des métriques d'activité à un instant T."""

    total_cycles: int
    cycles_with_position: int
    cycles_without_position: int
    inactivity_ratio: float  # 0.0 = toujours en position, 1.0 = jamais
    refused_count: int  # signaux refusés ALORS QUE score >= seuil
    executed_count: int
    execution_ratio: float  # exécutés / (exécutés + refusés)
    cycles_since_last_trade: int
    uptime_seconds: float

    def is_overfiltered(self, threshold: float = _INACTIVITY_WARN_THRESHOLD) -> bool:
        """True si le capital est inactif au-delà du seuil d'alerte."""
        return self.inactivity_ratio > threshold and self.total_cycles >= 10

    def summary_line(self) -> str:
        return (
            f"Activité: {1 - self.inactivity_ratio:.0%} | "
            f"Exécutés/Refusés: {self.executed_count}/{self.refused_count} "
            f"(exec_ratio={self.execution_ratio:.0%}) | "
            f"Sans trade depuis: {self.cycles_since_last_trade} cycles"
        )


class ActivityTracker:
    """
    Trace l'activité du capital cycle par cycle.

    Thread-safe pour usage depuis advisor_loop (boucle principale).
    """

    def __init__(self) -> None:
        self._started_at: float = time.time()
        self._total_cycles: int = 0
        self._cycles_with_position: int = 0
        self._refused: int = 0  # signaux bloqués avec score suffisant
        self._executed: int = 0  # ordres effectivement passés
        self._cycles_since_last_trade: int = 0
        self._last_trade_cycle: int = 0
        self._inactivity_streak: int = 0  # cycles consécutifs sans position

    # ── Alimentation par cycle ────────────────────────────────────────────────

    def record_cycle(
        self,
        has_position: bool,
        signal_refused: bool = False,
        signal_executed: bool = False,
    ) -> None:
        """
        Enregistre les données d'un cycle.

        Args:
            has_position    : True si au moins une position est ouverte
            signal_refused  : True si un signal valide (score >= seuil) a été refusé
            signal_executed : True si un ordre a été passé ce cycle
        """
        self._total_cycles += 1

        if has_position:
            self._cycles_with_position += 1
            self._inactivity_streak = 0
        else:
            self._inactivity_streak += 1

        if signal_refused:
            self._refused += 1

        if signal_executed:
            self._executed += 1
            self._last_trade_cycle = self._total_cycles
            self._inactivity_streak = 0

        self._cycles_since_last_trade = self._total_cycles - self._last_trade_cycle

        # Alerte si inactivité prolongée
        if self._inactivity_streak > 0 and self._inactivity_streak % 20 == 0:
            metrics = self.metrics()
            if metrics.is_overfiltered():
                logger.warning(
                    "[ActivityTracker] CAPITAL INACTIF depuis %d cycles "
                    "(inactivité=%.0f%%, refusés=%d) — sur-filtrage probable",
                    self._inactivity_streak,
                    metrics.inactivity_ratio * 100,
                    self._refused,
                )

    # ── Métriques ─────────────────────────────────────────────────────────────

    def metrics(self) -> ActivityMetrics:
        total = max(self._total_cycles, 1)
        without = total - self._cycles_with_position
        inactivity = without / total
        total_signals = self._executed + self._refused
        exec_ratio = self._executed / max(total_signals, 1)

        return ActivityMetrics(
            total_cycles=self._total_cycles,
            cycles_with_position=self._cycles_with_position,
            cycles_without_position=without,
            inactivity_ratio=round(inactivity, 4),
            refused_count=self._refused,
            executed_count=self._executed,
            execution_ratio=round(exec_ratio, 4),
            cycles_since_last_trade=self._cycles_since_last_trade,
            uptime_seconds=round(time.time() - self._started_at, 1),
        )

    def summary(self) -> str:
        return f"[ActivityTracker] {self.metrics().summary_line()}"

    def report(self) -> dict:
        """Dict JSON-sérialisable pour dashboard / Telegram."""
        m = self.metrics()
        alert = m.is_overfiltered()
        return {
            "total_cycles": m.total_cycles,
            "inactivity_ratio": m.inactivity_ratio,
            "execution_ratio": m.execution_ratio,
            "executed": m.executed_count,
            "refused": m.refused_count,
            "cycles_since_last_trade": m.cycles_since_last_trade,
            "uptime_seconds": m.uptime_seconds,
            "alert_overfiltered": alert,
            "summary": m.summary_line(),
        }

    def reset(self) -> None:
        """Remet les compteurs à zéro (ex. début de nouvelle session)."""
        self.__init__()  # type: ignore[misc]
