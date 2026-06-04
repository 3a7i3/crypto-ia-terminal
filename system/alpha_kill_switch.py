"""
system/alpha_kill_switch.py — Détecteur de dégradation alpha prolongée.

Invariant : ne modifie RIEN dans le système.
Produit uniquement un AlphaKillResult qui décrit la situation et suggère des
actions. La décision finale appartient à l'opérateur (ou à un futur module
de remédiation automatique).

Critères d'évaluation :
  1. PF global < pf_floor sur les `window` derniers trades (si N >= min_trades)
  2. Par symbole : expectancy < symbol_drag_threshold sur N >= symbol_min_trades

Usage :
    from system.alpha_kill_switch import AlphaKillSwitch
    result = AlphaKillSwitch().evaluate(closed_trades)
    if result.triggered:
        print(result.reasons)
        print(result.suggested_actions)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AlphaKillResult:
    triggered: bool
    reasons: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    rolling_pf: Optional[float] = None
    rolling_window: int = 0
    trades_evaluated: int = 0
    drag_symbols: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "triggered": self.triggered,
            "reasons": self.reasons,
            "suggested_actions": self.suggested_actions,
            "rolling_pf": self.rolling_pf,
            "rolling_window": self.rolling_window,
            "trades_evaluated": self.trades_evaluated,
            "drag_symbols": self.drag_symbols,
        }


class AlphaKillSwitch:
    """
    Évalue la qualité alpha des N derniers trades et détecte la dégradation.

    Paramètres :
        window               : taille de la fenêtre glissante (trades)
        pf_floor             : seuil PF global en dessous duquel on alerte
        min_trades           : minimum de trades pour activer le check PF global
        symbol_drag_threshold: seuil expectancy par symbole (négatif)
        symbol_min_trades    : minimum de trades par symbole pour le check
    """

    def __init__(
        self,
        window: int = 50,
        pf_floor: float = 0.8,
        min_trades: int = 30,
        symbol_drag_threshold: float = -0.3,
        symbol_min_trades: int = 5,
    ) -> None:
        self._window = window
        self._pf_floor = pf_floor
        self._min_trades = min_trades
        self._symbol_drag_threshold = symbol_drag_threshold
        self._symbol_min_trades = symbol_min_trades

    def evaluate(self, closed_trades: list[dict]) -> AlphaKillResult:
        """Évalue la dégradation alpha sur les trades les plus récents."""
        sorted_trades = sorted(
            closed_trades, key=lambda t: float(t.get("close_ts", 0) or 0)
        )
        recent = sorted_trades[-self._window :]
        n = len(recent)

        reasons: list[str] = []
        actions: list[str] = []
        drag_symbols: list[str] = []
        rolling_pf: Optional[float] = None

        # ── Check PF global ──────────────────────────────────────────────────
        if n >= self._min_trades:
            rets = [self._norm_pct(t.get("pnl_pct", 0.0)) for t in recent]
            wins_sum = sum(r for r in rets if r > 0)
            loss_sum = abs(sum(r for r in rets if r <= 0))
            rolling_pf = round(wins_sum / loss_sum, 4) if loss_sum > 0 else 0.0

            if rolling_pf < self._pf_floor:
                reasons.append(
                    f"PF global = {rolling_pf:.3f} < {self._pf_floor}"
                    f" ({n} derniers trades)"
                )
                actions.append("AUTO_PAPER_ONLY")

        # ── Check par symbole ─────────────────────────────────────────────────
        sym_map: dict[str, list[dict]] = {}
        for t in recent:
            sym = str(t.get("symbol", "") or "UNKNOWN")
            sym_map.setdefault(sym, []).append(t)

        for sym, subset in sorted(sym_map.items()):
            if len(subset) < self._symbol_min_trades:
                continue
            rets = [self._norm_pct(t.get("pnl_pct", 0.0)) for t in subset]
            expectancy = sum(rets) / len(rets)
            if expectancy < self._symbol_drag_threshold:
                drag_symbols.append(sym)
                reasons.append(
                    f"DRAG {sym}: expectancy = {expectancy:.3f}"
                    f" < {self._symbol_drag_threshold}"
                    f" ({len(subset)} trades)"
                )
                actions.append(f"AUTO_DISABLE_SYMBOL={sym}")

        return AlphaKillResult(
            triggered=bool(reasons),
            reasons=reasons,
            suggested_actions=actions,
            rolling_pf=rolling_pf,
            rolling_window=self._window,
            trades_evaluated=n,
            drag_symbols=drag_symbols,
        )

    @staticmethod
    def _norm_pct(value: object) -> float:
        try:
            v = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return v * 100.0 if abs(v) < 1.0 else v
