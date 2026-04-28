"""
Module : sensitivity_analysis.py
Analyse de sensibilité des hyperparamètres sur la performance (partial dependence plot).
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import PartialDependenceDisplay


def plot_sensitivity(sim_csv_dir="sim_summaries", output_file="sensitivity_plot.png"):
    csv_files = [f for f in os.listdir(sim_csv_dir) if f.endswith(".csv")]
    if not csv_files:
        print("Aucun fichier de simulation trouvé.")
        return
    sim_dfs = [pd.read_csv(os.path.join(sim_csv_dir, f)) for f in csv_files]
    sim_df = pd.concat(sim_dfs, ignore_index=True)
    exclude_cols = {"run", "seed", "best_fitness"}
    feat_cols = [
        col
        for col in sim_df.select_dtypes(include=["number"]).columns
        if col not in exclude_cols
    ]
    if len(feat_cols) < 1:
        print("Pas assez de paramètres numériques pour l'analyse de sensibilité.")
        return
    X = sim_df[feat_cols]
    y = sim_df["best_fitness"]
    model = RandomForestRegressor(n_estimators=100)
    model.fit(X, y)
    fig, ax = plt.subplots(figsize=(8, 5))
    PartialDependenceDisplay.from_estimator(model, X, features=feat_cols, ax=ax)
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Analyse de sensibilité sauvegardée : {output_file}")


if __name__ == "__main__":
    plot_sensitivity()
