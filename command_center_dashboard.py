"""
command_center_dashboard.py — Unified Cockpit Dashboard

Tableau de bord temps réel du système de trading autonome.
Rafraîchissement automatique toutes les 30 secondes.

Usage:
    streamlit run command_center_dashboard.py
    streamlit run command_center_dashboard.py -- --port 8502
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Config page ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Crypto AI — Command Center",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

REFRESH_INTERVAL = 30  # secondes

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
/* Global dark override */
.main { background-color: #0a0e1a; }
.block-container { padding-top: 1rem; padding-bottom: 0rem; }

/* Metric cards */
.metric-card {
    background: linear-gradient(135deg, #0d1b2a 0%, #1a2744 100%);
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 16px;
    text-align: center;
    margin-bottom: 8px;
}
.metric-card .label {
    color: #6b8cad;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 4px;
}
.metric-card .value {
    color: #e8f4fd;
    font-size: 22px;
    font-weight: 700;
}
.metric-card .value.green  { color: #00e676; }
.metric-card .value.red    { color: #ff4444; }
.metric-card .value.yellow { color: #ffd600; }
.metric-card .value.orange { color: #ff9100; }
.metric-card .sub {
    color: #6b8cad;
    font-size: 11px;
    margin-top: 4px;
}

/* Override badge */
.override-badge {
    display: inline-block;
    padding: 6px 16px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 1px;
}
.override-CLEAR   { background: #003d1f; color: #00e676; border: 1px solid #00e676; }
.override-REDUCE  { background: #3d2800; color: #ffd600; border: 1px solid #ffd600; }
.override-CAREFUL { background: #3d1600; color: #ff9100; border: 1px solid #ff9100; }
.override-MINIMAL { background: #3d0000; color: #ff6b6b; border: 1px solid #ff6b6b; }
.override-VETO    { background: #1a0000; color: #ff1744; border: 1px solid #ff1744; }

/* Section headers */
.section-header {
    color: #4fc3f7;
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 2px;
    border-bottom: 1px solid #1e3a5f;
    padding-bottom: 6px;
    margin-bottom: 12px;
    margin-top: 4px;
}

/* Event log rows */
.event-row {
    background: #0d1b2a;
    border-left: 3px solid #1e3a5f;
    padding: 6px 10px;
    margin-bottom: 4px;
    border-radius: 0 6px 6px 0;
    font-size: 12px;
    color: #a8c8e8;
}
.event-row.trade  { border-left-color: #00e676; }
.event-row.refused{ border-left-color: #ff9100; }
.event-row.halt   { border-left-color: #ff1744; }
.event-row.regime { border-left-color: #7c4dff; }

/* Position badge */
.pos-long  { color: #00e676; font-weight: 700; }
.pos-short { color: #ff4444; font-weight: 700; }
.pos-flat  { color: #6b8cad; }

/* Alert box */
.alert-box {
    background: #1a0000;
    border: 1px solid #ff1744;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
    color: #ff8a80;
    font-size: 13px;
}
.info-box {
    background: #001428;
    border: 1px solid #0288d1;
    border-radius: 8px;
    padding: 10px;
    color: #80d8ff;
    font-size: 12px;
}

/* Separator */
hr { border-color: #1e3a5f; margin: 8px 0; }

/* Stale data indicator */
.stale { color: #ff9100; font-size: 10px; }
</style>
""",
    unsafe_allow_html=True,
)


# ── Data Loaders ──────────────────────────────────────────────────────────────


@st.cache_data(ttl=REFRESH_INTERVAL)
def _load_jsonl(path: str, limit: int = 200) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        return []
    return rows[-limit:]


@st.cache_data(ttl=REFRESH_INTERVAL)
def _load_json(path: str) -> dict | list | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@st.cache_data(ttl=REFRESH_INTERVAL)
def _load_trade_db(db_path: str, limit: int = 50) -> list[dict]:
    p = Path(db_path)
    if not p.exists():
        return []
    try:
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            return []
        table = tables[0]
        cur.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT {limit}")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def _age_str(ts: float) -> str:
    if not ts:
        return "—"
    age = time.time() - ts
    if age < 60:
        return f"{int(age)}s ago"
    if age < 3600:
        return f"{int(age/60)}m ago"
    return f"{int(age/3600)}h ago"


def _pct_color(v: float) -> str:
    if v > 0:
        return "green"
    if v < -0.01:
        return "red"
    return "yellow"


# ── Derived State ─────────────────────────────────────────────────────────────


def _get_black_box() -> list[dict]:
    return _load_jsonl(os.getenv("BB_PATH", "databases/black_box.jsonl"), 300)


def _get_regrets() -> list[dict]:
    return _load_jsonl(os.getenv("REGRET_DB", "databases/regret_analysis.jsonl"), 100)


def _get_mistakes() -> list[dict]:
    return _load_jsonl(os.getenv("MISTAKE_DB", "databases/mistake_memory.jsonl"), 100)


def _get_trades() -> list[dict]:
    return _load_trade_db(os.getenv("EXEC_TRADE_LOG", "databases/trade_log.sqlite"), 50)


def _get_strategy_memory() -> dict:
    data = _load_json("databases/ai_evolution/strategy_memory.json")
    return data if isinstance(data, dict) else {}


def _get_ranking() -> dict:
    path = os.getenv("RANKER_DB", "databases/strategy_ranking.json")
    data = _load_json(path)
    return data if isinstance(data, dict) else {}


def _get_supervision() -> list[dict]:
    return _load_jsonl("supervision/alerts_audit.jsonl", 50)


# ── Component renderers ───────────────────────────────────────────────────────


def _metric(label: str, value: str, color: str = "", sub: str = "") -> str:
    val_cls = f"value {color}" if color else "value"
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return f"""
<div class="metric-card">
  <div class="label">{label}</div>
  <div class="{val_cls}">{value}</div>
  {sub_html}
</div>"""


def _override_badge(level: str) -> str:
    icons = {
        "CLEAR": "✅",
        "REDUCE": "⚠️",
        "CAREFUL": "🟠",
        "MINIMAL": "🔴",
        "VETO": "🚫",
    }
    icon = icons.get(level, "")
    return f'<span class="override-badge override-{level}">{icon} {level}</span>'


def _render_header() -> None:
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown("# 🎯 Crypto AI — Command Center")
    with col2:
        now = datetime.now().strftime("%H:%M:%S")
        st.markdown(
            f"<div style='text-align:right;color:#6b8cad;padding-top:14px'>🕐 {now}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("🔄 Refresh", width="stretch"):
            st.cache_data.clear()
            st.rerun()


def _render_override_panel(bb_events: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">⚡ Executive Override</div>',
        unsafe_allow_html=True,
    )

    # Fallback: look at last TRADE_REFUSED reasons
    recent_refused = [
        e for e in reversed(bb_events) if e.get("decision_type") == "TRADE_REFUSED"
    ]

    # Try to infer current level from latest system events
    level = "CLEAR"
    for e in reversed(bb_events):
        reason = str(e.get("reason", ""))
        if "VETO" in reason:
            level = "VETO"
            break
        if "MINIMAL" in reason:
            level = "MINIMAL"
            break
        if "CAREFUL" in reason:
            level = "CAREFUL"
            break
        if "REDUCE" in reason:
            level = "REDUCE"
            break

    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown(_override_badge(level), unsafe_allow_html=True)
    with c2:
        factors = {
            "CLEAR": "100%",
            "REDUCE": "50%",
            "CAREFUL": "25%",
            "MINIMAL": "10%",
            "VETO": "0%",
        }
        size_factor = factors.get(level, "—")
        refused_count = len(recent_refused)
        st.markdown(
            f"<div style='color:#a8c8e8;font-size:13px;padding-top:4px'>Taille ordre : <b>{size_factor}</b> &nbsp;|&nbsp; Refus récents : <b>{refused_count}</b></div>",
            unsafe_allow_html=True,
        )


def _render_capital_health(bb_events: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">💰 Capital Health</div>', unsafe_allow_html=True
    )

    executed = [e for e in bb_events if e.get("decision_type") == "TRADE_EXECUTED"]
    closed = [e for e in bb_events if e.get("decision_type") == "POSITION_CLOSED"]

    total_trades = len(executed)
    wins = sum(1 for e in closed if float(e.get("score", 0)) > 0)
    losses = len(closed) - wins
    wr = (wins / len(closed) * 100) if closed else 0.0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            _metric("TRADES EXÉCUTÉS", str(total_trades), sub=f"{len(closed)} fermés"),
            unsafe_allow_html=True,
        )
    with c2:
        color = "green" if wr >= 55 else ("yellow" if wr >= 45 else "red")
        st.markdown(_metric("WIN RATE", f"{wr:.1f}%", color), unsafe_allow_html=True)
    with c3:
        st.markdown(
            _metric(
                "WINS / LOSSES",
                f"{wins} / {losses}",
                "green" if wins >= losses else "red",
            ),
            unsafe_allow_html=True,
        )


def _render_active_positions(bb_events: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">📊 Positions Actives</div>', unsafe_allow_html=True
    )

    opened = {
        e.get("symbol"): e
        for e in bb_events
        if e.get("decision_type") == "TRADE_EXECUTED"
    }
    closed = {
        e.get("symbol")
        for e in bb_events
        if e.get("decision_type") == "POSITION_CLOSED"
    }
    active = {sym: e for sym, e in opened.items() if sym not in closed}

    if not active:
        st.markdown(
            '<div class="info-box">Aucune position ouverte actuellement.</div>',
            unsafe_allow_html=True,
        )
        return

    for sym, e in active.items():
        sig = e.get("signal", "HOLD")
        price = e.get("price", 0)
        score = e.get("score", 0)
        regime = e.get("regime", "—")
        ts = e.get("ts", 0)
        cls = "pos-long" if sig == "BUY" else "pos-short"
        direction = "LONG" if sig == "BUY" else "SHORT"
        st.markdown(
            f'<div class="event-row trade">'
            f'<b>{sym}</b> &nbsp; <span class="{cls}">{direction}</span> &nbsp;|&nbsp; '
            f"Entry ~${price:,.0f} &nbsp;|&nbsp; Score {score} &nbsp;|&nbsp; Régime: {regime} &nbsp;|&nbsp; {_age_str(ts)}"
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_black_box(bb_events: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">📦 Black Box — Dernières Décisions</div>',
        unsafe_allow_html=True,
    )

    icons = {
        "TRADE_EXECUTED": ("trade", "🟢"),
        "TRADE_REFUSED": ("refused", "🟠"),
        "POSITION_CLOSED": ("trade", "🔵"),
        "HALT_TRIGGERED": ("halt", "🔴"),
        "REGIME_CHANGE": ("regime", "🟣"),
        "SYSTEM_EVENT": ("", "⚪"),
    }

    for e in reversed(bb_events[-20:]):
        dt = e.get("decision_type", "EVENT")
        cls, icon = icons.get(dt, ("", "⚪"))
        sym = e.get("symbol", "SYS")
        reason = e.get("reason", "")[:80]
        score = e.get("score")
        ts = e.get("ts", 0)
        score_str = f" · Score {score}" if score is not None else ""
        st.markdown(
            f'<div class="event-row {cls}">'
            f'{icon} <b>{sym}</b> [{dt}]{score_str} — {reason} <span class="stale">{_age_str(ts)}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_mistakes(mistakes: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">🧠 Mistake Memory</div>', unsafe_allow_html=True
    )

    rules = [m for m in mistakes if m.get("type") == "RULE_CREATED"]
    errors = [m for m in mistakes if m.get("type") not in ("RULE_CREATED",)]

    error_types: dict[str, int] = {}
    for e in errors:
        t = e.get("error_type", "UNKNOWN")
        error_types[t] = error_types.get(t, 0) + 1

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            _metric("RÈGLES ACTIVES", str(len(rules)), "yellow" if rules else "green"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _metric("ERREURS ENREGISTRÉES", str(len(errors))), unsafe_allow_html=True
        )

    if error_types:
        st.markdown("**Distribution des erreurs :**")
        for etype, cnt in sorted(error_types.items(), key=lambda x: -x[1])[:5]:
            bar = "█" * min(cnt, 20)
            st.markdown(
                f"<div style='font-size:12px;color:#a8c8e8'>`{etype}` {bar} {cnt}</div>",
                unsafe_allow_html=True,
            )

    if rules:
        st.markdown("**Règles de blocage :**")
        for r in rules[-5:]:
            st.markdown(
                f'<div class="event-row refused">🚫 {r.get("rule_id","?")} — {r.get("reason","")[:80]}</div>',
                unsafe_allow_html=True,
            )


def _render_regrets(regrets: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">😔 Regret Engine</div>', unsafe_allow_html=True
    )

    missed = [r for r in regrets if r.get("outcome") == "MISSED_WIN"]
    correct = [r for r in regrets if r.get("outcome") == "GOOD_REFUSAL"]
    neutral = [r for r in regrets if r.get("outcome") == "NEUTRAL"]

    total = len(missed) + len(correct) + len(neutral)
    acc = (len(correct) / total * 100) if total else 0.0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            _metric("MISSED WIN", str(len(missed)), "red" if missed else "green"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _metric("BON REFUS", str(len(correct)), "green"), unsafe_allow_html=True
        )
    with c3:
        color = "green" if acc >= 60 else ("yellow" if acc >= 40 else "red")
        st.markdown(
            _metric("PRÉCISION REFUS", f"{acc:.1f}%", color), unsafe_allow_html=True
        )

    if missed:
        st.markdown("**Derniers MISSED_WIN :**")
        for r in reversed(missed[-3:]):
            sym = r.get("symbol", "?")
            move = r.get("move_pct", 0) * 100
            val = r.get("regret_value", 0)
            refused_by = r.get("refused_by", [])
            st.markdown(
                f'<div class="event-row refused">💸 {sym} +{move:.2f}% (regret={val:.2f}) — bloqué par: {refused_by}</div>',
                unsafe_allow_html=True,
            )


def _render_strategy_health(ranking: dict) -> None:
    st.markdown(
        '<div class="section-header">🏆 Strategy Ranking</div>', unsafe_allow_html=True
    )

    strategies = ranking.get("strategies", {}) if isinstance(ranking, dict) else {}
    if not strategies:
        st.markdown(
            '<div class="info-box">Pas encore de données de ranking.</div>',
            unsafe_allow_html=True,
        )
        return

    sorted_strats = sorted(
        strategies.items(),
        key=lambda x: x[1].get("composite_score", 0) if isinstance(x[1], dict) else 0,
        reverse=True,
    )

    for name, data in sorted_strats[:5]:
        if not isinstance(data, dict):
            continue
        score = data.get("composite_score", 0)
        wr = data.get("win_rate", 0) * 100
        trades = data.get("total_trades", 0)
        status = data.get("status", "active")
        color = (
            "green"
            if status == "active"
            else ("red" if status == "blacklisted" else "yellow")
        )
        bar = "█" * int(score / 10)
        st.markdown(
            f'<div class="event-row">'
            f'<span style="color:#{_score_hex(score)}">{bar}</span> '
            f"<b>{name}</b> — Score {score:.0f} | WR {wr:.0f}% | {trades} trades | "
            f'<span style="color:{"#00e676" if color=="green" else "#ff4444"}">{status.upper()}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )


def _score_hex(score: float) -> str:
    if score >= 70:
        return "00e676"
    if score >= 50:
        return "ffd600"
    return "ff4444"


def _render_system_health(bb_events: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">🔧 System Health</div>', unsafe_allow_html=True
    )

    halts = [e for e in bb_events if e.get("decision_type") == "HALT_TRIGGERED"]
    sys_events = [e for e in bb_events if e.get("decision_type") == "SYSTEM_EVENT"]
    last_boot = next(
        (
            e
            for e in reversed(sys_events)
            if "DEMARRAGE" in str(e.get("reason", "")).upper()
        ),
        None,
    )
    last_event_ts = bb_events[-1].get("ts", 0) if bb_events else 0

    age = time.time() - last_event_ts if last_event_ts else None
    stale = age is not None and age > 600  # >10 min sans event = stale

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            _metric(
                "HALTS",
                str(len(halts)),
                "red" if halts else "green",
                f"Dernier: {_age_str(halts[-1].get('ts',0)) if halts else 'jamais'}",
            ),
            unsafe_allow_html=True,
        )
    with c2:
        status_color = "red" if stale else "green"
        status_label = "STALE" if stale else "ACTIF"
        st.markdown(
            _metric(
                "SYSTÈME",
                status_label,
                status_color,
                f"Dernier event: {_age_str(last_event_ts)}",
            ),
            unsafe_allow_html=True,
        )
    with c3:
        boot_ts = last_boot.get("ts", 0) if last_boot else 0
        st.markdown(
            _metric("DERNIER BOOT", _age_str(boot_ts) if boot_ts else "—"),
            unsafe_allow_html=True,
        )

    if halts:
        st.markdown(
            '<div class="alert-box">🚨 HALT DÉTECTÉ — vérifier logs/advisor_loop.log</div>',
            unsafe_allow_html=True,
        )


def _render_chief_officer_brief(bb_events: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">🤖 AI Chief Officer — Dernier Brief</div>',
        unsafe_allow_html=True,
    )

    coo_events = [
        e
        for e in bb_events
        if e.get("decision_type") == "SYSTEM_EVENT"
        and "CHIEF" in str(e.get("reason", "")).upper()
    ]

    if not coo_events:
        st.markdown(
            '<div class="info-box">Pas encore de brief du Chief Officer. Il parle tous les 6 cycles.</div>',
            unsafe_allow_html=True,
        )
        return

    last = coo_events[-1]
    ts = last.get("ts", 0)
    text = last.get("reason", "")
    st.markdown(
        f'<div class="event-row" style="border-left-color:#7c4dff;padding:12px">'
        f'<div style="color:#6b8cad;font-size:11px">{_age_str(ts)}</div>'
        f'<div style="color:#e8f4fd;white-space:pre-wrap">{text[:600]}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_supervision_alerts(alerts: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">🚨 Supervision Alerts</div>',
        unsafe_allow_html=True,
    )

    if not alerts:
        st.markdown(
            '<div class="info-box">Aucune alerte supervision.</div>',
            unsafe_allow_html=True,
        )
        return

    for alert in reversed(alerts[-10:]):
        level = str(alert.get("level", "INFO")).upper()
        msg = str(alert.get("message", alert.get("msg", "")))[:120]
        ts = alert.get("ts", alert.get("timestamp", 0))
        color = (
            "#ff4444"
            if level in ("CRITICAL", "ERROR")
            else ("#ffd600" if level == "WARNING" else "#a8c8e8")
        )
        cls = (
            "halt"
            if level in ("CRITICAL", "ERROR")
            else ("refused" if level == "WARNING" else "")
        )
        st.markdown(
            f'<div class="event-row {cls}" style="border-left-color:{color}">'
            f'<b>[{level}]</b> {msg} <span class="stale">{_age_str(float(ts)) if ts else ""}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_trade_history(trades: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">📋 Historique Trades (DB)</div>',
        unsafe_allow_html=True,
    )

    if not trades:
        st.markdown(
            '<div class="info-box">Aucun trade dans la base de données.</div>',
            unsafe_allow_html=True,
        )
        return

    cols = [
        c
        for c in ("symbol", "side", "status", "price", "amount", "pnl", "timestamp")
        if c in (trades[0] if trades else {})
    ]
    if not cols:
        cols = list(trades[0].keys())[:6]

    header = " | ".join(f"<b>{c.upper()}</b>" for c in cols)
    st.markdown(
        f'<div style="font-size:11px;color:#6b8cad;border-bottom:1px solid #1e3a5f;padding-bottom:4px">{header}</div>',
        unsafe_allow_html=True,
    )

    for t in trades[:10]:
        pnl = t.get("pnl", t.get("realized_pnl", None))
        pnl_str = ""
        if pnl is not None:
            try:
                pnl_f = float(pnl)
                color = (
                    "#00e676" if pnl_f > 0 else ("#ff4444" if pnl_f < 0 else "#6b8cad")
                )
                pnl_str = f'<span style="color:{color}">{pnl_f:+.2f}</span>'
            except Exception:
                pnl_str = str(pnl)

        row_parts = []
        for c in cols:
            v = t.get(c, "—")
            if c == "pnl" and pnl_str:
                row_parts.append(pnl_str)
            else:
                row_parts.append(str(v)[:20])

        side = str(t.get("side", "")).upper()
        side_color = (
            "#00e676"
            if side in ("BUY", "LONG")
            else ("#ff4444" if side in ("SELL", "SHORT") else "#a8c8e8")
        )

        st.markdown(
            '<div class="event-row" style="font-size:11px">'
            + " | ".join(
                f'<span style="color:{side_color}">{p}</span>' if c == "side" else p
                for c, p in zip(cols, row_parts)
            )
            + "</div>",
            unsafe_allow_html=True,
        )


def _render_regime_panel(bb_events: list[dict]) -> None:
    st.markdown(
        '<div class="section-header">🌊 Régime de Marché</div>', unsafe_allow_html=True
    )

    regime_events = [e for e in reversed(bb_events) if e.get("regime")]
    regime_counts: dict[str, int] = {}
    for e in regime_events[:50]:
        r = e.get("regime", "unknown")
        regime_counts[r] = regime_counts.get(r, 0) + 1

    current_regime = regime_events[0].get("regime", "—") if regime_events else "—"

    c1, c2 = st.columns(2)
    with c1:
        regime_colors = {
            "bull_trend": "green",
            "bear_trend": "red",
            "sideways": "yellow",
            "high_volatility": "orange",
            "flash_crash": "red",
            "unknown": "",
        }
        color = regime_colors.get(current_regime, "")
        st.markdown(
            _metric("RÉGIME ACTUEL", current_regime.replace("_", " ").upper(), color),
            unsafe_allow_html=True,
        )
    with c2:
        top_regime = max(regime_counts, key=regime_counts.get) if regime_counts else "—"
        st.markdown(
            _metric(
                "RÉGIME DOMINANT (50 derniers)", top_regime.replace("_", " ").upper()
            ),
            unsafe_allow_html=True,
        )


# ── Main Layout ───────────────────────────────────────────────────────────────


def main() -> None:
    _render_header()
    st.markdown("<hr>", unsafe_allow_html=True)

    # Load data
    bb_events = _get_black_box()
    regrets = _get_regrets()
    mistakes = _get_mistakes()
    trades = _get_trades()
    ranking = _get_ranking()
    alerts = _get_supervision()

    if not bb_events:
        st.markdown(
            """
<div class="alert-box">
⚠️ <b>Black Box vide</b> — Le système n'a pas encore enregistré d'événements.<br>
Lancez <code>python advisor_loop.py</code> pour démarrer la collecte de données.
</div>
""",
            unsafe_allow_html=True,
        )

    # ── Ligne 1 : Override + Capital Health ──────────────────────────────────
    col_left, col_right = st.columns([1, 2])
    with col_left:
        _render_override_panel(bb_events)
        st.markdown("<br>", unsafe_allow_html=True)
        _render_regime_panel(bb_events)
    with col_right:
        _render_capital_health(bb_events)
        st.markdown("<br>", unsafe_allow_html=True)
        _render_active_positions(bb_events)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Ligne 2 : Black Box + System Health ──────────────────────────────────
    col_bb, col_sys = st.columns([3, 1])
    with col_bb:
        _render_black_box(bb_events)
    with col_sys:
        _render_system_health(bb_events)
        if alerts:
            st.markdown("<br>", unsafe_allow_html=True)
            _render_supervision_alerts(alerts)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Ligne 3 : Mistakes + Regrets ─────────────────────────────────────────
    col_mm, col_re = st.columns(2)
    with col_mm:
        _render_mistakes(mistakes)
    with col_re:
        _render_regrets(regrets)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Ligne 4 : Chief Officer + Strategy Ranking ───────────────────────────
    col_coo, col_rank = st.columns([2, 1])
    with col_coo:
        _render_chief_officer_brief(bb_events)
    with col_rank:
        _render_strategy_health(ranking)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Ligne 5 : Trade History ───────────────────────────────────────────────
    _render_trade_history(trades)

    # ── Auto-refresh ─────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="text-align:center;color:#2a4060;font-size:11px;margin-top:20px">'
        f"Auto-refresh toutes les {REFRESH_INTERVAL}s · "
        f"{len(bb_events)} événements Black Box · "
        f"{len(mistakes)} erreurs enregistrées · "
        f"{len(regrets)} candidats regret"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Streamlit auto-rerun via fragment or sleep
    time.sleep(REFRESH_INTERVAL)
    st.rerun()


if __name__ == "__main__":
    main()
