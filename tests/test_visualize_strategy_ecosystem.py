from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pandas as pd
import pytest


def _import_module(monkeypatch, dataframe: pd.DataFrame):
    import pandas as _pandas
    import plotly.express as _px

    shown = {"called": False}

    class _FakeFigure:
        def show(self) -> None:
            shown["called"] = True

    monkeypatch.setattr(_pandas, "read_csv", lambda path: dataframe)
    monkeypatch.setattr(_px, "scatter_3d", lambda *args, **kwargs: _FakeFigure())
    if "visualize_strategy_ecosystem" in sys.modules:
        del sys.modules["visualize_strategy_ecosystem"]
    module = importlib.import_module("visualize_strategy_ecosystem")
    return module, shown


def test_visualize_strategy_ecosystem_empty(monkeypatch) -> None:
    dataframe = pd.DataFrame(columns=["entry.type"])
    module, shown = _import_module(monkeypatch, dataframe)
    module.main("ignored.csv")
    assert module is not None
    assert shown["called"] is True


def test_visualize_strategy_ecosystem_with_csv(monkeypatch, tmp_path) -> None:
    dataframe = pd.DataFrame(
        {
            "fitness": [1.0],
            "species": ["A"],
            "generation": [0],
            "entry.type": ["X"],
            "fitness_trend": [0.5],
            "fitness_range": [0.2],
            "fitness_crash": [0.1],
        }
    )

    module, shown = _import_module(monkeypatch, dataframe)
    module.main("ignored.csv")
    assert module is not None
    assert shown["called"] is True