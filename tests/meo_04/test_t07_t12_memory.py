"""MEO-04 T07–T12: exclusions, proofs and limits, oracle counts, partitions, bounded reads, architecture."""

import ast
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest

from observability.meo_memory import canon as c
from observability.meo_memory.reads import Reader
from observability.meo_memory.store import LIMITS, SCHEMA_SQL, Store, init_root

from ._support import canonical_reads, make_archive, new_root, tree

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "observability" / "meo_memory"


def refused(fn, category, detail=None):
    with pytest.raises(c.MemoryRefusal) as e:
        fn()
    assert e.value.category == category, (e.value.category, e.value.detail)
    if detail is not None:
        assert e.value.detail.startswith(detail), e.value.detail
    return e.value


def second_capture(capture_copy):
    """A distinct capture of the same frames: overlapping on the native axis, another manifest."""
    m = json.loads((capture_copy / "manifest.json").read_bytes())
    m["host"] = "another-host"
    (capture_copy / "manifest.json").write_bytes(json.dumps(m).encode())
    return capture_copy


# T07 — PRE_SUBSCRIPTION and OVERLAPS_SUBSCRIPTION exclusions are kept, read and never eligible.
def test_t07_exclusions_are_preserved_and_documentary(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    r = Reader(root)
    assert r.events()["result"] == "EMPTY" and r.events()["items"] == []  # no eligible divergence
    doc = r.events(include_excluded=True)["items"]
    assert [(i["event"]["exclusion_reason"], i["documentary_only"]) for i in doc] == [("OVERLAPS_SUBSCRIPTION", True)]
    s = r.summary()["sessions"][0]
    assert s["by_exclusion_reason"] == {"NONE": 1, "NOT_COVERED": 1, "OVERLAPS_SUBSCRIPTION": 1,
                                        "PRE_SUBSCRIPTION": 1}
    assert s["first_desalignment_by_segment"] == [] and s["first_desalignment"] is None


def test_t07_real_pre_and_overlapping_subscription_windows_are_kept(l3_archive, tmp_path):
    root = new_root(tmp_path, "HISTORICAL")
    Store(root).import_capture(partition="HISTORICAL", archive=l3_archive)
    items = Reader(root).events(include_excluded=True)["items"]
    assert [(i["event"]["start_ns"], i["event"]["exclusion_reason"]) for i in items] == [
        ("1795833300000000000", "PRE_SUBSCRIPTION"), ("1795833600000000000", "PRE_SUBSCRIPTION"),
        ("1795833900000000000", "OVERLAPS_SUBSCRIPTION"), ("1795834500000000000", None)]
    s = Reader(root).summary()["sessions"][0]
    assert s["by_exclusion_reason"] == {"NONE": 2, "OVERLAPS_SUBSCRIPTION": 1, "PRE_SUBSCRIPTION": 3}


# T08 — proofs and links verified; missing, corrupt, unsafe and over-budget inputs refused.
def test_t08_missing_corrupt_and_unsafe_stored_proofs(synthetic_capture, capture_copy, tmp_path):
    root = new_root(tmp_path)
    out = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    proof = root / "proofs" / out["reading_sha256"][:2] / out["reading_sha256"]
    data = proof.read_bytes()
    proof.chmod(0o600)
    proof.write_bytes(data.replace(b"DESALIGN-1", b"DESALIGN-2"))
    refused(lambda: Reader(root).now(), c.PROOF_CORRUPT, "PROOF_HASH_MISMATCH")
    assert Store(root).verify()["state"] == "INCONSISTENT"
    proof.unlink()
    refused(lambda: Reader(root).events(), c.PROOF_UNAVAILABLE)  # unavailable is not corrupt
    os.symlink("/etc/hostname", proof)
    refused(lambda: Reader(root).summary(), c.PROOF_CORRUPT, "REF_SYMLINK")
    refused(lambda: Store(root).rebuild(), c.PROOF_CORRUPT)  # no destructive repair, no substitution
    proof.unlink()
    proof.write_bytes(data)
    proof.chmod(0o400)
    assert Store(root).verify()["state"] == "CONSISTENT"
    # The journal: a broken chain, a gap and a stray entry are refused.
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=second_capture(capture_copy))
    rec1 = root / "journal" / "000000000001.json"
    raw = rec1.read_bytes()
    rec1.chmod(0o600)
    rec1.write_bytes(raw.replace(b'"producer":"meo-memory/0.1"', b'"producer":"meo-memory/0.2"'))
    refused(lambda: Reader(root).now(), c.PROOF_CORRUPT, "RECORD_CHAIN_BROKEN:2")
    rec1.write_bytes(raw + b" ")
    refused(lambda: Reader(root).now(), c.PROOF_CORRUPT, "RECORD_NOT_CANONICAL:1")
    rec1.unlink()
    refused(lambda: Reader(root).now(), c.PROOF_UNAVAILABLE, "JOURNAL_GAP")
    rec1.write_bytes(raw)
    (root / "journal" / "notes.txt").write_bytes(b"x")
    refused(lambda: Reader(root).now(), c.PROOF_CORRUPT, "JOURNAL_UNEXPECTED_ENTRY")


def test_t08_unsafe_missing_or_altered_inputs_are_refused_and_nothing_is_written(capture_copy, tmp_path):
    root = new_root(tmp_path)
    snap = tree(root)

    def imp(**kw):
        return lambda: Store(root).import_capture(partition="SYNTHETIC", **kw)

    frames = (capture_copy / "frames.bin").read_bytes()
    refused(imp(capture_dir=capture_copy / ".." / "copy"), c.INPUT_REFUSED, "INPUT_INVALID_PATH")
    link = tmp_path / "link"
    os.symlink(capture_copy, link)
    refused(imp(capture_dir=link), c.INPUT_REFUSED, "INPUT_INVALID_PATH")
    (capture_copy / "frames.bin").write_bytes(frames[:-1] + bytes([frames[-1] ^ 1]))
    refused(imp(capture_dir=capture_copy), c.PROOF_CORRUPT, "SEAL_OR_JOURNAL:FRAMES_SHA256_MISMATCH")
    (capture_copy / "frames.bin").unlink()
    refused(imp(capture_dir=capture_copy), c.PROOF_UNAVAILABLE, "INPUT_MISSING:frames.bin")
    os.symlink("/etc/hostname", capture_copy / "frames.bin")
    refused(imp(capture_dir=capture_copy), c.INPUT_REFUSED, "INPUT_INVALID_PATH")
    (capture_copy / "frames.bin").unlink()
    (capture_copy / "frames.bin").write_bytes(frames)
    (capture_copy / "report-original.json").write_bytes(b"{}")
    refused(imp(capture_dir=capture_copy), c.PROOF_CORRUPT, "REPLAY_NOT_REPRODUCED")
    (capture_copy / "report-original.json").unlink()
    (capture_copy / "manifest.json").write_bytes(b'\xef\xbb\xbf' + (capture_copy / "manifest.json").read_bytes())
    refused(imp(capture_dir=capture_copy), c.PROOF_CORRUPT, "JSON_BOM")
    assert tree(root) == snap


def test_t08_archives_are_sealed_flat_and_regular(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    snap = tree(root)

    def imp(path):
        return lambda: Store(root).import_capture(partition="SYNTHETIC", archive=path)

    bad_sum = make_archive(synthetic_capture, tmp_path / "a.tar.gz")
    with tarfile.open(bad_sum) as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers()}
    members["SHA256SUMS"] = members["SHA256SUMS"].replace(members["SHA256SUMS"][:8], b"00000000", 1)
    for name, extra in (("sums", None), ("link", "SYMTYPE"), ("trav", "../x")):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for n, d in members.items():
                info = tarfile.TarInfo(n)
                info.size = len(d)
                tar.addfile(info, io.BytesIO(d))
            if extra == "SYMTYPE":
                info = tarfile.TarInfo("preflight.json")
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/hostname"
                tar.addfile(info)
            elif extra:
                info = tarfile.TarInfo(extra)
                info.size = 1
                tar.addfile(info, io.BytesIO(b"x"))
        (tmp_path / f"{name}.tar.gz").write_bytes(buf.getvalue())
    refused(imp(tmp_path / "sums.tar.gz"), c.PROOF_CORRUPT, "SHA256SUMS_MISMATCH")
    refused(imp(tmp_path / "link.tar.gz"), c.INPUT_REFUSED, "ARCHIVE_MEMBER_REFUSED")
    refused(imp(tmp_path / "trav.tar.gz"), c.INPUT_REFUSED, "ARCHIVE_MEMBER_REFUSED")
    (tmp_path / "junk.tar.gz").write_bytes(b"not gzip")
    refused(imp(tmp_path / "junk.tar.gz"), c.INPUT_REFUSED, "ARCHIVE_MALFORMED")
    assert tree(root) == snap


def test_t08_byte_and_root_budgets_refuse_before_writing(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    snap = tree(root)
    small = replace(LIMITS, journal_bytes=1000)
    refused(lambda: Store(root, limits=small).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture),
            c.BUDGET_EXCEEDED, "INPUT_TOO_LARGE:events.jsonl")
    tight = replace(LIMITS, reserve_bytes=1024)
    root2 = Path(tmp_path).resolve() / "tight"
    init_root(root2, "SYNTHETIC", budget_bytes=2 * 1024 * 1024, limits=tight)
    snap2 = tree(root2)
    refused(lambda: Store(root2, limits=tight).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture),
            c.BUDGET_EXCEEDED, "ROOT_BUDGET")
    assert tree(root) == snap and tree(root2) == snap2


def test_t08_root_must_be_explicit_private_initialized_and_outside_the_repository(tmp_path):
    refused(lambda: Reader(tmp_path.resolve() / "absent"), c.NOT_CONFIGURED, "ROOT_MISSING")
    plain = tmp_path.resolve() / "plain"
    plain.mkdir(mode=0o700)
    refused(lambda: Reader(plain), c.NOT_CONFIGURED, "MARKER_PROOF_UNAVAILABLE")
    root = new_root(tmp_path)
    root.chmod(0o755)
    refused(lambda: Reader(root), c.NOT_CONFIGURED, "ROOT_NOT_PRIVATE")
    root.chmod(0o700)
    refused(lambda: Reader("relative/root"), c.INVALID_REQUEST, "ROOT_NOT_ABSOLUTE")
    refused(lambda: init_root(ROOT / "meo-memory-root-test", "SYNTHETIC"), c.INVALID_REQUEST, "ROOT_INSIDE_REPOSITORY")
    assert not (ROOT / "meo-memory-root-test").exists()
    (plain / "x").write_bytes(b"")
    refused(lambda: init_root(plain, "SYNTHETIC"), c.INVALID_REQUEST, "ROOT_NOT_EMPTY")
    assert init_root(root, "SYNTHETIC")["result"] == "NO_OP"


def test_t08_strict_json_refuses_ambiguous_documents():
    for raw, detail in ((b'{"a":1,"a":2}', "JSON_DUPLICATE_KEY"), (b'{"a":1.5}', "JSON_FLOAT_FORBIDDEN"),
                        (b'{"a":NaN}', "JSON_CONSTANT_FORBIDDEN"), (b'\xef\xbb\xbf{}', "JSON_BOM"),
                        (b'{"a":', "JSON_MALFORMED"), (b'\xff', "JSON_MALFORMED")):
        with pytest.raises(c.MemoryRefusal) as e:
            c.strict_json(raw)
        assert e.value.detail == detail


# T09 — the real oracle: 4 DIVERGENT of which 1 eligible, 1 ALIGNED, 1 UNKNOWN, 1 first desalignment.
def test_t09_real_corpus_counts_and_oracle(l3_archive, tmp_path):
    root = new_root(tmp_path, "HISTORICAL")
    Store(root).import_capture(partition="HISTORICAL", archive=l3_archive)
    s = Reader(root).summary()["sessions"][0]
    assert s["by_alignment"] == {"ALIGNED": 1, "DIVERGENT": 4, "UNKNOWN": 1}
    assert s["divergent_events"] == {"total": 4, "eligible": 1, "excluded": 3}
    assert s["first_desalignment_by_segment"] == [{"segment": 0, "start_ns": "1795834500000000000"}]
    ev = Reader(root).events()
    assert len(ev["items"]) == 1 and ev["items"][0]["event"]["first_in_segment"] is True
    assert Reader(root).events(first_only=True)["items"] == ev["items"]
    w = ev["items"][0]["window"]
    assert (w["start_ns"], w["trade_count"], w["price_change"], w["delta"], w["cvd_end"]) == \
        ("1795834500000000000", 15, "-6.7", "0.03605679", "0.30183487")
    prev = [i["window"] for i in Reader(root).events(include_excluded=True)["items"]]
    assert all(x["alignment"] == "DIVERGENT" for x in prev)
    aligned = Reader(root).summary()["sessions"][0]
    assert aligned["by_alignment"]["ALIGNED"] == 1
    rec = json.loads((root / "journal" / "000000000001.json").read_bytes())
    parts = Store(root).session_parts(rec)
    before = [x["body"] for x in parts["windows"] if x["body"]["end_ns"] == "1795834500000000000"][0]
    assert (before["alignment"], before["delta"]) == ("ALIGNED", "0.01890780")


# T10 — SYNTHETIC never mixed or promoted; overlapping captures stay distinct and are never summed.
def test_t10_partitions_are_explicit_and_never_mixed(synthetic_capture, tmp_path):
    hist = new_root(tmp_path, "HISTORICAL", name="hist")
    snap = tree(hist)
    refused(lambda: Store(hist).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture),
            c.INPUT_REFUSED, "PARTITION_MISMATCH_WITH_ROOT")
    refused(lambda: Store(hist).import_capture(partition="HISTORICAL", capture_dir=synthetic_capture),
            c.INPUT_REFUSED, "PARTITION_MISMATCH_WITH_EVIDENCE")
    assert tree(hist) == snap
    syn = new_root(tmp_path, "SYNTHETIC", name="syn")
    Store(syn).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    now = Reader(syn).now()
    assert now["marking"]["evidence_kind"] == "SYNTHETIC" and now["freshness"]["state"] == "NOT_FRESH_SYNTHETIC"
    assert now["provenance"]["identity"]["partition"] == "SYNTHETIC"


def test_t10_real_corpus_is_refused_by_a_synthetic_root(l3_archive, tmp_path):
    syn = new_root(tmp_path, "SYNTHETIC")
    refused(lambda: Store(syn).import_capture(partition="SYNTHETIC", archive=l3_archive),
            c.INPUT_REFUSED, "PARTITION_MISMATCH_WITH_EVIDENCE")


def test_t10_overlapping_captures_are_distinct_listed_and_not_summed(synthetic_capture, capture_copy, tmp_path):
    root = new_root(tmp_path)
    a = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    b = Store(root).import_capture(partition="SYNTHETIC", capture_dir=second_capture(capture_copy))
    assert b["result"] == "IMPORTED" and a["session_id"] != b["session_id"] and b["knowledge_seq"] == 2
    s = Reader(root).summary()
    assert s["totals_across_sessions"] is None
    assert [x["session_id"] for x in s["sessions"]] == [a["session_id"], b["session_id"]]
    assert s["sessions"][0]["overlapping_sessions_native_conditional"] == [b["session_id"]]
    assert s["sessions"][1]["overlapping_sessions_native_conditional"] == [a["session_id"]]
    assert all(x["windows"] == 4 for x in s["sessions"])
    ev = Reader(root).events(include_excluded=True)["items"]
    assert len(ev) == 2 and len({i["event_id"] for i in ev}) == 2  # one per capture, never deduplicated
    assert Reader(root).now()["provenance"]["session_id"] == b["session_id"]  # knowledge order, not native


# T11 — bounded reads, stable numeric order, errors never read as empty.
def test_t11_empty_is_a_result_and_errors_are_not_empty(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    r = Reader(root)
    assert (r.now()["result"], r.events()["result"], r.summary()["result"]) == ("EMPTY", "EMPTY", "EMPTY")
    out = Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    proof = root / "proofs" / out["reading_sha256"][:2] / out["reading_sha256"]
    proof.unlink()
    for fn in (r.now, lambda: r.events(include_excluded=True), r.summary):
        refused(fn, c.PROOF_UNAVAILABLE)


def test_t11_pagination_is_bounded_deterministic_and_pinned_to_its_knowledge_bound(synthetic_capture,
                                                                                    capture_copy, tmp_path):
    root = new_root(tmp_path)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=second_capture(capture_copy))
    r = Reader(root)
    for bad in (0, 101, "5"):
        refused(lambda bad=bad: r.events(limit=bad), c.INVALID_REQUEST, "PAGE_SIZE_OUT_OF_BOUNDS")
    full = r.events(include_excluded=True, limit=100)["items"]
    pages, cursor = [], None
    while True:
        p = r.events(include_excluded=True, limit=1, cursor=cursor)
        pages += p["items"]
        cursor = p["next_cursor"]
        if cursor is None:
            break
    assert [i["event_id"] for i in pages] == [i["event_id"] for i in full] and len(full) == 2
    s1 = r.summary(limit=1)
    assert len(s1["sessions"]) == 1 and r.summary(limit=1, cursor=s1["next_cursor"])["next_cursor"] is None
    for bad in ("x", "2:1", "2:1:1:" + "g" * 64, "2:" + "9" * 30):
        refused(lambda bad=bad: r.events(cursor=bad), c.INVALID_REQUEST)
    first = r.events(include_excluded=True, limit=1)["next_cursor"]
    third = tmp_path / "third"
    import shutil
    shutil.copytree(capture_copy, third)
    m = json.loads((third / "manifest.json").read_bytes())
    m["host"] = "third-host"
    (third / "manifest.json").write_bytes(json.dumps(m).encode())
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=third)
    refused(lambda: r.events(include_excluded=True, cursor=first), c.INVALID_REQUEST,
            "CURSOR_FROM_ANOTHER_KNOWLEDGE_BOUND")


def test_t11_native_nanoseconds_sort_as_integers_never_as_text(synthetic_capture, tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    for i, ns in enumerate((1000000000000000000, 999999999999999999, 10)):
        conn.execute("INSERT INTO windows VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (f"w{i}", "s", 1, ns, ns + 1, 0, "COVERED", "ALIGNED", 1, None, "0" * 64))
    got = [r[0] for r in conn.execute("SELECT start_ns FROM windows ORDER BY start_ns")]
    assert got == [10, 999999999999999999, 1000000000000000000]
    assert sorted(str(x) for x in got) != [str(x) for x in got]  # a text sort would misorder them
    root = new_root(tmp_path)
    Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture)
    with sqlite3.connect(root / "index" / "memory.sqlite") as db:
        for t in ("windows", "events"):
            assert {r[0] for r in db.execute(f"SELECT typeof(start_ns) FROM {t}")} == {"integer"}


def test_t11_single_writer(synthetic_capture, tmp_path):
    root = new_root(tmp_path)
    s = Store(root)
    with s.writer():
        refused(lambda: Store(root).import_capture(partition="SYNTHETIC", capture_dir=synthetic_capture),
                c.WRITER_BUSY)
        assert Reader(root).now()["result"] == "EMPTY"  # readers are not blocked


# T12 — architecture: one-way dependency, a single bridge, no protected domain, no write on import.
ALLOWED_INTERNAL = {"observability.operator_api.bounded_file", "observability.radar_selection",
                    "observability.radar_selection.fixture"}
BRIDGE = {"observability.market_flow"}


def _imports(path):
    tree_ = ast.parse(path.read_text())
    out = set()
    for n in ast.walk(tree_):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out.add(("." * n.level) + (n.module or ""))
    return out


def test_t12_memory_imports_only_stdlib_its_bridge_and_inventoried_helpers():
    stdlib = set(sys.stdlib_module_names)
    for p in sorted(PKG.glob("*.py")):
        for name in _imports(p):
            if name.startswith(".") or name.split(".")[0] in stdlib or name == "__future__":
                continue
            allowed = ALLOWED_INTERNAL | (BRIDGE if p.name == "engine.py" else set())
            assert name in allowed, (p.name, name)
        text = p.read_text()
        if p.name != "engine.py":
            assert "market_flow" not in text and "meo_reading" not in text, p.name
        for needle in ("paper_trading", "core.", "advisor", "exchange_", "socket", "requests", "http.client",
                       "urllib.request", "kraken_trade_pilot", "subprocess"):
            assert needle not in text, (p.name, needle)


def test_t12_dependency_is_one_way_and_scientific_modules_ignore_the_memory():
    for p in (ROOT / "observability").rglob("*.py"):
        if "meo_memory" in p.read_text(errors="ignore"):
            assert p.parent == PKG, str(p)


def test_t12_importing_the_package_writes_nothing(tmp_path):
    before = sorted(os.listdir(tmp_path))
    code = ("import observability.meo_memory, observability.meo_memory.store, observability.meo_memory.reads, "
            "observability.meo_memory.engine, observability.meo_memory.__main__")
    proc = subprocess.run([sys.executable, "-B", "-c", code], cwd=tmp_path, capture_output=True, timeout=120,
                          env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert proc.returncode == 0, proc.stderr
    assert sorted(os.listdir(tmp_path)) == before


def test_t12_cli_round_trip_and_exit_codes(synthetic_capture, tmp_path, capsys):
    from observability.meo_memory.__main__ import main
    root = str(tmp_path.resolve() / "cli")
    assert main(["init", "--root", root, "--partition", "SYNTHETIC"]) == 0
    assert main(["import", "--root", root, "--partition", "SYNTHETIC", "--capture", str(synthetic_capture)]) == 0
    assert main(["import", "--root", root, "--partition", "SYNTHETIC", "--capture", str(synthetic_capture)]) == 0
    capsys.readouterr()
    for cmd in (["now"], ["events", "--include-excluded"], ["summary"], ["verify"], ["recover"]):
        assert main([cmd[0], "--root", root] + cmd[1:]) == 0
    assert main(["import", "--root", root, "--partition", "HISTORICAL", "--capture", str(synthetic_capture)]) == 4
    err = json.loads(capsys.readouterr().err)
    assert err == {"refused": "INPUT_REFUSED", "detail": "PARTITION_MISMATCH_WITH_ROOT"}
    assert main(["now", "--root", str(tmp_path.resolve() / "nowhere")]) == 4
    assert canonical_reads(Path(root))
