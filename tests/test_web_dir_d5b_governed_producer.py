"""Vérifications source D5B-R1 : aucun accès API, disque runtime ou réseau."""
from dataclasses import replace
import pytest

from observability.operator_decisions.producer import (
    AvailabilityProof, Candidate, ContractError, GovernedProducer,
)

NOW = "2026-09-28T03:00:00Z"


def candidate() -> Candidate:
    return Candidate(
        candidate_id="cand-1", candidate_revision=1,
        source_type="PROBLEM", source_id="problem-1",
        source_ref="governed:problem-1:v1", source_sha="a" * 64,
        source_generated_at_utc=NOW, producer="problem-registry",
        producer_authority="GOVERNED_SOURCE", owner_registry="problem-registry",
        owner_record_version="v1", decision_type="PROPOSED_EVOLUTION",
        title="Corriger une lacune", summary="Dossier relu",
        proposed_change="Planifier une correction future",
        decision_purpose="planifier", requested_status="TO_PLAN",
        requested_priority="MEDIUM", evidence_status="VERIFIED",
        evidence_refs=("artifact:sha256:abc",), upstream_approval_ref="review:1",
        risk="Risque circonscrit", validation="Revue indépendante",
        rollback="Annuler dans une phase future",
    )


def producer() -> GovernedProducer:
    return GovernedProducer({"PROBLEM": "problem-registry"})


def proof(count: int) -> AvailabilityProof:
    return AvailabilityProof(True, "deploy-audit:sha256:abc", count, NOW)


def admit(p: GovernedProducer, c: Candidate) -> str:
    return p.admit(
        c, occurred_at_utc=NOW, approved_status="TO_PLAN",
        approved_priority="HIGH", admission_approval_ref="gate:review-1",
    )


def test_absence_de_producteur_ne_devient_jamais_zero():
    p = producer()
    assert p.project()["availability"] == "NON DÉPLOYÉ"
    assert p.project()["decision_count"] is None
    assert p.project(proof(0))["decision_count"] == 0


def test_admission_est_idempotente_et_projection_reproductible():
    p = producer()
    first = admit(p, candidate())
    second = admit(p, candidate())
    assert first == second
    assert len(p.events()) == 1
    view = p.project(proof(1))
    assert view["decision_count"] == 1
    assert view["counts_by_status"]["TO_PLAN"] == 1
    assert view["items"][0]["priority"] == "HIGH"
    assert view["items"][0]["decision_id"] == first
    assert view == p.project(proof(1))


def test_collision_meme_source_version_et_finalite_est_rejetee():
    p = producer()
    admit(p, candidate())
    with pytest.raises(ContractError, match="collision"):
        admit(p, replace(candidate(), title="Autre décision"))
    assert len(p.events()) == 1


@pytest.mark.parametrize("change", [
    {"owner_registry": "untrusted"},
    {"producer_authority": "AGENT"},
    {"source_sha": "missing"},
    {"evidence_refs": ()},
    {"evidence_status": "UNKNOWN"},
    {"requested_status": "ACCEPTED_FOR_FUTURE_GATE"},
    {"requested_priority": "URGENT"},
])
def test_source_non_gouvernee_ou_preuve_insuffisante_rejetee(change):
    p = producer()
    with pytest.raises(ContractError):
        admit(p, replace(candidate(), **change))
    assert p.events() == ()


def test_chaine_inalterable_depuis_copie_et_corruption_fail_closed():
    p = producer()
    admit(p, candidate())
    external = p.events()[0]
    external["candidate"]["title"] = "modifié"
    assert p.project(proof(1))["availability"] == "AVAILABLE"
    p._events[0]["candidate"]["title"] = "corrompu"
    view = p.project(proof(1))
    assert view["availability"] == "UNKNOWN"
    assert view["decision_count"] is None
    with pytest.raises(ContractError):
        admit(p, replace(candidate(), source_id="problem-2"))


def test_watermark_incomplet_ne_produit_pas_un_nombre():
    p = producer()
    admit(p, candidate())
    assert p.project(proof(0))["availability"] == "UNKNOWN"
    assert p.project(proof(0))["decision_count"] is None


def test_admission_sans_approbation_distincte_est_refusee():
    p = producer()
    with pytest.raises(ContractError):
        p.admit(candidate(), occurred_at_utc=NOW, approved_status="TO_PLAN",
                approved_priority="HIGH", admission_approval_ref="")
    assert p.events() == ()


def test_aucune_action_humaine_ni_effet_runtime_expose():
    p = producer()
    assert not hasattr(p, "human_action")
    assert not hasattr(p, "deploy")
    assert p.events() == ()
