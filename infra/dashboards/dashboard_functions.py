"""
dashboard_functions.py — Fonctions pures d'analyse et de visualisation,
extraites de streamlit_dashboard.py pour pouvoir être testées sans runtime Streamlit.
"""

from __future__ import annotations

import pandas as pd


def visualisation_3d(df: pd.DataFrame) -> None:
    """Affiche un scatter 3D TP/SL/Fitness via Plotly."""
    import streamlit as st

    required = {"exit.tp", "exit.sl", "fitness"}
    missing = required - set(df.columns)
    if missing:
        st.warning(f"Colonnes manquantes pour la 3D : {missing}")
        return
    try:
        import plotly.express as px

        fig = px.scatter_3d(
            df,
            x="exit.tp",
            y="exit.sl",
            z="fitness",
            color="fitness",
            title="Visualisation 3D TP/SL/Fitness",
        )
        st.plotly_chart(fig, width="stretch")
    except ImportError:
        st.error("plotly requis : pip install plotly")
    except Exception as e:
        st.warning(f"Erreur visualisation 3D : {e}")


def stats_par_espece(df: pd.DataFrame) -> None:
    """Affiche les statistiques groupées par espèce."""
    import streamlit as st

    if "species" not in df.columns:
        st.info("Colonne 'species' absente — stats globales affichées.")
        st.dataframe(df.describe(), width="stretch")
        return
    stats = df.groupby("species").agg(["mean", "std", "count"]).round(4)
    st.dataframe(stats, width="stretch")


def top5_et_heatmap(df: pd.DataFrame) -> None:
    """Affiche le top 5 des stratégies et une heatmap de corrélation."""
    import streamlit as st

    num_cols = df.select_dtypes(include="number").columns.tolist()
    if not num_cols:
        st.warning("Aucune colonne numérique disponible.")
        return
    sort_col = "fitness" if "fitness" in df.columns else num_cols[0]
    top5 = df.nlargest(5, sort_col) if sort_col in df.columns else df.head(5)
    st.markdown("#### Top 5 stratégies")
    st.dataframe(top5, width="stretch")
    if len(num_cols) >= 2:
        try:
            import plotly.express as px

            corr = df[num_cols].corr().round(2)
            fig = px.imshow(corr, text_auto=True, title="Heatmap de corrélation")
            st.plotly_chart(fig, width="stretch")
        except ImportError:
            st.error("plotly requis : pip install plotly")
        except Exception as e:
            st.warning(f"Erreur heatmap : {e}")


def evolution_fitness(df: pd.DataFrame) -> None:
    """Trace l'évolution de la fitness par génération."""
    import streamlit as st

    if "generation" not in df.columns:
        st.warning("Colonne 'generation' absente — impossible de tracer l'évolution.")
        return
    if "fitness" not in df.columns:
        st.warning("Colonne 'fitness' absente.")
        return
    try:
        import plotly.express as px

        grouped = df.groupby("generation")["fitness"].mean().reset_index()
        fig = px.line(
            grouped,
            x="generation",
            y="fitness",
            title="Évolution de la fitness par génération",
        )
        st.plotly_chart(fig, width="stretch")
    except ImportError:
        st.error("plotly requis : pip install plotly")
    except Exception as e:
        st.warning(f"Erreur courbe fitness : {e}")


def comparatif_multi_simulations(df: pd.DataFrame) -> None:
    """Affiche un comparatif statistique et une distribution de fitness."""
    import streamlit as st

    if df.empty:
        st.info("DataFrame vide — aucune simulation à comparer.")
        return
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if not num_cols:
        st.warning("Aucune colonne numérique pour le comparatif.")
        return
    st.markdown("#### Statistiques comparatives")
    st.dataframe(df[num_cols].describe().round(4), width="stretch")
    if "fitness" in df.columns:
        try:
            import plotly.express as px

            fig = px.histogram(df, x="fitness", title="Distribution de la fitness")
            st.plotly_chart(fig, width="stretch")
        except ImportError:
            pass


def import_export_csv(df: pd.DataFrame) -> None:
    """Permet l'import et l'export de fichiers CSV."""
    import streamlit as st

    st.markdown("#### Import / Export CSV")
    if not df.empty:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Télécharger CSV", data=csv_bytes, file_name="export.csv", mime="text/csv"
        )
    uploaded = st.file_uploader("Importer un CSV", type="csv", key="csv_uploader")
    if uploaded is not None:
        try:
            imported = pd.read_csv(uploaded)
            st.success(
                f"Fichier importé : {len(imported)} lignes × {len(imported.columns)} colonnes"
            )
            st.dataframe(imported.head(20), width="stretch")
        except Exception as e:
            st.error(f"Erreur d'import : {e}")
