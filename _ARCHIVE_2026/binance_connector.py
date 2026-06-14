"""
binance_connector.py — Connecteur Binance unifié (paper / testnet / futures_demo / live).
==========================================================================================
Détecte automatiquement le mode via les variables d'environnement et expose une API
simple, thread-safe, avec déduplication et session guard intégrés.

Modes (priorité décroissante) :
  1. live          — BINANCE_LIVE_API_KEY + BINANCE_LIVE_API_SECRET (BINANCE_TESTNET=false)
  2. futures_demo  — BINANCE_FUTURES_DEMO_KEY + BINANCE_FUTURES_DEMO_SECRET
  3. spot_testnet  — BINANCE_API_KEY + BINANCE_API_SECRET + BINANCE_TESTNET=true
  4. paper         — aucune clé (simulation locale, défaut)

Variables d'env reconnues :
    BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET
    BINANCE_LIVE_API_KEY, BINANCE_LIVE_API_SECRET
    BINANCE_FUTURES_DEMO_KEY, BINANCE_FUTURES_DEMO_SECRET
    PAPER_INITIAL_CAPITAL  (float, défaut 10 000 USDT)

Sécurité :
    - OrderDeduplicator  → bloque les doublons < 30 s
    - SessionGuard       → halt si drawdown/pertes dépassent les seuils
    - Aucune clé hardcodée

Usage :
    from quant_hedge_ai.binance_connector import BinanceConnector
    bc = BinanceConnector()
    print(bc.test_connection())
    print(bc.get_balance())
    order = bc.place_order("BTC/USDT", "buy", amount_usdt=50)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator
from quant_hedge_ai.agents.risk.session_guard import SessionGuard

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

_PAPER_CAPITAL_DEFAULT = 10_000.0
_DEDUP_WINDOW_SEC = 30.0
_MAX_ORDER_USD = 50_000.0
_MAX_DD = 0.08
_MAX_SESSION_LOSS = 0.05
_MAX_CONSEC_LOSSES = 5


# ── Helpers internes ──────────────────────────────────────────────────────────


def _detect_mode() -> str:
    """
    Détermine le mode de trading selon les variables d'environnement présentes.
    Retourne l'une de : "live", "futures_demo", "spot_testnet", "paper".
    """
    has_live_keys = bool(
        os.getenv("BINANCE_LIVE_API_KEY") and os.getenv("BINANCE_LIVE_API_SECRET")
    )
    has_futures_demo = bool(
        os.getenv("BINANCE_FUTURES_DEMO_KEY")
        and os.getenv("BINANCE_FUTURES_DEMO_SECRET")
    )
    has_spot_keys = bool(
        os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_SECRET")
    )
    is_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    if has_live_keys and not is_testnet:
        return "live"
    if has_futures_demo:
        return "futures_demo"
    if has_spot_keys and is_testnet:
        return "spot_testnet"
    return "paper"


# ── Paper wallet simulé ───────────────────────────────────────────────────────


class _PaperWallet:
    """Portefeuille simulé en mémoire pour le mode paper."""

    def __init__(self, initial_usdt: float = _PAPER_CAPITAL_DEFAULT) -> None:
        self._balances: dict[str, float] = {"USDT": initial_usdt}
        self._orders: list[dict] = []
        self._order_counter = 1

    def get_balance(self) -> dict[str, float]:
        return dict(self._balances)

    def get_usdt(self) -> float:
        return self._balances.get("USDT", 0.0)

    def place_order(
        self, symbol: str, side: str, amount_usdt: float, price: float
    ) -> dict:
        """Simule un ordre market et met à jour le solde."""
        asset = symbol.split("/")[0] if "/" in symbol else symbol.replace("USDT", "")
        fee = amount_usdt * 0.001  # 0.1 % commission Binance
        order_id = f"paper_{self._order_counter:06d}"
        self._order_counter += 1

        if side.lower() == "buy":
            cost = amount_usdt + fee
            if self._balances.get("USDT", 0) < cost:
                return {
                    "status": "rejected",
                    "reason": "insufficient_funds",
                    "mode": "paper",
                }
            qty = amount_usdt / price
            self._balances["USDT"] = self._balances.get("USDT", 0) - cost
            self._balances[asset] = self._balances.get(asset, 0) + qty
        else:  # sell
            qty = amount_usdt / price
            if self._balances.get(asset, 0) < qty:
                return {
                    "status": "rejected",
                    "reason": "insufficient_asset",
                    "mode": "paper",
                }
            self._balances[asset] = self._balances.get(asset, 0) - qty
            self._balances["USDT"] = self._balances.get("USDT", 0) + amount_usdt - fee

        order = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "amount_usdt": amount_usdt,
            "price": price,
            "qty": qty if "qty" in dir() else 0,
            "fee_usdt": fee,
            "status": "filled",
            "mode": "paper",
            "timestamp": time.time(),
        }
        self._orders.append(order)
        return order

    def get_open_orders(self) -> list[dict]:
        # Paper trading → tous les ordres sont immédiatement remplis
        return []


# ── Connecteur principal ──────────────────────────────────────────────────────


class BinanceConnector:
    """
    API unifiée Binance (paper / testnet / futures_demo / live).

    Le mode est détecté automatiquement depuis les variables d'environnement.
    En mode paper, aucune clé API n'est nécessaire.
    """

    def __init__(self, mode: Optional[str] = None) -> None:
        self._mode = mode or _detect_mode()
        self._exchange = None
        self._paper = None

        # Couche de sécurité toujours active
        self._dedup = OrderDeduplicator(window_seconds=_DEDUP_WINDOW_SEC)
        self._guard = SessionGuard(
            max_session_drawdown=float(os.getenv("EXEC_MAX_DD", str(_MAX_DD))),
            max_session_loss=float(os.getenv("EXEC_MAX_LOSS", str(_MAX_SESSION_LOSS))),
            max_consecutive_losses=int(
                os.getenv("EXEC_MAX_CONSEC_LOSSES", str(_MAX_CONSEC_LOSSES))
            ),
            max_order_size_usd=float(
                os.getenv("EXEC_MAX_ORDER_USD", str(_MAX_ORDER_USD))
            ),
        )

        if self._mode == "paper":
            initial = float(
                os.getenv("PAPER_INITIAL_CAPITAL", str(_PAPER_CAPITAL_DEFAULT))
            )
            self._paper = _PaperWallet(initial)
            logger.info("[BinanceConnector] Mode PAPER (capital=%.2f USDT)", initial)
        else:
            self._exchange = self._init_exchange()

    # ── Initialisation exchange ───────────────────────────────────────────────

    def _init_exchange(self):
        try:
            import ccxt  # noqa: F401
        except ImportError:
            logger.error("[BinanceConnector] ccxt non installé — fallback paper")
            self._mode = "paper"
            self._paper = _PaperWallet()
            return None

        try:
            import ccxt

            if self._mode == "live":
                ex = ccxt.binance(
                    {
                        "apiKey": os.getenv("BINANCE_LIVE_API_KEY"),
                        "secret": os.getenv("BINANCE_LIVE_API_SECRET"),
                        "enableRateLimit": True,
                        "options": {"defaultType": "spot"},
                    }
                )
                logger.info("[BinanceConnector] Mode LIVE initialisé")
                return ex

            elif self._mode == "spot_testnet":
                ex = ccxt.binance(
                    {
                        "apiKey": os.getenv("BINANCE_API_KEY"),
                        "secret": os.getenv("BINANCE_API_SECRET"),
                        "enableRateLimit": True,
                        "options": {"defaultType": "spot"},
                    }
                )
                ex.set_sandbox_mode(True)
                logger.info("[BinanceConnector] Mode SPOT TESTNET initialisé")
                return ex

            elif self._mode == "futures_demo":
                ex = ccxt.binanceusdm(
                    {
                        "apiKey": os.getenv("BINANCE_FUTURES_DEMO_KEY"),
                        "secret": os.getenv("BINANCE_FUTURES_DEMO_SECRET"),
                        "enableRateLimit": True,
                    }
                )
                ex.enable_demo_trading(True)
                logger.info("[BinanceConnector] Mode FUTURES DEMO initialisé")
                return ex

        except Exception as exc:
            logger.error(
                "[BinanceConnector] Erreur init exchange (%s) — fallback paper", exc
            )
            self._mode = "paper"
            self._paper = _PaperWallet()
            return None

    # ── API publique ──────────────────────────────────────────────────────────

    def test_connection(self) -> dict:
        """
        Teste la connexion et retourne un dict de statut.

        Returns:
            {"status": "ok"|"error", "mode": str, "balance_usdt": float, "latency_ms": int}
        """
        t0 = time.time()
        try:
            if self._mode == "paper":
                usdt = self._paper.get_usdt()  # type: ignore[union-attr]
                latency = int((time.time() - t0) * 1000)
                return {
                    "status": "ok",
                    "mode": "paper",
                    "balance_usdt": usdt,
                    "latency_ms": latency,
                }

            bal = self._exchange.fetch_balance()  # type: ignore[union-attr]
            usdt = float(bal.get("free", {}).get("USDT", 0.0))
            latency = int((time.time() - t0) * 1000)
            logger.info(
                "[BinanceConnector] Connexion OK — mode=%s balance=%.2f USDT lat=%dms",
                self._mode,
                usdt,
                latency,
            )
            return {
                "status": "ok",
                "mode": self._mode,
                "balance_usdt": usdt,
                "latency_ms": latency,
            }

        except Exception as exc:
            logger.error("[BinanceConnector] test_connection erreur : %s", exc)
            return {
                "status": "error",
                "mode": self._mode,
                "error": str(exc),
                "latency_ms": -1,
            }

    def get_balance(self) -> dict[str, float]:
        """Retourne {asset: montant} pour tous les actifs avec solde > 0."""
        try:
            if self._mode == "paper":
                return {k: v for k, v in self._paper.get_balance().items() if v > 0}  # type: ignore

            bal = self._exchange.fetch_balance()  # type: ignore
            free = bal.get("free", {})
            return {k: float(v) for k, v in free.items() if v and float(v) > 0}
        except Exception as exc:
            logger.error("[BinanceConnector] get_balance erreur : %s", exc)
            return {}

    def place_order(
        self,
        symbol: str,
        side: str,
        amount_usdt: float,
        order_type: str = "market",
    ) -> dict:
        """
        Place un ordre market (buy/sell) pour `amount_usdt` dollars.

        Toujours soumis au pipeline de sécurité (déduplication + session guard).

        Args:
            symbol:      ex. "BTC/USDT"
            side:        "buy" ou "sell"
            amount_usdt: montant en USDT
            order_type:  "market" (seul supporté actuellement)

        Returns:
            dict ordre avec clés: id, symbol, side, status, mode, ...
        """
        # ── 1. Déduplication ─────────────────────────────────────────────────
        if self._dedup.is_duplicate(symbol, side, amount_usdt):
            return {
                "status": "rejected",
                "reason": "duplicate_order",
                "mode": self._mode,
            }

        # ── 2. Session guard ─────────────────────────────────────────────────
        try:
            self._guard.check_order(symbol, side, amount_usdt)
        except Exception as exc:
            logger.warning("[BinanceConnector] SessionGuard bloque l'ordre : %s", exc)
            return {"status": "rejected", "reason": str(exc), "mode": self._mode}

        # ── 3. Exécution ─────────────────────────────────────────────────────
        try:
            price = self.get_price(symbol)
            if price <= 0:
                return {
                    "status": "error",
                    "reason": "price_fetch_failed",
                    "mode": self._mode,
                }

            if self._mode == "paper":
                order = self._paper.place_order(symbol, side, amount_usdt, price)  # type: ignore
            else:
                qty = amount_usdt / price
                raw = self._exchange.create_order(  # type: ignore
                    symbol, order_type, side, qty
                )
                order = {
                    "id": raw.get("id", "?"),
                    "symbol": symbol,
                    "side": side,
                    "amount_usdt": amount_usdt,
                    "price": price,
                    "qty": qty,
                    "status": raw.get("status", "filled"),
                    "mode": self._mode,
                    "timestamp": time.time(),
                    "raw": raw,
                }

            # Enregistre pour déduplication future
            self._dedup.register(symbol, side, amount_usdt)
            logger.info(
                "[BinanceConnector] Ordre %s %s %.2f USDT @ %.4f → %s",
                side,
                symbol,
                amount_usdt,
                price,
                order.get("status"),
            )
            return order

        except Exception as exc:
            logger.error("[BinanceConnector] place_order erreur : %s", exc)
            return {"status": "error", "reason": str(exc), "mode": self._mode}

    def get_open_orders(self) -> list[dict]:
        """Retourne la liste des ordres ouverts."""
        try:
            if self._mode == "paper":
                return self._paper.get_open_orders()  # type: ignore
            raw = self._exchange.fetch_open_orders()  # type: ignore
            return [
                {
                    "id": o.get("id"),
                    "symbol": o.get("symbol"),
                    "side": o.get("side"),
                    "price": o.get("price"),
                    "amount": o.get("amount"),
                    "status": o.get("status"),
                    "mode": self._mode,
                }
                for o in raw
            ]
        except Exception as exc:
            logger.error("[BinanceConnector] get_open_orders erreur : %s", exc)
            return []

    def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Annule un ordre ouvert par son ID."""
        try:
            if self._mode == "paper":
                return {"status": "cancelled", "order_id": order_id, "mode": "paper"}
            result = self._exchange.cancel_order(order_id, symbol)  # type: ignore
            return {
                "status": "cancelled",
                "order_id": order_id,
                "mode": self._mode,
                "raw": result,
            }
        except Exception as exc:
            logger.error("[BinanceConnector] cancel_order erreur : %s", exc)
            return {"status": "error", "reason": str(exc), "mode": self._mode}

    def get_price(self, symbol: str) -> float:
        """
        Retourne le prix actuel (last) du symbole.
        En mode paper sans exchange, utilise des prix simulés (BTC≈42 000, etc.).
        """
        if self._exchange is not None:
            try:
                ticker = self._exchange.fetch_ticker(symbol)
                return float(ticker.get("last") or ticker.get("close") or 0.0)
            except Exception as exc:
                logger.warning(
                    "[BinanceConnector] get_price(%s) erreur : %s", symbol, exc
                )

        # Fallback paper : prix simulés stables
        _fallback = {
            "BTC/USDT": 42_000.0,
            "ETH/USDT": 2_300.0,
            "BNB/USDT": 320.0,
            "SOL/USDT": 90.0,
        }
        return _fallback.get(symbol, 1.0)

    def get_portfolio_value(self) -> float:
        """
        Retourne la valeur totale du portefeuille en USDT
        (balance USDT + valeur des actifs au prix marché).
        """
        try:
            balances = self.get_balance()
            total = balances.get("USDT", 0.0)
            for asset, qty in balances.items():
                if asset == "USDT" or qty <= 0:
                    continue
                symbol = f"{asset}/USDT"
                try:
                    price = self.get_price(symbol)
                    total += qty * price
                except Exception:
                    pass
            return round(total, 2)
        except Exception as exc:
            logger.error("[BinanceConnector] get_portfolio_value erreur : %s", exc)
            return 0.0

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        """Mode actif : "paper", "spot_testnet", "futures_demo" ou "live"."""
        return self._mode

    def __repr__(self) -> str:
        return f"BinanceConnector(mode={self._mode!r})"


# ── Point d'entrée ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    bc = BinanceConnector()
    print("\n=== BinanceConnector — Test rapide ===")
    status = bc.test_connection()
    print(f"  Connexion  : {status}")
    print(f"  Balances   : {bc.get_balance()}")
    print(f"  BTC price  : {bc.get_price('BTC/USDT'):.2f} USDT")
    print(f"  Portfolio  : {bc.get_portfolio_value():.2f} USDT")
    print(f"  Mode       : {bc.mode}")
    order = bc.place_order("BTC/USDT", "buy", 100)
    print(f"  Ordre test : {order}")
    print("======================================\n")
