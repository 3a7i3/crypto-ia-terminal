"""
Tests des fonctions d'analyse et de visualisation du dashboard.
Importe depuis dashboard_functions (module pur) pour éviter l'exécution
du code Streamlit au niveau module lors de l'import.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_streamlit(monkeypatch):
    """Remplace streamlit par un mock pour tous les tests."""
    mock_st = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)
    return mock_st


def _get_mod():
    import importlib
    import sys

    if "dashboard_functions" in sys.modules:
        del sys.modules["dashboard_functions"]
    return importlib.import_module("dashboard_functions")


# --- visualisation_3d ---


def test_visualisation_3d_handles_missing_columns():
    mod = _get_mod()
    df = pd.DataFrame({"exit.tp": [1], "exit.sl": [2]})
    mod.visualisation_3d(df)  # ne doit pas lever d'exception


def test_visualisation_3d_with_all_columns():
    mod = _get_mod()
    df = pd.DataFrame(
        {"exit.tp": [0.01, 0.02], "exit.sl": [0.005, 0.01], "fitness": [0.8, 0.9]}
    )
    mod.visualisation_3d(df)


# --- stats_par_espece ---


def test_stats_par_espece_handles_no_species():
    mod = _get_mod()
    df = pd.DataFrame({"fitness": [1, 2, 3]})
    mod.stats_par_espece(df)


def test_stats_par_espece_with_species():
    mod = _get_mod()
    df = pd.DataFrame({"species": ["A", "A", "B"], "fitness": [1.0, 2.0, 3.0]})
    mod.stats_par_espece(df)


# --- top5_et_heatmap ---


def test_top5_et_heatmap_handles_empty_df():
    mod = _get_mod()
    df = pd.DataFrame()
    mod.top5_et_heatmap(df)


def test_top5_et_heatmap_handles_small_df():
    mod = _get_mod()
    df = pd.DataFrame({"id": [1], "fitness": [0.5]})
    mod.top5_et_heatmap(df)


# --- evolution_fitness ---


def test_evolution_fitness_handles_missing_generation():
    mod = _get_mod()
    df = pd.DataFrame({"generation": [1, 2, 3]})
    mod.evolution_fitness(df)  # fitness absente → warning


def test_evolution_fitness_with_valid_data():
    mod = _get_mod()
    df = pd.DataFrame({"generation": [1, 1, 2, 2], "fitness": [0.5, 0.6, 0.7, 0.8]})
    mod.evolution_fitness(df)


# --- comparatif_multi_simulations ---


def test_comparatif_multi_simulations_handles_empty_df():
    mod = _get_mod()
    mod.comparatif_multi_simulations(pd.DataFrame())


def test_comparatif_multi_simulations_with_data():
    mod = _get_mod()
    df = pd.DataFrame({"fitness": [1, 2, 3], "sharpe": [0.5, 1.0, 1.5]})
    mod.comparatif_multi_simulations(df)


# --- import_export_csv ---


def test_import_export_csv_handles_empty_df():
    mod = _get_mod()
    mod.import_export_csv(pd.DataFrame())


def test_import_export_csv_with_data():
    mod = _get_mod()
    df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
    mod.import_export_csv(df)
