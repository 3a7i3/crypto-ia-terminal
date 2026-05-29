"""Tests G-02 — ImmutableStamp (11 tests)"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from certification.immutable_stamp import (
    _DEFAULT_KEY,
    ImmutableStamp,
    StampRecord,
    _sign,
)

ROOT = Path(__file__).parent.parent.parent
FAKE_SHA = "a" * 64


# ── Tests stamp ───────────────────────────────────────────────────────────────


def test_stamp_creates_record(tmp_path):
    st = ImmutableStamp(root=ROOT, stamps_file=tmp_path / "stamps.json")
    record = st.stamp("A-01", FAKE_SHA, "cold_start/cold_start_manager.py")
    assert isinstance(record, StampRecord)
    assert record.module_id == "A-01"
    assert record.sha256 == FAKE_SHA
    assert record.hmac_sig != ""


def test_stamp_persisted(tmp_path):
    sf = tmp_path / "stamps.json"
    st = ImmutableStamp(root=ROOT, stamps_file=sf)
    st.stamp("A-01", FAKE_SHA)
    assert sf.exists()
    data = json.loads(sf.read_text())
    assert "A-01" in data


def test_stamp_from_disk_real_file(tmp_path):
    st = ImmutableStamp(root=ROOT, stamps_file=tmp_path / "stamps.json")
    record = st.stamp_from_disk("G-01", "certification/module_certifier.py")
    assert len(record.sha256) == 64
    assert record.hmac_sig != ""


# ── Tests verify ─────────────────────────────────────────────────────────────


def test_verify_ok_without_source(tmp_path):
    st = ImmutableStamp(root=ROOT, stamps_file=tmp_path / "stamps.json")
    st.stamp("A-01", FAKE_SHA)
    ok, reason = st.verify("A-01")
    assert ok
    assert reason is None


def test_verify_detects_tampered_signature(tmp_path):
    sf = tmp_path / "stamps.json"
    st = ImmutableStamp(root=ROOT, stamps_file=sf)
    st.stamp("A-01", FAKE_SHA)
    data = json.loads(sf.read_text())
    data["A-01"]["hmac_sig"] = "bad_sig"
    sf.write_text(json.dumps(data))
    ok, reason = st.verify("A-01")
    assert not ok
    assert "invalide" in (reason or "")


def test_verify_detects_drift_on_real_file(tmp_path, tmp_path_factory):
    # Crée un fichier temporaire, le stampe, puis le modifie
    fake_file = tmp_path / "fake_module.py"
    fake_file.write_text("# original")
    st = ImmutableStamp(root=tmp_path, stamps_file=tmp_path / "stamps.json")
    record = st.stamp_from_disk("X-01", "fake_module.py")
    fake_file.write_text("# modified")
    ok, reason = st.verify("X-01")
    assert not ok
    assert "DRIFT" in (reason or "")


def test_verify_missing_module_returns_false(tmp_path):
    st = ImmutableStamp(root=ROOT, stamps_file=tmp_path / "stamps.json")
    ok, reason = st.verify("Z-99")
    assert not ok


# ── Tests verify_all ─────────────────────────────────────────────────────────


def test_verify_all_returns_dict(tmp_path):
    st = ImmutableStamp(root=ROOT, stamps_file=tmp_path / "stamps.json")
    for mid in ["A-01", "F-01", "G-01"]:
        st.stamp(mid, FAKE_SHA)
    results = st.verify_all()
    assert set(results.keys()) == {"A-01", "F-01", "G-01"}


def test_count_tracks_stamps(tmp_path):
    st = ImmutableStamp(root=ROOT, stamps_file=tmp_path / "stamps.json")
    assert st.count() == 0
    st.stamp("A-01", FAKE_SHA)
    st.stamp("A-02", FAKE_SHA)
    assert st.count() == 2


# ── Tests record roundtrip ────────────────────────────────────────────────────


def test_stamp_record_roundtrip():
    r = StampRecord("A-01", "cold_start/cold_start_manager.py", FAKE_SHA, "sig123")
    r2 = StampRecord.from_dict(r.to_dict())
    assert r2.module_id == r.module_id
    assert r2.sha256 == r.sha256
    assert r2.hmac_sig == r.hmac_sig
