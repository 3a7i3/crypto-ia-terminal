"""Security boundary tests. Never mutate services or exercise a privileged install."""

import hashlib
import io
import json
import tarfile

import pytest

from scripts.activate_workboard_frontend import SOURCE_SHA, verified_files
from scripts import activate_workboard_frontend as release


def archive(extra=None, merge=None):
    files = {
        "frontend/dist/index.html": b"<html>fixture</html>",
        "frontend/scripts/web01_local_frontend_server.mjs": b"fixture-only",
    }
    manifest = {
        "source_sha": SOURCE_SHA,
        "scope": "FRONTEND_ONLY",
        "source_merge_sha": merge,
        "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()},
    }
    files["manifest.json"] = json.dumps(manifest).encode()
    if extra:
        files.update(extra)
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    raw = out.getvalue()
    return raw, hashlib.sha256(raw).hexdigest()


def test_unmerged_package_can_be_inspected_without_activating():
    raw, sha = archive()
    manifest, files = verified_files(raw, sha)
    assert manifest["source_merge_sha"] is None
    assert set(files) == {
        "frontend/dist/index.html",
        "frontend/scripts/web01_local_frontend_server.mjs",
    }


@pytest.mark.parametrize(
    "name",
    ["../escape", "/etc/override", "frontend/dist/../../escape", "backend/app.py"],
)
def test_files_outside_frontend_boundary_are_refused(name):
    raw, sha = archive({name: b"bad"})
    with pytest.raises(ValueError, match="UNSAFE_ARCHIVE_MEMBER"):
        verified_files(raw, sha)


def test_hash_substitution_is_refused():
    raw, _ = archive()
    with pytest.raises(ValueError, match="ARCHIVE_HASH_OR_SIZE_MISMATCH"):
        verified_files(raw, "0" * 64)


def test_undeclared_frontend_asset_is_refused():
    raw, sha = archive({"frontend/dist/extra.js": b"bad"})
    with pytest.raises(ValueError, match="MANIFEST_MEMBERS_MISMATCH"):
        verified_files(raw, sha)


def test_activate_refuses_unmerged_source_before_any_install(tmp_path, monkeypatch):
    raw, sha = archive()
    package = tmp_path / "package.tar.gz"
    package.write_bytes(raw)
    target = tmp_path / "uncreated-release"
    monkeypatch.setattr(release, "RELEASE", target)
    monkeypatch.setattr(release, "DROPIN", tmp_path / "uncreated-override")
    monkeypatch.setattr(
        release,
        "service_state",
        lambda _: {"ActiveState": "active", "SubState": "running"},
    )
    monkeypatch.setattr(release, "web_directory", lambda: release.PREVIOUS)
    monkeypatch.setattr(release.os, "readlink", lambda _: "previous-link")
    monkeypatch.setattr(
        release, "command", lambda *args: pytest.fail("Unexpected service mutation")
    )
    monkeypatch.setattr(
        release.os.sys,
        "argv",
        ["script", "--archive", str(package), "--sha256", sha, "--activate"],
    )
    with pytest.raises(ValueError, match="MERGED_SOURCE_GATE_MISSING"):
        release.main()
    assert not target.exists()


def test_builder_output_is_deterministic_and_accepted_by_verifier(tmp_path):
    import subprocess

    from scripts.build_workboard_frontend_package import build

    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "frontend/dist").mkdir(parents=True)
    (tmp_path / "frontend/scripts").mkdir()
    (tmp_path / "frontend/dist/index.html").write_bytes(b"<html></html>")
    (tmp_path / "frontend/scripts/web01_local_frontend_server.mjs").write_bytes(b"x")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "fixture")
    first, manifest = build(tmp_path, None)
    assert build(tmp_path, None)[0] == first
    assert manifest["files"].keys() == {
        "frontend/dist/index.html",
        "frontend/scripts/web01_local_frontend_server.mjs",
    }
    (tmp_path / "frontend/dist/index.html").write_bytes(b"changed")
    with pytest.raises(ValueError, match="DIRTY_FRONTEND_CHECKOUT"):
        build(tmp_path, None)
