#!/usr/bin/env python3
"""scripts/backfill_ohlcv.py — Amorce databases/market_data.sqlite retrospectivement.

Contexte : PR #42 a active la persistance passive OHLCV dans advisor_loop.py
(observer passif ADR-0007), mais la table market_data.sqlite ne se remplit
qu'a partir du moment ou tu actives ADVISOR_OHLCV_PERSISTENCE=true et
redemarres le service. Attendre 30j de fetch live pour un dataset exploitable
n'est pas realiste — ce script fait le backfill en une passe.

Delegation : utilise HistoricalDataFetcher (deja present dans
quant_hedge_ai/agents/market/historical_fetcher.py) qui gere pagination CCXT,
retry backoff, validation, sauvegarde SQLite via MarketDatabase.

Usage typique :

    # Univers epingle (ADR-0015, UNIVERSE_PINNED_SYMBOLS dans .env)
    python scripts/backfill_ohlcv.py --years 2

    # Un symbole precis (test)
    python scripts/backfill_ohlcv.py --symbols BTC/USDT --years 1

    # Univers explicite + timeframe 4h
    python scripts/backfill_ohlcv.py \\
        --symbols BTC/USDT ETH/USDT SOL/USDT \\
        --timeframe 4h --years 3

    # Dry-run : liste les symboles cibles, ne fetch rien
    python scripts/backfill_ohlcv.py --dry-run

Idempotent : le schema market_data.sqlite a UNIQUE(symbol, timestamp) +
INSERT OR IGNORE, donc relancer le script ne cree jamais de doublons.

Exit codes :
    0 — succes (au moins 1 bougie sauvegardee, ou dry-run)
    1 — aucun symbole cible (ni --symbols ni UNIVERSE_PINNED_SYMBOLS)
    2 — echec fetch (exchange indisponible, aucune bougie recuperee)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Charger .env avant tout import qui lit os.environ
try:
    from dotenv import load_dotenv  # noqa: E402

    load_dotenv()
except ImportError:
    pass


def _resolve_symbols(cli_symbols: list[str] | None) -> list[str]:
    """Priorite : CLI --symbols > UNIVERSE_PINNED_SYMBOLS env > vide."""
    if cli_symbols:
        return [s.strip() for s in cli_symbols if s.strip()]
    env_pinned = os.getenv("UNIVERSE_PINNED_SYMBOLS", "").strip()
    if env_pinned:
        return env_pinned.split()
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill OHLCV vers databases/market_data.sqlite via ccxt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Voir en-tete du script pour exemples detailles.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Symboles a fetcher (ex: BTC/USDT ETH/USDT). Defaut: UNIVERSE_PINNED_SYMBOLS.",
    )
    parser.add_argument(
        "--timeframe",
        default="1h",
        choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
        help="Timeframe des bougies (defaut: 1h).",
    )
    parser.add_argument(
        "--years",
        type=float,
        default=2.0,
        help="Nombre d'annees a backfill par symbole (defaut: 2.0).",
    )
    parser.add_argument(
        "--db-path",
        default="databases/market_data.sqlite",
        help="Chemin de la DB SQLite (defaut: databases/market_data.sqlite).",
    )
    parser.add_argument(
        "--exchange",
        default=None,
        help="ID exchange ccxt (defaut: EXCHANGE_ID env ou 'mexc').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Liste les symboles cibles et sort, sans fetch reseau.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduit la verbosite (WARNING+ seulement).",
    )
    args = parser.parse_args()

    # Logging : configurer le root logger AVANT d'importer les modules qui logguent
    import logging

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    symbols = _resolve_symbols(args.symbols)
    if not symbols:
        print(
            "[ERREUR] Aucun symbole cible : ni --symbols en CLI, ni "
            "UNIVERSE_PINNED_SYMBOLS dans .env",
            file=sys.stderr,
        )
        return 1

    print(f"[Backfill] Cible : {len(symbols)} symbole(s) | timeframe={args.timeframe} | years={args.years}")
    print(f"[Backfill] Exchange : {args.exchange or os.getenv('EXCHANGE_ID') or 'mexc'}")
    print(f"[Backfill] DB       : {args.db_path}")
    if len(symbols) <= 10:
        print(f"[Backfill] Symboles : {' '.join(symbols)}")
    else:
        print(f"[Backfill] Symboles : {' '.join(symbols[:5])} ... {' '.join(symbols[-3:])} (total {len(symbols)})")

    if args.dry_run:
        print("[Backfill] --dry-run : sortie sans fetch.")
        return 0

    from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher

    t0 = time.time()
    fetcher = HistoricalDataFetcher(exchange_id=args.exchange)
    results = fetcher.fetch_and_save(
        symbols=symbols,
        timeframe=args.timeframe,
        years=args.years,
        db_path=args.db_path,
    )
    duration = time.time() - t0

    total_saved = sum(results.values())
    total_failed = sum(1 for n in results.values() if n == 0)

    print()
    print(f"[Backfill] Termine en {duration/60:.1f} min")
    print(f"[Backfill] Total sauvegarde : {total_saved} bougies sur {len(symbols)} symboles")
    if total_failed:
        print(f"[Backfill] Symboles sans bougies : {total_failed}")
        failed_syms = [s for s, n in results.items() if n == 0]
        print(f"[Backfill]   -> {' '.join(failed_syms[:10])}" + (" ..." if len(failed_syms) > 10 else ""))

    if total_saved == 0:
        print("[ERREUR] Aucune bougie sauvegardee — exchange indisponible ou tous symboles invalides", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
