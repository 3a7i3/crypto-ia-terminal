"""
dashboard_unified.py — Cockpit central Crypto AI Terminal.

Layer 1 : System Health (toujours visible en haut)
Layer 2 : Tabs — Trading | Système | IA | Analyse | Alertes
Layer 3 : Expanders — détail à la demande

Usage:
    streamlit run dashboard_unified.py --server.port 8500
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import time
from datetime import datetime

import streamlit as st
from dashboard_unified_helpers import (
    build_signal_lists,
    describe_feed_status,
    normalize_positions,
    summarize_multi_exchange,
)

ROOT = pathlib.Path(__file__).parent
DB = ROOT / "databases"
LOGS = ROOT / "logs"

st.set_page_config(
    page_title="Crypto AI Terminal",
    page_icon="🎛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS : terminal professionnel ──────────────────────────────────────────────
st.markdown(
    """
<style>
/* Global */
body, [data-testid="stAppViewContainer"] { background: #0a0e1a; }
[data-testid="stSidebar"] { display: none; }

/* Score cards Layer 1 */
.score-card {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    text-align: center;
    min-height: 80px;
}
.score-label {
    font-size: 0.65rem;
    font-weight: 700;
    color: #4b5563;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 0.3rem;
}
.score-value {
    font-size: 1.4rem;
    font-weight: 800;
    color: #f9fafb;
    font-family: 'Courier New', monospace;
}
.score-sub {
    font-size: 0.7rem;
    color: #6b7280;
    margin-top: 0.1rem;
}

/* Status dots */
.dot-green { color: #22c55e; }
.dot-yellow { color: #f59e0b; }
.dot-red { color: #ef4444; }
.dot-blue { color: #3b82f6; }
.dot-gray { color: #6b7280; }

/* Header barre */
.cockpit-header {
    border-bottom: 1px solid #1e293b;
    padding-bottom: 0.5rem;
    margin-bottom: 0.8rem;
}
.cockpit-title {
    font-size: 0.8rem;
    font-weight: 700;
    color: #3b82f6;
    letter-spacing: 0.15em;
    text-transform: uppercase;
}
.cockpit-time {
    font-size: 0.75rem;
    color: #374151;
    font-family: monospace;
}

/* Tabs */
[data-testid="stTabs"] button {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em;
    color: #6b7280 !important;
    padding: 0.4rem 1rem !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #f9fafb !important;
    border-bottom: 2px solid #3b82f6 !important;
}

/* Metric compact */
[data-testid="stMetric"] label { font-size: 0.7rem !important; }
[data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.1rem !important; }

/* Séparateur de section */
.section-title {
    font-size: 0.7rem;
    font-weight: 700;
    color: #374151;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    border-left: 3px solid #1d4ed8;
    padding-left: 0.5rem;
    margin: 0.8rem 0 0.4rem 0;
}
</style>
""",
    unsafe_allow_html=True,
)


# ── Chargement de données (cache 10s) ─────────────────────────────────────────


@st.cache_data(ttl=10, show_spinner=False)
def load_live_snapshot() -> dict:
    p = DB / "live_snapshot.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


@st.cache_data(ttl=10, show_spinner=False)
def load_positions_snapshot() -> dict | list:
    p = DB / "positions_snapshot.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


@st.cache_data(ttl=10, show_spinner=False)
def load_positions() -> list[dict]:
    data = load_positions_snapshot()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("positions", [])
    return []


@st.cache_data(ttl=15, show_spinner=False)
def load_multi_exchange_snapshot() -> dict:
    p = DB / "multi_exchange_snapshot.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


@st.cache_data(ttl=30, show_spinner=False)
def load_strategy_ranking() -> dict:
    p = DB / "strategy_ranking.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


@st.cache_data(ttl=30, show_spinner=False)
def load_regret_analysis(n: int = 50) -> list[dict]:
    p = DB / "regret_analysis.jsonl"
    if not p.exists():
        return []
    try:
        lines = p.read_text().strip().splitlines()[-n:]
        return [json.loads(ln) for ln in lines if ln]
    except Exception:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def load_shadow_log(n: int = 30) -> list[dict]:
    p = DB / "shadow_execution" / "shadow_log.jsonl"
    if not p.exists():
        return []
    try:
        lines = p.read_text().strip().splitlines()[-n:]
        return [json.loads(ln) for ln in lines if ln]
    except Exception:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def load_mistake_memory(n: int = 20) -> list[dict]:
    p = DB / "mistake_memory.jsonl"
    if not p.exists():
        return []
    try:
        lines = p.read_text().strip().splitlines()[-n:]
        return [json.loads(ln) for ln in lines if ln]
    except Exception:
        return []


@st.cache_data(ttl=10, show_spinner=False)
def load_cycle_history(n: int = 50) -> list[dict]:
    p = DB / "cycle_data.jsonl"
    if not p.exists():
        return []
    try:
        lines = p.read_text().strip().splitlines()[-n:]
        return [json.loads(ln) for ln in lines if ln]
    except Exception:
        return []


@st.cache_data(ttl=15, show_spinner=False)
def load_recent_trades(n: int = 20) -> list[dict]:
    try:
        conn = sqlite3.connect(str(ROOT / "databases" / "trade_log.sqlite"))
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (n,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def bot_is_running() -> bool:
    pid_file = LOGS / "advisor_loop.pid"
    if not pid_file.exists():
        return False
    try:
        import os

        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def last_log_lines(n: int = 20) -> list[str]:
    p = LOGS / "advisor_loop.log"
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except Exception:
        return []


# ── Données ───────────────────────────────────────────────────────────────────
snap = load_live_snapshot()
positions_snapshot = load_positions_snapshot()
positions = load_positions()
multi_exchange = load_multi_exchange_snapshot()
ranking = load_strategy_ranking()
shadow = load_shadow_log()
mistakes = load_mistake_memory()
cycles = load_cycle_history()
trades = load_recent_trades()
regrets = load_regret_analysis()
bot_ok = bot_is_running()

cycle_num = snap.get("cycle", "—")
capital = snap.get("capital", 1000.0)
safe_mode = snap.get("safe_mode", False)
n_actionable = snap.get("n_actionable", 0)
n_traded = snap.get("n_traded", 0)
n_refused = snap.get("n_refused", 0)
cycle_ms = snap.get("cycle_duration_ms", 0)

open_pos = [p for p in positions if p.get("status", "open") == "open"]
display_positions = normalize_positions(open_pos)
total_pnl = sum(p.get("pnl_usd", 0.0) for p in positions)
win_count = sum(1 for p in positions if p.get("pnl_usd", 0) > 0)
total_closed = sum(1 for p in positions if p.get("status") == "closed")
win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0.0
signal_lists = build_signal_lists(snap.get("symbols", []), top_n=5)
live_feed = describe_feed_status(snap)
positions_feed = describe_feed_status(positions_snapshot)
multi_exchange_feed = describe_feed_status(multi_exchange)
multi_exchange_summary = summarize_multi_exchange(multi_exchange)

# ── LAYER 1 — Cockpit header ──────────────────────────────────────────────────
now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
bot_dot = "🟢" if bot_ok else "🔴"
safe_dot = "🟡 SAFE MODE" if safe_mode else ""

st.markdown(
    f'<div class="cockpit-header">'
    f'<span class="cockpit-title">⚙ CRYPTO AI TERMINAL</span>'
    f'&nbsp;&nbsp;<span class="cockpit-time">{bot_dot} BOT &nbsp;|&nbsp; '
    f"Cycle {cycle_num} &nbsp;|&nbsp; {now_str} &nbsp;{safe_dot}</span>"
    f"</div>",
    unsafe_allow_html=True,
)


# ── Score cards (8 indicateurs critiques) ────────────────────────────────────
def score_card(label: str, value: str, sub: str = "", color: str = "#f9fafb") -> str:
    return (
        f'<div class="score-card">'
        f'<div class="score-label">{label}</div>'
        f'<div class="score-value" style="color:{color}">{value}</div>'
        f'<div class="score-sub">{sub}</div>'
        f"</div>"
    )


# Couleurs dynamiques
bot_color = "#22c55e" if bot_ok else "#ef4444"
pnl_color = "#22c55e" if total_pnl >= 0 else "#ef4444"
wr_color = "#22c55e" if win_rate >= 50 else ("#f59e0b" if win_rate >= 35 else "#ef4444")
p5_progress = min(len([p for p in positions if p.get("status") == "closed"]), 30)
p5_color = (
    "#22c55e" if p5_progress >= 20 else ("#f59e0b" if p5_progress >= 10 else "#3b82f6")
)

c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
with c1:
    st.markdown(
        score_card(
            "BOT", "RUN" if bot_ok else "DOWN", f"cycle {cycle_ms:.0f}ms", bot_color
        ),
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        score_card("P5 TRADES", f"{p5_progress}/30", "objectif GO/NO-GO", p5_color),
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        score_card(
            "PNL SESSION",
            f"{'+'if total_pnl>=0 else ''}{total_pnl:.2f}$",
            f"{total_closed} fermés",
            pnl_color,
        ),
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        score_card(
            "WIN RATE",
            f"{win_rate:.0f}%",
            f"{win_count}W / {total_closed-win_count}L",
            wr_color,
        ),
        unsafe_allow_html=True,
    )
with c5:
    pos_color = "#3b82f6" if len(open_pos) > 0 else "#4b5563"
    st.markdown(
        score_card("POSITIONS", str(len(open_pos)), "ouvertes", pos_color),
        unsafe_allow_html=True,
    )
with c6:
    sig_color = "#22c55e" if n_actionable > 0 else "#4b5563"
    st.markdown(
        score_card(
            "SIGNAUX",
            str(n_actionable),
            f"/{snap.get('n_symbols', 20)} analysés",
            sig_color,
        ),
        unsafe_allow_html=True,
    )
with c7:
    cap_color = "#22c55e" if capital >= 900 else "#f59e0b"
    st.markdown(
        score_card("CAPITAL", f"${capital:.0f}", "disponible", cap_color),
        unsafe_allow_html=True,
    )
with c8:
    sm_color = "#f59e0b" if safe_mode else "#22c55e"
    sm_label = "SAFE MODE" if safe_mode else "ACTIF"
    st.markdown(
        score_card("GATE", sm_label, "trading", sm_color), unsafe_allow_html=True
    )

st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

# ── LAYER 2 — Navigation par tabs ─────────────────────────────────────────────
tab_trading, tab_system, tab_ai, tab_analyse, tab_alertes = st.tabs(
    [
        "📈  TRADING",
        "⚙️  SYSTÈME",
        "🧠  IA & APPRENTISSAGE",
        "📊  ANALYSE",
        "🚨  ALERTES",
    ]
)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — TRADING
# ═════════════════════════════════════════════════════════════════════════════
with tab_trading:
    col_left, col_right = st.columns([3, 2])

    with col_left:
        # Positions ouvertes
        st.markdown(
            '<div class="section-title">POSITIONS OUVERTES</div>',
            unsafe_allow_html=True,
        )
        if open_pos:
            import pandas as pd

            df_pos = pd.DataFrame(display_positions)
            st.dataframe(df_pos, use_container_width=True, hide_index=True)
        else:
            st.caption("Aucune position ouverte.")

        # Derniers trades
        st.markdown(
            '<div class="section-title">DERNIERS TRADES (20)</div>',
            unsafe_allow_html=True,
        )
        if trades:
            import pandas as pd

            df_t = pd.DataFrame(trades)
            show_cols = [
                c
                for c in [
                    "timestamp",
                    "symbol",
                    "side",
                    "size_usd",
                    "entry_price",
                    "exit_price",
                    "pnl_usd",
                    "regime",
                ]
                if c in df_t.columns
            ]
            if show_cols:
                st.dataframe(df_t[show_cols], use_container_width=True, hide_index=True)
        else:
            with st.expander("Shadow Execution (30 derniers)"):
                if shadow:
                    import pandas as pd

                    df_sh = pd.DataFrame(shadow)
                    show_sh = [
                        c
                        for c in [
                            "symbol",
                            "action",
                            "signal_score",
                            "signal_price",
                            "notional",
                            "slippage_pct",
                            "regime",
                        ]
                        if c in df_sh.columns
                    ]
                    st.dataframe(
                        df_sh[show_sh] if show_sh else df_sh,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("Pas de shadow log.")

    with col_right:
        st.markdown(
            '<div class="section-title">TOP 5 DOMINATION</div>', unsafe_allow_html=True
        )
        if signal_lists["dominant"]:
            import pandas as pd

            st.dataframe(
                pd.DataFrame(signal_lists["dominant"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Aucun signal dominant disponible.")

        split_buy, split_sell = st.columns(2)
        with split_buy:
            st.markdown(
                '<div class="section-title">TOP 5 BUY</div>', unsafe_allow_html=True
            )
            if signal_lists["buy"]:
                st.dataframe(
                    pd.DataFrame(signal_lists["buy"]),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Aucun BUY prioritaire.")
        with split_sell:
            st.markdown(
                '<div class="section-title">TOP 5 SELL</div>', unsafe_allow_html=True
            )
            if signal_lists["sell"]:
                st.dataframe(
                    pd.DataFrame(signal_lists["sell"]),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Aucun SELL prioritaire.")

        # Breakdown refus
        st.markdown(
            '<div class="section-title">REFUS CE CYCLE</div>', unsafe_allow_html=True
        )
        refusal = snap.get("refusal_breakdown", {})
        if refusal:
            for reason, count in sorted(refusal.items(), key=lambda x: -x[1]):
                bar_pct = min(int(count / max(refusal.values()) * 100), 100)
                bar_html = (
                    f"<div style='display:flex;justify-content:space-between;"
                    f"font-size:0.75rem;margin-bottom:4px'>"
                    f"<span style='color:#9ca3af'>{reason}</span>"
                    f"<span style='color:#f9fafb;font-weight:700'>{count}</span></div>"
                    f"<div style='background:#1e293b;border-radius:3px;height:4px;"
                    f"margin-bottom:8px'>"
                    f"<div style='background:#3b82f6;width:{bar_pct}%;"
                    f"height:4px;border-radius:3px'></div></div>"
                )
                st.markdown(bar_html, unsafe_allow_html=True)
        else:
            st.caption("—")

        # Cycle history
        st.markdown(
            '<div class="section-title">ACTIVITÉ (50 CYCLES)</div>',
            unsafe_allow_html=True,
        )
        if cycles:
            import pandas as pd

            df_cy = pd.DataFrame(cycles)
            if "n_traded" in df_cy.columns and "ts" in df_cy.columns:
                import plotly.express as px

                df_cy["heure"] = pd.to_datetime(df_cy["ts"], unit="s").dt.strftime(
                    "%H:%M"
                )
                fig = px.bar(
                    df_cy.tail(30),
                    x="heure",
                    y="n_traded",
                    color_discrete_sequence=["#3b82f6"],
                    height=160,
                )
                fig.update_layout(
                    margin=dict(l=0, r=0, t=0, b=0),
                    plot_bgcolor="#111827",
                    paper_bgcolor="#111827",
                    font_color="#9ca3af",
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=False, title=""),
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — SYSTÈME
# ═════════════════════════════════════════════════════════════════════════════
with tab_system:
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            '<div class="section-title">RUNTIME BOT</div>', unsafe_allow_html=True
        )
        st.metric("Statut", "🟢 Running" if bot_ok else "🔴 Arrêté")
        st.metric("Cycle actuel", cycle_num)
        st.metric("Durée cycle", f"{cycle_ms:.0f} ms" if cycle_ms else "—")
        st.metric("Capital", f"${capital:.0f}")
        st.metric("Safe Mode", "🟡 Actif" if safe_mode else "✅ Inactif")

    with c2:
        st.markdown('<div class="section-title">EXCHANGE</div>', unsafe_allow_html=True)
        exchange_raw = snap.get("exchange", "gateio")
        if isinstance(exchange_raw, dict):
            exchange_name = exchange_raw.get("name", exchange_raw.get("id", "gateio"))
            ex_latency = exchange_raw.get("last_latency_ms", 0)
            ex_up = exchange_raw.get("uptime_pct", 100)
            st.metric("Exchange", str(exchange_name))
            st.metric("Latence", f"{ex_latency:.0f} ms")
            st.metric("Uptime", f"{ex_up:.1f}%")
        else:
            st.metric("Exchange", str(exchange_raw) or "gateio")
        st.metric("Symboles", snap.get("n_symbols", 20))
        regime_dist = snap.get("regime_distribution", {})
        if regime_dist:
            dominant = max(regime_dist, key=regime_dist.get)
            st.metric("Régime dominant", dominant)

    with c3:
        st.markdown(
            '<div class="section-title">CYCLE DISTRIBUTION</div>',
            unsafe_allow_html=True,
        )
        if regime_dist:
            for r, count in sorted(regime_dist.items(), key=lambda x: -x[1]):
                pct = count / sum(regime_dist.values()) * 100
                st.markdown(
                    f"<div style='font-size:0.75rem;color:#9ca3af;margin-bottom:6px'>"
                    f"{r} — <b style='color:#f9fafb'>{pct:.0f}%</b></div>",
                    unsafe_allow_html=True,
                )

    st.markdown(
        '<div class="section-title">CONNECTIVITÉ DONNÉES</div>',
        unsafe_allow_html=True,
    )
    feed_c1, feed_c2, feed_c3, feed_c4 = st.columns(4)
    with feed_c1:
        st.metric("Live snapshot", live_feed["status"], live_feed["age_label"])
    with feed_c2:
        st.metric("Positions", positions_feed["status"], positions_feed["age_label"])
    with feed_c3:
        st.metric(
            "Multi-exchange",
            multi_exchange_feed["status"],
            multi_exchange_feed["age_label"],
        )
    with feed_c4:
        st.metric("Mode trading", "SAFE" if safe_mode else "ACTIF")

    multi_c1, multi_c2 = st.columns([2, 3])
    with multi_c1:
        st.markdown(
            '<div class="section-title">COUVERTURE MULTI-EXCHANGE</div>',
            unsafe_allow_html=True,
        )
        st.metric("Couverture globale", f"{multi_exchange_summary['coverage_pct']:.1f}%")
        if multi_exchange_summary["exchange_rows"]:
            import pandas as pd

            st.dataframe(
                pd.DataFrame(multi_exchange_summary["exchange_rows"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Snapshot multi-exchange absent.")
    with multi_c2:
        st.markdown(
            '<div class="section-title">COUVERTURE PAR SYMBOLE</div>',
            unsafe_allow_html=True,
        )
        if multi_exchange_summary["symbol_rows"]:
            import pandas as pd

            st.dataframe(
                pd.DataFrame(multi_exchange_summary["symbol_rows"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Aucune donnée multi-exchange disponible.")

    st.markdown('<div class="section-title">LOGS RÉCENTS</div>', unsafe_allow_html=True)
    with st.expander("Dernières lignes du log bot", expanded=False):
        log_lines = last_log_lines(30)
        if log_lines:
            log_text = "".join(log_lines)
            st.code(log_text, language=None)
        else:
            st.caption("Log introuvable.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — IA & APPRENTISSAGE
# ═════════════════════════════════════════════════════════════════════════════
with tab_ai:
    col_rank, col_mem = st.columns(2)

    with col_rank:
        st.markdown(
            '<div class="section-title">STRATEGY RANKER</div>', unsafe_allow_html=True
        )
        scores_section = ranking.get("scores", {})
        events_section = ranking.get("events", [])
        if scores_section:
            import pandas as pd

            rows = []
            for strat, info in scores_section.items():
                rows.append(
                    {
                        "Stratégie": strat,
                        "Score": round(info.get("composite_score", 0), 3),
                        "WR": f"{info.get('win_rate', 0):.0%}",
                        "Trades": info.get("total_trades", 0),
                        "État": info.get("status", "active"),
                    }
                )
            df_rank = pd.DataFrame(rows).sort_values("Score", ascending=False)
            st.dataframe(df_rank, use_container_width=True, hide_index=True)
        else:
            st.caption("Aucune stratégie rankée pour l'instant.")

        if events_section:
            with st.expander("Événements stratégies"):
                for ev in events_section[-10:]:
                    ev_html = (
                        f"<div style='font-size:0.75rem;color:#9ca3af;"
                        f"border-left:2px solid #374151;"
                        f"padding-left:6px;margin-bottom:4px'>{ev}</div>"
                    )
                    st.markdown(ev_html, unsafe_allow_html=True)

    with col_mem:
        st.markdown(
            '<div class="section-title">MISTAKE MEMORY</div>', unsafe_allow_html=True
        )
        if mistakes:
            import pandas as pd

            df_mm = pd.DataFrame(mistakes)
            show_mm = [
                c
                for c in [
                    "timestamp",
                    "symbol",
                    "signal",
                    "regime",
                    "pnl_pct",
                    "type",
                    "rule",
                ]
                if c in df_mm.columns
            ]
            if show_mm:
                st.dataframe(
                    df_mm[show_mm].tail(15), use_container_width=True, hide_index=True
                )
            else:
                st.dataframe(df_mm.tail(15), use_container_width=True, hide_index=True)
        else:
            st.caption("Aucune erreur mémorisée.")

    # Régrets
    st.markdown(
        '<div class="section-title">REGRET ENGINE — OPPORTUNITÉS MANQUÉES</div>',
        unsafe_allow_html=True,
    )
    with st.expander("Derniers regrets", expanded=False):
        if regrets:
            import pandas as pd

            df_reg = pd.DataFrame(regrets)
            show_reg = [
                c
                for c in [
                    "ts",
                    "symbol",
                    "signal",
                    "score",
                    "regime",
                    "refused_by",
                    "price_at_refusal",
                ]
                if c in df_reg.columns
            ]
            st.dataframe(
                df_reg[show_reg] if show_reg else df_reg,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Aucun regret enregistré.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — ANALYSE
# ═════════════════════════════════════════════════════════════════════════════
with tab_analyse:
    st.markdown(
        '<div class="section-title">SHADOW EXECUTION — SIMULATIONS</div>',
        unsafe_allow_html=True,
    )
    if shadow:
        import pandas as pd
        import plotly.express as px  # noqa: F811

        df_sh = pd.DataFrame(shadow)
        show_sh = [
            c
            for c in [
                "symbol",
                "action",
                "signal_score",
                "signal_price",
                "notional",
                "slippage_pct",
                "signal_to_order_ms",
                "regime",
            ]
            if c in df_sh.columns
        ]

        col_a, col_b = st.columns(2)
        with col_a:
            st.dataframe(
                df_sh[show_sh] if show_sh else df_sh,
                use_container_width=True,
                hide_index=True,
                height=300,
            )
        with col_b:
            if "slippage_pct" in df_sh.columns:
                fig_slip = px.histogram(
                    df_sh,
                    x="slippage_pct",
                    nbins=20,
                    title="Distribution slippage (%)",
                    color_discrete_sequence=["#3b82f6"],
                    height=300,
                )
                fig_slip.update_layout(
                    plot_bgcolor="#111827",
                    paper_bgcolor="#111827",
                    font_color="#9ca3af",
                    margin=dict(l=0, r=0, t=30, b=0),
                )
                st.plotly_chart(fig_slip, use_container_width=True)

    st.markdown(
        '<div class="section-title">PERFORMANCES PAR SYMBOLE</div>',
        unsafe_allow_html=True,
    )
    with st.expander("Détail trades SQLite", expanded=False):
        if trades:
            import pandas as pd

            df_tr = pd.DataFrame(trades)
            if "symbol" in df_tr.columns and "pnl_usd" in df_tr.columns:
                df_sym = (
                    df_tr.groupby("symbol")["pnl_usd"]
                    .agg(["sum", "count", "mean"])
                    .reset_index()
                )
                df_sym.columns = ["Symbole", "PnL total", "Trades", "PnL moyen"]
                st.dataframe(
                    df_sym.sort_values("PnL total", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.dataframe(df_tr, use_container_width=True, hide_index=True)
        else:
            st.caption("Aucun trade SQLite trouvé.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 5 — ALERTES
# ═════════════════════════════════════════════════════════════════════════════
with tab_alertes:
    # Violations BSM (si disponibles dans live_snapshot)
    bsm_state = snap.get("bsm_state", None)
    bsm_violations = snap.get("bsm_violations", [])

    st.markdown(
        '<div class="section-title">STABILITÉ COMPORTEMENTALE (BSM)</div>',
        unsafe_allow_html=True,
    )
    if bsm_state:
        state_color = {
            "stable": "#22c55e",
            "oscillating": "#f59e0b",
            "drifting": "#f97316",
            "frozen": "#ef4444",
            "degraded": "#dc2626",
        }.get(bsm_state, "#6b7280")
        bsm_html = (
            f"<div style='font-size:1.2rem;font-weight:800;"
            f"color:{state_color}'>{bsm_state.upper()}</div>"
        )
        st.markdown(bsm_html, unsafe_allow_html=True)
        if bsm_violations:
            for v in bsm_violations:
                st.warning(v)
        else:
            st.success("Aucune violation active.")
    else:
        st.caption("BSM non disponible dans le snapshot — données Telegram à utiliser.")

    st.markdown(
        '<div class="section-title">ERREURS LOG RÉCENTES</div>', unsafe_allow_html=True
    )
    log_lines = last_log_lines(100)
    error_lines = [
        ln for ln in log_lines if "ERROR" in ln or "WARNING" in ln or "CRITICAL" in ln
    ]
    if error_lines:
        for line in error_lines[-15:]:
            level = "🔴" if "ERROR" in line or "CRITICAL" in line else "🟡"
            st.markdown(
                f"<div style='font-size:0.72rem;font-family:monospace;color:#9ca3af;"
                f"border-left:2px solid #374151;padding-left:6px;margin-bottom:3px'>"
                f"{level} {line.strip()}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.success("Aucune erreur ou warning dans les logs récents.")

    st.markdown('<div class="section-title">SAFE MODE</div>', unsafe_allow_html=True)
    if safe_mode:
        st.error("⚠️ SAFE MODE ACTIF — Aucun trade n'est exécuté.")
    else:
        st.success("Safe mode inactif — trading normal.")

# ── Auto-refresh ──────────────────────────────────────────────────────────────
with st.sidebar:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()
    auto = st.checkbox("Auto-refresh (15s)", value=False)

if auto:
    time.sleep(15)
    st.cache_data.clear()
    st.rerun()
