#!/usr/bin/env python3
"""GT01-G-INTEGRATION-01 — Sentinel (backend Governance Tower) avec l'identité GitHub App.

Exécuté uniquement par `.github/workflows/gt01-g-integration-sentinel-backend.yml`
(workflow_dispatch, `main` seulement). Le jeton d'installation, créé par l'action
officielle dans l'environnement protégé, est passé au backend par
`GT_SENTINEL_INSTALLATION_TOKEN` ; le backend tourne en mode strict
`APP_INSTALLATION` (jamais de requête anonyme), pose une question READ-ONLY
bornée et produit un rapport (JSON + Markdown) sans le jeton.

Chaîne exercée : jeton temporaire → backend du checkout `main` → GET allowlistés
→ EvidenceRef / AgentRun → rapport borné. La révocation reste au post-step de
l'action. Aucune écriture GitHub, aucun accès VPS, aucun artifact publié.

Classes de preuve : VERIFIED (observé avec le jeton dans une réponse GitHub),
DECLARED (fourni par l'étape qui a créé le jeton), NOT_VERIFIABLE (hors portée).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # `python3 -I` n'ajoute ni le cwd ni le dossier du script
    sys.path.insert(0, str(ROOT))

import governance_tower  # noqa: E402
from governance_tower.contracts import Provenance, SourceKind, format_utc, utc_now  # noqa: E402
from governance_tower.providers.github import (  # noqa: E402
    APP_SLUG_ENV,
    INSTALLATION_TOKEN_ENV,
    SENTINEL_APP_SLUG,
    AuthMode,
    HttpGithubProvider,
)
from governance_tower.providers.host import NotConfiguredHostProvider  # noqa: E402
from governance_tower.sentinel.agent import Sentinel  # noqa: E402

SCHEMA = "gt01_g_integration_run.v1"
VERDICT_OK = "GT01_G_INTEGRATION_VERIFIED"
VERDICT_FAILED = "GT01_G_INTEGRATION_FAILED"
REPO = "3a7i3/crypto-ia-terminal"
SHORTCUT = "examine_repository"
MAX_REPORT_BYTES = 64 * 1024
MAX_STATEMENTS = 20
MAX_TEXT = 500
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_DIGITS = re.compile(r"^[0-9]{1,20}$")
_TOKEN_SHAPES = re.compile(r"gh[opsur]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")


class SecretInReport(RuntimeError):
    pass


def _clip(text: Any) -> str:
    s = str(text)
    return s if len(s) <= MAX_TEXT else s[: MAX_TEXT - 1] + "…"


def _check(name: str, klass: str, ok: bool | None, detail: dict) -> dict:
    return {"check": name, "class": klass, "ok": ok, "detail": detail}


def run(
    env: Mapping[str, str],
    *,
    transport: Callable | None = None,
    clock: Callable = utc_now,
) -> dict:
    """Pose la question bornée et retourne le document de rapport (sans aucun secret)."""
    checks: list[dict] = []
    checkout_sha = env.get("GITHUB_SHA", "")
    package_dir = Path(governance_tower.__file__).resolve().parent
    checks.append(
        _check(
            "backend_from_checkout",
            "VERIFIED",
            package_dir == ROOT / "governance_tower" and bool(_SHA40.match(checkout_sha)),
            {"checkout_sha": checkout_sha or None, "package": str(package_dir.relative_to(ROOT))
             if package_dir.is_relative_to(ROOT) else "OUTSIDE_CHECKOUT"},
        )
    )
    slug = env.get(APP_SLUG_ENV, "")
    installation_id = env.get("GT_SENTINEL_INSTALLATION_ID", "")
    checks.append(
        _check(
            "app_identity_declared",
            "DECLARED",
            slug == SENTINEL_APP_SLUG and bool(_DIGITS.match(installation_id)),
            {
                "app_slug": slug if slug == SENTINEL_APP_SLUG else "UNEXPECTED",
                "installation_id": installation_id if _DIGITS.match(installation_id) else "INVALID",
                "source": "sorties de actions/create-github-app-token (obtenues avec la clé privée)",
            },
        )
    )

    github = HttpGithubProvider(
        REPO,
        clock=clock,
        transport=transport,
        auth_mode=AuthMode.APP_INSTALLATION,
        token_env=INSTALLATION_TOKEN_ENV,
    )
    host = NotConfiguredHostProvider(clock)
    sentinel = Sentinel(github, host, clock)
    agent_run = sentinel.ask("", shortcut=SHORTCUT)

    auth = github.auth_status()
    checks.append(
        _check(
            "installation_scope",
            "VERIFIED",
            auth.get("identity") == "INSTALLATION_SCOPE_VERIFIED",
            {"identity": auth.get("identity"), "reason": auth.get("reason"),
             "repository": auth.get("installation_repository")},
        )
    )
    checks.append(
        _check(
            "agent_run_contract",
            "VERIFIED",
            agent_run.mode == "LIVE_READ"
            and agent_run.operational_authority == "DENIED"
            and agent_run.capability == "OBSERVE_ONLY"
            and not agent_run.answer.refusals,
            {"mode": agent_run.mode, "intent": agent_run.intent.value,
             "capability": agent_run.capability, "operational_authority": agent_run.operational_authority},
        )
    )
    gh_evidence = [e for e in agent_run.evidence if e.source is SourceKind.GITHUB]
    not_ok = sorted({(e.note or "").split(" · ")[0] for e in gh_evidence} - {"GET HTTP 200"})
    evidence_ok = bool(gh_evidence) and not not_ok and all(
        e.provenance is Provenance.LIVE_READ
        and e.locator.startswith("https://api.github.com/")
        and (e.note or "").endswith("auth APP_INSTALLATION")
        for e in gh_evidence
    )
    checks.append(
        _check(
            "evidence_live_authenticated",
            "VERIFIED",
            evidence_ok,
            {"github_evidence": len(gh_evidence), "non_200": not_ok},
        )
    )
    head = next((e.source_sha for e in gh_evidence if e.evidence_id == "gh-live-branch"), None)
    checks.append(
        _check(
            "main_head_matches_checkout",
            "VERIFIED",
            head is not None and head == checkout_sha,
            {"observed_head": head, "checkout_sha": checkout_sha or None,
             "status": "MATCH" if head is not None and head == checkout_sha else
             ("HEAD_NOT_OBSERVED" if head is None else "CHECKOUT_DIVERGES_FROM_MAIN")},
        )
    )
    budget = github.budget_status()
    failed_tools = [c.tool for c in agent_run.tool_calls if c.availability.value not in ("AVAILABLE", "STALE")]
    checks.append(
        _check(
            "bounded_reads",
            "VERIFIED",
            budget["used_this_question"] <= budget["per_question"] and not failed_tools,
            {"requests_sent": github.requests_sent, "per_question": budget["per_question"],
             "failed_tool_calls": failed_tools},
        )
    )
    checks.append(
        _check(
            "host_observation",
            "NOT_VERIFIABLE",
            None,
            {"reason": "aucune source hôte configurée dans ce job : aucun accès VPS"},
        )
    )
    checks.append(
        _check(
            "token_revocation",
            "NOT_VERIFIABLE",
            None,
            {"reason": "révocation exécutée par le post-step de l'action, après ce script"},
        )
    )

    verified = all(c["ok"] for c in checks if c["class"] in ("VERIFIED", "DECLARED"))
    answer = agent_run.answer
    return {
        "schema": SCHEMA,
        "verdict": VERDICT_OK if verified else VERDICT_FAILED,
        "generated_at_utc": format_utc(clock()),
        "repository": REPO,
        "checkout_sha": checkout_sha or None,
        "question_shortcut": SHORTCUT,
        "checks": checks,
        "agent_run": {
            "run_id": agent_run.run_id,
            "intent": agent_run.intent.value,
            "mode": agent_run.mode,
            "started_at_utc": agent_run.started_at_utc,
            "finished_at_utc": agent_run.finished_at_utc,
            "summary": _clip(answer.summary),
            "statements": [
                {"status": s.claim_status.value, "text": _clip(s.text), "evidence": list(s.evidence_ids)}
                for s in answer.statements[:MAX_STATEMENTS]
            ],
            "statements_total": len(answer.statements),
            "tool_calls": [{"tool": c.tool, "availability": c.availability.value} for c in agent_run.tool_calls],
            "evidence": [
                {"id": e.evidence_id, "provenance": e.provenance.value, "locator": e.locator,
                 "source_sha": e.source_sha, "note": e.note}
                for e in agent_run.evidence
            ],
        },
        "boundaries": [
            "GET uniquement, liste fermée ; aucune écriture GitHub",
            "aucun accès VPS, aucun déploiement, aucun artifact",
            "fait observé à cet instant ≠ déploiement ≠ certification",
        ],
    }


def to_markdown(doc: dict) -> str:
    lines = [
        f"# GT01-G-INTEGRATION — {doc['verdict']}",
        "",
        f"- Dépôt : `{doc['repository']}` · checkout `{doc['checkout_sha']}`",
        f"- Généré : {doc['generated_at_utc']} · question `{doc['question_shortcut']}`",
        "",
        "| Contrôle | Classe | Résultat |",
        "|---|---|---|",
    ]
    for c in doc["checks"]:
        res = "n/a" if c["ok"] is None else ("OK" if c["ok"] else "ÉCHEC")
        lines.append(f"| {c['check']} | {c['class']} | {res} |")
    run_ = doc["agent_run"]
    lines += ["", f"**AgentRun** `{run_['run_id']}` · {run_['mode']} · {run_['intent']}", "", run_["summary"], ""]
    lines += [f"- `{e['id']}` · {e['provenance']} · {e['locator']}" for e in run_["evidence"]]
    lines += ["", *[f"> {b}" for b in doc["boundaries"]]]
    return "\n".join(lines) + "\n"


def assert_no_secret(text: str, secrets: list[str]) -> None:
    for s in secrets:
        if s and s in text:
            raise SecretInReport("jeton présent dans le rapport")
    if _TOKEN_SHAPES.search(text) or _PRIVATE_KEY.search(text):
        raise SecretInReport("motif de jeton ou de clé privée dans le rapport")


def render(doc: dict, secrets: list[str]) -> tuple[str, str]:
    as_json = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True)
    as_md = to_markdown(doc)
    for text in (as_json, as_md):
        assert_no_secret(text, secrets)
        if len(text.encode("utf-8")) > MAX_REPORT_BYTES:
            raise SecretInReport("rapport hors borne")  # jamais publié tronqué
    return as_json, as_md


def main() -> int:
    env = dict(os.environ)
    token = env.get(INSTALLATION_TOKEN_ENV, "")
    try:
        doc = run(env)
        as_json, as_md = render(doc, [token])
    except SecretInReport as exc:
        print(f"{VERDICT_FAILED}: rapport refusé ({exc})", file=sys.stderr)
        return 1
    report_dir = env.get("REPORT_DIR")
    if report_dir:
        out = Path(report_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "gt01_g_integration.json").write_text(as_json + "\n", encoding="utf-8")
        (out / "gt01_g_integration.md").write_text(as_md, encoding="utf-8")
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(as_md)
    print(as_json)
    return 0 if doc["verdict"] == VERDICT_OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
