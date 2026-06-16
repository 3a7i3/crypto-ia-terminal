"""
infra/wallet_sync.py — Source unique de vérité pour le solde du portefeuille.

Avant ce module, 4 chiffres de capital coexistaient sans jamais être synchronisés :
  - V9_INITIAL_CAPITAL      ($1000) — fallback exec_engine.fetch_available_capital()
  - MexcSimulator           ($10)   — fallback hardcodé interne au simulateur
  - VIRTUAL_CAPITAL_USD     ($100)  — equity pour portfolio_bot/system_intel_reporter
  - MEXC_SIM_CAPITAL                — override censé primer, absent en pratique

Résultat : chaque bot/module affichait un solde différent pour le même système.

Avec WalletSync, un seul chemin :
  - Mode paper  → WALLET_PAPER_CAPITAL (un seul env var) + somme cumulative des
                  pnl_usd du ledger (databases/paper_trades.jsonl) — solde qui
                  évolue avec chaque trade fermé, identique pour tous les
                  consommateurs (sizing, simulateur, bots Telegram, gates).
  - Mode live/testnet → solde réel récupéré via l'API de l'exchange configuré
                  par l'utilisateur (MEXC par défaut), avec cache TTL et
                  fallback sur la dernière valeur connue si l'API échoue
                  (évite de fabriquer un faux drawdown sur un échec réseau
                  temporaire).

Tous les modules doivent appeler get_wallet_sync().get_balance() au lieu de
lire indépendamment MEXC_SIM_CAPITAL / V9_INITIAL_CAPITAL / VIRTUAL_CAPITAL_USD.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

_TRADES_LOG = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
_PAPER_CAPITAL = float(os.getenv("WALLET_PAPER_CAPITAL", "100"))
_CACHE_TTL_S = float(os.getenv("WALLET_CACHE_TTL_S", "30"))


def _read_ledger_pnl() -> float:
    """Somme des pnl_usd de tous les trades CLOSE du ledger paper."""
    if not _TRADES_LOG.exists():
        return 0.0
    total = 0.0
    try:
        for line in _TRADES_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("event") == "CLOSE":
                total += float(ev.get("pnl_usd", 0) or 0)
    except Exception:
        pass
    return total


class WalletSync:
    """
    Source unique de solde — un seul point de vérité pour tout le système.

    Usage :
        wallet = WalletSync(exchange=ccxt_exchange, mode="paper")
        balance = wallet.get_balance()
    """

    def __init__(
        self,
        exchange: Any = None,
        mode: str = "paper",
        quote_asset: str = "USDT",
    ) -> None:
        self._exchange = exchange
        self._mode = mode
        self._quote_asset = quote_asset
        self._lock = threading.Lock()
        self._last_value: Optional[float] = None
        self._last_fetch_ts: float = 0.0

    @property
    def mode(self) -> str:
        return self._mode

    def get_balance(self, force_refresh: bool = False) -> float:
        """
        Retourne le solde actuel — paper (ledger) ou live/testnet (API réelle).

        Mode paper : toujours recalculé depuis le ledger (pas de cache,
        coût négligeable, garantit la fraîcheur après chaque trade fermé).
        Mode live/testnet : caché sur WALLET_CACHE_TTL_S secondes, fallback
        sur la dernière valeur connue si l'exchange échoue.
        """
        if self._mode == "paper":
            return _PAPER_CAPITAL + _read_ledger_pnl()

        with self._lock:
            now = time.time()
            if (
                not force_refresh
                and self._last_value is not None
                and now - self._last_fetch_ts < _CACHE_TTL_S
            ):
                return self._last_value

            if self._exchange is None:
                return self._fallback()

            try:
                bal = self._exchange.fetch_balance()
                usdt = float(bal.get("free", {}).get(self._quote_asset, 0.0))
                if usdt > 0:
                    self._last_value = usdt
                    self._last_fetch_ts = now
                    return usdt
            except Exception:
                pass

            return self._fallback()

    def _fallback(self) -> float:
        if self._last_value is not None:
            return self._last_value
        return _PAPER_CAPITAL

    def initial_capital(self) -> float:
        """Capital de départ — utilisé pour calculer ROI%/drawdown%."""
        return _PAPER_CAPITAL


_singleton: Optional[WalletSync] = None
_singleton_lock = threading.Lock()


def get_wallet_sync(exchange: Any = None, mode: Optional[str] = None) -> WalletSync:
    """
    Accesseur singleton — tous les modules partagent la même instance,
    garantissant un solde identique partout dans le système.

    Si l'instance existe déjà mais sans exchange attaché (créée par un module
    qui n'avait pas encore accès à l'objet ccxt), l'exchange fourni ici est
    attaché rétroactivement — évite qu'un appelant tardif (ex: ExecutionEngine
    après MexcSimulator) reste bloqué en mode dégradé.
    """
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            resolved_mode = mode or os.getenv("EXCHANGE_MODE", "paper")
            _singleton = WalletSync(exchange=exchange, mode=resolved_mode)
        elif exchange is not None and _singleton._exchange is None:
            _singleton._exchange = exchange
        return _singleton


def reset_wallet_sync() -> None:
    """Réinitialise le singleton — usage tests uniquement."""
    global _singleton
    with _singleton_lock:
        _singleton = None
