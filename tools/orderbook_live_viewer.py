"""
tools/orderbook_live_viewer.py — Viewer TUI live du carnet d'ordres et
de l'indicateur unique de liquidite (LiquidityScore).

Observateur strictement passif (ADR-0007) : aucune ecriture d'etat trading,
aucune influence sur les decisions. Se contente de lire le book d'un
exchange en REST (defaut) ou WebSocket et de l'afficher dans le terminal.

Usage
-----
    python tools/orderbook_live_viewer.py --symbol BTCUSDT
    python tools/orderbook_live_viewer.py --symbol ETHUSDT --exchange mexc
    python tools/orderbook_live_viewer.py --symbol SOLUSDT --exchange hyperliquid \
        --interval 1.0 --depth 15 --notional 25000

Ctrl-C pour quitter.
"""

from __future__ import annotations

import argparse
import math
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Optional

# Permettre l'execution directe (`python tools/orderbook_live_viewer.py`)
# sans avoir a poser PYTHONPATH manuellement.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from market_data.connectors import HyperliquidConnector, MEXCFuturesConnector
from market_data.connectors.base import BaseConnector
from market_data.metrics.liquidity import (
    LiquidityConfig,
    LiquiditySnapshot,
    liquidity_score,
)
from market_data.models import NormalizedOrderBook

# Codes ANSI (pas de dependance a rich/curses)
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_CLEAR = "\x1b[2J\x1b[H"
_CLEAR_LINE = "\x1b[2K"
_UP = "\x1b[F"

_GREEN = "\x1b[32m"
_RED = "\x1b[31m"
_YELLOW = "\x1b[33m"
_CYAN = "\x1b[36m"
_MAGENTA = "\x1b[35m"
_GREY = "\x1b[90m"

_TIER_COLOR = {
    "excellent": _GREEN,
    "healthy": _CYAN,
    "thin": _YELLOW,
    "fragile": _MAGENTA,
    "toxic": _RED,
    "empty": _GREY,
}


# ---------------------------------------------------------------------------
# Connecteurs disponibles
# ---------------------------------------------------------------------------


def _connector(name: str) -> BaseConnector:
    n = name.lower()
    if n in ("hyperliquid", "hl"):
        return HyperliquidConnector()
    if n in ("mexc", "mexc_futures"):
        return MEXCFuturesConnector()
    raise SystemExit(
        f"Exchange inconnu : {name!r}. Supportes : hyperliquid, mexc."
    )


# ---------------------------------------------------------------------------
# Formatage
# ---------------------------------------------------------------------------


def _fmt_price(p: float) -> str:
    if p >= 1000:
        return f"{p:,.2f}"
    if p >= 1:
        return f"{p:.4f}"
    return f"{p:.6f}"


def _fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f}M$"
    if v >= 1_000:
        return f"{v/1_000:.1f}k$"
    return f"{v:.0f}$"


def _bar(value: float, width: int, char: str = "█") -> str:
    """Barre horizontale [0, 1] -> chaine longueur `width`."""
    filled = max(0, min(width, int(round(value * width))))
    return char * filled + " " * (width - filled)


def _tier_bar(score: float, width: int = 40) -> str:
    return _bar(max(0.0, min(1.0, score / 100.0)), width)


# ---------------------------------------------------------------------------
# Rendu
# ---------------------------------------------------------------------------


@dataclass
class Stats:
    ticks: int = 0
    errors: int = 0
    started_at: float = 0.0
    last_score: Optional[float] = None
    min_score: float = math.inf
    max_score: float = -math.inf

    def observe(self, snap: LiquiditySnapshot) -> None:
        self.ticks += 1
        self.last_score = snap.score
        self.min_score = min(self.min_score, snap.score)
        self.max_score = max(self.max_score, snap.score)


def _render(
    book: NormalizedOrderBook,
    snap: LiquiditySnapshot,
    stats: Stats,
    depth_display: int,
) -> str:
    lines: list[str] = []
    tier_color = _TIER_COLOR.get(snap.tier, "")
    uptime_s = int(time.time() - stats.started_at) if stats.started_at else 0
    header = (
        f"{_BOLD}{snap.symbol}{_RESET} @ {_CYAN}{snap.exchange}{_RESET}   "
        f"{_DIM}tick #{stats.ticks}  uptime {uptime_s}s  "
        f"errors {stats.errors}{_RESET}"
    )
    lines.append(header)
    lines.append("")

    # --- Bloc score
    score_line = (
        f"{_BOLD}Liquidity Score{_RESET}  "
        f"{tier_color}{snap.score:6.2f}/100  [{snap.tier}]{_RESET}  "
        f"{tier_color}{_tier_bar(snap.score)}{_RESET}"
    )
    lines.append(score_line)

    subs = (
        f"  tightness {snap.tightness:.2f}  depth {snap.depth:.2f}  "
        f"resilience {snap.resilience:.2f}  balance {snap.balance:.2f}"
    )
    lines.append(f"{_DIM}{subs}{_RESET}")

    if snap.tier == "empty":
        lines.append(f"{_RED}Book vide ou degenere — aucun mid disponible.{_RESET}")
        return "\n".join(lines)

    spread_txt = f"{snap.spread_bps:6.2f} bps"
    depth_txt = (
        f"depth +-{snap.config.depth_pct:.1f}%: "
        f"{_fmt_usd(snap.depth_usd)}  "
        f"(bid {_fmt_usd(snap.bid_depth_usd)}, ask {_fmt_usd(snap.ask_depth_usd)})"
    )
    slip_txt = (
        f"slip @ {_fmt_usd(snap.config.slippage_notional_usd)} "
        f"buy {snap.slippage_buy_bps:5.1f} bps / "
        f"sell {snap.slippage_sell_bps:5.1f} bps"
    )
    if not snap.filled_buy or not snap.filled_sell:
        slip_txt += f"  {_YELLOW}[book insuffisant]{_RESET}"
    imb_txt = f"imbalance {snap.imbalance:+.3f}"

    lines.append(f"  spread {spread_txt}   {imb_txt}")
    lines.append(f"  {depth_txt}")
    lines.append(f"  {slip_txt}")
    lines.append("")

    # --- Livre : top N bids/asks cote a cote
    lines.append(
        f"{_BOLD}{'PRICE (bid)':>14}  {'SIZE':>12}  {'USD':>10}  "
        f"|  {'PRICE (ask)':>14}  {'SIZE':>12}  {'USD':>10}{_RESET}"
    )
    bids = book.bids[:depth_display]
    asks = book.asks[:depth_display]
    max_rows = max(len(bids), len(asks))
    for i in range(max_rows):
        if i < len(bids):
            bp, bs = bids[i]
            bid_cell = (
                f"{_GREEN}{_fmt_price(bp):>14}{_RESET}  {bs:>12.4f}  "
                f"{_fmt_usd(bp*bs):>10}"
            )
        else:
            bid_cell = f"{'':>14}  {'':>12}  {'':>10}"
        if i < len(asks):
            ap, as_ = asks[i]
            ask_cell = (
                f"{_RED}{_fmt_price(ap):>14}{_RESET}  {as_:>12.4f}  "
                f"{_fmt_usd(ap*as_):>10}"
            )
        else:
            ask_cell = f"{'':>14}  {'':>12}  {'':>10}"
        lines.append(f"  {bid_cell}  |  {ask_cell}")

    if stats.last_score is not None and stats.ticks > 1:
        lines.append("")
        lines.append(
            f"{_DIM}session min {stats.min_score:.1f}  max {stats.max_score:.1f}  "
            f"last {stats.last_score:.1f}{_RESET}"
        )

    lines.append("")
    lines.append(f"{_DIM}Ctrl-C pour quitter.{_RESET}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------


def run(
    symbol: str,
    exchange: str,
    interval_s: float,
    depth_display: int,
    depth_fetch: int,
    notional_usd: float,
    depth_pct: float,
    max_ticks: Optional[int] = None,
) -> int:
    conn = _connector(exchange)
    cfg = LiquidityConfig(
        depth_pct=depth_pct,
        slippage_notional_usd=notional_usd,
    )
    stats = Stats(started_at=time.time())

    stop = {"flag": False}

    def _handle(_sig, _frame):  # pragma: no cover - handler signal
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    print(_CLEAR, end="")
    try:
        while not stop["flag"]:
            try:
                book = conn.fetch_orderbook(symbol, depth=depth_fetch)
                snap = liquidity_score(book, cfg)
                stats.observe(snap)
                sys.stdout.write(_CLEAR)
                sys.stdout.write(_render(book, snap, stats, depth_display))
                sys.stdout.write("\n")
                sys.stdout.flush()
            except Exception as exc:  # noqa: BLE001 — resilience UX
                stats.errors += 1
                sys.stdout.write(_CLEAR)
                sys.stdout.write(
                    f"{_RED}[erreur fetch] {type(exc).__name__}: {exc}{_RESET}\n"
                    f"{_DIM}retry dans {interval_s:.1f}s (tick #{stats.ticks}, "
                    f"errors {stats.errors}){_RESET}\n"
                )
                sys.stdout.flush()

            if max_ticks is not None and stats.ticks >= max_ticks:
                break

            # Sleep tronconne pour reagir vite au signal
            elapsed = 0.0
            while elapsed < interval_s and not stop["flag"]:
                time.sleep(min(0.2, interval_s - elapsed))
                elapsed += 0.2
    finally:
        print(f"\n{_DIM}Session terminee — {stats.ticks} ticks, "
              f"{stats.errors} errors.{_RESET}")
    return 0


def _parse(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Viewer live orderbook + LiquidityScore (observateur passif).",
    )
    p.add_argument("--symbol", "-s", default="BTCUSDT", help="Ex: BTCUSDT, ETHUSDT.")
    p.add_argument(
        "--exchange",
        "-x",
        default="hyperliquid",
        choices=["hyperliquid", "mexc"],
        help="Exchange source (defaut: hyperliquid).",
    )
    p.add_argument(
        "--interval", "-i", type=float, default=2.0,
        help="Intervalle entre polls REST en secondes (defaut 2.0).",
    )
    p.add_argument(
        "--depth", "-d", type=int, default=10,
        help="Nombre de niveaux affiches par cote (defaut 10).",
    )
    p.add_argument(
        "--fetch-depth", type=int, default=50,
        help="Profondeur demandee au REST (defaut 50, pour un score robuste).",
    )
    p.add_argument(
        "--notional", "-n", type=float, default=10_000.0,
        help="Notionnel USD pour le calcul de slippage (defaut 10000).",
    )
    p.add_argument(
        "--depth-pct", type=float, default=0.5,
        help="Bande +/- pct du mid pour la depth (defaut 0.5).",
    )
    p.add_argument(
        "--max-ticks", type=int, default=None,
        help="Nombre max de ticks (utile pour debug/CI).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse(argv)
    return run(
        symbol=args.symbol.upper(),
        exchange=args.exchange,
        interval_s=args.interval,
        depth_display=args.depth,
        depth_fetch=args.fetch_depth,
        notional_usd=args.notional,
        depth_pct=args.depth_pct,
        max_ticks=args.max_ticks,
    )


if __name__ == "__main__":
    sys.exit(main())
