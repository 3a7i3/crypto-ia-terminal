"""
bench_session_contention.py — Micro-benchmark first-fetch vs shared-session.

Compare les coûts de première initialisation (pool froid) vs session partagée
(pool chaud) pour 1, 4 et 8 symboles fetachés simultanément.

Métriques par thread :
  exchange_init_ms  : création objet CCXT (une seule fois par pool)
  load_markets_ms   : GET /exchangeInfo — payé ou attendu (Event.wait)
  fetch_ohlcv_ms    : GET /api/v3/klines par symbole
  lock_wait_ms      : contention sur exchange_call_lock dans _do_fetch()

Modèle de contention (serialisation fetch_ohlcv) :
  Avec exchange_call_lock, les N fetches sont traités séquentiellement.
  Thread i attend (i × fetch_ohlcv_ms) avant d'accéder au socket.
  → Pire cas (dernier thread) : (N-1) × fetch_ohlcv_ms d'attente.

Scenario COLD (premier fetch, pool vide) :
  Thread 0 crée l'exchange + appelle load_markets(), puis fetch_ohlcv().
  Threads 1..N-1 attendent exchange_init + load_markets dans
  _ensure_markets_loaded() (bloqués sur exchange_call_lock), puis attendent
  derrière Thread 0 dans _do_fetch().

Scenario WARM (session partagée, pool chaud) :
  Tous les threads trouvent l'exchange et les markets déjà prêts.
  Seule la sérialisation exchange_call_lock dans _do_fetch() crée de la contention.

Exécution :
    python -m quant_hedge_ai.bench_session_contention
    python -m quant_hedge_ai.bench_session_contention --runs 20 --seed 42
    python -m quant_hedge_ai.bench_session_contention --symbols 1 4 8 16
"""

from __future__ import annotations

import argparse
import random
import statistics
import time
from typing import NamedTuple

# ── Latences calibrées (ms) — Normal(mean, std) ───────────────────────────────
# Source : fetch_audit.py mesuré sur Binance mainnet (Windows, latence Europe/US)

_LAT: dict[str, tuple[float, float]] = {
    "exchange_init":  (28.0,   6.0),   # ccxt.binance().__init__()
    "load_markets":   (620.0, 90.0),   # GET /api/v3/exchangeInfo cold
    "fetch_ohlcv":    (148.0, 32.0),   # GET /api/v3/klines (96 bougies)
    "pool_lock_wait": (0.05,  0.02),   # _exchange_pool_lock.acquire() (µs range)
}

N_RUNS_DEFAULT    = 15
SYMBOL_COUNTS_DEFAULT = [1, 4, 8]


def _sample(key: str, rng: random.Random) -> float:
    mu, sigma = _LAT[key]
    return max(0.0, rng.gauss(mu, sigma))


class ThreadTiming(NamedTuple):
    """Timings pour un thread (= un symbole fetché)."""
    exchange_init_ms: float   # 0 si pool chaud ou thread non-créateur
    load_markets_ms: float    # temps passé à attendre/faire load_markets
    fetch_ohlcv_ms: float     # durée du fetch_ohlcv() proprement dit
    lock_wait_ms: float       # attente exchange_call_lock dans _do_fetch()

    @property
    def total_ms(self) -> float:
        return self.exchange_init_ms + self.load_markets_ms + self.fetch_ohlcv_ms + self.lock_wait_ms


def _simulate_cold_run(n_syms: int, rng: random.Random) -> list[ThreadTiming]:
    """
    Simule N threads démarrant simultanément sur un pool FROID.

    Thread 0 crée l'exchange et charge les markets (il détient exchange_call_lock
    pendant load_markets). Threads 1..N-1 sont bloqués sur exchange_call_lock dans
    _ensure_markets_loaded() pendant toute la durée (exchange_init + load_markets)
    de Thread 0. Après libération, tous les threads se disputent exchange_call_lock
    dans _do_fetch() — sérialisés dans l'ordre 0, 1, 2, ...
    """
    ex_init = _sample("exchange_init", rng)
    lm      = _sample("load_markets", rng)
    # Thread 0 holds exchange_call_lock from t=ex_init to t=ex_init+lm
    # Non-creator threads become unblocked at t = ex_init + lm

    timings: list[ThreadTiming] = []

    # Thread 0: crée exchange + charge markets + fetch
    fetch_0 = _sample("fetch_ohlcv", rng)
    timings.append(ThreadTiming(
        exchange_init_ms=ex_init,
        load_markets_ms=lm,
        fetch_ohlcv_ms=fetch_0,
        lock_wait_ms=0.0,   # Thread 0 acquiert exchange_call_lock en premier
    ))

    # Threads 1..N-1
    # Tous débloqués à t=ex_init+lm (fin de _ensure_markets_loaded de Thread 0).
    # Ensuite, exchange_call_lock dans _do_fetch() est disputé séquentiellement.
    # Thread i attend la somme des fetch_ohlcv de threads 0..i-1.
    cumulative_fetch_before = fetch_0   # Thread 1 attend Thread 0's fetch
    for i in range(1, n_syms):
        fetch_i   = _sample("fetch_ohlcv", rng)
        # Ce thread était bloqué dans _ensure_markets_loaded pour ex_init+lm ms.
        # load_markets_ms = temps total bloqué dans ensure_markets_loaded (inclut ex_init)
        lm_wait_i = ex_init + lm

        # lock_wait_ms = attente dans _do_fetch() uniquement
        # Thread 0 acquiert d'abord (il sort de load_markets puis entre dans _do_fetch),
        # Threads 1..N-1 se queueuent derrière. Thread 1 attend Thread 0's fetch, etc.
        # max(0, cumulative_fetch_before - lm_wait_i) = si le fetch de Thread 0 est déjà fini
        # avant que Thread i finisse d'attendre _ensure_markets_loaded.
        lf_wait = max(0.0, cumulative_fetch_before - lm_wait_i)

        timings.append(ThreadTiming(
            exchange_init_ms=0.0,
            load_markets_ms=lm_wait_i,
            fetch_ohlcv_ms=fetch_i,
            lock_wait_ms=lf_wait,
        ))
        cumulative_fetch_before += fetch_i

    return timings


def _simulate_warm_run(n_syms: int, rng: random.Random) -> list[ThreadTiming]:
    """
    Simule N threads démarrant simultanément sur une session CHAUDE.

    Exchange et markets déjà prêts → aucun exchange_init ni load_markets.
    Seule la sérialisation de exchange_call_lock dans _do_fetch() crée de la contention.
    Thread i attend la somme des fetch_ohlcv de threads 0..i-1.
    """
    timings: list[ThreadTiming] = []
    cumulative_fetch = 0.0
    for _ in range(n_syms):
        fetch_i   = _sample("fetch_ohlcv", rng)
        lock_wait = cumulative_fetch
        timings.append(ThreadTiming(
            exchange_init_ms=0.0,
            load_markets_ms=0.0,
            fetch_ohlcv_ms=fetch_i,
            lock_wait_ms=lock_wait,
        ))
        cumulative_fetch += fetch_i
    return timings


def run_benchmark(
    n_runs: int = N_RUNS_DEFAULT,
    seed: int = 0,
    symbol_counts: list[int] | None = None,
) -> dict[str, dict[int, list[list[ThreadTiming]]]]:
    """Lance n_runs simulations pour (cold, warm) × chaque N_symbols."""
    if symbol_counts is None:
        symbol_counts = SYMBOL_COUNTS_DEFAULT

    results: dict[str, dict[int, list[list[ThreadTiming]]]] = {
        "cold": {n: [] for n in symbol_counts},
        "warm": {n: [] for n in symbol_counts},
    }
    for run_i in range(n_runs):
        rng = random.Random(seed + run_i * 137)
        for n in symbol_counts:
            results["cold"][n].append(_simulate_cold_run(n, rng))
            results["warm"][n].append(_simulate_warm_run(n, rng))
    return results


# ── Statistiques ──────────────────────────────────────────────────────────────

def _field_stats(
    runs: list[list[ThreadTiming]],
    field: str,
) -> tuple[float, float]:
    """Moyenne et std du champ sur tous les threads de tous les runs."""
    vals = [getattr(t, field) for run in runs for t in run]
    if not vals:
        return 0.0, 0.0
    return statistics.mean(vals), (statistics.stdev(vals) if len(vals) > 1 else 0.0)


def _worst_total_stats(runs: list[list[ThreadTiming]]) -> tuple[float, float]:
    """Pire latence totale (dernier thread) par run — moyenne et std."""
    worsts = [max(t.total_ms for t in run) for run in runs]
    return statistics.mean(worsts), (statistics.stdev(worsts) if len(worsts) > 1 else 0.0)


def _best_total_stats(runs: list[list[ThreadTiming]]) -> tuple[float, float]:
    """Meilleure latence totale (premier thread) par run — moyenne et std."""
    bests = [min(t.total_ms for t in run) for run in runs]
    return statistics.mean(bests), (statistics.stdev(bests) if len(bests) > 1 else 0.0)


# ── Rapport ───────────────────────────────────────────────────────────────────

def print_report(
    results: dict[str, dict[int, list[list[ThreadTiming]]]],
    n_runs: int,
    symbol_counts: list[int],
) -> None:
    fields = [
        ("exchange_init_ms", "exchange_init"),
        ("load_markets_ms",  "load_markets"),
        ("fetch_ohlcv_ms",   "fetch_ohlcv"),
        ("lock_wait_ms",     "lock_wait"),
    ]
    W = 90

    print()
    print("=" * W)
    print("  MICRO-BENCHMARK — first-fetch (COLD) vs shared-session (WARM)")
    print(f"  {n_runs} runs | Monte-Carlo calibre (exchange_init~28ms, load_markets~620ms, fetch~148ms)")
    print(f"  Symboles testés : {symbol_counts}")
    print("=" * W)

    # ── Tableau par métrique ───────────────────────────────────────────────────
    hdr = (
        f"  {'N sym':<6} {'Métrique':<18} "
        f"{'COLD avg (ms)':>16} {'WARM avg (ms)':>16} "
        f"{'Δ cold-warm':>12} {'Ratio':>8}"
    )
    print()
    print(hdr)
    print("  " + "-" * (W - 2))

    for n in symbol_counts:
        cold_runs = results["cold"][n]
        warm_runs = results["warm"][n]

        for idx, (field, label) in enumerate(fields):
            cold_mu, cold_std = _field_stats(cold_runs, field)
            warm_mu, warm_std = _field_stats(warm_runs, field)
            delta = cold_mu - warm_mu
            ratio = (cold_mu / warm_mu) if warm_mu > 0.1 else float("inf")

            n_col   = str(n) if idx == 0 else ""
            delta_s = f"+{delta:>6.0f}" if delta >= 0 else f"{delta:>7.0f}"
            ratio_s = f"x{ratio:.1f}" if ratio != float("inf") else "∞"

            print(
                f"  {n_col:<6} {label:<18} "
                f"{cold_mu:>9.1f} ±{cold_std:>5.1f} "
                f"{warm_mu:>9.1f} ±{warm_std:>5.1f} "
                f"{delta_s:>12}  {ratio_s:>7}"
            )

        # Pire cas (dernier thread)
        cw_mu, cw_std = _worst_total_stats(cold_runs)
        ww_mu, ww_std = _worst_total_stats(warm_runs)
        delta_w = cw_mu - ww_mu
        ratio_w = cw_mu / ww_mu if ww_mu > 0.1 else float("inf")
        print(
            f"  {'':6} {'total (pire thread)':<18} "
            f"{cw_mu:>9.1f} ±{cw_std:>5.1f} "
            f"{ww_mu:>9.1f} ±{ww_std:>5.1f} "
            f"{delta_w:>+12.0f}  x{ratio_w:.1f}"
        )

        # Meilleur cas (premier thread)
        cb_mu, cb_std = _best_total_stats(cold_runs)
        wb_mu, wb_std = _best_total_stats(warm_runs)
        print(
            f"  {'':6} {'total (meill. thread)':<18} "
            f"{cb_mu:>9.1f} ±{cb_std:>5.1f} "
            f"{wb_mu:>9.1f} ±{wb_std:>5.1f} "
            f"{cb_mu - wb_mu:>+12.0f}  x{cb_mu / wb_mu if wb_mu > 0.1 else 0:.1f}"
        )

        if n != symbol_counts[-1]:
            print("  " + "·" * (W - 2))

    print("  " + "=" * (W - 2))

    # ── Analyse contention lock ────────────────────────────────────────────────
    print()
    print("  CONTENTION exchange_call_lock — sérialisation fetch_ohlcv (O·N) :")
    print(f"  {'N sym':<6} {'lock_wait cold':>16} {'lock_wait warm':>16} {'surcoût vs N=1':>16} {'pire thread':>14}")
    print("  " + "-" * (W - 2))

    warm_1_lock, _ = _field_stats(results["warm"][symbol_counts[0]], "lock_wait_ms")
    for n in symbol_counts:
        c_lock, c_std = _field_stats(results["cold"][n], "lock_wait_ms")
        w_lock, w_std = _field_stats(results["warm"][n], "lock_wait_ms")
        overhead      = w_lock - warm_1_lock
        worst_wait, _ = _worst_total_stats(results["warm"][n])
        print(
            f"  {n:<6} "
            f"{c_lock:>10.1f} ±{c_std:>4.1f} "
            f"{w_lock:>10.1f} ±{w_std:>4.1f} "
            f"{overhead:>+14.0f}ms "
            f"{worst_wait:>12.0f}ms"
        )

    fetch_avg = _LAT["fetch_ohlcv"][0]
    print()
    print(f"  Modele : lock_wait[i] = i x fetch_ohlcv ~= i x {fetch_avg:.0f}ms")
    print(f"  Cout serialisation N=8 (pire thread) ~= 7 x {fetch_avg:.0f}ms = {7*fetch_avg:.0f}ms")

    # ── Gain session primer ────────────────────────────────────────────────────
    print()
    print("  GAIN SESSION PRIMER (primer = exchange_init + load_markets en avance) :")
    print(f"  {'N sym':<6} {'Total cold pire':>16} {'Total warm pire':>16} {'Gain absolu':>12} {'Gain %':>8}")
    print("  " + "-" * (W - 2))
    for n in symbol_counts:
        c_w, _ = _worst_total_stats(results["cold"][n])
        w_w, _ = _worst_total_stats(results["warm"][n])
        gain   = c_w - w_w
        pct    = gain / c_w * 100 if c_w > 0 else 0.0
        print(
            f"  {n:<6} {c_w:>14.0f}ms {w_w:>14.0f}ms "
            f"{gain:>+10.0f}ms {pct:>7.1f}%"
        )

    lm_mu  = _LAT["load_markets"][0]
    ex_mu  = _LAT["exchange_init"][0]
    print()
    print(f"  Le primer elimine {ex_mu:.0f}ms (exchange_init) + {lm_mu:.0f}ms (load_markets)")
    print(f"  = {ex_mu + lm_mu:.0f}ms constant quel que soit N (cout fixe paye une seule fois).")
    print()
    print("=" * W)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark contention session exchange")
    parser.add_argument("--runs",    type=int, default=N_RUNS_DEFAULT,
                        help="Nombre de runs Monte-Carlo")
    parser.add_argument("--seed",    type=int, default=0,
                        help="Graine aléatoire")
    parser.add_argument("--symbols", type=int, nargs="+",
                        default=SYMBOL_COUNTS_DEFAULT,
                        help="Tailles N à tester (ex: 1 4 8 16)")
    args = parser.parse_args()

    print(f"Simulation ({args.runs} runs × 2 modes × {args.symbols} symboles)...")
    t0 = time.perf_counter()
    results = run_benchmark(n_runs=args.runs, seed=args.seed, symbol_counts=args.symbols)
    print(f"Terminé en {time.perf_counter() - t0:.4f}s")
    print_report(results, n_runs=args.runs, symbol_counts=args.symbols)
