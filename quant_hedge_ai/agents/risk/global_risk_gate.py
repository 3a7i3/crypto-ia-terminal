"""
global_risk_gate.py — Vérification pré-trade en 5 conditions (Phase 7).

Checklist avant tout ordre live :
  1. Session non halted (SessionGuard)
  2. Drawdown de session acceptable (DrawdownGuard)
  3. Score du signal suffisant (LiveSignalEngine)
  4. Signal confirmé multi-timeframes
  5. Régime de marché non blacklisté

Si au moins une condition échoue → ordre BLOQUÉ + raison détaillée.

Migration DecisionPacket :
  - GlobalRiskGate.check_packet() — API souveraine sur DecisionPacket.
    C'est ICI et UNIQUEMENT ICI que packet.reject() est appelé en flux normal.
    Chaque rejet est tracé dans state_history + reasoning du packet.
  - check() classique préservé pour compatibilité ascendante.

Souveraineté : le risk_gate lit les opinions advisory (lse_actionable,
conviction, conviction_size_factor) sans en être gouverné.
Il applique les règles de gouvernance et décide seul.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from quant_hedge_ai.agents.intelligence.market_regime_classifier import (
        MarketRegimeClassifier as _RegimeClassifier,
    )

    _regime_clf = _RegimeClassifier()
except Exception:
    _regime_clf = None  # type: ignore[assignment]

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
        return (
            f"GATE BLOCK — {len(self.failed)} condition(s)"
            f" échouée(s): {', '.join(self.failed)}"
        )


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
        safe_mode: bool = False,
    ) -> None:
        self._session_guard = session_guard
        self._drawdown_guard = drawdown_guard
        self.min_signal_score = min_signal_score  # base statique (env var)
        self.require_confirmed = require_confirmed
        self.blacklisted_regimes: set[str] = (blacklisted_regimes or set()) | {
            "unknown"
        }
        self.max_portfolio_drawdown = max_portfolio_drawdown
        self._safe_mode = safe_mode
        # Calibration adaptative
        self._regret_delta: int = 0  # feedback du RegretEngine (ATE/P6)
        self._governor_delta: int = 0  # delta d'état RiskGovernor (P7)
        self._last_regime: str = "unknown"  # régime courant pour le log
        self._transition_threshold: int | None = None  # override rampe RegimeSmoother
        # Plancher absolu : les ajustements régime peuvent descendre jusqu'ici
        import os as _os

        self._absolute_floor: int = int(_os.getenv("REGIME_ABSOLUTE_FLOOR", "55"))

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
            warnings.append(
                f"Drawdown {portfolio_drawdown:.1%} proche"
                f" du seuil max {self.max_portfolio_drawdown:.1%}"
            )

        # ③ Score suffisant — seuil régime-aware
        score = getattr(signal_result, "score", 0)
        regime_str = getattr(signal_result, "regime", "unknown")
        effective_min = self._effective_min_score(regime_str)
        c3 = score >= effective_min
        conditions["signal_score"] = c3
        if not c3:
            failed.append(f"signal_score ({score}<{effective_min})")

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
        result = GateResult(
            allowed=allowed, conditions=conditions, failed=failed, warnings=warnings
        )

        log_fn = logger.info if allowed else logger.warning
        log_fn("[GlobalRiskGate] %s", result.summary())
        if warnings:
            for w in warnings:
                logger.warning("[GlobalRiskGate] ⚠️  %s", w)

        self._emit_event(result, signal_result)
        return result

    # ── API DecisionPacket ────────────────────────────────────────────────────

    def check_packet(
        self,
        packet,
        portfolio_drawdown: float = 0.0,
        order_size_usd: float = 0.0,
    ) -> "GateResult":
        """
        Vérification pré-trade depuis un DecisionPacket.

        SOUVERAINETÉ : c'est ici et uniquement ici que packet.reject() est
        appelé en flux normal. Chaque rejet est tracé dans state_history.

        Lit en advisory (sans en être gouverné) :
          - packet.metadata["lse_actionable"]         → recommandation LSE
          - packet.conviction                          → niveau conviction
          - packet.metadata["conviction_size_factor"]  → sizing advisory

        Args:
            packet            : DecisionPacket en état CONTEXT_ENRICHED
            portfolio_drawdown: drawdown courant du portefeuille (0.0–1.0)
            order_size_usd    : taille de l'ordre en USD (pour SessionGuard)

        Returns:
            GateResult — packet transitionne vers RISK_EVALUATED ou REJECTED
        """
        from core.decision_packet import DecisionSide, DecisionState, ReasoningCategory

        actor = "global_risk_gate"
        packet.add_agent(actor)

        conditions: dict[str, bool] = {}
        failed: list[str] = []
        warnings: list[str] = []

        # ── Guard préliminaire : direction détectée ────────────────────────
        # Un packet FLAT n'a rien à faire ici — signal HOLD confirmé.
        # Tracé séparément de la checklist pour distinguer de l'échec de score.
        if packet.side == DecisionSide.FLAT:
            packet.add_reasoning(
                actor,
                "Signal HOLD (side=FLAT) : aucune direction détectée, rejet immédiat",
                confidence_impact=-50.0,
                category=ReasoningCategory.RISK_GOVERNANCE,
            )
            packet.reject(actor, "side=FLAT — aucune direction tradeable")
            return GateResult(
                allowed=False,
                conditions={"direction_detected": False},
                failed=["direction_detected"],
                warnings=[],
            )

        # ── Lecture advisory (observabilité, pas gouvernance) ──────────────
        lse_actionable = packet.metadata.get("lse_actionable", True)
        conviction_level = packet.conviction.value  # ex. "SKIP", "LOW", ...

        # ① Session active
        c1 = self._check_session_packet(packet, order_size_usd)
        conditions["session_active"] = c1
        if not c1:
            failed.append("session_active")
            packet.add_reasoning(
                actor,
                "Session halted ou ordre refusé par SessionGuard",
                confidence_impact=-20.0,
                category=ReasoningCategory.RISK_GOVERNANCE,
            )

        # ② Drawdown acceptable
        c2 = self._check_drawdown(portfolio_drawdown)
        conditions["drawdown_ok"] = c2
        packet.features["risk_drawdown_pct"] = round(portfolio_drawdown * 100, 2)
        if not c2:
            failed.append("drawdown_ok")
            packet.add_reasoning(
                actor,
                f"Drawdown {portfolio_drawdown:.1%}"
                f" dépasse seuil max {self.max_portfolio_drawdown:.1%}",
                confidence_impact=-30.0,
                category=ReasoningCategory.RISK_GOVERNANCE,
            )
        elif portfolio_drawdown > self.max_portfolio_drawdown * 0.7:
            warn_msg = (
                f"Drawdown {portfolio_drawdown:.1%}"
                f" proche du seuil max {self.max_portfolio_drawdown:.1%}"
            )
            warnings.append(warn_msg)
            packet.add_reasoning(
                actor,
                warn_msg,
                confidence_impact=-5.0,
                category=ReasoningCategory.RISK_GOVERNANCE,
            )

        # ③ Score suffisant — seuil régime-aware + delta RegretEngine
        score = packet.confidence
        regime_str = packet.regime.value  # ex. "RANGE", "TREND_BULL"
        effective_min = self._effective_min_score(regime_str)
        c3 = score >= effective_min
        conditions["signal_score"] = c3
        if not c3:
            failed.append(f"signal_score ({score:.0f}<{effective_min})")
            packet.add_reasoning(
                actor,
                f"Score {score:.0f} insuffisant "
                f"(seuil régime={regime_str}: {effective_min})",
                confidence_impact=-15.0,
                category=ReasoningCategory.RISK_GOVERNANCE,
            )
        # LSE disait non mais score passe — noter la divergence pour le meta-learning
        if not lse_actionable and c3:
            packet.add_reasoning(
                actor,
                f"Advisory LSE=non-actionable mais"
                f" score={score:.0f} passe la gouvernance",
                confidence_impact=0.0,
                category=ReasoningCategory.RISK_GOVERNANCE,
            )

        # ④ Signal confirmé MTF
        confirmed = bool(packet.metadata.get("mtf_confirmed", False))
        c4 = confirmed if self.require_confirmed else True
        conditions["signal_confirmed"] = c4
        if not c4:
            failed.append("signal_confirmed")
            packet.add_reasoning(
                actor,
                "Signal non confirmé multi-timeframes",
                confidence_impact=-10.0,
                category=ReasoningCategory.TREND_ALIGNMENT,
            )

        # ⑤ Régime non blacklisté (MarketRegime.value dans le monde packet)
        regime_value = packet.regime.value  # ex. "TREND_BULL"
        c5 = regime_value not in self.blacklisted_regimes
        conditions["regime_allowed"] = c5
        if not c5:
            failed.append(f"regime_blacklisted ({regime_value})")
            packet.add_reasoning(
                actor,
                f"Régime {regime_value} blacklisté",
                confidence_impact=-25.0,
                category=ReasoningCategory.RISK_GOVERNANCE,
            )

        # ── Écriture dans le packet ────────────────────────────────────────
        packet.metadata["risk_conditions"] = conditions
        packet.metadata["risk_failed"] = failed
        packet.metadata["risk_warnings"] = warnings
        packet.metadata["risk_conviction_advisory"] = conviction_level

        allowed = len(failed) == 0
        result = GateResult(
            allowed=allowed, conditions=conditions, failed=failed, warnings=warnings
        )

        log_fn = logger.info if allowed else logger.warning
        log_fn("[GlobalRiskGate] %s | %s", packet.symbol, result.summary())
        for w in warnings:
            logger.warning("[GlobalRiskGate] %s", w)

        # ── Transition d'état — la souveraineté s'exerce ici ──────────────
        if allowed:
            packet.transition_to(
                DecisionState.RISK_EVALUATED,
                actor,
                f"Gate pass — {len(conditions)}/{len(conditions)} conditions OK"
                + (
                    f" | conviction={conviction_level}"
                    if conviction_level != "SKIP"
                    else ""
                ),
            )
        else:
            packet.reject(
                actor,
                f"Gate block — {len(failed)} condition(s)"
                f" échouée(s): {', '.join(failed)}",
            )

        self._emit_event(result, None)
        return result

    # ── Calibration adaptative ────────────────────────────────────────────────

    def apply_regret_delta(self, delta: int) -> None:
        """
        Applique un ajustement de seuil provenant du RegretEngine.

        delta < 0 → plus permissif (trop de MISSED_WIN)
        delta > 0 → plus strict   (trop de false positifs)
        delta = 0 → stable

        L'ajustement est accumulatif et plafonné à [-5, +5] (anti-windup).
        """
        if self._safe_mode:
            return
        prev = self._regret_delta
        self._regret_delta = max(-5, min(5, self._regret_delta + delta))
        if self._regret_delta != prev:
            logger.info(
                "[GlobalRiskGate] Delta regret: %+d → %+d (min_score base=%d)",
                prev,
                self._regret_delta,
                self.min_signal_score,
            )

    def set_transition_threshold(self, value: int | None) -> None:
        """
        Override le seuil effectif pendant une transition de régime.

        Appelé par advisor_loop avec la valeur lissée du RegimeTransitionSmoother.
        None = fin de transition, seuil régime reprend la main.
        """
        if self._safe_mode:
            return
        self._transition_threshold = value

    def set_governor_delta(self, delta: int) -> None:
        """Delta appliqué par le RiskGovernor (P7) — s'additionne au delta ATE."""
        self._governor_delta = max(-10, min(20, delta))

    def set_adaptive_delta(self, delta: int) -> None:
        """
        Remplace le delta de calibration par la valeur PID de l'ATE.

        Contrairement à apply_regret_delta (accumulatif), ici le delta est
        positionnel : l'AdaptiveThresholdEngine est la source de vérité.
        """
        if self._safe_mode:
            return
        clamped = max(-5, min(5, delta))
        if clamped != self._regret_delta:
            logger.debug(
                "[GlobalRiskGate] ATE delta: %+d → %+d",
                self._regret_delta,
                clamped,
            )
            self._regret_delta = clamped

    def _effective_min_score(self, regime: str) -> int:
        """
        Seuil effectif pour un régime donné.

        Priorité :
          1. _transition_threshold (rampe RegimeSmoother active)
          2. MarketRegimeClassifier.effective_min_score(regime, delta)
          3. Fallback : self.min_signal_score + delta
        """
        if self._transition_threshold is not None:
            return self._transition_threshold
        if _regime_clf is not None:
            _combined_delta = self._regret_delta + self._governor_delta
            regime_effective = _regime_clf.effective_min_score(regime, _combined_delta)
            # Le plancher absolu (REGIME_ABSOLUTE_FLOOR=55) permet aux ajustements
            # régime de descendre sous min_signal_score (ex: SIDEWAYS -4 → 66).
            # min_signal_score reste la référence de l'ATE, pas un plancher dur.
            effective = max(self._absolute_floor, regime_effective)
            if regime != self._last_regime:
                self._last_regime = regime
                logger.info(
                    "[GlobalRiskGate] Seuil régime %s → %d (delta=%+d)",
                    regime,
                    effective,
                    self._regret_delta,
                )
            return effective
        # Fallback sans classifier
        return max(
            self.min_signal_score + self._regret_delta + self._governor_delta, 55
        )

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

    def _check_session_packet(self, packet, order_size_usd: float) -> bool:
        """Variante de _check_session pour DecisionPacket."""
        if self._session_guard is None:
            return True
        try:
            from core.decision_packet import DecisionSide

            action_map = {
                DecisionSide.LONG: "BUY",
                DecisionSide.SHORT: "SELL",
                DecisionSide.FLAT: "HOLD",
            }
            action = action_map.get(packet.side, "BUY")
            self._session_guard.check_order(packet.symbol, action, order_size_usd)
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
