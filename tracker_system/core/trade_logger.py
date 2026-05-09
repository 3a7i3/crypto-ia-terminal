from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracker_system.config.settings import PRICE_PATH_LIMIT, TRADES_LOG_FILE
from tracker_system.storage.saver import append_jsonl


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _legacy_direction(side: str | None) -> str:
    raw = str(side or "BUY").strip().upper()
    if raw in {"BUY", "LONG"}:
        return "long"
    if raw in {"SELL", "SHORT"}:
        return "short"
    return raw.lower()


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


def log_event(
    event: dict[str, Any], log_file: Path = TRADES_LOG_FILE
) -> dict[str, Any]:
    payload = dict(event)
    payload.setdefault("logged_at", _utcnow_iso())
    payload.setdefault("timestamp", _utcnow_iso())
    append_jsonl(log_file, payload)
    return payload


def log_entry(
    symbol: str,
    side: str,
    entry_price: float,
    size: float,
    stop_loss: float,
    take_profit: float,
    regime: str | None = None,
    confidence: float | None = None,
    log_file: Path = TRADES_LOG_FILE,
    **extra: Any,
) -> dict[str, Any]:
    if stop_loss is None or take_profit is None:
        raise ValueError("stop_loss and take_profit are required")
    normalized_side = str(side).strip().upper()
    legacy_direction = _legacy_direction(normalized_side)
    numeric_size = float(size)
    payload = {
        "type": "entry",
        "symbol": symbol,
        "side": normalized_side,
        "direction": legacy_direction,
        "entry_price": float(entry_price),
        "size": numeric_size,
        "size_usd": numeric_size,
        "regime": _text_default(regime, "unknown"),
        "confidence": _float_default(confidence, 0.0),
        "stop_loss": float(stop_loss),
        "take_profit": float(take_profit),
        **extra,
    }
    payload.setdefault("signal_type", _text_default(payload.get("signal"), "unknown"))
    payload.setdefault("score", 0.0)
    payload.setdefault("atr_pct", payload.get("atr_ratio", 0.0))
    payload.setdefault("paper", True)
    return log_event(payload, log_file=log_file)


def log_exit(
    position: dict[str, Any],
    exit_price: float,
    pnl_pct: float,
    pnl_usd: float,
    mfe: float,
    mae: float,
    exit_reason: str,
    duration_min: float,
    log_file: Path = TRADES_LOG_FILE,
) -> dict[str, Any]:
    side = (
        str(position.get("side") or position.get("direction") or "BUY").strip().upper()
    )
    legacy_direction = _legacy_direction(side)
    size = float(position.get("size", position.get("size_usd", 0.0)))
    rounded_duration = round(duration_min, 3)
    rounded_pnl_pct = round(pnl_pct, 6)
    rounded_pnl_usd = round(pnl_usd, 6)
    rounded_mfe = round(mfe, 6)
    rounded_mae = round(mae, 6)
    # fee estimé: 0.04% par side (taker Gate.io/Binance)
    _fee_usd = round(size * 0.0004 * 2, 4)
    # R-multiple = PnL réalisé / risque initial (en $)
    _entry = float(position.get("entry_price") or 0.0)
    _sl = float(position.get("stop_loss") or 0.0)
    _risk_usd = abs(_entry - _sl) / _entry * size if _entry and _sl else 0.0
    _r_multiple = round(rounded_pnl_usd / _risk_usd, 3) if _risk_usd > 0 else 0.0
    payload = {
        "type": "exit",
        "id": position.get("id"),
        "symbol": position.get("symbol"),
        "side": side,
        "direction": legacy_direction,
        "entry_price": position.get("entry_price"),
        "exit_price": float(exit_price),
        "size": size,
        "size_usd": size,
        "regime": _text_default(position.get("regime"), "unknown"),
        "confidence": _float_default(position.get("confidence"), 0.0),
        "pnl_pct": rounded_pnl_pct,
        "pnl_usd": rounded_pnl_usd,
        "mfe": rounded_mfe,
        "mae": rounded_mae,
        "win": rounded_pnl_usd > 0,
        "duration_min": rounded_duration,
        "duration_minutes": rounded_duration,
        "exit_reason": exit_reason,
        "fee_usd": _fee_usd,
        "r_multiple": _r_multiple,
        "price_path": [
            round(float(price), 8)
            for price in position.get("price_path", [])[-PRICE_PATH_LIMIT:]
        ],
    }
    payload.setdefault(
        "signal_type",
        _text_default(position.get("signal_type", position.get("signal")), "unknown"),
    )
    payload.setdefault("paper", bool(position.get("paper", True)))
    return log_event(payload, log_file=log_file)
