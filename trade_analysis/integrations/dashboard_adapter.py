"""
trade_analysis/integrations/dashboard_adapter.py — Lecture du sidecar LMI
pour l'API du dashboard.

Fonctions pures : elles lisent lmi_live_state.json et retournent des dicts
prets a serialiser en JSON. Aucune dependance FastAPI (testable seul).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

# Un symbole dont le dernier etat date de plus de STALE_MS est "stale".
STALE_MS = 15_000


def _resolve_live_state_file() -> Path:
    """Résolu à chaque appel — injectable par env, testable, jamais figé."""
    return Path(os.getenv("LMI_DIR", "databases/trade_analysis")) / "lmi_live_state.json"


def _load(path: Path | None = None) -> dict:
    p = path if path is not None else _resolve_live_state_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def lmi_status(path: Path | None = None) -> dict:
    """Etat global de l'observatoire."""
    data = _load(path)
    stats = data.get("stats", {})
    symbols = data.get("symbols", {})
    fresh = sum(1 for s in symbols.values() if s.get("age_ms", 1e9) <= STALE_MS)
    contract_meta = data.get("contract_meta", {})
    return {
        "running": bool(symbols),
        "exchange": data.get("exchange"),
        "updated_at": data.get("updated_at"),
        "symbols_watched": stats.get("symbols_watched", len(data.get("watchlist", []))),
        "symbols_active": stats.get("symbols_active", len(symbols)),
        "symbols_fresh": fresh,
        "events": stats.get("events", 0),
        # Provenance scientifique des unites : "api" = fiable, sinon degrade.
        "contract_source": contract_meta.get("source", "unknown"),
        "contract_degraded": bool(contract_meta.get("degraded_symbols")),
    }


def _row(sym: str, st: dict) -> dict:
    flow = st.get("flow", {})
    res = st.get("resistance", {})
    buy = flow.get("buy_volume_usd", 0.0)
    sell = flow.get("sell_volume_usd", 0.0)
    total = buy + sell
    buy_pressure = round(flow.get("pressure_ratio", 0.5) * 100, 0)
    return {
        "symbol": sym,
        "state": st.get("state", "quiet"),
        "state_confidence": st.get("state_confidence", 0.0),
        "buy_pressure": buy_pressure,
        "sell_pressure": round(100 - buy_pressure, 0),
        "price": st.get("price", 0.0),
        "price_change_bps": st.get("price_change_bps", 0.0),
        "executed_buy_usd": round(buy, 0),
        "executed_sell_usd": round(sell, 0),
        "total_flow_usd": round(total, 0),
        "resistance": round(res.get("resistance_score", 0.0), 0),
        "fragility": round(res.get("fragility_score", 0.0), 3),
        "age_ms": st.get("age_ms", 0),
        "stale": st.get("age_ms", 1e9) > STALE_MS,
    }


def lmi_table(path: Path | None = None) -> dict:
    """Tableau resume de tous les symboles observes."""
    data = _load(path)
    symbols = data.get("symbols", {})
    rows = [_row(sym, st) for sym, st in symbols.items()]
    rows.sort(key=lambda r: r["total_flow_usd"], reverse=True)
    return {
        "data": rows,
        "count": len(rows),
        "updated_at": data.get("updated_at"),
    }


def lmi_symbol(symbol: str, path: Path | None = None) -> Optional[dict]:
    """Detail microstructure complet d'un symbole (None si absent)."""
    data = _load(path)
    symbols = data.get("symbols", {})
    key = symbol.replace("/", "").replace("_", "").upper()
    st = symbols.get(key)
    if st is None:
        for k, v in symbols.items():
            if key in k:
                st = v
                key = k
                break
    if st is None:
        return None
    liq = st.get("liquidity", {})
    return {
        "symbol": key,
        "summary": _row(key, st),
        "liquidity": {
            "consumed_usd": round(
                liq.get("bid_consumed_usd", 0.0) + liq.get("ask_consumed_usd", 0.0), 0
            ),
            "removed_usd": round(
                liq.get("bid_removed_usd", 0.0) + liq.get("ask_removed_usd", 0.0), 0
            ),
            "added_usd": round(
                liq.get("bid_added_usd", 0.0) + liq.get("ask_added_usd", 0.0), 0
            ),
            "cancellation_rate_bid": liq.get("cancellation_rate_bid", 0.0),
            "cancellation_rate_ask": liq.get("cancellation_rate_ask", 0.0),
        },
        "state_components": st.get("state_components", {}),
        "raw": st,
    }


def lmi_events(path: Path | None = None, min_confidence: float = 0.6) -> dict:
    """
    Etats "notables" en cours (confiance >= seuil et etat non-QUIET).
    Sert d'alimentation au fil d'evenements de recherche.
    """
    data = _load(path)
    symbols = data.get("symbols", {})
    events = []
    for sym, st in symbols.items():
        state = st.get("state", "quiet")
        conf = st.get("state_confidence", 0.0)
        if state == "quiet" or conf < min_confidence:
            continue
        if st.get("age_ms", 1e9) > STALE_MS:
            continue
        events.append(
            {
                "symbol": sym,
                "state": state,
                "confidence": round(conf, 3),
                "buy_pressure": round(
                    st.get("flow", {}).get("pressure_ratio", 0.5) * 100, 0
                ),
                "price": st.get("price", 0.0),
            }
        )
    events.sort(key=lambda e: e["confidence"], reverse=True)
    return {"data": events, "count": len(events), "updated_at": data.get("updated_at")}
