from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_full_workflow_with_alerts(monkeypatch) -> None:
    pytest.importorskip("matplotlib")
    import terminal_core.quant.logging_alerts as logging_alerts
    from run_strategy_factory import create_population, evaluate_fitness, evolve, mutate

    pop = create_population(50)
    assert len(pop) == 50

    mutated = [mutate(genome) for genome in pop]
    for genome in mutated:
        evaluate_fitness(genome)

    new_pop = evolve(mutated)
    assert len(new_pop) == 50

    notified: list[str] = []
    notifier = SimpleNamespace(notify=lambda message: notified.append(message))
    logging_alerts.log_and_alert(
        "info", "Test multi-module OK", alert=True, notifier=notifier
    )

    assert notified == ["[INFO] Test multi-module OK"]
