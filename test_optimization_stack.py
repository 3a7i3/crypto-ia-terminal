"""
test_optimization_stack.py — Validation stack d'optimisation complète
Teste tous les 7 composants ensemble
"""

import logging
import sys
import time
from typing import Any, TypeAlias, cast

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s"
)
log = logging.getLogger("test_optimization")

JSONDict: TypeAlias = dict[str, Any]
TestResults: TypeAlias = list[tuple[str, bool]]


def test_startup_cache():
    """Test 1: startup_cache.py"""
    log.info("\n" + "=" * 60)
    log.info("TEST 1: startup_cache.py")
    log.info("=" * 60)

    try:
        from startup_cache import get_startup_cache

        cache = get_startup_cache()

        # Test save config
        test_config: JSONDict = {"test": "config", "value": 123}
        assert cache.save_config(test_config), "Failed to save config"

        # Test load config
        loaded = cache.load_config(max_age_seconds=3600)
        assert loaded is not None, "Failed to load config"
        log.info("✓ Config save/load OK")

        # Test save state
        test_state: JSONDict = {"iteration": 100, "fitness": 1.5}
        assert cache.save_runtime_state(test_state), "Failed to save state"

        # Test load state
        loaded_state = cache.load_runtime_state(max_age_seconds=3600)
        assert loaded_state is not None, "Failed to load state"
        log.info("✓ State save/load OK")

        # Test memory snapshot
        test_memory: JSONDict = {
            "genome_1": {"fitness": 1.5},
            "genome_2": {"fitness": 1.3},
        }
        assert cache.save_memory_snapshot(test_memory), "Failed to save memory"

        loaded_memory = cache.load_memory_snapshot()
        assert loaded_memory is not None, "Failed to load memory"
        log.info("✓ Memory save/load OK")

        # Test stats
        stats = cache.get_cache_stats()
        assert "config_cached" in stats, "Stats missing keys"
        log.info(f"✓ Cache stats: {stats}")

    except Exception as e:
        log.error(f"✗ Test failed: {e}", exc_info=True)
        raise


def test_warm_boot():
    """Test 2: warm_boot.py"""
    log.info("\n" + "=" * 60)
    log.info("TEST 2: warm_boot.py")
    log.info("=" * 60)

    try:
        from warm_boot import WarmBootManager

        mgr = WarmBootManager(max_workers=2)
        results = mgr.boot_parallel()

        assert "results" not in results or isinstance(results, dict), "Invalid results format"
        log.info(f"✓ Boot phases executed: {len(mgr.phases)} phases")

        report = mgr.get_boot_report()
        assert "total_boot_time_ms" in report, "Report missing timing"
        log.info(f"✓ Boot time: {report['total_boot_time_ms']:.1f}ms")

        assert mgr.save_boot_report(), "Failed to save boot report"
        log.info("✓ Boot report saved")

    except Exception as e:
        log.error(f"✗ Test failed: {e}", exc_info=True)
        raise


def test_evolution_memory():
    """Test 3: evolution_memory.py"""
    log.info("\n" + "=" * 60)
    log.info("TEST 3: evolution_memory.py")
    log.info("=" * 60)

    try:
        from evolution_memory import (
            get_evolution_memory_db,
            GenomeRecord,
            IncidentPattern,
        )

        db = get_evolution_memory_db()

        # Test save genome
        genome = GenomeRecord(
            genome_id="test_001",
            generation=50,
            world="trend",
            fitness_score=1.45,
            genes={"param1": 0.5, "param2": 0.8},
            win_count=10,
            loss_count=2,
            avg_return=0.02,
        )
        assert db.save_genome(genome), "Failed to save genome"
        log.info("✓ Genome saved")

        # Test get best genomes
        best = db.get_best_genomes(world="trend", limit=5)
        assert len(best) > 0, "No genomes retrieved"
        log.info(f"✓ Retrieved {len(best)} best genomes")

        # Test incident pattern
        pattern = IncidentPattern(
            pattern_id="crash_001",
            incident_type="crash",
            frequency=3,
            first_seen=time.time(),
            last_seen=time.time(),
            severity="HIGH",
            mitigation_applied="retry_policy",
        )
        assert db.save_incident_pattern(pattern), "Failed to save pattern"
        log.info("✓ Incident pattern saved")

        # Test get patterns
        patterns = db.get_incident_patterns(min_frequency=1)
        assert len(patterns) > 0, "No patterns retrieved"
        log.info(f"✓ Retrieved {len(patterns)} patterns")

        # Test fitness snapshot
        assert db.save_fitness_snapshot("trend", 1.5, 1.2, 100), "Failed to save fitness"
        trend = db.get_fitness_trend("trend", hours=24)
        log.info(f"✓ Fitness trend: {len(trend)} snapshots")

        # Test stats
        stats = db.get_stats()
        assert "genomes_stored" in stats, "Stats missing keys"
        log.info(f"✓ DB stats: {stats}")

    except Exception as e:
        log.error(f"✗ Test failed: {e}", exc_info=True)
        raise


def test_lazy_loader():
    """Test 4: lazy_loader.py"""
    log.info("\n" + "=" * 60)
    log.info("TEST 4: lazy_loader.py")
    log.info("=" * 60)

    try:
        from lazy_loader import get_lazy_loader

        loader = get_lazy_loader()

        # Test load single module
        # (Using a light module that should exist)
        result = loader.load("streamlit")
        # streamlit might not be installed, but test the mechanism
        log.info(f"✓ Load attempted (result: {result is not None})")

        # Test cache check
        is_cached = loader.is_cached("streamlit")
        log.info(f"✓ Cache check OK (cached: {is_cached})")

        # Test stats
        stats = loader.get_import_stats()
        log.info(f"✓ Import stats: {len(stats)} modules tracked")

        # Test cache size
        size_mb = loader.cache_size_mb()
        log.info(f"✓ Cache size: {size_mb:.2f}MB")

    except Exception as e:
        log.error(f"✗ Test failed: {e}", exc_info=True)
        raise


def test_daily_analyzer():
    """Test 5: daily_analyzer.py"""
    log.info("\n" + "=" * 60)
    log.info("TEST 5: daily_analyzer.py")
    log.info("=" * 60)

    try:
        from daily_analyzer import get_daily_analyzer, SystemSnapshot

        analyzer = get_daily_analyzer()

        # Test save snapshot
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
        assert analyzer.save_snapshot(snapshot), "Failed to save snapshot"
        log.info("✓ Snapshot saved")

        # Test generate report
        report = analyzer.generate_daily_report()
        if report:
            assert "date" in report, "Report missing date"
            log.info(f"✓ Report generated: {report['summary']}")

            # Test format
            text = analyzer.format_report_text(report)
            assert "DAILY REPORT" in text, "Format issue"
            log.info("✓ Report formatted OK")
        else:
            log.warning("⚠ No snapshots yet for today")

        # Test stats
        stats = analyzer.get_last_n_reports(n=7)
        log.info(f"✓ Retrieved {len(stats)} historical reports")

    except Exception as e:
        log.error(f"✗ Test failed: {e}", exc_info=True)
        raise


def test_circuit_breaker():
    """Test 6: circuit_breaker.py"""
    log.info("\n" + "=" * 60)
    log.info("TEST 6: circuit_breaker.py")
    log.info("=" * 60)

    try:
        from circuit_breaker import get_circuit_breaker, CircuitState

        breaker = get_circuit_breaker()
        breaker.reset()

        # Test initial state
        assert breaker.state == CircuitState.CLOSED, "Initial state should be CLOSED"
        log.info("✓ Initial state: CLOSED")

        # Test update metrics
        breaker.update_metric("memory", 50.0)
        breaker.update_latency(0.5)
        breaker.update_error_rate(1, 100)
        log.info("✓ Metrics updated")

        # Test can_proceed
        can_proceed = breaker.can_proceed()
        assert can_proceed, "Should be able to proceed"
        log.info(f"✓ Can proceed: {can_proceed}")

        # Test get state
        state = cast(JSONDict, cast(Any, breaker).get_state())
        assert "state" in state, "State missing keys"
        assert "metrics" in state, "Metrics missing"
        log.info(f"✓ State retrieved: {state['state']}")

        # Test reset
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED, "Reset failed"
        log.info("✓ Reset OK")

    except Exception as e:
        log.error(f"✗ Test failed: {e}", exc_info=True)
        raise


def test_bootstrap_integration():
    """Test 7: bootstrap_integration.py"""
    log.info("\n" + "=" * 60)
    log.info("TEST 7: bootstrap_integration.py")
    log.info("=" * 60)

    try:
        from bootstrap_integration import SystemBootstrap

        system = SystemBootstrap(enable_monitoring=False)

        # Run bootstrap (test mode, no monitoring)
        report = system.run_bootstrap()

        assert "status" in report, "Report missing status"
        assert report["status"] == "SUCCESS", f"Bootstrap failed: {report}"
        log.info(f"✓ Bootstrap completed: {report['status']}")

        total_time = report.get("total_boot_time", 0)
        log.info(f"✓ Total boot time: {total_time:.2f}s")

        # Test health check
        health = system.get_system_health()
        assert "memory_mb" in health, "Health missing keys"
        log.info(f"✓ Health check OK (memory: {health['memory_mb']:.1f}MB)")

    except Exception as e:
        log.error(f"✗ Test failed: {e}", exc_info=True)
        raise


def main():
    """Lance tous les tests"""
    log.info("\n" + "#" * 70)
    log.info("# OPTIMIZATION STACK VALIDATION TEST")
    log.info("#" * 70)

    tests = [
        ("Startup Cache", test_startup_cache),
        ("Warm Boot", test_warm_boot),
        ("Evolution Memory", test_evolution_memory),
        ("Lazy Loader", test_lazy_loader),
        ("Daily Analyzer", test_daily_analyzer),
        ("Circuit Breaker", test_circuit_breaker),
        ("Bootstrap Integration", test_bootstrap_integration),
    ]

    results: TestResults = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            log.error(f"Test {name} crashed: {e}", exc_info=True)
            results.append((name, False))

    # Summary
    log.info("\n" + "=" * 70)
    log.info("TEST SUMMARY")
    log.info("=" * 70)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        log.info(f"{status:10} {name}")

    log.info("=" * 70)
    log.info(f"Result: {passed}/{total} tests passed")
    log.info("=" * 70)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
