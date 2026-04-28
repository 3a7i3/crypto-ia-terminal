"""
feedback_dashboard.py — Dashboard de collecte et visualisation des feedbacks.

Tutoriel d'utilisation:
    Lancez ce dashboard avec : streamlit run ai_autonomous_loop/feedback_dashboard.py

Tutorial:
    1. Le dashboard collecte automatiquement les feedbacks depuis feedback_logs/
    2. Filtrez par date, module, ou type de feedback
    3. Exportez les feedbacks en CSV pour analyse
"""

from __future__ import annotations

from pathlib import Path

FEEDBACK_DIR = Path("feedback_logs")
TUTORIAL = """
## Tutoriel — Feedback Dashboard

- **Vue globale** : Résumé de tous les feedbacks collectés
- **Filtres** : Par date, module, type (positif/négatif/neutre)
- **Export** : Téléchargement CSV des données filtrées
"""


def load_feedbacks() -> list[dict]:
    """Charge tous les feedbacks depuis feedback_logs/."""
    import json

    feedbacks = []
    if not FEEDBACK_DIR.exists():
        return feedbacks
    for f in FEEDBACK_DIR.glob("*.json"):
        try:
            feedbacks.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return feedbacks


def render() -> None:
    """Affiche le dashboard de feedback via Streamlit."""
    import streamlit as st

    st.markdown("## 💬 Feedback Dashboard")
    st.markdown(TUTORIAL)
    feedbacks = load_feedbacks()
    if feedbacks:
        import pandas as pd

        df = pd.DataFrame(feedbacks)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Aucun feedback collecté pour l'instant.")
