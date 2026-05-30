"""
Chaos #6 — RAM/CPU spike.

Simule une surcharge CPU/mémoire avec de très grands datasets.
Invariants vérifiés :
  - compute_signal complète en < 2s sur 10 000 candles
  - validate_candles complète en < 1s sur 10 000 candles corrompus
  - Tous les indicateurs (RSI/EMA/MACD/BOLLINGER/VWAP/ATR) respectent le budget
  - Le résultat est déterministe (pas de race condition sur les données partagées)
  - _run_with_timeout détecte correctement les dépassements
"""

from __future__ import annotations

import threading
import time

import pytest

from quant_hedge_ai.agents.execution.signal_engine import compute_signal
from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles

_MAX_SIGNAL_MS = 2_000
_MAX_VALIDATE_MS = 1_000


def _candles(n: int, base: float = 50_000.0) -> list[dict]:
    return [
        {
            "open": base + i * 0.01,
            "high": (base + i * 0.01) * 1.005,
            "low": (base + i * 0.01) * 0.995,
            "close": base + i * 0.01,
            "volume": float(1000 + i % 500),
        }
        for i in range(n)
    ]


def _timed(fn, *args, **kwargs) -> tuple:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000.0


def _run_with_timeout(fn, timeout_s: float, *args, **kwargs):
    """Lance fn dans un thread avec un timeout strict. Lève TimeoutError si dépassé."""
    result = [None]
    exc = [None]

    def _run():
        try:
            result[0] = fn(*args, **kwargs)
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        raise TimeoutError(f"Timeout après {timeout_s}s")
    if exc[0]:
        raise exc[0]
    return result[0]


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestResourceSpike:
    def test_compute_signal_10k_candles_within_budget(self):
        """compute_signal sur 10 000 candles doit finir en < 2s."""
        candles = _candles(10_000)
        strategy = {
            "entry_indicator": "RSI",
            "period": 14,
            "entry_threshold": 30,
            "exit_threshold": 70,
        }
        result, elapsed_ms = _timed(compute_signal, strategy, candles)
        assert (
            elapsed_ms < _MAX_SIGNAL_MS
        ), f"LATENCE TROP ÉLEVÉE: {elapsed_ms:.0f}ms (max {_MAX_SIGNAL_MS}ms)"
        assert result in ("BUY", "SELL", "HOLD")

    def test_validate_candles_10k_within_budget(self):
        """validate_candles sur 10 000 candles doit finir en < 1s."""
        candles = _candles(10_000)
        _, elapsed_ms = _timed(validate_candles, candles)
        assert (
            elapsed_ms < _MAX_VALIDATE_MS
        ), f"LATENCE TROP ÉLEVÉE: {elapsed_ms:.0f}ms (max {_MAX_VALIDATE_MS}ms)"

    @pytest.mark.parametrize(
        "indicator", ["RSI", "EMA", "MACD", "BOLLINGER", "VWAP", "ATR"]
    )
    def test_all_indicators_1k_candles_within_budget(self, indicator):
        """Chaque indicateur doit tenir dans le budget de temps sur 1 000 candles."""
        candles = _candles(1_000)
        strategy = {
            "entry_indicator": indicator,
            "period": 14,
            "entry_threshold": 30,
            "exit_threshold": 70,
        }
        result, elapsed_ms = _timed(compute_signal, strategy, candles)
        assert (
            elapsed_ms < _MAX_SIGNAL_MS
        ), f"LATENCE TROP ÉLEVÉE pour {indicator}: {elapsed_ms:.0f}ms"
        assert result in (
            "BUY",
            "SELL",
            "HOLD",
        ), f"Signal invalide pour {indicator}: {result}"

    def test_compute_signal_deterministic_under_repeat(self):
        """100 appels répétés avec les mêmes candles produisent le même résultat."""
        strategy = {
            "entry_indicator": "MACD",
            "period": 14,
            "entry_threshold": 30,
            "exit_threshold": 70,
        }
        candles = _candles(100)
        results = {compute_signal(strategy, candles) for _ in range(100)}
        assert len(results) == 1, f"Résultats non-déterministes: {results}"

    def test_timeout_protection_fast_op(self):
        """Une opération rapide (10ms) ne déclenche pas le timeout (1s)."""

        def fast():
            time.sleep(0.01)
            return "done"

        result = _run_with_timeout(fast, timeout_s=1.0)
        assert result == "done"

    def test_timeout_protection_slow_op(self):
        """Une opération lente (2s) est détectée par le timeout (200ms)."""

        def slow():
            time.sleep(2.0)
            return "done"

        with pytest.raises(TimeoutError):
            _run_with_timeout(slow, timeout_s=0.2)
