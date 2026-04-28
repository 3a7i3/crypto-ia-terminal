"""
multi_timeframe_signal.py — Confirmation de signal sur plusieurs timeframes.

Principe :
  - Calcule un signal (BUY/SELL/HOLD) sur chaque timeframe via SignalEngine.
  - Vote pondéré (1d > 4h > 1h) pour le signal final.
  - Confirmation = au moins 2 TF d'accord + poids ≥ 50 % du total.

Usage :
    from quant_hedge_ai.agents.execution.multi_timeframe_signal import MultiTimeframeSignal

    mtf = MultiTimeframeSignal()
    result = mtf.confirm(strategy, {"1h": candles_1h, "4h": candles_4h, "1d": candles_1d})
    # result = {"signal": "BUY", "confirmed": True, "strength": 0.75, "alignment": {...}}
"""

from __future__ import annotations

import logging

from quant_hedge_ai.agents.execution.signal_engine import compute_signal

logger = logging.getLogger(__name__)

# Poids par timeframe — les TF longs ont plus d'autorité
_TF_WEIGHTS: dict[str, float] = {
    "1d": 3.0,
    "4h": 2.0,
    "1h": 1.0,
    "15m": 0.5,
}


class MultiTimeframeSignal:
    """
    Agrège les signaux de plusieurs timeframes en un signal final pondéré.

    Paramètres :
        min_strength   — fraction minimale du poids total pour valider (défaut 0.5)
        min_agreement  — nombre minimal de TF d'accord (défaut 2)
    """

    def __init__(
        self,
        min_strength: float = 0.5,
        min_agreement: int = 2,
    ) -> None:
        self.min_strength = min_strength
        self.min_agreement = min_agreement

    # ── API principale ────────────────────────────────────────────────────────

    def confirm(
        self,
        strategy: dict,
        mtf_candles: dict[str, list[dict]],
    ) -> dict:
        """
        Args:
            strategy    : dict stratégie (entry_indicator, period, etc.)
            mtf_candles : {timeframe: [candle_dicts]} — au moins 1 TF requis

        Returns:
            {
              "signal":    "BUY" | "SELL" | "HOLD",
              "confirmed": bool,   # True = signal fiable
              "strength":  float,  # 0.0–1.0 (part du poids total)
              "alignment": {tf: signal, ...},
              "detail":    str,    # résumé lisible
            }
        """
        if not mtf_candles:
            return self._result("HOLD", False, 0.0, {}, "Pas de données MTF")

        # ① Signal par timeframe
        alignment: dict[str, str] = {}
        for tf, candles in mtf_candles.items():
            sig = compute_signal(strategy, candles)
            alignment[tf] = sig
            logger.debug("[MTF] %s → %s", tf, sig)

        # ② Vote pondéré
        buy_w = sum(
            _TF_WEIGHTS.get(tf, 1.0) for tf, s in alignment.items() if s == "BUY"
        )
        sell_w = sum(
            _TF_WEIGHTS.get(tf, 1.0) for tf, s in alignment.items() if s == "SELL"
        )
        total_w = sum(_TF_WEIGHTS.get(tf, 1.0) for tf in alignment)

        if total_w == 0:
            return self._result("HOLD", False, 0.0, alignment, "Poids nul")

        if buy_w > sell_w:
            candidate, weight = "BUY", buy_w
        elif sell_w > buy_w:
            candidate, weight = "SELL", sell_w
        else:
            return self._result("HOLD", False, 0.0, alignment, "Égalité BUY/SELL")

        strength = weight / total_w

        # ③ Critères de confirmation
        n_agree = sum(1 for s in alignment.values() if s == candidate)
        confirmed = (strength >= self.min_strength) and (n_agree >= self.min_agreement)

        detail = (
            f"{candidate}: {n_agree}/{len(alignment)} TF | "
            f"poids={strength:.0%} | "
            + " | ".join(f"{tf}={s}" for tf, s in sorted(alignment.items()))
        )
        logger.info("[MTF] %s", detail)

        signal = candidate if confirmed else "HOLD"
        return self._result(signal, confirmed, round(strength, 3), alignment, detail)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _result(
        signal: str,
        confirmed: bool,
        strength: float,
        alignment: dict,
        detail: str,
    ) -> dict:
        return {
            "signal": signal,
            "confirmed": confirmed,
            "strength": strength,
            "alignment": alignment,
            "detail": detail,
        }

    def summary(self, result: dict) -> str:
        """Rendu texte pour les logs."""
        icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(result["signal"], "⚪")
        conf = "✓" if result["confirmed"] else "✗"
        return (
            f"{icon} {result['signal']} [{conf}] "
            f"strength={result['strength']:.0%} — {result['detail']}"
        )
