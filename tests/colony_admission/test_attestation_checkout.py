"""Temporary checkout acquisition probes; no campaign or submitted code runs."""

import hashlib
import os
from contextlib import ExitStack

import pytest

from colony_admission import _attestation_checkout as c
from colony_admission import _attestation_statement as s
from colony_admission import observer as o
from colony_admission.evidence_observer import _EvidenceAcquisition, _Capacity


def put(root, path, raw=b"fixture\n", mode=0o644):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    target.chmod(mode)
    return target


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir(mode=0o755)
    for path in c.SUBJECT_ROOTS:
        put(root, path + "/fixture.json" if path == "governance_tower" else path)
    put(root, "colony_lab/evaluator.py")
    put(root, "sentinel_activity/fixture.json")
    for path in (s.CRITERIA_PATH, s.EVIDENCE_PATH, s.HISTORY_PATH):
        put(root, path, b'{}\n')
    yield root
    root.chmod(0o755)


def digest(root, paths):
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(path.encode() + b"\0" + hashlib.sha256((root / path).read_bytes()).digest())
    return h.hexdigest()


def test_complete_closures_non_python_files_and_single_acquisition(checkout, monkeypatch):
    put(checkout, "governance_tower/sub/fixture.data", b"non-Python fixture")
    put(checkout, "colony_lab/__pycache__/ignored.pyc", b"opaque cache")
    reads, original = [], os.read
    def tracked(fd, count):
        reads.append(os.readlink(f"/proc/self/fd/{fd}"))
        return original(fd, count)
    monkeypatch.setattr(os, "read", tracked)
    with ExitStack() as stack:
        owner = _EvidenceAcquisition(stack)
        reader = c.Checkout(owner, checkout)
        artifacts, subject, evaluator = reader.science(True)
        assert set(artifacts) == {s.CRITERIA_PATH, s.EVIDENCE_PATH, s.HISTORY_PATH}
        subject_files = {p for p in c.SUBJECT_ROOTS if p != "governance_tower"}
        subject_files.update({"governance_tower/fixture.json", "governance_tower/sub/fixture.data"})
        assert subject == digest(checkout, subject_files)
        assert evaluator == digest(checkout, {"colony_lab/evaluator.py", "sentinel_activity/fixture.json"})
        before = tuple(reads)
        assert reader.science(False) == ({k: artifacts[k] for k in (s.CRITERIA_PATH, s.EVIDENCE_PATH)}, subject, evaluator)
        assert tuple(reads) == before
        assert not any(path.endswith("ignored.pyc") for path in reads)
        assert len({x.resource for x in owner.stamps}) == len(owner.stamps)
        reader.verify()
        owner.verify()


@pytest.mark.parametrize("name", [".env", ".ENV.local", "mySecret.py", "credentials.json", "private_key.txt", "id_rsa", "id_ed25519", "a.pem", "a.KEY", "a.p12", "a.pfx"])
def test_forbidden_closure_never_reads_sensitive_file(checkout, monkeypatch, name):
    target = put(checkout, "governance_tower/" + name, b"never-read")
    original, reads = os.read, []
    def track(fd, count):
        reads.append(os.readlink(f"/proc/self/fd/{fd}"))
        return original(fd, count)
    monkeypatch.setattr(os, "read", track)
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        with pytest.raises(o._Blocked, match="SOURCE_PATH_FORBIDDEN"):
            reader.science()
    assert str(target) not in reads


@pytest.mark.parametrize("path", ["/etc/passwd", "../anything", "a/../b", "a//b", "a/./b", "", "a\\b", "a\x00b"])
def test_untrusted_paths_refused_before_io(checkout, monkeypatch, path):
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        monkeypatch.setattr(os, "read", lambda *a: pytest.fail("forbidden path read"))
        with pytest.raises(o._Blocked, match="SOURCE_PATH_FORBIDDEN"):
            reader.selected(path)


@pytest.mark.parametrize("kind", ["subdirectory", "wrong-extension", "symlink", "fifo"])
def test_cache_layout_refused_without_reading_content(checkout, kind):
    cache = checkout / "colony_lab/__pycache__"
    cache.mkdir()
    if kind == "subdirectory":
        (cache / "nested").mkdir()
    elif kind == "wrong-extension":
        put(checkout, "colony_lab/__pycache__/wrong.py")
    elif kind == "symlink":
        (cache / "fake.pyc").symlink_to(checkout / "colony_lab/evaluator.py")
    else:
        os.mkfifo(cache / "pipe.pyc")
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        with pytest.raises(o._Blocked, match="SOURCE_CODE_IRREGULAR"):
            reader.science()


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_code_irregular_types_refuse_entire_closure(checkout, kind):
    path = checkout / "governance_tower/irregular"
    if kind == "symlink":
        path.symlink_to(checkout / "colony_lab/evaluator.py")
    else:
        os.mkfifo(path)
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        with pytest.raises(o._Blocked, match="SOURCE_CODE_IRREGULAR"):
            reader.science()


@pytest.mark.parametrize("mode", [0o666, 0o664, 0o000, 0o200])
def test_checkout_file_permissions(checkout, mode):
    (checkout / s.EVIDENCE_PATH).chmod(mode)
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        with pytest.raises((o._Blocked, PermissionError)):
            reader.science()


@pytest.mark.parametrize("mode", [0o777, 0o775, 0o000, 0o600])
def test_checkout_root_permissions(checkout, mode):
    checkout.chmod(mode)
    with ExitStack() as stack:
        with pytest.raises((o._Blocked, PermissionError)):
            c.Checkout(_EvidenceAcquisition(stack), checkout)


def test_hardlink_not_read(checkout):
    path = checkout / s.EVIDENCE_PATH
    os.link(path, checkout / "second-copy")
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        with pytest.raises(o._Blocked, match="SOURCE_PERMISSIONS"):
            reader.selected(s.EVIDENCE_PATH)


def test_selected_absence_and_listing_revalidation(checkout):
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        assert reader.selected("docs/missing.json") is None
        reader.verify()
        put(checkout, "docs/missing.json")
        with pytest.raises(o._Blocked, match="SOURCE_CHANGED"):
            reader.verify()


def test_fd_metadata_replacement_invalidates(checkout):
    with ExitStack() as stack:
        owner = _EvidenceAcquisition(stack)
        reader = c.Checkout(owner, checkout)
        assert reader.selected(s.EVIDENCE_PATH) == b'{}\n'
        path = checkout / s.EVIDENCE_PATH
        path.unlink()
        put(checkout, s.EVIDENCE_PATH, b'{}\n')
        with pytest.raises(o._Blocked, match="SOURCE_CHANGED"):
            owner.verify()


def test_directory_new_entry_invalidates(checkout):
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        reader.science()
        put(checkout, "governance_tower/new.data")
        with pytest.raises(o._Blocked, match="SOURCE_CHANGED"):
            reader.verify()


@pytest.mark.parametrize("constant,value,limit_name", [("PER_FILE_BYTES", 16, "checkout_file_bytes"), ("CHECKOUT_BYTES", 1, "checkout_bytes"), ("CHECKOUT_FILES", 1, "checkout_files"), ("CHECKOUT_ENTRIES", 1, "checkout_entries")])
def test_budgets_fail_closed(checkout, monkeypatch, constant, value, limit_name):
    # Per-file selected limit is explicit, avoiding a captured default constant.
    monkeypatch.setattr(c, constant, value)
    with ExitStack() as stack:
        if constant == "CHECKOUT_ENTRIES":
            with pytest.raises(_Capacity) as exc:
                c.Checkout(_EvidenceAcquisition(stack), checkout).science()
        else:
            reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
            with pytest.raises(_Capacity) as exc:
                if constant == "PER_FILE_BYTES":
                    reader.selected(s.EVIDENCE_PATH, 17)
                else:
                    reader.science()
        assert exc.value.limit_name == limit_name


def test_missing_expected_root_never_hashes_partial_closure(checkout):
    (checkout / "colony_lab/workers/sentinel.py").unlink()
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        with pytest.raises(o._Blocked, match="SCIENTIFIC_SOURCE_UNAVAILABLE"):
            reader.science()


def test_read_error_is_not_absence(checkout, monkeypatch):
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        def fail(*a):
            raise FileNotFoundError()
        monkeypatch.setattr(os, "read", fail)
        with pytest.raises(FileNotFoundError):
            reader.selected(s.EVIDENCE_PATH)
        assert not reader.absences


def test_close_error_propagates(checkout, monkeypatch):
    original = os.close
    failed = False
    def close(fd):
        nonlocal failed
        original(fd)
        if not failed:
            failed = True
            raise OSError("fixture close failure")
    monkeypatch.setattr(os, "close", close)
    with pytest.raises(OSError):
        with ExitStack() as stack:
            owner = _EvidenceAcquisition(stack)
            reader = c.Checkout(owner, checkout)
            reader.science()
            reader.verify()
            owner.verify()


def test_file_size_limit_precedes_read(checkout, monkeypatch):
    put(checkout, "docs/oversized.json", b"x" * 17)
    with ExitStack() as stack:
        reader = c.Checkout(_EvidenceAcquisition(stack), checkout)
        monkeypatch.setattr(os, "read", lambda *a: pytest.fail("oversized file read"))
        with pytest.raises(_Capacity) as exc:
            reader.selected("docs/oversized.json", 16)
        assert exc.value.limit_name == "checkout_file_bytes"


def test_shared_descriptor_capacity_counts_checkout_roots(checkout):
    with ExitStack() as stack:
        owner = _EvidenceAcquisition(stack)
        owner.count = 4096
        with pytest.raises(_Capacity) as exc:
            c.Checkout(owner, checkout)
        assert exc.value.limit_name == "descriptors"


def test_mode_change_after_read_invalidates(checkout):
    with ExitStack() as stack:
        owner = _EvidenceAcquisition(stack)
        reader = c.Checkout(owner, checkout)
        reader.selected(s.EVIDENCE_PATH)
        (checkout / s.EVIDENCE_PATH).chmod(0o600)
        with pytest.raises(o._Blocked, match="SOURCE_CHANGED"):
            owner.verify()


def test_cache_replacement_invalidates_even_without_content_read(checkout):
    put(checkout, "colony_lab/__pycache__/opaque.pyc", b"original")
    with ExitStack() as stack:
        owner = _EvidenceAcquisition(stack)
        reader = c.Checkout(owner, checkout)
        reader.science()
        put(checkout, "colony_lab/__pycache__/opaque.pyc", b"changed")
        with pytest.raises(o._Blocked, match="SOURCE_CHANGED"):
            owner.verify()


def test_checkout_root_symlink_is_never_followed(checkout):
    alias = checkout.parent / "alias"
    alias.symlink_to(checkout, target_is_directory=True)
    with ExitStack() as stack:
        with pytest.raises(OSError):
            c.Checkout(_EvidenceAcquisition(stack), alias)


def test_nonowner_checkout_root_refused(checkout, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: -1)
    with ExitStack() as stack:
        with pytest.raises(o._Blocked, match="SOURCE_PERMISSIONS"):
            c.Checkout(_EvidenceAcquisition(stack), checkout)
