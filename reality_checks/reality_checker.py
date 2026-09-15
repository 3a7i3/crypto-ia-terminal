"""Realité vs Paper — mesure l''écart entre simulation et réel.

À exécuter après 48h de paper trading.
Compare : slippage, spread, fees, partial fills, latence.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RealityGap:
    slippage_bps: float = 0.0
    spread_bps: float = 0.0
    fee_bps: float = 0.0
    partial_fill_rate: float = 0.0
    latency_ms: float = 0.0
    gap_percent: float = 0.0


class RealityChecker:
    """Compare paper trading vs execution réelle."""

    def __init__(self, paper_engine, execution_engine):
        self._paper = paper_engine
        self._execution = execution_engine
        self._report: Optional[RealityGap] = None

    def measure_slippage(self) -> float:
        """Écart entre prix demandé et prix exécuté."""
        return self._execution.avg_slippage_bps - self._paper.avg_slippage_bps

    def measure_spread(self) -> float:
        """Bid-ask au moment de l''exécution."""
        return self._execution.avg_spread_bps

    def measure_fees(self) -> float:
        """Frais réels vs frais configurés."""
        return self._execution.total_fees_bps

    def measure_partial_fills(self) -> float:
        """Fréquence des exécutions partielles."""
        total = self._execution.total_orders
        partial = self._execution.partial_fill_count
        return partial / total if total > 0 else 0.0

    def measure_latency(self) -> float:
        """Temps entre envoi et confirmation."""
        return self._execution.avg_latency_ms

    def run(self) -> RealityGap:
        gap = RealityGap(
            slippage_bps=self.measure_slippage(),
            spread_bps=self.measure_spread(),
            fee_bps=self.measure_fees(),
            partial_fill_rate=self.measure_partial_fills(),
            latency_ms=self.measure_latency(),
        )
        # Écart total pondéré
        gap.gap_percent = (
            abs(gap.slippage_bps) * 0.3
            + gap.spread_bps * 0.2
            + gap.fee_bps * 0.2
            + gap.partial_fill_rate * 100 * 0.15
            + gap.latency_ms * 0.15
        )
        self._report = gap
        return gap

    @property
    def report(self) -> Optional[RealityGap]:
        return self._report

    def is_acceptable(self, threshold: float = 15.0) -> bool:
        """Écart < 15% = acceptable pour le live."""
        if self._report is None:
            return False
        return self._report.gap_percent < threshold


# Métriques clés à collecter sur 48h :
# paper_pnl vs execution_pnl
# slippage réel
# spread réel
# fees réels
# partial fills
# latence réelle
