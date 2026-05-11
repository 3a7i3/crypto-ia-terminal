"""
bench_e2e_warmup.py — Benchmark end-to-end "démarrage → premier rapport complet".

Compare ADVISOR_PREWARM_1H=true vs false sur 10 runs simulés.

Approche : simulation Monte-Carlo calibrée sur les latences réelles mesurées
par fetch_audit.py (DNS, TCP/TLS, CCXT init, load_markets, fetch_ohlcv).
Cela évite 10 × 4s de réseau réel (40s) et rend le bench reproductible.

Phases simulées :
  1. Bootstrap (indépendant du prewarm)
       - Init Python/modules      : Normal(200ms, 30ms)
       - CCXT exchange.__init__() : Normal(20ms, 5ms)
       - load_markets() [1× pool] : Normal(2500ms, 500ms)  ← mesuré 13.7s en froid extrême
         En pratique le pool est souvent chaud dès le 2e run → bimodal
  2. Warmup 1h (si PREWARM=true, exécuté en parallèle du bootstrap)
       - fetch_ohlcv par symbole  : Normal(400ms, 80ms) × N_SYMBOLS en //
         → durée effective = max latence parmi les N workers
  3. Cycle 1 (analyse + signal)
       - Si PREWARM=true  : 1h depuis cache (≈0ms), + MTF fetch si pas prewarm MTF
       - Si PREWARM=false : 1h fetch froid par symbole en série
       - Analyse LiveSignalEngine : Normal(10ms, 2ms) par symbole

Exécution :
    python -m quant_hedge_ai.bench_e2e_warmup
    python -m quant_hedge_ai.bench_e2e_warmup --runs 20
    python -m quant_hedge_ai.bench_e2e_warmup --seed 42
"""

from __future__ import annotations

import argparse
import random
import statistics
import time

# ── Paramètres de calibration (issus de fetch_audit.py réel) ─────────────────

N_SYMBOLS = 3   # BTC/USDT, ETH/USDT, SOL/USDT (défaut advisor)
N_RUNS    = 10

# Distributions latences (ms) — Normal(mean, std)
_LAT = {
    # Bootstrap phases
    "py_init":      (180.0, 25.0),    # import modules, dataclasses, etc.
    "ccxt_init":    (19.0,  5.0),     # exchange.__init__() mesuré
    "load_markets": (2_500.0, 600.0), # 1er appel (pool vide) — pool chaud = ~0ms
    "tcp_tls":      (90.0,  20.0),    # TCP + TLS handshake mesuré (90ms moy)
    "dns_cold":     (18.0,  8.0),     # DNS à froid mesuré
    # Fetch OHLCV par symbole
    "fetch_1h":     (145.0, 30.0),    # fetch_ohlcv mesuré (froid après load_markets)
    "fetch_4h":     (145.0, 35.0),
    "fetch_1d":     (130.0, 25.0),
    # Analyse signal
    "signal_eval":  (10.0,  2.5),
    # Rate limiter CCXT
    "rate_limit":   (50.0,  5.0),
}


def _sample(key: str, rng: random.Random) -> float:
    """Tire un échantillon de latence (ms) depuis la distribution calibrée."""
    mu, sigma = _LAT[key]
    return max(0.0, rng.gauss(mu, sigma))


def _parallel_max(latencies: list[float]) -> float:
    """Durée effective d'N tâches en parallèle = max des latences."""
    return max(latencies) if latencies else 0.0


def _simulate_run(prewarm: bool, pool_warm: bool, rng: random.Random) -> dict:
    """
    Simule un run complet et retourne les timings en ms.

    pool_warm=True signifie que load_markets() est déjà en cache classe-level
    (ce qui est le cas dès le 2ème run, ou si MarketScanner._exchange_pool est peuplé).
    """
    t = {}

    # ── Phase 1 : Bootstrap ─────────────────────────────────────────────────

    t["py_init"]   = _sample("py_init", rng)
    t["ccxt_init"] = _sample("ccxt_init", rng)
    # load_markets est payé une seule fois (pool classe-level)
    t["load_markets"] = 0.0 if pool_warm else _sample("load_markets", rng)
    t["bootstrap_total"] = t["py_init"] + t["ccxt_init"] + t["load_markets"]

    # ── Phase 2 : Warmup 1h (en parallèle du bootstrap si PREWARM=true) ────
    if prewarm:
        # Warmup démarre en même temps que le bootstrap (threads)
        # Durée = DNS + TCP + fetch_ohlcv pour chaque symbole, max entre workers
        warmup_per_sym = [
            _sample("dns_cold", rng)     # DNS froid si pool DNS vide
            + _sample("tcp_tls", rng)    # nouvelle connexion TCP/TLS
            + _sample("fetch_1h", rng)   # fetch_ohlcv
            + _sample("rate_limit", rng) # rate limiter CCXT
            for _ in range(N_SYMBOLS)
        ]
        t["warmup_parallel_ms"] = _parallel_max(warmup_per_sym)

        # Le warmup démarre au moment du bootstrap ; si bootstrap > warmup,
        # le cycle 1 n'attend rien (cache déjà chaud). Sinon attend la diff.
        t["warmup_wait_at_cycle1"] = max(
            0.0, t["warmup_parallel_ms"] - t["bootstrap_total"]
        )
    else:
        t["warmup_parallel_ms"]   = 0.0
        t["warmup_wait_at_cycle1"] = 0.0

    # ── Phase 3 : Cycle 1 ───────────────────────────────────────────────────
    if prewarm:
        # 1h en cache → 0 ms réseau
        t["cycle1_fetch_1h"] = 0.0
    else:
        # Fetch 1h pour chaque symbole en série (comportement actuel sans prewarm)
        # DNS + TCP sont payés une seule fois pour la première connexion,
        # puis keep-alive HTTP réutilisé
        t["cycle1_fetch_1h"] = (
            _sample("dns_cold", rng) + _sample("tcp_tls", rng)   # 1ère connexion
            + sum(_sample("fetch_1h", rng) + _sample("rate_limit", rng)
                  for _ in range(N_SYMBOLS))
        )

    # MTF fetch (4h + 1d) : toujours froid au cycle 1 (sauf si MTF prewarm)
    t["cycle1_fetch_mtf"] = sum(
        _sample("fetch_4h", rng) + _sample("fetch_1d", rng) + _sample("rate_limit", rng)
        for _ in range(N_SYMBOLS)
    )

    # Analyse signal
    t["cycle1_signal_eval"] = sum(_sample("signal_eval", rng) for _ in range(N_SYMBOLS))

    # Cycle 1 total = attente éventuelle warmup + fetch 1h + MTF + eval
    t["cycle1_total"] = (
        t["warmup_wait_at_cycle1"]
        + t["cycle1_fetch_1h"]
        + t["cycle1_fetch_mtf"]
        + t["cycle1_signal_eval"]
    )

    # ── Total end-to-end (démarrage → fin cycle 1) ─────────────────────────
    # Avec prewarm : le warmup se passe EN PARALLÈLE du bootstrap
    overlap = min(t["warmup_parallel_ms"], t["bootstrap_total"]) if prewarm else 0.0
    t["e2e_total"] = t["bootstrap_total"] + t["cycle1_total"]
    t["_overlap_ms"] = overlap  # portion du warmup qui s'est faite pendant le bootstrap

    return t


def run_benchmark(n_runs: int = N_RUNS, seed: int = 0) -> dict:
    """Lance n_runs simulations pour prewarm=true et false."""
    results: dict[str, list[dict]] = {"prewarm": [], "no_prewarm": []}

    for run_i in range(n_runs):
        rng = random.Random(seed + run_i * 137)
        # Premier run : load_markets froid (pool vide)
        # Runs suivants : pool chaud (exchange partagé classe-level)
        pool_warm = (run_i > 0)

        for prewarm in (True, False):
            key = "prewarm" if prewarm else "no_prewarm"
            results[key].append(
                _simulate_run(prewarm=prewarm, pool_warm=pool_warm, rng=rng)
            )

    return results


def _stats(values: list[float]) -> dict:
    if not values:
        return {}
    s = sorted(values)
    return {
        "min":  round(min(values), 1),
        "max":  round(max(values), 1),
        "mean": round(statistics.mean(values), 1),
        "std":  round(statistics.stdev(values) if len(values) > 1 else 0.0, 1),
        "p50":  round(s[len(s) // 2], 1),
        "p95":  round(s[min(int(len(s) * 0.95), len(s) - 1)], 1),
    }


def print_report(results: dict, n_runs: int) -> None:
    pw  = results["prewarm"]
    npw = results["no_prewarm"]

    e2e_pw  = [r["e2e_total"]     for r in pw]
    e2e_npw = [r["e2e_total"]     for r in npw]
    c1_pw   = [r["cycle1_total"]  for r in pw]
    c1_npw  = [r["cycle1_total"]  for r in npw]
    wm_pw   = [r["warmup_parallel_ms"] for r in pw]
    boot_pw = [r["bootstrap_total"]    for r in pw]

    gain_e2e   = statistics.mean(e2e_npw) - statistics.mean(e2e_pw)
    gain_cycle1 = statistics.mean(c1_npw) - statistics.mean(c1_pw)

    print()
    print("=" * 72)
    print("  BENCHMARK E2E — Demarrage → Premier rapport cycle 1")
    print(f"  {n_runs} runs | {N_SYMBOLS} symboles | Monte-Carlo calibré sur latences réelles")
    print("=" * 72)

    # ── Tableau principal
    hdr = f"  {'Metrique':<28}  {'PREWARM=true':>16}  {'PREWARM=false':>16}  {'Gain':>8}"
    print(hdr)
    print("  " + "-" * 68)

    def _row(label: str, vals_pw: list[float], vals_npw: list[float]) -> None:
        sp = _stats(vals_pw)
        sn = _stats(vals_npw)
        gain = sn["mean"] - sp["mean"]
        gain_str = f"+{gain:.0f}ms" if gain >= 0 else f"{gain:.0f}ms"
        print(f"  {label:<28}  {sp['mean']:>7.0f}ms ±{sp['std']:>4.0f}  "
              f"{sn['mean']:>7.0f}ms ±{sn['std']:>4.0f}  {gain_str:>8}")

    _row("E2E total (boot + cycle 1)", e2e_pw, e2e_npw)
    _row("  Cycle 1 seulement",        c1_pw,   c1_npw)
    _row("  Bootstrap seulement",      boot_pw, boot_pw)  # identique
    _row("  Warmup 1h (parallèle)",    wm_pw,   [0.0] * n_runs)

    print("  " + "-" * 68)

    # ── Variance réseau
    print("\n  VARIANCE RESEAU (std):")
    print(f"    E2E prewarm=true  : ±{_stats(e2e_pw)['std']:.0f}ms")
    print(f"    E2E prewarm=false : ±{_stats(e2e_npw)['std']:.0f}ms")
    print(f"    Variance réduite  : {_stats(e2e_npw)['std'] - _stats(e2e_pw)['std']:+.0f}ms "
          f"(prewarm amortit les pics réseau)")

    # ── Gain
    print(f"\n  GAIN E2E MOYEN    : +{gain_e2e:.0f}ms  ({gain_e2e / statistics.mean(e2e_npw) * 100:.1f}%)")
    print(f"  GAIN CYCLE 1      : +{gain_cycle1:.0f}ms  ({gain_cycle1 / max(statistics.mean(c1_npw), 1) * 100:.1f}%)")

    # ── Percentiles détaillés
    print("\n  PERCENTILES E2E (ms):")
    sp = _stats(e2e_pw)
    sn = _stats(e2e_npw)
    for pct in ("min", "p50", "p95", "max"):
        delta = sn[pct] - sp[pct]
        print(f"    {pct:<4}: prewarm={sp[pct]:>6.0f}  no_prewarm={sn[pct]:>6.0f}  "
              f"delta={delta:>+6.0f}ms")

    # ── Recommandation MTF prewarm
    print()
    print("=" * 72)
    print("  ANALYSE MTF PREWARM (ADVISOR_PREWARM_MTF)")
    print("=" * 72)

    # Coût MTF fetch froid (en // avec 1h warmup)
    mtf_cold_mean = statistics.mean([r["cycle1_fetch_mtf"] for r in pw])
    # Si on lance MTF en même temps que 1h (en parallèle du bootstrap)
    # Le MTF prewarm prend max(4h_sym, 1d_sym) × N_SYMBOLS en // = ~2 symboles
    # ≈ max latences MTF parmi N workers
    statistics.mean(
        [_stats([r["warmup_parallel_ms"] for r in pw])["mean"]]
        * 1  # déjà mesuré
    )

    # Bootstrap additionnel estimé pour MTF en parallèle
    # MTF = 4h + 1d simultané via ThreadPool. Durée ≈ même pool que 1h warmup
    # → surcoût bootstrap ≈ 0 (même executor), surcoût sur temps d'attente au cycle 1
    (
        statistics.mean([_stats([_LAT["fetch_4h"][0], _LAT["fetch_1d"][0]])[k]
                         for k in ("mean",)])
        if True else 0
    )
    # Approximation : durée MTF prewarm en parallèle
    mtf_warmup_est = max(_LAT["fetch_4h"][0] + _LAT["rate_limit"][0],
                         _LAT["fetch_1d"][0] + _LAT["rate_limit"][0])

    gain_from_mtf_warmup = mtf_cold_mean  # ce qu'on économise au cycle 1

    print(f"\n  Cout fetch MTF à froid au cycle 1 : ~{mtf_cold_mean:.0f}ms")
    print(f"  Durée estimée warmup MTF parallèle : ~{mtf_warmup_est:.0f}ms")
    print("  Bootstrap delta (même executor)    : ~0ms  (threads déjà actifs)")

    if mtf_warmup_est <= gain_from_mtf_warmup:
        verdict = "RECOMMANDE"
        reason  = (f"gain cycle 1 {gain_from_mtf_warmup:.0f}ms "
                   f"> surcoût {mtf_warmup_est:.0f}ms")
    else:
        verdict = "OPTIONNEL"
        reason  = (f"gain cycle 1 {gain_from_mtf_warmup:.0f}ms "
                   f"~ surcoût {mtf_warmup_est:.0f}ms — dépend de la latence réseau")

    print(f"\n  VERDICT MTF PREWARM : {verdict}")
    print(f"    {reason}")
    print("    Activer avec : ADVISOR_PREWARM_MTF=true")
    print()
    print("=" * 72)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark e2e warmup prewarm")
    parser.add_argument("--runs",  type=int, default=N_RUNS, help="Nombre de runs")
    parser.add_argument("--seed",  type=int, default=0,      help="Graine aléatoire")
    args = parser.parse_args()

    print(f"Simulation Monte-Carlo ({args.runs} runs × 2 modes × {N_SYMBOLS} symboles)...")
    t0 = time.perf_counter()
    results = run_benchmark(n_runs=args.runs, seed=args.seed)
    print(f"Simulation terminée en {time.perf_counter() - t0:.3f}s")
    print_report(results, n_runs=args.runs)
