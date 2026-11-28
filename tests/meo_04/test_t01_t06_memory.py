"""MEO-04 T01–T06: import, idempotence, conflict, crash boundaries, rebuild, exact values."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from observability import meo_trades_replay as cli
from observability.market_flow import meo_reading as mr
from observability.meo_memory import canon as c
from observability.meo_memory import engine
from observability.meo_memory import store as st
from observability.meo_memory.reads import Reader
from observability.meo_memory.store import SimulatedCrash, Store

from ._support import canonical_reads, make_archive, new_root, reads, tree

ROOT = Path(__file__).resolve().parents[2]


def expected_reading(capture):
    manifest, events = cli.load(str(capture))
    from observability.market_flow import kraken_trades as kt
    return mr.canonical(mr.read_report(kt.replay_journal(manifest, events)))


def journal(root):
    return sorted(os.listdir(Path(root) / "journal"))


# T01 — import of one sealed capture: one session, all windows, sources intact, reading recomposable.
def test_t01_synthetic_import_keeps_every_window_and_the_reading_byte_for_byte(synthetic_capture, tmp_path):
    before = tree(synthetic_capture)
    root = new_root(tmp_path)
    out = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    assert out["result"] == "IMPORTED" and out["knowledge_seq"] == 1 and out["windows"] == 4 and out["events"] == 1
    assert tree(synthetic_capture) == before  # source untouched
    rec_raw = (root / "journal" / "000000000001.json").read_bytes()
    rec = json.loads(rec_raw)
    assert hashlib.sha256(rec_raw).hexdigest() == out["import_sha256"]
    want = expected_reading(synthetic_capture)
    assert rec["reading_sha256"] == hashlib.sha256(want).hexdigest()
    proof = root / "proofs" / rec["reading_sha256"][:2] / rec["reading_sha256"]
    assert proof.read_bytes() == want and (proof.stat().st_mode & 0o777) == 0o400
    parts = Store(root).session_parts(rec)
    assert c.canonical(c.recompose(parts)) == want
    assert rec["verification"]["seal"] == "VERIFIED" and rec["verification"]["reading"] == "RECOMPUTED_AT_IMPORT"
    assert str(root) not in rec_raw.decode() and str(synthetic_capture) not in rec_raw.decode()  # no local path


def test_t01_real_l3_archive_one_session_six_windows_sources_intact(l3_archive, l3_reading, tmp_path):
    before = (l3_archive.stat().st_mtime_ns, hashlib.sha256(l3_archive.read_bytes()).hexdigest())
    root = new_root(tmp_path, "HISTORICAL")
    out = Store(root).import_capture(partition="HISTORICAL", archive=l3_archive, reading=l3_reading)
    assert (out["result"], out["windows"], out["events"], out["knowledge_seq"]) == ("IMPORTED", 6, 4, 1)
    assert out["proofs"]["archive.tar.gz"] == "4b06e0327aea7719d80a9b3179982078288c7f3a54797080d48335b45b9aa5bd"
    assert out["proofs"]["reading"] == out["reading_sha256"] == hashlib.sha256(l3_reading.read_bytes()).hexdigest()
    assert out["proofs"]["replay-report"] == out["proofs"]["report-original.json"] == \
        "3ebbca6ea2fe806a47bd20a5cad43e7feba90b028d2c00c54d7df6e914db4aec"
    assert (l3_archive.stat().st_mtime_ns, hashlib.sha256(l3_archive.read_bytes()).hexdigest()) == before
    s = Reader(root).summary()["sessions"]
    assert len(s) == 1 and s[0]["windows"] == 6
    rec = json.loads((root / "journal" / "000000000001.json").read_bytes())
    assert rec["verification"]["replay"] == "SOURCE_FILE_BYTE_IDENTICAL_TO_REPLAY"
    assert rec["verification"]["reading"] == "SOURCE_FILE_BYTE_IDENTICAL_TO_READING"
    assert c.canonical(c.recompose(Store(root).session_parts(rec))) == l3_reading.read_bytes()


# T02 — a repeated import is a NO_OP: same ids, same knowledge sequence, not one byte written.
def test_t02_reimport_is_a_no_op_with_same_ids_and_knowledge(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    first = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    snap, view = tree(root), canonical_reads(root)
    reading = tmp_path / "reading.json"
    reading.write_bytes(expected_reading(synthetic_capture))
    arch = make_archive(synthetic_capture, tmp_path / "cap.tar.gz")
    for kw in ({"capture_dir": synthetic_capture}, {"capture_dir": synthetic_capture, "reading": reading},
               {"archive": arch}):
        again = Store(root).import_capture(partition="SYNTHETIC", **kw)
        assert again["result"] == "NO_OP"
        for k in ("session_id", "knowledge_seq", "import_sha256", "reading_sha256", "windows", "events"):
            assert again[k] == first[k]
        assert tree(root) == snap and canonical_reads(root) == view


def test_t02_real_l3_reimport_by_archive_or_by_directory_is_a_no_op(l3_archive, l3_reading, tmp_path):
    import tarfile
    root = new_root(tmp_path, "HISTORICAL")
    first = Store(root).import_capture(partition="HISTORICAL", archive=l3_archive, reading=l3_reading)
    snap = tree(root)
    flat = tmp_path / "flat"
    flat.mkdir()
    with tarfile.open(l3_archive) as tar:
        for m in tar.getmembers():
            (flat / m.name).write_bytes(tar.extractfile(m).read())
    for kw in ({"archive": l3_archive}, {"capture_dir": flat, "reading": l3_reading}):
        again = Store(root).import_capture(partition="HISTORICAL", **kw)
        assert (again["result"], again["session_id"], again["import_sha256"]) == \
            ("NO_OP", first["session_id"], first["import_sha256"])
    assert tree(root) == snap


# T03 — same identity, different content: refused, nothing overwritten, nothing added.
@pytest.mark.parametrize("where", ["window", "session"])
def test_t03_contradictory_content_with_the_same_identity_is_refused(synthetic_capture, tmp_path, monkeypatch,
                                                                       where):
    root = new_root(tmp_path)
    first = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    snap, view = tree(root), canonical_reads(root)
    original = mr.read_report

    def contradict(report):
        r = original(report)
        if where == "window":
            r["windows"][2]["price_change"] = "999"  # same bounds and segment: same identity
        else:
            r["limits"] = r["limits"] + ["another wording"]
        return r

    monkeypatch.setattr(engine.mr, "read_report", contradict)
    with pytest.raises(c.MemoryRefusal) as e:
        Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    assert e.value.category == c.CONFLICT and first["session_id"] in e.value.detail
    assert tree(root) == snap and canonical_reads(root) == view


def test_t03_a_supplied_reading_that_the_engine_does_not_reproduce_is_refused(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    snap = tree(root)
    good = json.loads(expected_reading(synthetic_capture))
    good["windows"][2]["delta"] = "0.1"
    bad = tmp_path / "bad.json"
    bad.write_bytes(mr.canonical(good))
    with pytest.raises(c.MemoryRefusal) as e:
        Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture, reading=bad)
    assert (e.value.category, e.value.detail) == (c.PROOF_CORRUPT, "READING_NOT_REPRODUCED")
    assert tree(root) == snap


# T04 — a failure at each critical boundary: never a partial view; recovery converges to the clean state.
BOUNDARIES = ["proof_tmp_written", "proof_linked", "proofs_durable", "record_tmp_written", "record_linked",
              "record_durable", "index_transaction_open", "index_committed"]


@pytest.fixture(scope="module")
def clean(synthetic_capture, tmp_path_factory):
    root = new_root(tmp_path_factory.mktemp("clean"))
    out = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    return out, canonical_reads(root)


@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_t04_crash_at_each_boundary_never_shows_a_partial_view_and_recovers(boundary, synthetic_capture, tmp_path,
                                                                            clean):
    root = new_root(tmp_path)

    def fault(name):
        if name == boundary:
            raise SimulatedCrash(name)

    with pytest.raises(SimulatedCrash):
        Store(root, fault=fault).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    linked = BOUNDARIES.index(boundary) >= BOUNDARIES.index("record_linked")
    assert journal(root) == (["000000000001.json"] if linked else [])
    if not linked:  # before the record: the old knowledge bound, complete and empty
        assert Reader(root).now()["result"] == "EMPTY"
    elif boundary != "index_committed":  # record durable, index behind: refused, never partial
        with pytest.raises(c.MemoryRefusal) as e:
            Reader(root).now()
        assert (e.value.category, e.value.detail) == (c.INDEX_INCONSISTENT, "INDEX_BEHIND_JOURNAL")
    else:  # committed but not acknowledged: visible, and identical to the clean state
        assert canonical_reads(root) == clean[1]
    rec = Store(root).recover()
    assert rec["action"] in ("NONE", "APPLIED_PENDING")
    again = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    assert again["result"] == ("NO_OP" if linked else "IMPORTED")
    assert (again["session_id"], again["import_sha256"]) == (clean[0]["session_id"], clean[0]["import_sha256"])
    assert canonical_reads(root) == clean[1]
    audit = Store(root).verify()
    assert audit["state"] == "CONSISTENT" and audit["journal_head"] == 1 and audit["orphan_proofs"] == []


def test_t04_directory_fsync_failure_is_uncertain_never_acknowledged(synthetic_capture, tmp_path, monkeypatch, clean):
    root = new_root(tmp_path)
    broken = {"on": False}
    real = st._fsync_dir

    def fsync_dir(fd):
        if broken["on"]:
            raise OSError(5, "EIO")
        real(fd)

    def fault(name):
        if name == "record_linked":
            broken["on"] = True

    monkeypatch.setattr(st, "_fsync_dir", fsync_dir)
    with pytest.raises(c.MemoryRefusal) as e:
        Store(root, fault=fault).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    assert (e.value.category, e.value.detail) == (c.PUBLICATION_UNCERTAIN, "DIRECTORY_FSYNC_FAILED:record")
    with pytest.raises(c.MemoryRefusal) as e:
        Store(root).recover()  # still failing: still uncertain, nothing confirmed
    assert e.value.category == c.PUBLICATION_UNCERTAIN
    with pytest.raises(c.MemoryRefusal) as e:
        Reader(root).events()
    assert e.value.category == c.INDEX_INCONSISTENT
    broken["on"] = False
    assert Store(root).recover()["action"] == "APPLIED_PENDING"
    assert Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)["result"] == "NO_OP"
    assert canonical_reads(root) == clean[1]


@pytest.mark.parametrize("boundary", ["record_linked", "index_transaction_open"])
def test_t04_real_process_death_after_durable_proof_and_before_index(boundary, synthetic_capture, tmp_path, clean):
    root = new_root(tmp_path)
    code = ("import os, sys\nfrom observability.meo_memory.store import Store\n"
            "def fault(name):\n    if name == sys.argv[3]:\n        os._exit(9)\n"
            "Store(sys.argv[1], fault=fault).import_capture(partition='SYNTHETIC', capture_dir=sys.argv[2])\n")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.run([sys.executable, "-c", code, str(root), str(synthetic_capture), boundary],
                          cwd=ROOT, env=env, capture_output=True, timeout=300)
    assert proc.returncode == 9, proc.stderr
    with pytest.raises(c.MemoryRefusal) as e:
        Reader(root).summary()
    assert e.value.category == c.INDEX_INCONSISTENT
    assert Store(root).recover()["action"] == "APPLIED_PENDING"
    assert canonical_reads(root) == clean[1]


# T05 — reopening and rebuilding SQLite give the same results, the same order and the same knowledge.
def test_t05_reopen_rebuild_and_lost_or_corrupt_index_give_identical_reads(synthetic_capture, capture_copy, tmp_path):
    root = new_root(tmp_path)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    m = json.loads((capture_copy / "manifest.json").read_bytes())
    m["host"] = "another-host"  # a distinct capture of the same frames (unsealed field)
    (capture_copy / "manifest.json").write_bytes(json.dumps(m).encode())
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=capture_copy)
    view = canonical_reads(root)
    assert canonical_reads(root) == view  # reopen
    out = Store(root).rebuild()
    assert out["rebuilt_records"] == 2 and out["retired_index"].startswith("retired-")
    assert canonical_reads(root) == view
    idx = root / "index" / "memory.sqlite"
    with sqlite3.connect(idx) as conn:
        assert conn.execute("SELECT knowledge_seq FROM sessions ORDER BY knowledge_seq").fetchall() == [(1,), (2,)]
    idx.unlink()
    with pytest.raises(c.MemoryRefusal) as e:
        Reader(root).now()
    assert (e.value.category, e.value.detail) == (c.INDEX_INCONSISTENT, "INDEX_MISSING")
    assert Store(root).recover()["action"] == "REBUILT"
    assert canonical_reads(root) == view
    idx.write_bytes(b"not a database" * 100)
    with pytest.raises(c.MemoryRefusal) as e:
        Reader(root).summary()
    assert e.value.category == c.INDEX_INCONSISTENT
    assert Store(root).recover()["action"] == "REBUILT"
    assert canonical_reads(root) == view
    retired = [n for n in os.listdir(root / "index") if n.startswith("retired-")]
    assert len(retired) == 2  # never deleted: kept for audit


def test_t05_an_index_that_disagrees_with_the_proofs_is_refused_then_rebuilt(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    view = canonical_reads(root)
    with sqlite3.connect(root / "index" / "memory.sqlite") as conn:
        conn.execute("UPDATE windows SET content_sha256 = ? WHERE rowid = 1", ("0" * 64,))
    with pytest.raises(c.MemoryRefusal) as e:
        Reader(root).now()
    assert e.value.category == c.INDEX_INCONSISTENT and e.value.detail.startswith("INDEX_DISAGREES_WITH_PROOF")
    Store(root).rebuild()
    assert canonical_reads(root) == view


# T06 — UNKNOWN stays null, bounds and exact decimals are kept as text; no float anywhere.
def test_t06_unknown_null_bounds_and_exact_decimals_are_preserved(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    want = json.loads(expected_reading(synthetic_capture))
    got = {i["window"]["start_ns"]: i["window"] for i in Reader(root).events(include_excluded=True)["items"]}
    now = Reader(root).now()["window"]
    assert now == want["windows"][-1]
    assert now["alignment"] == "UNKNOWN" and now["price_change"] is None and now["delta"] is None
    assert now["trade_count"] is None and now["volume_base"] is None  # UNKNOWN never 0
    for w in want["windows"]:
        if w["start_ns"] in got:
            assert got[w["start_ns"]] == w
    covered = [w for w in want["windows"] if w["status"] == "COVERED"]
    for w in covered:
        assert all(isinstance(x, str) for x in w["delta_bounds"])
    with sqlite3.connect(root / "index" / "memory.sqlite") as conn:
        for table in ("sessions", "windows", "events"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            for col in cols:
                kinds = {r[0] for r in conn.execute(f"SELECT DISTINCT typeof({col}) FROM {table}")}
                assert "real" not in kinds, (table, col)
        assert {r[0] for r in conn.execute("SELECT typeof(start_ns) FROM windows")} == {"integer"}
    text = json.dumps(reads(root))
    assert "NaN" not in text and "Infinity" not in text


def test_t06_real_oracle_values_are_exact(l3_archive, tmp_path):
    root = new_root(tmp_path, "HISTORICAL")
    Store(root).import_capture(partition="HISTORICAL", archive=l3_archive)
    now = Reader(root).now()
    w = now["window"]
    assert (w["start_ns"], w["end_ns"], w["cvd_segment"]) == ("1795834500000000000", "1795834800000000000", 0)
    assert (w["trade_count"], w["price_first"], w["price_last"], w["price_change"]) == (15, "59980.0", "59973.3",
                                                                                        "-6.7")
    assert (w["delta"], w["volume_base"], w["cvd_end"]) == ("0.03605679", "0.36705679", "0.30183487")
    first = Reader(root).events(include_excluded=True)["items"]
    unknown = [i for i in Reader(root).summary()["sessions"]]
    assert unknown[0]["by_alignment"]["UNKNOWN"] == 1 and first
    assert now["freshness"]["state"] == "NOT_FRESH_HISTORICAL" and now["freshness"]["age"] == "UNKNOWN"
    assert now["marking"]["evidence_kind"] == "HISTORICAL" and now["marking"]["source_evidence_kind"] == "OBSERVATION"
