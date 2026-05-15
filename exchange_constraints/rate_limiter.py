"""
exchange_constraints/rate_limiter.py — Rate limiter token bucket pour Binance.

Binance USDT-M Futures limites :
  - 10 ordres / seconde (ORDER rate limit)
  - 1200 poids / minute = 20/s (REQUEST_WEIGHT rate limit)

Chaque endpoint Binance a un poids different (ex: exchangeInfo = 40, newOrder = 1).
Le poids par defaut est 1 si non specifie.

Classes :
  TokenBucket      : token bucket generique thread-safe
  OrderRateLimiter : facade Binance (deux buckets + weights par endpoint)

Constantes ENDPOINT_WEIGHTS : poids officiels des endpoints les plus utilises.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

# Poids des endpoints Binance USDT-M Futures les plus utilises
# Source : https://binance-docs.github.io/apidocs/futures/en/
ENDPOINT_WEIGHTS: dict[str, int] = {
    "POST /fapi/v1/order": 1,  # nouvel ordre
    "DELETE /fapi/v1/order": 1,  # annuler ordre
    "DELETE /fapi/v1/allOpenOrders": 1,  # annuler tous les ordres
    "GET /fapi/v1/order": 1,  # statut d'un ordre
    "GET /fapi/v1/openOrders": 1,  # liste ordres ouverts (si symbole specifie)
    "GET /fapi/v1/openOrders_all": 40,  # liste tous ordres ouverts (sans symbole)
    "GET /fapi/v1/ticker/price": 1,  # prix actuel (avec symbole)
    "GET /fapi/v1/ticker/price_all": 2,  # tous les prix
    "GET /fapi/v1/depth": 10,  # orderbook (limite 100)
    "GET /fapi/v1/klines": 1,  # klines (avec symbole + limit <= 100)
    "GET /fapi/v1/exchangeInfo": 40,  # regles de l'exchange
    "GET /fapi/v1/account": 5,  # infos compte
    "GET /fapi/v2/account": 5,
    "GET /fapi/v1/positionRisk": 5,  # positions ouvertes
}


@dataclass
class AcquireResult:
    allowed: bool
    reason: Optional[str] = None
    retry_after_s: float = 0.0
    order_tokens_remaining: float = 0.0
    weight_tokens_remaining: float = 0.0


class TokenBucket:
    """
    Token bucket thread-safe.

    capacity    : nombre max de tokens (burst max)
    refill_rate : tokens ajoutes par seconde
    """

    def __init__(self, capacity: float, refill_rate: float, name: str = "") -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity}")
        if refill_rate <= 0:
            raise ValueError(f"refill_rate must be > 0, got {refill_rate}")
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.name = name
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    def acquire(self, tokens: float = 1.0) -> tuple[bool, float]:
        """
        Tente d'acquerir 'tokens' tokens.
        Retourne (allowed: bool, retry_after_s: float).
        """
        if tokens <= 0:
            raise ValueError(f"tokens must be > 0")

        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True, 0.0
            deficit = tokens - self._tokens
            retry_after = deficit / self.refill_rate
            return False, retry_after

    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def wait_until_available(
        self, tokens: float = 1.0, timeout_s: float = 30.0
    ) -> bool:
        """
        Attend que les tokens soient disponibles (bloquant).
        Retourne True si acquis avant timeout, False si timeout depasse.

        A utiliser en production pour absorber les pics de rate limiting
        plutot que d'echouer immediatement.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            allowed, retry_after = self.acquire(tokens)
            if allowed:
                return True
            sleep_time = min(retry_after, deadline - time.monotonic(), 1.0)
            if sleep_time <= 0:
                break
            time.sleep(sleep_time)
        return False

    def reset(self) -> None:
        with self._lock:
            self._tokens = self.capacity
            self._last_refill = time.monotonic()

    def stats(self) -> dict:
        with self._lock:
            self._refill()
            return {
                "name": self.name,
                "tokens_available": round(self._tokens, 2),
                "capacity": self.capacity,
                "refill_rate_per_s": self.refill_rate,
                "fill_pct": round(self._tokens / self.capacity * 100, 1),
            }


class OrderRateLimiter:
    """
    Facade Binance : deux buckets en serie + gestion des weights par endpoint.

    order_bucket  : 10 ordres/s
    weight_bucket : 1200 poids/min = 20/s

    acquire(endpoint)              : acquiert en utilisant le weight de l'endpoint
    acquire_weight(weight)         : acquiert avec un weight explicite
    wait_and_acquire(endpoint)     : attend si necessaire (bloquant)
    """

    def __init__(
        self,
        order_capacity: float = 10.0,
        order_rate_per_s: float = 10.0,
        weight_capacity: float = 1200.0,
        weight_rate_per_s: float = 20.0,
    ) -> None:
        self._order_bucket = TokenBucket(
            capacity=order_capacity,
            refill_rate=order_rate_per_s,
            name="order_rate",
        )
        self._weight_bucket = TokenBucket(
            capacity=weight_capacity,
            refill_rate=weight_rate_per_s,
            name="weight",
        )

    def _get_weight(self, endpoint: str) -> int:
        return ENDPOINT_WEIGHTS.get(endpoint, 1)

    def acquire(self, endpoint: str = "POST /fapi/v1/order") -> AcquireResult:
        """
        Tente d'acquerir 1 slot d'ordre + le weight de l'endpoint.
        Non-bloquant : retourne immediatement si rate-limited.
        """
        weight = self._get_weight(endpoint)
        return self.acquire_weight(weight, is_order="order" in endpoint.lower())

    def acquire_weight(
        self, weight: float = 1.0, is_order: bool = True
    ) -> AcquireResult:
        """Acquiert avec un weight explicite. is_order=True consomme aussi le bucket ordre."""
        # Order bucket (seulement pour les ordres)
        if is_order:
            order_ok, order_retry = self._order_bucket.acquire(1.0)
            if not order_ok:
                return AcquireResult(
                    allowed=False,
                    reason="order_rate_limit",
                    retry_after_s=order_retry,
                    order_tokens_remaining=self._order_bucket.available(),
                    weight_tokens_remaining=self._weight_bucket.available(),
                )

        # Weight bucket
        weight_ok, weight_retry = self._weight_bucket.acquire(weight)
        if not weight_ok:
            return AcquireResult(
                allowed=False,
                reason="weight_rate_limit",
                retry_after_s=weight_retry,
                order_tokens_remaining=self._order_bucket.available(),
                weight_tokens_remaining=self._weight_bucket.available(),
            )

        return AcquireResult(
            allowed=True,
            order_tokens_remaining=self._order_bucket.available(),
            weight_tokens_remaining=self._weight_bucket.available(),
        )

    def wait_and_acquire(
        self, endpoint: str = "POST /fapi/v1/order", timeout_s: float = 30.0
    ) -> bool:
        """
        Attend et acquiert en mode bloquant.
        Retourne True si acquis, False si timeout.
        """
        weight = self._get_weight(endpoint)
        is_order = "order" in endpoint.lower()

        if is_order:
            if not self._order_bucket.wait_until_available(1.0, timeout_s):
                return False

        return self._weight_bucket.wait_until_available(weight, timeout_s)

    def reset(self) -> None:
        self._order_bucket.reset()
        self._weight_bucket.reset()

    def stats(self) -> dict:
        return {
            "order_bucket": self._order_bucket.stats(),
            "weight_bucket": self._weight_bucket.stats(),
        }

    @property
    def order_tokens_available(self) -> float:
        return self._order_bucket.available()

    @property
    def weight_tokens_available(self) -> float:
        return self._weight_bucket.available()
