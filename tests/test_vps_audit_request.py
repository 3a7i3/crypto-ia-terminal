from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import vps_audit_request as audit_request


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_request(repo: Path, request_id: str, action: str) -> str:
    request_path = repo / audit_request.REQUEST_PATH
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": request_id,
                "action": action,
                "requested_at_utc": "2026-09-01T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", audit_request.REQUEST_PATH)
    _git(repo, "commit", "-m", f"audit request {request_id}")
    return _git(repo, "rev-parse", "HEAD")


class TestImmutableGitRequests(unittest.TestCase):
    def test_service_matrix_is_allowlisted_end_to_end(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/vps-audit.yml").read_text(
            encoding="utf-8"
        )
        dispatcher = (root / "scripts/claude-audit-dispatch").read_text(
            encoding="utf-8"
        )
        pack = (root / "scripts/claude-service-matrix.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("service_matrix", audit_request.ALLOWED_ACTIONS)
        self.assertIn("          - service_matrix\n", workflow)
        self.assertIn("    service_matrix)\n", dispatcher)
        self.assertIn("SERVICE_CATALOG = (\n", pack)

    def test_repo_diff_summary_is_allowlisted_end_to_end(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/vps-audit.yml").read_text(encoding="utf-8")
        dispatcher = (root / "scripts/claude-audit-dispatch").read_text(encoding="utf-8")
        wrapper = (root / "scripts/claude-repo-diff-summary").read_text(encoding="utf-8")

        self.assertIn("repo_diff_summary", audit_request.ALLOWED_ACTIONS)
        self.assertIn("          - repo_diff_summary\n", workflow)
        self.assertIn("    repo_diff_summary)\n", dispatcher)
        self.assertIn("readonly -a TARGETS=(\n", wrapper)

    def test_repo_diff_summary_never_emits_file_contents(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "scripts/claude-repo-diff-summary").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            _git(repo, "init")
            _git(repo, "config", "user.name", "Test")
            _git(repo, "config", "user.email", "test@example.invalid")

            env_file = repo / ".env.example"
            bot_file = repo / "src/telegram/quant_observer/bot.py"
            bot_file.parent.mkdir(parents=True)
            env_file.write_text("SECRET_VALUE=must-not-leak\n", encoding="utf-8")
            bot_file.write_text("def run():\n    return 'safe'\n", encoding="utf-8")
            _git(repo, "add", ".env.example", "src/telegram/quant_observer/bot.py")
            _git(repo, "commit", "-m", "baseline")

            env_file.unlink()
            bot_file.write_text(
                "def run():\n    token = 'another-must-not-leak'\n    return token\n",
                encoding="utf-8",
            )

            test_script = Path(directory) / "summary"
            test_script.write_text(
                source.replace(
                    "readonly SNAPSHOT='/srv/claude-audit/repo'",
                    f"readonly SNAPSHOT='{repo}'",
                ),
                encoding="utf-8",
            )
            test_script.chmod(0o700)

            result = subprocess.run(
                [str(test_script)],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertNotIn("must-not-leak", result.stdout)
            self.assertIn("worktree_status=D", result.stdout)
            self.assertIn("worktree_state=absent", result.stdout)
            self.assertIn("bot_diff_sha256=", result.stdout)
            self.assertIn("bot_hunk_1=@@", result.stdout)
            self.assertLess(len(result.stdout), 16_384)

    def test_manifest_metadata_action_is_allowlisted_end_to_end(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/vps-audit.yml").read_text(encoding="utf-8")
        dispatcher = (root / "scripts/claude-audit-dispatch").read_text(encoding="utf-8")

        self.assertIn("snapshot_manifest_meta", audit_request.ALLOWED_ACTIONS)
        self.assertIn("          - snapshot_manifest_meta\n", workflow)
        self.assertIn("    snapshot_manifest_meta)\n", dispatcher)

    def test_successive_requests_are_loaded_from_their_trigger_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            _git(repo, "init")
            _git(repo, "config", "user.name", "Test")
            _git(repo, "config", "user.email", "test@example.invalid")

            first_sha = _commit_request(repo, "REQ-MOBILE-FIRST", "identity")
            second_sha = _commit_request(repo, "REQ-MOBILE-SECOND", "repo_status")

            self.assertEqual(_git(repo, "rev-parse", "HEAD"), second_sha)

            first = audit_request.load_request_from_git(repo, first_sha)
            second = audit_request.load_request_from_git(repo, second_sha)

            self.assertEqual(first["request_id"], "REQ-MOBILE-FIRST")
            self.assertEqual(first["action"], "identity")
            self.assertEqual(second["request_id"], "REQ-MOBILE-SECOND")
            self.assertEqual(second["action"], "repo_status")

    def test_validate_git_rejects_non_immutable_ref(self):
        with self.assertRaisesRegex(audit_request.RequestError, "exactly 40"):
            audit_request.load_request_from_git(Path.cwd(), "main")

    def test_request_hash_is_stable_across_key_order(self):
        first = {
            "schema_version": 1,
            "request_id": "REQ-HASH",
            "action": "identity",
            "requested_at_utc": "2026-09-01T00:00:00Z",
        }
        second = dict(reversed(list(first.items())))

        self.assertEqual(
            audit_request._request_sha256(first),
            audit_request._request_sha256(second),
        )


if __name__ == "__main__":
    unittest.main()
