"""External bytes produce immutable structural claims, never machine authority."""

import dataclasses
import hashlib
import inspect

import pytest

from colony_admission import external_evidence as e
from colony_admission import formats as f
from colony_admission import project_fault_log, project_installed_trust
from tests.colony_trust.keys import LAB, root

OP, CHILD, FAULT_BOOT = "a" * 64, "b" * 64, "11111111-1111-1111-1111-111111111111"


def raw(*entries):
    return b"".join(f.canonical(x) + b"\n" for x in entries)


def target(resource="OPERATION_LOG", kind="FILE", path=None):
    path = CHILD + ".log" if path is None and resource == "OPERATION_LOG" else "" if path is None else path
    return {"resource": resource, "object_kind": kind, "relative_path": path}


def fault(*, schema="colony-admission.fault-entry/1", **changes):
    return {"schema": schema, "lab_id": LAB, "scope": "OPERATION", "child_agent_id": CHILD,
            "operation_sha256": OP, "attempt": 1, "boot_id": FAULT_BOOT, "event": "FAULT", "step": "D3",
            "phase": "D3", "code": "DURABILITY_UNKNOWN",
            "data": {"origin": "CONTROLLER", "failure": "WRITE", "target": target()}, **changes}


def observation(count=1):
    entry = {"ledger_schema": "colony-trust.consumed/1", "issuer_id": "fixture-issuer",
             "envelope_id": "c" * 64, "envelope_sha256": "d" * 64, "operation_sha256": OP}
    return {"inspection_schema": "colony-trust.operation-inspection/0", "status": "OPERATION_ENTRY_PRESENT" if count else "NO_OPERATION_ENTRY",
            "operation_sha256": OP, "operation_entries": count, "legacy_entries": 0, "ledger_entries": count,
            "ledger_sha256": "e" * 64, "entry": entry if count else None, "failures": [], "accepted": False,
            **dict.fromkeys(("authenticity", "authorization", "completeness", "provenance", "durability"), "NOT_EVALUATED")}


def terminate(source=None, count=1, version=1, **changes):
    source = fault() if source is None else source
    obs = observation(count)
    finding = {"status": obs["status"] if version else "CONSUMED_BY_OPERATION" if count else "ABSENT_IN_VALID_LEDGER",
               "operation_entries": count, "observation_sha256": f.digest(obs)}
    if version:
        finding.update(inspection_schema=obs["inspection_schema"], observation=obs)
    return fault(schema=f"colony-admission.fault-entry/{version}", event="TERMINATED_EXTERNALLY", step=None,
                 phase="TERMINATE", code="OPERATOR_TERMINATED",
                 data={"fault_sha256": f.digest(source), "ledger_finding": finding}, **changes)


def aside(term, done=False, **changes):
    return fault(event="SET_ASIDE_DONE" if done else "SET_ASIDE_BEGIN", phase="SET_ASIDE", step="D3",
                 code="OPERATOR_SET_ASIDE", data={"termination_sha256": f.digest(term)}, **changes)


def projection(data, lab=LAB):
    result = project_fault_log(data, lab)
    assert result.accepted is False
    assert result.provenance == result.durability == result.external_facts == "NOT_EVALUATED"
    return result


def corrupt(data, lab=LAB):
    result = projection(data, lab)
    assert result.status == "CORRUPT", result
    assert not result.entry_bytes and not result.fault_claims and not result.termination_claims
    assert result.ledger_fault_claim is None and result.trust_fault_claim is None
    assert result.raw_sha256 is None


def installed(value=None, floor=1):
    value = root() if value is None else value
    pin = f.digest(value)
    policy = {"schema": "colony-admission.installed-trust/0", "lab_id": LAB, "root": value,
              "root_sha256": pin, "pin": pin, "minimum_version": floor}
    history = {"root_version": value["root_version"], "root_sha256": pin, "pin": pin, "minimum_version": floor}
    return policy, history


def trust_projection(policy, history, lab=LAB):
    result = project_installed_trust(policy, history, lab)
    assert result.accepted is False and result.provenance == result.durability == result.external_facts == "NOT_EVALUATED"
    return result


def unavailable(policy, history, lab=LAB):
    result = trust_projection(policy, history, lab)
    assert result.status == "UNAVAILABLE" and result.code == "TRUST_CURRENT_UNAVAILABLE"
    assert not result.history and result.policy_bytes is None and result.root_sha256 is None
    assert result.policy_sha256 is None and result.history_sha256 is None


def test_valid_fault_is_immutable_claim_not_machine_health():
    data = raw(fault())
    result = projection(data)
    assert result.status == "STRUCTURAL_ONLY" and len(result.fault_claims) == 1
    assert result.raw_sha256 == hashlib.sha256(data).hexdigest()
    assert result.entry_bytes == (f.canonical(fault()),)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.fault_claims[0].target.relative_path = "other"
    empty = projection(b"")
    assert empty.status == "EMPTY" and empty.ledger_fault_claim is False
    corrupt(b"bad\n")  # not an empty/healthy prefix


@pytest.mark.parametrize("version", [0, 1])
@pytest.mark.parametrize("count", [0, 1])
def test_external_termination_versions_are_distinct_historical_claims(version, count):
    source = fault(schema=f"colony-admission.fault-entry/{version}")
    term = terminate(source, count=count, version=version)
    result = projection(raw(source, term))
    assert result.status == "STRUCTURAL_ONLY" and len(result.fault_claims) == 1
    claim = result.termination_claims[0]
    assert claim.classification == ("FAILED_CONSUMED" if count else "ABANDONED")
    assert claim.evidence == ("EMBEDDED_HISTORICAL" if version else "REFERENCE_UNRESOLVED")
    assert claim.fault_sha256 == f.digest(source)


def test_embedded_snapshot_is_historical_not_compared_to_current_ledger():
    source, term = fault(), terminate()
    term["data"]["ledger_finding"]["observation"]["ledger_sha256"] = "0" * 64
    term["data"]["ledger_finding"]["observation_sha256"] = f.digest(term["data"]["ledger_finding"]["observation"])
    assert projection(raw(source, term)).status == "STRUCTURAL_ONLY"
    assert list(inspect.signature(project_fault_log).parameters) == ["raw", "lab_id"]


@pytest.mark.parametrize("key,value", [("accepted", True), ("provenance", "PASS"), ("durability", "PASS"),
                                      ("completeness", "PASS"), ("operation_sha256", "f" * 64),
                                      ("operation_entries", True), ("ledger_entries", 0), ("legacy_entries", -1),
                                      ("ledger_sha256", "bad"), ("failures", ["ERROR"]), ("extra", 1)])
def test_embedded_observation_must_be_closed_consistent_and_unprivileged(key, value):
    source, term = fault(), terminate()
    finding = term["data"]["ledger_finding"]
    finding["observation"][key] = value
    finding["observation_sha256"] = f.digest(finding["observation"])
    corrupt(raw(source, term))


@pytest.mark.parametrize("where", ["digest", "status", "count", "schema", "missing", "entry"])
def test_finding_bindings_and_versions(where):
    source, term = fault(), terminate()
    finding = term["data"]["ledger_finding"]
    if where == "digest":
        finding["observation_sha256"] = "f" * 64
    elif where == "status":
        finding["status"] = "CONSUMED_BY_OPERATION"
    elif where == "count":
        finding["operation_entries"] = 0
    elif where == "schema":
        term["schema"] = "colony-admission.fault-entry/0"
    elif where == "missing":
        del finding["observation"]
    else:
        finding["observation"]["entry"]["operation_sha256"] = "f" * 64
        finding["observation_sha256"] = f.digest(finding["observation"])
    corrupt(raw(source, term))


@pytest.mark.parametrize("status", ["LEDGER_MISSING", "LEDGER_BUSY", "CONFLICT", "LEGACY_AMBIGUITY", "LEDGER_CORRUPT"])
def test_unknown_or_ambiguous_ledger_status_cannot_be_a_terminal_claim(status):
    term = terminate()
    term["data"]["ledger_finding"]["status"] = status
    corrupt(raw(fault(), term))


def test_external_termination_requires_prior_exact_fault_and_identity():
    source, term = fault(), terminate()
    corrupt(raw(term))
    corrupt(raw(source, term, term))
    for key, value in (("child_agent_id", "f" * 64), ("attempt", 2), ("operation_sha256", "f" * 64)):
        changed = {**term, key: value}
        corrupt(raw(source, changed))
    source["data"]["target"] = target("LEDGER", path="")
    corrupt(raw(source, terminate(source)))


def test_set_aside_brackets_preserve_fault_and_terminal():
    source, term = fault(), terminate()
    begin, done = aside(term), aside(term, done=True)
    result = projection(raw(source, term, begin))
    assert result.pending_set_aside == (OP,)
    result = projection(raw(source, term, begin, done))
    assert not result.pending_set_aside and len(result.fault_claims) == len(result.termination_claims) == 1
    for entries in ((source, term, done), (source, begin), (source, term, begin, begin), (source, term, begin, done, done)):
        corrupt(raw(*entries))
    source = fault(step="D2", phase="D2")
    term = terminate(source)
    corrupt(raw(source, term, aside(term)))


def test_fault_during_set_aside_never_becomes_done_or_cleared():
    source, term = fault(), terminate()
    action_fault = fault(phase="SET_ASIDE", data={"origin": "CONTROLLER", "failure": "FSYNC",
                                               "target": target("QUARANTINE_DIRECTORY", "DIRECTORY", "")})
    entries = (source, term, aside(term), action_fault)
    result = projection(raw(*entries))
    assert result.pending_set_aside == (OP,) and len(result.fault_claims) == 2
    corrupt(raw(*entries, aside(term, done=True)))
    corrupt(raw(*entries, aside(term)))


@pytest.mark.parametrize("resource,path", [("INDIVIDUALS_DIRECTORY", ""), ("HOME_DIRECTORY", CHILD),
                                          ("QUARANTINE_DIRECTORY", "")])
def test_directory_faults_block_later_set_aside(resource, path):
    source, term = fault(), terminate()
    directory_fault = fault(data={"origin": "CONTROLLER", "failure": "FSYNC",
                                 "target": target(resource, "DIRECTORY", path)})
    corrupt(raw(source, directory_fault, term, aside(term)))


def test_ledger_fault_survives_external_termination():
    source, term = fault(), terminate()
    ledger_fault = fault(phase="D1", step="D1", data={"origin": "TRUST", "failure": "CONSUMPTION_IO_UNKNOWN",
                                                    "target": target("LEDGER", path="")})
    result = projection(raw(source, ledger_fault, term))
    assert result.ledger_fault_claim is True and len(result.fault_claims) == 2


def test_lab_fault_never_invents_a_birth_and_supervisor_never_a_path():
    lab_fault = fault(scope="LAB", child_agent_id=None, operation_sha256=None, attempt=None, phase="TRUST_INSTALL",
                      step=None, data={"origin": "CONTROLLER", "failure": "FSYNC",
                                       "target": target("TRUST_DIRECTORY", "DIRECTORY", "")})
    result = projection(raw(lab_fault))
    assert result.trust_fault_claim is True and result.fault_claims[0].operation_sha256 is None
    corrupt(raw({**lab_fault, "scope": "OPERATION"}))
    corrupt(raw({**fault(), "phase": "TRUST_INSTALL", "step": None}))
    supervisor = fault(data={"origin": "SUPERVISOR", "failure": "ADMIT", "target": None})
    assert projection(raw(supervisor)).fault_claims[0].target is None
    supervisor["data"]["target"] = target()
    corrupt(raw(supervisor))


@pytest.mark.parametrize("path", ["/root", "../x", "a/../x", "a//x", ".", "a\\x", "x\x00y", "x\ny"])
def test_path_labels_never_escape_their_bound_namespace(path):
    source = fault(data={"origin": "CONTROLLER", "failure": "WRITE", "target": target(path=path)})
    corrupt(raw(source))


@pytest.mark.parametrize("resource,kind,path", [("OPERATION_LOG_DIRECTORY", "DIRECTORY", ""),
    ("LEDGER_DIRECTORY", "DIRECTORY", ""), ("ADMISSION_DIRECTORY", "DIRECTORY", ""),
    ("ENVELOPE_DIRECTORY", "DIRECTORY", ""), ("HOME_ENTRY", "DIRECTORY", CHILD + "/tasks")])
def test_exact_parent_directory_claims_are_not_file_claims(resource, kind, path):
    source = fault(data={"origin": "CONTROLLER", "failure": "FSYNC", "target": target(resource, kind, path)})
    assert projection(raw(source)).fault_claims[0].target.object_kind == "DIRECTORY"
    source["data"]["target"]["object_kind"] = "FILE"
    if resource != "HOME_ENTRY":
        corrupt(raw(source))


@pytest.mark.parametrize("key", sorted(e.FAULT_KEYS))
def test_closed_fault_entries_require_every_field(key):
    source = fault()
    del source[key]
    corrupt(raw(source))


@pytest.mark.parametrize("changes", [{"extra": 1}, {"schema": "future/9"}, {"event": []}, {"attempt": True},
                                      {"lab_id": "other-lab"}, {"phase": "D2"}, {"code": "raw exception"}])
def test_wrong_fault_fields(changes):
    corrupt(raw({**fault(), **changes}))


@pytest.mark.parametrize("tail", [b'bad\n', b'{"torn":', b'{ }\n', b'\xff\n', b'{}\n'])
def test_fault_corruption_after_terminal_never_exposes_a_good_prefix(tail):
    corrupt(raw(fault(), terminate()) + tail)


def test_no_ack_exception_in_external_log():
    corrupt(raw(fault()) + b'{"torn":\n' + raw({"event": "TORN_TAIL_ACKNOWLEDGED"}))


def test_trust_policy_matches_only_complete_latest_history_head():
    policy, head = installed()
    result = trust_projection(f.canonical(policy), raw(head))
    assert result.status == "STRUCTURAL_MATCH" and result.root_version == 1
    assert result.root_sha256 == policy["pin"] and result.policy_bytes == f.canonical(policy)
    assert result.history_sha256 == hashlib.sha256(raw(head)).hexdigest()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.history[0].minimum_version = 0
    next_policy, next_head = installed(root(version=2))
    unavailable(f.canonical(policy), raw(head, next_head))
    assert trust_projection(f.canonical(next_policy), raw(head, next_head)).status == "STRUCTURAL_MATCH"


@pytest.mark.parametrize("history_change", [{"root_version": True}, {"minimum_version": True}, {"minimum_version": 2},
                                           {"pin": "0" * 64}, {"extra": 1}, {"root_sha256": "BAD"}])
def test_history_lexical_closure_and_pin(history_change):
    policy, head = installed()
    unavailable(f.canonical(policy), raw({**head, **history_change}))


def test_history_version_and_floor_are_monotone_not_rotation_certification():
    policy, head = installed(root(version=2), floor=2)
    unavailable(f.canonical(policy), raw(head, head))
    next_policy, next_head = installed(root(version=3), floor=1)
    unavailable(f.canonical(next_policy), raw(head, next_head))
    unavailable(f.canonical(policy), raw(head, {**head, "root_version": 1}))
    # Invalid cryptographic root still parses structurally, never becomes check_root PASS.
    bad = root()
    bad["issuers"][0]["keys"][0]["public_key"] = "0" * 64
    policy, head = installed(bad)
    assert trust_projection(f.canonical(policy), raw(head)).status == "STRUCTURAL_MATCH"
    from colony_trust import trust
    with pytest.raises(trust.TrustError):
        trust.check_root(bad, pin_sha256=policy["pin"], minimum_version=1, lab_id=LAB)


@pytest.mark.parametrize("key", sorted(e.POLICY_KEYS))
def test_policy_requires_closed_wrapper(key):
    policy, head = installed()
    del policy[key]
    unavailable(f.canonical(policy), raw(head))


@pytest.mark.parametrize("bad", [b'', b'{}\n', b'bad', b'{ }', b'\xff', b'{"x":1.0}', b'{"x":1,"x":1}'])
def test_bad_policy_or_history_never_falls_back(bad):
    policy, head = installed()
    unavailable(bad, raw(head))
    unavailable(f.canonical(policy), bad)


@pytest.mark.parametrize("changes", [{"environment": "LIVE"}, {"lab_id": "other-lab"}, {"root_version": True},
                                      {"extra": "private-key"}, {"issuers": []}])
def test_root_environment_label_and_nested_closure(changes):
    policy, head = installed({**root(), **changes})
    unavailable(f.canonical(policy), raw(head))


def test_unknown_private_key_fields_are_not_carried_as_opaque_material():
    value = root()
    value["issuers"][0]["keys"][0]["private_key"] = "fixture-not-a-secret"
    policy, head = installed(value)
    unavailable(f.canonical(policy), raw(head))


def test_input_types_and_expected_lab_are_never_paths_or_authority():
    policy, head = installed()
    for value in (None, "", bytearray(), {}):
        corrupt(value)
        unavailable(value, raw(head))
        unavailable(f.canonical(policy), value)
    corrupt(raw(fault()), "other-lab")
    corrupt(raw(fault()), None)
    unavailable(f.canonical(policy), raw(head), "other-lab")
    assert list(inspect.signature(project_installed_trust).parameters) == ["policy_raw", "history_raw", "lab_id"]


def test_fault_and_trust_limits_are_fail_closed(monkeypatch):
    source = raw(fault())
    monkeypatch.setattr(e, "FAULT_MAX_LINES", 1)
    assert projection(source).status == "STRUCTURAL_ONLY"
    corrupt(source + source)
    monkeypatch.setattr(e, "FAULT_LINE_BYTES", len(source) - 1)
    corrupt(source)
    policy, head = installed()
    monkeypatch.setattr(e, "HISTORY_MAX_LINES", 1)
    unavailable(f.canonical(policy), raw(head, head))
    monkeypatch.setattr(e, "HISTORY_LINE_BYTES", len(raw(head)) - 1)
    unavailable(f.canonical(policy), raw(head))
    monkeypatch.setattr(e, "HISTORY_LINE_BYTES", 1024)
    monkeypatch.setattr(e, "POLICY_MAX_BYTES", len(f.canonical(policy)) - 1)
    unavailable(f.canonical(policy), raw(head))


def test_embedded_snapshots_and_all_public_output_are_detached():
    source, term = fault(), terminate()
    result = projection(raw(source, term))
    term["data"]["ledger_finding"]["observation"]["entry"]["operation_sha256"] = "0" * 64
    assert result.termination_claims[0].operation_sha256 == OP
    assert result.entry_bytes[-1] != f.canonical(term)
    policy, head = installed()
    projected = trust_projection(f.canonical(policy), raw(head))
    policy["root"]["environment"] = "LIVE"
    assert projected.policy_bytes != f.canonical(policy)


def test_set_aside_fault_preserves_normal_context_but_checks_external_brackets():
    action_fault = fault(phase="SET_ASIDE", data={"origin": "CONTROLLER", "failure": "WRITE", "target": target()})
    result = projection(raw(action_fault))
    assert result.status == "STRUCTURAL_ONLY" and len(result.fault_claims) == 1
    assert not result.pending_set_aside and not result.termination_claims
    corrupt(raw(fault(), terminate(), action_fault))


def test_faulty_child_cannot_be_rehabilitated_as_another_operation():
    source, term = fault(), terminate()
    new_op = fault(operation_sha256="f" * 64, attempt=2)
    corrupt(raw(source, term, new_op))
    # A separate child/operation is structurally possible; global restrictions remain claims.
    new_child = "c" * 64
    new_op["child_agent_id"] = new_child
    new_op["data"]["target"]["relative_path"] = new_child + ".log"
    result = projection(raw(source, term, new_op))
    assert result.status == "STRUCTURAL_ONLY" and len(result.fault_claims) == 2



def test_normal_set_aside_directory_fault_is_sticky_without_external_termination():
    normal_fault = fault(phase="SET_ASIDE", data={"origin": "CONTROLLER", "failure": "FSYNC",
                                               "target": target("HOME_DIRECTORY", "DIRECTORY", CHILD)})
    result = projection(raw(normal_fault))
    assert result.status == "STRUCTURAL_ONLY" and result.fault_claims[0].target.resource == "HOME_DIRECTORY"
    assert result.fault_claims[0].phase == "SET_ASIDE" and not result.termination_claims
    source, term = fault(), terminate()
    corrupt(raw(normal_fault, source, term, aside(term)))


def test_exact_external_limits_are_inclusive(monkeypatch):
    source = raw(fault())
    monkeypatch.setattr(e, "FAULT_MAX_LINES", 1)
    monkeypatch.setattr(e, "FAULT_LINE_BYTES", len(source))
    assert projection(source).status == "STRUCTURAL_ONLY"
    policy, head = installed()
    pbytes, hbytes = f.canonical(policy), raw(head)
    monkeypatch.setattr(e, "POLICY_MAX_BYTES", len(pbytes))
    monkeypatch.setattr(e, "HISTORY_MAX_LINES", 1)
    monkeypatch.setattr(e, "HISTORY_LINE_BYTES", len(hbytes))
    assert trust_projection(pbytes, hbytes).status == "STRUCTURAL_MATCH"
