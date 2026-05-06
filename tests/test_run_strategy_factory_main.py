from __future__ import annotations

import builtins
from pathlib import Path

import pytest
import pandas as pd

matplotlib = pytest.importorskip("matplotlib")

matplotlib.use("Agg")


def test_run_strategy_factory_main(monkeypatch, tmp_path) -> None:
    import run_strategy_factory

    run_strategy_factory.SHOW_PLOTS = False

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    monkeypatch.setattr(run_strategy_factory, "SHOW_PLOTS", False)
    monkeypatch.setattr(run_strategy_factory, "POP_SIZE", 5)
    monkeypatch.setattr(run_strategy_factory, "N_GEN", 2)
    monkeypatch.setattr(run_strategy_factory, "MIGRATION_FREQ", 2)
    monkeypatch.setattr(run_strategy_factory, "MIGRATION_RATE", 0.5)
    monkeypatch.setattr(run_strategy_factory, "WORLD_NAMES", ["trend", "range"])

    original_to_csv = pd.DataFrame.to_csv

    def fake_to_csv(self, path, *args, **kwargs):
        if isinstance(path, str) and path.startswith("results/"):
            path = str(results_dir / Path(path).name)
        return original_to_csv(self, path, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_csv", fake_to_csv)

    original_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if isinstance(file, str) and file.startswith("results/"):
            file = str(results_dir / Path(file).name)
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    logs: list[str] = []
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: logs.append(" ".join(map(str, args))))

    run_strategy_factory.main()

    csvs = list(results_dir.glob("*.csv"))
    jsons = list(results_dir.glob("*.json"))
    assert csvs
    assert jsons
    assert any("best_strategies_cross_world.json" in line for line in logs)