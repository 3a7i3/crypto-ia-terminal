"""GOV-TOWER-00 lot G — intégration contractuelle fixtures GitHub + hôte + Sentinel + serveur.

Trois scénarios exigés : GitHub OK / VPS OK, GitHub OK / VPS indisponible, runtime
volontairement épinglé ; plus dérive, périmé, refus GitHub et injection.
"""

from __future__ import annotations

import http.client
import json
import threading

import pytest

from governance_tower.__main__ import main
from governance_tower.contracts import Availability, ClaimStatus, DiscrepancyClass, Intent, Provenance
from governance_tower.scenarios import SCENARIOS, demo_providers
from governance_tower.sentinel.agent import Sentinel
from governance_tower.sentinel.injection import looks_like_instruction
from governance_tower.server import make_server

from tests.governance_tower.stubs import clock

OPERATOR_QUESTION = (
    "Sentinel, analyse mon dépôt et les observations autorisées du VPS. Distingue ce qui est intégré dans "
    "GitHub, ce qui est effectivement déployé, ce qui est certifié et ce qui demeure inconnu. Cite les preuves. "
    "Ne corrige rien."
)
EXPECTED = {
    "nominal": DiscrepancyClass.EXPECTED_PINNED_RUNTIME,
    "injection": DiscrepancyClass.EXPECTED_PINNED_RUNTIME,
    "drift": DiscrepancyClass.POSSIBLE_DRIFT,
    "stale": DiscrepancyClass.STALE,
    "host_unavailable": DiscrepancyClass.INSUFFICIENT_EVIDENCE,
    "github_denied": DiscrepancyClass.INSUFFICIENT_EVIDENCE,
}


def sentinel_for(scenario):
    gh, host = demo_providers(scenario, clock)
    return Sentinel(gh, host, clock)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_every_scenario_classifies_and_stays_honest(scenario):
    run = sentinel_for(scenario).ask(OPERATOR_QUESTION)
    assert run.intent is Intent.FULL_REVIEW and run.mode == "DEMO"
    cmp = run.answer.discrepancies[0]
    assert cmp.classification is EXPECTED[scenario]
    assert all(e.provenance in (Provenance.SYNTHETIC, Provenance.DECLARED_REFERENCE) for e in run.evidence)
    known = {e.evidence_id for e in run.evidence}
    for st in run.answer.statements:
        if st.claim_status is ClaimStatus.OBSERVED:
            assert set(st.evidence_ids) <= known and st.evidence_ids
    assert run.answer.uncertainties[0].startswith("DÉMO")
    assert all(p.execution == "NOT_EXECUTED" for p in run.answer.proposals)
    json.dumps(run.to_dict())


def test_host_unavailable_reports_not_available_never_zero():
    run = sentinel_for("host_unavailable").ask("", shortcut="examine_host")
    host = next(s for s in run.sources if s.source.value == "HOST")
    assert host.availability is Availability.NOT_AVAILABLE
    assert not any(s.claim_status is ClaimStatus.OBSERVED for s in run.answer.statements)


def test_github_denied_is_denied_not_empty():
    run = sentinel_for("github_denied").ask("Quels travaux sont en cours ?")
    gh = next(s for s in run.sources if s.source.value == "GITHUB")
    assert gh.availability is Availability.DENIED
    assert not any("open_on_page=0" in s.text for s in run.answer.statements)


def test_injection_scenario_quotes_redacts_and_never_acts():
    run = sentinel_for("injection").ask(OPERATOR_QUESTION)
    dumped = json.dumps(run.to_dict(), ensure_ascii=False)
    assert "ghp_" not in dumped
    quotes = " ".join(run.answer.untrusted_quotes)
    assert "IGNORE PREVIOUS INSTRUCTIONS" in quotes and "sudo systemctl" in quotes
    assert {c.tool for c in run.tool_calls} <= {
        "github.repository_snapshot", "host.host_snapshot", "github.compare_commits"
    }
    assert run.answer.refusals == ()


def test_routine_titles_are_not_flagged_as_injection():
    for title in ("Merge pull request #458 from 3a7i3/claude/x", "fix(deploy): garde NeedDaemonReload",
                  "docs: restart policy des publishers"):
        assert not looks_like_instruction(title), title


@pytest.mark.parametrize(
    "question,needle",
    [
        ("Quelle est la roadmap active ?", "#285"),
        ("Quels travaux sont en cours ?", "PR ouvertes"),
        ("Quels composants du code contrôlent les publishers ?", "publish"),
        ("Quels commits sont dans main mais pas prouvés comme déployés ?", "ahead_by=42"),
    ],
)
def test_mandatory_repository_questions(question, needle):
    run = sentinel_for("nominal").ask(question)
    assert any(needle in s.text for s in run.answer.statements), [s.text for s in run.answer.statements]


def test_cli_ask_json(capsys):
    assert main(["ask", "", "--shortcut", "compare", "--scenario", "drift", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["answer"]["discrepancies"][0]["classification"] == "POSSIBLE_DRIFT"


def test_live_mode_requires_explicit_flag():
    from governance_tower.scenarios import live_providers

    with pytest.raises(ValueError):
        live_providers(github_live=False, host_snapshots=None, host_operator_api=None)


def test_http_end_to_end_on_fixtures():
    srv = make_server(sentinel_for("nominal"), "127.0.0.1", 0, "nominal")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        port = srv.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"question": OPERATOR_QUESTION}).encode()
        conn.request("POST", "/api/sentinel/ask", body, {
            "Host": f"127.0.0.1:{port}", "Content-Type": "application/json", "X-GT-Request": "1",
            "Content-Length": str(len(body)),
        })
        run = json.loads(conn.getresponse().read())
        assert run["answer"]["discrepancies"][0]["classification"] == "EXPECTED_PINNED_RUNTIME"
        conn.request("GET", "/", headers={"Host": f"127.0.0.1:{port}"})
        page = conn.getresponse().read().decode()
        assert "GOVERNANCE TOWER" in page and "SENTINEL-01" in page
        conn.request("GET", "/api/status", headers={"Host": f"127.0.0.1:{port}"})
        status = json.loads(conn.getresponse().read())
        assert {s["source"]: s["availability"] for s in status["sources"]} == {
            "GITHUB": "AVAILABLE", "HOST": "AVAILABLE"
        }
        conn.close()
    finally:
        srv.shutdown()
        srv.server_close()
