"""
persistent_warmup.py — CacheWarmer daemon thread avec refresh TTL-aware.

Garde les données OHLCV 1h + MTF (4h, 1d) toujours prêtes en mémoire
pour tous les symboles configurés. Le cache est rafraîchi automatiquement
avant l'expiration du TTL.

Activation dans advisor_loop.py :
    ADVISOR_PERSISTENT_WARMUP=true  (désactivé par défaut)
    ADVISOR_WARMUP_TTL=55           (secondes avant re-fetch, défaut 55s)
    ADVISOR_WARMUP_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT

Utilisation standalone :
    python -m quant_hedge_ai.persistent_warmup [--demo]

Architecture :
    ┌─────────────────────────────────────────────────────┐
    │  CacheWarmer (daemon thread)                        │
    │                                                     │
    │  ① startup  → pre-fetch tous symboles (1h+MTF)     │
    │  ② loop     → re-fetch symbols dont cache < TTL    │
    │  ③ get()    → retourne données depuis cache         │
    │                                                     │
    │  Résultat : cycle 1 voit toujours cache CHAUD       │
    └─────────────────────────────────────────────────────┘

Comparaison bootstrap vs cycle 1 :
    Sans CacheWarmer : cycle 1 = bootstrap + fetch 1h froid (~400ms/sym)
    Avec CacheWarmer : cycle 1 = 0ms fetch (cache déjà chaud)
    Gain estimé      : 400ms × N_SYMBOLS (ex: 1200ms pour 3 symboles)
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_ENABLED     = os.getenv("ADVISOR_PERSISTENT_WARMUP", "false").lower() == "true"
_TTL         = float(os.getenv("ADVISOR_WARMUP_TTL", "55"))       # secondes
_SYMBOLS_ENV = os.getenv("ADVISOR_WARMUP_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT")
_SYMBOLS     = [s.strip() for s in _SYMBOLS_ENV.split(",") if s.strip()]
_TIMEFRAMES  = ["1h", "4h", "1d"]
_LIMIT_MAP   = {"1h": int(os.getenv("ADVISOR_1H_LIMIT", "96")), "4h": 96, "1d": 60}
_POLL_SEC    = float(os.getenv("ADVISOR_WARMUP_POLL", "5"))       # intervalle de vérification TTL


# ── Structure de cache ─────────────────────────────────────────────────────────

@dataclass
class _CacheEntry:
    data:      list[Any]  # liste de bougies OHLCV
    fetched_at: float     # time.monotonic() au moment du fetch
    symbol:    str
    timeframe: str

    @property
    def age_s(self) -> float:
        return time.monotonic() - self.fetched_at

    @property
    def is_fresh(self) -> bool:
        return self.age_s < _TTL


@dataclass
class WarmupStats:
    """Métriques exportables pour comparaison bootstrap vs cycle 1."""
    startup_duration_ms: float = 0.0      # temps du premier fetch complet (tous sym + TF)
    total_fetches:       int   = 0        # nombre total de fetches effectués
    cache_hits:          int   = 0        # get() avec cache frais
    cache_misses:        int   = 0        # get() avec cache absent/expiré
    last_refresh_ms:     dict  = field(default_factory=dict)  # {sym_tf: ms}
    errors:              int   = 0


# ── CacheWarmer ───────────────────────────────────────────────────────────────

class CacheWarmer:
    """
    Daemon thread qui pré-charge et rafraîchit le cache OHLCV en arrière-plan.

    Usage :
        warmer = CacheWarmer(scanner=MarketScanner())
        warmer.start()           # lance le daemon
        warmer.wait_ready()      # attend le premier fetch complet (bloquant)

        data = warmer.get("BTC/USDT", "1h")   # retourne cache (jamais None si ready)

        warmer.compare_bootstrap_vs_cycle1()  # imprime le tableau comparatif
    """

    def __init__(
        self,
        scanner: Any = None,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        ttl: float = _TTL,
        poll_sec: float = _POLL_SEC,
    ) -> None:
        self._scanner    = scanner
        self._symbols    = symbols or _SYMBOLS
        self._timeframes = timeframes or _TIMEFRAMES
        self._ttl        = ttl
        self._poll_sec   = poll_sec
        self._cache: dict[str, _CacheEntry] = {}   # clé = "SYM/TF"
        self._lock   = threading.RLock()
        self._ready  = threading.Event()           # signalé après premier fetch complet
        self._stop   = threading.Event()
        self._thread: threading.Thread | None = None
        self.stats   = WarmupStats()
        self._t_start: float = 0.0

    # ── API publique ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._t_start = time.perf_counter()
        self._thread = threading.Thread(
            target=self._run,
            name="CacheWarmer",
            daemon=True,
        )
        self._thread.start()
        log.info("[CacheWarmer] démarré (%d sym × %d TF, TTL=%.0fs)",
                 len(self._symbols), len(self._timeframes), self._ttl)

    def stop(self) -> None:
        """Arrête le daemon proprement."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def wait_ready(self, timeout: float = 60.0) -> bool:
        """Attend que le premier fetch complet soit terminé."""
        return self._ready.wait(timeout=timeout)

    def get(self, symbol: str, timeframe: str = "1h") -> list[Any] | None:
        """
        Retourne les données depuis le cache.
        Incrémente cache_hits si frais, cache_misses sinon.
        """
        key = f"{symbol}/{timeframe}"
        with self._lock:
            entry = self._cache.get(key)
            if entry and entry.is_fresh:
                self.stats.cache_hits += 1
                return entry.data
            self.stats.cache_misses += 1
            return entry.data if entry else None   # retourne données périmées si disponibles

    def is_warm(self, symbol: str, timeframe: str = "1h") -> bool:
        """Retourne True si le cache est frais pour ce symbole/TF."""
        key = f"{symbol}/{timeframe}"
        with self._lock:
            entry = self._cache.get(key)
            return bool(entry and entry.is_fresh)

    def all_warm(self) -> bool:
        """Retourne True si tous les symboles × TF sont dans le cache frais."""
        return all(self.is_warm(s, tf) for s in self._symbols for tf in self._timeframes)

    # ── Boucle interne ────────────────────────────────────────────────────────

    def _run(self) -> None:
        """Boucle principale du daemon."""
        # ① Premier fetch complet (startup warmup)
        self._fetch_all(is_startup=True)
        self._ready.set()
        startup_ms = (time.perf_counter() - self._t_start) * 1000
        self.stats.startup_duration_ms = startup_ms
        log.info("[CacheWarmer] prêt après %.0fms (%.0fms/sym)",
                 startup_ms, startup_ms / max(len(self._symbols), 1))

        # ② Boucle de rafraîchissement TTL
        while not self._stop.is_set():
            self._stop.wait(self._poll_sec)
            if self._stop.is_set():
                break
            self._refresh_stale()

    def _fetch_all(self, is_startup: bool = False) -> None:
        """Fetch initial de tous les symboles et timeframes."""
        for sym in self._symbols:
            for tf in self._timeframes:
                if self._stop.is_set():
                    return
                self._fetch_one(sym, tf, is_startup=is_startup)

    def _refresh_stale(self) -> None:
        """Rafraîchit les entrées du cache dont l'âge dépasse TTL × 0.9."""
        threshold = self._ttl * 0.9   # refresh avant expiration
        stale = []
        with self._lock:
            for key, entry in self._cache.items():
                if entry.age_s >= threshold:
                    stale.append((entry.symbol, entry.timeframe))

        for sym, tf in stale:
            if self._stop.is_set():
                return
            self._fetch_one(sym, tf)

    def _fetch_one(self, symbol: str, timeframe: str, is_startup: bool = False) -> None:
        """Fetch une série OHLCV et la stocke dans le cache."""
        key = f"{symbol}/{timeframe}"
        limit = _LIMIT_MAP.get(timeframe, 96)
        t0 = time.perf_counter()
        try:
            if self._scanner is not None:
                data = self._scanner.fetch(symbol=symbol, timeframe=timeframe, limit=limit)
            else:
                # Mode synthétique pour tests / benchmarks
                data = _synthetic_ohlcv(symbol, timeframe, limit)

            elapsed_ms = (time.perf_counter() - t0) * 1000

            with self._lock:
                self._cache[key] = _CacheEntry(
                    data=data or [],
                    fetched_at=time.monotonic(),
                    symbol=symbol,
                    timeframe=timeframe,
                )
                self.stats.total_fetches += 1
                self.stats.last_refresh_ms[key] = round(elapsed_ms, 1)

            if not is_startup:
                log.debug("[CacheWarmer] refresh %s %s → %.0fms", symbol, timeframe, elapsed_ms)

        except Exception as exc:
            self.stats.errors += 1
            log.warning("[CacheWarmer] erreur fetch %s %s: %s", symbol, timeframe, exc)

    # ── Rapport comparatif ────────────────────────────────────────────────────

    def compare_bootstrap_vs_cycle1(self) -> None:
        """Imprime le tableau de comparaison bootstrap vs cycle 1."""
        s = self.stats
        n_sym = len(self._symbols)
        n_tf  = len(self._timeframes)

        # Estimation coût cycle 1 SANS cache (fetch froid × all sym × 1h)
        # Basé sur mesures fetch_audit : ~280ms froid, ~145ms chaud
        cold_fetch_ms_per_sym = 280.0
        cycle1_without_cache = cold_fetch_ms_per_sym * n_sym
        cycle1_with_cache    = 0.0    # cache hit ≈ 0ms
        gain_ms              = cycle1_without_cache - cycle1_with_cache

        print()
        print("=" * 64)
        print("  COMPARAISON BOOTSTRAP vs CYCLE 1 — CacheWarmer")
        print("=" * 64)
        print(f"  Symboles         : {', '.join(self._symbols)}")
        print(f"  Timeframes       : {', '.join(self._timeframes)}")
        print(f"  TTL cache        : {self._ttl:.0f}s")
        print()
        print(f"  Warmup startup   : {s.startup_duration_ms:.0f}ms")
        print(f"  Fetches total    : {s.total_fetches} ({n_sym}×{n_tf} TF)")
        print(f"  Erreurs          : {s.errors}")
        print()
        print("  Dernier refresh par cache :")
        for key, ms in sorted(s.last_refresh_ms.items()):
            fresh = self.is_warm(*key.split("/", 1))
            tag = "FRAIS" if fresh else "EXPIRE"
            print(f"    {key:<20} {ms:>6.0f}ms  [{tag}]")
        print()
        print(f"  IMPACT CYCLE 1 (estimé):")
        print(f"    Sans CacheWarmer : {cycle1_without_cache:.0f}ms fetch froid × {n_sym} sym")
        print(f"    Avec CacheWarmer : {cycle1_with_cache:.0f}ms (cache chaud)")
        print(f"    Gain             : +{gain_ms:.0f}ms  (≈{gain_ms/max(cycle1_without_cache,1)*100:.0f}%)")
        print()
        print(f"  Cache hits/misses : {s.cache_hits}/{s.cache_misses}")
        if s.cache_hits + s.cache_misses > 0:
            hr = s.cache_hits / (s.cache_hits + s.cache_misses)
            print(f"  Hit rate         : {hr:.0%}")
        print("=" * 64)
        print()


# ── Instance globale (singleton) ──────────────────────────────────────────────

_warmer: CacheWarmer | None = None
_warmer_lock = threading.Lock()


def get_warmer(scanner: Any = None) -> CacheWarmer:
    """Retourne le CacheWarmer singleton (créé si nécessaire)."""
    global _warmer
    if _warmer is None:
        with _warmer_lock:
            if _warmer is None:
                _warmer = CacheWarmer(scanner=scanner)
    return _warmer


def start_persistent_warmup(scanner: Any = None) -> CacheWarmer | None:
    """
    Démarre le CacheWarmer si ADVISOR_PERSISTENT_WARMUP=true.
    Retourne l'instance ou None si désactivé.
    """
    if not _ENABLED:
        return None
    warmer = get_warmer(scanner=scanner)
    warmer.start()
    return warmer


# ── Données synthétiques (tests/benchmarks) ──────────────────────────────────

def _synthetic_ohlcv(symbol: str, timeframe: str, limit: int = 96) -> list:
    """Génère des bougies OHLCV synthétiques pour tests."""
    seeds = {"BTC/USDT": 65_000, "ETH/USDT": 3_100, "SOL/USDT": 170}
    price = seeds.get(symbol, 100.0)
    rng = random.Random(hash(f"{symbol}{timeframe}"))
    tf_sec = {"1h": 3600, "4h": 14400, "1d": 86400}.get(timeframe, 3600)
    now_ms = int(time.time() * 1000)
    result = []
    for i in range(limit):
        price *= 1 + rng.gauss(0, 0.002)
        ts = now_ms - (limit - i) * tf_sec * 1000
        result.append([ts, price * 0.998, price * 1.002, price * 0.996, price, 1000.0 + rng.random() * 500])
    # Simule latence réseau synthétique
    time.sleep(rng.gauss(0.015, 0.003))
    return result


# ── Demo / benchmark CLI ──────────────────────────────────────────────────────

def _run_demo(n_cycles: int = 5) -> None:
    """Demo : compare bootstrap vs cycle 1 avec et sans CacheWarmer."""
    import sys

    print("\n" + "=" * 64)
    print("  DEMO CacheWarmer — Comparaison bootstrap vs cycle 1")
    print("=" * 64)

    # ── Sans CacheWarmer
    print("\n[1/2] Sans CacheWarmer (fetch froid au cycle 1)...")
    cold_times = []
    for run in range(3):
        t = time.perf_counter()
        for sym in _SYMBOLS:
            _synthetic_ohlcv(sym, "1h", 96)   # simule fetch froid
        cold_times.append((time.perf_counter() - t) * 1000)
    cold_mean = sum(cold_times) / len(cold_times)
    print(f"  Cycle 1 froid : {cold_mean:.0f}ms avg (3 runs)")

    # ── Avec CacheWarmer
    print("\n[2/2] Avec CacheWarmer (bootstrap en arrière-plan)...")
    t_boot = time.perf_counter()
    warmer = CacheWarmer(scanner=None, symbols=_SYMBOLS, timeframes=["1h"], ttl=30.0)
    warmer.start()
    ready = warmer.wait_ready(timeout=30.0)
    bootstrap_ms = (time.perf_counter() - t_boot) * 1000

    if not ready:
        print("  ERREUR: warmup timeout")
        return

    # Cycle 1 avec cache chaud
    warm_times = []
    for run in range(3):
        t = time.perf_counter()
        for sym in _SYMBOLS:
            data = warmer.get(sym, "1h")
            assert data is not None, f"Cache manquant pour {sym}"
        warm_times.append((time.perf_counter() - t) * 1000)
    warm_mean = sum(warm_times) / len(warm_times)

    warmer.stop()

    # ── Rapport
    print()
    print("=" * 64)
    print("  RESULTATS")
    print("=" * 64)
    print(f"  Bootstrap CacheWarmer : {bootstrap_ms:.0f}ms")
    print(f"  Cycle 1 FROID         : {cold_mean:.1f}ms")
    print(f"  Cycle 1 CHAUD (cache) : {warm_mean:.2f}ms")
    gain = cold_mean - warm_mean
    print(f"  Gain cycle 1          : +{gain:.0f}ms (+{gain/max(cold_mean,0.1)*100:.0f}%)")
    print()
    print(f"  Note: bootstrap ({bootstrap_ms:.0f}ms) overlaps avec init loop")
    print(f"        → temps effectif gagné = max(0, {cold_mean:.0f} - overlap)")
    print()
    warmer.compare_bootstrap_vs_cycle1()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    parser = argparse.ArgumentParser(description="CacheWarmer — warmup persistant OHLCV")
    parser.add_argument("--demo",    action="store_true", help="Lance la demo comparaison")
    parser.add_argument("--cycles",  type=int, default=5, help="Nombre de cycles demo")
    args = parser.parse_args()

    if args.demo:
        _run_demo(args.cycles)
    else:
        # Mode standalone : démarre le warmer et maintient actif
        warmer = CacheWarmer(scanner=None)
        warmer.start()
        print(f"CacheWarmer démarré. CTRL+C pour arrêter.")
        try:
            warmer.wait_ready(timeout=30.0)
            warmer.compare_bootstrap_vs_cycle1()
            while True:
                time.sleep(10)
                all_w = warmer.all_warm()
                print(f"  Cache: {'CHAUD' if all_w else 'EN COURS'} | hits={warmer.stats.cache_hits} | fetches={warmer.stats.total_fetches}")
        except KeyboardInterrupt:
            warmer.stop()
            print("CacheWarmer arrêté.")
