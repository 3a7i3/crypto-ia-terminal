"""Tests G-01 — ModuleCertifier (12 tests)"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from certification.module_certifier import (
    _REGISTRY,
    ModuleCertificate,
    ModuleCertifier,
    ModuleSpec,
)

ROOT = Path(__file__).parent.parent.parent


# ── Tests registre ────────────────────────────────────────────────────────────


def test_registry_has_41_modules():
    assert len(_REGISTRY) == 41


def test_registry_covers_all_phases():
    phases = {mid.split("-")[0] for mid in _REGISTRY}
    assert phases == {"A", "B", "C", "D", "E", "F", "G"}


def test_g_modules_self_reference():
    assert "G-01" in _REGISTRY
    assert _REGISTRY["G-01"].source_path == "certification/module_certifier.py"


# ── Tests certify dry-run ─────────────────────────────────────────────────────


def test_certify_dry_run_a01(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    cert = mc.certify("A-01", dry_run=True)
    assert cert.module_id == "A-01"
    assert cert.tests_passed
    assert cert.sha256 != ""
    assert cert.dry_run


def test_certify_saves_json(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    mc.certify("F-01", dry_run=True)
    cert_file = tmp_path / "F-01.json"
    assert cert_file.exists()
    data = json.loads(cert_file.read_text())
    assert data["module_id"] == "F-01"


def test_certify_unknown_module_raises(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    with pytest.raises(ValueError, match="inconnu"):
        mc.certify("Z-99")


# ── Tests sceau ───────────────────────────────────────────────────────────────


def test_seal_contains_module_id(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    cert = mc.certify("A-01", dry_run=True)
    seal = cert.seal()
    assert "A-01" in seal
    assert "COMPLETED" in seal
    assert "CYBERTECHNIQUE" in seal


def test_seal_contains_date(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    cert = mc.certify("A-01", dry_run=True)
    seal = cert.seal()
    assert cert.certified_date in seal


# ── Tests load / is_certified ─────────────────────────────────────────────────


def test_load_returns_none_if_not_certified(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    assert mc.load("A-01") is None


def test_is_certified_true_after_certify(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    mc.certify("G-01", dry_run=True)
    assert mc.is_certified("G-01")


def test_certify_all_dry_run(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    results = mc.certify_all(dry_run=True)
    assert len(results) == len(_REGISTRY)
    passed = [r for r in results.values() if r.tests_passed]
    assert len(passed) >= 35  # la plupart des fichiers existent


# ── Tests from_dict roundtrip ─────────────────────────────────────────────────


def test_certificate_roundtrip(tmp_path):
    mc = ModuleCertifier(root=ROOT, cert_dir=tmp_path)
    cert = mc.certify("F-05", dry_run=True)
    cert2 = ModuleCertificate.from_dict(cert.to_dict())
    assert cert2.module_id == cert.module_id
    assert cert2.sha256 == cert.sha256
