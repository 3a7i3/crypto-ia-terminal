"""
tune.py — Panneau de contrôle à chaud du bot (Streamlit)

Lance avec :  streamlit run tune.py

Modifie databases/runtime_config.json que advisor_loop.py recharge
automatiquement à chaque cycle — aucun redémarrage nécessaire.

GOUVERNANCE : GATE_MIN_SCORE_OVERRIDE et FORCE_TEST_EXECUTION sont
des variables de gouvernance verrouillées. Elles ne peuvent pas être
modifiées via ce panneau. Un redémarrage du processus est requis.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Crypto AI — Panneau de contrôle",
    page_icon="🎛️",
    layout="centered",
)

st.markdown(
    """
<style>
.stApp { background: #0e1117; color: #e0e0e0; }
h1, h2, h3 { color: #00e0ff; }
.stAlert { border-radius: 8px; }
</style>
""",
    unsafe_allow_html=True,
)

CONFIG_PATH = Path("databases/runtime_config.json")

DEFAULTS = {
    "EXEC_MAX_ORDER_USD": 50,
    "SIGNAL_MIN_SCORE": 70,
    "EO_DD_VETO": 0.10,
    "EO_DD_RECOVERY": 0.04,
    "EXCHANGE_HEARTBEAT_S": 15,
}


def load_config() -> dict:
    try:
        return {**DEFAULTS, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    except Exception:
        return dict(DEFAULTS)


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ── En-tête ───────────────────────────────────────────────────────────────────
st.title("🎛️ Panneau de contrôle — Crypto AI")
st.caption(
    "Les changements sont pris en compte au **prochain cycle** du bot "
    "sans redémarrage. Fichier : `databases/runtime_config.json`"
)

cfg = load_config()

# ── Snapshot live (si disponible) ─────────────────────────────────────────────
snap_path = Path("databases/live_snapshot.json")
if snap_path.exists():
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        age = time.time() - snap.get("ts", 0)
        col1, col2, col3 = st.columns(3)
        col1.metric("Cycle actuel", f"#{snap.get('cycle', '?')}")
        col2.metric("Capital", f"${snap.get('capital', 0):,.0f}")
        col3.metric("Snapshot age", f"{age:.0f}s")
        if age > 400:
            st.warning("Le bot semble inactif (snapshot > 400s).")
    except Exception:
        pass

st.divider()
st.info(
    "**Variables de gouvernance verrouillées** — `GATE_MIN_SCORE_OVERRIDE` et "
    "`FORCE_TEST_EXECUTION` ne sont pas reconfigurables à chaud. "
    "Elles nécessitent un redémarrage du processus et ne doivent jamais être "
    "activées en production.",
    icon="🔒",
)

st.divider()
# ── Contrôles ─────────────────────────────────────────────────────────────────
st.subheader("Sizing & signal")

col_c, col_d = st.columns(2)
with col_c:
    max_order = st.number_input(
        "EXEC_MAX_ORDER_USD ($)",
        min_value=5,
        max_value=10000,
        value=int(cfg["EXEC_MAX_ORDER_USD"]),
        step=5,
        help="Taille maximale d'un ordre en USD.",
    )
with col_d:
    signal_min = st.slider(
        "SIGNAL_MIN_SCORE",
        min_value=0,
        max_value=100,
        value=int(cfg["SIGNAL_MIN_SCORE"]),
        step=5,
        help="Score minimum pour qu'un signal soit 'actionable'.",
    )

st.divider()
st.subheader("Risk — ExecutiveOverride")

col_e, col_f = st.columns(2)
with col_e:
    eo_veto = st.slider(
        "EO_DD_VETO (%)",
        min_value=1,
        max_value=50,
        value=int(float(cfg["EO_DD_VETO"]) * 100),
        step=1,
        help="Drawdown (%) déclenchant le VETO global.",
    )
with col_f:
    eo_recovery = st.slider(
        "EO_DD_RECOVERY (%)",
        min_value=1,
        max_value=20,
        value=int(float(cfg["EO_DD_RECOVERY"]) * 100),
        step=1,
        help="Drawdown (%) pour sortir du VETO.",
    )

st.divider()
st.subheader("Exchange monitor")

heartbeat = st.slider(
    "EXCHANGE_HEARTBEAT_S (secondes)",
    min_value=5,
    max_value=120,
    value=int(cfg["EXCHANGE_HEARTBEAT_S"]),
    step=5,
    help="Fréquence des pings Binance. Valeur basse = détection rapide, mais plus de requêtes.",
)

st.divider()

# ── Sauvegarde ────────────────────────────────────────────────────────────────
new_cfg = {
    "EXEC_MAX_ORDER_USD": max_order,
    "SIGNAL_MIN_SCORE": signal_min,
    "EO_DD_VETO": round(eo_veto / 100, 3),
    "EO_DD_RECOVERY": round(eo_recovery / 100, 3),
    "EXCHANGE_HEARTBEAT_S": heartbeat,
}

col_save, col_reset = st.columns([3, 1])
with col_save:
    if st.button(
        "💾 Appliquer les changements", use_container_width=True, type="primary"
    ):
        save_config(new_cfg)
        st.success("Config sauvegardée — prise en compte au prochain cycle du bot.")

with col_reset:
    if st.button("↺ Défauts", use_container_width=True):
        save_config(dict(DEFAULTS))
        st.rerun()

# ── Aperçu JSON ───────────────────────────────────────────────────────────────
with st.expander("Voir le JSON actuel"):
    try:
        st.json(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:
        st.json(DEFAULTS)
