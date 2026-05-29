"""
Module : export_excel_report.py
Exporte les résultats multi-simulations dans un fichier Excel multi-feuilles.
"""

import os

import numpy as np
import pandas as pd
from pandas import ExcelWriter


def export_excel_report(
    sim_dir="sim_summaries", output_file="rapport_simulations.xlsx"
):
    sim_files = [f for f in os.listdir(sim_dir) if f.endswith(".csv")]
    if not sim_files:
        print("Aucun fichier de simulation trouvé.")
        return
    sim_dfs = [pd.read_csv(os.path.join(sim_dir, f)) for f in sim_files]
    sim_df = pd.concat(sim_dfs, ignore_index=True)
    # Synthèse
    synthese = pd.DataFrame(
        {
            "Nb runs": [len(sim_df)],
            "Fitness moyen": [sim_df["best_fitness"].mean()],
            "Fitness max": [sim_df["best_fitness"].max()],
            "Fitness min": [sim_df["best_fitness"].min()],
        }
    )
    # Corrélations
    exclude_cols = {
        "run",
        "seed",
        "elite_ratio",
        "mutation_base",
        "stagnation_patience",
        "pop_size",
        "n_generations",
    }
    num_cols = [
        col
        for col in sim_df.select_dtypes(include=["number"]).columns
        if col not in exclude_cols
    ]
    corr = sim_df[num_cols].corr() if len(num_cols) >= 2 else pd.DataFrame()
    # Top stratégies (best fitness)
    top_strat = sim_df.sort_values("best_fitness", ascending=False).head(20)
    # Export Excel
    with ExcelWriter(output_file) as writer:
        synthese.to_excel(writer, sheet_name="Synthese", index=False)
        sim_df.to_excel(writer, sheet_name="Tous_Runs", index=False)
        top_strat.to_excel(writer, sheet_name="Top_Strategies", index=False)
        if not corr.empty:
            corr.to_excel(writer, sheet_name="Correlations")
    print(f"Rapport Excel généré : {output_file}")


if __name__ == "__main__":
    export_excel_report()
