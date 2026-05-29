"""
Module : pareto_front.py
Exploration multi-objectifs (front de Pareto) pour comparer les stratégies sur plusieurs métriques.
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_pareto(
    sim_csv_dir="sim_summaries",
    x_metric="best_fitness",
    y_metric="drawdown",
    output_file="pareto_front.png",
):
    csv_files = [f for f in os.listdir(sim_csv_dir) if f.endswith(".csv")]
    if not csv_files:
        print("Aucun fichier de simulation trouvé.")
        return
    sim_dfs = [pd.read_csv(os.path.join(sim_csv_dir, f)) for f in csv_files]
    sim_df = pd.concat(sim_dfs, ignore_index=True)
    if x_metric not in sim_df.columns or y_metric not in sim_df.columns:
        print(f"Colonnes {x_metric} ou {y_metric} manquantes.")
        return
    x = sim_df[x_metric]
    y = sim_df[y_metric]
    is_pareto = np.ones(x.shape[0], dtype=bool)
    for i, (xi, yi) in enumerate(zip(x, y)):
        is_pareto[i] = np.all((x >= xi) | (y <= yi))
    plt.figure(figsize=(8, 5))
    plt.scatter(x, y, c="gray", label="Stratégies")
    plt.scatter(x[is_pareto], y[is_pareto], c="red", label="Front de Pareto")
    plt.xlabel(x_metric)
    plt.ylabel(y_metric)
    plt.title("Front de Pareto")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Front de Pareto sauvegardé : {output_file}")


if __name__ == "__main__":
    plot_pareto()
