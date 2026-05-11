from __future__ import annotations

from tracker_system.engine.exit_engine import ExitEngine


def _compute_pnl_pct(entry_price: float, exit_price: float, side: str | None) -> float:
    if str(side or "BUY").strip().upper() in {"BUY", "LONG"}:
        return (exit_price - entry_price) / entry_price
    return (entry_price - exit_price) / entry_price


def simulate_trade(trade: dict, engine: ExitEngine) -> dict[str, float | str | None]:
    path = [float(price) for price in trade.get("price_path", [])]
    entry_price = float(trade["entry_price"])
    reason, exit_price = engine.check_path(
        {
            "entry_price": entry_price,
            "side": trade.get("side", trade.get("direction", "BUY")),
            "max_price": entry_price,
            "min_price": entry_price,
        },
        path,
        context={"regime": trade.get("regime")},
    )
    pnl_pct = _compute_pnl_pct(entry_price, float(exit_price), trade.get("side", trade.get("direction")))
    return {"exit_reason": reason, "exit_price": float(exit_price), "pnl_pct": pnl_pct}
