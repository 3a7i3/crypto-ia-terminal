from __future__ import annotations

import json
import os
from pathlib import Path


def test_ti00_scientific_data_guard_baseline_is_empty() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (repo_root / ".ci" / "scientific_data_guard_baseline.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["known_leaking_paths"] == []


def test_ti00_run_repository_default_uses_isolated_env() -> None:
    from src.storage.run_repository import RunRepository

    repo = RunRepository()
    assert Path(repo._path) == Path(os.environ["SIM_RUNS_DB"])
    assert Path(repo._path).exists()


def test_ti00_simbot_default_uses_isolated_run_repository() -> None:
    from src.telegram.sim_bot import SimBot

    bot = SimBot()
    assert Path(bot._repo._path) == Path(os.environ["SIM_RUNS_DB"])


def test_ti00_evolution_memory_default_uses_isolated_env() -> None:
    from evolution_memory import EvolutionMemoryDB

    db = EvolutionMemoryDB()
    assert db.db_path == Path(os.environ["EVOLUTION_MEMORY_DB"])
    assert db.db_path.exists()


def test_ti00_startup_cache_default_uses_isolated_env() -> None:
    from infra.startup_cache import StartupCache

    cache = StartupCache()
    expected = Path(os.environ["STARTUP_CACHE_DIR"])
    assert cache.CACHE_DIR == expected
    assert cache.CONFIG_CACHE == expected / "configs.json"
    assert cache.STATE_CACHE == expected / "runtime_state.pkl"
    assert cache.MEMORY_CACHE == expected / "evolution_memory.pkl"
    assert cache.TIMESTAMP_FILE == expected / "last_snapshot.txt"


def test_ti00_daily_analyzer_default_uses_isolated_env() -> None:
    from infra.monitoring.daily_analyzer import DailyAnalyzer

    analyzer = DailyAnalyzer()
    assert analyzer.DB_PATH == Path(os.environ["DAILY_ANALYZER_DB"])
    assert analyzer.DB_PATH.exists()


def test_ti00_strategy_memory_default_uses_isolated_env() -> None:
    from quant_hedge_ai.ai_evolution.strategy_memory import StrategyMemoryStore

    store = StrategyMemoryStore()
    assert store.cfg.file_path == Path(os.environ["STRATEGY_MEMORY_FILE"])


def test_ti00_dip_default_uses_isolated_env() -> None:
    from dip.core.store import DIPStore

    DIPStore._instance = None
    try:
        store = DIPStore.instance()
        assert store._path == Path(os.environ["DIP_DB_PATH"])
        assert store._path.exists()
    finally:
        DIPStore._instance = None


def test_ti00_system_state_default_uses_isolated_env() -> None:
    from system.state_machine import SystemStateMachine

    state = SystemStateMachine()
    assert state._path == Path(os.environ["SYSTEM_STATE_FILE"])
