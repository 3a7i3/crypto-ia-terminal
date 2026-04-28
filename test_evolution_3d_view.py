import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import numpy as np
import pandas as pd

from evolution_3d_view import load_population_data


def test_load_population_data_empty(monkeypatch, tmp_path):
    # Patch glob.glob dans le namespace evolution_3d_view
    monkeypatch.setattr("evolution_3d_view.glob.glob", lambda pattern: [])
    import importlib
    import sys

    if "evolution_3d_view" in sys.modules:
        importlib.reload(sys.modules["evolution_3d_view"])
    evolution_3d_view = importlib.import_module("evolution_3d_view")
    data = evolution_3d_view.load_population_data(results_dir=str(tmp_path))
    assert isinstance(data, dict)
    assert len(data) == 0


def test_load_population_data_single_file(monkeypatch, tmp_path):
    # Crée un faux fichier CSV
    fake_file = tmp_path / "world1_pop_gen_0.csv"
    df = pd.DataFrame(
        {"fitness": [1.0, 2.0], "species": ["A", "B"], "generation": [0, 0]}
    )
    df.to_csv(fake_file, index=False)
    # Patch glob.glob dans le namespace evolution_3d_view
    monkeypatch.setattr("evolution_3d_view.glob.glob", lambda pattern: [str(fake_file)])
    import importlib
    import sys

    if "evolution_3d_view" in sys.modules:
        importlib.reload(sys.modules["evolution_3d_view"])
    evolution_3d_view = importlib.import_module("evolution_3d_view")
    data = evolution_3d_view.load_population_data(results_dir=str(tmp_path))
    assert "world1" in data
    assert isinstance(data["world1"], pd.DataFrame)
    assert set(data["world1"].columns) >= {"fitness", "species", "generation"}
