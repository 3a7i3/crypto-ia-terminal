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

from dashboard.colors import C, css_inject

# ── Config ────────────────────────────────────────────────────────────────────

BASE = Path(__file__).parent
BLACK_BOX = BASE / "databases" / "black_box.jsonl"
CYCLE_DATA = BASE / "databases" / "cycle_data.jsonl"
SNAPSHOT = BASE / "databases" / "live_snapshot.json"
TRADES = BASE / "logs" / "trades.jsonl"

REFRESH_SEC = 20
ACCENT = "#00e0ff"  # unique couleur d'action — signaux actionnables seulement

# Aliases (backslash interdit dans expression f-string avant Python 3.12)
_TEXT_MUTED = C["text"]["muted"]
_TEXT_SEC = C["text"]["secondary"]
_TEXT_PRI = C["text"]["primary"]
_BG_CARD = C["background"]["card"]
_BG_BORDER = C["background"]["border"]
_COL_OK = C["status"]["ok"]
_COL_WARN = C["status"]["warning"]
_COL_ERR = C["status"]["error"]

st.set_page_config(
    page_title="Crypto AI — Master Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

css_inject()
st.markdown(
    f"""
<style>
/* ── Base ── */
.stApp {{ background: {C["background"]["dark"]}; }}
.block-container {{ padding-top: 0.8rem; padding-bottom: 1rem; }}

/* ── Metrics ── */
div[data-testid="metric-container"] {{
    background: {_BG_CARD};
    border: 1px solid {_BG_BORDER};
    border-radius: 8px;
    padding: 10px 14px;
}}

/* ── Module cards ── */
.mod-card {{
    background: {_BG_CARD};
    border-left: 3px solid {_BG_BORDER};
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 0.78rem;
    margin-bottom: 4px;
}}

/* ── Signal badges ── */
.sig-badge {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 3px;
    font-size: 0.7rem;
    font-weight: 700;
    font-family: monospace;
    letter-spacing: 0.05em;
    vertical-align: middle;
}}

/* ── Indicator chips ── */
.chip {{
    display: inline-block;
    padding: 1px 7px;
    border-radius: 3px;
    font-size: 0.67rem;
    font-weight: 600;
    font-family: monospace;
    margin: 1px 2px;
    vertical-align: middle;
}}

/* ── Symbol row ── */
.sym-row {{
    background: {_BG_CARD};
    border: 1px solid {_BG_BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    margin-bottom: 5px;
    line-height: 1.8;
}}

/* ── Compact symbol row ── */
.sym-compact {{
    background: {_BG_CARD};
    border: 1px solid {_BG_BORDER};
    border-radius: 5px;
    padding: 5px 10px;
    margin-bottom: 3px;
}}

/* ── Status text ── */
.status-ok  {{ color: {_COL_OK};   font-weight: 700; }}
.status-warn{{ color: {_COL_WARN}; font-weight: 700; }}
.status-err {{ color: {_COL_ERR};  font-weight: 700; }}

/* ── Verdict bar ── */
.verdict-bar {{
    border-radius: 6px;
    padding: 0.55rem 1rem;
    margin-bottom: 0.7rem;
    font-weight: 600;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("**⚙ Affichage**")
    COMPACT = st.toggle("Mode compact", value=False)
    st.caption("Masque les graphiques secondaires.")

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


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ── Visual helpers ────────────────────────────────────────────────────────────


def sig_badge(label: str, kind: str) -> str:
    """Badge HTML inline — kind: trade | watch | hold | block | setup"""
    palette = {
        "trade": (ACCENT, "#0a0c12"),
        "setup": (ACCENT, "#0a0c12"),
        "watch": (_COL_WARN, "#0a0c12"),
        "hold": (_BG_BORDER, _TEXT_SEC),
        "block": (_COL_ERR, "#fff"),
    }
    bg, fg = palette.get(kind, palette["hold"])
    return f'<span class="sig-badge" style="background:{bg};color:{fg};">{label}</span>'


def market_state(s: dict) -> tuple[str, str, str]:
    """
    Retourne (glyph, label, color) selon le régime + état du signal.
    Glyphs sobres, pas d'emojis voyants.
    """
    regime = s.get("regime", "")
    score = s.get("score", 0)
    gate_ok = s.get("gate_allowed", True)
    if not gate_ok:
        return "⛔", "Blocked", _COL_ERR
    if regime == "TREND_BULL" and score >= 70:
        return "⚡", "Setup", ACCENT
    if regime == "TREND_BULL":
        return "↗", "Bull", _COL_OK
    if regime == "TREND_BEAR" and score >= 70:
        return "↘", "Short", _COL_ERR
    if regime == "TREND_BEAR":
        return "↘", "Bear", _COL_ERR
    if regime == "VOLATILE":
        return "⏳", "Watch", _COL_WARN
    if score >= 50:
        return "⏳", "Watch", _COL_WARN
    return "●", "Hold", _TEXT_MUTED


def ind_chip(label: str, value: str, state: str) -> str:
    """
    Chip d'indicateur — state: ok | warn | alert | neutral
    Couleurs sobres : fond foncé + texte coloré, pas de néon.
    """
    bg_fg = {
        "ok": ("#0f2d1a", _COL_OK),
        "warn": ("#2d1e04", _COL_WARN),
        "alert": ("#2d0a0a", _COL_ERR),
        "neutral": (_BG_CARD, _TEXT_SEC),
    }
    bg, fg = bg_fg.get(state, bg_fg["neutral"])
    return (
        f'<span class="chip" style="background:{bg};color:{fg};">'
        f"{label}&nbsp;<b>{value}</b></span>"
    )


def rsi_chip(rsi) -> str:
    if rsi is None:
        return ind_chip("RSI", "—", "neutral")
    v = f"{rsi:.0f}"
    if rsi > 70:
        return ind_chip("RSI", v + " ⚠", "alert")
    if rsi < 30:
        return ind_chip("RSI", v + " ✓", "ok")
    return ind_chip("RSI", v, "neutral")


def bb_chip(bb) -> str:
    if bb is None:
        return ind_chip("BB%", "—", "neutral")
    v = f"{bb:.2f}"
    if bb > 0.9:
        return ind_chip("BB%", v, "warn")
    if bb < 0.1:
        return ind_chip("BB%", v, "ok")
    return ind_chip("BB%", v, "neutral")


def bool_chip(label: str, val: bool, invert: bool = False) -> str:
    positive = val if not invert else not val
    if val is None:
        return ind_chip(label, "—", "neutral")
    return ind_chip(label, "OK" if val else "—", "ok" if positive else "neutral")


def compute_coherence(decisions: list[dict]) -> list[dict]:
    executions = [d for d in decisions if d.get("decision_type") == "TRADE_EXECUTED"]
    closures = [d for d in decisions if d.get("decision_type") == "POSITION_CLOSED"]
    closures_by_sym: dict[str, list[dict]] = {}
    for c in closures:
        closures_by_sym.setdefault(c.get("symbol", ""), []).append(c)

    results = []
    for ex in executions:
        sym = ex.get("symbol", "")
        ex_ts = ex.get("ts", 0)
        score = ex.get("score", 0)
        candidates = [c for c in closures_by_sym.get(sym, []) if c.get("ts", 0) > ex_ts]
        if not candidates:
            continue
        cl = min(candidates, key=lambda c: c["ts"] - ex_ts)
        pnl_pct = cl.get("pnl_pct", 0.0)
        win = pnl_pct > 0
        hc = score >= 70
        label = (
            "VALIDATED"
            if hc and win
            else (
                "LUCKY"
                if not hc and win
                else "UNLUCKY" if hc and not win else "MISTAKE"
            )
        )
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


# ── Header ────────────────────────────────────────────────────────────────────

hcol, rcol = st.columns([5, 1])
with hcol:
    st.markdown("## Crypto AI — Master Dashboard")
with rcol:
    st.markdown(
        f"<small style='color:{_TEXT_MUTED}'>auto {REFRESH_SEC}s</small>",
        unsafe_allow_html=True,
    )
    if st.button("↻ Rafraîchir"):
        st.cache_data.clear()
        st.rerun()

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "↗  Vue Globale",
        "● Marchés Live",
        "⚡ Analyse Décisions",
        "■  Positions",
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
        c1.metric("Capital", f"${capital:,.2f}")
        c2.metric("Cycle", cycle)
        c3.metric("Durée cycle", f"{snap.get('cycle_duration_ms', 0):.0f} ms")
        c4.metric("Latence exchange", f"{exch.get('last_latency_ms', 0):.0f} ms")
        c5.metric("Uptime exchange", f"{exch.get('uptime_pct', 0):.1f}%")
        c6.metric("Safe Mode", "OUI ⚠" if safe else "NON")

        n_sym = snap.get("n_symbols", 0)
        n_act = snap.get("n_actionable", 0)
        n_trd = snap.get("n_traded", 0)
        n_ref = snap.get("n_refused", 0)
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Symboles analysés", n_sym)
        d2.metric("Signaux actionnables", n_act)
        d3.metric("Trades exécutés", n_trd)
        d4.metric("Refusés", n_ref)

        st.caption(f"Dernière mise à jour : {ts_str} | Cycle #{cycle}")

        exch_ok = exch.get("healthy", False)
        exch_color = _COL_OK if exch_ok else _COL_ERR
        exch_label = "↗ Connecté" if exch_ok else "⛔ Déconnecté"
        st.markdown(
            f"**Exchange** : <span style='color:{exch_color};font-weight:700'>{exch_label}</span>"
            f"  —  Échecs : {exch.get('consecutive_failures', 0)}"
            f"  —  Checks : {exch.get('total_checks', 0)}",
            unsafe_allow_html=True,
        )
        if exch.get("last_error"):
            with st.expander("Dernière erreur exchange"):
                st.code(exch["last_error"], language=None)

        col_rb, col_rd = st.columns(2)
        with col_rb:
            rb = snap.get("refusal_breakdown", {})
            if rb:
                st.markdown("**Couches de refus — cycle courant**")
                st.dataframe(
                    pd.DataFrame(rb.items(), columns=["Couche", "Refus"]),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.markdown("Aucun signal bloqué ce cycle.")
        with col_rd:
            rd = snap.get("regime_distribution", {})
            if rd:
                st.markdown("**Régimes détectés ce cycle**")
                st.dataframe(
                    pd.DataFrame(rd.items(), columns=["Régime", "Symboles"]),
                    width="stretch",
                    hide_index=True,
                )
    else:
        st.warning("Snapshot live introuvable — le bot tourne-t-il ?")

    st.divider()

    # Modules status grid
    st.markdown("**Modules système**")
    MODULES = [
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
            color, tag = _COL_ERR, "absent"
        elif min_bytes > 0 and p.stat().st_size < min_bytes:
            color, tag = _COL_WARN, "vide"
        else:
            color, tag = _COL_OK, "OK"
        cols[i % 4].markdown(
            f"<div class='mod-card' style='border-left-color:{color}'>"
            f"<span style='color:{color};font-size:0.62rem;font-weight:700'>{tag.upper()}</span>"
            f"<br><span style='color:{_TEXT_PRI}'>{name}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    if cycles:
        df_cyc = (
            pd.DataFrame(
                [
                    {
                        "cycle": r.get("cycle"),
                        "capital": r.get("capital"),
                        "duration_ms": r.get("cycle_duration_ms"),
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
                st.markdown("**Capital (150 derniers cycles)**")
                st.line_chart(df_cyc.set_index("cycle")["capital"], height=175)
            with ch_dur:
                st.markdown("**Durée cycle ms**")
                df_dur = df_cyc.dropna(subset=["duration_ms"])
                if not df_dur.empty:
                    st.line_chart(df_dur.set_index("cycle")["duration_ms"], height=175)
                else:
                    st.info("Durée non encore enregistrée.")

        if not COMPACT:
            bb_snap = [r for r in cycles if r.get("refusal_breakdown")]
            if bb_snap:
                st.markdown("**Refus cumulés par couche (depuis démarrage)**")
                total_ref: dict[str, int] = {}
                for r in bb_snap:
                    for layer, cnt in r["refusal_breakdown"].items():
                        total_ref[layer] = total_ref.get(layer, 0) + cnt
                df_tot = pd.DataFrame(
                    sorted(total_ref.items(), key=lambda x: -x[1]),
                    columns=["Couche", "Refus totaux"],
                )
                st.bar_chart(df_tot.set_index("Couche"), height=190)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Marchés Live
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    snap = load_snapshot()
    symbols = snap.get("symbols", [])

    if symbols:
        st.markdown(f"**Signaux live — Cycle #{snap.get('cycle', '—')}**")

        # Tableau principal avec colonne Market State
        rows = []
        for s in symbols:
            score = s.get("score", 0)
            rsi = s.get("rsi")
            bb = s.get("bb_pct")
            atr = s.get("atr_ratio")
            g, lbl, _ = market_state(s)
            rows.append(
                {
                    "Symbole": s.get("symbol", ""),
                    "State": f"{g} {lbl}",
                    "Prix": f"${s.get('prix', 0):,.4f}",
                    "Score": score,
                    "Conviction": s.get("conviction_level", ""),
                    "Régime": s.get("regime", ""),
                    "RSI": f"{rsi:.1f}" if rsi is not None else "—",
                    "BB%": f"{bb:.2f}" if bb is not None else "—",
                    "ATR%": f"{atr*100:.2f}%" if atr is not None else "—",
                    "MACD": "OK" if s.get("macd_bullish") else "—",
                    "EMA": "OK" if s.get("ema_bullish") else "—",
                    "Squeeze": "ON" if s.get("bb_squeeze") else "OFF",
                    "Gate": "✓" if s.get("gate_allowed") else "⛔",
                    "Trade": "✓" if s.get("trade_allowed") else "—",
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        st.markdown("**Détail par symbole**")

        if COMPACT:
            # Mode compact : 3 colonnes — badge state + barre
            cols = st.columns(3)
            for i, s in enumerate(symbols):
                score = s.get("score", 0)
                g, lbl, gcolor = market_state(s)
                if score >= 70:
                    bkind = "trade"
                elif score >= 50:
                    bkind = "watch"
                else:
                    bkind = "hold"
                with cols[i % 3]:
                    st.markdown(
                        f"<div class='sym-compact'>"
                        f"{sig_badge(f'{g} {lbl}', bkind)} "
                        f"<b style='font-size:0.82rem'>{s.get('symbol','')}</b> "
                        f"<span style='color:{_TEXT_MUTED};font-size:0.72rem'>{score}/100</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.progress(min(score / 100, 1.0))
        else:
            # Mode complet : row avec badges d'indicateurs
            for s in symbols:
                score = s.get("score", 0)
                rsi = s.get("rsi")
                bb = s.get("bb_pct")
                atr = s.get("atr_ratio")
                g, lbl, gcolor = market_state(s)

                if score >= 70:
                    sbadge = sig_badge("⚡ TRADE", "trade")
                elif score >= 50:
                    sbadge = sig_badge("⏳ WATCH", "watch")
                else:
                    sbadge = sig_badge("● HOLD", "hold")

                atr_str = f"{atr*100:.2f}%" if atr is not None else "—"
                chips = "".join(
                    [
                        rsi_chip(rsi),
                        bb_chip(bb),
                        ind_chip("ATR", atr_str, "neutral"),
                        bool_chip("MACD", s.get("macd_bullish")),
                        bool_chip("EMA", s.get("ema_bullish")),
                        ind_chip(
                            "Squeeze",
                            "ON" if s.get("bb_squeeze") else "OFF",
                            "warn" if s.get("bb_squeeze") else "neutral",
                        ),
                    ]
                )

                st.markdown(
                    f"<div class='sym-row'>"
                    f"<span style='color:{gcolor};font-weight:700;font-size:0.85rem'>{g}</span> "
                    f"<b style='font-size:0.9rem'>{s.get('symbol','')}</b> &nbsp;"
                    f"{sbadge} &nbsp;"
                    f"<span style='color:{_TEXT_SEC};font-size:0.8rem'>{score}/100</span>"
                    f"<br>{chips}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.progress(min(score / 100, 1.0))

        # ── Mini graphe repliable ─────────────────────────────────────────────
        st.divider()
        with st.expander(
            "◎ Mini graphe live — Score / PnL / Exposition", expanded=False
        ):
            chart_mode = st.radio(
                "Afficher :",
                ["Score signal", "PnL cumulé", "Exposition"],
                horizontal=True,
                label_visibility="collapsed",
            )
            if chart_mode == "Score signal":
                # Score par symbole sur les N derniers cycles du black_box
                bb_rec = load_jsonl(BLACK_BOX, max_lines=2000)
                score_by_cycle: dict[str, list] = {}
                for d in bb_rec:
                    sym = d.get("symbol", "?")
                    cyc = d.get("cycle")
                    sc = d.get("score")
                    if cyc and sc is not None:
                        score_by_cycle.setdefault(sym, []).append(
                            {"cycle": cyc, "score": sc}
                        )
                if score_by_cycle:
                    dfs = []
                    for sym, pts in score_by_cycle.items():
                        df_s = (
                            pd.DataFrame(pts)
                            .groupby("cycle")["score"]
                            .mean()
                            .rename(sym)
                        )
                        dfs.append(df_s)
                    df_sc = pd.concat(dfs, axis=1).sort_index().tail(60)
                    st.line_chart(df_sc, height=160)
                    st.caption("Score moyen par cycle — seuil 70 = déclenchement trade")
                else:
                    st.info("Pas encore de données de score.")

            elif chart_mode == "PnL cumulé":
                trades_raw = load_jsonl(TRADES, max_lines=500)
                exits = [r for r in trades_raw if r.get("type") == "exit"]
                if exits:
                    cum, rows_pnl = 0.0, []
                    for e in exits:
                        cum += e.get("pnl_usd", 0)
                        rows_pnl.append(
                            {"trade": len(rows_pnl) + 1, "PnL $": round(cum, 4)}
                        )
                    st.line_chart(pd.DataFrame(rows_pnl).set_index("trade"), height=160)
                else:
                    st.info("Aucun trade fermé enregistré.")

            else:  # Exposition
                open_pos = snap.get("positions", [])
                if open_pos:
                    df_exp = pd.DataFrame(open_pos)
                    exp_cols = [
                        c
                        for c in ["symbol", "size", "notional_usd"]
                        if c in df_exp.columns
                    ]
                    if exp_cols:
                        st.dataframe(df_exp[exp_cols], width="stretch", hide_index=True)
                    else:
                        st.dataframe(df_exp, width="stretch", hide_index=True)
                else:
                    st.info("Aucune position ouverte — exposition nulle.")

    else:
        cycles_data = load_jsonl(CYCLE_DATA, max_lines=10)
        if cycles_data:
            last = cycles_data[-1]
            ts_last = fmt_ts(last.get("ts", 0))
            st.info(f"Snapshot vide — dernier cycle #{last.get('cycle')} à {ts_last}")
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
            verdict, detail = (
                "COHÉRENT — marché sans tendance, refus massifs justifiés",
                f"Score moyen {avg_score:.1f}/100 < seuil 70.",
            )
            vcolor = _COL_OK
        elif avg_score >= 50 and holds_pct > 95:
            verdict, detail = (
                "À SURVEILLER — scores corrects mais aucun trade",
                f"Score moyen {avg_score:.1f}/100. Vérifier les couches de refus.",
            )
            vcolor = _COL_WARN
        elif holds_pct < 50:
            verdict, detail = (
                "TRADING ACTIF",
                f"{100-holds_pct:.1f}% des décisions ont mené à un trade.",
            )
            vcolor = ACCENT
        else:
            verdict, detail = (
                "EN OBSERVATION",
                f"Score moyen {avg_score:.1f}/100, {holds_pct:.1f}% HOLD.",
            )
            vcolor = _TEXT_MUTED

        st.markdown(
            f"<div class='verdict-bar' style='border-left:4px solid {vcolor};"
            f"background:{_BG_CARD}'>"
            f"<span style='color:{vcolor}'>{verdict}</span>"
            f"<br><span style='color:{_TEXT_SEC};font-size:0.82rem'>{detail}</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"{len(decisions):,} décisions · {n_cycles_seen} cycles · "
            f"dernier cycle #{last_cyc} à {last_ts} · score max {max_score}/100"
        )

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
        c3.metric("Trades exécutés", f"{trades:,}")
        c4.metric("Positions fermées", closed)
        c5.metric("Refus explicites", refused)

        st.divider()

        # Distribution des scores — graphique le plus utile, conservé
        if scores:
            st.markdown("**Distribution des scores de signal**")
            hist = pd.DataFrame({"score": scores})["score"].value_counts().sort_index()
            st.bar_chart(hist, height=190)
            st.caption(f"Moyenne {avg_score:.1f} · Max {max_score} · Min {min(scores)}")

        # Tableaux compacts (régimes / conviction+personnalité) — pas de bar charts
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("**Régimes**")
            regimes = Counter(d.get("regime", "unknown") for d in decisions)
            st.dataframe(
                pd.DataFrame(regimes.most_common(), columns=["Régime", "Count"]),
                width="stretch",
                hide_index=True,
                height=175,
            )
        with col_r:
            st.markdown("**Conviction · Personnalité**")
            convs = Counter(d.get("conviction_level", "—") for d in decisions)
            persos = Counter(d.get("personality", "—") for d in decisions)
            df_cp = pd.DataFrame(
                [
                    {"Type": "conviction", "Valeur": k, "Count": v}
                    for k, v in convs.most_common(5)
                ]
                + [
                    {"Type": "personality", "Valeur": k, "Count": v}
                    for k, v in persos.most_common(5)
                ]
            )
            st.dataframe(df_cp, width="stretch", hide_index=True, height=175)

        if not COMPACT:
            st.divider()
            st.markdown("**Évolution du score par cycle**")
            score_by_cycle: dict[str, list] = {}
            for d in decisions:
                sym = d.get("symbol", "?")
                cyc = d.get("cycle")
                sc = d.get("score")
                if cyc and sc is not None:
                    score_by_cycle.setdefault(sym, []).append(
                        {"cycle": cyc, "score": sc}
                    )
            if score_by_cycle:
                dfs = []
                for sym, pts in score_by_cycle.items():
                    df_s = (
                        pd.DataFrame(pts).groupby("cycle")["score"].mean().rename(sym)
                    )
                    dfs.append(df_s)
                st.line_chart(pd.concat(dfs, axis=1).sort_index().tail(100), height=210)
                st.caption("Seuil mental à 70 = déclenchement trade")

        st.divider()
        st.markdown("**Raisons de refus — top modules**")
        all_refused_by: list[str] = []
        for d in decisions:
            all_refused_by.extend(d.get("refused_by", []))
        if all_refused_by:
            cnt = Counter(all_refused_by)
            st.dataframe(
                pd.DataFrame(cnt.most_common(15), columns=["Raison", "Occurrences"]),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("Aucun refus enregistré.")

        if not COMPACT:
            st.divider()
            st.markdown("**Modules qui valident (passed_by)**")
            all_passed: list[str] = []
            for d in decisions:
                all_passed.extend(d.get("passed_by", []))
            if all_passed:
                cnt2 = Counter(all_passed)
                st.dataframe(
                    pd.DataFrame(
                        cnt2.most_common(10), columns=["Module", "Validations"]
                    ),
                    width="stretch",
                    hide_index=True,
                )

        # ── Cohérence Signal → Résultat ──────────────────────────────────────
        st.divider()
        st.markdown("**Cohérence Signal → Résultat (post-mortem automatique)**")

        coherence = compute_coherence(decisions)
        if not coherence:
            st.info(
                "Pas encore de trades fermés à analyser — "
                "s'affiche dès la première clôture de position."
            )
        else:
            cnt_labels = Counter(r["label"] for r in coherence)
            total_coh = len(coherence)

            cc1, cc2, cc3, cc4, cc5 = st.columns(5)
            cc1.metric("Trades analysés", total_coh)
            cc2.metric(
                "VALIDATED",
                cnt_labels.get("VALIDATED", 0),
                f"{100*cnt_labels.get('VALIDATED',0)//total_coh}%",
            )
            cc3.metric(
                "LUCKY",
                cnt_labels.get("LUCKY", 0),
                f"{100*cnt_labels.get('LUCKY',0)//total_coh}%",
            )
            cc4.metric(
                "UNLUCKY",
                cnt_labels.get("UNLUCKY", 0),
                f"{100*cnt_labels.get('UNLUCKY',0)//total_coh}%",
            )
            cc5.metric(
                "MISTAKE",
                cnt_labels.get("MISTAKE", 0),
                f"{100*cnt_labels.get('MISTAKE',0)//total_coh}%",
            )

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
                cv, cc = (
                    f"MODÈLE COHÉRENT — {validated_pct:.0f}% trades haute conviction gagnants",
                    _COL_OK,
                )
            elif mistake_pct >= 40:
                cv, cc = (
                    f"MODÈLE INCOHÉRENT — {mistake_pct:.0f}% MISTAKE (score élevé + perte)",
                    _COL_ERR,
                )
            elif win_rate_high > win_rate_low + 10:
                cv, cc = (
                    f"SIGNAL UTILE — WR score≥70 : {win_rate_high:.0f}% vs <70 : {win_rate_low:.0f}%",
                    _COL_WARN,
                )
            else:
                cv, cc = (
                    f"SIGNAL NEUTRE — WR similaire ({win_rate_high:.0f}% vs {win_rate_low:.0f}%)",
                    _TEXT_MUTED,
                )

            st.markdown(
                f"<div class='verdict-bar' style='border-left:4px solid {cc};background:{_BG_CARD}'>"
                f"<span style='color:{cc}'>{cv}</span></div>",
                unsafe_allow_html=True,
            )

            wr1, wr2 = st.columns(2)
            wr1.metric(
                "Win rate score ≥ 70 (haute conviction)", f"{win_rate_high:.1f}%"
            )
            wr2.metric("Win rate score < 70 (basse conviction)", f"{win_rate_low:.1f}%")

            with st.expander("Détail trade par trade"):
                df_coh = pd.DataFrame(coherence).sort_values(
                    "entry_ts", ascending=False
                )
                st.dataframe(df_coh, width="stretch", hide_index=True)

        st.divider()
        st.markdown("**50 dernières décisions**")
        recent = decisions[-50:][::-1]
        rows_dec = []
        for d in recent:
            rows_dec.append(
                {
                    "Heure": fmt_ts(d.get("ts", 0)),
                    "Symbole": d.get("symbol", ""),
                    "Décision": d.get("decision_type", ""),
                    "Score": d.get("score", ""),
                    "Régime": d.get("regime", ""),
                    "Conviction": d.get("conviction_level", ""),
                    "Prix": f"${d.get('price', 0):,.4f}" if d.get("price") else "—",
                    "Raison": (d.get("reason") or "")[:60],
                }
            )
        st.dataframe(pd.DataFrame(rows_dec), width="stretch", hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Positions
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    snap = load_snapshot()
    open_positions = snap.get("positions", [])

    st.markdown("**Positions ouvertes**")
    if open_positions:
        st.dataframe(pd.DataFrame(open_positions), width="stretch", hide_index=True)
    else:
        st.info("Aucune position ouverte.")

    st.divider()
    st.markdown("**Historique des positions fermées**")

    trades_raw = load_jsonl(TRADES, max_lines=1000)
    entries = {r["id"]: r for r in trades_raw if r.get("type") == "entry"}
    exits = [r for r in trades_raw if r.get("type") == "exit"]

    if exits:
        rows_hist = []
        for ex in reversed(exits[-100:]):
            tid = ex.get("id", "")
            win = ex.get("win")
            pnl_pct = ex.get("pnl_pct", 0) * 100
            pnl_usd = ex.get("pnl_usd", 0)

            # Régime badge
            regime_map = {
                "TREND_BULL": "↗ Bull",
                "TREND_BEAR": "↘ Bear",
                "RANGE": "● Range",
                "VOLATILE": "⏳ Vol",
                "UNKNOWN": "— ?",
            }
            regime_str = regime_map.get(ex.get("regime", ""), ex.get("regime", "—"))

            rows_hist.append(
                {
                    "Symbole": ex.get("symbol", ""),
                    "Résultat": "Win" if win else "Loss",
                    "PnL %": f"+{pnl_pct:.2f}%" if pnl_pct > 0 else f"{pnl_pct:.2f}%",
                    "PnL $": (
                        f"+${pnl_usd:.4f}" if pnl_usd > 0 else f"-${abs(pnl_usd):.4f}"
                    ),
                    "Régime": regime_str,
                    "Conviction": ex.get("confidence", ex.get("conviction_level", "—")),
                    "Direction": ex.get("direction", ""),
                    "Entrée": f"${ex.get('entry_price', 0):.4f}",
                    "Sortie": f"${ex.get('exit_price', 0):.4f}",
                    "Durée (min)": f"{ex.get('duration_min', 0):.1f}",
                    "Raison sortie": ex.get("exit_reason", ""),
                    "Paper": "📄" if ex.get("paper") else "–",
                    "Date": ex.get("logged_at", "")[:16],
                }
            )

        df_hist = pd.DataFrame(rows_hist)
        st.dataframe(df_hist, width="stretch", hide_index=True)

        st.divider()

        wins = sum(1 for e in exits if e.get("win"))
        total_pnl = sum(e.get("pnl_usd", 0) for e in exits)
        avg_pnl = total_pnl / len(exits) if exits else 0
        pnl_pcts = [e.get("pnl_pct", 0) for e in exits]
        best = max(pnl_pcts) * 100 if pnl_pcts else 0
        worst = min(pnl_pcts) * 100 if pnl_pcts else 0

        st.markdown("**Performance globale**")

        pnl_sign = "+" if total_pnl >= 0 else ""
        pnl_color = _COL_OK if total_pnl >= 0 else _COL_ERR

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total trades", len(exits))
        c2.metric("Win Rate", f"{100*wins//len(exits)}%" if exits else "—")
        c3.metric("PnL total", f"{pnl_sign}${total_pnl:.2f}")
        c4.metric("PnL moyen / trade", f"${avg_pnl:.2f}")
        c5.metric("Meilleur trade", f"+{best:.2f}%")
        c6.metric("Pire trade", f"{worst:.2f}%")

        # Courbe PnL cumulé — vert si positif, rouge si perte (positifs confirmés only)
        pnl_cumul, cum = [], 0.0
        for e in exits:
            cum += e.get("pnl_usd", 0)
            pnl_cumul.append({"trade": len(pnl_cumul) + 1, "PnL $": round(cum, 4)})
        df_pnl = pd.DataFrame(pnl_cumul).set_index("trade")
        st.markdown("**PnL cumulé ($)**")
        st.line_chart(df_pnl["PnL $"], height=175)

        if not COMPACT:
            exit_reasons = Counter(e.get("exit_reason", "?")[:30] for e in exits)
            if exit_reasons:
                st.markdown("**Raisons de sortie**")
                st.dataframe(
                    pd.DataFrame(
                        exit_reasons.most_common(), columns=["Raison", "Count"]
                    ),
                    width="stretch",
                    hide_index=True,
                )
    else:
        st.info("Aucun historique de trade enregistré.")


# ── Auto-refresh ──────────────────────────────────────────────────────────────

st.divider()
st.caption(
    f"Rafraîchissement dans {REFRESH_SEC}s · {datetime.now().strftime('%H:%M:%S')}"
)
time.sleep(REFRESH_SEC)
st.rerun()
