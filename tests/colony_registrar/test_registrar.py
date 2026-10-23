"""colony-registrar/0: a qualified descendant may become a parent, only within explicit limits."""

import ast
import copy
import fcntl
import json
import os
import threading
from contextlib import contextmanager
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

    def admission(self, child_spec, parent_id, *, qualification=None, budget=None,
                  permissions=("DIAGNOSTIC_PRODUCE",), declared_diff=None, **changes):
        """The external decision for exactly this birth (same defaults as birth())."""
        parent, parent_spec = self.lab.load(parent_id)
        qualification = builders.qualification(parent) if qualification is None else qualification
        return {"admission_schema": reg.ADMISSION_SCHEMA, "child_agent_id": child_spec["agent_id"],
                "child_agent_spec_id": child_spec["agent_spec_id"], "parent_agent_id": parent_id,
                "admitter_kind": "EXTERNAL_HUMAN", "admitter_id": ADMITTER,
                "policy_sha256": self.registrar.policy_sha256,
                "parent_qualification_sha256": reg._sha(qualification),
                "budget": dict(budget or builders.BUDGET),
                "lab_permissions": None if permissions is None else list(permissions),
                "declared_diff": lineage.spec_diff(parent_spec, child_spec) if declared_diff is None else declared_diff,
                **changes}

    def birth(self, parent_id, name, *, qualification=None, admission=None, permissions=("DIAGNOSTIC_PRODUCE",),
              budget=None, declared_diff=None, child_spec=None):
        child_spec = child_spec or _spec(name)
        parent, parent_spec = self.lab.load(parent_id)
        qualification = builders.qualification(parent) if qualification is None else qualification
        if admission is None:
            try:
                admission = self.admission(child_spec, parent_id, qualification=qualification, budget=budget,
                                           permissions=permissions, declared_diff=declared_diff)
            except (TypeError, KeyError):
                admission = {}
        return self.registrar.birth(
            parent_id, child_spec, parent_qualification=qualification, admission=admission,
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


@contextmanager
def _held(path):
    """Hold the advisory lock another registrar process would hold."""
    path.parent.mkdir(exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _free(path):
    """The lock file, if any, is not held."""
    if not path.exists():
        return True
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


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
    admission = c.lab.root / reg.ADMISSIONS / f"{grandchild['agent_id']}.json"
    assert json.loads(admission.read_text()) == c.admission(c.spec_of(grandchild["agent_id"]), child["agent_id"])
    assert json.loads((home / "birth_qualification.json").read_text()) == builders.qualification(
        c.lab.load(child["agent_id"])[0])
    assert _free(c.lab.root / reg.LOCK)


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
    assert c.homes() == before and _free(c.lab.root / reg.LOCK)


def test_population_and_children_are_capped(colony):
    c = colony(max_population=2)
    c.birth(c.founder["agent_id"], "child_01")
    _refused("POPULATION_LIMIT", lambda: c.birth(c.founder["agent_id"], "child_02"))
    c = colony(max_children_per_parent=1)
    child = c.birth(c.founder["agent_id"], "child_01")
    _refused("CHILDREN_LIMIT", lambda: c.birth(c.founder["agent_id"], "child_02"))
    assert c.birth(child["agent_id"], "grandchild_01")["generation"] == 2  # the limit is per parent


def test_children_are_capped_for_a_parent_of_any_generation(colony):
    c = colony(max_children_per_parent=1)
    child = c.birth(c.founder["agent_id"], "child_01")
    c.birth(child["agent_id"], "grandchild_01")
    _refused("CHILDREN_LIMIT", lambda: c.birth(child["agent_id"], "grandchild_02"))


@pytest.mark.parametrize("field", sorted(builders.BUDGET))
def test_each_budget_field_is_bounded_by_the_parent(colony, field):
    c = colony()
    half = {name: value // 2 for name, value in builders.BUDGET.items()}
    child = c.birth(c.founder["agent_id"], "child_01", budget=half)
    _refused("BUDGET_ESCALATION", lambda: c.birth(child["agent_id"], "grandchild_01",
                                                  budget={**half, field: half[field] + 1}))
    assert c.birth(child["agent_id"], "grandchild_01", budget=half)["generation"] == 2


@pytest.mark.parametrize("field", sorted(builders.BUDGET))
def test_each_budget_field_is_bounded_by_the_colony(colony, field):
    budget = {**reg.load_policy()[0]["colony_budget"], field: 2 * builders.BUDGET[field]}
    c = colony(colony_budget=budget)
    c.birth(c.founder["agent_id"], "child_01")  # founder + child = exactly the cap on this field
    _refused("COLONY_BUDGET_EXCEEDED", lambda: c.birth(c.founder["agent_id"], "child_02",
                                                       budget={**builders.BUDGET, field: 1}))


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
    with _held(c.lab.root / reg.LOCK):
        _refused("REGISTRAR_BUSY", lambda: c.birth(c.founder["agent_id"], "child_01"))
    assert c.homes() == [c.founder["agent_id"]]
    (c.lab.root / reg.LOCK).write_text("")  # a lock file left by a dead process blocks nothing
    assert c.birth(c.founder["agent_id"], "child_01")["generation"] == 1


def test_concurrent_births_never_exceed_the_population(colony):
    c = colony(max_population=2)
    outcomes = []

    def birth(name):
        try:
            outcomes.append(c.birth(c.founder["agent_id"], name)["agent_id"])
        except reg.RegistrarError as exc:
            outcomes.append(exc.code)
    threads = [threading.Thread(target=birth, args=(f"child_0{i}",)) for i in range(1, 7)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(c.homes()) == 2 and set(outcomes) - set(c.homes()) <= {"REGISTRAR_BUSY", "POPULATION_LIMIT"}


def test_runs_through_the_registrar_are_capped_and_release_their_slot(colony):
    c = colony()
    slots = c.lab.root / reg.SLOTS
    with _held(slots / "slot-0"):
        _refused("CONCURRENCY_LIMIT", lambda: c.registrar.run(c.founder["agent_id"], {}))
    outcome = c.registrar.run(c.founder["agent_id"], {})
    assert outcome["agent_id"] == c.founder["agent_id"] and _free(slots / "slot-0")  # the lab decided
    (slots / "slot-0").unlink()  # a slot file removed by someone else breaks nothing
    assert c.registrar.run(c.founder["agent_id"], {})["agent_id"] == c.founder["agent_id"]


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
    ({"parent_qualification_sha256": "a" * 64}, "ADMISSION_NOT_FOR_THIS_BIRTH"),
    ({"budget": {**builders.BUDGET, "runs": 19}}, "ADMISSION_NOT_FOR_THIS_BIRTH"),
    ({"lab_permissions": ["DIAGNOSTIC_PRODUCE", "GOVERNED_ARTIFACT_READ"]}, "ADMISSION_NOT_FOR_THIS_BIRTH"),
    ({"declared_diff": ["purpose"]}, "ADMISSION_NOT_FOR_THIS_BIRTH"),
])
def test_a_birth_needs_its_own_external_admission(colony, change, code):
    c = colony()
    spec = _spec("child_01")
    admission = c.admission(spec, c.founder["agent_id"], **change)
    _refused(code, lambda: c.birth(c.founder["agent_id"], "child_01", admission=admission))
    assert c.homes() == [c.founder["agent_id"]]


def test_nobody_admitted_in_the_colony_qualifies_or_admits_a_birth(colony):
    """Not only the line: a sibling or any other admitted individual is excluded too."""
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    sibling = c.birth(c.founder["agent_id"], "child_02")
    parent = c.lab.load(child["agent_id"])[0]
    reviewer = "fixture-" + sibling["agent_id"][:16]
    spec = _spec("grandchild_01")
    _refused("SELF_QUALIFICATION_DENIED", lambda: c.birth(
        child["agent_id"], "grandchild_01", qualification=builders.qualification(parent, reviewer=reviewer)))
    _refused("SELF_ADMISSION_DENIED", lambda: c.birth(
        child["agent_id"], "grandchild_01", admission=c.admission(spec, child["agent_id"], admitter_id=reviewer)))


def test_a_parent_admitted_outside_the_registrar_cannot_have_children_through_it(colony):
    c = colony()
    spec = _spec("child_01")
    parent = c.founder
    record = lineage.make_descendant(parent, c.founder_spec, spec, parent_qualification=builders.qualification(parent),
                                     lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=dict(builders.BUDGET),
                                     declared_diff=lineage.spec_diff(c.founder_spec, spec))
    c.lab.admit(record, spec, parent_qualification=builders.qualification(parent))  # the lab alone, no admission
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(record["agent_id"], "grandchild_01"))


def test_an_ancestor_whose_admission_was_altered_is_refused(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    path = c.lab.root / reg.ADMISSIONS / f"{child['agent_id']}.json"
    admission = json.loads(path.read_text())
    path.write_text(json.dumps({**admission, "budget": {**admission["budget"], "runs": 1}}))
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(child["agent_id"], "grandchild_01"))
    path.write_text("{")
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(child["agent_id"], "grandchild_01"))
    path.write_text(json.dumps({**admission, "admission_schema": "colony-registrar.admission/1"}))
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(child["agent_id"], "grandchild_01"))
    sibling = c.birth(c.founder["agent_id"], "child_02")
    path.write_bytes((c.lab.root / reg.ADMISSIONS / f"{sibling['agent_id']}.json").read_bytes())
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(child["agent_id"], "grandchild_01"))
    path.write_text(json.dumps(admission))
    assert c.birth(child["agent_id"], "grandchild_01")["generation"] == 2


def test_the_admission_is_recorded_before_the_child_and_only_the_same_one_resumes(colony, monkeypatch):
    c = colony()
    spec = _spec("child_01")
    admit = c.lab.admit

    def crash(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(c.lab, "admit", crash)
    _refused("LAB_IO_ERROR", lambda: c.birth(c.founder["agent_id"], "child_01"))
    assert c.homes() == [c.founder["agent_id"]]
    assert (c.lab.root / reg.ADMISSIONS / f"{spec['agent_id']}.json").exists()
    monkeypatch.setattr(c.lab, "admit", admit)
    other = c.admission(spec, c.founder["agent_id"], admitter_id="fixture-other-admitter")
    _refused("ADMISSION_CONFLICT", lambda: c.birth(c.founder["agent_id"], "child_01", admission=other))
    assert c.birth(c.founder["agent_id"], "child_01")["generation"] == 1  # the same decision resumes


def test_no_birth_while_the_operator_stop_is_set(colony):
    c = colony()
    c.lab.stop_file.write_text("")
    _refused("LAB_STOPPED", lambda: c.birth(c.founder["agent_id"], "child_01"))
    assert c.homes() == [c.founder["agent_id"]] and _free(c.lab.root / reg.LOCK)


@pytest.mark.parametrize("call", [
    lambda c: c.birth(c.founder["agent_id"], "child_01", permissions=[{}]),
    lambda c: c.birth(c.founder["agent_id"], "child_01",
                      qualification={**builders.qualification(c.founder), "state": [1]}),
    lambda c: c.birth(c.founder["agent_id"], "child_01",
                      qualification={**builders.qualification(c.founder), "reviewer_kind": {}}),
    lambda c: c.birth(c.founder["agent_id"], "child_01", admission={**c.admission(_spec("child_01"),
                                                                    c.founder["agent_id"]), "admitter_kind": []}),
    lambda c: c.registrar.birth(c.founder["agent_id"], _spec("child_01"), parent_qualification=None,
                                admission=None, lab_permissions=None, budget=None, declared_diff=None),
])
def test_malformed_inputs_get_a_coded_refusal(colony, call):
    c = colony()
    with pytest.raises(reg.RegistrarError):
        call(c)
    assert c.homes() == [c.founder["agent_id"]] and _free(c.lab.root / reg.LOCK)


def test_the_population_and_children_count_individuals_admitted_outside_the_registrar(colony):
    c = colony(max_population=4, max_children_per_parent=2)
    c.birth(c.founder["agent_id"], "child_01")
    _outside(c, "child_02")
    _refused("CHILDREN_LIMIT", lambda: c.birth(c.founder["agent_id"], "child_03"))
    c = colony(max_population=2)
    _outside(c, "child_02")
    _refused("POPULATION_LIMIT", lambda: c.birth(c.founder["agent_id"], "child_01"))


def _outside(c, name, qualification=None):
    """A child admitted by the lab alone, without the registrar."""
    spec = _spec(name)
    qualification = qualification or builders.qualification(c.founder)
    record = lineage.make_descendant(c.founder, c.founder_spec, spec, parent_qualification=qualification,
                                     lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=dict(builders.BUDGET),
                                     declared_diff=lineage.spec_diff(c.founder_spec, spec))
    c.lab.admit(record, spec, parent_qualification=qualification)
    return record


def test_an_orphan_admission_does_not_make_a_lab_admitted_child_a_parent(colony, monkeypatch):
    """A birth stops after its admission is written; the lab then admits the same child itself, under
    inadmissible criteria and with a sibling as reviewer. The registrar refuses it as a parent."""
    c = colony()
    sibling = c.birth(c.founder["agent_id"], "child_02")
    admit = c.lab.admit
    monkeypatch.setattr(c.lab, "admit", lambda *a, **k: (_ for _ in ()).throw(OSError("crash")))
    _refused("LAB_IO_ERROR", lambda: c.birth(c.founder["agent_id"], "child_01"))
    monkeypatch.setattr(c.lab, "admit", admit)
    bad = builders.qualification(c.founder, reviewer="fixture-" + sibling["agent_id"][:16])
    bad["criteria_sha256"] = "5" * 64
    child = _outside(c, "child_01", qualification=bad)
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(child["agent_id"], "grandchild_01"))


@pytest.mark.parametrize("bad", ["criteria", "reviewer"])
def test_a_consistent_admission_still_needs_admissible_criteria_and_an_outside_reviewer(colony, bad):
    """Even an admission whose hashes match the stored qualification is checked against the policy and
    the colony today: inadmissible criteria, or a reviewer who is a sibling, refuse the line."""
    c = colony()
    sibling = c.birth(c.founder["agent_id"], "child_02")
    qualification = builders.qualification(c.founder)
    if bad == "criteria":
        qualification["criteria_sha256"] = "5" * 64
    else:
        qualification["reviewer_id"] = "fixture-" + sibling["agent_id"][:16]
    spec = _spec("child_01")
    admission = c.admission(spec, c.founder["agent_id"], qualification=qualification)
    (c.lab.root / reg.ADMISSIONS / f"{spec['agent_id']}.json").write_bytes(sup._dump(admission))
    child = _outside(c, "child_01", qualification=qualification)
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(child["agent_id"], "grandchild_01"))


@pytest.mark.parametrize("field,value", [
    ("admitter_id", "fixture-other-admitter"), ("admitter_kind", "AGENT"),
    ("policy_sha256", "a" * 64), ("parent_qualification_sha256", "a" * 64),
    ("lab_permissions", ["GOVERNED_ARTIFACT_READ"]), ("parent_agent_id", "a" * 64),
    ("child_agent_spec_id", "a" * 64), ("child_agent_id", "a" * 64), ("extra", 1),
    ("declared_diff", ["purpose"]), ("budget", {**builders.BUDGET, "runs": True}),
])
def test_every_field_of_an_ancestor_admission_is_verified_again(colony, field, value):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    path = c.lab.root / reg.ADMISSIONS / f"{child['agent_id']}.json"
    admission = json.loads(path.read_text())
    if field == "admitter_id":
        # a different admitter is only wrong because the record no longer matches: re-sign nothing, check binding
        path.write_text(json.dumps({**admission, field: "fixture-" + child["agent_id"][:16]}))
    else:
        path.write_text(json.dumps({**admission, field: value}))
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(child["agent_id"], "grandchild_01"))


def test_an_ancestor_admission_under_another_policy_or_criteria_is_refused(colony):
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    policy, pin = _policy(admissible_parent_criteria_sha256=["5" * 64])
    stricter = reg.Registrar(c.lab, policy=policy, policy_sha256=pin)
    parent = c.lab.load(child["agent_id"])[0]
    spec = _spec("grandchild_01")
    qualification = {**builders.qualification(parent), "criteria_sha256": "5" * 64}
    admission = {**c.admission(spec, child["agent_id"], qualification=qualification), "policy_sha256": pin}
    with pytest.raises(reg.RegistrarError) as info:
        stricter.birth(child["agent_id"], spec, parent_qualification=qualification, admission=admission,
                       lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=dict(builders.BUDGET),
                       declared_diff=lineage.spec_diff(c.spec_of(child["agent_id"]), spec))
    assert info.value.code == "ANCESTOR_NOT_ADMITTED"  # the child was admitted under another pin


def test_an_ancestor_two_generations_up_needs_its_admission_too(colony):
    c = colony(max_generation=3)
    child = c.birth(c.founder["agent_id"], "child_01")
    small = {**builders.BUDGET, "memory_bytes": 1 << 28, "output_bytes": 1 << 18}
    grandchild = c.birth(child["agent_id"], "grandchild_01", budget=small)
    (c.lab.root / reg.ADMISSIONS / f"{child['agent_id']}.json").unlink()
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(grandchild["agent_id"], "great_01", budget=small))


def test_the_operator_stop_latch_blocks_a_birth(colony):
    c = colony()
    c.lab.stop()
    _refused("LAB_STOPPED", lambda: c.birth(c.founder["agent_id"], "child_01"))


def test_a_stop_set_during_the_checks_is_read_again_before_anything_is_written(colony, monkeypatch):
    c = colony()
    original = lineage.verify_record

    def verify_then_stop(*args, **kwargs):
        original(*args, **kwargs)
        c.lab.stop_file.write_text("")
    monkeypatch.setattr(lineage, "verify_record", verify_then_stop)
    _refused("LAB_STOPPED", lambda: c.birth(c.founder["agent_id"], "child_01"))
    assert not (c.lab.root / reg.ADMISSIONS / f"{_spec('child_01')['agent_id']}.json").exists()


def test_a_linked_admissions_directory_is_refused(colony, tmp_path):
    c = colony()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (c.lab.root / reg.ADMISSIONS).symlink_to(elsewhere)
    _refused("LAB_IO_ERROR", lambda: c.birth(c.founder["agent_id"], "child_01"))
    assert list(elsewhere.iterdir()) == []


@pytest.mark.parametrize("change", [
    {"budget": {**builders.BUDGET, "runs": 20.0}},
    {"budget": {**builders.BUDGET, "cpu_seconds": 20, "runs": 20, "journal_events": 200.0}},
])
def test_admission_bindings_compare_types_too(colony, change):
    c = colony()
    admission = c.admission(_spec("child_01"), c.founder["agent_id"], **change)
    _refused("ADMISSION_NOT_FOR_THIS_BIRTH", lambda: c.birth(c.founder["agent_id"], "child_01", admission=admission))


def test_identity_errors_are_coded_refusals(colony):
    c = colony()
    secret_like = "ghp_" + "a" * 36
    admission = c.admission(_spec("child_01"), c.founder["agent_id"], parent_qualification_sha256="0" * 64)
    _refused("BIRTH_INPUT_INVALID", lambda: c.birth(
        c.founder["agent_id"], "child_01", admission=admission,
        qualification=builders.qualification(c.founder, reviewer=secret_like)))
    child = c.birth(c.founder["agent_id"], "child_01")
    record = c.lab.root / "individuals" / child["agent_id"] / "record.json"
    record.write_text(json.dumps({**child["record"], "budget": {**child["record"]["budget"], "runs": 1.5}}))
    _refused("POPULATION_UNVERIFIABLE", lambda: c.birth(c.founder["agent_id"], "child_02"))


@pytest.mark.parametrize("change", [
    lambda p: p.update(admitter_kinds=["EXTERNAL_HUMAN"]),
])
def test_the_admitter_kinds_come_from_the_policy(colony, change):
    policy, pin = _policy(admitter_kinds=["EXTERNAL_REVIEW_PROCESS"])
    c = colony()
    c.registrar = reg.Registrar(c.lab, policy=policy, policy_sha256=pin)
    _refused("SELF_ADMISSION_DENIED", lambda: c.birth(c.founder["agent_id"], "child_01"))  # EXTERNAL_HUMAN


def test_an_admitter_id_must_match_the_whole_grammar(colony):
    c = colony()
    admission = c.admission(_spec("child_01"), c.founder["agent_id"], admitter_id=ADMITTER + " X")
    _refused("SELF_ADMISSION_DENIED", lambda: c.birth(c.founder["agent_id"], "child_01", admission=admission))


def test_a_lock_removed_during_a_birth_does_not_hide_its_success(colony, monkeypatch):
    c = colony()
    admit = c.lab.admit

    def admit_and_drop_lock(*args, **kwargs):
        (c.lab.root / reg.LOCK).unlink()
        return admit(*args, **kwargs)
    monkeypatch.setattr(c.lab, "admit", admit_and_drop_lock)
    assert c.birth(c.founder["agent_id"], "child_01")["generation"] == 1


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
    {"colony_budget": {"runs": 1}}, {"extra": 1}, {"admissible_parent_criteria_sha256": [[1]]},
    {"admitter_kinds": [{}]}, {"colony_budget": {**lineage.BUDGET_MAX, "runs": True}},
    {"admissible_parent_criteria_sha256": ["2" * 64, "1" * 64]},
    {"admitter_kinds": ["EXTERNAL_REVIEW_PROCESS", "EXTERNAL_HUMAN"]},
])
def test_a_policy_looser_than_the_ceilings_or_malformed_is_refused(tmp_path, change):
    policy = {**reg.load_policy()[0], **change}
    lab = sup.Supervisor(builders.lab_root(tmp_path), missions=frozenset({MISSION}))
    _refused("POLICY_INVALID", lambda: reg.Registrar(lab, policy=policy, policy_sha256=reg._sha(policy)))


@pytest.mark.parametrize("field", sorted(lineage.BUDGET_MAX))
def test_the_colony_budget_ceiling_is_64_individuals_at_their_maximum(tmp_path, field):
    lab = sup.Supervisor(builders.lab_root(tmp_path), missions=frozenset({MISSION}))
    budget = reg.load_policy()[0]["colony_budget"]
    at_ceiling, _ = _policy(colony_budget={**budget, field: 64 * lineage.BUDGET_MAX[field]})
    reg.Registrar(lab, policy=at_ceiling, policy_sha256=reg._sha(at_ceiling))
    above, _ = _policy(colony_budget={**budget, field: 64 * lineage.BUDGET_MAX[field] + 1})
    _refused("POLICY_INVALID", lambda: reg.Registrar(lab, policy=above, policy_sha256=reg._sha(above)))


def test_a_policy_is_only_used_with_its_own_pin(tmp_path):
    policy, pin = _policy()
    lab = sup.Supervisor(builders.lab_root(tmp_path), missions=frozenset({MISSION}))
    _refused("POLICY_PIN_MISMATCH", lambda: reg.Registrar(lab, policy=policy, policy_sha256=reg.POLICY_SHA256))
    changed = copy.deepcopy(policy)
    changed["max_population"] = 7
    _refused("POLICY_PIN_MISMATCH", lambda: reg.Registrar(lab, policy=changed, policy_sha256=pin))


def test_a_policy_changed_after_the_registrar_is_built_has_no_effect(colony):
    policy, pin = _policy(max_population=2)
    c = colony()
    c.registrar = reg.Registrar(c.lab, policy=policy, policy_sha256=pin)
    policy["max_population"] = 64
    c.birth(c.founder["agent_id"], "child_01")
    _refused("POPULATION_LIMIT", lambda: c.birth(c.founder["agent_id"], "child_02"))


def test_a_nested_policy_change_after_construction_has_no_effect(colony):
    budget = {**reg.load_policy()[0]["colony_budget"], "runs": 2 * builders.BUDGET["runs"]}
    policy, pin = _policy(colony_budget=budget)
    c = colony()
    c.registrar = reg.Registrar(c.lab, policy=policy, policy_sha256=pin)
    policy["colony_budget"]["runs"] = 64 * lineage.BUDGET_MAX["runs"]
    c.birth(c.founder["agent_id"], "child_01")
    _refused("COLONY_BUDGET_EXCEEDED", lambda: c.birth(c.founder["agent_id"], "child_02",
                                                       budget={**builders.BUDGET, "runs": 1}))


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
    packages = [name for name in ("colony_lab", "colony_pilot", "colony_trust") if (ROOT / name).is_dir()]
    assert {"colony_lab", "colony_pilot"} <= set(packages)  # colony_trust is checked once it is merged
    for package in packages:
        paths = list((ROOT / package).rglob("*.py"))
        assert paths, package
        for path in paths:
            assert not any(name.startswith("colony_registrar") for name in _imports(path)), path
    assert all(not t.module.startswith("colony_registrar") for t in sup.TASKS.values())
    allowed = {"__future__", "copy", "threading", "fcntl", "hashlib", "stat", "json", "os", "contextlib", "pathlib", "typing", "colony_lab"}
    for path in (ROOT / "colony_registrar").rglob("*.py"):
        assert all(name in allowed or name.startswith("colony_lab.") for name in _imports(path)), path


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


# ── Third review: guards for the remaining contract rules ───────────────
def test_a_run_in_progress_holds_its_slot(colony, monkeypatch):
    c = colony()
    started, release, calls = threading.Event(), threading.Event(), []
    run = c.lab.run

    def slow_first(agent_id, task):
        calls.append(agent_id)
        if len(calls) == 1:
            started.set()
            release.wait(10)
        return run(agent_id, task)
    monkeypatch.setattr(c.lab, "run", slow_first)
    outcome = {}
    worker = threading.Thread(target=lambda: outcome.update(c.registrar.run(c.founder["agent_id"], {})))
    worker.start()
    try:
        assert started.wait(10)
        _refused("CONCURRENCY_LIMIT", lambda: c.registrar.run(c.founder["agent_id"], {}))
    finally:
        release.set()
        worker.join(10)
    assert outcome["agent_id"] == c.founder["agent_id"] and len(calls) == 1
    assert c.registrar.run(c.founder["agent_id"], {})["agent_id"] == c.founder["agent_id"]


def test_an_ancestor_admitted_by_a_sibling_is_refused(colony):
    """The admitter of an ancestor is outside the whole colony, not only outside that ancestor's line."""
    c = colony()
    child = c.birth(c.founder["agent_id"], "child_01")
    sibling = c.birth(c.founder["agent_id"], "child_02")
    path = c.lab.root / reg.ADMISSIONS / f"{child['agent_id']}.json"
    admission = json.loads(path.read_text())
    path.write_text(json.dumps({**admission, "admitter_id": "fixture-" + sibling["agent_id"][:16]}))
    _refused("ANCESTOR_NOT_ADMITTED", lambda: c.birth(child["agent_id"], "grandchild_01"))


def test_an_altered_policy_file_does_not_load_under_the_g0_pin(tmp_path, monkeypatch):
    altered = json.loads(reg.POLICY_FILE.read_text())
    altered["max_population"] = 64
    altered["admissible_parent_criteria_sha256"] = sorted([*altered["admissible_parent_criteria_sha256"], "1" * 64])
    copy_of_g0 = tmp_path / "POLICY_G0.json"
    copy_of_g0.write_text(json.dumps(altered))
    monkeypatch.setattr(reg, "POLICY_FILE", copy_of_g0)
    _refused("POLICY_PIN_MISMATCH", reg.load_policy)
    lab = sup.Supervisor(builders.lab_root(tmp_path), missions=frozenset({MISSION}))
    _refused("POLICY_PIN_MISMATCH", lambda: reg.Registrar(lab))
