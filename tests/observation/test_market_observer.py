"""Pouls du marché MEXC (ADR-0016) — fonctions pures, aucun appel réseau."""

import gzip
import json
import time

from observation.market_observer import (
    append_records,
    build_record,
    day_file,
    prune_old_files,
    read_day,
    summarize_day,
)

_TS = 1_784_100_000.0  # 2026-07-15 ~07:20 UTC


def test_build_record_computes_spread_and_quote_volume():
    raw = {
        "last": 100.0,
        "bid": 99.9,
        "ask": 100.1,
        "quoteVolume": 5_000_000.0,
        "percentage": 2.5,
    }

    rec = build_record(_TS, "BTC/USDT", "spot", raw)

    assert rec["sym"] == "BTC/USDT"
    assert rec["mkt"] == "spot"
    assert abs(rec["sp"] - 0.1998) < 1e-4  # (100.1-99.9)/100.1*100
    assert rec["qv"] == 5_000_000.0
    assert rec["chg"] == 2.5


def test_build_record_falls_back_to_base_volume():
    raw = {"last": 2.0, "baseVolume": 1000.0}

    rec = build_record(_TS, "X/USDT", "swap", raw)

    assert rec["qv"] == 2000.0  # baseVolume × last
    assert rec["sp"] is None  # pas de bid/ask exploitables


def test_build_record_rejects_dead_ticker():
    assert build_record(_TS, "DEAD/USDT", "spot", {"last": 0}) is None
    assert build_record(_TS, "DEAD/USDT", "spot", {}) is None


def test_append_and_read_day_gzip_roundtrip(tmp_path):
    path = day_file(tmp_path, _TS)
    r1 = build_record(_TS, "BTC/USDT", "spot", {"last": 100.0, "quoteVolume": 1.0})
    r2 = build_record(
        _TS + 900, "BTC/USDT", "spot", {"last": 101.0, "quoteVolume": 2.0}
    )

    append_records(path, [r1])
    append_records(path, [r2])  # append gzip = membres successifs

    got = read_day(path)
    assert [g["last"] for g in got] == [100.0, 101.0]
    assert path.name == "market_pulse_2026-07-15.jsonl.gz"


def test_prune_old_files_respects_retention(tmp_path):
    old = tmp_path / "market_pulse_2026-05-01.jsonl.gz"
    recent = day_file(tmp_path, _TS)
    for p in (old, recent):
        with gzip.open(p, "wt") as fh:
            fh.write("{}\n")

    removed = prune_old_files(tmp_path, retention_days=45, now=_TS)

    assert removed == ["market_pulse_2026-05-01.jsonl.gz"]
    assert not old.exists()
    assert recent.exists()


def test_prune_ignores_foreign_files(tmp_path):
    keep = tmp_path / "market_pulse_notadate.jsonl.gz"
    with gzip.open(keep, "wt") as fh:
        fh.write("{}\n")

    assert prune_old_files(tmp_path, retention_days=1, now=_TS) == []
    assert keep.exists()


def test_snapshot_once_skips_write_when_disk_low(tmp_path, monkeypatch):
    """Garde-fou disque (VPS à 92% au moment de l'ADR-0016) : sous le seuil,
    aucune écriture, signalé dans le résumé — jamais un risque pour le moteur."""
    import observation.market_observer as mo

    monkeypatch.setenv("OBS_MIN_FREE_DISK_GB", "1.5")
    monkeypatch.setattr(mo, "free_disk_gb", lambda _p: 0.9)

    summary = mo.snapshot_once(tmp_path)

    assert summary["skipped_disk"] is True
    assert summary["bytes_written"] == 0
    assert list(tmp_path.glob("*.gz")) == []


def test_snapshot_once_writes_all_markets(tmp_path, monkeypatch):
    import observation.market_observer as mo

    class _FakeClient:
        def __init__(self, market):
            self._market = market

        def fetch_tickers(self):
            if self._market == "spot":
                return {
                    "BTC/USDT": {"last": 100.0, "quoteVolume": 1e6},
                    "DEAD/USDT": {"last": 0},  # ignoré
                }
            return {"BTC/USDT:USDT": {"last": 100.5, "quoteVolume": 2e6}}

    monkeypatch.setattr(mo, "free_disk_gb", lambda _p: 50.0)
    monkeypatch.setattr(mo, "_make_client", lambda market: _FakeClient(market))

    summary = mo.snapshot_once(tmp_path)

    assert summary["counts"] == {"spot": 1, "swap": 1}
    assert summary["bytes_written"] > 0
    records = read_day(day_file(tmp_path, time.time()))
    assert {r["mkt"] for r in records} == {"spot", "swap"}
    # Sidecar top-K (ADR-0017) : dernier tick spot, écrit atomiquement
    latest = json.loads((tmp_path / "latest_tick.json").read_text(encoding="utf-8"))
    assert "BTC/USDT" in latest["pairs"]
    assert "BTC/USDT:USDT" not in latest["pairs"]  # spot uniquement


def test_summarize_day_reads_back(tmp_path):
    path = day_file(tmp_path, _TS)
    recs = [
        build_record(
            _TS,
            "BTC/USDT",
            "spot",
            {"last": 100.0, "quoteVolume": 1e6, "percentage": 1.0},
        ),
        build_record(
            _TS,
            "PUMP/USDT",
            "swap",
            {"last": 1.0, "quoteVolume": 5e4, "percentage": 42.0},
        ),
    ]
    append_records(path, recs)

    text = summarize_day(tmp_path, "2026-07-15")

    assert "2 observations" in text
    assert "PUMP/USDT" in text  # plus forte variation en tête
    data = json.dumps(recs)  # sanity : les records restent sérialisables
    assert "PUMP" in data
