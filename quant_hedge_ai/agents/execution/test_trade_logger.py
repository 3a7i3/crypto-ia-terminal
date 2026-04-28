"""Tests unitaires — TradeLogger."""

from __future__ import annotations

import time

import pytest

from quant_hedge_ai.agents.execution.trade_logger import TradeLogger


@pytest.fixture
def logger(tmp_path):
    return TradeLogger(db_path=str(tmp_path / "trades.sqlite"))


# ── log ───────────────────────────────────────────────────────────────────────


class TestTradeLoggerLog:
    def test_log_basic_order(self, logger):
        logger.log(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 0.1, "mode": "paper"}
        )
        trades = logger.recent_trades(10)
        assert len(trades) == 1
        assert trades[0]["symbol"] == "BTC/USDT"
        assert trades[0]["action"] == "BUY"

    def test_log_sets_status_ok_by_default(self, logger):
        logger.log(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 0.1, "mode": "paper"}
        )
        trades = logger.recent_trades(1)
        assert trades[0]["status"] == "ok"

    def test_log_custom_status(self, logger):
        logger.log(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 0.1, "mode": "live_failed"},
            status="error",
        )
        trades = logger.recent_trades(1)
        assert trades[0]["status"] == "error"

    def test_log_extracts_pnl(self, logger):
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": 5.5,
            }
        )
        trades = logger.recent_trades(1)
        assert trades[0]["pnl"] == pytest.approx(5.5)

    def test_log_extracts_price(self, logger):
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "BUY",
                "size": 0.1,
                "mode": "paper",
                "price": 45000.0,
            }
        )
        trades = logger.recent_trades(1)
        assert trades[0]["price"] == pytest.approx(45000.0)

    def test_log_extracts_order_id(self, logger):
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "BUY",
                "size": 0.1,
                "mode": "live",
                "id": "order123",
            }
        )
        trades = logger.recent_trades(1)
        assert trades[0]["order_id"] == "order123"

    def test_log_multiple_orders(self, logger):
        for i in range(5):
            logger.log(
                {
                    "symbol": "BTC/USDT",
                    "action": "BUY",
                    "size": float(i),
                    "mode": "paper",
                }
            )
        trades = logger.recent_trades(10)
        assert len(trades) == 5

    def test_log_does_not_raise_on_missing_fields(self, logger):
        logger.log({})  # ordre minimal vide
        trades = logger.recent_trades(1)
        assert len(trades) == 1

    def test_log_normalizes_action_uppercase(self, logger):
        logger.log(
            {"symbol": "ETH/USDT", "action": "sell", "size": 0.5, "mode": "paper"}
        )
        trades = logger.recent_trades(1)
        assert trades[0]["action"] == "SELL"


# ── log_rejected ──────────────────────────────────────────────────────────────


class TestTradeLoggerLogRejected:
    def test_log_rejected_sets_status(self, logger):
        logger.log_rejected("BTC/USDT", "BUY", 0.1, "duplicate within 30s")
        trades = logger.recent_trades(1)
        assert trades[0]["status"] == "rejected"
        assert trades[0]["mode"] == "rejected"

    def test_log_rejected_stores_reason(self, logger):
        logger.log_rejected("BTC/USDT", "BUY", 0.1, "order too large")
        trades = logger.recent_trades(1)
        assert trades[0]["error"] == "order too large"


# ── recent_trades ─────────────────────────────────────────────────────────────


class TestRecentTrades:
    def test_returns_newest_first(self, logger):
        logger.log(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 1.0, "mode": "paper"}
        )
        time.sleep(0.01)
        logger.log(
            {"symbol": "ETH/USDT", "action": "BUY", "size": 2.0, "mode": "paper"}
        )
        trades = logger.recent_trades(2)
        assert trades[0]["symbol"] == "ETH/USDT"
        assert trades[1]["symbol"] == "BTC/USDT"

    def test_limit_respected(self, logger):
        for i in range(10):
            logger.log(
                {
                    "symbol": "BTC/USDT",
                    "action": "BUY",
                    "size": float(i),
                    "mode": "paper",
                }
            )
        trades = logger.recent_trades(3)
        assert len(trades) == 3

    def test_empty_db_returns_empty_list(self, logger):
        assert logger.recent_trades(10) == []


# ── session_pnl ───────────────────────────────────────────────────────────────


class TestSessionPnl:
    def test_sum_of_pnl(self, logger):
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": 10.0,
            }
        )
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": -5.0,
            }
        )
        pnl = logger.session_pnl(since_ts=time.time() - 60)
        assert pnl == pytest.approx(5.0)

    def test_excludes_old_trades(self, logger):
        # On log manuellement un trade "vieux" en manipulant le timestamp
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": 100.0,
            }
        )
        pnl = logger.session_pnl(since_ts=time.time() + 1)  # futur → exclut tout
        assert pnl == pytest.approx(0.0)

    def test_no_pnl_returns_zero(self, logger):
        logger.log(
            {"symbol": "BTC/USDT", "action": "BUY", "size": 0.1, "mode": "paper"}
        )
        pnl = logger.session_pnl(since_ts=time.time() - 60)
        assert pnl == pytest.approx(0.0)

    def test_default_since_last_24h(self, logger):
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": 7.5,
            }
        )
        pnl = logger.session_pnl()  # défaut = dernières 24h
        assert pnl == pytest.approx(7.5)


# ── stats ─────────────────────────────────────────────────────────────────────


class TestStats:
    def test_empty_stats(self, logger):
        stats = logger.stats()
        assert stats["total_trades"] == 0
        assert stats["pnl_sum"] == pytest.approx(0.0)

    def test_total_trades_counted(self, logger):
        for _ in range(3):
            logger.log(
                {"symbol": "BTC/USDT", "action": "BUY", "size": 0.1, "mode": "paper"}
            )
        assert logger.stats()["total_trades"] == 3

    def test_rejected_counted(self, logger):
        logger.log_rejected("BTC/USDT", "BUY", 0.1, "too large")
        logger.log_rejected("BTC/USDT", "BUY", 0.1, "duplicate")
        assert logger.stats()["rejected"] == 2

    def test_win_rate_calculation(self, logger):
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": 10.0,
            }
        )
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": -5.0,
            }
        )
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": 3.0,
            }
        )
        stats = logger.stats()
        assert stats["win_rate"] == pytest.approx(2 / 3, rel=1e-3)

    def test_pnl_sum(self, logger):
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": 10.0,
            }
        )
        logger.log(
            {
                "symbol": "BTC/USDT",
                "action": "SELL",
                "size": 0.1,
                "mode": "paper",
                "pnl": -3.0,
            }
        )
        assert logger.stats()["pnl_sum"] == pytest.approx(7.0)

    def test_thread_safety(self, logger):
        import threading

        errors = []

        def _log():
            try:
                for _ in range(20):
                    logger.log(
                        {
                            "symbol": "BTC/USDT",
                            "action": "BUY",
                            "size": 0.1,
                            "mode": "paper",
                        }
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_log) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert logger.stats()["total_trades"] == 100
