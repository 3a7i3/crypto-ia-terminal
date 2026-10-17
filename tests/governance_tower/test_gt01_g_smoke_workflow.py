"""GT01-G-SMOKE-01 — contrat statique du banc d'identité Sentinel (aucune exécution Actions)."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/gt01-g-smoke-sentinel-identity.yml"
SCRIPT = ROOT / "scripts/governance_tower/gt01_g_smoke_identity.py"

APP_TOKEN_ACTION = (
    "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1"
)
CHECKOUT_ACTION = "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5"
ENVIRONMENT = "sentinel-github-identity-smoke"
GATE = (
    "github.repository == '3a7i3/crypto-ia-terminal' && "
    "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
)


class ActionsLoader(yaml.SafeLoader):
    """Keep the YAML 1.2 Actions key 'on' from YAML 1.1 boolean coercion."""


ActionsLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values if tag != "tag:yaml.org,2002:bool"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def read_workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=ActionsLoader)


def load_script():
    spec = importlib.util.spec_from_file_location("gt01_g_smoke_identity", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestWorkflowContract(unittest.TestCase):
    def setUp(self):
        self.wf = read_workflow()
        self.job = self.wf["jobs"]["sentinel-identity"]
        # Texte exécutable : commentaires YAML retirés.
        self.text = "\n".join(
            line.split(" #")[0]
            for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )

    def test_manual_trigger_only(self):
        self.assertEqual(set(self.wf["on"]), {"workflow_dispatch"})
        for forbidden in (
            "pull_request",
            "push",
            "schedule",
            "workflow_run",
            "repository_dispatch",
            "workflow_call",
        ):
            self.assertNotIn(forbidden, self.text)
        self.assertEqual(re.sub(r"\s+", " ", self.job["if"].strip()), GATE)

    def test_single_job_in_dedicated_environment(self):
        self.assertEqual(list(self.wf["jobs"]), ["sentinel-identity"])
        self.assertEqual(self.job["environment"], ENVIRONMENT)
        self.assertLessEqual(self.job["timeout-minutes"], 10)

    def test_github_token_is_read_only(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        self.assertEqual(self.job["permissions"], {"contents": "read"})

    def test_every_action_is_pinned_by_full_sha(self):
        uses = [s["uses"] for s in self.job["steps"] if "uses" in s]
        self.assertEqual(uses, [CHECKOUT_ACTION, APP_TOKEN_ACTION])
        for ref in uses:
            self.assertRegex(ref, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")

    def test_checkout_does_not_persist_credentials(self):
        checkout = self.job["steps"][0]
        self.assertEqual(checkout["with"]["persist-credentials"], "false")

    def test_token_request_is_read_only_and_single_repository(self):
        step = next(s for s in self.job["steps"] if s.get("uses") == APP_TOKEN_ACTION)
        w = step["with"]
        self.assertEqual(w["owner"], "3a7i3")
        self.assertEqual(w["repositories"], "crypto-ia-terminal")
        perms = {k: v for k, v in w.items() if k.startswith("permission-")}
        self.assertEqual(
            perms,
            {
                "permission-contents": "read",
                "permission-checks": "read",
                "permission-issues": "read",
                "permission-pull-requests": "read",
            },
        )
        self.assertEqual(w["client-id"], "${{ vars.SENTINEL_APP_CLIENT_ID }}")
        self.assertEqual(w["private-key"], "${{ secrets.SENTINEL_APP_PRIVATE_KEY }}")
        self.assertNotIn("skip-token-revoke", w)

    def test_secrets_never_reach_shell_text(self):
        self.assertEqual(
            set(re.findall(r"secrets\.([A-Z_]+)", self.text)),
            {"SENTINEL_APP_PRIVATE_KEY"},
        )
        self.assertNotIn("GITHUB_TOKEN", self.text)
        self.assertNotIn("github.token", self.text)
        for step in self.job["steps"]:
            run = step.get("run", "")
            self.assertNotIn(
                "${{", run, "les expressions passent par env, jamais par le shell"
            )
            self.assertNotIn("curl", run)
            self.assertNotIn("gh ", run)

    def test_no_write_vps_or_deploy_surface(self):
        lowered = self.text.lower()
        for word in (
            "ssh",
            "scp",
            "upload-artifact",
            "deploy",
            "systemctl",
            "git push",
            ": write",
        ):
            self.assertNotIn(word, lowered)
        self.assertNotIn("BEGIN", self.text)


class FakeGitHub:
    def __init__(self, routes):
        self.routes = routes
        self.paths = []

    def __call__(self, path):
        self.paths.append(path)
        status, body = self.routes.get(path, (404, {"message": "Not Found"}))
        return status, {"X-RateLimit-Remaining": "4990"}, body


MAIN_SHA = "a" * 40
PR_SHA = "b" * 40
CLAUDE = b"# Constitution\n"


def git_blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def healthy_routes(m):
    repo = f"/repos/{m.OWNER}/{m.REPO}"
    return {
        f"/apps/{m.EXPECTED_APP_SLUG}": (
            200,
            {
                "slug": m.EXPECTED_APP_SLUG,
                "id": 1,
                "owner": {"login": "3a7i3"},
                "permissions": {
                    "contents": "read",
                    "checks": "read",
                    "issues": "read",
                    "pull_requests": "read",
                    "metadata": "read",
                },
            },
        ),
        "/installation/repositories?per_page=100": (
            200,
            {
                "total_count": 1,
                "repository_selection": "selected",
                "repositories": [{"full_name": m.FULL_NAME}],
            },
        ),
        f"{repo}/git/ref/heads/main": (200, {"object": {"sha": MAIN_SHA}}),
        f"{repo}/contents/CLAUDE.md?ref={MAIN_SHA}": (
            200,
            {"content": base64.b64encode(CLAUDE).decode(), "sha": git_blob(CLAUDE)},
        ),
        f"{repo}/issues/461": (
            200,
            {"number": 461, "state": "open", "title": "GOV-TOWER-01"},
        ),
        f"{repo}/pulls/462": (
            200,
            {
                "number": 462,
                "state": "open",
                "draft": True,
                "head": {"sha": PR_SHA, "ref": "x"},
                "base": {"ref": "main"},
            },
        ),
        f"{repo}/commits/{PR_SHA}/check-runs?per_page=100&page=1": (
            200,
            {
                "total_count": 2,
                "check_runs": [
                    {
                        "name": "pytest",
                        "status": "completed",
                        "conclusion": "success",
                        "head_sha": PR_SHA,
                    },
                    {
                        "name": "ruff",
                        "status": "completed",
                        "conclusion": "failure",
                        "head_sha": PR_SHA,
                    },
                ],
            },
        ),
    }


class TestReportScript(unittest.TestCase):
    def setUp(self):
        self.m = load_script()

    def run_with(self, routes, **kw):
        fake = FakeGitHub(routes)
        args = {
            "app_slug": self.m.EXPECTED_APP_SLUG,
            "installation_id": "42",
            "local_claude_md": CLAUDE,
            "expected_claude_md_sha256": "",
        }
        args.update(kw)
        return self.m.run_checks(fake, **args), fake

    def test_healthy_run_is_verified_and_get_only(self):
        report, fake = self.run_with(healthy_routes(self.m))
        self.assertEqual(report.failures, [])
        doc = self.m.build_document(report, {})
        self.assertEqual(doc["verdict"], self.m.VERDICT_OK)
        self.assertEqual(doc["boundaries"]["http_methods_used"], ["GET"])
        self.assertEqual(doc["boundaries"]["github_writes"], 0)
        for path in fake.paths:
            self.m.check_path(path)
        classes = {f["check"]: f["class"] for f in doc["facts"]}
        self.assertEqual(classes["installation_scope"], "VERIFIED")
        self.assertEqual(classes["token_requested_permissions"], "DECLARED")
        self.assertEqual(classes["app_configured_permissions"], "DECLARED")
        self.assertEqual(classes["token_write_denial"], "NOT_VERIFIABLE")
        checks = next(f for f in doc["facts"] if f["check"] == "pr_462_check_runs")
        self.assertEqual(
            checks["detail"]["by_conclusion"], {"success": 1, "failure": 1}
        )
        fp = next(f for f in doc["facts"] if f["check"] == "claude_md_fingerprint")
        self.assertEqual(fp["detail"]["sha256"], hashlib.sha256(CLAUDE).hexdigest())
        self.assertTrue(fp["detail"]["local_matches_main"])

    def test_wrong_identity_fails(self):
        report, _ = self.run_with(healthy_routes(self.m), app_slug="some-other-app")
        self.assertIn("app_identity_from_token_action", report.failures)

    def test_installation_wider_than_one_repository_fails(self):
        routes = healthy_routes(self.m)
        routes["/installation/repositories?per_page=100"] = (
            200,
            {
                "total_count": 2,
                "repositories": [
                    {"full_name": self.m.FULL_NAME},
                    {"full_name": "3a7i3/other"},
                ],
            },
        )
        report, _ = self.run_with(routes)
        self.assertIn("installation_scope", report.failures)

    def test_app_write_permission_is_flagged(self):
        routes = healthy_routes(self.m)
        routes[f"/apps/{self.m.EXPECTED_APP_SLUG}"][1]["permissions"]["contents"] = (
            "write"
        )
        report, _ = self.run_with(routes)
        self.assertIn("app_configured_permissions", report.failures)

    def test_fingerprint_mismatch_fails(self):
        report, _ = self.run_with(
            healthy_routes(self.m), expected_claude_md_sha256="0" * 64
        )
        self.assertIn("claude_md_fingerprint", report.failures)

    def test_read_failure_is_not_an_empty_population(self):
        routes = healthy_routes(self.m)
        del routes[
            f"/repos/{self.m.OWNER}/{self.m.REPO}/commits/{PR_SHA}/check-runs"
            "?per_page=100&page=1"
        ]
        report, _ = self.run_with(routes)
        self.assertIn("pr_462_check_runs", report.failures)

    def test_closed_path_list_refuses_anything_else(self):
        for path in (
            "/repos/3a7i3/crypto-ia-terminal/actions/secrets",
            "/repos/3a7i3/other/pulls/462",
            "/user",
            "/repos/3a7i3/crypto-ia-terminal/contents/.env?ref=" + MAIN_SHA,
        ):
            with self.assertRaises(self.m.PathNotAllowed):
                self.m.check_path(path)

    def test_report_never_contains_token(self):
        token = "ghs_" + "x" * 36
        with self.assertRaises(RuntimeError):
            self.m.assert_no_secret(json.dumps({"leak": token}), [token])
        with self.assertRaises(RuntimeError):
            self.m.assert_no_secret("-----BEGIN RSA PRIVATE KEY-----", [])
        self.m.assert_no_secret("aucun secret", [token])

    def test_script_has_no_write_method(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('method="GET"', source)
        for verb in (
            '"POST"',
            '"PUT"',
            '"PATCH"',
            '"DELETE"',
            "subprocess",
            "paramiko",
        ):
            self.assertNotIn(verb, source)


if __name__ == "__main__":
    unittest.main()
