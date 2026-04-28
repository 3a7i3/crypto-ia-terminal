"""
validate_historical.py — Validation walk-forward sur données historiques réelles.

Usage :
    python scripts/validate_historical.py
    python scripts/validate_historical.py --symbols BTC/USDT ETH/USDT --years 2 --timeframe 1h
    python scripts/validate_historical.py --synthetic   # mode hors-ligne (données synthétiques)

Sortie :
    - Tableau récapitulatif par stratégie (Sharpe IS / OOS, PnL, verdict)
    - Résumé global (taux d'overfit, meilleure stratégie OOS)
    - Sauvegarde JSON dans databases/walk_forward_results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# ── Racine du projet dans le PYTHONPATH ────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("validate_historical")


# ── Génération de stratégies de test si le scoreboard est vide ────────────────

def _default_strategies() -> list[dict]:
    """Stratégies de référence couvrant tous les indicateurs disponibles."""
    return [
        {"entry_indicator": "EMA",      "period": 14, "threshold": 1.0, "timeframe": "1h"},
        {"entry_indicator": "EMA",      "period": 21, "threshold": 1.5, "timeframe": "1h"},
        {"entry_indicator": "RSI",      "period": 14, "threshold": 1.0, "timeframe": "1h"},
        {"entry_indicator": "RSI",      "period": 21, "threshold": 0.8, "timeframe": "1h"},
        {"entry_indicator": "MACD",     "period": 26, "threshold": 1.0, "timeframe": "1h"},
        {"entry_indicator": "BOLLINGER","period": 20, "threshold": 2.0, "timeframe": "1h"},
        {"entry_indicator": "VWAP",     "period": 20, "threshold": 1.0, "timeframe": "1h"},
        {"entry_indicator": "ATR",      "period": 14, "threshold": 1.5, "timeframe": "1h"},
        # Variantes période courte
        {"entry_indicator": "EMA",      "period": 7,  "threshold": 1.0, "timeframe": "1h"},
        {"entry_indicator": "RSI",      "period": 7,  "threshold": 1.2, "timeframe": "1h"},
    ]


def _load_strategies(top_n: int = 20) -> list[dict]:
    """
    Charge les meilleures stratégies depuis le scoreboard.
    Si le scoreboard est vide (première exécution), utilise les stratégies par défaut.
    """
    try:
        from quant_hedge_ai.databases.strategy_scoreboard import StrategyScoreboard
        board = StrategyScoreboard()
        entries = board.get_active_strategies(n=top_n)
        if entries:
            strategies = [e["strategy"] for e in entries if "strategy" in e]
            if strategies:
                logger.info("Scoreboard : %d stratégies chargées", len(strategies))
                return strategies
    except Exception as exc:
        logger.warning("Impossible de charger le scoreboard : %s", exc)

    strats = _default_strategies()
    logger.info("Scoreboard vide — utilisation de %d stratégies par défaut", len(strats))
    return strats


# ── Fetch des données ──────────────────────────────────────────────────────────

def _fetch_candles(
    symbol: str,
    timeframe: str,
    years: float,
    synthetic: bool,
) -> list[dict]:
    """Retourne les bougies OHLCV (réelles ou synthétiques)."""

    if synthetic:
        logger.info("Mode synthétique — génération de bougies pour %s", symbol)
        from quant_hedge_ai.agents.market.market_scanner import _synthetic_series
        n = int(years * 365 * 24)  # bougies 1h
        return _synthetic_series(symbol, n)

    logger.info("Fetch données réelles — %s  %s  %.1f an(s)…", symbol, timeframe, years)
    try:
        from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher
        fetcher = HistoricalDataFetcher()
        candles = fetcher.fetch(symbol, timeframe=timeframe, years=years, progress=True)
        if candles:
            return candles
    except Exception as exc:
        logger.warning("Fetch réel échoué (%s) — bascule synthétique", exc)

    # Fallback synthétique si le fetch réseau échoue
    logger.warning("%s : fallback synthétique", symbol)
    from quant_hedge_ai.agents.market.market_scanner import _synthetic_series
    n = int(years * 365 * 24)
    return _synthetic_series(symbol, n)


# ── Affichage du rapport ───────────────────────────────────────────────────────

_VERDICT_COLOR = {
    "ROBUSTE":    "\033[92m",  # vert
    "ACCEPTABLE": "\033[96m",  # cyan
    "SUSPECT":    "\033[93m",  # jaune
    "OVERFIT":    "\033[91m",  # rouge
}
_RESET = "\033[0m"


def _fmt_verdict(verdict: str) -> str:
    color = _VERDICT_COLOR.get(verdict, "")
    return f"{color}{verdict:<10}{_RESET}"


def _print_table(results, symbol: str) -> None:
    sep = "-" * 88
    header = (
        f"\n{sep}\n"
        f"  {symbol}  --  {len(results)} strategies validated\n"
        f"{sep}\n"
        f"  {'Indicator':<12} {'Period':>6} {'Thr':>5} | "
        f"{'Sharpe IS':>9} {'Sharpe OOS':>10} | "
        f"{'PnL IS%':>8} {'PnL OOS%':>9} | "
        f"{'Trades':>6} | Verdict\n"
        f"{sep}"
    )
    print(header)
    for r in results:
        s = r.strategy
        ind = s.get("entry_indicator", "?")
        per = s.get("period", "?")
        thr = s.get("threshold", "?")
        print(
            f"  {ind:<12} {per:>6} {thr:>5} | "
            f"{r.sharpe_in:>9.3f} {r.sharpe_out:>10.3f} | "
            f"{r.pnl_in:>8.2f} {r.pnl_out:>9.2f} | "
            f"{r.trades_out:>6} | {_fmt_verdict(r.verdict)}"
        )
    print(sep)


def _print_summary(summary: dict, symbol: str) -> None:
    print(
        f"\n  Summary {symbol}:\n"
        f"    Total strategies : {summary['total']}\n"
        f"    ROBUST={summary['robust']}  ACCEPTABLE={summary['acceptable']}  "
        f"SUSPECT={summary['suspect']}  OVERFIT={summary['overfit']}\n"
        f"    Overfit rate     : {summary['overfit_rate']:.0%}\n"
        f"    Avg Sharpe IS    : {summary['avg_sharpe_in']:.3f}\n"
        f"    Avg Sharpe OOS   : {summary['avg_sharpe_out']:.3f}\n"
        f"    Sharpe decay     : {summary['sharpe_decay']:.0%}\n"
        f"    Best Sharpe OOS  : {summary['best_sharpe_out']:.3f}  "
        f"({summary['best_strategy'].get('entry_indicator','?')} "
        f"p={summary['best_strategy'].get('period','?')})\n"
    )


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Walk-forward validation sur données réelles")
    parser.add_argument(
        "--symbols", nargs="+",
        default=["BTC/USDT", "ETH/USDT"],
        help="Symboles CCXT (défaut: BTC/USDT ETH/USDT)",
    )
    parser.add_argument(
        "--timeframe", default="1h",
        choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
        help="Timeframe OHLCV (défaut: 1h)",
    )
    parser.add_argument(
        "--years", type=float, default=2.0,
        help="Années d'historique à télécharger (défaut: 2.0)",
    )
    parser.add_argument(
        "--top-n", type=int, default=20,
        help="Nombre de stratégies à valider depuis le scoreboard (défaut: 20)",
    )
    parser.add_argument(
        "--synthetic", action="store_true",
        help="Utiliser des données synthétiques (mode hors-ligne)",
    )
    parser.add_argument(
        "--output", default="databases/walk_forward_results.json",
        help="Fichier JSON de sortie (défaut: databases/walk_forward_results.json)",
    )
    args = parser.parse_args(argv)

    from quant_hedge_ai.agents.quant.walk_forward import WalkForwardValidator

    strategies = _load_strategies(top_n=args.top_n)
    validator = WalkForwardValidator(
        train_ratio=0.7,
        decay_threshold=0.5,
        min_trades_oos=5,
    )

    all_output: dict = {"meta": {}, "by_symbol": {}}
    all_output["meta"] = {
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "symbols": args.symbols,
        "timeframe": args.timeframe,
        "years": args.years,
        "n_strategies": len(strategies),
        "synthetic": args.synthetic,
    }

    t0 = time.time()
    for symbol in args.symbols:
        candles = _fetch_candles(symbol, args.timeframe, args.years, args.synthetic)

        if len(candles) < 100:
            logger.error(
                "%s : seulement %d bougies — validation ignorée (minimum 100)", symbol, len(candles)
            )
            continue

        logger.info(
            "%s : %d bougies disponibles — validation de %d stratégies…",
            symbol, len(candles), len(strategies),
        )

        results = validator.validate_batch(strategies, candles, verbose=True)
        summary = WalkForwardValidator.summary(results)

        _print_table(results, symbol)
        _print_summary(summary, symbol)

        all_output["by_symbol"][symbol] = {
            "n_candles": len(candles),
            "summary": summary,
            "results": [r.as_dict() for r in results],
        }

    elapsed = time.time() - t0
    logger.info("Validation terminée en %.1fs", elapsed)

    # Sauvegarde JSON
    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_output, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Résultats sauvegardés → %s", out_path)

    # Code de sortie non-zéro si overfit global > 50%
    total_overfit = sum(
        v["summary"].get("overfit", 0) for v in all_output["by_symbol"].values()
    )
    total_strategies = sum(
        v["summary"].get("total", 0) for v in all_output["by_symbol"].values()
    )
    if total_strategies and (total_overfit / total_strategies) > 0.5:
        logger.warning(
            "WARNING: more than 50%% of strategies are overfit (%d/%d)",
            total_overfit, total_strategies,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
