"""
risk_engine_mvp.py — Risk Engine MVP

"Le Risk Manager est le vrai générateur de profit."

4 fonctions. Pas plus.

  1. SIZE      — combien risquer sur ce trade (Kelly simplifié)
  2. GUARD     — drawdown protection (soft/hard stop)
  3. FILTER    — no-trade intelligent (quand ne pas trader)
  4. CORRELATE — éviter les doublons de risque entre positions

Une seule décision de sortie : RiskDecision avec allow/size/reason.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATE_PATH = Path("databases/mvp_risk_state.json")


@dataclass
class RiskDecision:
    allowed: bool
    size_usd: float
    size_pct_capital: float     # % du capital total
    reason: str
    # Détail des checks
    drawdown_ok: bool = True
    filter_ok: bool = True
    correlation_ok: bool = True
    sizing_method: str = "kelly"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    def __bool__(self) -> bool:
        return self.allowed


class RiskEngineMVP:
    """
    Risk engine minimaliste mais complet.

    Paramètres configurables (tous avec valeurs par défaut prudentes) :
      - max_risk_per_trade_pct : max % du capital par trade (défaut 1%)
      - max_drawdown_soft      : drawdown qui réduit la taille à 50% (défaut 5%)
      - max_drawdown_hard      : drawdown qui arrête tout trading (défaut 10%)
      - max_open_positions     : limite de positions simultanées (défaut 3)
      - max_correlation_same_side : max positions long ou short simultanées (défaut 2)
    """

    def __init__(
        self,
        capital_usd: float = 1000.0,
        max_risk_per_trade_pct: float = 0.01,
        max_drawdown_soft: float = 0.05,
        max_drawdown_hard: float = 0.10,
        max_open_positions: int = 3,
        max_same_side: int = 2,
        maker_fee: float = 0.0002,
        taker_fee: float = 0.0004,
    ) -> None:
        self.capital_usd             = capital_usd
        self.max_risk_pct            = max_risk_per_trade_pct
        self.soft_dd                 = max_drawdown_soft
        self.hard_dd                 = max_drawdown_hard
        self.max_positions           = max_open_positions
        self.max_same_side           = max_same_side
        self.maker_fee               = maker_fee
        self.taker_fee               = taker_fee

        # État interne
        self._peak_capital           = capital_usd
        self._current_capital        = capital_usd
        self._open_positions: list[dict] = []
        self._consecutive_losses: int = 0
        self._trade_history: list[dict] = []
        self._load_state()

    # ──────────────────────────────────────────────────────────────────────────
    # API principale
    # ──────────────────────────────────────────────────────────────────────────

    def evaluate(
        self,
        symbol: str,
        direction: str,
        signal_score: float,
        signal_confidence: float,
        atr_pct: float = 0.01,
        win_rate_history: float | None = None,
        avg_win_pct: float = 0.02,
        avg_loss_pct: float = 0.01,
    ) -> RiskDecision:
        """
        Décide si on peut trader et pour quelle taille.
        Retourne immédiatement REJECT si n'importe quel garde est déclenché.
        """
        # ── 1. No-Trade filter ────────────────────────────────────────────────
        filter_ok, filter_reason = self._no_trade_filter(symbol, direction, signal_score, signal_confidence)
        if not filter_ok:
            return RiskDecision(False, 0, 0, f"NO_TRADE: {filter_reason}", filter_ok=False)

        # ── 2. Drawdown guard ─────────────────────────────────────────────────
        dd = self._current_drawdown()
        if dd >= self.hard_dd:
            return RiskDecision(False, 0, 0,
                                f"HARD_STOP: drawdown {dd:.1%} >= {self.hard_dd:.1%}",
                                drawdown_ok=False)

        # ── 3. Correlation check ──────────────────────────────────────────────
        corr_ok, corr_reason = self._correlation_check(symbol, direction)
        if not corr_ok:
            return RiskDecision(False, 0, 0, f"CORRELATION: {corr_reason}", correlation_ok=False)

        # ── 4. Position sizing ────────────────────────────────────────────────
        size_usd, method = self._compute_size(
            signal_score, signal_confidence, atr_pct,
            win_rate_history, avg_win_pct, avg_loss_pct, dd
        )

        if size_usd < 5.0:
            return RiskDecision(False, 0, 0, f"SIZE_TOO_SMALL: ${size_usd:.2f}")

        size_pct = size_usd / self._current_capital

        reason = (
            f"OK | size=${size_usd:.2f} ({size_pct:.1%}) | "
            f"dd={dd:.1%} | method={method} | "
            f"positions={len(self._open_positions)}/{self.max_positions}"
        )
        return RiskDecision(True, size_usd, size_pct, reason, sizing_method=method)

    def register_open(self, symbol: str, direction: str, size_usd: float, entry_price: float) -> None:
        self._open_positions.append({
            "symbol": symbol,
            "direction": direction,
            "size_usd": size_usd,
            "entry_price": entry_price,
            "open_at": time.time(),
        })
        self._save_state()

    def register_close(self, symbol: str, pnl_usd: float, pnl_pct: float) -> None:
        self._open_positions = [p for p in self._open_positions if p["symbol"] != symbol]
        self._current_capital += pnl_usd
        self._peak_capital = max(self._peak_capital, self._current_capital)
        if pnl_pct < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._trade_history.append({"symbol": symbol, "pnl_usd": pnl_usd, "pnl_pct": pnl_pct, "ts": time.time()})
        self._save_state()
        logger.info("[RiskMVP] Close %s PnL=%.2f$ (%.2f%%) | capital=%.2f$ dd=%.1%%",
                    symbol, pnl_usd, pnl_pct*100, self._current_capital, self._current_drawdown()*100)

    def update_capital(self, capital_usd: float) -> None:
        self._current_capital = capital_usd
        self._peak_capital = max(self._peak_capital, capital_usd)

    @property
    def current_drawdown(self) -> float:
        return self._current_drawdown()

    def status(self) -> dict[str, Any]:
        dd = self._current_drawdown()
        return {
            "capital_usd": round(self._current_capital, 2),
            "peak_capital": round(self._peak_capital, 2),
            "drawdown_pct": round(dd * 100, 2),
            "open_positions": len(self._open_positions),
            "consecutive_losses": self._consecutive_losses,
            "trading_halted": dd >= self.hard_dd,
            "reduced_mode": dd >= self.soft_dd,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # No-Trade filter
    # ──────────────────────────────────────────────────────────────────────────

    def _no_trade_filter(
        self, symbol: str, direction: str, score: float, confidence: float
    ) -> tuple[bool, str]:
        # Score trop faible
        if score < 55:
            return False, f"score {score:.0f} < 55"
        if confidence < 0.40:
            return False, f"confidence {confidence:.0%} < 40%"

        # Trop de positions ouvertes
        if len(self._open_positions) >= self.max_positions:
            return False, f"{len(self._open_positions)} positions ouvertes >= {self.max_positions}"

        # Déjà une position sur ce symbole
        if any(p["symbol"] == symbol for p in self._open_positions):
            return False, f"position déjà ouverte sur {symbol}"

        # Série de pertes consécutives → pause
        if self._consecutive_losses >= 3:
            return False, f"{self._consecutive_losses} pertes consécutives — pause forcée"

        return True, "OK"

    # ──────────────────────────────────────────────────────────────────────────
    # Drawdown
    # ──────────────────────────────────────────────────────────────────────────

    def _current_drawdown(self) -> float:
        if self._peak_capital <= 0:
            return 0.0
        return max(0.0, (self._peak_capital - self._current_capital) / self._peak_capital)

    # ──────────────────────────────────────────────────────────────────────────
    # Correlation check
    # ──────────────────────────────────────────────────────────────────────────

    def _correlation_check(self, symbol: str, direction: str) -> tuple[bool, str]:
        same_side = sum(1 for p in self._open_positions if p["direction"] == direction)
        if same_side >= self.max_same_side:
            return False, f"{same_side} positions {direction} ouvertes >= {self.max_same_side}"

        # Actifs corrélés : BTC/ETH/SOL sont tous très corrélés
        base_asset = symbol.split("/")[0]
        correlated_assets = {
            "BTC": {"ETH", "SOL"},
            "ETH": {"BTC", "SOL"},
            "SOL": {"BTC", "ETH"},
        }
        related = correlated_assets.get(base_asset, set())
        related_open = [p for p in self._open_positions
                        if p["symbol"].split("/")[0] in related and p["direction"] == direction]
        if len(related_open) >= 2:
            return False, f"Trop d'actifs corrélés en {direction}: {[p['symbol'] for p in related_open]}"

        return True, "OK"

    # ──────────────────────────────────────────────────────────────────────────
    # Position sizing — Kelly simplifié + volatility scaling
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_size(
        self,
        score: float,
        confidence: float,
        atr_pct: float,
        win_rate: float | None,
        avg_win: float,
        avg_loss: float,
        current_dd: float,
    ) -> tuple[float, str]:
        """
        Taille = min(Kelly, max_risk_pct) × capital × volatility_adj × dd_adj × confidence_adj

        Kelly fraction = (p * b - q) / b
          p = win rate
          q = 1 - p
          b = avg_win / avg_loss (payoff ratio)

        On utilise le demi-Kelly pour la sécurité.
        """
        # Fallback win rate si pas d'historique
        if win_rate is None or win_rate <= 0:
            # Estimation depuis le score du signal
            win_rate = 0.40 + (score / 100.0) * 0.20
        win_rate = max(0.3, min(win_rate, 0.75))

        # Kelly fraction
        b = avg_win / avg_loss if avg_loss > 0 else 2.0
        q = 1 - win_rate
        kelly = (win_rate * b - q) / b
        kelly = max(0.0, min(kelly, 0.25))   # cap à 25%
        half_kelly = kelly * 0.5             # demi-Kelly = plus safe

        # Plafond absolu
        max_fraction = self.max_risk_pct
        base_fraction = min(half_kelly, max_fraction)

        # Ajustement volatilité : vol élevée → taille réduite
        vol_adj = max(0.3, 1.0 - (atr_pct - 0.01) * 20)

        # Ajustement drawdown doux : si DD > soft_threshold, on réduit
        if current_dd >= self.soft_dd:
            dd_adj = max(0.3, 1.0 - (current_dd - self.soft_dd) / (self.hard_dd - self.soft_dd))
        else:
            dd_adj = 1.0

        # Ajustement confiance
        conf_adj = 0.5 + confidence * 0.5     # [0.5, 1.0]

        # Prise en compte des frais : taille minimale pour que l'EV soit positif après frais
        total_fee = self.taker_fee * 2         # entrée + sortie
        if avg_win - total_fee <= 0:
            return 0.0, "kelly"

        final_fraction = base_fraction * vol_adj * dd_adj * conf_adj
        size_usd = self._current_capital * final_fraction

        method = "half_kelly" if half_kelly < max_fraction else "capped"
        logger.debug("[RiskMVP] size=%.2f$ kelly=%.3f vol_adj=%.2f dd_adj=%.2f conf_adj=%.2f",
                     size_usd, kelly, vol_adj, dd_adj, conf_adj)
        return round(size_usd, 2), method

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────────

    def _save_state(self) -> None:
        try:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "capital_usd": self._current_capital,
                "peak_capital": self._peak_capital,
                "consecutive_losses": self._consecutive_losses,
                "open_positions": self._open_positions,
                "saved_at": time.time(),
            }
            with _STATE_PATH.open("w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as exc:
            logger.debug("[RiskMVP] save error: %s", exc)

    def _load_state(self) -> None:
        try:
            if _STATE_PATH.exists():
                with _STATE_PATH.open("r", encoding="utf-8") as f:
                    s = json.load(f)
                self._current_capital    = s.get("capital_usd", self.capital_usd)
                self._peak_capital       = s.get("peak_capital", self._current_capital)
                self._consecutive_losses = s.get("consecutive_losses", 0)
                self._open_positions     = s.get("open_positions", [])
                logger.info("[RiskMVP] État chargé: capital=%.2f$ dd=%.1%%",
                            self._current_capital, self._current_drawdown()*100)
        except Exception as exc:
            logger.debug("[RiskMVP] load error: %s", exc)
