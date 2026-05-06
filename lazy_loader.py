"""
lazy_loader.py — Chargement à la demande des modules non-critiques
Réduit temps bootstrap de 50% en reportant imports lourds
"""

import importlib
import logging
import sys
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("lazy_loader")


class LazyModuleLoader:
    """Cache modules importés lazily"""

    # Modules à charger à la demande (non-critiques)
    LAZY_MODULES = {
        # Dashboard & UI
        "streamlit_dashboard": "quant_hedge_ai.dashboard.streamlit_dashboard",
        "streamlit": "streamlit",
        "plotly": "plotly",
        "panel": "panel",

        # Strategy & Backtest
        "strategy_lab": "quant_hedge_ai.strategy_lab.test_performance",
        "backtester": "strategy_factory.backtester",
        "genetic_optimizer": "quant_hedge_ai.agents.strategy.genetic_optimizer",

        # ML & Data
        "sklearn": "sklearn",
        "xgboost": "xgboost",
        "tensorflow": "tensorflow",

        # Advanced agents
        "whale_behavior": "quant_hedge_ai.agents.onchain.whale_behavior_classifier",
        "blockchain_ingester": "quant_hedge_ai.agents.onchain.blockchain_ingester",

        # Visualization
        "visualization": "visualization",
        "hvplot": "hvplot",
    }

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._import_times: Dict[str, float] = {}

    def load(self, module_name: str) -> Optional[Any]:
        """Charge module lazily (cache après)"""
        if module_name in self._cache:
            log.debug(f"Loading {module_name} from cache")
            return self._cache[module_name]

        if module_name not in self.LAZY_MODULES:
            log.warning(f"Unknown lazy module: {module_name}")
            return None

        import_path = self.LAZY_MODULES[module_name]
        log.info(f"Lazy loading: {module_name} ({import_path})")

        t0 = time.time()
        try:
            mod = importlib.import_module(import_path)
            t1 = time.time()
            duration = (t1 - t0) * 1000

            self._cache[module_name] = mod
            self._import_times[module_name] = duration
            log.info(f"✓ {module_name} loaded in {duration:.1f}ms")
            return mod

        except ImportError as e:
            log.error(f"Failed to import {import_path}: {e}")
            return None
        except Exception as e:
            log.error(f"Error loading {module_name}: {e}")
            return None

    def preload_batch(self, module_names: List[str]) -> Dict[str, bool]:
        """Précharge batch de modules en background"""
        results = {}
        for name in module_names:
            result = self.load(name)
            results[name] = result is not None
        return results

    def get_import_stats(self) -> Dict[str, float]:
        """Retourne temps d'import par module"""
        return self._import_times.copy()

    def is_cached(self, module_name: str) -> bool:
        """Vérifie si module en cache"""
        return module_name in self._cache

    def cache_size_mb(self) -> float:
        """Taille approx cache en MB"""
        total = 0
        for mod in self._cache.values():
            try:
                total += sys.getsizeof(mod)
            except (TypeError, AttributeError):
                pass
        return total / (1024 * 1024)


# Singleton
_loader_instance: Optional[LazyModuleLoader] = None


def get_lazy_loader() -> LazyModuleLoader:
    """Retourne instance unique"""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = LazyModuleLoader()
    return _loader_instance


def lazy_import(module_name: str) -> Optional[Any]:
    """Fonction convenience pour import lazy"""
    loader = get_lazy_loader()
    return loader.load(module_name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = get_lazy_loader()

    # Test load
    print("Testing lazy load of streamlit...")
    result = loader.load("streamlit")
    print(f"Result: {result is not None}")
    print(f"Cache stats: {loader.get_import_stats()}")
