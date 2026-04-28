# feature_cache.py
"""
Module pour le caching des features calculées.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=100)
def compute_feature(name: str, *args: Any) -> float:
    """Calcule et cache une feature par son nom et ses paramètres.

    Les implémentations concrètes sont dispatchées par nom de feature.
    Ajouter de nouveaux cas dans _FEATURE_REGISTRY pour étendre.
    """
    handler = _FEATURE_REGISTRY.get(name)
    if handler is None:
        raise ValueError(
            f"Feature inconnue: '{name}'. Features disponibles: {list(_FEATURE_REGISTRY)}"
        )
    return handler(*args)


def _rolling_volatility(values: tuple[float, ...], window: int = 20) -> float:
    import statistics

    series = list(values)
    if len(series) < 2:
        return 0.0
    tail = series[-window:]
    returns = [
        tail[i] / tail[i - 1] - 1 for i in range(1, len(tail)) if tail[i - 1] != 0
    ]
    return statistics.stdev(returns) if len(returns) >= 2 else 0.0


def _mean(values: tuple[float, ...]) -> float:
    return sum(values) / len(values) if values else 0.0


def _correlation(xs: tuple[float, ...], ys: tuple[float, ...]) -> float:
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    mx, my = sum(xs[:n]) / n, sum(ys[:n]) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = sum((xs[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ys[i] - my) ** 2 for i in range(n)) ** 0.5
    return num / (dx * dy) if dx * dy != 0 else 0.0


_FEATURE_REGISTRY: dict[str, Any] = {
    "rolling_volatility": _rolling_volatility,
    "mean": _mean,
    "correlation": _correlation,
}


def register_feature(name: str, handler) -> None:
    """Enregistre un handler personnalisé dans le registre de features.

    Invalide le cache LRU car les résultats précédents peuvent être obsolètes.

    Raises:
        TypeError: si handler n'est pas callable.
    """
    if not callable(handler):
        raise TypeError(f"handler doit être callable, reçu: {type(handler).__name__}")
    _FEATURE_REGISTRY[name] = handler
    compute_feature.cache_clear()


def list_features() -> list[str]:
    """Retourne la liste des noms de features disponibles."""
    return list(_FEATURE_REGISTRY)


def clear_cache() -> None:
    compute_feature.cache_clear()
