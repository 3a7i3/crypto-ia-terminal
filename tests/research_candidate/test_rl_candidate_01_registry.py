from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from research_candidate import (
    CANDIDATE_SCHEMA,
    PROMOTION_REQUEST_SCHEMA,
    CandidateValidationError,
    RegistryError,
    canonical_json_bytes,
    compute_candidate_config_hash,
    compute_candidate_id,
    compute_evaluation_run_id,
    compute_event_id,
    compute_promotion_request_id,
    dataset_requirement_id,
    project_candidate_states,
    publish_candidate,
    validate_candidate,
    validate_promotion_request,
)

DATASET_ID = "1" * 64
BOUNDARY_ID = "2" * 64
RESEARCH_RUN_ID = "3" * 64
DIAG_RUN_ID = "4" * 64
BASE_CONFIG_HASH = "5" * 64
BASE_SOURCE_SHA = "a" * 40
EVAL_CODE_SHA = "b" * 40
EVAL_CONFIG_HASH = "7" * 64
EPOCH = "TEST-EPOCH"

BASE_MATERIAL_CONFIG = {
    "MEXC_SIM_MAX_POSITION_USD": {
        "value": "10",
        "value_type": "float",
    },
    "PB_MAX_POSITIONS": {
        "value": "2",
        "value_type": "int",
    },
}

CONFIG_COMPONENT = {
    "kind": "CONFIG_SET",
    "path": "MEXC_SIM_MAX_POSITION_USD",
    "old_value": "10",
    "new_value": "20",
    "value_type": "float",
    "materiality": "SIZING",
}

CANDIDATE_CONFIG_HASH = compute_candidate_config_hash(
    BASE_MATERIAL_CONFIG,
    {"components": [CONFIG_COMPONENT]},
)


def _requirement(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["requirement_id"] = dataset_requirement_id(result)
    return result


def _exact_requirement(
    *,
    role: str = "DISCOVERY",
    dataset_id: str = DATASET_ID,
) -> dict[str, Any]:
    return _requirement(
        {
            "kind": "EXACT_DATASET",
            "dataset_id": dataset_id,
            "source_boundary_id": BOUNDARY_ID,
            "source_domain": "PAPER",
            "source_authority": "PPL_AUTHORITY",
            "evidence_role": role,
        }
    )


def _future_requirement() -> dict[str, Any]:
    return _requirement(
        {
            "kind": "FUTURE_DATASET_REQUIREMENT",
            "source_domain": "PAPER",
            "source_authority": "PPL_AUTHORITY",
            "evidence_role": "VALIDATION",
            "required_relation": "NEW_PAPER_EPOCH",
            "required_source_config_binding": {
                "candidate_config_hash": CANDIDATE_CONFIG_HASH,
            },
            "minimum_conditions": {
                "minimum_closed_trades": 100,
                "unresolved_policy": "EXPLICIT",
            },
        }
    )


def _candidate(
    *,
    created_at: str = "2026-09-25T22:00:00Z",
    candidate_config_hash: str = CANDIDATE_CONFIG_HASH,
) -> dict[str, Any]:
    requirements = [_exact_requirement(), _future_requirement()]
    requirements.sort(key=canonical_json_bytes)

    candidate: dict[str, Any] = {
        "candidate_schema": CANDIDATE_SCHEMA,
        "candidate_id": "0" * 64,
        "candidate_class": "CONFIG",
        "target_domains": ["SIZING"],
        "parents": {
            "dataset_ids": [DATASET_ID],
            "source_boundary_ids": [BOUNDARY_ID],
            "research_run_ids": [RESEARCH_RUN_ID],
            "diagnostic_run_ids": [DIAG_RUN_ID],
            "paper_epoch_ids": [EPOCH],
        },
        "lineage": {
            "supersedes_candidate_ids": [],
            "derived_from_candidate_ids": [],
        },
        "baseline": {
            "source_code_sha": BASE_SOURCE_SHA,
            "config_identity_kind": "EXPERIMENT_CONFIG_SNAPSHOT",
            "config_hash": BASE_CONFIG_HASH,
            "paper_epoch_id": EPOCH,
            "strategy_id": "NOT_AVAILABLE",
            "baseline_semantics_version": "BASELINE_V1",
            "baseline_population_definition": "F00_FACTUAL_N13",
        },
        "candidate_config_hash": candidate_config_hash,
        "proposal": {
            "components": [copy.deepcopy(CONFIG_COMPONENT)]
        },
        "hypothesis": {
            "question": "Does a unified sizing experiment change outcomes?",
            "rationale": "A5 proved dual sizing semantics.",
            "mechanism": "Executed principal would follow the governed candidate config.",
            "primary_metric": "net_realized_pnl_usd",
            "expected_direction": "NON_DEGRADATION",
            "guardrail_metrics": ["max_drawdown", "unresolved_count"],
            "minimum_evidence_requirements": ["independent_new_epoch", "minimum_n"],
            "falsification_conditions": ["guardrail_failure", "primary_metric_failure"],
        },
        "evaluation_plan": {
            "evaluation_methods": ["FACTUAL_BINDING_CHECK", "NEW_PAPER_EPOCH"],
            "dataset_requirements": requirements,
            "population_definition": "POSITION_CLOSED_FOR_PERFORMANCE",
            "primary_metric_semantics": "NET_REALIZED_PNL_V1",
            "guardrail_metric_semantics": {
                "max_drawdown": "REALIZED_CLOSE_TO_CLOSE",
                "unresolved_count": "PPL_UNRESOLVED_COUNT",
            },
            "minimum_sample_evidence_requirement": "N>=100 on independent epoch",
            "comparison_baseline": "CERTIFIED_F00",
            "missing_evidence_behavior": "FAIL_CLOSED",
            "determinism_requirements": "IDENTICAL_INPUTS_IDENTICAL_IDS",
            "data_reuse_policy": {
                "discovery_dataset_ids": [DATASET_ID],
                "allow_discovery_as_validation": False,
                "justification": None,
            },
        },
        "known_limitations": [
            "F00_N13_LOW_SAMPLE",
            "NO_MARKET_PATH_COUNTERFACTUAL",
        ],
        "promotion_policy": {
            "version": "RL_CANDIDATE_PROMOTION_V1",
            "target_environment": "PAPER_NEW_EPOCH",
            "new_epoch_only": True,
            "requires_operator_authorization": True,
        },
        "created_at_utc": created_at,
    }
    candidate["candidate_id"] = compute_candidate_id(candidate)
    return candidate


def _catalog() -> dict[str, set[str]]:
    return {
        "dataset_ids": {DATASET_ID},
        "source_boundary_ids": {BOUNDARY_ID},
        "research_run_ids": {RESEARCH_RUN_ID},
        "diagnostic_run_ids": {DIAG_RUN_ID},
        "paper_epoch_ids": {EPOCH},
    }


def _event(
    candidate_id: str,
    *,
    sequence: int,
    ordinal: int,
    previous: str,
    new: str,
    evidence: list[str],
    reason: str,
) -> dict[str, Any]:
    event = {
        "event_id": "0" * 64,
        "registry_sequence": sequence,
        "candidate_transition_ordinal": ordinal,
        "candidate_id": candidate_id,
        "event_type": "STATE_TRANSITION",
        "previous_state": previous,
        "new_state": new,
        "evidence_refs": sorted(evidence),
        "reason_code": reason,
        "reason_detail": None,
        "timestamp_utc": f"2026-09-25T22:0{ordinal}:00Z",
    }
    event["event_id"] = compute_event_id(event)
    return event


def test_candidate_identity_is_deterministic_and_timestamp_independent() -> None:
    a = _candidate(created_at="2026-09-25T22:00:00Z")
    b = _candidate(created_at="2026-09-26T01:00:00Z")

    assert a["candidate_id"] == b["candidate_id"]
    assert validate_candidate(
        a,
        evidence_catalog=_catalog(),
        baseline_material_config=BASE_MATERIAL_CONFIG,
    ) == a["candidate_id"]
    assert validate_candidate(
        b,
        evidence_catalog=_catalog(),
        baseline_material_config=BASE_MATERIAL_CONFIG,
    ) == b["candidate_id"]


def test_candidate_config_hash_participates_in_candidate_identity() -> None:
    a = _candidate(candidate_config_hash="6" * 64)
    b = _candidate(candidate_config_hash="8" * 64)

    assert a["candidate_id"] != b["candidate_id"]


def test_exact_and_future_dataset_requirements_have_deterministic_ids() -> None:
    exact = _exact_requirement()
    future = _future_requirement()

    assert exact["requirement_id"] == dataset_requirement_id(exact)
    assert future["requirement_id"] == dataset_requirement_id(future)
    assert exact["requirement_id"] != future["requirement_id"]


def test_discovery_dataset_cannot_silently_be_validation() -> None:
    candidate = _candidate()
    req = _exact_requirement(role="VALIDATION")
    candidate["evaluation_plan"]["dataset_requirements"] = [req]
    candidate["candidate_id"] = compute_candidate_id(candidate)

    with pytest.raises(
        CandidateValidationError,
        match="discovery evidence cannot silently be reused as validation",
    ):
        validate_candidate(
        candidate,
        evidence_catalog=_catalog(),
        baseline_material_config=BASE_MATERIAL_CONFIG,
    )


def test_parent_evidence_must_exist_in_catalog() -> None:
    candidate = _candidate()
    catalog = _catalog()
    catalog["diagnostic_run_ids"] = set()

    with pytest.raises(CandidateValidationError, match="unknown parent evidence"):
        validate_candidate(
            candidate,
            evidence_catalog=catalog,
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )


def test_proposal_components_require_canonical_order() -> None:
    candidate = _candidate()
    second = {
        "kind": "CONFIG_SET",
        "path": "PB_MAX_POSITIONS",
        "old_value": "2",
        "new_value": "3",
        "value_type": "int",
        "materiality": "SIZING",
    }
    components = candidate["proposal"]["components"] + [second]
    components.sort(key=canonical_json_bytes, reverse=True)
    candidate["proposal"]["components"] = components
    candidate["candidate_id"] = compute_candidate_id(candidate)

    with pytest.raises(CandidateValidationError, match="canonically"):
        validate_candidate(
            candidate,
            evidence_catalog=_catalog(),
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )


def test_publish_candidate_is_write_once_and_idempotent(tmp_path: Path) -> None:
    candidate = _candidate()

    first = publish_candidate(
        tmp_path,
        candidate,
        evidence_catalog=_catalog(),
        baseline_material_config=BASE_MATERIAL_CONFIG,
    )
    second = publish_candidate(
        tmp_path,
        candidate,
        evidence_catalog=_catalog(),
        baseline_material_config=BASE_MATERIAL_CONFIG,
    )

    assert first.disposition == "CREATED"
    assert second.disposition == "ALREADY_EXISTS_IDENTICAL"
    assert first.path.read_bytes() == second.path.read_bytes()


def test_same_identity_with_different_artifact_bytes_fails_closed(tmp_path: Path) -> None:
    a = _candidate(created_at="2026-09-25T22:00:00Z")
    b = _candidate(created_at="2026-09-26T01:00:00Z")

    assert a["candidate_id"] == b["candidate_id"]

    publish_candidate(
        tmp_path,
        a,
        evidence_catalog=_catalog(),
        baseline_material_config=BASE_MATERIAL_CONFIG,
    )

    with pytest.raises(RegistryError, match="CANDIDATE_ID_COLLISION_OR_CORRUPTION"):
        publish_candidate(
            tmp_path,
            b,
            evidence_catalog=_catalog(),
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )


def test_evaluation_identity_is_deterministic() -> None:
    candidate = _candidate()
    req = _exact_requirement()

    kwargs = dict(
        candidate=candidate,
        dataset_id=DATASET_ID,
        source_boundary_id=BOUNDARY_ID,
        satisfied_dataset_requirement_id=req["requirement_id"],
        dataset_evidence_role="DISCOVERY",
        dataset_source_domain="PAPER",
        dataset_source_authority="PPL_AUTHORITY",
        evaluation_engine_code_sha=EVAL_CODE_SHA,
        evaluation_method_version="FACTUAL_BINDING_CHECK_V1",
        evaluation_config_hash=EVAL_CONFIG_HASH,
        population_definition="POSITION_CLOSED_FOR_PERFORMANCE",
        metric_semantics_version="METRICS_V1",
    )

    assert compute_evaluation_run_id(**kwargs) == compute_evaluation_run_id(**kwargs)


def test_registry_projects_only_legal_contiguous_transitions() -> None:
    candidate = _candidate()
    cid = candidate["candidate_id"]

    events = [
        _event(
            cid,
            sequence=1,
            ordinal=1,
            previous="CANDIDATE",
            new="REPLAYED",
            evidence=["8" * 64],
            reason="EVALUATION_COMPLETED",
        ),
        _event(
            cid,
            sequence=2,
            ordinal=2,
            previous="REPLAYED",
            new="SHADOW_READY",
            evidence=["9" * 64],
            reason="SHADOW_READINESS_CERTIFIED",
        ),
        _event(
            cid,
            sequence=3,
            ordinal=3,
            previous="SHADOW_READY",
            new="QUALIFIED",
            evidence=["a" * 64],
            reason="QUALIFICATION_PASSED",
        ),
    ]

    evaluation_catalog = {
        "8" * 64: {
            "evaluation_run_id": "8" * 64,
            "candidate_id": cid,
            "dataset_evidence_role": "DISCOVERY",
            "qualification_eligible": False,
            "unresolved_blockers": [],
        },
        "a" * 64: {
            "evaluation_run_id": "a" * 64,
            "candidate_id": cid,
            "dataset_evidence_role": "VALIDATION",
            "qualification_eligible": True,
            "unresolved_blockers": [],
        },
    }

    state = project_candidate_states(
        {cid: candidate},
        events,
        baseline_material_configs={cid: BASE_MATERIAL_CONFIG},
        evaluation_catalog=evaluation_catalog,
    )
    assert state[cid] == "QUALIFIED"


def test_registry_rejects_state_skip_and_ordinal_gap() -> None:
    candidate = _candidate()
    cid = candidate["candidate_id"]

    skip = _event(
        cid,
        sequence=1,
        ordinal=1,
        previous="CANDIDATE",
        new="QUALIFIED",
        evidence=["8" * 64],
        reason="INVALID_SKIP",
    )
    with pytest.raises(RegistryError, match="illegal transition"):
        project_candidate_states(
            {cid: candidate},
            [skip],
            baseline_material_configs={cid: BASE_MATERIAL_CONFIG},
        )

    replayed = _event(
        cid,
        sequence=1,
        ordinal=2,
        previous="CANDIDATE",
        new="REPLAYED",
        evidence=["8" * 64],
        reason="EVALUATION_COMPLETED",
    )
    with pytest.raises(RegistryError, match="candidate_transition_ordinal"):
        project_candidate_states(
            {cid: candidate},
            [replayed],
            baseline_material_configs={cid: BASE_MATERIAL_CONFIG},
        )


def test_research_only_candidate_cannot_enter_shadow_ready() -> None:
    candidate = _candidate()
    candidate["candidate_class"] = "FEATURE"
    candidate["target_domains"] = ["RESEARCH_ONLY"]
    feature = {
        "kind": "FEATURE_SPEC",
        "feature_name": "research_only_fixture",
        "feature_semantic_version": "v1",
        "derivation_spec_sha256": "b" * 64,
        "input_schema": {"type": "object"},
        "output_schema": {"type": "number"},
        "missing_value_policy": "UNKNOWN",
        "intended_consumer": "RESEARCH",
        "affects_population_or_capital": False,
    }
    candidate["proposal"]["components"] = [feature]
    candidate["candidate_config_hash"] = "NOT_AVAILABLE"
    candidate["evaluation_plan"]["evaluation_methods"] = [
        "DESCRIPTIVE_COMPARISON"
    ]
    candidate["evaluation_plan"]["dataset_requirements"] = [
        _exact_requirement(role="EVALUATION")
    ]
    candidate["candidate_id"] = compute_candidate_id(candidate)
    validate_candidate(
        candidate,
        evidence_catalog=_catalog(),
        baseline_material_config=BASE_MATERIAL_CONFIG,
    )

    cid = candidate["candidate_id"]
    events = [
        _event(
            cid,
            sequence=1,
            ordinal=1,
            previous="CANDIDATE",
            new="REPLAYED",
            evidence=["8" * 64],
            reason="EVALUATION_COMPLETED",
        ),
        _event(
            cid,
            sequence=2,
            ordinal=2,
            previous="REPLAYED",
            new="SHADOW_READY",
            evidence=["9" * 64],
            reason="INVALID_PROMOTABLE_STATE",
        ),
    ]

    evaluation_catalog = {
        "8" * 64: {
            "evaluation_run_id": "8" * 64,
            "candidate_id": cid,
            "dataset_evidence_role": "DISCOVERY",
            "qualification_eligible": False,
            "unresolved_blockers": [],
        }
    }

    with pytest.raises(RegistryError, match="RESEARCH_ONLY"):
        project_candidate_states(
            {cid: candidate},
            events,
            evaluation_catalog=evaluation_catalog,
        )


def _promotion_request(candidate: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "promotion_request_schema": PROMOTION_REQUEST_SCHEMA,
        "promotion_request_id": "0" * 64,
        "candidate_id": candidate["candidate_id"],
        "candidate_state": "QUALIFIED",
        "qualification_evidence_refs": ["c" * 64],
        "target_environment": "PAPER_NEW_EPOCH",
        "target_source_sha": BASE_SOURCE_SHA,
        "target_config_hash": candidate["candidate_config_hash"],
        "requested_new_epoch": {
            "kind": "EXACT_NEW_EPOCH",
            "paper_epoch_id": "TEST-EPOCH-02",
        },
        "baseline_epoch": EPOCH,
        "rollback_boundary_identity": {
            "previous_epoch": EPOCH,
            "rollback_mode": "BEFORE_FIRST_EVENT",
        },
        "rollback_plan": {
            "mode": "NEW_EPOCH_ONLY",
            "preserve_parent_epoch": True,
        },
        "required_operator_authorization": True,
        "required_preflight_checks": ["CLEAN_PPL", "SOURCE_SHA_MATCH"],
        "preflight_contract_version": "PROMOTION_PREFLIGHT_V1",
        "status": "READY_FOR_AUTHORIZATION",
    }
    request["promotion_request_id"] = compute_promotion_request_id(request)
    return request


def test_promotion_request_requires_qualified_new_epoch_and_is_deterministic() -> None:
    candidate = _candidate()
    request = _promotion_request(candidate)

    first = validate_promotion_request(
        request,
        candidate=candidate,
        candidate_state="QUALIFIED",
        baseline_material_config=BASE_MATERIAL_CONFIG,
    )
    second = validate_promotion_request(
        request,
        candidate=candidate,
        candidate_state="QUALIFIED",
        baseline_material_config=BASE_MATERIAL_CONFIG,
    )

    assert first == second == request["promotion_request_id"]

    with pytest.raises(RegistryError, match="requires QUALIFIED"):
        validate_promotion_request(
            request,
            candidate=candidate,
            candidate_state="SHADOW_READY",
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )

    same_epoch = copy.deepcopy(request)
    same_epoch["requested_new_epoch"]["paper_epoch_id"] = EPOCH
    same_epoch["promotion_request_id"] = compute_promotion_request_id(same_epoch)
    with pytest.raises(RegistryError, match="new PAPER epoch"):
        validate_promotion_request(
            same_epoch,
            candidate=candidate,
            candidate_state="QUALIFIED",
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )


def test_rl_candidate_boundary_cannot_authorize_or_execute_promotion() -> None:
    candidate = _candidate()
    request = _promotion_request(candidate)

    for status in ("AUTHORIZED", "EXECUTED"):
        changed = copy.deepcopy(request)
        changed["status"] = status
        # Status is deliberately excluded from scientific request identity.
        assert compute_promotion_request_id(changed) == request["promotion_request_id"]
        with pytest.raises(RegistryError, match="cannot record AUTHORIZED or EXECUTED"):
            validate_promotion_request(
                changed,
                candidate=candidate,
                candidate_state="QUALIFIED",
                baseline_material_config=BASE_MATERIAL_CONFIG,
            )



def test_config_candidate_requires_exact_candidate_config_hash() -> None:
    candidate = _candidate()
    candidate["candidate_config_hash"] = "NOT_AVAILABLE"
    candidate["candidate_id"] = compute_candidate_id(candidate)

    with pytest.raises(CandidateValidationError, match="candidate_config_hash"):
        validate_candidate(
            candidate,
            evidence_catalog=_catalog(),
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )


def test_dataset_requirement_id_tampering_fails_closed() -> None:
    candidate = _candidate()
    candidate["evaluation_plan"]["dataset_requirements"][0]["requirement_id"] = "f" * 64
    candidate["candidate_id"] = compute_candidate_id(candidate)

    with pytest.raises(CandidateValidationError, match="requirement_id mismatch"):
        validate_candidate(
            candidate,
            evidence_catalog=_catalog(),
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )


def test_forward_registry_transition_requires_evidence() -> None:
    candidate = _candidate()
    cid = candidate["candidate_id"]

    event = _event(
        cid,
        sequence=1,
        ordinal=1,
        previous="CANDIDATE",
        new="REPLAYED",
        evidence=[],
        reason="EVALUATION_COMPLETED",
    )

    with pytest.raises(RegistryError, match="requires exact evidence_refs"):
        project_candidate_states(
            {cid: candidate},
            [event],
            baseline_material_configs={cid: BASE_MATERIAL_CONFIG},
        )


def test_promotion_rejects_source_or_config_identity_drift() -> None:
    candidate = _candidate()
    request = _promotion_request(candidate)

    source_drift = copy.deepcopy(request)
    source_drift["target_source_sha"] = "c" * 40
    source_drift["promotion_request_id"] = compute_promotion_request_id(source_drift)

    with pytest.raises(RegistryError, match="target_source_sha"):
        validate_promotion_request(
            source_drift,
            candidate=candidate,
            candidate_state="QUALIFIED",
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )

    config_drift = copy.deepcopy(request)
    config_drift["target_config_hash"] = "d" * 64
    config_drift["promotion_request_id"] = compute_promotion_request_id(config_drift)

    with pytest.raises(RegistryError, match="target_config_hash"):
        validate_promotion_request(
            config_drift,
            candidate=candidate,
            candidate_state="QUALIFIED",
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )


def test_promotion_rejects_proposal_without_implemented_source() -> None:
    candidate = _candidate()
    candidate["candidate_class"] = "STRATEGY"
    candidate["target_domains"] = ["SIZING"]
    candidate["proposal"]["components"] = [
        {
            "kind": "CODE_PATCH",
            "baseline_source_sha": BASE_SOURCE_SHA,
            "proposed_source_sha": "NOT_IMPLEMENTED",
            "changed_paths": ["core/sizing_policy.py"],
            "patch_sha256": "NOT_IMPLEMENTED",
            "semantic_domain": "SIZING",
        }
    ]
    candidate["candidate_config_hash"] = CANDIDATE_CONFIG_HASH
    candidate["candidate_id"] = compute_candidate_id(candidate)
    validate_candidate(
            candidate,
            evidence_catalog=_catalog(),
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )

    request = _promotion_request(candidate)

    with pytest.raises(RegistryError, match="no exact implemented source"):
        validate_promotion_request(
            request,
            candidate=candidate,
            candidate_state="QUALIFIED",
            baseline_material_config=BASE_MATERIAL_CONFIG,
        )
