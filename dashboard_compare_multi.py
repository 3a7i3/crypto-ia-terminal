import os

import pandas as pd
import streamlit as st

# --- Comparatif multi-simulations ---
with st.container():
    st.markdown("### 📊 Comparatif multi-simulations")
    sim_dir = "sim_summaries"
    if os.path.exists(sim_dir):
        sim_files = [f for f in os.listdir(sim_dir) if f.endswith(".csv")]
        if sim_files:
            sim_dfs = [pd.read_csv(os.path.join(sim_dir, f)) for f in sim_files]
            sim_df = pd.concat(sim_dfs, ignore_index=True)
            st.dataframe(sim_df)
            # Bar chart des meilleurs fitness
            st.markdown("#### 🏅 Meilleur fitness par simulation")
            st.bar_chart(sim_df.set_index("run")["best_fitness"])
            # Scatter plot best_fitness vs std_fitness
            import plotly.express as px

            fig = px.scatter(
                sim_df,
                x="std_fitness",
                y="best_fitness",
                hover_data=["run", "seed"],
                title="Best fitness vs Std fitness",
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Aucun résumé de simulation trouvé dans sim_summaries/.")
    else:
        st.info(
            "Dossier sim_summaries/ introuvable. Lancez run_multi_simulations.py pour générer des runs."
        )
