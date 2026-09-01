from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/claude-audit-snapshot-build.py"
SPEC = importlib.util.spec_from_file_location("claude_audit_snapshot_build", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
snapshot_build = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = snapshot_build
SPEC.loader.exec_module(snapshot_build)


def _git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


class TestAuditSnapshotBuild(unittest.TestCase):
    def test_builder_is_not_exposed_by_forced_command(self):
        dispatcher = (ROOT / "scripts/claude-audit-dispatch").read_text(
            encoding="utf-8"
        )
        self.assertIn("export GIT_OPTIONAL_LOCKS=0\n", dispatcher)
        self.assertNotIn("claude-audit-snapshot-build", dispatcher)

    def _source_repo(self, directory: Path) -> Path:
        repo = directory / "source"
        repo.mkdir()
        _git(repo, "init", "--initial-branch=main")
        _git(repo, "config", "user.name", "Snapshot Test")
        _git(repo, "config", "user.email", "snapshot@example.invalid")
        (repo / "README.md").write_text("scientific source\n", encoding="utf-8")
        executable = repo / "tool.sh"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        _git(repo, "add", "README.md", "tool.sh")
        _git(repo, "commit", "-m", "initial snapshot source")
        return repo

    def _config(self, directory: Path, source: Path):
        return snapshot_build.SnapshotConfig(
            base_dir=directory / "audit",
            source_url=str(source),
            snapshot_uid=os.getuid(),
            snapshot_gid=os.getgid(),
            audit_uid=os.getuid(),
            audit_gid=os.getgid(),
            audit_owner="test-owner",
            audit_group="test-group",
            builder_path=SCRIPT,
            lock_path=directory / "snapshot.lock",
            allow_file_protocol=True,
        )

    def test_builds_clean_read_only_snapshot_and_manifest(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._source_repo(directory)
            source_sha = _git(source, "rev-parse", "HEAD")
            config = self._config(directory, source)

            result = snapshot_build.build_snapshot(
                config,
                source_sha,
                moment=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(_git(config.target, "rev-parse", "HEAD"), source_sha)
            self.assertEqual(_git(config.target, "branch", "--show-current"), "main")
            self.assertEqual(
                _git(config.target, "rev-parse", "refs/remotes/origin/main"),
                source_sha,
            )
            self.assertEqual(_git(config.target, "status", "--porcelain=v1"), "")
            self.assertEqual(result.previous_snapshot_path, None)

            manifest = config.manifest.read_text(encoding="utf-8")
            self.assertIn("schema_version=1\n", manifest)
            self.assertIn(f"source_sha={source_sha}\n", manifest)
            self.assertIn("worktree_clean=true\n", manifest)
            self.assertIn("sanitized_paths_count=0\n", manifest)
            self.assertIn("production_runtime_source_accessed=false\n", manifest)

            readme_mode = stat.S_IMODE((config.target / "README.md").stat().st_mode)
            tool_mode = stat.S_IMODE((config.target / "tool.sh").stat().st_mode)
            self.assertEqual(readme_mode, 0o440)
            self.assertEqual(tool_mode, 0o550)
            self.assertEqual(
                (config.target / "README.md").stat().st_uid,
                config.snapshot_uid,
            )

    def test_rebuild_preserves_previous_snapshot_and_manifest(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._source_repo(directory)
            config = self._config(directory, source)
            first_sha = _git(source, "rev-parse", "HEAD")
            snapshot_build.build_snapshot(
                config,
                first_sha,
                moment=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
            )

            (source / "README.md").write_text("second source\n", encoding="utf-8")
            _git(source, "add", "README.md")
            _git(source, "commit", "-m", "second snapshot source")
            second_sha = _git(source, "rev-parse", "HEAD")

            result = snapshot_build.build_snapshot(
                config,
                second_sha,
                moment=datetime(2026, 9, 1, 12, 1, tzinfo=timezone.utc),
            )

            self.assertEqual(_git(config.target, "rev-parse", "HEAD"), second_sha)
            self.assertIsNotNone(result.previous_snapshot_path)
            self.assertIsNotNone(result.previous_manifest_path)
            assert result.previous_snapshot_path is not None
            assert result.previous_manifest_path is not None
            self.assertEqual(
                _git(result.previous_snapshot_path, "rev-parse", "HEAD"), first_sha
            )
            self.assertIn(
                f"source_sha={first_sha}\n",
                result.previous_manifest_path.read_text(encoding="utf-8"),
            )

    def test_invalid_sha_cannot_replace_existing_target(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._source_repo(directory)
            config = self._config(directory, source)
            config.base_dir.mkdir()
            config.target.mkdir()
            sentinel = config.target / "sentinel"
            sentinel.write_text("preserve me\n", encoding="utf-8")

            with self.assertRaisesRegex(
                snapshot_build.SnapshotBuildError, "exactly 40"
            ):
                snapshot_build.build_snapshot(config, "main")

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me\n")

    def test_tracked_symlink_fails_before_replacing_existing_target(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            source = self._source_repo(directory)
            symlink = source / "escape-link"
            symlink.symlink_to("/etc/passwd")
            _git(source, "add", "escape-link")
            _git(source, "commit", "-m", "add forbidden symlink")
            source_sha = _git(source, "rev-parse", "HEAD")
            config = self._config(directory, source)
            config.base_dir.mkdir()
            config.target.mkdir()
            sentinel = config.target / "sentinel"
            sentinel.write_text("old snapshot\n", encoding="utf-8")

            with self.assertRaisesRegex(
                snapshot_build.SnapshotBuildError, "tracked symlink"
            ):
                snapshot_build.build_snapshot(config, source_sha)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "old snapshot\n")


if __name__ == "__main__":
    unittest.main()
