"""
capital_allocation_engine.py — Capital Allocation Engine

Détermine la taille optimale d'un ordre en combinant :
  1. Kelly Fraction simplifiée (EV / (gain potentiel / perte potentielle))
  2. EV-weighted sizing   (taille ∝ espérance de gain positive)
  3. Volatility-adjusted  (réduit la taille quand la vol monte)
  4. Confidence-weighted  (multiplie par le score de conviction)
  5. Regime-dependent cap (exposition max selon le régime de marché)
  6. Dynamic leverage reduction (réduit le levier sous pression)

Retourne :
  AllocationResult(size_usd, leverage, reason, factors)

Le Kelly et l'EV sont calculés depuis l'historique des trades mémorisés
(win_rate + avg_win_pct + avg_loss_pct du StrategyRanker).
Si l'historique est insuffisant, le moteur bascule en mode conservateur.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.risk.capital_allocation_engine")
# ── Caps par régime ────────────────────────────────────────────────────────────
_REGIME_CAPS: dict[str, float] = {
    "bull_trend": 1.00,  # plein capital autorisé
    "bear_trend": 0.60,  # réduit en bear
    "sideways": 0.70,
    "high_volatility_regime": 0.40,  # très prudent en haute vol
    "flash_crash": 0.00,  # aucun trade en krach
    "unknown": 0.50,
}

# ── Multiplicateur levier par régime ──────────────────────────────────────────
_REGIME_LEVERAGE: dict[str, float] = {
    "bull_trend": 1.0,
    "bear_trend": 0.75,
    "sideways": 0.75,
    "high_volatility_regime": 0.50,
    "flash_crash": 0.0,
    "unknown": 0.60,
}


@dataclass
class AllocationResult:
    size_usd: float
    leverage: float  # levier recommandé [1.0, MAX]
    reason: str
    kelly_fraction: float = 0.0  # fraction Kelly brute
    ev_score: float = 0.0  # espérance positive normalisée
    factors: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.size_usd > 0


class CapitalAllocationEngine:
    """
    Calcule la taille optimale d'un ordre.

    Usage :
        cae = CapitalAllocationEngine(total_capital=1000)
        result = cae.allocate(
            base_size_usd   = 55.0,
            win_rate        = 0.55,
            avg_win_pct     = 0.04,
            avg_loss_pct    = 0.02,
            volatility      = 0.02,   # vol normalisée (ATR / prix)
            conviction_factor = 0.8,  # issu de ConvictionEngine.size_factor
            regime          = "bull_trend",
            leverage        = 1,
        )
        if result:
            exec_engine.create_futures_order(..., size=result.size_usd)
    """

    # ── Paramètres globaux ─────────────────────────────────────────────────────
    KELLY_SAFETY = float(os.getenv("CAE_KELLY_SAFETY", "0.25"))  # Kelly × 25%
    KELLY_MAX = float(os.getenv("CAE_KELLY_MAX", "0.20"))  # cap Kelly à 20% du capital
    EV_MIN_THRESHOLD = float(
        os.getenv("CAE_EV_MIN", "0.005")
    )  # EV min pour ouvrir un trade
    VOL_REFERENCE = float(
        os.getenv("CAE_VOL_REFERENCE", "0.015")
    )  # vol de référence (1.5%)
    VOL_MAX_REDUCTION = float(
        os.getenv("CAE_VOL_MAX_REDUCTION", "0.50")
    )  # réduction max à haute vol
    LEVERAGE_MAX = float(os.getenv("CAE_LEVERAGE_MAX", "3.0"))  # levier max absolu
    MIN_TRADES_KELLY = int(
        os.getenv("CAE_MIN_TRADES_KELLY", "10")
    )  # min trades pour Kelly

    def __init__(self, total_capital: float = 1000.0) -> None:
        self._capital = total_capital

    def update_capital(self, capital: float) -> None:
        self._capital = max(1.0, capital)

    # ── Allocation principale ──────────────────────────────────────────────────

    def allocate(
        self,
        base_size_usd: float,
        win_rate: float = 0.50,
        avg_win_pct: float = 0.03,
        avg_loss_pct: float = 0.02,
        volatility: float = 0.015,
        conviction_factor: float = 1.0,
        regime: str = "unknown",
        leverage: int = 1,
        n_trades_history: int = 0,
    ) -> AllocationResult:
        """
        Retourne la taille allouée et le levier ajusté.

        Paramètres :
            base_size_usd     : taille de départ (issue de l'ExecutionEngine / .env)
            win_rate          : taux de gain historique (0-1) depuis StrategyRanker
            avg_win_pct       : gain moyen en % par trade gagnant
            avg_loss_pct      : perte moyenne en % par trade perdant (valeur positive)
            volatility        : ATR / prix du dernier cycle
            conviction_factor : facteur ConvictionEngine.size_factor [0, 1.5]
            regime            : régime de marché courant
            leverage          : levier demandé
            n_trades_history  : nombre de trades dans l'historique
        """
        factors = {}

        # ── 0. Cap régime — refus immédiat si flash_crash ─────────────────────
        regime_cap = _REGIME_CAPS.get(regime, 0.50)
        if regime_cap == 0.0:
            return AllocationResult(
                size_usd=0.0,
                leverage=0.0,
                reason=f"Regime '{regime}' — aucun trade autorisé",
                factors={"regime_cap": 0.0},
            )
        factors["regime_cap"] = regime_cap

        # ── 1. Kelly Fraction simplifiée ─────────────────────────────────────
        kelly_fraction = 0.0
        ev_score = 0.0
        ev_reliable = False  # True seulement quand l'historique est suffisant
        if n_trades_history >= self.MIN_TRADES_KELLY and avg_loss_pct > 0:
            # Kelly = (p × b - q) / b  où b = avg_win/avg_loss
            b = avg_win_pct / avg_loss_pct
            p = win_rate
            q = 1.0 - p
            kelly_raw = (p * b - q) / b
            kelly_fraction = max(0.0, kelly_raw * self.KELLY_SAFETY)
            kelly_fraction = min(kelly_fraction, self.KELLY_MAX)

            # EV = p × avg_win - q × avg_loss
            ev_score = p * avg_win_pct - q * avg_loss_pct
            ev_reliable = True
        else:
            # Pas assez d'historique → taille conservative, EV non fiable
            kelly_fraction = 0.08  # équivaut à 8% Kelly de sécurité
            ev_score = (win_rate - 0.5) * avg_win_pct * 2.0  # estimation grossière

        # Refus si EV négatif — seulement quand historique fiable (>= MIN_TRADES_KELLY)
        if ev_reliable and ev_score < self.EV_MIN_THRESHOLD:
            return AllocationResult(
                size_usd=0.0,
                leverage=0.0,
                reason=f"EV insuffisant: {ev_score:.4f} < {self.EV_MIN_THRESHOLD:.4f}",
                kelly_fraction=kelly_fraction,
                ev_score=ev_score,
                factors=factors,
            )
        factors["kelly_fraction"] = round(kelly_fraction, 4)
        factors["ev_score"] = round(ev_score, 5)

        # ── 2. Taille Kelly = capital × kelly_fraction ────────────────────────
        kelly_size = self._capital * kelly_fraction
        factors["kelly_size"] = round(kelly_size, 2)

        # ── 3. EV-weighted sizing — amplifie quand EV fort ────────────────────
        # Normalisation EV : 0.005 → ×1.0, 0.05 → ×1.5 (cap)
        ev_factor = min(1.5, 1.0 + (ev_score - self.EV_MIN_THRESHOLD) / 0.05)
        factors["ev_factor"] = round(ev_factor, 3)

        # ── 4. Volatility adjustment ──────────────────────────────────────────
        # Plus la vol est haute, plus on réduit (protection contre faux signaux)
        if volatility > 0:
            vol_ratio = volatility / self.VOL_REFERENCE
            vol_factor = (
                max(
                    1.0 - self.VOL_MAX_REDUCTION,
                    1.0 - self.VOL_MAX_REDUCTION * (vol_ratio - 1.0) / 2.0,
                )
                if vol_ratio > 1.0
                else 1.0
            )
        else:
            vol_factor = 1.0
        factors["vol_factor"] = round(vol_factor, 3)

        # ── 5. Conviction factor (issu de ConvictionEngine) ───────────────────
        factors["conviction_factor"] = round(conviction_factor, 3)

        # ── 6. Composition finale ─────────────────────────────────────────────
        # On part de la taille Kelly et on applique les facteurs
        size = kelly_size * ev_factor * vol_factor * conviction_factor * regime_cap

        # Guardrails : ne jamais dépasser base_size × 1.5, ni base_size × 0.3
        size = min(size, base_size_usd * 1.5)
        size = max(size, base_size_usd * 0.30)

        # Guardrails absolus : min $30, max 20% du capital
        size = max(30.0, size)
        size = min(size, self._capital * 0.20)

        factors["final_size"] = round(size, 2)

        # ── 7. Levier ajusté ──────────────────────────────────────────────────
        lev_regime_factor = _REGIME_LEVERAGE.get(regime, 0.60)
        lev_vol_factor = max(
            0.5, 1.0 - max(0.0, (volatility / self.VOL_REFERENCE - 1.0) * 0.3)
        )
        adjusted_leverage = max(
            1.0,
            min(
                self.LEVERAGE_MAX,
                leverage * lev_regime_factor * lev_vol_factor,
            ),
        )
        factors["leverage_adjusted"] = round(adjusted_leverage, 2)

        reason = "OK"
        if size < base_size_usd * 0.7:
            reason = (
                f"Taille réduite: kelly={kelly_fraction:.2f}"
                f" ev={ev_score:.4f} vol={volatility:.3f}"
            )

        _log.debug(
            "[CAE] size=%.2f lev=%.1f kelly=%.4f ev=%.5f vol=%.3f regime=%s conv=%.2f",
            size,
            adjusted_leverage,
            kelly_fraction,
            ev_score,
            volatility,
            regime,
            conviction_factor,
        )

        return AllocationResult(
            size_usd=round(size, 2),
            leverage=round(adjusted_leverage, 2),
            reason=reason,
            kelly_fraction=round(kelly_fraction, 4),
            ev_score=round(ev_score, 5),
            factors=factors,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def stats_from_ranker(self, ranker, strategy_name: str, regime: str) -> dict:
        """Extrait win_rate / avg_win / avg_loss depuis le StrategyRanker."""
        try:
            score = ranker.get_score(strategy_name, regime)
            if score:
                return {
                    "win_rate": score.win_rate,
                    "avg_win_pct": (
                        score.avg_pnl_pct * 2.0 if score.avg_pnl_pct > 0 else 0.03
                    ),
                    "avg_loss_pct": (
                        abs(score.avg_pnl_pct) * 0.5 if score.avg_pnl_pct < 0 else 0.02
                    ),
                    "n_trades_history": score.n_trades,
                    "sharpe": score.avg_sharpe,
                }
        except Exception:
            pass
        return {
            "win_rate": 0.50,
            "avg_win_pct": 0.03,
            "avg_loss_pct": 0.02,
            "n_trades_history": 0,
            "sharpe": 0.0,
        }
