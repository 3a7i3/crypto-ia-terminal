from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock
import os
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/preprod/cat_prod_inventory_readonly.sh"


class InventoryTests(TestCase):
    def setUp(self):
        source = SCRIPT.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        self.n = {"__name__": "inventory_test"}
        exec(compile(source, str(SCRIPT), "exec"), self.n)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_only_named_systemd_fields_are_requested_and_exported(self):
        response = SimpleNamespace(stdout=(
            "ActiveState=active\nMainPID=123\nExecMainStartTimestampMonotonic=456\n"
            "Environment=SECRET_PATH=/sample/value SECRET_PORT=2345\n"
            "ExecStart=/sample/value\n"
        ))
        with mock.patch("subprocess.run", return_value=response) as run:
            episode = self.n["unit"](self.n["API"])
        self.assertEqual(episode, {"active": "active", "pid": 123, "start_monotonic_us": 456})
        self.assertEqual(run.call_args.args[0][2], "--property=ActiveState,MainPID,ExecMainStartTimestampMonotonic")

    def test_fingerprint_retains_hash_and_refuses_links_and_oversize(self):
        path = self.root / "file"
        path.write_bytes(b"abc")
        digest = self.n["fingerprint"]
        self.assertEqual(digest(self.root, "file")["git_blob_sha1"], "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f")
        (self.root / "link").symlink_to(path)
        (self.root / "dir-link").symlink_to(self.root, target_is_directory=True)
        self.assertEqual(digest(self.root, "link")["state"], "UNKNOWN")
        self.assertEqual(digest(self.root, "dir-link/file")["state"], "UNKNOWN")
        self.assertEqual(digest(self.root, "../file")["state"], "UNKNOWN")
        path.write_bytes(bytes(self.n["MAX_BYTES"] + 1))
        self.assertEqual(digest(self.root, "file")["reason"], "TOO_LARGE")
        os.mkfifo(self.root / "fifo")
        self.assertEqual(digest(self.root, "fifo")["reason"], "NOT_REGULAR")

    def test_fingerprint_discards_a_file_changed_during_read(self):
        path = self.root / "file"
        path.write_bytes(b"abc")
        real_fstat = os.fstat
        calls = 0

        def changing_fstat(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                path.write_bytes(b"changed")
            return real_fstat(fd)

        with mock.patch("os.fstat", side_effect=changing_fstat):
            self.assertEqual(self.n["fingerprint"](self.root, "file")["reason"], "FILE_CHANGED")

    def test_http_reports_redirect_status_without_following_or_reading_body(self):
        with mock.patch("http.client.HTTPConnection") as factory:
            connection = factory.return_value
            response = connection.getresponse.return_value.__enter__.return_value
            response.status = 302
            self.assertEqual(self.n["health_status"](), {"state": "OBSERVED", "status": 302})
            factory.assert_called_once_with("127.0.0.1", 8090, timeout=2)
            connection.request.assert_called_once_with("GET", "/healthz", headers={"Connection": "close"})
            response.read.assert_not_called()

    def test_wrong_host_stops_before_contacting_services(self):
        get_unit = self.n["unit"] = mock.Mock()
        with mock.patch("socket.gethostname", return_value="other-host"):
            self.assertEqual(self.n["inventory"](), {"state": "UNKNOWN", "reason": "WRONG_HOST"})
        get_unit.assert_not_called()

    def test_web_uses_process_root_and_invalidates_files_after_restart(self):
        api, web = self.n["API"], self.n["WEB"]
        self.n["unit"] = mock.Mock(side_effect=[
            {"active": "active", "pid": 10, "start_monotonic_us": 1},
            {"active": "active", "pid": 20, "start_monotonic_us": 1},
            {"active": "inactive"}, {"active": "active"},
            {"active": "active", "pid": 10, "start_monotonic_us": 1},
            {"active": "active", "pid": 20, "start_monotonic_us": 2},
        ])
        self.n["health_status"] = mock.Mock(return_value={"state": "OBSERVED", "status": 200})
        self.n["fingerprint"] = mock.Mock(return_value={"state": "OBSERVED", "sha256": "hash"})
        with mock.patch("socket.gethostname", return_value=self.n["HOST"]):
            report = self.n["inventory"]()
        self.assertIn(api, report["units"])
        self.assertIn(web, report["units"])
        for path, (target, candidate) in self.n["WEB_FILES"].items():
            self.n["fingerprint"].assert_any_call("/proc/20/root", target)
            self.n["fingerprint"].assert_any_call("/", candidate)
            self.assertEqual(report["files"][path]["observation"]["reason"], "PROCESS_CHANGED")
            self.assertIsNone(report["files"][path]["mount_content_matches"])

    def test_r6_fingerprints_only_regular_top_level_modules(self):
        scan = self.n["inventory_directory"]
        for path in self.n["API_DIRECTORIES"]:
            directory = self.root / path
            directory.mkdir(parents=True)
            module = directory / "storage_inventory.py"
            module.write_text("x = 1\n")
            (directory / "data.json").write_text("{}")
            (directory / "linked.py").symlink_to(module)
            (directory / "nested").mkdir()
            (directory / "nested" / "ignored.py").write_text("x = 2\n")
            files, status = scan(self.root, path)
            self.assertEqual(status, {"state": "OBSERVED"})
            self.assertEqual(list(files), [f"{path}/storage_inventory.py"])
            self.assertEqual(next(iter(files.values()))["observation"]["size"], 6)

    def test_r6_limits_all_entries_and_rejects_symlinked_directories(self):
        scan = self.n["inventory_directory"]
        real = self.root / "real"
        real.mkdir()
        (self.root / "alias").symlink_to(real, target_is_directory=True)
        self.assertEqual(scan(self.root, "alias")[1]["reason"], "DIRECTORY_UNAVAILABLE")
        self.n["MAX_DIRECTORY_ENTRIES"] = 1
        (real / "a.py").touch()
        (real / "ignored.json").touch()
        self.assertEqual(scan(self.root, "real"), ({}, {"state": "UNKNOWN", "reason": "DIRECTORY_LIMIT"}))
