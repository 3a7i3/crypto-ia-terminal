#!/usr/bin/env python3
"""Build a pinned, read-only audit snapshot and provenance manifest.

This is an administrator-only deployment tool.  It is deliberately separate
from ``claude-audit-dispatch`` and is never reachable through the SSH forced
command.  The production CLI accepts one value only: an exact 40-character
Git commit SHA from the fixed public GitHub repository.
"""

from __future__ import annotations

import argparse
import fcntl
import grp
import hashlib
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PRODUCTION_SOURCE_URL = "https://github.com/3a7i3/crypto-ia-terminal.git"


class SnapshotBuildError(RuntimeError):
    """Raised when a snapshot cannot be built or certified safely."""


@dataclass(frozen=True)
class SnapshotConfig:
    base_dir: Path
    source_url: str
    snapshot_uid: int
    snapshot_gid: int
    audit_uid: int
    audit_gid: int
    audit_owner: str
    audit_group: str
    builder_path: Path
    lock_path: Path
    allow_file_protocol: bool = False

    @property
    def target(self) -> Path:
        return self.base_dir / "repo"

    @property
    def manifest(self) -> Path:
        return self.base_dir / "AUDIT_MANIFEST.txt"


@dataclass(frozen=True)
class BuildResult:
    source_sha: str
    source_tree_sha: str
    manifest_path: Path
    previous_snapshot_path: Path | None
    previous_manifest_path: Path | None


def _run(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    user: int | None = None,
    group: int | None = None,
) -> str:
    try:
        completed = subprocess.run(
            list(argv),
            check=True,
            capture_output=True,
            text=True,
            env=dict(env) if env is not None else None,
            user=user,
            group=group,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise SnapshotBuildError(
            f"command failed ({exc.returncode}): {argv[0]}: {stderr or 'no stderr'}"
        ) from exc
    return completed.stdout.strip()


def _git_env(*, allow_file_protocol: bool) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C",
            "TZ": "UTC",
        }
    )
    if allow_file_protocol:
        env["GIT_ALLOW_PROTOCOL"] = "file:https"
    else:
        env["GIT_ALLOW_PROTOCOL"] = "https"
    return env


def _git(
    repo: Path,
    *args: str,
    allow_file_protocol: bool,
    user: int | None = None,
    group: int | None = None,
) -> str:
    return _run(
        [
            "/usr/bin/git",
            "--no-optional-locks",
            "-c",
            f"safe.directory={repo}",
            "-C",
            str(repo),
            *args,
        ],
        env=_git_env(allow_file_protocol=allow_file_protocol),
        user=user,
        group=group,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _assert_safe_fixed_paths(config: SnapshotConfig) -> None:
    base = config.base_dir
    if not base.is_absolute() or base == Path("/"):
        raise SnapshotBuildError("base directory must be an absolute non-root path")
    if config.target.parent != base or config.manifest.parent != base:
        raise SnapshotBuildError("snapshot paths must be direct children of the base")
    if config.target.is_symlink() or config.manifest.is_symlink():
        raise SnapshotBuildError("snapshot target and manifest must not be symlinks")


def _prepare_base(config: SnapshotConfig) -> None:
    config.base_dir.mkdir(parents=True, exist_ok=True)
    if config.base_dir.is_symlink() or not config.base_dir.is_dir():
        raise SnapshotBuildError("snapshot base must be a real directory")
    os.chown(
        config.base_dir,
        config.snapshot_uid,
        config.snapshot_gid,
        follow_symlinks=False,
    )
    os.chmod(config.base_dir, 0o750, follow_symlinks=False)


def _tracked_special_entry_counts(
    repo: Path, *, allow_file_protocol: bool
) -> tuple[int, int]:
    output = _git(
        repo,
        "ls-files",
        "--stage",
        allow_file_protocol=allow_file_protocol,
    )
    if not output:
        return 0, 0
    lines = output.splitlines()
    symlinks = sum(1 for line in lines if line.startswith("120000 "))
    gitlinks = sum(1 for line in lines if line.startswith("160000 "))
    return symlinks, gitlinks


def _make_tree_read_only(path: Path, *, uid: int, gid: int) -> None:
    """Remove write bits without following symlinks or changing Git exec bits."""

    for root, directories, files in os.walk(path, topdown=False, followlinks=False):
        root_path = Path(root)
        for name in files:
            entry = root_path / name
            if entry.is_symlink():
                raise SnapshotBuildError(f"snapshot contains a symlink: {entry}")
            current_mode = stat.S_IMODE(entry.stat().st_mode)
            readonly_mode = 0o550 if current_mode & 0o111 else 0o440
            os.chown(entry, uid, gid, follow_symlinks=False)
            os.chmod(entry, readonly_mode, follow_symlinks=False)
        for name in directories:
            entry = root_path / name
            if entry.is_symlink():
                raise SnapshotBuildError(f"snapshot contains a symlink: {entry}")
            os.chown(entry, uid, gid, follow_symlinks=False)
            os.chmod(entry, 0o550, follow_symlinks=False)
    os.chown(path, uid, gid, follow_symlinks=False)
    os.chmod(path, 0o550, follow_symlinks=False)


def _remove_generated_stage(path: Path, *, base_dir: Path) -> None:
    """Remove only the exact temporary tree created underneath ``base_dir``."""

    if path.parent != base_dir or not path.name.startswith(".snapshot-stage-"):
        raise SnapshotBuildError("refusing to remove a non-staging path")
    for root, directories, files in os.walk(path, topdown=False, followlinks=False):
        root_path = Path(root)
        for name in files:
            entry = root_path / name
            if not entry.is_symlink():
                os.chmod(entry, 0o600, follow_symlinks=False)
        for name in directories:
            entry = root_path / name
            if not entry.is_symlink():
                os.chmod(entry, 0o700, follow_symlinks=False)
        os.chmod(root_path, 0o700, follow_symlinks=False)
    shutil.rmtree(path)


def _write_manifest_temp(
    config: SnapshotConfig,
    *,
    moment: datetime,
    source_sha: str,
    source_tree_sha: str,
    source_commit_time: str,
    tracked_file_count: int,
    previous_snapshot_path: Path | None,
) -> Path:
    fd, name = tempfile.mkstemp(prefix=".AUDIT_MANIFEST.", dir=config.base_dir)
    path = Path(name)
    previous = str(previous_snapshot_path) if previous_snapshot_path else "none"
    fields = [
        ("schema_version", "1"),
        ("snapshot_format", "git_worktree"),
        ("snapshot_path", str(config.target)),
        ("created_at_utc", _iso(moment)),
        ("source_kind", "github_commit"),
        ("source_repository", config.source_url),
        ("source_sha", source_sha),
        ("source_tree_sha", source_tree_sha),
        ("source_commit_time", source_commit_time),
        ("branch", "main"),
        ("remote_tracking_ref", "origin/main"),
        ("worktree_clean", "true"),
        ("tracked_file_count", str(tracked_file_count)),
        ("tracked_symlink_count", "0"),
        ("tracked_gitlink_count", "0"),
        ("sanitized_paths_count", "0"),
        ("sanitized_paths", "none"),
        ("production_runtime_source_accessed", "false"),
        ("owner", config.audit_owner),
        ("group", config.audit_group),
        ("directory_mode", "0550"),
        ("regular_file_mode", "0440"),
        ("executable_file_mode", "0550"),
        ("builder_path", str(config.builder_path)),
        ("builder_sha256", _sha256(config.builder_path)),
        ("previous_snapshot_path", previous),
    ]
    payload = "".join(f"{key}={value}\n" for key, value in fields)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(
            path,
            config.snapshot_uid,
            config.snapshot_gid,
            follow_symlinks=False,
        )
        os.chmod(path, 0o440, follow_symlinks=False)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _validate_as_auditor(config: SnapshotConfig, *, expected_sha: str) -> None:
    actual_sha = _git(
        config.target,
        "rev-parse",
        "HEAD",
        allow_file_protocol=config.allow_file_protocol,
        user=config.audit_uid,
        group=config.audit_gid,
    )
    if actual_sha != expected_sha:
        raise SnapshotBuildError("final snapshot HEAD differs from the requested SHA")

    status_output = _git(
        config.target,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        allow_file_protocol=config.allow_file_protocol,
        user=config.audit_uid,
        group=config.audit_gid,
    )
    if status_output:
        raise SnapshotBuildError("final snapshot worktree is not clean")

    branch = _git(
        config.target,
        "branch",
        "--show-current",
        allow_file_protocol=config.allow_file_protocol,
        user=config.audit_uid,
        group=config.audit_gid,
    )
    if branch != "main":
        raise SnapshotBuildError("final snapshot is not on branch main")

    remote_sha = _git(
        config.target,
        "rev-parse",
        "refs/remotes/origin/main",
        allow_file_protocol=config.allow_file_protocol,
        user=config.audit_uid,
        group=config.audit_gid,
    )
    if remote_sha != expected_sha:
        raise SnapshotBuildError("origin/main does not match the requested SHA")

    manifest_text = _run(
        ["/usr/bin/cat", str(config.manifest)],
        user=config.audit_uid,
        group=config.audit_gid,
    ) + "\n"
    if f"source_sha={expected_sha}\n" not in manifest_text:
        raise SnapshotBuildError("installed manifest does not attest the requested SHA")


def build_snapshot(
    config: SnapshotConfig,
    source_sha: str,
    *,
    moment: datetime | None = None,
) -> BuildResult:
    """Build and atomically install a certified snapshot.

    The previous snapshot and manifest are moved to timestamped backup paths.
    They are never deleted by this function.
    """

    if not SOURCE_SHA_RE.fullmatch(source_sha):
        raise SnapshotBuildError("source SHA must be exactly 40 lowercase hex characters")

    _prepare_base(config)
    _assert_safe_fixed_paths(config)
    moment = (moment or _utc_now()).astimezone(timezone.utc).replace(microsecond=0)
    stamp = _stamp(moment)
    backup_repo = config.base_dir / f"repo.pre-snapshot-{stamp}"
    backup_manifest = config.base_dir / f"AUDIT_MANIFEST.pre-snapshot-{stamp}.txt"
    failed_repo = config.base_dir / f"repo.failed-snapshot-{stamp}"
    failed_manifest = config.base_dir / f"AUDIT_MANIFEST.failed-snapshot-{stamp}.txt"

    for reserved in (backup_repo, backup_manifest, failed_repo, failed_manifest):
        if reserved.exists() or reserved.is_symlink():
            raise SnapshotBuildError(f"reserved transaction path already exists: {reserved}")

    config.lock_path.parent.mkdir(parents=True, exist_ok=True)
    with config.lock_path.open("a+", encoding="utf-8") as lock_stream:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SnapshotBuildError("another snapshot build is already running") from exc

        stage = Path(tempfile.mkdtemp(prefix=".snapshot-stage-", dir=config.base_dir))
        manifest_temp: Path | None = None
        old_repo_moved = False
        old_manifest_moved = False
        new_repo_installed = False
        new_manifest_installed = False
        try:
            _run(["/usr/bin/git", "init", "--initial-branch=main", str(stage)])
            _git(
                stage,
                "remote",
                "add",
                "origin",
                config.source_url,
                allow_file_protocol=config.allow_file_protocol,
            )
            _git(
                stage,
                "fetch",
                "--no-tags",
                "--depth=1",
                "origin",
                source_sha,
                allow_file_protocol=config.allow_file_protocol,
            )
            fetched_sha = _git(
                stage,
                "rev-parse",
                "FETCH_HEAD^{commit}",
                allow_file_protocol=config.allow_file_protocol,
            )
            if fetched_sha != source_sha:
                raise SnapshotBuildError("fetched commit does not match the requested SHA")

            _git(
                stage,
                "checkout",
                "-B",
                "main",
                source_sha,
                allow_file_protocol=config.allow_file_protocol,
            )
            _git(
                stage,
                "update-ref",
                "refs/remotes/origin/main",
                source_sha,
                allow_file_protocol=config.allow_file_protocol,
            )

            status_output = _git(
                stage,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                allow_file_protocol=config.allow_file_protocol,
            )
            if status_output:
                raise SnapshotBuildError("staged snapshot worktree is not clean")

            symlink_count, gitlink_count = _tracked_special_entry_counts(
                stage, allow_file_protocol=config.allow_file_protocol
            )
            if symlink_count:
                raise SnapshotBuildError(
                    f"snapshot contains {symlink_count} tracked symlink(s); policy requires zero"
                )
            if gitlink_count:
                raise SnapshotBuildError(
                    f"snapshot contains {gitlink_count} gitlink(s); policy requires zero"
                )

            source_tree_sha = _git(
                stage,
                "rev-parse",
                f"{source_sha}^{{tree}}",
                allow_file_protocol=config.allow_file_protocol,
            )
            source_commit_time = _git(
                stage,
                "show",
                "-s",
                "--format=%cI",
                source_sha,
                allow_file_protocol=config.allow_file_protocol,
            )
            tracked_file_count = len(
                _git(
                    stage,
                    "ls-files",
                    "-z",
                    allow_file_protocol=config.allow_file_protocol,
                ).split("\0")
            )
            if tracked_file_count and _git(
                stage,
                "ls-files",
                "-z",
                allow_file_protocol=config.allow_file_protocol,
            ).endswith("\0"):
                tracked_file_count -= 1

            _make_tree_read_only(
                stage, uid=config.snapshot_uid, gid=config.snapshot_gid
            )
            previous_snapshot_path = backup_repo if config.target.exists() else None
            manifest_temp = _write_manifest_temp(
                config,
                moment=moment,
                source_sha=source_sha,
                source_tree_sha=source_tree_sha,
                source_commit_time=source_commit_time,
                tracked_file_count=tracked_file_count,
                previous_snapshot_path=previous_snapshot_path,
            )

            if config.target.exists():
                os.replace(config.target, backup_repo)
                old_repo_moved = True
            if config.manifest.exists():
                os.replace(config.manifest, backup_manifest)
                old_manifest_moved = True

            os.replace(stage, config.target)
            new_repo_installed = True
            os.replace(manifest_temp, config.manifest)
            manifest_temp = None
            new_manifest_installed = True

            _validate_as_auditor(config, expected_sha=source_sha)

            return BuildResult(
                source_sha=source_sha,
                source_tree_sha=source_tree_sha,
                manifest_path=config.manifest,
                previous_snapshot_path=backup_repo if old_repo_moved else None,
                previous_manifest_path=backup_manifest if old_manifest_moved else None,
            )
        except Exception:
            # Preserve every material state.  A failed new snapshot is moved
            # aside and the previous paths are restored when possible.
            if new_manifest_installed and config.manifest.exists():
                os.replace(config.manifest, failed_manifest)
            if new_repo_installed and config.target.exists():
                os.replace(config.target, failed_repo)
            if old_repo_moved and backup_repo.exists():
                os.replace(backup_repo, config.target)
            if old_manifest_moved and backup_manifest.exists():
                os.replace(backup_manifest, config.manifest)
            raise
        finally:
            if manifest_temp is not None:
                manifest_temp.unlink(missing_ok=True)
            if stage.exists():
                _remove_generated_stage(stage, base_dir=config.base_dir)


def _production_config() -> SnapshotConfig:
    try:
        account = pwd.getpwnam("claude-audit")
        audit_group = grp.getgrnam("claude-audit")
    except KeyError as exc:
        raise SnapshotBuildError("claude-audit user/group is unavailable") from exc
    return SnapshotConfig(
        base_dir=Path("/srv/claude-audit"),
        source_url=PRODUCTION_SOURCE_URL,
        snapshot_uid=0,
        snapshot_gid=audit_group.gr_gid,
        audit_uid=account.pw_uid,
        audit_gid=audit_group.gr_gid,
        audit_owner="root",
        audit_group="claude-audit",
        builder_path=Path(__file__).resolve(),
        lock_path=Path("/run/lock/claude-audit-snapshot-build.lock"),
        allow_file_protocol=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a pinned read-only GitHub audit snapshot."
    )
    parser.add_argument("source_sha", help="exact 40-character lowercase Git SHA")
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        print("SNAPSHOT_BUILD_REJECTED: root authority required", file=sys.stderr)
        return 77

    try:
        result = build_snapshot(_production_config(), args.source_sha)
    except SnapshotBuildError as exc:
        print(f"SNAPSHOT_BUILD_FAILED: {exc}", file=sys.stderr)
        return 1

    print("SNAPSHOT_BUILD_OK")
    print(f"source_sha={result.source_sha}")
    print(f"source_tree_sha={result.source_tree_sha}")
    print(f"manifest={result.manifest_path}")
    print(
        "previous_snapshot="
        + (str(result.previous_snapshot_path) if result.previous_snapshot_path else "none")
    )
    print(
        "previous_manifest="
        + (str(result.previous_manifest_path) if result.previous_manifest_path else "none")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
