"""3C-1 private own-proof tranche, detached LAB_TEST inputs, no scan authority."""

import ast
import dataclasses
import inspect

import pytest

from colony_admission import _attestation_core as c
from colony_admission import _population_core as pc
from colony_admission import formats as f
from colony_admission._population_inventory import HomeInput
from colony_lab import lineage
from colony_trust import trust
from tests.colony_admission import test_attestation_core as helpers
from tests.colony_admission import test_attestation_projection as projection
from tests.colony_lab import builders as b
from tests.colony_trust.keys import ADMITTER, LAB, OPERATOR, REVIEWER, pin

complete = projection.complete


def snapshot(op, env, terminal="COMMITTED"):
    row = {"status": "OPERATION_ENTRY_PRESENT", "operation_sha256": f.digest(op), "operation_entries": 1,
        "entry": {"ledger_schema": trust.OPERATION_LEDGER_SCHEMA, "issuer_id": env["issuer_id"],
                  "envelope_id": env["envelope_id"], "envelope_sha256": f.digest(env),
                  "operation_sha256": f.digest(op)}}
    return f.canonical(op), terminal, f.canonical(row)


@pytest.fixture
def population(complete):
    op = c.operation(complete["op_bytes"])
    parent = complete["nodes"][0]
    child, plan = op["child_agent_id"], op["birth_plan"]
    env = complete["envelopes"]
    individual = helpers.signed(plan["record"], c.IND, OPERATOR, label="child", key_label="operator-1")
    homes = (HomeInput(parent.agent_id, parent.record_bytes, parent.spec_bytes,
                       individual_envelope=env[parent.agent_id + "/individual"]),
             HomeInput(child, f.canonical(plan["record"]), f.canonical(plan["child_spec"]),
                       f.canonical(plan["qualification"]), f.canonical(plan["admission"]), complete["statement_raw"],
                       f.canonical(individual), env[child + "/admission"], env[child + "/qualification"],
                       env[child + "/statement"]))
    return dict(homes=homes, snapshots=(snapshot(op, c.decode(env[child + "/admission"])),),
        root_raw=complete["root_bytes"], root_pin=complete["root_pin"], minimum_version=1, lab_id=LAB,
        policy_raw=complete["policy_bytes"], policy_pin=complete["policy_pin"], artifacts=complete["artifacts"],
        subject_digest=complete["subject_digest"], evaluator_digest=complete["evaluator_digest"])


def child_proof(population):
    return next(x for x in pc.own_proofs(**population) if x.agent_id == population["homes"][1].agent_id)


def alter_child(population, **values):
    population["homes"] = (population["homes"][0], dataclasses.replace(population["homes"][1], **values))


def test_complete_own_proofs_do_not_claim_population_or_filiation(population):
    result = pc.own_proofs(**population)
    assert all(x.classification == "AUTHENTICATED" and x.counted == "INCLUDED" for x in result)
    child = child_proof(population)
    assert child.birth_proof == child.individual_proof == child.scientific_bindings == "PASS"
    assert child.completeness == child.authorization == child.filiation == pc.NE
    assert child.accepted is False and child.execution_restriction is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        child.accepted = True
    population["artifacts"].clear()
    assert child.scientific_bindings == "PASS"  # result retains no mutable inputs


def test_absent_individual_only_is_awaiting(population):
    alter_child(population, individual_envelope=None)
    result = child_proof(population)
    assert result.classification == "AWAITING_INDIVIDUAL_ATTESTATION" and result.counted == "INCLUDED"
    assert result.individual_proof == pc.NE and result.birth_proof == "PASS"


@pytest.mark.parametrize("field", ["record_bytes", "spec_bytes", "qualification_bytes", "admission_bytes",
    "statement_bytes", "admission_envelope", "qualification_envelope", "statement_envelope"])
@pytest.mark.parametrize("value", [None, b'{"broken":true}'])
def test_each_missing_or_divergent_required_proof_blocks(population, field, value):
    alter_child(population, **{field: value, "individual_envelope": None})
    result = child_proof(population)
    assert result.classification == "UNAUTHENTICATED" and result.counted == "BLOCKING"
    assert result.execution_restriction is None


def test_founder_without_individual_is_not_awaiting(population):
    population["homes"] = (dataclasses.replace(population["homes"][0], individual_envelope=None),)
    result = pc.own_proofs(**population)[0]
    assert result.classification == "UNAUTHENTICATED" and result.birth_proof == pc.NE
    assert "NOT_APPLICABLE_FOUNDER" in result.codes


@pytest.mark.parametrize("field", ["individual_envelope", "admission_envelope", "qualification_envelope", "statement_envelope"])
@pytest.mark.parametrize("invalid", [False, True])
def test_genuine_revocation_counts_but_invalid_signature_cannot_suspend(population, field, invalid):
    env = c.decode(getattr(population["homes"][1], field))
    current = c.decode(population["root_raw"])
    current["revoked_envelopes"] = [env["envelope_id"]]
    population.update(root_raw=f.canonical(current), root_pin=pin(current))
    if invalid:
        env["signature"] = "0" * 128
        alter_child(population, **{field: f.canonical(env)})
    result = child_proof(population)
    assert result.classification == ("UNAUTHENTICATED" if invalid else "SUSPENDED"), result
    assert result.execution_restriction == (None if invalid else "EXECUTION_SUSPENDED")
    assert result.counted == ("BLOCKING" if invalid else "INCLUDED")
    assert result.individual_proof in ("PASS", "FAIL", pc.NE)
    assert result.birth_proof in ("PASS", "FAIL", pc.NE)
    if field == "individual_envelope":
        assert result.individual_proof == "FAIL"
    else:
        assert result.birth_proof == "FAIL"


def test_revocation_precedes_awaiting(population):
    env = c.decode(population["homes"][1].qualification_envelope)
    current = c.decode(population["root_raw"])
    current["revoked_envelopes"] = [env["envelope_id"]]
    population.update(root_raw=f.canonical(current), root_pin=pin(current))
    alter_child(population, individual_envelope=None)
    assert child_proof(population).classification == "SUSPENDED"


@pytest.mark.parametrize("role", ["admission", "qualification", "statement"])
def test_valid_resign_cannot_replace_presented_envelope(population, role):
    field = role + "_envelope"
    env = c.decode(getattr(population["homes"][1], field))
    env["envelope_id"] = "f" * 64
    from tests.colony_trust.keys import lab_key
    env["signature"] = lab_key("admitter-1" if role == "admission" else "reviewer-1").sign(trust._message(env)).hex()
    alter_child(population, **{field: f.canonical(env)})
    result = child_proof(population)
    assert result.birth_proof == "FAIL" and result.classification == "UNAUTHENTICATED"
    assert "BIRTH_COMMIT_DIVERGENT" in result.codes or "BIRTH_COMMIT_UNPROVEN" in result.codes


def test_valid_new_statement_for_same_qualification_is_not_birth_evidence(population):
    home = population["homes"][1]
    st = c.decode(home.statement_bytes)
    st["verified_at_source_sha"] = "b" * 40
    env = helpers.signed(st, c.STATEMENT, label="new-statement")
    alter_child(population, statement_bytes=f.canonical(st), statement_envelope=f.canonical(env))
    result = child_proof(population)
    assert result.birth_proof == "FAIL" and result.classification == "UNAUTHENTICATED"


@pytest.mark.parametrize("role", ["admission", "qualification", "statement"])
def test_population_role_cannot_replace_birth_decision(population, role):
    op = c.operation(population["snapshots"][0][0])
    kind = {"admission": c.ADM, "qualification": c.QUAL, "statement": c.STATEMENT}[role]
    next(x for x in op["items"] if x["kind"] == kind)["role"] = "POPULATION"
    population["snapshots"] = (snapshot(op, c.decode(population["homes"][1].admission_envelope)),)
    assert child_proof(population).birth_proof == "FAIL"


@pytest.mark.parametrize("change", ["none", "duplicate", "legacy", "wrong_issuer", "wrong_spec", "failed", "refused"])
def test_commit_and_exact_ledger_are_required(population, change):
    op_raw, terminal, row_raw = population["snapshots"][0]
    op, row = c.operation(op_raw), c.decode(row_raw)
    if change == "none":
        population["snapshots"] = ()
    elif change == "duplicate":
        population["snapshots"] *= 2
    else:
        if change == "legacy":
            row["entry"]["ledger_schema"] = trust.LEDGER_SCHEMA
        elif change == "wrong_issuer":
            row["entry"]["issuer_id"] = "other"
        elif change == "wrong_spec":
            op["birth_plan"]["child_spec"]["display_name"] = "Changed"
        else:
            terminal = "FAILED_CONSUMED" if change == "failed" else "REFUSED"
        population["snapshots"] = ((f.canonical(op), terminal, f.canonical(row)),)
    assert child_proof(population).classification == "UNAUTHENTICATED"


def test_unrelated_later_operation_does_not_hide_committed_birth(population):
    op = c.operation(population["snapshots"][0][0])
    parent = c.decode(population["homes"][0].record_bytes)
    pspec = c.decode(population["homes"][0].spec_bytes)
    q, st = op["birth_plan"]["qualification"], c.decode(population["homes"][1].statement_bytes)
    cspec = b.spec(name="unrelated_candidate")
    record = lineage.make_descendant(parent, pspec, cspec, parent_qualification=q,
        lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=dict(b.BUDGET), declared_diff=lineage.spec_diff(pspec, cspec))
    admission = helpers.admission(record, parent, q, population["policy_pin"])
    other = helpers.make_operation(parent, record, cspec, q, admission, st)
    row = {"status": "NO_OPERATION_ENTRY", "operation_sha256": f.digest(other), "operation_entries": 0, "entry": None}
    population["snapshots"] += ((f.canonical(other), "REFUSED", f.canonical(row)),)
    assert child_proof(population).classification == "AUTHENTICATED"


def test_missing_scientific_source_is_blocking_ne(population):
    # R8 evidence absent is a missing source NE; it must not be replaced by PASS.
    population["artifacts"] = {}
    result = child_proof(population)
    assert result.scientific_bindings == pc.NE and result.classification == pc.NE
    assert result.counted == "NE" and result.birth_proof == pc.NE


def test_pc2_consistently_signed_and_bound_stays_unsupported(population):
    op = c.operation(population["snapshots"][0][0])
    home = population["homes"][1]
    q, st, admission = c.decode(home.qualification_bytes), c.decode(home.statement_bytes), c.decode(home.admission_bytes)
    q["criteria_sha256"] = "dcc3fe71909117ee2501ff3c5d2f8866f5343123929af40e06484a8ebf713ef7"
    st.update(criteria_sha256=q["criteria_sha256"], qualification_record_sha256=f.digest(q))
    admission["parent_qualification_sha256"] = f.digest(q)
    op["birth_plan"].update(qualification=q, admission=admission)
    op["items"] = [x for x in op["items"] if x["kind"] == c.IND]
    new = dict(qualification_bytes=f.canonical(q), admission_bytes=f.canonical(admission), statement_bytes=f.canonical(st))
    for role, kind, record, issuer, key in (("qualification", c.QUAL, q, REVIEWER, "reviewer-1"),
            ("admission", c.ADM, admission, ADMITTER, "admitter-1"),
            ("statement", c.STATEMENT, st, REVIEWER, "reviewer-1")):
        env = helpers.signed(record, kind, issuer, label="pc2-" + role, key_label=key)
        new[role + "_envelope"] = f.canonical(env)
        op["presented"][role] = {"record_sha256": f.digest(record), "envelope_sha256": f.digest(env)}
        op["items"].append(helpers.item(kind, record, env=f.digest(env)))
    helpers.sort_items(op)
    alter_child(population, **new)
    population["snapshots"] = (snapshot(op, c.decode(new["admission_envelope"])),)
    result = child_proof(population)
    assert result.birth_proof == pc.NE and result.scientific_bindings == pc.NE
    assert result.classification == pc.NE and result.counted == "NE"
    assert "SCIENTIFIC_PROFILE_UNSUPPORTED" in result.codes


def test_scientific_divergence_is_also_failed_birth_proof(population):
    population["artifacts"]["docs/colony_lab/evidence/C9_sentinel_evidence.json"] += b"\n"
    result = child_proof(population)
    assert result.birth_proof == result.scientific_bindings == "FAIL"
    assert result.classification == "UNAUTHENTICATED"


def test_open_home_is_never_blindly_excluded(population):
    raw, _, row = population["snapshots"][0]
    population["snapshots"] = ((raw, None, row),)
    result = child_proof(population)
    assert result.classification == pc.NE and result.counted == "NE"
    assert "OWN_HOME_NOT_EVALUATED" in result.codes


@pytest.mark.parametrize("mutation", ["parent_absent", "cycle", "wrong_spec", "bad_record", "bool_budget", "duplicate"])
def test_no_positive_structural_prefix_or_subset(population, mutation):
    homes = population["homes"]
    record = c.decode(homes[1].record_bytes)
    if mutation == "parent_absent":
        homes = (homes[1],)
    elif mutation == "duplicate":
        with pytest.raises(c.CoreError):
            pc.structures(homes * 2)
        return
    elif mutation == "wrong_spec":
        homes = (homes[0], dataclasses.replace(homes[1], spec_bytes=homes[0].spec_bytes))
    elif mutation == "bad_record":
        homes = (homes[0], dataclasses.replace(homes[1], record_bytes=b"{}"))
    else:
        if mutation == "cycle":
            record["lineage"]["parent_agent_id"] = record["agent_id"]
        else:
            record["budget"]["runs"] = True
        record["record_hash"] = lineage._record_hash(record)
        homes = (homes[0], dataclasses.replace(homes[1], record_bytes=f.canonical(record)))
    result = next(x for x in pc.structures(homes) if x.agent_id == population["homes"][1].agent_id)
    assert result.status == "FAIL" and result.branch == ()


def test_pure_core_performs_no_io_and_no_public_api_is_exported():
    calls = {ast.unparse(n.func) for n in ast.walk(ast.parse(inspect.getsource(pc))) if isinstance(n, ast.Call)}
    assert not calls & {"open", "os.open", "os.read", "reg.load_policy", "trust.check_bundle", "trust._spend"}
    import colony_admission
    assert not hasattr(colony_admission, "PopulationObserver")
    assert not hasattr(pc, "PopulationObserver")
