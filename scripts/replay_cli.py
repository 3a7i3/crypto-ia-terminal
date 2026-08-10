"""
replay_cli.py — Interface CLI pour rejouer et analyser les trades.

Usage :
    python replay_cli.py                        # liste les 20 derniers shadow trades
    python replay_cli.py --id SHD-xxx           # rejoue un trade par son ID
    python replay_cli.py --list 50              # liste les 50 derniers
    python replay_cli.py --search BTC/USDT      # filtre par symbole
    python replay_cli.py --search --regime bull_trend --min-score 60
    python replay_cli.py --stats                # statistiques globales
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from quant_hedge_ai.agents.execution.trade_replay import TradeReplaySystem


def _sep(char: str = "─", n: int = 60) -> str:
    return char * n


def cmd_list(replay: TradeReplaySystem, n: int, source: str) -> None:
    trades = replay.list_trades(n=n, source=source)
    if not trades:
        print(f"Aucun trade trouvé dans la source '{source}'.")
        return

    print(_sep("═"))
    print(f"  {len(trades)} trades ({source})")
    print(_sep("═"))
    fmt = "{:<26}  {:<12}  {:>6}  {:>8}  {:>10}  {:<20}"
    print(fmt.format("ID", "SYMBOL", "SCORE", "ACTION", "NOTIONAL", "REGIME"))
    print(_sep())
    for t in trades:
        tid      = t.get("id", t.get("ts", "—"))[:25]
        sym      = t.get("symbol", "—")
        score    = t.get("signal_score", t.get("score", "—"))
        action   = t.get("action", t.get("signal", "—"))
        notional = t.get("notional", 0.0)
        regime   = t.get("regime", "—")
        notional_s = f"${notional:.2f}" if isinstance(notional, (int, float)) else "—"
        print(fmt.format(str(tid), sym, str(score), action, notional_s, regime))
    print(_sep())


def cmd_replay(replay: TradeReplaySystem, trade_id: str) -> None:
    report = replay.replay(trade_id)
    print(report.render())


def cmd_search(
    replay: TradeReplaySystem,
    symbol: str | None,
    regime: str | None,
    min_score: int,
    n: int,
) -> None:
    results = replay.search(symbol=symbol, regime=regime, min_score=min_score, n=n)
    if not results:
        print("Aucun trade correspond aux critères.")
        return

    print(_sep("═"))
    print(f"  {len(results)} résultats (symbol={symbol}, regime={regime}, min_score={min_score})")
    print(_sep("═"))
    for t in results:
        tid    = t.get("id", "—")[:20]
        sym    = t.get("symbol", "—")
        score  = t.get("signal_score", "—")
        action = t.get("action", "—")
        slip   = t.get("slippage_pct", 0.0)
        lat    = t.get("signal_to_order_ms", 0.0)
        regime_s = t.get("regime", "—")
        ts     = t.get("timestamp", "—")[:19]
        print(f"  {tid:<22}  {sym:<12}  score={score:<4}  {action:<5}  "
              f"slip={slip:.4f}%  lat={lat:.0f}ms  {regime_s:<25}  {ts}")
    print(_sep())


def cmd_stats(replay: TradeReplaySystem) -> None:
    """Statistiques agrégées sur tous les shadow trades."""
    trades = replay.list_trades(n=0, source="shadow")  # 0 = tout lire
    if not trades:
        print("Aucun shadow trade enregistré.")
        return

    total = len(trades)
    by_symbol: dict[str, int]  = {}
    by_regime: dict[str, int]  = {}
    by_signal: dict[str, int]  = {}
    scores: list[int]          = []
    slippages: list[float]     = []
    latencies: list[float]     = []
    notionals: list[float]     = []

    for t in trades:
        sym    = t.get("symbol", "?")
        regime = t.get("regime", "?")
        action = t.get("action", t.get("signal", "?"))
        score  = t.get("signal_score", 0)
        slip   = t.get("slippage_pct", 0.0)
        lat    = t.get("signal_to_order_ms", 0.0)
        notional = t.get("notional", 0.0)

        by_symbol[sym]    = by_symbol.get(sym, 0) + 1
        by_regime[regime] = by_regime.get(regime, 0) + 1
        by_signal[action] = by_signal.get(action, 0) + 1
        if isinstance(score, (int, float)):
            scores.append(float(score))
        if isinstance(slip, (int, float)):
            slippages.append(slip)
        if isinstance(lat, (int, float)):
            latencies.append(lat)
        if isinstance(notional, (int, float)):
            notionals.append(notional)

    print(_sep("═"))
    print(f"  STATISTIQUES SHADOW TRADES — {total} trades")
    print(_sep("═"))

    print("\nPar symbole:")
    for sym, cnt in sorted(by_symbol.items(), key=lambda x: -x[1]):
        print(f"  {sym:<14} {cnt:>4} trades")

    print("\nPar régime:")
    for reg, cnt in sorted(by_regime.items(), key=lambda x: -x[1]):
        print(f"  {reg:<28} {cnt:>4} trades")

    print("\nPar signal:")
    for sig, cnt in sorted(by_signal.items(), key=lambda x: -x[1]):
        print(f"  {sig:<8} {cnt:>4} trades")

    if scores:
        print(f"\nScores    : moy={sum(scores)/len(scores):.1f}  "
              f"min={min(scores):.0f}  max={max(scores):.0f}")
    if slippages:
        print(f"Slippage  : moy={sum(slippages)/len(slippages):.4f}%  "
              f"max={max(slippages):.4f}%")
    if latencies:
        print(f"Latence   : moy={sum(latencies)/len(latencies):.1f}ms  "
              f"max={max(latencies):.0f}ms")
    if notionals:
        print(f"Notionnel : moy=${sum(notionals)/len(notionals):.2f}  "
              f"total=${sum(notionals):.2f}")

    print(_sep())


def main() -> None:
    parser = argparse.ArgumentParser(description="Trade Replay CLI")
    parser.add_argument("--id",        type=str,  help="ID du trade à rejouer")
    parser.add_argument("--list",      type=int,  nargs="?", const=20, metavar="N",
                        help="Liste les N derniers trades (défaut: 20)")
    parser.add_argument("--source",    type=str,  default="shadow",
                        choices=["shadow", "trade_log", "paper"],
                        help="Source des trades (défaut: shadow)")
    parser.add_argument("--search",    action="store_true", help="Mode recherche filtré")
    parser.add_argument("--symbol",    type=str,  help="Filtre par symbole (ex: BTC/USDT)")
    parser.add_argument("--regime",    type=str,  help="Filtre par régime")
    parser.add_argument("--min-score", type=int,  default=0, help="Score minimum")
    parser.add_argument("--n",         type=int,  default=50, help="Nombre de résultats max")
    parser.add_argument("--stats",     action="store_true", help="Statistiques globales")
    args = parser.parse_args()

    replay = TradeReplaySystem()

    if args.id:
        cmd_replay(replay, args.id)
    elif args.stats:
        cmd_stats(replay)
    elif args.search or args.symbol or args.regime or args.min_score:
        cmd_search(replay, args.symbol, args.regime, args.min_score, args.n)
    elif args.list is not None:
        cmd_list(replay, args.list, args.source)
    else:
        # Défaut : liste des 20 derniers shadow trades
        cmd_list(replay, 20, "shadow")


if __name__ == "__main__":
    main()
