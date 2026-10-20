"""The trial evaluator: frozen criteria, independent predicates, failures never hidden."""

import hashlib
import json

import pytest

from colony_lab import qualification as q
from tests.colony_lab.test_supervisor import HOST_NAMESPACES


def test_every_criteria_revision_is_pinned_and_r1_changes_no_expectation():
    for path, pinned in q.CRITERIA.values():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pinned
    r0, _ = q.load_criteria("r0")
    r1, _ = q.load_criteria("r1")
    assert r0["trials"] == r1["trials"] and r0["predicates"] == r1["predicates"]
    assert r1["revision"]["supersedes_sha256"] == q.CRITERIA["r0"][1]
    categories = {t["category"] for t in r1["trials"]}
    assert categories >= {"absent_source", "stale_source", "corrupted_journal", "interruption", "budget",
                          "malicious_content", "fake_governance_message", "mission_conflict",
                          "secret_read_attempt", "self_promotion"}


def test_recorded_campaigns_are_kept_with_their_verdicts():
    c1 = json.loads((q.DOCS / "evidence" / "C1_sentinel_evidence.json").read_text())
    c2 = json.loads((q.DOCS / "evidence" / "C2_sentinel_evidence.json").read_text())
    assert c1["proposed_state"] == "FAILED" and c1["criteria_sha256"] == q.CRITERIA["r0"][1]
    assert c2["proposed_state"] == "PROPOSED_QUALIFIED_SIMULATED" and c2["criteria_revision"] == "r1"
    assert c2["scope"] == "SIMULATED_DETERMINISTIC" and c2["environment"]["sandbox"] == "VERIFIED"


def _facts(**outcome):
    base = {"status": "COMPLETED", "code": "RUN_COMPLETED", "output_redactions": 0,
            "output": {"agent_id": "SENTINEL-01", "capability": "OBSERVE_ONLY", "operational_authority": "DENIED",
                       "sources": [{"source": "HOST", "availability": "AVAILABLE"}],
                       "tool_calls": [{"tool": "host.host_snapshot"}],
                       "answer": {"diagnostics": [], "refusals": []}}}
    base.update(outcome)
    return {"outcome": base, "journal_last": ["OBSERVATION_RECORDED", "RUN_COMPLETED"],
            "record_unchanged": True, "runs_unchanged": True, "qualification_files": []}


def test_evaluator_passes_a_matching_outcome():
    expect = {"status": "COMPLETED", "availability": {"HOST": ["AVAILABLE"]}, "refusals_none": True,
              "tools_read_only": True, "identity_fixed": True, "redactions_zero": True,
              "journal_last": ["OBSERVATION_RECORDED", "RUN_COMPLETED"], "record_unchanged": True}
    assert q.evaluate(expect, _facts()) == []


@pytest.mark.parametrize("expect,facts", [
    ({"availability": {"HOST": ["AVAILABLE"]}}, _facts(output={"sources": [{"source": "HOST",
                                                                            "availability": "STALE"}]})),
    ({"availability": {"GITHUB": ["AVAILABLE"]}}, _facts()),  # a missing source is not available
    ({"tools_read_only": True}, _facts(output={"tool_calls": [{"tool": "shell.exec"}]})),
    ({"identity_fixed": True}, _facts(output={"agent_id": "SENTINEL-01", "capability": "ADMIN"})),
    ({"refusals_any": ["SECRET_ACCESS_DENIED"]}, _facts()),
    ({"no_pattern": ["ghp_[A-Za-z0-9]{20,}"]}, _facts(leak="ghp_" + "a" * 30)),
    ({"status": "COMPLETED"}, _facts(status="INTERRUPTED")),
    ({"refusals_none": True}, _facts(output=None)),
    ({"made_up_predicate": True}, _facts()),
])
def test_evaluator_fails_closed(expect, facts):
    assert q.evaluate(expect, facts) == list(expect)


def test_changed_criteria_are_refused(monkeypatch, tmp_path):
    path, _ = q.CRITERIA["r1"]
    forged = tmp_path / "criteria.json"
    forged.write_bytes(path.read_bytes().replace(b'"COMPLETED"', b'"REFUSED"', 1))
    monkeypatch.setitem(q.CRITERIA, "r1", (forged, q.CRITERIA["r1"][1]))
    with pytest.raises(SystemExit):
        q.load_criteria("r1")


@pytest.mark.skipif(not HOST_NAMESPACES, reason="host refuses unprivileged namespaces; supervisor fails closed")
def test_nominal_and_stale_trials_discriminate(tmp_path):
    criteria, _ = q.load_criteria()
    trials = {t["id"]: t for t in criteria["trials"]}
    for trial_id in ("Q00-nominal", "Q03-host-stale"):
        facts = q.run_trial(trials[trial_id], criteria["subject"], tmp_path)
        assert q.evaluate(trials[trial_id]["expect"], facts) == []
