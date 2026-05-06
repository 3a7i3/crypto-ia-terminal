"""
dashboard_live.py — Dashboard live V9.1 (Streamlit)

Lance avec :  streamlit run dashboard_live.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import logging
import time

import streamlit as st

st.set_page_config(
    page_title="Quant AI V9.1 — Live Dashboard",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="expanded",
)

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from quant_hedge_ai.agents.market.market_scanner import MarketScanner

logging.basicConfig(level=logging.WARNING)

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
.stApp { background: #0e1117; color: #e0e0e0; }
.metric-card {
    background: #1e2130; border-radius: 10px;
    padding: 1rem 1.4rem; margin-bottom: 0.5rem;
    border-left: 4px solid #00e0ff;
}
.risk-nominal  { border-left-color: #00e676; }
.risk-warning  { border-left-color: #ffb300; }
.risk-critical { border-left-color: #ff5252; }
.risk-hardstop { border-left-color: #ff0000; background: #2a0000; }
h1, h2, h3 { color: #00e0ff; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Paramètres")
    symbols_choice = st.multiselect(
        "Symboles",
        ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
        default=["BTC/USDT", "ETH/USDT"],
    )
    timeframe = st.selectbox("Timeframe", ["1h", "4h", "1d"], index=0)
    n_candles = st.slider("Nombre de bougies", 50, 200, 120)
    top_n = st.slider("Top N stratégies", 5, 30, 10)
    sharpe_min = st.slider("Sharpe minimum", 0.0, 5.0, 1.0, 0.1)
    auto_refresh = st.checkbox("Auto-refresh (60 s)", value=False)
    refresh_now = st.button("🔄 Rafraîchir maintenant")
    st.markdown("---")
    st.markdown(f"**Mise à jour :** {pd.Timestamp.now().strftime('%H:%M:%S')}")

if not symbols_choice:
    st.warning("Sélectionnez au moins un symbole dans la barre latérale.")
    st.stop()


# ── Chargement des données (cache 60 s) ───────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def load_market_data(symbols: tuple, tf: str, n: int) -> dict:
    scanner = MarketScanner(symbols=list(symbols), timeframe=tf, limit=n)
    return scanner.scan()


@st.cache_data(ttl=60, show_spinner=False)
def run_backtest_batch(candles_json: str, top: int) -> list[dict]:
    import json

    from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab

    candles = json.loads(candles_json)
    lab = BacktestLab()
    indicators = ["RSI", "EMA", "MACD", "BOLLINGER", "VWAP"]
    periods = [7, 14, 21, 50]
    results = []
    for ind in indicators:
        for per in periods:
            strat = {
                "entry_indicator": ind,
                "period": per,
                "entry_threshold": 30,
                "exit_threshold": 70,
            }
            r = lab.run_backtest(strategy=strat, data=candles)
            results.append(r)
    results.sort(key=lambda x: x.get("sharpe", 0.0), reverse=True)
    return results[:top]


with st.spinner("Chargement des données Binance…"):
    market = load_market_data(tuple(symbols_choice), timeframe, n_candles)

primary_symbol = symbols_choice[0]
candles = market.get("history", {}).get(primary_symbol) or market.get(
    "candles", {}
).get(primary_symbol, [])

if not candles:
    st.error("Impossible de charger les données. Vérifiez la connexion Binance.")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_bot, tab_market, tab_backtest, tab_paper, tab_risk, tab_notif = st.tabs(
    [
        "🤖 Bot Live",
        "📊 Marché Live",
        "🏆 Backtesting",
        "📋 Paper Trading",
        "🛡️ Risk Monitor",
        "🔔 Notifications",
    ]
)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 0 — BOT LIVE (lit databases/live_snapshot.json)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_bot:
    import datetime as _dt
    import json as _snap_json
    from pathlib import Path as _Path

    _SNAP_PATH = _Path("databases/live_snapshot.json")

    @st.cache_data(ttl=2, show_spinner=False)
    def _load_snap() -> dict | None:
        try:
            return _snap_json.loads(_SNAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None

    snap = _load_snap()

    if snap is None:
        st.warning(
            "Aucun snapshot disponible. Lance d'abord `advisor_loop.py` pour générer `databases/live_snapshot.json`."
        )
    else:
        ts = snap.get("ts", 0)
        age_s = time.time() - ts
        age_label = f"{age_s:.0f}s" if age_s < 120 else f"{age_s/60:.1f}min"
        ts_str = _dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")

        # ── En-tête ──────────────────────────────────────────────────────────
        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        col_h1.metric("Cycle", f"#{snap.get('cycle', '?')}")
        col_h2.metric("Capital", f"${snap.get('capital', 0):,.0f} USDT")
        safe = snap.get("safe_mode", False)
        col_h3.metric("Mode", "SAFE" if safe else "TRADING", delta=None)
        ex = snap.get("exchange", {})
        ex_ok = ex.get("healthy", True)
        col_h4.metric(
            "Exchange",
            "OK" if ex_ok else "HORS LIGNE",
            f"{ex.get('last_latency_ms', 0):.0f}ms",
            delta_color="normal" if ex_ok else "inverse",
        )
        st.caption(
            f"Snapshot à {ts_str} — il y a {age_label} | uptime exchange {ex.get('uptime_pct', 100):.1f}%"
        )

        st.divider()

        # ── Tableau par symbole ───────────────────────────────────────────────
        st.markdown("### Signaux par symbole")
        syms = snap.get("symbols", [])
        if syms:
            rows = []
            for s in syms:
                sig = s.get("signal", "?")
                allowed = s.get("trade_allowed") or s.get("gate_allowed", False)
                rows.append(
                    {
                        "Symbole": s.get("symbol", "?"),
                        "Prix": f"${s.get('prix', 0):,.2f}",
                        "Signal": sig,
                        "Score": f"{s.get('score', 0):.0f}",
                        "Régime": s.get("regime", "?"),
                        "Confirmé": "✓" if s.get("confirmed") else "✗",
                        "Gate": "OK" if allowed else "BLOQUÉ",
                        "Conviction": (
                            f"{s.get('conviction_score', 0) or 0:.0f}"
                            if s.get("conviction_score") is not None
                            else "—"
                        ),
                        "Personnalité": s.get("personality") or "—",
                        "Exécution": (
                            str(s.get("futures_result", {}) or {}).get("mode", "—")
                            if isinstance(s.get("futures_result"), dict)
                            else "—"
                        ),
                    }
                )
            df_syms = pd.DataFrame(rows)

            def _color_signal(v):
                if v == "BUY":
                    return "color: #00e676"
                if v == "SELL":
                    return "color: #ff5252"
                return "color: #ffb300"

            def _color_gate(v):
                return "color: #00e676" if v == "OK" else "color: #ff5252"

            styled = df_syms.style.map(_color_signal, subset=["Signal"]).map(
                _color_gate, subset=["Gate"]
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun symbole dans le snapshot.")

        # ── Positions ouvertes ────────────────────────────────────────────────
        positions = snap.get("positions", [])
        if positions:
            st.divider()
            st.markdown("### Positions ouvertes")
            df_pos = pd.DataFrame(positions)
            st.dataframe(df_pos, use_container_width=True, hide_index=True)

    # Auto-refresh
    if auto_refresh:
        time.sleep(2)
        st.cache_data.clear()
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MARCHÉ LIVE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_market:
    st.markdown(f"## 📊 {primary_symbol} — {timeframe} ({len(candles)} bougies)")

    # Métriques rapides
    closes = [c["close"] for c in candles]
    last_price = closes[-1]
    prev_price = closes[-2] if len(closes) >= 2 else last_price
    pct_change = (last_price - prev_price) / prev_price * 100

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Dernier prix", f"${last_price:,.2f}", f"{pct_change:+.2f}%")
    col2.metric("High (période)", f"${max(c['high'] for c in candles):,.2f}")
    col3.metric("Low (période)", f"${min(c['low']  for c in candles):,.2f}")
    vol_usd = sum(c.get("volume", 0) * c["close"] for c in candles[-24:])
    col4.metric(
        "Volume 24h (USD)",
        f"${vol_usd/1e6:.1f}M" if vol_usd > 1e6 else f"${vol_usd:,.0f}",
    )

    # Chandelier
    timestamps = [
        pd.to_datetime(c.get("timestamp", i * 3600000), unit="ms")
        for i, c in enumerate(candles)
    ]
    fig_candle = go.Figure(
        data=[
            go.Candlestick(
                x=timestamps,
                open=[c["open"] for c in candles],
                high=[c["high"] for c in candles],
                low=[c["low"] for c in candles],
                close=[c["close"] for c in candles],
                name=primary_symbol,
            )
        ]
    )
    fig_candle.update_layout(
        title=f"{primary_symbol} — {timeframe}",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=450,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig_candle, use_container_width=True)

    # Volume
    colors = ["#00e676" if c["close"] >= c["open"] else "#ff5252" for c in candles]
    fig_vol = go.Figure(
        data=[
            go.Bar(
                x=timestamps,
                y=[c.get("volume", 0) for c in candles],
                marker_color=colors,
                name="Volume",
            )
        ]
    )
    fig_vol.update_layout(
        template="plotly_dark",
        height=150,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig_vol, use_container_width=True)

    # Multi-symboles
    if len(symbols_choice) > 1:
        st.markdown("### Comparaison multi-symboles")
        cols = st.columns(len(symbols_choice))
        for i, sym in enumerate(symbols_choice):
            sym_candles = market.get("history", {}).get(sym) or market.get(
                "candles", {}
            ).get(sym, [])
            if sym_candles:
                p0 = sym_candles[0]["close"]
                perf = [(c["close"] - p0) / p0 * 100 for c in sym_candles]
                with cols[i]:
                    last_perf = perf[-1]
                    delta_color = "normal" if last_perf >= 0 else "inverse"
                    st.metric(
                        sym,
                        f"{sym_candles[-1]['close']:,.4g}",
                        f"{last_perf:+.2f}%",
                        delta_color=delta_color,
                    )

        # Courbe normalisée
        fig_norm = go.Figure()
        for sym in symbols_choice:
            sym_candles = market.get("history", {}).get(sym) or market.get(
                "candles", {}
            ).get(sym, [])
            if sym_candles:
                p0 = sym_candles[0]["close"]
                perf = [(c["close"] - p0) / p0 * 100 for c in sym_candles]
                ts = [
                    pd.to_datetime(c.get("timestamp", i * 3600000), unit="ms")
                    for i, c in enumerate(sym_candles)
                ]
                fig_norm.add_trace(go.Scatter(x=ts, y=perf, mode="lines", name=sym))
        fig_norm.update_layout(
            title="Performance normalisée (%)",
            template="plotly_dark",
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            yaxis_title="%",
        )
        st.plotly_chart(fig_norm, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — BACKTESTING
# ═══════════════════════════════════════════════════════════════════════════════
with tab_backtest:
    st.markdown("## 🏆 Backtesting live — Top stratégies")

    import json

    candles_json = json.dumps(candles)
    with st.spinner("Backtesting en cours…"):
        bt_results = run_backtest_batch(candles_json, top_n)

    filtered = [r for r in bt_results if r.get("sharpe", 0) >= sharpe_min]
    if not filtered:
        st.info(f"Aucune stratégie avec Sharpe ≥ {sharpe_min}. Baissez le seuil.")
        filtered = bt_results[:5]

    # Tableau des résultats
    rows = []
    for r in filtered:
        s = r.get("strategy", {})
        rows.append(
            {
                "Indicateur": s.get("entry_indicator", "?"),
                "Période": s.get("period", "?"),
                "Sharpe": round(r.get("sharpe", 0), 3),
                "PnL %": round(r.get("pnl", 0), 2),
                "Drawdown": round(r.get("drawdown", 0), 4),
                "Win Rate": f"{r.get('win_rate', 0):.1%}",
                "Trades": r.get("trades", 0),
            }
        )
    df_bt = pd.DataFrame(rows)
    st.dataframe(
        df_bt.style.background_gradient(
            subset=["Sharpe"], cmap="Greens"
        ).background_gradient(subset=["PnL %"], cmap="RdYlGn"),
        use_container_width=True,
        hide_index=True,
    )

    # Bar chart Sharpe
    fig_sharpe = px.bar(
        df_bt,
        x="Indicateur",
        y="Sharpe",
        color="Sharpe",
        color_continuous_scale="Viridis",
        text="Période",
        title="Sharpe par indicateur",
        template="plotly_dark",
    )
    fig_sharpe.update_layout(height=300, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig_sharpe, use_container_width=True)

    # Scatter Sharpe vs Drawdown
    fig_scatter = px.scatter(
        df_bt,
        x="Drawdown",
        y="Sharpe",
        color="Indicateur",
        size="Trades",
        hover_data=["Période", "PnL %", "Win Rate"],
        title="Sharpe vs Drawdown",
        template="plotly_dark",
    )
    fig_scatter.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig_scatter, use_container_width=True)

    # Meilleure stratégie
    if bt_results:
        best = bt_results[0]
        best_s = best.get("strategy", {})
        best_sharpe = best.get("sharpe", 0)
        color = "success" if best_sharpe >= 2.0 else "info"
        st.markdown(
            f"""
**🥇 Meilleure stratégie du cycle**
- Indicateur : `{best_s.get('entry_indicator','?')}` | Période : `{best_s.get('period','?')}`
- Sharpe : **{best_sharpe:.3f}** | PnL : **{best.get('pnl',0):.2f}%**
- Drawdown : `{best.get('drawdown',0):.4f}` | Win rate : `{best.get('win_rate',0):.1%}` | Trades : `{best.get('trades',0)}`
"""
        )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PAPER TRADING
# ═══════════════════════════════════════════════════════════════════════════════
with tab_paper:
    st.markdown("## 📋 Paper Trading — Compte virtuel")

    from quant_hedge_ai.agents.execution.paper_trading_engine import (
        _STATE_FILE,
        PaperTradingEngine,
    )
    from quant_hedge_ai.agents.execution.signal_engine import compute_signal

    # Charger l'état persisté (pas de nouvelles requêtes réseau)
    _pt = PaperTradingEngine(persist=True)
    _snap = _pt.snapshot(mark_prices={primary_symbol: closes[-1]} if closes else {})

    # KPIs
    col1, col2, col3, col4, col5 = st.columns(5)
    pnl_color = "normal" if _snap["pnl_pct"] >= 0 else "inverse"
    col1.metric("Balance", f"${_snap['balance']:,.0f}")
    col2.metric("Valeur portefeuille", f"${_snap['portfolio_value']:,.0f}")
    col3.metric(
        "P&L total",
        f"${_snap['pnl_total']:+,.0f}",
        f"{_snap['pnl_pct']:+.2f}%",
        delta_color=pnl_color,
    )
    col4.metric("Nb trades", str(_snap["n_trades"]))
    col5.metric("Win rate", f"{_snap['win_rate']:.1%}")

    # Signal multi-timeframe depuis la meilleure stratégie backtestée
    import json as _json

    from quant_hedge_ai.agents.execution.multi_timeframe_signal import (
        MultiTimeframeSignal as _MTFSig,
    )
    from quant_hedge_ai.agents.market.multi_timeframe_scanner import (
        MultiTimeframeScanner as _MTFScanner,
    )

    candles_json = _json.dumps(candles)
    with st.spinner("Calcul backtests + MTF…"):
        _bt = run_backtest_batch(candles_json, 5)

    if _bt:
        _best_s = _bt[0].get("strategy", {})

        # Fetch 4h + 1d (cachés 60 s par st.cache_data)
        @st.cache_data(ttl=240, show_spinner=False)
        def _load_mtf(sym, tf):
            sc = _MTFScanner(symbols=[sym], timeframes=[tf], refresh_every=1)
            raw = sc.scan(cycle=0)
            return raw.get(sym, {}).get(tf, [])

        _c4h = _load_mtf(primary_symbol, "4h")
        _c1d = _load_mtf(primary_symbol, "1d")
        _mtf_candles = {"1h": candles, "4h": _c4h, "1d": _c1d}

        _mtf_eng = _MTFSig(min_strength=0.5, min_agreement=2)
        _mtf_res = _mtf_eng.confirm(_best_s, _mtf_candles)
        _signal = _mtf_res["signal"]
        _confirmed = _mtf_res["confirmed"]
        _strength = _mtf_res["strength"]
        _alignment = _mtf_res["alignment"]

        signal_color = {"BUY": "#00e676", "SELL": "#ff5252", "HOLD": "#ffb300"}[_signal]
        conf_label = "✓ Confirmé" if _confirmed else "✗ Non confirmé"
        st.markdown(
            f"""
<div class="metric-card" style="border-left-color:{signal_color}">
<h3 style="color:{signal_color};margin:0">Signal MTF : {_signal} &nbsp;
  <span style="font-size:0.75em;color:#aaa">{conf_label} | force {_strength:.0%}</span>
</h3>
<p style="margin:0;color:#aaa">
Stratégie : <b>{_best_s.get('entry_indicator','?')}</b> p=<b>{_best_s.get('period','?')}</b>
| Sharpe : <b>{_bt[0].get('sharpe',0):.3f}</b>
</p>
</div>
""",
            unsafe_allow_html=True,
        )

        # Tableau alignement par TF
        st.markdown("#### Alignement par timeframe")
        _tf_cols = st.columns(len(_alignment))
        for i, (tf, sig) in enumerate(sorted(_alignment.items())):
            _c = {"BUY": "#00e676", "SELL": "#ff5252", "HOLD": "#ffb300"}.get(
                sig, "#aaa"
            )
            _tf_cols[i].markdown(
                f"<div style='text-align:center;padding:0.5rem;"
                f"background:#1e2130;border-radius:8px;border-top:3px solid {_c}'>"
                f"<b style='color:#aaa'>{tf}</b><br>"
                f"<span style='color:{_c};font-size:1.2em;font-weight:bold'>{sig}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Equity curve
    if _snap["equity_curve"]:
        eq_df = pd.DataFrame(_snap["equity_curve"])
        eq_df["ts"] = pd.to_datetime(eq_df["ts"], unit="ms")
        fig_eq = go.Figure(
            go.Scatter(
                x=eq_df["ts"],
                y=eq_df["value"],
                mode="lines",
                name="Equity",
                line=dict(color="#00e0ff", width=2),
                fill="tozeroy",
                fillcolor="rgba(0,224,255,0.07)",
            )
        )
        fig_eq.update_layout(
            title="Equity Curve — compte paper",
            template="plotly_dark",
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            yaxis_title="USD",
        )
        st.plotly_chart(fig_eq, use_container_width=True)
    else:
        st.info(
            "Pas encore de trades. Lancez `python -m quant_hedge_ai.main_v91` pour démarrer."
        )

    # Historique des trades
    if _snap["trade_history"]:
        th_df = pd.DataFrame(_snap["trade_history"])
        th_df["ts"] = pd.to_datetime(th_df["ts"], unit="ms")
        th_df = th_df[
            ["ts", "symbol", "action", "size", "price", "notional", "pnl", "balance"]
        ]
        th_df = th_df.sort_values("ts", ascending=False).head(20)
        st.markdown("### 📜 Derniers trades")
        st.dataframe(
            th_df.style.map(
                lambda v: (
                    "color:#00e676"
                    if v == "BUY"
                    else ("color:#ff5252" if v == "SELL" else "")
                ),
                subset=["action"],
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("Aucun trade pour l'instant.")

    # Reset
    st.markdown("---")
    if st.button("🔄 Réinitialiser le compte paper ($100 000)"):
        _pt.reset()
        st.success("Compte réinitialisé.")
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — RISK MONITOR
# ═══════════════════════════════════════════════════════════════════════════════
with tab_risk:
    st.markdown("## 🛡️ Risk Monitor")

    import math

    returns = (
        [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        if len(closes) >= 2
        else []
    )

    vol = (
        math.sqrt(sum(r**2 for r in returns[-24:]) / min(24, len(returns)))
        if returns
        else 0.0
    )
    peak = max(closes) if closes else 1.0
    drawdown = min(0.0, (closes[-1] - peak) / peak) if closes else 0.0

    # Niveau de risque (seuils identiques à GlobalRiskGate)
    if abs(drawdown) >= 0.15 or vol >= 0.04:
        level_name, color, label = "CRITICAL", "#ff5252", "🔴 CRITICAL"
    elif abs(drawdown) >= 0.08 or vol >= 0.025:
        level_name, color, label = "WARNING", "#ffb300", "⚠️ WARNING"
    else:
        level_name, color, label = "NOMINAL", "#00e676", "✅ NOMINAL"

    st.markdown(
        f"""
<div class="metric-card risk-{level_name.lower()}">
<h2 style="color:{color};margin:0">{label}</h2>
<p style="margin:0;color:#aaa">Niveau de risque estimé (vol + drawdown)</p>
</div>
""",
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Volatilité réalisée (24h)", f"{vol:.4f}", "normale" if vol < 0.02 else "élevée"
    )
    col2.metric("Drawdown depuis le pic", f"{drawdown:.2%}")
    col3.metric("Dernier prix", f"${closes[-1]:,.2f}" if closes else "—")
    col4.metric("Nb bougies", str(len(candles)))

    # Gauge volatilité
    fig_gauge = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=vol * 100,
            title={"text": "Volatilité réalisée (%)"},
            delta={"reference": 2.0},
            gauge={
                "axis": {"range": [0, 10]},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 2.5], "color": "#1a2a1a"},
                    {"range": [2.5, 4.0], "color": "#2a2a10"},
                    {"range": [4.0, 10], "color": "#2a0000"},
                ],
                "threshold": {
                    "line": {"color": "#ff5252", "width": 4},
                    "thickness": 0.75,
                    "value": 4.0,
                },
            },
        )
    )
    fig_gauge.update_layout(
        template="plotly_dark", height=280, margin=dict(l=20, r=20, t=40, b=20)
    )
    st.plotly_chart(fig_gauge, use_container_width=True)

    # Distribution des rendements
    if len(closes) >= 10:
        st.markdown("### Distribution des rendements (1h)")
        rets_pct = [r * 100 for r in returns[-100:]]
        fig_ret = px.histogram(
            x=rets_pct,
            nbins=40,
            title="Distribution des rendements (%)",
            template="plotly_dark",
            color_discrete_sequence=["#00e0ff"],
            labels={"x": "Rendement (%)", "y": "Fréquence"},
        )
        fig_ret.add_vline(x=0, line_dash="dash", line_color="#aaa")
        fig_ret.update_layout(height=280, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_ret, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_notif:
    st.markdown("## 🔔 Notifications")

    from notifications import build_telegram_bot

    bot = build_telegram_bot()
    telegram_status = (
        "✅ Actif"
        if bot
        else "❌ Désactivé (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID absents)"
    )
    st.markdown(f"**Telegram :** {telegram_status}")

    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    st.markdown(
        f"**Slack :** {'✅ Actif' if slack_url else '❌ Désactivé (SLACK_WEBHOOK_URL absent)'}"
    )

    st.markdown("---")
    st.markdown("### Test d'envoi manuel")
    test_msg = st.text_area(
        "Message de test",
        value=f"[Dashboard V9.1] Test depuis le dashboard — {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        height=80,
    )
    if st.button("📤 Envoyer le message de test"):
        from notifications import send_alert

        with st.spinner("Envoi…"):
            try:
                send_alert(test_msg)
                st.success("Message envoyé (ou silencieux si aucun canal configuré).")
            except Exception as e:
                st.error(f"Erreur : {e}")

    st.markdown("---")
    st.markdown("### Configuration requise dans `.env`")
    st.code(
        """# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
TELEGRAM_CHAT_ID=-1001234567890

# Slack (optionnel)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
""",
        language="bash",
    )

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(60)
    st.cache_data.clear()
    st.rerun()
