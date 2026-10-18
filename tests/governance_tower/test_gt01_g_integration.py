"""GT01-G-INTEGRATION-01 — contrat statique du workflow et runner borné (aucune exécution Actions, aucun réseau)."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from governance_tower.providers.github import INSTALLATION_REPOS_URL

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/gt01-g-integration-sentinel-backend.yml"
SCRIPT = ROOT / "scripts/governance_tower/gt01_g_integration_run.py"
APP_TOKEN_ACTION = "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1"
CHECKOUT_ACTION = "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5"
ENVIRONMENT = "sentinel-github-identity-smoke"
GATE = (
    "github.repository == '3a7i3/crypto-ia-terminal' && "
    "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
)
SHA = "c0ffee0000000000000000000000000000000001"
TOKEN = "ghs_" + "K4" * 18


class ActionsLoader(yaml.SafeLoader):
    """Garde la clé Actions « on » hors de la coercition booléenne YAML 1.1."""


ActionsLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values if tag != "tag:yaml.org,2002:bool"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_script():
    spec = importlib.util.spec_from_file_location("gt01_g_integration_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


m = load_script()


# ── Workflow ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def wf():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=ActionsLoader)


@pytest.fixture(scope="module")
def text():
    return "\n".join(
        line.split(" #")[0]
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_manual_main_only(wf, text):
    assert set(wf["on"]) == {"workflow_dispatch"}
    for forbidden in ("pull_request", "push", "schedule", "workflow_run", "repository_dispatch", "workflow_call"):
        assert forbidden not in text
    job = wf["jobs"]["sentinel-backend"]
    assert list(wf["jobs"]) == ["sentinel-backend"]
    assert re.sub(r"\s+", " ", job["if"].strip()) == GATE
    assert job["environment"] == ENVIRONMENT and job["timeout-minutes"] <= 10


def test_only_main_sha_is_checked_out_and_run(wf, text):
    steps = wf["jobs"]["sentinel-backend"]["steps"]
    assert [s.get("uses") for s in steps if "uses" in s] == [CHECKOUT_ACTION, APP_TOKEN_ACTION]
    assert steps[0]["with"] == {"ref": "${{ github.sha }}", "persist-credentials": "false"}
    assert text.count("actions/checkout") == 1
    for forbidden in ("head_ref", "inputs.", "github.event.pull_request", "git fetch", "git checkout", "pip install"):
        assert forbidden not in text
    run_steps = [s for s in steps if "run" in s]
    assert len(run_steps) == 1
    assert run_steps[0]["run"].strip() == "python3 -I scripts/governance_tower/gt01_g_integration_run.py"


def test_token_is_the_app_installation_token_never_github_token(wf, text):
    steps = wf["jobs"]["sentinel-backend"]["steps"]
    token_step = next(s for s in steps if s.get("uses") == APP_TOKEN_ACTION)
    w = token_step["with"]
    assert w["owner"] == "3a7i3" and w["repositories"] == "crypto-ia-terminal"
    assert {k: v for k, v in w.items() if k.startswith("permission-")} == {
        "permission-contents": "read",
        "permission-checks": "read",
        "permission-issues": "read",
        "permission-pull-requests": "read",
    }
    assert "skip-token-revoke" not in w
    env = next(s for s in steps if "run" in s)["env"]
    assert env["GT_SENTINEL_INSTALLATION_TOKEN"] == "${{ steps.sentinel.outputs.token }}"
    assert env["GT_SENTINEL_APP_SLUG"] == "${{ steps.sentinel.outputs.app-slug }}"
    assert env["GT_SENTINEL_INSTALLATION_ID"] == "${{ steps.sentinel.outputs.installation-id }}"
    assert "GT_GITHUB_TOKEN" not in text and "GITHUB_TOKEN" not in text and "github.token" not in text
    assert set(re.findall(r"secrets\.([A-Z_]+)", text)) == {"SENTINEL_APP_PRIVATE_KEY"}
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["sentinel-backend"]["permissions"] == {"contents": "read"}


def test_no_write_vps_or_deploy_surface(text):
    lowered = text.lower()
    for word in ("ssh", "scp", "upload-artifact", "deploy", "systemctl", "git push", ": write", "curl", "gh "):
        assert word not in lowered
    assert "BEGIN" not in text


# ── Runner ──────────────────────────────────────────────────────────────────


def ok(obj):
    return (200, {}, json.dumps(obj).encode("utf-8"))


API = "https://api.github.com/repos/3a7i3/crypto-ia-terminal"


class GitHubStub:
    def __init__(self, head=SHA, overrides=None):
        self.head = head
        self.overrides = overrides or {}
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers)))
        for key, resp in self.overrides.items():
            if key in url:
                return resp
        if url == INSTALLATION_REPOS_URL:
            return ok({"total_count": 1, "repositories": [{"full_name": m.REPO}]})
        if url == API:
            return ok({"default_branch": "main"})
        if url == f"{API}/branches/main":
            return ok({"name": "main", "protected": True, "commit": {
                "sha": self.head, "commit": {"message": "x", "committer": {"date": "2026-10-17T08:00:00Z"}}}})
        if "/check-runs" in url:
            return ok({"total_count": 1, "check_runs": [
                {"name": "pytest", "head_sha": self.head, "status": "completed", "conclusion": "success"}]})
        if "/pulls?" in url or "/issues?" in url:
            return ok([])
        return (404, {}, b"{}")


def env(**over):
    base = {
        "GT_SENTINEL_INSTALLATION_TOKEN": TOKEN,
        "GT_SENTINEL_APP_SLUG": "crypto-ai-sentinel-observer",
        "GT_SENTINEL_INSTALLATION_ID": "987654",
        "GITHUB_SHA": SHA,
    }
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


@pytest.fixture
def os_env(monkeypatch):
    def apply(values):
        for k in ("GT_SENTINEL_INSTALLATION_TOKEN", "GT_SENTINEL_APP_SLUG", "GT_GITHUB_TOKEN"):
            monkeypatch.delenv(k, raising=False)
        for k, v in values.items():
            monkeypatch.setenv(k, v)
        return values

    return apply


def checks(doc):
    return {c["check"]: c for c in doc["checks"]}


def test_healthy_run_is_verified_and_authenticated(os_env):
    e = os_env(env())
    gh = GitHubStub()
    doc = m.run(e, transport=gh)
    assert doc["verdict"] == m.VERDICT_OK, doc["checks"]
    assert gh.calls[0][0] == INSTALLATION_REPOS_URL
    assert all(h["Authorization"] == f"Bearer {TOKEN}" for _, h in gh.calls)
    assert len(gh.calls) <= 12
    c = checks(doc)
    assert c["installation_scope"]["detail"]["identity"] == "INSTALLATION_SCOPE_VERIFIED"
    assert c["host_observation"]["class"] == "NOT_VERIFIABLE"
    as_json, as_md = m.render(doc, [TOKEN])
    assert TOKEN not in as_json + as_md and "GT01_G_INTEGRATION_VERIFIED" in as_md


def test_checkout_diverging_from_main_fails(os_env):
    e = os_env(env())
    doc = m.run(e, transport=GitHubStub(head="d" * 40))
    assert doc["verdict"] == m.VERDICT_FAILED
    assert checks(doc)["main_head_matches_checkout"]["detail"]["status"] == "CHECKOUT_DIVERGES_FROM_MAIN"


def test_missing_token_fails_without_any_request(os_env):
    e = os_env(env(GT_SENTINEL_INSTALLATION_TOKEN=None))
    gh = GitHubStub()
    doc = m.run(e, transport=gh)
    assert doc["verdict"] == m.VERDICT_FAILED and gh.calls == []
    assert checks(doc)["installation_scope"]["detail"]["reason"] == "AUTH_MISSING"


def test_unexpected_app_slug_fails_without_any_request(os_env):
    e = os_env(env(GT_SENTINEL_APP_SLUG="github-actions"))
    gh = GitHubStub()
    doc = m.run(e, transport=gh)
    assert doc["verdict"] == m.VERDICT_FAILED and gh.calls == []
    assert checks(doc)["app_identity_declared"]["detail"]["app_slug"] == "UNEXPECTED"


def test_broad_installation_fails(os_env):
    e = os_env(env())
    gh = GitHubStub(overrides={"/installation/repositories": ok(
        {"total_count": 2, "repositories": [{"full_name": m.REPO}, {"full_name": "3a7i3/x"}]})})
    doc = m.run(e, transport=gh)
    assert doc["verdict"] == m.VERDICT_FAILED and len(gh.calls) == 1


def test_partial_read_is_not_verified(os_env):
    e = os_env(env())
    doc = m.run(e, transport=GitHubStub(overrides={"/pulls?": (404, {}, b"{}")}))
    assert doc["verdict"] == m.VERDICT_FAILED
    assert checks(doc)["evidence_live_authenticated"]["detail"]["non_200"] == ["GET HTTP 404"]


def test_report_with_secret_or_oversize_is_refused(os_env):
    e = os_env(env())
    doc = m.run(e, transport=GitHubStub())
    leaked = dict(doc, generated_at_utc=TOKEN)
    with pytest.raises(m.SecretInReport):
        m.render(leaked, [TOKEN])
    other = dict(doc, generated_at_utc="ghp_" + "a" * 36)
    with pytest.raises(m.SecretInReport):
        m.render(other, [TOKEN])
    big = dict(doc, boundaries=["x" * (m.MAX_REPORT_BYTES + 1)])
    with pytest.raises(m.SecretInReport):
        m.render(big, [TOKEN])


def test_isolated_entrypoint_without_token_sends_nothing(tmp_path):
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("GT_", "GITHUB_"))}
    clean.update({"GITHUB_SHA": SHA, "REPORT_DIR": str(tmp_path / "r"), "GITHUB_STEP_SUMMARY": str(tmp_path / "s.md")})
    proc = subprocess.run(
        [sys.executable, "-I", str(SCRIPT)], cwd=tmp_path, env=clean, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 1, proc.stderr
    doc = json.loads((tmp_path / "r" / "gt01_g_integration.json").read_text(encoding="utf-8"))
    assert doc["verdict"] == "GT01_G_INTEGRATION_FAILED"
    c = checks(doc)
    assert c["installation_scope"]["detail"]["reason"] == "AUTH_MISSING"
    assert c["bounded_reads"]["detail"]["requests_sent"] == 0
    assert c["backend_from_checkout"]["ok"] is True
    assert "GT01_G_INTEGRATION_FAILED" in (tmp_path / "s.md").read_text(encoding="utf-8")
