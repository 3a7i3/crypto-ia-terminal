"""GOV-TOWER-01 M3 — diagnostics croisés GitHub × snapshots (SYNTHETIC uniquement).

Chaque diagnostic sépare observation, interprétation possible et vérifications
restantes ; aucun n'exprime une violation ni une santé, aucun n'exécute rien.
"""

from __future__ import annotations

import json

import pytest

from governance_tower.contracts import (
    DIAGNOSTICS_WITHOUT_EVIDENCE,
    Availability,
    ContractError,
    Diagnostic,
    DiagnosticCode,
    DiagnosticLevel,
    Intent,
    to_jsonable,
)
from governance_tower.scenarios import demo_providers
from governance_tower.sentinel.agent import Sentinel
from governance_tower.sentinel.policy import decide
from tests.governance_tower.stubs import HEAD, PINNED, StubGithub, StubHost, clock

VERSION_Q = "Le VPS exécute-t-il la même version que GitHub ?"
FULL_Q = "Analyse le dépôt et le VPS, distingue ce qui est certifié et inconnu"


def diags(scenario: str, question: str = VERSION_Q):
    gh, host = demo_providers(scenario, clock)
    run = Sentinel(gh, host, clock).ask(question)
    return run, {d.diagnostic_id: d for d in run.answer.diagnostics}


# ── Routage des questions croisées ───────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [VERSION_Q, "Le VPS est-il aligné avec main ?", "Le serveur est-il à jour par rapport au dépôt ?"],
)
def test_cross_version_questions_are_comparisons(question):
    assert decide(question).intent is Intent.COMPARE


@pytest.mark.parametrize("question", ["Quelle version tourne sur le VPS ?", "La branche main est-elle à jour ?"])
def test_single_side_questions_are_not_comparisons(question):
    assert decide(question).intent is not Intent.COMPARE


# ── Scénarios : un code par situation ────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario, code, level",
    [
        ("nominal", DiagnosticCode.EXPECTED_PINNED_RUNTIME, DiagnosticLevel.INFO),  # GitHub en avance sur le pin
        ("drift", DiagnosticCode.POSSIBLE_DRIFT, DiagnosticLevel.ATTENTION),
        ("stale", DiagnosticCode.STALE, DiagnosticLevel.UNKNOWN),
        ("host_unavailable", DiagnosticCode.SOURCE_UNAVAILABLE, DiagnosticLevel.UNKNOWN),
        ("no_deployment_id", DiagnosticCode.NO_DEPLOYED_BUILD_ID, DiagnosticLevel.UNKNOWN),
    ],
)
def test_runtime_diagnostic_per_scenario(scenario, code, level):
    _, d = diags(scenario)
    assert (d["diag-runtime"].code, d["diag-runtime"].level) == (code, level)


def test_github_ahead_of_pin_is_expected_not_a_violation():
    _, d = diags("nominal")
    rt = d["diag-runtime"]
    assert "attendu" in rt.interpretation.lower() and "116634be0d3c" in rt.observation
    assert any("42 commit" in v and "≠ déployé" in v for v in rt.verification)
    assert any("NON VÉRIFIÉ" in v for v in rt.verification)  # hash de configuration non publié
    assert rt.proposal_ref is None


def test_drift_is_possible_not_proven_and_proposes_only_on_full_review():
    _, d = diags("drift")
    assert "non prouvée" in d["diag-runtime"].interpretation
    run, d = diags("drift", FULL_Q)
    assert d["diag-runtime"].proposal_ref == "prop-f-runtime-drift"
    assert "prop-f-runtime-drift" in {p.proposal_id for p in run.answer.proposals}
    assert all((p.authority, p.execution) == ("NONE", "NOT_EXECUTED") for p in run.answer.proposals)


@pytest.mark.parametrize(
    "scenario, code, needle",
    [
        ("github_denied", DiagnosticCode.SOURCE_DENIED, "aucun contournement"),
        ("github_rate_limited", DiagnosticCode.SOURCE_RATE_LIMITED, "Quota ≠ panne"),
    ],
)
def test_github_absence_is_named_and_main_stays_unknown(scenario, code, needle):
    _, d = diags(scenario)
    assert d["diag-github"].code is code and needle in d["diag-github"].interpretation
    assert "main n'a pas été lu" in d["diag-runtime"].observation
    assert not any("commit(s) de main" in v for v in d["diag-runtime"].verification)


def test_active_is_not_health():
    _, d = diags("nominal")
    svc = d["diag-service"]
    assert svc.code is DiagnosticCode.ACTIVE_NOT_HEALTH and svc.level is DiagnosticLevel.INFO
    assert "ne prouve ni" in svc.interpretation
    assert any("angle mort" in v for v in svc.verification)


def test_partial_host_evidence():
    _, d = diags("partial")
    assert d["diag-host-partial"].code is DiagnosticCode.PARTIAL_HOST_EVIDENCE
    assert "même instant" in d["diag-host-partial"].interpretation


def test_compare_unavailable_is_not_comparable():
    _, d = diags("drift")
    assert d["diag-compare"].code is DiagnosticCode.NOT_COMPARABLE
    assert any("nombre de commits inconnu" in v for v in d["diag-runtime"].verification)


def test_host_unavailable_never_claims_running_service():
    _, d = diags("host_unavailable")
    assert "diag-service" not in d


# ── Stubs : branches non couvertes par les fixtures ──────────────────────────


def stub_run(question=VERSION_Q, gh=None, host=None):
    return Sentinel(gh or StubGithub(), host or StubHost(), clock, pinned=()).ask(question)


def test_aligned_with_main_without_pin_is_not_health():
    run = stub_run(host=StubHost(deployed=HEAD))
    d = {g.diagnostic_id: g for g in run.answer.diagnostics}
    assert d["diag-runtime"].code is DiagnosticCode.ALIGNED_WITH_MAIN
    assert "≠ même configuration ni même santé" in d["diag-runtime"].interpretation


def test_service_not_running_is_attention():
    run = stub_run(host=StubHost(active=("failed", "failed")))
    d = {g.diagnostic_id: g for g in run.answer.diagnostics}
    assert d["diag-service"].code is DiagnosticCode.SERVICE_NOT_RUNNING
    assert d["diag-service"].level is DiagnosticLevel.ATTENTION


def test_ci_states_are_failure_or_inconclusive_never_green_by_default():
    for ci, code in (("FAILURE", DiagnosticCode.CI_FAILURE), ("PENDING", DiagnosticCode.CI_INCONCLUSIVE),
                     ("NONE", DiagnosticCode.CI_INCONCLUSIVE)):
        run = stub_run("Analyse le dépôt GitHub", gh=StubGithub(ci=ci))
        codes = {g.code for g in run.answer.diagnostics}
        assert code in codes, (ci, codes)
    run = stub_run("Analyse le dépôt GitHub", gh=StubGithub(ci="SUCCESS"))
    assert not {DiagnosticCode.CI_FAILURE, DiagnosticCode.CI_INCONCLUSIVE} & {g.code for g in run.answer.diagnostics}


# ── Contrat Diagnostic ───────────────────────────────────────────────────────


def _diag(**over):
    base = dict(diagnostic_id="diag-x", code=DiagnosticCode.STALE, level=DiagnosticLevel.UNKNOWN, title="t",
                observation="o", interpretation="i", verification=("v",), evidence=())
    base.update(over)
    return Diagnostic(**base)


def test_diagnostic_contract_rejects_empty_verification_and_bad_vocab():
    with pytest.raises(ContractError):
        _diag(verification=())
    with pytest.raises(ContractError):
        _diag(verification=tuple("v" * 3 for _ in range(13)))
    with pytest.raises(ContractError):
        _diag(code="VIOLATION")
    with pytest.raises(ContractError):
        _diag(level="CRITICAL")


def test_no_diagnostic_code_expresses_violation_or_health():
    names = " ".join(c.value for c in DiagnosticCode)
    for forbidden in ("VIOLATION", "HEALTHY", "CERTIFIED", "OK"):
        assert forbidden not in names.split()
    assert "HEALTH" not in names.replace("ACTIVE_NOT_HEALTH", "")


def test_every_scenario_diagnostic_cites_evidence_present_in_run():
    for scenario in ("nominal", "drift", "stale", "host_unavailable", "github_denied", "github_rate_limited",
                     "no_deployment_id", "partial", "injection"):
        run, d = diags(scenario, FULL_Q)
        ids = {e.evidence_id for e in run.evidence}
        for g in d.values():
            assert g.evidence or g.code in DIAGNOSTICS_WITHOUT_EVIDENCE, (scenario, g.diagnostic_id)
            assert {e.evidence_id for e in g.evidence} <= ids
            assert g.verification
        json.dumps(to_jsonable(run))  # sérialisable pour l'API


def test_synthetic_runs_stay_synthetic():
    run, _ = diags("nominal")
    assert run.mode == "DEMO"
    assert all(e.provenance.value in {"SYNTHETIC", "DECLARED_REFERENCE"} for e in run.evidence)
    assert all(e.locator.startswith("fixture:") for e in run.evidence if e.provenance.value == "SYNTHETIC")
    assert PINNED[:12] in json.dumps(to_jsonable(run.answer), ensure_ascii=False)
    assert Availability.AVAILABLE.value  # vocabulaire fermé importable
