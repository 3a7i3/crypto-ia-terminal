"""
__main__.py — Point d'entree pour le service systemd.

Usage : python -m orderbook_observer
"""

from __future__ import annotations

import asyncio
import signal
import sys

from observability.json_logger import get_logger

from .config import is_enabled
from .observer import OrderbookObserver

_log = get_logger("orderbook_observer.__main__")


def main() -> None:
    if not is_enabled():
        _log.error(
            "ORDERBOOK_OBSERVER_ENABLED n'est pas 'true'. "
            "Ajoutez ORDERBOOK_OBSERVER_ENABLED=true dans .env pour activer."
        )
        sys.exit(1)

    observer = OrderbookObserver()

    def _shutdown(signum: int, frame: object) -> None:
        _log.info("Signal %d recu, arret en cours...", signum)
        observer.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    _log.info("Demarrage orderbook_observer...")
    asyncio.run(observer.run())


if __name__ == "__main__":
    main()
