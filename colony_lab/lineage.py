"""Individuals, lineage and genotype of the colony lab (schema colony-lab.individual/0).

An individual IS an A1 agent: its persistent identity is the A1 ``agent_id``
and a restart or a spec revision keeps it. A descendant has its own
canonical_name, hence its own agent_id. This module only adds what A1 lacks
for a nursery (parent, founder, lineage, genotype, lab permissions, budget,
memory) and keeps three things apart:

* the A1 registry state, never claimed here (registry NON_DEPLOYED);
* the lab qualification, a separate record produced outside the individual;
* lab permissions, declared explicitly for each individual, never inherited.

Being a founder, a coordinator or a "reine" grants no capability.
"""

from __future__ import annotations

import re
from typing import Any

from colony_lab.a1_identity import F2, SPEC_IDENTITY_FIELDS, IdentityError, _canonical, _sha, check_spec

INDIVIDUAL_SCHEMA = "colony-lab.individual/0"
LINEAGE_SCHEMA = "colony-lab.lineage/0"
QUALIFICATION_SCHEMA = "colony-lab.qualification/0"
REGISTRY = {"availability": "NON_DEPLOYED", "state": "NOT_AVAILABLE"}
MEMORY = {"kind": "OWN_J01_JOURNAL", "inherits_parent_memory": False}
QUALIFICATION_STATES = frozenset({"UNQUALIFIED", "IN_TRIAL", "QUALIFIED_SIMULATED", "FAILED", "REVOKED"})
REVIEWER_KINDS = frozenset({"EXTERNAL_HUMAN", "EXTERNAL_REVIEW_PROCESS"})
BUDGET_MAX = {"cpu_seconds": 60, "wall_seconds": 120, "memory_bytes": 1 << 30, "output_bytes": 1 << 20,
              "runs": 1000, "journal_events": 5000}
# Lab permissions are A1 capability tokens; the lab grants none above F2 and
# none that is reserved or forbidden (F2 already excludes both).
LAB_GRANTABLE = F2
RECORD_FIELDS = frozenset({"individual_schema", "agent_id", "agent_spec_id", "spec_artifact_hash", "role",
                           "lineage", "genotype", "lab_permissions", "budget", "memory", "credentials",
                           "registry", "operational_authority", "record_hash"})
_REVIEWER_ID = re.compile(r"[a-z][a-z0-9_.:-]{2,127}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
# Fields whose change is a consequence of being another individual, not a mutation.
_DERIVED = frozenset({"agent_id", "canonical_name", "display_name", "spec_revision", "supersedes_spec_id"})


class LineageError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def lineage_id(founder_agent_id: str) -> str:
    return _sha({"lineage_schema": LINEAGE_SCHEMA, "founder_agent_id": founder_agent_id})


def spec_diff(parent_spec: dict, child_spec: dict) -> list[str]:
    """Spec identity fields the child changes, apart from those that make it another individual."""
    return sorted(name for name in SPEC_IDENTITY_FIELDS
                  if name not in _DERIVED and parent_spec[name] != child_spec[name])


def _record_hash(record: dict) -> str:
    return _sha({key: value for key, value in record.items() if key != "record_hash"})


def _permissions(value: Any, spec: dict) -> list[str]:
    if value is None:
        raise LineageError("PERMISSIONS_NOT_DECLARED")
    if type(value) is not list or value != sorted(set(value)) or any(type(p) is not str for p in value):
        raise LineageError("PERMISSIONS_NOT_CANONICAL")
    for token in value:
        if token not in LAB_GRANTABLE:
            raise LineageError("PERMISSION_NOT_GRANTABLE")
        if token not in spec["capabilities"]:
            raise LineageError("PERMISSION_OUTSIDE_SPEC")
    return list(value)


def _budget(value: Any) -> dict:
    if type(value) is not dict or set(value) != set(BUDGET_MAX):
        raise LineageError("BUDGET_INVALID")
    for name, maximum in BUDGET_MAX.items():
        amount = value[name]
        if type(amount) is not int or not 1 <= amount <= maximum:
            raise LineageError("BUDGET_INVALID")
    return dict(value)


def _spec(spec: Any) -> dict:
    try:
        return check_spec(spec)
    except IdentityError as exc:
        raise LineageError(exc.code) from None


def _seal(record: dict) -> dict:
    _canonical(record)
    record["record_hash"] = _record_hash(record)
    return record


def make_founder(spec: dict, *, lab_permissions: Any, budget: Any) -> dict:
    ids = _spec(spec)
    return _seal({
        "individual_schema": INDIVIDUAL_SCHEMA, **ids, "role": "FOUNDER",
        "lineage": {"lineage_id": lineage_id(ids["agent_id"]), "founder_agent_id": ids["agent_id"],
                    "parent_agent_id": None, "parent_agent_spec_id": None, "generation": 0},
        "genotype": {"base_agent_spec_id": None, "declared_diff": []},
        "lab_permissions": _permissions(lab_permissions, spec), "budget": _budget(budget),
        "memory": dict(MEMORY), "credentials": "NONE", "registry": dict(REGISTRY),
        "operational_authority": "DENIED",
    })


def check_qualification(qualification: Any, record: dict, *, also_excluded: frozenset[str] = frozenset()) -> None:
    """A descendant may only be born from a parent qualified by someone else.

    The reviewer id must be a plain lowercase name that does not contain (even
    as a 16-character prefix) the id of the individual, its founder, its parent
    or ``also_excluded`` (the child being born). This record is not
    authenticated: whoever can write the lab root can write one, so it is a
    declaration checked for shape and self-reference, not a proof of review.
    """
    fields = {"qualification_schema", "agent_id", "agent_spec_id", "state", "scope", "criteria_sha256",
              "evidence_sha256", "subject_code_sha256", "reviewer_kind", "reviewer_id"}
    if type(qualification) is not dict or set(qualification) != fields or \
            qualification["qualification_schema"] != QUALIFICATION_SCHEMA:
        raise LineageError("QUALIFICATION_INVALID")
    if qualification["agent_id"] != record["agent_id"] or \
            qualification["agent_spec_id"] != record["agent_spec_id"]:
        raise LineageError("QUALIFICATION_NOT_FOR_THIS_SPEC")
    if qualification["state"] not in QUALIFICATION_STATES or qualification["state"] != "QUALIFIED_SIMULATED" \
            or qualification["scope"] != "SIMULATED_DETERMINISTIC":
        raise LineageError("PARENT_NOT_QUALIFIED")
    for name in ("criteria_sha256", "evidence_sha256", "subject_code_sha256"):
        if type(qualification[name]) is not str or not _HEX64.fullmatch(qualification[name]):
            raise LineageError("QUALIFICATION_INVALID")
    reviewer = qualification["reviewer_id"]
    if qualification["reviewer_kind"] not in REVIEWER_KINDS or type(reviewer) is not str or \
            not _REVIEWER_ID.fullmatch(reviewer):
        raise LineageError("SELF_QUALIFICATION_DENIED")
    lineage = record["lineage"]
    excluded = {record["agent_id"], lineage["founder_agent_id"], lineage["parent_agent_id"], *also_excluded}
    if any(type(agent) is str and agent[:16] in reviewer for agent in excluded):
        raise LineageError("SELF_QUALIFICATION_DENIED")


def make_descendant(parent: dict, parent_spec: dict, child_spec: dict, *, parent_qualification: Any,
                    lab_permissions: Any, budget: Any, declared_diff: Any) -> dict:
    verify_record(parent, parent_spec)
    ids = _spec(child_spec)
    check_qualification(parent_qualification, parent, also_excluded=frozenset({ids["agent_id"]}))
    if ids["agent_id"] == parent["agent_id"]:
        raise LineageError("SAME_IDENTITY_AS_PARENT")
    if declared_diff != spec_diff(parent_spec, child_spec):
        raise LineageError("UNDECLARED_MUTATION")
    permissions = _permissions(lab_permissions, child_spec)
    if not set(permissions) <= set(parent["lab_permissions"]):
        raise LineageError("PERMISSION_ESCALATION")
    lineage = parent["lineage"]
    return _seal({
        "individual_schema": INDIVIDUAL_SCHEMA, **ids, "role": "DESCENDANT",
        "lineage": {"lineage_id": lineage["lineage_id"], "founder_agent_id": lineage["founder_agent_id"],
                    "parent_agent_id": parent["agent_id"], "parent_agent_spec_id": parent["agent_spec_id"],
                    "generation": lineage["generation"] + 1},
        "genotype": {"base_agent_spec_id": parent["agent_spec_id"], "declared_diff": list(declared_diff)},
        "lab_permissions": permissions, "budget": _budget(budget), "memory": dict(MEMORY),
        "credentials": "NONE", "registry": dict(REGISTRY), "operational_authority": "DENIED",
    })


def verify_record(record: Any, spec: dict, parent: dict | None = None, parent_spec: dict | None = None) -> None:
    """Recompute everything a stored record claims; a record is data, not a permission.

    A descendant is checked against its parent's record, which the caller has
    verified first (a lineage is verified from the founder down).
    """
    if type(record) is not dict or set(record) != RECORD_FIELDS:
        raise LineageError("RECORD_SCHEMA_VIOLATION")
    _canonical(record)
    if record["record_hash"] != _record_hash(record):
        raise LineageError("RECORD_HASH_MISMATCH")
    ids = _spec(spec)
    if any(record[name] != value for name, value in ids.items()):
        raise LineageError("RECORD_SPEC_MISMATCH")
    if record["individual_schema"] != INDIVIDUAL_SCHEMA or record["memory"] != MEMORY or \
            record["credentials"] != "NONE" or record["registry"] != REGISTRY or \
            record["operational_authority"] != "DENIED":
        raise LineageError("RECORD_SCHEMA_VIOLATION")
    _permissions(record["lab_permissions"], spec)
    _budget(record["budget"])
    lineage = record["lineage"]
    if type(lineage) is not dict or set(lineage) != {"lineage_id", "founder_agent_id", "parent_agent_id",
                                                      "parent_agent_spec_id", "generation"}:
        raise LineageError("RECORD_SCHEMA_VIOLATION")
    if record["role"] == "FOUNDER":
        expected = {"lineage_id": lineage_id(record["agent_id"]), "founder_agent_id": record["agent_id"],
                    "parent_agent_id": None, "parent_agent_spec_id": None, "generation": 0}
        if lineage != expected or record["genotype"] != {"base_agent_spec_id": None, "declared_diff": []}:
            raise LineageError("LINEAGE_INVALID")
        return
    if record["role"] != "DESCENDANT" or parent is None or parent_spec is None:
        raise LineageError("LINEAGE_INVALID")
    expected = {"lineage_id": parent["lineage"]["lineage_id"],
                "founder_agent_id": parent["lineage"]["founder_agent_id"],
                "parent_agent_id": parent["agent_id"], "parent_agent_spec_id": parent["agent_spec_id"],
                "generation": parent["lineage"]["generation"] + 1}
    genotype = {"base_agent_spec_id": parent["agent_spec_id"], "declared_diff": spec_diff(parent_spec, spec)}
    if lineage != expected or record["genotype"] != genotype or record["agent_id"] == parent["agent_id"]:
        raise LineageError("LINEAGE_INVALID")
    if not set(record["lab_permissions"]) <= set(parent["lab_permissions"]):
        raise LineageError("PERMISSION_ESCALATION")
