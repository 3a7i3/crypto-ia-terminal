"""Synthetic lab specs; none of them is registered in A1 or deployed anywhere."""

import copy
from pathlib import Path

from colony_lab import a1_identity as a1
from colony_lab import lineage

BUDGET = {"cpu_seconds": 20, "wall_seconds": 60, "memory_bytes": 1 << 30, "output_bytes": 1 << 20,
          "runs": 20, "journal_events": 200}
SENTINEL_CAPS = ["CI_READ", "DIAGNOSTIC_PRODUCE", "GITHUB_METADATA_READ", "GOVERNED_ARTIFACT_READ",
                 "REPOSITORY_READ", "REPOSITORY_SEARCH"]


def spec(name="sentinel_01", cls="FORENSIC", level="F2", caps=None, display="Sentinel 01", **scope):
    caps = list(SENTINEL_CAPS if caps is None else caps)
    body = {
        "agent_schema": "AGENT_SPEC_V1", "constitution_version": "AGENT_ECON_A0_FOREST_V1", "spec_revision": 1,
        "namespace": "forest", "canonical_name": name, "display_name": display, "agent_class": cls,
        "maintenance_level": level,
        "purpose": "Synthetic lab individual: observes fixtures only, never registered or deployed.",
        "capabilities": caps,
        "scope_policy": {
            "repository_read_paths": scope.get("paths", ["docs/"] if {"REPOSITORY_READ", "REPOSITORY_SEARCH",
                                                                      "STATIC_ANALYSIS"} & set(caps) else []),
            "repository_write_paths_future": [],
            "github_surfaces": scope.get("surfaces", ["CHECK_RUNS"] if {"CI_READ", "GITHUB_METADATA_READ"}
                                         & set(caps) else []),
            "artifact_domains": scope.get("domains", ["GOVERNANCE_DOCUMENTS"] if "GOVERNED_ARTIFACT_READ"
                                          in caps else []),
        },
        "independence_policy": copy.deepcopy(a1.INDEPENDENCE_POLICY),
        "authority_policy": copy.deepcopy(a1.AUTHORITY_POLICY),
        "execution_binding": copy.deepcopy(a1.EXECUTION_BINDING), "supersedes_spec_id": None,
        "created_from_ref": "bfb1109fcc7a0a646db57ca96283a56443497acd", "created_at_utc": "2026-10-20T00:00:00Z",
    }
    return seal(body)


def seal(body):
    body["agent_id"] = a1.agent_id(body["namespace"], body["canonical_name"], body["agent_class"])
    body["agent_spec_id"] = a1.agent_spec_id(body)
    return body


def founder(permissions=("DIAGNOSTIC_PRODUCE", "GOVERNED_ARTIFACT_READ"), budget=None, **kwargs):
    body = spec(**kwargs)
    return body, lineage.make_founder(body, lab_permissions=list(permissions), budget=dict(budget or BUDGET))


def archivist_spec():
    return spec(name="archivist_01", cls="DATA_STEWARD", display="Archivist 01",
                caps=["GOVERNED_ARTIFACT_READ"])


def qualification(record, state="QUALIFIED_SIMULATED", reviewer="fixture-independent-reviewer",
                  kind="EXTERNAL_REVIEW_PROCESS"):
    return {"qualification_schema": lineage.QUALIFICATION_SCHEMA, "agent_id": record["agent_id"],
            "agent_spec_id": record["agent_spec_id"], "state": state, "scope": "SIMULATED_DETERMINISTIC",
            "criteria_sha256": "1" * 64, "evidence_sha256": "2" * 64, "reviewer_kind": kind,
            "reviewer_id": reviewer}


def lab_root(tmp_path: Path) -> Path:
    root = tmp_path / "colony-lab-test"
    root.mkdir(mode=0o700)
    return root
