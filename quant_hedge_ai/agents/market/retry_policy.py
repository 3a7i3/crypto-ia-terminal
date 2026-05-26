"""Retry avec backoff exponentiel + circuit breaker pour les appels réseau."""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.market.retry_policy")
T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    label: str = "",
) -> T | None:
    """
    Exécute fn() avec retry exponentiel. Retourne None après max_retries échecs.

    Usage:
        result = retry_with_backoff(
            lambda: exchange.fetch_ohlcv("BTC/USDT", "1h", limit=200),
            max_retries=3, base_delay=1.0, label="fetch_ohlcv BTC/USDT",
        )
    """
    prefix = f"[{label}] " if label else ""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_retries:
                _log.error(
                    "%séchec définitif après %d tentatives: %s",
                    prefix,
                    max_retries + 1,
                    exc,
                )
                return None
            delay = min(base_delay * (2**attempt), max_delay)
            if jitter:
                delay *= random.uniform(0.6, 1.4)
            _log.warning(
                "%stentative %d/%d échouée (%s) — retry dans %.1fs",
                prefix,
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            time.sleep(delay)
    return None


class CircuitBreaker:
    """
    Circuit breaker à 3 états : CLOSED → OPEN → HALF_OPEN → CLOSED.

    - CLOSED   : fonctionne normalement
    - OPEN     : bloque tous les appels pendant recovery_timeout secondes
    - HALF_OPEN: laisse passer un appel test ; succès → CLOSED, échec → OPEN

    Usage:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        result = cb.call(lambda: exchange.fetch_ohlcv(...))
        if result is None and cb.is_open:
            # utiliser le fallback
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        label: str = "",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.label = label
        self._failures = 0
        self._state = self.CLOSED
        self._opened_at: float = 0.0
        self._half_open_attempted = False

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.time() - self._opened_at >= self.recovery_timeout:
                self._state = self.HALF_OPEN
                self._half_open_attempted = False
                _log.info("[CircuitBreaker:%s] → HALF_OPEN (test autorisé)", self.label)
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == self.OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == self.CLOSED

    def call(self, fn: Callable[[], T]) -> T | None:
        current = self.state
        if current == self.OPEN:
            _log.debug("[CircuitBreaker:%s] OUVERT — appel bloqué", self.label)
            return None
        if current == self.HALF_OPEN and self._half_open_attempted:
            return None

        if current == self.HALF_OPEN:
            self._half_open_attempted = True

        try:
            result = fn()
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure(exc)
            return None

    def _on_success(self) -> None:
        if self._state != self.CLOSED:
            _log.info("[CircuitBreaker:%s] → CLOSED (récupéré)", self.label)
        self._failures = 0
        self._state = self.CLOSED

    def _on_failure(self, exc: Exception) -> None:
        self._failures += 1
        _log.warning(
            "[CircuitBreaker:%s] échec #%d/%d: %s",
            self.label,
            self._failures,
            self.failure_threshold,
            exc,
        )
        if self._failures >= self.failure_threshold:
            self._state = self.OPEN
            self._opened_at = time.time()
            _log.error(
                "[CircuitBreaker:%s] → OPEN (%d échecs consécutifs, recovery dans %.0fs)",
                self.label,
                self._failures,
                self.recovery_timeout,
            )

    def reset(self) -> None:
        self._failures = 0
        self._state = self.CLOSED
        self._opened_at = 0.0
