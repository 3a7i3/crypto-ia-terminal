from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("matplotlib")

from run_strategy_factory import Genome, create_population, mutate, score_env_trend


def test_full_workflow_generates_expected_dataframe_and_plot(monkeypatch, tmp_path) -> None:
    import run_strategy_factory

    pop = create_population(10)
    assert len(pop) == 10
    assert all(isinstance(genome, Genome) for genome in pop)

    mutated = [mutate(genome, mutation_rate=0.5, intensity=0.5) for genome in pop]
    assert len(mutated) == 10

    scores = [score_env_trend(genome) for genome in mutated]
    assert all(isinstance(score, float) for score in scores)

    df = pd.DataFrame(
        [
            {
                "id": index,
                "fitness": score,
                "species": genome.genes.get("entry.type", "?"),
                "exit.tp": genome.genes.get("exit.tp", 0),
                "exit.sl": genome.genes.get("exit.sl", 0),
            }
            for index, (genome, score) in enumerate(zip(mutated, scores))
        ]
    )

    output_path = tmp_path / "god_mode_3d.png"

    def fake_savefig(path, *args, **kwargs):
        Path(output_path).write_bytes(b"plot")

    monkeypatch.setattr(run_strategy_factory.plt, "savefig", fake_savefig)
    monkeypatch.setattr(run_strategy_factory, "SHOW_PLOTS", False)

    run_strategy_factory.plot_god_mode(df)
    assert output_path.exists()