"""
trade_analysis/observatory.py — Observatoire LMI live (processus collecteur).

Couche d'OBSERVATION strictement passive (ADR-0007) :
  - processus SEPARE du moteur — zero import moteur, zero ecriture dans ses
    stores, WebSocket public uniquement (aucune cle, aucun ordre possible) ;
  - streame les symboles choisis par SymbolSelector (market cap / volatilite
    / win-loss), un LMIEngine par symbole ;
  - ecrit deux artefacts, lus ensuite en LECTURE SEULE par le dashboard et
    le bot Telegram :
      * databases/trade_analysis/lmi_live_state.json  (dernier etat/symbole)
      * databases/trade_analysis/lmi_YYYY-MM-DD.jsonl.gz (historique = ledger)

Le LMI n'est JAMAIS branche sur une decision de trading. Il observe.

Usage :
  python -m trade_analysis.observatory --once     # 1 cycle de selection, dump
  python -m trade_analysis.observatory --live      # boucle WebSocket
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from trade_analysis.lmi_engine import LMIEngine
from trade_analysis.models import PressureField
from trade_analysis.recorder import LMIRecorder
from trade_analysis.selection import SymbolSelector

LMI_DIR = Path(os.getenv("LMI_DIR", "databases/trade_analysis"))
LIVE_STATE_FILE = LMI_DIR / "lmi_live_state.json"
DEFAULT_EXCHANGE = os.getenv("LMI_EXCHANGE", "mexc")


# ---------------------------------------------------------------------------
# Store du sidecar (dernier etat par symbole) — testable sans WebSocket
# ---------------------------------------------------------------------------


@dataclass
class LiveStateStore:
    """
    Maintient le dernier PressureField par symbole et le persiste en JSON
    de facon atomique (ecriture temp + rename).
    """

    path: Path = LIVE_STATE_FILE
    exchange: str = DEFAULT_EXCHANGE
    watchlist: list[str] = field(default_factory=list)
    _states: dict[str, dict] = field(default_factory=dict)
    _event_count: int = 0

    def update(self, pf: PressureField) -> None:
        self._states[pf.symbol] = pf.as_dict()
        self._event_count += 1

    def set_watchlist(self, symbols: list[str]) -> None:
        self.watchlist = list(symbols)

    def snapshot(self) -> dict:
        now_ms = int(time.time() * 1000)
        symbols = {}
        for sym, st in self._states.items():
            age_ms = now_ms - int(st.get("timestamp_ms", now_ms))
            symbols[sym] = {**st, "age_ms": age_ms}
        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "exchange": self.exchange,
            "watchlist": self.watchlist,
            "symbols": symbols,
            "stats": {
                "events": self._event_count,
                "symbols_active": len(self._states),
                "symbols_watched": len(self.watchlist),
            },
        }

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.snapshot(), ensure_ascii=False, separators=(",", ":"))
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


# ---------------------------------------------------------------------------
# Observatoire live
# ---------------------------------------------------------------------------


class Observatory:
    """
    Orchestrateur : selection -> streams WebSocket -> LMIEngines -> store.

    Un LMIEngine par symbole. La watchlist est reevaluee periodiquement
    (reselect_interval_s) ; les symboles qui sortent sont arretes, les
    nouveaux demarres.
    """

    def __init__(
        self,
        exchange: str = DEFAULT_EXCHANGE,
        selector: Optional[SymbolSelector] = None,
        max_symbols: int = 20,
        flush_interval_s: float = 2.0,
        reselect_interval_s: float = 300.0,
        record: bool = True,
        selection_kwargs: Optional[dict] = None,
    ) -> None:
        self.exchange = exchange
        self.selector = selector or SymbolSelector()
        self.max_symbols = max_symbols
        self.flush_interval_s = flush_interval_s
        self.reselect_interval_s = reselect_interval_s
        self.selection_kwargs = selection_kwargs or {}

        self.store = LiveStateStore(exchange=exchange)
        self._recorder = LMIRecorder() if record else None
        self._engines: dict[str, LMIEngine] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    def compute_watchlist(self) -> list[str]:
        kwargs = {"limit": self.max_symbols, **self.selection_kwargs}
        symbols = self.selector.select_symbols(**kwargs)
        return symbols[: self.max_symbols]

    def _make_connector(self):
        """Instancie le connecteur WebSocket demande (import tardif)."""
        if self.exchange == "mexc":
            from market_data.connectors.mexc import MEXCFuturesConnector

            return MEXCFuturesConnector()
        if self.exchange == "hyperliquid":
            from market_data.connectors.hyperliquid import HyperliquidConnector

            return HyperliquidConnector()
        raise ValueError(f"Exchange non supporte: {self.exchange}")

    async def _run_symbol(self, symbol: str) -> None:
        from market_data.stream import MultiExchangeStream

        engine = LMIEngine(symbol=symbol)
        self._engines[symbol] = engine
        stream = MultiExchangeStream()
        stream.add_connector(self._make_connector())

        try:
            async for pf in engine.run_live(stream):
                self.store.update(pf)
                if self._recorder:
                    self._recorder.record(pf)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - resilience live
            print(f"[Observatory] {symbol} stream error: {exc}")

    async def _reconcile(self) -> None:
        """Aligne les taches actives sur la watchlist courante."""
        watchlist = self.compute_watchlist()
        self.store.set_watchlist(watchlist)
        wanted = set(watchlist)

        for sym in list(self._tasks):
            if sym not in wanted:
                self._tasks[sym].cancel()
                self._tasks.pop(sym, None)
                self._engines.pop(sym, None)

        for sym in watchlist:
            if sym not in self._tasks:
                self._tasks[sym] = asyncio.create_task(self._run_symbol(sym))

    async def run(self) -> None:
        self._running = True
        await self._reconcile()
        last_reselect = time.monotonic()
        try:
            while self._running:
                await asyncio.sleep(self.flush_interval_s)
                self.store.flush()
                if time.monotonic() - last_reselect >= self.reselect_interval_s:
                    await self._reconcile()
                    last_reselect = time.monotonic()
        finally:
            for t in self._tasks.values():
                t.cancel()
            if self._recorder:
                self._recorder.close()

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_once(args: argparse.Namespace) -> None:
    """Calcule la watchlist et ecrit un sidecar vide (diagnostic selection)."""
    selector = SymbolSelector()
    store = LiveStateStore(exchange=args.exchange)
    candidates = selector.select(limit=args.max_symbols)
    store.set_watchlist([c.symbol for c in candidates])
    store.flush()
    print(f"[Observatory] watchlist ({len(candidates)}): "
          f"{', '.join(c.symbol for c in candidates) or '(vide)'}")
    print(f"[Observatory] sidecar -> {store.path}")


def _cmd_live(args: argparse.Namespace) -> None:
    obs = Observatory(exchange=args.exchange, max_symbols=args.max_symbols)
    print(f"[Observatory] live sur {args.exchange} — {args.max_symbols} symboles max")
    try:
        asyncio.run(obs.run())
    except KeyboardInterrupt:
        print("[Observatory] arret demande")


def _load_env(path: str | Path = ".env") -> None:
    """
    Charge le .env du projet (UNIVERSE_PINNED_SYMBOLS, OBS_DIR, ...).

    En run manuel, systemd ne charge pas EnvironmentFile : sans ceci le
    filtre d'univers epingle serait un no-op. Parseur minimal, sans
    dependance (python-dotenv pas garanti). Les variables deja definies
    dans l'environnement gagnent (setdefault) — jamais d'ecrasement.
    """
    p = Path(path)
    if not p.exists():
        return
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    except OSError:
        return


def main() -> None:
    _load_env()
    p = argparse.ArgumentParser(description="Observatoire LMI live (passif)")
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    p.add_argument("--max-symbols", type=int, default=20)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true", help="1 selection + dump sidecar")
    g.add_argument("--live", action="store_true", help="boucle WebSocket")
    args = p.parse_args()

    if args.live:
        _cmd_live(args)
    else:
        _cmd_once(args)


if __name__ == "__main__":
    main()
