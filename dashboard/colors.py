"""
dashboard/colors.py — Utilitaire couleurs pour tous les dashboards Streamlit.

Charge anara_context/color_system.json une seule fois et expose des helpers.

Usage :
    from dashboard.colors import C, state_color, conviction_color, css_inject

    css_inject()  # à appeler après st.set_page_config()
    color = state_color("REJECTED")   # "#ef4444"
    color = conviction_color("HIGH")  # "#84cc16"
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).parent.parent
_COLOR_FILE = _ROOT / "anara_context" / "color_system.json"

# Charge le fichier une seule fois au niveau module
with open(_COLOR_FILE, encoding="utf-8") as _f:
    C: dict = json.load(_f)


# ── Helpers ───────────────────────────────────────────────────────────────────


def state_color(state: str) -> str:
    """Couleur hex pour un DecisionState."""
    return C["decision_states"].get(state, C["status"]["neutral"])


def conviction_color(level: str) -> str:
    """Couleur hex pour un ConvictionLevel."""
    return C["conviction_levels"].get(level, C["status"]["neutral"])


def regime_color(regime: str) -> str:
    """Couleur hex pour un MarketRegime."""
    return C["market_regimes"].get(regime, C["status"]["neutral"])


def severity_color(severity: str) -> str:
    """Couleur hex pour une sévérité (INFO/WARNING/CRITICAL/FATAL)."""
    return C["severity"].get(severity, C["status"]["neutral"])


def postmortem_color(category: str) -> str:
    """Couleur hex pour VALIDATED/LUCKY/UNLUCKY/MISTAKE."""
    return C["postmortem_categories"].get(category, C["status"]["neutral"])


def mode_color(mode: str) -> str:
    """Couleur hex pour paper/testnet/live."""
    return C["trading_modes"].get(mode, C["status"]["neutral"])


def status_badge(label: str, color: str) -> str:
    """HTML badge coloré inline."""
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.75rem;font-weight:600;">{label}</span>'
    )


def colored_metric(label: str, value: str, color: str) -> str:
    """Carte métrique HTML simple avec bordure colorée."""
    bg = C["background"]["card"]
    return (
        f'<div style="background:{bg};border-left:4px solid {color};'
        f'border-radius:6px;padding:0.6rem 1rem;margin-bottom:0.4rem;">'
        f'<div style="color:{C["text"]["secondary"]};font-size:0.75rem;">{label}</div>'
        f'<div style="color:{color};font-size:1.1rem;font-weight:700;">{value}</div>'
        f"</div>"
    )


# ── CSS global ────────────────────────────────────────────────────────────────


def css_inject() -> None:
    """
    Injecte le CSS de base dans Streamlit depuis color_system.json.
    À appeler une fois après st.set_page_config().
    """
    bg = C["background"]
    text = C["text"]
    status = C["status"]

    st.markdown(
        f"""
<style>
/* ── Base ── */
.stApp {{ background: {bg["dark"]}; color: {text["primary"]}; }}
.block-container {{ padding-top: 0.8rem; padding-bottom: 0; }}

/* ── Métriques ── */
div[data-testid="metric-container"] {{
    background: {bg["card"]};
    border: 1px solid {bg["border"]};
    border-radius: 8px;
    padding: 10px 14px;
}}

/* ── Onglets ── */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{
    background: {bg["card"]};
    border-radius: 6px 6px 0 0;
    color: {text["secondary"]};
    padding: 6px 16px;
}}
.stTabs [aria-selected="true"] {{
    background: {bg["card_hover"]};
    color: {text["primary"]};
    font-weight: 600;
}}

/* ── Status classes ── */
.status-ok   {{ color: {status["ok"]};      font-weight: 700; }}
.status-warn {{ color: {status["warning"]};  font-weight: 700; }}
.status-err  {{ color: {status["error"]};    font-weight: 700; }}
.status-info {{ color: {status["info"]};     font-weight: 700; }}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{ background: {bg["card"]}; }}

/* ── Séparateurs ── */
hr {{ border-color: {bg["border"]}; }}
</style>
""",
        unsafe_allow_html=True,
    )
