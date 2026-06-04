import time
from dataclasses import dataclass, field
from typing import Optional

MEXC_FEE_RATE = 0.002  # 0.2% taker


@dataclass
class PaperPosition:
    symbol: str
    side: str  # "LONG" | "SHORT"
    entry_price: float
    size_usdt: float
    entry_time: float = field(default_factory=time.time)
    entry_rsi: float = 0.0


class PaperPositionManager:
    def __init__(self) -> None:
        self._position: Optional[PaperPosition] = None

    @property
    def in_position(self) -> bool:
        return self._position is not None

    @property
    def position(self) -> Optional[PaperPosition]:
        return self._position

    def open(
        self, symbol: str, side: str, price: float, size_usdt: float, rsi: float
    ) -> PaperPosition:
        if self._position is not None:
            raise RuntimeError(f"Already in position: {self._position}")
        self._position = PaperPosition(
            symbol=symbol,
            side=side,
            entry_price=price,
            size_usdt=size_usdt,
            entry_rsi=rsi,
        )
        return self._position

    def close(self, exit_price: float) -> tuple[PaperPosition, float, float, float]:
        """Returns (closed_pos, pnl_net, enl_already_paid_at_open, hold_seconds)."""
        if self._position is None:
            raise RuntimeError("No open position")
        pos = self._position
        hold_s = time.time() - pos.entry_time
        qty = pos.size_usdt / pos.entry_price
        if pos.side == "LONG":
            pnl_gross = (exit_price - pos.entry_price) * qty
        else:
            pnl_gross = (pos.entry_price - exit_price) * qty
        fee = pos.size_usdt * MEXC_FEE_RATE * 2  # entry + exit
        pnl_net = pnl_gross - fee
        self._position = None
        return pos, pnl_net, fee, hold_s

    def to_dict(self) -> dict | None:
        if self._position is None:
            return None
        p = self._position
        return {
            "symbol": p.symbol,
            "side": p.side,
            "entry_price": p.entry_price,
            "size_usdt": p.size_usdt,
            "entry_time": p.entry_time,
            "entry_rsi": p.entry_rsi,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "PaperPositionManager":
        mgr = cls()
        if data is not None:
            mgr._position = PaperPosition(
                symbol=data["symbol"],
                side=data["side"],
                entry_price=data["entry_price"],
                size_usdt=data["size_usdt"],
                entry_time=data["entry_time"],
                entry_rsi=data["entry_rsi"],
            )
        return mgr
