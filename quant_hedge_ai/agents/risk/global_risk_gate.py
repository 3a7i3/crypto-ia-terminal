"""
global_risk_gate.py — Vérification pré-trade en 5 conditions (Phase 7).

Checklist avant tout ordre live :
  1. Session non halted (SessionGuard)
  2. Drawdown de session acceptable (DrawdownGuard)
  3. Score du signal suffisant (LiveSignalEngine)
  4. Signal confirmé multi-timeframes
  5. Régime de marché non blacklisté

Si au moins une condition échoue → ordre BLOQUÉ + raison détaillée.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_CONDITION_NAMES = [
    "session_active",
    "drawdown_ok",
    "signal_score",
    "signal_confirmed",
    "regime_allowed",
]


@dataclass
class GateResult:
    """Résultat de la vérification GlobalRiskGate."""

    allowed: bool
    conditions: dict[str, bool] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "conditions": self.conditions,
            "failed": self.failed,
            "warnings": self.warnings,
        }

    def summary(self) -> str:
        if self.allowed:
            return f"GATE PASS — toutes les conditions OK ({len(self.conditions)}/5)"
        return f"GATE BLOCK — {len(self.failed)} condition(s) échouée(s): {', '.join(self.failed)}"


class GlobalRiskGate:
    """
    Checklist pré-trade en 5 conditions.

    Usage:
        gate = GlobalRiskGate(
            session_guard=guard,
            drawdown_guard=dg,
            min_signal_score=70,
            blacklisted_regimes={"flash_crash"},
        )
        result = gate.check(signal_result, portfolio_drawdown=0.03)
        if not result.allowed:
            return  # bloquer l'ordre
    """

    def __init__(
        self,
        session_guard=None,
        drawdown_guard=None,
        min_signal_score: int = 70,
        require_confirmed: bool = True,
        blacklisted_regimes: set[str] | None = None,
        max_portfolio_drawdown: float = 0.10,
    ) -> None:
        self._session_guard = session_guard
        self._drawdown_guard = drawdown_guard
        self.min_signal_score = min_signal_score
        self.require_confirmed = require_confirmed
        self.blacklisted_regimes: set[str] = blacklisted_regimes or set()
        self.max_portfolio_drawdown = max_portfolio_drawdown

    # ── API principale ─────────────────────────────────────────────────────────

    def check(
        self,
        signal_result,
        portfolio_drawdown: float = 0.0,
        order_size_usd: float = 0.0,
    ) -> GateResult:
        """
        Vérifie les 5 conditions pré-trade.

        Args:
            signal_result       : SignalResult du LiveSignalEngine
            portfolio_drawdown  : drawdown courant du portefeuille (0.0-1.0)
            order_size_usd      : taille de l'ordre en USD (pour SessionGuard)

        Returns:
            GateResult avec allowed=True si toutes les conditions passent
        """
        conditions: dict[str, bool] = {}
        failed: list[str] = []
        warnings: list[str] = []

        # ① Session active
        c1 = self._check_session(order_size_usd, signal_result)
        conditions["session_active"] = c1
        if not c1:
            failed.append("session_active")

        # ② Drawdown acceptable
        c2 = self._check_drawdown(portfolio_drawdown)
        conditions["drawdown_ok"] = c2
        if not c2:
            failed.append("drawdown_ok")
        elif portfolio_drawdown > self.max_portfolio_drawdown * 0.7:
            warnings.append(f"Drawdown {portfolio_drawdown:.1%} proche du seuil max {self.max_portfolio_drawdown:.1%}")

        # ③ Score suffisant
        score = getattr(signal_result, "score", 0)
        c3 = score >= self.min_signal_score
        conditions["signal_score"] = c3
        if not c3:
            failed.append(f"signal_score ({score}<{self.min_signal_score})")

        # ④ Signal confirmé MTF
        confirmed = getattr(signal_result, "confirmed", False)
        c4 = confirmed if self.require_confirmed else True
        conditions["signal_confirmed"] = c4
        if not c4:
            failed.append("signal_confirmed")

        # ⑤ Régime non blacklisté
        regime = getattr(signal_result, "regime", "unknown")
        c5 = regime not in self.blacklisted_regimes
        conditions["regime_allowed"] = c5
        if not c5:
            failed.append(f"regime_blacklisted ({regime})")

        allowed = len(failed) == 0
        result = GateResult(allowed=allowed, conditions=conditions,
                            failed=failed, warnings=warnings)

        log_fn = logger.info if allowed else logger.warning
        log_fn("[GlobalRiskGate] %s", result.summary())
        if warnings:
            for w in warnings:
                logger.warning("[GlobalRiskGate] ⚠️  %s", w)

        self._emit_event(result, signal_result)
        return result

    def blacklist_regime(self, regime: str) -> None:
        self.blacklisted_regimes.add(regime)

    def unblacklist_regime(self, regime: str) -> None:
        self.blacklisted_regimes.discard(regime)

    # ── Checks internes ───────────────────────────────────────────────────────

    def _check_session(self, order_size_usd: float, signal_result) -> bool:
        if self._session_guard is None:
            return True
        try:
            symbol = getattr(signal_result, "symbol", "UNKNOWN")
            action = getattr(signal_result, "signal", "BUY")
            self._session_guard.check_order(symbol, action, order_size_usd)
            return True
        except Exception as exc:
            logger.warning("[GlobalRiskGate] SessionGuard: %s", exc)
            return False

    def _check_drawdown(self, portfolio_drawdown: float) -> bool:
        if self._drawdown_guard is not None:
            adjusted = self._drawdown_guard.adjust_position_size(portfolio_drawdown)
            if adjusted <= 0.1:
                return False
        return portfolio_drawdown <= self.max_portfolio_drawdown

    def _emit_event(self, result: GateResult, signal_result) -> None:
        if result.allowed:
            return
        try:
            from event_bus.bus import EventBus
            from event_bus.events import SessionHaltEvent
            EventBus.get().emit(
                SessionHaltEvent(
                    reason="; ".join(result.failed),
                    halt_duration_seconds=0.0,
                    source="global_risk_gate",
                )
            )
        except Exception as exc:
            logger.warning("[GlobalRiskGate] Erreur emission evenement halt: %s", exc)
