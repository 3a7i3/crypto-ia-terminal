"""
dashboard_hub.py — Hub central des dashboards Crypto AI Terminal

Lance avec :  streamlit run dashboard_hub.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent

st.set_page_config(
    page_title="Crypto AI — Dashboard Hub",
    page_icon="🎛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Injection CSS ─────────────────────────────────────────────────────────────
try:
    from dashboard.colors import C, css_inject

    css_inject()
    _has_colors = True
except Exception:
    _has_colors = False
    C = {}

st.markdown(
    """
<style>
.hub-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.2s;
}
.hub-card:hover { border-color: #3b82f6; }
.hub-title { font-size: 1rem; font-weight: 700; color: #f8fafc; margin-bottom: 0.2rem; }
.hub-desc  { font-size: 0.8rem; color: #94a3b8; margin-bottom: 0.6rem; }
.hub-port  { font-size: 0.7rem; color: #475569; font-family: monospace; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Catalogue des dashboards ───────────────────────────────────────────────────
DASHBOARDS = [
    {
        "name": "Live Dashboard",
        "file": "dashboard_live.py",
        "port": 8501,
        "description": "Prix live, signaux, scores — vue marché en temps réel",
        "tag": "PRINCIPAL",
        "tag_color": "#22c55e",
    },
    {
        "name": "Master Dashboard",
        "file": "dashboard_master.py",
        "port": 8502,
        "description": "Vue globale unifiée — black box, cycles, positions, analyse",
        "tag": "MASTER",
        "tag_color": "#3b82f6",
    },
    {
        "name": "Decision Trace",
        "file": "dashboard_decision_trace.py",
        "port": 8503,
        "description": "Trace complète des décisions — lifecycle, raisonnements, états",
        "tag": "DECISIONS",
        "tag_color": "#8b5cf6",
    },
    {
        "name": "Command Center",
        "file": "command_center_dashboard.py",
        "port": 8504,
        "description": "Centre de contrôle — 63 modules, health checks, alertes",
        "tag": "CONTRÔLE",
        "tag_color": "#f59e0b",
    },
    {
        "name": "Risk Dashboard",
        "file": "dashboard_risk.py",
        "port": 8505,
        "description": "Exposition, drawdown, risk gate — gouvernance du capital",
        "tag": "RISQUE",
        "tag_color": "#ef4444",
    },
    {
        "name": "Positions",
        "file": "dashboard_positions.py",
        "port": 8506,
        "description": "Positions ouvertes — TP/SL, trailing, liquidation",
        "tag": "POSITIONS",
        "tag_color": "#14b8a6",
    },
    {
        "name": "Evolution",
        "file": "evolution_dashboard.py",
        "port": 8507,
        "description": "Apprentissage automatique — MistakeMemory, règles auto-générées",
        "tag": "LEARNING",
        "tag_color": "#f97316",
    },
    {
        "name": "Compare Multi",
        "file": "dashboard_compare_multi.py",
        "port": 8508,
        "description": "Comparaison multi-stratégies et multi-sessions",
        "tag": "ANALYSE",
        "tag_color": "#6b7280",
    },
    {
        "name": "Execution Health",
        "file": "execution_health.py",
        "port": 8509,
        "description": "Santé d'exécution P2 — audit ordres, slippage simulé, rejections, pipeline",
        "tag": "EXECUTION",
        "tag_color": "#00e0ff",
    },
]

# ── State — processus lancés ───────────────────────────────────────────────────
if "running_ports" not in st.session_state:
    st.session_state.running_ports: dict[int, subprocess.Popen] = {}


def launch(dashboard: dict) -> None:
    port = dashboard["port"]
    file = ROOT / dashboard["file"]

    if not file.exists():
        st.error(f"Fichier introuvable : {dashboard['file']}")
        return

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(file),
            "--server.port",
            str(port),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    st.session_state.running_ports[port] = proc
    time.sleep(1.5)


def stop(port: int) -> None:
    proc = st.session_state.running_ports.pop(port, None)
    if proc:
        proc.terminate()


def is_running(port: int) -> bool:
    proc = st.session_state.running_ports.get(port)
    if proc is None:
        return False
    return proc.poll() is None


# ── UI ────────────────────────────────────────────────────────────────────────
st.markdown("# Crypto AI — Dashboard Hub")
st.markdown(
    '<span style="color:#94a3b8;font-size:0.9rem;">Lancez et accédez à tous les dashboards depuis un seul endroit.</span>',
    unsafe_allow_html=True,
)
st.markdown("---")

cols = st.columns(2)

for i, dash in enumerate(DASHBOARDS):
    col = cols[i % 2]
    port = dash["port"]
    running = is_running(port)
    file_exists = (ROOT / dash["file"]).exists()

    with col:
        tag_html = (
            f'<span style="background:{dash["tag_color"]};color:#fff;'
            f"padding:1px 7px;border-radius:3px;font-size:0.7rem;"
            f'font-weight:700;">{dash["tag"]}</span>'
        )
        st.markdown(
            f'<div class="hub-card">'
            f'<div class="hub-title">{tag_html}&nbsp; {dash["name"]}</div>'
            f'<div class="hub-desc">{dash["description"]}</div>'
            f'<div class="hub-port">:{port} — {dash["file"]}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 3])

        with btn_col1:
            if not file_exists:
                st.button("Indisponible", key=f"na_{port}", disabled=True)
            elif running:
                if st.button("Arrêter", key=f"stop_{port}", type="secondary"):
                    stop(port)
                    st.rerun()
            else:
                if st.button("Lancer", key=f"launch_{port}", type="primary"):
                    launch(dash)
                    st.rerun()

        with btn_col2:
            if running:
                st.link_button(
                    "Ouvrir",
                    f"http://localhost:{port}",
                )

        with btn_col3:
            if running:
                st.markdown(
                    '<span style="color:#22c55e;font-size:0.8rem;">● En cours</span>',
                    unsafe_allow_html=True,
                )
            elif file_exists:
                st.markdown(
                    '<span style="color:#6b7280;font-size:0.8rem;">○ Arrêté</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span style="color:#ef4444;font-size:0.8rem;">✕ Fichier manquant</span>',
                    unsafe_allow_html=True,
                )

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
running_count = sum(1 for p in st.session_state.running_ports if is_running(p))
st.markdown(
    f'<span style="color:#94a3b8;font-size:0.8rem;">'
    f"{running_count} dashboard(s) actif(s) — "
    f"Ce hub tourne sur le port 8500 par défaut "
    f"(<code>streamlit run dashboard_hub.py --server.port 8500</code>)"
    f"</span>",
    unsafe_allow_html=True,
)
