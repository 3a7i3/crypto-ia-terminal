"""S4-a — SA1 (contract versioned and documented) and SA4 (incompatible versions refused).

SYNTHETIC, offline. The D-R1 archive is read, never rewritten.
"""
from __future__ import annotations

import json
import re

import pytest

from observability.radar_projection import contract as pc
from observability.radar_projection.projection import project
from observability.radar_projection.verifier import ProjectionRefusal, verify_export
from observability.radar_selection import contract as rc
from observability.radar_selection import selection
from tests.radar_projection._exports import ARCHIVE, ROOT, export, loads, reseal

CONTRACT = ROOT / "docs" / "contracts" / "CAT_S4A_CONTRAT_PROJECTION_RADAR.md"
PACKAGE = ROOT / "observability" / "radar_projection"


def refused(raw: bytes) -> str:
    with pytest.raises(ProjectionRefusal) as exc:
        verify_export(raw)
    return exc.value.code


# ---------------------------------------------------------------- SA1
def test_SA1_projection_schema_is_versioned():
    p = project(export("r0_syn_01_calm"))
    assert p["schema"] == pc.PROJECTION_SCHEMA == "radar-projection/1.0.0"


def test_SA1_supported_source_is_pinned_to_the_current_engine():
    # Literals in the projection contract; this test fails on any engine bump, forcing a
    # deliberate revision of radar-projection instead of a silent acceptance.
    assert pc.SUPPORTED_SOURCE == (rc.EVALUATION_SCHEMA, rc.RULES_VERSION, rc.RANKING_VERSION)
    assert pc.WEIGHTS == rc.WEIGHTS
    assert pc.MAX_CANDIDATES == rc.MAX_CANDIDATES
    assert pc.MAX_REASON_CODES == rc.MAX_REASON_CODES
    assert pc.DECISIONS == rc.DECISIONS and pc.CRITERIA == rc.CRITERIA
    assert pc.DECISION_SEVERITY == rc.DECISION_SEVERITY
    assert pc.CRITERION_STATES == rc.CRITERION_STATES
    assert pc.AUTHORITY == rc.AUTHORITY and pc.ADMISSION == rc.ADMISSION
    assert {k: v for k, v in rc.MODE.items() if k != "evidence"} == pc.MODE_DISABLED
    assert {k: (v["needs_bbo"], v["needs_l2_verified"]) for k, v in rc.MISSIONS.items()} == pc.MISSIONS
    assert pc.PRODUCTION_BUDGETS_STATUS == rc.PRODUCTION_BUDGETS_STATUS
    assert set(pc.BUDGET_LIMIT_KEYS) | {"future_cycle_interval_s", "profile"} == set(rc.TEST_BUDGETS.as_dict())
    assert pc.L2_STATUSES == rc.L2_STATUSES and pc.PRICE_KINDS == rc.PRICE_KINDS
    assert pc.ACTIVITY_KINDS == rc.ACTIVITY_KINDS and pc.COST_BASES == rc.COST_BASES
    assert pc.REGIMES == rc.REGIMES and pc.L2_VERIFIERS == rc.L2_VERIFIERS
    assert pc.TYPE_CODES == rc.TYPE_CODES and pc.FUTURE_TOLERANCE_MS == rc.FUTURE_TOLERANCE_MS
    assert pc.MAX_EXCLUDED_INSTANTS == rc.MAX_EXCLUDED_INSTANTS
    assert pc.L2_PROOF == selection.L2_PROOF
    assert pc.MAX_EXPORT_BYTES == rc.TEST_BUDGETS.max_output_bytes + 1
    assert set(pc.SCHEMA_EVIDENCE[pc.FIXTURE_SCHEMA]) == set(rc.EVIDENCE_KINDS)
    assert set(pc.SCHEMA_EVIDENCE[pc.BATCH_SCHEMA]) == set(rc.BATCH_EVIDENCE_KINDS)
    assert set(pc.EMPTY_REASONS) == {"NO_ADMISSIBLE_MARKET_FOR_MISSION", "ADMISSIBLE_MARKETS_ALL_EXCLUDED"}
    assert set(selection.EVIDENCE_LIMITS) == set(rc.BATCH_EVIDENCE_KINDS)


def test_SA1_contract_document_exists_and_names_every_refusal_code():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "radar-projection/1.0.0" in text
    for gate in [f"SA{i}" for i in range(1, 11)]:
        assert gate in text
    source = (PACKAGE / "verifier.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'_refuse\("([A-Z0-9_]+)"', source)) | set(pc.EVIDENCE_REFUSALS.values())
    codes |= {"INPUT_EMPTY", "DUPLICATE_KEY", "FLOAT_NOT_ALLOWED", "NONFINITE_NUMBER"}
    missing = sorted(code for code in codes if f"`{code}`" not in text)
    assert not missing, missing


def test_SA1_contract_documents_integrity_versus_authenticity():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "authenticité" in text and "intégrité" in text
    assert pc.INTEGRITY == {"seal": "VERIFIED", "proves": "CONTENT_INTEGRITY", "producer_authenticity": "NOT_PROVEN"}


# ---------------------------------------------------------------- SA4
ARCHIVED = sorted(p for p in ARCHIVE.rglob("*.json") if p.name != "MANIFEST.json")


def test_SA4_archive_has_the_27_d_r1_outputs():
    assert len(ARCHIVED) == 27


@pytest.mark.parametrize("path", ARCHIVED, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_SA4_every_archived_pre_rref_output_is_refused(path):
    raw = path.read_bytes()
    before = raw
    assert refused(raw) == "PRE_RREF_EVALUATION"
    assert path.read_bytes() == before  # read only


@pytest.mark.parametrize("schema", ["radar-evaluation/1.0.0", "radar-evaluation/1.1.0", "radar-evaluation/0.9.0",
                                    "radar-evaluation/1.1.9"])
def test_SA4_former_schemas_are_pre_rref(schema):
    d = loads(export("r0_syn_01_calm"))
    d["schema_version"] = schema
    assert refused(reseal(d)) == "PRE_RREF_EVALUATION"


@pytest.mark.parametrize("schema", ["radar-evaluation/1.2.1", "radar-evaluation/1.3.0", "radar-evaluation/2.0.0",
                                    "radar-evaluation/1.2.0-rc1", "radar-projection/1.0.0"])
def test_SA4_unknown_future_or_foreign_schemas_are_refused(schema):
    d = loads(export("r0_syn_01_calm"))
    d["schema_version"] = schema
    assert refused(reseal(d)) == "UNSUPPORTED_EVALUATION_SCHEMA"


@pytest.mark.parametrize("field,value", [("rules_version", "radar-rules/1.1.0"),
                                         ("ranking_version", "radar-ranking/1.2.0"),
                                         ("ranking_version", "radar-ranking/1.4.0"),
                                         ("rules_version", None)])
def test_SA4_mixed_version_combinations_are_refused(field, value):
    d = loads(export("r0_syn_01_calm"))
    d[field] = value
    assert refused(reseal(d)) == "UNSUPPORTED_VERSION_COMBINATION"


@pytest.mark.parametrize("value", [None, 12, ["radar-evaluation/1.2.0"]])
def test_SA4_missing_or_malformed_schema_version(value):
    d = loads(export("r0_syn_01_calm"))
    d["schema_version"] = value
    assert refused(reseal(d)) == "EVALUATION_SCHEMA_MISSING"


def test_SA4_versions_are_checked_before_the_seal():
    # A former output with a broken seal is still identified as pre-R-REF, never projected.
    d = json.loads(ARCHIVED[0].read_bytes())
    d["evaluation_sha256"] = "0" * 64
    assert refused(json.dumps(d).encode()) == "PRE_RREF_EVALUATION"
