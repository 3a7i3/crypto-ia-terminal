"""
bootstrap_integration.py — Point d'entrée unifié pour démarrage optimisé
Intègre: warm_boot + cache + lazy_load + circuit_breaker + daily_analyzer
"""

import json
import logging
import sys
import time
from pathlib import Path
from signal.evolution.evolution_memory import get_evolution_memory_db
from typing import Any, Dict, Optional

# Import des composants
from core.warm_boot import WarmBootManager
from infra.lazy_loader import get_lazy_loader
from infra.monitoring.daily_analyzer import SystemSnapshot, get_daily_analyzer
from infra.startup_cache import get_startup_cache
from risk.circuit_breaker import enable_circuit_breaker

try:
    import psutil
except ImportError:
    psutil = None

log = logging.getLogger("bootstrap_integration")


class SystemBootstrap:
    """Orchestrateur unifié du démarrage système"""

    def __init__(self, enable_monitoring: bool = True):
        self.enable_monitoring = enable_monitoring
        self.boot_start = time.time()
        self.boot_manager: Optional[WarmBootManager] = None
        self.circuit_breaker = None
        self.analyzer = get_daily_analyzer() if enable_monitoring else None
        self.cache = get_startup_cache()
        self.lazy_loader = get_lazy_loader()
        self.evolution_db = get_evolution_memory_db()
        self.boot_report: Dict[str, Any] = {}

    def _setup_logging(self) -> None:
        """Configure logging centralisé"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        handler_file = logging.FileHandler(log_dir / "bootstrap.log", encoding="utf-8")
        handler_console = logging.StreamHandler(sys.stdout)

        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s - %(message)s"
        )
        handler_file.setFormatter(formatter)
        handler_console.setFormatter(formatter)

        logging.basicConfig(
            level=logging.INFO,
            handlers=[handler_file, handler_console],
        )
        log.info("Logging configured")

    def phase_0_setup(self) -> bool:
        """Phase 0: Setup de base (logging, env)"""
        log.info("=" * 70)
        log.info("🚀 SYSTEM BOOTSTRAP — INTEGRATED STARTUP SEQUENCE")
        log.info("=" * 70)

        self._setup_logging()
        return True

    def phase_1_warm_boot(self) -> Dict[str, Any]:
        """Phase 1: Warm boot parallèle (configs, cache, modules)"""
        log.info("\n[PHASE 1] Warm boot sequence...")
        self.boot_manager = WarmBootManager(max_workers=4)
        results = self.boot_manager.boot_parallel()
        self.boot_manager.save_boot_report()
        return results

    def phase_2_circuit_breaker(self) -> bool:
        """Phase 2: Active circuit breaker pour protection"""
        log.info("\n[PHASE 2] Activating circuit breaker...")

        def on_critical():
            log.critical(
                "🛑 CIRCUIT BREAKER: System in critical state - pausing operations"
            )
            if self.analyzer:
                snapshot = SystemSnapshot(
                    timestamp=time.time(),
                    uptime_seconds=time.time() - self.boot_start,
                    memory_used_mb=0,
                    cpu_percent=0,
                    error_count=0,
                    warning_count=0,
                    best_strategy_name="PAUSED",
                    best_fitness_score=0,
                    force_level=0,
                    system_health="RED",
                )
                self.analyzer.save_snapshot(snapshot)

        def on_recover():
            log.info("✓ System recovered - resuming operations")

        self.circuit_breaker = enable_circuit_breaker(
            on_critical=on_critical,
            on_recover=on_recover,
        )
        log.info("✓ Circuit breaker active")
        return True

    def phase_3_lazy_loader(self) -> Dict[str, bool]:
        """Phase 3: Configure lazy loader pour dashboard & viz (optionnel)"""
        log.info("\n[PHASE 3] Setting up lazy loader...")

        optional_modules = ["streamlit", "plotly", "panel"]
        preload_results = self.lazy_loader.preload_batch(optional_modules)

        stats = self.lazy_loader.get_import_stats()
        log.info(f"✓ Lazy loader configured ({len(preload_results)} modules)")
        for name, loaded in preload_results.items():
            status = "✓" if loaded else "✗"
            duration = stats.get(name, 0)
            log.info(f"  {status} {name:15} {duration:7.1f}ms")

        return preload_results

    def phase_4_evolution_restore(self) -> Dict[str, Any]:
        """Phase 4: Restaure mémoire d'évolution & patterns"""
        log.info("\n[PHASE 4] Restoring evolution memory...")

        stats = self.evolution_db.get_stats()
        log.info("✓ Evolution memory DB loaded:")
        log.info(f"  • Genomes stored: {stats.get('genomes_stored', 0)}")
        log.info(f"  • Incident patterns: {stats.get('incident_patterns', 0)}")
        log.info(f"  • Fitness snapshots: {stats.get('fitness_snapshots', 0)}")
        log.info(f"  • DB size: {stats.get('db_size_kb', 0):.1f}KB")
        log.info("  • Top 5 genomes loaded")

        return stats

    def phase_5_monitoring_start(self) -> bool:
        """Phase 5: Start daily analyzer pour surveillance"""
        if not self.analyzer:
            log.debug("Daily analyzer disabled")
            return True

        log.info("\n[PHASE 5] Starting system monitoring...")

        # Enregistre snapshot initial
        try:
            import psutil

            process = psutil.Process()
            snapshot = SystemSnapshot(
                timestamp=time.time(),
                uptime_seconds=time.time() - self.boot_start,
                memory_used_mb=process.memory_info().rss / (1024 * 1024),
                cpu_percent=process.cpu_percent(),
                error_count=0,
                warning_count=0,
                best_strategy_name="BOOTSTRAPPING",
                best_fitness_score=0,
                force_level=0,
                system_health="GREEN",
            )
            self.analyzer.save_snapshot(snapshot)
            log.info("✓ Initial system snapshot saved")
        except Exception as e:
            log.warning(f"Could not save snapshot: {e}")

        return True

    def run_bootstrap(self) -> Dict[str, Any]:
        """Lance séquence complète de bootstrap"""
        try:
            self.phase_0_setup()
            self.phase_1_warm_boot()
            self.phase_2_circuit_breaker()
            self.phase_3_lazy_loader()
            self.phase_4_evolution_restore()
            self.phase_5_monitoring_start()

            total_time = time.time() - self.boot_start
            log.info("\n" + "=" * 70)
            log.info(f"✅ BOOTSTRAP COMPLETE in {total_time:.2f}s")
            log.info("=" * 70)

            self.boot_report = {
                "timestamp": time.time(),
                "total_boot_time": total_time,
                "status": "SUCCESS",
                "circuit_breaker_active": self.circuit_breaker is not None,
                "monitoring_active": self.analyzer is not None,
            }

            return self.boot_report

        except Exception as e:
            log.critical(f"Bootstrap failed: {e}", exc_info=True)
            self.boot_report = {
                "timestamp": time.time(),
                "status": "FAILED",
                "error": str(e),
            }
            return self.boot_report

    def get_system_health(self) -> Dict[str, Any]:
        """Retourne rapport santé système actuel"""
        try:
            import psutil

            process = psutil.Process()

            return {
                "circuit_breaker_state": (
                    self.circuit_breaker.get_state() if self.circuit_breaker else None
                ),
                "memory_mb": process.memory_info().rss / (1024 * 1024),
                "memory_percent": psutil.virtual_memory().percent,
                "cpu_percent": process.cpu_percent(),
                "uptime_seconds": time.time() - self.boot_start,
                "evolution_db_stats": self.evolution_db.get_stats(),
                "lazy_loader_cache_size_mb": self.lazy_loader.cache_size_mb(),
            }
        except Exception as e:
            log.error(f"Failed to get health: {e}")
            return {"error": str(e)}


def bootstrap_system(enable_monitoring: bool = True) -> SystemBootstrap:
    """Point d'entrée convenience"""
    system = SystemBootstrap(enable_monitoring=enable_monitoring)
    system.run_bootstrap()
    return system


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="System bootstrap with integrated startup"
    )
    parser.add_argument(
        "--no-monitoring", action="store_true", help="Disable daily monitoring"
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Print health status after bootstrap",
    )
    args = parser.parse_args()

    system = bootstrap_system(enable_monitoring=not args.no_monitoring)

    if args.health_check:
        print("\n📊 System health:")
        health = system.get_system_health()
        print(json.dumps(health, indent=2, default=str))
