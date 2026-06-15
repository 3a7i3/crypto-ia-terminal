"""
Script CLI — Scan de l'univers perp MEXC et export des paires qualifiées.

Effectue un fetch_tickers() batch (1 seul appel), filtre selon Vol/Spread,
score composite, puis affiche le rapport et optionnellement sauvegarde en JSON.

Usage:
    # Scan basique top 50
    python scripts/perp_universe_scan.py

    # Top 100 paires avec vol min 2M USD
    python scripts/perp_universe_scan.py --top 100 --min-vol 2000000

    # Sauvegarder pour import dans advisor
    python scripts/perp_universe_scan.py --top 50 --save databases/perp_universe.json

    # Afficher seulement les symboles (pour copier dans advisor_loop.py)
    python scripts/perp_universe_scan.py --symbols-only

    # Scan plus large avec critères relâchés
    python scripts/perp_universe_scan.py --top 100 --min-vol 1000000 --max-spread 0.5

Sortie JSON contient:
    - symbols: list[str]  → prête à coller dans V9_SYMBOLS ou SYMBOLS_DEFAULT
    - candidates: list[dict] avec score, vol, spread, price
"""

import argparse
import os
import sys
import time

# Résolution du chemin projet depuis n'importe où
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.perp_universe_builder import PerpUniverseBuilder  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Perp Universe Scanner — découverte dynamique de paires MEXC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--exchange", default=None, help="Exchange CCXT (défaut: mexc)")
    p.add_argument(
        "--top", type=int, default=50, help="Nombre de paires à retenir (défaut: 50)"
    )
    p.add_argument(
        "--min-vol",
        type=float,
        default=None,
        metavar="USD",
        help="Volume 24h minimum en USD (défaut: 5_000_000)",
    )
    p.add_argument(
        "--max-spread",
        type=float,
        default=None,
        metavar="PCT",
        help="Spread bid/ask maximum en %% (défaut: 0.30)",
    )
    p.add_argument(
        "--save",
        default=None,
        metavar="PATH",
        help="Chemin de sauvegarde JSON (ex: databases/perp_universe.json)",
    )
    p.add_argument(
        "--symbols-only",
        action="store_true",
        help="N'affiche que la liste des symboles (un par ligne)",
    )
    p.add_argument(
        "--python-list",
        action="store_true",
        help="Affiche les symboles au format Python list (pour copier dans advisor_loop.py)",  # noqa: E501
    )
    p.add_argument(
        "--swap",
        action="store_true",
        help="Requête le marché swap/perpetuel (PERP_BUILDER_USE_SWAP=true)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.swap:
        os.environ["PERP_BUILDER_USE_SWAP"] = "true"

    builder = PerpUniverseBuilder(exchange_id=args.exchange)

    print(
        f"[PerpScan] Connexion à {builder._exchange_id.upper()} — "
        f"top {args.top} | min_vol={args.min_vol or builder.MIN_VOL_USD:,.0f} USD | "
        f"max_spread={args.max_spread or builder.MAX_SPREAD_PCT}%"
    )

    t0 = time.perf_counter()
    try:
        candidates = builder.discover(
            top_n=args.top,
            min_vol_usd=args.min_vol,
            max_spread_pct=args.max_spread,
        )
    except Exception as exc:
        print(f"[ERREUR] Scan échoué : {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - t0
    print(f"[PerpScan] {len(candidates)} paires qualifiées en {elapsed:.1f}s\n")

    if not candidates:
        print(
            "Aucune paire ne satisfait les critères. Essayez --min-vol plus bas ou --max-spread plus haut."  # noqa: E501
        )
        return 0

    if args.symbols_only:
        for c in candidates:
            print(c.symbol)

    elif args.python_list:
        _print_python_list(candidates)

    else:
        builder.print_report(candidates)
        # Résumé stats
        vols = [c.vol_24h_usd for c in candidates]
        spreads = [c.spread_pct for c in candidates]
        scores = [c.score for c in candidates]
        print(f"  Volume médian : ${_median(vols)/1e6:.1f}M")
        print(f"  Spread médian : {_median(spreads):.4f}%")
        print(f"  Score médian  : {_median(scores):.1f}\n")

    if args.save:
        _ensure_dir(args.save)
        builder.save(candidates, args.save)
        print(f"[PerpScan] Sauvegardé → {args.save}")
        print(
            f"  Utilisation : V9_SYMBOLS=\"$(python scripts/perp_universe_scan.py --symbols-only | tr '\\n' ' ')\"",  # noqa: E501
        )

    return 0


def _print_python_list(candidates) -> None:
    """Affiche les symboles au format SYMBOLS_DEFAULT Python."""
    print("\n# Coller dans core/advisor_loop.py → SYMBOLS_DEFAULT")
    print("SYMBOLS_DEFAULT = [")
    for i, c in enumerate(candidates):
        comma = "," if i < len(candidates) - 1 else ""
        vol_label = f"${c.vol_24h_usd/1e6:.0f}M vol"
        print(f'    "{c.symbol}"{comma}  # score={c.score:.0f} {vol_label}')
    print("]")


def _median(values: list) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2.0 if n % 2 == 0 else s[mid]


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


if __name__ == "__main__":
    sys.exit(main())
