"""
Module : automl_tuning.py
AutoML/Auto-tuning (grid search) pour optimiser les hyperparamètres automatiquement.
"""

import os

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import ParameterGrid


def automl_grid_search(
    sim_csv_dir="sim_summaries", param_grid=None, output_file="automl_results.csv"
):
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
        print("Pas assez de paramètres numériques pour l'AutoML.")
        return
    X = sim_df[feat_cols]
    y = sim_df["best_fitness"]
    if param_grid is None:
        param_grid = {"n_estimators": [50, 100], "max_depth": [3, 5, None]}
    results = []
    for params in ParameterGrid(param_grid):
        model = RandomForestRegressor(**params)
        model.fit(X, y)
        score = model.score(X, y)
        results.append({**params, "score": score})
    results_df = pd.DataFrame(results)
    results_df.to_csv(output_file, index=False)
    print(f"AutoML résultats sauvegardés : {output_file}")


if __name__ == "__main__":
    automl_grid_search()
