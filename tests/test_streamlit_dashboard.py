from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_streamlit(monkeypatch):
    mock_st = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)
    return mock_st


def _get_mod():
    import importlib
    import sys

    if "dashboard_functions" in sys.modules:
        del sys.modules["dashboard_functions"]
    return importlib.import_module("dashboard_functions")


def test_visualisation_3d_handles_missing_columns() -> None:
    mod = _get_mod()
    mod.visualisation_3d(pd.DataFrame({"exit.tp": [1], "exit.sl": [2]}))


def test_visualisation_3d_with_all_columns() -> None:
    mod = _get_mod()
    mod.visualisation_3d(
        pd.DataFrame({"exit.tp": [0.01, 0.02], "exit.sl": [0.005, 0.01], "fitness": [0.8, 0.9]})
    )


def test_stats_par_espece_handles_no_species() -> None:
    mod = _get_mod()
    mod.stats_par_espece(pd.DataFrame({"fitness": [1, 2, 3]}))


def test_stats_par_espece_with_species() -> None:
    mod = _get_mod()
    mod.stats_par_espece(pd.DataFrame({"species": ["A", "A", "B"], "fitness": [1.0, 2.0, 3.0]}))


def test_top5_et_heatmap_handles_empty_df() -> None:
    mod = _get_mod()
    mod.top5_et_heatmap(pd.DataFrame())


def test_top5_et_heatmap_handles_small_df() -> None:
    mod = _get_mod()
    mod.top5_et_heatmap(pd.DataFrame({"id": [1], "fitness": [0.5]}))


def test_evolution_fitness_handles_missing_generation() -> None:
    mod = _get_mod()
    mod.evolution_fitness(pd.DataFrame({"generation": [1, 2, 3]}))


def test_evolution_fitness_with_valid_data() -> None:
    mod = _get_mod()
    mod.evolution_fitness(pd.DataFrame({"generation": [1, 1, 2, 2], "fitness": [0.5, 0.6, 0.7, 0.8]}))


def test_comparatif_multi_simulations_handles_empty_df() -> None:
    mod = _get_mod()
    mod.comparatif_multi_simulations(pd.DataFrame())


def test_comparatif_multi_simulations_with_data() -> None:
    mod = _get_mod()
    mod.comparatif_multi_simulations(pd.DataFrame({"fitness": [1, 2, 3], "sharpe": [0.5, 1.0, 1.5]}))


def test_import_export_csv_handles_empty_df() -> None:
    mod = _get_mod()
    mod.import_export_csv(pd.DataFrame())


def test_import_export_csv_with_data() -> None:
    mod = _get_mod()
    mod.import_export_csv(pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]}))
