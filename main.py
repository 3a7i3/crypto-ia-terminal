"""
Module: main.py
Point d'entrée principal du programme (orchestration, boucle principale, logs, etc.)
"""

import json
import logging
import os
import pickle

import pandas as pd

from config_utils import parse_args, read_config
from evolution_core import (Genome, apply_extinction, create_population,
                            crossover, evolve_world, migrate, mutate,
                            score_env_crash, score_env_range, score_env_trend,
                            select_parents)
from visualization import plot_dominance, plot_god_mode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    args = parse_args()
    config = read_config(args.config)
    if config is None:
        logging.error("Impossible de lire la configuration.")
        return
    POP_SIZE = args.pop_size or config.getint("simulation", "pop_size", fallback=100)
    N_GEN = args.n_gen or config.getint("simulation", "n_gen", fallback=100)
    MIGRATION_FREQ = args.migration_freq or config.getint(
        "simulation", "migration_freq", fallback=5
    )
    MIGRATION_RATE = args.migration_rate or config.getfloat(
        "simulation", "migration_rate", fallback=0.1
    )
    SHOW_PLOTS = args.show_plots or config.getboolean(
        "visualization", "show_plots", fallback=True
    )
    SAVE_FREQ = 10  # sauvegarde toutes les 10 générations
    RESUME_FILE = "evo_state.pkl"
    WORLD_NAMES = ["trend", "range", "crash", "chaos"]
    if POP_SIZE <= 0 or N_GEN <= 0:
        logging.error("Paramètres incohérents : pop_size et n_gen doivent être > 0.")
        return
    if not os.path.exists("results"):
        os.makedirs("results")
    # Reprise si --resume
    start_gen = 0
    if hasattr(args, "resume") and args.resume and os.path.exists(RESUME_FILE):
        populations, envs, start_gen = load_state(RESUME_FILE)
        logging.info(f"Simulation reprise à la génération {start_gen}")
    else:
        populations = {w: create_population(POP_SIZE) for w in WORLD_NAMES}
        envs = {w: w for w in WORLD_NAMES}
    histories = {w: [] for w in WORLD_NAMES}
    for generation in range(start_gen, N_GEN):
        for w in WORLD_NAMES:
            populations[w], envs[w] = evolve_world(
                populations[w],
                envs[w],
                score_env_trend,
                score_env_range,
                score_env_crash,
                apply_extinction,
                select_parents,
                Genome,
            )
        if (generation + 1) % MIGRATION_FREQ == 0:
            populations = migrate(
                populations, migration_rate=MIGRATION_RATE, pop_size=POP_SIZE
            )
            logging.info(
                f"\n🌐 MIGRATION entre mondes à la génération {generation+1}\n"
            )
        for w in WORLD_NAMES:
            pop = populations[w]
            pop_data = []
            for g in pop:
                row = {
                    **g.genes,
                    "fitness": g.fitness,
                    "id": g.id,
                    "environment": envs[w],
                    "species": g.genes["entry.type"],
                    "world": w,
                    "parent_ids": (
                        ",".join(g.parent_ids) if hasattr(g, "parent_ids") else ""
                    ),
                }
                pop_data.append(row)
            df = pd.DataFrame(pop_data)
            histories[w].append(df)
            species_counts = (
                pd.Series([g.genes["entry.type"] for g in pop]).value_counts().to_dict()
            )
            best = max(pop, key=lambda g: g.fitness)
            logging.info(
                f"[MONDE: {w}] Gen {generation} | Env: {envs[w]} | Best fitness: {best.fitness:.4f} | Species: {best.genes['entry.type']} | Species counts: {species_counts} | Best ID: {best.id}"
            )
            df.to_csv(f"results/{w}_pop_gen_{generation}.csv", index=False)
        # Sauvegarde automatique
        if (generation + 1) % SAVE_FREQ == 0:
            save_state(RESUME_FILE, populations, envs, generation + 1)
            logging.info(f"[SAUVEGARDE] État sauvegardé à la génération {generation+1}")
    # Export best strategies
    best_strategies = {}
    for w in WORLD_NAMES:
        last_df = histories[w][-1] if histories[w] else pd.DataFrame()
        if (
            not last_df.empty
            and "fitness" in last_df.columns
            and not last_df["fitness"].isnull().all()
        ):
            best = last_df.loc[last_df["fitness"].idxmax()]
            best_strategies[w] = best.to_dict()
        else:
            logging.warning(
                f"Aucun survivant ou colonne 'fitness' manquante pour le monde {w}"
            )
    with open("results/best_strategies_cross_world.json", "w", encoding="utf-8") as f:
        json.dump(best_strategies, f, indent=2, ensure_ascii=False)
    logging.info(
        "[EXPORT] Meilleurs survivants cross-monde exportés dans results/best_strategies_cross_world.json"
    )
    # Optionnel : visualisation finale
    for w in WORLD_NAMES:
        if histories[w]:
            plot_god_mode(histories[w][-1], show_plots=SHOW_PLOTS)
    # Visualisation domination (toutes générations)
    all_df = pd.concat(
        [
            df.assign(world=w, generation=i)
            for w, hist in histories.items()
            for i, df in enumerate(hist)
        ],
        ignore_index=True,
    )
    plot_dominance(all_df, show_plots=SHOW_PLOTS)
    logging.info("Simulation terminée.")


def save_state(filename, populations, envs, generation):
    with open(filename, "wb") as f:
        pickle.dump(
            {"populations": populations, "envs": envs, "generation": generation}, f
        )


def load_state(filename):
    with open(filename, "rb") as f:
        state = pickle.load(f)
    return state["populations"], state["envs"], state["generation"]


if __name__ == "__main__":
    main()
