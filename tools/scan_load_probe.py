"""
tools/scan_load_probe.py — Sonde de charge T4 (ADR-0017) : coût réel du scan.

Mesure le temps de récupération OHLCV (le poste dominant du cycle moteur —
l'analyse CPU est négligeable, load VPS ~0.04) pour K paires de la shortlist
radar, puis extrapole le temps de cycle aux tailles de palier (100/200/500/
1000). Lecture seule, API publique, aucun impact moteur.

Usage :
  python tools/scan_load_probe.py --pairs 150 [--timeframes 1h,4h,1d]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_REPO_ROOT = (
    Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd()
)
sys.path.insert(0, str(_REPO_ROOT))

PALIER_TARGETS = (100, 200, 500, 1000)
CYCLE_BUDGET_S = 200.0  # déclencheur T4 de l'ADR-0017


def extrapolate(elapsed_s: float, n_measured: int, targets=PALIER_TARGETS) -> dict:
    """Temps de cycle projeté par taille de palier (linéaire sur K mesuré)."""
    if n_measured <= 0 or elapsed_s <= 0:
        return {}
    per_pair = elapsed_s / n_measured
    return {
        str(t): {
            "cycle_s": round(per_pair * t, 1),
            "sous_budget_200s": per_pair * t < CYCLE_BUDGET_S,
        }
        for t in targets
    }


def _load_shortlist_symbols(max_pairs: int) -> list[str]:
    from observation.market_observer import obs_dir

    directory = obs_dir()
    candidates = sorted(directory.glob("radar_shortlist_*.json"))
    if not candidates:
        return []
    data = json.loads(candidates[-1].read_text(encoding="utf-8"))
    return [e["sym"] for e in data.get("shortlist", [])][:max_pairs]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sonde de charge T4 (ADR-0017)")
    parser.add_argument("--pairs", type=int, default=150)
    parser.add_argument("--timeframes", default="1h,4h,1d")
    parser.add_argument("--limit", type=int, default=100, help="bougies par appel")
    args = parser.parse_args(argv)

    import ccxt

    symbols = _load_shortlist_symbols(args.pairs)
    if not symbols:
        print("Aucune shortlist radar — lancer d'abord market_radar --run")
        return 1
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    spot = ccxt.mexc({"enableRateLimit": True, "options": {"defaultType": "spot"}})
    swap = ccxt.mexc({"enableRateLimit": True, "options": {"defaultType": "swap"}})

    t0 = time.time()
    ok, errors = 0, 0
    for sym in symbols:
        client = swap if ":" in sym else spot
        for tf in timeframes:
            try:
                client.fetch_ohlcv(sym, timeframe=tf, limit=args.limit)
                ok += 1
            except Exception:
                errors += 1
    elapsed = time.time() - t0

    n = len(symbols)
    proj = extrapolate(elapsed, n)
    print(
        f"SONDE DE CHARGE T4 — {n} paires x {len(timeframes)} TF "
        f"= {ok} appels OK, {errors} erreurs, {elapsed:.1f} s "
        f"({elapsed / n:.2f} s/paire)"
    )
    print(f"Budget cycle ADR-0017 : < {CYCLE_BUDGET_S:.0f} s")
    for size, p in proj.items():
        verdict = "OK" if p["sous_budget_200s"] else "DEPASSE (rotation top-K requise)"
        print(f"  palier {size:>4} paires : cycle ~{p['cycle_s']:>7.1f} s  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
