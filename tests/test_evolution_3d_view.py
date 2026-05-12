from __future__ import annotations

import importlib
import sys

import pandas as pd
import pytest


pytest.importorskip("matplotlib")


def _reload_module():
    if "evolution_3d_view" in sys.modules:
        del sys.modules["evolution_3d_view"]
    return importlib.import_module("evolution_3d_view")


def test_load_population_data_empty(monkeypatch, tmp_path) -> None:
    module = _reload_module()
    monkeypatch.setattr(module.glob, "glob", lambda pattern: [])

    data = module.load_population_data(results_dir=str(tmp_path))
    assert isinstance(data, dict)
    assert data == {}


def test_load_population_data_single_file(monkeypatch, tmp_path) -> None:
    fake_file = tmp_path / "world1_pop_gen_0.csv"
    pd.DataFrame({"fitness": [1.0, 2.0], "species": ["A", "B"], "generation": [0, 0]}).to_csv(
        fake_file, index=False
    )

    module = _reload_module()
    monkeypatch.setattr(module.glob, "glob", lambda pattern: [str(fake_file)])

    data = module.load_population_data(results_dir=str(tmp_path))
    assert "world1" in data
    assert isinstance(data["world1"], pd.DataFrame)
    assert {"fitness", "species", "generation"}.issubset(data["world1"].columns)
