"""
Chaos #5 — Stale signal.

Injecte un signal avec TTL expiré.
Invariants vérifiés :
  - Un SignalResult avec timestamp ancien (> TTL) est détectable comme stale
  - is_series_fresh() rejette les séries OHLCV de plus de 1h
  - compute_signal reste stable sur candles avec vieux timestamps (pas de crash)
  - Boundary conditions : juste avant / après le TTL
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from quant_hedge_ai.agents.execution.live_signal_engine import SignalResult
from quant_hedge_ai.agents.execution.signal_engine import compute_signal
from quant_hedge_ai.agents.market.ohlcv_validator import is_series_fresh

_SIGNAL_TTL_S = 60.0  # TTL standard : 1 minute


def _is_signal_stale(signal: SignalResult, ttl_s: float = _SIGNAL_TTL_S) -> bool:
    """Détecte si un signal a dépassé son TTL — logique à câbler dans l'appelant."""
    return (time.time() - signal.timestamp) > ttl_s


def _candle_with_ts(price: float, age_hours: float) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return {
        "open": price,
        "high": price * 1.005,
        "low": price * 0.995,
        "close": price,
        "volume": 1000.0,
        "timestamp": ts.isoformat(),
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestStaleSignal:
    def test_fresh_signal_not_stale(self):
        """Signal créé il y a < 60s → frais."""
        sig = SignalResult(symbol="BTC/USDT", score=80, signal="BUY")
        assert not _is_signal_stale(sig), "Signal récent ne doit pas être stale"

    def test_old_signal_detected_as_stale(self):
        """Signal créé il y a 2 min → stale."""
        sig = SignalResult(
            symbol="BTC/USDT",
            score=80,
            signal="BUY",
            timestamp=time.time() - 120.0,
        )
        assert _is_signal_stale(
            sig, ttl_s=60.0
        ), "INVARIANT BRISÉ: signal de 2 min détecté comme frais"

    def test_ttl_boundary_fresh_side(self):
        """Signal à 59s → encore frais (juste avant la frontière TTL)."""
        sig = SignalResult(
            symbol="X",
            score=50,
            signal="HOLD",
            timestamp=time.time() - 59.0,
        )
        assert not _is_signal_stale(sig, ttl_s=60.0), "Signal à 59s doit être frais"

    def test_ttl_boundary_stale_side(self):
        """Signal à 61s → stale (juste après la frontière TTL)."""
        sig = SignalResult(
            symbol="X",
            score=50,
            signal="HOLD",
            timestamp=time.time() - 61.0,
        )
        assert _is_signal_stale(sig, ttl_s=60.0), "Signal à 61s doit être stale"

    def test_stale_ohlcv_series_rejected(self):
        """Série OHLCV dont le dernier candle a 2h → is_series_fresh False."""
        candles = [_candle_with_ts(100.0, age_hours=2.0)]
        assert (
            is_series_fresh(candles, max_age_seconds=3600) is False
        ), "INVARIANT BRISÉ: données de 2h acceptées comme fraîches"

    def test_compute_signal_no_crash_on_candles_with_old_timestamps(self):
        """compute_signal stable sur candles avec vieux timestamps (pas de crash)."""
        candles = [_candle_with_ts(100.0 - i * 0.5, age_hours=3.0) for i in range(20)]
        try:
            result = compute_signal(
                {
                    "entry_indicator": "RSI",
                    "period": 14,
                    "entry_threshold": 30,
                    "exit_threshold": 70,
                },
                candles,
            )
        except Exception as exc:
            pytest.fail(f"CRASH sur candles avec vieux timestamps: {exc}")
        assert result in ("BUY", "SELL", "HOLD"), f"Signal invalide: {result}"

    def test_stale_signal_actionable_flag_correct(self):
        """Un signal BUY stale a bien actionable=True — la fraîcheur est séparée."""
        sig = SignalResult(
            symbol="BTC/USDT",
            score=80,
            signal="BUY",
            timestamp=time.time() - 120.0,
        )
        # actionable reflète le contenu du signal, pas sa fraîcheur
        assert sig.actionable is True
        # La fraîcheur est vérifiée séparément par l'appelant
        assert _is_signal_stale(
            sig
        ), "L'appelant doit détecter la fraîcheur avant d'agir"

    def test_hold_signal_not_actionable_regardless_of_freshness(self):
        """Un signal HOLD n'est pas actionable, qu'il soit frais ou stale."""
        fresh = SignalResult(symbol="X", score=50, signal="HOLD")
        stale = SignalResult(
            symbol="X", score=50, signal="HOLD", timestamp=time.time() - 120.0
        )
        assert not fresh.actionable
        assert not stale.actionable
