from __future__ import annotations

from datetime import datetime, timezone


def _first_value(payload: dict, *keys: str):
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _format_age(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "—"
    if age_seconds < 60:
        return f"{age_seconds:.0f}s"
    return f"{age_seconds / 60:.1f}m"


def describe_feed_status(
    payload: dict | list | None,
    *,
    now_ts: float | None = None,
    warn_after_s: float = 20.0,
    stale_after_s: float = 45.0,
) -> dict:
    if not payload:
        return {"status": "ABSENT", "age_seconds": None, "age_label": "—"}

    now_ts = now_ts or datetime.now(timezone.utc).timestamp()
    ts = None

    if isinstance(payload, dict):
        raw_ts = payload.get("ts")
        if isinstance(raw_ts, (int, float)):
            ts = float(raw_ts)
        elif payload.get("updated_at"):
            try:
                ts = datetime.fromisoformat(
                    str(payload["updated_at"]).replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                ts = None

    age_seconds = max(0.0, now_ts - ts) if ts is not None else None
    if age_seconds is None:
        status = "UNKNOWN"
    elif age_seconds >= stale_after_s:
        status = "STALE"
    elif age_seconds >= warn_after_s:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "status": status,
        "age_seconds": age_seconds,
        "age_label": _format_age(age_seconds),
    }


def normalize_positions(positions: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for pos in positions:
        normalized.append(
            {
                "SYMBOL": _first_value(pos, "symbol") or "—",
                "SIDE": str(_first_value(pos, "side") or "—").upper(),
                "ENTRY": _first_value(pos, "entry_price", "entry"),
                "CURRENT": _first_value(pos, "current_price", "current"),
                "PNL USD": _first_value(pos, "pnl_usd"),
                "PNL %": _first_value(pos, "pnl_pct"),
                "SIZE USD": _first_value(pos, "size_usd"),
                "LEVERAGE": _first_value(pos, "leverage"),
                "REGIME": _first_value(pos, "regime") or "—",
                "AGE MIN": _first_value(pos, "age_min"),
            }
        )
    return normalized


def build_signal_lists(symbols: list[dict], top_n: int = 5) -> dict[str, list[dict]]:
    def row_key(symbol: dict) -> tuple:
        return (
            symbol.get("symbol", "—"),
            symbol.get("signal", "—"),
            symbol.get("score", 0),
        )

    def sort_key(symbol: dict) -> tuple:
        conviction = symbol.get("conviction_score")
        conviction_val = float(conviction) if conviction is not None else -1.0
        return (
            bool(symbol.get("trade_allowed")),
            bool(symbol.get("actionable")),
            bool(symbol.get("confirmed")),
            conviction_val,
            float(symbol.get("score", 0) or 0),
        )

    def compact_row(symbol: dict) -> dict:
        return {
            "Symbole": symbol.get("symbol", "—"),
            "Signal": symbol.get("signal", "—"),
            "Score": round(float(symbol.get("score", 0) or 0), 1),
            "Conviction": (
                round(float(symbol["conviction_score"]), 1)
                if symbol.get("conviction_score") is not None
                else None
            ),
            "Gate": "OK" if symbol.get("trade_allowed") else "BLOQUÉ",
            "Confirmé": "✓" if symbol.get("confirmed") else "✗",
            "Régime": symbol.get("regime", "—"),
        }

    dominant = sorted(symbols, key=sort_key, reverse=True)[:top_n]
    buys = [s for s in dominant if str(s.get("signal", "")).upper() == "BUY"]
    sells = [s for s in dominant if str(s.get("signal", "")).upper() == "SELL"]
    buy_keys = {row_key(s) for s in buys}
    sell_keys = {row_key(s) for s in sells}

    if len(buys) < top_n:
        extra_buys = [
            s
            for s in sorted(symbols, key=sort_key, reverse=True)
            if str(s.get("signal", "")).upper() == "BUY" and row_key(s) not in buy_keys
        ]
        buys.extend(extra_buys[: top_n - len(buys)])

    if len(sells) < top_n:
        extra_sells = [
            s
            for s in sorted(symbols, key=sort_key, reverse=True)
            if str(s.get("signal", "")).upper() == "SELL"
            and row_key(s) not in sell_keys
        ]
        sells.extend(extra_sells[: top_n - len(sells)])

    return {
        "dominant": [compact_row(s) for s in dominant],
        "buy": [compact_row(s) for s in buys[:top_n]],
        "sell": [compact_row(s) for s in sells[:top_n]],
    }


def summarize_multi_exchange(data: dict | None) -> dict:
    if not data:
        return {
            "coverage_pct": 0.0,
            "exchange_rows": [],
            "symbol_rows": [],
        }

    symbols = data.get("symbols", {}) or {}
    expected = int(data.get("total_exchanges") or 0)
    actual_prices = 0
    possible_prices = max(len(symbols), 1) * max(expected, 1)
    exchange_counts: dict[str, int] = {}
    symbol_rows: list[dict] = []

    for symbol, exchange_map in symbols.items():
        available = 0
        for exchange_name, payload in exchange_map.items():
            if payload.get("price") is not None:
                available += 1
                actual_prices += 1
                exchange_counts[exchange_name] = exchange_counts.get(exchange_name, 0) + 1
        spread = ((data.get("spreads", {}) or {}).get(symbol) or {}).get("spread_pct", 0)
        symbol_rows.append(
            {
                "Symbole": symbol,
                "Couverture": f"{available}/{expected or len(exchange_map) or 0}",
                "Spread %": round(float(spread or 0), 4),
                "Statut": "OK" if expected and available == expected else "PARTIEL",
            }
        )

    coverage_pct = round(actual_prices / possible_prices * 100, 1) if possible_prices else 0.0
    exchange_rows = [
        {
            "Exchange": exchange_name.upper(),
            "Couverture": f"{count}/{max(len(symbols), 1)}",
            "Statut": "OK" if count == len(symbols) and symbols else "PARTIEL",
        }
        for exchange_name, count in sorted(exchange_counts.items())
    ]

    return {
        "coverage_pct": coverage_pct,
        "exchange_rows": exchange_rows,
        "symbol_rows": sorted(symbol_rows, key=lambda row: row["Symbole"]),
    }
