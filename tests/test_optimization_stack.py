from __future__ import annotations

import time
from typing import Any, cast

import pytest


pytestmark = pytest.mark.integration

JSONDict = dict[str, Any]


@pytest.fixture(scope="module")
def seeded_startup_cache() -> Any:
    from startup_cache import get_startup_cache

    cache = get_startup_cache()
    test_config: JSONDict = {"test": "config", "value": 123}
    test_state: JSONDict = {"iteration": 100, "fitness": 1.5}
    test_memory: JSONDict = {
        "genome_1": {"fitness": 1.5},
        "genome_2": {"fitness": 1.3},
    }

    assert cache.save_config(test_config)
    assert cache.save_runtime_state(test_state)
    assert cache.save_memory_snapshot(test_memory)
    return cache


@pytest.fixture(scope="module")
def seeded_evolution_memory() -> Any:
    from evolution_memory import GenomeRecord, IncidentPattern, get_evolution_memory_db

    db = get_evolution_memory_db()
    suffix = str(int(time.time() * 1000))
    genome = GenomeRecord(
        genome_id=f"test_{suffix}",
        generation=50,
        world="trend",
        fitness_score=1.45,
        genes={"param1": 0.5, "param2": 0.8},
        win_count=10,
        loss_count=2,
        avg_return=0.02,
    )
    pattern = IncidentPattern(
        pattern_id=f"crash_{suffix}",
        incident_type="crash",
        frequency=3,
        first_seen=time.time(),
        last_seen=time.time(),
        severity="HIGH",
        mitigation_applied="retry_policy",
    )

    assert db.save_genome(genome)
    assert db.save_incident_pattern(pattern)
    assert db.save_fitness_snapshot("trend", 1.5, 1.2, 100)
    return db


def test_startup_cache_round_trip(seeded_startup_cache: Any) -> None:
    cache = seeded_startup_cache

    loaded = cache.load_config(max_age_seconds=3600)
    assert loaded is not None

    loaded_state = cache.load_runtime_state(max_age_seconds=3600)
    assert loaded_state is not None

    loaded_memory = cache.load_memory_snapshot()
    assert loaded_memory is not None

    stats = cache.get_cache_stats()
    assert "config_cached" in stats


def test_warm_boot_uses_seeded_cache(seeded_startup_cache: Any) -> None:
    from warm_boot import WarmBootManager

    mgr = WarmBootManager(max_workers=2)
    results = mgr.boot_parallel()

    assert isinstance(results, dict)
    assert len(mgr.phases) > 0

    report = mgr.get_boot_report()
    assert "total_boot_time_ms" in report
    assert mgr.save_boot_report()


def test_evolution_memory_round_trip(seeded_evolution_memory: Any) -> None:
    db = seeded_evolution_memory

    best = db.get_best_genomes(world="trend", limit=5)
    assert len(best) > 0

    patterns = db.get_incident_patterns(min_frequency=1)
    assert len(patterns) > 0

    trend = db.get_fitness_trend("trend", hours=24)
    assert len(trend) > 0

    stats = db.get_stats()
    assert "genomes_stored" in stats


def test_lazy_loader_tracks_loaded_modules() -> None:
    from lazy_loader import get_lazy_loader

    loader = get_lazy_loader()
    result = loader.load("streamlit")

    assert result is not None
    assert loader.is_cached("streamlit")
    assert len(loader.get_import_stats()) >= 1
    assert loader.cache_size_mb() >= 0


def test_daily_analyzer_generates_report() -> None:
    from daily_analyzer import SystemSnapshot, get_daily_analyzer

    analyzer = get_daily_analyzer()
    snapshot = SystemSnapshot(
        timestamp=time.time(),
        uptime_seconds=3600,
        memory_used_mb=512,
        cpu_percent=25.5,
        error_count=2,
        warning_count=5,
        best_strategy_name="TestStrategy",
        best_fitness_score=1.45,
        force_level=75.0,
        system_health="GREEN",
    )

    assert analyzer.save_snapshot(snapshot)

    report = analyzer.generate_daily_report()
    assert report is not None
    assert "date" in report

    text = analyzer.format_report_text(report)
    assert "DAILY REPORT" in text

    assert isinstance(analyzer.get_last_n_reports(n=7), list)


def test_circuit_breaker_basic_flow() -> None:
    from circuit_breaker import CircuitState, get_circuit_breaker

    breaker = get_circuit_breaker()
    breaker.reset()  # Ensure clean state regardless of previous tests
    assert breaker.state == CircuitState.CLOSED

    breaker.update_metric("memory", 50.0)
    breaker.update_latency(0.5)
    breaker.update_error_rate(1, 100)

    assert breaker.can_proceed()
    state = cast(JSONDict, cast(Any, breaker).get_state())
    assert "state" in state
    assert "metrics" in state

    breaker.reset()
    assert breaker.state == CircuitState.CLOSED


def test_bootstrap_integration_stack(
    seeded_startup_cache: Any,
    seeded_evolution_memory: Any,
) -> None:
    from bootstrap_integration import SystemBootstrap

    system = SystemBootstrap(enable_monitoring=False)
    report = system.run_bootstrap()

    assert report["status"] == "SUCCESS"
    assert report.get("total_boot_time", 0) >= 0

    health = system.get_system_health()
    assert "memory_mb" in health
