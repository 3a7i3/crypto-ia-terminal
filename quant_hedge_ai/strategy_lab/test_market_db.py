"""Tests unitaires — MarketDatabase (SQLite OHLCV store)."""

from __future__ import annotations

import time

import pytest

from quant_hedge_ai.strategy_lab.market_db import MarketDatabase

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_candle(symbol: str, ts: str, close: float, source: str = "synthetic") -> dict:
    return {
        "symbol": symbol,
        "timestamp": ts,
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": 1000.0,
        "source": source,
    }


def _make_snapshot(symbols=("BTCUSDT",), n=5, base_ts="2024-01-01T00:00:00+00:00"):
    from datetime import datetime, timedelta

    dt0 = datetime.fromisoformat(base_ts)
    history = {}
    for sym in symbols:
        seed = 30_000.0 if "BTC" in sym else 2_000.0
        candles = []
        for i in range(n):
            ts = (dt0 + timedelta(hours=i)).isoformat()
            candles.append(_make_candle(sym, ts, seed + i * 10))
        history[sym] = candles
    snapshot_candles = [h[-1] for h in history.values()]
    return {"candles": snapshot_candles, "history": history}


@pytest.fixture
def db(tmp_path):
    return MarketDatabase(db_path=str(tmp_path / "test.sqlite"), max_age_days=30)


# ── Initialisation ────────────────────────────────────────────────────────────


class TestMarketDatabaseInit:
    def test_db_file_created(self, tmp_path):
        path = tmp_path / "sub" / "db.sqlite"
        MarketDatabase(db_path=str(path))
        assert path.exists()

    def test_parent_dirs_created(self, tmp_path):
        path = tmp_path / "a" / "b" / "c" / "db.sqlite"
        MarketDatabase(db_path=str(path))
        assert path.parent.exists()

    def test_latest_snapshot_empty_on_init(self, db):
        assert db.get_latest_snapshot() == {}

    def test_get_history_empty_on_init(self, db):
        assert db.get_history("BTCUSDT") == []

    def test_double_init_same_path_is_idempotent(self, tmp_path):
        path = str(tmp_path / "dup.sqlite")
        db1 = MarketDatabase(db_path=path)
        db2 = MarketDatabase(db_path=path)
        snap = _make_snapshot(n=3)
        db1.save_snapshot(snap)
        assert len(db2.get_history("BTCUSDT")) == 3


# ── save_snapshot ─────────────────────────────────────────────────────────────


class TestSaveSnapshot:
    def test_returns_inserted_count(self, db):
        snap = _make_snapshot(n=5)
        inserted = db.save_snapshot(snap)
        assert inserted == 5

    def test_empty_history_returns_zero(self, db):
        assert db.save_snapshot({"candles": [], "history": {}}) == 0

    def test_snapshot_without_history_key_returns_zero(self, db):
        assert db.save_snapshot({}) == 0

    def test_duplicate_candles_not_inserted_twice(self, db):
        snap = _make_snapshot(n=4)
        db.save_snapshot(snap)
        inserted2 = db.save_snapshot(snap)
        assert inserted2 == 0

    def test_updates_latest_snapshot_in_memory(self, db):
        snap = _make_snapshot(n=2)
        db.save_snapshot(snap)
        assert db.get_latest_snapshot() is snap

    def test_multiple_symbols_all_saved(self, db):
        snap = _make_snapshot(symbols=("BTCUSDT", "ETHUSDT"), n=3)
        inserted = db.save_snapshot(snap)
        assert inserted == 6

    def test_new_candles_in_second_snapshot_are_inserted(self, db):
        snap1 = _make_snapshot(n=3, base_ts="2024-01-01T00:00:00+00:00")
        snap2 = _make_snapshot(n=3, base_ts="2024-01-01T03:00:00+00:00")
        db.save_snapshot(snap1)
        inserted2 = db.save_snapshot(snap2)
        assert inserted2 == 3

    def test_mixed_sources_saved(self, db):
        ts1 = "2024-03-01T00:00:00+00:00"
        ts2 = "2024-03-01T01:00:00+00:00"
        candle_synth = _make_candle("BTCUSDT", ts1, 30000.0, source="synthetic")
        candle_real = _make_candle("BTCUSDT", ts2, 31000.0, source="ccxt_live")
        snap = {
            "candles": [candle_real],
            "history": {"BTCUSDT": [candle_synth, candle_real]},
        }
        inserted = db.save_snapshot(snap)
        assert inserted == 2


# ── get_history ───────────────────────────────────────────────────────────────


class TestGetHistory:
    def test_returns_correct_symbol_only(self, db):
        snap = _make_snapshot(symbols=("BTCUSDT", "ETHUSDT"), n=5)
        db.save_snapshot(snap)
        btc = db.get_history("BTCUSDT")
        eth = db.get_history("ETHUSDT")
        assert all(c["symbol"] == "BTCUSDT" for c in btc)
        assert all(c["symbol"] == "ETHUSDT" for c in eth)

    def test_returns_in_chronological_order(self, db):
        snap = _make_snapshot(n=10)
        db.save_snapshot(snap)
        history = db.get_history("BTCUSDT")
        timestamps = [c["timestamp"] for c in history]
        assert timestamps == sorted(timestamps)

    def test_limit_respected(self, db):
        snap = _make_snapshot(n=20)
        db.save_snapshot(snap)
        result = db.get_history("BTCUSDT", limit=5)
        assert len(result) == 5

    def test_returns_all_ohlcv_keys(self, db):
        snap = _make_snapshot(n=1)
        db.save_snapshot(snap)
        candle = db.get_history("BTCUSDT")[0]
        for key in (
            "symbol",
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "source",
        ):
            assert key in candle

    def test_unknown_symbol_returns_empty(self, db):
        snap = _make_snapshot(n=3)
        db.save_snapshot(snap)
        assert db.get_history("XYZUSDT") == []

    def test_default_limit_200(self, db):
        snap = _make_snapshot(n=10)
        db.save_snapshot(snap)
        result = db.get_history("BTCUSDT")
        assert len(result) == 10

    def test_returns_latest_n_when_more_available(self, db):
        snap1 = _make_snapshot(n=15, base_ts="2024-01-01T00:00:00+00:00")
        db.save_snapshot(snap1)
        result = db.get_history("BTCUSDT", limit=5)
        assert len(result) == 5
        assert result[-1]["timestamp"] == snap1["history"]["BTCUSDT"][-1]["timestamp"]


# ── get_stats ─────────────────────────────────────────────────────────────────


class TestGetStats:
    def test_empty_db_stats(self, db):
        stats = db.get_stats()
        assert stats["total_candles"] == 0
        assert stats["symbols"] == 0
        assert stats["real_ratio"] == 0.0
        assert stats["synthetic_ratio"] == 0.0
        assert stats["oldest"] is None
        assert stats["newest"] is None

    def test_total_candles_after_insert(self, db):
        db.save_snapshot(_make_snapshot(n=7))
        stats = db.get_stats()
        assert stats["total_candles"] == 7

    def test_symbols_count(self, db):
        db.save_snapshot(_make_snapshot(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"), n=3))
        stats = db.get_stats()
        assert stats["symbols"] == 3

    def test_synthetic_ratio_is_one_when_all_synthetic(self, db):
        db.save_snapshot(_make_snapshot(n=5))
        stats = db.get_stats()
        assert stats["synthetic_ratio"] == 1.0
        assert stats["real_ratio"] == 0.0

    def test_sources_dict_present(self, db):
        db.save_snapshot(_make_snapshot(n=3))
        stats = db.get_stats()
        assert isinstance(stats["sources"], dict)
        assert "synthetic" in stats["sources"]

    def test_oldest_and_newest_set(self, db):
        db.save_snapshot(_make_snapshot(n=5, base_ts="2024-06-01T00:00:00+00:00"))
        stats = db.get_stats()
        assert stats["oldest"] is not None
        assert stats["newest"] is not None
        assert stats["oldest"] < stats["newest"]

    def test_real_ratio_after_mixed_sources(self, db):
        ts_synth = "2024-01-01T00:00:00+00:00"
        ts_real = "2024-01-01T01:00:00+00:00"
        snap = {
            "candles": [],
            "history": {
                "BTCUSDT": [
                    _make_candle("BTCUSDT", ts_synth, 30000.0, "synthetic"),
                    _make_candle("BTCUSDT", ts_real, 31000.0, "ccxt_live"),
                ]
            },
        }
        db.save_snapshot(snap)
        stats = db.get_stats()
        assert stats["real_ratio"] == 0.5
        assert stats["synthetic_ratio"] == 0.5


# ── _purge_old ────────────────────────────────────────────────────────────────


class TestPurgeOld:
    def test_purge_removes_old_rows(self, tmp_path, monkeypatch):
        db = MarketDatabase(db_path=str(tmp_path / "purge.sqlite"), max_age_days=1)
        snap = _make_snapshot(n=5)
        db.save_snapshot(snap)
        assert db.get_stats()["total_candles"] == 5

        old_time = time.time() - 2 * 86400
        monkeypatch.setattr(time, "time", lambda: old_time)
        db2 = MarketDatabase(db_path=str(tmp_path / "purge2.sqlite"), max_age_days=0)
        db2.save_snapshot(snap)

        db2._max_age_days = 0
        db2._purge_old()
        assert db2.get_stats()["total_candles"] == 5

    def test_purge_disabled_when_max_age_zero(self, tmp_path):
        db = MarketDatabase(db_path=str(tmp_path / "nopurge.sqlite"), max_age_days=0)
        db.save_snapshot(_make_snapshot(n=3))
        db._purge_old()
        assert db.get_stats()["total_candles"] == 3

    def test_purge_triggered_at_every_10_saves(self, tmp_path, monkeypatch):
        purge_calls = []
        db = MarketDatabase(db_path=str(tmp_path / "trigger.sqlite"), max_age_days=1)
        original_purge = db._purge_old

        def counting_purge():
            purge_calls.append(1)
            original_purge()

        monkeypatch.setattr(db, "_purge_old", counting_purge)

        for i in range(10):
            from datetime import datetime, timedelta
            from datetime import timezone as tz

            ts = (datetime(2024, 1, 1, tzinfo=tz.utc) + timedelta(hours=i)).isoformat()
            unique_snap = {
                "candles": [],
                "history": {"BTCUSDT": [_make_candle("BTCUSDT", ts, 30000.0 + i)]},
            }
            db.save_snapshot(unique_snap)

        assert len(purge_calls) == 1
