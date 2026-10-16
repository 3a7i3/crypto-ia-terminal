"""Security boundary tests. Never mutate services or exercise a privileged install."""

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from scripts.activate_workboard_frontend import SOURCE_SHA, verified_files
from scripts import activate_workboard_frontend as release


def test_harness_cleanup_targets_only_its_registered_helper(tmp_path):
    """An unrelated worker must survive test cleanup, even with the same code."""
    target = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (tmp_path / "helper-pids").write_text(str(target.pid) + "\n")
        driver = Path(__file__).parent / "workboard_frontend_block" / "drive.py"
        subprocess.run(
            [sys.executable, str(driver), "cleanup"],
            env={**os.environ, "SBX": str(tmp_path)},
            check=True,
            timeout=5,
        )
        assert target.wait(timeout=5) == -9
        assert unrelated.poll() is None
    finally:
        for proc in (target, unrelated):
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)


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


def read_only_command(*args):
    """Only the NeedDaemonReload read is allowed; any mutation fails the test."""
    if args[:2] == ("systemctl", "show") and "--property=NeedDaemonReload" in args:
        return "no\n"
    pytest.fail(f"Unexpected service mutation: {args}")


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
    monkeypatch.setattr(release, "command", read_only_command)
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


def test_release_pins_and_dropin_ordering():
    assert len(SOURCE_SHA) == 40 and release.RELEASE.name == SOURCE_SHA
    assert "bdca77f9bcf306c17846985faef870844fdd1334" in release.PREVIOUS
    # The new drop-in must sort after the one it supersedes, and must not collide with it.
    assert release.DROPIN.name != release.PREVIOUS_DROPIN
    assert release.DROPIN.name > release.PREVIOUS_DROPIN


# --- v5: NeedDaemonReload guards, atomic drop-in, counted restore --------------------------------


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    dropdir = tmp_path / "web.service.d"
    dropdir.mkdir()
    (tmp_path / "releases").mkdir()
    monkeypatch.setattr(release, "DROPIN", dropdir / "99-workboard2.conf")
    monkeypatch.setattr(release, "RELEASE", tmp_path / "releases" / SOURCE_SHA)
    return dropdir


@pytest.mark.parametrize("value", ["yes", "", "maybe", "No"])
def test_pending_daemon_reload_refuses_before_any_mutation(monkeypatch, value):
    calls = []

    def command(*args):
        calls.append(args)
        if "--property=NeedDaemonReload" in args:
            return value + "\n" if args[2] != release.WEB else "no\n"
        pytest.fail(f"mutation: {args}")

    monkeypatch.setattr(release, "command", command)
    with pytest.raises(ValueError, match="NEED_DAEMON_RELOAD_PENDING"):
        release.assert_no_pending_reload("NEED_DAEMON_RELOAD_PENDING")
    # every guarded unit is read: manager-wide daemon-reload would apply a pending change to any of them
    assert {c[2] for c in calls} == set(release.RELOAD_GUARDED)


def test_pending_reload_on_web_alone_also_refuses(monkeypatch):
    monkeypatch.setattr(
        release,
        "command",
        lambda *a: "yes\n" if a[2] == release.WEB else "no\n",
    )
    with pytest.raises(ValueError, match="NEED_DAEMON_RELOAD_PENDING"):
        release.assert_no_pending_reload("NEED_DAEMON_RELOAD_PENDING")


def test_dropin_is_complete_or_absent_and_never_replaced(sandbox, monkeypatch):
    content = "[Service]\nWorkingDirectory=/x\n"
    release.link_dropin_atomic(content)
    assert release.DROPIN.read_text() == content
    assert oct(release.DROPIN.stat().st_mode & 0o777) == "0o644"
    assert not release.dropin_tmp().exists()
    assert not release.dropin_tmp().name.endswith(".conf")
    assert release.DROPIN.stat().st_nlink == 1
    with pytest.raises(FileExistsError):
        release.link_dropin_atomic("other")
    assert release.DROPIN.read_text() == content


def test_failure_while_writing_leaves_neither_dropin_nor_temp(sandbox, monkeypatch):
    def broken_fsync(_fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(release.os, "fsync", broken_fsync)
    with pytest.raises(OSError, match="injected"):
        release.link_dropin_atomic("[Service]\n")
    assert list(sandbox.iterdir()) == []


def test_restore_counts_every_failure_and_keeps_going(sandbox, monkeypatch):
    release.DROPIN.write_text("x")
    calls = []

    def command(*args):
        calls.append(args)
        if "reload" in args[1] and args[1] == "daemon-reload":
            raise OSError("reload refused")
        if args[1] == "restart":
            raise OSError("restart refused")
        return "no\n"

    monkeypatch.setattr(release, "command", command)
    monkeypatch.setattr(release, "web_directory", lambda: "/elsewhere")
    failures = release.restore_previous(created=True)
    assert not release.DROPIN.exists()  # removal happened despite later failures
    names = [f.split(":")[0] for f in failures]
    assert names == [
        "daemon_reload",
        "restart_web",
        "web_directory_after",
    ]
    assert [c[1] for c in calls if c[1] in ("daemon-reload", "restart")] == [
        "daemon-reload",
        "restart",
    ]


def test_restore_does_not_touch_a_file_it_did_not_create(sandbox, monkeypatch):
    release.DROPIN.write_text("operator file")
    monkeypatch.setattr(release, "command", lambda *a: "no\n")
    monkeypatch.setattr(release, "web_directory", lambda: release.PREVIOUS)
    assert release.restore_previous(created=False) == []
    assert release.DROPIN.read_text() == "operator file"


def test_restore_restarts_web_only_when_new_config_was_loaded(sandbox, monkeypatch):
    seen = []
    monkeypatch.setattr(
        release, "command", lambda *a: (seen.append(a[1]) or "no\n")
    )
    state = {"wd": release.PREVIOUS}
    monkeypatch.setattr(release, "web_directory", lambda: state["wd"])
    assert release.restore_previous(created=False) == []
    assert "restart" not in seen
    seen.clear()
    state["wd"] = "/new"

    def reload_resets(*a):
        seen.append(a[1])
        if a[1] == "daemon-reload":
            state["wd"] = release.PREVIOUS
        return "no\n"

    monkeypatch.setattr(release, "command", reload_resets)
    assert release.restore_previous(created=False) == []
    assert "restart" in seen


@pytest.mark.parametrize("fail_restart", [False, True])
def test_activation_failure_restores_and_reports_counted_failures(
    sandbox, tmp_path, monkeypatch, capsys, fail_restart
):
    files = {
        "frontend/dist/index.html": b"<html>x</html>",
        "frontend/scripts/web01_local_frontend_server.mjs": b"s",
    }
    manifest = {
        "source_sha": SOURCE_SHA,
        "scope": "FRONTEND_ONLY",
        "source_merge_sha": "a" * 40,
        "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()},
    }
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for name, data in {"manifest.json": json.dumps(manifest).encode(), **files}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    raw = out.getvalue()
    package = tmp_path / "p.tar.gz"
    package.write_bytes(raw)
    state = {"wd": release.PREVIOUS}
    log = []

    def command(*args):
        log.append(args[1:3])
        if args[1] == "show" and "--property=NeedDaemonReload" in args:
            return "no\n"
        if args[1] == "daemon-reload" and release.DROPIN.exists():
            state["wd"] = "/new"
        elif args[1] == "daemon-reload":
            state["wd"] = release.PREVIOUS
        if args[1] == "restart" and fail_restart:
            raise OSError("restart refused")
        return ""

    monkeypatch.setattr(release, "command", command)
    monkeypatch.setattr(release, "web_directory", lambda: state["wd"])
    monkeypatch.setattr(
        release,
        "service_state",
        lambda _: {"ActiveState": "active", "SubState": "running"},
    )
    monkeypatch.setattr(release.os, "readlink", lambda _: "cur")
    monkeypatch.setattr(release.os, "geteuid", lambda: 0)
    monkeypatch.setattr(release, "fsync_dir", lambda _p: None)

    def failing_verify(_files):
        raise ValueError("SERVED_ASSET_HASH_MISMATCH")

    monkeypatch.setattr(release, "verify_served", failing_verify)
    monkeypatch.setattr(release.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        release.os.sys,
        "argv",
        ["s", "--archive", str(package), "--sha256", hashlib.sha256(raw).hexdigest(), "--activate"],
    )
    with pytest.raises((ValueError, OSError), match="SERVED_ASSET_HASH_MISMATCH|restart refused"):
        release.main()
    report = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert not release.DROPIN.exists() and not release.dropin_tmp().exists()
    assert release.RELEASE.exists()  # kept for forensics
    if fail_restart:
        # the first activation restart also fails: the original error wins, restore is reported as counted failure
        assert report["restore"] == "INCOMPLETE" and report["failure_count"] >= 1
        assert report["failures"][0].startswith("restart_web")
    else:
        assert report["restore"] == "OK" and report["failure_count"] == 0
        assert state["wd"] == release.PREVIOUS


def test_restore_never_reloads_when_nothing_was_mutated(sandbox, monkeypatch):
    seen = []
    monkeypatch.setattr(release, "command", lambda *a: (seen.append(a[1]) or "no\n"))
    monkeypatch.setattr(release, "web_directory", lambda: release.PREVIOUS)
    assert release.restore_previous(created=False) == []
    assert "daemon-reload" not in seen and "restart" not in seen


def test_restore_refuses_to_reload_a_foreign_pending_change(sandbox, monkeypatch):
    release.DROPIN.write_text("ours")
    seen = []

    def command(*a):
        seen.append(a[1])
        return "yes\n" if a[2:3] == ("crypto-advisor.service",) else "no\n"

    monkeypatch.setattr(release, "command", command)
    monkeypatch.setattr(release, "web_directory", lambda: release.PREVIOUS)
    failures = release.restore_previous(created=True)
    assert not release.DROPIN.exists()  # our own file is still removed
    assert "daemon-reload" not in seen and "restart" not in seen
    assert failures[0].startswith("daemon_reload_skipped_foreign_pending")


def test_restore_leaves_a_foreign_temp_file_alone(sandbox, monkeypatch):
    release.dropin_tmp().write_text("foreign")
    monkeypatch.setattr(release, "command", lambda *a: "no\n")
    monkeypatch.setattr(release, "web_directory", lambda: release.PREVIOUS)
    release.restore_previous(created=False, tmp_owned=False)
    assert release.dropin_tmp().read_text() == "foreign"
    # and the writer itself refuses to reuse it
    with pytest.raises(FileExistsError):
        release.link_dropin_atomic("x", owned=[])
    assert release.dropin_tmp().read_text() == "foreign"
