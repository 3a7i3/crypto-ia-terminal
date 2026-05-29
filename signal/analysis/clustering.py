"""
Module : clustering.py
Clustering des stratégies (KMeans + t-SNE) pour visualiser les familles de solutions.
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE


def plot_clustering(
    sim_csv_dir="sim_summaries", n_clusters=4, output_file="clustering_plot.png"
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
    if len(feat_cols) < 2:
        print("Pas assez de paramètres numériques pour le clustering.")
        return
    X = sim_df[feat_cols].fillna(0)
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    labels = kmeans.fit_predict(X)
    tsne = TSNE(n_components=2, random_state=42)
    X_embedded = tsne.fit_transform(X)
    plt.figure(figsize=(8, 5))
    for i in range(n_clusters):
        plt.scatter(
            X_embedded[labels == i, 0],
            X_embedded[labels == i, 1],
            label=f"Cluster {i+1}",
        )
    plt.title("Clustering des stratégies (t-SNE)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Clustering sauvegardé : {output_file}")


if __name__ == "__main__":
    plot_clustering()
