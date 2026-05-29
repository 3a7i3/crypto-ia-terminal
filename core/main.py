"""
Module: main.py
Point d'entrée principal du programme (orchestration, boucle principale, logs, etc.)
"""

import json
import logging
import pickle
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TypeAlias, cast

import pandas as pd

from config_utils import parse_args, read_config
import evolution_core as _evolution_core
import visualization as _visualization

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class GenomeLike(Protocol):
    id: str
    genes: dict[str, Any]
    fitness: float
    parent_ids: list[str]

    def copy(self) -> "GenomeLike": ...


WorldName: TypeAlias = str
RowDict: TypeAlias = dict[str, Any]
Population: TypeAlias = list[GenomeLike]
PopulationMap: TypeAlias = dict[WorldName, Population]
EnvironmentMap: TypeAlias = dict[WorldName, str]
HistoryMap: TypeAlias = dict[WorldName, list[pd.DataFrame]]
ScoreFn: TypeAlias = Callable[[GenomeLike], float]
CreatePopulationFn: TypeAlias = Callable[[int], Population]
ApplyExtinctionFn: TypeAlias = Callable[[Population, int], Population]
SelectParentsFn: TypeAlias = Callable[[Population], tuple[GenomeLike, GenomeLike]]
EvolveWorldFn: TypeAlias = Callable[
    [
        Population,
        str,
        ScoreFn,
        ScoreFn,
        ScoreFn,
        ApplyExtinctionFn,
        SelectParentsFn,
        type[GenomeLike],
    ],
    tuple[Population, str],
]
MigrationFn: TypeAlias = Callable[..., PopulationMap]
PlotFn: TypeAlias = Callable[..., None]

_evolution_core_any = cast(Any, _evolution_core)
_visualization_any = cast(Any, _visualization)

Genome = cast(type[GenomeLike], _evolution_core_any.Genome)
create_population = cast(CreatePopulationFn, _evolution_core_any.create_population)
apply_extinction = cast(ApplyExtinctionFn, _evolution_core_any.apply_extinction)
evolve_world = cast(EvolveWorldFn, _evolution_core_any.evolve_world)
migrate = cast(MigrationFn, _evolution_core_any.migrate)
score_env_crash = cast(ScoreFn, _evolution_core_any.score_env_crash)
score_env_range = cast(ScoreFn, _evolution_core_any.score_env_range)
score_env_trend = cast(ScoreFn, _evolution_core_any.score_env_trend)
select_parents = cast(SelectParentsFn, _evolution_core_any.select_parents)
plot_dominance = cast(PlotFn, _visualization_any.plot_dominance)
plot_god_mode = cast(Callable[..., None], _visualization_any.plot_god_mode)


def _species_name(genome: GenomeLike) -> str:
    return str(genome.genes.get("entry.type", "unknown"))


def _genome_row(genome: GenomeLike, environment: str, world: WorldName) -> RowDict:
    row: RowDict = dict(genome.genes)
    row.update(
        {
            "fitness": genome.fitness,
            "id": genome.id,
            "environment": environment,
            "species": _species_name(genome),
            "world": world,
            "parent_ids": ",".join(str(parent_id) for parent_id in genome.parent_ids),
        }
    )
    return row


def main():
    args = parse_args()
    config = read_config(args.config)
    if config is None:
        logging.error("Impossible de lire la configuration.")
        return
    pop_size = args.pop_size or config.getint("simulation", "pop_size", fallback=100)
    n_generations = args.n_gen or config.getint("simulation", "n_gen", fallback=100)
    migration_freq = args.migration_freq or config.getint(
        "simulation", "migration_freq", fallback=5
    )
    migration_rate = args.migration_rate or config.getfloat(
        "simulation", "migration_rate", fallback=0.1
    )
    show_plots = args.show_plots or config.getboolean(
        "visualization", "show_plots", fallback=True
    )
    save_frequency = 10  # sauvegarde toutes les 10 générations
    resume_file = Path("evo_state.pkl")
    results_dir = Path("results")
    world_names: list[WorldName] = ["trend", "range", "crash", "chaos"]
    if pop_size <= 0 or n_generations <= 0:
        logging.error("Paramètres incohérents : pop_size et n_gen doivent être > 0.")
        return
    results_dir.mkdir(exist_ok=True)

    # Reprise si --resume
    start_gen = 0
    populations: PopulationMap
    envs: EnvironmentMap
    if getattr(args, "resume", False) and resume_file.exists():
        populations, envs, start_gen = load_state(resume_file)
        logging.info(f"Simulation reprise à la génération {start_gen}")
    else:
        populations = {world: create_population(pop_size) for world in world_names}
        envs = {world: world for world in world_names}

    histories: HistoryMap = {world: [] for world in world_names}
    for generation in range(start_gen, n_generations):
        for world in world_names:
            population, current_env = evolve_world(
                populations[world],
                envs[world],
                score_env_trend,
                score_env_range,
                score_env_crash,
                apply_extinction,
                select_parents,
                Genome,
            )
            populations[world] = population
            envs[world] = current_env

        if (generation + 1) % migration_freq == 0:
            populations = migrate(
                populations, migration_rate=migration_rate, pop_size=pop_size
            )
            logging.info(
                f"\n🌐 MIGRATION entre mondes à la génération {generation+1}\n"
            )

        for world in world_names:
            pop = populations[world]
            pop_data: list[RowDict] = []
            for genome in pop:
                pop_data.append(_genome_row(genome, envs[world], world))

            df = pd.DataFrame(pop_data)
            histories[world].append(df)
            species_counts = pd.Series(
                [_species_name(genome) for genome in pop]
            ).value_counts().to_dict()
            best = max(pop, key=lambda genome: genome.fitness)
            logging.info(
                f"[MONDE: {world}] Gen {generation} | Env: {envs[world]} | Best fitness: {best.fitness:.4f} | Species: {_species_name(best)} | Species counts: {species_counts} | Best ID: {best.id}"
            )
            df.to_csv(results_dir / f"{world}_pop_gen_{generation}.csv", index=False)

        # Sauvegarde automatique
        if (generation + 1) % save_frequency == 0:
            save_state(resume_file, populations, envs, generation + 1)
            logging.info(f"[SAUVEGARDE] État sauvegardé à la génération {generation+1}")

    # Export best strategies
    best_strategies: dict[str, RowDict] = {}
    for world in world_names:
        history = histories[world]
        last_df = history[-1] if history else pd.DataFrame()
        if (
            not last_df.empty
            and "fitness" in last_df.columns
            and not cast(Any, last_df["fitness"]).isnull().all()
        ):
            best_row = cast(
                RowDict,
                cast(Any, last_df.loc[cast(Any, last_df["fitness"]).idxmax()]).to_dict(),
            )
            best_strategies[world] = best_row
        else:
            logging.warning(
                f"Aucun survivant ou colonne 'fitness' manquante pour le monde {world}"
            )

    with open(results_dir / "best_strategies_cross_world.json", "w", encoding="utf-8") as f:
        json.dump(best_strategies, f, indent=2, ensure_ascii=False)
    logging.info(
        "[EXPORT] Meilleurs survivants cross-monde exportés dans results/best_strategies_cross_world.json"
    )

    # Optionnel : visualisation finale
    for world in world_names:
        history = histories[world]
        if history:
            plot_god_mode(history[-1], show_plots=show_plots)

    # Visualisation domination (toutes générations)
    frames = [
        df.assign(world=world, generation=index)
        for world, history in histories.items()
        for index, df in enumerate(history)
    ]
    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        plot_dominance(all_df, show_plots=show_plots)
    logging.info("Simulation terminée.")


def save_state(
    filename: Path | str,
    populations: PopulationMap,
    envs: EnvironmentMap,
    generation: int,
) -> None:
    with open(filename, "wb") as f:
        pickle.dump(
            {"populations": populations, "envs": envs, "generation": generation}, f
        )


def load_state(filename: Path | str) -> tuple[PopulationMap, EnvironmentMap, int]:
    with open(filename, "rb") as f:
        state = cast(dict[str, Any], pickle.load(f))
    return state["populations"], state["envs"], state["generation"]


if __name__ == "__main__":
    main()
    