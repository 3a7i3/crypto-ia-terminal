"""
dashboard_utils.py — Styles, composants et thème partagés pour tous les dashboards.

Utilisation dans chaque dashboard :
    from dashboard_utils import inject_css, metric_card, compact_df, CHART_THEME, C

    inject_css()                # dark theme + polices
    metric_card("Capital", "$1000")
    compact_df(df)              # tableau compact sans défilement infini
    fig.update_layout(**CHART_THEME)
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).parent
_COLORS = json.loads((_HERE / "color_system.json").read_text(encoding="utf-8"))
C = _COLORS


def inject_css() -> None:
    bg_dark = C["background"]["dark"]
    bg_card = C["background"]["card"]
    bg_border = C["background"]["border"]
    txt_pri = C["text"]["primary"]
    txt_sec = C["text"]["secondary"]
    txt_mut = C["text"]["muted"]
    accent = C["accent"]
    ok = C["status"]["ok"]
    warn = C["status"]["warning"]
    err = C["status"]["error"]
    neutral = C["status"]["neutral"]

    st.markdown(
        f"""<style>
        .stApp, .stApp > header {{ background-color: {bg_dark}; }}
        .stApp .main .block-container {{ padding-top: 1.5rem; padding-bottom: 1.5rem; }}
        h1, h2, h3, h4, h5, h6 {{ color: {txt_pri} !important; }}
        .stMarkdown p, .stMarkdown li, p, li {{ color: {txt_sec} !important; }}
        .stCaption, caption, .caption {{ color: {txt_mut} !important; font-size: 0.75rem !important; }}

        div[data-testid="metric-container"] {{
            background-color: {bg_card};
            border: 1px solid {bg_border};
            border-radius: 8px;
            padding: 10px 14px;
        }}
        div[data-testid="metric-container"] label {{
            color: {txt_sec} !important;
            font-size: 0.8rem !important;
        }}
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] {{
            color: {txt_pri} !important;
            font-weight: 700 !important;
            font-size: 1.4rem !important;
        }}

        .custom-card {{
            background-color: {bg_card};
            border: 1px solid {bg_border};
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 8px;
        }}
        .custom-card-title {{
            color: {txt_sec};
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        .custom-card-value {{
            color: {txt_pri};
            font-size: 1.3rem;
            font-weight: 700;
        }}
        .custom-card-sub {{ color: {txt_mut}; font-size: 0.7rem; }}

        .module-card {{
            background-color: {bg_card};
            border-left: 3px solid {neutral};
            border-radius: 6px;
            padding: 7px 12px;
            margin-bottom: 6px;
        }}
        .module-card .name {{ color: {txt_pri}; font-size: 0.85rem; font-weight: 600; }}
        .module-card .desc {{ color: {txt_sec}; font-size: 0.7rem; }}

        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.67rem;
            font-weight: 700;
            font-family: 'Courier New', monospace;
            letter-spacing: 0.3px;
        }}
        .badge-ok      {{ background-color: {ok}22;      color: {ok}; }}
        .badge-warn    {{ background-color: {warn}22;    color: {warn}; }}
        .badge-err     {{ background-color: {err}22;     color: {err}; }}
        .badge-neutral {{ background-color: {neutral}22; color: {neutral}; }}
        .badge-accent  {{ background-color: {accent}22;  color: {accent}; }}

        .signal-trade {{ background-color: #00e0ff; color: #0a0c12; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; font-family: monospace; }}
        .signal-watch {{ background-color: #f59e0b; color: #0a0c12; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; font-family: monospace; }}
        .signal-hold  {{ background-color: #334155; color: #94a3b8; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; font-family: monospace; }}
        .signal-block {{ background-color: #ef4444; color: #ffffff; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; font-family: monospace; }}

        .verdict-bar {{
            border-left: 4px solid {accent};
            background-color: {bg_card};
            border-radius: 6px;
            padding: 0.55rem 1rem;
            margin: 8px 0;
        }}
        .verdict-bar .label {{ color: {txt_sec}; font-size: 0.75rem; }}
        .verdict-bar .value {{ color: {txt_pri}; font-size: 1rem; font-weight: 600; }}

        div[data-testid="stDataFrame"] {{ font-size: 0.75rem !important; }}
        div[data-testid="stDataFrame"] th {{
            background-color: {bg_card} !important;
            color: {txt_sec} !important;
            font-size: 0.7rem !important;
            font-weight: 600 !important;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }}
        div[data-testid="stDataFrame"] td {{
            color: {txt_pri} !important;
            font-size: 0.72rem !important;
        }}

        div[data-testid="stProgress"] > div > div > div > div {{ background-color: {accent}; }}

        button[data-baseweb="tab"] {{ color: {txt_sec} !important; font-size: 0.85rem !important; }}
        button[data-baseweb="tab"][aria-selected="true"] {{
            color: {accent} !important;
            border-bottom-color: {accent} !important;
        }}

        section[data-testid="stSidebar"] {{ background-color: {bg_dark}; }}
        section[data-testid="stSidebar"] .stMarkdown p {{ color: {txt_sec} !important; }}

        .chip {{
            display: inline-block;
            background-color: {bg_border};
            color: {txt_sec};
            padding: 1px 8px;
            border-radius: 10px;
            font-size: 0.67rem;
            font-family: monospace;
            margin-right: 4px;
        }}
        hr {{ border-color: {bg_border} !important; opacity: 0.5; margin: 0.8rem 0; }}
        </style>""",
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, delta: str | None = None) -> None:
    sub = f'<div class="custom-card-sub">{delta}</div>' if delta else ""
    st.markdown(
        f'<div class="custom-card">'
        f'<div class="custom-card-title">{label}</div>'
        f'<div class="custom-card-value">{value}</div>'
        f"{sub}</div>",
        unsafe_allow_html=True,
    )


def signal_badge(signal: str) -> str:
    return f'<span class="signal-{signal.lower()}">{signal}</span>'


def status_badge(status: str) -> str:
    cls_map = {
        "OK": "badge-ok",
        "ACTIF": "badge-ok",
        "WARNING": "badge-warn",
        "ERROR": "badge-err",
        "ABSENT": "badge-err",
        "VIDE": "badge-neutral",
        "INACTIF": "badge-neutral",
    }
    cls = cls_map.get(status.upper(), "badge-neutral")
    return f'<span class="badge {cls}">{status}</span>'


def regime_badge(regime: str) -> str:
    color_map = {
        "TREND_BULL": "#22c55e",
        "BULL": "#22c55e",
        "TREND_BEAR": "#ef4444",
        "BEAR": "#ef4444",
        "RANGE": "#6b7280",
        "SIDEWAYS": "#6b7280",
        "VOLATILE": "#f59e0b",
    }
    color = color_map.get(regime.upper(), "#9ca3af")
    return f'<span class="badge" style="background-color:{color}22; color:{color};">{regime}</span>'


def conviction_badge(level: str) -> str:
    color_map = {
        "VERY_HIGH": "#22c55e",
        "HIGH": "#84cc16",
        "MEDIUM": "#f59e0b",
        "LOW": "#f97316",
        "SKIP": "#6b7280",
    }
    color = color_map.get(level.upper(), "#6b7280")
    return f'<span class="badge" style="background-color:{color}22; color:{color};">{level}</span>'


def verdict_bar(label: str, value: str, color: str = "#00e0ff") -> None:
    st.markdown(
        f'<div class="verdict-bar" style="border-left-color: {color};">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div></div>',
        unsafe_allow_html=True,
    )


def module_card(name: str, status: str, description: str = "") -> None:
    color_map = {
        "OK": "#22c55e",
        "ACTIF": "#22c55e",
        "WARNING": "#f59e0b",
        "ERROR": "#ef4444",
        "ABSENT": "#ef4444",
        "VIDE": "#6b7280",
        "INACTIF": "#6b7280",
    }
    color = color_map.get(status.upper(), "#6b7280")
    badge_cls = (
        "ok"
        if status.upper() == "OK"
        else (
            "warn"
            if status.upper() in ("WARNING", "WARN")
            else "err" if status.upper() in ("ERROR", "ABSENT") else "neutral"
        )
    )
    st.markdown(
        f'<div class="module-card" style="border-left-color: {color};">'
        f'<div class="name">{name} <span class="badge badge-{badge_cls}">{status}</span></div>'
        f'<div class="desc">{description}</div></div>',
        unsafe_allow_html=True,
    )


def compact_df(df, height: int = 250, use_container_width: bool = True) -> None:
    st.dataframe(
        df, height=height, use_container_width=use_container_width, hide_index=True
    )


def dashboard_header(
    title: str, subtitle: str | None = None, refresh_interval: str = "auto 20s"
) -> None:
    cols = st.columns([5, 1])
    with cols[0]:
        st.markdown(f"## {title}")
        if subtitle:
            st.markdown(
                f'<p style="color:{C["text"]["secondary"]}; font-size:0.85rem;">{subtitle}</p>',
                unsafe_allow_html=True,
            )
    with cols[1]:
        if refresh_interval:
            st.markdown(
                f'<p style="text-align:right; color:{C["text"]["muted"]}; font-size:0.7rem; font-family:monospace;">{refresh_interval}</p>',
                unsafe_allow_html=True,
            )
    st.markdown("---")


def apply_chart_theme(fig):
    fig.update_layout(**CHART_THEME)
    return fig


CHART_THEME: dict = {
    "paper_bgcolor": "#0a0c12",
    "plot_bgcolor": "#0e1117",
    "font": {"color": "#94a3b8", "size": 11, "family": "system-ui, sans-serif"},
    "title": {"font": {"color": "#f8fafc", "size": 14}},
    "xaxis": {
        "gridcolor": "#1a1e2a",
        "zerolinecolor": "#1e293b",
        "tickfont": {"color": "#475569", "size": 10},
    },
    "yaxis": {
        "gridcolor": "#1a1e2a",
        "zerolinecolor": "#1e293b",
        "tickfont": {"color": "#475569", "size": 10},
    },
    "legend": {"bgcolor": "#111420", "font": {"color": "#94a3b8"}},
    "hoverlabel": {"bgcolor": "#1e293b", "font": {"color": "#f8fafc"}},
    "margin": {"l": 40, "r": 20, "t": 30, "b": 40},
}
