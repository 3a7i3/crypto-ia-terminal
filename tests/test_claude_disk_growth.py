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
SCRIPT = ROOT / "scripts/claude-disk-growth.py"
SPEC = importlib.util.spec_from_file_location("claude_disk_growth", SCRIPT)
assert SPEC and SPEC.loader
disk_growth = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = disk_growth
SPEC.loader.exec_module(disk_growth)


class TestDiskGrowthAuditPack(unittest.TestCase):
    def test_catalog_is_fixed_unique_and_runtime_scoped(self):
        self.assertEqual(
            [(item.label, item.path) for item in disk_growth.ROOT_CATALOG],
            [
                ("databases", "/home/mathieu/crypto_ai_terminal/databases"),
                ("logs", "/home/mathieu/crypto_ai_terminal/logs"),
            ],
        )
        self.assertEqual(
            len({item.label for item in disk_growth.ROOT_CATALOG}),
            len(disk_growth.ROOT_CATALOG),
        )

    def test_source_has_no_content_read_or_process_execution_primitive(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_names = {"open", "exec", "eval", "compile", "__import__"}
        forbidden_attributes = {
            "read",
            "read_text",
            "read_bytes",
            "Popen",
            "run",
            "call",
            "check_call",
            "check_output",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, forbidden_names)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, forbidden_attributes)
        self.assertNotIn("subprocess", source)

    def test_scan_reports_metadata_without_file_content_or_symlink_following(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = root / "observation"
            observation.mkdir()
            secret = "MUST-NOT-APPEAR-IN-EVIDENCE"
            (root / "root.jsonl").write_text(secret * 50, encoding="utf-8")
            (observation / "events.jsonl").write_bytes(b"x" * 2048)
            (root / "outside").symlink_to("/etc")

            spec = disk_growth.RootSpec("test_runtime", str(root))
            record, largest = disk_growth.scan_root(spec)
            rendered = json.dumps({"record": record, "largest": largest})

            self.assertEqual(record["query_status"], "ok")
            self.assertEqual(record["scan_status"], "complete")
            self.assertEqual(record["regular_file_count"], 2)
            self.assertEqual(record["logical_bytes"], len(secret * 50) + 2048)
            self.assertEqual(record["symlink_count"], 1)
            self.assertNotIn(secret, rendered)
            self.assertNotIn("/etc", rendered)
            self.assertEqual(
                {bucket["name"] for bucket in record["buckets"]},
                {"[root_files]", "observation"},
            )
            self.assertTrue(all(not item["relative_path"].startswith("/") for item in largest))

    def test_hardlinks_are_not_double_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.bin"
            first.write_bytes(b"z" * 100)
            os.link(first, root / "second.bin")
            record, _ = disk_growth.scan_root(
                disk_growth.RootSpec("test_runtime", str(root))
            )
            self.assertEqual(record["regular_file_count"], 1)
            self.assertEqual(record["logical_bytes"], 100)
            self.assertEqual(record["hardlink_duplicate_count"], 1)

    def test_unsafe_or_oversized_paths_are_hashed(self):
        unsafe = disk_growth.safe_relative_path("bad\nname")
        oversized = disk_growth.safe_relative_path(
            "x" * (disk_growth.MAX_RELATIVE_PATH_LENGTH + 1)
        )
        self.assertRegex(unsafe, r"^path_sha256:[0-9a-f]{64}$")
        self.assertRegex(oversized, r"^path_sha256:[0-9a-f]{64}$")
        self.assertEqual(disk_growth.safe_relative_path("safe/file.jsonl"), "safe/file.jsonl")

    def test_missing_root_is_explicit_and_content_free(self):
        spec = disk_growth.RootSpec("missing", "/definitely/not/present/disk-growth")
        record, largest = disk_growth.scan_root(spec)
        self.assertEqual(record["query_status"], "not_found")
        self.assertEqual(record["scan_status"], "not_scanned")
        self.assertEqual(record["logical_bytes"], 0)
        self.assertEqual(largest, [])

    def test_entry_limit_marks_collection_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(4):
                (root / f"{index}.bin").write_bytes(b"x")
            with mock.patch.object(disk_growth, "MAX_ENTRIES_PER_ROOT", 2):
                record, _ = disk_growth.scan_root(
                    disk_growth.RootSpec("limited", str(root))
                )
            self.assertEqual(record["scan_status"], "limited")
            self.assertEqual(record["limit_reason"], "entry_limit")
            self.assertEqual(record["entries_examined"], 2)

    def test_timeout_marks_collection_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = iter([0.0, 9.0, 10.0])
            record, _ = disk_growth.scan_root(
                disk_growth.RootSpec("timeout", directory),
                monotonic=lambda: next(clock),
            )
            self.assertEqual(record["scan_status"], "limited")
            self.assertEqual(record["limit_reason"], "timeout")

    def test_snapshot_is_comparable_but_does_not_claim_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.jsonl").write_bytes(b"a" * 128)
            payload, exit_code = disk_growth.collect_snapshot(
                catalog=(disk_growth.RootSpec("test", str(root)),),
                observed_at_utc="2026-09-02T00:00:00Z",
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["collection_status"], "complete")
            self.assertFalse(payload["growth_computed"])
            self.assertIn("compare_two_complete_envelopes", payload["growth_method"])
            self.assertFalse(payload["contract"]["file_content_read"])
            self.assertFalse(payload["contract"]["local_baseline_written"])

    def test_render_is_bounded_and_deterministic(self):
        payload = {"z": 1, "a": 2}
        first = disk_growth.render_snapshot(payload)
        second = disk_growth.render_snapshot(payload)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first.encode("utf-8")), disk_growth.MAX_OUTPUT_BYTES)
        with mock.patch.object(disk_growth, "MAX_OUTPUT_BYTES", 5):
            with self.assertRaisesRegex(ValueError, "output limit"):
                disk_growth.render_snapshot(payload)

    def test_main_rejects_arguments_without_collecting(self):
        error = StringIO()
        with mock.patch.object(disk_growth, "collect_snapshot") as collect:
            with redirect_stderr(error):
                exit_code = disk_growth.main(["/caller/controlled/path"])
        self.assertEqual(exit_code, 64)
        collect.assert_not_called()
        self.assertIn("arguments are not accepted", error.getvalue())

    def test_filesystem_capacity_is_numeric_and_content_free(self):
        observation = disk_growth.filesystem_observation("/")
        self.assertEqual(observation["query_status"], "ok")
        self.assertGreater(observation["total_bytes"], 0)
        self.assertGreaterEqual(observation["available_bytes_unprivileged"], 0)
        self.assertIsInstance(observation["used_basis_points"], int)


if __name__ == "__main__":
    unittest.main()
