"""
infra/mexc_reader.py — Connexion MEXC read-only (Spot + Futures USDT).

Objectif Phase 1 : lecture seule — aucun ordre, aucune mutation d'état.
Variables d'environnement :
    MEXC_API_KEY    : clé API MEXC (permissions : lecture uniquement)
    MEXC_API_SECRET : secret API MEXC

Usage :
    from infra.mexc_reader import MexcReader
    reader = MexcReader()
    print(reader.spot.test_connection())
    print(reader.futures.test_connection())
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

try:
    import ccxt

    _CCXT_OK = True
except ImportError:
    _CCXT_OK = False


@dataclass
class ConnectionResult:
    exchange: str
    mode: str
    status: str  # "ok" | "error" | "no_keys"
    latency_ms: int
    balance_usdt: float = 0.0
    markets_count: int = 0
    error: str = ""

    def __str__(self) -> str:
        if self.status == "ok":
            return (
                f"[{self.exchange}] OK | {self.mode} | "
                f"lat={self.latency_ms}ms | "
                f"USDT={self.balance_usdt:.2f} | "
                f"marchés={self.markets_count}"
            )
        return f"[{self.exchange}] {self.status.upper()} — {self.error}"


class _MexcEndpoint:
    """
    Connexion read-only à un endpoint MEXC (spot ou futures).

    Sécurité structurelle : aucune méthode d'ordre n'est exposée.
    """

    def __init__(self, name: str, default_type: str) -> None:
        self._name = name
        self._default_type = default_type
        self._exchange: Optional[object] = None
        self._api_key = os.getenv("MEXC_API_KEY", "")
        self._api_secret = os.getenv("MEXC_API_SECRET", "")

    def _build(self) -> Optional[object]:
        if not _CCXT_OK:
            return None
        cfg: dict = {
            "enableRateLimit": True,
            "options": {"defaultType": self._default_type},
        }
        if self._api_key and self._api_secret:
            cfg["apiKey"] = self._api_key
            cfg["secret"] = self._api_secret
        ex = ccxt.mexc(cfg)
        return ex

    def _get(self) -> Optional[object]:
        if self._exchange is None:
            self._exchange = self._build()
        return self._exchange

    # ── Lecture seule — API publique ──────────────────────────────────────────

    def test_connection(self) -> ConnectionResult:
        ex = self._get()
        has_keys = bool(self._api_key and self._api_secret)
        mode = "read_only_auth" if has_keys else "read_only_public"
        t0 = time.time()
        if ex is None:
            return ConnectionResult(
                exchange=self._name,
                mode=mode,
                status="error",
                latency_ms=-1,
                error="ccxt non installé",
            )
        try:
            markets = ex.load_markets()  # type: ignore[union-attr]
            latency = int((time.time() - t0) * 1000)
            usdt = 0.0
            if has_keys:
                try:
                    bal = ex.fetch_balance()  # type: ignore[union-attr]
                    usdt = float(bal.get("free", {}).get("USDT", 0.0))
                except Exception:
                    pass
            return ConnectionResult(
                exchange=self._name,
                mode=mode,
                status="ok",
                latency_ms=latency,
                balance_usdt=usdt,
                markets_count=len(markets),
            )
        except Exception as exc:
            latency = int((time.time() - t0) * 1000)
            return ConnectionResult(
                exchange=self._name,
                mode=mode,
                status="error",
                latency_ms=latency,
                error=str(exc)[:200],
            )

    def fetch_ticker(self, symbol: str) -> dict:
        ex = self._get()
        if ex is None:
            return {}
        return ex.fetch_ticker(symbol)  # type: ignore[union-attr]

    def fetch_balance(self) -> dict:
        ex = self._get()
        if ex is None or not self._api_key:
            return {}
        return ex.fetch_balance()  # type: ignore[union-attr]

    def fetch_positions(self) -> list:
        """Futures uniquement — positions ouvertes (read-only)."""
        ex = self._get()
        if ex is None or not self._api_key:
            return []
        try:
            return ex.fetch_positions() or []  # type: ignore[union-attr]
        except Exception:
            return []

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list:
        ex = self._get()
        if ex is None:
            return []
        return ex.fetch_ohlcv(symbol, timeframe, limit=limit)  # type: ignore

    def fetch_order_book(self, symbol: str, depth: int = 20) -> dict:
        ex = self._get()
        if ex is None:
            return {}
        return ex.fetch_order_book(symbol, depth)  # type: ignore[union-attr]


class MexcReader:
    """
    Façade read-only unifiée MEXC Spot + Futures.

    Aucune méthode d'écriture n'est exposée — sécurité structurelle.
    """

    def __init__(self) -> None:
        self.spot = _MexcEndpoint("mexc_spot", "spot")
        self.futures = _MexcEndpoint("mexc_futures", "swap")

    def test_all(self) -> tuple[ConnectionResult, ConnectionResult]:
        spot_r = self.spot.test_connection()
        futures_r = self.futures.test_connection()
        return spot_r, futures_r


# ── Diagnostic CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    root = Path(__file__).parent.parent
    env_file = root / ".env"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)

    key = os.getenv("MEXC_API_KEY", "")
    print("\n=== MEXC Reader — Diagnostic ===")
    status = "OK presente" if key else "ABSENTE (lecture publique uniquement)"
    print(f"  API Key : {status}")
    print()

    reader = MexcReader()
    spot_r, futures_r = reader.test_all()

    print(f"  Spot    : {spot_r}")
    print(f"  Futures : {futures_r}")
    print()

    if spot_r.status == "ok":
        print("  Test ticker BTC/USDT (spot) :")
        try:
            t = reader.spot.fetch_ticker("BTC/USDT")
            print(f"    last={t.get('last')} bid={t.get('bid')} ask={t.get('ask')}")
        except Exception as e:
            print(f"    Erreur: {e}")

    if futures_r.status == "ok":
        print("  Test ticker BTC/USDT:USDT (futures) :")
        try:
            t = reader.futures.fetch_ticker("BTC/USDT:USDT")
            print(f"    last={t.get('last')} bid={t.get('bid')} ask={t.get('ask')}")
        except Exception as e:
            print(f"    Erreur: {e}")

    overall = (
        "OK" if spot_r.status == "ok" and futures_r.status == "ok" else "PARTIEL/ERREUR"
    )
    print(f"\n  Résultat global : {overall}")
    print("================================\n")
    sys.exit(0 if overall == "OK" else 1)
