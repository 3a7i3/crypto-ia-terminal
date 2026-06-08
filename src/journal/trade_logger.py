from datetime import datetime, timezone

from src.domain.trade_event import TradeEvent


class TradeLogger:
    def __init__(self):
        self._open_logs: list[dict] = []  # événements d'ouverture (opérationnel)
        self._closed_trades: list[TradeEvent] = []  # vérité économique (SSoT)

    # -- EventBus subscribers --

    def on_trade_opened(self, event: dict) -> None:
        self._open_logs.append(
            {
                "type": "OPENED",
                "symbol": event.get("symbol"),
                "side": event.get("side"),
                "entry": event.get("price"),
                "run_id": event.get("run_id"),
                "strategy_id": event.get("strategy_id"),
                "confidence": event.get("confidence"),
                "market_state": event.get("market_state"),
                "timestamp": event.get("timestamp") or _now(),
            }
        )

    def on_trade_closed(self, event: dict) -> None:
        trade = event.get("trade_event")
        if isinstance(trade, TradeEvent):
            self._closed_trades.append(trade)

    # -- Backward-compat property (open logs only) --

    @property
    def logs(self) -> list[dict]:
        return self._open_logs

    # -- Query helpers --

    def closed_trades(self) -> list[TradeEvent]:
        return list(self._closed_trades)

    def total_pnl(self) -> float:
        return float(sum(t.net_pnl_usd for t in self._closed_trades))

    def win_rate(self) -> float:
        if not self._closed_trades:
            return 0.0
        wins = sum(1 for t in self._closed_trades if t.net_pnl_usd > 0)
        return wins / len(self._closed_trades)

    def by_run(self, run_id: str) -> list[TradeEvent]:
        return [t for t in self._closed_trades if t.run_id == run_id]

    def by_strategy(self, strategy_id: str) -> list[TradeEvent]:
        return [t for t in self._closed_trades if t.strategy_id == strategy_id]

    def replay(self) -> list:
        """Retourne opens (dict) + closes (TradeEvent) en ordre chronologique."""
        return list(self._open_logs) + list(self._closed_trades)

    def reset(self) -> None:
        self._open_logs.clear()
        self._closed_trades.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
