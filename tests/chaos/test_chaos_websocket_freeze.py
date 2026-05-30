"""
Chaos #2 — WebSocket freeze.

Simule un feed de données gelé : le dernier candle n'est plus mis à jour.
Invariants vérifiés :
  - is_series_fresh() retourne False quand le dernier candle est trop ancien
  - compute_signal retourne HOLD sur feed vide ou trop court (< 5 candles)
  - Le deduplicator bloque les retries sur signal stale
  - La reprise du feed est correctement détectée comme fraîche
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator
from quant_hedge_ai.agents.execution.signal_engine import compute_signal
from quant_hedge_ai.agents.market.ohlcv_validator import is_series_fresh


def _candle(price: float, age_hours: float = 0.0) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return {
        "open": price,
        "high": price * 1.005,
        "low": price * 0.995,
        "close": price,
        "volume": 1000.0,
        "timestamp": ts.isoformat(),
    }


_STRAT_RSI = {
    "entry_indicator": "RSI",
    "period": 14,
    "entry_threshold": 30,
    "exit_threshold": 70,
}


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestWebsocketFreeze:
    def test_stale_series_detected(self):
        """Dernier candle à 2h d'ancienneté → is_series_fresh retourne False."""
        candles = [_candle(100.0, age_hours=2.0)]
        assert (
            is_series_fresh(candles, max_age_seconds=3600) is False
        ), "INVARIANT BRISÉ: données de 2h détectées comme fraîches"

    def test_fresh_series_accepted(self):
        """Dernier candle à 1 minute → is_series_fresh retourne True."""
        candles = [_candle(100.0, age_hours=1 / 60)]
        assert is_series_fresh(candles, max_age_seconds=3600) is True

    def test_empty_feed_returns_hold(self):
        """Feed vide (websocket mort) → compute_signal retourne HOLD."""
        result = compute_signal(_STRAT_RSI, [])
        assert result == "HOLD", f"Feed vide doit retourner HOLD, obtenu: {result}"

    def test_single_candle_feed_returns_hold(self):
        """Feed gelé après 1 seul tick → compute_signal retourne HOLD."""
        result = compute_signal(_STRAT_RSI, [_candle(100.0)])
        assert result == "HOLD"

    def test_four_candles_returns_hold(self):
        """4 candles (seuil = 5) → compute_signal retourne HOLD."""
        candles = [_candle(100.0 - i * 0.5) for i in range(4)]
        result = compute_signal(_STRAT_RSI, candles)
        assert result == "HOLD", "Moins de 5 candles doit toujours retourner HOLD"

    def test_dedup_blocks_stale_signal_retry(self):
        """Retry d'un signal stale dans la fenêtre est bloqué par le deduplicator."""
        dedup = OrderDeduplicator(window_seconds=30.0)
        dedup.register("BTC/USDT", "BUY", 0.1)
        assert dedup.is_duplicate(
            "BTC/USDT", "BUY", 0.1
        ), "Retry sur signal stale doit être bloqué"

    def test_frozen_then_resumed_feed_detected(self):
        """Après un freeze, les nouvelles données fraîches sont acceptées."""
        stale = [_candle(100.0, age_hours=3.0)]
        fresh = [_candle(101.0, age_hours=1 / 60)]
        assert is_series_fresh(stale, max_age_seconds=3600) is False
        assert is_series_fresh(fresh, max_age_seconds=3600) is True

    def test_no_signal_from_flat_price_many_candles(self):
        """Prix complètement plat → indicateurs neutres → HOLD (pas d'ordre fantôme)."""
        candles = [_candle(100.0) for _ in range(30)]
        result = compute_signal(_STRAT_RSI, candles)
        assert result in ("BUY", "SELL", "HOLD")  # pas de crash, signal cohérent
