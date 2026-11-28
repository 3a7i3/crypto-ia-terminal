"""MEO-04-RV01-R1: adversarial index, mandatory proofs, rebuild budget, proof-directory fsync recovery.

Every index mutation below leaves the stored content hashes untouched: only the derived columns used
for selection, filtering, ordering and linking are altered, or rows are deleted or added.
"""

import json
import os
import sqlite3
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from observability.meo_memory import canon as c
from observability.meo_memory import store as st
from observability.meo_memory.reads import Reader
from observability.meo_memory.store import LIMITS, Store, init_root

from ._support import canonical_reads, make_archive, new_root, tree

MUTATIONS = {
    "eligible_raised": "UPDATE events SET eligible = 1",
    "eligible_lowered": "UPDATE windows SET eligible = 0 WHERE eligible = 1",
    "first_in_segment": "UPDATE events SET first_in_segment = 1 - first_in_segment",
    "event_start_ns": "UPDATE events SET start_ns = start_ns + 1",
    "window_start_ns": "UPDATE windows SET start_ns = start_ns - 300000000000 "
                       "WHERE start_ns = (SELECT MAX(start_ns) FROM windows)",
    "window_alignment": "UPDATE windows SET alignment = 'ALIGNED'",
    "window_exclusion": "UPDATE windows SET exclusion_reason = NULL, eligible = 1",
    "window_segment": "UPDATE windows SET segment = 7 WHERE segment IS NOT NULL",
    "event_window_link": "UPDATE events SET window_id = (SELECT window_id FROM windows ORDER BY start_ns LIMIT 1)",
    "event_session_link": "UPDATE events SET session_id = 'x'",
    "window_knowledge_seq": "UPDATE windows SET knowledge_seq = 2",
    "session_bounds": "UPDATE sessions SET native_last_ns = native_first_ns",
    "delete_windows": "DELETE FROM windows",
    "delete_events": "DELETE FROM events",
    "delete_one_window": "DELETE FROM windows WHERE start_ns = (SELECT MAX(start_ns) FROM windows)",
    "parasite_event": "INSERT INTO events SELECT substr('f' || event_id, 1, 64), session_id, knowledge_seq, "
                      "window_id, start_ns + 1, segment, 1, NULL, 1, content_sha256 FROM events",
    "parasite_window": "INSERT INTO windows SELECT 'p' || window_id, session_id, knowledge_seq, start_ns + 1, "
                       "end_ns + 1, segment, status, alignment, eligible, exclusion_reason, content_sha256 FROM windows",
    "parasite_session": "INSERT INTO sessions VALUES ('ghost', 99, 'h', 0, 1)",
    "meta_extra": "INSERT INTO meta VALUES ('extra', 'x')",
}


def refused(fn, category, detail=None):
    with pytest.raises(c.MemoryRefusal) as e:
        fn()
    assert e.value.category == category, (e.value.category, e.value.detail)
    if detail is not None:
        assert e.value.detail.startswith(detail), e.value.detail
    return e.value


def mutate(root, sql):
    with sqlite3.connect(root / "index" / "memory.sqlite") as conn:
        hashes = sorted(conn.execute("SELECT content_sha256 FROM windows UNION ALL "
                                     "SELECT content_sha256 FROM events").fetchall())
        assert conn.execute(sql).rowcount > 0  # the mutation really changes the index
        after = sorted(conn.execute("SELECT content_sha256 FROM windows UNION ALL "
                                    "SELECT content_sha256 FROM events").fetchall())
    assert set(after) <= set(hashes) or "INSERT" in sql  # no stored hash invented or altered


# RV01-01 — every derived column, cardinality and link is checked; recovery rebuilds from the proofs.
@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_rv01_01_any_index_tampering_is_inconsistent_never_empty_and_recover_rebuilds(name, synthetic_capture,
                                                                                    tmp_path):
    root = new_root(tmp_path)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    view = canonical_reads(root)
    mutate(root, MUTATIONS[name])
    r = Reader(root)
    for read in (r.now, lambda: r.events(), lambda: r.events(include_excluded=True), r.summary):
        refused(read, c.INDEX_INCONSISTENT)
    assert Store(root).verify()["state"] == "INCONSISTENT"
    assert Store(root).recover()["action"] == "REBUILT"
    assert canonical_reads(root) == view
    assert Store(root).verify()["state"] == "CONSISTENT"


def test_rv01_01_real_eligible_desalignment_cannot_be_hidden(l3_archive, tmp_path):
    root = new_root(tmp_path, "HISTORICAL")
    Store(root).import_capture(partition="HISTORICAL", archive=l3_archive)
    view = canonical_reads(root)
    mutate(root, "UPDATE events SET eligible = 0")  # the reviewer's case: hides the eligible desalignment
    refused(lambda: Reader(root).events(), c.INDEX_INCONSISTENT)
    mutate(root, MUTATIONS["delete_windows"])
    refused(lambda: Reader(root).now(), c.INDEX_INCONSISTENT)
    assert Store(root).verify()["state"] == "INCONSISTENT"
    assert Store(root).recover()["action"] == "REBUILT"
    assert canonical_reads(root) == view


# RV01-02 — every recorded proof is mandatory: unavailable and corrupt are distinct and never acknowledged.
@pytest.fixture
def archived(synthetic_capture, tmp_path):
    arch = make_archive(synthetic_capture, tmp_path / "cap.tar.gz")
    root = new_root(tmp_path)
    out = Store(root).import_capture(partition="SYNTHETIC", archive=arch)
    return root, arch, out


ROLES = ["SHA256SUMS", "archive.tar.gz", "events.jsonl", "frames.bin", "manifest.json", "reading", "replay-report"]


def _proof_path(root, sha):
    return root / "proofs" / sha[:2] / sha


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("damage", ["delete", "flip"])
def test_rv01_02_missing_or_corrupt_proof_of_any_role_blocks_reads_noop_and_recovery(role, damage, archived):
    root, arch, out = archived
    view = canonical_reads(root)
    assert set(out["proofs"]) == set(ROLES)
    p = _proof_path(root, out["proofs"][role])
    data = p.read_bytes()
    p.chmod(0o600)
    if damage == "delete":
        p.unlink()
        category = c.PROOF_UNAVAILABLE
    else:
        p.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        category = c.PROOF_CORRUPT
    r = Reader(root)
    for read in (r.now, lambda: r.events(include_excluded=True), r.summary):
        refused(read, category)
    audit = Store(root).verify()
    assert audit["state"] == "INCONSISTENT" and audit["findings"][0]["category"] == category
    refused(lambda: Store(root).recover(), category)
    refused(lambda: Store(root).import_capture(partition="SYNTHETIC", archive=arch), category)  # never NO_OP
    if damage == "flip":
        p.unlink()
    p.write_bytes(data)  # the operator restores the exact bytes: everything is valid again
    p.chmod(0o400)
    assert Store(root).recover()["action"] in ("NONE", "REBUILT")
    assert Store(root).import_capture(partition="SYNTHETIC", archive=arch)["result"] == "NO_OP"
    assert canonical_reads(root) == view


def test_rv01_02_record_links_to_its_proofs_are_checked(archived):
    root, _arch, _out = archived
    rec_path = root / "journal" / "000000000001.json"
    raw = rec_path.read_bytes()
    rec = json.loads(raw)
    rec_path.chmod(0o600)
    for edit, detail in (
            (lambda r: r.update(proofs=[p for p in r["proofs"] if p["role"] != "replay-report"]),
             "RECORD_REQUIRED_PROOF_MISSING:replay-report"),
            (lambda r: r["identity"]["session"].update(events_sha256="0" * 64), "RECORD_PROOF_LINK"),
            (lambda r: r.update(reading_sha256="0" * 64), "RECORD_PROOF_LINK")):
        bad = json.loads(raw)
        edit(bad)
        rec_path.write_bytes(c.canonical(bad))
        refused(lambda: Store(root).recover(), c.PROOF_CORRUPT, detail)
        refused(lambda: Reader(root).now(), c.INDEX_INCONSISTENT)  # index head no longer matches the record
    rec_path.write_bytes(raw)
    assert json.loads(rec_path.read_bytes()) == rec
    assert Store(root).verify()["state"] == "CONSISTENT"


# RV01-03 — rebuilds respect the root budget, before and during writing; refusal keeps the previous state.
def test_rv01_03_rebuilds_are_refused_when_the_budget_is_insufficient(tmp_path):
    lim = replace(LIMITS, reserve_bytes=1024)
    root = Path(tmp_path).resolve() / "tight"
    budget = 100_000
    init_root(root, "SYNTHETIC", budget_bytes=budget, limits=lim)

    def used():
        return sum(os.lstat(os.path.join(d, f)).st_size for d, _ds, fs in os.walk(root) for f in fs)

    sizes, refusals = [used()], 0
    for _ in range(5):
        before = tree(root)
        try:
            Store(root, limits=lim).rebuild()
        except c.MemoryRefusal as exc:
            assert (exc.category, exc.detail.split(":")[0]) == (c.BUDGET_EXCEEDED, "ROOT_BUDGET")
            assert tree(root) == before  # nothing left behind, previous index intact
            refusals += 1
        sizes.append(used())
        assert sizes[-1] <= budget - lim.reserve_bytes, sizes
    assert refusals >= 1, sizes
    assert Reader(root, limits=lim).now()["result"] == "EMPTY"  # the previous state stays usable
    assert not any(n.endswith(".tmp") or n.startswith("index-") for n in os.listdir(root / "tmp"))


def test_rv01_03_the_rebuild_file_itself_is_capped_while_it_is_written(synthetic_capture, tmp_path, monkeypatch):
    lim = replace(LIMITS, reserve_bytes=1024)
    root = Path(tmp_path).resolve() / "cap"
    init_root(root, "SYNTHETIC", budget_bytes=16 * 1024 * 1024, limits=lim)
    Store(root, limits=lim).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    view = canonical_reads(root)
    monkeypatch.setattr(st.Store, "_estimate_index_bytes", lambda self: 0)  # a wrong pre-check estimate
    used = sum(os.lstat(os.path.join(d, f)).st_size for d, _ds, fs in os.walk(root) for f in fs)
    marker = json.loads((root / "meo-memory-root.json").read_bytes())
    lim2 = replace(lim, reserve_bytes=marker["budget_bytes"] - used - 8192)  # leaves room for two pages only
    refused(lambda: Store(root, limits=lim2).rebuild(), c.BUDGET_EXCEEDED, "ROOT_BUDGET")
    assert canonical_reads(root) == view
    assert not any(n.startswith("index-") for n in os.listdir(root / "tmp"))


def test_rv01_03_proof_directory_fsync_failure_is_uncertain_then_synced_on_retry(synthetic_capture, tmp_path,
                                                                                 monkeypatch, clean_reads):
    root = new_root(tmp_path)
    proofs_ino = os.lstat(root / "proofs").st_ino
    synced = {"proofs": 0}
    state = {"fail": True}
    real = st._fsync_dir

    def fsync_dir(fd):
        if os.fstat(fd).st_ino == proofs_ino:
            if state["fail"]:
                state["fail"] = False
                raise OSError(5, "EIO")
            synced["proofs"] += 1
        real(fd)

    monkeypatch.setattr(st, "_fsync_dir", fsync_dir)
    refused(lambda: Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture),
            c.PUBLICATION_UNCERTAIN, "DIRECTORY_FSYNC_FAILED:proofs")
    assert os.listdir(root / "journal") == []  # no record after an uncertain proof directory
    assert Reader(root).now()["result"] == "EMPTY"
    synced["proofs"] = 0
    Store(root).recover()
    assert synced["proofs"] >= 1  # recovery re-syncs the proof directory left uncertain
    synced["proofs"] = 0
    out = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    assert out["result"] == "IMPORTED"
    # Every proof publication syncs proofs/, including the one whose sub-directory already existed.
    assert synced["proofs"] >= len(set(out["proofs"].values()))
    assert canonical_reads(root) == clean_reads


@pytest.fixture(scope="module")
def clean_reads(synthetic_capture, tmp_path_factory):
    root = new_root(tmp_path_factory.mktemp("rv01clean"))
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    return canonical_reads(root)


def test_rv01_03_recover_syncs_the_proof_directories_of_pending_records(synthetic_capture, tmp_path, monkeypatch):
    root = new_root(tmp_path)

    def fault(name):
        if name == "record_durable":
            raise st.SimulatedCrash(name)

    with pytest.raises(st.SimulatedCrash):
        Store(root, fault=fault).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    proof_dirs = {os.lstat(root / "proofs" / d).st_ino for d in os.listdir(root / "proofs")}
    proof_dirs.add(os.lstat(root / "proofs").st_ino)
    seen = set()
    real = st._fsync_dir

    def fsync_dir(fd):
        seen.add(os.fstat(fd).st_ino)
        real(fd)

    monkeypatch.setattr(st, "_fsync_dir", fsync_dir)
    assert Store(root).recover()["action"] == "APPLIED_PENDING"
    assert proof_dirs <= seen
    assert stat.S_ISDIR(os.lstat(root / "proofs").st_mode)
