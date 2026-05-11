"""
alert_dashboard.py — Lecture et filtrage des alertes depuis le fichier d'audit JSONL.

Tutoriel d'utilisation:
    Ce module s'utilise en conjonction avec AlertManager pour visualiser les alertes.
    Lancez le dashboard avec : streamlit run dashboard/alert_dashboard.py

Tutorial:
    1. Les alertes sont lues depuis AUDIT_FILE (défaut: alerts_audit.jsonl)
    2. Filtrez par module ou severity via `filter_by_module()` / `filter_by_severity()`
    3. Exportez les résultats filtrés via pandas DataFrame

Interface publique:
    AUDIT_FILE: chemin vers le fichier d'audit (modifiable par les tests)
    load_audit() -> list[dict]: charge toutes les entrées du fichier d'audit
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

AUDIT_FILE: Any = Path("alerts_audit.jsonl")


def load_audit() -> list[dict]:
    """Charge toutes les entrées du fichier d'audit JSONL.

    Retourne une liste vide si le fichier n'existe pas ou est vide.
    """
    path = Path(AUDIT_FILE)
    if not path.exists():
        return []
    entries: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def filter_by_module(entries: list[dict], module: str) -> list[dict]:
    return [e for e in entries if e.get("alert", {}).get("module") == module]


def filter_by_severity(entries: list[dict], severity: str) -> list[dict]:
    return [e for e in entries if e.get("alert", {}).get("severity") == severity]


def render() -> None:
    """Affiche le dashboard d'alertes via Streamlit."""
    import pandas as pd
    import streamlit as st

    st.markdown("## 🚨 Alert Dashboard — Supervision & Auto-Heal")
    entries = load_audit()
    if not entries:
        st.info("Aucune alerte enregistrée dans le fichier d'audit.")
        return

    pd.DataFrame(entries)

    # Filtres sidebar
    modules = sorted(
        {e.get("alert", {}).get("module", "") for e in entries if e.get("alert")}
    )
    severities = sorted(
        {e.get("alert", {}).get("severity", "") for e in entries if e.get("alert")}
    )

    selected_module = st.selectbox("Filtrer par module", ["Tous"] + modules)
    selected_severity = st.selectbox("Filtrer par gravité", ["Toutes"] + severities)

    filtered = entries
    if selected_module != "Tous":
        filtered = filter_by_module(filtered, selected_module)
    if selected_severity != "Toutes":
        filtered = filter_by_severity(filtered, selected_severity)

    st.markdown(f"**{len(filtered)} alerte(s) affichée(s)**")
    if filtered:
        df_filtered = pd.DataFrame(filtered)
        st.dataframe(df_filtered, use_container_width=True)
        csv = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Exporter CSV", data=csv, file_name="alertes.csv", mime="text/csv"
        )
