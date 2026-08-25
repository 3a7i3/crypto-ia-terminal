"""
Exit rules simples pour CompositeExitEngine.
Chacune = une décision potentielle d'exit.
"""
from __future__ import annotations


class StopLossRule:
    """Exit si prix <= stop_loss."""

    def check(self, pos: dict, price: float, context: dict | None = None) -> str | None:
        sl = pos.get("stop_loss", 0)
        side = pos.get("side", "BUY")

        if side == "BUY" and price <= sl:
            return f"SL @ {price:.2f}"
        elif side == "SELL" and price >= sl:
            return f"SL @ {price:.2f}"

        return None


class TakeProfitRule:
    """Exit si prix >= take_profit."""

    def check(self, pos: dict, price: float, context: dict | None = None) -> str | None:
        tp = pos.get("take_profit", 0)
        side = pos.get("side", "BUY")

        if side == "BUY" and price >= tp:
            return f"TP @ {price:.2f}"
        elif side == "SELL" and price <= tp:
            return f"TP @ {price:.2f}"

        return None


class TimeExitRule:
    """Exit si durée > max_duration_min."""

    def __init__(self, max_duration_min: float = 240.0):
        self.max_duration_min = max_duration_min

    def check(self, pos: dict, price: float, context: dict | None = None) -> str | None:
        import time
        from datetime import datetime

        try:
            raw_ts = pos.get("timestamp")
            if isinstance(raw_ts, (int, float)):
                entry_ts = float(raw_ts)
            else:
                entry_ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00")).timestamp()

            duration_min = (time.time() - entry_ts) / 60.0
            if duration_min >= self.max_duration_min:
                return f"TIME_EXIT ({duration_min:.0f}min)"
        except Exception:
            pass

        return None


class BreakEvenRule:
    """Exit si PnL tourne au breakeven après gain min."""

    def __init__(self, min_gain_pct: float = 0.02, breakeven_threshold_pct: float = 0.001):
        self.min_gain_pct = min_gain_pct
        self.breakeven_threshold_pct = breakeven_threshold_pct

    def check(self, pos: dict, price: float, context: dict | None = None) -> str | None:
        entry = pos.get("entry_price", 0)
        max_price = pos.get("max_price", entry)
        side = pos.get("side", "BUY")

        if entry == 0:
            return None

        # Calcule le max gain atteint
        if side == "BUY":
            max_gain = (max_price - entry) / entry
            current_pnl = (price - entry) / entry
        else:
            max_gain = (entry - max_price) / entry
            current_pnl = (entry - price) / entry

        # Si on a eu un gain et on redescend proche du breakeven
        if max_gain >= self.min_gain_pct and current_pnl <= self.breakeven_threshold_pct:
            return f"BREAKEVEN (max_gain={max_gain:.1%})"

        return None


class RegimeProtectionRule:
    """Exit si le régime change (stop pertes si bullish → bearish)."""

    def check(self, pos: dict, price: float, context: dict | None = None) -> str | None:
        if not context:
            return None

        current_regime = context.get("current_regime")
        position_regime = pos.get("regime")

        # Exit long si regime change de bullish → bearish
        if pos.get("side") == "BUY" and position_regime == "bullish" and current_regime == "bearish":
            return "REGIME_CHANGE (bullish→bearish)"

        # Exit short si regime change de bearish → bullish
        if pos.get("side") == "SELL" and position_regime == "bearish" and current_regime == "bullish":
            return "REGIME_CHANGE (bearish→bullish)"

        return None
