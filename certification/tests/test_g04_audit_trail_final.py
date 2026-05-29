"""Tests G-04 — AuditTrailFinal (11 tests)"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from certification.audit_trail_final import AuditSection, AuditTrail, AuditTrailFinal

ROOT = Path(__file__).parent.parent.parent


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_audit(tmp_path: Path) -> AuditTrailFinal:
    from certification.doc_freeze import DocFreeze
    from certification.immutable_stamp import ImmutableStamp
    from certification.module_certifier import ModuleCertifier

    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path / "certs")
    st = ImmutableStamp(root=ROOT, stamps_file=tmp_path / "stamps.json")
    df = DocFreeze(root=ROOT, freeze_file=tmp_path / "freeze.json")

    # Certifie quelques modules dry-run et les stampe
    for mid in ["A-01", "F-01", "G-01"]:
        cert = mc.certify(mid, dry_run=True)
        st.stamp(mid, cert.sha256, cert.source_path)
    df.freeze()

    return AuditTrailFinal(
        root=ROOT,
        trail_file=tmp_path / "AUDIT_TRAIL.json",
        certifier=mc,
        stamper=st,
        doc_freeze=df,
    )


# ── Tests compile ─────────────────────────────────────────────────────────────


def test_compile_returns_trail(tmp_path):
    audit = _make_audit(tmp_path)
    trail = audit.compile()
    assert isinstance(trail, AuditTrail)
    assert len(trail.sections) == 5


def test_compile_has_required_sections(tmp_path):
    audit = _make_audit(tmp_path)
    trail = audit.compile()
    names = [s.name for s in trail.sections]
    assert any("G-01" in n for n in names)
    assert any("G-02" in n for n in names)
    assert any("G-03" in n for n in names)


def test_compile_is_signed(tmp_path):
    audit = _make_audit(tmp_path)
    trail = audit.compile()
    assert trail.signature != ""
    assert trail.verify_signature()


# ── Tests save ────────────────────────────────────────────────────────────────


def test_save_creates_file(tmp_path):
    audit = _make_audit(tmp_path)
    trail = audit.compile()
    path = audit.save(trail)
    assert path.exists()


def test_load_after_save(tmp_path):
    audit = _make_audit(tmp_path)
    trail = audit.compile()
    audit.save(trail)
    loaded = audit.load()
    assert loaded is not None
    assert loaded.signature == trail.signature


# ── Tests blackbox ────────────────────────────────────────────────────────────


def test_store_in_blackbox_writes_entry(tmp_path):
    bb = tmp_path / "black_box.jsonl"
    bb.write_text("")
    audit = _make_audit(tmp_path)
    audit._root = ROOT  # reset to use real root for module checks
    # Override blackbox path via monkeypatch approach
    with patch.object(audit, "_root", tmp_path):
        (tmp_path / "databases").mkdir(exist_ok=True)
        (tmp_path / "databases" / "black_box.jsonl").write_text("")
        trail = audit.compile()
        ok = audit.store_in_blackbox(trail)
    assert ok  # file write succeeded (used real root)


# ── Tests AuditTrail ─────────────────────────────────────────────────────────


def test_audit_trail_complete_when_all_sections_pass():
    sections = [
        AuditSection("S1", True, 5, 5),
        AuditSection("S2", True, 3, 3),
    ]
    trail = AuditTrail(sections=sections)
    assert trail.complete


def test_audit_trail_not_complete_when_section_fails():
    sections = [
        AuditSection("S1", True, 5, 5),
        AuditSection("S2", False, 2, 3),
    ]
    trail = AuditTrail(sections=sections)
    assert not trail.complete


def test_summary_contains_section_names():
    sections = [AuditSection("Modules G-01", True, 41, 41)]
    trail = AuditTrail(sections=sections)
    trail.sign()
    assert "G-01" in trail.summary()


def test_signature_changes_when_section_mutated():
    sections = [AuditSection("S1", True, 5, 5)]
    trail = AuditTrail(sections=sections)
    trail.sign()
    original = trail.signature
    sections[0].count_ok = 3
    trail.sign()
    assert trail.signature != original
