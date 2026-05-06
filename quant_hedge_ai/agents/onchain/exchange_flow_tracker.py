"""
exchange_flow_tracker.py — Exchange Inflow/Outflow Real-Time Tracker

Surveille les flux nets vers/depuis les exchanges centralisés.
Signal critique : inflow massif = pression vente imminente.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FlowReport:
    symbol: str
    timestamp: float

    # Flux absolus (USD)
    inflow_1h: float = 0.0
    outflow_1h: float = 0.0
    net_flow_1h: float = 0.0            # positif = accumulation (sortie > entrée)

    # Variation
    inflow_change_pct: float = 0.0      # vs moyenne 24h
    outflow_change_pct: float = 0.0

    # Alertes
    inflow_spike: bool = False          # inflow > 2x moyenne = sell pressure imminent
    outflow_spike: bool = False         # outflow > 2x moyenne = accumulation forte
    net_flow_extreme: bool = False      # déséquilibre extrême

    # Score de pression vente [0,1]
    sell_pressure_score: float = 0.0

    # Signal directionnel
    flow_signal: str = "neutral"        # "buy", "sell", "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class ExchangeFlowTracker:
    """
    Maintient un historique des flux exchange et détecte les anomalies.
    Fonctionne avec les données de BlockchainIngester.
    """

    SPIKE_MULTIPLIER = 2.0      # seuil pour détecter un spike
    WINDOW_SIZE = 24            # fenêtre historique (24 snapshots = 24h si 1 snapshot/h)

    def __init__(self) -> None:
        self._inflow_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.WINDOW_SIZE))
        self._outflow_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.WINDOW_SIZE))
        self._last_reports: dict[str, FlowReport] = {}

    def update(self, symbol: str, inflow_usd: float, outflow_usd: float) -> FlowReport:
        """Met à jour les flux et retourne un rapport d'analyse."""
        self._inflow_history[symbol].append(inflow_usd)
        self._outflow_history[symbol].append(outflow_usd)

        inflow_hist = list(self._inflow_history[symbol])
        outflow_hist = list(self._outflow_history[symbol])

        report = FlowReport(
            symbol=symbol,
            timestamp=time.time(),
            inflow_1h=inflow_usd,
            outflow_1h=outflow_usd,
            net_flow_1h=outflow_usd - inflow_usd,
        )

        if len(inflow_hist) >= 3:
            avg_inflow = sum(inflow_hist[:-1]) / max(len(inflow_hist) - 1, 1)
            avg_outflow = sum(outflow_hist[:-1]) / max(len(outflow_hist) - 1, 1)

            if avg_inflow > 0:
                report.inflow_change_pct = (inflow_usd - avg_inflow) / avg_inflow
            if avg_outflow > 0:
                report.outflow_change_pct = (outflow_usd - avg_outflow) / avg_outflow

            report.inflow_spike = inflow_usd > avg_inflow * self.SPIKE_MULTIPLIER
            report.outflow_spike = outflow_usd > avg_outflow * self.SPIKE_MULTIPLIER

            total = inflow_usd + outflow_usd
            if total > 0:
                imbalance = abs(inflow_usd - outflow_usd) / total
                report.net_flow_extreme = imbalance > 0.6

        report.sell_pressure_score = self._compute_sell_pressure(report)
        report.flow_signal = self._determine_signal(report)

        self._last_reports[symbol] = report

        if report.inflow_spike:
            logger.warning("[FlowTracker] %s — INFLOW SPIKE: %.0f USD (sell pressure)", symbol, inflow_usd)
        if report.outflow_spike:
            logger.info("[FlowTracker] %s — OUTFLOW SPIKE: %.0f USD (accumulation)", symbol, outflow_usd)

        return report

    def update_from_onchain(self, symbol: str, onchain_data) -> FlowReport:
        """Mise à jour depuis un objet OnChainData."""
        inflow = getattr(onchain_data, "exchange_inflow_usd", 0.0)
        outflow = getattr(onchain_data, "exchange_outflow_usd", 0.0)
        return self.update(symbol, inflow, outflow)

    def get_last(self, symbol: str) -> FlowReport | None:
        return self._last_reports.get(symbol)

    def net_flow_trend(self, symbol: str, n: int = 6) -> str:
        """Tendance sur les n dernières heures."""
        in_hist = list(self._inflow_history[symbol])[-n:]
        out_hist = list(self._outflow_history[symbol])[-n:]
        if len(in_hist) < 2:
            return "unknown"
        net_flows = [o - i for o, i in zip(out_hist, in_hist)]
        avg_net = sum(net_flows) / len(net_flows)
        if avg_net > 5_000_000:
            return "accumulation"
        if avg_net < -5_000_000:
            return "sell_pressure"
        return "neutral"

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _compute_sell_pressure(self, report: FlowReport) -> float:
        """Score de pression vente [0,1]."""
        pressure = 0.0
        if report.inflow_spike:
            pressure += 0.4
        if report.net_flow_1h < 0:
            total = abs(report.inflow_1h) + abs(report.outflow_1h)
            if total > 0:
                pressure += abs(report.net_flow_1h) / total * 0.4
        if report.inflow_change_pct > 0.5:
            pressure += min(report.inflow_change_pct * 0.2, 0.2)
        return min(pressure, 1.0)

    def _determine_signal(self, report: FlowReport) -> str:
        if report.sell_pressure_score > 0.5 or report.inflow_spike:
            return "sell"
        if report.outflow_spike or report.net_flow_1h > 10_000_000:
            return "buy"
        return "neutral"
