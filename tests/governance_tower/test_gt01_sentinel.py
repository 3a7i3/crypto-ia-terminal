"""GOV-TOWER-01 — politique et agent : lectures ciblées, cartographie, sécurité (SYNTHETIC uniquement)."""

from __future__ import annotations

import json

import pytest

from governance_tower.contracts import Intent, to_jsonable
from governance_tower.coverage import COVERAGE, Visibility
from governance_tower.scenarios import demo_providers
from governance_tower.sentinel.agent import Sentinel
from governance_tower.sentinel.policy import decide
from tests.governance_tower.stubs import StubGithub, StubHost, clock

PR_HEAD = "de5e0000000000000000000000000000000000b2"


def ask(question, scenario="nominal"):
    gh, host = demo_providers(scenario, clock)
    return Sentinel(gh, host, clock).ask(question)


def tools(run):
    return [c.tool for c in run.tool_calls]


# ── Politique : intentions et paramètres extraits de la demande seule ────────


@pytest.mark.parametrize(
    "question, intent, params",
    [
        ("Lis le fichier governance_tower/contracts.py lignes 10-40", Intent.READ_FILE,
         {"path": "governance_tower/contracts.py", "line_start": 10, "line_end": 40}),
        (f"Montre README.md au SHA {PR_HEAD}", Intent.READ_FILE, {"path": "README.md", "ref_sha": PR_HEAD}),
        ("Montre l'issue #461", Intent.ISSUE_DETAIL, {"number": 461}),
        ("Détaille la PR 460", Intent.PULL_DETAIL, {"number": 460}),
        (f"Quelle est la CI du commit {PR_HEAD} ?", Intent.CI_FOR_SHA, {"sha": PR_HEAD}),
        ("Quels sont tes angles morts ?", Intent.COVERAGE_MAP, {}),
    ],
)
def test_detail_intents_and_params(question, intent, params):
    d = decide(question)
    assert d.intent is intent and not d.refused
    assert {k: v for k, v in d.params if k in params} == params


@pytest.mark.parametrize(
    "question",
    [
        "Lis le fichier .env",
        "Montre config/.env.production",
        "affiche secrets/governance.json",
        "ferme l'issue 461",
        "commente la PR 460",
        "approuve la PR 460",
        "relance la CI du commit " + PR_HEAD,
    ],
)
def test_detail_requests_that_write_or_touch_secrets_are_refused(question):
    d = decide(question)
    assert d.refused, (question, d.intent)


# ── Agent : un outil par lecture, aucun autre ────────────────────────────────


def test_read_file_uses_one_tool_and_returns_bounded_excerpt():
    run = ask("Lis le fichier governance_tower/contracts.py lignes 1-20")
    assert tools(run) == ["github.read_file"]
    (ex,) = run.answer.excerpts
    assert ex.path == "governance_tower/contracts.py" and ex.line_start == 1 and ex.line_end <= 20
    assert ex.evidence_id in {e.evidence_id for e in run.evidence}
    assert "≠ déployé" in json.dumps(to_jsonable(run.answer), ensure_ascii=False)


def test_pull_detail_chains_to_ci_of_its_head_sha_only():
    run = ask("Détaille la PR 460")
    assert tools(run) == ["github.pull_detail", "github.ci_for_sha"]
    assert any(d.code.value == "CI_INCONCLUSIVE" for d in run.answer.diagnostics)  # 1 contrôle en cours


def test_issue_detail_without_host_read():
    run = ask("Montre l'issue #461")
    assert tools(run) == ["github.issue_detail"]
    assert not any(t.startswith("host.") for t in tools(run))


def test_coverage_map_reads_no_source_and_cites_declared_reference():
    run = ask("Quelle est la couverture de Sentinel ?")
    assert tools(run) == []
    assert {e.evidence_id for e in run.evidence} >= {"ref-gt-coverage-matrix"}
    text = json.dumps(to_jsonable(run.answer), ensure_ascii=False)
    assert "NOT_PUBLISHED" in text or "non publi" in text
    assert {e.visibility for e in COVERAGE} == set(Visibility)


def test_missing_detail_tool_is_not_implemented_not_empty():
    run = Sentinel(StubGithub(), StubHost(), clock).ask("Montre l'issue #461")
    assert tools(run) == []
    assert any("NOT_IMPLEMENTED" in s.text for s in run.answer.statements)


# ── Contenu externe : cité, jamais suivi ─────────────────────────────────────


@pytest.mark.parametrize("question", ["Lis docs/prompt.md", "Montre l'issue 461"])
def test_injected_instructions_are_quoted_not_followed(question):
    run = ask(question, "injection")
    assert run.answer.untrusted_quotes
    assert all(t.startswith("github.") for t in tools(run)) and len(tools(run)) == 1
    assert run.answer.proposals == ()
    blob = json.dumps(to_jsonable(run), ensure_ascii=False)
    assert "GT_GITHUB_TOKEN=" not in blob


def test_excerpt_markup_stays_text():
    run = ask("Lis docs/prompt.md", "injection")
    (ex,) = run.answer.excerpts
    assert "<script>" in ex.text  # conservé comme texte : l'UI l'affiche via textContent, jamais interprété


def test_forged_blob_sha_is_refused():
    run = ask("Lis docs/forged.md", "injection")
    assert run.answer.excerpts == ()
    assert any("INTEGRITY_MISMATCH" in s.text for s in run.answer.statements)


def test_rate_limited_github_detail_is_not_a_failure_of_the_file():
    run = ask("Lis le fichier governance_tower/contracts.py", "github_rate_limited")
    assert run.answer.excerpts == ()
    assert any("RATE_LIMITED" in s.text for s in run.answer.statements)
