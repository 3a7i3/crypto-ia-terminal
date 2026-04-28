"""
Module: config_utils.py
Gestion de la configuration INI et des arguments ligne de commande
"""

import argparse
import configparser


def read_config(config_path="strategy_factory_config.ini"):
    config = configparser.ConfigParser()
    try:
        config.read(config_path)
    except Exception as e:
        print(f"Erreur lecture config: {e}")
        return None
    return config


def parse_args():
    parser = argparse.ArgumentParser(description="Evolutionary Strategy Factory")
    parser.add_argument("--pop_size", type=int, help="Population size")
    parser.add_argument("--n_gen", type=int, help="Number of generations")
    parser.add_argument("--migration_freq", type=int, help="Migration frequency")
    parser.add_argument("--migration_rate", type=float, help="Migration rate")
    parser.add_argument("--show_plots", action="store_true", help="Show plots")
    parser.add_argument(
        "--config",
        type=str,
        default="strategy_factory_config.ini",
        help="Config file path",
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume from last saved state"
    )
    return parser.parse_args()
