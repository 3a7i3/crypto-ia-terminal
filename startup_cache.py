"""
startup_cache.py — Cache intelligent pour démarrage rapide à froid
Stocke configs, états, modèles en RAM pré-chargée
"""

import json
import pickle
import time
from pathlib import Path
from typing import Any, Dict, Optional
import logging

log = logging.getLogger("startup_cache")


class StartupCache:
    """Cache centralisé pour bootstrap rapide"""

    CACHE_DIR = Path("cache/startup")
    CONFIG_CACHE = CACHE_DIR / "configs.json"
    STATE_CACHE = CACHE_DIR / "runtime_state.pkl"
    MEMORY_CACHE = CACHE_DIR / "evolution_memory.pkl"
    TIMESTAMP_FILE = CACHE_DIR / "last_snapshot.txt"

    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._memory: Dict[str, Any] = {}
        self._load_timestamp = None

    def save_config(self, config_dict: Dict[str, Any], name: str = "main") -> bool:
        """Sauvegarde config INI parsée en JSON pour accès rapide"""
        try:
            cache_data = {"timestamp": time.time(), "config": config_dict, "name": name}
            with open(self.CONFIG_CACHE, "w") as f:
                json.dump(cache_data, f, indent=2)
            log.info(f"Config cache saved: {name}")
            return True
        except Exception as e:
            log.error(f"Failed to save config cache: {e}")
            return False

    def load_config(self, max_age_seconds: int = 3600) -> Optional[Dict[str, Any]]:
        """Charge config du cache si encore fraîche (défaut: 1h)"""
        if not self.CONFIG_CACHE.exists():
            return None
        try:
            with open(self.CONFIG_CACHE) as f:
                data = json.load(f)
            age = time.time() - data["timestamp"]
            if age > max_age_seconds:
                log.debug(f"Config cache too old: {age:.0f}s")
                return None
            log.info(f"Config cache loaded (age: {age:.0f}s)")
            return data["config"]
        except Exception as e:
            log.error(f"Failed to load config cache: {e}")
            return None

    def save_runtime_state(self, state: Dict[str, Any]) -> bool:
        """Sauvegarde snapshot état runtime (best genomes, iteration count, etc)"""
        try:
            snapshot = {
                "timestamp": time.time(),
                "state": state,
            }
            with open(self.STATE_CACHE, "wb") as f:
                pickle.dump(snapshot, f)
            log.info(f"Runtime state cached (keys: {list(state.keys())})")
            return True
        except Exception as e:
            log.error(f"Failed to save runtime state: {e}")
            return False

    def load_runtime_state(self, max_age_seconds: int = 300) -> Optional[Dict[str, Any]]:
        """Charge état runtime si fraîche (défaut: 5 min)
        Utile pour reprendre après crash ou redémarrage"""
        if not self.STATE_CACHE.exists():
            return None
        try:
            with open(self.STATE_CACHE, "rb") as f:
                snapshot = pickle.load(f)
            age = time.time() - snapshot["timestamp"]
            if age > max_age_seconds:
                log.debug(f"Runtime state cache too old: {age:.0f}s")
                return None
            log.info(f"Runtime state loaded (age: {age:.0f}s)")
            return snapshot["state"]
        except Exception as e:
            log.error(f"Failed to load runtime state: {e}")
            return None

    def save_memory_snapshot(self, memory: Dict[str, Any]) -> bool:
        """Sauvegarde meilleurs genomes + patterns d'apprentissage"""
        try:
            snapshot = {
                "timestamp": time.time(),
                "memory": memory,
                "version": "1.0"
            }
            with open(self.MEMORY_CACHE, "wb") as f:
                pickle.dump(snapshot, f)
            with open(self.TIMESTAMP_FILE, "w") as f:
                f.write(str(time.time()))
            log.info(f"Memory snapshot saved (size: {len(memory)} items)")
            return True
        except Exception as e:
            log.error(f"Failed to save memory snapshot: {e}")
            return False

    def load_memory_snapshot(self) -> Optional[Dict[str, Any]]:
        """Charge meilleurs genomes + patterns pour warm-start"""
        if not self.MEMORY_CACHE.exists():
            return None
        try:
            with open(self.MEMORY_CACHE, "rb") as f:
                snapshot = pickle.load(f)
            log.info(f"Memory snapshot loaded (version: {snapshot.get('version')})")
            return snapshot["memory"]
        except Exception as e:
            log.error(f"Failed to load memory snapshot: {e}")
            return None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Retourne statistiques de cache pour dashboard"""
        stats = {
            "config_cached": self.CONFIG_CACHE.exists(),
            "state_cached": self.STATE_CACHE.exists(),
            "memory_cached": self.MEMORY_CACHE.exists(),
        }
        if self.CONFIG_CACHE.exists():
            stats["config_size_kb"] = self.CONFIG_CACHE.stat().st_size / 1024
            stats["config_age_min"] = (time.time() - self.CONFIG_CACHE.stat().st_mtime) / 60

        if self.MEMORY_CACHE.exists():
            stats["memory_size_kb"] = self.MEMORY_CACHE.stat().st_size / 1024
            stats["memory_age_min"] = (time.time() - self.MEMORY_CACHE.stat().st_mtime) / 60

        return stats

    def clear_old_cache(self, days: int = 7) -> int:
        """Nettoie cache > N jours"""
        cutoff = time.time() - (days * 86400)
        removed = 0
        for cache_file in self.CACHE_DIR.glob("*"):
            if cache_file.is_file() and cache_file.stat().st_mtime < cutoff:
                try:
                    cache_file.unlink()
                    removed += 1
                except Exception as e:
                    log.error(f"Failed to remove {cache_file}: {e}")
        if removed > 0:
            log.info(f"Cleared {removed} old cache files")
        return removed


# Singleton global
_cache_instance: Optional[StartupCache] = None


def get_startup_cache() -> StartupCache:
    """Retourne instance unique de cache"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = StartupCache()
    return _cache_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cache = get_startup_cache()
    stats = cache.get_cache_stats()
    print(json.dumps(stats, indent=2))
