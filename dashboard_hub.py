"""
dashboard_hub.py — Point d'entrée unique du Crypto AI Terminal.

3 niveaux cognitifs sélectionnables par dropdown :
  Opérationnel  : Vue Globale, Marchés Live
  Contrôle      : Risk Gate, Positions
  Analytique    : Decision Trace, Multi-Exchange, Comparaison, Panel P6

Technique : runpy.run_path() exécute chaque dashboard dans un namespace isolé.
st.set_page_config() est intercepté pour éviter le double-appel.

Usage :
    streamlit run dashboard_hub.py
    streamlit run dashboard_hub.py --server.port 8500
"""

from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

from dashboard.colors import C, css_inject

BASE = Path(__file__).parent

# ── Structure de navigation ───────────────────────────────────────────────────

PAGES: dict[str, list[tuple[str, str]]] = {
    "Opérationnel": [
        ("Vue Globale", "dashboard_master.py"),
        ("Marchés Live", "dashboard_live.py"),
    ],
    "Contrôle": [
        ("Risk Gate", "dashboard_risk.py"),
        ("Positions", "dashboard_positions.py"),
    ],
    "Analytique": [
        ("Decision Trace", "dashboard_decision_trace.py"),
        ("Multi-Exchange", "dashboard_multi_exchange.py"),
        ("Comparaison", "dashboard_compare_multi.py"),
        ("Panel P6", "dashboard_p6_panel.py"),
    ],
}

# ── Page config (appelé une seule fois) ───────────────────────────────────────

st.set_page_config(
    page_title="Crypto AI Terminal",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

css_inject()

# CSS hub minimal — complète css_inject() sans le remplacer
_bg = C["background"]
_txt = C["text"]
_status = C["status"]

st.markdown(
    f"""
<style>
/* Hub — sidebar header */
.hub-title {{
    padding: 0.5rem 0 1rem 0;
    border-bottom: 1px solid {_bg["border"]};
    margin-bottom: 1rem;
}}
.hub-label {{
    font-size: 0.62rem;
    font-weight: 700;
    color: {_txt["muted"]};
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.2rem;
}}
.hub-name {{
    font-size: 1.05rem;
    font-weight: 800;
    color: {_txt["primary"]};
    font-family: 'Courier New', monospace;
}}
/* Supprime le padding excessif du selectbox hub */
.hub-nav .stSelectbox {{ margin-bottom: 0.4rem; }}
</style>
""",
    unsafe_allow_html=True,
)

# ── Sidebar : navigation hub ──────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        """
        <div class="hub-title">
            <div class="hub-label">Crypto AI Terminal</div>
            <div class="hub-name">Navigation</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    section = st.selectbox(
        "Niveau",
        list(PAGES.keys()),
        key="hub_section",
    )

    dashboard_labels = [name for name, _ in PAGES[section]]
    selected_label = st.selectbox(
        "Dashboard",
        dashboard_labels,
        key="hub_dashboard",
    )

    st.divider()
    # Le contenu sidebar spécifique au dashboard s'injecte ici automatiquement
    # (les appels st.sidebar.* dans chaque dashboard s'ajoutent après la divider)

# ── Résolution du fichier ─────────────────────────────────────────────────────

selected_file = next(
    filepath for name, filepath in PAGES[section] if name == selected_label
)

target = BASE / selected_file

# ── Rendu du dashboard sélectionné ───────────────────────────────────────────

if not target.exists():
    st.error(
        f"Dashboard introuvable : `{selected_file}`  \n"
        f"Vérifier que le fichier existe dans `{BASE}`"
    )
    st.stop()

# Intercepte st.set_page_config pour éviter le double-appel (interdit par Streamlit).
# Le dashboard s'exécute dans un namespace frais via runpy mais injecte ses éléments
# dans la session Streamlit courante — comportement identique à l'exécution standalone.
_orig_spc = st.set_page_config
st.set_page_config = lambda **kw: None  # type: ignore[method-assign]

try:
    runpy.run_path(
        str(target),
        init_globals={"__file__": str(target)},
        run_name="__render__",
    )
except SystemExit:
    pass  # st.stop() lève SystemExit — normal
except Exception as exc:
    st.error(
        f"Erreur lors du chargement de **{selected_label}** :\n\n"
        f"```\n{type(exc).__name__}: {exc}\n```"
    )
finally:
    st.set_page_config = _orig_spc  # type: ignore[method-assign]
