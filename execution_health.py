"""
execution_health.py — Tableau de bord santé d'exécution (P2 Operational Closure).

Tabs :
  1. Audit P2 Live       — ordres validés/rejetés, slippage simulé, latence, fees
  2. Trades Historiques  — PnL cumulé, win rate, régime, breakdown
  3. Pipeline & Rejections — rejections signal, latence pipeline, raisons

Sources :
  logs/execution_audit/audit.jsonl   (nouveau P2 — se remplit en live)
  logs/trades.jsonl                  (historique paper/live)
  logs/decisions/*.jsonl             (rejections pipeline)

Usage :
    streamlit run execution_health.py
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from dashboard.colors import C, css_inject

    _has_colors = True
except Exception:
    _has_colors = False
    C = {
        "background": {"dark": "#0f172a", "card": "#1e293b", "border": "#334155"},
        "text": {"primary": "#f1f5f9", "secondary": "#94a3b8", "muted": "#64748b"},
        "status": {
            "ok": "#22c55e",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "neutral": "#64748b",
        },
    }

BASE = Path(__file__).parent
AUDIT_LOG = BASE / "logs" / "execution_audit" / "audit.jsonl"
TRADES_LOG = BASE / "logs" / "trades.jsonl"
DECISIONS_DIR = BASE / "logs" / "decisions"
DECISIONS_LOG = BASE / "logs" / "decisions.jsonl"

REFRESH_SEC = 20

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Execution Health",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if _has_colors:
    css_inject()

_OK = C["status"]["ok"]
_WARN = C["status"]["warning"]
_ERR = C["status"]["error"]
_NEU = C["status"]["neutral"]
_CARD = C["background"]["card"]
_BORDER = C["background"]["border"]
_PRI = C["text"]["primary"]
_SEC = C["text"]["secondary"]
_MUT = C["text"]["muted"]

st.markdown(
    f"""
<style>
.stApp {{ background: {C["background"]["dark"]}; }}
.block-container {{ padding-top: 0.8rem; padding-bottom: 1rem; }}
div[data-testid="metric-container"] {{
    background: {_CARD};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 10px 14px;
}}
.eh-badge-ok {{ background: {_OK}22; color: {_OK}; border: 1px solid {_OK}55;
    border-radius: 4px; padding: 1px 7px; font-size: 0.72rem; font-weight: 600; }}
.eh-badge-err {{ background: {_ERR}22; color: {_ERR}; border: 1px solid {_ERR}55;
    border-radius: 4px; padding: 1px 7px; font-size: 0.72rem; font-weight: 600; }}
.eh-badge-warn {{ background: {_WARN}22; color: {_WARN}; border: 1px solid {_WARN}55;
    border-radius: 4px; padding: 1px 7px; font-size: 0.72rem; font-weight: 600; }}
.eh-empty {{ color: {_MUT}; font-size: 0.85rem; padding: 24px 0; text-align: center; }}
</style>
""",
    unsafe_allow_html=True,
)

# ── Loaders ───────────────────────────────────────────────────────────────────


@st.cache_data(ttl=REFRESH_SEC)
def load_audit(max_lines: int = 2000) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    rows = []
    with open(AUDIT_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows[-max_lines:]


@st.cache_data(ttl=REFRESH_SEC)
def load_trades(max_lines: int = 5000) -> list[dict]:
    if not TRADES_LOG.exists():
        return []
    rows = []
    with open(TRADES_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows[-max_lines:]


@st.cache_data(ttl=REFRESH_SEC)
def load_decisions(max_lines: int = 3000) -> list[dict]:
    rows = []
    sources = list(DECISIONS_DIR.glob("*.jsonl")) if DECISIONS_DIR.exists() else []
    if DECISIONS_LOG.exists():
        sources.append(DECISIONS_LOG)
    for src in sorted(sources):
        with open(src, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows[-max_lines:]


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(
    f"<h2 style='color:{_PRI};margin-bottom:0'>⚙️ Execution Health</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<p style='color:{_MUT};font-size:0.8rem;margin-top:2px'>P2 Operational — validation · rate limiter · simulation · audit</p>",
    unsafe_allow_html=True,
)

# Auto-refresh notice
col_h1, col_h2 = st.columns([8, 2])
with col_h2:
    st.caption(f"Auto-refresh {REFRESH_SEC}s")
    if st.button("↻ Refresh", width="stretch"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "⚡ Audit P2 Live",
        "📊 Trades Historiques",
        "🚫 Pipeline & Rejections",
        "🛡️ Robustness GO/NO-GO",
    ]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Audit P2 Live
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    audit_rows = load_audit()

    if not audit_rows:
        st.markdown(
            f"""
<div style='background:{_CARD};border:1px solid {_BORDER};border-radius:8px;padding:32px;text-align:center;margin-top:16px'>
  <div style='font-size:2rem'>⏳</div>
  <div style='color:{_PRI};font-size:1rem;margin-top:8px'>En attente de données live</div>
  <div style='color:{_MUT};font-size:0.82rem;margin-top:6px'>
    Le fichier <code>logs/execution_audit/audit.jsonl</code> sera créé<br>
    dès que l'advisor exécutera son premier ordre avec le code P2.
  </div>
  <div style='color:{_SEC};font-size:0.78rem;margin-top:12px'>
    Lancer : <code>python advisor_loop.py</code>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        # KPI row
        validated = [r for r in audit_rows if r.get("validated", True)]
        rejected = [r for r in audit_rows if not r.get("validated", True)]
        has_sim = [r for r in audit_rows if r.get("simulated_fill")]

        slip_vals = [
            r["simulated_fill"]["slippage_bps"]
            for r in has_sim
            if r.get("simulated_fill", {}).get("slippage_bps") is not None
        ]
        lat_vals = [
            r["simulated_fill"]["latency_ms"]
            for r in has_sim
            if r.get("simulated_fill", {}).get("latency_ms") is not None
        ]
        fee_vals = [
            r["simulated_fill"]["fee_usd"]
            for r in has_sim
            if r.get("simulated_fill", {}).get("fee_usd") is not None
        ]

        rej_ratio = len(rejected) / len(audit_rows) * 100 if audit_rows else 0
        avg_slip = sum(slip_vals) / len(slip_vals) if slip_vals else 0
        avg_lat = sum(lat_vals) / len(lat_vals) if lat_vals else 0
        total_fee = sum(fee_vals)

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Ordres tentés", len(audit_rows))
        k2.metric(
            "Validés",
            len(validated),
            delta=f"-{len(rejected)} rejetés" if rejected else None,
            delta_color="inverse",
        )
        k3.metric("Rejection rate", f"{rej_ratio:.1f}%", delta_color="inverse")
        k4.metric("Slippage moyen", f"{avg_slip:.2f} bps")
        k5.metric("Latence simulée", f"{avg_lat:.0f} ms")

        st.markdown(
            f"**Fees totaux simulés** : `${total_fee:.4f}` USD sur {len(audit_rows)} ordres"
        )

        st.markdown("---")

        # Table audit
        rows_table = []
        for r in reversed(audit_rows[-200:]):
            sf = r.get("simulated_fill", {})
            ts = r.get("ts", 0)
            dt_str = (
                datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")
                if ts
                else "?"
            )
            rows_table.append(
                {
                    "Heure (UTC)": dt_str,
                    "Symbole": r.get("symbol", "?"),
                    "Side": r.get("side", "?").upper(),
                    "Size USD": f"${r.get('intent', {}).get('size_usd', 0):.2f}",
                    "Prix": f"${r.get('intent', {}).get('price', 0):,.2f}",
                    "Validé": "✅" if r.get("validated", True) else "❌",
                    "Slippage bps": f"{sf.get('slippage_bps', 0):.2f}" if sf else "—",
                    "Latence ms": f"{sf.get('latency_ms', 0):.0f}" if sf else "—",
                    "Fee USD": f"${sf.get('fee_usd', 0):.4f}" if sf else "—",
                    "Partial": "⚠" if sf.get("is_partial") else "—",
                }
            )
        df_audit = pd.DataFrame(rows_table)
        st.dataframe(df_audit, width="stretch", hide_index=True)

        # Slippage distribution
        if slip_vals:
            st.markdown("**Distribution slippage simulé (bps)**")
            df_slip = pd.DataFrame({"slippage_bps": slip_vals})
            st.bar_chart(df_slip["slippage_bps"].value_counts().sort_index())

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Trades Historiques
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    all_trades = load_trades()
    exits = [t for t in all_trades if t.get("type") == "exit"]

    if not exits:
        st.markdown(
            f"<div class='eh-empty'>Aucun trade de sortie dans logs/trades.jsonl</div>",
            unsafe_allow_html=True,
        )
    else:
        wins = [t for t in exits if t.get("win")]
        total = len(exits)
        win_rate = len(wins) / total * 100 if total else 0
        pnl_vals = [t.get("pnl_pct", 0) for t in exits]
        pnl_usd_vals = [t.get("pnl_usd", 0) for t in exits]
        avg_pnl = sum(pnl_vals) / len(pnl_vals) if pnl_vals else 0
        total_pnl_usd = sum(pnl_usd_vals)
        avg_dur = (
            sum(t.get("duration_min", t.get("duration_minutes", 0)) for t in exits)
            / total
            if total
            else 0
        )

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total trades", total)
        k2.metric("Win Rate", f"{win_rate:.1f}%")
        k3.metric("PnL moyen", f"{avg_pnl:+.3f}%")
        k4.metric("PnL total USD", f"${total_pnl_usd:+.2f}")
        k5.metric("Durée moyenne", f"{avg_dur:.1f} min")

        st.markdown("---")

        # PnL cumulé chart
        pnl_series = pd.Series(pnl_vals).cumsum()
        st.markdown("**PnL cumulé (%)**")
        st.line_chart(pnl_series)

        # Breakdown par régime
        col_r, col_s = st.columns(2)

        with col_r:
            st.markdown("**Win rate par régime**")
            regime_stats: dict[str, dict] = {}
            for t in exits:
                reg = t.get("regime", "unknown")
                if reg not in regime_stats:
                    regime_stats[reg] = {"n": 0, "wins": 0, "pnl": 0.0}
                regime_stats[reg]["n"] += 1
                regime_stats[reg]["wins"] += int(bool(t.get("win")))
                regime_stats[reg]["pnl"] += t.get("pnl_pct", 0)
            reg_rows = [
                {
                    "Régime": reg,
                    "Trades": v["n"],
                    "Win%": f"{v['wins']/v['n']*100:.1f}%",
                    "PnL moy%": f"{v['pnl']/v['n']:+.3f}%",
                }
                for reg, v in sorted(regime_stats.items(), key=lambda x: -x[1]["n"])
            ]
            st.dataframe(pd.DataFrame(reg_rows), width="stretch", hide_index=True)

        with col_s:
            st.markdown("**Top 5 meilleures sorties**")
            top5 = sorted(exits, key=lambda t: t.get("pnl_pct", 0), reverse=True)[:5]
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Symbole": t.get("symbol", "?"),
                            "PnL%": f"{t.get('pnl_pct', 0):+.3f}%",
                            "Durée": f"{t.get('duration_min', t.get('duration_minutes', 0)):.1f}m",
                            "Régime": t.get("regime", "?"),
                        }
                        for t in top5
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

        st.markdown("---")

        # Table complète (50 derniers)
        st.markdown("**50 derniers trades**")
        table_rows = []
        for t in exits[-50:]:
            pnl = t.get("pnl_pct", 0)
            table_rows.append(
                {
                    "Date": t.get("logged_at", t.get("timestamp", "?"))[:19],
                    "Symbole": t.get("symbol", "?"),
                    "Side": t.get("side", "?"),
                    "Entry": f"${t.get('entry_price', 0):,.2f}",
                    "Exit": f"${t.get('exit_price', 0):,.2f}",
                    "PnL%": f"{pnl:+.3f}%",
                    "PnL$": f"${t.get('pnl_usd', 0):+.4f}",
                    "Win": "✅" if t.get("win") else "❌",
                    "Régime": t.get("regime", "?"),
                    "Paper": "📄" if t.get("paper") else "🟢",
                    "Raison sortie": t.get("exit_reason", "?"),
                }
            )
        st.dataframe(pd.DataFrame(table_rows), width="stretch", hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Pipeline & Rejections
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    dec_rows = load_decisions()

    rejections = [
        r
        for r in dec_rows
        if r.get("event") == "signal_rejected"
        or (isinstance(r.get("action"), str) and "STOP" in r.get("action", ""))
    ]
    pipeline_rows = [
        r for r in dec_rows if r.get("event") in ("signal_received", "signal_rejected")
    ]

    # KPIs
    k1, k2, k3 = st.columns(3)
    k1.metric("Évènements pipeline", len(pipeline_rows))
    k2.metric("Signaux rejetés", len(rejections))

    pipeline_ms_vals = []
    for r in pipeline_rows:
        ctx = r.get("context", {})
        ms = ctx.get("pipeline_ms")
        if ms is not None:
            try:
                pipeline_ms_vals.append(float(ms))
            except Exception:
                pass
    avg_pipeline = (
        sum(pipeline_ms_vals) / len(pipeline_ms_vals) if pipeline_ms_vals else 0
    )
    k3.metric("Latence pipeline moy.", f"{avg_pipeline:.1f} ms")

    st.markdown("---")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Raisons de rejet**")
        reasons: list[str] = []
        for r in rejections:
            ctx = r.get("context", {})
            reasons.append(ctx.get("reason", r.get("reason", "unknown")))
        if reasons:
            counts = Counter(reasons)
            df_rej = pd.DataFrame(
                [{"Raison": k, "Count": v} for k, v in counts.most_common(15)]
            )
            st.dataframe(df_rej, width="stretch", hide_index=True)
        else:
            st.markdown(
                f"<div class='eh-empty'>Aucun rejet enregistré</div>",
                unsafe_allow_html=True,
            )

    with col_b:
        st.markdown("**Latence pipeline (ms)**")
        if pipeline_ms_vals:
            import statistics as _stats

            p50 = _stats.median(pipeline_ms_vals)
            p95 = (
                sorted(pipeline_ms_vals)[int(len(pipeline_ms_vals) * 0.95)]
                if len(pipeline_ms_vals) >= 20
                else max(pipeline_ms_vals)
            )
            p_max = max(pipeline_ms_vals)
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Percentile": "P50 (médiane)", "ms": f"{p50:.1f}"},
                        {"Percentile": "P95", "ms": f"{p95:.1f}"},
                        {"Percentile": "Max", "ms": f"{p_max:.1f}"},
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
            st.bar_chart(pd.Series(pipeline_ms_vals[:500], name="pipeline_ms"))
        else:
            st.markdown(
                f"<div class='eh-empty'>Pas de données pipeline_ms</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("**50 derniers évènements rejet**")
    if rejections:
        rej_table = []
        for r in rejections[-50:]:
            ctx = r.get("context", {})
            ts = r.get("timestamp", "?")[:19]
            rej_table.append(
                {
                    "Timestamp": ts,
                    "Symbole": ctx.get("symbol", r.get("symbol", "?")),
                    "Side": ctx.get("side", "?"),
                    "Raison": ctx.get("reason", r.get("reason", "?")),
                    "Détail": str(ctx.get("detail", ""))[:60],
                    "Pipeline ms": f"{ctx.get('pipeline_ms', '?')}",
                }
            )
        st.dataframe(pd.DataFrame(rej_table), width="stretch", hide_index=True)
    else:
        st.markdown(
            f"<div class='eh-empty'>Aucun rejet dans les logs chargés</div>",
            unsafe_allow_html=True,
        )

    # Décisions advisor_loop
    st.markdown("---")
    st.markdown("**Décisions système (REDUCE_RISK / STOP_TRADING)**")
    sys_dec = [
        r
        for r in dec_rows
        if r.get("action") in ("REDUCE_RISK", "STOP_TRADING", "INCREASE_RISK")
    ]
    if sys_dec:
        sys_rows = [
            {
                "Timestamp": r.get("timestamp", "?")[:19],
                "Action": r.get("action", "?"),
                "Raison": r.get("reason", "?")[:70],
                "Confiance": f"{r.get('confidence', 0):.0%}",
                "Exécuté": "✅" if r.get("executed") else "❌",
            }
            for r in sys_dec[-30:]
        ]
        st.dataframe(pd.DataFrame(sys_rows), width="stretch", hide_index=True)
    else:
        st.markdown(
            f"<div class='eh-empty'>Aucune décision système enregistrée</div>",
            unsafe_allow_html=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Robustness GO/NO-GO
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    try:
        from metrics.robustness import RobustnessReport, robustness_report
        from risk_limits import HARD_LIMITS, limits_summary

        _rob_available = True
    except Exception as _re:
        _rob_available = False
        st.error(f"metrics/robustness.py non disponible: {_re}")

    if _rob_available:
        exits_rob = [t for t in load_trades() if t.get("type") == "exit"]
        n = len(exits_rob)

        # ── Calcul des inputs depuis les trades existants ─────────────────────
        if n >= 5:
            pnl_vals = [t.get("pnl_pct", 0) for t in exits_rob]
            wins_rob = [p for p in pnl_vals if p > 0]
            losses_rob = [p for p in pnl_vals if p < 0]

            win_rate_pct = len(wins_rob) / n * 100.0
            avg_win = sum(wins_rob) / len(wins_rob) if wins_rob else 0.01
            avg_loss = abs(sum(losses_rob) / len(losses_rob)) if losses_rob else 0.01

            # Sharpe OOS simplifié sur les pnl_pct
            import statistics as _st

            mean_pnl = sum(pnl_vals) / n
            std_pnl = _st.stdev(pnl_vals) if n > 1 else 1.0
            sharpe_est = (mean_pnl / std_pnl * (252**0.5)) if std_pnl > 0 else 0.0

            # Drawdown sur courbe cumulative
            curve = []
            eq = 0.0
            peak = 0.0
            max_dd = 0.0
            for p in pnl_vals:
                eq += p
                peak = max(peak, eq)
                dd = eq - peak
                max_dd = min(max_dd, dd)

            report = robustness_report(
                sharpe=round(sharpe_est, 3),
                max_drawdown_pct=round(max_dd, 2),
                win_rate_pct=round(win_rate_pct, 1),
                n_trades=n,
                avg_win_pct=round(avg_win, 3),
                avg_loss_pct=round(avg_loss, 3),
                capital_usd=10_000.0,
                bet_size_usd=500.0,
            )

            # ── GO / NO-GO banner ─────────────────────────────────────────────
            is_go = report.go_no_go == "GO"
            banner_color = _OK if is_go else _ERR
            banner_text = (
                "✅  GO — Critères P5 validés"
                if is_go
                else "🔴  NO-GO — Critères insuffisants"
            )
            st.markdown(
                f"""
<div style='background:{banner_color}22;border:2px solid {banner_color};border-radius:10px;
padding:20px 28px;text-align:center;margin-bottom:20px'>
  <div style='font-size:1.6rem;color:{banner_color};font-weight:700'>{banner_text}</div>
  <div style='color:{_SEC};font-size:0.82rem;margin-top:6px'>
    Survival Score : <b style='color:{_PRI}'>{report.survival_score:.1f}/100</b>
    &nbsp;·&nbsp;
    Ruin Probability : <b style='color:{_PRI}'>{report.ruin_probability:.1%}</b>
    &nbsp;·&nbsp;
    Basé sur <b style='color:{_PRI}'>{n}</b> trades
  </div>
</div>
""",
                unsafe_allow_html=True,
            )

            # ── KPI row ───────────────────────────────────────────────────────
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric(
                "Survival Score",
                f"{report.survival_score:.1f}/100",
                delta="≥60 requis",
                delta_color="off",
            )
            k2.metric(
                "Sharpe OOS",
                f"{report.sharpe:.3f}",
                delta="≥0.3 requis",
                delta_color="off",
            )
            k3.metric(
                "Max Drawdown",
                f"{report.max_drawdown_pct:.1f}%",
                delta="≤25% requis",
                delta_color="off",
            )
            k4.metric(
                "Win Rate",
                f"{report.win_rate_pct:.1f}%",
                delta="≥45% cible",
                delta_color="off",
            )
            k5.metric(
                "Ruin Probability",
                f"{report.ruin_probability:.1%}",
                delta="≤10% requis",
                delta_color="off",
            )

            st.markdown("---")

            col_r, col_l = st.columns(2)

            # ── Raisons GO/NO-GO ─────────────────────────────────────────────
            with col_r:
                st.markdown("**Critères de validation**")
                if report.reasons:
                    for reason in report.reasons:
                        color = (
                            _ERR
                            if reason.startswith("survival")
                            or ">" in reason
                            or "<" in reason
                            else _WARN
                        )
                        st.markdown(
                            f"<div style='background:{color}22;border-left:3px solid {color};"
                            f"border-radius:4px;padding:6px 12px;margin:4px 0;"
                            f"font-size:0.82rem;color:{_PRI}'>{reason}</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown(
                        f"<div style='background:{_OK}22;border-left:3px solid {_OK};"
                        f"border-radius:4px;padding:6px 12px;font-size:0.82rem;color:{_PRI}'>"
                        f"Tous les critères satisfaits</div>",
                        unsafe_allow_html=True,
                    )

            # ── Inputs du modèle ──────────────────────────────────────────────
            with col_l:
                st.markdown("**Inputs du modèle de robustesse**")
                inputs = [
                    ("Avg gain/trade", f"{avg_win:.3f}%"),
                    ("Avg perte/trade", f"{avg_loss:.3f}%"),
                    (
                        "Profit factor",
                        f"{(avg_win * len(wins_rob)) / max(avg_loss * len(losses_rob), 0.001):.2f}",
                    ),
                    ("Capital modélisé", "$10 000"),
                    ("Taille mise", "$500"),
                    ("Seuil ruine", "−50% capital"),
                ]
                st.dataframe(
                    pd.DataFrame(inputs, columns=["Paramètre", "Valeur"]),
                    width="stretch",
                    hide_index=True,
                )

            st.markdown("---")

            # ── Hard limits actives ───────────────────────────────────────────
            st.markdown("**Hard limits actives (`risk_limits.py` — immuables)**")
            lims = limits_summary()
            lim_rows = [
                {
                    "Limite": "Max ordre USD",
                    "Valeur": f"${lims['max_order_usd']:.0f}",
                    "Type": "HARD",
                },
                {
                    "Limite": "Max ordre % capital",
                    "Valeur": f"{lims['max_order_pct_capital']:.0f}%",
                    "Type": "HARD",
                },
                {
                    "Limite": "Max positions ouvertes",
                    "Valeur": str(lims["max_open_positions"]),
                    "Type": "HARD",
                },
                {
                    "Limite": "Drawdown arrêt total",
                    "Valeur": f"{lims['max_drawdown_pct']:.0f}%",
                    "Type": "HARD",
                },
                {
                    "Limite": "Drawdown pause trading",
                    "Valeur": f"{lims['pause_drawdown_pct']:.0f}%",
                    "Type": "HARD",
                },
                {
                    "Limite": "Capital minimum",
                    "Valeur": f"${lims['min_capital_usd']:.0f}",
                    "Type": "HARD",
                },
                {
                    "Limite": "Exposition max / symbole",
                    "Valeur": f"{lims['max_symbol_exposure_pct']:.0f}%",
                    "Type": "HARD",
                },
                {
                    "Limite": "Levier maximum",
                    "Valeur": f"{lims['max_leverage']}x",
                    "Type": "HARD",
                },
                {
                    "Limite": "Pertes consécutives max",
                    "Valeur": str(lims["max_consecutive_losses"]),
                    "Type": "HARD",
                },
            ]
            df_lims = pd.DataFrame(lim_rows)
            st.dataframe(df_lims, width="stretch", hide_index=True)

            # ── Évolution survival score dans le temps ────────────────────────
            st.markdown("---")
            st.markdown("**Évolution survival score (fenêtres glissantes 20 trades)**")
            if n >= 20:
                from metrics.robustness import ruin_probability as _rp
                from metrics.robustness import survival_score as _ss

                scores = []
                for i in range(20, n + 1, max(1, (n - 20) // 30)):
                    window = pnl_vals[:i]
                    w_wins = [p for p in window if p > 0]
                    w_losses = [p for p in window if p < 0]
                    w_wr = len(w_wins) / len(window) * 100
                    w_aw = sum(w_wins) / len(w_wins) if w_wins else 0.01
                    w_al = abs(sum(w_losses) / len(w_losses)) if w_losses else 0.01
                    w_std = _st.stdev(window) if len(window) > 1 else 1.0
                    w_sharpe = (
                        (sum(window) / len(window) / w_std * (252**0.5))
                        if w_std > 0
                        else 0
                    )
                    w_ruin = _rp(w_wr / 100, w_aw, w_al, 10_000, 500)
                    w_dd = min(
                        0.0,
                        (
                            min(
                                sum(window[:j])
                                - max(sum(window[:k]) for k in range(1, j + 1))
                                for j in range(1, len(window) + 1)
                            )
                            if len(window) > 0
                            else 0
                        ),
                    )
                    score = _ss(w_sharpe, w_dd, w_wr, w_ruin)
                    scores.append({"trade": i, "survival_score": score})
                if scores:
                    df_scores = pd.DataFrame(scores).set_index("trade")
                    st.line_chart(df_scores["survival_score"])
            else:
                st.caption(
                    f"Minimum 20 trades requis pour l'évolution — {n} disponibles actuellement."
                )

        else:
            st.markdown(
                f"""
<div style='background:{_CARD};border:1px solid {_BORDER};border-radius:8px;
padding:32px;text-align:center;margin-top:16px'>
  <div style='font-size:2rem'>📊</div>
  <div style='color:{_PRI};font-size:1rem;margin-top:8px'>Données insuffisantes</div>
  <div style='color:{_MUT};font-size:0.82rem;margin-top:6px'>
    Minimum <b>5 trades fermés</b> requis pour calculer le robustness score.<br>
    Actuellement : <b>{n}</b> trade(s) dans logs/trades.jsonl
  </div>
</div>
""",
                unsafe_allow_html=True,
            )

            # Affiche quand même les hard limits
            try:
                from risk_limits import limits_summary

                st.markdown("---")
                st.markdown("**Hard limits actives (indépendantes des données)**")
                lims = limits_summary()
                st.json(lims)
            except Exception:
                pass

# ── Auto-refresh ──────────────────────────────────────────────────────────────

st.divider()
st.caption(
    f"⚙️ Execution Health | Refresh {REFRESH_SEC}s | Source: logs/execution_audit · logs/trades · logs/decisions · metrics/robustness"
)

import time as _time

_time.sleep(REFRESH_SEC)
st.rerun()
