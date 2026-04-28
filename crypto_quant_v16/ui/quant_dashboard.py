"""
quant_dashboard.py — Dashboard principal du terminal Quant V16.

Tutoriel d'utilisation:
    Lancez ce dashboard avec : streamlit run crypto_quant_v16/ui/quant_dashboard.py

Tutorial:
    1. Configurez vos clés API dans .env
    2. Lancez : streamlit run crypto_quant_v16/ui/quant_dashboard.py
    3. Naviguez entre les panels via la sidebar
"""

from __future__ import annotations

DASHBOARD_VERSION = "16.0"
TUTORIAL = """
## Tutoriel — Quant Dashboard V16

1. **Marché** : Visualisez les prix et volumes en temps réel
2. **Stratégies** : Explorez les signaux générés par le moteur quant
3. **Risque** : Consultez les métriques de drawdown et VaR
4. **Evolution** : Suivez la performance des stratégies par génération
"""


def render() -> None:
    """Affiche le dashboard Quant V16 via Streamlit."""
    import streamlit as st

    st.markdown(f"## 📈 Quant Dashboard V{DASHBOARD_VERSION}")
    st.markdown(TUTORIAL)
    st.info("Connectez votre exchange pour afficher les données en temps réel.")
