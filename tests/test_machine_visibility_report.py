"""No raw secrets or log messages may cross the observation boundary."""
import json
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("visibility_report", SCRIPTS / "machine_visibility_report.py")
report = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(SCRIPTS), *sys.path]):
    SPEC.loader.exec_module(report)


class VisibilityTests(unittest.TestCase):
    def test_log_messages_and_unknown_fields_never_exported(self):
        raw = b'{"PRIORITY":"3","MESSAGE":"TOKEN=TOP_SECRET","SECRET":"hidden"}\n'
        result = report.summarize_journal(raw)
        self.assertEqual(result["priority_counts"], {"3": 1})
        self.assertNotIn("TOP_SECRET", json.dumps(result))
        self.assertNotIn("hidden", json.dumps(result))

    def test_empty_is_not_no_activity(self):
        result = report.summarize_journal(b"")
        self.assertEqual(result["status"], "NO_VISIBLE_RECORDS")
        self.assertEqual(result["permission"], "NOT_PROVEN")

    def test_hostile_priority_does_not_echo(self):
        result = report.summarize_journal(b'{"PRIORITY":"SECRET_VALUE"}\n')
        self.assertEqual(result["priority_counts"], {"UNKNOWN": 1})
        self.assertNotIn("SECRET_VALUE", json.dumps(result))

    def test_limits_and_malformed_record(self):
        for data in [b"x" * 1048577, b"{}\n" * 201]:
            self.assertEqual(report.summarize_journal(data)["status"], "OUTPUT_LIMIT")
        for data in [b"bad\n", b"[]\n"]:
            self.assertEqual(report.summarize_journal(data)["status"], "INVALID_DOCUMENT")

    def test_environment_only_fixed_paths_and_never_raw_commands(self):
        text = ('Environment="TOKEN=TOP_SECRET" "BURN_IN_STATUS_SNAPSHOT_PATH=/home/mathieu/operator_presentation/burn.json"\n'
                'ExecStart=/bin/app --password TOP_SECRET\n')
        result = report.summarize_unit(text)
        self.assertNotIn("TOP_SECRET", json.dumps(result))
        self.assertEqual(result["declared_path_settings"]["BURN_IN_STATUS_SNAPSHOT_PATH"],
                         "/home/mathieu/operator_presentation/burn.json")

    def test_outside_path_and_traversal_are_not_published(self):
        for path in ["/etc/secret", "/home/mathieu/operator_presentation/../secret", "TOKEN"]:
            result = report.summarize_unit("Environment=BURN_IN_STATUS_SNAPSHOT_PATH=" + path)
            self.assertEqual(result["declared_path_settings"]["BURN_IN_STATUS_SNAPSHOT_PATH"], "REJECTED_VALUE")

    def test_journal_command_is_fixed(self):
        with self.assertRaises(ValueError):
            report.journal_command("--all;cat /etc/secret")
        self.assertIn("--lines=200", report.journal_command(report.LOG_UNITS[0]))

    def test_import_has_no_collection(self):
        with patch.object(report.subprocess, "Popen") as process:
            SPEC.loader.exec_module(report)
        process.assert_not_called()
