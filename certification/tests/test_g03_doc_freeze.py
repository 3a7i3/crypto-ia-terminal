"""Tests G-03 — DocFreeze (10 tests)"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from certification.doc_freeze import DocFreeze, DocRecord, FreezeManifest

ROOT = Path(__file__).parent.parent.parent


# ── Tests freeze ─────────────────────────────────────────────────────────────


def test_freeze_creates_manifest(tmp_path):
    df = DocFreeze(root=ROOT, freeze_file=tmp_path / "freeze.json")
    manifest = df.freeze()
    assert isinstance(manifest, FreezeManifest)
    assert len(manifest.docs) > 0
    assert manifest.signature != ""


def test_freeze_persists_to_file(tmp_path):
    freeze_file = tmp_path / "freeze.json"
    df = DocFreeze(root=ROOT, freeze_file=freeze_file)
    df.freeze()
    assert freeze_file.exists()


def test_freeze_includes_arborescence(tmp_path):
    df = DocFreeze(root=ROOT, freeze_file=tmp_path / "freeze.json")
    manifest = df.freeze()
    paths = [d.path for d in manifest.docs]
    assert "ARBORESCENCE.md" in paths


def test_freeze_includes_plan(tmp_path):
    df = DocFreeze(root=ROOT, freeze_file=tmp_path / "freeze.json")
    manifest = df.freeze()
    paths = [d.path for d in manifest.docs]
    assert "certification/PLAN.md" in paths


# ── Tests verify ─────────────────────────────────────────────────────────────


def test_verify_ok_after_freeze(tmp_path):
    df = DocFreeze(root=ROOT, freeze_file=tmp_path / "freeze.json")
    df.freeze()
    ok, drifts = df.verify()
    assert ok
    assert drifts == []


def test_verify_fails_without_freeze(tmp_path):
    df = DocFreeze(root=ROOT, freeze_file=tmp_path / "nonexistent.json")
    ok, drifts = df.verify()
    assert not ok
    assert len(drifts) > 0


def test_verify_detects_tampered_signature(tmp_path):
    freeze_file = tmp_path / "freeze.json"
    df = DocFreeze(root=ROOT, freeze_file=freeze_file)
    df.freeze()
    data = json.loads(freeze_file.read_text())
    data["signature"] = "tampered"
    freeze_file.write_text(json.dumps(data))
    ok, drifts = df.verify()
    assert not ok
    assert any("invalide" in d for d in drifts)


def test_is_frozen_true_after_freeze(tmp_path):
    df = DocFreeze(root=ROOT, freeze_file=tmp_path / "freeze.json")
    assert not df.is_frozen()
    df.freeze()
    assert df.is_frozen()


# ── Tests manifest ────────────────────────────────────────────────────────────


def test_manifest_signature_verified(tmp_path):
    df = DocFreeze(root=ROOT, freeze_file=tmp_path / "freeze.json")
    manifest = df.freeze()
    assert manifest.verify_signature()


def test_manifest_roundtrip():
    docs = [DocRecord("test.md", "a" * 64, 100)]
    m = FreezeManifest(docs=docs)
    m.sign()
    m2 = FreezeManifest.from_dict(m.to_dict())
    assert m2.verify_signature()
    assert len(m2.docs) == 1
