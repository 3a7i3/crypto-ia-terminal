import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from unittest import TestCase, mock

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/preprod/cat_inventory_match.py"
SPEC = importlib.util.spec_from_file_location("cat_inventory_match", SCRIPT)
MATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MATCH)


class MatchTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "-q", "-b", "main")
        self.commit("main.py", "main")
        self.git("switch", "-qc", "other")
        self.commit("other.py", "other")
        self.git("switch", "-q", "main")
        self.inventory = {
            "inventory_schema": "cat-prod-inventory/3.0.0",
            "files": {
                "main.py": self.row(self.git("rev-parse", "main:main.py")),
                "other.py": self.row(self.git("rev-parse", "other:other.py")),
                "missing.py": self.row("0" * 40),
                "frontend/dist/index.html": self.row("0" * 40),
                "unreadable.py": {"observation": {"state": "UNKNOWN"}},
            },
        }

    def git(self, *args):
        return subprocess.check_output(("git", "-C", str(self.root), *args), text=True).strip()

    def commit(self, path, content):
        (self.root / path).write_text(content)
        self.git("add", path)
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", content)

    def row(self, blob):
        return {"observation": {"state": "OBSERVED", "git_blob_sha1": blob}}

    def compare(self, *refs):
        inventory = self.root / "inventory.json"
        inventory.write_text(json.dumps(self.inventory))
        args = [str(SCRIPT), str(inventory), "--ref", "main"]
        for ref in refs:
            args += ["--scope-ref", ref]
        return json.loads(subprocess.check_output(("python3", *args), cwd=self.root, text=True))

    def test_exact_other_absent_and_unknown_against_real_git(self):
        report = self.compare("other")
        self.assertEqual(report["scope_refs"]["other"], self.git("rev-parse", "other"))
        self.assertTrue(report["absence_scope_checked"])
        self.assertEqual({path: row["class"] for path, row in report["files"].items()}, {
            "main.py": "SAME_AS_REF",
            "other.py": "IN_GITHUB_OTHER",
            "missing.py": "ABSENT",
            "frontend/dist/index.html": "UNKNOWN",
            "unreadable.py": "UNKNOWN",
        })

    def test_missing_scope_or_ref_keeps_unmatched_files_unknown(self):
        for refs in ((), ("other", "missing-ref")):
            with self.subTest(refs=refs):
                report = self.compare(*refs)
                self.assertFalse(report["absence_scope_checked"])
                self.assertEqual(report["files"]["missing.py"]["class"], "UNKNOWN")
                self.assertEqual(report["files"]["main.py"]["class"], "SAME_AS_REF")

    def test_missing_git_object_cannot_prove_absence(self):
        other = self.git("rev-parse", "other:other.py")
        (self.root / ".git" / "objects" / other[:2] / other[2:]).unlink()
        report = self.compare("other")
        self.assertFalse(report["absence_scope_checked"])
        self.assertEqual(report["files"]["missing.py"]["class"], "UNKNOWN")

    def test_failed_walk_or_shallow_history_does_not_prove_absence(self):
        for shallow in ("true", "false"):
            def git_result(command, *_args):
                return {
                    "rev-parse": shallow,
                    "ls-tree": "",
                    "rev-list": None,
                }[command]

            with self.subTest(shallow=shallow), mock.patch.object(MATCH, "git", side_effect=git_result), mock.patch.object(
                MATCH, "resolve", return_value="1" * 40,
            ):
                report = MATCH.compare(self.inventory, "main", ["other"])
            self.assertFalse(report["absence_scope_checked"])
            self.assertEqual(report["files"]["missing.py"]["class"], "UNKNOWN")
