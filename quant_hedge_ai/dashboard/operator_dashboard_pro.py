"""
operator_dashboard_pro.py — Dashboard Opérateur PRO pour Hedge Fund IA.
========================================================================
Application Streamlit complète avec 7 panneaux :

  Panel 1 — Portfolio Overview   : P&L, equity curve, balance USDT
  Panel 2 — Backtest Results     : tableau stratégies, filtres, graphiques
  Panel 3 — Active Trades        : trades en cours, statuts, mode paper/live
  Panel 4 — Risk Dashboard       : drawdown, métriques risque, alertes
  Panel 5 — Market Radar         : heatmap signaux, régime de marché
  Panel 6 — System Health        : agents, CPU/RAM, logs récents
  Panel 7 — Binance Config       : connexion API, solde, testnet/live

Lancement :
    streamlit run quant_hedge_ai/dashboard/operator_dashboard_pro.py --server.port 8510

Dépendances optionnelles (fallback gracieux si absentes) :
    streamlit, plotly, pandas, psutil
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Imports optionnels ────────────────────────────────────────────────────────

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False
    logger.error("streamlit non installé — pip install streamlit")

try:
    import plotly.express as px
    import plotly.graph_objects as go
    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False
    logger.warning("plotly non installé — graphiques désactivés")

try:
    import pandas as pd
    _HAS_PD = True
except ImportError:
    _HAS_PD = False
    logger.warning("pandas non installé — tableaux texte")

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

# ── Constantes ────────────────────────────────────────────────────────────────

REPORT_PATH    = Path("databases/backtest_report.json")
TITLE          = "🏦 AI Hedge Fund — Operator Dashboard PRO"
VERSION        = "v1.0"
REFRESH_SEC    = 5
SYMBOLS        = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "ADA/USDT", "DOGE/USDT"]
STRATEGIES     = ["RSI", "EMA", "MACD", "BOLLINGER", "VWAP", "ATR"]
_SEED          = 42

# ── Helpers / données simulées ────────────────────────────────────────────────

def _rng(seed: int = _SEED) -> random.Random:
    return random.Random(seed + int(time.time() / 60))  # change chaque minute


def _equity_curve(n: int = 252, vol: float = 0.012, drift: float = 0.0004) -> list[float]:
    rng    = random.Random(int(time.time() / 300))  # stable 5 min
    equity = [10_000.0]
    for _ in range(n - 1):
        r = rng.gauss(drift, vol)
        equity.append(equity[-1] * math.exp(r))
    return equity


def _fake_trades(n: int = 25) -> list[dict]:
    rng    = _rng()
    trades = []
    for i in range(n):
        sym    = rng.choice(SYMBOLS)
        side   = rng.choice(["BUY", "SELL"])
        entry  = rng.uniform(100, 50_000)
        pnl    = rng.gauss(15, 80)
        trades.append({
            "id":       f"T{1000+i}",
            "symbol":   sym,
            "side":     side,
            "entry":    round(entry, 2),
            "pnl_usdt": round(pnl, 2),
            "pnl_pct":  round(pnl / entry * 100, 3),
            "status":   rng.choice(["OPEN", "OPEN", "CLOSED"]),
            "strategy": rng.choice(STRATEGIES),
            "time":     (datetime.now() - timedelta(minutes=rng.randint(1, 240))).strftime("%H:%M"),
        })
    return trades


def _risk_metrics() -> dict:
    rng = _rng()
    return {
        "drawdown":        round(rng.uniform(0.5, 8.0), 2),
        "sharpe":          round(rng.uniform(0.8, 2.5), 3),
        "sortino":         round(rng.uniform(1.0, 3.2), 3),
        "var_95":          round(rng.uniform(200, 900), 1),
        "max_position":    round(rng.uniform(5, 25), 1),
        "open_positions":  rng.randint(1, 8),
        "win_rate":        round(rng.uniform(45, 68), 1),
        "profit_factor":   round(rng.uniform(1.1, 2.4), 2),
    }


def _signal_matrix() -> dict[str, dict[str, float]]:
    """Matrice signaux : symbole × stratégie → score [-1, 1]."""
    rng = _rng()
    return {
        sym: {strat: round(rng.gauss(0, 0.5), 3) for strat in STRATEGIES}
        for sym in SYMBOLS
    }


def _agent_status() -> list[dict]:
    rng = _rng()
    agents = [
        "HistoricalFetcher", "BacktestLab", "RiskMonitor", "ExecutionEngine",
        "MarketScanner", "SessionGuard", "OrderDeduplicator", "TradeLogger",
    ]
    return [
        {
            "agent":   a,
            "status":  rng.choice(["🟢 OK", "🟢 OK", "🟢 OK", "🟡 WARN", "🔴 ERR"]),
            "last_ok": f"{rng.randint(1, 120)}s ago",
            "calls":   rng.randint(10, 5000),
        }
        for a in agents
    ]


def _load_backtest_report() -> dict | None:
    try:
        if REPORT_PATH.exists():
            with open(REPORT_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning("Impossible de charger le rapport backtest : %s", exc)
    return None


def _system_resources() -> dict:
    if _HAS_PSUTIL:
        return {
            "cpu_pct":    psutil.cpu_percent(interval=0.1),
            "ram_pct":    psutil.virtual_memory().percent,
            "ram_used_gb": psutil.virtual_memory().used / 1e9,
        }
    return {"cpu_pct": 0, "ram_pct": 0, "ram_used_gb": 0}


def _binance_status() -> dict:
    """Tente une connexion BinanceConnector et retourne le statut."""
    try:
        from quant_hedge_ai.binance_connector import BinanceConnector
        bc     = BinanceConnector()
        status = bc.test_connection()
        status["portfolio_value"] = bc.get_portfolio_value()
        status["balances"]        = bc.get_balance()
        return status
    except Exception as exc:
        return {"status": "error", "error": str(exc), "mode": "unknown"}


# ── Styles CSS personnalisés ──────────────────────────────────────────────────

_CSS = """
<style>
  /* Fond sombre */
  .stApp { background-color: #0d1117; color: #e6edf3; }
  /* Sidebar */
  section[data-testid="stSidebar"] { background-color: #161b22; }
  /* Métriques */
  [data-testid="stMetric"] {
    background-color: #21262d;
    border-radius: 8px;
    padding: 12px 16px;
    border: 1px solid #30363d;
  }
  [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
  /* Cards génériques */
  .hedge-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.8rem;
  }
  .badge-ok   { color: #3fb950; font-weight: bold; }
  .badge-warn { color: #d29922; font-weight: bold; }
  .badge-err  { color: #f85149; font-weight: bold; }
  /* Headers de panel */
  h2 { color: #58a6ff !important; }
  h3 { color: #79c0ff !important; }
</style>
"""

# ── Composants réutilisables ──────────────────────────────────────────────────

def _metric_row(cols: list, data: list[tuple[str, str, str]]) -> None:
    """Affiche des métriques dans une ligne de colonnes."""
    for col, (label, value, delta) in zip(cols, data):
        with col:
            st.metric(label, value, delta)


def _plotly_line(y: list[float], title: str, color: str = "#58a6ff", height: int = 250) -> None:
    if not _HAS_PLOTLY:
        st.write(f"{title}: {y[-1]:.2f}")
        return
    fig = go.Figure(
        go.Scatter(
            y=y,
            mode="lines",
            fill="tozeroy",
            line=dict(color=color, width=2),
            fillcolor=color.replace("ff", "22") if len(color) == 7 else color + "22",
        )
    )
    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=10, r=10, t=35, b=10),
        plot_bgcolor="#0d1117",
        paper_bgcolor="#161b22",
        font_color="#e6edf3",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#30363d"),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Panneaux ──────────────────────────────────────────────────────────────────

def _panel_portfolio() -> None:
    st.header("📊 Panel 1 — Portfolio Overview")

    equity = _equity_curve(252)
    current = equity[-1]
    peak    = max(equity)
    dd      = (peak - current) / peak * 100
    pnl_pct = (current / equity[0] - 1) * 100
    pnl_usd = current - equity[0]

    cols = st.columns(4)
    _metric_row(
        cols,
        [
            ("💰 Equity",    f"${current:,.2f}",   f"{pnl_pct:+.2f}%"),
            ("📈 P&L USDT",  f"${pnl_usd:+,.2f}",  f"{pnl_pct:+.1f}%"),
            ("📉 Drawdown",  f"{dd:.2f}%",          "max drawdown"),
            ("🎯 Capital",   f"${equity[0]:,.0f}",  "initial"),
        ],
    )

    st.divider()
    _plotly_line(equity, "Equity Curve (252 jours simulés)", color="#3fb950", height=320)

    # Distribution des rendements journaliers
    if _HAS_PLOTLY and _HAS_PD:
        daily_rets = [(equity[i] / equity[i - 1] - 1) * 100 for i in range(1, len(equity))]
        fig = px.histogram(
            x=daily_rets,
            nbins=30,
            title="Distribution des rendements journaliers (%)",
            color_discrete_sequence=["#58a6ff"],
        )
        fig.update_layout(
            height=230,
            margin=dict(l=10, r=10, t=35, b=10),
            plot_bgcolor="#0d1117",
            paper_bgcolor="#161b22",
            font_color="#e6edf3",
        )
        st.plotly_chart(fig, use_container_width=True)


def _panel_backtest() -> None:
    st.header("🔬 Panel 2 — Backtest Results")

    report = _load_backtest_report()
    if report is None:
        st.info(
            "Aucun rapport backtest trouvé. Lancez d'abord :\n\n"
            "```bash\npython -m quant_hedge_ai.backtest_real\n```"
        )
        return

    meta    = report.get("metadata", {})
    results = report.get("results", [])

    # Métadonnées
    cols = st.columns(4)
    cols[0].metric("Symboles testés",    len(meta.get("symbols", [])))
    cols[1].metric("Runs totaux",        meta.get("total_runs", 0))
    cols[2].metric("Trades totaux",      report.get("total_trades", 0))
    cols[3].metric("Source données",     str(meta.get("data_sources", {}).get("BTC/USDT", "?")))

    st.divider()

    # Filtres
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        sym_filter = st.multiselect("Symboles", SYMBOLS, default=SYMBOLS[:2])
    with col_f2:
        strat_filter = st.multiselect(
            "Stratégies", STRATEGIES, default=STRATEGIES
        )
    with col_f3:
        min_trades = st.slider("Trades min", 0, 100, 5)

    # Filtrage
    filtered = [
        r for r in results
        if (not sym_filter or r.get("symbol", "") in sym_filter)
        and (not strat_filter or r.get("strategy", {}).get("entry_indicator", "") in strat_filter)
        and r.get("trades", 0) >= min_trades
    ]

    if _HAS_PD and filtered:
        rows = []
        for r in filtered:
            rows.append({
                "Symbole":   r.get("symbol", "?"),
                "Stratégie": r.get("strategy", {}).get("name", "?"),
                "Sharpe":    r.get("sharpe", 0),
                "PnL %":     r.get("pnl", 0),
                "Drawdown":  r.get("drawdown", 0),
                "Win Rate":  r.get("win_rate", 0),
                "Trades":    r.get("trades", 0),
            })
        df = pd.DataFrame(rows).sort_values("Sharpe", ascending=False)
        st.dataframe(df, use_container_width=True, height=280)

        # Top 10 Sharpe
        top10 = df.head(10)
        if _HAS_PLOTLY:
            fig = px.bar(
                top10,
                x="Stratégie",
                y="Sharpe",
                color="Symbole",
                title="Top 10 stratégies par Sharpe ratio",
                color_discrete_sequence=px.colors.qualitative.Plotly,
            )
            fig.update_layout(
                height=300,
                margin=dict(l=10, r=10, t=35, b=10),
                plot_bgcolor="#0d1117",
                paper_bgcolor="#161b22",
                font_color="#e6edf3",
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.write(f"{len(filtered)} résultats après filtrage.")
        for r in filtered[:20]:
            st.text(
                f"{r.get('symbol','?')} | {r.get('strategy',{}).get('name','?')} "
                f"| Sharpe={r.get('sharpe',0):.3f} | PnL={r.get('pnl',0):.2f}%"
            )


def _panel_trades() -> None:
    st.header("⚡ Panel 3 — Active Trades")

    trades = _fake_trades(30)
    open_t = [t for t in trades if t["status"] == "OPEN"]
    closed = [t for t in trades if t["status"] == "CLOSED"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Positions ouvertes", len(open_t))
    c2.metric("Trades fermés",      len(closed))
    c3.metric("P&L total (simulé)", f"${sum(t['pnl_usdt'] for t in trades):+.2f}")
    c4.metric("Mode",               "📄 PAPER")

    st.divider()
    st.subheader("🟢 Positions ouvertes")
    if _HAS_PD and open_t:
        df_open = pd.DataFrame(open_t)[["id", "symbol", "side", "entry", "pnl_usdt", "pnl_pct", "strategy", "time"]]
        df_open.columns = ["ID", "Symbole", "Côté", "Entrée $", "P&L $", "P&L %", "Stratégie", "Heure"]

        def _color_pnl(val: float):
            return "color: #3fb950" if val >= 0 else "color: #f85149"

        if hasattr(df_open.style, "map"):
            styled = df_open.style.map(_color_pnl, subset=["P&L $", "P&L %"])
        else:
            styled = df_open.style.applymap(_color_pnl, subset=["P&L $", "P&L %"])
        st.dataframe(styled, use_container_width=True)
    elif open_t:
        for t in open_t:
            st.text(f"[{t['id']}] {t['symbol']} {t['side']} @ {t['entry']:.2f} | PnL: {t['pnl_usdt']:+.2f}")

    st.subheader("📋 Derniers trades fermés")
    if _HAS_PD and closed:
        df_cl = pd.DataFrame(closed)[["id", "symbol", "side", "pnl_usdt", "pnl_pct", "strategy"]]
        df_cl.columns = ["ID", "Symbole", "Côté", "P&L $", "P&L %", "Stratégie"]
        st.dataframe(df_cl, use_container_width=True, height=200)


def _panel_risk() -> None:
    st.header("🛡️ Panel 4 — Risk Dashboard")

    metrics = _risk_metrics()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📉 Drawdown",     f"{metrics['drawdown']:.2f}%",  "limite: 10%")
    c2.metric("⚡ Sharpe",       f"{metrics['sharpe']:.3f}",     "> 1.0 objectif")
    c3.metric("🎯 Win Rate",     f"{metrics['win_rate']:.1f}%",  "")
    c4.metric("📊 Profit Factor",f"{metrics['profit_factor']:.2f}", "> 1.5 objectif")

    st.divider()
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("🔒 VaR 95%",         f"${metrics['var_95']:.0f}", "montant à risque")
    c6.metric("📐 Sortino",          f"{metrics['sortino']:.3f}", "")
    c7.metric("🏦 Positions ouv.", metrics['open_positions'],   "")
    c8.metric("📏 Pos. max",         f"{metrics['max_position']:.1f}%", "du capital")

    # Gauge drawdown
    if _HAS_PLOTLY:
        fig = go.Figure(
            go.Indicator(
                mode    = "gauge+number+delta",
                value   = metrics["drawdown"],
                title   = {"text": "Drawdown actuel (%)", "font": {"color": "#e6edf3"}},
                delta   = {"reference": 5.0},
                gauge   = {
                    "axis":  {"range": [0, 20], "tickcolor": "#e6edf3"},
                    "bar":   {"color": "#f85149"},
                    "steps": [
                        {"range": [0, 5],  "color": "#238636"},
                        {"range": [5, 10], "color": "#d29922"},
                        {"range": [10, 20],"color": "#b62324"},
                    ],
                    "threshold": {
                        "line":  {"color": "white", "width": 4},
                        "thickness": 0.75,
                        "value": 10,
                    },
                },
            )
        )
        fig.update_layout(
            height=280,
            margin=dict(l=20, r=20, t=50, b=20),
            paper_bgcolor="#161b22",
            font_color="#e6edf3",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Alertes
    st.subheader("🚨 Alertes actives")
    alerts = []
    if metrics["drawdown"] > 7:
        alerts.append(f"⚠️  Drawdown élevé : {metrics['drawdown']:.2f}% (seuil 7%)")
    if metrics["open_positions"] > 6:
        alerts.append(f"⚠️  Nombreuses positions ouvertes : {metrics['open_positions']}")
    if metrics["sharpe"] < 1.0:
        alerts.append(f"⚠️  Sharpe faible : {metrics['sharpe']:.3f} (objectif > 1.0)")
    if not alerts:
        alerts.append("✅  Tous les indicateurs de risque dans les limites.")
    for a in alerts:
        st.warning(a) if "⚠️" in a else st.success(a)


def _panel_market_radar() -> None:
    st.header("📡 Panel 5 — Market Radar")

    matrix = _signal_matrix()

    if _HAS_PLOTLY and _HAS_PD:
        df = pd.DataFrame(matrix).T  # symboles × stratégies
        fig = px.imshow(
            df,
            color_continuous_scale=[[0, "#f85149"], [0.5, "#161b22"], [1, "#3fb950"]],
            zmin=-1, zmax=1,
            title="Heatmap des signaux (rouge=baisse, vert=hausse)",
            text_auto=".2f",
        )
        fig.update_layout(
            height=350,
            margin=dict(l=10, r=10, t=45, b=10),
            paper_bgcolor="#161b22",
            font_color="#e6edf3",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        for sym, signals in matrix.items():
            st.text(f"{sym}: {signals}")

    st.divider()
    st.subheader("🌐 Régime de marché estimé")
    rng    = _rng()
    regime = rng.choice(["📈 Bull Trend", "📉 Bear Trend", "↔️ Range / Consolidation", "🌩️ Haute Volatilité"])
    conf   = round(rng.uniform(55, 92), 1)
    cols   = st.columns(3)
    cols[0].metric("Régime", regime)
    cols[1].metric("Confiance", f"{conf:.1f}%")
    cols[2].metric("Mis à jour", datetime.now().strftime("%H:%M:%S"))

    # Prix en temps réel (simulés)
    st.subheader("💹 Prix simulés")
    price_cols = st.columns(len(SYMBOLS))
    fake_prices = {
        "BTC/USDT": 42_150, "ETH/USDT": 2_280, "BNB/USDT": 318,
        "SOL/USDT": 88, "ADA/USDT": 0.45, "DOGE/USDT": 0.082,
    }
    for col, sym in zip(price_cols, SYMBOLS):
        p    = fake_prices.get(sym, 1.0)
        chg  = rng.gauss(0, 1.5)
        col.metric(sym, f"${p:,.4g}", f"{chg:+.2f}%")


def _panel_system_health() -> None:
    st.header("💻 Panel 6 — System Health")

    res     = _system_resources()
    agents  = _agent_status()
    ok_cnt  = sum(1 for a in agents if "🟢" in a["status"])
    warn_cnt= sum(1 for a in agents if "🟡" in a["status"])
    err_cnt = sum(1 for a in agents if "🔴" in a["status"])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🟢 Agents OK",   ok_cnt)
    c2.metric("🟡 Warnings",    warn_cnt)
    c3.metric("🔴 Erreurs",     err_cnt)
    c4.metric("🖥️ CPU",         f"{res['cpu_pct']:.1f}%" if _HAS_PSUTIL else "N/A")
    c5.metric("🧠 RAM",         f"{res['ram_pct']:.1f}%" if _HAS_PSUTIL else "N/A")

    # Barres CPU/RAM
    if _HAS_PSUTIL:
        st.progress(int(res["cpu_pct"]), text=f"CPU {res['cpu_pct']:.1f}%")
        st.progress(int(res["ram_pct"]), text=f"RAM {res['ram_pct']:.1f}% ({res['ram_used_gb']:.1f} Go)")

    st.divider()
    st.subheader("🤖 Statut des agents")
    if _HAS_PD:
        df_agents = pd.DataFrame(agents)
        df_agents.columns = ["Agent", "Statut", "Dernier OK", "Appels"]
        st.dataframe(df_agents, use_container_width=True)
    else:
        for a in agents:
            st.text(f"[{a['status']}] {a['agent']} — {a['last_ok']} — {a['calls']} appels")

    # Logs factices
    st.subheader("📜 Logs récents")
    log_entries = [
        f"{(datetime.now() - timedelta(seconds=i*15)).strftime('%H:%M:%S')}  "
        f"INFO  {'ExecutionEngine' if i % 3 == 0 else ('RiskMonitor' if i % 3 == 1 else 'BacktestLab')}"
        f" — {'Paper trade BTC/USDT BUY $100' if i % 3 == 0 else ('Drawdown check OK' if i % 3 == 1 else 'Backtest run completed')}"
        for i in range(10)
    ]
    st.code("\n".join(log_entries), language="text")


def _panel_binance_config() -> None:
    st.header("🔗 Panel 7 — Binance Configuration")

    st.info(
        "Les clés API sont lues depuis les **variables d'environnement** ou le fichier **`.env`**.\n"
        "Utilisez `python -m quant_hedge_ai.setup_binance` pour les configurer de manière sécurisée."
    )

    current_mode = os.getenv("BINANCE_MODE", "paper")
    has_key      = bool(os.getenv("BINANCE_API_KEY") or os.getenv("BINANCE_LIVE_API_KEY"))

    c1, c2, c3 = st.columns(3)
    c1.metric("Mode actif",     current_mode.upper())
    c2.metric("Clés détectées", "✅ Oui" if has_key else "❌ Non (paper)")
    c3.metric("Testnet",        "✅ Oui" if os.getenv("BINANCE_TESTNET", "").lower() == "true" else "❌ Non")

    st.divider()

    if st.button("🔌 Tester la connexion", key="test_conn"):
        with st.spinner("Test en cours…"):
            status = _binance_status()

        if status.get("status") == "ok":
            st.success(
                f"✅ Connexion réussie ! Mode: **{status['mode']}** | "
                f"Balance: **{status['balance_usdt']:.2f} USDT** | "
                f"Latence: **{status['latency_ms']} ms**"
            )
            if status.get("balances"):
                st.subheader("💼 Balances")
                if _HAS_PD:
                    df_bal = pd.DataFrame(
                        [{"Actif": k, "Montant": v} for k, v in status["balances"].items()]
                    )
                    st.dataframe(df_bal, use_container_width=True)
                else:
                    for k, v in status["balances"].items():
                        st.text(f"  {k}: {v:.6f}")
        else:
            st.error(f"❌ Connexion échouée : {status.get('error', 'inconnue')}")

    st.divider()
    st.subheader("⚙️ Variables d'environnement requises")
    env_table = {
        "paper":         ["PAPER_INITIAL_CAPITAL (optionnel)"],
        "spot_testnet":  ["BINANCE_API_KEY", "BINANCE_API_SECRET", "BINANCE_TESTNET=true"],
        "futures_demo":  ["BINANCE_FUTURES_DEMO_KEY", "BINANCE_FUTURES_DEMO_SECRET"],
        "live":          ["BINANCE_LIVE_API_KEY", "BINANCE_LIVE_API_SECRET"],
    }
    for mode, vars_ in env_table.items():
        with st.expander(f"Mode : `{mode}`"):
            for v in vars_:
                present = any(os.getenv(v.split("=")[0]) for _ in [1])
                icon    = "✅" if present else "⭕"
                st.markdown(f"- {icon} `{v}`")

    # Formulaire de test d'un prix
    st.divider()
    st.subheader("💱 Tester un prix en temps réel")
    sym_test = st.selectbox("Symbole", SYMBOLS, key="sym_test")
    if st.button("📥 Récupérer le prix", key="get_price"):
        try:
            from quant_hedge_ai.binance_connector import BinanceConnector
            bc = BinanceConnector()
            p  = bc.get_price(sym_test)
            st.success(f"Prix actuel **{sym_test}** : `${p:,.4f}`  (mode {bc.mode})")
        except Exception as exc:
            st.error(f"Erreur : {exc}")


# ── Application principale ────────────────────────────────────────────────────

_PANELS = {
    "📊 Portfolio Overview":  _panel_portfolio,
    "🔬 Backtest Results":    _panel_backtest,
    "⚡ Active Trades":       _panel_trades,
    "🛡️ Risk Dashboard":     _panel_risk,
    "📡 Market Radar":        _panel_market_radar,
    "💻 System Health":       _panel_system_health,
    "🔗 Binance Config":      _panel_binance_config,
}


def _header(mode: str) -> None:
    mode_badge = {
        "paper":        ("📄", "#58a6ff"),
        "spot_testnet": ("🧪", "#d29922"),
        "futures_demo": ("🎮", "#a371f7"),
        "live":         ("🔴", "#f85149"),
    }.get(mode, ("❓", "#8b949e"))

    icon, color = mode_badge
    col_logo, col_title, col_mode, col_clock = st.columns([1, 4, 2, 2])
    with col_logo:
        st.markdown("### 🏦")
    with col_title:
        st.markdown(f"## {TITLE}  `{VERSION}`")
    with col_mode:
        st.markdown(
            f"<span style='color:{color};font-weight:bold;font-size:1.1rem'>"
            f"{icon} MODE : {mode.upper()}"
            f"</span>",
            unsafe_allow_html=True,
        )
    with col_clock:
        st.markdown(
            f"<span style='color:#8b949e;font-size:0.9rem'>"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
            f"</span>",
            unsafe_allow_html=True,
        )


def main() -> None:
    if not _HAS_ST:
        print("streamlit non installé. Installez avec : pip install streamlit")
        sys.exit(1)

    st.set_page_config(
        page_title="Hedge Fund Operator PRO",
        page_icon="🏦",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CSS, unsafe_allow_html=True)

    mode = os.getenv("BINANCE_MODE", "paper")

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🏦 Hedge Fund AI")
        st.markdown(f"**Mode** : `{mode}`")
        st.markdown("---")
        panel_name = st.radio("Navigation", list(_PANELS.keys()), label_visibility="collapsed")
        st.markdown("---")

        # Paramètres globaux
        with st.expander("⚙️ Paramètres"):
            st.number_input("Capital initial (USDT)", value=10_000, step=1_000, key="capital")
            st.slider("Max drawdown (%)", 1, 30, 10, key="max_dd")
            st.toggle("Auto-refresh (5s)", value=False, key="auto_refresh")

        st.markdown("---")
        st.caption(f"Version {VERSION} | {datetime.now().strftime('%Y-%m-%d')}")

    # ── Header ────────────────────────────────────────────────────────────────
    _header(mode)
    st.divider()

    # ── Panel actif ───────────────────────────────────────────────────────────
    _PANELS[panel_name]()

    # ── Auto-refresh ─────────────────────────────────────────────────────────
    if st.session_state.get("auto_refresh"):
        time.sleep(REFRESH_SEC)
        st.rerun()


# ── Point d'entrée ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    main()
