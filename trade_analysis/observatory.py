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

DEFAULT_EXCHANGE = os.getenv("LMI_EXCHANGE", "mexc")
STALE_MS = 15_000


def _resolve_live_state_file() -> Path:
    """Résolu à chaque appel — injectable par env, testable, jamais figé."""
    return Path(os.getenv("LMI_DIR", "databases/trade_analysis")) / "lmi_live_state.json"


# ---------------------------------------------------------------------------
# Store du sidecar (dernier etat par symbole) — testable sans WebSocket
# ---------------------------------------------------------------------------


@dataclass
class LiveStateStore:
    """
    Maintient le dernier PressureField par symbole et le persiste en JSON
    de facon atomique (ecriture temp + rename).

    ``watchlist`` représente les symboles demandés par le sélecteur.
    ``stream_watchlist`` représente le sous-ensemble réellement souscrit.
    ``unavailable`` documente explicitement les symboles refusés avant stream.
    """

    path: Path | None = None
    exchange: str = DEFAULT_EXCHANGE
    watchlist: list[str] = field(default_factory=list)
    stream_watchlist: list[str] | None = None
    unavailable: dict[str, str] = field(default_factory=dict)
    contract_meta: dict = field(default_factory=dict)
    _states: dict[str, dict] = field(default_factory=dict)
    _event_count: int = 0

    def __post_init__(self) -> None:
        if self.path is None:
            self.path = _resolve_live_state_file()
        else:
            self.path = Path(self.path)

    def update(self, pf: PressureField) -> None:
        # Après une rotation de watchlist, une task annulée peut encore rendre la
        # main une fois. Ne jamais réintroduire un symbole hors population active.
        if self.watchlist and pf.symbol not in self.watchlist:
            return
        self._states[pf.symbol] = pf.as_dict()
        self._event_count += 1

    def set_watchlist(
        self,
        symbols: list[str],
        *,
        stream_symbols: list[str] | None = None,
        unavailable: dict[str, str] | None = None,
    ) -> None:
        self.watchlist = list(dict.fromkeys(symbols))
        self.stream_watchlist = list(
            dict.fromkeys(self.watchlist if stream_symbols is None else stream_symbols)
        )
        self.unavailable = dict(unavailable or {})

        # Le sidecar est un état du présent, pas un historique implicite.
        # L'historique durable reste le ledger gzip du Recorder.
        wanted = set(self.watchlist)
        self._states = {
            sym: state for sym, state in self._states.items() if sym in wanted
        }

    def set_contract_meta(self, meta: dict) -> None:
        """Provenance des contractSize (source api|fallback|mixed) — audit."""
        self.contract_meta = dict(meta or {})

    def snapshot(self) -> dict:
        now_ms = int(time.time() * 1000)
        symbols: dict[str, dict] = {}

        # Compatibilité des usages de test/dev où aucune watchlist n'a encore
        # été posée : dans ce cas on conserve les états explicitement injectés.
        state_items = self._states.items()
        if self.watchlist:
            state_items = (
                (sym, self._states[sym])
                for sym in self.watchlist
                if sym in self._states
            )

        for sym, st in state_items:
            age_ms = max(0, now_ms - int(st.get("timestamp_ms", now_ms)))
            symbols[sym] = {**st, "age_ms": age_ms}

        requested = self.watchlist or list(symbols)
        stream_list = (
            list(requested)
            if self.stream_watchlist is None
            else list(self.stream_watchlist)
        )
        streamable = set(stream_list)
        coverage: dict[str, dict] = {}
        n_fresh = 0
        n_stale = 0
        n_unavailable = 0

        for sym in requested:
            reason = self.unavailable.get(sym)
            st = symbols.get(sym)
            if reason:
                status = "UNAVAILABLE"
                age_ms = None
                n_unavailable += 1
            elif st is None:
                status = "UNAVAILABLE"
                reason = "no_pressure_field"
                age_ms = None
                n_unavailable += 1
            else:
                age_ms = int(st.get("age_ms", STALE_MS + 1))
                if age_ms <= STALE_MS:
                    status = "LIVE"
                    n_fresh += 1
                else:
                    status = "STALE"
                    n_stale += 1

            coverage[sym] = {
                "status": status,
                "age_ms": age_ms,
                "stream_requested": sym in streamable,
                "reason": reason,
            }

        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "exchange": self.exchange,
            "watchlist": requested,
            "stream_watchlist": stream_list,
            "coverage": coverage,
            # Provenance scientifique : avec quelle source de contractSize
            # ces observations ont-elles ete calculees (api|fallback|mixed).
            "contract_meta": self.contract_meta,
            "symbols": symbols,
            "stats": {
                # Compteur de sortie LMI (PressureField), pas événements WS bruts.
                "events": self._event_count,
                "symbols_active": len(symbols),
                "symbols_watched": len(requested),
                "symbols_streamable": len(streamable),
                "symbols_fresh": n_fresh,
                "symbols_stale": n_stale,
                "symbols_unavailable": n_unavailable,
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

    async def _validate_watchlist(
        self, symbols: list[str]
    ) -> tuple[list[str], dict[str, str]]:
        """Valide l'existence des instruments avant d'ouvrir les WebSockets.

        Pour MEXC, la preuve est le catalogue Futures public ``contract/detail``.
        Une indisponibilité du catalogue est fail-closed pour cette itération :
        le service reste vivant et réessaiera au prochain reconcile, mais aucun
        symbole n'est présenté comme streamable sans preuve d'existence.
        """
        if self.exchange != "mexc":
            return list(symbols), {}

        connector = self._make_connector()
        loop = asyncio.get_running_loop()
        try:
            supported = await loop.run_in_executor(
                None, connector.fetch_supported_symbols
            )
        except Exception as exc:
            reason = f"market_catalog_unavailable:{type(exc).__name__}"
            return [], {sym: reason for sym in symbols}

        streamable = [sym for sym in symbols if sym in supported]
        unavailable = {
            sym: "not_in_mexc_futures_catalog"
            for sym in symbols
            if sym not in supported
        }
        return streamable, unavailable

    def _contract_provenance(self) -> dict:
        """Provenance des contractSize du connecteur actif (pour le sidecar)."""
        if self.exchange == "mexc":
            from market_data.connectors.mexc import MEXCFuturesConnector

            return MEXCFuturesConnector.contract_provenance()
        return {"source": "n/a"}

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

    async def _restart_dead_tasks(self) -> None:
        """Relance les tasks terminées pour les symboles encore dans la watchlist.

        Invoquée à chaque flush_interval_s — bien plus fréquemment que
        _reconcile() (reselect_interval_s).  Ne recalcule pas la watchlist
        et ne touche pas aux symboles sortants : seule la détection et la
        relance des tasks done()/cancelled() est effectuée ici.
        """
        for sym in list(self._tasks):
            task = self._tasks[sym]
            if task.done():
                exc = None
                if not task.cancelled():
                    exc = task.exception()
                reason = f"exception={exc!r}" if exc else "completed normally"
                print(f"[Observatory] {sym} task done ({reason}), restarting")
                self._tasks.pop(sym, None)
                self._engines.pop(sym, None)
                self._tasks[sym] = asyncio.create_task(self._run_symbol(sym))

    async def _reconcile(self) -> None:
        """Aligne les taches actives sur la watchlist courante.

        Recalcule la watchlist, valide l'existence des instruments MEXC,
        arrête les symboles sortants/non supportés et démarre les nouveaux.
        La détection des tasks mortes reste déléguée à _restart_dead_tasks().
        """
        watchlist = self.compute_watchlist()
        stream_watchlist, unavailable = await self._validate_watchlist(watchlist)
        self.store.set_watchlist(
            watchlist,
            stream_symbols=stream_watchlist,
            unavailable=unavailable,
        )
        wanted = set(stream_watchlist)

        if unavailable:
            summary = ", ".join(
                f"{sym}={reason}" for sym, reason in sorted(unavailable.items())
            )
            print(f"[Observatory] symbols unavailable: {summary}")

        for sym in list(self._tasks):
            task = self._tasks[sym]
            if sym not in wanted:
                # Symbole sorti de la watchlist ou non supporté : annuler/retirer.
                task.cancel()
                self._tasks.pop(sym, None)
                self._engines.pop(sym, None)

        for sym in stream_watchlist:
            if sym not in self._tasks:
                self._tasks[sym] = asyncio.create_task(self._run_symbol(sym))

    async def run(self) -> None:
        self._running = True
        await self._reconcile()
        last_reselect = time.monotonic()
        try:
            while self._running:
                await asyncio.sleep(self.flush_interval_s)
                self.store.set_contract_meta(self._contract_provenance())
                self.store.flush()
                # Relance des tasks mortes à chaque flush (rythme flush_interval_s).
                await self._restart_dead_tasks()
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
    print(
        f"[Observatory] watchlist ({len(candidates)}): "
        f"{', '.join(c.symbol for c in candidates) or '(vide)'}"
    )
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
                line = line[len("export ") :]
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
