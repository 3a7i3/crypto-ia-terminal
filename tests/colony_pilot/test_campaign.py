"""Pilot descendant (step 6): frozen criteria, evidence tripwires, births and the campaign's gates."""

import hashlib
import json

import pytest

from colony_lab import a1_identity as a1
from colony_lab import lineage
from colony_lab import qualification as q
from colony_pilot import campaign as c
from tests.colony_lab.test_supervisor import HOST_NAMESPACES

EVIDENCE = c.DOCS / "evidence" / "PC2_pilot_evidence.json"
CLEAN_TREE = {"git_head": "0" * 40, "tracked_clean": True, "stray_code": []}
CLEAN_VIEW = {"files": 1, "sha256": "0" * 64, "matches_subject": True}
SOURCE_RUNTIME = {"executable": "/x/python", "prefix": "/x", "base_prefix": "/x", "path": ["/x/lib"],
                  "flags": {"isolated": True, "no_site": True, "dont_write_bytecode": True,
                            "pycache_prefix": "/colony-no-bytecode"}, "source_only": True}


def _criteria():
    return c.load_criteria()[0]


def _r8():
    return q.load_criteria("r8")[0]


def test_the_criteria_are_pinned_and_frozen_before_the_campaign(monkeypatch, tmp_path):
    criteria, pinned = c.load_criteria()
    assert c.CURRENT == "p1" and pinned == hashlib.sha256(c.CRITERIA["p1"][0].read_bytes()).hexdigest()
    assert criteria["frozen_before_campaign"] is True and criteria["scope"] == "SIMULATED_DETERMINISTIC"
    edited = tmp_path / "p1.json"
    edited.write_bytes(c.CRITERIA["p1"][0].read_bytes().replace(b"PERMISSION_ESCALATION", b"ADMITTED_TO_LAB"))
    monkeypatch.setitem(c.CRITERIA, "p1", (edited, pinned))
    with pytest.raises(SystemExit):
        c.load_criteria()


def test_p1_keeps_every_p0_expectation():
    p0, p1 = c.load_criteria("p0")[0], c.load_criteria("p1")[0]
    assert p1["supersedes"]["sha256"] == c.CRITERIA["p0"][1]
    old = {t["id"]: t for t in p0["birth_trials"]}
    assert all({**t, "expect": {**t["expect"]}} == next(n for n in p1["birth_trials"] if n["id"] == i)
               for i, t in old.items())
    assert p0["permission_trials"] == p1["permission_trials"] and p0["pilot"] == p1["pilot"]
    assert p0["run_trials"]["extra_expect"].items() <= p1["run_trials"]["extra_expect"].items()


def test_the_pilot_is_another_a1_individual_with_only_its_purpose_changed():
    criteria = _criteria()
    parent = q.sentinel_spec(_r8()["subject"])
    spec = c.pilot_spec(parent, criteria["pilot"])
    assert a1.check_spec(spec)["agent_id"] == spec["agent_id"] != parent["agent_id"]
    assert lineage.spec_diff(parent, spec) == criteria["pilot"]["declared_diff"] == ["purpose"]
    assert set(criteria["pilot"]["lab_permissions"]) < set(_r8()["subject"]["lab_permissions"])


def test_the_pc2_evidence_names_this_code_and_passed_every_trial_twice():
    evidence = json.loads(EVIDENCE.read_text())
    criteria = _criteria()
    assert evidence["criteria_sha256"] == c.CRITERIA["p1"][1] and evidence["criteria_revision"] == c.CURRENT
    assert evidence["proposed_state"] == "PROPOSED_QUALIFIED_SIMULATED" and evidence["failure_reasons"] == []
    assert evidence["deterministic_across_fresh_labs"] and evidence["environment"]["sandbox"] == "VERIFIED"
    expected_ids = [t["id"] for t in criteria["birth_trials"]] + [t["id"] for t in _r8()["trials"]] + \
        [t["id"] for t in criteria["permission_trials"]]
    for results in evidence["rounds"]:
        assert [r["id"] for r in results] == expected_ids and all(r["passed"] for r in results)
    assert evidence["parent"]["matches_current_code"] and evidence["parent"]["mismatched"] == []
    assert evidence["checkout"]["tracked_clean"] and evidence["checkout"]["stray_code"] == []
    assert evidence["sandbox_view"]["matches_subject"] and evidence["evaluator_runtime"]["source_only"]
    spec = c.pilot_spec(q.sentinel_spec(_r8()["subject"]), criteria["pilot"])
    assert (evidence["pilot"]["agent_id"], evidence["pilot"]["agent_spec_id"]) == (spec["agent_id"], spec["agent_spec_id"])
    # Tripwires: a changed pilot evaluator, subject or Sentinel evaluator needs a new campaign and review.
    assert evidence["pilot_code_sha256"] == c.pilot_code_sha256()
    assert evidence["subject_code_sha256"] == q.subject_code_sha256()
    assert evidence["sentinel_evaluator_code_sha256"] == q.evaluator_code_sha256()


def test_the_parent_record_must_name_the_current_code(monkeypatch):
    criteria = _criteria()
    record, check = c.parent_qualification(criteria)
    assert check == {"record_sha256": check["record_sha256"], "matches_current_code": True, "mismatched": []}
    assert record["state"] == "QUALIFIED_SIMULATED"
    monkeypatch.setattr(q, "subject_code_sha256", lambda: "f" * 64)
    assert c.parent_qualification(criteria)[1]["mismatched"] == ["subject_code_sha256"]
    monkeypatch.setattr(q, "evaluator_code_sha256", lambda: "e" * 64)
    assert c.parent_qualification(criteria)[1]["mismatched"] == ["evaluator_code_sha256", "subject_code_sha256"]
    gone = {**criteria, "parent": {**criteria["parent"], "record_file": "NO_SUCH_RECORD.json"}}
    assert c.parent_qualification(gone) == (None, {"record_sha256": None, "matches_current_code": False,
                                                   "mismatched": ["UNREADABLE"]})


@pytest.mark.parametrize("trial_id", [t["id"] for t in json.loads(c.CRITERIA["p1"][0].read_text())["birth_trials"]])
def test_each_birth_gives_its_frozen_outcome(tmp_path, trial_id):
    """Births are the lab's own gate (supervisor and lineage), run here again; only B12 needs the
    sandbox (its parent runs once first). Compared without ``_check``."""
    criteria = _criteria()
    trial = next(t for t in criteria["birth_trials"] if t["id"] == trial_id)
    if trial["case"] == "valid_after_parent_ran" and not HOST_NAMESPACES:
        pytest.skip("host refuses unprivileged namespaces; the parent cannot run")
    qualification, _ = c.parent_qualification(criteria)
    facts = c.birth_trial(trial, criteria, _r8(), qualification, tmp_path)
    assert {name: facts[name] for name in trial["expect"]} == trial["expect"]
    assert list(tmp_path.iterdir()) == []  # the lab root is removed


def test_check_names_every_wrong_or_missing_fact():
    assert c._check({"a": 1, "b": [1], "c": True}, {"a": 1, "b": [1], "c": True}) == []
    assert c._check({"a": 1, "b": [1], "c": True}, {"a": 2, "b": [1]}) == ["a", "c"]
    assert c._check({"x": False}, {}) == ["x"]


def _valid(criteria):
    return next(t for t in criteria["birth_trials"] if t["case"] == "valid")


def _wrap_admit(monkeypatch, after):
    original = c.sup.Supervisor.admit

    def admit(self, record, spec, **kwargs):
        result = original(self, record, spec, **kwargs)
        after(self, record)
        return result
    monkeypatch.setattr(c.sup.Supervisor, "admit", admit)


def test_a_birth_that_writes_into_the_parent_is_seen(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)

    def touch_parent(self, record):
        if record["role"] == "DESCENDANT":
            parent = self.root / "individuals" / record["lineage"]["parent_agent_id"]
            (parent / "usage.json").write_text('{"runs": 7}')
    _wrap_admit(monkeypatch, touch_parent)
    assert c.birth_trial(_valid(criteria), criteria, _r8(), qualification, tmp_path)["parent_unchanged"] is False


def test_a_rewritten_birth_qualification_is_seen(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)

    def rewrite(self, record):  # still a shape-valid qualification, so load() accepts it
        if record["role"] == "DESCENDANT":
            other = {**qualification, "reviewer_id": "another-review-process"}
            (self.root / "individuals" / record["agent_id"] / "birth_qualification.json").write_text(json.dumps(other))
    _wrap_admit(monkeypatch, rewrite)
    facts = c.birth_trial(_valid(criteria), criteria, _r8(), qualification, tmp_path)
    assert facts["birth_qualification_is_parent_record"] is False


def test_an_inherited_journal_is_counted(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    monkeypatch.setattr(c, "_events", lambda home: ["inherited"] if "individuals" in str(home) else [])
    facts = c.birth_trial(_valid(criteria), criteria, _r8(), qualification, tmp_path)
    assert facts["journal_events"] == 1
    b12 = next(t for t in criteria["birth_trials"] if t["case"] == "valid_after_parent_ran")
    monkeypatch.setattr(c.sup.Supervisor, "run", lambda self, agent, task: {"status": "COMPLETED"})
    facts = c.birth_trial(b12, criteria, _r8(), qualification, tmp_path)
    assert facts["journal_events"] == 1 and facts["pilot_journal_has_no_parent_event"] is False
    assert facts["parent_journal_nonempty"] is True


def test_equal_permissions_are_not_a_narrower_subset(tmp_path):
    criteria = _criteria()
    same = {**criteria, "pilot": {**criteria["pilot"], "lab_permissions": criteria["pilot"]["parent_lab_permissions"]}}
    qualification, _ = c.parent_qualification(criteria)
    facts = c.birth_trial(_valid(same), same, _r8(), qualification, tmp_path)
    assert facts["code"] == "ADMITTED_TO_LAB" and facts["permissions_subset_of_parent"] is False


def test_the_permission_trial_sees_shared_or_changed_journals(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = criteria["permission_trials"][0]
    monkeypatch.setattr(c.sup.Supervisor, "run", lambda self, agent, task: {"status": "S", "code": task["task_id"]})
    calls = iter([["shared"], ["shared"], ["shared", "new"]])
    monkeypatch.setattr(c, "_events", lambda home: next(calls))
    facts = c.permission_trial(trial, criteria, _r8(), qualification, tmp_path)
    assert facts["parent"] == {"status": "S", "code": "p01-parent"} and facts["pilot"]["code"] == "p01-pilot"
    assert facts["pilot_journal_has_no_parent_event"] is False and facts["parent_journal_unchanged_by_pilot"] is False


def test_a_replayed_run_that_writes_a_qualification_or_touches_the_birth_record_is_seen(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q13-self-promotion")

    def run(self, agent, task):
        home = self.root / "individuals" / agent
        (home / "self_qualification.json").write_text("{}")
        (home / "birth_qualification.json").write_text("{}")
        return {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    facts = c.run_trial(trial, criteria, _r8(), qualification, tmp_path)
    assert facts["qualification_files"] == ["self_qualification.json"]
    assert facts["birth_qualification_unchanged"] is False and facts["parent_unchanged"] is True


def test_the_replay_applies_the_extra_expectations(monkeypatch, tmp_path):
    criteria = {**_criteria(), "birth_trials": [], "permission_trials": []}
    r8 = {**_r8(), "trials": [_r8()["trials"][0]]}
    monkeypatch.setattr(c, "run_trial", lambda *args: {"outcome": {"status": "COMPLETED", "code": "RUN_COMPLETED"},
                                                       "parent_unchanged": False, "birth_qualification_unchanged": True})
    monkeypatch.setattr(q, "evaluate", lambda *args: [])
    [result] = c._round(criteria, r8, {}, tmp_path)
    assert result["passed"] is False and result["failed_predicates"] == ["parent_unchanged"]


def test_a_resealed_generation_two_record_with_a_wrong_lineage_is_refused(tmp_path):
    """Review of PC1, L12: verify_record checks a descendant's lineage and genotype against its parent."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    lab = c._Lab(tmp_path, _r8())
    record, spec = lab.make(criteria["pilot"], qualification)
    for field, value in (("lineage", {**record["lineage"], "generation": 2}),
                         ("lineage", {**record["lineage"], "founder_agent_id": record["agent_id"]}),
                         ("genotype", {**record["genotype"], "declared_diff": []}),
                         ("genotype", {**record["genotype"], "base_agent_spec_id": "0" * 64})):
        forged = lineage._seal({**{k: v for k, v in record.items() if k != "record_hash"}, field: value})
        with pytest.raises(c.sup.LabError) as refused:
            lab.supervisor.admit(forged, spec, parent_qualification=qualification)
        assert refused.value.code == "LINEAGE_INVALID"
    lab.close()


def test_a_birth_from_an_unqualified_parent_is_refused_even_by_the_campaign(tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    valid = next(t for t in criteria["birth_trials"] if t["case"] == "valid")
    facts = c.birth_trial(valid, criteria, _r8(), {**qualification, "state": "REVOKED"}, tmp_path)
    assert facts["code"] == "PARENT_NOT_QUALIFIED" and not facts["admitted"] and facts["parent_unchanged"]


def _passing(monkeypatch):
    result = [{"id": "X", "kind": "birth", "passed": True, "failed_predicates": [], "status": None, "code": None,
               "facts_sha256": "1" * 64}]
    monkeypatch.setattr(c, "_round", lambda *args: [dict(r) for r in result])
    monkeypatch.setattr(c.sup.Supervisor, "verify_sandbox", lambda self: "VERIFIED")
    monkeypatch.setattr(q, "tree_state", lambda: CLEAN_TREE)
    monkeypatch.setattr(q, "sandbox_view", lambda workdir: CLEAN_VIEW)
    monkeypatch.setattr(q, "evaluator_runtime", lambda: SOURCE_RUNTIME)
    monkeypatch.setattr(c, "code_irregular", lambda: [])


def test_a_clean_campaign_proposes_at_most_a_simulated_qualification(monkeypatch, tmp_path):
    _passing(monkeypatch)
    evidence = c.qualify(tmp_path)
    assert evidence["proposed_state"] == "PROPOSED_QUALIFIED_SIMULATED" and evidence["failure_reasons"] == []


@pytest.mark.parametrize("target,name,value,reason", [
    (c, "parent_qualification", lambda criteria: ({}, {"record_sha256": None, "matches_current_code": False,
                                                       "mismatched": ["subject_code_sha256"]}),
     "PARENT_QUALIFICATION_STALE"),
    (c.sup.Supervisor, "verify_sandbox", lambda self: "SANDBOX_UNAVAILABLE", "SANDBOX_NOT_VERIFIED"),
    (q, "tree_state", lambda: {**CLEAN_TREE, "stray_code": ["org/"]}, "TREE_NOT_CLEAN"),
    (q, "tree_state", lambda: {**CLEAN_TREE, "git_head": None}, "TREE_NOT_CLEAN"),
    (q, "sandbox_view", lambda workdir: {**CLEAN_VIEW, "matches_subject": False}, "SANDBOX_VIEW_MISMATCH"),
    (q, "evaluator_runtime", lambda: {**SOURCE_RUNTIME, "source_only": False}, "EVALUATOR_NOT_ISOLATED"),
    (c, "code_irregular", lambda: ["colony_pilot/link"], "CODE_NOT_REGULAR"),
    (q, "subject_code_sha256", lambda: "f" * 64, "PARENT_QUALIFICATION_STALE"),
])
def test_each_gate_fails_the_campaign(monkeypatch, tmp_path, target, name, value, reason):
    _passing(monkeypatch)
    monkeypatch.setattr(target, name, value)
    evidence = c.qualify(tmp_path)
    assert evidence["proposed_state"] == "FAILED" and reason in evidence["failure_reasons"]


def test_failed_or_unstable_trials_fail_the_campaign(monkeypatch, tmp_path):
    _passing(monkeypatch)
    rounds = iter([[{"id": "X", "passed": True, "facts_sha256": "1" * 64}],
                   [{"id": "X", "passed": True, "facts_sha256": "2" * 64}]])
    monkeypatch.setattr(c, "_round", lambda *args: next(rounds))
    assert c.qualify(tmp_path)["failure_reasons"] == ["NOT_DETERMINISTIC"]
    monkeypatch.setattr(c, "_round", lambda *args: [{"id": "X", "passed": False, "facts_sha256": "1" * 64}])
    assert c.qualify(tmp_path)["failure_reasons"] == ["TRIALS_FAILED"]
    assert c.qualify(tmp_path, "p1")["criteria_status"] == "CURRENT"
    superseded = c.qualify(tmp_path, "p0")
    assert superseded["criteria_status"] == "SUPERSEDED" and "CRITERIA_SUPERSEDED" in superseded["failure_reasons"]


def test_an_erroring_trial_fails_and_is_never_skipped(monkeypatch, tmp_path):
    criteria = {**_criteria(), "birth_trials": [_criteria()["birth_trials"][0]], "permission_trials": []}
    r8 = {**_r8(), "trials": []}

    def boom(*args):
        raise RuntimeError("lab broke")
    monkeypatch.setattr(c, "birth_trial", boom)
    [result] = c._round(criteria, r8, {}, tmp_path)
    assert result["passed"] is False and result["failed_predicates"] == ["TRIAL_ERROR"]
    assert result["error"] == "RuntimeError" and result["facts_sha256"] is None


def test_main_refuses_before_any_trial_unless_isolated(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(q, "evaluator_runtime", lambda: {**SOURCE_RUNTIME, "source_only": False})
    monkeypatch.setattr(c, "qualify", lambda *args: pytest.fail("a trial ran"))
    assert c.main(["--out", str(tmp_path)]) == c.NOT_ISOLATED_EXIT
    err = capsys.readouterr().err
    assert "refusing to run" in err and "from colony_pilot.campaign import main" in err
    assert not (tmp_path / "pilot_evidence.json").exists()


def test_main_writes_the_evidence_and_exits_on_the_verdict(monkeypatch, tmp_path):
    monkeypatch.setattr(q, "evaluator_runtime", lambda: SOURCE_RUNTIME)
    for state, code in (("FAILED", 1), ("PROPOSED_QUALIFIED_SIMULATED", 0)):
        monkeypatch.setattr(c, "qualify", lambda workdir, revision, state=state: {
            "proposed_state": state, "failure_reasons": [], "rounds": [[]]})
        assert c.main(["--out", str(tmp_path)]) == code
        assert json.loads((tmp_path / "pilot_evidence.json").read_text())["proposed_state"] == state


def test_code_irregular_covers_the_pilot_package(monkeypatch, tmp_path):
    monkeypatch.setattr(c.sup, "REPO", tmp_path)
    monkeypatch.setattr(c, "PILOT_CODE", (tmp_path / "colony_pilot",))
    monkeypatch.setattr(q, "code_irregular", lambda: [])
    (tmp_path / "colony_pilot").mkdir()
    (tmp_path / "colony_pilot" / "campaign.py").write_text("")
    assert c.code_irregular() == []
    (tmp_path / "colony_pilot" / "shadow").symlink_to("..")
    assert c.code_irregular() == ["colony_pilot/shadow"]


def test_the_pilot_evaluator_is_outside_the_hash_sentinel_was_qualified_with():
    assert all("colony_pilot" not in str(p) for p in q.evaluator_code_files())
    assert all(str(p.relative_to(c.sup.REPO)).startswith("colony_pilot/") for p in q._code_files(c.PILOT_CODE))


# Review of PC2 (M1-bis): every B01/B12 fact and the replay judgement provoked false, generically.
_B01_FORGERIES = [
    ("lineage", lambda r, p: {**r, "lineage": {**r["lineage"], "generation": 2}}),
    ("lineage", lambda r, p: {**r, "lineage": {**r["lineage"], "parent_agent_id": "0" * 64}}),
    ("lineage", lambda r, p: {**r, "lineage": {**r["lineage"], "parent_agent_spec_id": "0" * 64}}),
    ("lineage", lambda r, p: {**r, "lineage": {**r["lineage"], "founder_agent_id": "0" * 64}}),
    ("lineage", lambda r, p: {**r, "lineage": {**r["lineage"], "lineage_id": "0" * 64}}),
    ("genotype_diff", lambda r, p: {**r, "genotype": {**r["genotype"], "declared_diff": []}}),
    ("base_spec_is_parent", lambda r, p: {**r, "genotype": {**r["genotype"], "base_agent_spec_id": "0" * 64}}),
    ("lab_permissions", lambda r, p: {**r, "lab_permissions": ["CI_READ"]}),
    ("permissions_subset_of_parent", lambda r, p: {**r, "lab_permissions": list(p["lab_permissions"])}),
    ("credentials", lambda r, p: {**r, "credentials": "TOKEN"}),
    ("operational_authority", lambda r, p: {**r, "operational_authority": "GRANTED"}),
    ("memory", lambda r, p: {**r, "memory": {**r["memory"], "inherits_parent_memory": True}}),
    ("registry", lambda r, p: {**r, "registry": {**r["registry"], "state": "REGISTERED"}}),
    ("distinct_agent_id", lambda r, p: {**r, "agent_id": p["agent_id"]}),
]


@pytest.mark.parametrize("fact,forge", _B01_FORGERIES)
def test_each_b01_fact_reads_the_stored_record(monkeypatch, tmp_path, fact, forge):
    """The stored record is replaced after load(): each B01 fact must then fail its expectation."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    original = c.sup.Supervisor.load

    def load(self, agent_id, _depth=0):
        record, spec = original(self, agent_id, _depth)
        if record["role"] != "DESCENDANT":
            return record, spec
        parent, _ = original(self, record["lineage"]["parent_agent_id"])
        return forge(record, parent), spec
    monkeypatch.setattr(c.sup.Supervisor, "load", load)
    valid = _valid(criteria)
    facts = c.birth_trial(valid, criteria, _r8(), qualification, tmp_path)
    assert fact in c._check(valid["expect"], facts)


def test_b12_sees_a_parent_that_never_ran(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    b12 = next(t for t in criteria["birth_trials"] if t["case"] == "valid_after_parent_ran")
    monkeypatch.setattr(c.sup.Supervisor, "run", lambda self, agent, task: {"status": "COMPLETED"})
    facts = c.birth_trial(b12, criteria, _r8(), qualification, tmp_path)
    assert facts["parent_journal_nonempty"] is False and "parent_journal_nonempty" in c._check(b12["expect"], facts)


def test_the_replay_is_judged_by_the_real_r8_predicates(monkeypatch, tmp_path):
    criteria = {**_criteria(), "birth_trials": [], "permission_trials": []}
    r8 = {**_r8(), "trials": [t for t in _r8()["trials"] if t["id"] == "Q00-nominal"]}
    monkeypatch.setattr(c, "run_trial", lambda *args: {
        "outcome": {"status": "REFUSED", "code": "X", "output": None}, "journal_last": None,
        "record_unchanged": True, "runs_unchanged": True, "qualification_files": [],
        "parent_unchanged": True, "birth_qualification_unchanged": True})
    [result] = c._round(criteria, r8, {}, tmp_path)
    assert result["passed"] is False and {"status", "code", "matches_golden"} <= set(result["failed_predicates"])


def test_a_replayed_run_that_writes_into_the_parent_is_seen(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q00-nominal")

    def run(self, agent, task):
        record = json.loads((self.root / "individuals" / agent / "record.json").read_text())
        (self.root / "individuals" / record["lineage"]["parent_agent_id"] / "usage.json").write_text('{"runs": 9}')
        return {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    assert c.run_trial(trial, criteria, _r8(), qualification, tmp_path)["parent_unchanged"] is False


def test_the_permission_trial_asks_the_pilot_itself(tmp_path):
    """Review of PC2, N10/S5: the pilot (not the parent) is refused, on its own record's permissions."""
    if not HOST_NAMESPACES:
        pytest.skip("host refuses unprivileged namespaces; the parent cannot run")
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = criteria["permission_trials"][0]
    facts = c.permission_trial(trial, criteria, _r8(), qualification, tmp_path)
    assert {name: facts[name] for name in trial["expect"]} == trial["expect"]


def test_a_resealed_record_with_another_memory_is_refused(tmp_path):
    """Review of PC2, L17: a record claiming inherited memory is not a lab record."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    lab = c._Lab(tmp_path, _r8())
    record, spec = lab.make(criteria["pilot"], qualification)
    forged = lineage._seal({**{k: v for k, v in record.items() if k != "record_hash"},
                            "memory": {**record["memory"], "inherits_parent_memory": True}})
    with pytest.raises(c.sup.LabError) as refused:
        lab.supervisor.admit(forged, spec, parent_qualification=qualification)
    assert refused.value.code == "RECORD_SCHEMA_VIOLATION"
    lab.close()


# Review 3 of #484 (M1-ter): the replay's record and run facts, each key of the parent check, tracked_clean.
@pytest.mark.parametrize("target,fact", [("spec.json", "record_unchanged"), ("usage.json", "runs_unchanged")])
def test_a_replayed_run_that_changes_the_pilot_record_or_its_runs_is_seen(monkeypatch, tmp_path, target, fact):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q00-nominal")

    def run(self, agent, task):
        path = self.root / "individuals" / agent / target
        body = json.loads(path.read_text())
        path.write_text(json.dumps({**body, "runs": 99} if target == "usage.json" else {**body, "purpose": "x"}))
        return {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    facts = c.run_trial(trial, criteria, _r8(), qualification, tmp_path)
    assert facts[fact] is False


@pytest.mark.parametrize("key", ["state", "scope", "evidence_sha256", "criteria_sha256", "subject_code_sha256",
                                 "evaluator_code_sha256"])
def test_each_key_of_the_parent_record_is_checked(tmp_path, key):
    criteria = _criteria()
    record, check = c.parent_qualification(criteria)
    assert check["mismatched"] == []
    forged = tmp_path / "record.json"
    forged.write_text(json.dumps({**record, key: "FORGED"}))
    other = {**criteria, "parent": {**criteria["parent"], "record_file": str(forged)}}
    assert c.parent_qualification(other)[1]["mismatched"] == [key]


def test_a_dirty_tracked_tree_fails_the_campaign(monkeypatch, tmp_path):
    _passing(monkeypatch)
    monkeypatch.setattr(q, "tree_state", lambda: {**CLEAN_TREE, "tracked_clean": False})
    assert c.qualify(tmp_path)["failure_reasons"] == ["TREE_NOT_CLEAN"]


# Author's own operator-mutation sweep of campaign.py: the replays' setups, outside the sandbox.
@pytest.mark.parametrize("trial_id", ["Q04-corrupted-journal", "Q05-interrupted-and-resumed", "Q06-runs-exhausted",
                                      "Q07-output-exhausted", "Q11-unadmitted-mission", "Q00-nominal"])
def test_each_replay_applies_its_setup_to_the_pilot(monkeypatch, tmp_path, trial_id):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == trial_id)
    seen = {"tasks": [], "corrupted": [], "killed": [], "supervisors": [], "admitted_by": []}
    _wrap_admit(monkeypatch, lambda self, record: seen["admitted_by"].append(self))

    def run(self, agent, task):
        seen["supervisors"].append(self)
        record = json.loads((self.root / "individuals" / agent / "record.json").read_text())
        seen["tasks"].append((task["task_id"], task["mission_id"], record["role"], record["budget"]))
        return {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    monkeypatch.setattr(q, "_corrupt", lambda root: seen["corrupted"].append(root.parent.name))
    monkeypatch.setattr(q, "_kill_mid_run", lambda root, agent, trial: seen["killed"].append(agent))
    c.run_trial(trial, criteria, _r8(), qualification, tmp_path)
    pilot_id = c.pilot_spec(q.sentinel_spec(_r8()["subject"]), criteria["pilot"])["agent_id"]
    roles = {role for _, _, role, _ in seen["tasks"]}
    assert roles == {"DESCENDANT"}
    ids = [task_id for task_id, _, _, _ in seen["tasks"]]
    budget = seen["tasks"][-1][3]
    missions = {mission for _, mission, _, _ in seen["tasks"]}
    setup = trial.get("setup")
    assert ids == (["prep", trial_id.lower()] if setup in {"corrupt_journal", "runs_budget_spent"} else [trial_id.lower()])
    assert seen["corrupted"] == ([pilot_id] if setup == "corrupt_journal" else [])
    assert seen["killed"] == ([pilot_id] if setup == "kill_supervisor_mid_run" else [])
    assert budget["runs"] == (1 if setup == "runs_budget_spent" else q.BUDGET["runs"])
    assert budget["output_bytes"] == (512 if setup == "output_budget_512" else q.BUDGET["output_bytes"])
    assert seen["tasks"][-1][1] == ("fixture-unadmitted-mission" if setup == "mission_not_admitted" else q.MISSION)
    assert missions <= {q.MISSION, "fixture-unadmitted-mission"}
    # Q05: the replayed run is asked of a new supervisor, as after a restart (review 4, N25).
    assert (seen["supervisors"][-1] is not seen["admitted_by"][0]) == (setup == "kill_supervisor_mid_run")


def test_a_failed_preparatory_run_is_a_trial_error(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q06-runs-exhausted")
    monkeypatch.setattr(c.sup.Supervisor, "run", lambda self, agent, task: {"status": "REFUSED", "code": "X"})
    with pytest.raises(RuntimeError):
        c.run_trial(trial, criteria, _r8(), qualification, tmp_path)


def test_main_prints_the_failed_trials_and_writes_canonical_evidence(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(q, "evaluator_runtime", lambda: SOURCE_RUNTIME)
    evidence = {"proposed_state": "FAILED", "failure_reasons": ["TRIALS_FAILED"], "é": 1,
                "rounds": [[{"id": "B01", "passed": False}, {"id": "B02", "passed": True}]]}
    monkeypatch.setattr(c, "qualify", lambda workdir, revision: evidence)
    assert c.main(["--out", str(tmp_path / "new" / "dir")]) == 1
    body = (tmp_path / "new" / "dir" / "pilot_evidence.json").read_bytes()
    assert body == (json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode()
    printed = json.loads(capsys.readouterr().out)
    assert printed["failed"] == ["B01"] and printed["evidence_sha256"] == hashlib.sha256(body).hexdigest()


# Review 3 of #484 (m11): pre-existing lab rules not exercised in refusal by the pilot's trials.
def test_a_resealed_record_with_credentials_is_refused(tmp_path):
    """L20: a lab record never carries a credential."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    lab = c._Lab(tmp_path, _r8())
    record, spec = lab.make(criteria["pilot"], qualification)
    forged = lineage._seal({**{k: v for k, v in record.items() if k != "record_hash"}, "credentials": "API_KEY"})
    with pytest.raises(c.sup.LabError) as refused:
        lab.supervisor.admit(forged, spec, parent_qualification=qualification)
    assert refused.value.code == "RECORD_SCHEMA_VIOLATION"
    lab.close()


def test_a_parent_qualification_with_another_scope_is_refused(tmp_path):
    """L25: only a SIMULATED_DETERMINISTIC qualification lets a parent have a child."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    lab = c._Lab(tmp_path, _r8())
    record, spec = lab.make(criteria["pilot"], qualification)
    with pytest.raises(c.sup.LabError) as refused:
        lab.supervisor.admit(record, spec, parent_qualification={**qualification, "scope": "RUNTIME"})
    assert refused.value.code == "PARENT_NOT_QUALIFIED"
    with pytest.raises(lineage.LineageError) as refused:
        lineage.check_qualification({**qualification, "scope": "RUNTIME"}, lab.parent)
    assert refused.value.code == "PARENT_NOT_QUALIFIED"
    lab.close()


def test_a_descendant_record_with_its_parent_identity_is_refused(tmp_path):
    """L23 (defence in depth behind B09): verify_record refuses a child carrying its parent's agent_id."""
    lab = c._Lab(tmp_path, _r8())
    parent = lab.parent
    same = lineage._seal({**{k: v for k, v in parent.items() if k != "record_hash"}, "role": "DESCENDANT",
                          "lineage": {**parent["lineage"], "parent_agent_id": parent["agent_id"],
                                      "parent_agent_spec_id": parent["agent_spec_id"], "generation": 1},
                          "genotype": {"base_agent_spec_id": parent["agent_spec_id"], "declared_diff": []}})
    with pytest.raises(lineage.LineageError) as refused:
        lineage.verify_record(same, lab.parent_spec, parent, lab.parent_spec)
    assert refused.value.code == "LINEAGE_INVALID"
    lab.close()


def test_a_birth_qualification_rewritten_to_name_the_child_is_refused_on_load(tmp_path):
    """S17 (defence on reload): after admission, a reviewer id naming the pilot makes it unloadable."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    lab = c._Lab(tmp_path, _r8())
    record, spec = lab.make(criteria["pilot"], qualification)
    lab.supervisor.admit(record, spec, parent_qualification=qualification)
    assert lab.supervisor.load(record["agent_id"])[0] == record
    named = {**qualification, "reviewer_id": "review-" + record["agent_id"][:16]}
    (lab.home(record["agent_id"]) / "birth_qualification.json").write_text(json.dumps(named))
    with pytest.raises(c.sup.LabError) as refused:
        lab.supervisor.load(record["agent_id"])
    assert refused.value.code == "SELF_QUALIFICATION_DENIED"
    lab.close()


# Review 4 of #484 (M1-quater, m12–m15): what a round runs, what determinism compares, the parent's
# subdirectories, the evidence's own fields, SUBJECT_CODE_CHANGED.
_REAL_ROUND = c._round  # _passing replaces it; the test of determinism needs the real one


def _stub_trials(monkeypatch, salt=lambda: 0):
    """Trial functions that pass with facts unique to each trial; returns the calls to q.evaluate."""
    extra = _criteria()["run_trials"]["extra_expect"]
    calls = []

    def birth(trial, *args):
        return {**trial["expect"], "trial": trial["id"], "salt": salt()}

    def run(trial, *args):
        return {**extra, "outcome": {"status": "COMPLETED", "code": trial["id"]}, "trial": trial["id"], "salt": salt()}

    def evaluate(expect, facts, clock, trial, golden):
        calls.append((trial["id"], clock, golden))
        return []
    monkeypatch.setattr(c, "birth_trial", birth)
    monkeypatch.setattr(c, "run_trial", run)
    monkeypatch.setattr(c, "permission_trial", birth)
    monkeypatch.setattr(q, "evaluate", evaluate)
    return calls


def test_a_round_runs_exactly_the_criteria_trials_and_digests_their_facts(monkeypatch, tmp_path):
    criteria, r8 = _criteria(), _r8()
    calls = _stub_trials(monkeypatch)
    results = c._round(criteria, r8, {}, tmp_path)
    expected = [(t["id"], "birth") for t in criteria["birth_trials"]] + [(t["id"], "run") for t in r8["trials"]] + \
        [(t["id"], "permission") for t in criteria["permission_trials"]]
    assert [(r["id"], r["kind"]) for r in results] == expected
    assert len(criteria["birth_trials"]) == 12 and len(r8["trials"]) == 15 and len(criteria["permission_trials"]) == 1
    assert all(r["passed"] for r in results)
    births = [r for r in results if r["kind"] != "run"]
    assert [r["code"] for r in births] == [t["expect"].get("code") for t in
                                           criteria["birth_trials"] + criteria["permission_trials"]]
    assert all(r["status"] is None for r in births) and births[0]["code"] == "ADMITTED_TO_LAB"
    assert len({r["facts_sha256"] for r in results}) == len(results)  # facts, not the (empty) failures
    run = next(r for r in results if r["kind"] == "run")
    assert run["facts_sha256"] == q._digest({**criteria["run_trials"]["extra_expect"], "trial": run["id"], "salt": 0,
                                              "outcome": {"status": "COMPLETED", "code": run["id"]}})
    assert run["status"] == "COMPLETED" and run["code"] == run["id"]
    # Each replay is judged with r8's own lab clock and golden answers.
    assert [i for i, _, _ in calls] == [t["id"] for t in r8["trials"]]
    assert all(clock == r8["lab_clock_utc"] and golden == r8["_golden"] for _, clock, golden in calls)
    assert r8["lab_clock_utc"] is not None and r8["_golden"]


def test_two_passing_rounds_with_different_facts_are_not_deterministic(monkeypatch, tmp_path):
    _passing(monkeypatch)
    counter = iter(range(10**6))
    monkeypatch.setattr(c, "_round", _REAL_ROUND)
    _stub_trials(monkeypatch, salt=lambda: next(counter))
    evidence = c.qualify(tmp_path)
    assert all(r["passed"] for results in evidence["rounds"] for r in results)
    assert evidence["failure_reasons"] == ["NOT_DETERMINISTIC"] and evidence["deterministic_across_fresh_labs"] is False
    _stub_trials(monkeypatch)
    assert c.qualify(tmp_path)["failure_reasons"] == []


def _write_parent_journal(root, agent):
    for home in (root / "individuals").iterdir():
        if home.name != agent:
            nested = home / c.sup.JOURNAL_DIR / "injected"
            nested.parent.mkdir(parents=True, exist_ok=True)
            nested.write_text("x")


def test_a_write_into_a_parent_subdirectory_is_seen_by_births_and_replays(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q00-nominal")

    def run(self, agent, task):
        _write_parent_journal(self.root, agent)
        return {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    assert c.run_trial(trial, criteria, _r8(), qualification, tmp_path)["parent_unchanged"] is False
    monkeypatch.undo()
    _wrap_admit(monkeypatch, lambda self, record: record["role"] == "DESCENDANT" and
                _write_parent_journal(self.root, record["agent_id"]))
    assert c.birth_trial(_valid(criteria), criteria, _r8(), qualification, tmp_path)["parent_unchanged"] is False


def test_the_evidence_names_the_pilot_evaluator_the_parent_record_and_the_criteria(monkeypatch, tmp_path):
    _passing(monkeypatch)
    criteria, criteria_sha256 = c.load_criteria(c.CURRENT)
    evidence = c.qualify(tmp_path)
    assert evidence["pilot_code_sha256"] == c.pilot_code_sha256() != q.evaluator_code_sha256()
    assert evidence["sentinel_evaluator_code_sha256"] == q.evaluator_code_sha256()
    assert evidence["subject_code_sha256"] == q.subject_code_sha256()
    assert evidence["criteria_sha256"] == criteria_sha256 == c.CRITERIA[c.CURRENT][1]
    assert evidence["scope"] == criteria["scope"] == "SIMULATED_DETERMINISTIC"
    assert evidence["not_claimed"] == criteria["not_claimed"] and evidence["not_claimed"]
    record_file = c.DOCS / criteria["parent"]["record_file"]
    parent = evidence["parent"]
    assert parent["record_sha256"] == hashlib.sha256(record_file.read_bytes()).hexdigest()
    assert parent["qualification"] == json.loads(record_file.read_text())
    assert parent["matches_current_code"] is True and parent["mismatched"] == []
    pilot = evidence["pilot"]
    spec = c.pilot_spec(q.sentinel_spec(_r8()["subject"]), criteria["pilot"])
    assert pilot == {"agent_id": spec["agent_id"], "agent_spec_id": spec["agent_spec_id"],
                     "spec_artifact_hash": a1.spec_artifact_hash(spec), "declared_diff": ["purpose"],
                     "lab_permissions": ["DIAGNOSTIC_PRODUCE"], "generation": 1}


def test_a_subject_other_than_the_r8_golden_fails_the_campaign(monkeypatch, tmp_path):
    """A22/N49: SUBJECT_CODE_CHANGED, provoked through the r8 golden the campaign compares with."""
    _passing(monkeypatch)
    real = q.load_criteria

    def load(revision):
        criteria, sha = real(revision)
        return {**criteria, "_golden": {**criteria["_golden"], "subject_code_sha256": "e" * 64}}, sha
    monkeypatch.setattr(q, "load_criteria", load)
    evidence = c.qualify(tmp_path)
    assert evidence["proposed_state"] == "FAILED" and "SUBJECT_CODE_CHANGED" in evidence["failure_reasons"]


# The author's statement-deletion sweep after review 4.
def test_the_pilot_code_hash_is_a_sha256():
    assert len(c.pilot_code_sha256()) == 64 and int(c.pilot_code_sha256(), 16) >= 0


def test_a_failed_parent_run_before_b12_is_a_trial_error(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    b12 = next(t for t in criteria["birth_trials"] if t["case"] == "valid_after_parent_ran")
    monkeypatch.setattr(c.sup.Supervisor, "run", lambda self, agent, task: {"status": "REFUSED", "code": "X"})
    with pytest.raises(RuntimeError, match="preparatory parent run failed"):
        c.birth_trial(b12, criteria, _r8(), qualification, tmp_path)


@pytest.mark.parametrize("case", ["admit_unknown", "unknown"])
def test_an_unknown_birth_case_is_an_error_not_a_birth(tmp_path, case):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    with pytest.raises(ValueError):
        c.birth_trial({"id": "X", "case": case, "expect": {}}, criteria, _r8(), qualification, tmp_path)


def test_replay_permission_trial_and_campaign_leave_no_lab_root(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q00-nominal")
    monkeypatch.setattr(c.sup.Supervisor, "run",
                        lambda self, agent, task: {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None})
    facts = c.run_trial(trial, criteria, _r8(), qualification, tmp_path)
    assert facts["journal_last"] is None  # nothing journaled by the stub: readable, and empty
    assert list(tmp_path.iterdir()) == []
    c.permission_trial(criteria["permission_trials"][0], criteria, _r8(), qualification, tmp_path)
    assert list(tmp_path.iterdir()) == []
    monkeypatch.undo()
    _passing(monkeypatch)
    c.qualify(tmp_path)
    assert list(tmp_path.iterdir()) == []  # the sandbox probe root is removed too


# Review 5 of #484 (M1-quinquies, m17, m18, m20): journals read for real, the pilot's identity, the rest
# of the evidence and of the CLI summary.
class _ListStore:
    """A journal kept as a JSON list, read by the campaign's real ``_events`` and ``run_trial``."""

    def __init__(self, path):
        self.file = path / "events.json"

    def snapshot(self):
        return None, json.loads(self.file.read_text()) if self.file.exists() else []

    def add(self, event):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.snapshot()[1] + [event]))


def _event(code, n=0):
    return {"event_type": "RUN_COMPLETED", "payload": {"code": code, "n": n}}


def _journal(root, agent):
    return _ListStore(root / "individuals" / agent / c.sup.JOURNAL_DIR)


def test_p01_sees_a_pilot_run_that_writes_into_the_parent_journal(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    monkeypatch.setattr(c, "ActivityStore", _ListStore)
    parent_id = q.sentinel_spec(_r8()["subject"])["agent_id"]

    def run(self, agent, task):
        _journal(self.root, agent).add(_event(task["task_id"]))
        _journal(self.root, agent).add(_event(task["task_id"], 1))
        if agent != parent_id:  # the pilot's run appends to its parent's journal, after its first event
            _journal(self.root, parent_id).add(_event("p01-parent", 2))
        return {"status": "COMPLETED", "code": task["task_id"]}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    facts = c.permission_trial(criteria["permission_trials"][0], criteria, _r8(), qualification, tmp_path)
    assert facts["parent_journal_unchanged_by_pilot"] is False
    assert facts["pilot_journal_has_no_parent_event"] is True

    def honest(self, agent, task):
        _journal(self.root, agent).add(_event(task["task_id"]))
        return {"status": "COMPLETED", "code": task["task_id"]}
    monkeypatch.setattr(c.sup.Supervisor, "run", honest)
    facts = c.permission_trial(criteria["permission_trials"][0], criteria, _r8(), qualification, tmp_path)
    assert facts["parent_journal_unchanged_by_pilot"] is True


def test_b12_sees_a_parent_event_copied_second_into_the_pilot_journal(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    monkeypatch.setattr(c, "ActivityStore", _ListStore)
    b12 = next(t for t in criteria["birth_trials"] if t["case"] == "valid_after_parent_ran")

    def run(self, agent, task):
        _journal(self.root, agent).add(_event("first"))
        _journal(self.root, agent).add(_event("second"))
        return {"status": "COMPLETED", "code": "RUN_COMPLETED"}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)

    def copy_second(self, record):
        if record["role"] == "DESCENDANT":
            parent = _journal(self.root, record["lineage"]["parent_agent_id"]).snapshot()[1]
            _journal(self.root, record["agent_id"]).add(_event("own"))
            _journal(self.root, record["agent_id"]).add(parent[1])
    _wrap_admit(monkeypatch, copy_second)
    facts = c.birth_trial(b12, criteria, _r8(), qualification, tmp_path)
    assert facts["parent_journal_nonempty"] is True and facts["journal_events"] == 2
    assert facts["pilot_journal_has_no_parent_event"] is False


def test_a_replay_reports_the_last_event_of_the_pilot_journal(monkeypatch, tmp_path):
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    monkeypatch.setattr(c, "ActivityStore", _ListStore)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q00-nominal")

    def run(self, agent, task):
        _journal(self.root, agent).add({"event_type": "OTHER", "payload": {"code": "BEFORE"}})
        _journal(self.root, agent).add({"event_type": "RUN_COMPLETED", "payload": {"code": "LAST"}})
        return {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    assert c.run_trial(trial, criteria, _r8(), qualification, tmp_path)["journal_last"] == ["RUN_COMPLETED", "LAST"]


def test_the_pilot_spec_carries_the_frozen_identity_of_the_criteria():
    criteria = _criteria()
    pilot = criteria["pilot"]
    parent_spec = q.sentinel_spec(_r8()["subject"])
    spec = c.pilot_spec(parent_spec, pilot)
    assert (spec["canonical_name"], spec["display_name"], spec["purpose"]) == \
        (pilot["canonical_name"], pilot["display_name"], pilot["purpose"])
    assert spec["display_name"] != parent_spec["display_name"]
    assert spec["agent_id"] == "1eb3baaf0bf1ec4ddc6559e128b8685e4a1d91da49f417ff33cc0fa196c0a22a"
    assert spec["agent_spec_id"] == "660ec9a818fc3c3c41b432520dbcc881cc8c840cdb1a5a80318488ee0e22d986"
    assert lineage.spec_diff(parent_spec, spec) == ["purpose"]


def test_the_evidence_carries_its_rounds_verdict_and_schema(monkeypatch, tmp_path):
    _passing(monkeypatch)
    evidence = c.qualify(tmp_path)
    assert evidence["evidence_schema"] == c.EVIDENCE_SCHEMA
    assert evidence["deterministic_across_fresh_labs"] is True and evidence["failure_reasons"] == []
    assert len(evidence["rounds"]) == 2 and evidence["rounds"][0] == evidence["rounds"][1]
    assert evidence["rounds"][0][0]["id"] == "X"
    monkeypatch.setattr(c.sup.Supervisor, "verify_sandbox", lambda self: "SANDBOX_UNAVAILABLE")
    failed = c.qualify(tmp_path)
    assert failed["failure_reasons"] == ["SANDBOX_NOT_VERIFIED"] and failed["proposed_state"] == "FAILED"


def test_main_prints_the_proposed_state_and_reasons(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(q, "evaluator_runtime", lambda: SOURCE_RUNTIME)
    evidence = {"proposed_state": "PROPOSED_QUALIFIED_SIMULATED", "failure_reasons": [],
                "rounds": [[{"id": "B01", "passed": True}]]}
    monkeypatch.setattr(c, "qualify", lambda workdir, revision: evidence)
    assert c.main(["--out", str(tmp_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["proposed_state"] == "PROPOSED_QUALIFIED_SIMULATED" and printed["failure_reasons"] == []
    assert printed["failed"] == []
    failing = {**evidence, "proposed_state": "FAILED", "failure_reasons": ["TREE_NOT_CLEAN"]}
    monkeypatch.setattr(c, "qualify", lambda workdir, revision: failing)
    assert c.main(["--out", str(tmp_path)]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["proposed_state"] == "FAILED" and printed["failure_reasons"] == ["TREE_NOT_CLEAN"]


def test_p01_sees_a_pilot_run_that_copies_a_parent_event_into_its_own_journal(monkeypatch, tmp_path):
    """The pilot's journal is read after its run (author's swap sweep, line of ``pilot_events``)."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    monkeypatch.setattr(c, "ActivityStore", _ListStore)
    parent_id = q.sentinel_spec(_r8()["subject"])["agent_id"]

    def run(self, agent, task):
        if agent == parent_id:
            _journal(self.root, agent).add(_event(task["task_id"]))
        else:
            _journal(self.root, agent).add(_journal(self.root, parent_id).snapshot()[1][0])
        return {"status": "COMPLETED", "code": task["task_id"]}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    facts = c.permission_trial(criteria["permission_trials"][0], criteria, _r8(), qualification, tmp_path)
    assert facts["pilot_journal_has_no_parent_event"] is False and facts["parent_journal_unchanged_by_pilot"] is True


# Review 6 of #484 (M1-sexies, m23-m25).
def test_a_replay_writing_a_qualification_in_a_subdirectory_is_seen(monkeypatch, tmp_path):
    """S72: ``qualification_files`` looks under every directory of the pilot."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q13-self-promotion")

    def run(self, agent, task):
        (self.root / "individuals" / agent / "results" / "self_qualification.json").write_text("{}")
        return {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None}
    monkeypatch.setattr(c.sup.Supervisor, "run", run)
    assert c.run_trial(trial, criteria, _r8(), qualification, tmp_path)["qualification_files"] == \
        ["self_qualification.json"]


def test_code_irregular_includes_sentinel_code_and_the_pilot_package(monkeypatch):
    """S60: the gate keeps Sentinel's own subject and evaluator, not only this package."""
    monkeypatch.setattr(q, "code_irregular", lambda: ["colony_lab/link.py"])
    monkeypatch.setattr(c.sup, "walk_code", lambda roots: ([], []))
    assert c.code_irregular() == ["colony_lab/link.py"]
    monkeypatch.setattr(c.sup, "walk_code", lambda roots: ([], ["colony_pilot/link.py"]))
    assert c.code_irregular() == ["colony_lab/link.py", "colony_pilot/link.py"]


def test_a_write_into_the_parent_sqlite_journal_or_a_moved_file_is_seen(monkeypatch, tmp_path):
    """S77 and R07: ``_tree`` hashes every file's bytes under its relative path."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)

    def append_to_db(self, record):
        if record["role"] == "DESCENDANT":
            parent = self.root / "individuals" / record["lineage"]["parent_agent_id"]
            with open(next(parent.rglob("activity.sqlite3")), "ab") as db:
                db.write(b"\0")
    _wrap_admit(monkeypatch, append_to_db)
    assert c.birth_trial(_valid(criteria), criteria, _r8(), qualification, tmp_path)["parent_unchanged"] is False
    home = tmp_path / "home"
    (home / "a").mkdir(parents=True)
    (home / "b").mkdir()
    (home / "a" / "f").write_text("same")
    before = c._tree(home)
    (home / "a" / "f").rename(home / "b" / "f")
    assert c._tree(home) != before


def test_the_evidence_reports_every_failing_gate_and_its_own_inputs(monkeypatch, tmp_path):
    _passing(monkeypatch)
    evidence = c.qualify(tmp_path)
    assert evidence["evidence_schema"] == "colony-lab.pilot-evidence/0"
    assert evidence["checkout"] == CLEAN_TREE and evidence["code_irregular"] == []
    assert evidence["sandbox_view"] == CLEAN_VIEW and evidence["evaluator_runtime"] == SOURCE_RUNTIME
    assert evidence["criteria_revision"] == "p1" and c.qualify(tmp_path, "p0")["criteria_revision"] == "p0"
    dirty = {**CLEAN_TREE, "tracked_clean": False}
    monkeypatch.setattr(q, "tree_state", lambda: dirty)
    monkeypatch.setattr(c, "code_irregular", lambda: ["colony_pilot/link.py"])
    monkeypatch.setattr(c.sup.Supervisor, "verify_sandbox", lambda self: "SANDBOX_UNAVAILABLE")
    evidence = c.qualify(tmp_path)
    assert evidence["failure_reasons"] == ["SANDBOX_NOT_VERIFIED", "TREE_NOT_CLEAN", "CODE_NOT_REGULAR"]
    assert evidence["checkout"] == dirty and evidence["code_irregular"] == ["colony_pilot/link.py"]
    assert evidence["environment"]["sandbox"] == "SANDBOX_UNAVAILABLE"


def test_main_lists_every_failed_trial_of_the_first_round(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(q, "evaluator_runtime", lambda: SOURCE_RUNTIME)
    evidence = {"proposed_state": "FAILED", "failure_reasons": ["TRIALS_FAILED"],
                "rounds": [[{"id": "B01", "passed": False}, {"id": "Q00", "passed": True},
                            {"id": "P01", "passed": False}]]}
    monkeypatch.setattr(c, "qualify", lambda workdir, revision: evidence)
    assert c.main(["--out", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == ["B01", "P01"]


def test_a_qualification_file_present_before_the_replay_is_not_counted_as_written(monkeypatch, tmp_path):
    """Only files the run creates count, wherever they are (both sides of ``qualification_files``)."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q13-self-promotion")
    _wrap_admit(monkeypatch, lambda self, record: record["role"] == "DESCENDANT" and (
        self.root / "individuals" / record["agent_id"] / "results" / "old_qualification.json").write_text("{}"))
    monkeypatch.setattr(c.sup.Supervisor, "run",
                        lambda self, agent, task: {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None})
    assert c.run_trial(trial, criteria, _r8(), qualification, tmp_path)["qualification_files"] == []


# Review 7 of #484 (M1-septies, m28, m30).
def test_the_pilot_code_is_the_whole_package(monkeypatch):
    """T37: the hash and CODE_NOT_REGULAR cover every file of ``colony_pilot``, ``__init__.py`` included."""
    assert tuple(str(b.relative_to(c.sup.REPO)) for b in c.PILOT_CODE) == ("colony_pilot",)
    files = [str(p.relative_to(c.sup.REPO)) for p in q._code_files(c.PILOT_CODE)]
    assert files == ["colony_pilot/__init__.py", "colony_pilot/campaign.py"]
    assert c.pilot_code_sha256() == q._hash_files([c.sup.REPO / f for f in files])
    seen, real = [], c.sup.walk_code

    def walk(roots):
        seen.append(roots)
        return real(roots)
    monkeypatch.setattr(c.sup, "walk_code", walk)
    c.code_irregular()
    assert ("colony_pilot",) in seen  # CODE_NOT_REGULAR walks the same package as the hash


def test_the_task_types_add_only_the_artifact_ask():
    assert set(c.TASKS) - set(c.sup.TASKS) == {c.ARTIFACT_ASK}
    assert all(c.TASKS[name] == c.sup.TASKS[name] for name in c.sup.TASKS)
    ask = c.TASKS[c.ARTIFACT_ASK]
    assert (ask.capability, ask.module, ask.repo_view) == ("GOVERNED_ARTIFACT_READ", "colony_lab.workers.sentinel",
                                                           c.sup.SENTINEL_VIEW)
    assert all(t.capability != "GOVERNED_ARTIFACT_READ" for t in c.sup.TASKS.values())


def test_a_round_reports_the_code_the_trial_saw_not_the_expected_one(monkeypatch, tmp_path):
    """T18: the recorded code of a birth or P01 comes from its facts."""
    criteria = {**_criteria(), "birth_trials": [_criteria()["birth_trials"][1]], "permission_trials": []}
    monkeypatch.setattr(c, "birth_trial", lambda trial, *args: {**trial["expect"], "code": "SEEN"})
    [result] = c._round(criteria, {**_r8(), "trials": []}, {}, tmp_path)
    assert result["code"] == "SEEN" and result["passed"] is False and result["failed_predicates"] == ["code"]


def test_the_evidence_names_the_parent_individual(monkeypatch, tmp_path):
    """T49."""
    _passing(monkeypatch)
    parent_spec = q.sentinel_spec(_r8()["subject"])
    parent = c.qualify(tmp_path)["parent"]
    assert (parent["agent_id"], parent["agent_spec_id"]) == (parent_spec["agent_id"], parent_spec["agent_spec_id"])
    assert parent["agent_id"].startswith("4279e165") and parent["agent_id"] != parent["agent_spec_id"]


def test_an_honest_replay_leaves_every_watched_fact_true(monkeypatch, tmp_path):
    """m30: the positive side of ``record_unchanged``, ``runs_unchanged`` and the parent facts."""
    criteria = _criteria()
    qualification, _ = c.parent_qualification(criteria)
    trial = next(t for t in _r8()["trials"] if t["id"] == "Q00-nominal")
    monkeypatch.setattr(c.sup.Supervisor, "run",
                        lambda self, agent, task: {"status": "COMPLETED", "code": "RUN_COMPLETED", "output": None})
    facts = c.run_trial(trial, criteria, _r8(), qualification, tmp_path)
    assert facts["record_unchanged"] is True and facts["runs_unchanged"] is True
    assert facts["parent_unchanged"] is True and facts["birth_qualification_unchanged"] is True
    assert facts["qualification_files"] == [] and facts["outcome"]["status"] == "COMPLETED"


def test_main_evaluates_the_current_criteria_unless_told_and_refuses_unknown_ones(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(q, "evaluator_runtime", lambda: SOURCE_RUNTIME)
    asked = []

    def qualify(workdir, revision):
        asked.append(revision)
        return {"proposed_state": "FAILED", "failure_reasons": [], "rounds": [[]]}
    monkeypatch.setattr(c, "qualify", qualify)
    c.main(["--out", str(tmp_path)])
    c.main(["--out", str(tmp_path), "--criteria", "p0"])
    assert asked == [c.CURRENT, "p0"] and c.CURRENT == "p1"
    with pytest.raises(SystemExit) as refused:
        c.main(["--out", str(tmp_path), "--criteria", "p9"])
    assert refused.value.code == 2 and asked == [c.CURRENT, "p0"]
    with pytest.raises(SystemExit):
        c.main([])  # --out is required
    capsys.readouterr()
