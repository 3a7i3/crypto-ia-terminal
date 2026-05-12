"""
bench_1h_limit.py — Benchmark de sensibilité ADVISOR_1H_LIMIT.

Mesure l'impact de limit = 80 / 96 / 120 sur :
  - Score de signal moyen (LiveSignalEngine, 0-100)
  - Qualité des données (nombre de features valides / total)
  - Taux de signaux actionnables (score >= 70)
  - Latence de scan synthétique (µs — calcul pur, sans réseau)

Exécution :
    python -m quant_hedge_ai.bench_1h_limit
"""

from __future__ import annotations

import math
import os
import random
import statistics
import time

# Désactive les logs trop verbeux pendant le bench
os.environ.setdefault("MARKET_SCANNER_SYNTHETIC", "true")

from quant_hedge_ai.agents.execution.live_signal_engine import LiveSignalEngine
from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer

# ── Constantes du bench ───────────────────────────────────────────────────────

LIMITS         = [80, 96, 120]
N_CYCLES       = 25
N_SYMBOLS      = 4
SYMBOLS        = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
SEEDS          = [42, 7, 99, 13]


# ── Générateur OHLCV synthétique identique à backtest_real ───────────────────

def _synthetic_ohlcv(seed: int, n_bars: int) -> list[dict]:
    """Log-normal random walk, reproductible par seed."""
    rng = random.Random(seed)
    price = 100.0
    bars: list[dict] = []
    ts = 1_700_000_000
    for _ in range(n_bars):
        ret = rng.gauss(0, 0.012)
        price = max(price * math.exp(ret), 0.01)
        h = price * (1 + abs(rng.gauss(0, 0.004)))
        lo = price * (1 - abs(rng.gauss(0, 0.004)))
        bars.append({
            "timestamp": ts,
            "open":  price,
            "high":  h,
            "low":   lo,
            "close": price,
            "volume": abs(rng.gauss(1000, 300)),
        })
        ts += 3600
    return bars


def _build_mtf_candles(seed: int, limit_1h: int) -> dict[str, list[dict]]:
    """Simule un contexte MTF réaliste : 1h (limit candles) + 4h (limit//4)."""
    bars_1h = _synthetic_ohlcv(seed, limit_1h)
    bars_4h = _synthetic_ohlcv(seed + 100, limit_1h // 4)
    bars_15m = _synthetic_ohlcv(seed + 200, limit_1h * 4)
    return {"1h": bars_1h, "4h": bars_4h, "15m": bars_15m}


# ── Métriques de qualité des features ────────────────────────────────────────

def _feature_quality(features: dict, limit: int) -> float:
    """
    Ratio de features numériquement significatives.
    Un feature == 0.0 exact signifie qu'il n'a pas pu être calculé.
    """
    relevant = ["rsi", "macd", "atr_ratio", "ema_20", "bollinger_pct", "trend_strength"]
    valid = sum(1 for k in relevant if features.get(k, 0.0) != 0.0)
    # Bonus si limit >= 50 (EMA50 stable) et limit >= 26 (MACD stable)
    macd_stable  = 1.0 if limit >= 26 else 0.8
    ema50_stable = 1.0 if limit >= 50 else 0.9
    base_quality = valid / len(relevant) if relevant else 0.0
    return min(1.0, base_quality * macd_stable * ema50_stable)


# ── Boucle principale du bench ────────────────────────────────────────────────

def run_benchmark() -> list[dict]:
    """Lance N_CYCLES × N_SYMBOLS cycles pour chaque valeur de limit."""
    fe = FeatureEngineer()
    eng = LiveSignalEngine()

    results: list[dict] = []

    for limit in LIMITS:
        scores: list[float]     = []
        qualities: list[float]  = []
        latencies_us: list[float] = []
        actionable_count: int   = 0

        for cycle_i in range(N_CYCLES):
            for sym_i, (sym, seed) in enumerate(zip(SYMBOLS, SEEDS)):
                cycle_seed = seed + cycle_i * 31 + sym_i * 7
                mtf = _build_mtf_candles(cycle_seed, limit)

                t0 = time.perf_counter()

                features = fe.extract_features(mtf.get("1h", []))
                result = eng.evaluate(
                    symbol=sym,
                    mtf_candles=mtf,
                    features=features,
                    memory_sharpe=None,
                )

                elapsed_us = (time.perf_counter() - t0) * 1e6

                scores.append(result.score)
                qualities.append(_feature_quality(features, limit))
                latencies_us.append(elapsed_us)
                if result.actionable:
                    actionable_count += 1

        total_evals = N_CYCLES * N_SYMBOLS
        results.append({
            "limit":          limit,
            "avg_score":      round(statistics.mean(scores), 1),
            "score_stdev":    round(statistics.stdev(scores), 2),
            "avg_quality":    round(statistics.mean(qualities), 3),
            "actionable_pct": round(actionable_count / total_evals * 100, 1),
            "avg_latency_us": round(statistics.mean(latencies_us), 1),
            "p95_latency_us": round(sorted(latencies_us)[int(len(latencies_us) * 0.95)], 1),
        })

    return results


# ── Affichage du tableau ───────────────────────────────────────────────────────

def _recommend(results: list[dict]) -> int:
    """
    Choisit la valeur optimale via score composite :
        composite = 0.4*score + 0.35*quality + 0.25*(1/latency_norm)
    """
    max_lat = max(r["avg_latency_us"] for r in results)
    min_lat = min(r["avg_latency_us"] for r in results)
    lat_range = max(max_lat - min_lat, 1.0)

    best = None
    best_val = -1.0
    for r in results:
        score_norm   = r["avg_score"] / 100.0
        quality_norm = r["avg_quality"]
        latency_norm = 1.0 - (r["avg_latency_us"] - min_lat) / lat_range
        composite = 0.40 * score_norm + 0.35 * quality_norm + 0.25 * latency_norm
        r["_composite"] = round(composite, 4)
        if composite > best_val:
            best_val = composite
            best = r["limit"]
    return best  # type: ignore[return-value]


def print_report(results: list[dict]) -> None:
    recommended = _recommend(results)

    print()
    print("=" * 74)
    print("  BENCHMARK ADVISOR_1H_LIMIT — Sensibilite signal / qualite / latence")
    print(f"  {N_CYCLES} cycles x {N_SYMBOLS} symboles = {N_CYCLES * N_SYMBOLS} evaluations par valeur")
    print("=" * 74)
    hdr = (
        f"{'LIMIT':>6}  {'Score moy':>9}  {'Std':>5}  "
        f"{'Qualite':>7}  {'Actionnable':>11}  "
        f"{'Lat.moy(us)':>11}  {'Lat.p95(us)':>11}  {'Composite':>9}  {'':>5}"
    )
    print(hdr)
    print("-" * 74)
    for r in results:
        tag = "  <-- RECOMMANDE" if r["limit"] == recommended else ""
        print(
            f"{r['limit']:>6}  "
            f"{r['avg_score']:>9.1f}  "
            f"{r['score_stdev']:>5.2f}  "
            f"{r['avg_quality']:>7.3f}  "
            f"{r['actionable_pct']:>10.1f}%  "
            f"{r['avg_latency_us']:>11.1f}  "
            f"{r['p95_latency_us']:>11.1f}  "
            f"{r.get('_composite', 0):>9.4f}"
            f"{tag}"
        )
    print("=" * 74)
    print()
    print(f"  Valeur recommandee : ADVISOR_1H_LIMIT={recommended}")
    rec = next(r for r in results if r["limit"] == recommended)
    print(f"  Score moyen  : {rec['avg_score']:.1f}/100")
    print(f"  Qualite feat.: {rec['avg_quality']:.1%}")
    print(f"  Actionnable  : {rec['actionable_pct']:.1f}%  des cycles produisent un signal trade")
    print(f"  Latence calcul (synthétique, sans réseau) : {rec['avg_latency_us']:.0f} µs/eval")
    print()
    print("  Explication :")
    print("   - 80 candles = 3.3j de 1h, EMA50 instable, MACD marginalement valide")
    print("   - 96 candles = 4j de 1h, bon compromis EMA20/50 + RSI + MACD stables")
    print("   - 120 candles = 5j de 1h, indicateurs tres stables mais payload +25%")
    print()


if __name__ == "__main__":
    print("Lancement du benchmark ADVISOR_1H_LIMIT (synthétique, sans réseau)...")
    t_start = time.perf_counter()
    results = run_benchmark()
    t_end = time.perf_counter()
    print_report(results)
    print(f"  Bench complet en {t_end - t_start:.2f}s")
