"""
trade_logger.py — Logger de trades découplé

Ecrit dans logs/trades.jsonl. Aucune dépendance vers le reste du MVP.
Format : 1 ligne JSON par événement (entry / exit / signal_detected).

Schéma par type :
  signal_detected : meta seulement (pas de price_path)
  entry           : meta + niveaux SL/TP (pas de price_path)
  exit            : meta + pnl + price_path tronqué à _MAX_PATH points
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from observability.json_logger import get_logger

_log = get_logger("mvp.trade_logger")
_LOG_FILE = Path("logs/trades.jsonl")
_MAX_PATH = 150  # points max dans price_path — ~2h30 à 1min d'intervalle


def log_event(data: dict[str, Any]) -> None:
    """Ajoute un événement dans logs/trades.jsonl (une ligne JSON)."""
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, default=str) + "\n")
    except Exception as exc:
        _log.debug("[TradeLogger] erreur: %s", exc)


def log_signal(
    symbol: str,
    signal_type: str,
    direction: str,
    score: float,
    confidence: float,
    price: float,
    regime: str,
    trade_allowed: bool,
) -> None:
    """Loggue un signal détecté (pas encore un trade)."""
    log_event(
        {
            "type": "signal_detected",
            "symbol": symbol,
            "signal_type": signal_type,
            "direction": direction,
            "score": round(score, 2),
            "confidence": round(confidence, 4),
            "price": price,
            "regime": regime,
            "trade_allowed": trade_allowed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def log_entry(
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
) -> None:
    """Loggue l'ouverture d'une position."""
    log_event(
        {
            "type": "entry",
            "symbol": symbol,
            "direction": direction,
            "signal_type": signal_type,
            "regime": regime,
            "entry_price": entry_price,
            "size_usd": round(size_usd, 2),
            "stop_loss": round(stop_loss, 8),
            "take_profit": round(take_profit, 8),
            "score": round(score, 2),
            "confidence": round(confidence, 4),
            "atr_pct": round(atr_pct, 6),
            "paper": paper,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def log_exit(
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
) -> None:
    """
    Loggue la fermeture d'une position.
    price_path est tronqué à _MAX_PATH points (depuis la fin — les plus récents).
    """
    path = (price_path or [])[-_MAX_PATH:]
    log_event(
        {
            "type": "exit",
            "symbol": symbol,
            "direction": direction,
            "signal_type": signal_type,
            "regime": regime,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "size_usd": round(size_usd, 2),
            "pnl_usd": round(pnl_usd, 4),
            "pnl_pct": round(pnl_pct, 6),
            "win": pnl_usd > 0,
            "exit_reason": exit_reason,
            "duration_minutes": round(duration_minutes, 1),
            "attribution": attribution,
            "fee_usd": round(fee_usd, 4),
            "price_path": [round(p, 8) for p in path],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
