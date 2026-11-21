import json
import sqlite3
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from observability.derivatives_positioning import PositioningPolicy, PositioningStore, StorageError
from observability.derivatives_positioning.migrations import LATEST_VERSION
from tests.derivatives_positioning.support import T0, ms, obs_a, obs_b, without_source_time

REPO = Path(__file__).resolve().parents[2]
NOW = ms(T0) + 5_000


def open_store(path, **kw):
    kw.setdefault("now_ms", lambda: NOW)
    return PositioningStore(path, **kw)


def count(store):
    return store.status()["observations"]


# -- proof 1: empty start, write, read back with metadata ---------------------------------
def test_empty_start_write_and_read_back_with_metadata(tmp_path):
    with open_store(tmp_path) as s:
        st = s.status()
        assert st["observations"] == 0 and st["schema_versions"] == [LATEST_VERSION]
        assert s.latest("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=NOW)["reason"] == "NO_OBSERVATION"
        r = s.ingest(obs_a())
        assert r.status == "INSERTED" and r.seq == 1
        got = s.latest("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=NOW)["observation"]
    assert got["source_time_utc"] == "2026-11-21T12:00:00.000Z"
    assert got["received_at_utc"] == "2026-11-21T12:00:01.000Z"
    assert got["time_basis"] == "SOURCE" and got["lateness"] == "ON_TIME" and got["receipt_latency_ms"] == 1000
    assert got["freshness"]["status"] == "FRESH" and got["freshness"]["age_ms"] == 5000
    assert got["units"] == {"prices": "USDT", "open_interest": "CONTRACTS", "contract_size_base": "0.0001",
                            "funding_interval_s": 28800, "funding_rate": "FRACTION_PER_INTERVAL"}
    assert got["provenance"]["source"] == "synthetic:exchange_a/ticker"
    assert got["provenance"]["collector_run_id"] == "run-1"
    assert got["measures"]["mark_price"]["value"] == "65000.5"
    assert got["unavailable_fields"] == []
    d = got["derived"]
    assert d["premium_to_index"]["status"] == "AVAILABLE" and d["basis_vs_spot"]["status"] == "AVAILABLE"
    assert d["premium_to_index"]["bps"] != d["basis_vs_spot"]["bps"]  # premium vs index is not basis vs spot
    assert d["basis_vs_spot"]["against"] == {"venue": "exchange_a", "native_symbol": "BTCUSDT"}
    assert d["open_interest_notional"]["notional_quote"] == "8125062.50000000"  # 1250000 * 0.0001 * 65000.5
    assert d["funding"]["rate_8h_equivalent"] == "0.0001000000"


# -- proof 2: replay is idempotent; two platforms with different units -----------------------
def test_reinjection_is_idempotent_even_with_a_later_receipt(tmp_path):
    with open_store(tmp_path) as s:
        assert s.ingest(obs_a()).status == "INSERTED"
        assert s.ingest(obs_a()).status == "DUPLICATE"
        assert s.ingest(obs_a(received_delay_s=900, run="retry-7")).status == "DUPLICATE"
        assert count(s) == 1
        # the stored receipt is the first one
        got = s.latest("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=NOW)["observation"]
        assert got["received_at_utc"] == "2026-11-21T12:00:01.000Z"


def test_two_platforms_keep_native_units_and_flag_unavailable_comparisons(tmp_path):
    with open_store(tmp_path) as s:
        assert s.ingest_batch([obs_a(), obs_b()]).ok
        cmp = s.compare([("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR"),
                         ("exchange_b", "PF_XBTUSD", "PERPETUAL_LINEAR")], as_of_ms=NOW)
    a, b = (leg["observation"] for leg in cmp["legs"])
    assert a["measures"]["open_interest"]["value"] == "1250000" and a["units"]["open_interest"] == "CONTRACTS"
    assert b["measures"]["open_interest"]["value"] == "125.5" and b["units"]["open_interest"] == "BASE"
    assert a["measures"]["funding_rate"]["value"] == "0.0001" and b["measures"]["funding_rate"]["value"] == "-0.00002"
    pair = cmp["pairs"][0]
    assert pair["open_interest"] == {"status": "NOT_AVAILABLE", "reason": "OPEN_INTEREST_UNITS_DIFFER",
                                     "units": ["CONTRACTS", "BASE"]}
    assert pair["funding"]["status"] == "NOT_AVAILABLE"
    assert pair["funding"]["reason"] == "FUNDING_INTERVALS_DIFFER" and pair["funding"]["intervals_s"] == [28800, 3600]
    assert b["unavailable_fields"] == [{"field": "spot_reference", "reason": "SPOT_REFERENCE_NOT_QUALIFIED"}]
    assert b["derived"]["basis_vs_spot"]["reason"] == "SPOT_REFERENCE_NOT_QUALIFIED_OR_MISSING"
    assert b["derived"]["premium_to_index"]["status"] == "AVAILABLE"


def test_identity_without_source_time_is_idempotent_and_lateness_undetermined(tmp_path):
    with open_store(tmp_path) as s:
        first = without_source_time(obs_a(), received=T0)
        assert s.ingest(first).status == "INSERTED"
        assert s.ingest(without_source_time(obs_a(), received=T0 + timedelta(minutes=3))).status == "DUPLICATE"
        got = s.latest("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=NOW)["observation"]
    assert got["time_basis"] == "RECEIPT" and got["lateness"] == "UNDETERMINED" and got["receipt_latency_ms"] is None


# -- conflicts and late observations ------------------------------------------------------
def test_conflict_keeps_original_and_retries_do_not_grow_the_journal(tmp_path):
    with open_store(tmp_path) as s:
        s.ingest(obs_a())
        for _ in range(5):
            r = s.ingest(obs_a(oi="9999999"))
            assert r.status == "CONFLICT" and r.code == "CONTENT_DIFFERS_ORIGINAL_KEPT"
        s.ingest(obs_a(oi="8888888"))
        st = s.status()
        for _ in range(200):
            s.ingest(obs_a(oi="9999999"))
        st2 = s.status()
        got = s.latest("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=NOW)["observation"]
    assert st["observations"] == 1
    assert st["conflicts"] == {"distinct": 2, "attempts": 6}
    assert st2["conflicts"] == {"distinct": 2, "attempts": 206}
    assert got["measures"]["open_interest"]["value"] == "1250000"


def test_late_and_out_of_order_observations_are_accepted_and_flagged(tmp_path):
    policy = PositioningPolicy(late_after_ms=120_000)
    with open_store(tmp_path, policy=policy) as s:
        s.ingest(obs_a(T0))
        r = s.ingest(obs_a(T0 - timedelta(minutes=10), received_delay_s=700))
        assert r.status == "INSERTED" and r.out_of_order is True
        h = s.history("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", ms(T0) - 3_600_000, ms(T0))
    late = h["observations"][0]
    assert late["lateness"] == "LATE" and late["out_of_order_at_ingest"] is True
    assert h["observations"][1]["lateness"] == "ON_TIME"
    assert h["coverage"]["late"] == 1
    # threshold is configuration, not data: a looser policy re-reads the same row as on time
    with open_store(tmp_path, policy=PositioningPolicy(late_after_ms=800_000)) as s:
        h = s.history("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", ms(T0) - 3_600_000, ms(T0))
    assert h["observations"][0]["lateness"] == "ON_TIME"


# -- proof 4: write refusal ----------------------------------------------------------------
def test_disk_full_is_observable_and_history_stays_consistent(tmp_path):
    with open_store(tmp_path) as s:
        assert s.ingest(obs_a()).status == "INSERTED"
        s.checkpoint()
        pages = s._conn.execute("PRAGMA page_count").fetchone()[0]
        s._conn.execute("PRAGMA max_page_count=%d" % pages)  # simulate a full volume
        big = [obs_a(T0 + timedelta(seconds=i), oi=str(1_000_000 + i)) for i in range(1, 400)]
        batch = s.ingest_batch(big)
        assert not batch.ok and batch.code == "STORAGE_FULL"
        assert {r.status for r in batch.results} == {"NOT_WRITTEN"}
        assert count(s) == 1  # all-or-nothing: no partial batch
        got = s.latest("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=NOW)["observation"]
        assert got["measures"]["open_interest"]["value"] == "1250000"
        assert s._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_read_only_store_refuses_writes_and_still_reads(tmp_path):
    with open_store(tmp_path) as s:
        s.ingest(obs_a())
    with open_store(tmp_path, read_only=True) as ro:
        r = ro.ingest(obs_a(T0 + timedelta(minutes=1)))
        assert r.status == "NOT_WRITTEN" and r.code == "STORAGE_READ_ONLY"
        assert count(ro) == 1


def test_sqlite_readonly_error_is_mapped(tmp_path):
    with open_store(tmp_path) as s:
        s.ingest(obs_a())
        s._conn.execute("PRAGMA query_only=ON")  # the engine itself refuses the write
        r = s.ingest(obs_a(T0 + timedelta(minutes=1)))
        assert r.status == "NOT_WRITTEN" and r.code == "STORAGE_READ_ONLY"
        s._conn.execute("PRAGMA query_only=OFF")
        assert count(s) == 1


def test_missing_volume_is_an_explicit_error(tmp_path):
    with pytest.raises(StorageError) as exc:
        open_store(tmp_path / "absent")
    assert exc.value.code == "STORAGE_DIRECTORY_MISSING"
    (tmp_path / "file").write_text("x")
    with pytest.raises(StorageError) as exc:
        open_store(tmp_path / "file")
    assert exc.value.code == "STORAGE_NOT_A_DIRECTORY"
    with pytest.raises(StorageError) as exc:
        open_store(tmp_path, read_only=True)
    assert exc.value.code == "STORAGE_EMPTY_NOT_INITIALISED"


def test_interrupted_write_leaves_nothing_behind(tmp_path):
    with open_store(tmp_path) as s:
        s.ingest(obs_a())
    script = (
        "import os,sys; sys.path.insert(0, %r)\n"
        "from observability.derivatives_positioning import PositioningStore, normalize\n"
        "from tests.derivatives_positioning.support import obs_a, T0\n"
        "from datetime import timedelta\n"
        "s = PositioningStore(%r)\n"
        "s._conn.execute('BEGIN IMMEDIATE')\n"
        "for i in range(1, 50): s._write_one(normalize(obs_a(T0 + timedelta(seconds=i))))\n"
        "os._exit(9)\n") % (str(REPO), str(tmp_path))
    proc = subprocess.run([sys.executable, "-c", script], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 9, proc.stderr
    with open_store(tmp_path) as s:
        assert count(s) == 1
        assert s._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert s.ingest(obs_a(T0 + timedelta(seconds=1))).status == "INSERTED"


# -- migrations -----------------------------------------------------------------------------
def test_tampered_or_newer_schema_is_refused(tmp_path):
    open_store(tmp_path).close()
    db = sqlite3.connect(tmp_path / "positioning.sqlite3")
    db.execute("UPDATE schema_migrations SET sql_sha256 = 'x' WHERE version = 1")
    db.commit()
    with pytest.raises(StorageError) as exc:
        open_store(tmp_path)
    assert exc.value.code == "STORAGE_MIGRATION_TAMPERED"
    db.execute("INSERT INTO schema_migrations VALUES (99, 'future', 'y', 0)")
    db.commit()
    db.close()
    with pytest.raises(StorageError) as exc:
        open_store(tmp_path)
    assert exc.value.code == "STORAGE_SCHEMA_NEWER"


# -- reading: history and OI change ----------------------------------------------------------
def series(s, *, start, n, step_s, oi0=1_000_000, skip=(), unit_change_at=None):
    docs = []
    for i in range(n):
        if i in skip:
            continue
        doc = obs_a(start + timedelta(seconds=i * step_s), oi=str(oi0 + i * 100))
        if unit_change_at is not None and i >= unit_change_at:
            doc["measures"]["open_interest"] = {"value": str(100 + i), "unit": "BASE"}
        docs.append(doc)
    assert s.ingest_batch(docs).ok


def test_history_is_bounded_and_reports_coverage(tmp_path):
    with open_store(tmp_path, policy=PositioningPolicy(history_max_rows=50)) as s:
        series(s, start=T0, n=120, step_s=60)
        h = s.history("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", ms(T0), ms(T0) + 3_600_000, cadence_s=60)
        assert h["limit"] == 50 and len(h["observations"]) == 50 and h["coverage"]["truncated"] is True
        h = s.history("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", ms(T0), ms(T0) + 1_800_000, limit=40, cadence_s=60)
        assert len(h["observations"]) == 31 and h["coverage"]["truncated"] is False
        assert h["coverage"]["expected"] == 31 and h["coverage"]["ratio"] == "1.000000"
        h = s.history("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", ms(T0), ms(T0) + 1_800_000)
        assert h["coverage"]["reason"] == "CADENCE_UNKNOWN" and h["coverage"]["ratio"] is None
        other = s.history("exchange_b", "PF_XBTUSD", "PERPETUAL_LINEAR", ms(T0), ms(T0) + 1_800_000)
        assert other["observations"] == [] and other["coverage"]["observations"] == 0


def test_oi_change_with_comparable_points_and_sufficient_coverage(tmp_path):
    start = T0 - timedelta(hours=24)
    with open_store(tmp_path) as s:
        series(s, start=start, n=24 * 12 + 1, step_s=300)
        out = s.oi_change("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=ms(T0), cadence_s=300)
    assert out["tolerance_ms"] == 300_000
    w = {x["window_s"]: x for x in out["windows"]}
    assert all(x["status"] == "AVAILABLE" for x in w.values())
    end = 1_000_000 + 288 * 100
    one_h = w[3600]
    assert one_h["start"]["value"] == str(end - 12 * 100) and one_h["end"]["value"] == str(end)
    assert one_h["unit"] == "CONTRACTS" and one_h["coverage"] == {"points": 13, "expected": 13, "ratio": "1.000000"}
    assert one_h["change_pct"] == "%.6f" % ((1200) / (end - 1200) * 100)


def test_oi_change_refuses_without_cadence_coverage_or_comparable_reference(tmp_path):
    start = T0 - timedelta(hours=24)
    with open_store(tmp_path) as s:
        series(s, start=start, n=24 * 12 + 1, step_s=300, skip=set(range(276, 282)))  # ~30 min hole in last hour
        none = s.oi_change("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=ms(T0), cadence_s=None)
        gap = s.oi_change("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=ms(T0), cadence_s=300)
        early = s.oi_change("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=ms(start) + 1_800_000, cadence_s=300)
    assert {x["reason"] for x in none["windows"]} == {"CADENCE_UNKNOWN"}
    w = {x["window_s"]: x for x in gap["windows"]}
    assert w[3600]["reason"] == "INSUFFICIENT_COVERAGE" and w[3600]["change_pct"] is None
    assert w[3600]["coverage"]["points"] == 7
    assert w[86400]["status"] == "AVAILABLE"
    assert {x["reason"] for x in early["windows"]} == {"NO_COMPARABLE_POINT_AT_START"}
    with open_store(tmp_path, policy=PositioningPolicy(min_coverage="0.5")) as s:
        relaxed = s.oi_change("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=ms(T0), cadence_s=300)
    assert relaxed["windows"][0]["status"] == "AVAILABLE"


def test_oi_change_refuses_when_units_differ_between_ends(tmp_path):
    start = T0 - timedelta(hours=24)
    with open_store(tmp_path) as s:
        series(s, start=start, n=24 * 12 + 1, step_s=300, unit_change_at=250)
        out = s.oi_change("exchange_a", "BTC_USDT", "PERPETUAL_LINEAR", as_of_ms=ms(T0), cadence_s=300)
    w = {x["window_s"]: x for x in out["windows"]}
    assert w[3600]["status"] == "AVAILABLE" and w[3600]["unit"] == "BASE"
    assert w[14400]["reason"] == "OPEN_INTEREST_UNITS_DIFFER"
    assert w[86400]["reason"] == "OPEN_INTEREST_UNITS_DIFFER"


# -- policy ---------------------------------------------------------------------------------
def test_policy_is_configurable_and_purge_stays_off(tmp_path):
    p = PositioningPolicy.from_file(REPO / "config" / "derivatives_positioning.example.json")
    assert p == PositioningPolicy()
    assert p.tolerance_ms(30) == 60_000 and p.tolerance_ms(300) == 300_000
    with pytest.raises(ValueError):
        PositioningPolicy(purge_enabled=True)
    with pytest.raises(ValueError):
        PositioningPolicy(min_coverage="1.5")
    bad = tmp_path / "p.json"
    bad.write_text(json.dumps({"late_after_s": 1}))
    with pytest.raises(ValueError):
        PositioningPolicy.from_file(bad)
    with open_store(tmp_path) as s:
        budget = s.status()["budget"]
    assert budget["status"] == "HYPOTHESIS_NOT_ENFORCED" and budget["purge_enabled"] is False
