"""
Module: visualization.py
Contient les fonctions de visualisation (plots, exports)
"""

import matplotlib.pyplot as plt


def plot_god_mode(df, tracked_id=None, show_plots=True):

    if not all(
        col in df.columns for col in ["exit.tp", "exit.sl", "fitness", "species"]
    ):
        print("[plot_god_mode] Colonnes manquantes dans le DataFrame!")
        return
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    species_list = df["species"].unique()
    cmap = plt.get_cmap("tab20") if len(species_list) > 10 else plt.get_cmap("tab10")
    colors = [cmap(i % cmap.N) for i in range(len(species_list))]
    for i, species in enumerate(species_list):
        sub = df[df["species"] == species]
        ax.scatter(
            sub["exit.tp"],
            sub["exit.sl"],
            sub["fitness"],
            label=species,
            color=colors[i],
            alpha=0.7,
        )
    if tracked_id and tracked_id in df["id"].values:
        tracked = df[df["id"] == tracked_id]
        ax.scatter(
            tracked["exit.tp"],
            tracked["exit.sl"],
            tracked["fitness"],
            color="red",
            s=120,
            marker="*",
            label="Tracked",
        )
    ax.set_xlabel("Take Profit")
    ax.set_ylabel("Stop Loss")
    ax.set_zlabel("Fitness")
    ax.set_title("GOD MODE: 3D Evolutionary Strategies")
    ax.legend()
    plt.tight_layout()
    plt.savefig("results/god_mode_3d.png")
    print("[plot_god_mode] Graphique exporté : results/god_mode_3d.png")
    if show_plots:
        plt.show()
    else:
        plt.close()


def plot_dominance(full_df, show_plots=True):
    if not all(col in full_df.columns for col in ["generation", "species"]):
        print("[plot_dominance] Colonnes manquantes dans le DataFrame!")
        return
    pivot = full_df.groupby(["generation", "species"]).size().unstack(fill_value=0)
    pivot.plot(kind="area", stacked=True, colormap="tab20", figsize=(12, 6))
    plt.title("Domination par espèce au fil des générations")
    plt.xlabel("Génération")
    plt.ylabel("Nombre d'individus")
    plt.legend(title="Espèce", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig("results/dominance_by_species.png")
    print("[plot_dominance] Graphique exporté : results/dominance_by_species.png")
    if show_plots:
        plt.show()
    else:
        plt.close()
