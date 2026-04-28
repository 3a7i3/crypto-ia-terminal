"""
Module : timeline_animation.py
Timeline interactive (animation de l’évolution des stratégies).
"""

import os

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import pandas as pd


def animate_evolution(
    sim_csv_dir="sim_summaries", output_file="timeline_animation.mp4"
):
    csv_files = [f for f in os.listdir(sim_csv_dir) if f.endswith(".csv")]
    if not csv_files:
        print("Aucun fichier de simulation trouvé.")
        return
    sim_dfs = [pd.read_csv(os.path.join(sim_csv_dir, f)) for f in csv_files]
    sim_df = pd.concat(sim_dfs, ignore_index=True)
    if "generation" not in sim_df.columns or "best_fitness" not in sim_df.columns:
        print("Colonnes 'generation' ou 'best_fitness' manquantes.")
        return
    generations = sorted(sim_df["generation"].unique())
    fig, ax = plt.subplots(figsize=(8, 5))

    def update(gen):
        ax.clear()
        df = sim_df[sim_df["generation"] == gen]
        ax.hist(df["best_fitness"], bins=20, color="blue", alpha=0.7)
        ax.set_title(f"Distribution fitness - Génération {gen}")
        ax.set_xlabel("Fitness")
        ax.set_ylabel("Nombre de stratégies")

    ani = animation.FuncAnimation(fig, update, frames=generations, repeat=False)
    ani.save(output_file, writer="ffmpeg")
    print(f"Animation sauvegardée : {output_file}")


if __name__ == "__main__":
    animate_evolution()
