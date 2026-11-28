"""MEO-04-RV02-R2: prospective import bounds, and recovery when the indexed journal prefix is inconsistent."""

import json
import os
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from observability.meo_memory import canon as c
from observability.meo_memory import store as st
from observability.meo_memory.reads import Reader
from observability.meo_memory.store import LIMITS, Store, init_root

from ._support import canonical_reads, new_root, tree


def refused(fn, category, detail=None):
    with pytest.raises(c.MemoryRefusal) as e:
        fn()
    assert e.value.category == category, (e.value.category, e.value.detail)
    if detail is not None:
        assert e.value.detail.startswith(detail), e.value.detail
    return e.value


def variant(src, tmp_path, host):
    """A distinct capture of the same frames (other manifest): another session, same reading bytes."""
    dst = Path(tmp_path).resolve() / host
    shutil.copytree(src, dst)
    for p in dst.iterdir():
        p.chmod(0o644)
    m = json.loads((dst / "manifest.json").read_bytes())
    m["host"] = host
    (dst / "manifest.json").write_bytes(json.dumps(m).encode())
    return dst


def root_with(tmp_path, lim, name="r"):
    root = Path(tmp_path).resolve() / name
    init_root(root, "SYNTHETIC", limits=lim)
    return root


def authority(root):
    return {k: v for k, v in tree(root).items() if k.startswith(("proofs", "journal", "meo-memory-root"))}


# RV02-01 — an import that would leave the memory unverifiable is refused before publication.
def test_rv02_01_session_limit_exact_then_one_more_is_refused_and_noop_still_works(synthetic_capture, tmp_path):
    lim = replace(LIMITS, sessions_per_read=2)
    root = root_with(tmp_path, lim)
    a, b, x = synthetic_capture, variant(synthetic_capture, tmp_path, "b"), variant(synthetic_capture, tmp_path, "x")
    Store(root, limits=lim).import_capture(partition="SYNTHETIC", capture_dir=a)
    assert Store(root, limits=lim).import_capture(partition="SYNTHETIC", capture_dir=b)["knowledge_seq"] == 2
    view, snap = canonical_reads_lim(root, lim), tree(root)
    refused(lambda: Store(root, limits=lim).import_capture(partition="SYNTHETIC", capture_dir=x),
            c.BUDGET_EXCEEDED, "SESSIONS_PER_READ")
    assert tree(root) == snap and canonical_reads_lim(root, lim) == view  # last valid state intact
    for cap in (a, b):  # saturated memory: identical re-imports are still NO_OP
        assert Store(root, limits=lim).import_capture(partition="SYNTHETIC", capture_dir=cap)["result"] == "NO_OP"
    assert tree(root) == snap
    assert Store(root, limits=lim).verify()["state"] == "CONSISTENT"


def test_rv02_01_proof_bytes_limit_exact_then_exceeded(synthetic_capture, tmp_path):
    probe = new_root(tmp_path, name="probe")
    Store(probe).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    rec = json.loads((probe / "journal" / "000000000001.json").read_bytes())
    one = sum(p["bytes"] for p in rec["proofs"])  # same accounting as verified_parts
    lim = replace(LIMITS, proof_bytes_per_check=one)
    root = root_with(tmp_path, lim)
    assert Store(root, limits=lim).import_capture(partition="SYNTHETIC",
                                                  capture_dir=synthetic_capture)["result"] == "IMPORTED"
    view, snap = canonical_reads_lim(root, lim), tree(root)
    refused(lambda: Store(root, limits=lim).import_capture(
        partition="SYNTHETIC", capture_dir=variant(synthetic_capture, tmp_path, "b")),
        c.BUDGET_EXCEEDED, "PROOF_BYTES_PER_CHECK")
    assert tree(root) == snap and canonical_reads_lim(root, lim) == view
    assert Store(root, limits=lim).import_capture(partition="SYNTHETIC",
                                                  capture_dir=synthetic_capture)["result"] == "NO_OP"
    lim1 = replace(lim, proof_bytes_per_check=one - 1)
    fresh = root_with(tmp_path, lim1, "fresh")
    refused(lambda: Store(fresh, limits=lim1).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture),
            c.BUDGET_EXCEEDED, "PROOF_BYTES_PER_CHECK")
    assert os.listdir(fresh / "journal") == [] and Reader(fresh, limits=lim1).now()["result"] == "EMPTY"


def canonical_reads_lim(root, lim):
    r = Reader(root, limits=lim)
    return c.canonical({"now": r.now(), "events": r.events(include_excluded=True), "summary": r.summary()})


# RV02-02 — recovery after an interruption when the indexed prefix is inconsistent.
def crashed(tmp_path, captures, name="root"):
    """Import all but the last capture, then crash the last one after its record is durable."""
    root = new_root(tmp_path, name=name)
    for cap in captures[:-1]:
        Store(root).import_capture(partition="SYNTHETIC", capture_dir=cap)

    def fault(n):
        if n == "record_durable":
            raise st.SimulatedCrash(n)

    with pytest.raises(st.SimulatedCrash):
        Store(root, fault=fault).import_capture(partition="SYNTHETIC", capture_dir=captures[-1])
    return root


def clean_view(tmp_path, captures):
    root = new_root(tmp_path, name="clean")
    for cap in captures:
        Store(root).import_capture(partition="SYNTHETIC", capture_dir=cap)
    return canonical_reads(root)


def sql(root, statement):
    with sqlite3.connect(root / "index" / "memory.sqlite") as conn:
        assert conn.execute(statement).rowcount > 0


def test_rv02_02_parasite_row_colliding_with_the_pending_import_is_rebuilt(synthetic_capture, tmp_path):
    root = crashed(tmp_path, [synthetic_capture])
    pending = json.loads((root / "journal" / "000000000001.json").read_bytes())
    wid = pending["windows"][0]["window_id"]
    sql(root, f"INSERT INTO windows VALUES ('{wid}', 's', 9, 1, 2, NULL, 'COVERED', 'ALIGNED', 1, NULL, 'h')")
    out = Store(root).recover()  # no raw sqlite3.IntegrityError
    assert out["action"] == "REBUILT"
    assert canonical_reads(root) == clean_view(tmp_path, [synthetic_capture])


def test_rv02_02_modified_prefix_is_verified_before_applying_pending(synthetic_capture, tmp_path, monkeypatch):
    caps = [synthetic_capture, variant(synthetic_capture, tmp_path, "b")]
    root = crashed(tmp_path, caps)
    sql(root, "UPDATE windows SET alignment = 'ALIGNED' WHERE knowledge_seq = 1")
    applied = []
    real = st.Store._index_record

    def spy(self, conn, rec, sha, parts):
        applied.append(conn.execute("PRAGMA database_list").fetchone()[2])
        return real(self, conn, rec, sha, parts)

    monkeypatch.setattr(st.Store, "_index_record", spy)
    out = Store(root).recover()
    assert out["action"] == "REBUILT"
    assert not any(p.endswith("index/memory.sqlite") for p in applied)  # nothing applied onto a bad prefix
    monkeypatch.undo()
    assert canonical_reads(root) == clean_view(tmp_path, caps)


def test_rv02_02_insufficient_budget_for_the_rebuild_is_typed_and_preserves_proofs(synthetic_capture, tmp_path):
    root = crashed(tmp_path, [synthetic_capture])
    sql(root, "INSERT INTO meta VALUES ('extra', 'x')")
    before = authority(root)
    used = sum(os.lstat(os.path.join(d, f)).st_size for d, _ds, fs in os.walk(root) for f in fs)
    budget = json.loads((root / "meo-memory-root.json").read_bytes())["budget_bytes"]
    tight = replace(LIMITS, reserve_bytes=budget - used - 1024)
    refused(lambda: Store(root, limits=tight).recover(), c.BUDGET_EXCEEDED)
    assert authority(root) == before
    refused(lambda: Reader(root).now(), c.INDEX_INCONSISTENT)
    assert Store(root).recover()["action"] == "REBUILT"  # with room again, recovery completes
    assert canonical_reads(root) == clean_view(tmp_path, [synthetic_capture])


def test_rv02_02_any_sqlite_failure_during_recovery_is_typed(synthetic_capture, tmp_path, monkeypatch):
    root = crashed(tmp_path, [synthetic_capture])

    def broken(self, conn, rec, sha, parts):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(st.Store, "_index_record", broken)
    refused(lambda: Store(root).recover(), c.INDEX_INCONSISTENT, "INDEX_WRITE_FAILED")


# Open point from RV01-R1 (py3.10, 1 run in 7): a refused cursor leaked the read transaction, and the
# next import then failed with a raw "database is locked" while the refusal's traceback was alive.
def test_refused_cursor_closes_its_read_transaction(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    r = Reader(root)
    kept = [refused(lambda: r.events(cursor="x"), c.INVALID_REQUEST),
            refused(lambda: r.summary(cursor="x"), c.INVALID_REQUEST)]  # tracebacks stay referenced
    out = Store(root).import_capture(partition="SYNTHETIC", capture_dir=variant(synthetic_capture, tmp_path, "b"))
    assert out["result"] == "IMPORTED" and len(kept) == 2
