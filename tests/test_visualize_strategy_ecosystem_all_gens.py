from __future__ import annotations

import importlib
import sys

import pandas as pd


def _import_module(monkeypatch, dataframe: pd.DataFrame, csv_files: list[str]):
    import pandas as _pandas
    import plotly.express as _px

    shown = {"called": 0}

    class _FakeFigure:
        def show(self) -> None:
            shown["called"] += 1

    monkeypatch.setattr(_pandas, "read_csv", lambda path: dataframe)
    monkeypatch.setattr(_px, "scatter_3d", lambda *args, **kwargs: _FakeFigure())
    if "visualize_strategy_ecosystem_all_gens" in sys.modules:
        del sys.modules["visualize_strategy_ecosystem_all_gens"]
    module = importlib.import_module("visualize_strategy_ecosystem_all_gens")
    monkeypatch.setattr(module.glob, "glob", lambda pattern: csv_files)
    return module, shown


def test_visualize_strategy_ecosystem_all_gens_empty(monkeypatch) -> None:
    dataframe = pd.DataFrame(columns=["entry.type"])
    module, shown = _import_module(monkeypatch, dataframe, [])

    processed = module.main("ignored.csv", pause=False)

    assert processed == 0
    assert shown["called"] == 0


def test_visualize_strategy_ecosystem_all_gens_with_csv(monkeypatch, tmp_path) -> None:
    fake_file = tmp_path / "pop_gen_0.csv"
    fake_file.write_text("placeholder", encoding="utf-8")
    dataframe = pd.DataFrame(
        {
            "entry.type": ["X"],
            "fitness_trend": [0.5],
            "fitness_range": [0.2],
            "fitness_crash": [0.1],
        }
    )

    module, shown = _import_module(monkeypatch, dataframe, [str(fake_file)])

    processed = module.main("ignored.csv", pause=False)

    assert processed == 1
    assert shown["called"] == 1