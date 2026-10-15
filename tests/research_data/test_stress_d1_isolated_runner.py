"""Synthetic source custody and isolated invocation; never a real capture audit."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from research_data import stress_d1_isolated_runner as runner
from research_data import stress_d1_rejection_eligibility as eligibility

SOURCE = Path(runner.__file__).parent


@pytest.fixture
def sources(tmp_path, monkeypatch):
    root = tmp_path / "readonly_d1_c_source"
    root.mkdir()
    for name in (runner.HISTORICAL, runner.CLASSIFIER):
        (root / name).write_bytes((SOURCE / name).read_bytes())
        (root / name).chmod(0o444)
    root.chmod(0o555)
    # CI is non-root and tmp ancestors are writable. This synthetic seam only
    # replaces directory custody; production CLI has no override for it.
    monkeypatch.setattr(runner, "_custody", lambda path: None)
    original_fstat = runner.os.fstat

    def fixture_stat(fd):
        value = original_fstat(fd)
        return types.SimpleNamespace(**{name: (0 if name == "st_uid" else getattr(value, name))
                                       for name in ("st_uid", "st_mode", "st_size", "st_dev",
                                                    "st_ino", "st_mtime_ns")})

    monkeypatch.setattr(runner.os, "fstat", fixture_stat)
    digest = hashlib.sha256((root / runner.CLASSIFIER).read_bytes()).hexdigest()
    yield root, digest
    root.chmod(0o755)
    for path in root.iterdir():
        path.chmod(0o644)


def test_exact_verified_bytes_loaded(sources):
    root, digest = sources
    module = runner._load_sources(root, digest)
    proof = module._source_verifier()
    assert proof["script_sha256"] == digest
    assert proof["historical_d1_auditor_sha256"] == runner.HISTORICAL_SHA256
    assert module.d1.__file__ == str(root / runner.HISTORICAL)
    assert module.__spec__.origin == str(root / runner.CLASSIFIER)
    assert module.VERSION == "D1_C_V2"


@pytest.mark.parametrize("mutation", ["substitute", "file", "origin", "hash", "classifier_hash"])
def test_source_failure_precedes_any_data_read(sources, monkeypatch, mutation):
    root, digest = sources
    module = runner._load_sources(root, digest)
    reads = []
    monkeypatch.setattr(module, "_read", lambda *args: reads.append(args))
    monkeypatch.setattr(module.d1, "audit", lambda *args: reads.append(args))
    if mutation == "substitute":
        module.d1 = types.SimpleNamespace()
    elif mutation == "file":
        module.d1.__file__ = str(root / "other.py")
    elif mutation == "origin":
        module.d1.__spec__.origin = str(root / "other.py")
    else:
        path = root / (runner.HISTORICAL if mutation == "hash" else runner.CLASSIFIER)
        path.chmod(0o644)
        path.write_bytes(path.read_bytes() + b"\n# substituted\n")
        path.chmod(0o444)
    result = module.audit(Path("/unavailable/readonly_research_staging"))
    assert result["status"] == "D1_C_INTEGRITY_FAILURE"
    assert result["classification"] == "NOT_EMITTED"
    assert not reads


@pytest.mark.parametrize("name", [runner.HISTORICAL, runner.CLASSIFIER])
def test_wrong_digest_rejected_before_execution(sources, name):
    root, digest = sources
    path = root / name
    path.chmod(0o644)
    path.write_bytes(b"raise AssertionError('unverified code executed')\n")
    path.chmod(0o444)
    with pytest.raises(runner.SourceBlocked, match="SOURCE_SHA256_MISMATCH"):
        runner._load_sources(root, digest)


def test_wrong_expected_classifier_hash(sources):
    root, _ = sources
    with pytest.raises(runner.SourceBlocked, match="SOURCE_SHA256_MISMATCH"):
        runner._load_sources(root, "0" * 64)


def test_symlink_source_refused(sources):
    root, digest = sources
    root.chmod(0o755)
    path = root / runner.HISTORICAL
    path.unlink()
    path.symlink_to(SOURCE / runner.HISTORICAL)
    with pytest.raises(OSError):
        runner._load_sources(root, digest)
    path.unlink()


@pytest.mark.parametrize("path", ["relative/readonly_d1_c_source", "/home/readonly_d1_c_source",
                                  "/workspace/crypto-ia-terminal/research_data"])
def test_wrong_source_root(path):
    with pytest.raises(runner.SourceBlocked, match="AUTHORIZED_RESEARCH_SOURCE_ROOT_REQUIRED"):
        runner._custody(Path(path))


def test_package_entry_without_verified_launcher_fails_before_data(monkeypatch):
    monkeypatch.setattr(eligibility, "_read", lambda *args: pytest.fail("dataset read"))
    result = eligibility.audit(Path("/unavailable/readonly_research_staging"))
    assert result["status"] == "D1_C_INTEGRITY_FAILURE"


def test_isolated_without_package_has_explicit_standalone_entry(tmp_path):
    executable = str(SOURCE / "stress_d1_isolated_runner.py")
    missing = subprocess.run([sys.executable, "-I", "-B", "-m",
                              "research_data.stress_d1_rejection_eligibility"],
                             cwd=tmp_path, capture_output=True, text=True, check=False)
    assert missing.returncode != 0
    assert "No module named" in missing.stderr
    help_result = subprocess.run([sys.executable, "-I", "-B", executable, "--help"],
                                 cwd=tmp_path, capture_output=True, text=True, check=False)
    assert help_result.returncode == 0
    failure = subprocess.run([sys.executable, "-I", "-B", executable,
                              "--source-root", str(SOURCE), "--classifier-sha256", "0" * 64,
                              "--research-root", "/unavailable/readonly_research_staging"],
                             cwd=tmp_path, capture_output=True, text=True, check=False)
    assert failure.returncode == 2
    assert json.loads(failure.stdout)["reason_code"] == "AUTHORIZED_RESEARCH_SOURCE_ROOT_REQUIRED"


def test_isolated_loader_needs_no_package(sources, tmp_path):
    root, digest = sources
    # Synthetic subprocess bypasses only OS custody for CI's non-root tempfile.
    # It executes the real loader and hash checks, but never invokes data audit.
    harness = tmp_path / "synthetic_harness.py"
    harness.write_text('''import runpy, sys, types
namespace = runpy.run_path(sys.argv[1])
load = namespace['_load_sources']
load.__globals__['_custody'] = lambda root: None
original = namespace['os'].fstat
def fake_stat(fd):
    value = original(fd)
    return types.SimpleNamespace(**{key: (0 if key == 'st_uid' else getattr(value, key))
        for key in ('st_uid', 'st_mode', 'st_size', 'st_dev', 'st_ino', 'st_mtime_ns')})
namespace['os'].fstat = fake_stat
module = load(namespace['Path'](sys.argv[2]), sys.argv[3])
assert 'research_data' not in sys.modules
assert module._source_verifier()['historical_d1_auditor_sha256'] == namespace['HISTORICAL_SHA256']
print(module.VERSION)
''')
    result = subprocess.run([sys.executable, "-I", "-B", str(harness), str(Path(runner.__file__)),
                             str(root), digest], cwd=tmp_path, capture_output=True,
                            text=True, check=False, env={**os.environ, "PYTHONPATH": "/invalid"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "D1_C_V2"
    assert not list(root.rglob("*.pyc"))


@pytest.mark.parametrize("mode,uid", [(0o100644, 0), (0o100444, 1000), (0o040444, 0)])
def test_untrusted_source_file_custody(sources, monkeypatch, mode, uid):
    root, digest = sources
    original = runner.os.fstat

    def untrusted(fd):
        value = original(fd)
        value.st_mode, value.st_uid = mode, uid
        return value

    monkeypatch.setattr(runner.os, "fstat", untrusted)
    with pytest.raises(runner.SourceBlocked, match="IMMUTABLE_SOURCE_FILE_REQUIRED"):
        runner._source(root / runner.CLASSIFIER, digest)


@pytest.mark.parametrize("mode,uid", [(0o040777, 0), (0o040755, 1000), (0o120555, 0)])
def test_untrusted_source_directory_custody(monkeypatch, mode, uid):
    monkeypatch.setattr(Path, "lstat", lambda path: types.SimpleNamespace(st_mode=mode, st_uid=uid))
    with pytest.raises(runner.SourceBlocked, match="UNTRUSTED_SOURCE_ANCESTOR"):
        runner._custody(runner.AUTHORIZED_SOURCE_ROOT)


def test_writable_owner_source_root_refused(monkeypatch):
    monkeypatch.setattr(Path, "lstat", lambda path: types.SimpleNamespace(st_mode=0o040755, st_uid=0))
    monkeypatch.setattr(Path, "is_symlink", lambda path: False)
    monkeypatch.setattr(Path, "stat", lambda path: types.SimpleNamespace(st_mode=0o040755, st_uid=0))
    with pytest.raises(runner.SourceBlocked, match="IMMUTABLE_SOURCE_ROOT_REQUIRED"):
        runner._custody(runner.AUTHORIZED_SOURCE_ROOT)


def test_nonisolated_cli_refused(tmp_path):
    result = subprocess.run([sys.executable, str(Path(runner.__file__)),
                             "--source-root", str(runner.AUTHORIZED_SOURCE_ROOT),
                             "--classifier-sha256", "0" * 64,
                             "--research-root", "/unavailable/readonly_research_staging"],
                            cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason_code"] == "ISOLATED_NO_BYTECODE_EXECUTION_REQUIRED"
