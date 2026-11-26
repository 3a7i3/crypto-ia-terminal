import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import TestCase, mock
import os
import shutil
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/preprod/cat_prod_inventory_readonly.sh"
MATCH_SCRIPT = SCRIPT.with_name("cat_inventory_match.py")


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

    # ------------------------------------------------------------------ R7 recursive tree
    def make_tree(self):
        root = self.root / "release"
        (root / "observability" / "operator_api").mkdir(parents=True)
        (root / "observability" / "lab_sync" / "deep").mkdir(parents=True)
        (root / "observability" / "operator_api" / "app.py").write_text("app = 1\n")
        (root / "observability" / "lab_sync" / "deep" / "jobs.py").write_text("x = 2\n")
        (root / "observability" / "lab_sync" / "notes.txt").write_text("not python\n")
        (root / "top.py").write_text("t = 3\n")
        return root

    def test_r7_hashes_nested_regular_python_files_only(self):
        files, tree = self.n["inventory_tree"](self.make_tree())
        self.assertEqual(sorted(files), [
            "observability/lab_sync/deep/jobs.py", "observability/operator_api/app.py", "top.py",
        ])
        row = files["observability/lab_sync/deep/jobs.py"]["observation"]
        self.assertEqual((row["state"], row["size"]), ("OBSERVED", 6))
        self.assertEqual(set(row), {"state", "size", "git_blob_sha1", "sha256"})
        self.assertEqual(tree["state"], "COMPLETE")
        self.assertEqual((tree["files_observed"], tree["files_unknown"], tree["errors"]), (3, [], []))

    def test_r7_declares_exclusions_and_never_follows_links(self):
        root = self.make_tree()
        for name in (".venv", "__pycache__", "data"):
            (root / name).mkdir()
            (root / name / "hidden.py").write_text("secret = 1\n")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "elsewhere.py").write_text("y = 1\n")
        (root / "linked_dir").symlink_to(outside, target_is_directory=True)
        (root / "linked.py").symlink_to(root / "top.py")
        files, tree = self.n["inventory_tree"](root)
        self.assertEqual(sorted(tree["excluded_directories"]), [".venv", "__pycache__", "data"])
        self.assertEqual(sorted(tree["skipped_symlinks"]), ["linked.py", "linked_dir"])
        self.assertFalse(any("hidden" in path or "elsewhere" in path or "linked" in path for path in files))
        # A link is never followed, so what it hides is unverified: the tree cannot be COMPLETE.
        self.assertEqual(tree["unverified"]["symlinks"], ["linked.py", "linked_dir"])
        self.assertEqual(tree["state"], "INCOMPLETE")

    def test_r7_runtime_data_names_are_excluded_only_at_the_top_level(self):
        root = self.make_tree()
        (root / "pkg" / "databases").mkdir(parents=True)
        (root / "pkg" / "databases" / "scoreboard.py").write_text("s = 1\n")
        (root / "logs").mkdir()
        (root / "logs" / "rotated.py").write_text("r = 1\n")
        files, tree = self.n["inventory_tree"](root)
        self.assertIn("pkg/databases/scoreboard.py", files)
        self.assertNotIn("logs/rotated.py", files)
        self.assertEqual(tree["excluded_directories"], ["logs"])

    def test_r7_invalid_names_are_counted_not_printed(self):
        root = self.make_tree()
        (root / "bad name.py").write_text("z = 1\n")
        files, tree = self.n["inventory_tree"](root)
        self.assertEqual(tree["skipped_invalid_names"], 1)
        self.assertNotIn("bad name.py", files)
        self.assertNotIn("bad name", json.dumps(tree))

    def test_r7_each_limit_is_declared_and_makes_the_tree_incomplete(self):
        root = self.make_tree()
        for name, value, expected in (("TREE_MAX_DEPTH", 1, "max_depth"), ("TREE_MAX_FILES", 1, "max_files"),
                                      ("TREE_MAX_ENTRIES", 2, "max_entries")):
            with self.subTest(limit=name):
                saved = self.n[name]
                self.n[name] = value
                try:
                    _, tree = self.n["inventory_tree"](root)
                finally:
                    self.n[name] = saved
                self.assertEqual(tree["state"], "INCOMPLETE")
                self.assertEqual([item["limit"] for item in tree["limits_reached"]], [expected])

    def test_r7_unreadable_or_swapped_directory_is_declared(self):
        root = self.make_tree()
        real_open = os.open

        def refusing_open(name, flags, *args, **kwargs):
            if name == "lab_sync" and kwargs.get("dir_fd") is not None:
                raise PermissionError(13, "denied")
            return real_open(name, flags, *args, **kwargs)

        with mock.patch("os.open", side_effect=refusing_open):
            files, tree = self.n["inventory_tree"](root)
        self.assertEqual(tree["state"], "INCOMPLETE")
        self.assertEqual(tree["errors"], [{"path": "observability/lab_sync", "reason": "DIRECTORY_UNAVAILABLE", "errno": 13}])
        self.assertNotIn("observability/lab_sync/deep/jobs.py", files)

    def test_r7_directory_changed_during_scan_is_declared(self):
        root = self.make_tree()
        real_fstat = os.fstat
        target = os.stat(root / "observability" / "operator_api").st_ino
        seen = []

        def changing_fstat(fd):
            info = real_fstat(fd)
            if info.st_ino == target:
                seen.append(1)
                if len(seen) == 2:
                    (root / "observability" / "operator_api" / "late.py").write_text("late = 1\n")
                    return real_fstat(fd)
            return info

        with mock.patch("os.fstat", side_effect=changing_fstat):
            _, tree = self.n["inventory_tree"](root)
        self.assertEqual(tree["state"], "INCOMPLETE")
        self.assertIn({"path": "observability/operator_api", "reason": "DIRECTORY_CHANGED"}, tree["errors"])

    def test_r7_tree_is_invalidated_when_the_api_process_changes(self):
        root = self.make_tree()
        self.n["unit"] = mock.Mock(side_effect=[
            {"active": "active", "pid": 10, "start_monotonic_us": 1},
            {"active": "active", "pid": 20, "start_monotonic_us": 1},
            {"active": "inactive"}, {"active": "active"},
            {"active": "active", "pid": 11, "start_monotonic_us": 9},
            {"active": "active", "pid": 20, "start_monotonic_us": 1},
        ])
        self.n["health_status"] = mock.Mock(return_value={"state": "OBSERVED", "status": 200})
        real_tree = self.n["inventory_tree"]
        self.n["inventory_tree"] = mock.Mock(side_effect=lambda anchor: real_tree(root))
        with mock.patch("socket.gethostname", return_value=self.n["HOST"]):
            report = self.n["inventory"]()
        self.n["inventory_tree"].assert_called_once_with("/proc/10/cwd")
        self.assertEqual(report["api_tree"], {"state": "UNKNOWN", "reason": "PROCESS_CHANGED"})
        self.assertEqual(report["files"]["observability/lab_sync/deep/jobs.py"]["observation"]["reason"], "PROCESS_CHANGED")

    # ------------------------------------------------------------------ R7 review corrections
    def test_r7_link_or_invalid_name_that_may_hide_code_prevents_complete(self):
        cases = {
            "linked directory": lambda root: (root / "pkg_link").symlink_to(root / "observability", target_is_directory=True),
            "invalid directory name": lambda root: (root / "bad dir").mkdir() or (root / "bad dir" / "m.py").write_text("m = 1\n"),
            "invalid module name": lambda root: (root / "bad-module name.py").write_text("m = 1\n"),
        }
        for label, build in cases.items():
            with self.subTest(case=label):
                root = self.make_tree()
                build(root)
                files, tree = self.n["inventory_tree"](root)
                self.assertEqual(tree["state"], "INCOMPLETE")
                self.assertFalse(any(" " in path or "pkg_link" in path for path in files))
                self.assertNotIn("bad", json.dumps(tree["unverified"]))
                shutil.rmtree(root)

    def test_r7_harmless_skips_keep_the_tree_complete(self):
        root = self.make_tree()
        (root / "notes file.txt").write_text("not code\n")
        (root / "data").symlink_to(self.root, target_is_directory=True)
        files, tree = self.n["inventory_tree"](root)
        self.assertEqual((tree["skipped_invalid_names"], tree["skipped_symlinks"]), (1, ["data"]))
        self.assertEqual(tree["unverified"], {"symlinks": [], "invalid_names": 0})
        self.assertEqual(tree["state"], "COMPLETE")
        self.assertEqual(len(files), 3)

    def test_r7_entry_cap_is_global_and_stops_consuming_the_iterator(self):
        root = self.make_tree()
        for index in range(50):
            (root / "observability" / "lab_sync" / f"m{index:02}.py").write_text("x\n")
        real_scandir = os.scandir
        consumed = []

        class Counting:
            def __init__(self, fd):
                self.inner = real_scandir(fd)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.inner.close()

            def __iter__(self):
                for entry in self.inner:
                    consumed.append(entry.name)
                    yield entry

        self.n["TREE_MAX_ENTRIES"] = 6
        with mock.patch("os.scandir", side_effect=Counting):
            files, tree = self.n["inventory_tree"](root)
        # 6 entries are kept across several directories, the 7th reveals the cap, nothing more is read.
        self.assertEqual(len(consumed), 7)
        self.assertEqual(tree["entries_scanned"], 6)
        self.assertEqual(tree["limits_reached"], [{"limit": "max_entries", "at": "observability/lab_sync/"}])
        self.assertEqual(tree["state"], "INCOMPLETE")
        self.assertLess(len(files), 50)

    def test_r7_complete_output_is_deterministic_whatever_the_listing_order(self):
        root = self.make_tree()
        (root / ".venv").mkdir()
        (root / "zeta").mkdir()
        (root / "zeta" / "z.py").write_text("z\n")
        first = self.n["inventory_tree"](root)
        real_scandir = os.scandir

        class Reversed:
            def __init__(self, fd):
                with real_scandir(fd) as entries:
                    self.entries = list(entries)[::-1]

            def __enter__(self):
                return iter(self.entries)

            def __exit__(self, *exc):
                return None

        with mock.patch("os.scandir", side_effect=Reversed):
            second = self.n["inventory_tree"](root)
        self.assertEqual(first[1]["state"], "COMPLETE")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(list(first[0]), list(second[0]))

    def test_r6_r7_duplicates_export_one_print_or_unknown_with_a_reason(self):
        same = {"state": "OBSERVED", "size": 1, "git_blob_sha1": "a" * 40, "sha256": "b" * 64}
        other = {**same, "git_blob_sha1": "c" * 40, "sha256": "d" * 64}
        files = {
            "pkg/same.py": {"observation": dict(same)},
            "pkg/diverged.py": {"observation": dict(same)},
            "pkg/unreadable.py": {"observation": dict(same)},
            "pkg/vanished.py": {"observation": dict(same)},
            "agent_bench/observation/agents.py": {"observation": {"state": "UNKNOWN", "reason": "FILE_UNAVAILABLE"}},
            "data/outside.py": {"observation": dict(same)},
        }
        tree_files = {
            "pkg/same.py": {"observation": dict(same)},
            "pkg/diverged.py": {"observation": other},
            "pkg/unreadable.py": {"observation": {"state": "UNKNOWN", "reason": "FILE_CHANGED"}},
            "pkg/new.py": {"observation": other},
        }
        tree = {"state": "COMPLETE", "conflicts": [], "files_observed": 3, "files_unknown": ["pkg/unreadable.py"]}
        self.n["merge_tree"](files, tree_files, tree)
        self.assertEqual(tree["files_unknown"], ["pkg/diverged.py", "pkg/unreadable.py", "pkg/vanished.py"])
        self.assertEqual(tree["files_observed"], 2)
        self.assertEqual(files["pkg/same.py"]["observation"], same)
        self.assertEqual(files["pkg/new.py"]["observation"], other)
        self.assertEqual(files["data/outside.py"]["observation"], same)
        self.assertEqual(files["agent_bench/observation/agents.py"]["observation"]["reason"], "FILE_UNAVAILABLE")
        self.assertEqual(tree["conflicts"], [
            {"path": "pkg/diverged.py", "reason": "R6_R7_MISMATCH"},
            {"path": "pkg/unreadable.py", "reason": "R7_UNREADABLE"},
            {"path": "pkg/vanished.py", "reason": "R7_NOT_SEEN"},
        ])
        for item in tree["conflicts"]:
            self.assertEqual(files[item["path"]]["observation"], {"state": "UNKNOWN", "reason": item["reason"]})
        self.assertEqual(tree["state"], "INCOMPLETE")

    def test_r6_r7_conflict_reaches_the_v3_comparator_as_unknown(self):
        root = self.make_tree()
        api_dir = root / "observability" / "operator_api"
        subprocess.run(("git", "init", "-q", "-b", "main", str(root)), check=True)
        subprocess.run(("git", "-C", str(root), "add", "-A"), check=True)
        subprocess.run(("git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "base"), check=True)
        self.n["unit"] = mock.Mock(side_effect=[
            {"active": "active", "pid": 10, "start_monotonic_us": 1},
            {"active": "inactive"}, {"active": "inactive"}, {"active": "inactive"},
            {"active": "active", "pid": 10, "start_monotonic_us": 1},
        ])
        self.n["health_status"] = mock.Mock(return_value={"state": "OBSERVED", "status": 200})

        def anchor(value):
            return str(root) if value == "/proc/10/cwd" else value

        real_fingerprint, real_directory, real_tree = (
            self.n["fingerprint"], self.n["inventory_directory"], self.n["inventory_tree"])

        def tree_after_change(value):
            (api_dir / "app.py").write_text("app = 2  # changed between R6 and R7\n")
            return real_tree(anchor(value))

        self.n["fingerprint"] = lambda value, path: real_fingerprint(anchor(value), path)
        self.n["inventory_directory"] = lambda value, path: real_directory(anchor(value), path)
        self.n["inventory_tree"] = tree_after_change
        with mock.patch("socket.gethostname", return_value=self.n["HOST"]):
            report = self.n["inventory"]()
        self.assertEqual(report["api_tree"]["conflicts"],
                         [{"path": "observability/operator_api/app.py", "reason": "R6_R7_MISMATCH"}])
        self.assertEqual(report["api_tree"]["state"], "INCOMPLETE")
        # Counters follow the reconciled observations: app.py was read by R7 but is now UNKNOWN.
        self.assertEqual(report["api_tree"]["files_unknown"], ["observability/operator_api/app.py"])
        self.assertEqual(report["api_tree"]["files_observed"], 2)
        inventory = self.root / "inventory.json"
        inventory.write_text(json.dumps(report, indent=2, sort_keys=True))
        matched = json.loads(subprocess.check_output(
            ("python3", str(MATCH_SCRIPT), str(inventory), "--ref", "main", "--scope-ref", "main"),
            cwd=root, text=True))
        self.assertEqual(matched["files"]["observability/operator_api/app.py"], {"class": "UNKNOWN", "blob": None})
        self.assertEqual(matched["files"]["top.py"]["class"], "SAME_AS_REF")
