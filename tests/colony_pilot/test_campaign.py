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
