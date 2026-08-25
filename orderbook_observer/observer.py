"""
observer.py — Squelette du collecteur orderbook + trades stream.

P2/P3 de la roadmap : le corps des methodes stream sera implemente
lorsque l'operateur disposera d'un poste PC pour le debug WebSocket.
Ce fichier definit l'interface et le lifecycle (start/stop/health).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from observability.json_logger import get_logger

from .config import get_config, is_enabled
from .db import OrderbookDatabase

_log = get_logger("orderbook_observer.observer")


class OrderbookObserver:
    """
    Observer passif — collecte trades et orderbook via WebSocket.

    ADR-0007 + ADR-0018 : aucun signal, aucune injection dans le moteur.
    """

    def __init__(self) -> None:
        self._cfg = get_config()
        self._db = OrderbookDatabase(
            db_path=self._cfg["db_path"],
            retention_days=self._cfg["retention_days"],
        )
        self._running = False
        self._last_purge = 0.0
        self._symbols: list[str] = []

    @property
    def db(self) -> OrderbookDatabase:
        return self._db

    def load_symbols(self) -> list[str]:
        """Charge la liste des symboles depuis UNIVERSE_PINNED_SYMBOLS ou .env."""
        import os

        raw = os.getenv("UNIVERSE_PINNED_SYMBOLS", "")
        if raw:
            self._symbols = [s.strip() for s in raw.split(",") if s.strip()]
        else:
            self._symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        _log.info("[OrderbookObserver] %d symboles charges", len(self._symbols))
        return self._symbols

    async def run(self) -> None:
        """Boucle principale — connecte les streams et collecte."""
        if not is_enabled():
            _log.warning("[OrderbookObserver] ORDERBOOK_OBSERVER_ENABLED=false, arret.")
            return

        self.load_symbols()
        self._running = True
        _log.info(
            "[OrderbookObserver] demarrage — exchange=%s, %d symboles, depth=%d",
            self._cfg["exchange"],
            len(self._symbols),
            self._cfg["depth"],
        )

        try:
            while self._running:
                self._maybe_purge()
                await self._collect_cycle()
                await asyncio.sleep(self._cfg["snapshot_interval_s"])
        except asyncio.CancelledError:
            _log.info("[OrderbookObserver] arret demande (cancel)")
        except Exception as exc:
            _log.error("[OrderbookObserver] erreur fatale: %s", exc, exc_info=True)
        finally:
            self._running = False
            _log.info("[OrderbookObserver] arrete.")

    async def _collect_cycle(self) -> None:
        """
        Un cycle de collecte.

        TODO (P2/P3) : remplacer par de vrais appels WebSocket ccxt.pro.
        Pour l'instant, placeholder qui log le cycle.
        """
        _log.debug(
            "[OrderbookObserver] cycle — %d symboles (placeholder, streams non connectes)",
            len(self._symbols),
        )

    def _maybe_purge(self) -> None:
        """Purge les vieilles donnees si l'intervalle est depasse."""
        now = time.time()
        if now - self._last_purge > self._cfg["purge_interval_s"]:
            self._db.purge_old_data()
            self._last_purge = now

    def stop(self) -> None:
        """Arrete l'observer proprement."""
        self._running = False

    def health(self) -> dict[str, Any]:
        """Retourne l'etat de sante de l'observer."""
        return {
            "running": self._running,
            "enabled": is_enabled(),
            "exchange": self._cfg["exchange"],
            "symbols_count": len(self._symbols),
            "db_stats": self._db.stats,
        }
