"""
dashboard_master.py — Tableau de bord unifié Crypto AI Terminal

Onglets :
  1. Vue Globale   — santé système, capital, exchange, modules
  2. Marchés Live  — prix, signaux, scores par symbole
  3. Analyse       — cohérence décisions, raisons refus, scores
  4. Positions     — positions ouvertes + historique

Auto-refresh configurable.
Source : databases/black_box.jsonl + cycle_data.jsonl + trades.jsonl

Usage :
    streamlit run dashboard_master.py
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Config ────────────────────────────────────────────────────────────────────

BASE = Path(__file__).parent
BLACK_BOX = BASE / "databases" / "black_box.jsonl"
CYCLE_DATA = BASE / "databases" / "cycle_data.jsonl"
SNAPSHOT = BASE / "databases" / "live_snapshot.json"
TRADES = BASE / "logs" / "trades.jsonl"

REFRESH_SEC = 20

st.set_page_config(
    page_title="Crypto AI — Master Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
.main { background-color: #080d1a; }
.block-container { padding-top: 0.35rem; padding-bottom: 0rem; }
div[data-testid="metric-container"] {
    background: linear-gradient(135deg, #0d1b2a 0%, #1a2744 100%);
    border: 1px solid #1e3a5f;
    border-radius: 7px;
    padding: 6px 10px;
}
div[data-testid="metric-container"] label {
    font-size: 0.68rem !important;
    color: #6b8cad !important;
}
div[data-testid="stMetricValue"] {
    font-size: 1.05rem !important;
    color: #ffffff !important;
    font-weight: 700;
}
div[data-testid="stMetricDelta"] { font-size: 0.7rem !important; }
h1, h2 { font-size: 1.1rem !important; margin-bottom: 0.2rem !important; }
h3, h4 { font-size: 0.88rem !important; margin-bottom: 0.15rem !important; }
.status-ok   { color: #00d4aa; font-weight: 700; }
.status-warn { color: #f0a500; font-weight: 700; }
.status-err  { color: #ff4444; font-weight: 700; }
hr { margin: 0.35rem 0 !important; }
div[data-testid="stAlert"] { padding: 0.45rem 0.75rem !important; font-size: 0.8rem; }
.mod-card {
    background: #0d1b2a;
    border: 1px solid #1e3a5f;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 11px;
    min-width: 130px;
}
</style>
""",
    unsafe_allow_html=True,
)


# ── Loaders ───────────────────────────────────────────────────────────────────


@st.cache_data(ttl=REFRESH_SEC)
def load_jsonl(path: Path, max_lines: int = 5000) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-max_lines:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


@st.cache_data(ttl=REFRESH_SEC)
def load_snapshot() -> dict:
    if not SNAPSHOT.exists():
        return {}
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def to_df(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def compute_coherence(decisions: list[dict]) -> list[dict]:
    """
    Croise TRADE_EXECUTED avec POSITION_CLOSED (même symbole, clôture après entrée).
    Retourne une liste de trades classifiés :
      VALIDATED  — score ≥ 70 + win
      LUCKY      — score < 70 + win
      UNLUCKY    — score ≥ 70 + loss
      MISTAKE    — score < 70 + loss
    """
    executions = [d for d in decisions if d.get("decision_type") == "TRADE_EXECUTED"]
    closures = [d for d in decisions if d.get("decision_type") == "POSITION_CLOSED"]
    # Index closures par symbole pour lookup rapide
    closures_by_sym: dict[str, list[dict]] = {}
    for c in closures:
        closures_by_sym.setdefault(c.get("symbol", ""), []).append(c)

    results = []
    for ex in executions:
        sym = ex.get("symbol", "")
        ex_ts = ex.get("ts", 0)
        score = ex.get("score", 0)
        # Trouver la clôture la plus proche APRÈS l'exécution
        candidates = [c for c in closures_by_sym.get(sym, []) if c.get("ts", 0) > ex_ts]
        if not candidates:
            continue
        cl = min(candidates, key=lambda c: c["ts"] - ex_ts)
        pnl_pct = cl.get("pnl_pct", 0.0)
        win = pnl_pct > 0
        high_conf = score >= 70
        if high_conf and win:
            label = "VALIDATED"
        elif not high_conf and win:
            label = "LUCKY"
        elif high_conf and not win:
            label = "UNLUCKY"
        else:
            label = "MISTAKE"
        results.append(
            {
                "symbol": sym,
                "entry_ts": fmt_ts(ex_ts),
                "score": score,
                "regime": ex.get("regime", ""),
                "pnl_pct": round(pnl_pct * 100, 2),
                "win": win,
                "label": label,
                "duration_min": round((cl["ts"] - ex_ts) / 60, 1),
                "close_reason": cl.get("close_reason", ""),
            }
        )
    return results


# ── Layout ────────────────────────────────────────────────────────────────────

header_col, refresh_col = st.columns([5, 1])
with header_col:
    st.markdown("## 🤖 Crypto AI — Master Dashboard")
with refresh_col:
    st.markdown(
        f"<small style='color:#6b8cad'>Auto-refresh {REFRESH_SEC}s</small>",
        unsafe_allow_html=True,
    )
    if st.button("⟳ Rafraîchir"):
        st.cache_data.clear()
        st.rerun()

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "🌐 Vue Globale",
        "📈 Marchés Live",
        "🧠 Analyse Décisions",
        "📋 Positions",
    ]
)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Vue Globale
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    snap = load_snapshot()
    cycles = load_jsonl(CYCLE_DATA, max_lines=500)

    if snap:
        ts_str = fmt_ts(snap.get("ts", time.time()))
        cycle = snap.get("cycle", "—")
        capital = snap.get("capital", 0.0)
        safe = snap.get("safe_mode", False)
        exch = snap.get("exchange", {})

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("💰 Capital", f"${capital:,.2f}")
        c2.metric("🔄 Cycle", cycle)
        c3.metric("⚡ Durée cycle", f"{snap.get('cycle_duration_ms', 0):.0f} ms")
        c4.metric("⏱ Latence exchange", f"{exch.get('last_latency_ms', 0):.0f} ms")
        c5.metric("📡 Uptime exchange", f"{exch.get('uptime_pct', 0):.1f}%")
        c6.metric("🛡 Safe Mode", "OUI ⚠️" if safe else "NON ✅")

        # Ligne 2 — signaux du cycle
        n_sym = snap.get("n_symbols", 0)
        n_act = snap.get("n_actionable", 0)
        n_trd = snap.get("n_traded", 0)
        n_ref = snap.get("n_refused", 0)
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("📊 Symboles analysés", n_sym)
        d2.metric("🎯 Signaux actionnables", n_act)
        d3.metric("✅ Trades exécutés", n_trd)
        d4.metric("🚫 Refusés", n_ref)

        st.caption(f"Dernière mise à jour : {ts_str} | Cycle #{cycle}")

        # Exchange status
        exch_ok = exch.get("healthy", False)
        st.markdown(
            f"**Exchange** : <span class='{'status-ok' if exch_ok else 'status-err'}'>"
            f"{'✅ Connecté' if exch_ok else '❌ Déconnecté'}</span> "
            f"— Échecs consécutifs : {exch.get('consecutive_failures', 0)} "
            f"— Vérifications totales : {exch.get('total_checks', 0)}",
            unsafe_allow_html=True,
        )
        if exch.get("last_error"):
            with st.expander("Dernière erreur exchange"):
                st.code(exch["last_error"], language=None)

        # Refusal breakdown + régimes
        col_rb, col_rd = st.columns(2)
        with col_rb:
            rb = snap.get("refusal_breakdown", {})
            if rb:
                st.markdown("**🚫 Couches de refus (cycle courant)**")
                df_rb = pd.DataFrame(rb.items(), columns=["Couche", "Refus"])
                st.dataframe(df_rb, use_container_width=True, hide_index=True)
            else:
                st.markdown("**🚫 Refus ce cycle :** aucun signal actionnable bloqué")
        with col_rd:
            rd = snap.get("regime_distribution", {})
            if rd:
                st.markdown("**📈 Régimes détectés ce cycle**")
                df_rd = pd.DataFrame(rd.items(), columns=["Régime", "Symboles"])
                st.dataframe(df_rd, use_container_width=True, hide_index=True)
    else:
        st.warning("Snapshot live introuvable — le bot est-il en cours d'exécution ?")

    st.divider()

    # Modules status grid
    st.markdown("#### 🧩 Modules système")
    MODULES = [
        # (nom affiché, chemin relatif, taille min en bytes pour "actif")
        ("Signal Engine", "quant_hedge_ai/agents/execution/signal_engine.py", 0),
        ("Execution Engine", "quant_hedge_ai/agents/execution/execution_engine.py", 0),
        ("Position Manager", "quant_hedge_ai/agents/execution/position_manager.py", 0),
        ("Shadow Engine", "quant_hedge_ai/agents/execution/shadow_engine.py", 0),
        ("Portfolio Brain", "quant_hedge_ai/agents/risk/portfolio_brain.py", 0),
        ("Risk Gate", "quant_hedge_ai/agents/risk/global_risk_gate.py", 0),
        ("Executive Override", "quant_hedge_ai/agents/risk/executive_override.py", 0),
        (
            "Capital Alloc.",
            "quant_hedge_ai/agents/risk/capital_allocation_engine.py",
            0,
        ),
        ("Black Box", "databases/black_box.jsonl", 1000),
        ("Cycle Data", "databases/cycle_data.jsonl", 1000),
        ("Mistake Memory", "databases/mistake_memory.jsonl", 0),
        ("Strategy Ranking", "databases/strategy_ranking.json", 100),
        (
            "Conviction Engine",
            "quant_hedge_ai/agents/intelligence/conviction_engine.py",
            0,
        ),
        (
            "Meta Strategy",
            "quant_hedge_ai/agents/intelligence/meta_strategy_engine.py",
            0,
        ),
        (
            "Self-Awareness",
            "quant_hedge_ai/agents/intelligence/self_awareness_engine.py",
            0,
        ),
        ("Threat Radar", "quant_hedge_ai/agents/intelligence/threat_radar.py", 0),
        ("Watchdog VPS", "watchdog_vps.py", 0),
        ("Watchdog Audit", "supervision/watchdog_audit.jsonl", 10),
    ]
    cols = st.columns(4)
    for i, (name, fpath, min_bytes) in enumerate(MODULES):
        p = BASE / fpath
        if not p.exists():
            icon, color = "🔴", "#ff4444"
        elif min_bytes > 0 and p.stat().st_size < min_bytes:
            icon, color = "🟡", "#f0a500"
        else:
            icon, color = "🟢", "#00d4aa"
        card = (
            f"<div class='mod-card' style='border-color:{color}'>"
            f"{icon} <b>{name}</b></div>"
        )
        cols[i % 4].markdown(card, unsafe_allow_html=True)

    st.divider()

    # Capital + durée cycles
    if cycles:
        df_cyc = (
            pd.DataFrame(
                [
                    {
                        "cycle": r.get("cycle"),
                        "capital": r.get("capital"),
                        "duration_ms": r.get("cycle_duration_ms"),
                        "n_traded": r.get("n_traded", 0),
                    }
                    for r in cycles
                    if r.get("capital")
                ]
            )
            .sort_values("cycle")
            .tail(150)
        )

        if not df_cyc.empty:
            ch_cap, ch_dur = st.columns(2)
            with ch_cap:
                st.markdown("#### 💰 Capital (150 derniers cycles)")
                st.line_chart(df_cyc.set_index("cycle")["capital"], height=130)
            with ch_dur:
                st.markdown("#### ⚡ Durée cycle ms (150 derniers cycles)")
                df_dur = df_cyc.dropna(subset=["duration_ms"])
                if not df_dur.empty:
                    st.line_chart(df_dur.set_index("cycle")["duration_ms"], height=130)
                else:
                    st.info("Durée non encore enregistrée (redémarrer le bot)")

        # Tableau refusal_breakdown historique
        bb_snap = [r for r in cycles if r.get("refusal_breakdown")]
        if bb_snap:
            st.markdown("#### 🚫 Refus cumulés par couche (depuis démarrage)")
            total_ref: dict[str, int] = {}
            for r in bb_snap:
                for layer, cnt in r["refusal_breakdown"].items():
                    total_ref[layer] = total_ref.get(layer, 0) + cnt
            df_tot = pd.DataFrame(
                sorted(total_ref.items(), key=lambda x: -x[1]),
                columns=["Couche", "Refus totaux"],
            )
            st.bar_chart(df_tot.set_index("Couche"), height=140)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Marchés Live
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    snap = load_snapshot()
    symbols = snap.get("symbols", [])

    if symbols:
        st.markdown(f"#### 📊 Signaux live — Cycle #{snap.get('cycle', '—')}")
        rows = []
        for s in symbols:
            score = s.get("score", 0)
            rsi = s.get("rsi")
            bb = s.get("bb_pct")
            atr = s.get("atr_ratio")
            rows.append(
                {
                    "Symbole": s.get("symbol", ""),
                    "Prix": f"${s.get('prix', 0):,.4f}",
                    "Signal": s.get("signal", ""),
                    "Score": score,
                    "Régime": s.get("regime", ""),
                    "Personnalité": s.get("personality", ""),
                    "Conviction": s.get("conviction_level", ""),
                    "RSI": f"{rsi:.1f}" if rsi is not None else "—",
                    "BB%": f"{bb:.2f}" if bb is not None else "—",
                    "ATR%": f"{atr*100:.2f}%" if atr is not None else "—",
                    "MACD ▲": "✅" if s.get("macd_bullish") else "❌",
                    "EMA ▲": "✅" if s.get("ema_bullish") else "❌",
                    "Squeeze": "🔴" if s.get("bb_squeeze") else "—",
                    "Actionnable": "✅" if s.get("actionable") else "❌",
                    "Gate OK": "✅" if s.get("gate_allowed") else "❌",
                    "Trade OK": "✅" if s.get("trade_allowed") else "❌",
                }
            )
        df_sym = pd.DataFrame(rows)
        st.dataframe(df_sym, use_container_width=True, hide_index=True)

        # Score bars + indicateurs visuels par symbole
        st.markdown("#### 🎯 Scores de signal (seuil = 70) + indicateurs clés")
        for s in symbols:
            score = s.get("score", 0)
            rsi = s.get("rsi")
            bb = s.get("bb_pct")
            color = (
                "#00d4aa" if score >= 70 else "#f0a500" if score >= 50 else "#ff6b6b"
            )
            rsi_color = (
                "#ff4444"
                if rsi and rsi > 70
                else "#00d4aa" if rsi and rsi < 30 else "#aaaaaa"
            )
            rsi_str = (
                f"RSI <span style='color:{rsi_color}'>{rsi:.1f}</span>"
                if rsi is not None
                else "RSI —"
            )
            bb_str = f"BB% {bb:.2f}" if bb is not None else "BB —"
            label = "⬆ TRADE" if score >= 70 else "⏸ HOLD"
            st.markdown(
                f"**{s['symbol']}** &nbsp; score {score}/100 "
                f"<span style='color:{color}'>{label}</span>"
                f" &nbsp;|&nbsp; {rsi_str} &nbsp;|&nbsp; {bb_str}",
                unsafe_allow_html=True,
            )
            st.progress(min(score / 100, 1.0))
    else:
        cycles_data = load_jsonl(CYCLE_DATA, max_lines=10)
        if cycles_data:
            last = cycles_data[-1]
            cyc = last.get("cycle")
            ts_last = fmt_ts(last.get("ts", 0))
            st.info(f"Snapshot vide — dernier cycle #{cyc} à {ts_last}")
        else:
            st.warning("Aucune donnée marché disponible.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Analyse Décisions
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    bb_records = load_jsonl(BLACK_BOX, max_lines=5000)
    decisions = [
        r for r in bb_records if r.get("decision_type") not in ("SYSTEM_EVENT", None)
    ]

    if not decisions:
        st.warning("Aucune décision enregistrée dans black_box.jsonl")
    else:
        n_cycles_seen = len({d.get("cycle") for d in decisions if d.get("cycle")})
        last_dec = decisions[-1]
        last_ts = fmt_ts(last_dec.get("ts", 0))
        last_cyc = last_dec.get("cycle", "—")

        # Diagnostic de cohérence automatique
        scores = [
            d.get("score", 0)
            for d in decisions
            if isinstance(d.get("score"), (int, float))
        ]
        avg_score = sum(scores) / len(scores) if scores else 0
        max_score = max(scores) if scores else 0
        holds_pct = (
            sum(1 for d in decisions if d.get("decision_type") == "HOLD")
            / len(decisions)
            * 100
        )

        if avg_score < 50 and holds_pct > 95:
            verdict = "🟢 COHÉRENT — Marché sans tendance, refus massifs justifiés"
            detail = (
                f"Score moyen {avg_score:.1f}/100 < seuil 70."
                " Le bot attend un meilleur setup."
            )
        elif avg_score >= 50 and holds_pct > 95:
            verdict = "🟡 À SURVEILLER — Scores corrects mais aucun trade passé"
            detail = f"Score moyen {avg_score:.1f}/100. Vérifier les couches de refus."
        elif holds_pct < 50:
            verdict = "🔵 TRADING ACTIF — Le bot exécute des positions"
            detail = f"{100-holds_pct:.1f}% des décisions ont mené à un trade."
        else:
            verdict = "⚪ EN OBSERVATION"
            detail = f"Score moyen {avg_score:.1f}/100, {holds_pct:.1f}% HOLD."

        st.info(f"**Diagnostic :** {verdict}  \n{detail}")
        st.markdown(
            f"**{len(decisions):,}** décisions · **{n_cycles_seen}** cycles · "
            f"Dernier cycle **#{last_cyc}** à {last_ts} · "
            f"Score max vu : **{max_score}**/100"
        )

        # KPIs
        total = len(decisions)
        holds = sum(1 for d in decisions if d.get("decision_type") == "HOLD")
        trades = sum(1 for d in decisions if d.get("decision_type") in ("BUY", "SELL"))
        closed = sum(
            1 for d in decisions if d.get("decision_type") == "POSITION_CLOSED"
        )
        refused = sum(1 for d in decisions if d.get("decision_type") == "TRADE_REFUSED")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total décisions", f"{total:,}")
        c2.metric("HOLD", f"{holds:,}", f"{100*holds//total}%")
        c3.metric("TRADES exécutés", f"{trades:,}")
        c4.metric("Positions fermées", closed)
        c5.metric("Refus explicites", refused)

        st.divider()
        col_left, col_right = st.columns(2)

        with col_left:
            # Régimes
            st.markdown("**Régimes détectés**")
            regimes = Counter(d.get("regime", "unknown") for d in decisions)
            df_reg = pd.DataFrame(regimes.most_common(), columns=["Régime", "Count"])
            st.bar_chart(df_reg.set_index("Régime"), height=140)

            # Conviction
            st.markdown("**Niveaux de conviction**")
            convs = Counter(d.get("conviction_level", "—") for d in decisions)
            df_conv = pd.DataFrame(convs.most_common(), columns=["Conviction", "Count"])
            st.bar_chart(df_conv.set_index("Conviction"), height=120)

        with col_right:
            # Score distribution
            st.markdown("**Distribution des scores de signal**")
            scores = [
                d.get("score", 0)
                for d in decisions
                if isinstance(d.get("score"), (int, float))
            ]
            if scores:
                df_scores = pd.DataFrame({"score": scores})
                hist = df_scores["score"].value_counts().sort_index()
                st.bar_chart(hist, height=140)
                avg_s = sum(scores) / len(scores)
                st.caption(
                    f"Score moyen : {avg_s:.1f}"
                    f" | Max : {max(scores)} | Min : {min(scores)}"
                )

            # Personnalités
            st.markdown("**Personnalités activées**")
            persos = Counter(d.get("personality", "—") for d in decisions)
            df_perso = pd.DataFrame(
                persos.most_common(), columns=["Personnalité", "Count"]
            )
            st.bar_chart(df_perso.set_index("Personnalité"), height=120)

        # Évolution du score par cycle (par symbole)
        st.divider()
        st.markdown("#### 📈 Évolution du score de signal par cycle")
        score_by_cycle: dict[str, list] = {}
        for d in decisions:
            sym = d.get("symbol", "?")
            cycle = d.get("cycle")
            score = d.get("score")
            if cycle and score is not None:
                score_by_cycle.setdefault(sym, []).append(
                    {"cycle": cycle, "score": score}
                )
        if score_by_cycle:
            dfs = []
            for sym, pts in score_by_cycle.items():
                df_s = pd.DataFrame(pts).groupby("cycle")["score"].mean().rename(sym)
                dfs.append(df_s)
            df_scores_time = pd.concat(dfs, axis=1).sort_index().tail(100)
            st.line_chart(df_scores_time, height=150)
            st.caption(
                "Score moyen par cycle — ligne pointillée mentale à 70 = seuil de trade"
            )

        st.divider()
        st.markdown("#### 🚫 Raisons de refus (top modules)")
        all_refused_by = []
        for d in decisions:
            all_refused_by.extend(d.get("refused_by", []))
        if all_refused_by:
            cnt = Counter(all_refused_by)
            df_ref = pd.DataFrame(
                cnt.most_common(15), columns=["Raison", "Occurrences"]
            )
            st.dataframe(df_ref, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun refus enregistré.")

        st.divider()
        st.markdown("#### ✅ Modules qui valident (passed_by)")
        all_passed = []
        for d in decisions:
            all_passed.extend(d.get("passed_by", []))
        if all_passed:
            cnt2 = Counter(all_passed)
            df_pass = pd.DataFrame(
                cnt2.most_common(10), columns=["Module", "Validations"]
            )
            st.dataframe(df_pass, use_container_width=True, hide_index=True)

        # ── Cohérence Signal vs Résultat ──────────────────────────────────────
        st.divider()
        st.markdown("#### 🔬 Cohérence Signal → Résultat (post-mortem automatique)")

        coherence = compute_coherence(decisions)
        if not coherence:
            st.info(
                "Pas encore de trades fermés à analyser — "
                "la cohérence s'affiche dès la première clôture de position."
            )
        else:
            cnt_labels = Counter(r["label"] for r in coherence)
            total_coh = len(coherence)
            wins_coh = sum(1 for r in coherence if r["win"])

            cc1, cc2, cc3, cc4, cc5 = st.columns(5)
            cc1.metric("Trades analysés", total_coh)
            cc2.metric(
                "✅ VALIDATED",
                cnt_labels.get("VALIDATED", 0),
                f"{100*cnt_labels.get('VALIDATED',0)//total_coh}%",
            )
            cc3.metric(
                "🍀 LUCKY",
                cnt_labels.get("LUCKY", 0),
                f"{100*cnt_labels.get('LUCKY',0)//total_coh}%",
            )
            cc4.metric(
                "😓 UNLUCKY",
                cnt_labels.get("UNLUCKY", 0),
                f"{100*cnt_labels.get('UNLUCKY',0)//total_coh}%",
            )
            cc5.metric(
                "❌ MISTAKE",
                cnt_labels.get("MISTAKE", 0),
                f"{100*cnt_labels.get('MISTAKE',0)//total_coh}%",
            )

            # Verdict de qualité
            validated_pct = cnt_labels.get("VALIDATED", 0) / total_coh * 100
            mistake_pct = cnt_labels.get("MISTAKE", 0) / total_coh * 100
            win_rate_high = (
                sum(1 for r in coherence if r["win"] and r["score"] >= 70)
                / max(sum(1 for r in coherence if r["score"] >= 70), 1)
                * 100
            )
            win_rate_low = (
                sum(1 for r in coherence if r["win"] and r["score"] < 70)
                / max(sum(1 for r in coherence if r["score"] < 70), 1)
                * 100
            )

            if validated_pct >= 50:
                coh_verdict = (
                    f"🟢 MODÈLE COHÉRENT — {validated_pct:.0f}% des trades"
                    f" haute conviction sont gagnants"
                )
            elif mistake_pct >= 40:
                coh_verdict = (
                    f"🔴 MODÈLE INCOHÉRENT — {mistake_pct:.0f}% de MISTAKE"
                    " (score élevé mais perte)"
                )
            elif win_rate_high > win_rate_low + 10:
                coh_verdict = (
                    f"🟡 SIGNAL UTILE — Win rate score≥70 : {win_rate_high:.0f}%"
                    f" vs score<70 : {win_rate_low:.0f}%"
                )
            else:
                coh_verdict = (
                    f"⚪ SIGNAL NEUTRE — Win rate similaire peu importe le score"
                    f" ({win_rate_high:.0f}% vs {win_rate_low:.0f}%)"
                )
            st.info(coh_verdict)

            # Barre de classification
            df_coh_bar = pd.DataFrame(
                [(k, v) for k, v in cnt_labels.most_common()],
                columns=["Classification", "Count"],
            )
            st.bar_chart(df_coh_bar.set_index("Classification"), height=110)

            # Win rate score≥70 vs score<70
            wr_col1, wr_col2 = st.columns(2)
            wr_col1.metric(
                "Win rate score ≥ 70 (haute conviction)",
                f"{win_rate_high:.1f}%",
            )
            wr_col2.metric(
                "Win rate score < 70 (basse conviction)",
                f"{win_rate_low:.1f}%",
            )

            # Tableau détaillé
            with st.expander("📋 Détail trade par trade"):
                df_coh = pd.DataFrame(coherence)
                df_coh = df_coh.sort_values("entry_ts", ascending=False)
                st.dataframe(df_coh, use_container_width=True, hide_index=True)

        # ── 50 dernières décisions ─────────────────────────────────────────────
        st.divider()
        st.markdown("#### 📜 50 dernières décisions")
        recent = decisions[-50:][::-1]
        rows = []
        for d in recent:
            rows.append(
                {
                    "Heure": fmt_ts(d.get("ts", 0)),
                    "Symbole": d.get("symbol", ""),
                    "Décision": d.get("decision_type", ""),
                    "Score": d.get("score", ""),
                    "Régime": d.get("regime", ""),
                    "Personnalité": d.get("personality", ""),
                    "Conviction": d.get("conviction_level", ""),
                    "Prix": f"${d.get('price', 0):,.4f}" if d.get("price") else "—",
                    "Raison": (d.get("reason") or "")[:60],
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Positions
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    snap = load_snapshot()
    open_positions = snap.get("positions", [])

    st.markdown("#### 📂 Positions ouvertes")
    if open_positions:
        df_open = pd.DataFrame(open_positions)
        st.dataframe(df_open, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune position ouverte en ce moment.")

    st.divider()
    st.markdown("#### 📚 Historique des positions fermées")

    trades_raw = load_jsonl(TRADES, max_lines=1000)
    entries = {r["id"]: r for r in trades_raw if r.get("type") == "entry"}
    exits = [r for r in trades_raw if r.get("type") == "exit"]

    if exits:
        rows = []
        for ex in reversed(exits[-100:]):
            tid = ex.get("id", "")
            en = entries.get(tid, {})
            win = ex.get("win")
            rows.append(
                {
                    "ID": tid,
                    "Symbole": ex.get("symbol", ""),
                    "Direction": ex.get("direction", ""),
                    "Entrée": f"${ex.get('entry_price', 0):.4f}",
                    "Sortie": f"${ex.get('exit_price', 0):.4f}",
                    "PnL %": f"{ex.get('pnl_pct', 0)*100:.2f}%",
                    "PnL $": f"${ex.get('pnl_usd', 0):.4f}",
                    "Résultat": "✅ Win" if win else "❌ Loss",
                    "Durée (min)": f"{ex.get('duration_min', 0):.1f}",
                    "Raison sortie": ex.get("exit_reason", ""),
                    "Régime": ex.get("regime", ""),
                    "Confiance": ex.get("confidence", ""),
                    "Paper": "📄" if ex.get("paper") else "💰",
                    "Date": ex.get("logged_at", "")[:16],
                }
            )
        df_hist = pd.DataFrame(rows)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        st.divider()
        # Stats de performance
        wins = sum(1 for e in exits if e.get("win"))
        losses = len(exits) - wins
        total_pnl = sum(e.get("pnl_usd", 0) for e in exits)
        avg_pnl = total_pnl / len(exits) if exits else 0
        avg_dur = (
            sum(e.get("duration_min", 0) for e in exits) / len(exits) if exits else 0
        )
        pnl_pcts = [e.get("pnl_pct", 0) for e in exits]
        best = max(pnl_pcts) * 100 if pnl_pcts else 0
        worst = min(pnl_pcts) * 100 if pnl_pcts else 0

        st.markdown("#### 📊 Performance globale")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total trades", len(exits))
        c2.metric("Win Rate", f"{100*wins//len(exits)}%" if exits else "—")
        c3.metric("PnL total", f"${total_pnl:.2f}")
        c4.metric("PnL moyen / trade", f"${avg_pnl:.2f}")
        c5.metric("Meilleur trade", f"+{best:.2f}%")
        c6.metric("Pire trade", f"{worst:.2f}%")

        # Courbe PnL cumulé
        if exits:
            pnl_cumul = []
            cum = 0.0
            for e in exits:
                cum += e.get("pnl_usd", 0)
                pnl_cumul.append(
                    {"trade": len(pnl_cumul) + 1, "pnl_cumul": round(cum, 4)}
                )
            df_pnl = pd.DataFrame(pnl_cumul).set_index("trade")
            st.markdown("#### 📈 PnL cumulé ($)")
            st.line_chart(df_pnl["pnl_cumul"], height=130)

        # Breakdown par raison de sortie
        exit_reasons = Counter(e.get("exit_reason", "?")[:30] for e in exits)
        if exit_reasons:
            st.markdown("#### 🚪 Raisons de sortie")
            df_er = pd.DataFrame(
                exit_reasons.most_common(), columns=["Raison", "Count"]
            )
            st.dataframe(df_er, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun historique de trade enregistré.")


# ── Auto-refresh ──────────────────────────────────────────────────────────────

st.divider()
now_str = datetime.now().strftime("%H:%M:%S")
st.caption(f"Rafraîchissement automatique dans {REFRESH_SEC}s · {now_str}")
time.sleep(REFRESH_SEC)
st.rerun()
