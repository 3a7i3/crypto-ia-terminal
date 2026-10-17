"""GT01-G-INTEGRATION-01 — mode d'authentification strict GitHub App (transport factice, aucun réseau).

Le mode ``APP_INSTALLATION`` n'émet jamais de requête sans ``Authorization``,
n'utilise jamais ``GT_GITHUB_TOKEN`` en repli, et atteste le périmètre de
l'installation (un seul dépôt) avant toute lecture.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from governance_tower.__main__ import build_sentinel
from governance_tower.contracts import Availability, ContractError, to_jsonable
from governance_tower.providers.github import (
    APP_SLUG_ENV,
    INSTALLATION_REPOS_URL,
    INSTALLATION_TOKEN_ENV,
    SENTINEL_APP_SLUG,
    AuthMode,
    HttpGithubProvider,
    Reason,
    is_allowed_api_url,
)
from governance_tower.scenarios import live_providers

REPO = "3a7i3/crypto-ia-terminal"
API = f"https://api.github.com/repos/{REPO}"
HEAD = "de5e0000000000000000000000000000000000a1"
NOW = datetime(2026, 10, 17, 9, 0, 0, tzinfo=timezone.utc)
APP_TOKEN = "ghs_" + "Z9" * 18
OTHER_APP_TOKEN = "ghs_" + "Y8" * 18
PAT = "ghp_" + "Q7" * 18

BRANCH_JSON = {
    "name": "main",
    "protected": True,
    "commit": {"sha": HEAD, "commit": {"message": "Titre", "committer": {"date": "2026-10-17T08:00:00Z"}}},
}
SCOPE_OK = {"total_count": 1, "repository_selection": "selected", "repositories": [{"full_name": REPO}]}


def clock():
    return NOW


def ok(obj):
    return (200, {}, json.dumps(obj).encode("utf-8"))


class Router:
    def __init__(self, scope=None, branch=None):
        self.scope = ok(SCOPE_OK) if scope is None else scope
        self.branch = ok(BRANCH_JSON) if branch is None else branch
        self.calls: list[tuple[str, dict]] = []

    @property
    def urls(self):
        return [u for u, _ in self.calls]

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers)))
        if url == INSTALLATION_REPOS_URL:
            return self.scope
        if url == f"{API}/branches/main":
            return self.branch
        return (404, {}, b"{}")


def strict(router, **kw):
    return HttpGithubProvider(REPO, clock=clock, transport=router, auth_mode=AuthMode.APP_INSTALLATION, **kw)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("GT_GITHUB_TOKEN", INSTALLATION_TOKEN_ENV, APP_SLUG_ENV):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def app_env(monkeypatch):
    monkeypatch.setenv(INSTALLATION_TOKEN_ENV, APP_TOKEN)
    monkeypatch.setenv(APP_SLUG_ENV, SENTINEL_APP_SLUG)


# ── Refus avant le réseau ────────────────────────────────────────────────────


def test_missing_token_sends_nothing_and_never_falls_back(monkeypatch):
    monkeypatch.setenv("GT_GITHUB_TOKEN", PAT)  # jeton hérité présent : jamais utilisé en mode strict
    monkeypatch.setenv(APP_SLUG_ENV, SENTINEL_APP_SLUG)
    r = Router()
    p = strict(r)
    obs = p.branch_head("main")
    assert obs.availability is Availability.DENIED and obs.reason == Reason.AUTH_MISSING
    assert r.calls == [] and p.requests_sent == 0
    assert p.auth_status()["identity"] == "NOT_ATTESTED"


@pytest.mark.parametrize("token", [PAT, "ghs_short", "ghs_" + "a" * 36 + "\r\nX: 1", "github_pat_" + "a" * 40, ""])
def test_non_installation_token_is_refused_without_request(monkeypatch, token):
    monkeypatch.setenv(INSTALLATION_TOKEN_ENV, token)
    monkeypatch.setenv(APP_SLUG_ENV, SENTINEL_APP_SLUG)
    r = Router()
    obs = strict(r).branch_head("main")
    assert obs.reason == Reason.AUTH_MISSING and r.calls == []


@pytest.mark.parametrize("slug", [None, "", "github-actions", "crypto-ai-sentinel-observer-x"])
def test_undeclared_or_other_app_is_refused_without_request(monkeypatch, slug):
    monkeypatch.setenv(INSTALLATION_TOKEN_ENV, APP_TOKEN)
    if slug is not None:
        monkeypatch.setenv(APP_SLUG_ENV, slug)
    r = Router()
    obs = strict(r).branch_head("main")
    assert obs.availability is Availability.DENIED and obs.reason == Reason.AUTH_IDENTITY_MISMATCH
    assert r.calls == []


def test_snapshot_without_token_is_qualified_absence_not_empty(monkeypatch):
    r = Router()
    snap = strict(r).repository_snapshot()
    assert snap.availability is Availability.DENIED and snap.head_sha is None
    assert r.calls == []


# ── Attestation puis lecture ────────────────────────────────────────────────


def test_attestation_precedes_reads_and_every_request_is_authenticated(app_env):
    r = Router()
    p = strict(r)
    obs = p.branch_head("main")
    assert obs.has_value and obs.value["sha"] == HEAD
    assert r.urls == [INSTALLATION_REPOS_URL, f"{API}/branches/main"]
    assert all(h.get("Authorization") == f"Bearer {APP_TOKEN}" for _, h in r.calls)
    assert all(e.note.endswith("auth APP_INSTALLATION") for e in obs.evidence)
    status = p.auth_status()
    assert status["identity"] == "INSTALLATION_SCOPE_VERIFIED"
    assert status["app_slug_declared"] == SENTINEL_APP_SLUG and status["installation_repository"] == REPO
    p.begin_investigation()
    p.branch_head("main")
    assert r.urls.count(INSTALLATION_REPOS_URL) == 1  # attestation conservée pour le même jeton


@pytest.mark.parametrize(
    "scope",
    [
        ok({"total_count": 2, "repositories": [{"full_name": REPO}, {"full_name": "3a7i3/autre"}]}),
        ok({"total_count": 1, "repositories": [{"full_name": "3a7i3/autre"}]}),
        ok({"total_count": 1, "repositories": []}),
        ok({"total_count": "1", "repositories": [{"full_name": REPO}]}),
        ok([]),
        (403, {}, b'{"message":"You must authenticate with an installation access token"}'),
        (404, {}, b"{}"),
        (302, {"location": "https://evil.example/"}, b""),
        (200, {}, b"not json"),
    ],
)
def test_unattested_scope_blocks_every_read(app_env, scope):
    r = Router(scope=scope)
    p = strict(r)
    obs = p.branch_head("main")
    assert obs.availability is Availability.DENIED and obs.reason == Reason.AUTH_UNATTESTED
    assert r.urls == [INSTALLATION_REPOS_URL]
    p.begin_investigation()
    again = p.branch_head("main")
    assert again.reason == Reason.AUTH_UNATTESTED and r.urls == [INSTALLATION_REPOS_URL]  # même jeton : pas de relance
    assert p.auth_status() == {"mode": AuthMode.APP_INSTALLATION, "identity": "NOT_ATTESTED", "reason": Reason.AUTH_UNATTESTED}


def test_rate_limited_attestation_is_not_cached_as_unattested(app_env):
    r = Router(scope=(429, {"retry-after": "60"}, b"{}"))
    p = strict(r)
    assert p.branch_head("main").reason == Reason.RATE_LIMITED
    assert p.auth_status()["reason"] is None


def test_new_token_is_attested_again(app_env, monkeypatch):
    r = Router()
    p = strict(r)
    p.branch_head("main")
    monkeypatch.setenv(INSTALLATION_TOKEN_ENV, OTHER_APP_TOKEN)
    p.begin_investigation()
    p.branch_head("main")
    assert r.urls.count(INSTALLATION_REPOS_URL) == 2
    assert r.calls[-1][1]["Authorization"] == f"Bearer {OTHER_APP_TOKEN}"


def test_token_removed_after_attestation_sends_nothing_more(app_env, monkeypatch):
    r = Router()
    p = strict(r)
    p.branch_head("main")
    monkeypatch.delenv(INSTALLATION_TOKEN_ENV)
    p.begin_investigation()
    obs = p.branch_head("main")
    assert obs.reason == Reason.AUTH_MISSING and len(r.calls) == 2
    assert all("Authorization" in h for _, h in r.calls)


def test_401_forces_a_new_attestation(app_env):
    r = Router(branch=(401, {}, b"{}"))
    p = strict(r)
    assert p.branch_head("main").reason == Reason.DENIED
    r.branch = ok(BRANCH_JSON)
    p.begin_investigation()
    assert p.branch_head("main").has_value
    assert r.urls.count(INSTALLATION_REPOS_URL) == 2


def test_token_never_appears_in_outputs(app_env):
    r = Router()
    p = strict(r)
    obs = p.branch_head("main")
    blob = json.dumps(to_jsonable(obs)) + repr(p) + json.dumps(p.auth_status()) + p.info.description
    assert APP_TOKEN not in blob and APP_TOKEN[4:20] not in blob


# ── Frontières d'URL et mode hérité ─────────────────────────────────────────


def test_installation_url_is_the_only_exception_outside_repos():
    assert is_allowed_api_url(INSTALLATION_REPOS_URL)
    for url in (
        "https://api.github.com/installation/repositories",
        "https://api.github.com/installation/repositories?per_page=50",
        "https://api.github.com/installation/token",
        "https://api.github.com/app",
        "https://api.github.com/user",
        "http://api.github.com/installation/repositories?per_page=100",
    ):
        assert not is_allowed_api_url(url), url


def test_optional_token_mode_is_unchanged_and_declares_no_identity(monkeypatch):
    monkeypatch.setenv(INSTALLATION_TOKEN_ENV, APP_TOKEN)  # ignoré : variable du mode strict
    r = Router()
    p = HttpGithubProvider(REPO, clock=clock, transport=r)
    assert p.auth_mode == AuthMode.OPTIONAL_TOKEN
    assert p.branch_head("main").has_value
    assert r.urls == [f"{API}/branches/main"] and "Authorization" not in r.calls[0][1]
    assert p.auth_status() == {"mode": AuthMode.OPTIONAL_TOKEN, "identity": "NOT_ATTESTED", "reason": None}
    assert "non attesté" in p.info.description


def test_invalid_configuration_is_refused():
    with pytest.raises(ContractError):
        HttpGithubProvider(REPO, clock=clock, auth_mode="BEARER")
    with pytest.raises(ContractError):
        HttpGithubProvider(REPO, clock=clock, auth_mode=AuthMode.APP_INSTALLATION, expected_app_slug="Bad Slug")


def test_live_providers_and_cli_select_strict_mode():
    github, _ = live_providers(
        github_live=True, host_snapshots=None, host_operator_api=None, github_auth=AuthMode.APP_INSTALLATION
    )
    assert github.auth_mode == AuthMode.APP_INSTALLATION

    import argparse

    args = argparse.Namespace(
        audit_log=None, github_live=True, host_snapshots=None, host_operator_api=None,
        github_auth="app-installation", scenario="nominal",
    )
    sentinel, scenario = build_sentinel(args)
    assert scenario is None and sentinel.mode == "LIVE_READ"
    assert sentinel._github.auth_mode == AuthMode.APP_INSTALLATION


def test_cli_refuses_app_auth_without_live(capsys):
    from governance_tower.__main__ import main

    with pytest.raises(SystemExit):
        main(["ask", "x", "--github-auth", "app-installation"])
    assert "exige --github-live" in capsys.readouterr().err
