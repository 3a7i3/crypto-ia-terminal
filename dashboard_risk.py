"""
dashboard_risk.py — Risk Dashboard Streamlit temps réel.

Affiche l'état complet du système en temps réel :
  - Signaux actifs (score, régime, direction) par symbole
  - État du risk gate (autorisé / bloqué)
  - Shadow trades simulés (slippage, latence, notionnel)
  - Santé exchange (latence, uptime)
  - Historique des scores (graphique)
  - Journal des alertes

Lancement :
    streamlit run dashboard_risk.py
    streamlit run dashboard_risk.py --server.port 8502
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Crypto AI — Risk Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constantes ────────────────────────────────────────────────────────────────

SHADOW_LOG = Path("databases/shadow_execution/shadow_log.jsonl")
TRADE_LOG_DB = Path(os.getenv("EXEC_TRADE_LOG", "databases/trade_log.sqlite"))
ADVISOR_LOG = Path("logs/advisor_loop.log")

REFRESH_INTERVAL = int(os.getenv("DASHBOARD_REFRESH", "15"))  # secondes

SIGNAL_COLOR = {"BUY": "green", "SELL": "red", "HOLD": "gray"}
STATUS_EMOJI = {"ok": "✅", "warn": "⚠️", "degraded": "🔴", "offline": "❌"}


# ── Chargement des données ────────────────────────────────────────────────────


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_shadow_trades(n: int = 50) -> list[dict]:
    if not SHADOW_LOG.exists():
        return []
    trades = []
    try:
        with SHADOW_LOG.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))
    except Exception:
        return []
    return trades[-n:]


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_trade_log(n: int = 50) -> list[dict]:
    if not TRADE_LOG_DB.exists():
        return []
    try:
        import sqlite3

        con = sqlite3.connect(str(TRADE_LOG_DB))
        cur = con.execute(
            "SELECT symbol, action, size, status, ts FROM trades ORDER BY ts DESC LIMIT ?",
            (n,),
        )
        rows = cur.fetchall()
        con.close()
        return [
            {"symbol": r[0], "action": r[1], "size": r[2], "status": r[3], "ts": r[4]}
            for r in rows
        ]
    except Exception:
        return []


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_advisor_log_tail(n: int = 200) -> list[str]:
    if not ADVISOR_LOG.exists():
        return []
    try:
        with ADVISOR_LOG.open(encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [line.rstrip() for line in lines[-n:]]
    except Exception:
        return []


def parse_cycle_data(log_lines: list[str]) -> list[dict]:
    """Extrait les lignes de signal des logs pour construire l'historique."""
    records = []
    for line in log_lines:
        # Format: 2026-04-30 12:34:56 INFO advisor_loop - BTC/USDT | $70000.00 | score: 47/100 | BUY | regime: bull_trend | gate: OK
        if " | score: " in line and " | regime: " in line:
            try:
                parts = line.split(" | ")
                ts_part = parts[0].split()[0] + " " + parts[0].split()[1]
                sym = parts[0].split()[-1]
                price = float(parts[1].replace("$", ""))
                score = int(parts[2].replace("score: ", "").replace("/100", ""))
                signal = parts[3].strip()
                regime = parts[4].replace("regime: ", "").strip()
                gate = parts[5].replace("gate: ", "").strip() if len(parts) > 5 else "?"
                records.append(
                    {
                        "ts": ts_part,
                        "symbol": sym,
                        "price": price,
                        "score": score,
                        "signal": signal,
                        "regime": regime,
                        "gate": gate,
                    }
                )
            except Exception:
                continue
    return records


def check_exchange_health() -> dict:
    """Ping Binance testnet et retourne la santé."""
    import requests as req

    testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
    base = "https://testnet.binance.vision" if testnet else "https://api.binance.com"
    t0 = time.time()
    try:
        r = req.get(f"{base}/api/v3/ping", timeout=5)
        ms = (time.time() - t0) * 1000
        if r.status_code == 200:
            return {"status": "ok", "latency_ms": round(ms, 0), "error": ""}
    except Exception as exc:
        return {"status": "offline", "latency_ms": 0.0, "error": str(exc)}
    return {
        "status": "warn",
        "latency_ms": round((time.time() - t0) * 1000, 0),
        "error": "",
    }


# ── Layout ────────────────────────────────────────────────────────────────────

st.title("📊 Crypto AI Terminal — Risk Dashboard")
st.caption(
    f"Actualisation automatique toutes les {REFRESH_INTERVAL}s | Mode: ADVISOR ONLY"
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Paramètres")
    n_shadow = st.slider("Shadow trades affichés", 10, 200, 50)
    n_log = st.slider("Lignes de log", 50, 500, 200)
    show_raw_log = st.checkbox("Afficher log brut", value=False)
    st.divider()
    st.markdown("**Commandes Telegram**")
    st.code("/STATUS\n/SAFE_MODE\n/RESUME\n/STOP_ALL\n/CLOSE_ALL")
    st.divider()
    if st.button("🔄 Actualiser maintenant"):
        st.cache_data.clear()
        st.rerun()

# ── Row 1 : métriques globales ─────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

# Exchange health
exchange = check_exchange_health()
with col1:
    emoji = STATUS_EMOJI.get(exchange["status"], "?")
    st.metric(
        label=f"{emoji} Exchange Binance",
        value="En ligne" if exchange["status"] == "ok" else "HORS LIGNE",
        delta=(
            f"{exchange['latency_ms']:.0f} ms"
            if exchange["status"] == "ok"
            else exchange["error"][:30]
        ),
    )

# Shadow trades summary
shadow_trades = load_shadow_trades(n_shadow)
with col2:
    n_sh = len(shadow_trades)
    if n_sh > 0:
        avg_slip = sum(t.get("slippage_pct", 0) for t in shadow_trades) / n_sh
        st.metric(
            label="🧪 Shadow Trades",
            value=str(n_sh),
            delta=f"Slippage moy: {avg_slip:.3f}%",
        )
    else:
        st.metric(label="🧪 Shadow Trades", value="0", delta="Aucun signal actionable")

# Trade log
real_trades = load_trade_log(50)
with col3:
    n_real = len(real_trades)
    n_rej = sum(1 for t in real_trades if t.get("status") == "rejected")
    st.metric(label="📋 Ordres loggés", value=str(n_real), delta=f"{n_rej} rejetés")

# Advisor log last cycle
log_lines = load_advisor_log_tail(n_log)
cycle_data = parse_cycle_data(log_lines)
with col4:
    n_cy = len(cycle_data)
    if cycle_data:
        last = cycle_data[-1]
        st.metric(
            label="📈 Dernier signal",
            value=f"{last['symbol']} {last['signal']}",
            delta=f"Score: {last['score']}/100",
        )
    else:
        st.metric(label="📈 Dernier signal", value="—", delta="En attente")

st.divider()

# ── Row 2 : Signaux par symbole ────────────────────────────────────────────────

st.subheader("Signaux actifs par symbole")

SYMBOLS = os.getenv("ADVISOR_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT").split(",")

sym_cols = st.columns(len(SYMBOLS))
for i, sym in enumerate(SYMBOLS):
    sym_data = [r for r in cycle_data if r["symbol"].strip() == sym.strip()]
    with sym_cols[i]:
        if sym_data:
            last = sym_data[-1]
            color = SIGNAL_COLOR.get(last["signal"], "gray")
            score_bar = min(int(last["score"]), 100)
            st.markdown(f"**{sym}**")
            st.markdown(f"Prix: **${last['price']:,.2f}**")
            st.markdown(f"Signal: :{color}[**{last['signal']}**]")
            st.progress(score_bar, text=f"Score: {last['score']}/100")
            st.caption(f"Régime: {last['regime']} | Gate: {last['gate']}")
        else:
            st.markdown(f"**{sym}**")
            st.caption("En attente de données...")

st.divider()

# ── Row 3 : Graphique historique des scores ────────────────────────────────────

st.subheader("Historique des scores (derniers cycles)")

if cycle_data:
    df = pd.DataFrame(cycle_data)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")

    chart_data = df.pivot_table(
        index="ts", columns="symbol", values="score", aggfunc="last"
    ).reset_index()
    chart_data = chart_data.set_index("ts")

    st.line_chart(chart_data, use_container_width=True)

    # Seuils
    st.caption("Seuils: 70+ signal actionable | 50-69 à surveiller | <50 pas d'action")
else:
    st.info(
        "Aucune donnée de cycle disponible — lancez `python advisor_loop.py` pour démarrer."
    )

st.divider()

# ── Row 4 : Shadow trades détaillés ───────────────────────────────────────────

st.subheader("🧪 Shadow Trades simulés")

if shadow_trades:
    df_sh = pd.DataFrame(shadow_trades)
    cols_display = [
        c
        for c in [
            "id",
            "symbol",
            "signal",
            "signal_price",
            "simulated_fill_price",
            "slippage_pct",
            "notional",
            "signal_to_order_ms",
            "regime",
            "timestamp",
        ]
        if c in df_sh.columns
    ]

    if cols_display:
        df_show = df_sh[cols_display].tail(20)
        # Formater
        if "slippage_pct" in df_show.columns:
            df_show = df_show.copy()
            df_show["slippage_pct"] = df_show["slippage_pct"].map("{:.4f}%".format)
        if "notional" in df_show.columns:
            df_show["notional"] = df_show["notional"].map("${:.2f}".format)
        st.dataframe(df_show, use_container_width=True)

    # Stats agrégées
    if "slippage_pct" in df_sh.columns:
        col_a, col_b, col_c = st.columns(3)
        slippages = pd.to_numeric(
            df_sh["slippage_pct"].astype(str).str.replace("%", ""), errors="coerce"
        ).dropna()
        with col_a:
            st.metric("Slippage moyen", f"{slippages.mean():.4f}%")
        with col_b:
            st.metric("Slippage max", f"{slippages.max():.4f}%")
        if "signal_to_order_ms" in df_sh.columns:
            with col_c:
                lat = df_sh["signal_to_order_ms"].mean()
                st.metric("Latence moyenne", f"{lat:.1f} ms")
else:
    st.info(
        "Aucun shadow trade enregistré. Les trades simulés apparaissent quand le score atteint 70+."
    )

st.divider()

# ── Row 5 : Journal des ordres réels / paper ───────────────────────────────────

st.subheader("📋 Journal des ordres")

if real_trades:
    df_tr = pd.DataFrame(real_trades)
    st.dataframe(df_tr, use_container_width=True)
else:
    db_path = str(TRADE_LOG_DB)
    if TRADE_LOG_DB.exists():
        st.info(f"Base de données trouvée ({db_path}) — aucun ordre enregistré.")
    else:
        st.info(f"Base de données non trouvée ({db_path}).")

st.divider()

# ── Row 6 : Trade Replay ───────────────────────────────────────────────────────

st.subheader("🔁 Trade Replay")

with st.expander("Rejouer un trade par ID", expanded=False):
    replay_id = st.text_input("ID du trade (ex: SHD-1714300000-0001)", key="replay_id")
    if st.button("Rejouer") and replay_id.strip():
        try:
            from quant_hedge_ai.agents.execution.trade_replay import TradeReplaySystem

            rp = TradeReplaySystem()
            report = rp.replay(replay_id.strip())
            if report.found:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Symbole", report.symbol)
                c2.metric("Action", report.action)
                c3.metric("Score", f"{report.entry_score}/100")
                c4.metric("Régime", report.regime)
                c1b, c2b, c3b = st.columns(3)
                c1b.metric("Prix entrée", f"${report.entry_price:.4f}")
                c2b.metric("Slippage", f"{report.slippage_pct:.4f}%")
                c3b.metric("Latence", f"{report.latency_ms:.1f} ms")
                if report.components:
                    st.markdown("**Scores détaillés:**")
                    comp_cols = st.columns(len(report.components))
                    for i, (k, v) in enumerate(report.components.items()):
                        comp_cols[i].metric(k, f"{v:.1f}")
                if report.gate_conditions:
                    st.markdown("**Gate conditions:**")
                    for k, v in report.gate_conditions.items():
                        icon = "✅" if v else "❌"
                        st.write(f"{icon} {k}")
                with st.expander("JSON brut"):
                    st.json(report.raw)
            else:
                st.warning(f"Trade '{replay_id}' non trouvé dans les logs.")
        except Exception as exc:
            st.error(f"Erreur replay: {exc}")

with st.expander("Recherche dans les shadow trades", expanded=False):
    s_col1, s_col2, s_col3 = st.columns(3)
    with s_col1:
        s_symbol = st.selectbox("Symbole", ["", "BTC/USDT", "ETH/USDT", "SOL/USDT"])
    with s_col2:
        s_regime = st.selectbox(
            "Régime",
            [
                "",
                "bull_trend",
                "bear_trend",
                "sideways",
                "high_volatility_regime",
                "flash_crash",
            ],
        )
    with s_col3:
        s_min_score = st.slider("Score minimum", 0, 100, 0)
    if st.button("Rechercher"):
        try:
            from quant_hedge_ai.agents.execution.trade_replay import TradeReplaySystem

            rp = TradeReplaySystem()
            results = rp.search(
                symbol=s_symbol or None,
                regime=s_regime or None,
                min_score=s_min_score,
                n=100,
            )
            if results:
                df_rp = pd.DataFrame(results)
                cols_rp = [
                    c
                    for c in [
                        "id",
                        "symbol",
                        "action",
                        "signal_score",
                        "regime",
                        "slippage_pct",
                        "notional",
                        "signal_to_order_ms",
                        "timestamp",
                    ]
                    if c in df_rp.columns
                ]
                st.dataframe(df_rp[cols_rp], use_container_width=True)
                st.caption(f"{len(results)} résultats trouvés")
            else:
                st.info("Aucun résultat pour ces critères.")
        except Exception as exc:
            st.error(f"Erreur recherche: {exc}")

st.divider()

# ── Row 7 : Confidence Score Explainability ───────────────────────────────────

st.subheader("🔍 Analyse de confiance par symbole")

with st.expander("Décomposition détaillée du dernier score", expanded=True):
    ex_sym = st.selectbox("Symbole à analyser", SYMBOLS, key="ex_sym")

    # Récupérer le dernier signal enregistré pour ce symbole depuis les logs
    sym_data_ex = [r for r in cycle_data if r["symbol"].strip() == ex_sym.strip()]
    if sym_data_ex:
        last_ex = sym_data_ex[-1]
        score_ex = last_ex["score"]
        signal_ex = last_ex["signal"]
        regime_ex = last_ex["regime"]

        # Barre de score principale
        col_ex1, col_ex2, col_ex3 = st.columns(3)
        with col_ex1:
            st.metric("Score global", f"{score_ex}/100")
        with col_ex2:
            st.metric("Signal", signal_ex)
        with col_ex3:
            st.metric("Régime", regime_ex)

        st.progress(min(score_ex, 100), text=f"Score: {score_ex}/100")

        # Reconstruction des composants depuis les shadow trades si disponibles
        comp_data = None
        for t in reversed(shadow_trades):
            if t.get("symbol", "").strip() == ex_sym.strip():
                comp_data = t.get("components", {})
                break

        if comp_data:
            st.markdown("**Décomposition des composants :**")
            comp_rows = [
                ("Alignement multi-timeframes (MTF)", comp_data.get("mtf", 0), 40),
                ("Régime de marché", comp_data.get("regime", 0), 25),
                ("Qualité des données", comp_data.get("data_quality", 0), 15),
                ("Mémoire stratégique (Sharpe)", comp_data.get("memory", 0), 20),
            ]
            for label, val, max_val in comp_rows:
                pct = min(100.0, val / max_val * 100) if max_val else 0
                rating = (
                    "excellent"
                    if pct >= 85
                    else ("bon" if pct >= 65 else ("moyen" if pct >= 40 else "faible"))
                )
                color = "green" if pct >= 65 else ("orange" if pct >= 40 else "red")
                st.markdown(
                    f"**{label}** — {val:.1f}/{max_val} ({pct:.0f}%) :{color}[{rating}]"
                )
                st.progress(int(pct))

            # Verdict — utilise le vrai score signal, pas la somme des sous-composants
            if score_ex >= 70:
                st.success(
                    f"Verdict: SIGNAL ACTIONABLE — score {score_ex}/100 au-dessus du seuil (70)"
                )
            elif score_ex >= 50:
                st.warning(
                    f"Verdict: A SURVEILLER — score {score_ex}/100 proche du seuil (70)"
                )
            else:
                st.info(
                    f"Verdict: EN ATTENTE — score {score_ex}/100 sous le seuil (70)"
                )
        else:
            # Afficher ce qu'on a depuis les logs
            st.markdown("**Composants (depuis les logs) :**")
            st.info(
                "Score issu des cycles en cours. Les composants détaillés apparaissent quand un shadow trade est déclenché (score ≥ 70)."
            )

        # Graphique historique du score pour ce symbole
        if len(sym_data_ex) > 1:
            df_ex = pd.DataFrame(sym_data_ex)
            df_ex["ts"] = pd.to_datetime(df_ex["ts"], errors="coerce")
            df_ex = df_ex.set_index("ts")[["score"]].rename(
                columns={"score": f"Score {ex_sym}"}
            )
            st.line_chart(df_ex, use_container_width=True)
            # Ligne de seuil à 70
            st.caption("Seuil d'activation: 70/100 | Score actuel: " + str(score_ex))
    else:
        st.info(
            f"Aucune donnée disponible pour {ex_sym} — en attente du premier cycle."
        )

st.divider()

# ── Row 8 : Monte Carlo Stress Test ───────────────────────────────────────────

st.subheader("🎲 Monte Carlo Stress Test")

with st.expander("Lancer une simulation de survie", expanded=False):
    mc_col1, mc_col2, mc_col3 = st.columns(3)
    with mc_col1:
        mc_equity = st.number_input(
            "Capital ($)",
            value=float(os.getenv("V9_INITIAL_CAPITAL", "1000")),
            min_value=100.0,
        )
        mc_win_rate = st.slider(
            "Win rate estimé", 0.30, 0.75, 0.55, 0.01, format="%.2f"
        )
    with mc_col2:
        mc_avg_win = st.slider(
            "Gain moyen / trade (%)", 0.5, 5.0, 1.5, 0.1, format="%.1f%%"
        )
        mc_avg_loss = st.slider(
            "Perte moyenne / trade (%)", 0.3, 4.0, 1.0, 0.1, format="%.1f%%"
        )
    with mc_col3:
        mc_paths = st.select_slider(
            "Simulations", options=[200, 500, 1000, 2000], value=500
        )
        mc_steps = st.select_slider(
            "Trades simulés", options=[100, 200, 500], value=200
        )
        mc_pos_pct = st.slider(
            "Taille position (%)", 1.0, 10.0, 2.0, 0.5, format="%.1f%%"
        )

    use_shadow_calib = st.checkbox(
        "Calibrer depuis les shadow trades réels", value=False
    )

    if st.button("Lancer le stress test", type="primary"):
        try:
            import json as _json

            from quant_hedge_ai.agents.quant.stress_test import MonteCarloStressTester

            win_r = mc_win_rate
            avg_w = mc_avg_win / 100.0
            avg_l = mc_avg_loss / 100.0

            # Calibration shadow si demandée
            if use_shadow_calib and SHADOW_LOG.exists():
                trades_sh = []
                with SHADOW_LOG.open(encoding="utf-8") as _f:
                    for _ln in _f:
                        _ln = _ln.strip()
                        if _ln:
                            trades_sh.append(_json.loads(_ln))
                if len(trades_sh) >= 3:
                    n_buys = sum(1 for t in trades_sh if t.get("action") == "BUY")
                    win_r = n_buys / len(trades_sh)
                    slips = [t.get("slippage_pct", 0.05) / 100.0 for t in trades_sh]
                    avg_sl = sum(slips) / len(slips)
                    avg_w = max(0.005, 0.015 - avg_sl)
                    avg_l = max(0.005, 0.010 + avg_sl)
                    st.info(
                        f"Calibration: win_rate={win_r:.1%}  avg_win={avg_w:.2%}  avg_loss={avg_l:.2%}"
                    )

            with st.spinner(
                f"Simulation en cours ({mc_paths} chemins × {mc_steps} trades)..."
            ):
                tester = MonteCarloStressTester(
                    equity=mc_equity,
                    win_rate=win_r,
                    avg_win=avg_w,
                    avg_loss=avg_l,
                    position_pct=mc_pos_pct / 100.0,
                    seed=42,
                )
                report = tester.run_all(paths=mc_paths, steps=mc_steps)

            # Tableau résultats
            rows = []
            for s in report.scenarios:
                r = s.result
                rows.append(
                    {
                        "Scénario": s.name,
                        "Survie (%)": r["survival_rate_pct"],
                        "Ruine (%)": r["ruin_rate_pct"],
                        "Capital médian": f"${r['median_final_equity']:,.0f}",
                        "p5 (pire)": f"${r['p05_final_equity']:,.0f}",
                        "p95 (meilleur)": f"${r['p95_final_equity']:,.0f}",
                        "DD moy (%)": r["avg_max_drawdown_pct"],
                        "DD pire (%)": r["worst_max_drawdown_pct"],
                        "Retour méd (%)": r["median_return_pct"],
                    }
                )
            df_mc = pd.DataFrame(rows)

            # Coloriser selon taux de survie
            def _color_surv(val):
                try:
                    v = float(val)
                    if v >= 90:
                        return "background-color: #d4edda"
                    if v >= 70:
                        return "background-color: #fff3cd"
                    return "background-color: #f8d7da"
                except Exception:
                    return ""

            st.dataframe(
                df_mc.style.applymap(_color_surv, subset=["Survie (%)"]),
                use_container_width=True,
            )

            # Verdict
            worst = report.worst_scenario()
            if worst:
                min_surv = worst.survival_rate()
                if min_surv >= 90:
                    st.success(
                        f"GO LIVE — taux de survie minimum {min_surv:.1f}% (scénario: {worst.name})"
                    )
                elif min_surv >= 70:
                    st.warning(
                        f"PRUDENCE — taux de survie minimum {min_surv:.1f}% (scénario: {worst.name})"
                    )
                else:
                    st.error(
                        f"RISQUE ELEVE — taux de survie minimum {min_surv:.1f}% (scénario: {worst.name})"
                    )

            # Graphique survival par scénario
            surv_data = {s.name: s.survival_rate() for s in report.scenarios}
            st.bar_chart(pd.DataFrame({"Taux de survie (%)": surv_data}))

        except Exception as exc:
            st.error(f"Erreur stress test: {exc}")

st.divider()

# ── Row 9 : Log brut (optionnel) ───────────────────────────────────────────────

if show_raw_log:
    st.subheader("📄 Log brut (advisor_loop.log)")
    if log_lines:
        # Coloriser les niveaux
        colored = []
        for ln in log_lines[-100:]:
            if "ERROR" in ln or "CRITICAL" in ln:
                colored.append(f"🔴 {ln}")
            elif "WARNING" in ln:
                colored.append(f"⚠️ {ln}")
            elif "SIGNAL ACTIONABLE" in ln:
                colored.append(f"📈 {ln}")
            else:
                colored.append(ln)
        st.text("\n".join(colored))
    else:
        st.info("Log non disponible (logs/advisor_loop.log introuvable).")

# ── Auto-refresh ──────────────────────────────────────────────────────────────

st.caption(f"Dernière actualisation: {datetime.now().strftime('%H:%M:%S')}")
time.sleep(REFRESH_INTERVAL)
st.rerun()
