"""
Event writer adapters for MVP → Tracker logger migration.

Provides compatibility wrappers to convert MVP logger call patterns
to unified tracker_system.core.trade_logger interface.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tracker_system.config.settings import TRADES_LOG_FILE
from tracker_system.core.trade_logger import log_entry, log_exit


def _direction_to_side(direction: str) -> str:
    raw = str(direction or "BUY").strip().upper()
    if raw in {"LONG", "long"}:
        return "BUY"
    if raw in {"SHORT", "short"}:
        return "SELL"
    if raw in {"BUY", "buy"}:
        return "BUY"
    if raw in {"SELL", "sell"}:
        return "SELL"
    return raw


def record_entry_from_mvp(
    symbol: str,
    direction: str,
    signal_type: str,
    regime: str,
    entry_price: float,
    size_usd: float,
    stop_loss: float,
    take_profit: float,
    score: float,
    confidence: float,
    atr_pct: float,
    paper: bool,
    log_file: Path = TRADES_LOG_FILE,
) -> dict[str, Any]:
    """
    MVP→Tracker adapter for entry events.

    Converts MVP parameter names/types to unified logger interface.

    Args:
        direction: "long" or "short" (MVP nomenclature)
        size_usd: USD value (MVP nomenclature)
        All other params: direct from MVP logger

    Returns:
        Event dict written to logs/trades.jsonl
    """
    return log_entry(
        symbol=symbol,
        side=_direction_to_side(direction),
        entry_price=entry_price,
        size=size_usd,
        stop_loss=stop_loss,
        take_profit=take_profit,
        regime=regime,
        confidence=confidence,
        log_file=log_file,
        signal_type=signal_type,
        score=score,
        atr_pct=atr_pct,
        paper=paper,
    )


def record_exit_from_mvp(
    symbol: str,
    direction: str,
    signal_type: str,
    regime: str,
    entry_price: float,
    exit_price: float,
    size_usd: float,
    pnl_usd: float,
    pnl_pct: float,
    exit_reason: str,
    duration_minutes: float,
    attribution: str,
    fee_usd: float,
    price_path: list[float] | None = None,
    confidence: float | None = None,
    log_file: Path = TRADES_LOG_FILE,
) -> dict[str, Any]:
    """
    MVP→Tracker adapter for exit events.

    Converts MVP parameter names to unified logger interface.
    Computes MFE/MAE from price_path and position metrics.

    Args:
        direction: "long" or "short" (MVP nomenclature)
        size_usd: USD value (MVP nomenclature)
        price_path: Historical prices (optional, used for MFE/MAE)
        All other params: direct from MVP logger

    Returns:
        Event dict written to logs/trades.jsonl
    """
    if price_path is None:
        price_path = []

    side = _direction_to_side(direction)

    if not price_path:
        path = []
        mfe = pnl_pct if pnl_pct > 0 else 0.0
        mae = pnl_pct if pnl_pct < 0 else 0.0
    else:
        entry = entry_price
        path = list(price_path)

        if side == "BUY":
            mfe = (max(path) - entry) / entry if path else 0.0
            mae = (min(path) - entry) / entry if path else 0.0
        else:
            mfe = (entry - min(path)) / entry if path else 0.0
            mae = (entry - max(path)) / entry if path else 0.0

    position = {
        "symbol": symbol,
        "side": side,
        "direction": direction,
        "entry_price": entry_price,
        "size": size_usd,
        "size_usd": size_usd,
        "regime": regime,
        "confidence": confidence,
        "signal_type": signal_type,
        "price_path": path,
    }

    return log_exit(
        position=position,
        exit_price=exit_price,
        pnl_pct=pnl_pct,
        pnl_usd=pnl_usd,
        mfe=mfe,
        mae=mae,
        exit_reason=exit_reason,
        duration_min=duration_minutes,
        log_file=log_file,
    )
