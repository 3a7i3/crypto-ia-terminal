"""
capital_throttle.py — Throttle progressif taille des positions selon le drawdown (P7).

- Drawdown > 5% : réduction linéaire de 10% par palier de 1% de drawdown
- Drawdown > 10% : arrêt complet (factor = 0)
- Retour à la normale : rampe inverse sur 5 cycles minimum
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("capital_throttle")


class CapitalThrottle:
    """Réduit progressivement la taille des positions en fonction du drawdown."""

    SOFT_DD = float(os.getenv("CT_SOFT_DD", "0.05"))  # 5% → début réduction
    HARD_DD = float(os.getenv("CT_HARD_DD", "0.10"))  # 10% → arrêt complet
    REDUCTION_PER_PCT = float(
        os.getenv("CT_REDUCTION", "0.10")
    )  # 10% réduction / 1% dd
    RAMP_RATE = float(os.getenv("CT_RAMP_RATE", "0.20"))  # récupération 20%/cycle
    MIN_OPERATIONAL = float(os.getenv("CT_MIN_OPERATIONAL", "0.10"))  # plancher 10%

    def __init__(self) -> None:
        self._factor: float = 1.0
        self._peak_capital: float = 0.0
        self._current_drawdown: float = 0.0
        self._throttle_active: bool = False

    def update(self, capital: float) -> float:
        """
        Met à jour le throttle en fonction du capital courant.
        Retourne le factor (0.0 à 1.0) à appliquer à la taille des ordres.
        """
        if capital > self._peak_capital:
            self._peak_capital = capital

        if self._peak_capital <= 0:
            return 1.0

        self._current_drawdown = max(
            0.0, (self._peak_capital - capital) / self._peak_capital
        )
        dd = self._current_drawdown

        if dd >= self.HARD_DD:
            target = 0.0
        elif dd > self.SOFT_DD:
            excess_pct = (dd - self.SOFT_DD) * 100  # en %
            reduction = min(
                excess_pct * self.REDUCTION_PER_PCT, 1.0 - self.MIN_OPERATIONAL
            )
            target = max(self.MIN_OPERATIONAL, 1.0 - reduction)
        else:
            target = 1.0

        # Rampe : vers le haut doucement, vers le bas immédiatement
        if target < self._factor:
            self._factor = target  # dégradation immédiate
        else:
            self._factor = min(1.0, self._factor + self.RAMP_RATE)

        was_active = self._throttle_active
        self._throttle_active = self._factor < 1.0

        if self._throttle_active and not was_active:
            log.warning(
                "[CapitalThrottle] Activé — dd=%.1f%% → factor=%.2f",
                dd * 100,
                self._factor,
            )
        elif not self._throttle_active and was_active:
            log.info("[CapitalThrottle] Désactivé — capital revenu à la normale")

        return self._factor

    @property
    def factor(self) -> float:
        return self._factor

    @property
    def allow_trades(self) -> bool:
        return self._factor > 0.0

    @property
    def drawdown_pct(self) -> float:
        return self._current_drawdown

    def snapshot(self) -> dict:
        return {
            "factor": round(self._factor, 3),
            "drawdown_pct": round(self._current_drawdown * 100, 2),
            "peak_capital": round(self._peak_capital, 2),
            "throttle_active": self._throttle_active,
            "allow_trades": self.allow_trades,
        }
