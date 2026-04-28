"""Tests unitaires — retry_policy (retry_with_backoff + CircuitBreaker)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from quant_hedge_ai.agents.market.retry_policy import CircuitBreaker, retry_with_backoff

# ── retry_with_backoff ────────────────────────────────────────────────────────


class TestRetryWithBackoff:
    def test_success_first_try(self):
        fn = MagicMock(return_value=42)
        result = retry_with_backoff(fn, max_retries=3, base_delay=0.0, label="t")
        assert result == 42
        assert fn.call_count == 1

    def test_success_after_retries(self):
        fn = MagicMock(side_effect=[RuntimeError("fail"), RuntimeError("fail"), 99])
        with patch("time.sleep"):
            result = retry_with_backoff(fn, max_retries=3, base_delay=0.01, label="t")
        assert result == 99
        assert fn.call_count == 3

    def test_returns_none_after_all_retries_fail(self):
        fn = MagicMock(side_effect=RuntimeError("always fails"))
        with patch("time.sleep"):
            result = retry_with_backoff(fn, max_retries=3, base_delay=0.01, label="t")
        assert result is None
        assert fn.call_count == 4  # tentative initiale + 3 retries

    def test_max_retries_zero_no_retry(self):
        fn = MagicMock(side_effect=RuntimeError("fail"))
        with patch("time.sleep"):
            result = retry_with_backoff(fn, max_retries=0, base_delay=0.01, label="t")
        assert result is None
        assert fn.call_count == 1

    def test_jitter_does_not_break_execution(self):
        fn = MagicMock(return_value="ok")
        result = retry_with_backoff(
            fn, max_retries=2, base_delay=0.0, jitter=True, label="t"
        )
        assert result == "ok"

    def test_no_jitter_option(self):
        fn = MagicMock(side_effect=[RuntimeError(), "ok"])
        with patch("time.sleep") as mock_sleep:
            result = retry_with_backoff(
                fn, max_retries=2, base_delay=0.05, jitter=False, label="t"
            )
        assert result == "ok"
        mock_sleep.assert_called_once()

    def test_delay_capped_at_max_delay(self):
        fn = MagicMock(
            side_effect=[RuntimeError(), RuntimeError(), RuntimeError(), "ok"]
        )
        delays = []
        with patch("time.sleep", side_effect=lambda d: delays.append(d)):
            retry_with_backoff(
                fn,
                max_retries=3,
                base_delay=100.0,
                max_delay=5.0,
                jitter=False,
                label="t",
            )
        for d in delays:
            assert d <= 5.0 + 0.01  # léger epsilon


# ── CircuitBreaker ────────────────────────────────────────────────────────────


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=9999, label="test")
        assert cb.state.upper() == "CLOSED"
        assert cb.is_closed
        assert not cb.is_open

    def test_success_stays_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=9999, label="test")
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.is_closed

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=9999, label="test")
        for _ in range(3):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.is_open
        assert cb.state.upper() == "OPEN"

    def test_open_circuit_returns_none_without_calling_fn(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=9999, label="test")
        fn = MagicMock(side_effect=RuntimeError("fail"))
        cb.call(fn)
        cb.call(fn)
        assert cb.is_open

        fn2 = MagicMock(return_value="should_not_call")
        result = cb.call(fn2)
        assert result is None
        fn2.assert_not_called()

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05, label="test")
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        assert cb.is_open
        time.sleep(0.1)
        # Prochain appel → HALF_OPEN
        cb.call(lambda: "ok")
        assert cb.is_closed  # succès en HALF_OPEN → retour CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05, label="test")
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        time.sleep(0.1)
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))  # HALF_OPEN → OPEN
        assert cb.is_open

    def test_reset_closes_open_circuit(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=9999, label="test")
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        assert cb.is_open
        cb.reset()
        assert cb.is_closed

    def test_failure_count_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=9999, label="test")
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        cb.call(lambda: "ok")  # succès → reset compteur
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError()))
        # 2 nouveaux échecs seulement → doit rester fermé (seuil=3)
        assert cb.is_closed

    def test_label_in_logs(self, caplog):
        import logging

        cb = CircuitBreaker(
            failure_threshold=1, recovery_timeout=9999, label="MyService"
        )
        with caplog.at_level(logging.WARNING):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert "MyService" in caplog.text
