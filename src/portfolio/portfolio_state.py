from src.domain.position import Position


class PortfolioState:
    def __init__(self, balance: float):
        self.balance = balance
        self.positions: dict[str, Position] = {}

    def mark_to_market(self, price_map: dict) -> float:
        unrealized = 0.0
        for symbol, position in self.positions.items():
            price = price_map.get(symbol)
            if price is None:
                continue
            if position.side == "long":
                position.unrealized_pnl = (price - position.entry_price) * position.size
            else:
                position.unrealized_pnl = (position.entry_price - price) * position.size
            unrealized += position.unrealized_pnl
        return self.balance + unrealized

    def snapshot(self) -> dict:
        return {
            "balance": self.balance,
            "positions": {
                symbol: {
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "size": pos.size,
                    "entry_price": pos.entry_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                }
                for symbol, pos in self.positions.items()
            },
        }
