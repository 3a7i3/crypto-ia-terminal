"""
feature_store.py — Central Feature Store with Versioning & Caching

Stocke, versionne et sert les features calculées.
Permet le time-travel (accès à n'importe quelle version passée),
la détection de drift, et le recalcul incrémental.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_STORE_PATH = Path("databases/feature_store.jsonl")


@dataclass
class FeatureVector:
    symbol: str
    timeframe: str
    version: str
    timestamp: float
    features: dict[str, float]
    source_hash: str = ""       # hash des candles source
    quality_score: float = 1.0  # [0,1] : qualité des données entrantes

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "version": self.version,
            "timestamp": self.timestamp,
            "features": self.features,
            "source_hash": self.source_hash,
            "quality_score": self.quality_score,
        }


class FeatureStore:
    """
    Store central de features avec cache en mémoire + persistance JSONL.
    - Cache LRU par (symbol, timeframe, version)
    - Détection automatique de drift (variation > seuil)
    - Recalcul déclenché si le hash source change
    """

    CURRENT_VERSION = "v2.0"

    def __init__(self, store_path: Path | None = None, ttl_seconds: float = 300.0) -> None:
        self._path = store_path or _STORE_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, FeatureVector] = {}
        self._history: dict[str, list[FeatureVector]] = defaultdict(list)
        self._ttl = ttl_seconds
        self._drift_alerts: list[dict] = []

    # ------------------------------------------------------------------
    # API principale
    # ------------------------------------------------------------------

    def put(
        self,
        symbol: str,
        timeframe: str,
        features: dict[str, float],
        source_candles: list | None = None,
        version: str | None = None,
    ) -> FeatureVector:
        ver = version or self.CURRENT_VERSION
        src_hash = self._hash_candles(source_candles) if source_candles else ""
        fv = FeatureVector(
            symbol=symbol,
            timeframe=timeframe,
            version=ver,
            timestamp=time.time(),
            features=features,
            source_hash=src_hash,
            quality_score=self._compute_quality(features),
        )
        key = self._key(symbol, timeframe, ver)
        prev = self._cache.get(key)
        if prev:
            self._check_drift(prev, fv)
        self._cache[key] = fv
        self._history[key].append(fv)
        self._persist(fv)
        return fv

    def get(
        self,
        symbol: str,
        timeframe: str = "1h",
        version: str | None = None,
        max_age: float | None = None,
    ) -> FeatureVector | None:
        ver = version or self.CURRENT_VERSION
        key = self._key(symbol, timeframe, ver)
        fv = self._cache.get(key)
        if fv is None:
            return None
        age = time.time() - fv.timestamp
        effective_ttl = max_age if max_age is not None else self._ttl
        if age > effective_ttl:
            logger.debug("[FeatureStore] %s stale (age=%.0fs)", key, age)
            return None
        return fv

    def needs_recompute(
        self,
        symbol: str,
        timeframe: str,
        source_candles: list,
        version: str | None = None,
    ) -> bool:
        ver = version or self.CURRENT_VERSION
        fv = self.get(symbol, timeframe, ver)
        if fv is None:
            return True
        new_hash = self._hash_candles(source_candles)
        return fv.source_hash != new_hash

    def history(self, symbol: str, timeframe: str = "1h", n: int = 10) -> list[FeatureVector]:
        key = self._key(symbol, timeframe, self.CURRENT_VERSION)
        return self._history[key][-n:]

    def drift_alerts(self) -> list[dict]:
        alerts = list(self._drift_alerts)
        self._drift_alerts.clear()
        return alerts

    def all_keys(self) -> list[str]:
        return list(self._cache.keys())

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _key(self, symbol: str, timeframe: str, version: str) -> str:
        return f"{symbol}|{timeframe}|{version}"

    def _hash_candles(self, candles: list) -> str:
        if not candles:
            return ""
        payload = str([(c[0], c[4]) for c in candles[-5:] if len(c) >= 5])
        return hashlib.md5(payload.encode()).hexdigest()[:8]

    def _compute_quality(self, features: dict[str, float]) -> float:
        if not features:
            return 0.0
        valid = sum(1 for v in features.values() if v is not None and v == v)  # NaN check
        return valid / len(features)

    def _check_drift(self, old: FeatureVector, new: FeatureVector) -> None:
        drift_threshold = 0.30
        drifted = []
        for k, new_val in new.features.items():
            old_val = old.features.get(k)
            if old_val is None or old_val == 0:
                continue
            change = abs(new_val - old_val) / abs(old_val)
            if change > drift_threshold:
                drifted.append({"feature": k, "old": old_val, "new": new_val, "change_pct": change})
        if drifted:
            alert = {
                "symbol": new.symbol,
                "timeframe": new.timeframe,
                "timestamp": new.timestamp,
                "drifted_features": drifted,
            }
            self._drift_alerts.append(alert)
            logger.warning("[FeatureStore] DRIFT detected on %s/%s: %d features", new.symbol, new.timeframe, len(drifted))

    def _persist(self, fv: FeatureVector) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(fv.to_dict()) + "\n")
        except Exception as exc:
            logger.debug("[FeatureStore] persist error: %s", exc)
