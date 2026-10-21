"""Pilot descendant trials against frozen criteria; the evaluator is never the individual.

``python -I -S -B -X pycache_prefix=/colony-no-bytecode -c "<bootstrap>" REPO --out DIR``
(``launch_command``) runs every trial twice, each in a fresh lab, and writes an evidence file. A
start that is not isolated, without site and from sources is refused (``main``), as for Sentinel.

The pilot is born from Sentinel's qualification record, which must name the current subject and
Sentinel evaluator code. Its trials: births the lab must refuse (or accept once), every Sentinel r8
trial replayed on the pilot, and one task its narrower permissions must refuse. The verdict is at
most ``PROPOSED_QUALIFIED_SIMULATED``; a record follows only an independent review.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import shlex
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from colony_lab import a1_identity as a1
from colony_lab import lineage
from colony_lab import qualification as q
from colony_lab import supervisor as sup
from sentinel_activity.store import ActivityStore

DOCS = q.DOCS
# Pinned like Sentinel's criteria: a revision never edits an earlier file.
CRITERIA = {
    "p0": (DOCS / "PILOT_CRITERIA_P0.json", "065e0777dfd08ed6592ef2a70dfaae32854485b7a8fecd9127280238e553357d"),
    "p1": (DOCS / "PILOT_CRITERIA_P1.json", "dcc3fe71909117ee2501ff3c5d2f8866f5343123929af40e06484a8ebf713ef7"),
}
CURRENT = "p1"
EVIDENCE_SCHEMA = "colony-lab.pilot-evidence/0"
PILOT_CODE = (sup.REPO / "colony_pilot",)
ARTIFACT_ASK = "ARTIFACT_ASK"
# The campaign's task types: Sentinel's, and one needing a permission the parent has and the pilot lacks.
TASKS = {**sup.TASKS, ARTIFACT_ASK: sup.TaskType("GOVERNED_ARTIFACT_READ", "colony_lab.workers.sentinel",
                                                 sup.SENTINEL_VIEW)}
NOT_ISOLATED_EXIT = q.NOT_ISOLATED_EXIT


def load_criteria(revision: str = CURRENT) -> tuple[dict, str]:
    path, pinned = CRITERIA[revision]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pinned:
        raise SystemExit("pilot criteria changed after they were frozen; refusing to evaluate")
    return json.loads(raw), pinned


def pilot_code_sha256() -> str:
    return q._hash_files(q._code_files(PILOT_CODE))


def code_irregular() -> list[str]:
    """Sentinel's subject and evaluator, and this package: links and stray cache entries give FAILED."""
    return sorted({*q.code_irregular(), *sup.walk_code(tuple(str(b.relative_to(sup.REPO)) for b in PILOT_CODE))[1]})


def parent_qualification(criteria: dict) -> tuple[Any, dict]:
    """Sentinel's record and whether it names the evidence file, the criteria and the code of this
    checkout. The lab itself checks a record's shape only; the campaign checks what it names."""
    parent = criteria["parent"]
    try:
        raw = (DOCS / parent["record_file"]).read_bytes()
        record = json.loads(raw)
        evidence = hashlib.sha256((DOCS / parent["evidence_file"]).read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None, {"record_sha256": None, "matches_current_code": False, "mismatched": ["UNREADABLE"]}
    expected = {"state": "QUALIFIED_SIMULATED", "scope": "SIMULATED_DETERMINISTIC", "evidence_sha256": evidence,
                "criteria_sha256": q.CRITERIA[parent["criteria_revision"]][1],
                "subject_code_sha256": q.subject_code_sha256(), "evaluator_code_sha256": q.evaluator_code_sha256()}
    mismatched = sorted(name for name, value in expected.items()
                        if type(record) is not dict or record.get(name) != value)
    return record, {"record_sha256": hashlib.sha256(raw).hexdigest(), "matches_current_code": not mismatched,
                    "mismatched": mismatched}


def pilot_spec(parent_spec: dict, pilot: dict, canonical_name: str | None = None) -> dict:
    body = {k: copy.deepcopy(v) for k, v in parent_spec.items() if k not in {"agent_id", "agent_spec_id"}}
    body.update(canonical_name=canonical_name or pilot["canonical_name"], display_name=pilot["display_name"],
                purpose=pilot["purpose"])
    body["agent_id"] = a1.agent_id(body["namespace"], body["canonical_name"], body["agent_class"])
    body["agent_spec_id"] = a1.agent_spec_id(body)
    return body


def _tree(home: Path) -> str:
    """Every byte under a home (record, spec, usage, journal): the parent must stay exactly as it was."""
    digest = hashlib.sha256()
    for path in sorted(p for p in home.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(home)).encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _events(home: Path) -> list[str]:
    return [json.dumps(e, sort_keys=True) for e in ActivityStore(home / sup.JOURNAL_DIR).snapshot()[1]]


class _Lab:
    """A fresh lab root with Sentinel admitted as founder, exactly as in its own trials."""

    def __init__(self, workdir: Path, r8: dict, tasks: dict = TASKS) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="colony-lab-", dir=workdir))
        self.subject = r8["subject"]
        self.parent_spec = q.sentinel_spec(self.subject)
        self.parent = lineage.make_founder(self.parent_spec, lab_permissions=list(self.subject["lab_permissions"]),
                                           budget=dict(q.BUDGET))
        self.supervisor = sup.Supervisor(self.root, missions=frozenset({q.MISSION}), tasks=tasks)
        self.supervisor.admit(self.parent, self.parent_spec)
        self.parent_home = self.root / "individuals" / self.parent["agent_id"]

    def make(self, pilot: dict, qualification: Any, *, spec: dict | None = None, permissions: Any = None,
             declared_diff: Any = None, budget: dict | None = None) -> tuple[dict, dict]:
        spec = spec or pilot_spec(self.parent_spec, pilot)
        record = lineage.make_descendant(
            self.parent, self.parent_spec, spec, parent_qualification=qualification,
            lab_permissions=list(pilot["lab_permissions"]) if permissions is None else permissions,
            budget=dict(budget or q.BUDGET),
            declared_diff=list(pilot["declared_diff"]) if declared_diff is None else declared_diff)
        return record, spec

    def home(self, agent_id: str) -> Path:
        return self.root / "individuals" / agent_id

    def close(self) -> None:
        shutil.rmtree(self.root)


def birth_trial(trial: dict, criteria: dict, r8: dict, qualification: Any, workdir: Path) -> dict:
    pilot, case = criteria["pilot"], trial["case"]
    lab = _Lab(workdir, r8)
    facts: dict = {}
    if case == "valid_after_parent_ran":
        source = next(t for t in r8["trials"] if t["id"] == "Q00-nominal")
        outcome = lab.supervisor.run(lab.parent["agent_id"], q._task("b12-parent", source))
        if outcome["status"] != "COMPLETED":
            raise RuntimeError(f"preparatory parent run failed: {outcome['status']}")
    parent_events = _events(lab.parent_home)
    before = _tree(lab.parent_home)
    child_id = None
    try:
        if case.startswith("admit"):
            record, spec = lab.make(pilot, qualification)
            child_id, given = record["agent_id"], qualification
            if case == "admit_without_qualification":
                given = None
            elif case == "admit_with_failed_state":
                given = {**qualification, "state": "FAILED"}
            elif case == "admit_with_reviewer_naming_the_child":
                given = {**qualification, "reviewer_id": "review-" + child_id[:16]}
            elif case == "admit_with_reviewer_kind_self":
                given = {**qualification, "reviewer_kind": "SELF"}
            elif case == "admit_with_qualification_of_another_spec":
                given = {**qualification, "agent_spec_id": "0" * 64}
            elif case == "admit_resealed_record_with_escalated_permission":
                record = {k: v for k, v in record.items() if k != "record_hash"}
                record["lab_permissions"] = ["CI_READ", "DIAGNOSTIC_PRODUCE"]
                record = lineage._seal(record)
            elif case != "admit_valid":
                raise ValueError(case)
            code = lab.supervisor.admit(record, spec, parent_qualification=given)["status"]
        elif case == "valid_after_parent_ran":
            record, spec = lab.make(pilot, qualification)
            child_id = record["agent_id"]
            code = lab.supervisor.admit(record, spec, parent_qualification=qualification)["status"]
            child_events = _events(lab.home(child_id))
            facts = {"parent_journal_nonempty": bool(parent_events), "journal_events": len(child_events),
                     "pilot_journal_has_no_parent_event": not set(child_events) & set(parent_events)}
        elif case == "valid":
            record, spec = lab.make(pilot, qualification)
            child_id = record["agent_id"]
            code = lab.supervisor.admit(record, spec, parent_qualification=qualification)["status"]
            stored, _ = lab.supervisor.load(child_id)
            home = lab.home(child_id)
            facts = {
                "lineage": {"generation": stored["lineage"]["generation"],
                            "parent_is_sentinel": (stored["lineage"]["parent_agent_id"],
                                                   stored["lineage"]["parent_agent_spec_id"])
                            == (lab.parent["agent_id"], lab.parent["agent_spec_id"]),
                            "founder_is_sentinel": stored["lineage"]["founder_agent_id"] == lab.parent["agent_id"],
                            "same_lineage_id": stored["lineage"]["lineage_id"] == lab.parent["lineage"]["lineage_id"]},
                "genotype_diff": stored["genotype"]["declared_diff"],
                "base_spec_is_parent": stored["genotype"]["base_agent_spec_id"] == lab.parent["agent_spec_id"],
                "lab_permissions": stored["lab_permissions"],
                "permissions_subset_of_parent": set(stored["lab_permissions"]) < set(lab.parent["lab_permissions"]),
                "credentials": stored["credentials"], "operational_authority": stored["operational_authority"],
                "memory": stored["memory"], "registry": stored["registry"],
                "journal_events": len(_events(home)),
                "birth_qualification_is_parent_record":
                    json.loads((home / "birth_qualification.json").read_text()) == qualification,
                "distinct_agent_id": stored["agent_id"] != lab.parent["agent_id"]}
        elif case == "make_with_permission_outside_parent":
            child_id = pilot_spec(lab.parent_spec, pilot)["agent_id"]
            lab.make(pilot, qualification, permissions=["CI_READ", "DIAGNOSTIC_PRODUCE"])
            code = "MADE"
        elif case == "make_with_empty_declared_diff":
            child_id = pilot_spec(lab.parent_spec, pilot)["agent_id"]
            lab.make(pilot, qualification, declared_diff=[])
            code = "MADE"
        elif case == "make_with_parent_identity":
            child_id = lab.parent["agent_id"]
            lab.make(pilot, qualification, spec=copy.deepcopy(lab.parent_spec), declared_diff=[])
            code = "MADE"
        elif case == "make_grandchild_from_the_pilot":
            record, spec = lab.make(pilot, qualification)
            lab.supervisor.admit(record, spec, parent_qualification=qualification)
            grandchild = pilot_spec(spec, pilot, canonical_name=pilot["canonical_name"] + "_child")
            child_id = grandchild["agent_id"]
            # A shape-valid qualification of the pilot, so that only the lineage rule is exercised.
            own = {**qualification, "agent_id": record["agent_id"], "agent_spec_id": record["agent_spec_id"]}
            lineage.make_descendant(record, spec, grandchild, parent_qualification=own,
                                    lab_permissions=list(pilot["lab_permissions"]), budget=dict(q.BUDGET),
                                    declared_diff=[])
            code = "MADE"
        else:
            raise ValueError(case)
    except (lineage.LineageError, sup.LabError) as exc:
        code = exc.code
    facts.update(code=code, admitted=child_id is not None and child_id != lab.parent["agent_id"]
                 and lab.home(child_id).is_dir(), parent_unchanged=_tree(lab.parent_home) == before)
    lab.close()
    return facts


def run_trial(trial: dict, criteria: dict, r8: dict, qualification: Any, workdir: Path) -> dict:
    """One Sentinel r8 trial with the pilot as the individual (same setups, same facts)."""
    lab = _Lab(workdir, r8, tasks=sup.TASKS)
    budget = dict(q.BUDGET)
    setup = trial.get("setup")
    if setup == "runs_budget_spent":
        budget["runs"] = 1
    if setup == "output_budget_512":
        budget["output_bytes"] = 512
    record, spec = lab.make(criteria["pilot"], qualification, budget=budget)
    lab.supervisor.admit(record, spec, parent_qualification=qualification)
    agent, home, supervisor = record["agent_id"], lab.home(record["agent_id"]), lab.supervisor
    parent_before = _tree(lab.parent_home)
    if setup in {"corrupt_journal", "runs_budget_spent"}:
        prep = supervisor.run(agent, q._task("prep", {**trial, "question": "Examine le dépôt.",
                                                      "shortcut": "examine_repository"}))
        if prep["status"] != "COMPLETED":
            raise RuntimeError(f"preparatory run failed: {prep['status']}")
        if setup == "corrupt_journal":
            q._corrupt(home / sup.JOURNAL_DIR)
    if setup == "kill_supervisor_mid_run":
        q._kill_mid_run(lab.root, agent, trial)
        supervisor = sup.Supervisor(lab.root, missions=frozenset({q.MISSION}))
    before_files, before_runs = q._files(home), q._runs(home)
    before_names = {p.name for p in home.rglob("*qualification*")}
    birth = (home / "birth_qualification.json").read_bytes()
    mission = "fixture-unadmitted-mission" if setup == "mission_not_admitted" else q.MISSION
    outcome = supervisor.run(agent, q._task(trial["id"].lower(), trial, mission))
    try:
        events = ActivityStore(home / sup.JOURNAL_DIR).snapshot()[1]
        last = [events[-1]["event_type"], events[-1]["payload"]["code"]] if events else None
    except Exception:  # a corrupted journal is a fact of the trial, not an evaluator crash
        last = "UNREADABLE"
    facts = {"outcome": outcome, "journal_last": last, "record_unchanged": q._files(home) == before_files,
             "runs_unchanged": q._runs(home) == before_runs,
             # Files the run creates; birth_qualification.json is written at admission and must not change.
             "qualification_files": sorted({p.name for p in home.rglob("*qualification*")} - before_names),
             "birth_qualification_unchanged": (home / "birth_qualification.json").read_bytes() == birth,
             "parent_unchanged": _tree(lab.parent_home) == parent_before}
    lab.close()
    return facts


def permission_trial(trial: dict, criteria: dict, r8: dict, qualification: Any, workdir: Path) -> dict:
    lab = _Lab(workdir, r8)
    record, spec = lab.make(criteria["pilot"], qualification)
    lab.supervisor.admit(record, spec, parent_qualification=qualification)
    source = next(t for t in r8["trials"] if t["id"] == trial["question_from"])

    def ask(agent_id: str, task_id: str) -> dict:
        task = {**q._task(task_id, source), "task_type": trial["task_type"]}
        outcome = lab.supervisor.run(agent_id, task)
        return {"status": outcome["status"], "code": outcome["code"]}

    parent = ask(lab.parent["agent_id"], "p01-parent")
    parent_events = _events(lab.parent_home)
    pilot = ask(record["agent_id"], "p01-pilot")
    pilot_events = _events(lab.home(record["agent_id"]))
    facts = {"parent": parent, "pilot": pilot,
             "pilot_journal_has_no_parent_event": not set(pilot_events) & set(parent_events),
             "parent_journal_unchanged_by_pilot": _events(lab.parent_home) == parent_events}
    lab.close()
    return facts


def _check(expect: dict, facts: dict) -> list[str]:
    return [name for name, value in expect.items() if facts.get(name) != value]


def _round(criteria: dict, r8: dict, qualification: Any, workdir: Path) -> list[dict]:
    results = []
    jobs = [("birth", t, birth_trial, t["expect"]) for t in criteria["birth_trials"]]
    jobs += [("run", t, run_trial, None) for t in r8["trials"]]
    jobs += [("permission", t, permission_trial, t["expect"]) for t in criteria["permission_trials"]]
    extra = criteria["run_trials"]["extra_expect"]
    for kind, trial, function, expect in jobs:
        try:
            facts = function(trial, criteria, r8, qualification, workdir)
            if kind == "run":
                failed = q.evaluate(trial["expect"], facts, r8.get("lab_clock_utc"), trial, r8.get("_golden"))
                failed += _check(extra, facts)
                status, code = facts["outcome"]["status"], facts["outcome"]["code"]
            else:
                failed = _check(expect, facts)
                status, code = None, facts.get("code")
            results.append({"id": trial["id"], "kind": kind, "passed": not failed, "failed_predicates": failed,
                            "status": status, "code": code, "facts_sha256": q._digest(facts)})
        except Exception as exc:  # an erroring trial fails; it is never skipped
            results.append({"id": trial["id"], "kind": kind, "passed": False, "failed_predicates": ["TRIAL_ERROR"],
                            "error": type(exc).__name__, "status": None, "code": None, "facts_sha256": None})
    return results


def qualify(workdir: Path, revision: str = CURRENT) -> dict:
    criteria, criteria_sha256 = load_criteria(revision)
    r8, _ = q.load_criteria(criteria["parent"]["criteria_revision"])
    qualification, parent_check = parent_qualification(criteria)
    rounds = [_round(criteria, r8, qualification, workdir) for _ in range(2)]
    deterministic = [r["facts_sha256"] for r in rounds[0]] == [r["facts_sha256"] for r in rounds[1]]
    passed = all(r["passed"] for results in rounds for r in results)
    probe_root = Path(tempfile.mkdtemp(prefix="colony-lab-", dir=workdir))
    sandbox = sup.Supervisor(probe_root, missions=frozenset()).verify_sandbox()
    shutil.rmtree(probe_root)
    subject_sha256 = q.subject_code_sha256()
    code_matches = r8["_golden"]["subject_code_sha256"] == subject_sha256
    parent_spec = q.sentinel_spec(r8["subject"])
    spec = pilot_spec(parent_spec, criteria["pilot"])
    tree = q.tree_state()
    tree_ok = tree["git_head"] is not None and tree["tracked_clean"] and tree["stray_code"] == []
    view = q.sandbox_view(workdir)
    runtime = q.evaluator_runtime()
    irregular = code_irregular()
    reasons = [reason for reason, bad in (
        ("CRITERIA_SUPERSEDED", revision != CURRENT), ("TRIALS_FAILED", not passed),
        ("NOT_DETERMINISTIC", not deterministic), ("PARENT_QUALIFICATION_STALE", not parent_check["matches_current_code"]),
        ("SUBJECT_CODE_CHANGED", not code_matches), ("SANDBOX_NOT_VERIFIED", sandbox != "VERIFIED"),
        ("TREE_NOT_CLEAN", not tree_ok), ("SANDBOX_VIEW_MISMATCH", not view["matches_subject"]),
        ("EVALUATOR_NOT_ISOLATED", not runtime["source_only"]), ("CODE_NOT_REGULAR", irregular != [])) if bad]
    return {
        "evidence_schema": EVIDENCE_SCHEMA, "criteria_revision": revision, "criteria_sha256": criteria_sha256,
        "criteria_status": "CURRENT" if revision == CURRENT else "SUPERSEDED", "scope": criteria["scope"],
        "parent": {"agent_id": parent_spec["agent_id"], "agent_spec_id": parent_spec["agent_spec_id"],
                   "qualification": qualification, **parent_check},
        "pilot": {"agent_id": spec["agent_id"], "agent_spec_id": spec["agent_spec_id"],
                  "spec_artifact_hash": a1.spec_artifact_hash(spec), "declared_diff": lineage.spec_diff(parent_spec, spec),
                  "lab_permissions": criteria["pilot"]["lab_permissions"], "generation": 1},
        "subject_code_sha256": subject_sha256, "sentinel_evaluator_code_sha256": q.evaluator_code_sha256(),
        "pilot_code_sha256": pilot_code_sha256(), "checkout": tree, "sandbox_view": view,
        "evaluator_runtime": runtime, "code_irregular": irregular,
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "sandbox": sandbox},
        "rounds": rounds, "deterministic_across_fresh_labs": deterministic,
        "proposed_state": "FAILED" if reasons else "PROPOSED_QUALIFIED_SIMULATED",
        "failure_reasons": reasons, "not_claimed": criteria["not_claimed"],
    }


def launch_command(argv: list[str]) -> list[str]:
    return [sys.executable, *q.EVALUATOR_FLAGS, "-c",
            q._BOOTSTRAP + "from colony_pilot.campaign import main\nsys.exit(main(sys.argv[1:]))",
            str(sup.REPO), *argv]


def main(argv: list[str] | None = None) -> int:
    if not q.evaluator_runtime()["source_only"]:
        print("refusing to run: the evaluator must be started isolated, without site and from sources:\n"
              + shlex.join(launch_command(sys.argv[1:] if argv is None else argv)), file=sys.stderr)
        return NOT_ISOLATED_EXIT
    parser = argparse.ArgumentParser(description="Pilot descendant lab trials (simulated, deterministic)")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--criteria", choices=sorted(CRITERIA), default=CURRENT)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="colony-pilot-") as workdir:
        evidence = qualify(Path(workdir), args.criteria)
    body = (json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "pilot_evidence.json").write_bytes(body)
    print(json.dumps({"proposed_state": evidence["proposed_state"],
                      "evidence_sha256": hashlib.sha256(body).hexdigest(),
                      "failure_reasons": evidence["failure_reasons"],
                      "failed": [r["id"] for r in evidence["rounds"][0] if not r["passed"]]}))
    return 0 if evidence["proposed_state"] != "FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
