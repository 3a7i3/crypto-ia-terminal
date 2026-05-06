"""
dashboard_positions.py — Position Intelligence Dashboard

Affiche en temps réel :
  - Positions ouvertes (PnL live, SL/TP, risque liquidation)
  - Historique des positions fermées
  - Stats subcomptes (win rate, PnL cumulé)
  - Alertes liquidation

Usage :
    streamlit run dashboard_positions.py
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Position Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

REFRESH_INTERVAL = int(os.getenv("DASHBOARD_REFRESH", "10"))

SUBACCOUNTS = {
    "btc_momentum":    "BTC Momentum",
    "eth_volatility":  "ETH Volatility",
    "sol_experimental":"SOL Experimental",
    "shadow_validation":"Shadow / Validation",
    "genetic_optimizer":"Genetic Optimizer",
}


# ── Helpers lecture DB ──────────────────────────────────────────────────────────

@st.cache_data(ttl=REFRESH_INTERVAL)
def _load_trades(db_path: str, n: int = 100) -> list[dict]:
    if not Path(db_path).exists():
        return []
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (n,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except Exception:
        return []


_SNAPSHOT_PATH = Path(os.getenv("POSITION_SNAPSHOT", "databases/positions_snapshot.json"))


@st.cache_data(ttl=REFRESH_INTERVAL)
def _load_snapshot() -> list[dict]:
    """Lit le snapshot JSON écrit par advisor_loop après chaque enregistrement de position."""
    if not _SNAPSHOT_PATH.exists():
        return []
    try:
        import json
        data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return data.get("positions", [])
    except Exception:
        return []


def _pnl_color(val: float) -> str:
    return "color: #00ff88" if val >= 0 else "color: #ff4444"


# ── Layout ──────────────────────────────────────────────────────────────────────

st.title("📊 Position Intelligence Dashboard")
st.caption(f"Refresh toutes les {REFRESH_INTERVAL}s — {time.strftime('%H:%M:%S')}")

# ── Tentative de connexion au PositionManager live ──────────────────────────────

_pos_manager = None
_sub_manager = None

try:
    from quant_hedge_ai.agents.execution.subaccount_manager import SubaccountManager
    _sub_manager = SubaccountManager.from_env()
    # Récupère le premier position manager actif
    for unit in _sub_manager.all_active():
        if unit.position_manager:
            _pos_manager = unit.position_manager
            break
except Exception as _e:
    st.warning(f"SubaccountManager non disponible (mode lecture DB): {_e}")


# ── Section 1 : Positions ouvertes ─────────────────────────────────────────────

st.header("Positions ouvertes")

if _sub_manager:
    open_positions = _sub_manager.all_open_positions()
    global_pnl     = _sub_manager.global_pnl()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Positions ouvertes", len(open_positions))
    col2.metric("PnL ouvert",  f"{global_pnl['open_pnl_usd']:+.2f} $",
                delta_color="normal")
    col3.metric("PnL réalisé", f"{global_pnl['closed_pnl_usd']:+.2f} $",
                delta_color="normal")
    col4.metric("PnL total",   f"{global_pnl['total_pnl_usd']:+.2f} $",
                delta_color="normal")

    if open_positions:
        st.subheader("Détail positions")
        for pos in open_positions:
            liq_dist = pos.get("liq_dist_pct", 100)
            is_danger = liq_dist < 10

            with st.container():
                cols = st.columns([2, 1, 1, 1, 1, 1, 1, 1])
                side_icon = "🟢" if pos["side"] == "long" else "🔴"
                cols[0].markdown(f"**{side_icon} {pos['symbol']}** — *{pos.get('subaccount','?')}*")
                cols[1].metric("Entry", f"${pos['entry']:.2f}")
                cols[2].metric("Actuel", f"${pos['current']:.2f}")

                pnl_usd = pos["pnl_usd"]
                pnl_pct = pos["pnl_pct"]
                cols[3].metric("PnL $", f"{pnl_usd:+.2f}",
                               delta=f"{pnl_pct:+.1f}%",
                               delta_color="normal" if pnl_usd >= 0 else "inverse")

                cols[4].metric("SL", f"${pos['sl']:.2f}")
                cols[5].metric("TP", f"${pos['tp']:.2f}")
                cols[6].metric("Levier", f"x{pos.get('leverage', 1)}")

                liq_label = f"⚠️ {liq_dist:.0f}%" if is_danger else f"{liq_dist:.0f}%"
                cols[7].metric("Dist. Liq.", liq_label,
                               delta_color="inverse" if is_danger else "off")

                if is_danger:
                    st.error(f"🚨 RISQUE LIQUIDATION — {pos['symbol']} distance: {liq_dist:.1f}%")

                # Barre de progression PnL (de -sl% à +tp%)
                sl_pct  = 2.0   # défaut 2%
                tp_pct  = 4.0   # défaut 4%
                progress = min(1.0, max(0.0, (pnl_pct + sl_pct) / (sl_pct + tp_pct)))
                st.progress(progress, text=f"Progression vers TP: {pnl_pct:+.1f}%")
                st.divider()
    else:
        st.info("Aucune position ouverte.")
else:
    # Fallback 1 : snapshot JSON écrit par advisor_loop
    _snapshot_positions = _load_snapshot()
    if _snapshot_positions:
        st.info(f"⚡ Source : snapshot advisor_loop ({len(_snapshot_positions)} position(s))")
        for pos in _snapshot_positions:
            liq_dist = pos.get("liq_dist_pct", 100)
            is_danger = liq_dist < 10
            with st.container():
                cols = st.columns([2, 1, 1, 1, 1, 1, 1, 1])
                side_icon = "🟢" if pos.get("side") == "long" else "🔴"
                cols[0].markdown(f"**{side_icon} {pos['symbol']}** — *{pos.get('subaccount','?')}*")
                cols[1].metric("Entry", f"${pos['entry']:.2f}")
                cols[2].metric("Actuel", f"${pos.get('current', pos['entry']):.2f}")
                pnl_usd = pos.get("pnl_usd", 0.0)
                pnl_pct = pos.get("pnl_pct", 0.0)
                cols[3].metric("PnL $", f"{pnl_usd:+.2f}",
                               delta=f"{pnl_pct:+.1f}%",
                               delta_color="normal" if pnl_usd >= 0 else "inverse")
                cols[4].metric("SL", f"${pos.get('sl', 0.0):.2f}")
                cols[5].metric("TP", f"${pos.get('tp', 0.0):.2f}")
                cols[6].metric("Levier", f"x{pos.get('leverage', 1)}")
                liq_label = f"⚠️ {liq_dist:.0f}%" if is_danger else f"{liq_dist:.0f}%"
                cols[7].metric("Dist. Liq.", liq_label,
                               delta_color="inverse" if is_danger else "off")
                if is_danger:
                    st.error(f"🚨 RISQUE LIQUIDATION — {pos['symbol']} distance: {liq_dist:.1f}%")
                sl_pct  = 2.0
                tp_pct  = 4.0
                progress = min(1.0, max(0.0, (pnl_pct + sl_pct) / (sl_pct + tp_pct)))
                st.progress(progress, text=f"Progression vers TP: {pnl_pct:+.1f}%")
                st.divider()
    else:
        st.info("Connecter les subcomptes pour voir les positions live.")


# ── Section 2 : Stats par subcompte ────────────────────────────────────────────

st.header("Performance par subcompte")

if _sub_manager:
    global_stats = _sub_manager.global_stats()
    cols = st.columns(len(global_stats))
    for i, (name, stats) in enumerate(global_stats.items()):
        label = SUBACCOUNTS.get(name, name)
        pos_s = stats.get("positions", {})
        with cols[i]:
            st.subheader(label)
            active = stats.get("active", False)
            halted = stats.get("halted", False)
            status = "🔴 HALTED" if halted else ("🟢 Actif" if active else "⚫ Inactif")
            st.caption(status)
            if pos_s:
                st.metric("Positions fermées", pos_s.get("closed_count", 0))
                st.metric("Win rate", f"{pos_s.get('win_rate', 0):.0%}")
                pnl = pos_s.get("total_pnl_usd", 0)
                st.metric("PnL réalisé", f"{pnl:+.2f} $",
                          delta_color="normal" if pnl >= 0 else "inverse")
            guard = stats.get("guard", {})
            if guard:
                dd = guard.get("session_drawdown_pct", 0)
                st.progress(min(1.0, abs(dd) / 3.0),
                            text=f"Drawdown session: {dd:.1f}%")
else:
    # Mode fallback : lecture SQLite directe
    st.subheader("Lecture depuis base de données")
    for name, label in SUBACCOUNTS.items():
        db_path = f"databases/trade_log_{name}.sqlite"
        trades  = _load_trades(db_path, n=50)
        if trades:
            with st.expander(f"{label} — {len(trades)} trades"):
                import pandas as pd
                df = pd.DataFrame(trades)
                st.dataframe(df[["ts", "symbol", "action", "size", "mode", "status"]].head(20),
                             use_container_width=True)


# ── Section 3 : Historique trades SQLite ───────────────────────────────────────

st.header("Historique des trades")

selected_sub = st.selectbox("Subcompte", list(SUBACCOUNTS.keys()),
                             format_func=lambda x: SUBACCOUNTS[x])
db_path = f"databases/trade_log_{selected_sub}.sqlite"
# Fallback sur la DB principale
if not Path(db_path).exists():
    db_path = os.getenv("EXEC_TRADE_LOG", "databases/trade_log.sqlite")

trades = _load_trades(db_path, n=200)
if trades:
    import pandas as pd
    df = pd.DataFrame(trades)
    # Stats rapides
    c1, c2, c3 = st.columns(3)
    c1.metric("Total trades", len(df))
    ok   = df[df.get("status", pd.Series()) == "ok"] if "status" in df else df
    c2.metric("Exécutés", len(ok))
    rej  = df[df.get("status", pd.Series()) == "error"] if "status" in df else pd.DataFrame()
    c3.metric("Erreurs", len(rej))
    cols_show = [c for c in ["ts", "symbol", "action", "size", "mode", "status", "error"]
                 if c in df.columns]
    st.dataframe(df[cols_show], use_container_width=True, height=300)
else:
    st.info(f"Aucun trade enregistré pour {SUBACCOUNTS[selected_sub]}.")


# ── Section 4 : Alertes et événements ──────────────────────────────────────────

st.header("Événements récents")

audit_path = Path("supervision/alerts_audit.jsonl")
if audit_path.exists():
    import json
    events = []
    try:
        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        for line in lines[-30:]:
            if line.strip():
                events.append(json.loads(line))
    except Exception:
        pass
    if events:
        import pandas as pd
        df_ev = pd.DataFrame(events[::-1])
        cols_ev = [c for c in ["ts", "type", "severity", "module", "message"]
                   if c in df_ev.columns]
        st.dataframe(df_ev[cols_ev], use_container_width=True, height=250)
    else:
        st.info("Aucun événement récent.")
else:
    st.info("Fichier audit non trouvé.")


# ── Auto-refresh ────────────────────────────────────────────────────────────────

time.sleep(REFRESH_INTERVAL)
st.rerun()
