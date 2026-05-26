"""
executive_override.py — Executive Override Layer

Le commandement supreme. Domine TOUTES les autres couches.

Un trade peut etre parfait :
  - Score 95
  - Conviction EXCEPTIONAL
  - Regime bull_trend
  - Toutes les gates passees

MAIS si l'une de ces conditions est violee :
  - Drawdown global trop haut
  - Capital trop expose
  - Trop de pertes recentes
  - Seuil de perte journaliere atteint
  - Perte hebdo critique

Le systeme superieur dit NON. Sans exception.

5 niveaux d'override (pas de Halte complet — ca c'est le KillSwitch) :
  CLEAR      (0) : tout OK, trade autorise
  REDUCE     (1) : taille reduite 50% — signal de prudence
  CAREFUL    (2) : taille reduite 25% — regime de surveillance
  MINIMAL    (3) : taille minimum uniquement ($30-$55) — mode survie
  VETO       (4) : aucun nouveau trade — preservation capital

Transitions :
  CLEAR    → REDUCE  : drawdown > 3% OU loss_streak >= 3
  REDUCE   → CAREFUL : drawdown > 5% OU loss_streak >= 5
  CAREFUL  → MINIMAL : drawdown > 7% OU daily_loss > 5%
  MINIMAL  → VETO    : drawdown > 10% OU daily_loss > 8%
  VETO     → MINIMAL : drawdown < 5% AND daily_loss < 3% (auto-recovery)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.risk.executive_override")


class OverrideLevel(IntEnum):
    CLEAR = 0
    REDUCE = 1
    CAREFUL = 2
    MINIMAL = 3
    VETO = 4


# Facteurs de taille par niveau
_SIZE_FACTORS = {
    OverrideLevel.CLEAR: 1.0,
    OverrideLevel.REDUCE: 0.5,
    OverrideLevel.CAREFUL: 0.25,
    OverrideLevel.MINIMAL: 0.10,
    OverrideLevel.VETO: 0.0,
}

_LEVEL_NAMES = {
    OverrideLevel.CLEAR: "CLEAR",
    OverrideLevel.REDUCE: "REDUCE",
    OverrideLevel.CAREFUL: "CAREFUL",
    OverrideLevel.MINIMAL: "MINIMAL",
    OverrideLevel.VETO: "VETO",
}


@dataclass
class OverrideVerdict:
    allowed: bool
    level: OverrideLevel
    size_factor: float
    reason: str
    triggers: list = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class SessionMetrics:
    """Metriques de session calculees en temps reel."""

    capital_start: float = 0.0
    capital_current: float = 0.0
    peak_capital: float = 0.0
    session_pnl_pct: float = 0.0  # PnL session en %
    drawdown_pct: float = 0.0  # Drawdown depuis le pic
    daily_loss_pct: float = 0.0  # Perte nette depuis minuit
    weekly_loss_pct: float = 0.0  # Perte nette 7 jours
    loss_streak: int = 0  # Pertes consecutives
    trades_today: int = 0
    trades_per_hour: float = 0.0
    open_pnl_pct: float = 0.0  # PnL latent positions ouvertes


class ExecutiveOverride:
    """
    Commandement supreme. Verifie les conditions globales AVANT tout trade.

    Usage :
        eo = ExecutiveOverride(total_capital=1000)
        eo.update(
            capital_current=950,
            session_pnl_pct=-0.05,
            loss_streak=3,
            open_pnl_pct=-0.02,
        )
        verdict = eo.check_trade(size_usd=55, conviction_score=85)
        if not verdict.allowed:
            return  # VETO
        effective_size = size_usd * verdict.size_factor
    """

    # Seuils de drawdown (% du capital total)
    DD_REDUCE = float(os.getenv("EO_DD_REDUCE", "0.03"))  # -3%  → REDUCE
    DD_CAREFUL = float(os.getenv("EO_DD_CAREFUL", "0.05"))  # -5%  → CAREFUL
    DD_MINIMAL = float(os.getenv("EO_DD_MINIMAL", "0.07"))  # -7%  → MINIMAL
    DD_VETO = float(os.getenv("EO_DD_VETO", "0.10"))  # -10% → VETO

    # Seuils de perte journaliere
    DAILY_REDUCE = float(os.getenv("EO_DAILY_REDUCE", "0.02"))
    DAILY_CAREFUL = float(os.getenv("EO_DAILY_CAREFUL", "0.03"))
    DAILY_MINIMAL = float(os.getenv("EO_DAILY_MINIMAL", "0.05"))
    DAILY_VETO = float(os.getenv("EO_DAILY_VETO", "0.08"))

    # Seuils de pertes consecutives
    STREAK_REDUCE = int(os.getenv("EO_STREAK_REDUCE", "3"))
    STREAK_CAREFUL = int(os.getenv("EO_STREAK_CAREFUL", "5"))
    STREAK_MINIMAL = int(os.getenv("EO_STREAK_MINIMAL", "7"))
    STREAK_VETO = int(os.getenv("EO_STREAK_VETO", "10"))

    # Seuils de trades par heure (anti-overtrading)
    MAX_TRADES_HOUR = int(os.getenv("EO_MAX_TRADES_HOUR", "6"))

    # PnL latent critique (perte sur positions ouvertes)
    OPEN_PNL_CAREFUL = float(os.getenv("EO_OPEN_PNL_CAREFUL", "-0.05"))
    OPEN_PNL_MINIMAL = float(os.getenv("EO_OPEN_PNL_MINIMAL", "-0.08"))
    OPEN_PNL_VETO = float(os.getenv("EO_OPEN_PNL_VETO", "-0.12"))

    # Recovery automatique
    DD_RECOVERY = float(os.getenv("EO_DD_RECOVERY", "0.04"))  # VETO → MINIMAL
    DAILY_RECOVERY = float(os.getenv("EO_DAILY_RECOVERY", "0.02"))

    def __init__(
        self,
        total_capital: float = 1000.0,
        on_level_change: Optional[Callable] = None,
    ) -> None:
        self._capital = total_capital
        self._on_change = on_level_change
        self._level = OverrideLevel.CLEAR
        self._metrics = SessionMetrics(
            capital_start=total_capital,
            capital_current=total_capital,
            peak_capital=total_capital,
        )
        self._last_check_ts = time.time()
        self._trade_timestamps: list[float] = []

    def update_capital(self, capital: float) -> None:
        self._capital = max(1.0, capital)
        self._metrics.capital_current = capital
        if capital > self._metrics.peak_capital:
            self._metrics.peak_capital = capital
        peak = self._metrics.peak_capital
        self._metrics.drawdown_pct = max(0.0, (peak - capital) / peak) if peak else 0.0

    def update(
        self,
        capital_current: float = None,
        session_pnl_pct: float = None,
        daily_loss_pct: float = None,
        loss_streak: int = None,
        open_pnl_pct: float = None,
        trades_today: int = None,
    ) -> None:
        """Met a jour les metriques de session."""
        m = self._metrics
        if capital_current is not None:
            self.update_capital(capital_current)
        if session_pnl_pct is not None:
            m.session_pnl_pct = session_pnl_pct
        if daily_loss_pct is not None:
            m.daily_loss_pct = (
                abs(daily_loss_pct) if daily_loss_pct < 0 else daily_loss_pct
            )
        if loss_streak is not None:
            m.loss_streak = loss_streak
        if open_pnl_pct is not None:
            m.open_pnl_pct = open_pnl_pct
        if trades_today is not None:
            m.trades_today = trades_today

        # Calcul trades/heure depuis la fenetre glissante
        now = time.time()
        self._trade_timestamps = [t for t in self._trade_timestamps if now - t < 3600]
        m.trades_per_hour = len(self._trade_timestamps)

        # Recalculer le niveau
        self._recalculate_level()

    def record_trade(self) -> None:
        """A appeler a chaque ordre execute."""
        self._trade_timestamps.append(time.time())
        self._metrics.trades_today += 1
        self._metrics.trades_per_hour = len(
            [t for t in self._trade_timestamps if time.time() - t < 3600]
        )

    # ── Verification principale ───────────────────────────────────────────────

    def check_trade(
        self,
        size_usd: float = 0.0,
        conviction_score: float = 50.0,
    ) -> OverrideVerdict:
        """
        Retourne un verdict avec le facteur de taille autorise.
        VETO = aucun trade autorise, independamment de tout signal.
        """
        level = self._level
        factor = _SIZE_FACTORS[level]
        allowed = level < OverrideLevel.VETO
        triggers = self._active_triggers()

        if level == OverrideLevel.VETO:
            reason = (
                f"VETO EXECUTIF — {triggers[0] if triggers else 'protection capital'}"
            )
        elif level >= OverrideLevel.MINIMAL:
            reason = f"MINIMAL — taille x{factor:.0%} | {' | '.join(triggers[:2])}"
        elif level >= OverrideLevel.CAREFUL:
            reason = f"CAREFUL — taille x{factor:.0%} | {' | '.join(triggers[:2])}"
        elif level >= OverrideLevel.REDUCE:
            reason = f"REDUCE — taille x{factor:.0%} | {' | '.join(triggers[:2])}"
        else:
            reason = "CLEAR"

        return OverrideVerdict(
            allowed=allowed,
            level=level,
            size_factor=factor,
            reason=reason,
            triggers=triggers,
        )

    def current_level(self) -> OverrideLevel:
        return self._level

    def is_clear(self) -> bool:
        return self._level == OverrideLevel.CLEAR

    def metrics_snapshot(self) -> dict:
        m = self._metrics
        return {
            "level": _LEVEL_NAMES[self._level],
            "drawdown_pct": round(m.drawdown_pct * 100, 2),
            "daily_loss_pct": round(m.daily_loss_pct * 100, 2),
            "loss_streak": m.loss_streak,
            "open_pnl_pct": round(m.open_pnl_pct * 100, 2),
            "trades_today": m.trades_today,
            "trades_per_hour": m.trades_per_hour,
            "capital_current": round(m.capital_current, 2),
            "size_factor": _SIZE_FACTORS[self._level],
        }

    # ── Logique interne ───────────────────────────────────────────────────────

    def _recalculate_level(self) -> None:
        old_level = self._level
        new_level = self._compute_level()
        if new_level != old_level:
            self._level = new_level
            _log.warning(
                "[ExecutiveOverride] %s -> %s | triggers: %s",
                _LEVEL_NAMES[old_level],
                _LEVEL_NAMES[new_level],
                " | ".join(self._active_triggers()),
            )
            if self._on_change:
                try:
                    self._on_change(old_level, new_level, self._active_triggers())
                except Exception as exc:
                    _log.debug("[EO] callback erreur: %s", exc)

    def _compute_level(self) -> OverrideLevel:
        m = self._metrics

        # VETO — conditions absolues
        if (
            m.drawdown_pct >= self.DD_VETO
            or m.daily_loss_pct >= self.DAILY_VETO
            or m.loss_streak >= self.STREAK_VETO
            or m.open_pnl_pct <= self.OPEN_PNL_VETO
        ):
            return OverrideLevel.VETO

        # Recovery : VETO → MINIMAL si amelioration
        if self._level == OverrideLevel.VETO:
            if (
                m.drawdown_pct <= self.DD_RECOVERY
                and m.daily_loss_pct <= self.DAILY_RECOVERY
            ):
                return OverrideLevel.MINIMAL
            return OverrideLevel.VETO

        # MINIMAL
        if (
            m.drawdown_pct >= self.DD_MINIMAL
            or m.daily_loss_pct >= self.DAILY_MINIMAL
            or m.loss_streak >= self.STREAK_MINIMAL
            or m.open_pnl_pct <= self.OPEN_PNL_MINIMAL
        ):
            return OverrideLevel.MINIMAL

        # CAREFUL
        if (
            m.drawdown_pct >= self.DD_CAREFUL
            or m.daily_loss_pct >= self.DAILY_CAREFUL
            or m.loss_streak >= self.STREAK_CAREFUL
            or m.open_pnl_pct <= self.OPEN_PNL_CAREFUL
        ):
            return OverrideLevel.CAREFUL

        # REDUCE
        if (
            m.drawdown_pct >= self.DD_REDUCE
            or m.daily_loss_pct >= self.DAILY_REDUCE
            or m.loss_streak >= self.STREAK_REDUCE
            or m.trades_per_hour > self.MAX_TRADES_HOUR
        ):
            return OverrideLevel.REDUCE

        return OverrideLevel.CLEAR

    def _active_triggers(self) -> list[str]:
        m = self._metrics
        triggers = []
        if m.drawdown_pct >= self.DD_REDUCE:
            triggers.append(f"DD={m.drawdown_pct:.1%}")
        if m.daily_loss_pct >= self.DAILY_REDUCE:
            triggers.append(f"Daily={m.daily_loss_pct:.1%}")
        if m.loss_streak >= self.STREAK_REDUCE:
            triggers.append(f"Streak={m.loss_streak}")
        if m.open_pnl_pct <= self.OPEN_PNL_CAREFUL:
            triggers.append(f"OpenPnL={m.open_pnl_pct:.1%}")
        if m.trades_per_hour > self.MAX_TRADES_HOUR:
            triggers.append(f"Overtrading={m.trades_per_hour:.0f}/h")
        return triggers or ["OK"]
