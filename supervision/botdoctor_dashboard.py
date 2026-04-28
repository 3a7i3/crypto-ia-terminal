"""
botdoctor_dashboard.py — Dashboard de supervision BotDoctor.

Tutoriel d'utilisation:
    Ce module expose la fonction `render()` pour afficher le tableau de bord
    BotDoctor dans Streamlit. Importez-le et appelez `render(doctor)`.

Tutorial:
    from supervision.botdoctor_dashboard import render
    render(doctor_instance)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supervision.bot_doctor import BotDoctor


def render(doctor: "BotDoctor | None" = None) -> None:
    """Affiche le rapport BotDoctor via Streamlit."""
    import streamlit as st

    st.markdown("## 🤖 BotDoctor Dashboard")
    st.markdown(
        "> **Tutoriel** : Ce panel affiche l'état de santé de vos modules de trading."
    )
    if doctor is None:
        st.info(
            "Aucun BotDoctor fourni. Initialisez-en un et appelez `render(doctor)`."
        )
        return
    statuses = doctor.get_report()
    for s in statuses:
        icon = "✅" if s["is_healthy"] else "❌"
        st.markdown(f"{icon} **{s['name']}** — {s.get('error') or 'OK'}")
