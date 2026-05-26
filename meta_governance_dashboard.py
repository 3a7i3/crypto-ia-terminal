"""
meta_governance_dashboard.py — P9 Meta Governance Dashboard

Affiche en temps réel l'état des 6 composants de surveillance P9 :
  • SystemHealthMonitor  — composants GREEN/YELLOW/RED
  • BehavioralDriftDetector — dérive comportementale
  • SelfMonitoringLoop   — meta_health_score + alertes niveau 2
  • AnomalyGovernance    — suspensions actives, entropie
  • PerformanceSupervisor — Sharpe glissant, Profit Factor, Drawdown
  • PortfolioIntelligence — concentration exchange/stratégie, exposition nette

Source : databases/live_snapshot.json (clé "p9") — écrit par advisor_loop.py

Usage :
    streamlit run meta_governance_dashboard.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="P9 Meta Governance",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

REFRESH_INTERVAL = 15  # secondes
SNAPSHOT_PATH = Path("databases/live_snapshot.json")

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
.main { background-color: #070b14; }
.block-container { padding-top: 0.8rem; padding-bottom: 0.5rem; }

.section-header {
    color: #4fc3f7;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 2px;
    border-bottom: 1px solid #1a2744;
    padding-bottom: 5px;
    margin-bottom: 10px;
    margin-top: 2px;
}

.kpi-card {
    background: linear-gradient(135deg, #0d1b2a 0%, #111e35 100%);
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 14px 12px;
    text-align: center;
    margin-bottom: 8px;
}
.kpi-label {
    color: #5a7fa0;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 4px;
}
.kpi-value { font-size: 22px; font-weight: 700; color: #e8f4fd; }
.kpi-value.green  { color: #00e676; }
.kpi-value.yellow { color: #ffd600; }
.kpi-value.red    { color: #ff4444; }
.kpi-value.orange { color: #ff9100; }
.kpi-sub { color: #5a7fa0; font-size: 10px; margin-top: 3px; }

.status-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.badge-green  { background: #003d1f; color: #00e676; border: 1px solid #00c853; }
.badge-yellow { background: #3d2800; color: #ffd600; border: 1px solid #ffc400; }
.badge-red    { background: #3d0000; color: #ff5252; border: 1px solid #ff1744; }
.badge-blue   { background: #002244; color: #80d8ff; border: 1px solid #0288d1; }
.badge-grey   { background: #1a1a2e; color: #607d8b; border: 1px solid #37474f; }

.comp-row {
    display: flex;
    align-items: center;
    padding: 5px 8px;
    margin-bottom: 3px;
    border-radius: 6px;
    background: #0d1b2a;
    font-size: 12px;
}
.comp-name { flex: 1; color: #a8c8e8; }
.comp-status { margin-left: 8px; }

.alert-box {
    background: #1a0000;
    border: 1px solid #ff1744;
    border-radius: 6px;
    padding: 8px 12px;
    margin-bottom: 6px;
    color: #ff8a80;
    font-size: 12px;
}
.warn-box {
    background: #1a1000;
    border: 1px solid #ff9100;
    border-radius: 6px;
    padding: 8px 12px;
    margin-bottom: 6px;
    color: #ffcc80;
    font-size: 12px;
}
.ok-box {
    background: #001a0a;
    border: 1px solid #00c853;
    border-radius: 6px;
    padding: 8px 12px;
    color: #a5d6a7;
    font-size: 12px;
}

.suspension-tag {
    background: #2a0000;
    border: 1px solid #b71c1c;
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 11px;
    color: #ef9a9a;
    margin-right: 4px;
    display: inline-block;
    margin-bottom: 4px;
}

hr { border-color: #1a2744; margin: 8px 0; }
</style>
""",
    unsafe_allow_html=True,
)


# ── Data loader ───────────────────────────────────────────────────────────────


@st.cache_data(ttl=REFRESH_INTERVAL)
def _load_snapshot() -> dict | None:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _p9(snap: dict | None) -> dict:
    if snap is None:
        return {}
    return snap.get("p9", {})


# ── HTML helpers ──────────────────────────────────────────────────────────────


def _kpi(label: str, value: str, css_class: str = "", sub: str = "") -> str:
    val_cls = f"kpi-value {css_class}".strip()
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="{val_cls}">{value}</div>'
        f"{sub_html}"
        f"</div>"
    )


def _badge(text: str, color: str = "blue") -> str:
    return f'<span class="status-badge badge-{color}">{text}</span>'


def _score_color(score: float) -> str:
    if score >= 0.75:
        return "green"
    if score >= 0.50:
        return "yellow"
    return "red"


def _age_str(ts: float | None) -> str:
    if not ts:
        return "—"
    age = time.time() - ts
    if age < 60:
        return f"{int(age)}s ago"
    if age < 3600:
        return f"{int(age / 60)}m ago"
    return f"{int(age / 3600)}h ago"


# ── Header ────────────────────────────────────────────────────────────────────

snap = _load_snapshot()
p9 = _p9(snap)

ts = snap.get("ts") if snap else None
cycle = snap.get("cycle", 0) if snap else 0
data_age = _age_str(ts)
stale = (time.time() - ts) > 120 if ts else True

col_title, col_refresh = st.columns([5, 1])
with col_title:
    ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "--:--:--"
    stale_tag = (
        " &nbsp;<span style='color:#ff9100;font-size:11px;'>STALE</span>"
        if stale
        else ""
    )
    st.markdown(
        f"<h2 style='color:#4fc3f7;margin:0;font-size:20px;'>🧠 P9 — Meta Governance"
        f"&nbsp;&nbsp;<span style='color:#5a7fa0;font-size:13px;font-weight:400;'>"
        f"cycle={cycle} &nbsp;·&nbsp; {ts_str} ({data_age}){stale_tag}</span></h2>",
        unsafe_allow_html=True,
    )
with col_refresh:
    st.button("⟳ Refresh", on_click=st.cache_data.clear)

if not snap or not p9:
    st.markdown(
        '<div class="warn-box">⚠ Aucune donnée P9 disponible — advisor_loop.py '
        "n'a pas encore écrit le snapshot.<br>"
        "Lancez le bot ou attendez le prochain cycle.</div>",
        unsafe_allow_html=True,
    )
    st.stop()

st.markdown("<hr>", unsafe_allow_html=True)

# ── Row 1 : Meta health KPIs ──────────────────────────────────────────────────

st.markdown(
    '<div class="section-header">Score Meta Governance</div>', unsafe_allow_html=True
)

meta = p9.get("meta", {})
meta_score = meta.get("meta_health_score", 1.0)
level2_total = meta.get("level2_alerts_total", 0)
level2_active = meta.get("last_level2_alert", False)

perf = p9.get("performance", {})
sharpe20 = perf.get("sharpe_20", 0.0)
pf = perf.get("profit_factor", 0.0)
dd = perf.get("max_drawdown", 0.0)
trade_count = perf.get("trade_count", 0)

gov = p9.get("governance", {})
suspensions_active = gov.get("active_suspensions", 0)
crisis_count = gov.get("crisis_count", 0)
entropy = gov.get("governance_entropy", 1.0)

port = p9.get("portfolio", {})
net_expo = port.get("net_exposure", 0.0)
pos_count = port.get("position_count", 0)
total_usd = port.get("total_usd", 0.0)
port_alerts = port.get("active_alerts", 0)

c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    meta_pct = f"{meta_score:.0%}"
    meta_color = _score_color(meta_score)
    level2_badge = " 🔴" if level2_active else ""
    st.markdown(
        _kpi(
            "Meta Health Score",
            meta_pct + level2_badge,
            meta_color,
            f"L2 alerts total: {level2_total}",
        ),
        unsafe_allow_html=True,
    )

with c2:
    sh_color = "green" if sharpe20 >= 0.5 else ("yellow" if sharpe20 >= 0 else "red")
    st.markdown(
        _kpi(
            "Sharpe (20)",
            f"{sharpe20:.2f}",
            sh_color,
            f"{trade_count} trades · PF={pf:.2f}",
        ),
        unsafe_allow_html=True,
    )

with c3:
    dd_pct = dd * 100
    dd_color = "green" if dd_pct < 10 else ("yellow" if dd_pct < 15 else "red")
    st.markdown(
        _kpi("Max Drawdown", f"{dd_pct:.1f}%", dd_color, "fenêtre 100 trades"),
        unsafe_allow_html=True,
    )

with c4:
    susp_color = "green" if suspensions_active == 0 else "red"
    st.markdown(
        _kpi(
            "Suspensions",
            str(suspensions_active),
            susp_color,
            f"{crisis_count} crises · H={entropy:.2f}",
        ),
        unsafe_allow_html=True,
    )

with c5:
    expo_abs = abs(net_expo)
    expo_dir = "LONG" if net_expo > 0 else ("SHORT" if net_expo < 0 else "FLAT")
    expo_color = "green" if expo_abs < 0.5 else ("yellow" if expo_abs < 0.8 else "red")
    st.markdown(
        _kpi(
            "Exposition nette",
            f"{expo_dir} {expo_abs:.0%}",
            expo_color,
            f"{pos_count} pos · ${total_usd:,.0f}",
        ),
        unsafe_allow_html=True,
    )

with c6:
    port_color = "green" if port_alerts == 0 else "red"
    st.markdown(
        _kpi(
            "Alertes Portfolio",
            str(port_alerts),
            port_color,
            "exchange + stratégie",
        ),
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Row 2 : Composants + Drift ────────────────────────────────────────────────

col_health, col_drift = st.columns([1, 1])

with col_health:
    st.markdown(
        '<div class="section-header">Composants Système</div>', unsafe_allow_html=True
    )
    health = p9.get("health", {})

    _STATUS_MAP = {
        "GREEN": ("green", "GREEN"),
        "YELLOW": ("yellow", "YELLOW"),
        "RED": ("red", "RED"),
        "ok": ("green", "OK"),
        "warning": ("yellow", "WARN"),
        "error": ("red", "ERR"),
        "healthy": ("green", "SAIN"),
        "degraded": ("yellow", "DÉGRADÉ"),
        "critical": ("red", "CRITIQUE"),
    }

    # SHM summary keys: overall, components (count), GREEN, YELLOW, RED
    overall_raw = str(health.get("overall", "GREEN"))
    o_color, o_label = _STATUS_MAP.get(overall_raw, ("blue", overall_raw))
    components_count = health.get("components", "—")
    yellow_count = health.get("YELLOW", 0)
    red_count = health.get("RED", 0)

    st.markdown(
        f'<div class="comp-row">'
        f'<span class="comp-name" style="font-weight:700;">Santé globale</span>'
        f'<span class="comp-status">{_badge(o_label, o_color)}</span>'
        f"</div>"
        f'<div style="color:#5a7fa0;font-size:11px;padding:4px 8px;">'
        f"{components_count} composants · "
        f"{yellow_count} YELLOW · {red_count} RED"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Components détail si disponible
    comp_detail = health.get("components", {})
    if comp_detail:
        for cname, cdata in list(comp_detail.items())[:8]:
            if isinstance(cdata, dict):
                status_raw = str(cdata.get("status", "GREEN"))
                c_color, c_label = _STATUS_MAP.get(status_raw, ("blue", status_raw))
                latency = cdata.get("avg_latency_ms", None)
                lat_str = f" · {latency:.0f}ms" if latency is not None else ""
                st.markdown(
                    f'<div class="comp-row">'
                    f'<span class="comp-name">{cname}</span>'
                    f'<span style="color:#5a7fa0;font-size:10px;">{lat_str}</span>'
                    f'<span class="comp-status">{_badge(c_label, c_color)}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
    else:
        st.markdown(
            '<div style="color:#5a7fa0;font-size:11px;padding:4px 8px;">'
            "Détail composants non disponible dans ce cycle.</div>",
            unsafe_allow_html=True,
        )

with col_drift:
    st.markdown(
        '<div class="section-header">Dérive Comportementale (BDD)</div>',
        unsafe_allow_html=True,
    )
    drift = p9.get("drift", {})

    drifting = drift.get("drifting", False)
    drift_score = drift.get("drift_score", 0.0)
    alert_freq = drift.get("alert_frequency", 0.0)
    total_alerts = drift.get("total_alerts", 0)
    drift_dims = drift.get("drift_dimensions", [])

    if drifting:
        st.markdown(
            f'<div class="alert-box">🚨 <b>DÉRIVE DÉTECTÉE</b> '
            f"— score={drift_score:.2f} · freq={alert_freq:.2f}/10c</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="ok-box">✅ Comportement stable '
            f"— score={drift_score:.2f} · freq={alert_freq:.2f}/10c</div>",
            unsafe_allow_html=True,
        )

    if drift_dims:
        st.markdown(
            '<div style="color:#a8c8e8;font-size:11px;margin-top:6px;margin-bottom:4px;">'
            "Dimensions en dérive :</div>",
            unsafe_allow_html=True,
        )
        for dim in drift_dims:
            st.markdown(
                f'<div class="comp-row"><span class="comp-name">{dim}</span>'
                f'{_badge("DRIFT", "red")}</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        f'<div style="color:#5a7fa0;font-size:11px;padding:4px 8px;">'
        f"Total alertes dérive : {total_alerts}</div>",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Row 3 : Governance + Performance ─────────────────────────────────────────

col_gov, col_perf = st.columns([1, 1])

with col_gov:
    st.markdown(
        '<div class="section-header">Anomaly Governance</div>', unsafe_allow_html=True
    )

    total_interventions = gov.get("total_interventions", 0)

    st.markdown(
        f'<div style="color:#a8c8e8;font-size:12px;padding:4px 0;">'
        f"Interventions totales : <b>{total_interventions}</b> &nbsp;·&nbsp; "
        f"Crises mémorisées : <b>{crisis_count}</b> &nbsp;·&nbsp; "
        f"Entropie : <b>{entropy:.2f}</b></div>",
        unsafe_allow_html=True,
    )

    if suspensions_active > 0:
        susp_components = gov.get("suspended_components", [])
        if susp_components:
            tags = "".join(
                f'<span class="suspension-tag">🔒 {c}</span>' for c in susp_components
            )
            st.markdown(
                f'<div style="margin-top:6px;">{tags}</div>', unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="alert-box">{suspensions_active} composant(s) suspendu(s)</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="ok-box">✅ Aucun composant suspendu</div>',
            unsafe_allow_html=True,
        )

    # Entropie visuelle
    entropy_pct = int(entropy * 100)
    entropy_color = (
        "#00e676" if entropy >= 0.6 else ("#ffd600" if entropy >= 0.3 else "#ff4444")
    )
    st.markdown(
        f'<div style="margin-top:10px;">'
        f'<div style="color:#5a7fa0;font-size:10px;letter-spacing:1px;text-transform:uppercase;">'
        f"Entropie gouvernance</div>"
        f'<div style="background:#0d1b2a;border-radius:4px;height:8px;margin-top:4px;">'
        f'<div style="background:{entropy_color};width:{entropy_pct}%;height:8px;'
        f'border-radius:4px;"></div></div>'
        f'<div style="color:#5a7fa0;font-size:10px;margin-top:2px;">'
        f"0 = rigide (1 type) → 1 = diversifié (tous types équilibrés)</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

with col_perf:
    st.markdown(
        '<div class="section-header">Performance Supervisor</div>',
        unsafe_allow_html=True,
    )

    sharpe50 = perf.get("sharpe_50", 0.0)
    sharpe100 = perf.get("sharpe_100", 0.0)
    shadow_sigma = perf.get("shadow_deviation_sigma", 0.0)
    perf_alerts = perf.get("alerts", [])

    # Sharpe table
    rows_html = ""
    for label, val in [
        ("Sharpe (20)", sharpe20),
        ("Sharpe (50)", sharpe50),
        ("Sharpe (100)", sharpe100),
    ]:
        color = "green" if val >= 0.5 else ("yellow" if val >= 0 else "red")
        rows_html += (
            f'<div class="comp-row">'
            f'<span class="comp-name">{label}</span>'
            f'<span style="color:#e8f4fd;font-weight:700;">'
            f'<span style="color:{"#00e676" if color == "green" else ("#ffd600" if color == "yellow" else "#ff4444")};">'
            f"{val:.3f}</span></span></div>"
        )

    pf_color = "green" if pf >= 1.5 else ("yellow" if pf >= 1.0 else "red")
    rows_html += (
        f'<div class="comp-row"><span class="comp-name">Profit Factor</span>'
        f'<span style="color:{"#00e676" if pf_color == "green" else ("#ffd600" if pf_color == "yellow" else "#ff4444")};">'
        f"{pf:.3f}</span></div>"
        f'<div class="comp-row"><span class="comp-name">Shadow déviation</span>'
        f'<span style="color:{"#ff4444" if shadow_sigma > 2 else "#00e676"};">'
        f"{shadow_sigma:.2f}σ</span></div>"
    )
    st.markdown(rows_html, unsafe_allow_html=True)

    if perf_alerts:
        for alert in perf_alerts:
            st.markdown(
                f'<div class="warn-box">⚠ {alert}</div>', unsafe_allow_html=True
            )
    else:
        st.markdown(
            '<div class="ok-box" style="margin-top:6px;">✅ Aucune alerte performance</div>',
            unsafe_allow_html=True,
        )

st.markdown("<br>", unsafe_allow_html=True)

# ── Row 4 : Portfolio ─────────────────────────────────────────────────────────

st.markdown(
    '<div class="section-header">Portfolio Intelligence</div>', unsafe_allow_html=True
)

col_exch, col_strat, col_expo = st.columns([1, 1, 1])

by_exchange = port.get("by_exchange", {})
by_strategy = port.get("by_strategy", {})

CONC_WARN = 0.60
CONC_CRIT = 0.80


def _conc_color(frac: float) -> str:
    if frac >= CONC_CRIT:
        return "#ff4444"
    if frac >= CONC_WARN:
        return "#ffd600"
    return "#00e676"


with col_exch:
    st.markdown(
        '<div style="color:#5a7fa0;font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'margin-bottom:6px;">Par Exchange</div>',
        unsafe_allow_html=True,
    )
    if by_exchange:
        for exch, frac in sorted(by_exchange.items(), key=lambda x: -x[1]):
            bar_w = int(frac * 100)
            bar_color = _conc_color(frac)
            st.markdown(
                f'<div class="comp-row">'
                f'<span class="comp-name">{exch}</span>'
                f'<span style="color:{bar_color};font-weight:700;">{frac:.0%}</span>'
                f"</div>"
                f'<div style="background:#0d1b2a;border-radius:3px;height:5px;margin-bottom:4px;">'
                f'<div style="background:{bar_color};width:{bar_w}%;height:5px;border-radius:3px;"></div>'
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="color:#5a7fa0;font-size:11px;">Aucune position ouverte</div>',
            unsafe_allow_html=True,
        )

with col_strat:
    st.markdown(
        '<div style="color:#5a7fa0;font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'margin-bottom:6px;">Par Stratégie</div>',
        unsafe_allow_html=True,
    )
    if by_strategy:
        for strat, frac in sorted(by_strategy.items(), key=lambda x: -x[1]):
            bar_w = int(frac * 100)
            bar_color = _conc_color(frac)
            st.markdown(
                f'<div class="comp-row">'
                f'<span class="comp-name">{strat}</span>'
                f'<span style="color:{bar_color};font-weight:700;">{frac:.0%}</span>'
                f"</div>"
                f'<div style="background:#0d1b2a;border-radius:3px;height:5px;margin-bottom:4px;">'
                f'<div style="background:{bar_color};width:{bar_w}%;height:5px;border-radius:3px;"></div>'
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="color:#5a7fa0;font-size:11px;">Aucune position ouverte</div>',
            unsafe_allow_html=True,
        )

with col_expo:
    st.markdown(
        '<div style="color:#5a7fa0;font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'margin-bottom:6px;">Exposition nette</div>',
        unsafe_allow_html=True,
    )
    expo_pct = net_expo * 100  # -100% à +100%
    bar_center = 50
    bar_pos = max(0, min(100, 50 + expo_pct / 2))
    bar_color_expo = (
        "#00e676"
        if abs(net_expo) < 0.5
        else ("#ffd600" if abs(net_expo) < 0.8 else "#ff4444")
    )

    direction_label = "LONG" if net_expo > 0 else ("SHORT" if net_expo < 0 else "FLAT")
    dir_color = "#00e676" if net_expo >= 0 else "#ff4444"

    st.markdown(
        f'<div style="text-align:center;margin-bottom:10px;">'
        f'<span style="color:{dir_color};font-size:24px;font-weight:700;">'
        f"{direction_label} {abs(net_expo):.0%}"
        f"</span></div>"
        f'<div style="background:#0d1b2a;border-radius:4px;height:10px;position:relative;">'
        f'<div style="position:absolute;left:50%;width:1px;height:10px;background:#5a7fa0;"></div>'
        f'<div style="background:{bar_color_expo};width:8px;height:10px;border-radius:4px;'
        f'position:absolute;left:{bar_pos}%;transform:translateX(-50%);"></div>'
        f"</div>"
        f'<div style="display:flex;justify-content:space-between;color:#5a7fa0;font-size:9px;margin-top:2px;">'
        f"<span>-100% SHORT</span><span>NEUTRE</span><span>+100% LONG</span></div>"
        f'<div style="color:#5a7fa0;font-size:11px;margin-top:8px;">'
        f"Seuil alerte : ≥80% | {pos_count} positions · ${total_usd:,.0f}</div>",
        unsafe_allow_html=True,
    )

# ── Alerte niveau 2 banner ────────────────────────────────────────────────────

if level2_active:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="alert-box" style="border-color:#ff1744;font-size:14px;">'
        f"🚨 <b>ALERTE NIVEAU 2 ACTIVE</b> — meta_health_score={meta_score:.0%}"
        f"<br><span style='font-size:12px;'>"
        f"Le système surveille sa propre surveillance et détecte un état dégradé. "
        f"Vérifier : composants RED, dérive active, suspensions en cours.</span></div>",
        unsafe_allow_html=True,
    )

# ── Auto-refresh ──────────────────────────────────────────────────────────────

st.markdown(
    f'<div style="color:#2a3f55;font-size:10px;text-align:right;margin-top:12px;">'
    f"Rafraîchissement auto: {REFRESH_INTERVAL}s · "
    f"Source: {SNAPSHOT_PATH}</div>",
    unsafe_allow_html=True,
)

# Streamlit auto-refresh via time.sleep + st.rerun
import time as _time

_time.sleep(REFRESH_INTERVAL)
st.rerun()
