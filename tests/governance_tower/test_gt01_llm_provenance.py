"""GOV-TOWER-01-R1 — frontière de provenance du raisonneur modèle (HORS LIGNE, SYNTHETIC).

Défaut corrigé (revue indépendante sur 11d4493) : avec ``allow_host_facts=False``,
``build_fact_bundle`` retirait les observations HOST mais transmettait les diagnostics
et l'explication d'écart (catégorie ANALYSIS) dont le texte cite des valeurs VPS
(SHA déployé, état systemd…). La règle porte désormais sur la provenance déclarée par
l'analyse ; une provenance inconnue est traitée comme VPS.

Aucun réseau, aucun modèle : le transport est ``OfflineMockTransport``.
"""

from __future__ import annotations

import dataclasses
import json
import socket

import pytest

from governance_tower.contracts import Availability, Domain, EvidenceRef, Observation, Provenance, SourceKind, to_jsonable
from governance_tower.scenarios import demo_providers
from governance_tower.sentinel.agent import Sentinel
from governance_tower.sentinel.analysis import HOST, analyse
from governance_tower.sentinel.llm_adapter import (
    OfflineLlmReasoner,
    OfflineMockTransport,
    build_fact_bundle,
    build_request,
)
from governance_tower.sentinel.reasoner import DeterministicDemoReasoner, ReasonerDisabled
from tests.governance_tower.stubs import HEAD, StubGithub, StubHost, clock

VERSION_Q = "Le VPS exécute-t-il la même version que GitHub ?"
CANARY_SHA = "c0ffee0000000000000000000000000000c0ffee"


class Capture(DeterministicDemoReasoner):
    def __init__(self) -> None:
        super().__init__()
        self.facts = None

    def compose(self, facts):
        self.facts = facts
        return super().compose(facts)


def run_facts(gh, host, question=VERSION_Q):
    cap = Capture()
    Sentinel(gh, host, clock, reasoner=cap).ask(question)
    assert cap.facts is not None
    return cap.facts


def scenario_facts(name, question=VERSION_Q):
    return run_facts(*demo_providers(name, clock), question=question)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("aucune connexion réseau n'est admise")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


# ── Outils d'inspection ──────────────────────────────────────────────────────


def _leaves(value, out):
    if isinstance(value, dict):
        for v in value.values():
            _leaves(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _leaves(v, out)
    elif isinstance(value, str) and len(value) >= 8:
        out.add(value)
        if len(value) == 40 and all(c in "0123456789abcdef" for c in value):
            out.add(value[:12])  # forme abrégée utilisée dans les textes d'analyse


def host_tokens(facts) -> set[str]:
    """Valeurs publiées par le VPS qui ne sont connues d'aucune source non-VPS de ce run."""
    tokens: set[str] = set()
    if facts.host is not None:
        for obs in facts.host.observations:
            _leaves(obs.value, tokens)
            for ev in obs.evidence:
                _leaves([ev.observed_at_utc, ev.source_sha, ev.locator], tokens)
        _leaves([facts.host.deployed_source_sha], tokens)
    non_host = json.dumps(
        [to_jsonable(o) for o in (facts.repo.observations if facts.repo else ())]
        + [to_jsonable(p) for p in facts.pinned]
        + [to_jsonable(o) for o in (facts.code, *facts.details) if o is not None],
        ensure_ascii=False,
    )
    return {t for t in tokens if t not in non_host}


def host_evidence_ids(facts) -> set[str]:
    ids = set()
    if facts.host is not None:
        ids |= {e.evidence_id for o in facts.host.observations for e in o.evidence}
    for item in (*facts.analysis.diagnostics, *facts.analysis.discrepancies):
        ids |= {e.evidence_id for e in item.evidence if e.source is SourceKind.HOST}
    return ids


def host_dependent_diagnostics(facts):
    return [g for g in facts.analysis.diagnostics if HOST in facts.analysis.provenance["diagnostic:" + g.diagnostic_id]]


def payload(bundle) -> str:
    req = build_request(bundle, VERSION_Q)
    return req.facts_json + " " + " ".join(req.allowed_evidence_ids)


# ── Reproduction du défaut ───────────────────────────────────────────────────


def test_reproduction_vps_values_no_longer_cross_through_diagnostics():
    """Sur 11d4493, le SHA canari et « failed/failed » sortaient via DIAGNOSTIC/DISCREPANCY."""
    facts = run_facts(StubGithub(), StubHost(deployed=CANARY_SHA, active=("failed", "failed"), restarts=7))
    # Préconditions : l'analyse contient bien des textes ANALYSIS qui citent le VPS.
    texts = " ".join(g.observation for g in facts.analysis.diagnostics) + " ".join(
        d.explanation for d in facts.analysis.discrepancies
    )
    assert CANARY_SHA[:12] in texts and "failed/failed" in texts
    sent = payload(build_fact_bundle(facts))
    assert CANARY_SHA[:12] not in sent and CANARY_SHA not in sent
    assert "failed" not in sent
    assert not host_evidence_ids(facts) & set(sent.split())


# ── Scénarios : aucune valeur VPS, aucune preuve VPS, aucun diagnostic VPS ───

SCENARIOS = {
    "nominal": "runtime épinglé",
    "drift": "dérive",
    "no_deployment_id": "identité de build absente",
    "stale": "snapshot périmé",
    "partial": "un seul snapshot frais",
    "host_unavailable": "VPS indisponible",
}


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_no_host_derived_content_leaves_by_default(scenario):
    facts = scenario_facts(scenario)
    bundle = build_fact_bundle(facts)
    sent = payload(bundle)
    leaked = {t for t in host_tokens(facts) if t in sent}
    assert not leaked, (scenario, leaked)
    assert not host_evidence_ids(facts) & set(build_request(bundle, VERSION_Q).allowed_evidence_ids)
    held = host_dependent_diagnostics(facts)
    assert held, scenario  # chaque scénario a au moins un diagnostic dérivé du VPS
    for g in held:
        assert f"{g.code.value} : {g.observation}" not in sent, (scenario, g.diagnostic_id)
    assert not any(f.kind == "DISCREPANCY" for f in bundle.facts)  # l'écart compare GitHub au VPS
    assert any(w.startswith("VPS :") and "diagnostic" in w for w in bundle.withheld)


@pytest.mark.parametrize(
    "host, code",
    [
        (StubHost(deployed=CANARY_SHA), "POSSIBLE_DRIFT"),
        (StubHost(deployed=None), "NO_DEPLOYED_BUILD_ID"),
        (StubHost(active=("failed", "failed")), "SERVICE_NOT_RUNNING"),
        (StubHost(), "ACTIVE_NOT_HEALTH"),
        (StubHost(age=3600.0, availability=Availability.STALE), "STALE"),
    ],
)
def test_each_host_diagnostic_family_is_withheld(host, code):
    facts = run_facts(StubGithub(), host)
    codes = {g.code.value for g in facts.analysis.diagnostics}
    assert code in codes, codes
    sent = payload(build_fact_bundle(facts))
    assert f"{code} :" not in sent


def test_compare_whose_base_is_the_host_sha_is_withheld():
    facts = run_facts(StubGithub(), StubHost(deployed=CANARY_SHA))
    assert facts.compare is not None and facts.compare.value["base"] == CANARY_SHA
    assert facts.analysis.provenance["observation:gh-compare"] == frozenset({"GITHUB", "HOST"})
    assert CANARY_SHA not in payload(build_fact_bundle(facts))


def test_github_only_material_is_still_sent():
    facts = run_facts(StubGithub(ci="FAILURE"), StubHost(deployed=CANARY_SHA), "Analyse le dépôt et le VPS, cite les preuves")
    bundle = build_fact_bundle(facts)
    kinds = {f.kind for f in bundle.facts}
    assert {"OBSERVATION", "REFERENCE"} <= kinds
    assert any(f.kind == "DIAGNOSTIC" and f.text.startswith("CI_FAILURE") for f in bundle.facts)
    assert "ev-gh-head" in build_request(bundle, VERSION_Q).allowed_evidence_ids


def test_compare_without_host_read_is_github_only():
    compare = Observation("gh-compare", Domain.REPOSITORY, "commits", Availability.AVAILABLE,
                          {"base": "1" * 40, "head": HEAD, "ahead_by": 3}, None,
                          (EvidenceRef("ev-gh-compare", SourceKind.GITHUB, "fixture:stub/c", Provenance.SYNTHETIC,
                                       "2026-10-16T12:00:00Z"),))
    analysis = analyse(StubGithub().repository_snapshot(), None, (), (compare,))
    assert "observation:gh-compare" not in analysis.provenance
    assert analysis.provenance["discrepancy:0"] == frozenset({"GITHUB", "DECLARED_REFERENCE"})


# ── Fail-closed ──────────────────────────────────────────────────────────────


def test_unknown_provenance_is_treated_as_host():
    facts = run_facts(StubGithub(ci="FAILURE"), StubHost(), "Analyse le dépôt et le VPS, cite les preuves")
    ci_diag = next(g for g in facts.analysis.diagnostics if g.code.value == "CI_FAILURE")
    assert ci_diag.code.value + " :" in payload(build_fact_bundle(facts))
    stripped = dict(facts.analysis.provenance)
    del stripped["diagnostic:" + ci_diag.diagnostic_id]
    facts2 = dataclasses.replace(facts, analysis=dataclasses.replace(facts.analysis, provenance=stripped))
    assert "CI_FAILURE :" not in payload(build_fact_bundle(facts2))


def test_host_evidence_overrides_a_github_only_declaration():
    facts = run_facts(StubGithub(), StubHost())
    svc = next(g for g in facts.analysis.diagnostics if g.diagnostic_id == "diag-service")
    forged = dict(facts.analysis.provenance)
    forged["diagnostic:diag-service"] = frozenset({"GITHUB"})  # déclaration erronée
    facts2 = dataclasses.replace(facts, analysis=dataclasses.replace(facts.analysis, provenance=forged))
    assert any(e.source is SourceKind.HOST for e in svc.evidence)
    assert f"{svc.code.value} :" not in payload(build_fact_bundle(facts2))


def test_evidence_less_observation_of_unknown_origin_is_withheld():
    facts = run_facts(StubGithub(), StubHost())
    orphan = Observation.absent("gh-orphan", Domain.REPOSITORY, "orphelin", Availability.NOT_AVAILABLE, "NO_EVIDENCE")
    facts2 = dataclasses.replace(facts, details=(orphan,))
    assert "orphelin" not in payload(build_fact_bundle(facts2))


# ── Inverse : faits VPS admis explicitement, transport simulé seulement ──────


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_explicit_opt_in_includes_host_material(scenario):
    facts = scenario_facts(scenario)
    bundle = build_fact_bundle(facts, allow_host_facts=True)
    assert sum(f.kind == "DIAGNOSTIC" for f in bundle.facts) == len(facts.analysis.diagnostics)
    assert sum(f.kind == "DISCREPANCY" for f in bundle.facts) == len(facts.analysis.discrepancies)
    assert not any(w.startswith("VPS :") for w in bundle.withheld)
    allowed = set(build_request(bundle, VERSION_Q).allowed_evidence_ids)
    assert host_evidence_ids(facts) <= allowed


def test_opt_in_reasoner_may_cite_host_evidence_offline_only():
    gh, host = demo_providers("nominal", clock)
    seen = {}

    def script(req):
        host_id = next(i for i in req.allowed_evidence_ids if "runtime_service" in i)
        seen["host_id"] = host_id
        return json.dumps({"summary": "Interprétation", "uncertainties": [],
                           "interpretations": [{"text": "Le runtime publié semble suivre la référence.",
                                                "evidence_ids": [host_id]}]})

    transport = OfflineMockTransport(script)
    reasoner = OfflineLlmReasoner(transport, enabled=True, allow_host_facts=True)
    run = Sentinel(gh, host, clock, reasoner=reasoner).ask(VERSION_Q)
    assert reasoner.last_audit["outcome"] == "ACCEPTED" and seen["host_id"]
    assert any(seen["host_id"] in s.evidence_ids for s in run.answer.statements)

    class Lookalike:
        name = "offline-mock"

        def __call__(self, request):
            return "{}"

    with pytest.raises(ReasonerDisabled):
        OfflineLlmReasoner(Lookalike(), enabled=True, allow_host_facts=True)


def test_default_reasoner_withholds_and_reports_counts():
    gh, host = demo_providers("drift", clock)
    transport = OfflineMockTransport(["{}"])
    reasoner = OfflineLlmReasoner(transport, enabled=True)
    Sentinel(gh, host, clock, reasoner=reasoner).ask(VERSION_Q)
    (req,) = transport.requests
    assert not {"diag-runtime", "POSSIBLE_DRIFT"} & set(req.facts_json.split('"'))
    assert any("diagnostic" in w for w in reasoner.last_audit["withheld"])


# ── Contrats et résultats inchangés ──────────────────────────────────────────


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_provenance_does_not_change_the_deterministic_answer(scenario):
    gh, host = demo_providers(scenario, clock)
    run = Sentinel(gh, host, clock).ask(VERSION_Q)
    doc = to_jsonable(run)
    assert set(doc["answer"]) == {  # la provenance reste une métadonnée interne, hors contrat AgentRun
        "summary", "statements", "uncertainties", "discrepancies", "findings", "proposals", "refusals",
        "untrusted_quotes", "diagnostics", "excerpts",
    }
    assert "discrepancy:0" not in json.dumps(doc)
    facts = scenario_facts(scenario)
    keys = {"diagnostic:" + g.diagnostic_id for g in facts.analysis.diagnostics}
    assert keys <= set(facts.analysis.provenance)  # chaque diagnostic a une provenance déclarée
    assert "discrepancy:0" in facts.analysis.provenance
