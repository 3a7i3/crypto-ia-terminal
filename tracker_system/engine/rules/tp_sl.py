from __future__ import annotations


def _is_long(side: str | None) -> bool:
    return str(side or "BUY").strip().upper() in {"BUY", "LONG"}


class TPSLRule:
    def __init__(self, tp: float = 0.02, sl: float = 0.01) -> None:
        self.tp = float(tp)
        self.sl = float(sl)

    def check(self, position: dict, price: float, context: dict | None = None) -> str | None:
        entry = float(position["entry_price"])
        if entry <= 0:
            return None

        if _is_long(position.get("side")):
            pnl_pct = (float(price) - entry) / entry
        else:
            pnl_pct = (entry - float(price)) / entry

        if pnl_pct <= -self.sl:
            return f"SL @ {float(price):.8f}"
        if pnl_pct >= self.tp:
            return f"TP @ {float(price):.8f}"
        return None
