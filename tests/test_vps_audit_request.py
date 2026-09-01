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
