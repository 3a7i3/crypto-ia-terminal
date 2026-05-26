from __future__ import annotations

import json
import time
from pathlib import Path

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.execution.paper_trading_engine")
_STATE_FILE = Path("databases/paper_trading/state.json")


class PaperTradingEngine:
    def __init__(
        self,
        initial_balance: float = 100_000.0,
        persist: bool = True,
    ) -> None:
        self._initial_balance = initial_balance
        self._persist = persist
        self._size_factor: float = 1.0
        self.balance: float = initial_balance
        self.positions: dict[str, float] = {}
        self.trade_history: list[dict] = []
        self.equity_curve: list[dict] = []  # [{ts, value}]

        if persist:
            self._load()

    def set_size_factor(self, factor: float) -> None:
        self._size_factor = max(0.0, min(1.0, float(factor)))

    # ── Exécution ─────────────────────────────────────────────────────────────

    def execute(self, order: dict, mark_price: float) -> dict:
        symbol = order["symbol"]
        action = order["action"]
        size = float(order["size"])
        notional = size * mark_price
        pnl = 0.0

        if action == "BUY" and self.balance >= notional:
            self.balance -= notional
            self.positions[symbol] = self.positions.get(symbol, 0.0) + size
        elif action == "SELL":
            current = self.positions.get(symbol, 0.0)
            sold = min(current, size)
            # P&L estimé : supposons entrée au prix courant pour simplifier
            pnl = sold * mark_price - sold * mark_price * 0.998  # 0.2 % slippage fictif
            self.positions[symbol] = current - sold
            self.balance += sold * mark_price

        ts = int(time.time() * 1000)
        trade = {
            "ts": ts,
            "symbol": symbol,
            "action": action,
            "size": round(size, 6),
            "price": round(mark_price, 4),
            "notional": round(notional, 2),
            "pnl": round(pnl, 4),
            "balance": round(self.balance, 2),
        }
        self.trade_history.append(trade)

        equity = self.portfolio_value({symbol: mark_price})
        self.equity_curve.append({"ts": ts, "value": round(equity, 2)})

        if self._persist:
            self._save()

        return {
            "balance": round(self.balance, 2),
            "positions": {k: round(v, 6) for k, v in self.positions.items() if v > 0},
            "last_trade": trade,
        }

    # ── Métriques ─────────────────────────────────────────────────────────────

    def portfolio_value(self, mark_prices: dict[str, float]) -> float:
        pos_value = sum(
            qty * mark_prices.get(sym, 0.0)
            for sym, qty in self.positions.items()
            if qty > 0
        )
        return self.balance + pos_value

    def total_pnl(self) -> float:
        return round(sum(t["pnl"] for t in self.trade_history), 4)

    def win_rate(self) -> float:
        sells = [t for t in self.trade_history if t["action"] == "SELL"]
        if not sells:
            return 0.0
        wins = sum(1 for t in sells if t["pnl"] > 0)
        return round(wins / len(sells), 4)

    def snapshot(self, mark_prices: dict[str, float] | None = None) -> dict:
        mark_prices = mark_prices or {}
        portfolio = self.portfolio_value(mark_prices)
        return {
            "balance": round(self.balance, 2),
            "portfolio_value": round(portfolio, 2),
            "pnl_total": round(portfolio - self._initial_balance, 2),
            "pnl_pct": round((portfolio / self._initial_balance - 1) * 100, 4),
            "positions": {k: round(v, 6) for k, v in self.positions.items() if v > 0},
            "n_trades": len(self.trade_history),
            "win_rate": self.win_rate(),
            "equity_curve": self.equity_curve[-200:],
            "trade_history": self.trade_history[-50:],
        }

    # ── Persistance ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "balance": self.balance,
            "initial_balance": self._initial_balance,
            "positions": self.positions,
            "trade_history": self.trade_history[-500:],
            "equity_curve": self.equity_curve[-1000:],
        }
        _STATE_FILE.write_text(json.dumps(state), encoding="utf-8")

    def _load(self) -> None:
        if not _STATE_FILE.exists():
            return
        try:
            state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            self.balance = state.get("balance", self._initial_balance)
            self._initial_balance = state.get("initial_balance", self._initial_balance)
            self.positions = state.get("positions", {})
            self.trade_history = state.get("trade_history", [])
            self.equity_curve = state.get("equity_curve", [])
        except (json.JSONDecodeError, KeyError) as exc:
            _log.warning(
                "[PaperTradingEngine] Etat corrompu ou incomplet — reset: %s", exc
            )

    def reset(self) -> None:
        self.balance = self._initial_balance
        self.positions = {}
        self.trade_history = []
        self.equity_curve = []
        if self._persist and _STATE_FILE.exists():
            _STATE_FILE.unlink()
