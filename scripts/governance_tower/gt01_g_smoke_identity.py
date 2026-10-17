#!/usr/bin/env python3
"""GT01-G-SMOKE-01 — vérification READ-ONLY de l'identité GitHub App de Sentinel.

Exécuté uniquement par `.github/workflows/gt01-g-smoke-sentinel-identity.yml`
(workflow_dispatch). Lit un jeton d'installation dans `SENTINEL_TOKEN`, appelle
une liste fermée d'endpoints GitHub en GET, puis écrit un rapport horodaté
(JSON + Markdown). Le jeton n'est jamais écrit, journalisé ni renvoyé.

Classes de preuve :
- VERIFIED      : observé dans une réponse GitHub obtenue avec le jeton ;
- DECLARED      : demandé ou configuré, sans exercice prouvant l'effet ;
- NOT_VERIFIABLE: hors de portée du jeton ou volontairement non testé
                  (aucune écriture n'est tentée pour prouver un refus).

Stdlib uniquement. Aucune écriture GitHub, aucun accès VPS.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "gt01_g_smoke_identity.v1"
VERDICT_OK = "GT01_G_SMOKE_IDENTITY_VERIFIED"
VERDICT_FAILED = "GT01_G_SMOKE_IDENTITY_FAILED"

OWNER = "3a7i3"
REPO = "crypto-ia-terminal"
FULL_NAME = f"{OWNER}/{REPO}"
EXPECTED_APP_SLUG = "crypto-ai-sentinel-observer"
ISSUE_NUMBER = 461
PR_NUMBER = 462
REQUESTED_PERMISSIONS = {
    "contents": "read",
    "checks": "read",
    "issues": "read",
    "pull_requests": "read",
}
API = "https://api.github.com"
MAX_CHECK_PAGES = 5
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Liste fermée : (motif d'URL relative, raison). Tout autre chemin est refusé.
_ALLOWED_PATHS = (
    re.compile(r"^/installation/repositories\?per_page=100$"),
    re.compile(rf"^/apps/{re.escape(EXPECTED_APP_SLUG)}$"),
    re.compile(rf"^/repos/{OWNER}/{REPO}/git/ref/heads/main$"),
    re.compile(rf"^/repos/{OWNER}/{REPO}/contents/CLAUDE\.md\?ref=[0-9a-f]{{40}}$"),
    re.compile(rf"^/repos/{OWNER}/{REPO}/issues/{ISSUE_NUMBER}$"),
    re.compile(rf"^/repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}$"),
    re.compile(
        rf"^/repos/{OWNER}/{REPO}/commits/[0-9a-f]{{40}}/check-runs"
        r"\?per_page=100&page=[1-9]$"
    ),
)

Fetch = Callable[[str], "tuple[int, dict, object]"]


class PathNotAllowed(ValueError):
    pass


def check_path(path: str) -> str:
    if not any(p.match(path) for p in _ALLOWED_PATHS):
        raise PathNotAllowed(path)
    return path


def make_fetch(token: str, api: str = API) -> Fetch:
    """GET-only client bound to the closed path list."""

    def fetch(path: str):
        check_path(path)
        req = urllib.request.Request(
            api + path,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "gt01-g-smoke-sentinel-identity",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                status, headers, raw = resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            status, headers, raw = exc.code, dict(exc.headers or {}), exc.read()
        try:
            body = json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            body = None
        return status, headers, body

    return fetch


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class Report:
    def __init__(self) -> None:
        self.facts: list[dict] = []
        self.failures: list[str] = []
        self.calls: list[dict] = []
        self.rate_limit_remaining: str | None = None

    def add(self, check: str, klass: str, ok: bool | None, detail: dict) -> None:
        self.facts.append({"check": check, "class": klass, "ok": ok, "detail": detail})
        if ok is False:
            self.failures.append(check)


def _get(fetch: Fetch, path: str, report: Report, check: str):
    status, headers, body = fetch(path)
    report.calls.append({"method": "GET", "path": path, "status": status})
    if headers:
        remaining = headers.get("X-RateLimit-Remaining") or headers.get(
            "x-ratelimit-remaining"
        )
        if remaining is not None:
            report.rate_limit_remaining = remaining
    if status != 200 or body is None:
        report.add(check, "VERIFIED", False, {"http_status": status})
        return None
    return body


def run_checks(
    fetch: Fetch,
    *,
    app_slug: str,
    installation_id: str,
    local_claude_md: bytes | None,
    expected_claude_md_sha256: str,
) -> Report:
    report = Report()

    # 1. Identité : slug et installation issus de l'action officielle, qui les
    # obtient de GitHub en s'authentifiant avec la clé privée de l'App.
    report.add(
        "app_identity_from_token_action",
        "VERIFIED",
        app_slug == EXPECTED_APP_SLUG and installation_id.isdigit(),
        {
            "app_slug": app_slug,
            "installation_id": installation_id,
            "expected_app_slug": EXPECTED_APP_SLUG,
        },
    )

    app = _get(fetch, f"/apps/{EXPECTED_APP_SLUG}", report, "app_public_record")
    if app is not None:
        declared = app.get("permissions") or {}
        writes = sorted(k for k, v in declared.items() if v not in ("read", None))
        report.add(
            "app_public_record",
            "VERIFIED",
            app.get("slug") == EXPECTED_APP_SLUG,
            {
                "slug": app.get("slug"),
                "app_id": app.get("id"),
                "owner": (app.get("owner") or {}).get("login"),
            },
        )
        report.add(
            "app_configured_permissions",
            "DECLARED",
            not writes,
            {"permissions": declared, "non_read_permissions": writes},
        )

    # 2. Périmètre de l'installation vu par le jeton.
    inst = _get(
        fetch, "/installation/repositories?per_page=100", report, "installation_scope"
    )
    if inst is not None:
        names = sorted(r.get("full_name") for r in inst.get("repositories") or [])
        report.add(
            "installation_scope",
            "VERIFIED",
            inst.get("total_count") == 1 and names == [FULL_NAME],
            {
                "total_count": inst.get("total_count"),
                "repositories": names,
                "repository_selection": inst.get("repository_selection"),
            },
        )

    report.add(
        "token_requested_permissions",
        "DECLARED",
        None,
        {
            "requested": REQUESTED_PERMISSIONS,
            "note": "demandées à la création du jeton ; l'absence d'écriture "
            "n'est pas exercée (aucune écriture tentée)",
        },
    )
    report.add(
        "token_write_denial",
        "NOT_VERIFIABLE",
        None,
        {
            "reason": "prouver un refus d'écriture exigerait une tentative "
            "d'écriture, exclue par la mission"
        },
    )

    # 3. HEAD exact de main.
    main_sha = None
    ref = _get(fetch, f"/repos/{OWNER}/{REPO}/git/ref/heads/main", report, "main_head")
    if ref is not None:
        main_sha = (ref.get("object") or {}).get("sha")
        report.add(
            "main_head",
            "VERIFIED",
            bool(main_sha and _SHA40.match(main_sha)),
            {"sha": main_sha},
        )

    # 4. CLAUDE.md au SHA exact de main et empreinte.
    if main_sha and _SHA40.match(main_sha):
        doc = _get(
            fetch,
            f"/repos/{OWNER}/{REPO}/contents/CLAUDE.md?ref={main_sha}",
            report,
            "claude_md_fingerprint",
        )
        if doc is not None:
            try:
                data = base64.b64decode(doc.get("content") or "", validate=False)
            except ValueError:
                data = b""
            blob = git_blob_sha1(data)
            sha256 = hashlib.sha256(data).hexdigest()
            detail = {
                "ref": main_sha,
                "bytes": len(data),
                "sha256": sha256,
                "git_blob_sha1_computed": blob,
                "git_blob_sha1_github": doc.get("sha"),
            }
            ok = data != b"" and blob == doc.get("sha")
            if local_claude_md is not None:
                detail["local_checkout_sha256"] = hashlib.sha256(
                    local_claude_md
                ).hexdigest()
                detail["local_matches_main"] = local_claude_md == data
            if expected_claude_md_sha256:
                detail["expected_sha256"] = expected_claude_md_sha256
                ok = ok and sha256 == expected_claude_md_sha256
            report.add("claude_md_fingerprint", "VERIFIED", ok, detail)

    # 5. Issue #461 et PR #462.
    issue = _get(
        fetch, f"/repos/{OWNER}/{REPO}/issues/{ISSUE_NUMBER}", report, "issue_461"
    )
    if issue is not None:
        report.add(
            "issue_461",
            "VERIFIED",
            issue.get("number") == ISSUE_NUMBER and "pull_request" not in issue,
            {
                "number": issue.get("number"),
                "state": issue.get("state"),
                "title": issue.get("title"),
                "updated_at": issue.get("updated_at"),
            },
        )

    pr_sha = None
    pr = _get(fetch, f"/repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}", report, "pr_462")
    if pr is not None:
        pr_sha = (pr.get("head") or {}).get("sha")
        report.add(
            "pr_462",
            "VERIFIED",
            pr.get("number") == PR_NUMBER and bool(pr_sha and _SHA40.match(pr_sha)),
            {
                "number": pr.get("number"),
                "state": pr.get("state"),
                "draft": pr.get("draft"),
                "merged": pr.get("merged"),
                "title": pr.get("title"),
                "head_sha": pr_sha,
                "head_ref": (pr.get("head") or {}).get("ref"),
                "base_ref": (pr.get("base") or {}).get("ref"),
            },
        )

    # 6. Contrôles CI au SHA exact de la PR.
    if pr_sha and _SHA40.match(pr_sha):
        runs: list[dict] = []
        total = None
        complete = False
        for page in range(1, MAX_CHECK_PAGES + 1):
            body = _get(
                fetch,
                f"/repos/{OWNER}/{REPO}/commits/{pr_sha}/check-runs?per_page=100&page={page}",
                report,
                "pr_462_check_runs",
            )
            if body is None:
                break
            total = body.get("total_count")
            batch = body.get("check_runs") or []
            runs.extend(batch)
            if len(batch) < 100 or (total is not None and len(runs) >= total):
                complete = True
                break
        if total is not None:
            summary: dict[str, int] = {}
            for r in runs:
                key = r.get("conclusion") or r.get("status") or "UNKNOWN"
                summary[key] = summary.get(key, 0) + 1
            report.add(
                "pr_462_check_runs",
                "VERIFIED",
                complete and all((r.get("head_sha") or pr_sha) == pr_sha for r in runs),
                {
                    "head_sha": pr_sha,
                    "total_count": total,
                    "collected": len(runs),
                    "complete": complete,
                    "by_conclusion": summary,
                    "runs": sorted(
                        (
                            {
                                "name": r.get("name"),
                                "status": r.get("status"),
                                "conclusion": r.get("conclusion"),
                            }
                            for r in runs
                        ),
                        key=lambda r: str(r["name"]),
                    ),
                },
            )
        report.add(
            "pr_462_commit_statuses",
            "NOT_VERIFIABLE",
            None,
            {
                "reason": "les statuts de commit exigent la permission "
                "« Commit statuses », non demandée"
            },
        )

    return report


def build_document(report: Report, meta: dict) -> dict:
    return {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": VERDICT_FAILED if report.failures else VERDICT_OK,
        "failures": report.failures,
        "run": meta,
        "boundaries": {
            "http_methods_used": sorted({c["method"] for c in report.calls}),
            "github_writes": 0,
            "vps_access": False,
            "deployment": False,
            "token_revocation": "post-step de actions/create-github-app-token "
            "(DELETE /installation/token, révoque ce seul jeton)",
        },
        "api_calls": report.calls,
        "rate_limit_remaining": report.rate_limit_remaining,
        "facts": report.facts,
    }


def to_markdown(doc: dict) -> str:
    lines = [
        "# GT01-G-SMOKE-01 — identité GitHub App de Sentinel",
        "",
        f"- Horodatage UTC : `{doc['generated_at_utc']}`",
        f"- Verdict : **{doc['verdict']}**",
        (
            f"- Run : `{doc['run'].get('run_id')}` (tentative {doc['run'].get('run_attempt')}),"
            f" SHA du workflow `{doc['run'].get('workflow_sha')}`"
        ),
        f"- Appels API : {len(doc['api_calls'])}, méthodes {doc['boundaries']['http_methods_used']}",
        "",
        "| Contrôle | Classe | Résultat |",
        "|---|---|---|",
    ]
    for fact in doc["facts"]:
        result = {True: "OK", False: "ÉCHEC", None: "—"}[fact["ok"]]
        lines.append(f"| `{fact['check']}` | {fact['class']} | {result} |")
    lines += [
        "",
        "<details><summary>Détail JSON</summary>",
        "",
        "```json",
        json.dumps(doc["facts"], indent=2, ensure_ascii=False),
        "```",
        "</details>",
        "",
    ]
    return "\n".join(lines)


def assert_no_secret(text: str, secrets: list[str]) -> None:
    for s in secrets:
        if s and s in text:
            raise RuntimeError("secret material detected in report; aborting")
    if re.search(
        r"gh[suopr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----", text
    ):
        raise RuntimeError("token-like material detected in report; aborting")


def main() -> int:
    token = os.environ.get("SENTINEL_TOKEN", "")
    if not token:
        print("SENTINEL_TOKEN absent", file=sys.stderr)
        return 2
    expected = os.environ.get("EXPECTED_CLAUDE_MD_SHA256", "").strip().lower()
    if expected and not _SHA256.match(expected):
        print(
            "EXPECTED_CLAUDE_MD_SHA256 invalide (64 hexadécimaux attendus)",
            file=sys.stderr,
        )
        return 2
    out_dir = Path(os.environ.get("REPORT_DIR", "."))
    local = Path("CLAUDE.md")
    report = run_checks(
        make_fetch(token),
        app_slug=os.environ.get("APP_SLUG", ""),
        installation_id=os.environ.get("INSTALLATION_ID", ""),
        local_claude_md=local.read_bytes() if local.is_file() else None,
        expected_claude_md_sha256=expected,
    )
    env = os.environ.get
    meta = {
        "run_id": env("GITHUB_RUN_ID"),
        "run_attempt": env("GITHUB_RUN_ATTEMPT"),
        "actor": env("GITHUB_ACTOR"),
        "event": env("GITHUB_EVENT_NAME"),
        "ref": env("GITHUB_REF"),
        "workflow_sha": env("GITHUB_SHA"),
    }
    doc = build_document(report, meta)
    text_json = json.dumps(doc, indent=2, ensure_ascii=False)
    text_md = to_markdown(doc)
    assert_no_secret(text_json + text_md, [token])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "gt01_g_smoke_identity.json").write_text(
        text_json + "\n", encoding="utf-8"
    )
    (out_dir / "gt01_g_smoke_identity.md").write_text(text_md, encoding="utf-8")
    print(text_md)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text_md)
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
