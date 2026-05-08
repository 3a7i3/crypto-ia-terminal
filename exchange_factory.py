"""
exchange_factory.py — Fabrique d'exchange générique multi-plateforme.
=====================================================================
Crée un exchange CCXT à partir des variables d'environnement.
Supporte Binance, Bybit, OKX, Kraken et tout exchange CCXT.

Convention de variables d'environnement :
    EXCHANGE_ID          — identifiant CCXT (défaut: binance)
    EXCHANGE_TESTNET     — true/false (défaut: false)
                           Alias supporté : BINANCE_TESTNET (rétrocompat)

    Clés API par exchange (remplacer {EXCHANGE} par l'ID en majuscule) :
    {EXCHANGE}_API_KEY   — ex. BINANCE_API_KEY, BYBIT_API_KEY, OKX_API_KEY
    {EXCHANGE}_API_SECRET

    Clés spéciales Binance (rétrocompatibilité) :
    BINANCE_API_KEY / BINANCE_API_SECRET         — spot testnet
    BINANCE_LIVE_API_KEY / BINANCE_LIVE_API_SECRET — live
    BINANCE_FUTURES_DEMO_KEY / BINANCE_FUTURES_DEMO_SECRET

Modes détectés :
    live          — clés live + EXCHANGE_TESTNET=false
    testnet       — clés + EXCHANGE_TESTNET=true
    futures_demo  — Binance uniquement (BINANCE_FUTURES_DEMO_KEY)
    paper         — aucune clé (simulation locale)

Usage :
    from exchange_factory import ExchangeFactory
    ex = ExchangeFactory.create()
    print(ExchangeFactory.detect_mode())
    print(ExchangeFactory.test_connection())
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Constantes par défaut ──────────────────────────────────────────────────────

_DEFAULT_EXCHANGE = "binance"
_CONNECTION_TIMEOUT = 10  # secondes

# Options CCXT communes à tous les exchanges
_COMMON_OPTIONS: dict[str, Any] = {
    "enableRateLimit": True,
}

# Options spécifiques par exchange (surcharges)
_EXCHANGE_OPTIONS: dict[str, dict[str, Any]] = {
    "binance": {
        "options": {
            "defaultType": "spot",
            "adjustForTimeDifference": False,
        }
    },
    "bybit": {
        "options": {
            "defaultType": "spot",
        }
    },
    "okx": {
        "options": {
            "defaultType": "spot",
        }
    },
    "kraken": {},
    "coinbase": {},
    "kucoin": {},
    "gateio": {
        "options": {
            "defaultType": "spot",
        }
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────


def _exchange_id() -> str:
    return os.getenv("EXCHANGE_ID", _DEFAULT_EXCHANGE).lower()


def _is_testnet() -> bool:
    exchange = _exchange_id()
    # Priorité : EXCHANGE_TESTNET → {EXCHANGE}_TESTNET (rétrocompat Binance)
    generic = os.getenv("EXCHANGE_TESTNET", "").lower()
    if generic in ("true", "false"):
        return generic == "true"
    legacy = os.getenv(f"{exchange.upper()}_TESTNET", "false").lower()
    return legacy == "true"


def _api_credentials(exchange: str) -> tuple[Optional[str], Optional[str]]:
    """Retourne (api_key, api_secret) pour l'exchange donné."""
    prefix = exchange.upper()
    key = os.getenv(f"{prefix}_API_KEY") or os.getenv(
        f"{prefix}_LIVE_API_KEY"
    )  # Binance live alias
    secret = os.getenv(f"{prefix}_API_SECRET") or os.getenv(f"{prefix}_LIVE_API_SECRET")
    return key or None, secret or None


def _futures_demo_credentials() -> tuple[Optional[str], Optional[str]]:
    """Binance uniquement — futures demo."""
    return (
        os.getenv("BINANCE_FUTURES_DEMO_KEY") or None,
        os.getenv("BINANCE_FUTURES_DEMO_SECRET") or None,
    )


# ── Détection de mode ──────────────────────────────────────────────────────────


def detect_mode(exchange: Optional[str] = None) -> str:
    """
    Détecte le mode de trading selon les variables d'environnement.

    Retourne : "live" | "testnet" | "futures_demo" | "paper"
    """
    exch = (exchange or _exchange_id()).lower()
    testnet = _is_testnet()
    key, secret = _api_credentials(exch)
    has_keys = bool(key and secret)

    # Futures demo Binance uniquement
    if exch == "binance":
        demo_key, demo_secret = _futures_demo_credentials()
        has_live_keys = bool(
            os.getenv("BINANCE_LIVE_API_KEY") and os.getenv("BINANCE_LIVE_API_SECRET")
        )
        if has_live_keys and not testnet:
            return "live"
        if demo_key and demo_secret:
            return "futures_demo"
        if has_keys and testnet:
            return "testnet"
        return "paper"

    # Exchange générique
    if has_keys and not testnet:
        return "live"
    if has_keys and testnet:
        return "testnet"
    return "paper"


# ── Fabrique principale ────────────────────────────────────────────────────────


class ExchangeFactory:
    """
    Fabrique d'exchange CCXT générique.

    Usage rapide :
        exchange = ExchangeFactory.create()            # depuis .env
        exchange = ExchangeFactory.create("bybit")     # exchange spécifique
        exchange = ExchangeFactory.create("okx", testnet=True)
    """

    @staticmethod
    def create(
        exchange_id: Optional[str] = None,
        testnet: Optional[bool] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        extra_options: Optional[dict] = None,
    ) -> Any:
        """
        Crée et retourne un objet exchange CCXT configuré.

        Args:
            exchange_id:   ID CCXT (ex. "binance", "bybit", "okx")
            testnet:       Force mode testnet (None = auto-détecte depuis env)
            api_key:       Clé API (None = depuis env)
            api_secret:    Secret API (None = depuis env)
            extra_options: Options CCXT supplémentaires

        Returns:
            Instance CCXT configurée ou None si import échoue.
        """
        try:
            import ccxt  # type: ignore[import]
        except ImportError:
            logger.error("[ExchangeFactory] ccxt non installé — pip install ccxt")
            return None

        exch_id = (exchange_id or _exchange_id()).lower()
        use_testnet = testnet if testnet is not None else _is_testnet()
        mode = detect_mode(exch_id)

        # Résolution des clés API
        if api_key is None or api_secret is None:
            env_key, env_secret = ExchangeFactory._resolve_credentials(exch_id, mode)
            api_key = api_key or env_key
            api_secret = api_secret or env_secret

        # Construction de la config CCXT
        config: dict[str, Any] = {**_COMMON_OPTIONS}
        exchange_opts = _EXCHANGE_OPTIONS.get(exch_id, {})
        config.update(exchange_opts)

        if api_key:
            config["apiKey"] = api_key
        if api_secret:
            config["secret"] = api_secret

        # Options passagères Binance (ex. password OKX)
        if extra_options:
            for k, v in extra_options.items():
                if k == "options":
                    config.setdefault("options", {}).update(v)
                else:
                    config[k] = v

        # Sélection classe CCXT
        if exch_id == "binance" and mode == "futures_demo":
            exch_cls = getattr(ccxt, "binanceusdm", None)
            if exch_cls is None:
                logger.error("[ExchangeFactory] binanceusdm non disponible")
                return None
        else:
            exch_cls = getattr(ccxt, exch_id, None)
            if exch_cls is None:
                logger.error(
                    "[ExchangeFactory] Exchange '%s' non reconnu par CCXT. "
                    "Exchanges disponibles: %s",
                    exch_id,
                    ", ".join(list(ccxt.exchanges)[:10]) + "...",
                )
                return None

        exchange = exch_cls(config)

        # Activation testnet/sandbox
        if use_testnet or mode == "testnet":
            ExchangeFactory._enable_testnet(exchange, exch_id)

        # Activation futures demo Binance
        if exch_id == "binance" and mode == "futures_demo":
            try:
                exchange.enable_demo_trading(True)
            except AttributeError:
                logger.warning(
                    "[ExchangeFactory] enable_demo_trading non supporté — futures demo peut ne pas fonctionner"
                )

        logger.info(
            "[ExchangeFactory] Exchange créé — id=%s mode=%s testnet=%s clés=%s",
            exch_id,
            mode,
            use_testnet,
            "oui" if api_key else "non",
        )
        return exchange

    @staticmethod
    def _resolve_credentials(
        exch_id: str, mode: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Résout les clés API depuis l'environnement selon le mode."""
        prefix = exch_id.upper()

        if exch_id == "binance":
            if mode == "live":
                return (
                    os.getenv("BINANCE_LIVE_API_KEY"),
                    os.getenv("BINANCE_LIVE_API_SECRET"),
                )
            if mode == "futures_demo":
                return (
                    os.getenv("BINANCE_FUTURES_DEMO_KEY"),
                    os.getenv("BINANCE_FUTURES_DEMO_SECRET"),
                )
            # testnet ou paper
            return os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET")

        # Exchange générique
        key = os.getenv(f"{prefix}_API_KEY") or os.getenv(f"{prefix}_LIVE_API_KEY")
        secret = os.getenv(f"{prefix}_API_SECRET") or os.getenv(
            f"{prefix}_LIVE_API_SECRET"
        )
        return key or None, secret or None

    @staticmethod
    def _enable_testnet(exchange: Any, exch_id: str) -> None:
        """Active le mode testnet/sandbox selon l'exchange."""
        try:
            if hasattr(exchange, "set_sandbox_mode"):
                exchange.set_sandbox_mode(True)
                return
        except Exception as e:
            logger.debug("[ExchangeFactory] set_sandbox_mode non supporté: %s", e)

        # Fallback : surcharger les URLs pour les exchanges qui n'ont pas set_sandbox_mode
        testnet_urls: dict[str, str] = {
            "bybit": "https://api-testnet.bybit.com",
            "okx": "https://www.okx.com",
            "kraken": "",
            "gateio": "https://fx-api-testnet.gateio.ws",
        }
        url = testnet_urls.get(exch_id)
        if url is None:
            return
        if not url:
            logger.warning(
                "[ExchangeFactory] %s : testnet non supporté — endpoint live utilisé",
                exch_id,
            )
            return
        try:
            exchange.urls["api"] = url
        except Exception as e:
            logger.warning(
                "[ExchangeFactory] Impossible d'appliquer l'URL testnet pour %s: %s",
                exch_id,
                e,
            )

    @staticmethod
    def test_connection(exchange_id: Optional[str] = None) -> dict:
        """
        Teste la connexion à l'exchange et retourne un dict de statut.

        Returns:
            {
                "status": "ok" | "error",
                "exchange": str,
                "mode": str,
                "latency_ms": int,
                "balance_usdt": float,
                "error": str (si erreur),
            }
        """
        exch_id = (exchange_id or _exchange_id()).lower()
        mode = detect_mode(exch_id)

        t0 = time.time()
        try:
            exchange = ExchangeFactory.create(exch_id)
            if exchange is None:
                return {
                    "status": "error",
                    "exchange": exch_id,
                    "mode": mode,
                    "latency_ms": -1,
                    "error": "Exchange creation failed",
                }

            balance = exchange.fetch_balance()
            usdt = float(balance.get("free", {}).get("USDT", 0.0))
            latency = int((time.time() - t0) * 1000)

            logger.info(
                "[ExchangeFactory] Connexion OK — %s/%s  USDT=%.2f  lat=%dms",
                exch_id,
                mode,
                usdt,
                latency,
            )
            return {
                "status": "ok",
                "exchange": exch_id,
                "mode": mode,
                "latency_ms": latency,
                "balance_usdt": usdt,
            }

        except Exception as exc:
            latency = int((time.time() - t0) * 1000)
            logger.error("[ExchangeFactory] test_connection erreur: %s", exc)
            return {
                "status": "error",
                "exchange": exch_id,
                "mode": mode,
                "latency_ms": latency,
                "error": str(exc),
            }

    @staticmethod
    def list_supported() -> list[str]:
        """Liste les exchanges CCXT disponibles."""
        try:
            import ccxt

            return ccxt.exchanges
        except ImportError:
            return []

    @staticmethod
    def info() -> dict:
        """Retourne les informations de configuration actuelles."""
        exch_id = _exchange_id()
        mode = detect_mode(exch_id)
        key, _ = ExchangeFactory._resolve_credentials(exch_id, mode)
        return {
            "exchange_id": exch_id,
            "mode": mode,
            "testnet": _is_testnet(),
            "has_api_key": bool(key),
            "env_vars": {
                "EXCHANGE_ID": os.getenv(
                    "EXCHANGE_ID", f"(non défini, défaut: {_DEFAULT_EXCHANGE})"
                ),
                "EXCHANGE_TESTNET": os.getenv(
                    "EXCHANGE_TESTNET",
                    f"(non défini, alias: BINANCE_TESTNET={os.getenv('BINANCE_TESTNET', 'false')})",
                ),
            },
        }


# ── Point d'entrée diagnostic ──────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    print("\n=== ExchangeFactory — Diagnostic ===")
    info = ExchangeFactory.info()
    print(f"\n  Configuration:")
    print(f"    Exchange   : {info['exchange_id']}")
    print(f"    Mode       : {info['mode']}")
    print(f"    Testnet    : {info['testnet']}")
    print(f"    Clés API   : {'✓' if info['has_api_key'] else '✗ (mode paper)'}")
    print(f"\n  Variables env:")
    for k, v in info["env_vars"].items():
        print(f"    {k} = {v}")

    print(f"\n  Test de connexion...")
    result = ExchangeFactory.test_connection()
    print(f"    Statut     : {result['status']}")
    print(f"    Latence    : {result['latency_ms']} ms")
    if result["status"] == "ok":
        print(f"    Balance    : {result.get('balance_usdt', 0):.2f} USDT")
    else:
        print(f"    Erreur     : {result.get('error', '?')}")

    print("\n====================================\n")
