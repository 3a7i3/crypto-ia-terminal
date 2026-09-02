from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/claude-service-trigger-matrix.py"
SPEC = importlib.util.spec_from_file_location("claude_service_trigger_matrix", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
trigger_matrix = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = trigger_matrix
SPEC.loader.exec_module(trigger_matrix)


def _healthy_pair(args, **_kwargs):
    unit = args[-1]
    if unit.endswith(".timer"):
        service = unit.removesuffix(".timer") + ".service"
        stdout = "\n".join(
            (
                "LoadState=loaded",
                "ActiveState=active",
                "SubState=waiting",
                "UnitFileState=enabled",
                f"Unit={service}",
                f"Triggers={service}",
                "Wants=timers.target",
                "Requires=sysinit.target",
                "After=sysinit.target time-set.target",
                f"Before={service} timers.target",
                "LastTriggerUSec=Tue 2026-09-01 19:45:00 UTC",
                "NextElapseUSecRealtime=Tue 2026-09-01 20:00:00 UTC",
                "NextElapseUSecMonotonic=n/a",
                "Persistent=no",
                "AccuracyUSec=1min",
                "RandomizedDelayUSec=0",
                "Result=success",
                "Environment=TOKEN=must-not-leak",
            )
        )
    else:
        timer = unit.removesuffix(".service") + ".timer"
        stdout = "\n".join(
            (
                "LoadState=loaded",
                "ActiveState=inactive",
                "SubState=dead",
                "UnitFileState=static",
                "Type=oneshot",
                f"TriggeredBy={timer}",
                "Wants=network-online.target",
                "Requires=sysinit.target",
                "After=network-online.target system.slice",
                "StateChangeTimestamp=Tue 2026-09-01 19:45:01 UTC",
                "ActiveEnterTimestamp=n/a",
                "Result=success",
                "ExecMainStatus=0",
                "ExecStart={ path=/secret/token; }",
            )
        )
    return subprocess.CompletedProcess(
        args,
        0,
        stdout=stdout + "\n",
        stderr="raw secret stderr must-not-leak",
    )


class TestServiceTriggerMatrixAuditPack(unittest.TestCase):
    def test_catalog_is_exact_and_sensitive_properties_are_excluded(self):
        pairs = [(item.timer, item.service) for item in trigger_matrix.TRIGGER_CATALOG]

        self.assertEqual(
            pairs,
            [
                (
                    "crypto-market-observer.timer",
                    "crypto-market-observer.service",
                ),
                ("crypto-market-radar.timer", "crypto-market-radar.service"),
                (
                    "crypto-market-horizons.timer",
                    "crypto-market-horizons.service",
                ),
            ],
        )
        forbidden = {
            "Environment",
            "EnvironmentFiles",
            "ExecStart",
            "ExecStop",
            "FragmentPath",
            "DropInPaths",
        }
        self.assertTrue(forbidden.isdisjoint(trigger_matrix.TIMER_PROPERTIES))
        self.assertTrue(forbidden.isdisjoint(trigger_matrix.SERVICE_PROPERTIES))

    def test_complete_matrix_proves_runtime_relationships_without_leaks(self):
        payload, exit_code = trigger_matrix.collect_matrix(
            run_command=_healthy_pair,
            observed_at_utc="2026-09-01T19:50:00Z",
        )
        rendered = trigger_matrix.render_matrix(payload)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["collection_status"], "complete")
        self.assertEqual(payload["summary"]["pair_count"], 3)
        self.assertEqual(payload["summary"]["scheduled_waiting_count"], 3)
        self.assertEqual(payload["summary"]["relationship_mismatch_count"], 0)
        self.assertTrue(
            all(pair["relationship_status"] == "match" for pair in payload["pairs"])
        )
        self.assertNotIn("must-not-leak", rendered)
        self.assertNotIn("ExecStart", rendered)
        self.assertNotIn("/secret/token", rendered)
        self.assertLessEqual(
            len(rendered.encode("utf-8")), trigger_matrix.MAX_OUTPUT_BYTES
        )

    def test_relationship_mismatch_is_observed_without_failing_collection(self):
        def mismatch(args, **kwargs):
            result = _healthy_pair(args, **kwargs)
            if args[-1].endswith(".timer"):
                result.stdout = result.stdout.replace(
                    args[-1].removesuffix(".timer") + ".service",
                    "unexpected.service",
                )
            return result

        payload, exit_code = trigger_matrix.collect_matrix(
            catalog=(trigger_matrix.TRIGGER_CATALOG[0],),
            run_command=mismatch,
            observed_at_utc="2026-09-01T19:50:00Z",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["collection_status"], "complete")
        self.assertEqual(payload["summary"]["relationship_mismatch_count"], 1)

    def test_missing_timer_is_a_complete_observation(self):
        def missing(args, **_kwargs):
            if args[-1].endswith(".timer"):
                return subprocess.CompletedProcess(
                    args,
                    4,
                    stdout="LoadState=not-found\nActiveState=inactive\n",
                    stderr="not found",
                )
            return _healthy_pair(args)

        payload, exit_code = trigger_matrix.collect_matrix(
            catalog=(trigger_matrix.TRIGGER_CATALOG[0],),
            run_command=missing,
            observed_at_utc="2026-09-01T19:50:00Z",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["collection_status"], "complete")
        self.assertEqual(payload["summary"]["not_found_timer_count"], 1)
        self.assertEqual(payload["pairs"][0]["relationship_status"], "timer_not_found")

    def test_timeout_marks_collection_partial(self):
        def timeout(_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="systemctl", timeout=3)

        payload, exit_code = trigger_matrix.collect_matrix(
            catalog=(trigger_matrix.TRIGGER_CATALOG[0],),
            run_command=timeout,
            observed_at_utc="2026-09-01T19:50:00Z",
        )

        self.assertEqual(exit_code, 69)
        self.assertEqual(payload["collection_status"], "partial")
        self.assertEqual(payload["summary"]["query_error_count"], 2)

    def test_dependency_lists_are_syntax_checked_and_bounded(self):
        value = " ".join(
            [f"safe-{index}.target" for index in range(40)]
            + ["bad/path.service", "bad=value.service"]
        )
        units = trigger_matrix.bounded_unit_list(value)

        self.assertEqual(len(units), trigger_matrix.MAX_DEPENDENCIES)
        self.assertTrue(all("/" not in unit and "=" not in unit for unit in units))

    def test_main_rejects_caller_controlled_arguments(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = trigger_matrix.main(["--timer", "ssh.service"])

        self.assertEqual(exit_code, 64)
        self.assertIn("arguments are not accepted", stderr.getvalue())

    def test_renderer_fails_closed_above_output_limit(self):
        with self.assertRaisesRegex(ValueError, "output limit"):
            trigger_matrix.render_matrix({"oversized": "x" * 25_000})


if __name__ == "__main__":
    unittest.main()
