"""Pilot descendant (step 6): frozen criteria, evidence tripwires, births and the campaign's gates."""

import hashlib
import json

import pytest

from colony_lab import a1_identity as a1
from colony_lab import lineage
from colony_lab import qualification as q
from colony_pilot import campaign as c

EVIDENCE = c.DOCS / "evidence" / "PC1_pilot_evidence.json"
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
    assert pinned == hashlib.sha256(c.CRITERIA["p0"][0].read_bytes()).hexdigest()
    assert criteria["frozen_before_campaign"] is True and criteria["scope"] == "SIMULATED_DETERMINISTIC"
    edited = tmp_path / "p0.json"
    edited.write_bytes(c.CRITERIA["p0"][0].read_bytes().replace(b"PERMISSION_ESCALATION", b"ADMITTED_TO_LAB"))
    monkeypatch.setitem(c.CRITERIA, "p0", (edited, pinned))
    with pytest.raises(SystemExit):
        c.load_criteria()


def test_the_pilot_is_another_a1_individual_with_only_its_purpose_changed():
    criteria = _criteria()
    parent = q.sentinel_spec(_r8()["subject"])
    spec = c.pilot_spec(parent, criteria["pilot"])
    assert a1.check_spec(spec)["agent_id"] == spec["agent_id"] != parent["agent_id"]
    assert lineage.spec_diff(parent, spec) == criteria["pilot"]["declared_diff"] == ["purpose"]
    assert set(criteria["pilot"]["lab_permissions"]) < set(_r8()["subject"]["lab_permissions"])


def test_the_pc1_evidence_names_this_code_and_passed_every_trial_twice():
    evidence = json.loads(EVIDENCE.read_text())
    criteria = _criteria()
    assert evidence["criteria_sha256"] == c.CRITERIA["p0"][1] and evidence["criteria_revision"] == c.CURRENT
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


@pytest.mark.parametrize("trial_id", [t["id"] for t in json.loads(c.CRITERIA["p0"][0].read_text())["birth_trials"]])
def test_each_birth_gives_its_frozen_outcome(tmp_path, trial_id):
    """Births need no sandbox: they are the lab's own gate (supervisor and lineage), run here again."""
    criteria = _criteria()
    trial = next(t for t in criteria["birth_trials"] if t["id"] == trial_id)
    qualification, _ = c.parent_qualification(criteria)
    facts = c.birth_trial(trial, criteria, _r8(), qualification, tmp_path)
    assert c._check(trial["expect"], facts) == []
    assert list(tmp_path.iterdir()) == []  # the lab root is removed


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
    assert c.qualify(tmp_path, "p0")["criteria_status"] == "CURRENT"


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
