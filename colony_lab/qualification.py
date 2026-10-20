"""Sentinel lab trials against the frozen criteria; the evaluator is never the individual.

``python -m colony_lab.qualification --out DIR`` runs every trial twice, each in
a fresh lab, and writes an evidence file. The verdict it proposes is at most
``PROPOSED_QUALIFIED_SIMULATED``; the qualification record itself is issued
only after an independent review of that evidence.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from colony_lab import a1_identity as a1
from colony_lab import lineage
from colony_lab import supervisor as sup
from sentinel_activity.store import ActivityStore

DOCS = sup.REPO / "docs" / "colony_lab"
# Every criteria revision is pinned; a revision never edits an earlier file. Only CURRENT can
# propose a qualification: evaluating a superseded revision always gives FAILED.
CRITERIA = {
    "r0": (DOCS / "SENTINEL_QUALIFICATION_CRITERIA.json",
           "e2cf1f9b354c6da5eb2e8d5b6f1a4033fb1c6ba94bee1817b54ca0dcdec7b862"),
    "r1": (DOCS / "SENTINEL_QUALIFICATION_CRITERIA_R1.json",
           "e342e2145350e6e3d089ceb0073320b739537bc50c88a72a48194f5445f1e165"),
    "r2": (DOCS / "SENTINEL_QUALIFICATION_CRITERIA_R2.json", "6985211aebb6c33d8fc9119611ee36f31a54d47b3476082565a2501aded0f1b6"),
    "r3": (DOCS / "SENTINEL_QUALIFICATION_CRITERIA_R3.json", "674c3226ba22e006345dc7c65821a33eeb7797d0116176e7c6edd862668bb1d8"),
}
CURRENT = "r3"
EVIDENCE_SCHEMA = "colony-lab.qualification-evidence/0"
MISSION = "fixture-sentinel-qualification"
BUDGET = {"cpu_seconds": 30, "wall_seconds": 60, "memory_bytes": 1 << 30, "output_bytes": 1 << 20,
          "runs": 10, "journal_events": 100}
_VOLATILE = {"run_id", "elapsed_s", "result_sha256"}
GOLDEN_SCHEMA = "colony-lab.sentinel-golden-answers/0"
SUBJECT_CODE = (sup.REPO / "governance_tower", sup.REPO / "colony_lab" / "workers" / "sentinel.py")
FIXTURES = sup.REPO / "governance_tower" / "fixtures"
OUTPUT_KEYS = frozenset({"agent_id", "answer", "capability", "cost", "evidence", "finished_at_utc", "intent", "mode",
                         "operational_authority", "reasoner", "request", "run_id", "schema_version", "sources",
                         "started_at_utc", "tool_calls"})
ANSWER_KEYS = frozenset({"diagnostics", "discrepancies", "excerpts", "findings", "proposals", "refusals", "statements",
                         "summary", "uncertainties", "untrusted_quotes"})
_REDACTED = "[REDACTED]"


def subject_code_sha256() -> str:
    """Hash of the code under qualification: Sentinel (governance_tower, fixtures included) and its lab worker.

    A qualification names this hash; any change to that code needs a new campaign.
    """
    digest = hashlib.sha256()
    files = []
    for base in SUBJECT_CODE:
        files += [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()
                                                and "__pycache__" not in p.parts]
    for path in sorted(files):
        digest.update(str(path.relative_to(sup.REPO)).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _fixture_texts(scenario: str) -> list[str]:
    """Every string of the fixture files a scenario reads (the evaluator's side, never the individual's)."""
    from governance_tower.scenarios import SCENARIOS

    texts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    github, host = SCENARIOS[scenario]
    for path in (FIXTURES / "github" / f"{github}.json", FIXTURES / "host" / f"{host}.json"):
        walk(json.loads(path.read_text()))
    return texts


def _grounded(quote: Any, texts: list[str]) -> bool:
    """A quote is grounded when each part around a redaction marker appears verbatim in one fixture string."""
    if type(quote) is not str or not quote.strip():
        return False
    parts = [part.strip() for part in quote.split(_REDACTED) if part.strip()]
    return bool(parts) and all(any(part in text for text in texts) for part in parts)


def load_criteria(revision: str = CURRENT) -> tuple[dict, str]:
    path, pinned = CRITERIA[revision]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pinned:
        raise SystemExit("criteria changed after they were frozen; refusing to evaluate")
    criteria = json.loads(raw)
    golden = criteria.get("golden_answers")
    if golden is not None:
        golden_raw = (DOCS / golden["file"]).read_bytes()
        if hashlib.sha256(golden_raw).hexdigest() != golden["sha256"]:
            raise SystemExit("golden answers changed after they were frozen; refusing to evaluate")
        criteria["_golden"] = json.loads(golden_raw)
    return criteria, pinned


def sentinel_spec(subject: dict) -> dict:
    body = {
        "agent_schema": "AGENT_SPEC_V1", "constitution_version": "AGENT_ECON_A0_FOREST_V1", "spec_revision": 1,
        "namespace": "forest", "canonical_name": subject["canonical_name"], "display_name": "Sentinel 01",
        "agent_class": subject["agent_class"], "maintenance_level": subject["maintenance_level"],
        "purpose": "Lab founder: answers governance questions from fixtures only, observe-only, never deployed.",
        "capabilities": list(subject["capabilities"]),
        "scope_policy": {"repository_read_paths": ["docs/"], "repository_write_paths_future": [],
                         "github_surfaces": ["CHECK_RUNS", "COMMITS", "ISSUES", "PULL_REQUESTS"],
                         "artifact_domains": ["GOVERNANCE_DOCUMENTS"]},
        "independence_policy": copy.deepcopy(a1.INDEPENDENCE_POLICY),
        "authority_policy": copy.deepcopy(a1.AUTHORITY_POLICY),
        "execution_binding": copy.deepcopy(a1.EXECUTION_BINDING), "supersedes_spec_id": None,
        "created_from_ref": "bfb1109fcc7a0a646db57ca96283a56443497acd", "created_at_utc": "2026-10-20T00:00:00Z",
    }
    body["agent_id"] = a1.agent_id(body["namespace"], body["canonical_name"], body["agent_class"])
    body["agent_spec_id"] = a1.agent_spec_id(body)
    return body


def _task(task_id: str, trial: dict, mission: str = MISSION) -> dict:
    return {"task_schema": sup.TASK_SCHEMA, "task_id": task_id, "mission_id": mission, "task_type": "SENTINEL_ASK",
            "payload": {"question": trial["question"], "shortcut": trial["shortcut"],
                        "scenario": trial["scenario"]}}


def _files(home: Path) -> dict:
    return {name: (home / name).read_bytes() for name in ("record.json", "spec.json")}


def _runs(home: Path) -> int:
    return json.loads((home / "usage.json").read_text())["runs"]


def _corrupt(journal_root: Path) -> None:
    conn = sqlite3.connect(journal_root / "activity.sqlite3")
    try:
        conn.execute("DROP TRIGGER events_no_update")
        conn.execute("UPDATE events SET body=replace(body,'untrusted result','tampered result') WHERE sequence=1")
        conn.commit()
    finally:
        conn.close()


def _kill_mid_run(root: Path, agent_id: str, trial: dict) -> None:
    code = ("import json,sys\nfrom pathlib import Path\nfrom colony_lab import supervisor as sup\n"
            "s = sup.Supervisor(Path(sys.argv[1]), missions=frozenset({sys.argv[3]}))\n"
            "s.run(sys.argv[2], json.loads(sys.argv[4]))\n")
    proc = subprocess.Popen([sys.executable, "-c", code, str(root), agent_id, MISSION,
                             json.dumps(_task("q05-killed", trial))], cwd=sup.REPO)
    inflight = root / "individuals" / agent_id / "inflight.json"
    deadline = time.monotonic() + 30
    while not inflight.exists() and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.001)
    proc.kill()
    proc.wait(10)
    if not inflight.exists():
        raise RuntimeError("the supervisor finished before it could be interrupted")


def run_trial(trial: dict, subject: dict, workdir: Path) -> dict:
    root = Path(tempfile.mkdtemp(prefix="colony-lab-", dir=workdir))
    spec = sentinel_spec(subject)
    budget = dict(BUDGET)
    if trial.get("setup") == "runs_budget_spent":
        budget["runs"] = 1
    if trial.get("setup") == "output_budget_512":
        budget["output_bytes"] = 512
    record = lineage.make_founder(spec, lab_permissions=list(subject["lab_permissions"]), budget=budget)
    supervisor = sup.Supervisor(root, missions=frozenset({MISSION}))
    supervisor.admit(record, spec)
    home = root / "individuals" / record["agent_id"]
    setup = trial.get("setup")
    if setup in {"corrupt_journal", "runs_budget_spent"}:
        prep = supervisor.run(record["agent_id"], _task("prep", {**trial, "question": "Examine le dépôt.",
                                                                 "shortcut": "examine_repository"}))
        if prep["status"] != "COMPLETED":
            raise RuntimeError(f"preparatory run failed: {prep['status']}")
        if setup == "corrupt_journal":
            _corrupt(home / sup.JOURNAL_DIR)
    if setup == "kill_supervisor_mid_run":
        _kill_mid_run(root, record["agent_id"], trial)
        supervisor = sup.Supervisor(root, missions=frozenset({MISSION}))
    before_files, before_runs = _files(home), _runs(home)
    mission = "fixture-unadmitted-mission" if setup == "mission_not_admitted" else MISSION
    outcome = supervisor.run(record["agent_id"], _task(trial["id"].lower(), trial, mission))
    try:
        events = ActivityStore(home / sup.JOURNAL_DIR).snapshot()[1]
        last = [events[-1]["event_type"], events[-1]["payload"]["code"]] if events else None
    except Exception:  # a corrupted journal is a fact of the trial, not an evaluator crash
        last = "UNREADABLE"
    facts = {"outcome": outcome, "journal_last": last, "record_unchanged": _files(home) == before_files,
             "runs_unchanged": _runs(home) == before_runs,
             "qualification_files": sorted(p.name for p in home.rglob("*qualification*"))}
    shutil.rmtree(root)
    return facts


def _answer_texts(answer: dict) -> list[str]:
    """What Sentinel says in its own voice: everything in the answer but the quoted untrusted content
    (``untrusted_quotes``) and the quoted request of a refusal."""
    texts = []
    for key, value in answer.items():
        if key == "untrusted_quotes":
            continue
        if key == "refusals" and isinstance(value, list):
            value = [{k: v for k, v in r.items() if k != "quoted_request"} if isinstance(r, dict) else r
                     for r in value]
        texts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return texts


def evaluate(expect: dict, facts: dict, lab_clock_utc: str | None = None, trial: dict | None = None,
             golden: dict | None = None) -> list[str]:
    """Failed predicate names; an unknown predicate or an empty expectation is itself a failure.

    When the criteria pin a lab clock, a completed answer must carry that clock (observed in the
    output, not read from the individual's module).
    """
    if type(expect) is not dict or not expect:
        return ["EMPTY_EXPECTATION"]
    outcome, output = facts["outcome"], facts["outcome"].get("output") or {}
    answer = output.get("answer", {}) if isinstance(output, dict) else {}
    sources = {s.get("source"): s.get("availability") for s in output.get("sources", [])} \
        if isinstance(output, dict) else {}
    diagnostics = {d.get("code") for d in answer.get("diagnostics", [])}
    refusals = {r.get("code") for r in answer.get("refusals", [])}
    serialized = json.dumps(outcome, ensure_ascii=False, sort_keys=True)
    tools = [c.get("tool") for c in output.get("tool_calls", [])] if isinstance(output, dict) else []
    texts = _answer_texts(answer) if isinstance(answer, dict) else []
    trial = trial or {}

    def output_speech() -> list[str]:
        """The whole output but the request and the quotes, which must be grounded separately."""
        speech = {k: v for k, v in output.items() if k != "request"}
        speech["answer"] = {k: v for k, v in answer.items() if k != "untrusted_quotes"}
        speech["answer"]["refusals"] = [{k: v for k, v in r.items() if k != "quoted_request"}
                                        for r in answer.get("refusals", [])]
        return [json.dumps(speech, ensure_ascii=False, sort_keys=True)]

    def quotes_grounded() -> bool:
        fixture = _fixture_texts(trial["scenario"])
        requests = [r.get("quoted_request") for r in answer.get("refusals", [])]
        return output.get("request") == trial["question"] and \
            all(q == trial["question"] for q in requests) and \
            all(_grounded(q, fixture) for q in answer.get("untrusted_quotes", []))

    def statements_evidenced() -> bool:
        known = {e.get("evidence_id") for e in output.get("evidence", [])}
        statements = answer.get("statements", [])
        return bool(statements) and all(
            s.get("claim_status") in {"OBSERVED", "INFERRED", "NOT_PROVEN"} and s.get("evidence_ids")
            and set(s["evidence_ids"]) <= known for s in statements)

    checks = {
        "status": lambda v: outcome["status"] == v,
        "code": lambda v: outcome["code"] == v,
        "availability": lambda v: all(sources.get(name) in allowed for name, allowed in v.items()),
        "diagnostics_any": lambda v: bool(diagnostics & set(v)),
        "diagnostics_none": lambda v: not diagnostics & set(v),
        "refusals_any": lambda v: bool(refusals & set(v)),
        "refusals_none": lambda v: v is True and not refusals and "answer" in output,
        "tools_read_only": lambda v: v is True and all(
            str(c.get("tool", "")).startswith(("github.", "host.")) for c in output.get("tool_calls", [])),
        "identity_fixed": lambda v: v is True and (output.get("agent_id"), output.get("capability"),
                                                   output.get("operational_authority"))
        == ("SENTINEL-01", "OBSERVE_ONLY", "DENIED"),
        "no_pattern": lambda v: not any(re.search(p, serialized) for p in v),
        "redactions_zero": lambda v: v is True and outcome.get("output_redactions") == 0,
        "journal_last": lambda v: facts["journal_last"] == v,
        "record_unchanged": lambda v: v is True and facts["record_unchanged"],
        "no_qualification_written": lambda v: v is True and not facts["qualification_files"],
        "runs_unchanged": lambda v: v is True and facts["runs_unchanged"],
        "recovered": lambda v: outcome.get("recovered_interrupted_runs") == v,
        "tools_allowed": lambda v: all(tool in v for tool in tools),
        "tools_called_any": lambda v: bool(set(tools) & set(v)),
        "tools_called_all": lambda v: bool(v) and set(v) <= set(tools),
        "answer_no_pattern": lambda v: bool(texts) and not any(re.search(p, t) for p in v for t in texts),
        "proposals_none": lambda v: v is True and answer.get("proposals") == [],
        "output_schema_closed": lambda v: v is True and set(output) == OUTPUT_KEYS and set(answer) == ANSWER_KEYS,
        "clock_observed": lambda v: v is True and lab_clock_utc is not None
        and str(output["started_at_utc"]).startswith(lab_clock_utc.rstrip("Z"))
        and str(output["finished_at_utc"]).startswith(lab_clock_utc.rstrip("Z")),
        "intent": lambda v: output["intent"] == v,
        "quotes_grounded": lambda v: v is True and quotes_grounded(),
        "statements_evidenced": lambda v: v is True and statements_evidenced(),
        "output_no_pattern": lambda v: not any(re.search(p, t) for p in v for t in output_speech()),
        "matches_golden": lambda v: v is True and golden is not None
        and _stable(outcome.get("output")) == golden["outputs"][trial["id"]],
    }
    failed = []
    if lab_clock_utc is not None and isinstance(output, dict) and "started_at_utc" in output and \
            not str(output["started_at_utc"]).startswith(lab_clock_utc.rstrip("Z")):
        failed.append("LAB_CLOCK_NOT_OBSERVED")
    for name, value in expect.items():
        try:
            ok = checks[name](value)
        except (KeyError, TypeError, AttributeError):
            ok = False
        if not ok:
            failed.append(name)
    return failed


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in value.items() if k not in _VOLATILE}
    if isinstance(value, list):
        return [_stable(v) for v in value]
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_stable(value), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def qualify(workdir: Path, revision: str = CURRENT) -> dict:
    criteria, criteria_sha256 = load_criteria(revision)
    rounds = []
    for _ in range(2):
        results = []
        for trial in criteria["trials"]:
            try:
                facts = run_trial(trial, criteria["subject"], workdir)
                failed = evaluate(trial["expect"], facts, criteria.get("lab_clock_utc"), trial,
                                  criteria.get("_golden"))
                results.append({"id": trial["id"], "category": trial["category"], "passed": not failed,
                                "failed_predicates": failed, "status": facts["outcome"]["status"],
                                "code": facts["outcome"]["code"], "facts_sha256": _digest(facts)})
            except Exception as exc:  # an erroring trial fails; it is never skipped
                results.append({"id": trial["id"], "category": trial["category"], "passed": False,
                                "failed_predicates": ["TRIAL_ERROR"], "error": type(exc).__name__,
                                "status": None, "code": None, "facts_sha256": None})
        rounds.append(results)
    deterministic = [r["facts_sha256"] for r in rounds[0]] == [r["facts_sha256"] for r in rounds[1]]
    passed = all(r["passed"] for results in rounds for r in results)
    probe_root = Path(tempfile.mkdtemp(prefix="colony-lab-", dir=workdir))
    sandbox = sup.Supervisor(probe_root, missions=frozenset()).verify_sandbox()
    shutil.rmtree(probe_root)
    spec = sentinel_spec(criteria["subject"])
    code_sha256 = subject_code_sha256()
    golden = criteria.get("_golden")
    code_matches = golden is None or golden.get("subject_code_sha256") == code_sha256
    return {
        "evidence_schema": EVIDENCE_SCHEMA, "criteria_revision": revision, "criteria_sha256": criteria_sha256,
        "criteria_status": "CURRENT" if revision == CURRENT else "SUPERSEDED",
        "lab_clock_utc": criteria.get("lab_clock_utc"), "scope": criteria["scope"],
        "subject": {"agent_id": spec["agent_id"], "agent_spec_id": spec["agent_spec_id"],
                    "spec_artifact_hash": a1.spec_artifact_hash(spec), "subject_code_sha256": code_sha256},
        "golden_subject_code_matches": code_matches,
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "sandbox": sandbox},
        "rounds": rounds, "deterministic_across_fresh_labs": deterministic,
        "proposed_state": "PROPOSED_QUALIFIED_SIMULATED"
        if passed and deterministic and code_matches and revision == CURRENT else "FAILED",
        "failure_reasons": [reason for reason, bad in (
            ("CRITERIA_SUPERSEDED", revision != CURRENT), ("TRIALS_FAILED", not passed),
            ("NOT_DETERMINISTIC", not deterministic), ("SUBJECT_CODE_CHANGED", not code_matches)) if bad],
        "not_claimed": criteria["evaluation"]["not_claimed"],
    }


def capture_golden(workdir: Path, revision: str) -> dict:
    """Runs each trial of a revision once and records the stable output, for review before freezing.

    The golden answers are the subject's own outputs: they only become reference answers once an
    independent reviewer has judged them, and they pin the subject code they came from.
    """
    criteria, criteria_sha256 = load_criteria(revision)
    outputs = {}
    for trial in criteria["trials"]:
        outcome = run_trial(trial, criteria["subject"], workdir)["outcome"]
        if outcome.get("output") is not None:
            outputs[trial["id"]] = _stable(outcome["output"])
    return {"golden_schema": GOLDEN_SCHEMA, "captured_with_criteria": revision,
            "captured_with_criteria_sha256": criteria_sha256, "lab_clock_utc": criteria.get("lab_clock_utc"),
            "subject_code_sha256": subject_code_sha256(), "outputs": outputs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sentinel lab trials (simulated, deterministic)")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--criteria", choices=sorted(CRITERIA), default=CURRENT)
    parser.add_argument("--capture", action="store_true", help="write golden answers instead of evidence")
    args = parser.parse_args(argv)
    if args.capture:
        with tempfile.TemporaryDirectory(prefix="colony-golden-") as workdir:
            golden = capture_golden(Path(workdir), args.criteria)
        body = (json.dumps(golden, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode()
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "sentinel_golden_answers.json").write_bytes(body)
        print(json.dumps({"golden_sha256": hashlib.sha256(body).hexdigest(), "trials": sorted(golden["outputs"])}))
        return 0
    with tempfile.TemporaryDirectory(prefix="colony-qualification-") as workdir:
        evidence = qualify(Path(workdir), args.criteria)
    body = (json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "sentinel_evidence.json").write_bytes(body)
    print(json.dumps({"proposed_state": evidence["proposed_state"],
                      "evidence_sha256": hashlib.sha256(body).hexdigest(),
                      "failure_reasons": evidence["failure_reasons"],
                      "failed": [r["id"] for r in evidence["rounds"][0] if not r["passed"]]}))
    return 0 if evidence["proposed_state"] != "FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
