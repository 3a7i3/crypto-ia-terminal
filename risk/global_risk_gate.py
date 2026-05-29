"""
GlobalRiskGate — circuit breaker systémique pour Annalise
S'insère dans la boucle principale de main_v91.py avant toute exécution.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger("GlobalRiskGate")


class RiskLevel(Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class RiskThresholds:
    # Drawdown du portefeuille global (ex: -0.08 = -8%)
    drawdown_warning: float = -0.08
    drawdown_critical: float = -0.15

    # Corrélation moyenne entre stratégies actives
    correlation_warning: float = 0.75
    correlation_critical: float = 0.90

    # Volatilité relative (multiple de la vol normale 30j)
    vol_multiplier_warning: float = 2.5
    vol_multiplier_critical: float = 4.0

    # Exposition nette maximale (fraction du capital total)
    exposure_warning: float = 0.70
    exposure_critical: float = 0.90

    # Durée de cooldown après CRITICAL (secondes)
    cooldown_seconds: int = 300

    # Facteur de réduction de taille en WARNING (0.5 = moitié)
    warning_size_factor: float = 0.50


@dataclass
class RiskSnapshot:
    timestamp: float = field(default_factory=time.time)
    level: RiskLevel = RiskLevel.SAFE
    drawdown: float = 0.0
    avg_correlation: float = 0.0
    vol_ratio: float = 1.0
    net_exposure: float = 0.0
    triggered_conditions: list = field(default_factory=list)
    size_factor: float = 1.0
    message: str = ""


class GlobalRiskGate:
    """
    Vérifie 4 conditions systémiques à chaque cycle d'Annalise.
    Usage dans main_v91.py :

        gate = GlobalRiskGate(thresholds=RiskThresholds(), telegram_bot=bot)
        snapshot = await gate.check(portfolio_agent, strategy_scoreboard, market_db)
        if snapshot.level == RiskLevel.CRITICAL:
            continue  # skip le cycle complet
        execution_agent.size_factor = snapshot.size_factor
    """

    def __init__(
        self,
        thresholds: Optional[RiskThresholds] = None,
        telegram_bot=None,  # ton bot Telegram existant (optionnel)
        baseline_vol: float = 0.02,  # vol journalière de référence (à calibrer)
    ):
        self.t = thresholds or RiskThresholds()
        self.telegram = telegram_bot
        self.baseline_vol = baseline_vol

        self._last_snapshot: Optional[RiskSnapshot] = None
        self._cooldown_until: float = 0.0
        self._history: list[RiskSnapshot] = []

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    async def check(
        self,
        portfolio_agent,  # ton PortfolioAgent existant
        strategy_scoreboard,  # ton StrategyScoreboard existant
        market_db,  # ton MarketDatabase existant
    ) -> RiskSnapshot:
        """
        Retourne un RiskSnapshot avec le niveau et le size_factor à appliquer.
        Appelle cette méthode au tout début de chaque cycle dans main_v91.py.
        """

        # Cooldown actif après un CRITICAL précédent
        if time.time() < self._cooldown_until:
            remaining = int(self._cooldown_until - time.time())
            snap = RiskSnapshot(
                level=RiskLevel.CRITICAL,
                message=f"Cooldown actif — {remaining}s restantes",
                size_factor=0.0,
            )
            self._store(snap)
            return snap

        # Collecte des métriques
        metrics = await self._collect_metrics(
            portfolio_agent, strategy_scoreboard, market_db
        )

        # Évaluation
        snap = self._evaluate(metrics)

        # Actions selon le niveau
        await self._act(snap)

        self._last_snapshot = snap
        self._store(snap)
        return snap

    # ------------------------------------------------------------------
    # Collecte
    # ------------------------------------------------------------------

    async def _collect_metrics(
        self, portfolio_agent, strategy_scoreboard, market_db
    ) -> dict:
        metrics = {}

        # 1. Drawdown portefeuille
        try:
            state = portfolio_agent.get_state()
            peak = state.get("peak_value", 1.0)
            current = state.get("current_value", 1.0)
            metrics["drawdown"] = (current - peak) / peak if peak > 0 else 0.0
        except Exception as e:
            logger.warning(f"Drawdown collection failed: {e}")
            metrics["drawdown"] = 0.0

        # 2. Corrélation inter-stratégies
        try:
            active_strategies = strategy_scoreboard.get_active_strategies(top_n=20)
            returns_matrix = np.array(
                [
                    s.recent_returns
                    for s in active_strategies
                    if len(s.recent_returns) >= 20
                ]
            )
            if returns_matrix.shape[0] >= 2:
                corr_matrix = np.corrcoef(returns_matrix)
                upper = corr_matrix[np.triu_indices_from(corr_matrix, k=1)]
                metrics["avg_correlation"] = float(np.mean(np.abs(upper)))
            else:
                metrics["avg_correlation"] = 0.0
        except Exception as e:
            logger.warning(f"Correlation collection failed: {e}")
            metrics["avg_correlation"] = 0.0

        # 3. Volatilité marché relative
        try:
            market_snap = market_db.get_latest_snapshot()
            current_vol = market_snap.get("btc_vol_24h", self.baseline_vol)
            metrics["vol_ratio"] = (
                current_vol / self.baseline_vol if self.baseline_vol > 0 else 1.0
            )
        except Exception as e:
            logger.warning(f"Volatility collection failed: {e}")
            metrics["vol_ratio"] = 1.0

        # 4. Exposition nette
        try:
            state = portfolio_agent.get_state()
            total_capital = state.get("total_capital", 1.0)
            net_exposure = state.get("net_exposure", 0.0)
            metrics["net_exposure"] = (
                net_exposure / total_capital if total_capital > 0 else 0.0
            )
        except Exception as e:
            logger.warning(f"Exposure collection failed: {e}")
            metrics["net_exposure"] = 0.0

        return metrics

    # ------------------------------------------------------------------
    # Évaluation
    # ------------------------------------------------------------------

    def _evaluate(self, metrics: dict) -> RiskSnapshot:
        triggered_warning = []
        triggered_critical = []

        dd = metrics["drawdown"]
        cor = metrics["avg_correlation"]
        vol = metrics["vol_ratio"]
        exp = metrics["net_exposure"]

        # Drawdown
        if dd <= self.t.drawdown_critical:
            triggered_critical.append(f"Drawdown CRITICAL ({dd:.1%})")
        elif dd <= self.t.drawdown_warning:
            triggered_warning.append(f"Drawdown WARNING ({dd:.1%})")

        # Corrélation
        if cor >= self.t.correlation_critical:
            triggered_critical.append(f"Corrélation CRITICAL ({cor:.2f})")
        elif cor >= self.t.correlation_warning:
            triggered_warning.append(f"Corrélation WARNING ({cor:.2f})")

        # Volatilité
        if vol >= self.t.vol_multiplier_critical:
            triggered_critical.append(f"Volatilité CRITICAL ({vol:.1f}×)")
        elif vol >= self.t.vol_multiplier_warning:
            triggered_warning.append(f"Volatilité WARNING ({vol:.1f}×)")

        # Exposition
        if exp >= self.t.exposure_critical:
            triggered_critical.append(f"Exposition CRITICAL ({exp:.1%})")
        elif exp >= self.t.exposure_warning:
            triggered_warning.append(f"Exposition WARNING ({exp:.1%})")

        # Niveau final
        if triggered_critical:
            level = RiskLevel.CRITICAL
            conditions = triggered_critical + triggered_warning
            size_factor = 0.0
            message = "HARD STOP — " + " | ".join(triggered_critical)
        elif triggered_warning:
            level = RiskLevel.WARNING
            conditions = triggered_warning
            size_factor = self.t.warning_size_factor
            message = "Mode dégradé — " + " | ".join(triggered_warning)
        else:
            level = RiskLevel.SAFE
            conditions = []
            size_factor = 1.0
            message = "Tous systèmes nominaux"

        return RiskSnapshot(
            level=level,
            drawdown=dd,
            avg_correlation=cor,
            vol_ratio=vol,
            net_exposure=exp,
            triggered_conditions=conditions,
            size_factor=size_factor,
            message=message,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _act(self, snap: RiskSnapshot) -> None:
        if snap.level == RiskLevel.CRITICAL:
            logger.critical(f"[GlobalRiskGate] {snap.message}")
            self._cooldown_until = time.time() + self.t.cooldown_seconds
            await self._send_telegram(
                f"🔴 ANNALISE — HARD STOP\n{snap.message}\nCooldown: {self.t.cooldown_seconds}s"
            )

        elif snap.level == RiskLevel.WARNING:
            logger.warning(f"[GlobalRiskGate] {snap.message}")
            await self._send_telegram(
                f"🟡 ANNALISE — WARNING\n{snap.message}\nSize factor: {snap.size_factor:.0%}"
            )

        else:
            logger.debug(
                f"[GlobalRiskGate] SAFE — dd={snap.drawdown:.1%} cor={snap.avg_correlation:.2f} vol={snap.vol_ratio:.1f}× exp={snap.net_exposure:.1%}"
            )

    async def _send_telegram(self, text: str) -> None:
        if self.telegram is None:
            return
        try:
            await self.telegram.send_message(text)
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _store(self, snap: RiskSnapshot) -> None:
        self._history.append(snap)
        if len(self._history) > 1000:
            self._history = self._history[-500:]

    def get_history(self, n: int = 50) -> list[RiskSnapshot]:
        return self._history[-n:]

    def current_level(self) -> RiskLevel:
        return self._last_snapshot.level if self._last_snapshot else RiskLevel.SAFE

    def is_blocked(self) -> bool:
        return time.time() < self._cooldown_until
