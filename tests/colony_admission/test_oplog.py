"""Adverse structural observations: no supplied log can grant an admission."""

import ast
import copy
import dataclasses
import hashlib
import inspect
from pathlib import Path

import pytest

from colony_admission import project_log
from colony_admission import formats as f

BOOT = "11111111-1111-1111-1111-111111111111"
COLD = "22222222-2222-2222-2222-222222222222"
BUDGET = dict.fromkeys(f.BUDGET_KEYS, 1)


def operation(attempt=1, **changes):
    """Sealed payload fixture; semantic admission is explicitly NOT evaluated."""
    child, spec, parent = "1" * 64, "2" * 64, "3" * 64
    record = {"agent_id": child, "agent_spec_id": spec, "budget": dict(BUDGET), "lab_permissions": []}
    qualification, admission = {"fixture": "qualification"}, {"fixture": "admission"}
    plan = {"plan_schema": "colony-registrar.birth-plan/0", "policy_sha256": "4" * 64,
            "parent": {"agent_id": parent}, "child_spec": {"agent_id": child, "agent_spec_id": spec},
            "record": record, "qualification": qualification, "admission": admission,
            "population": ["a" * 64], "population_count": 1, "children_count": 0,
            "budget_totals": dict(BUDGET)}
    presented = {key: {"record_sha256": f.digest(value), "envelope_sha256": "b" * 64}
                 for key, value in (("qualification", qualification), ("statement", {}), ("admission", admission))}
    return {"schema": "colony-admission.operation/0", "lab_id": "fixture-lab", "child_agent_id": child,
            "child_agent_spec_id": spec, "parent_agent_id": parent, "policy_sha256": "4" * 64,
            "historical_root_sha256": "5" * 64, "historical_root_version": 1, "items": [],
            "presented": presented, "budget": dict(BUDGET), "permissions": [], "declared_diff": [],
            "birth_plan": plan, "attempt": attempt, "boot_id": BOOT, **changes}


def entry(event, step=None, *, op=None, boot=BOOT, code="OBSERVED", data=None, **changes):
    op = operation() if op is None else op
    if data is None:
        data = {"operation": op} if event == "PREPARED" else {}
        if event == "COMMITTED":
            data = {"record_sha256": f.digest(op["birth_plan"]["record"])}
        if event == "DURABILITY_FAULT":
            data = {"fault_sha256": "f" * 64}
    return {"schema": "colony-admission.operation-entry/0", "operation_sha256": f.digest(op),
            "attempt": op["attempt"], "current_root_sha256": "5" * 64, "current_root_version": 1,
            "boot_id": boot, "event": event, "step": step, "code": code, "data": data, **changes}


def raw(*entries):
    return b"".join(f.canonical(e) + b"\n" for e in entries)


def prefix(level=0, *, op=None):
    result = [entry("PREPARED", op=op)]
    for k in range(1, level + 1):
        result += [entry("BEGIN", f"D{k}", op=op), entry("DONE", f"D{k}", op=op)]
    return result


def observed(data):
    result = project_log(data)
    assert result.accepted is False
    assert result.external_facts == "NOT_EVALUATED"
    return result


def corrupt(data):
    result = observed(data)
    assert result.status == "CORRUPT", result
    assert result.terminal_claim is None and result.operation_sha256 is None
    return result


def test_complete_birth_is_only_a_claim():
    result = observed(raw(*prefix(3), entry("COMMITTED")))
    assert result.status == "TERMINAL_CLAIM" and result.terminal_claim == "COMMITTED"
    assert result.last_completed_step == "D3" and result.d3_started
    assert len(result.history) == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.accepted = True
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.history[0].attempt = 2


@pytest.mark.parametrize("level", range(4))
def test_open_and_interrupted_prefixes(level):
    result = observed(raw(*prefix(level)))
    assert result.status == "OPEN" and result.last_completed_step == f"D{level}"
    if level < 3:
        result = observed(raw(*prefix(level), entry("BEGIN", f"D{level + 1}")))
        assert result.status == "INTERRUPTED" and result.pending_step == f"D{level + 1}"


@pytest.mark.parametrize("k", [1, 2, 3])
@pytest.mark.parametrize("outcome", ["ABSENT", "PRESENT", "PARTIAL"])
def test_explicit_recovery(k, outcome):
    events = prefix(k - 1) + [entry("BEGIN", f"D{k}")]
    recovered = entry("INTERRUPTED_RECOVERED", f"D{k}", boot=COLD, data={"result": outcome})
    if k == 1 and outcome == "PARTIAL":
        corrupt(raw(*events, recovered))
        return
    result = observed(raw(*events, recovered))
    assert result.status == "RECOVERED"
    assert result.last_completed_step == f"D{k if outcome == 'PRESENT' else k - 1}"
    if outcome == "PARTIAL" and k == 3:
        corrupt(raw(*events, recovered, entry("BEGIN", "D3")))
        events += [recovered, entry("QUARANTINE_BEGIN", "D3"), entry("QUARANTINE_DONE", "D3")]
        result = observed(raw(*events, entry("BEGIN", "D3")))
        assert result.status == "INTERRUPTED"
    elif outcome != "PRESENT":
        assert observed(raw(*events, recovered, entry("BEGIN", f"D{k}"))).status == "INTERRUPTED"
    elif k == 3:
        assert observed(raw(*events, recovered, entry("COMMITTED"))).terminal_claim == "COMMITTED"
    else:
        assert observed(raw(*events, recovered, entry("BEGIN", f"D{k + 1}"))).status == "INTERRUPTED"


@pytest.mark.parametrize("k", [1, 2, 3])
@pytest.mark.parametrize("outcome", ["PRESENT", "PARTIAL"])
def test_same_boot_never_cold(k, outcome):
    corrupt(raw(*prefix(k - 1), entry("BEGIN", f"D{k}"),
                entry("INTERRUPTED_RECOVERED", f"D{k}", data={"result": outcome})))


@pytest.mark.parametrize("step", ["D2", "D3"])
def test_begin_cancelled_returns_to_previous_step(step):
    k = int(step[1])
    events = prefix(k - 1) + [entry("BEGIN", step), entry("BEGIN_CANCELLED", step, code="LAB_STOPPED")]
    assert observed(raw(*events)).last_completed_step == f"D{k - 1}"
    assert observed(raw(*events, entry("BEGIN", step))).status == "INTERRUPTED"


def test_d1_cannot_cancel_a_registrar_commit():
    corrupt(raw(*prefix(), entry("BEGIN", "D1"), entry("BEGIN_CANCELLED", "D1")))


@pytest.mark.parametrize("level", [1, 2, 3])
def test_revocation_after_consumption(level):
    assert observed(raw(*prefix(level), entry("FAILED_CONSUMED", code="TRUST_REVOKED_AFTER_CONSUMPTION"))).terminal_claim == "FAILED_CONSUMED"
    corrupt(raw(*prefix(level), entry("FAILED_CONSUMED", code="LAB_STOPPED")))
    corrupt(raw(*prefix(level), entry("ABANDONED")))


@pytest.mark.parametrize("event", ["REFUSED", "ABANDONED"])
def test_next_attempt_same_child(event):
    op = operation(attempt=2)
    events = prefix() + [entry(event), entry("PREPARED", op=op)]
    result = observed(raw(*events))
    assert result.attempt == 2 and len(result.history) == 2
    assert result.history[0].terminal_claim == event
    corrupt(raw(*prefix(), entry(event), entry("PREPARED")))
    op = operation(attempt=2, child_agent_id="9" * 64)
    # Keep visible bindings consistent so the sequence, not the wrapper, refuses.
    op["birth_plan"]["record"]["agent_id"] = op["child_agent_id"]
    op["birth_plan"]["child_spec"]["agent_id"] = op["child_agent_id"]
    corrupt(raw(*prefix(), entry(event), entry("PREPARED", op=op)))


def test_termination_intermediate_and_endings():
    terminated = entry("TERMINATED", code="OPERATOR_TERMINATED")
    assert observed(raw(*prefix(), terminated)).status == "TERMINATING"
    assert observed(raw(*prefix(), terminated, entry("ABANDONED"))).terminal_claim == "ABANDONED"
    assert observed(raw(*prefix(1), terminated, entry("FAILED_CONSUMED", code="OPERATOR_TERMINATED"))).terminal_claim == "FAILED_CONSUMED"
    corrupt(raw(*prefix(1), terminated, entry("ABANDONED")))
    corrupt(raw(*prefix(), entry("TERMINATED", code="LAB_STOPPED")))


def failed_d3():
    return prefix(2) + [entry("BEGIN", "D3"), entry("TERMINATED", code="OPERATOR_TERMINATED"),
                        entry("FAILED_CONSUMED", code="OPERATOR_TERMINATED")]


def test_set_aside_preserves_terminal_and_cannot_repeat():
    events = failed_d3() + [entry("SET_ASIDE_BEGIN", "D3")]
    result = observed(raw(*events))
    assert result.status == "SETTING_ASIDE" and result.terminal_claim == "FAILED_CONSUMED"
    result = observed(raw(*events, entry("SET_ASIDE_DONE", "D3")))
    assert result.status == "TERMINAL_CLAIM" and result.terminal_claim == "FAILED_CONSUMED"
    corrupt(raw(*events, entry("SET_ASIDE_DONE", "D3"), entry("SET_ASIDE_BEGIN", "D3")))


@pytest.mark.parametrize("k", [1, 2, 3])
def test_fault_cannot_resume_and_can_only_be_terminated(k):
    events = prefix(k - 1) + [entry("BEGIN", f"D{k}"), entry("DURABILITY_FAULT", f"D{k}")]
    assert observed(raw(*events)).status == "BLOCKED_DURABILITY"
    corrupt(raw(*events, entry("BEGIN", f"D{k}")))
    corrupt(raw(*events, entry("INTERRUPTED_RECOVERED", f"D{k}", boot=COLD, data={"result": "PRESENT"})))
    ending = entry("ABANDONED") if k == 1 else entry("FAILED_CONSUMED", code="OPERATOR_TERMINATED")
    assert observed(raw(*events, entry("TERMINATED", code="OPERATOR_TERMINATED"), ending)).status == "TERMINAL_CLAIM"


def test_quarantine_and_set_aside_faults():
    quarantine = prefix(2) + [entry("BEGIN", "D3"), entry("INTERRUPTED_RECOVERED", "D3", boot=COLD,
                              data={"result": "PARTIAL"}), entry("QUARANTINE_BEGIN", "D3")]
    for events, terminal in [(quarantine, None), (failed_d3() + [entry("SET_ASIDE_BEGIN", "D3")], "FAILED_CONSUMED")]:
        events += [entry("DURABILITY_FAULT", "D3")]
        result = observed(raw(*events))
        assert result.status == "BLOCKED_DURABILITY" and result.terminal_claim == terminal
        assert result.d3_started
        corrupt(raw(*events, entry("SET_ASIDE_DONE", "D3")))
        corrupt(raw(*events, entry("QUARANTINE_DONE", "D3")))


def ack(fragment, **changes):
    return entry("TORN_TAIL_ACKNOWLEDGED", data={"fragment_sha256": hashlib.sha256(fragment).hexdigest()}, **changes)


def test_torn_tail_and_acknowledgement_do_not_create_transition():
    fragment = b'{"broken":'
    assert observed(raw(*prefix()) + fragment).status == "TORN_TAIL"
    assert observed(raw(*prefix()) + fragment + b"\n" + raw(ack(fragment))).status == "OPEN"
    preamble = fragment + b"\n" + raw(ack(fragment))
    result = observed(preamble)
    assert result.status == "PREPARATION_INCOMPLETE" and result.operation_sha256 is None
    assert observed(preamble + raw(*prefix())).status == "OPEN"
    corrupt(raw(*prefix()) + fragment + b"\n" + raw(ack(b"different")))
    corrupt(raw(*prefix(), ack(fragment)))
    # A canonical complete event cannot be erased by an acknowledgement.
    full = f.canonical(entry("BEGIN", "D1"))
    corrupt(raw(*prefix()) + full + b"\n" + raw(ack(full)))
    assert observed(full).status == "TORN_TAIL"  # no newline, never acted on


def test_corruption_after_terminal_and_torn_terminal_are_not_usable():
    completed = raw(*prefix(3), entry("COMMITTED"))
    corrupt(completed + b"bad\n")
    result = observed(completed + b"bad")
    assert result.status == "TORN_TAIL" and result.terminal_claim is None
    assert observed(b"").status == "EMPTY"
    for value in (None, "", bytearray(), Path("missing")):
        assert project_log(value).code == "INVALID_INPUT"


@pytest.mark.parametrize("change", [{"extra": 1}, {"attempt": True}, {"attempt": 0}, {"current_root_version": False},
                                   {"operation_sha256": "A" * 64}, {"schema": "future/1"}, {"boot_id": "bad"},
                                   {"event": []}, {"step": []}, {"code": "secret submitted text"}, {"data": None}])
def test_closed_entry_formats(change):
    corrupt(raw({**entry("PREPARED"), **change}))


@pytest.mark.parametrize("key", sorted(f.ENTRY_KEYS))
def test_missing_entry_field(key):
    value = entry("PREPARED")
    del value[key]
    corrupt(raw(value))


@pytest.mark.parametrize("key", sorted(f.OP_KEYS))
def test_missing_operation_field(key):
    op = operation()
    del op[key]
    # Digest remains syntactically valid; wrapper validation must refuse.
    e = entry("PREPARED", data={"operation": op})
    corrupt(raw(e))


@pytest.mark.parametrize("bad", [b'{} ', b'{"a":1,"a":1}', b'{"x":1.0}', b'{"x":NaN}', b'{"x":Infinity}',
                               b'\xef\xbb\xbf{}', b'{"x":"\\ud800"}', b'\xff', b'{"x":-0}', b'{"x":1e9}',
                               b'[' * 33 + b']' * 33, b'{"x":' + b'1' * 129 + b'}'])
def test_strict_canonical_decoder(bad):
    with pytest.raises(f.FormatError):
        f.loads(bad)
    corrupt(bad + b"\n")


def test_nesting_inside_strings_and_integer_boundary():
    value = {"brackets": "[" * 40 + '\\"' + "]" * 40, "integer": int("9" * 128)}
    assert f.loads(f.canonical(value)) == value


def test_identity_root_rotation_and_record_hash():
    op = operation()
    changed = entry("BEGIN", "D1", current_root_sha256="8" * 64, current_root_version=2)
    assert observed(raw(*prefix(), changed)).operation_sha256 == f.digest(op)
    corrupt(raw(*prefix(), entry("BEGIN", "D1", operation_sha256="9" * 64)))
    corrupt(raw(*prefix(3), entry("COMMITTED", data={"record_sha256": "0" * 64})))
    e = entry("PREPARED")
    e["data"]["operation"]["budget"]["runs"] = 2
    corrupt(raw(e))


def test_subject_order_duplicates_and_bindings():
    op = operation()
    one = {"role": "DECISION", "kind": "colony-lab.individual/0",
           "subject": {"agent_id": "a" * 64, "agent_spec_id": "b" * 64},
           "record_sha256": "c" * 64, "envelope_sha256": "d" * 64}
    two = copy.deepcopy(one)
    two["subject"]["agent_id"] = "e" * 64
    op["items"] = [one, two]
    assert observed(raw(entry("PREPARED", op=op))).status == "OPEN"
    for items in ([two, one], [one, one], [{**one, "subject": {"agent_id": "a" * 64}}]):
        op["items"] = items
        corrupt(raw(entry("PREPARED", op=op)))
    op = operation()
    op["birth_plan"]["record"]["agent_id"] = "f" * 64
    corrupt(raw(entry("PREPARED", op=op)))


# Generate forbidden event/state pairs from independently enumerated observation prefixes.
STATES = {
    "EMPTY": [], "OPEN_D0": prefix(), "PENDING_D1": prefix() + [entry("BEGIN", "D1")],
    "OPEN_D1": prefix(1), "OPEN_D2": prefix(2), "OPEN_D3": prefix(3),
    "COMMITTED": prefix(3) + [entry("COMMITTED")], "FAILED": failed_d3(),
}
FORBIDDEN = {
    "EMPTY": [("BEGIN", "D1"), ("DONE", "D1"), ("ABANDONED", None), ("COMMITTED", None)],
    "OPEN_D0": [("BEGIN", "D2"), ("DONE", "D1"), ("COMMITTED", None), ("QUARANTINE_BEGIN", "D3")],
    "PENDING_D1": [("BEGIN", "D1"), ("DONE", "D2"), ("ABANDONED", None), ("COMMITTED", None)],
    "OPEN_D1": [("BEGIN", "D1"), ("BEGIN", "D3"), ("REFUSED", None), ("COMMITTED", None)],
    "OPEN_D2": [("BEGIN", "D2"), ("DONE", "D3"), ("COMMITTED", None), ("ABANDONED", None)],
    "OPEN_D3": [("BEGIN", "D3"), ("QUARANTINE_BEGIN", "D3"), ("ABANDONED", None)],
    "COMMITTED": [("PREPARED", None), ("COMMITTED", None), ("SET_ASIDE_BEGIN", "D3"), ("TERMINATED", None)],
    "FAILED": [("PREPARED", None), ("BEGIN", "D3"), ("SET_ASIDE_DONE", "D3")],
}


@pytest.mark.parametrize("state,event,step", [(s, e, k) for s, pairs in FORBIDDEN.items() for e, k in pairs])
def test_forbidden_pairs(state, event, step):
    corrupt(raw(*STATES[state], entry(event, step)))


def test_file_wide_reserve_and_size_bounds():
    events = prefix(1)
    # 3 + 26*2 =55; normal lines still legal up to position56.
    for _ in range(26):
        events += [entry("BEGIN", "D2"), entry("BEGIN_CANCELLED", "D2", code="LAB_STOPPED")]
    assert len(events) == 55
    assert observed(raw(*events)).status == "OPEN"
    corrupt(raw(*events, entry("BEGIN", "D2"), entry("BEGIN_CANCELLED", "D2")))
    result = observed(raw(*events, entry("TERMINATED", code="OPERATOR_TERMINATED"),
                          entry("FAILED_CONSUMED", code="OPERATOR_TERMINATED")))
    assert result.terminal_claim == "FAILED_CONSUMED"
    corrupt(b"x" * f.MAX_LOG + b"x")
    corrupt(b"\n" * 65)
    corrupt(b"x" * f.MAX_LINE + b"\n")


def test_purity_imports_and_no_external_calls():
    root = Path(__file__).resolve().parents[2] / "colony_admission"
    allowed = {"hashlib", "json", "re", "dataclasses", "formats", "oplog", "external_evidence"}
    forbidden = {"open", "exec", "eval", "__import__", "getattr", "setattr", "globals", "locals"}
    for path in root.glob("*.py"):
        if path.name == "observer.py":  # Separate IO boundary; pure modules cannot import it.
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(x.name in allowed for x in node.names)
            if isinstance(node, ast.ImportFrom):
                if node.module is None:
                    assert node.level == 1 and [alias.name for alias in node.names] == ["formats"]
                else:
                    assert node.module in allowed
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden
    assert list(inspect.signature(project_log).parameters) == ["raw"]


def test_real_registrar_plan_is_carried_without_semantic_authority(tmp_path):
    from tests.colony_registrar.test_registrar import Colony, _spec
    from tests.colony_lab import builders
    from colony_lab import lineage
    c = Colony(tmp_path)
    child = _spec("reader_child")
    qualification = builders.qualification(c.founder)
    admission = c.admission(child, c.founder["agent_id"], qualification=qualification)
    plan = c.registrar.prepare(c.founder["agent_id"], child, parent_qualification=qualification,
                               admission=admission, lab_permissions=["DIAGNOSTIC_PRODUCE"],
                               budget=dict(builders.BUDGET),
                               declared_diff=lineage.spec_diff(c.founder_spec, child)).data
    op = operation(child_agent_id=child["agent_id"], child_agent_spec_id=child["agent_spec_id"],
                   parent_agent_id=c.founder["agent_id"], policy_sha256=plan["policy_sha256"], birth_plan=plan,
                   budget=plan["record"]["budget"], permissions=plan["record"]["lab_permissions"],
                   declared_diff=admission["declared_diff"])
    for key in ("qualification", "admission"):
        op["presented"][key]["record_sha256"] = f.digest(plan[key])
    assert observed(raw(entry("PREPARED", op=op))).status == "OPEN"


def test_limits_are_not_acknowledgeable_noncanonical_fragments():
    for fragment in (b'[' * 33 + b']' * 33, b'{"x":' + b'1' * 129 + b'}'):
        assert corrupt(raw(*prefix()) + fragment + b"\n" + raw(ack(fragment))).code == "FORMAT_LIMIT_REACHED"


def test_future_schema_is_not_acknowledgeable():
    fragment = f.canonical({**entry("BEGIN", "D1"), "schema": "future/1"})
    corrupt(raw(*prefix()) + fragment + b"\n" + raw(ack(fragment)))


def test_full_reserve_counts_across_attempts_and_fragments():
    events = prefix(2)
    for _ in range(25):
        events += [entry("BEGIN", "D3"), entry("BEGIN_CANCELLED", "D3", code="LAB_STOPPED")]
    assert len(events) == 55
    events += [entry("TERMINATED", code="OPERATOR_TERMINATED"),
               entry("FAILED_CONSUMED", code="OPERATOR_TERMINATED"),
               entry("SET_ASIDE_BEGIN", "D3"), entry("SET_ASIDE_DONE", "D3")]
    data = raw(*events)
    for fragment in (b'{"first":', b'{"second":'):
        data += fragment + b"\n" + raw(ack(fragment))
    # 59 events +4 physical fragment/ack lines =63; a final torn tail fits at64.
    assert observed(data).physical_lines == 63
    result = observed(data + b'{"third":')
    assert result.status == "TORN_TAIL" and result.physical_lines == 64
    corrupt(data + b'{"third":\n' + raw(ack(b'{"third":')))
    corrupt(data + raw(entry("PREPARED", op=operation(attempt=2))))


def test_projection_does_not_retain_caller_mutable_records():
    op = operation()
    result = observed(raw(entry("PREPARED", op=op)))
    op["attempt"] = 99
    assert result.attempt == 1 and result.history[0].attempt == 1


def test_no_reverse_imports_from_existing_components():
    root = Path(__file__).resolve().parents[2]
    for package in ("colony_lab", "colony_pilot", "colony_trust", "colony_registrar", "sentinel_activity"):
        for path in (root / package).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    assert all(not x.name.startswith("colony_admission") for x in node.names)
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("colony_admission")


@pytest.mark.parametrize("step", ["D2", "D3"])
def test_public_recovery_result_cannot_collapse_absent_and_partial(step):
    k = int(step[1])
    events = prefix(k - 1) + [entry("BEGIN", step)]
    results = []
    for classification in ("ABSENT", "PARTIAL"):
        value = observed(raw(*events, entry("INTERRUPTED_RECOVERED", step, boot=COLD,
                                            data={"result": classification})))
        assert value.recovery_step == step and value.recovery_result == classification
        assert value.last_completed_source == "DONE"
        results.append(value)
    assert results[0] != results[1]


def test_completed_source_and_quarantine_marker_lifecycle():
    events = prefix() + [entry("BEGIN", "D1"), entry("INTERRUPTED_RECOVERED", "D1", boot=COLD,
                        data={"result": "PRESENT"})]
    assert observed(raw(*events)).last_completed_source == "RECOVERY_PRESENT"
    value = observed(raw(*events, entry("BEGIN", "D2")))
    assert value.last_completed_source == "RECOVERY_PRESENT" and value.recovery_result is None
    events = prefix(2) + [entry("BEGIN", "D3"), entry("INTERRUPTED_RECOVERED", "D3", boot=COLD,
                         data={"result": "PARTIAL"}), entry("QUARANTINE_BEGIN", "D3")]
    assert observed(raw(*events)).recovery_result == "PARTIAL"
    assert observed(raw(*events, entry("QUARANTINE_DONE", "D3"))).recovery_result is None


def test_visible_budget_binding_cannot_alias_boolean_to_integer():
    op = operation()
    op["birth_plan"]["record"]["budget"]["runs"] = True
    corrupt(raw(entry("PREPARED", op=op)))
