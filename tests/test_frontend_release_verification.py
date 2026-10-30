"""Regression tests for a daemon-reload that preserves the running API."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/frontend_release_20261030/verify_frontend_release.py"
SPEC = importlib.util.spec_from_file_location("frontend_release_read_only_verifier", SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

PYTHON = "/home/lecanada26/crypto-install/releases/82cd63e202e09ff52e00372cb9d9f3eb65cc8345/.venv/bin/python"
ARGV = PYTHON + " -B -m uvicorn observability.operator_api.app:app --host 127.0.0.1 --port 8090 --no-access-log"
BEFORE = (
    "{ path=" + PYTHON + " ; argv[]=" + ARGV
    + " ; ignore_errors=no ; start_time=[Fri 2026-10-30 02:48:04 UTC]"
    + " ; stop_time=[n/a] ; pid=79546 ; code=(null) ; status=0/0 }"
)
AFTER_RELOAD = (
    "{ path=" + PYTHON + " ; argv[]=" + ARGV
    + " ; ignore_errors=no ; start_time=[n/a]"
    + " ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
)
KERNEL_ARGV = [
    PYTHON, "-B", "-m", "uvicorn", "observability.operator_api.app:app",
    "--host", "127.0.0.1", "--port", "8090", "--no-access-log",
]


class FrontendReleaseExecStartTests(unittest.TestCase):
    def test_daemon_reload_accepts_unchanged_configuration_and_api_identity(self):
        before = {
            "ExecStart": BEFORE, "MainPID": "79546",
            "ActiveEnterTimestamp": "Fri 2026-10-30 02:48:04 UTC",
            "NRestarts": "0",
        }
        after = {**before, "ExecStart": AFTER_RELOAD}
        CHECK.same_properties(after, before, "API")
        self.assertEqual(CHECK.exec_start_configuration(BEFORE),
                         (PYTHON, ARGV, "no"))

    def test_exec_status_metadata_is_separate_from_configuration(self):
        status_changed = AFTER_RELOAD.replace("code=(null)", "code=exited").replace("status=0/0", "status=1/FAILURE")
        CHECK.same_properties({"ExecStart": status_changed},
                              {"ExecStart": BEFORE}, "configuration")
        # Actual service state, PID, timestamps and privileges retain their
        # independent guards; parsing this field alone is never a health proof.

    def test_changed_executable_is_refused(self):
        changed = AFTER_RELOAD.replace("path=" + PYTHON, "path=/usr/bin/python3")
        with self.assertRaisesRegex(RuntimeError, "ExecStart"):
            CHECK.same_properties({"ExecStart": changed},
                                  {"ExecStart": BEFORE}, "API")

    def test_changed_configured_arguments_are_refused(self):
        for changed in (
            AFTER_RELOAD.replace("--port 8090", "--port 8091"),
            AFTER_RELOAD.replace("observability.operator_api.app:app", "other.app:app"),
            AFTER_RELOAD.replace("--no-access-log", "--no-access-log --reload"),
        ):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(RuntimeError, "ExecStart"):
                    CHECK.same_properties({"ExecStart": changed},
                                          {"ExecStart": BEFORE}, "API")

    def test_changed_ignore_errors_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "ExecStart"):
            CHECK.same_properties(
                {"ExecStart": AFTER_RELOAD.replace("ignore_errors=no", "ignore_errors=yes")},
                {"ExecStart": BEFORE}, "API",
            )

    def test_multiple_exec_entries_are_refused(self):
        with self.assertRaisesRegex(RuntimeError, "Unsupported ExecStart"):
            CHECK.exec_start_configuration(AFTER_RELOAD + " " + AFTER_RELOAD)

    def test_unknown_or_missing_exec_representation_is_refused(self):
        for malformed in (None, "", "{ path=/bin/true }",
                          AFTER_RELOAD.replace("ignore_errors=no", "flags=new-format")):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(RuntimeError, "Unsupported ExecStart"):
                    CHECK.exec_start_configuration(malformed)

    def test_main_pid_change_is_still_refused_after_reload(self):
        with self.assertRaisesRegex(RuntimeError, "MainPID"):
            CHECK.same_properties(
                {"ExecStart": AFTER_RELOAD, "MainPID": "99999"},
                {"ExecStart": BEFORE, "MainPID": "79546"}, "API",
            )

    def test_start_time_change_is_still_refused(self):
        with self.assertRaisesRegex(RuntimeError, "ActiveEnterTimestamp"):
            CHECK.same_properties(
                {"ExecStart": AFTER_RELOAD, "ActiveEnterTimestamp": "Fri 2026-10-30 09:26:25 UTC"},
                {"ExecStart": BEFORE, "ActiveEnterTimestamp": "Fri 2026-10-30 02:48:04 UTC"}, "API",
            )

    def test_automatic_restart_count_change_is_still_refused(self):
        with self.assertRaisesRegex(RuntimeError, "NRestarts"):
            CHECK.same_properties(
                {"ExecStart": AFTER_RELOAD, "NRestarts": "1"},
                {"ExecStart": BEFORE, "NRestarts": "0"}, "API",
            )

    def test_hardening_and_paths_are_not_normalized_away(self):
        for key, good, bad in (
            ("ProtectSystem", "strict", "no"),
            ("NoNewPrivileges", "yes", "no"),
            ("WorkingDirectory", "/pinned/source", "/other/source"),
            ("BindReadOnlyPaths", "/pinned/source:/pinned/source:rbind", ""),
            ("DropInPaths", "", "/etc/systemd/system/api.service.d/unexpected.conf"),
        ):
            with self.subTest(key=key):
                with self.assertRaisesRegex(RuntimeError, key):
                    CHECK.same_properties({key: bad}, {key: good}, "API")

    def test_new_release_cannot_masquerade_as_unchanged_configuration(self):
        changed = AFTER_RELOAD.replace(CHECK.OLD, CHECK.NEW)
        with self.assertRaisesRegex(RuntimeError, "ExecStart"):
            CHECK.same_properties({"ExecStart": changed},
                                  {"ExecStart": BEFORE}, "API")

    def test_exact_kernel_argv_is_accepted(self):
        CHECK.require_api_process_argv(KERNEL_ARGV)

    def test_kernel_argv_suffix_changes_are_refused(self):
        for argv in (
            KERNEL_ARGV[:-1],
            KERNEL_ARGV + ["--reload"],
            [*KERNEL_ARGV[:8], "8091", *KERNEL_ARGV[9:]],
            [*KERNEL_ARGV[:4], "other.app:app", *KERNEL_ARGV[5:]],
        ):
            with self.subTest(argv=argv):
                with self.assertRaisesRegex(RuntimeError, "Actual API command"):
                    CHECK.require_api_process_argv(argv)

    def test_only_matching_kernel_prefix_is_insufficient(self):
        with self.assertRaisesRegex(RuntimeError, "Actual API command"):
            CHECK.require_api_process_argv(KERNEL_ARGV[:4])


if __name__ == "__main__":
    unittest.main()
