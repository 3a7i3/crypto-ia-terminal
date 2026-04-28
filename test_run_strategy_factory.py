"""Test léger du pipeline run_strategy_factory (nécessite matplotlib, pandas, pytest)."""

from __future__ import annotations

import builtins
import os
import sys

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def test_run_strategy_factory_main(monkeypatch, tmp_path):
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

    orig_to_csv = pd.DataFrame.to_csv

    def fake_to_csv(self, path, *a, **k):
        if isinstance(path, str) and path.startswith("results/"):
            path = str(results_dir / os.path.basename(path))
        return orig_to_csv(self, path, *a, **k)

    monkeypatch.setattr(pd.DataFrame, "to_csv", fake_to_csv)

    orig_open = builtins.open

    def fake_open(file, mode="r", *a, **k):
        if isinstance(file, str) and file.startswith("results/"):
            file = str(results_dir / os.path.basename(file))
        return orig_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)

    logs = []
    monkeypatch.setattr(
        builtins, "print", lambda *a, **k: logs.append(" ".join(map(str, a)))
    )

    run_strategy_factory.main()

    csvs = list(results_dir.glob("*.csv"))
    jsons = list(results_dir.glob("*.json"))
    assert len(csvs) > 0, "Aucun CSV généré"
    assert len(jsons) > 0, "Aucun JSON généré"
    assert any("best_strategies_cross_world.json" in l for l in logs)
