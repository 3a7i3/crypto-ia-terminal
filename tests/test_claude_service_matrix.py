from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/claude-service-matrix.py"
SPEC = importlib.util.spec_from_file_location("claude_service_matrix", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
service_matrix = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = service_matrix
SPEC.loader.exec_module(service_matrix)


def _active_result(args, **_kwargs):
    unit = args[-1]
    stdout = "\n".join(
        (
            "LoadState=loaded",
            "ActiveState=active",
            "SubState=running",
            "UnitFileState=enabled",
            "MainPID=1234",
            "NRestarts=2",
            "ExecMainCode=exited",
            "ExecMainStatus=0",
            "Result=success",
            "ActiveEnterTimestamp=Tue 2026-09-01 19:00:00 UTC",
            "StateChangeTimestamp=Tue 2026-09-01 19:00:00 UTC",
            "NeedDaemonReload=no",
            "Environment=TOKEN=must-not-leak",
        )
    )
    return subprocess.CompletedProcess(
        args,
        0,
        stdout=stdout + "\n",
        stderr=f"secret stderr for {unit}",
    )


class TestServiceMatrixAuditPack(unittest.TestCase):
    def test_catalog_is_fixed_and_sensitive_properties_are_excluded(self):
        units = [item.unit for item in service_matrix.SERVICE_CATALOG]

        self.assertEqual(len(units), 10)
        self.assertEqual(len(units), len(set(units)))
        self.assertTrue(all(unit.endswith(".service") for unit in units))

        forbidden = {
            "Environment",
            "EnvironmentFiles",
            "ExecStart",
            "ExecStartPre",
            "ExecStartPost",
            "ExecReload",
            "ExecStop",
        }
        self.assertTrue(forbidden.isdisjoint(service_matrix.SAFE_PROPERTIES))

    def test_complete_matrix_is_bounded_and_does_not_leak_content(self):
        payload, exit_code = service_matrix.collect_matrix(
            run_command=_active_result,
            observed_at_utc="2026-09-01T19:00:00Z",
        )
        rendered = service_matrix.render_matrix(payload)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["collection_status"], "complete")
        self.assertEqual(payload["summary"]["active_count"], 10)
        self.assertEqual(payload["summary"]["query_error_count"], 0)
        self.assertNotIn("must-not-leak", rendered)
        self.assertNotIn("secret stderr", rendered)
        self.assertNotIn("ExecStart", rendered)
        self.assertLessEqual(
            len(rendered.encode("utf-8")), service_matrix.MAX_OUTPUT_BYTES
        )

    def test_missing_unit_is_a_complete_observation(self):
        def missing(args, **_kwargs):
            return subprocess.CompletedProcess(
                args,
                4,
                stdout="LoadState=not-found\nActiveState=inactive\n",
                stderr="Unit could not be found",
            )

        payload, exit_code = service_matrix.collect_matrix(
            catalog=(service_matrix.SERVICE_CATALOG[0],),
            run_command=missing,
            observed_at_utc="2026-09-01T19:00:00Z",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["collection_status"], "complete")
        self.assertEqual(payload["summary"]["not_found_count"], 1)
        self.assertEqual(payload["services"][0]["operational_state"], "not_found")

    def test_timeout_marks_collection_partial(self):
        def timeout(_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="systemctl", timeout=3)

        payload, exit_code = service_matrix.collect_matrix(
            catalog=(service_matrix.SERVICE_CATALOG[0],),
            run_command=timeout,
            observed_at_utc="2026-09-01T19:00:00Z",
        )

        self.assertEqual(exit_code, 69)
        self.assertEqual(payload["collection_status"], "partial")
        self.assertEqual(payload["summary"]["query_error_count"], 1)
        self.assertEqual(payload["services"][0]["query_status"], "timeout")

    def test_main_rejects_all_caller_controlled_arguments(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = service_matrix.main(["--unit", "ssh.service"])

        self.assertEqual(exit_code, 64)
        self.assertIn("arguments are not accepted", stderr.getvalue())

    def test_renderer_fails_closed_above_output_limit(self):
        with self.assertRaisesRegex(ValueError, "output limit"):
            service_matrix.render_matrix({"oversized": "x" * 25_000})


if __name__ == "__main__":
    unittest.main()
