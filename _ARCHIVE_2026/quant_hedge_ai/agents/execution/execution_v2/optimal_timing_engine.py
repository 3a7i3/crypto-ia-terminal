"""
optimal_timing_engine.py — Execution Timing Optimizer

Détermine le meilleur moment pour exécuter un ordre en surveillant :
- la microstructure (imbalance favorable)
- le spread (attendre un resserrement)
- la volatilité (éviter les pics)
- les patterns temporels (liquidité par heure)
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TimingSignal:
    symbol: str
    side: str
    timestamp: float

    execute_now: bool = False           # True = conditions favorables maintenant
    confidence: float = 0.5            # [0,1]
    wait_seconds: float = 0.0          # attente recommandée si execute_now=False
    reason: str = ""

    # Conditions évaluées
    spread_ok: bool = True
    imbalance_favorable: bool = True
    volatility_ok: bool = True
    liquidity_period_ok: bool = True

    score: float = 0.0                  # [-1,+1] : +1 = conditions parfaites

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class OptimalTimingEngine:
    """
    Évalue les conditions d'exécution et recommande le timing optimal.
    Maintient un historique de spread/imbalance pour détecter les améliorations.
    """

    MAX_WAIT_SECONDS = 120.0        # attente max avant exécution forcée
    SPREAD_IMPROVEMENT_THRESHOLD = 0.8  # attendre que le spread revienne à 80% du min récent

    def __init__(self) -> None:
        self._spread_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=30))
        self._imbalance_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=30))
        self._wait_start: dict[str, float] = {}

    def evaluate(
        self,
        symbol: str,
        side: str,
        spread_bps: float,
        ob_imbalance: float,
        atr_pct: float,
        urgency: float = 0.5,
    ) -> TimingSignal:
        """
        Évalue si le moment est favorable pour exécuter.
        urgency=1 → exécute immédiatement sans attendre.
        """
        self._spread_history[symbol].append(spread_bps)
        self._imbalance_history[symbol].append(ob_imbalance)

        sig = TimingSignal(
            symbol=symbol,
            side=side,
            timestamp=time.time(),
        )

        # Urgence maximale → exécuter maintenant
        if urgency >= 0.95:
            sig.execute_now = True
            sig.confidence = 0.9
            sig.reason = "Urgence maximale — exécution immédiate"
            sig.score = 1.0
            return sig

        # Timeout de sécurité : si on attend depuis trop longtemps → exécuter
        wait_start = self._wait_start.get(symbol, 0.0)
        if wait_start and (time.time() - wait_start) > self.MAX_WAIT_SECONDS:
            sig.execute_now = True
            sig.confidence = 0.6
            sig.reason = f"Timeout {self.MAX_WAIT_SECONDS:.0f}s — exécution forcée"
            sig.score = 0.5
            self._wait_start.pop(symbol, None)
            return sig

        # Évaluation des conditions
        sig.spread_ok = self._check_spread(symbol, spread_bps)
        sig.imbalance_favorable = self._check_imbalance(side, ob_imbalance)
        sig.volatility_ok = atr_pct < 0.03
        sig.liquidity_period_ok = self._check_liquidity_period()

        conditions_met = sum([sig.spread_ok, sig.imbalance_favorable, sig.volatility_ok, sig.liquidity_period_ok])

        # Score global
        sig.score = (
            (1.0 if sig.spread_ok else -0.3) +
            (0.5 if sig.imbalance_favorable else -0.2) +
            (0.3 if sig.volatility_ok else -0.3) +
            (0.2 if sig.liquidity_period_ok else 0.0)
        ) / 2.0
        sig.score = max(-1.0, min(1.0, sig.score))

        # Décision
        required_conditions = 3 if urgency < 0.5 else 2
        sig.execute_now = conditions_met >= required_conditions

        if sig.execute_now:
            sig.confidence = 0.7 + (conditions_met - required_conditions) * 0.1
            sig.reason = f"{conditions_met}/4 conditions favorables"
            self._wait_start.pop(symbol, None)
        else:
            if symbol not in self._wait_start:
                self._wait_start[symbol] = time.time()
            sig.wait_seconds = self._estimate_wait(symbol, spread_bps)
            sig.confidence = 0.5
            sig.reason = self._describe_issues(sig)

        return sig

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _check_spread(self, symbol: str, current_spread: float) -> bool:
        hist = list(self._spread_history[symbol])
        if len(hist) < 5:
            return True
        min_spread = min(hist)
        return current_spread <= min_spread * (1.0 / self.SPREAD_IMPROVEMENT_THRESHOLD)

    def _check_imbalance(self, side: str, imbalance: float) -> bool:
        if side == "buy":
            return imbalance >= -0.1    # pas de forte pression vente
        else:
            return imbalance <= 0.1     # pas de forte pression achat

    def _check_liquidity_period(self) -> bool:
        hour = time.gmtime().tm_hour
        # Heures de bonne liquidité : NY (13-21 UTC) et Londres (7-16 UTC)
        good_hours = set(range(7, 22))
        return hour in good_hours

    def _estimate_wait(self, symbol: str, current_spread: float) -> float:
        hist = list(self._spread_history[symbol])
        if len(hist) < 5:
            return 10.0
        min_spread = min(hist)
        if current_spread > min_spread * 1.5:
            return 30.0
        return 15.0

    def _describe_issues(self, sig: TimingSignal) -> str:
        issues = []
        if not sig.spread_ok:
            issues.append("spread élevé")
        if not sig.imbalance_favorable:
            issues.append("imbalance défavorable")
        if not sig.volatility_ok:
            issues.append("volatilité élevée")
        if not sig.liquidity_period_ok:
            issues.append("heure peu liquide")
        return "Attente: " + ", ".join(issues) if issues else "Conditions sub-optimales"
