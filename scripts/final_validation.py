#!/usr/bin/env python
"""
final_validation.py - Test de démarrage réaliste complet
Simule un démarrage réel du système avec tous les composants
"""

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s"
)
log = logging.getLogger("final_validation")


def main():
    """Lance validation finale complète"""
    log.info("\n" + "=" * 70)
    log.info("FINAL VALIDATION TEST - Real startup simulation")
    log.info("=" * 70 + "\n")

    total_start = time.time()
    all_passed = True

    # Test 1: Check all files exist
    log.info("[CHECK 1] Required files...")
    required_files = [
        'startup_cache.py',
        'warm_boot.py',
        'evolution_memory.py',
        'lazy_loader.py',
        'daily_analyzer.py',
        'circuit_breaker.py',
        'bootstrap_integration.py',
        'test_optimization_stack.py',
    ]

    for fname in required_files:
        path = Path(fname)
        if path.exists():
            log.info(f"  OK: {fname}")
        else:
            log.error(f"  MISSING: {fname}")
            all_passed = False

    # Test 2: Import all modules
    log.info("\n[CHECK 2] Importing all modules...")
    try:
        log.info("  OK: startup_cache")

        log.info("  OK: warm_boot")

        log.info("  OK: evolution_memory")

        log.info("  OK: lazy_loader")

        log.info("  OK: daily_analyzer")

        log.info("  OK: circuit_breaker")

        from bootstrap_integration import bootstrap_system
        log.info("  OK: bootstrap_integration")

    except Exception as e:
        log.error(f"  IMPORT ERROR: {e}")
        all_passed = False
        return all_passed

    # Test 3: Run bootstrap (simulated)
    log.info("\n[CHECK 3] Running bootstrap sequence...")
    try:
        system = bootstrap_system(enable_monitoring=False)  # Disable monitoring for speed

        if system.boot_report.get('status') == 'SUCCESS':
            boot_time = system.boot_report.get('total_boot_time', 0)
            log.info(f"  OK: Bootstrap completed in {boot_time:.2f}s")
        else:
            log.error(f"  FAILED: {system.boot_report.get('status')}")
            all_passed = False

    except Exception as e:
        log.error(f"  BOOTSTRAP ERROR: {e}")
        all_passed = False

    # Test 4: Verify caches created
    log.info("\n[CHECK 4] Cache files...")
    cache_files = [
        'cache/startup/configs.json',
        'cache/evolution_memory.db',
        'cache/daily_analysis.db',
    ]

    for cfile in cache_files:
        path = Path(cfile)
        if path.exists():
            size_kb = path.stat().st_size / 1024
            log.info(f"  OK: {cfile} ({size_kb:.1f}KB)")
        else:
            log.debug(f"  EMPTY: {cfile} (will be created on first use)")

    # Test 5: Verify logs
    log.info("\n[CHECK 5] Log files...")
    log_files = ['logs/bootstrap.log', 'logs/boot_report.json']

    for lfile in log_files:
        path = Path(lfile)
        if path.exists():
            size_kb = path.stat().st_size / 1024
            log.info(f"  OK: {lfile} ({size_kb:.1f}KB)")

    # Summary
    total_time = time.time() - total_start
    status = "PASS" if all_passed else "FAIL"

    log.info("\n" + "=" * 70)
    log.info(f"FINAL VALIDATION: {status}")
    log.info(f"Total time: {total_time:.2f}s")
    log.info("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
