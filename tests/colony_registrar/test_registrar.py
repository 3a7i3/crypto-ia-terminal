"""colony-registrar/0: a qualified descendant may become a parent, only within explicit limits."""

import ast
import copy
import json
from pathlib import Path

import pytest

from colony_lab import lineage
from colony_lab import qualification as q
from colony_lab import supervisor as sup
from colony_pilot import campaign
from colony_registrar import registrar as reg
from tests.colony_lab import builders

ROOT = Path(__file__).resolve().parents[2]
MISSION = "fixture-colony-mission"
ADMITTER = "fixture-external-admitter"
PERMS = ["DIAGNOSTIC_PRODUCE", "GOVERNED_ARTIFACT_READ"]


def _spec(name):
    return builders.spec(name=name, display=name.replace("_", " ").title())


def _policy(**changes):
    policy = {**reg.load_policy()[0], "admissible_parent_criteria_sha256": ["1" * 64], **changes}
    return policy, reg._sha(policy)


class Colony:
    def __init__(self, tmp_path, **changes):
        self.lab = sup.Supervisor(builders.lab_root(tmp_path), missions=frozenset({MISSION}))
        self.founder_spec, self.founder = builders.founder(permissions=PERMS)
        self.lab.admit(self.founder, self.founder_spec)
        policy, pin = _policy(**changes)
        self.registrar = reg.Registrar(self.lab, policy=policy, policy_sha256=pin)

    def spec_of(self, agent_id):
        return self.lab.load(agent_id)[1]

    def admission(self, child_spec, parent_id, **changes):
        return {"admission_schema": reg.ADMISSION_SCHEMA, "child_agent_id": child_spec["agent_id"],
                "child_agent_spec_id": child_spec["agent_spec_id"], "parent_agent_id": parent_id,
                "admitter_kind": "EXTERNAL_HUMAN", "admitter_id": ADMITTER,
                "policy_sha256": self.registrar.policy_sha256, **changes}

    def birth(self, parent_id, name, *, qualification=None, admission=None, permissions=("DIAGNOSTIC_PRODUCE",),
              budget=None, declared_diff=None, child_spec=None):
        child_spec = child_spec or _spec(name)
        parent, parent_spec = self.lab.load(parent_id)
        return self.registrar.birth(
            parent_id, child_spec,
            parent_qualification=builders.qualification(parent) if qualification is None else qualification,
            admission=self.admission(child_spec, parent_id) if admission is None else admission,
            lab_permissions=None if permissions is None else list(permissions),
            budget=dict(budget or builders.BUDGET),
            declared_diff=lineage.spec_diff(parent_spec, child_spec) if declared_diff is None else declared_diff)

    def homes(self):
        return sorted(p.name for p in (self.lab.root / "individuals").iterdir())


@pytest.fixture
def colony(tmp_path):
    count = iter(range(100))

    def make(**changes):
        place = tmp_path / f"colony-{next(count)}"
        place.mkdir()
        return Colony(place, **changes)
    return make


def _refused(code, call):
    with pytest.raises(reg.RegistrarError) as info:
        call()
    assert info.value.code == code


# ── A descendant becomes a parent ─────────────────────────────────────────
def test_a_qualified_descendant_becomes_a_parent_and_its_lineage_verifies(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    grandchild = c.birth(child["agent_id"], "grandchild_01")
    assert (child["generation"], grandchild["generation"]) == (1, 2)
    record, _ = c.lab.load(grandchild["agent_id"])  # re-verified from the founder down
    assert record == grandchild["record"]
    assert record["lineage"]["founder_agent_id"] == c.founder["agent_id"]
    assert record["lineage"]["parent_agent_id"] == child["agent_id"]
    assert record["lineage"]["lineage_id"] == c.founder["lineage"]["lineage_id"]
    assert record["lab_permissions"] == ["DIAGNOSTIC_PRODUCE"]
    assert (record["credentials"], record["operational_authority"]) == ("NONE", "DENIED")
    assert record["memory"] == lineage.MEMORY and record["registry"] == lineage.REGISTRY
    home = c.lab.root / "individuals" / grandchild["agent_id"]
    assert json.loads((home / "admission.json").read_text()) == c.admission(c.spec_of(grandchild["agent_id"]),
                                                                           child["agent_id"])
    assert json.loads((home / "birth_qualification.json").read_text()) == builders.qualification(
        c.lab.load(child["agent_id"])[0])
    assert not (c.lab.root / reg.LOCK).exists()


def test_the_lab_alone_cannot_make_a_grandchild_which_is_why_the_registrar_exists(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    parent, parent_spec = c.lab.load(child["agent_id"])
    spec = builders.spec(name="grandchild_01")
    with pytest.raises(lineage.LineageError, match="LINEAGE_INVALID"):
        lineage.make_descendant(parent, parent_spec, spec, parent_qualification=builders.qualification(parent),
                                lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=dict(builders.BUDGET),
                                declared_diff=lineage.spec_diff(parent_spec, spec))


# ── Limits ────────────────────────────────────────────────────────────────
def test_depth_is_capped(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    grandchild = c.birth(child["agent_id"], "grandchild_01")
    before = c.homes()
    _refused("GENERATION_LIMIT", lambda: c.birth(grandchild["agent_id"], "great_01"))
    assert c.homes() == before and not (c.lab.root / reg.LOCK).exists()


def test_population_and_children_are_capped(colony):
    c = colony(max_population=2)
    c.birth(c.founder["agent_id"], "child_01")
    _refused("POPULATION_LIMIT", lambda: c.birth(c.founder["agent_id"], "child_02"))
    c = colony(max_children_per_parent=1)
    child = c.birth(c.founder["agent_id"], "child_01")
    _refused("CHILDREN_LIMIT", lambda: c.birth(c.founder["agent_id"], "child_02"))
    assert c.birth(child["agent_id"], "grandchild_01")["generation"] == 2  # the limit is per parent


def test_costs_are_bounded_by_the_parent_and_by_the_colony(colony):
    c = colony()
    _refused("BUDGET_ESCALATION", lambda: c.birth(c.founder["agent_id"], "child_01",
                                                  budget={**builders.BUDGET, "runs": builders.BUDGET["runs"] + 1}))
    budget = {**reg.load_policy()[0]["colony_budget"], "cpu_seconds": 2 * builders.BUDGET["cpu_seconds"]}
    c = colony(colony_budget=budget)
    c.birth(c.founder["agent_id"], "child_01")  # founder + child = exactly the cap
    _refused("COLONY_BUDGET_EXCEEDED", lambda: c.birth(c.founder["agent_id"], "child_02",
                                                       budget={**builders.BUDGET, "cpu_seconds": 1}))


def test_admissions_are_serialized(colony):
    c = colony()
    (c.lab.root / reg.LOCK).write_text("")
    _refused("REGISTRAR_BUSY", lambda: c.birth(c.founder["agent_id"], "child_01"))
    assert c.homes() == [c.founder["agent_id"]]


def test_runs_through_the_registrar_are_capped_and_release_their_slot(colony):
    c = colony()
    slots = c.lab.root / reg.SLOTS
    slots.mkdir()
    (slots / "slot-0").write_text("")
    _refused("CONCURRENCY_LIMIT", lambda: c.registrar.run(c.founder["agent_id"], {}))
    (slots / "slot-0").unlink()
    outcome = c.registrar.run(c.founder["agent_id"], {})
    assert outcome["agent_id"] == c.founder["agent_id"] and list(slots.iterdir()) == []  # the lab decided


# ── Qualification and admission come from outside ─────────────────────────
@pytest.mark.parametrize("qualification,code", [
    ("missing", "QUALIFICATION_INVALID"),
    ({"state": "FAILED"}, "PARENT_NOT_QUALIFIED"),
    ({"state": "REVOKED"}, "PARENT_NOT_QUALIFIED"),
    ({"criteria_sha256": "5" * 64}, "CRITERIA_NOT_ADMISSIBLE"),
    ({"reviewer_kind": "AGENT"}, "SELF_QUALIFICATION_DENIED"),
])
def test_a_parent_needs_a_prior_external_qualification_under_admissible_criteria(colony, qualification, code):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    parent = c.lab.load(child["agent_id"])[0]
    value = None if qualification == "missing" else {**builders.qualification(parent), **qualification}
    _refused(code, lambda: c.birth(child["agent_id"], "grandchild_01", qualification=value or {}))


def test_the_qualification_must_be_of_the_parent_not_of_an_ancestor(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    _refused("QUALIFICATION_NOT_FOR_THIS_SPEC",
             lambda: c.birth(child["agent_id"], "grandchild_01", qualification=builders.qualification(c.founder)))


def test_no_ancestor_qualifies_or_admits_its_own_line(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    spec = _spec("grandchild_01")
    parent = c.lab.load(child["agent_id"])[0]
    for agent in (c.founder["agent_id"], child["agent_id"], spec["agent_id"]):
        reviewer = "fixture-" + agent[:16]
        _refused("SELF_QUALIFICATION_DENIED", lambda r=reviewer: c.birth(
            child["agent_id"], "grandchild_01", qualification=builders.qualification(parent, reviewer=r)))
        _refused("SELF_ADMISSION_DENIED", lambda r=reviewer: c.birth(
            child["agent_id"], "grandchild_01", admission=c.admission(spec, child["agent_id"], admitter_id=r)))


@pytest.mark.parametrize("change,code", [
    ({"admission_schema": "colony-registrar.admission/1"}, "ADMISSION_INVALID"),
    ({"extra": 1}, "ADMISSION_INVALID"),
    ({"child_agent_id": "a" * 64}, "ADMISSION_NOT_FOR_THIS_BIRTH"),
    ({"child_agent_spec_id": "a" * 64}, "ADMISSION_NOT_FOR_THIS_BIRTH"),
    ({"parent_agent_id": "a" * 64}, "ADMISSION_NOT_FOR_THIS_BIRTH"),
    ({"policy_sha256": "a" * 64}, "ADMISSION_NOT_FOR_THIS_BIRTH"),
    ({"admitter_kind": "AGENT"}, "SELF_ADMISSION_DENIED"),
    ({"admitter_kind": "LAB_OPERATOR"}, "SELF_ADMISSION_DENIED"),
    ({"admitter_id": "X"}, "SELF_ADMISSION_DENIED"),
])
def test_a_birth_needs_its_own_external_admission(colony, change, code):
    c = colony()
    spec = _spec("child_01")
    admission = c.admission(spec, c.founder["agent_id"], **change)
    _refused(code, lambda: c.birth(c.founder["agent_id"], "child_01", admission=admission))
    assert c.homes() == [c.founder["agent_id"]]


def test_a_missing_admission_is_refused(colony):
    c = colony()
    _refused("ADMISSION_INVALID", lambda: c.birth(c.founder["agent_id"], "child_01", admission={}))


# ── Identity, lineage, permissions ────────────────────────────────────────
def test_a_child_never_takes_the_identity_of_an_ancestor_or_of_an_admitted_individual(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    sibling = c.birth(c.founder["agent_id"], "child_02")
    _refused("CYCLE_DENIED", lambda: c.birth(child["agent_id"], "x", child_spec=c.founder_spec))
    _refused("CYCLE_DENIED", lambda: c.birth(child["agent_id"], "x", child_spec=c.spec_of(child["agent_id"])))
    _refused("ALREADY_ADMITTED", lambda: c.birth(child["agent_id"], "x", child_spec=c.spec_of(sibling["agent_id"])))


def test_permissions_are_declared_never_inherited_nor_widened(colony):
    c = colony()
    _refused("PERMISSIONS_NOT_DECLARED", lambda: c.birth(c.founder["agent_id"], "child_01", permissions=None))
    narrow = c.birth(c.founder["agent_id"], "child_01", permissions=("GOVERNED_ARTIFACT_READ",))
    _refused("PERMISSION_ESCALATION", lambda: c.birth(narrow["agent_id"], "grandchild_01",
                                                      permissions=("DIAGNOSTIC_PRODUCE",)))
    _refused("PERMISSION_NOT_GRANTABLE", lambda: c.birth(c.founder["agent_id"], "child_02",
                                                         permissions=("SECRET_READ",)))


def test_an_undeclared_mutation_is_refused(colony):
    c = colony()
    _refused("UNDECLARED_MUTATION", lambda: c.birth(c.founder["agent_id"], "child_01", declared_diff=["purpose"]))


def test_an_unverifiable_individual_in_the_colony_refuses_every_birth(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    record = c.lab.root / "individuals" / child["agent_id"] / "record.json"
    tampered = json.loads(record.read_text())
    tampered["lab_permissions"] = PERMS
    record.write_text(json.dumps(tampered))
    _refused("POPULATION_UNVERIFIABLE", lambda: c.birth(c.founder["agent_id"], "child_02"))
    (c.lab.root / "individuals" / "not-an-agent").mkdir()
    record.write_text(json.dumps(child["record"]))
    _refused("POPULATION_UNVERIFIABLE", lambda: c.birth(c.founder["agent_id"], "child_02"))


# ── Policy ────────────────────────────────────────────────────────────────
def test_the_frozen_policy_g0_is_pinned_and_admits_only_the_reviewed_criteria():
    policy, pin = reg.load_policy()
    assert pin == reg.POLICY_SHA256 == reg._sha(json.loads(reg.POLICY_FILE.read_text()))
    assert policy["admissible_parent_criteria_sha256"] == sorted([q.load_criteria("r8")[1],
                                                                  campaign.load_criteria("p1")[1]])
    assert (policy["max_generation"], policy["max_population"], policy["max_children_per_parent"],
            policy["max_concurrent_runs"]) == (2, 6, 2, 1)
    assert policy["admitter_kinds"] == ["EXTERNAL_HUMAN", "EXTERNAL_REVIEW_PROCESS"]


@pytest.mark.parametrize("change", [
    {"max_generation": sup.MAX_LINEAGE_DEPTH + 1}, {"max_generation": 0}, {"max_population": 65},
    {"max_children_per_parent": 9}, {"max_concurrent_runs": 5}, {"max_concurrent_runs": True},
    {"admitter_kinds": ["AGENT"]}, {"admitter_kinds": []}, {"admissible_parent_criteria_sha256": []},
    {"admissible_parent_criteria_sha256": ["X" * 64]}, {"policy_schema": "colony-registrar.policy/1"},
    {"colony_budget": {"runs": 1}}, {"extra": 1},
])
def test_a_policy_looser_than_the_ceilings_or_malformed_is_refused(tmp_path, change):
    policy = {**reg.load_policy()[0], **change}
    lab = sup.Supervisor(builders.lab_root(tmp_path), missions=frozenset({MISSION}))
    _refused("POLICY_INVALID", lambda: reg.Registrar(lab, policy=policy, policy_sha256=reg._sha(policy)))


def test_a_policy_is_only_used_with_its_own_pin(tmp_path):
    policy, pin = _policy()
    lab = sup.Supervisor(builders.lab_root(tmp_path), missions=frozenset({MISSION}))
    _refused("POLICY_PIN_MISMATCH", lambda: reg.Registrar(lab, policy=policy, policy_sha256=reg.POLICY_SHA256))
    changed = copy.deepcopy(policy)
    changed["max_population"] = 7
    _refused("POLICY_PIN_MISMATCH", lambda: reg.Registrar(lab, policy=changed, policy_sha256=pin))


def test_the_default_registrar_uses_the_frozen_policy(tmp_path):
    lab = sup.Supervisor(builders.lab_root(tmp_path), missions=frozenset({MISSION}))
    registrar = reg.Registrar(lab)
    assert registrar.policy_sha256 == reg.POLICY_SHA256


# ── No autonomous reproduction ────────────────────────────────────────────
def _imports(path):
    tree = ast.parse(path.read_text())
    return {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | \
        {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}


def test_no_lab_module_or_worker_can_reach_the_registrar():
    for package in ("colony_lab", "colony_pilot", "colony_trust"):
        for path in (ROOT / package).rglob("*.py"):
            assert not any(name.startswith("colony_registrar") for name in _imports(path)), path
    assert all(not t.module.startswith("colony_registrar") for t in sup.TASKS.values())
    allowed = ("__future__", "hashlib", "json", "os", "contextlib", "pathlib", "typing", "colony_lab")
    for path in (ROOT / "colony_registrar").rglob("*.py"):
        assert all(name.startswith(allowed) for name in _imports(path)), path


def test_an_admitted_identity_is_refused_before_any_limit_is_counted(colony):
    c = colony(max_children_per_parent=1)
    child = c.birth(c.founder["agent_id"], "child_01")
    _refused("ALREADY_ADMITTED", lambda: c.birth(c.founder["agent_id"], "x", child_spec=c.spec_of(child["agent_id"])))


def test_every_ancestor_is_excluded_from_qualifying_a_deep_birth(colony):
    """The lab excludes the parent, its parent and the founder; the registrar excludes the whole line."""
    c = colony(max_generation=4)
    small = {**builders.BUDGET, "memory_bytes": 1 << 28, "output_bytes": 1 << 18}
    line = [c.founder["agent_id"]]
    for name in ("child_01", "grandchild_01", "great_01"):
        line.append(c.birth(line[-1], name, budget=small)["agent_id"])
    parent = c.lab.load(line[-1])[0]
    reviewer = "fixture-" + line[1][:16]  # generation 1: neither the parent's parent nor the founder
    _refused("SELF_QUALIFICATION_DENIED", lambda: c.birth(
        line[-1], "great_great_01", budget=small,
        qualification=builders.qualification(parent, reviewer=reviewer)))
    assert c.birth(line[-1], "great_great_01", budget=small)["generation"] == 4
