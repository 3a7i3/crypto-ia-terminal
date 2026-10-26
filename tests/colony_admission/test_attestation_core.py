"""3B pure comparisons, synthetic detached data and public LAB_TEST keys only."""

import copy
import dataclasses
import hashlib
from pathlib import Path

import pytest

from colony_admission import _attestation_core as c
from colony_admission import _attestation_statement as s
from colony_admission import formats as f
from colony_lab import lineage
from colony_registrar import registrar as reg
from colony_trust import trust
from tests.colony_admission.test_oplog import operation
from tests.colony_lab import builders as b
from tests.colony_trust.keys import ADMITTER, LAB, REVIEWER, eid, lab_key, pin, root

ROOT = Path(__file__).resolve().parents[2]


def statement(q, scope=s.FRESH):
    return {"statement_schema": c.STATEMENT, "subject_agent_id": q["agent_id"],
        "subject_agent_spec_id": q["agent_spec_id"], "issuer_kind": q["reviewer_kind"],
        "issuer_id": q["reviewer_id"], "issuer_root_version": 1,
        "qualification_record_sha256": f.digest(q), "historical_record_path": None,
        "historical_record_sha256": None, "evidence": [{"path": s.EVIDENCE_PATH, "sha256": q["evidence_sha256"]}],
        "criteria_sha256": q["criteria_sha256"], "subject_code_sha256": q["subject_code_sha256"],
        "evaluator_code_sha256": q["evaluator_code_sha256"], "verified_at_source_sha": "a" * 40,
        "scope": scope, "campaign_replayed": True, "campaign_evidence_sha256": q["evidence_sha256"],
        "historical_signature_claimed": False}


def signed(record, kind, issuer=REVIEWER, label="one", key_label="reviewer-1"):
    return trust.make_envelope(record, record_kind=kind, lab_id=LAB, root_version=1,
        issuer_id=issuer, private_key=lab_key(key_label), envelope_id=eid(label))


def admission(record, parent, q, policy_pin):
    return {"admission_schema": c.ADM, "child_agent_id": record["agent_id"],
        "child_agent_spec_id": record["agent_spec_id"], "parent_agent_id": parent["agent_id"],
        "admitter_kind": "EXTERNAL_HUMAN", "admitter_id": ADMITTER, "policy_sha256": policy_pin,
        "parent_qualification_sha256": f.digest(q), "budget": copy.deepcopy(record["budget"]),
        "lab_permissions": record["lab_permissions"], "declared_diff": record["genotype"]["declared_diff"]}


def make_operation(parent, child, child_spec, q, a, st):
    op = operation(lab_id=LAB, parent_agent_id=parent["agent_id"], child_agent_id=child["agent_id"],
        child_agent_spec_id=child["agent_spec_id"], policy_sha256=a["policy_sha256"],
        budget=copy.deepcopy(child["budget"]), permissions=list(child["lab_permissions"]),
        declared_diff=list(child["genotype"]["declared_diff"]))
    op["birth_plan"].update(policy_sha256=a["policy_sha256"], parent=copy.deepcopy(parent),
        record=copy.deepcopy(child), child_spec=copy.deepcopy(child_spec), qualification=copy.deepcopy(q),
        admission=copy.deepcopy(a))
    for role, record in (("admission", a), ("qualification", q), ("statement", st)):
        op["presented"][role] = {"record_sha256": f.digest(record), "envelope_sha256": "b" * 64}
    return op


def item(kind, record, role="DECISION", env="b" * 64):
    k = c.key(kind, record)
    return {"role": role, "kind": kind, "subject": {"agent_id": k.agent_id, "agent_spec_id": k.agent_spec_id},
        "record_sha256": k.record_sha256, "envelope_sha256": env}


def sort_items(op):
    op["items"].sort(key=lambda x: (x["kind"], x["subject"]["agent_id"], x["subject"]["agent_spec_id"],
                                  x["record_sha256"]))


@pytest.fixture
def family():
    selected = reg.load_policy()[0]
    selected["admissible_parent_criteria_sha256"] = ["1" * 64]
    policy_bytes, policy_pin = f.canonical(selected), f.digest(selected)
    spec, founder = b.founder()
    child_spec = b.spec(name="fixture_child")
    q = b.qualification(founder)
    child = lineage.make_descendant(founder, spec, child_spec, parent_qualification=q,
        lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=dict(b.BUDGET), declared_diff=lineage.spec_diff(spec, child_spec))
    a, st = admission(child, founder, q, policy_pin), statement(q)
    op = make_operation(founder, child, child_spec, q, a, st)
    op["items"] = [item(c.IND, founder), item(c.QUAL, q), item(c.ADM, a), item(c.STATEMENT, st)]
    sort_items(op)
    node = c.Node(founder["agent_id"], f.canonical(founder), f.canonical(spec))
    return op, (node,), st, policy_bytes, policy_pin


def branch(family):
    op, nodes, _, pol, pp = family
    return c.branch(f.canonical(op), nodes, pol, pp)


def partition(family):
    op, nodes, st, pol, pp = family
    return c.decision_partition(f.canonical(op), nodes, branch(family), f.canonical(st), pol, pp)


def test_founder_branch_partition_and_no_candidate_individual(family):
    result = branch(family)
    assert result.status == "PASS" and result.agent_ids == (family[1][0].agent_id,)
    assert result.population == result.ceilings == c.NE and result.accepted is False
    projected = partition(family)
    assert projected.status == "PASS" and len(projected.needs) == 4
    assert projected.population_partition == c.NE and projected.accepted is False
    assert all(n.key.agent_id != family[0]["child_agent_id"] for n in projected.needs if n.key.kind == c.IND)
    with pytest.raises(dataclasses.FrozenInstanceError):
        projected.accepted = True
    with pytest.raises(dataclasses.FrozenInstanceError):
        projected.needs[0].key.kind = "changed"


@pytest.mark.parametrize("change", ["credentials", "permissions", "lineage", "spec", "parent", "candidate", "diff"])
def test_rehashed_semantic_substitutions_never_pass(family, change):
    op, nodes, _, _, _ = family
    record = c.decode(nodes[0].record_bytes)
    if change == "credentials":
        record["credentials"] = "SOME_AUTHORITY"
    elif change == "permissions":
        record["lab_permissions"] = ["SECRET_VALUE_READ"]
    elif change == "lineage":
        record["lineage"]["generation"] = 2
    elif change == "spec":
        altered = c.decode(nodes[0].spec_bytes)
        altered["display_name"] = "Substituted"
        nodes = (dataclasses.replace(nodes[0], spec_bytes=f.canonical(altered)),)
    elif change == "parent":
        op["birth_plan"]["parent"]["budget"]["runs"] = 1
    elif change == "candidate":
        op["child_agent_id"] = nodes[0].agent_id
    else:
        op["declared_diff"] = ["agent_class"]
    record["record_hash"] = lineage._record_hash(record)
    if change in ("credentials", "permissions", "lineage"):
        nodes = (dataclasses.replace(nodes[0], record_bytes=f.canonical(record)),)
    result = branch((op, nodes, *family[2:]))
    assert result.status != "PASS" and result.agent_ids == ()


def test_missing_parent_and_no_prefix_pass(family):
    op, _, st, pol, pp = family
    result = c.branch(f.canonical(op), (), pol, pp)
    assert result.status == c.NE and result.codes == ("BRANCH_INCOMPLETE",)
    assert c.decision_partition(f.canonical(op), (), c.Branch("PASS"), f.canonical(st), pol, pp).status != "PASS"


@pytest.mark.parametrize("mode", ["cycle", "duplicate", "depth"])
def test_bounded_walk(family, mode):
    op, nodes, _, pol, pp = family
    record = c.decode(nodes[0].record_bytes)
    if mode == "cycle":
        record["role"] = "DESCENDANT"
        record["lineage"]["parent_agent_id"] = record["agent_id"]
        nodes = (dataclasses.replace(nodes[0], record_bytes=f.canonical(record)),)
    else:
        nodes *= 2 if mode == "duplicate" else 10
    result = c.branch(f.canonical(op), nodes, pol, pp)
    assert result.status == "FAIL" and result.agent_ids == ()
    assert result.codes == ({"cycle": ("BRANCH_CYCLE",), "duplicate": ("BRANCH_DIVERGENT",),
                             "depth": ("BRANCH_DEPTH_LIMIT",)}[mode])


@pytest.mark.parametrize("field", ["budget", "lab_permissions", "declared_diff", "parent_qualification_sha256",
                                   "admitter_id", "admitter_kind", "policy_sha256"])
def test_admission_binding_and_exclusions(family, field):
    op = family[0]
    a = op["birth_plan"]["admission"]
    a[field] = {"budget": {**a["budget"], "runs": 1}, "lab_permissions": [], "declared_diff": ["agent_class"],
        "parent_qualification_sha256": "f" * 64, "admitter_id": "issuer-" + op["parent_agent_id"][:16],
        "admitter_kind": "PEER_AGENT", "policy_sha256": "e" * 64}[field]
    op["presented"]["admission"]["record_sha256"] = f.digest(a)
    assert branch(family).status == "FAIL"


@pytest.mark.parametrize("mode", ["omit", "unexpected", "role", "envelope", "statement", "duplicate"])
def test_required_decision_is_derived_not_trusted(family, mode):
    op, nodes, st, _, _ = family
    before = f.canonical(op)
    if mode == "omit":
        op["items"] = [x for x in op["items"] if x["kind"] != c.IND]
    elif mode == "unexpected":
        other = c.decode(nodes[0].record_bytes)
        other["record_hash"] = "f" * 64
        op["items"].append(item(c.IND, other))
    elif mode == "role":
        next(x for x in op["items"] if x["kind"] == c.IND)["role"] = "POPULATION"
    elif mode == "envelope":
        next(x for x in op["items"] if x["kind"] == c.QUAL)["envelope_sha256"] = "a" * 64
    elif mode == "statement":
        st["verified_at_source_sha"] = "b" * 40
    else:
        op["items"].append(copy.deepcopy(op["items"][0]))
    sort_items(op)
    mutated = f.canonical(op)
    result = partition(family)
    assert result.status != "PASS"
    assert f.canonical(op) == mutated  # no repair of the frozen list
    assert before != mutated or mode == "statement"


def test_population_is_not_read_or_claimed(family):
    other = copy.deepcopy(family[0]["birth_plan"]["record"])
    family[0]["items"].append(item(c.IND, other, role="POPULATION"))
    sort_items(family[0])
    result = partition(family)
    assert result.status == "PASS" and result.population_partition == c.NE and len(result.needs) == 4


@pytest.mark.parametrize("bad", [None, b'{"x":1,"x":1}', b'{"x":NaN}', b'{"x":1.0}', b"[1]",
                                  b"\xff", b"{" * 100, b" " * 65537])
def test_strict_detached_inputs(bad):
    with pytest.raises(c.CoreError):
        c.decode(bad)


@pytest.mark.parametrize("mutation", ["none", "revoked", "revoked-invalid", "retired", "future", "subject", "pin"])
def test_trust_properties_stay_separate_and_never_spend(monkeypatch, mutation):
    def forbidden(*args, **kwargs):
        pytest.fail("pure core must not call a ledger or bundle API")
    for name in ("check_bundle", "verify_bundle", "verify_consumed", "inspect_consumption", "_spend"):
        if hasattr(trust, name):
            monkeypatch.setattr(trust, name, forbidden)
    record = b.qualification(b.founder()[1])
    envelope = signed(record, c.QUAL)
    current = root()
    if mutation in ("revoked", "revoked-invalid"):
        current["revoked_envelopes"] = [envelope["envelope_id"]]
    if mutation == "revoked-invalid":
        envelope["signature"] = "0" * 128
    if mutation == "retired":
        current["root_version"] = 2
        current["issuers"][1]["keys"][0].update(status="RETIRED", retired_in_root=2)
    if mutation == "future":
        envelope["root_version"] = 2
        envelope["signature"] = lab_key("reviewer-1").sign(trust._message(envelope)).hex()
    if mutation == "subject":
        envelope["subject"]["agent_id"] = "f" * 64
    required = c.Need(c.key(c.QUAL, record), f.canonical(record), ("one",), (f.digest(envelope),))
    verdict = c.item_fact(required, (f.canonical(envelope),), f.canonical(current),
        pin_sha256="0" * 64 if mutation == "pin" else pin(current), minimum_version=1, lab_id=LAB)
    assert verdict.accepted is False
    if mutation in ("none", "retired"):
        assert (verdict.integrity, verdict.authenticity, verdict.issuer_authorization) == ("PASS",) * 3
    else:
        assert "FAIL" in (verdict.integrity, verdict.authenticity, verdict.issuer_authorization)
    assert verdict.genuine_but_revoked is (mutation == "revoked")


def test_item_requires_exact_frozen_envelope_and_all_copies():
    record = b.qualification(b.founder()[1])
    e = signed(record, c.QUAL)
    required = c.Need(c.key(c.QUAL, record), f.canonical(record), ("one", "two"), (f.digest(e),))
    args = dict(pin_sha256=pin(root()), minimum_version=1, lab_id=LAB)
    missing = c.item_fact(required, (f.canonical(e), None), f.canonical(root()), **args)
    assert missing.authenticity == missing.genuine_but_revoked == c.NE
    omitted = c.item_fact(required, (f.canonical(e),), f.canonical(root()), **args)
    assert omitted.authenticity == c.NE and omitted.codes == ("ATTESTATION_MISSING",)
    other = signed(record, c.QUAL, label="other")
    mismatch = c.item_fact(required, (f.canonical(e), f.canonical(other)), f.canonical(root()), **args)
    assert mismatch.integrity == "FAIL" and mismatch.authenticity == c.NE


@pytest.fixture
def statement_material():
    q = b.qualification(b.founder()[1])
    st = statement(q)
    return q, st


def statement_fact(material):
    q, st = material
    qe, se = signed(q, c.QUAL), signed(st, c.STATEMENT)
    return s.statement(f.canonical(st), f.canonical(q), f.canonical(qe), f.canonical(se))


def test_closed_statement_and_provenance_remain_distinct(statement_material):
    result = statement_fact(statement_material)
    assert result.status == "PASS" and result.source_revision_provenance == c.NE and result.accepted is False


@pytest.mark.parametrize("field,value", [
    ("scope", "OTHER"), ("scope", 1), ("scope", []), ("issuer_root_version", True), ("issuer_root_version", 0),
    ("issuer_root_version", trust.MAX_VERSION + 1), ("verified_at_source_sha", "A" * 40),
    ("historical_signature_claimed", 0), ("historical_signature_claimed", True), ("campaign_replayed", 1),
    ("campaign_evidence_sha256", "f" * 64), ("historical_record_path", s.HISTORY_PATH),
    ("subject_agent_id", "f" * 64), ("qualification_record_sha256", "f" * 64), ("issuer_id", "other"),
    ("evidence", []), ("evidence", [{"path": "../x", "sha256": "a" * 64}]),
    ("evidence", [{"path": ".env", "sha256": "a" * 64}]),
    ("evidence", [{"path": "a", "sha256": "a" * 64}, {"path": "a", "sha256": "a" * 64}]),
    ("extra", False),
])
def test_statement_signed_but_semantically_invalid(statement_material, field, value):
    statement_material[1][field] = value
    assert statement_fact(statement_material).status == "FAIL"


@pytest.mark.parametrize("path", ["/x", "../x", "a//b", "a/./b", "a/../b", ".ENV.local", "x/secret.txt",
    "credentials.json", "private_key_data", "id_rsa", "x/id_ed25519", "x.KEY", "cert.pem", "x.p12", "a\\b"])
def test_forbidden_source_paths_before_hashing(path):
    assert not s.safe_path(path)
    with pytest.raises(c.CoreError, match="SOURCE_PATH_FORBIDDEN"):
        s.code_digest(((path, b"never use"),))


def test_hash_encoding_not_only_python_and_no_duplicate_or_empty_closure():
    files = (("a.py", b"x"), ("fixture.json", b"{}"))
    expected = hashlib.sha256(b"a.py\0" + hashlib.sha256(b"x").digest()
                             + b"fixture.json\0" + hashlib.sha256(b"{}").digest()).hexdigest()
    assert s.code_digest(files) == expected
    for bad in ((), files[::-1], (files[0], files[0])):
        with pytest.raises(c.CoreError):
            s.code_digest(bad)


@pytest.fixture
def scientific():
    artifacts = {path: (ROOT / path).read_bytes() for path in (s.CRITERIA_PATH, s.EVIDENCE_PATH, s.HISTORY_PATH)}
    q = c.decode(artifacts[s.HISTORY_PATH])
    q.update(reviewer_id=REVIEWER, reviewer_kind="EXTERNAL_REVIEW_PROCESS")
    st = statement(q)
    st.update(scope=s.PRESENT, campaign_replayed=False, campaign_evidence_sha256=None,
              historical_record_path=s.HISTORY_PATH, historical_record_sha256=s.HISTORY_PIN)
    return q, st, artifacts


def scientific_fact(scientific, subject=s.SUBJECT_PIN, evaluator=s.EVALUATOR_PIN):
    q, st, artifacts = scientific
    return s.scientific_bindings(f.canonical(st), f.canonical(q), artifacts, subject, evaluator)


def test_current_r8_profile_with_new_present_author_and_historical_provenance(scientific):
    assert statement_fact(scientific[:2]).status == "PASS"
    assert scientific_fact(scientific).status == "PASS"
    assert scientific_fact(scientific).source_revision_provenance == c.NE


@pytest.mark.parametrize("change", ["q_and_statement_fake_evidence", "historical_digest", "historical_path",
    "subject_code", "evaluator_code", "changed_bytes", "missing_source", "pc2", "fresh"])
def test_science_binds_actual_pinned_bytes_not_merely_matching_claims(scientific, change):
    q, st, artifacts = scientific
    if change == "q_and_statement_fake_evidence":
        q["evidence_sha256"] = st["evidence"][0]["sha256"] = "a" * 64
        st["qualification_record_sha256"] = f.digest(q)
    elif change == "historical_digest":
        st["historical_record_sha256"] = "b" * 64
    elif change == "historical_path":
        st["historical_record_path"] = "docs/other.json"
    elif change == "changed_bytes":
        artifacts[s.EVIDENCE_PATH] += b"\n"
    elif change == "missing_source":
        del artifacts[s.EVIDENCE_PATH]
    elif change == "pc2":
        q["criteria_sha256"] = "dcc3fe71909117ee2501ff3c5d2f8866f5343123929af40e06484a8ebf713ef7"
    elif change == "fresh":
        st.update(scope=s.FRESH, campaign_replayed=True, campaign_evidence_sha256=s.EVIDENCE_PIN,
                  historical_record_path=None, historical_record_sha256=None)
        del artifacts[s.HISTORY_PATH]
    result = scientific_fact(scientific, subject="c" * 64 if change == "subject_code" else s.SUBJECT_PIN,
                             evaluator="c" * 64 if change == "evaluator_code" else s.EVALUATOR_PIN)
    if change == "fresh":
        assert result.status == "PASS" and result.source_revision_provenance == c.NE
    else:
        assert result.status != "PASS"
        if change == "pc2":
            assert result.codes == ("SCIENTIFIC_PROFILE_UNSUPPORTED",)


def test_ancestor_commit_requires_exact_operation_and_consumption(family):
    op, _, _, _, _ = family
    a = op["birth_plan"]["admission"]
    e = signed(a, c.ADM, ADMITTER, key_label="admitter-1")
    op["presented"]["admission"]["envelope_sha256"] = f.digest(e)
    n = c.Node(op["child_agent_id"], f.canonical(op["birth_plan"]["record"]),
        f.canonical(op["birth_plan"]["child_spec"]), f.canonical(op["birth_plan"]["qualification"]), f.canonical(a))
    entry = {"ledger_schema": trust.OPERATION_LEDGER_SCHEMA, "issuer_id": e["issuer_id"],
        "envelope_id": e["envelope_id"], "envelope_sha256": f.digest(e), "operation_sha256": f.digest(op)}
    row = {"status": "OPERATION_ENTRY_PRESENT", "operation_entries": 1, "operation_sha256": f.digest(op),
        "entry": entry}
    snapshots = ((f.canonical(op), "COMMITTED", f.canonical(row)),)
    assert c.ancestor_commit(n, snapshots, f.canonical(e)) == ("PASS", ())
    for field, value in (("ledger_schema", trust.LEDGER_SCHEMA), ("operation_sha256", "f" * 64),
                         ("issuer_id", "other"), ("envelope_id", "f" * 64), ("envelope_sha256", "f" * 64)):
        changed = copy.deepcopy(row)
        changed["entry"][field] = value
        assert c.ancestor_commit(n, ((f.canonical(op), "COMMITTED", f.canonical(changed)),), f.canonical(e))[0] != "PASS"
    for terminal in (None, "FAILED_CONSUMED", "REFUSED"):
        assert c.ancestor_commit(n, ((f.canonical(op), terminal, f.canonical(row)),), f.canonical(e))[0] != "PASS"
    for missing_or_ambiguous in ((), snapshots * 2):
        assert c.ancestor_commit(n, missing_or_ambiguous, f.canonical(e))[0] != "PASS"
    refused = (f.canonical(op), "REFUSED", f.canonical({**row, "operation_entries": 0, "entry": None}))
    assert c.ancestor_commit(n, (refused, *snapshots), f.canonical(e)) == ("PASS", ())
    assert c.ancestor_commit(n, ((f.canonical(op), "COMMITTED", f.canonical({**row, "operation_entries": True})),),
                             f.canonical(e))[0] != "PASS"


def test_pure_modules_have_no_io_calls_or_public_scan_api():
    import ast
    import inspect
    for module in (c, s):
        tree = ast.parse(inspect.getsource(module))
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not calls & {"open", "os.open", "os.read", "Path", "reg.load_policy", "trust.verify_bundle",
            "trust.check_bundle", "trust._spend", "trust.verify_consumed", "eval", "exec", "__import__"}
        assert not hasattr(module, "AttestationObserver")


def next_generation(family):
    op, nodes, st, pol, pp = family
    parent = op["birth_plan"]["record"]
    pspec = op["birth_plan"]["child_spec"]
    q = b.qualification(parent)
    cspec = b.spec(name="fixture_grandchild")
    # Registrar's descendant construction is pure; lineage.make_descendant is
    # founder-only and cannot be used for this multi-generation fixture.
    from colony_lab.a1_identity import check_spec
    child = copy.deepcopy(parent)
    child.update(check_spec(cspec))
    child["lineage"].update(parent_agent_id=parent["agent_id"], parent_agent_spec_id=parent["agent_spec_id"],
                            generation=parent["lineage"]["generation"] + 1)
    child["genotype"] = {"base_agent_spec_id": parent["agent_spec_id"], "declared_diff": lineage.spec_diff(pspec, cspec)}
    child["record_hash"] = lineage._record_hash(child)
    lineage.verify_record(child, cspec, parent, pspec)
    a, current_statement = admission(child, parent, q, pp), statement(q)
    candidate = make_operation(parent, child, cspec, q, a, current_statement)
    node = c.Node(parent["agent_id"], f.canonical(parent), f.canonical(pspec),
        f.canonical(op["birth_plan"]["qualification"]), f.canonical(op["birth_plan"]["admission"]), f.canonical(st))
    all_nodes = (*nodes, node)
    # Independent expectation, not the implementation's derived list.
    material = [(c.ADM, a), (c.QUAL, q), (c.STATEMENT, current_statement)]
    for n in all_nodes:
        material.append((c.IND, c.decode(n.record_bytes)))
        if n.qualification_bytes:
            material.extend(((c.ADM, c.decode(n.admission_bytes)), (c.QUAL, c.decode(n.qualification_bytes)),
                             (c.STATEMENT, c.decode(n.statement_bytes))))
    candidate["items"] = list({c.key(kind, record): item(kind, record) for kind, record in material}.values())
    sort_items(candidate)
    return candidate, all_nodes, current_statement, pol, pp


def test_founder_to_parent_order_and_each_ancestor_required(family):
    deep = next_generation(family)
    result = branch(deep)
    assert result.status == "PASS" and result.agent_ids == tuple(n.agent_id for n in deep[1])
    assert partition(deep).status == "PASS" and len(partition(deep).needs) == 8
    for field in ("qualification_bytes", "admission_bytes"):
        nodes = (*deep[1][:-1], dataclasses.replace(deep[1][-1], **{field: None}))
        assert branch((deep[0], nodes, *deep[2:])).status != "PASS"
    nodes = (*deep[1][:-1], dataclasses.replace(deep[1][-1], statement_bytes=None))
    assert partition((deep[0], nodes, *deep[2:])).status != "PASS"


def test_qualification_key_retains_record_digest_and_reuse_origins():
    record = b.founder()[1]
    qa = b.qualification(record)
    qb = {**qa, "evidence_sha256": "e" * 64}
    needs = {}
    c._add(needs, c.QUAL, qa, "first", "a" * 64)
    c._add(needs, c.QUAL, qa, "second", "a" * 64)
    c._add(needs, c.QUAL, qb, "third", "b" * 64)
    assert len(needs) == 2
    assert needs[c.key(c.QUAL, qa)].namespaces == ("first", "second")
    assert needs[c.key(c.QUAL, qa)].envelope_sha256s == ("a" * 64,)


def test_partition_preserves_demonstrated_branch_contradiction(family):
    op, nodes, st, pol, pp = family
    changed = c.decode(nodes[0].record_bytes)
    changed["credentials"] = "SOME_AUTHORITY"
    changed["record_hash"] = lineage._record_hash(changed)
    nodes = (dataclasses.replace(nodes[0], record_bytes=f.canonical(changed)),)
    fact = c.branch(f.canonical(op), nodes, pol, pp)
    projected = c.decision_partition(f.canonical(op), nodes, fact, f.canonical(st), pol, pp)
    assert fact.status == projected.status == "FAIL" and projected.codes == fact.codes


@pytest.mark.parametrize("cap,count", [(6, 20), (6, 21), (64, 252), (64, 253)])
def test_frozen_reference_policy_and_universal_cap_before_branch(family, cap, count):
    op, nodes, st, raw_policy, _ = family
    pol = c.decode(raw_policy)
    pol["max_population"] = cap
    pp = f.digest(pol)
    op["policy_sha256"] = op["birth_plan"]["policy_sha256"] = pp
    # Unique structurally valid unrelated items, so the result below the cap
    # is a branch binding failure, not an item limit.
    op["items"] = [item(c.IND, {"agent_id": f"{i:064x}", "agent_spec_id": "a" * 64}) for i in range(count)]
    sort_items(op)
    result = c.decision_partition(f.canonical(op), nodes, c.Branch(), f.canonical(st), f.canonical(pol), pp)
    assert (result.codes == ("SOURCE_LIMIT",)) is (count > min(252, 4 * cap - 4))


@pytest.mark.parametrize("side", ["qualification", "statement"])
@pytest.mark.parametrize("field,value", [("issuer_id", "another-issuer"), ("root_version", 2),
    ("record_sha256", "a" * 64), ("subject", {"agent_id": "a" * 64, "agent_spec_id": "b" * 64})])
def test_statement_envelopes_need_exact_author_version_record_subject(statement_material, side, field, value):
    q, st = statement_material
    qe, se = signed(q, c.QUAL), signed(st, c.STATEMENT)
    target = qe if side == "qualification" else se
    target[field] = value
    result = s.statement(f.canonical(st), f.canonical(q), f.canonical(qe), f.canonical(se))
    assert result.status == "FAIL"


def test_historical_reviewer_is_not_an_invented_present_issuer(scientific):
    q, st, _ = scientific
    q["reviewer_id"] = st["issuer_id"] = "colony-review-481-r8"
    st["qualification_record_sha256"] = f.digest(q)
    assert statement_fact((q, st)).status == "FAIL"
