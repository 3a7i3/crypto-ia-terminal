from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/claude-disk-attribution.py"
SPEC = importlib.util.spec_from_file_location("claude_disk_attribution", SCRIPT)
assert SPEC and SPEC.loader
disk_attribution = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = disk_attribution
SPEC.loader.exec_module(disk_attribution)


class TestDiskAttributionAuditPack(unittest.TestCase):
    def test_catalog_is_fixed_to_root_and_first_component_buckets(self):
        self.assertEqual(disk_attribution.ROOT_PATH, "/")
        self.assertEqual(
            disk_attribution.catalog_sha256(),
            disk_attribution.catalog_sha256(),
        )

    def test_source_has_no_content_read_or_process_execution_primitive(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_names = {"open", "exec", "eval", "compile", "__import__"}
        forbidden_attributes = {
            "read", "read_text", "read_bytes", "Popen", "run", "call",
            "check_call", "check_output",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, forbidden_names)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, forbidden_attributes)
        self.assertNotIn("subprocess", source)

    def test_scan_aggregates_metadata_without_emitting_paths_or_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "var" / "log").mkdir(parents=True)
            (root / "home").mkdir()
            secret = "MUST-NOT-APPEAR"
            (root / "var" / "log" / "a.log").write_text(secret * 20, encoding="utf-8")
            (root / "home" / "b.bin").write_bytes(b"x" * 2048)
            (root / "link").symlink_to("/etc")
            with mock.patch.object(disk_attribution, "ROOT_PATH", str(root)):
                record = disk_attribution.scan_root()
            rendered = json.dumps(record)
            self.assertEqual(record["scan_status"], "complete")
            self.assertEqual(record["regular_file_count"], 2)
            self.assertEqual({item["name"] for item in record["buckets"]}, {"var", "home"})
            self.assertNotIn(secret, rendered)
            self.assertNotIn("a.log", rendered)
            self.assertNotIn("b.bin", rendered)
            self.assertNotIn("/etc", rendered)

    def test_hardlinks_are_not_double_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "var").mkdir()
            first = root / "var" / "first"
            first.write_bytes(b"z" * 100)
            os.link(first, root / "var" / "second")
            with mock.patch.object(disk_attribution, "ROOT_PATH", str(root)):
                record = disk_attribution.scan_root()
            self.assertEqual(record["regular_file_count"], 1)
            self.assertEqual(record["hardlink_duplicate_count"], 1)

    def test_entry_limit_fails_closed_as_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(4):
                (root / str(index)).write_bytes(b"x")
            with mock.patch.object(disk_attribution, "ROOT_PATH", str(root)), mock.patch.object(
                disk_attribution, "MAX_ENTRIES", 2
            ):
                record = disk_attribution.scan_root()
            self.assertEqual(record["scan_status"], "limited")
            self.assertEqual(record["limit_reason"], "entry_limit")

    def test_timeout_during_directory_iteration_marks_limited_not_complete(self):
        """Independent review, bound 1: the deadline must be enforced
        *inside* a directory's entry loop, not only between directories.
        Uses an injected fake monotonic clock -- no real sleeps."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "var").mkdir()
            for index in range(5):
                (root / "var" / f"file{index}").write_bytes(b"x" * 10)

            calls = {"n": 0}

            def fake_monotonic() -> float:
                calls["n"] += 1
                # Calls 1-5: started, outer-check(root), inner-check(var
                # entry), outer-check(var dir), inner-check(file0) --
                # all "before the deadline". Call 6 onward (inner-check
                # before file1): well past the deadline, mid-directory.
                if calls["n"] <= 5:
                    return 0.0
                return disk_attribution.SCAN_TIMEOUT_SECONDS + 1.0

            with mock.patch.object(disk_attribution, "ROOT_PATH", str(root)):
                record = disk_attribution.scan_root(monotonic=fake_monotonic)

            self.assertEqual(record["scan_status"], "limited")
            self.assertEqual(record["limit_reason"], "timeout")
            self.assertNotEqual(record["scan_status"], "complete")
            # Partial accumulation is fine (file0 processed before the
            # deadline hit) -- but not all 5 files, proving the loop was
            # actually cut short mid-directory rather than completing it.
            self.assertGreaterEqual(record["regular_file_count"], 1)
            self.assertLess(record["regular_file_count"], 5)

    def test_root_level_files_are_aggregated_never_named(self):
        """Independent review, bound 2: a regular file directly under `/`
        must never appear as its own bucket (that would disclose its real
        name) -- it must fall into a fixed synthetic [root_files] bucket.
        Directories directly under `/` keep naming their own bucket."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "home").mkdir()
            (root / "home" / "a").write_bytes(b"x" * 10)
            (root / "var").mkdir()
            (root / "var" / "b").write_bytes(b"y" * 10)
            (root / "topsecret-root-file-one.dat").write_bytes(b"z" * 10)
            (root / "another-root-file.dat").write_bytes(b"w" * 10)

            with mock.patch.object(disk_attribution, "ROOT_PATH", str(root)):
                record = disk_attribution.scan_root()
            rendered = json.dumps(record)

            bucket_names = {item["name"] for item in record["buckets"]}
            self.assertEqual(bucket_names, {"home", "var", "[root_files]"})

            root_files_bucket = next(
                item for item in record["buckets"] if item["name"] == "[root_files]"
            )
            self.assertEqual(root_files_bucket["regular_file_count"], 2)

            self.assertNotIn("topsecret-root-file-one.dat", rendered)
            self.assertNotIn("another-root-file.dat", rendered)

    def test_main_rejects_arguments_without_collecting(self):
        error = StringIO()
        with mock.patch.object(disk_attribution, "collect_snapshot") as collect:
            with redirect_stderr(error):
                exit_code = disk_attribution.main(["/caller/path"])
        self.assertEqual(exit_code, 64)
        collect.assert_not_called()
        self.assertIn("arguments are not accepted", error.getvalue())


if __name__ == "__main__":
    unittest.main()
