"""Births under external control, with limits the lab itself does not have.

A descendant may become a parent once it is qualified by someone else under
criteria the frozen policy lists. Every birth also needs an admission decided
outside the lineage, keeps the child's identity distinct from every ancestor
and every admitted individual, stays within the policy's depth, population,
children, concurrency and cost limits, and grants nothing the parent does not
have. Records are re-verified from the founder down through the lab.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import contextmanager
from typing import Any

from colony_lab import lineage
from colony_lab import supervisor as sup
from colony_lab.a1_identity import IdentityError, _canonical

POLICY_SCHEMA = "colony-registrar.policy/0"
ADMISSION_SCHEMA = "colony-registrar.admission/0"
POLICY_FILE = sup.REPO / "docs" / "colony_registrar" / "POLICY_G0.json"
POLICY_SHA256 = "1226d889505e84b970be47b442c1db33ab85bcdba953a4f818a1f5a7dec4caff"
POLICY_FIELDS = frozenset({"policy_schema", "revision", "max_generation", "max_population",
                           "max_children_per_parent", "max_concurrent_runs", "colony_budget",
                           "admissible_parent_criteria_sha256", "admitter_kinds"})
ADMISSION_FIELDS = frozenset({"admission_schema", "child_agent_id", "child_agent_spec_id", "parent_agent_id",
                              "admitter_kind", "admitter_id", "policy_sha256", "parent_qualification_sha256",
                              "budget", "lab_permissions", "declared_diff"})
# Hard ceilings: a caller's own policy can be stricter, never looser.
CEILINGS = {"max_generation": sup.MAX_LINEAGE_DEPTH, "max_population": 64, "max_children_per_parent": 8,
            "max_concurrent_runs": 4}
BUDGET_CEILING = {name: 64 * value for name, value in lineage.BUDGET_MAX.items()}
LOCK = "registrar.lock"
SLOTS = "registrar-slots"
ADMISSIONS = "registrar-admissions"


class RegistrarError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def check_policy(policy: Any, pin_sha256: str) -> dict:
    """A copy of the policy equal to its pin, within the hard ceilings; POLICY_* refusals otherwise."""
    try:
        return copy.deepcopy(_check_policy(policy, pin_sha256))
    except TypeError:
        raise RegistrarError("POLICY_INVALID") from None


def _check_policy(policy: Any, pin_sha256: str) -> dict:
    try:
        digest = _sha(policy)
    except IdentityError:
        raise RegistrarError("POLICY_INVALID") from None
    if digest != pin_sha256:
        raise RegistrarError("POLICY_PIN_MISMATCH")
    if type(policy) is not dict or set(policy) != POLICY_FIELDS or policy["policy_schema"] != POLICY_SCHEMA or \
            type(policy["revision"]) is not str:
        raise RegistrarError("POLICY_INVALID")
    for name, ceiling in CEILINGS.items():
        if type(policy[name]) is not int or not 1 <= policy[name] <= ceiling:
            raise RegistrarError("POLICY_INVALID")
    budget = policy["colony_budget"]
    if type(budget) is not dict or set(budget) != set(BUDGET_CEILING) or \
            any(type(budget[n]) is not int or not 1 <= budget[n] <= c for n, c in BUDGET_CEILING.items()):
        raise RegistrarError("POLICY_INVALID")
    criteria, kinds = policy["admissible_parent_criteria_sha256"], policy["admitter_kinds"]
    if type(criteria) is not list or not criteria or criteria != sorted(set(criteria)) or \
            any(type(c) is not str or not lineage._HEX64.fullmatch(c) for c in criteria):
        raise RegistrarError("POLICY_INVALID")
    if type(kinds) is not list or not kinds or kinds != sorted(set(kinds)) or \
            not set(kinds) <= lineage.REVIEWER_KINDS:
        raise RegistrarError("POLICY_INVALID")
    return policy


def load_policy() -> tuple[dict, str]:
    """The frozen policy g0 and its pin."""
    try:
        policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RegistrarError("POLICY_INVALID") from None
    return check_policy(policy, POLICY_SHA256), POLICY_SHA256


def _excluded_in(name: str, agents: set) -> bool:
    return any(type(agent) is str and agent[:16] in name for agent in agents)


class Registrar:
    """The operator's gate for births; it holds no handle an individual can reach."""

    def __init__(self, supervisor: sup.Supervisor, *, policy: Any = None, policy_sha256: str | None = None) -> None:
        if policy is None:
            self.policy, self.policy_sha256 = load_policy()
        else:
            self.policy, self.policy_sha256 = check_policy(policy, policy_sha256), policy_sha256
        self.lab = supervisor

    # ── Population and admissions, read through the lab ────────────────────
    def _population(self) -> list[dict]:
        """Every admitted individual, each re-verified; an unreadable one refuses the birth."""
        individuals = self.lab.root / "individuals"
        if not individuals.is_dir():
            return []
        records = []
        for home in sorted(individuals.iterdir()):
            try:
                records.append(self.lab.load(home.name)[0])
            except sup.LabError:
                raise RegistrarError("POPULATION_UNVERIFIABLE") from None
        return records

    def _admission_path(self, agent_id: str):
        return self.lab.root / ADMISSIONS / f"{agent_id}.json"

    def _check_admitted(self, record: dict) -> None:
        """A descendant ancestor has the registrar admission that was written before it was born."""
        try:
            admission = sup._read_json(self._admission_path(record["agent_id"]))
        except sup.LabError:
            raise RegistrarError("ANCESTOR_NOT_ADMITTED") from None
        source = record["lineage"]
        if type(admission) is not dict or set(admission) != ADMISSION_FIELDS or \
                admission["admission_schema"] != ADMISSION_SCHEMA or \
                admission["child_agent_id"] != record["agent_id"] or \
                admission["child_agent_spec_id"] != record["agent_spec_id"] or \
                admission["parent_agent_id"] != source["parent_agent_id"] or \
                admission["budget"] != record["budget"] or admission["lab_permissions"] != record["lab_permissions"] \
                or admission["declared_diff"] != record["genotype"]["declared_diff"]:
            raise RegistrarError("ANCESTOR_NOT_ADMITTED")

    def _ancestry(self, record: dict) -> list[dict]:
        """The record and its ancestors, from the record up to the founder."""
        chain = [record]
        while chain[-1]["role"] == "DESCENDANT":
            chain.append(self.lab.load(chain[-1]["lineage"]["parent_agent_id"])[0])
        return chain

    @contextmanager
    def _lock(self):
        path = self.lab.root / LOCK
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            raise RegistrarError("REGISTRAR_BUSY") from None
        os.close(fd)
        try:
            yield
        finally:
            path.unlink(missing_ok=True)

    # ── Births ─────────────────────────────────────────────────────────────
    def birth(self, parent_agent_id: str, child_spec: dict, *, parent_qualification: Any, admission: Any,
              lab_permissions: Any, budget: Any, declared_diff: Any) -> dict:
        if self.lab.stopped:
            raise RegistrarError("LAB_STOPPED")
        with self._lock():
            try:
                return self._birth(parent_agent_id, child_spec, parent_qualification, admission,
                                   lab_permissions, budget, declared_diff)
            except (sup.LabError, lineage.LineageError) as exc:
                raise RegistrarError(exc.code) from None
            except (TypeError, KeyError, AttributeError):
                raise RegistrarError("BIRTH_INPUT_INVALID") from None
            except OSError:
                raise RegistrarError("LAB_IO_ERROR") from None

    def _birth(self, parent_agent_id, child_spec, qualification, admission, permissions, budget, declared_diff):
        policy = self.policy
        parent, parent_spec = self.lab.load(parent_agent_id)
        ancestry = self._ancestry(parent)
        ids = lineage._spec(child_spec)
        child_id = ids["agent_id"]
        ancestors = {agent["agent_id"] for agent in ancestry}
        if child_id in ancestors:
            raise RegistrarError("CYCLE_DENIED")
        for agent in ancestry:
            if agent["role"] == "DESCENDANT":
                self._check_admitted(agent)
        population = self._population()
        admitted = {agent["agent_id"] for agent in population}
        if child_id in admitted:
            raise RegistrarError("ALREADY_ADMITTED")
        excluded = frozenset({child_id, *ancestors, *admitted})
        if parent["lineage"]["generation"] + 1 > policy["max_generation"]:
            raise RegistrarError("GENERATION_LIMIT")
        if len(population) + 1 > policy["max_population"]:
            raise RegistrarError("POPULATION_LIMIT")
        children = [a for a in population if a["lineage"]["parent_agent_id"] == parent["agent_id"]]
        if len(children) + 1 > policy["max_children_per_parent"]:
            raise RegistrarError("CHILDREN_LIMIT")
        # Prior qualification by someone outside the whole colony, under admissible criteria.
        lineage.check_qualification(qualification, parent, also_excluded=excluded)
        if qualification["criteria_sha256"] not in policy["admissible_parent_criteria_sha256"]:
            raise RegistrarError("CRITERIA_NOT_ADMISSIBLE")
        self._check_admission(admission, ids, parent, excluded)
        # Explicit, narrower permissions; costs bounded by the parent and by the colony.
        child_budget = lineage._budget(budget)
        if any(child_budget[name] > parent["budget"][name] for name in child_budget):
            raise RegistrarError("BUDGET_ESCALATION")
        for name, cap in policy["colony_budget"].items():
            if sum(agent["budget"][name] for agent in population) + child_budget[name] > cap:
                raise RegistrarError("COLONY_BUDGET_EXCEEDED")
        if declared_diff != lineage.spec_diff(parent_spec, child_spec):
            raise RegistrarError("UNDECLARED_MUTATION")
        granted = lineage._permissions(permissions, child_spec)
        if not set(granted) <= set(parent["lab_permissions"]):
            raise RegistrarError("PERMISSION_ESCALATION")
        # The admission decided exactly this birth: this qualification, budget, permissions and diff.
        if admission["parent_qualification_sha256"] != _sha(qualification) or admission["budget"] != child_budget \
                or admission["lab_permissions"] != granted or admission["declared_diff"] != declared_diff:
            raise RegistrarError("ADMISSION_NOT_FOR_THIS_BIRTH")
        source = parent["lineage"]
        record = lineage._seal({
            "individual_schema": lineage.INDIVIDUAL_SCHEMA, **ids, "role": "DESCENDANT",
            "lineage": {"lineage_id": source["lineage_id"], "founder_agent_id": source["founder_agent_id"],
                        "parent_agent_id": parent["agent_id"], "parent_agent_spec_id": parent["agent_spec_id"],
                        "generation": source["generation"] + 1},
            "genotype": {"base_agent_spec_id": parent["agent_spec_id"], "declared_diff": list(declared_diff)},
            "lab_permissions": granted, "budget": child_budget, "memory": dict(lineage.MEMORY),
            "credentials": "NONE", "registry": dict(lineage.REGISTRY), "operational_authority": "DENIED",
        })
        lineage.verify_record(record, child_spec, parent, parent_spec)
        self._record_admission(child_id, admission)  # before the child: never a child without its admission
        result = self.lab.admit(record, child_spec, parent_qualification=qualification)
        return {**result, "generation": record["lineage"]["generation"], "record": record}

    def _record_admission(self, child_id: str, admission: dict) -> None:
        path, data = self._admission_path(child_id), sup._dump(admission)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        try:
            sup._write_new(path, data)
        except FileExistsError:
            # Left by a birth that stopped before admitting the child: only the same decision may resume it.
            try:
                same = sup._read_json(path) == admission
            except sup.LabError:
                same = False
            if not same:
                raise RegistrarError("ADMISSION_CONFLICT") from None

    def _check_admission(self, admission: Any, ids: dict, parent: dict, excluded: frozenset) -> None:
        if type(admission) is not dict or set(admission) != ADMISSION_FIELDS or \
                admission["admission_schema"] != ADMISSION_SCHEMA:
            raise RegistrarError("ADMISSION_INVALID")
        if admission["child_agent_id"] != ids["agent_id"] or \
                admission["child_agent_spec_id"] != ids["agent_spec_id"] or \
                admission["parent_agent_id"] != parent["agent_id"] or \
                admission["policy_sha256"] != self.policy_sha256:
            raise RegistrarError("ADMISSION_NOT_FOR_THIS_BIRTH")
        admitter = admission["admitter_id"]
        if admission["admitter_kind"] not in self.policy["admitter_kinds"] or type(admitter) is not str or \
                not lineage._REVIEWER_ID.fullmatch(admitter) or \
                _excluded_in(admitter, excluded):
            raise RegistrarError("SELF_ADMISSION_DENIED")

    # ── Runs, within the colony's concurrency ──────────────────────────────
    def run(self, agent_id: str, task: Any) -> dict:
        slots = self.lab.root / SLOTS
        slots.mkdir(mode=0o700, exist_ok=True)
        for index in range(self.policy["max_concurrent_runs"]):
            slot = slots / f"slot-{index}"
            try:
                fd = os.open(slot, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                continue
            os.close(fd)
            try:
                return self.lab.run(agent_id, task)
            finally:
                slot.unlink()
        raise RegistrarError("CONCURRENCY_LIMIT")
