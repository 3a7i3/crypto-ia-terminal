"""
dashboard_multi_exchange.py — Comparaison prix live multi-exchange.

Sources : Binance, Bybit, OKX, MEXC, Hyperliquid (publiques, sans clé API)
Données sync depuis VPS via vps_data_sync.py toutes les 30s.

Lancement :
    streamlit run dashboard_multi_exchange.py --server.port 8510
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

SNAPSHOT = Path("databases/multi_exchange_snapshot.json")
REFRESH = 30

st.set_page_config(
    page_title="Crypto AI — Multi-Exchange",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
.stApp { background: #0a0c12; }
.ex-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 0.7rem 1rem;
    margin-bottom: 0.4rem;
    font-family: monospace;
    font-size: 0.85rem;
}
.spread-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 700;
    font-family: monospace;
}
</style>
""",
    unsafe_allow_html=True,
)

EXCHANGES = ["binance", "bybit", "okx", "mexc", "hyperliquid"]
EXCHANGE_COLORS = {
    "binance": "#f3ba2f",
    "bybit": "#f7a600",
    "okx": "#00d4aa",
    "mexc": "#1d9bf0",
    "hyperliquid": "#a855f7",
}
SYM_LABELS = {
    "BTCUSDT": "BTC/USDT",
    "ETHUSDT": "ETH/USDT",
    "SOLUSDT": "SOL/USDT",
    "DOGEUSDT": "DOGE/USDT",
}


@st.cache_data(ttl=REFRESH)
def load() -> dict:
    if not SNAPSHOT.exists():
        return {}
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fmt_price(p) -> str:
    if p is None:
        return "—"
    if p > 1000:
        return f"${p:,.2f}"
    if p > 1:
        return f"${p:.4f}"
    return f"${p:.6f}"


def spread_color(pct: float) -> str:
    if pct < 0.05:
        return "#22c55e"
    if pct < 0.15:
        return "#f59e0b"
    return "#ef4444"


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("## 🌐 Multi-Exchange — Prix Live")
st.caption("Données publiques — aucune clé API requise | Refresh 30s")

data = load()

if not data:
    st.warning(
        "Aucune donnée disponible. Vérifier que `multi_exchange_feed.py` tourne sur le VPS "
        "et que `vps_data_sync.py` est actif."
    )
    st.stop()

# ── Métriques globales ─────────────────────────────────────────────────────────

updated = data.get("updated_at", "")[:19].replace("T", " ")
ex_ok = data.get("exchanges_ok", 0)
ex_total = data.get("total_exchanges", 5)

col_h1, col_h2, col_h3 = st.columns(3)
with col_h1:
    st.metric("Exchanges actifs", f"{ex_ok}/{ex_total}")
with col_h2:
    st.metric("Symboles suivis", str(len(data.get("symbols", {}))))
with col_h3:
    st.metric("Dernière mise à jour", updated if updated else "—")

st.divider()

# ── Tableau comparatif par symbole ────────────────────────────────────────────

symbols_data = data.get("symbols", {})
spreads_data = data.get("spreads", {})

for sym, label in SYM_LABELS.items():
    ex_data = symbols_data.get(sym, {})
    if not ex_data:
        continue

    spread_info = spreads_data.get(sym, {})
    spread_pct = spread_info.get("spread_pct", 0)
    cheapest = spread_info.get("cheapest", "")
    most_exp = spread_info.get("most_expensive", "")

    spread_col = spread_color(spread_pct)
    spread_html = (
        f'<span class="spread-badge" style="background:{spread_col}22;color:{spread_col};">'
        f"spread {spread_pct:.3f}%</span>"
    )

    st.markdown(
        f"### {label} &nbsp; {spread_html}",
        unsafe_allow_html=True,
    )

    prices = {ex: d["price"] for ex, d in ex_data.items() if d.get("price")}
    ref_price = prices.get("binance") or (list(prices.values())[0] if prices else None)

    cols = st.columns(len(EXCHANGES))
    for i, ex in enumerate(EXCHANGES):
        d = ex_data.get(ex)
        col = cols[i]
        color = EXCHANGE_COLORS.get(ex, "#94a3b8")
        with col:
            if d and d.get("price"):
                price = d["price"]
                change = d.get("change_24h_pct")
                diff_pct = ((price - ref_price) / ref_price * 100) if ref_price else 0
                tag = "✓ moins cher" if ex == cheapest and cheapest else ""
                tag = "↑ plus cher" if ex == most_exp and most_exp else tag

                change_str = f"{change:+.2f}%" if change is not None else "—"
                diff_str = (
                    f"{diff_pct:+.3f}% vs Binance" if ex != "binance" else "référence"
                )

                st.markdown(
                    f'<div class="ex-card">'
                    f'<span style="color:{color};font-weight:700;">{ex.upper()}</span>'
                    f" {tag}<br>"
                    f'<span style="font-size:1.1rem;font-weight:700;">{fmt_price(price)}</span><br>'
                    f'<span style="color:#94a3b8;">{change_str} 24h | {diff_str}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="ex-card">'
                    f'<span style="color:{color};font-weight:700;">{ex.upper()}</span><br>'
                    f'<span style="color:#475569;">Non disponible</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # Graphique historique des prix (si plusieurs exchanges)
    if len(prices) >= 2:
        df_prices = pd.DataFrame(
            [{"exchange": ex, "price": p} for ex, p in prices.items()]
        )
        st.dataframe(
            df_prices.style.format({"price": "{:.6g}"}),
            width="stretch",
            hide_index=True,
        )

    st.markdown("---")

# ── Tableau récapitulatif des spreads ──────────────────────────────────────────

if spreads_data:
    st.markdown("### Spreads inter-exchange")
    rows = []
    for sym, info in spreads_data.items():
        rows.append(
            {
                "Symbole": SYM_LABELS.get(sym, sym),
                "Prix min": fmt_price(info.get("min_price")),
                "Prix max": fmt_price(info.get("max_price")),
                "Spread %": f"{info.get('spread_pct', 0):.4f}%",
                "Moins cher": info.get("cheapest", "—").upper(),
                "Plus cher": info.get("most_expensive", "—").upper(),
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

# ── Auto-refresh ───────────────────────────────────────────────────────────────

st.caption(f"Auto-refresh dans {REFRESH}s")
time.sleep(0.1)
st.rerun() if False else None  # déclenché par TTL cache
