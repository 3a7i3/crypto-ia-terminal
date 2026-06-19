"""
infra/wallet_sync.py — Source unique de vérité pour le solde du portefeuille.

Portefeuille totalitaire unique : un seul X pour tout le système.
X = solde réel du compte API connecté (spot/futures USDT libre).
Si aucune clé API : X = WALLET_PAPER_CAPITAL (env var, défaut 100).
Si X < 1.0 USDT : X = null → le système ne peut pas trader.

Avant ce module, 4 chiffres de capital coexistaient sans jamais être synchronisés :
  - V9_INITIAL_CAPITAL      ($1000) — fallback exec_engine.fetch_available_capital()
  - MexcSimulator           ($10)   — fallback hardcodé interne au simulateur
  - VIRTUAL_CAPITAL_USD     ($100)  — equity pour portfolio_bot/system_intel_reporter
  - MEXC_SIM_CAPITAL                — override censé primer, absent en pratique

Résultat : chaque bot/module affichait un solde différent pour le même système.

Avec WalletSync, un seul chemin :
  - Mode paper  → X (solde API ou WALLET_PAPER_CAPITAL) + somme cumulative des
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
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger(__name__)

_TRADES_LOG = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
_PAPER_CAPITAL = float(os.getenv("WALLET_PAPER_CAPITAL", "100"))
_CACHE_TTL_S = float(os.getenv("WALLET_CACHE_TTL_S", "30"))

# Seuil minimal pour qu'un solde soit considéré comme valide (X >= MIN_CAPITAL_X)
MIN_CAPITAL_X = 1.0


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
    Source unique de solde — portefeuille totalitaire unique (X) pour tout le système.

    X = solde réel API (spot + futures USDT) récupéré au démarrage via bootstrap().
    Si bootstrap() réussit : X remplace WALLET_PAPER_CAPITAL comme base de capital.
    Si bootstrap() échoue (pas de clé API, solde=0) : X=None → dégradé.

    Usage :
        wallet = get_wallet_sync()
        x = wallet.bootstrap(exchange)   # au démarrage uniquement
        balance = wallet.get_balance()   # X + PnL cumulé (paper) ou API live
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
        self._x: Optional[float] = (
            None  # Capital X — source unique, initialisé via bootstrap()
        )

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def capital_x(self) -> Optional[float]:
        """Capital X actuellement en usage (None = non initialisé ou solde invalide)."""
        return self._x

    def set_x(self, x: float) -> None:
        """
        Définit le capital X — unique source de capital pour tout le système.
        Appeler via bootstrap() au démarrage, pas directement.
        """
        if x < MIN_CAPITAL_X:
            raise ValueError(
                f"Capital X={x:.2f} invalide — doit être >= {MIN_CAPITAL_X} USDT"
            )
        self._x = float(x)
        self._last_value = self._x  # fallback live aussi

    def bootstrap(self, exchange: Any = None) -> Optional[float]:
        """
        Récupère le solde réel (spot USDT libre) depuis l'API au démarrage.

        Retourne X si X >= MIN_CAPITAL_X, sinon None.
        En cas de succès, X devient la base de capital pour tout le système.
        En cas d'échec (pas d'exchange, erreur API, solde=0) : retourne None.
        Le système continue en mode dégradé (WALLET_PAPER_CAPITAL comme fallback).
        """
        exch = exchange or self._exchange
        if exch is None:
            _log.info("[WalletSync] bootstrap: pas d'exchange — X=null (mode paper)")
            return None
        try:
            bal = exch.fetch_balance()
            free = bal.get("free", {}) or {}
            usdt = float(free.get(self._quote_asset, 0.0) or 0.0)
            if usdt >= MIN_CAPITAL_X:
                self.set_x(usdt)
                _log.info("[WalletSync] bootstrap: X=%.2f USDT (depuis API)", usdt)
                return usdt
            _log.warning(
                "[WalletSync] bootstrap: solde API = %.4f USDT < %.1f — X=null",
                usdt,
                MIN_CAPITAL_X,
            )
            return None
        except Exception as exc:
            _log.warning("[WalletSync] bootstrap: erreur API (%s) — X=null", exc)
            return None

    def _base_capital(self) -> float:
        """Capital de base : X si bootstrappé, sinon WALLET_PAPER_CAPITAL."""
        return self._x if self._x is not None else _PAPER_CAPITAL

    def get_balance(self, force_refresh: bool = False) -> float:
        """
        Retourne le solde actuel — paper (X + PnL ledger) ou live/testnet (API réelle).

        Mode paper : X (ou WALLET_PAPER_CAPITAL si X non initialisé) + cumul PnL ledger.
        Mode live/testnet : balance API cachée sur WALLET_CACHE_TTL_S, fallback X.
        """
        if self._mode == "paper":
            return self._base_capital() + _read_ledger_pnl()

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
        return self._base_capital()

    def initial_capital(self) -> float:
        """Capital de départ — utilisé pour calculer ROI%/drawdown%."""
        return self._base_capital()


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


def bootstrap_capital_x(exchange: Any = None) -> Optional[float]:
    """
    Bootstrap le capital X du singleton depuis l'API au démarrage.

    À appeler une seule fois, juste après la création de l'exchange.
    Retourne X (float >= 1.0) si succès, None si solde invalide/absent.
    """
    wallet = get_wallet_sync(exchange=exchange)
    return wallet.bootstrap(exchange)


def reset_wallet_sync() -> None:
    """Réinitialise le singleton — usage tests uniquement."""
    global _singleton
    with _singleton_lock:
        _singleton = None
