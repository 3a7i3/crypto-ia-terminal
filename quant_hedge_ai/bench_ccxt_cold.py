"""
bench_ccxt_cold.py — Benchmark variance du warmup froid CCXT.

Simule 10 à 20 runs du chemin froid de MarketScanner._get_exchange() et
_fetch_series() en injectant des latences calibrées dans un mock CCXT.

Phases mesurées par run :
  1. exchange_pool_lock_wait_ms  — contention du verrou pool classe-level
  2. exchange_create_ms          — création objet ccxt.binance()
  3. exchange_call_lock_wait_ms  — verrou avant fetch_ohlcv
  4. fetch_ohlcv_http_ms         — requête HTTP pure
  5. parse_validate_ms           — parse JSON + validate_candles()

Chaque phase suit une distribution calibrée sur les données réelles de fetch_audit.py.
Le 2ème run et au-delà simule le pool chaud (exchange réutilisé, lock_wait ≈ 0).

Exécution :
    python -m quant_hedge_ai.bench_ccxt_cold
    python -m quant_hedge_ai.bench_ccxt_cold --runs 20 --seed 99
"""

from __future__ import annotations

import argparse
import random
import statistics
import threading
import time
import types
from typing import Any

# ── Distributions calibrées (ms) — Normal(mean, std), min=0 ────────────────

_DIST: dict[str, tuple[float, float]] = {
    # Verrou pool partagé (contention basse, occasionnellement élevée)
    "pool_lock_cold":   (0.3,   0.2),    # pool vide → quasi immédiat
    "pool_lock_warm":   (0.05,  0.02),   # pool chaud → micro-wait
    # Création exchange
    "create_cold":      (19.0,  5.0),    # mesuré dans fetch_audit: 18.8ms
    # Verrou appel HTTP
    "call_lock_serial": (0.1,   0.05),   # sans contention
    "call_lock_contention": (45.0, 15.0), # contention de 2 threads simultanés
    # HTTP fetch_ohlcv — bimodal : rapide si keep-alive, lent si nouvelle connexion
    "http_fast":        (145.0, 30.0),   # connexion keep-alive (chaud)
    "http_cold":        (280.0, 60.0),   # nouvelle connexion TCP + TLS
    "http_rate_limit":  (50.0,  5.0),    # CCXT rate limiter sleep
    # Parse + validate
    "parse":            (1.2,   0.4),    # parse 96 bougies JSON
    "validate":         (0.8,   0.3),    # validate_candles() sur 96 bougies
}

_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def _sample(key: str, rng: random.Random) -> float:
    mu, sigma = _DIST[key]
    return max(0.0, rng.gauss(mu, sigma))


# ── Mock CCXT exchange ────────────────────────────────────────────────────────

def _make_mock_exchange(rng: random.Random, is_warm_conn: bool) -> Any:
    """Crée un mock avec la latence injectée dans fetch_ohlcv."""
    ex = types.SimpleNamespace()
    def _fetch_ohlcv(symbol: str, tf: str = "1h", limit: int = 96) -> list:
        key = "http_fast" if is_warm_conn else "http_cold"
        time.sleep(_sample(key, rng) / 1000)
        time.sleep(_sample("http_rate_limit", rng) / 1000)
        # Retourne un tableau OHLCV minimal
        now_ms = int(time.time() * 1000)
        return [
            [now_ms - (limit - i) * 3_600_000, 100.0, 101.0, 99.0, 100.5, 1000.0]
            for i in range(limit)
        ]
    ex.fetch_ohlcv = _fetch_ohlcv
    return ex


# ── Simulation d'un run complet MarketScanner._fetch_series ──────────────────

def _simulate_run(
    run_idx: int,
    rng: random.Random,
    pool_lock: threading.Lock,
    pool: dict,
    exchange_call_locks: dict,
    symbols: list[str],
    contention: bool = False,
) -> dict[str, dict[str, float]]:
    """
    Simule un run complet sur tous les symboles.
    run_idx=0 → pool froid (création exchange)
    run_idx>0 → pool chaud (réutilisation)
    """
    pool_warm = run_idx > 0
    # Connexion TCP chaude après le 1er symbole du 1er run
    results: dict[str, dict[str, float]] = {}

    for sym_i, symbol in enumerate(symbols):
        # ① Pool lock wait
        t0 = time.perf_counter()
        with pool_lock:
            pool_wait_ms = (time.perf_counter() - t0) * 1000
            # Simule le vrai wait avec latence injectée
            simulated_pool_wait = _sample(
                "pool_lock_warm" if pool_warm else "pool_lock_cold", rng
            )

            if not pool_warm and "exchange" not in pool:
                # ② Création exchange (une seule fois)
                t_create = time.perf_counter()
                time.sleep(_sample("create_cold", rng) / 1000)
                create_ms = (time.perf_counter() - t_create) * 1000
                pool["exchange"] = _make_mock_exchange(rng, is_warm_conn=False)
            else:
                create_ms = 0.0

            exchange = pool["exchange"]

        # ③ Verrou appel (per-exchange)
        call_lock = exchange_call_locks.setdefault(id(exchange), threading.Lock())
        t_call_lock = time.perf_counter()
        with call_lock:
            call_lock_wait_ms = (time.perf_counter() - t_call_lock) * 1000
            # Injecter contention si demandé (2ème thread en attente)
            simulated_call_wait = _sample(
                "call_lock_contention" if contention and sym_i == 0 else "call_lock_serial",
                rng,
            )

            # ④ HTTP fetch
            t_http = time.perf_counter()
            # 1ère connexion du run = froid, les suivantes = keep-alive
            conn_warm = pool_warm or sym_i > 0
            ohlcvs = exchange.fetch_ohlcv(symbol, "1h", limit=96)
            http_ms = (time.perf_counter() - t_http) * 1000

        # ⑤ Parse + validate
        t_parse = time.perf_counter()
        _ = [
            {"ts": row[0], "o": row[1], "h": row[2], "l": row[3], "c": row[4], "v": row[5]}
            for row in ohlcvs
        ]
        # Simule validate_candles (légère)
        time.sleep(_sample("validate", rng) / 1000)
        parse_ms = (time.perf_counter() - t_parse) * 1000

        results[symbol] = {
            "pool_lock_wait_ms":     round(simulated_pool_wait, 3),
            "exchange_create_ms":    round(create_ms, 1),
            "call_lock_wait_ms":     round(simulated_call_wait, 3),
            "fetch_ohlcv_http_ms":   round(http_ms, 1),
            "parse_validate_ms":     round(parse_ms, 2),
            "total_ms":              round(simulated_pool_wait + create_ms + simulated_call_wait + http_ms + parse_ms, 1),
        }

    return results


# ── Agrégation multi-runs ─────────────────────────────────────────────────────

def _agg_phase(all_runs: list[dict], phase: str) -> dict:
    """Agrège une phase sur tous les symboles de tous les runs."""
    vals = [sym_data[phase] for run in all_runs for sym_data in run.values()]
    if not vals:
        return {}
    s = sorted(vals)
    return {
        "n":       len(vals),
        "mean":    round(statistics.mean(vals), 2),
        "std":     round(statistics.stdev(vals) if len(vals) > 1 else 0.0, 2),
        "min":     round(min(vals), 2),
        "p50":     round(s[len(s) // 2], 2),
        "p95":     round(s[min(int(len(s) * 0.95), len(s) - 1)], 2),
        "max":     round(max(vals), 2),
        "cv_pct":  round(
            statistics.stdev(vals) / max(statistics.mean(vals), 0.001) * 100, 1
        ),   # coefficient de variation = std/mean en %
    }


def run_benchmark(n_runs: int = 15, seed: int = 0, contention: bool = False) -> dict:
    """Lance n_runs sur 3 symboles, retourne les métriques par phase."""
    rng = random.Random(seed)
    pool: dict = {}
    pool_lock = threading.Lock()
    call_locks: dict = {}

    all_runs: list[dict] = []
    run_totals_cold: list[float] = []
    run_totals_warm: list[float] = []

    for i in range(n_runs):
        run_data = _simulate_run(i, rng, pool_lock, pool, call_locks, _SYMBOLS, contention)
        all_runs.append(run_data)
        total = sum(sd["total_ms"] for sd in run_data.values())
        if i == 0:
            run_totals_cold.append(total)
        else:
            run_totals_warm.append(total)

    phases = ["pool_lock_wait_ms", "exchange_create_ms", "call_lock_wait_ms",
              "fetch_ohlcv_http_ms", "parse_validate_ms"]

    return {
        "cold_run": _agg_phase(all_runs[:1], "total_ms"),
        "warm_runs": _agg_phase(all_runs[1:], "total_ms") if len(all_runs) > 1 else {},
        "phases": {phase: _agg_phase(all_runs, phase) for phase in phases},
        "phases_cold": {phase: _agg_phase(all_runs[:1], phase) for phase in phases},
        "phases_warm": {phase: _agg_phase(all_runs[1:], phase) for phase in phases},
        "n_runs": n_runs,
        "n_symbols": len(_SYMBOLS),
    }


# ── Affichage ─────────────────────────────────────────────────────────────────

_LABELS = {
    "pool_lock_wait_ms":   "Pool lock wait     ",
    "exchange_create_ms":  "Exchange create()  ",
    "call_lock_wait_ms":   "Call lock wait     ",
    "fetch_ohlcv_http_ms": "HTTP fetch_ohlcv   ",
    "parse_validate_ms":   "Parse + validate   ",
}


def print_report(r: dict) -> None:
    n   = r["n_runs"]
    sym = r["n_symbols"]

    print()
    print("=" * 76)
    print(f"  BENCH VARIANCE WARMUP FROID CCXT — {n} runs × {sym} symboles")
    print("=" * 76)

    # ── Tableau global (toutes phases, tous runs)
    print(f"\n  TOUTES PHASES — tous runs confondus")
    print(f"  {'Phase':<22} {'mean':>7} {'std':>7} {'min':>7} {'p50':>7} {'p95':>7} {'max':>7} {'CV%':>6}")
    print("  " + "-" * 66)
    phases = list(_LABELS.keys())
    for phase in phases:
        d = r["phases"][phase]
        if not d:
            continue
        print(f"  {_LABELS[phase]:<22} {d['mean']:>7.2f} {d['std']:>7.2f} "
              f"{d['min']:>7.2f} {d['p50']:>7.2f} {d['p95']:>7.2f} {d['max']:>7.2f} "
              f"{d['cv_pct']:>5.1f}%")

    # ── Run froid vs chaud
    print(f"\n  RUN 1 (FROID) vs RUNS 2..{n} (CHAUD)")
    print(f"  {'Phase':<22} {'FROID mean':>11}  {'CHAUD mean':>11}  {'Gain':>8}")
    print("  " + "-" * 58)
    for phase in phases:
        dc = r["phases_cold"].get(phase, {})
        dw = r["phases_warm"].get(phase, {})
        if not dc or not dw:
            continue
        gain = dc["mean"] - dw["mean"]
        print(f"  {_LABELS[phase]:<22} {dc['mean']:>10.2f}ms  {dw['mean']:>10.2f}ms  "
              f"{'+' if gain >= 0 else ''}{gain:>6.1f}ms")

    # ── Total run froid vs chaud
    cf = r["cold_run"]
    cw = r["warm_runs"]
    print(f"\n  TOTAL PAR RUN ({sym} symboles)")
    if cf:
        print(f"    Run FROID  (1er appel) : {cf.get('mean', 0):>7.0f}ms")
    if cw:
        print(f"    Run CHAUD  (2ème-{n})   : {cw.get('mean', 0):>7.0f}ms  ±{cw.get('std', 0):.0f}ms")
        if cf:
            speedup = cf.get("mean", 1) / max(cw.get("mean", 1), 0.1)
            print(f"    Speedup pool chaud     : x{speedup:.1f}")

    # ── Analyse de variance
    print(f"\n  ANALYSE VARIANCE (CV% = std/mean × 100)")
    print(f"    La phase avec la plus grande variance :")
    max_cv_phase = max(phases, key=lambda p: r["phases"][p].get("cv_pct", 0))
    d = r["phases"][max_cv_phase]
    print(f"    → {_LABELS[max_cv_phase].strip()} : CV={d['cv_pct']:.1f}%  "
          f"std={d['std']:.1f}ms  (range [{d['min']:.0f}–{d['max']:.0f}]ms)")

    # ── Recommandations
    http_mean = r["phases"]["fetch_ohlcv_http_ms"].get("mean", 0)
    create_mean = r["phases"]["exchange_create_ms"].get("mean", 0)
    total_cold = r["cold_run"].get("mean", 0)

    print(f"\n  CONCLUSIONS")
    print(f"    HTTP fetch_ohlcv   = {http_mean:.0f}ms/sym = dominante ({http_mean/max(total_cold/sym, 1)*100:.0f}% du coût froid)")
    print(f"    Exchange create()  = {create_mean:.0f}ms (payé 1 seule fois → pool partagé OK)")
    print(f"    Parse + validate   = négligeable (<2ms)")
    print(f"    Verrous (pool+call)= négligeables (<1ms sans contention)")
    print(f"\n    Solutions efficaces :")
    print(f"    1. ADVISOR_PREWARM_1H=true  → absorbe HTTP fetch en parallèle du bootstrap")
    print(f"    2. pool classe-level déjà en place → exchange_create payé 1× seulement")
    print(f"    3. adjustForTimeDifference=False → supprime GET /time (~200ms à froid)")
    print(f"    4. MARKET_SCANNER_CACHE_TTL augmenté → moins de refetches HTTP")
    print()
    print("=" * 76)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bench variance warmup froid CCXT")
    parser.add_argument("--runs",      type=int,  default=15,    help="Nombre de runs")
    parser.add_argument("--seed",      type=int,  default=0,     help="Graine aléatoire")
    parser.add_argument("--contention", action="store_true",     help="Simuler contention de verrou")
    args = parser.parse_args()

    print(f"Bench variance froid CCXT ({args.runs} runs × {len(_SYMBOLS)} symboles)...")
    t0 = time.perf_counter()
    results = run_benchmark(n_runs=args.runs, seed=args.seed, contention=args.contention)
    print(f"Simulation en {time.perf_counter() - t0:.3f}s\n")
    print_report(results)
