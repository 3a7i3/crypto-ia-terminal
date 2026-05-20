"""
meta_strategy_engine.py — Meta-Strategy Engine

Le bot ne choisit plus un signal. Il choisit une PERSONNALITÉ de trading
adaptée au régime de marché détecté en temps réel.

Régime → Personnalité → Paramètres actifs

  bull_trend           → momentum_following   (TP large, SL serré, trailing)
  bear_trend           → defensive_short      (tailles réduites, SL étroit)
  sideways             → mean_reversion       (grid logic, TP court, pas de trend)
  high_volatility      → scalping_mode        (positions petites, sorties rapides)
  flash_crash          → capital_protection   (aucun ordre, attente)

Usage :
    engine = MetaStrategyEngine()
    personality = engine.select(regime, features, memory_sharpe)
    # personality.order_size_factor, personality.tp_pct, personality.sl_pct ...
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TradingPersonality:
    """Paramètres actifs pour une personnalité de trading."""

    name: str
    description: str
    allowed_signals: list  # ["BUY", "SELL", "HOLD"] ou sous-ensemble

    # Sizing
    order_size_factor: float  # multiplie order_size de base (0.0 = bloqué)
    max_positions: int  # nb max positions simultanées

    # TP / SL / Trailing
    tp_pct: float
    sl_pct: float
    trailing_pct: float
    partial_close_pct: float  # 0 = désactivé

    # Signal
    min_score: int  # score minimum pour déclencher
    require_confirmation: bool  # exige signal.confirmed=True

    # Contexte
    leverage: int = 1
    regime: str = "unknown"
    selected_at: float = field(default_factory=time.time)
    reason: str = ""

    def blocks_trading(self) -> bool:
        return self.order_size_factor <= 0.0

    def summary(self) -> str:
        if self.blocks_trading():
            return f"[{self.name.upper()}] TRADING BLOQUE — {self.description}"
        return (
            f"[{self.name.upper()}] {self.description} | "
            f"size×{self.order_size_factor:.1f} TP:{self.tp_pct:.0%} "
            f"SL:{self.sl_pct:.0%} trail:{self.trailing_pct:.0%} "
            f"score≥{self.min_score}"
        )


# ── Personnalités prédéfinies ──────────────────────────────────────────────────


def _momentum_following(regime: str) -> TradingPersonality:
    min_s = int(os.getenv("META_MOMENTUM_MIN_SCORE", "62"))
    return TradingPersonality(
        name="momentum_following",
        description="Tendance haussière confirmée — suivre le momentum",
        allowed_signals=["BUY"],
        order_size_factor=1.0,
        max_positions=3,
        tp_pct=float(os.getenv("META_MOMENTUM_TP", "0.06")),
        sl_pct=float(os.getenv("META_MOMENTUM_SL", "0.02")),
        trailing_pct=float(os.getenv("META_MOMENTUM_TRAIL", "0.02")),
        partial_close_pct=0.5,
        min_score=min_s,
        require_confirmation=True,
        regime=regime,
        reason=f"Bull trend détecté — taille pleine, TP large, trailing actif (min_score={min_s})",
    )


def _defensive_short(regime: str) -> TradingPersonality:
    min_s = int(os.getenv("META_SHORT_MIN_SCORE", "68"))
    return TradingPersonality(
        name="defensive_short",
        description="Tendance baissière — short défensif taille réduite",
        allowed_signals=["SELL"],
        order_size_factor=0.6,
        max_positions=2,
        tp_pct=float(os.getenv("META_SHORT_TP", "0.04")),
        sl_pct=float(os.getenv("META_SHORT_SL", "0.015")),
        trailing_pct=float(os.getenv("META_SHORT_TRAIL", "0.015")),
        partial_close_pct=0.0,
        min_score=min_s,
        require_confirmation=True,
        regime=regime,
        reason=f"Bear trend — taille réduite 60%, SL serré 1.5% (min_score={min_s})",
    )


def _mean_reversion(regime: str) -> TradingPersonality:
    min_s = int(os.getenv("META_RANGE_MIN_SCORE", "60"))
    return TradingPersonality(
        name="mean_reversion",
        description="Range lateral — rebonds courts, sorties rapides",
        allowed_signals=["BUY", "SELL"],
        order_size_factor=0.7,
        max_positions=2,
        tp_pct=float(os.getenv("META_RANGE_TP", "0.025")),
        sl_pct=float(os.getenv("META_RANGE_SL", "0.015")),
        trailing_pct=0.0,
        partial_close_pct=0.0,
        min_score=min_s,
        require_confirmation=False,
        regime=regime,
        reason=f"Sideways — TP court 2.5%, pas de trailing, sortie rapide (min_score={min_s})",
    )


def _scalping_mode(regime: str) -> TradingPersonality:
    min_s = int(os.getenv("META_SCALP_MIN_SCORE", "65"))
    return TradingPersonality(
        name="scalping_mode",
        description="Haute volatilité — positions minuscules, sorties ultra-rapides",
        allowed_signals=["BUY", "SELL"],
        order_size_factor=0.3,
        max_positions=1,
        tp_pct=float(os.getenv("META_SCALP_TP", "0.015")),
        sl_pct=float(os.getenv("META_SCALP_SL", "0.01")),
        trailing_pct=0.0,
        partial_close_pct=0.0,
        min_score=min_s,
        require_confirmation=True,
        regime=regime,
        reason=f"Haute vol — taille 30%, TP 1.5% (min_score={min_s})",
    )


def _capital_protection(regime: str) -> TradingPersonality:
    return TradingPersonality(
        name="capital_protection",
        description="Danger extrême — aucun ordre, protection du capital",
        allowed_signals=[],
        order_size_factor=0.0,
        max_positions=0,
        tp_pct=0.0,
        sl_pct=0.0,
        trailing_pct=0.0,
        partial_close_pct=0.0,
        min_score=999,
        require_confirmation=True,
        regime=regime,
        reason="Flash crash ou risque extrême — trading suspendu",
    )


def _neutral(regime: str) -> TradingPersonality:
    return TradingPersonality(
        name="neutral",
        description="Régime indéterminé — paramètres prudents par défaut",
        allowed_signals=["BUY", "SELL"],
        order_size_factor=0.5,
        max_positions=2,
        tp_pct=0.04,
        sl_pct=0.02,
        trailing_pct=0.01,
        partial_close_pct=0.0,
        min_score=75,
        require_confirmation=True,
        regime=regime,
        reason="Régime inconnu — taille 50%, paramètres conservateurs",
    )


# ── Mapping régime → personnalité ─────────────────────────────────────────────

_REGIME_MAP = {
    "bull_trend": _momentum_following,
    "bear_trend": _defensive_short,
    "sideways": _mean_reversion,
    "high_volatility_regime": _scalping_mode,
    "flash_crash": _capital_protection,
    "unknown": _neutral,
}


class MetaStrategyEngine:
    """
    Sélectionne la personnalité de trading optimale selon :
      1. Le régime de marché détecté
      2. La volatilité réalisée
      3. Les performances récentes en mémoire (Sharpe par régime)
      4. Le nombre de pertes consécutives récentes
    """

    def __init__(self) -> None:
        self._current: Optional[TradingPersonality] = None
        self._history: list[dict] = []
        self._regime_stats: dict[str, dict] = {}  # régime → {wins, losses, sharpe}

    # ── Sélection principale ───────────────────────────────────────────────────

    def select(
        self,
        regime: str,
        features: dict,
        memory_sharpe: Optional[float] = None,
        consecutive_losses: int = 0,
        open_positions: int = 0,
    ) -> TradingPersonality:
        """
        Retourne la personnalité adaptée au contexte courant.
        Peut surcharger la personnalité par défaut si :
          - trop de pertes consécutives → downgrade à neutral / capital_protection
          - Sharpe mémoire faible pour ce régime → réduction de taille
          - trop de positions ouvertes → bloque jusqu'à fermeture
        """
        vol = float(features.get("realized_volatility", 0.0))

        # Surcharge : flash crash détecté par volatilité même si régime incorrect
        if vol > 0.20:
            p = _capital_protection("flash_crash_override")
            p.reason = f"Vol réalisée {vol:.2%} > 20% — override capital_protection"
            return self._record(p)

        # Personnalité de base selon régime
        factory = _REGIME_MAP.get(regime, _neutral)
        p = factory(regime)

        # ── Ajustements dynamiques ─────────────────────────────────────────────

        # 1. Trop de pertes consécutives → downgrade
        if consecutive_losses >= 3:
            p.order_size_factor *= 0.4
            p.min_score = max(p.min_score, 80)
            p.reason += f" | DOWNGRADE: {consecutive_losses} pertes consec."
            logger.warning(
                "[MetaStrategy] Downgrade taille ×0.4 — %d pertes consec.",
                consecutive_losses,
            )

        elif consecutive_losses >= 2:
            p.order_size_factor *= 0.7
            p.reason += f" | Prudence: {consecutive_losses} pertes consec."

        # 2. Sharpe mémoire mauvais pour ce régime → prudence
        if memory_sharpe is not None:
            if memory_sharpe < 0.5:
                p.order_size_factor *= 0.5
                p.min_score = max(p.min_score, 80)
                p.reason += f" | Sharpe mémoire faible: {memory_sharpe:.2f}"
            elif memory_sharpe > 2.0:
                # Bon historique → légère augmentation de taille (cap à 1.2)
                p.order_size_factor = min(1.2, p.order_size_factor * 1.15)
                p.reason += f" | Sharpe mémoire excellent: {memory_sharpe:.2f}"

        # 3. Trop de positions ouvertes → bloquer
        if open_positions >= p.max_positions:
            p.order_size_factor = 0.0
            p.reason += f" | Max positions atteint ({open_positions}/{p.max_positions})"

        # 4. Volatilité élevée même hors flash crash → réduire taille
        if 0.10 < vol <= 0.20:
            p.order_size_factor = min(p.order_size_factor, 0.5)
            p.reason += f" | Vol élevée {vol:.2%} — taille plafonnée à 50%"

        # 5. SL/TP ATR-adaptatif — tous les régimes via MarketRegimeClassifier
        # sl_factor_atr dépend du régime : SIDEWAYS=1.5, TREND=2.0, HIGH_VOL=1.8
        # flash_crash et régimes avec sl_factor_atr=0 : SL fixe conservé.
        atr_pct = float(features.get("atr_pct", features.get("atr_ratio", 0.0)))
        if atr_pct > 0:
            try:
                from quant_hedge_ai.agents.intelligence.market_regime_classifier import (
                    MarketRegimeClassifier as _MRC,
                )

                _cfg = _MRC().get_config(regime)
                sl_factor = _cfg.sl_factor_atr
                tp_factor = _cfg.tp_factor_atr
            except Exception:
                sl_factor = 1.5
                tp_factor = 2.5
            if sl_factor > 0:
                atr_sl = max(atr_pct * sl_factor, 0.008)  # plancher 0.8%
                atr_tp = max(atr_pct * tp_factor, atr_sl * 2.0)  # RR ≥ 2:1
                if abs(atr_sl - p.sl_pct) > 0.001:
                    logger.info(
                        "[MetaStrategy] SL/TP ATR [%s]: SL %.2f%% TP %.2f%%"
                        " (ATR=%.2f%% SL×%.1f TP×%.1f)",
                        regime,
                        atr_sl * 100,
                        atr_tp * 100,
                        atr_pct * 100,
                        sl_factor,
                        tp_factor,
                    )
                    p.sl_pct = round(atr_sl, 4)
                    p.tp_pct = round(atr_tp, 4)
                    p.reason += (
                        f" | SL ATR: {atr_sl:.2%} TP ATR: {atr_tp:.2%}"
                        f" (×{sl_factor:.1f}/×{tp_factor:.1f})"
                    )

        logger.info("[MetaStrategy] Personnalité: %s", p.summary())
        return self._record(p)

    # ── Validation d'un signal ─────────────────────────────────────────────────

    def validate_signal(
        self,
        signal_action: str,
        signal_score: int,
        confirmed: bool,
        personality: TradingPersonality,
    ) -> tuple[bool, str]:
        """
        Retourne (autorisé, raison).
        Vérifie que le signal est compatible avec la personnalité active.
        """
        if personality.blocks_trading():
            return False, f"Trading bloqué par personnalité {personality.name}"

        if signal_action not in personality.allowed_signals:
            return False, (
                f"Signal {signal_action} non autorisé en mode {personality.name} "
                f"(autorisés: {personality.allowed_signals})"
            )

        if signal_score < personality.min_score:
            return False, (
                f"Score {signal_score} < minimum {personality.min_score} "
                f"requis pour {personality.name}"
            )

        if personality.require_confirmation and not confirmed:
            return False, f"Confirmation MTF requise pour {personality.name}"

        return True, "OK"

    def effective_order_size(
        self, base_size: float, personality: TradingPersonality
    ) -> float:
        """Applique le facteur de taille de la personnalité."""
        return round(base_size * personality.order_size_factor, 2)

    # ── Feedback (apprentissage) ───────────────────────────────────────────────

    def record_trade_result(
        self,
        regime: str,
        personality: str,
        pnl_pct: float,
        sharpe: float = 0.0,
    ) -> None:
        """
        Enregistre le résultat d'un trade pour améliorer la sélection future.
        Appelé par le PositionManager à chaque fermeture de position.
        """
        stats = self._regime_stats.setdefault(
            regime,
            {
                "wins": 0,
                "losses": 0,
                "total_pnl": 0.0,
                "best_sharpe": 0.0,
                "personality": personality,
            },
        )
        if pnl_pct > 0:
            stats["wins"] += 1
        else:
            stats["losses"] += 1
        stats["total_pnl"] += pnl_pct
        stats["best_sharpe"] = max(stats["best_sharpe"], sharpe)
        logger.info(
            "[MetaStrategy] Résultat enregistré — régime=%s perso=%s pnl=%.2f%% "
            "wins=%d losses=%d",
            regime,
            personality,
            pnl_pct * 100,
            stats["wins"],
            stats["losses"],
        )

    def regime_stats(self) -> dict:
        return dict(self._regime_stats)

    def current_personality(self) -> Optional[TradingPersonality]:
        return self._current

    def history(self, n: int = 20) -> list[dict]:
        return self._history[-n:]

    # ── Interne ───────────────────────────────────────────────────────────────

    def _record(self, p: TradingPersonality) -> TradingPersonality:
        self._current = p
        self._history.append(
            {
                "ts": p.selected_at,
                "name": p.name,
                "regime": p.regime,
                "size_factor": p.order_size_factor,
                "min_score": p.min_score,
                "reason": p.reason,
            }
        )
        if len(self._history) > 200:
            self._history = self._history[-200:]
        return p
