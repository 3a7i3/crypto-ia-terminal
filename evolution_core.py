"""
Module: evolution_core.py
Contient la logique évolutionnaire (Genome, mutation, crossover, fitness, extinction, évolution, etc.)
"""

import json
import logging
import os
import random
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("evolution_core")


class GenomeSerializer:
    """Sérialisation JSON des Genome — sûr, lisible, versionné."""

    VERSION = 1

    @staticmethod
    def to_dict(genome) -> dict:
        return {
            "_version": GenomeSerializer.VERSION,
            "id": genome.id,
            "genes": genome.genes,
            "fitness": genome.fitness,
            "fitness_trend": genome.fitness_trend,
            "fitness_range": genome.fitness_range,
            "fitness_crash": genome.fitness_crash,
            "parent_ids": genome.parent_ids,
        }

    @staticmethod
    def from_dict(d: dict):
        g = Genome(genes=d["genes"])
        g.id = d["id"]
        g.fitness = d["fitness"]
        g.fitness_trend = d.get("fitness_trend", 0.0)
        g.fitness_range = d.get("fitness_range", 0.0)
        g.fitness_crash = d.get("fitness_crash", 0.0)
        g.parent_ids = d.get("parent_ids", [])
        return g

    @staticmethod
    def save_population(population: list, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "_version": GenomeSerializer.VERSION,
            "size": len(population),
            "genomes": [GenomeSerializer.to_dict(g) for g in population],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def load_population(path: str | Path) -> list:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return [GenomeSerializer.from_dict(d) for d in data["genomes"]]


# 1. GeneSpace (l'univers des gènes)
GENE_SPACE = {
    "entry.type": ["trend", "mean_reversion", "hybrid"],
    "entry.rsi_period": (5, 30),
    "entry.rsi_buy": (30, 70),
    "ma_short": (5, 50),
    "ma_long": (20, 200),
    "ma_signal": ["cross_over", "cross_under"],
    "exit.tp": (0.5, 5.0),
    "exit.sl": (0.3, 3.0),
    "risk.risk_per_trade": (0.001, 0.03),
}

# --- Fonctions d'évolution, fitness, marché, backtest, etc. ---


def get_random_environment():
    """Retourne un environnement aléatoire parmi trend, range, crash."""
    return random.choice(["trend", "range", "crash"])


def migrate(populations, migration_rate=0.1, pop_size=100):
    """Migre un pourcentage d'individus entre les mondes pour favoriser la diversité."""
    world_names = list(populations.keys())
    n_migrate = max(1, int(pop_size * migration_rate))
    migrants = {
        w: sorted(populations[w], key=lambda g: g.fitness, reverse=True)[:n_migrate]
        for w in world_names
    }
    for i, w in enumerate(world_names):
        next_w = world_names[(i + 1) % len(world_names)]
        populations[next_w][-n_migrate:] = [g.copy() for g in migrants[w]]
    return populations


def evolve_world(
    pop,
    env,
    score_env_trend,
    score_env_range,
    score_env_crash,
    apply_extinction,
    select_parents,
    Genome,
    elite_ratio=0.1,
    mutation_base=0.3,
    stagnation_patience=10,
    fitness_history=None,
):
    """Fait évoluer une population dans un monde donné (environnement)."""
    if env == "chaos":
        current_env = get_random_environment()
    else:
        current_env = env
    for g in pop:
        if current_env == "trend":
            g.fitness = float(score_env_trend(g))
        elif current_env == "range":
            g.fitness = float(score_env_range(g))
        elif current_env == "crash":
            g.fitness = float(score_env_crash(g))
    pop.sort(key=lambda g: g.fitness, reverse=True)
    # --- Sélection élitiste configurable ---
    N_ELITE = max(1, int(len(pop) * elite_ratio))
    survivors = pop[:N_ELITE]
    logger.info("evolve_world: sélection élitiste %d/%d", N_ELITE, len(pop))
    survivors = apply_extinction(survivors)
    logger.info("evolve_world: après extinction %d survivants", len(survivors))
    if not survivors:
        survivors = pop[: min(3, len(pop))]
        logger.warning("evolve_world: extinction totale, conservation des 3 meilleurs")

    # --- Mutation adaptative ---
    alert_stagnation = False
    alert_extinction = False
    alert_surperformance = False
    if fitness_history is not None and len(fitness_history) >= stagnation_patience:
        best_fitness = max(fitness_history)
        if all(
            abs(f - best_fitness) < 1e-6 for f in fitness_history[-stagnation_patience:]
        ):
            logger.warning(
                "evolve_world: stagnation sur %d générations — extinction dynamique",
                stagnation_patience,
            )
            alert_stagnation = True
            # extinction dynamique : on ne garde que 1 élite
            survivors = pop[:1]
            mutation_rate = min(1.0, mutation_base * 2)
            alert_extinction = True
        else:
            mutation_rate = mutation_base * (
                0.5
                + 0.5
                * (
                    1
                    - np.std([g.fitness for g in pop])
                    / (np.mean([g.fitness for g in pop]) + 1e-8)
                )
            )
        # Surperformance : record battu
        if pop[0].fitness > best_fitness:
            logger.info("evolve_world: nouveau record de fitness %.4f", pop[0].fitness)
            alert_surperformance = True
    else:
        mutation_rate = mutation_base
    logger.debug("evolve_world: mutation adaptative taux=%.3f", mutation_rate)

    new_pop = survivors.copy()
    while len(new_pop) < len(pop) - 2:
        if len(survivors) == 0:
            p1 = p2 = random.choice(pop)
        else:
            p1, p2 = select_parents(survivors)
        logger.debug("evolve_world: croisement %s x %s", p1.id, p2.id)
        child = crossover(p1, p2)
        child = mutate(child, mutation_rate=float(mutation_rate), intensity=0.2)
        if current_env == "trend":
            child.fitness = float(score_env_trend(child))
        elif current_env == "range":
            child.fitness = float(score_env_range(child))
        elif current_env == "crash":
            child.fitness = float(score_env_crash(child))
        new_pop.append(child)
    for _ in range(2):
        g = Genome()
        if current_env == "trend":
            g.fitness = float(score_env_trend(g))
        elif current_env == "range":
            g.fitness = float(score_env_range(g))
        elif current_env == "crash":
            g.fitness = float(score_env_crash(g))
        logger.debug("evolve_world: nouvel individu aléatoire %s", g.id)
        new_pop.append(g)
    logger.info("evolve_world: nouvelle population %d individus", len(new_pop))
    # --- Sauvegarde automatique de la population ---
    try:
        GenomeSerializer.save_population(new_pop, f"checkpoints/pop_{current_env}.json")
        logger.info(
            "evolve_world: population sauvegardée checkpoints/pop_%s.json", current_env
        )
    except Exception as e:
        logger.error("evolve_world: erreur sauvegarde: %s", e)
    return new_pop, current_env


def generate_trend_market(length=500):
    """Génère une série de prix simulant un marché haussier (trend)."""
    prices = [100.0]
    for _ in range(length):
        change = np.random.normal(0.05, 1)
        prices.append(prices[-1] * (1 + change * 0.01))
    return np.array(prices)


def generate_range_market(length=500):
    """Génère une série de prix simulant un marché range (oscillant)."""
    prices = [100.0]
    for _ in range(length):
        change = np.random.normal(0, 0.5)
        prices.append(prices[-1] * (1 + change * 0.01))
    return np.array(prices)


def generate_crash_market(length=500):
    """Génère une série de prix simulant un crash de marché."""
    prices = [100.0]
    for i in range(length):
        if i > length // 2:
            change = np.random.normal(-0.2, 1)
        else:
            change = np.random.normal(0, 1)
        prices.append(prices[-1] * (1 + change * 0.01))
    return np.array(prices)


def compute_rsi(prices, period=14):
    """Calcule l'indicateur RSI sur une série de prix."""
    deltas = np.diff(prices)
    gains = np.maximum(deltas, 0)
    losses = -np.minimum(deltas, 0)
    avg_gain = np.convolve(gains, np.ones(period) / period, mode="valid")
    avg_loss = np.convolve(losses, np.ones(period) / period, mode="valid")
    rs = avg_gain / (avg_loss + 1e-6)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def ma_signal(prices, short, long, signal_type="cross_over"):
    """Détecte les signaux de croisement de moyennes mobiles."""
    ma_s = np.convolve(prices, np.ones(int(short)) / int(short), mode="valid")
    ma_l = np.convolve(prices, np.ones(int(long)) / int(long), mode="valid")
    min_len = min(len(ma_s), len(ma_l))
    ma_s = ma_s[-min_len:]
    ma_l = ma_l[-min_len:]
    if signal_type == "cross_over":
        return np.where(np.diff((ma_s > ma_l).astype(int)) == 1)[0] + 1
    else:
        return np.where(np.diff((ma_s < ma_l).astype(int)) == 1)[0] + 1


def backtest(genome, prices):
    """Backtest une stratégie (Genome) sur une série de prix."""
    tp = genome.get("exit.tp") / 100
    sl = genome.get("exit.sl") / 100
    capital = 1.0
    equity_curve = [capital]
    position = None
    entry_price = 0
    entry_type = genome.get("entry.type")
    rsi_period = int(genome.get("entry.rsi_period"))
    rsi_buy = genome.get("entry.rsi_buy")
    rsi = compute_rsi(prices, rsi_period)
    ma_short = int(genome.get("ma_short", 10))
    ma_long = int(genome.get("ma_long", 30))
    ma_sig = genome.get("ma_signal", "cross_over")
    ma_idx = ma_signal(prices, ma_short, ma_long, ma_sig)
    ma_idx_set = set(ma_idx)
    min_len = min(len(rsi), len(prices) - 1)
    for i in range(min_len):
        price = prices[i + 1]
        signal = False
        if entry_type == "mean_reversion":
            if rsi[i] < rsi_buy:
                signal = True
        elif entry_type == "trend":
            if i in ma_idx_set:
                signal = True
        elif entry_type == "hybrid":
            if (rsi[i] < rsi_buy) and (i in ma_idx_set):
                signal = True
        if position is None and signal:
            position = "long"
            entry_price = price
        elif position == "long":
            change = (price - entry_price) / entry_price
            if change >= tp or change <= -sl:
                capital *= 1 + change
                position = None
        equity_curve.append(capital)
    return equity_curve


def compute_drawdown(equity_curve):
    """Calcule le drawdown maximal d'une courbe d'equity."""
    equity = np.array(equity_curve)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_dd = np.min(drawdown)
    return abs(max_dd)


def compute_sharpe(equity_curve):
    """Calcule le ratio de Sharpe d'une courbe d'equity."""
    equity = np.array(equity_curve)
    returns = np.diff(equity) / equity[:-1]
    if np.std(returns) == 0:
        return 0
    sharpe = np.mean(returns) / np.std(returns)
    return sharpe


def score_env_trend(g):
    """Score de fitness dans un environnement trend."""
    prices = generate_trend_market()
    equity = backtest(g, prices)
    final_return = equity[-1]
    drawdown = compute_drawdown(equity)
    sharpe = compute_sharpe(equity)
    return final_return * 0.4 + sharpe * 0.4 - drawdown * 0.6


def score_env_range(g):
    """Score de fitness dans un environnement range."""
    prices = generate_range_market()
    equity = backtest(g, prices)
    final_return = equity[-1]
    drawdown = compute_drawdown(equity)
    sharpe = compute_sharpe(equity)
    return final_return * 0.4 + sharpe * 0.4 - drawdown * 0.6


def score_env_crash(g):
    """Score de fitness dans un environnement crash."""
    prices = generate_crash_market()
    equity = backtest(g, prices)
    final_return = equity[-1]
    drawdown = compute_drawdown(equity)
    sharpe = compute_sharpe(equity)
    return final_return * 0.4 + sharpe * 0.4 - drawdown * 0.6


def evaluate_fitness(genome):
    """Calcule et assigne la fitness multi-environnement d'un Genome."""
    trend_prices = generate_trend_market()
    range_prices = generate_range_market()
    crash_prices = generate_crash_market()

    def score_env(prices):
        equity = backtest(genome, prices)
        final_return = equity[-1]
        drawdown = compute_drawdown(equity)
        sharpe = compute_sharpe(equity)
        score = final_return * 0.4 + sharpe * 0.4 - drawdown * 0.6
        return score

    genome.fitness_trend = score_env(trend_prices)
    genome.fitness_range = score_env(range_prices)
    genome.fitness_crash = score_env(crash_prices)
    genome.fitness = (
        genome.fitness_trend + genome.fitness_range + genome.fitness_crash
    ) / 3


def _compute_evolution_params(
    population, elite_ratio, mutation_base, stagnation_patience, fitness_history
):
    """Calcule élites, taux de mutation et alertes — logique commune à evolve/enrich_evolve."""
    population.sort(key=lambda x: x.fitness, reverse=True)
    n_elite = max(1, int(len(population) * elite_ratio))
    survivors = population[:n_elite]

    alert_stagnation = False
    alert_extinction = False
    alert_surperformance = False

    if fitness_history is not None and len(fitness_history) >= stagnation_patience:
        best_fitness = max(fitness_history)
        if all(
            abs(f - best_fitness) < 1e-6 for f in fitness_history[-stagnation_patience:]
        ):
            logger.warning(
                "stagnation sur %d générations — extinction dynamique",
                stagnation_patience,
            )
            alert_stagnation = True
            alert_extinction = True
            survivors = population[:1]
            mutation_rate = min(1.0, mutation_base * 2)
        else:
            mutation_rate = mutation_base * (
                0.5
                + 0.5
                * (
                    1
                    - np.std([g.fitness for g in population])
                    / (np.mean([g.fitness for g in population]) + 1e-8)
                )
            )
        if population[0].fitness > best_fitness:
            logger.info("nouveau record de fitness %.4f", population[0].fitness)
            alert_surperformance = True
    else:
        mutation_rate = mutation_base

    logger.debug("mutation adaptative taux=%.3f", mutation_rate)
    return (
        survivors,
        n_elite,
        float(mutation_rate),
        alert_stagnation,
        alert_extinction,
        alert_surperformance,
    )


def evolve(
    population,
    elite_ratio=0.1,
    mutation_base=0.3,
    stagnation_patience=10,
    fitness_history=None,
):
    """Fait évoluer une population (fitness composite, sans stats retournées)."""
    for g in population:
        evaluate_fitness(g)
    survivors, n_elite, mutation_rate, *_ = _compute_evolution_params(
        population, elite_ratio, mutation_base, stagnation_patience, fitness_history
    )
    logger.info("evolve: sélection élitiste %d/%d", n_elite, len(population))

    new_population = list(survivors)
    while len(new_population) < len(population):
        p1, p2 = (
            select_parents(survivors)
            if len(survivors) >= 2
            else (survivors[0], survivors[0])
        )
        child = crossover(p1, p2)
        child = mutate(child, mutation_rate=mutation_rate, intensity=0.2)
        evaluate_fitness(child)
        new_population.append(child)
    logger.info("evolve: nouvelle population %d individus", len(new_population))
    return new_population


# --- Comparatif multi-simulations : fonction utilitaire ---
def save_simulation_summary(summary_dict, filename):
    """Sauvegarde un résumé de simulation (dict) dans un fichier CSV ou pickle."""
    import csv
    import os
    import pickle

    os.makedirs("sim_summaries", exist_ok=True)
    if filename.endswith(".pkl"):
        with open(os.path.join("sim_summaries", filename), "wb") as f:
            pickle.dump(summary_dict, f)
    else:
        with open(os.path.join("sim_summaries", filename), "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary_dict.keys()))
            writer.writeheader()
            writer.writerow(summary_dict)

    # Suggestion d'amélioration : ajouter l'export JSON ou Excel si besoin


def enrich_evolve(
    population,
    elite_ratio=0.1,
    mutation_base=0.3,
    stagnation_patience=10,
    fitness_history=None,
):
    """Fait évoluer une population et retourne (nouvelle_population, stats)."""
    for g in population:
        evaluate_fitness(g)
    (
        survivors,
        n_elite,
        mutation_rate,
        alert_stagnation,
        alert_extinction,
        alert_surperformance,
    ) = _compute_evolution_params(
        population, elite_ratio, mutation_base, stagnation_patience, fitness_history
    )
    logger.info("enrich_evolve: sélection élitiste %d/%d", n_elite, len(population))

    new_population = [s for s in survivors]
    while len(new_population) < len(population):
        p1, p2 = random.choice(survivors), random.choice(survivors)
        logger.debug("enrich_evolve: croisement %s x %s", p1.id, p2.id)
        child = mutate(crossover(p1, p2), mutation_rate=mutation_rate)
        evaluate_fitness(child)
        new_population.append(child)
    logger.info("enrich_evolve: nouvelle population %d individus", len(new_population))

    try:
        GenomeSerializer.save_population(new_population, "checkpoints/pop_last.json")
        logger.info("enrich_evolve: population sauvegardée checkpoints/pop_last.json")
    except Exception as e:
        logger.error("enrich_evolve: erreur sauvegarde: %s", e)

    stats = {
        "best_fitness": float(new_population[0].fitness),
        "mean_fitness": float(np.mean([g.fitness for g in new_population])),
        "std_fitness": float(np.std([g.fitness for g in new_population])),
        "n_elite": n_elite,
        "mutation_rate": mutation_rate,
        "alert_stagnation": alert_stagnation,
        "alert_extinction": alert_extinction,
        "alert_surperformance": alert_surperformance,
    }
    return new_population, stats


def create_population(size=50):
    """Crée une population initiale de Genomes aléatoires."""
    return [Genome() for _ in range(size)]


class Genome:
    """Représente un individu (stratégie) dans la population évolutionnaire."""

    def __init__(self, genes=None):
        self.id = str(uuid.uuid4())[:8]
        self.genes = genes if genes else self.random_genome()
        self.fitness = 0.0
        self.fitness_trend = 0.0
        self.fitness_range = 0.0
        self.fitness_crash = 0.0
        self.parent_ids = []

    def random_genome(self):
        """Génère un génome aléatoire valide selon GENE_SPACE."""
        genome = {}
        for key, val in GENE_SPACE.items():
            if isinstance(val, tuple):
                genome[key] = random.uniform(*val)
            elif isinstance(val, list):
                genome[key] = random.choice(val)
        return genome

    def copy(self):
        """Retourne une copie profonde du génome."""
        return Genome(self.genes.copy())

    def get(self, key, default=None):
        """Accès sécurisé à un gène."""
        return self.genes.get(key, default)


def mutate(genome, mutation_rate=0.2, intensity=0.1):
    """Retourne un nouveau Genome muté à partir de genome."""
    new_genes = genome.genes.copy()
    for key in new_genes:
        if random.random() < mutation_rate:
            space = GENE_SPACE[key]
            if isinstance(space, tuple):
                current = new_genes[key]
                delta = (space[1] - space[0]) * intensity
                new_val = current + random.uniform(-delta, delta)
                new_genes[key] = clamp_gene(key, new_val)
            elif isinstance(space, list):
                new_genes[key] = random.choice(space)
    return Genome(new_genes)


def clamp_gene(key, value):
    """Force la valeur d'un gène à rester dans ses bornes."""
    space = GENE_SPACE[key]
    if isinstance(space, tuple):
        return max(space[0], min(space[1], value))
    return value


def crossover(parent1, parent2):
    """Retourne un enfant issu du croisement de deux parents."""
    child_genes = {}
    for key in parent1.genes:
        if random.random() < 0.5:
            child_genes[key] = parent1.genes[key]
        else:
            child_genes[key] = parent2.genes[key]
        child_genes[key] = clamp_gene(key, child_genes[key])
    child = Genome(child_genes)
    child.parent_ids = [parent1.id, parent2.id]
    return child


def apply_extinction(population, min_species_size=5):
    """Supprime les espèces trop rares de la population."""
    counts = Counter(g.genes["entry.type"] for g in population)
    return [g for g in population if counts[g.genes["entry.type"]] >= min_species_size]


def select_parents(survivors):
    """Sélectionne deux parents pour la reproduction, favorisant la même espèce."""
    parent1 = random.choice(survivors)
    species = parent1.genes["entry.type"]
    same_species = [g for g in survivors if g.genes["entry.type"] == species]
    if len(same_species) > 1:
        parent2 = random.choice(same_species)
    else:
        parent2 = random.choice(survivors)
    return parent1, parent2
