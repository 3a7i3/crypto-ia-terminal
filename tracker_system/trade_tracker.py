"""
trade_tracker.py — Suivi des positions ouvertes (entry / exit / PnL)

Lit logs/trades.jsonl (écrit par mvp/trade_logger.py).
Maintient l'état des positions dans logs/open_positions.json.
Peut être lancé indépendamment du MVP.

Usage:
    python tracker_system/trade_tracker.py          # update positions
    python tracker_system/trade_tracker.py --status # affiche positions ouvertes
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_FILE = Path("logs/open_positions.json")
LOG_FILE   = Path("logs/trades.jsonl")
_MAX_PATH  = 150   # points max dans price_path — cohérent avec trade_logger


# ── Persistence ───────────────────────────────────────────────────────────────

def load_positions() -> list[dict]:
    if not STATE_FILE.exists():
        return []
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_positions(positions: list[dict]) -> None:
    """Persiste les positions ouvertes — price_path exclu du fichier (reconstruit en mémoire)."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    slim = [{k: v for k, v in p.items() if k != "price_path"} for p in positions]
    STATE_FILE.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")


def append_log(event: dict[str, Any]) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    event.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


# ── Entry / Exit ──────────────────────────────────────────────────────────────

def open_position(
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
    timestamp: str,
) -> None:
    positions = load_positions()
    pos_id = f"{symbol.replace('/', '')}_{int(datetime.now(timezone.utc).timestamp())}"
    position = {
        "id": pos_id,
        "symbol": symbol,
        "direction": direction,
        "signal_type": signal_type,
        "regime": regime,
        "entry_price": entry_price,
        "size_usd": size_usd,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "score": score,
        "confidence": confidence,
        "atr_pct": atr_pct,
        "paper": paper,
        "entry_ts": timestamp,
        "max_price": entry_price,
        "min_price": entry_price,
        "price_path": [],
    }
    positions.append(position)
    save_positions(positions)


def close_position(pos: dict, exit_price: float, exit_reason: str, write_log: bool = False) -> dict:
    """
    Calcule PnL, MFE, MAE et retourne le record.

    write_log=False (défaut) : mode MVP — trade_logger est la source autoritaire du JSONL,
                               on ne réécrit pas.
    write_log=True           : mode standalone — le tracker est seul, il écrit lui-même.
    """
    entry  = pos["entry_price"]
    direction = pos["direction"]
    size   = pos["size_usd"]

    pnl_pct = ((exit_price - entry) / entry) if direction == "long" else (
               (entry - exit_price) / entry)
    pnl_usd = size * pnl_pct

    # MFE / MAE depuis le price_path
    path = pos.get("price_path", [])
    if path and direction == "long":
        mfe = max((p - entry) / entry for p in path)
        mae = min((p - entry) / entry for p in path)
    elif path and direction == "short":
        mfe = max((entry - p) / entry for p in path)
        mae = min((entry - p) / entry for p in path)
    else:
        mfe = pnl_pct if pnl_pct > 0 else 0.0
        mae = pnl_pct if pnl_pct < 0 else 0.0

    now = datetime.now(timezone.utc).isoformat()
    try:
        raw_ts = pos["entry_ts"]
        if isinstance(raw_ts, (int, float)):
            entry_dt = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
        else:
            entry_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        duration_min = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60.0
    except Exception:
        duration_min = 0.0

    record = {
        "type": "exit",
        "id": pos.get("id", "unknown"),
        "symbol": pos["symbol"],
        "direction": direction,
        "signal_type": pos.get("signal_type", "unknown"),
        "regime": pos.get("regime", "unknown"),
        "entry_price": entry,
        "exit_price": exit_price,
        "size_usd": size,
        "pnl_pct": round(pnl_pct, 6),
        "pnl_usd": round(pnl_usd, 4),
        "win": pnl_usd > 0,
        "mfe": round(mfe, 6),
        "mae": round(mae, 6),
        "exit_reason": exit_reason,
        "duration_minutes": round(duration_min, 1),
        "paper": pos.get("paper", True),
        "price_path": [round(p, 8) for p in path[-_MAX_PATH:]],
        "timestamp": now,
    }
    if write_log:
        append_log(record)
    return record


# ── Update cycle ──────────────────────────────────────────────────────────────

def update_positions(
    current_prices: dict[str, float],
    max_duration_min: float = 240.0,
) -> list[dict]:
    """
    Met à jour les positions ouvertes avec les prix courants.
    Ferme si SL/TP atteint ou durée max dépassée.
    Retourne la liste des positions fermées dans ce cycle.
    """
    positions = load_positions()
    open_positions = []
    closed = []

    now = datetime.now(timezone.utc)

    for pos in positions:
        symbol = pos["symbol"]
        price  = current_prices.get(symbol)

        if price is None:
            open_positions.append(pos)
            continue

        # Accumule le price_path (max 150 points — suffisant pour MFE/MAE + backtester)
        pos.setdefault("price_path", []).append(price)
        if len(pos["price_path"]) > 150:
            pos["price_path"].pop(0)
        pos["max_price"] = max(pos.get("max_price", price), price)
        pos["min_price"] = min(pos.get("min_price", price), price)

        pos["entry_price"]
        direction = pos["direction"]
        sl        = pos["stop_loss"]
        tp        = pos["take_profit"]

        # Durée
        try:
            raw_ts = pos["entry_ts"]
            if isinstance(raw_ts, (int, float)):
                entry_dt = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
            else:
                entry_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            duration_min = (now - entry_dt).total_seconds() / 60.0
        except Exception:
            duration_min = 0.0

        exit_reason = None

        if direction == "long":
            if price <= sl:
                exit_reason = f"SL @ {price:.4f}"
            elif price >= tp:
                exit_reason = f"TP @ {price:.4f}"
        else:
            if price >= sl:
                exit_reason = f"SL @ {price:.4f}"
            elif price <= tp:
                exit_reason = f"TP @ {price:.4f}"

        if exit_reason is None and duration_min >= max_duration_min:
            exit_reason = f"TIME_EXIT ({duration_min:.0f}min)"

        if exit_reason:
            record = close_position(pos, price, exit_reason, write_log=True)
            closed.append(record)
            print(f"[Tracker] FERMÉ {symbol} | {exit_reason} | PnL={record['pnl_usd']:+.4f}$")
        else:
            open_positions.append(pos)

    save_positions(open_positions)
    return closed


# ── Sync depuis trades.jsonl (rejouer les entrées non trackées) ───────────────

def sync_from_log() -> int:
    """Recharge les entrées depuis trades.jsonl non encore dans open_positions."""
    if not LOG_FILE.exists():
        return 0

    existing_ids = {p["id"] for p in load_positions()}
    added = 0

    with LOG_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line.strip())
            except Exception:
                continue
            if ev.get("type") != "entry":
                continue

            pos_id = ev.get("id", f"{ev['symbol'].replace('/', '')}_{ev.get('timestamp', '')}")
            if pos_id in existing_ids:
                continue

            open_position(
                symbol=ev["symbol"],
                direction=ev["direction"],
                signal_type=ev.get("signal_type", "unknown"),
                regime=ev.get("regime", "unknown"),
                entry_price=ev["entry_price"],
                size_usd=ev["size_usd"],
                stop_loss=ev["stop_loss"],
                take_profit=ev["take_profit"],
                score=ev.get("score", 0),
                confidence=ev.get("confidence", 0),
                atr_pct=ev.get("atr_pct", 0),
                paper=ev.get("paper", True),
                timestamp=ev.get("timestamp", datetime.now(timezone.utc).isoformat()),
            )
            existing_ids.add(pos_id)
            added += 1

    return added


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Trade Tracker")
    parser.add_argument("--status", action="store_true", help="Affiche positions ouvertes")
    parser.add_argument("--sync",   action="store_true", help="Sync depuis trades.jsonl")
    args = parser.parse_args()

    if args.sync:
        n = sync_from_log()
        print(f"[Tracker] {n} positions importées depuis trades.jsonl")
        return

    positions = load_positions()
    if args.status or not positions:
        print(f"\n=== Positions ouvertes ({len(positions)}) ===")
        for p in positions:
            print(f"  {p['symbol']} {p['direction'].upper()} @ {p['entry_price']:.4f} "
                  f"| SL={p['stop_loss']:.4f} TP={p['take_profit']:.4f} "
                  f"| {p['signal_type']} / {p['regime']}")
        return

    print("Lancez avec --status pour voir les positions, ou --sync pour importer depuis le log.")


if __name__ == "__main__":
    main()
