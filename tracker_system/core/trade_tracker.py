from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracker_system.config.settings import (
    DEFAULT_MAX_POSITION_DURATION_MIN,
    OPEN_POSITIONS_FILE,
    PRICE_PATH_LIMIT,
    TRADES_LOG_FILE,
)
from tracker_system.core.position_manager import load_positions, save_positions
from tracker_system.core.trade_logger import log_entry, log_exit
from tracker_system.engine.exit_factory import build_exit_engine
from tracker_system.engine.exit_engine import ExitEngine
from tracker_system.storage.loader import load_jsonl


def _normalize_side(side: str | None) -> str:
    raw = str(side or "BUY").strip().upper()
    if raw in {"BUY", "LONG"}:
        return "BUY"
    if raw in {"SELL", "SHORT"}:
        return "SELL"
    return raw


def _text_default(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _float_default(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _utc_timestamp() -> float:
    return time.time()


def _parse_event_timestamp(raw_timestamp: Any) -> float:
    if isinstance(raw_timestamp, (float, int)):
        return float(raw_timestamp)
    if isinstance(raw_timestamp, str) and raw_timestamp:
        try:
            return datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return _utc_timestamp()
    return _utc_timestamp()


def _duration_minutes(position: dict[str, Any], now_ts: float) -> float:
    try:
        raw_timestamp = position.get("timestamp", position.get("entry_ts"))
        return max(0.0, (now_ts - _parse_event_timestamp(raw_timestamp)) / 60.0)
    except (KeyError, TypeError, ValueError):
        return 0.0


def open_position(
    symbol: str,
    side: str,
    price: float,
    size: float,
    regime: str | None = None,
    confidence: float | None = None,
    log_file: Path = TRADES_LOG_FILE,
    state_file: Path = OPEN_POSITIONS_FILE,
    **extra: Any,
) -> dict[str, Any]:
    positions = load_positions(state_file)
    now_ts = _utc_timestamp()
    entry_price = float(price)
    stop_loss = extra.pop("stop_loss", 0.0)
    take_profit = extra.pop("take_profit", 0.0)
    position = {
        "id": extra.pop("id", f"{symbol}_{int(now_ts * 1000)}"),
        "symbol": symbol,
        "side": _normalize_side(side),
        "entry_price": entry_price,
        "size": float(size),
        "timestamp": extra.pop("timestamp", now_ts),
        "regime": regime,
        "confidence": confidence,
        "stop_loss": float(stop_loss),
        "take_profit": float(take_profit),
        "max_price": entry_price,
        "min_price": entry_price,
        "price_path": [entry_price],
        **extra,
    }
    positions.append(position)
    save_positions(positions, state_file)
    log_entry(symbol, position["side"], entry_price, float(size), stop_loss=float(stop_loss), take_profit=float(take_profit), regime=regime, confidence=confidence, log_file=log_file, id=position["id"])
    return position


def close_position(
    position: dict[str, Any],
    price: float,
    exit_reason: str = "MANUAL_EXIT",
    log_file: Path = TRADES_LOG_FILE,
) -> dict[str, Any]:
    now_ts = _utc_timestamp()
    entry_price = float(position["entry_price"])
    exit_price = float(price)
    size = float(position.get("size", position.get("size_usd", 0.0)))
    side = _normalize_side(position.get("side", position.get("direction")))

    if side == "BUY":
        pnl_pct = (exit_price - entry_price) / entry_price
        mfe = (float(position.get("max_price", entry_price)) - entry_price) / entry_price
        mae = (float(position.get("min_price", entry_price)) - entry_price) / entry_price
    else:
        pnl_pct = (entry_price - exit_price) / entry_price
        mfe = (entry_price - float(position.get("min_price", entry_price))) / entry_price
        mae = (entry_price - float(position.get("max_price", entry_price))) / entry_price

    pnl_usd = pnl_pct * size
    record = log_exit(
        position,
        exit_price=exit_price,
        pnl_pct=pnl_pct,
        pnl_usd=pnl_usd,
        mfe=mfe,
        mae=mae,
        exit_reason=exit_reason,
        duration_min=_duration_minutes(position, now_ts),
        log_file=log_file,
    )
    record["closed_at"] = datetime.now(timezone.utc).isoformat()
    return record


def finalize_position(
    position_id: str,
    price: float,
    exit_reason: str,
    state_file: Path = OPEN_POSITIONS_FILE,
    log_file: Path = TRADES_LOG_FILE,
    fallback_position: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    positions = load_positions(state_file)
    remaining_positions: list[dict[str, Any]] = []
    target_position: dict[str, Any] | None = None

    for position in positions:
        if target_position is None and str(position.get("id")) == str(position_id):
            target_position = position
            continue
        remaining_positions.append(position)

    if target_position is None:
        if fallback_position is None:
            return None
        target_position = dict(fallback_position)
        target_position.setdefault("id", position_id)

    current_price = float(price)
    target_position.setdefault("price_path", []).append(current_price)
    target_position["max_price"] = max(float(target_position.get("max_price", current_price)), current_price)
    target_position["min_price"] = min(float(target_position.get("min_price", current_price)), current_price)

    record = close_position(target_position, current_price, exit_reason=exit_reason, log_file=log_file)
    save_positions(remaining_positions, state_file)
    return record


def sync_entries_from_log(
    log_file: Path = TRADES_LOG_FILE,
    state_file: Path = OPEN_POSITIONS_FILE,
) -> int:
    events = load_jsonl(log_file)
    positions = load_positions(state_file)
    existing_ids = {position.get("id") for position in positions if position.get("id") is not None}
    closed_ids = {
        event.get("id")
        for event in events
        if event.get("type") == "exit" and event.get("id") is not None
    }
    added = 0

    for event in events:
        if event.get("type") != "entry":
            continue
        event_id = event.get("id")
        if event_id is not None and event_id in existing_ids:
            continue
        if event_id is not None and event_id in closed_ids:
            continue
        positions.append(
            {
                "id": event_id or f"{event.get('symbol')}_{int(_utc_timestamp() * 1000)}",
                "symbol": event.get("symbol"),
                "side": _normalize_side(event.get("side", event.get("direction"))),
                "entry_price": float(event.get("entry_price", 0.0)),
                "size": float(event.get("size", event.get("size_usd", 0.0))),
                "timestamp": _parse_event_timestamp(event.get("timestamp", event.get("entry_ts"))),
                "regime": _text_default(event.get("regime"), "unknown"),
                "confidence": _float_default(event.get("confidence"), 0.0),
                "signal_type": _text_default(event.get("signal_type", event.get("signal")), "unknown"),
                "score": float(event.get("score", 0.0)),
                "atr_pct": float(event.get("atr_pct", event.get("atr_ratio", 0.0))),
                "paper": bool(event.get("paper", True)),
                "stop_loss": float(event.get("stop_loss", 0.0)),
                "take_profit": float(event.get("take_profit", 0.0)),
                "max_price": float(event.get("entry_price", 0.0)),
                "min_price": float(event.get("entry_price", 0.0)),
                "price_path": [float(event.get("entry_price", 0.0))],
            }
        )
        if event_id is not None:
            existing_ids.add(event_id)
        added += 1

    save_positions(positions, state_file)
    return added


def update_positions(
    current_prices: dict[str, float],
    exit_engine: ExitEngine | None = None,
    max_duration_min: float = DEFAULT_MAX_POSITION_DURATION_MIN,
    state_file: Path = OPEN_POSITIONS_FILE,
    log_file: Path = TRADES_LOG_FILE,
) -> list[dict[str, Any]]:
    positions = load_positions(state_file)
    remaining_positions: list[dict[str, Any]] = []
    closed_positions: list[dict[str, Any]] = []
    now_ts = _utc_timestamp()

    for position in positions:
        symbol = position.get("symbol")
        current_price = current_prices.get(symbol)
        if current_price is None:
            remaining_positions.append(position)
            continue

        price = float(current_price)
        position.setdefault("price_path", []).append(price)
        if len(position["price_path"]) > PRICE_PATH_LIMIT:
            position["price_path"] = position["price_path"][-PRICE_PATH_LIMIT:]
        position["max_price"] = max(float(position.get("max_price", price)), price)
        position["min_price"] = min(float(position.get("min_price", price)), price)

        dynamic_engine = exit_engine or build_exit_engine(position.get("regime"), position.get("confidence"))
        exit_reason = dynamic_engine.check_exit(position, price, context={"regime": position.get("regime")})
        if exit_reason is None and _duration_minutes(position, now_ts) >= max_duration_min:
            exit_reason = f"TIME_EXIT @ {price:.8f}"

        if exit_reason:
            closed_positions.append(close_position(position, price, exit_reason=exit_reason, log_file=log_file))
        else:
            remaining_positions.append(position)

    save_positions(remaining_positions, state_file)
    return closed_positions
