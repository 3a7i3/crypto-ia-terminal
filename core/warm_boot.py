"""
warm_boot.py — Orchestration intelligente du démarrage à froid
Parallélise charge des configs, LM Studio, état, et warmup MTF
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger("warm_boot")


@dataclass
class BootPhase:
    """Étape de bootstrap avec timing"""

    name: str
    phase_num: int
    start_time: float = 0.0
    end_time: float = 0.0
    success: bool = False
    error: Optional[str] = None

    def duration_ms(self) -> float:
        if self.end_time == 0:
            return 0
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phase": self.phase_num,
            "duration_ms": self.duration_ms(),
            "success": self.success,
            "error": self.error,
        }


class WarmBootManager:
    """Orchestrer démarrage parallèle multi-étapes"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.phases: List[BootPhase] = []
        self.boot_start = time.time()
        self.results: Dict[str, Any] = {}

    def _load_env(self) -> BootPhase:
        """Phase 1: Charger .env"""
        phase = BootPhase(name="LoadEnv", phase_num=1)
        phase.start_time = time.time()
        try:
            load_dotenv()
            log.info("✓ Environment loaded")
            phase.success = True
        except Exception as e:
            phase.error = str(e)
            log.error(f"✗ Failed to load env: {e}")
        finally:
            phase.end_time = time.time()
        return phase

    def _load_config_cache(self) -> BootPhase:
        """Phase 2: Charger configs du cache"""
        phase = BootPhase(name="LoadConfigCache", phase_num=2)
        phase.start_time = time.time()
        try:
            from infra.startup_cache import get_startup_cache

            cache = get_startup_cache()
            config = cache.load_config(max_age_seconds=7200)  # 2h
            if config:
                self.results["config"] = config
                self.results["config_from_cache"] = True
                log.info(f"✓ Config loaded from cache ({len(config)} keys)")
                phase.success = True
            else:
                self.results["config_from_cache"] = False
                log.debug("Config cache miss or expired")
                phase.success = True  # Pas critique
        except Exception as e:
            phase.error = str(e)
            log.warning(f"⚠ Config cache load failed: {e}")
        finally:
            phase.end_time = time.time()
        return phase

    def _init_lm_studio(self) -> BootPhase:
        """Phase 3: Vérifier LM Studio disponible (non-bloquant)"""
        phase = BootPhase(name="CheckLMStudio", phase_num=3)
        phase.start_time = time.time()
        try:
            import requests

            host = os.getenv("LM_STUDIO_HOST", "127.0.0.1")
            port = os.getenv("LM_STUDIO_PORT", "1234")
            url = f"http://{host}:{port}/v1/models"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                self.results["lm_studio_available"] = True
                self.results["lm_studio_models"] = len(models)
                log.info(f"✓ LM Studio: {len(models)} models loaded")
                phase.success = True
            else:
                self.results["lm_studio_available"] = False
                log.warning(f"⚠ LM Studio returned {resp.status_code}")
                phase.success = True
        except Exception as e:
            phase.error = str(e)
            self.results["lm_studio_available"] = False
            log.debug(f"LM Studio check failed (will continue): {e}")
            phase.success = True  # Non-bloquant
        finally:
            phase.end_time = time.time()
        return phase

    def _load_runtime_state(self) -> BootPhase:
        """Phase 4: Reprendre état runtime du checkpoint"""
        phase = BootPhase(name="LoadRuntimeState", phase_num=4)
        phase.start_time = time.time()
        try:
            from infra.startup_cache import get_startup_cache

            cache = get_startup_cache()
            state = cache.load_runtime_state(max_age_seconds=600)  # 10 min
            if state:
                self.results["runtime_state"] = state
                self.results["resume_from_checkpoint"] = True
                it = state.get("iteration", "N/A")
                log.info(f"✓ Runtime state restored (iteration: {it})")
                phase.success = True
            else:
                log.debug("Runtime state cache miss")
                phase.success = True  # Pas critique
        except Exception as e:
            phase.error = str(e)
            log.warning(f"⚠ Runtime state load failed: {e}")
        finally:
            phase.end_time = time.time()
        return phase

    def _load_evolution_memory(self) -> BootPhase:
        """Phase 5: Charger meilleurs genomes + patterns d'apprentissage"""
        phase = BootPhase(name="LoadEvolutionMemory", phase_num=5)
        phase.start_time = time.time()
        try:
            from infra.startup_cache import get_startup_cache

            cache = get_startup_cache()
            memory = cache.load_memory_snapshot()
            if memory:
                self.results["evolution_memory"] = memory
                self.results["memory_items"] = len(memory)
                log.info(f"✓ Evolution memory loaded ({len(memory)} items)")
                phase.success = True
            else:
                log.debug("Evolution memory cache miss")
                phase.success = True
        except Exception as e:
            phase.error = str(e)
            log.warning(f"⚠ Evolution memory load failed: {e}")
        finally:
            phase.end_time = time.time()
        return phase

    def _preload_critical_modules(self) -> BootPhase:
        """Phase 6: Import modules critiques (non-lazy)"""
        phase = BootPhase(name="PreloadModules", phase_num=6)
        phase.start_time = time.time()
        try:
            import_times = {}
            modules_to_load = [
                ("config_utils", "config_utils"),
                ("quant_hedge_ai.ai_evolution.strategy_memory", "strategy_memory"),
            ]
            for mod_path, short_name in modules_to_load:
                t0 = time.time()
                try:
                    __import__(mod_path)
                    t1 = time.time()
                    import_times[short_name] = (t1 - t0) * 1000
                except ImportError:
                    log.debug(f"Module {mod_path} not critical, skipped")

            self.results["module_load_times"] = import_times
            log.info(f"✓ Critical modules preloaded ({len(import_times)} items)")
            phase.success = True
        except Exception as e:
            phase.error = str(e)
            log.warning(f"⚠ Module preload failed: {e}")
        finally:
            phase.end_time = time.time()
        return phase

    def boot_parallel(self) -> Dict[str, Any]:
        """Lance phases 1-6 en parallèle où possible"""
        log.info("=" * 60)
        log.info("🚀 WARM BOOT SEQUENCE STARTED")
        log.info("=" * 60)

        # Phase 1 doit être séquentielle (setup env)
        phase1 = self._load_env()
        self.phases.append(phase1)

        # Phases 2-6 peuvent être parallèles
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._load_config_cache): "ConfigCache",
                executor.submit(self._init_lm_studio): "LMStudio",
                executor.submit(self._load_runtime_state): "RuntimeState",
                executor.submit(self._load_evolution_memory): "EvolutionMemory",
                executor.submit(self._preload_critical_modules): "Modules",
            }

            for future in as_completed(futures):
                phase = future.result()
                self.phases.append(phase)

        boot_total = time.time() - self.boot_start
        self._print_boot_summary(boot_total)
        return self.results

    def _print_boot_summary(self, total_ms: float):
        """Affiche résumé bootstrap formaté"""
        log.info("=" * 60)
        log.info("📊 BOOT SUMMARY")
        log.info("=" * 60)
        for phase in sorted(self.phases, key=lambda p: p.phase_num):
            status = "✓" if phase.success else "✗"
            duration = phase.duration_ms()
            msg = f"{status} Phase {phase.phase_num}: {phase.name:20} {duration:7.1f}ms"
            if phase.error:
                msg += f" ({phase.error[:40]})"
            log.info(msg)

        log.info("=" * 60)
        log.info(f"🎯 TOTAL BOOT TIME: {total_ms * 1000:.0f}ms")
        log.info("=" * 60)

    def get_boot_report(self) -> Dict[str, Any]:
        """Génère rapport boot pour monitoring"""
        return {
            "timestamp": time.time(),
            "total_boot_time_ms": (time.time() - self.boot_start) * 1000,
            "phases": [p.to_dict() for p in self.phases],
            "results": self.results,
        }

    def save_boot_report(self, path: str = "logs/boot_report.json") -> bool:
        """Sauvegarde rapport pour analyse"""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            report = self.get_boot_report()
            with open(path, "w") as f:
                json.dump(report, f, indent=2)
            log.info(f"Boot report saved: {path}")
            return True
        except Exception as e:
            log.error(f"Failed to save boot report: {e}")
            return False


async def warm_boot_async() -> Dict[str, Any]:
    """Lance bootstrap et retourne résultats"""
    mgr = WarmBootManager(max_workers=4)
    return mgr.boot_parallel()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s - %(message)s"
    )
    mgr = WarmBootManager()
    results = mgr.boot_parallel()
    mgr.save_boot_report()
    print("\n📦 Boot results:")
    print(json.dumps(results, indent=2, default=str))
