"""
risk_governor.py — Machine à états de risque globale (P7).

États : NORMAL → DEFENSIVE → RISK_OFF → RECOVERY → AGGRESSIVE
Chaque état modifie : size_multiplier, threshold_delta, allow_new_trades.

Inclut VolatilityEmergencyMode (ATR > 3× médiane → suspension trades).
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass
from enum import Enum

from observability.json_logger import get_logger

_log = get_logger("risk_governor")


class RiskState(Enum):
    NORMAL = "normal"
    DEFENSIVE = "defensive"
    RISK_OFF = "risk_off"
    RECOVERY = "recovery"
    AGGRESSIVE = "aggressive"


# Multiplicateurs de taille par état
_SIZE_MUL: dict[RiskState, float] = {
    RiskState.NORMAL: 1.0,
    RiskState.DEFENSIVE: 0.5,
    RiskState.RISK_OFF: 0.0,
    RiskState.RECOVERY: 0.25,
    RiskState.AGGRESSIVE: 1.2,
}

# Delta threshold par état (appliqué sur le gate)
_THRESHOLD_DELTA: dict[RiskState, int] = {
    RiskState.NORMAL: 0,
    RiskState.DEFENSIVE: 0,
    RiskState.RISK_OFF: +15,  # bloque tout
    RiskState.RECOVERY: +3,
    RiskState.AGGRESSIVE: -2,
}


@dataclass
class GovernorSnapshot:
    state: str
    size_multiplier: float
    threshold_delta: int
    allow_new_trades: bool
    drawdown_pct: float
    consecutive_losses: int
    vol_emergency: bool
    cycles_in_state: int
    cycles_until_eligible: int


class RiskGovernor:
    """Machine à états de risque — pilote le comportement global du système."""

    # Seuils de drawdown
    DD_DEFENSIVE = float(os.getenv("RG_DD_DEFENSIVE", "0.03"))  # 3%
    DD_RISK_OFF = float(os.getenv("RG_DD_RISK_OFF", "0.06"))  # 6%

    # Seuils de volatilité (ATR ratio)
    VOL_DEFENSIVE = float(os.getenv("RG_VOL_DEFENSIVE", "2.0"))  # 2× ATR médian
    VOL_EMERGENCY = float(os.getenv("RG_VOL_EMERGENCY", "3.0"))  # 3× ATR médian

    # Hystérésis (cycles minimum entre deux transitions)
    MIN_CYCLES = int(os.getenv("RG_MIN_CYCLES", "5"))

    # Conditions de sortie
    RECOVERY_STABLE_CYCLES = int(os.getenv("RG_RECOVERY_STABLE", "20"))
    RECOVERY_PNL_CYCLES = int(os.getenv("RG_RECOVERY_PNL_CYCLES", "15"))
    RISK_OFF_SAFE_CYCLES = int(os.getenv("RG_RISK_OFF_SAFE_CYCLES", "10"))
    AGGRESSIVE_PNL_CYCLES = int(os.getenv("RG_AGGRESSIVE_PNL_CYCLES", "10"))

    # VolatilityEmergencyMode
    VOL_EMERGENCY_COOLDOWN = int(os.getenv("RG_VOL_EMERGENCY_COOLDOWN", "5"))

    def __init__(self) -> None:
        self._state = RiskState.NORMAL
        self._cycles_in_state = 0
        self._last_transition_cycle = 0
        self._current_cycle = 0

        # Historiques
        self._atr_history: deque[float] = deque(maxlen=50)
        self._pnl_history: deque[float] = deque(maxlen=30)
        self._loss_free_cycles = 0
        self._positive_pnl_cycles = 0

        # VolatilityEmergencyMode
        self._vol_emergency = False
        self._vol_emergency_cooldown = 0

    # ── API publique ──────────────────────────────────────────────────────────

    def update(
        self,
        cycle: int,
        drawdown_pct: float,
        consecutive_losses: int,
        atr_current: float = 0.0,
        cycle_pnl_pct: float = 0.0,
        regime: str = "unknown",
    ) -> GovernorSnapshot:
        """
        Met à jour la machine à états. À appeler une fois par cycle.

        Args:
            cycle: numéro de cycle courant
            drawdown_pct: drawdown courant (0.03 = 3%)
            consecutive_losses: pertes consécutives
            atr_current: ATR ratio courant (0 si indisponible)
            cycle_pnl_pct: PnL du cycle courant (positif = gain)
            regime: régime de marché courant
        """
        self._current_cycle = cycle
        self._cycles_in_state += 1

        # ── Enregistrer historiques
        if atr_current > 0:
            self._atr_history.append(atr_current)
        self._pnl_history.append(cycle_pnl_pct)

        if cycle_pnl_pct >= 0:
            self._loss_free_cycles += 1
            self._positive_pnl_cycles += 1
        else:
            self._loss_free_cycles = 0
            self._positive_pnl_cycles = 0

        # ── VolatilityEmergencyMode
        self._update_vol_emergency(atr_current)

        # ── Transitions d'état
        if self._can_transition():
            self._evaluate_transitions(
                drawdown_pct, consecutive_losses, atr_current, regime
            )

        _log.debug(
            "[RiskGovernor] cycle=%d state=%s dd=%.2f%% consec=%d vol_em=%s",
            cycle,
            self._state.value,
            drawdown_pct * 100,
            consecutive_losses,
            self._vol_emergency,
        )

        return self.snapshot(drawdown_pct, consecutive_losses)

    @property
    def state(self) -> RiskState:
        return self._state

    @property
    def allow_new_trades(self) -> bool:
        return self._state != RiskState.RISK_OFF and not self._vol_emergency

    @property
    def size_multiplier(self) -> float:
        return _SIZE_MUL[self._state]

    @property
    def threshold_delta(self) -> int:
        return _THRESHOLD_DELTA[self._state]

    @property
    def vol_emergency(self) -> bool:
        return self._vol_emergency

    def snapshot(
        self, drawdown_pct: float = 0.0, consecutive_losses: int = 0
    ) -> GovernorSnapshot:
        cycles_until = max(0, self.MIN_CYCLES - self._cycles_in_state)
        return GovernorSnapshot(
            state=self._state.value,
            size_multiplier=self.size_multiplier,
            threshold_delta=self.threshold_delta,
            allow_new_trades=self.allow_new_trades,
            drawdown_pct=drawdown_pct,
            consecutive_losses=consecutive_losses,
            vol_emergency=self._vol_emergency,
            cycles_in_state=self._cycles_in_state,
            cycles_until_eligible=cycles_until,
        )

    # ── Logique interne ───────────────────────────────────────────────────────

    def _can_transition(self) -> bool:
        return self._cycles_in_state >= self.MIN_CYCLES

    def _atr_median(self) -> float:
        if not self._atr_history:
            return 0.0
        s = sorted(self._atr_history)
        mid = len(s) // 2
        return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

    def _vol_ratio(self, atr_current: float) -> float:
        med = self._atr_median()
        if med <= 0 or atr_current <= 0:
            return 0.0
        return atr_current / med

    def _vol_is_known(self, atr_current: float) -> bool:
        return atr_current > 0 and self._atr_median() > 0

    def _update_vol_emergency(self, atr_current: float) -> None:
        ratio = self._vol_ratio(atr_current)
        if ratio >= self.VOL_EMERGENCY:
            if not self._vol_emergency:
                _log.warning(
                    "[RiskGovernor] VOLATILITY EMERGENCY — ATR ratio=%.1f × médiane",
                    ratio,
                )
            self._vol_emergency = True
            self._vol_emergency_cooldown = self.VOL_EMERGENCY_COOLDOWN
        elif self._vol_emergency:
            self._vol_emergency_cooldown -= 1
            if self._vol_emergency_cooldown < 0:
                _log.info(
                    "[RiskGovernor] Volatilité revenue sous seuil — urgence levée"
                )
                self._vol_emergency = False

    def _transition_to(self, new_state: RiskState) -> None:
        if new_state == self._state:
            return
        _log.warning(
            "[RiskGovernor] TRANSITION %s → %s (cycle %d, état depuis %d cycles)",
            self._state.value,
            new_state.value,
            self._current_cycle,
            self._cycles_in_state,
        )
        self._state = new_state
        self._cycles_in_state = 0
        self._last_transition_cycle = self._current_cycle

    def _evaluate_transitions(
        self,
        drawdown_pct: float,
        consecutive_losses: int,
        atr_current: float,
        regime: str,
    ) -> None:
        vol_known = self._vol_is_known(atr_current)
        vol_ratio = self._vol_ratio(atr_current)
        vol_hot = vol_known and vol_ratio > self.VOL_DEFENSIVE
        vol_calm = vol_known and vol_ratio < self.VOL_DEFENSIVE
        s = self._state

        if s == RiskState.NORMAL:
            if drawdown_pct > self.DD_DEFENSIVE or vol_hot:
                self._transition_to(RiskState.DEFENSIVE)
            elif (
                regime in ("bull_trend", "bear_trend")
                and vol_calm
                and self._positive_pnl_cycles >= self.AGGRESSIVE_PNL_CYCLES
            ):
                self._transition_to(RiskState.AGGRESSIVE)

        elif s == RiskState.DEFENSIVE:
            if drawdown_pct > self.DD_RISK_OFF or consecutive_losses >= 3:
                self._transition_to(RiskState.RISK_OFF)
            elif drawdown_pct <= self.DD_DEFENSIVE * 0.5 and (
                not vol_known or vol_calm
            ):
                self._transition_to(RiskState.NORMAL)

        elif s == RiskState.RISK_OFF:
            if self._loss_free_cycles >= self.RISK_OFF_SAFE_CYCLES or vol_calm:
                self._transition_to(RiskState.RECOVERY)

        elif s == RiskState.RECOVERY:
            if (
                self._cycles_in_state >= self.RECOVERY_STABLE_CYCLES
                or self._positive_pnl_cycles >= self.RECOVERY_PNL_CYCLES
            ):
                self._transition_to(RiskState.NORMAL)
            elif drawdown_pct > self.DD_RISK_OFF or consecutive_losses >= 3:
                self._transition_to(RiskState.RISK_OFF)

        elif s == RiskState.AGGRESSIVE:
            if drawdown_pct > self.DD_DEFENSIVE or vol_hot:
                self._transition_to(RiskState.DEFENSIVE)
            elif regime not in ("bull_trend", "bear_trend"):
                self._transition_to(RiskState.NORMAL)
