"""PC2 amendment C8.3: private validators on LAB_TEST fixtures only.

The pinned artifacts are the real checkout files; q, statements, envelopes,
issuer and keys are synthetic LAB_TEST fixtures that qualify nothing and imitate
no human or GitHub identity. Each test names the matrix cases it exercises with
``case``; the delivery document classifies all 80 cases and a test keeps both in
step. A matrix case is never counted as executed from its existence.
"""

import ast
import copy
import hashlib
import inspect
import json
import os
import re
import types
from pathlib import Path

import pytest

from colony_admission import _attestation_core as c
from colony_admission import _attestation_statement as s
from colony_admission import _pc2_profile as pc2
from colony_admission import formats as f
from colony_lab import a1_identity as a1
from colony_lab import lineage
from colony_lab import qualification as lab_q
from colony_registrar import registrar as reg
from colony_trust import trust
from tests.colony_trust.keys import LAB, eid, key_entry, lab_key, pin, root

ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "docs/colony_admission/P4_PC2_VALIDATORS_DELIVERY_V0.md"
MATRIX = ROOT / "docs/colony_admission/P4_PC2_NATIVE_EVIDENCE_AMENDMENT_CASES_V0.json"
ISSUER = "fixture-pc2-present-issuer"
OTHER_ISSUER = "fixture-pc2-other-issuer"
P0_PIN = "065e0777dfd08ed6592ef2a70dfaae32854485b7a8fecd9127280238e553357d"
PC1_PATH = "docs/colony_lab/evidence/PC1_pilot_evidence.json"
CASES = {}


def case(*ids):
    def mark(test):
        for x in ids:
            assert re.fullmatch(r"PC2-\d\d", x)
            CASES.setdefault(x, set()).add(test.__name__)
        return test
    return mark


def issuer(name=ISSUER, scopes=(c.QUAL, c.STATEMENT), label="pc2-issuer-1", status="ACTIVE"):
    retired = None if status == "ACTIVE" else 2
    return {"issuer_id": name, "issuer_kind": "EXTERNAL_REVIEW_PROCESS", "scopes": sorted(scopes),
            "keys": [key_entry(label, status=status, retired=retired)]}


def trust_root(*issuers, revoked=(), version=1):
    return root(version=version, issuers=list(issuers) or [issuer()], revoked=revoked)


def sign(record, kind, name=ISSUER, label="pc2-issuer-1", version=1, envelope="pc2"):
    return trust.make_envelope(record, record_kind=kind, lab_id=LAB, root_version=version, issuer_id=name,
                               private_key=lab_key(label), envelope_id=eid(envelope + kind))


def context_objects():
    r8c = json.loads((ROOT / s.CRITERIA_PATH).read_bytes())
    p1c = json.loads((ROOT / pc2.P1C_PATH).read_bytes())
    parent_spec = lab_q.sentinel_spec(r8c["subject"])
    # Independent of colony_pilot.campaign: the p1 pilot spec rebuilt from p1 itself.
    body = {k: copy.deepcopy(v) for k, v in parent_spec.items() if k not in {"agent_id", "agent_spec_id"}}
    body.update({k: p1c["pilot"][k] for k in ("canonical_name", "display_name", "purpose")})
    body["agent_id"] = a1.agent_id(body["namespace"], body["canonical_name"], body["agent_class"])
    body["agent_spec_id"] = a1.agent_spec_id(body)
    parent = lineage.make_founder(parent_spec, lab_permissions=list(r8c["subject"]["lab_permissions"]),
                                  budget=dict(lab_q.BUDGET))
    r8q = json.loads((ROOT / s.HISTORY_PATH).read_bytes())
    pilot = lineage.make_descendant(parent, parent_spec, body, parent_qualification=r8q,
                                    lab_permissions=list(p1c["pilot"]["lab_permissions"]),
                                    budget=dict(lab_q.BUDGET), declared_diff=list(p1c["pilot"]["declared_diff"]))
    return {"sentinel_record": parent, "sentinel_spec": parent_spec, "pilot_record": pilot, "pilot_spec": body}


class World:
    """One mutable LAB_TEST world: five raw artifacts, q/s, context, digests, signer."""

    def __init__(self):
        self.raw = {path: (ROOT / path).read_bytes() for path in pc2.PINS}
        self.context = context_objects()
        self.q = {"qualification_schema": lineage.QUALIFICATION_SCHEMA, **{k: pc2.PILOT[k] for k in (
            "agent_id", "agent_spec_id")}, "state": "QUALIFIED_SIMULATED", "scope": "SIMULATED_DETERMINISTIC",
            "criteria_sha256": pc2.P1C_PIN, "evidence_sha256": pc2.PC2_PIN, "subject_code_sha256": pc2.SUBJECT_PIN,
            "evaluator_code_sha256": pc2.PILOT_PIN, "reviewer_kind": "EXTERNAL_REVIEW_PROCESS", "reviewer_id": ISSUER}
        self.st = {"statement_schema": c.STATEMENT, "subject_agent_id": self.q["agent_id"],
            "subject_agent_spec_id": self.q["agent_spec_id"], "issuer_kind": "EXTERNAL_REVIEW_PROCESS",
            "issuer_id": ISSUER, "issuer_root_version": 1, "qualification_record_sha256": None,
            "historical_record_path": pc2.PC2_PATH, "historical_record_sha256": pc2.PC2_PIN,
            "evidence": [{"path": pc2.PC2_PATH, "sha256": pc2.PC2_PIN}], "criteria_sha256": pc2.P1C_PIN,
            "subject_code_sha256": pc2.SUBJECT_PIN, "evaluator_code_sha256": pc2.PILOT_PIN,
            "verified_at_source_sha": "a" * 40, "scope": s.PRESENT, "campaign_replayed": False,
            "campaign_evidence_sha256": None, "historical_signature_claimed": False}
        self.digests = [pc2.SUBJECT_PIN, pc2.EVALUATOR_PIN, pc2.PILOT_PIN]
        self.pins = dict(pc2.PINS)
        self.rehash()

    def rehash(self):
        self.st["qualification_record_sha256"] = f.digest(self.q)
        return self

    def docs(self):
        return {path: json.loads(raw) for path, raw in self.raw.items()}

    def reseal(self, **edits):
        """Edit artifacts by alias and rebuild every raw pointer above them (instrumented pins only)."""
        docs, changed = self.docs(), set()
        order = (("R8C", s.CRITERIA_PATH), ("C9", s.EVIDENCE_PATH), ("R8Q", s.HISTORY_PATH),
                 ("P1C", pc2.P1C_PATH), ("PC2", pc2.PC2_PATH))
        for alias, path in order:
            doc = docs[path]
            if alias in ("C9", "R8Q") and s.CRITERIA_PATH in changed:
                doc["criteria_sha256"] = self.pins[s.CRITERIA_PATH]
            if alias == "R8Q" and s.EVIDENCE_PATH in changed:
                doc["evidence_sha256"] = self.pins[s.EVIDENCE_PATH]
            if alias == "PC2":
                if s.HISTORY_PATH in changed:
                    doc["parent"]["record_sha256"] = self.pins[s.HISTORY_PATH]
                    doc["parent"]["qualification"] = copy.deepcopy(docs[s.HISTORY_PATH])
                if pc2.P1C_PATH in changed:
                    doc["criteria_sha256"] = self.pins[pc2.P1C_PATH]
            touched = alias in edits or (alias == "C9" and s.CRITERIA_PATH in changed) or (
                alias == "R8Q" and changed & {s.CRITERIA_PATH, s.EVIDENCE_PATH}) or (
                alias == "PC2" and changed & {s.HISTORY_PATH, pc2.P1C_PATH})
            if alias in edits:
                edits[alias](doc)
            if touched:
                self.raw[path] = json.dumps(doc, indent=2, ensure_ascii=False).encode() + b"\n"
                self.pins[path] = hashlib.sha256(self.raw[path]).hexdigest()
                changed.add(path)
        if pc2.P1C_PATH in changed:
            self.q["criteria_sha256"] = self.st["criteria_sha256"] = self.pins[pc2.P1C_PATH]
        if pc2.PC2_PATH in changed:
            new = self.pins[pc2.PC2_PATH]
            self.q["evidence_sha256"] = self.st["historical_record_sha256"] = new
            self.st["evidence"] = [{"path": pc2.PC2_PATH, "sha256": new}]
        return self.rehash()

    def context_bytes(self, **override):
        values = {k: f.canonical(v) for k, v in self.context.items()}
        values.update(override)
        return pc2.Context(**values)

    def reseal_record(self, name, mutate, spec=None):
        record = self.context[name]
        mutate(record)
        record["record_hash"] = lineage._record_hash(record)
        return self

    def science(self, module=pc2, **context):
        return module.bindings(f.canonical(self.st), f.canonical(self.q), dict(self.raw), *self.digests,
                               self.context_bytes(**context))

    def envelopes(self, q_signer=None, s_signer=None):
        def own(record, kind):
            return sign(record, kind, name=self.st["issuer_id"])
        qe = (q_signer or own)(self.q, c.QUAL)
        se = (s_signer or own)(self.st, c.STATEMENT)
        return qe, se

    def statement(self, qe=None, se=None):
        default_qe, default_se = self.envelopes()
        qe, se = qe or default_qe, se or default_se
        return s.statement(f.canonical(self.st), f.canonical(self.q), f.canonical(qe), f.canonical(se))


def variant(world=None, replace=()):
    """An in-memory copy of the validator, optionally with instrumented pins or a removed guard."""
    source = inspect.getsource(pc2)
    for old, new in replace:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    module = types.ModuleType("colony_admission._pc2_profile_variant")
    module.__package__ = "colony_admission"
    exec(compile(source, "<pc2-variant>", "exec"), module.__dict__)
    module.Context = pc2.Context
    if world is not None:
        module.PINS = dict(world.pins)
        module.P1C_PIN = world.pins[pc2.P1C_PATH]
        module.PC2_PIN = world.pins[pc2.PC2_PATH]
    return module


@pytest.fixture
def w():
    return World()


def verdict(world, envelope, record, kind, root_value):
    return trust.classify_envelope(envelope, record, root_value, pin_sha256=pin(root_value), minimum_version=1,
        lab_id=LAB, record_kind=kind, subject={k: world.q[k] for k in ("agent_id", "agent_spec_id")})


@case("PC2-02", "PC2-17", "PC2-26", "PC2-78")
def test_exact_lab_test_world_passes_only_its_comparisons(w):
    qe, se = w.envelopes()
    assert w.statement(qe, se).status == "PASS"
    fact = w.science()
    assert fact.status == "PASS" and fact.codes == ()
    assert fact.accepted is False and fact.source_revision_provenance == c.NE
    assert set(w.raw) == set(pc2.PINS) and len(pc2.PINS) == 5  # no historical pilot qualification file
    for envelope, record, kind in ((qe, w.q, c.QUAL), (se, w.st, c.STATEMENT)):
        result = verdict(w, envelope, record, kind, trust_root())
        assert (result["integrity"], result["authenticity"], result["authorization"]) == ("PASS",) * 3
    assert pc2.select(f.canonical(w.q), f.canonical(w.st)) == pc2.PROFILE


@case("PC2-01", "PC2-49", "PC2-52")
def test_public_readers_keep_the_refusal_until_integration(w):
    # C8.6: the R8 reader still refuses p1, and no reader imports this private module.
    old = s.scientific_bindings(f.canonical(w.st), f.canonical(w.q), dict(w.raw), pc2.SUBJECT_PIN, pc2.EVALUATOR_PIN)
    assert (old.status, old.codes) == (c.NE, ("SCIENTIFIC_PROFILE_UNSUPPORTED",))
    for path in sorted((ROOT / "colony_admission").glob("*.py")):
        if path.name == "_pc2_profile.py":
            continue
        tree = ast.parse(path.read_text())
        names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        assert "_pc2_profile" not in names and "_pc2_profile" not in path.read_text(), path


@case("PC2-03", "PC2-75")
def test_pc1_p0_and_alternative_paths_never_select_or_pass(w):
    pc1 = (ROOT / PC1_PATH).read_bytes()
    alternative = World()
    alternative.raw[PC1_PATH] = alternative.raw.pop(pc2.PC2_PATH)
    assert alternative.science().status == "FAIL"
    substituted = World()
    substituted.raw[pc2.PC2_PATH] = pc1
    assert substituted.science().codes == ("SCIENTIFIC_DIVERGENCE",)
    w.q["evidence_sha256"] = hashlib.sha256(pc1).hexdigest()
    w.st["evidence"] = [{"path": PC1_PATH, "sha256": w.q["evidence_sha256"]}]
    w.st["historical_record_path"], w.st["historical_record_sha256"] = PC1_PATH, w.q["evidence_sha256"]
    assert set(w.rehash().science().codes) == {"STATEMENT_INVALID", "SCIENTIFIC_DIVERGENCE"}
    p0 = World()
    p0.q["criteria_sha256"] = p0.st["criteria_sha256"] = P0_PIN
    assert pc2.select(f.canonical(p0.rehash().q), f.canonical(p0.st)) is None
    for reader in (p0.science(), s.scientific_bindings(f.canonical(p0.st), f.canonical(p0.q), {}, None, None)):
        assert (reader.status, reader.codes) == (c.NE, ("SCIENTIFIC_PROFILE_UNSUPPORTED",))


@case("PC2-04", "PC2-05")
@pytest.mark.parametrize("path", sorted(pc2.PINS))
@pytest.mark.parametrize("change", ["canonical", "aligned_claims"])
def test_raw_pin_refuses_reencoding_and_self_consistent_forgeries(w, path, change):
    if change == "canonical":
        w.raw[path] = f.canonical(json.loads(w.raw[path]))
    else:
        w.reseal(**{alias: (lambda d: d.update(note="forged")) for alias, p in (
            ("R8C", s.CRITERIA_PATH), ("C9", s.EVIDENCE_PATH), ("R8Q", s.HISTORY_PATH), ("P1C", pc2.P1C_PATH),
            ("PC2", pc2.PC2_PATH)) if p == path})
    fact = w.science()
    if change == "aligned_claims" and path == pc2.P1C_PATH:
        # q now names other criteria: no profile is selected at all (C10.2).
        assert (fact.status, fact.codes) == (c.NE, ("SCIENTIFIC_PROFILE_UNSUPPORTED",))
    else:
        assert fact.status == "FAIL" and "SCIENTIFIC_DIVERGENCE" in fact.codes


@case("PC2-06", "PC2-07")
@pytest.mark.parametrize("swap", ["S_P", "E_for_P", "S_for_P"])
def test_no_permutation_or_substitution_of_closures(w, swap):
    if swap == "S_P":
        w.q["subject_code_sha256"], w.q["evaluator_code_sha256"] = pc2.PILOT_PIN, pc2.SUBJECT_PIN
    else:
        w.q["evaluator_code_sha256"] = pc2.EVALUATOR_PIN if swap == "E_for_P" else pc2.SUBJECT_PIN
    w.st["subject_code_sha256"], w.st["evaluator_code_sha256"] = w.q["subject_code_sha256"], w.q["evaluator_code_sha256"]
    assert w.rehash().statement().status == "PASS"  # signed and coherent, still not this profile's mapping
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-08", "PC2-09", "PC2-70")
@pytest.mark.parametrize("index", [0, 1, 2])
def test_each_recomputed_closure_is_bound_and_rechecked_per_call(w, index):
    assert w.science().status == "PASS"
    w.digests[index] = "c" * 64
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)
    w.digests[index] = None
    assert (w.science().status, w.science().codes) == (c.NE, ("SCIENTIFIC_SOURCE_UNAVAILABLE",))


@case("PC2-50")
def test_current_checkout_closures_equal_the_three_pins():
    # C3.1 selection over this checkout (cache directories carry no content); not an acquisition proof.
    def closure(roots, minus=frozenset()):
        files = set()
        for name in roots:
            top = ROOT / name
            for current, dirs, names in os.walk(top) if top.is_dir() else [(str(top.parent), [], [top.name])]:
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for leaf in names:
                    files.add(str(Path(current, leaf).relative_to(ROOT)))
        return s.code_digest(tuple((p, (ROOT / p).read_bytes()) for p in sorted(files - minus)))

    from colony_admission import _attestation_checkout as checkout

    subject = {str(p.relative_to(ROOT)) for name in checkout.SUBJECT_ROOTS for p in (
        [ROOT / name] if (ROOT / name).is_file() else (ROOT / name).rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts}
    assert closure(checkout.SUBJECT_ROOTS) == pc2.SUBJECT_PIN
    assert closure(checkout.EVALUATOR_ROOTS, frozenset(subject)) == pc2.EVALUATOR_PIN
    assert closure(pc2.PILOT_ROOTS) == pc2.PILOT_PIN


@case("PC2-13", "PC2-14", "PC2-34")
@pytest.mark.parametrize("subject", ["sentinel", "other_pilot", "other_spec", "new_child"])
def test_subject_is_exactly_the_native_pilot(w, subject):
    sentinel = w.context["sentinel_record"]
    ids = {"sentinel": (sentinel["agent_id"], sentinel["agent_spec_id"]), "other_pilot": ("d" * 64, w.q["agent_spec_id"]),
           "other_spec": (w.q["agent_id"], "d" * 64), "new_child": ("e" * 64, "f" * 64)}[subject]
    w.q["agent_id"], w.q["agent_spec_id"] = ids
    w.st["subject_agent_id"], w.st["subject_agent_spec_id"] = ids
    assert w.rehash().statement().status == "PASS"
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-34")
def test_pilot_as_parent_keeps_lineage_layer_and_grants_nothing(w):
    # The q concerns the pilot itself; the lab layer accepts it for the pilot record only.
    lineage.check_qualification(w.q, w.context["pilot_record"], also_excluded=frozenset({"9" * 64}))
    assert w.science().status == "PASS"
    assert not any(hasattr(pc2, name) for name in ("admit", "birth", "authorize", "scan"))


@case("PC2-15")
def test_fake_evidence_hash_in_both_q_and_statement(w):
    w.q["evidence_sha256"] = "a" * 64
    w.st["evidence"] = [{"path": pc2.PC2_PATH, "sha256": "a" * 64}]
    assert w.rehash().statement().status == "PASS"
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-16", "PC2-57")
@pytest.mark.parametrize("history", ["r8q", "fake_pilot_record", "other_hex"])
def test_only_native_pc2_is_the_historical_record(w, history):
    path, digest = {"r8q": (s.HISTORY_PATH, s.HISTORY_PIN),
                    "fake_pilot_record": ("docs/colony_lab/PILOT_QUALIFICATION_RECORD_P1.json", "b" * 64),
                    "other_hex": (pc2.PC2_PATH, "b" * 64)}[history]
    w.st["historical_record_path"], w.st["historical_record_sha256"] = path, digest
    assert w.statement().status == "PASS"
    assert w.science().codes == ("STATEMENT_INVALID",)
    r8 = World()
    r8.q.update(c.decode(r8.raw[s.HISTORY_PATH]), reviewer_kind="EXTERNAL_REVIEW_PROCESS", reviewer_id=ISSUER)
    r8.st.update(criteria_sha256=s.CRITERIA_PIN, evidence=[{"path": s.EVIDENCE_PATH, "sha256": s.EVIDENCE_PIN}],
                 subject_agent_id=r8.q["agent_id"], subject_agent_spec_id=r8.q["agent_spec_id"],
                 evaluator_code_sha256=s.EVALUATOR_PIN)
    r8.rehash()
    assert pc2.select(f.canonical(r8.q), f.canonical(r8.st)) == pc2.R8_PROFILE
    r8_fact = s.scientific_bindings(f.canonical(r8.st), f.canonical(r8.q),
        {p: r8.raw[p] for p in (s.CRITERIA_PATH, s.EVIDENCE_PATH, s.HISTORY_PATH)}, s.SUBJECT_PIN, s.EVALUATOR_PIN)
    assert r8_fact.codes == ("STATEMENT_INVALID",)  # PC2 path under R8 criteria: no switch by path


@case("PC2-18")
def test_missing_or_swapped_present_envelopes(w):
    qe, se = w.envelopes()
    for missing in ("qe", "se"):
        args = [f.canonical(w.st), f.canonical(w.q), f.canonical(qe), f.canonical(se)]
        args[2 if missing == "qe" else 3] = None
        fact = s.statement(*args)
        assert (fact.status, fact.codes) == (c.NE, ("EVIDENCE_NOT_STORED",))
    assert w.statement(se, qe).codes == ("STATEMENT_INVALID",)


@case("PC2-19", "PC2-62")
@pytest.mark.parametrize("divergence", ["q_reviewer", "statement_issuer", "qe_issuer", "se_issuer",
                                        "root_version", "qe_version", "se_version"])
def test_one_author_and_one_root_version_for_both_records(w, divergence):
    def other(record, kind):
        return sign(record, kind, name=OTHER_ISSUER, label="pc2-issuer-2")
    qe, se = w.envelopes()
    if divergence == "q_reviewer":
        w.q["reviewer_id"] = OTHER_ISSUER
        w.rehash()
        qe = sign(w.q, c.QUAL)
    elif divergence == "statement_issuer":
        w.st["issuer_id"] = OTHER_ISSUER
        se = sign(w.st, c.STATEMENT)
    elif divergence in ("qe_issuer", "se_issuer"):
        qe, se = w.envelopes(other if divergence == "qe_issuer" else None,
                             other if divergence == "se_issuer" else None)
    elif divergence == "root_version":
        w.st["issuer_root_version"] = 2
        qe, se = w.envelopes()
    else:
        qe, se = w.envelopes(*(((lambda r, k: sign(r, k, version=2)), None) if divergence == "qe_version"
                               else (None, (lambda r, k: sign(r, k, version=2)))))
    assert w.statement(qe, se).codes == ("STATEMENT_INVALID",)


@case("PC2-20", "PC2-64")
@pytest.mark.parametrize("who", ["historical", "pilot", "sentinel", "candidate"])
def test_historical_reviewer_and_branch_prefixes_are_excluded(w, who):
    pilot, sentinel = w.context["pilot_record"], w.context["sentinel_record"]
    candidate = "7" * 64
    name = {"historical": "colony-review-481-r8", "pilot": "x-" + pilot["agent_id"][:16],
            "sentinel": "x-" + sentinel["agent_id"][:16], "candidate": "x-" + candidate[:16]}[who]
    w.q["reviewer_id"] = w.st["issuer_id"] = name
    w.rehash()
    if who == "historical":
        assert w.statement().codes == ("STATEMENT_INVALID",)
        return
    assert w.statement().status == "PASS"  # statement() does not carry the prefix exclusion (C11.2)
    with pytest.raises(lineage.LineageError) as raised:
        lineage.check_qualification(w.q, pilot, also_excluded=frozenset({candidate}))
    assert raised.value.code == "SELF_QUALIFICATION_DENIED"


@case("PC2-21", "PC2-80")
@pytest.mark.parametrize("trust_case", ["forged", "envelope_revoked", "key_revoked"])
def test_forged_and_genuinely_revoked_envelopes_never_pass_trust(w, trust_case):
    qe, _ = w.envelopes()
    root_value = trust_root()
    if trust_case == "forged":
        qe = {**qe, "signature": ("0" if qe["signature"][0] != "0" else "1") + qe["signature"][1:]}
    elif trust_case == "envelope_revoked":
        root_value = trust_root(revoked=(qe["envelope_id"],))
    else:
        root_value = trust_root(issuer(status="REVOKED"), version=2)
    result = verdict(w, qe, w.q, c.QUAL, root_value)
    assert result["attested"] is False
    expected = {"forged": "SIGNATURE_INVALID", "envelope_revoked": "ENVELOPE_REVOKED", "key_revoked": "KEY_REVOKED"}
    assert expected[trust_case] in result["failures"]
    assert result["genuine_but_revoked"] is (trust_case != "forged")


@case("PC2-22", "PC2-23")
@pytest.mark.parametrize("fresh", ["well_formed", "replayed_false", "historical_not_null"])
def test_fresh_under_p1_is_unsupported_after_its_grammar(w, fresh):
    w.st.update(scope=s.FRESH, campaign_replayed=True, campaign_evidence_sha256=w.q["evidence_sha256"],
                historical_record_path=None, historical_record_sha256=None, verified_at_source_sha="f" * 40)
    if fresh == "replayed_false":
        w.st["campaign_replayed"] = False
    elif fresh == "historical_not_null":
        w.st.update(historical_record_path=pc2.PC2_PATH, historical_record_sha256=pc2.PC2_PIN)
    assert pc2.select(f.canonical(w.q), f.canonical(w.st)) is None
    assert w.science().codes == ("SCIENTIFIC_PROFILE_UNSUPPORTED",) and w.science().status == c.NE
    statement = w.statement()
    assert statement.status == ("PASS" if fresh == "well_formed" else "FAIL")  # FAIL then dominates NE


@case("PC2-24", "PC2-77")
@pytest.mark.parametrize("field,value", [("campaign_replayed", True), ("campaign_evidence_sha256", "f" * 64),
                                         ("historical_signature_claimed", True), ("campaign_replayed", 0),
                                         ("historical_signature_claimed", None), ("historical_signature_claimed", 0),
                                         ("campaign_evidence_sha256", "")])
def test_present_claims_no_campaign_and_no_past_signature(w, field, value):
    w.st[field] = value
    assert w.statement().codes == ("STATEMENT_INVALID",)
    assert w.science().codes == ("STATEMENT_INVALID",)


@case("PC2-25", "PC2-61")
@pytest.mark.parametrize("change", ["third_code_hash_q", "third_code_hash_statement", "missing_q_field",
                                    "missing_read_q_field",
                                    "bool_version", "float", "upper_hex", "duplicate_key", "nan", "not_utf8"])
def test_closed_formats_and_strict_decoding(w, change):
    if change in ("third_code_hash_q", "missing_q_field", "missing_read_q_field"):
        if change == "third_code_hash_q":
            w.q["sentinel_evaluator_code_sha256"] = pc2.EVALUATOR_PIN
        else:
            del w.q["scope" if change == "missing_q_field" else "subject_code_sha256"]
        w.rehash()
        # C10.1/C13.3: science FAIL, lineage QUALIFICATION_INVALID; statement FAIL only for a field it reads.
        assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)
        with pytest.raises(lineage.LineageError) as raised:
            lineage.check_qualification(w.q, w.context["pilot_record"])
        assert raised.value.code == "QUALIFICATION_INVALID"
        statement = w.statement()
        assert (statement.status, statement.codes) == (("FAIL", ("STATEMENT_INVALID",))
            if change == "missing_read_q_field" else ("PASS", ()))
        return
    qe, se = w.envelopes()
    raw = f.canonical(w.st)
    if change == "third_code_hash_statement":
        raw = f.canonical({**w.st, "sentinel_evaluator_code_sha256": pc2.EVALUATOR_PIN})
    elif change == "bool_version":
        raw = f.canonical({**w.st, "issuer_root_version": True})
    elif change == "float":
        raw = raw.replace(b'"issuer_root_version":1', b'"issuer_root_version":1.0')
    elif change == "upper_hex":
        raw = f.canonical({**w.st, "verified_at_source_sha": "A" * 40})
    elif change == "duplicate_key":
        raw = raw.replace(b'"scope":', b'"scope":"FRESH_CAMPAIGN","scope":', 1)
    elif change == "nan":
        raw = raw.replace(b'"issuer_root_version":1', b'"issuer_root_version":NaN')
    else:
        raw = raw.replace(b'"verified_at_source_sha":"', b'"verified_at_source_sha":"\xff', 1)
    assert raw != f.canonical(w.st)
    fact = s.statement(raw, f.canonical(w.q), f.canonical(qe), f.canonical(se))
    assert (fact.status, fact.codes) == ("FAIL", ("STATEMENT_INVALID",))


@case("PC2-27")
@pytest.mark.parametrize("missing", ["sentinel_record", "sentinel_spec", "pilot_record", "pilot_spec"])
def test_absent_context_is_not_evaluated(w, missing):
    fact = w.science(**{missing: None})
    assert (fact.status, fact.codes) == (c.NE, ("SCIENTIFIC_SOURCE_UNAVAILABLE",))
    w.q["evidence_sha256"] = "a" * 64  # a proven contradiction dominates the missing context
    assert w.rehash().science(**{missing: None}).status == "FAIL"


@case("PC2-28")
def test_spec_artifact_hash_is_compared_beyond_a1_identity(w):
    spec = w.context["pilot_spec"]
    spec["created_at_utc"] = "2026-10-21T00:00:00Z"
    assert a1.agent_spec_id(spec) == pc2.PILOT["agent_spec_id"]
    w.reseal_record("pilot_record", lambda r: r.update(spec_artifact_hash=a1.spec_artifact_hash(spec)))
    lineage.verify_record(w.context["pilot_record"], spec, w.context["sentinel_record"], w.context["sentinel_spec"])
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


LINEAGE_MUTATIONS = {
    "parent": lambda r: r["lineage"].update(parent_agent_id="1" * 64),
    "founder": lambda r: r["lineage"].update(founder_agent_id="1" * 64),
    "generation": lambda r: r["lineage"].update(generation=2),
    "generation_bool": lambda r: r["lineage"].update(generation=True),
    "base_spec": lambda r: r["genotype"].update(base_agent_spec_id="1" * 64),
    "diff": lambda r: r["genotype"].update(declared_diff=[]),
    "widened": lambda r: r.update(lab_permissions=["DIAGNOSTIC_PRODUCE", "GOVERNED_ARTIFACT_READ"]),
    "memory": lambda r: r["memory"].update(inherits_parent_memory=True),
    "memory_int": lambda r: r["memory"].update(inherits_parent_memory=0),
    "credentials": lambda r: r.update(credentials="TOKEN"),
    "registry": lambda r: r["registry"].update(state="AVAILABLE"),
    "authority": lambda r: r.update(operational_authority="GRANTED"),
}


@case("PC2-29", "PC2-30", "PC2-32", "PC2-54")
@pytest.mark.parametrize("mutation", sorted(LINEAGE_MUTATIONS))
def test_pilot_lineage_context_is_exact(w, mutation):
    w.reseal_record("pilot_record", LINEAGE_MUTATIONS[mutation])
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-30", "PC2-54")
@pytest.mark.parametrize("mutation", ["narrowed", "generation_bool", "memory_int"])
def test_sentinel_parent_context_is_exact(w, mutation):
    change = {"narrowed": lambda r: r.update(lab_permissions=["DIAGNOSTIC_PRODUCE"]),
              "generation_bool": lambda r: r["lineage"].update(generation=False),
              "memory_int": lambda r: r["memory"].update(inherits_parent_memory=0)}[mutation]
    w.reseal_record("sentinel_record", change)
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-31", "PC2-54")
@pytest.mark.parametrize("name", sorted(pc2.BUDGET))
@pytest.mark.parametrize("value", ["lower", "bool", "float_like"])
@pytest.mark.parametrize("record", ["pilot_record", "sentinel_record"])
def test_each_campaign_budget_is_exact_without_coercion(w, name, value, record):
    amount = pc2.BUDGET[name]
    if value == "float_like":
        # Lab sealing refuses floats; acquired bytes carrying one are not strictly decodable.
        raw = f.canonical(w.context[record])
        old = f'"{name}":{amount}'.encode()
        assert raw.count(old) == 1
        fact = w.science(**{record: raw.replace(old, old + b".0")})
        assert fact.codes == ("STORED_FILE_DIVERGENT",)
        return
    replacement = {"lower": amount - 1, "bool": True}[value]
    w.reseal_record(record, lambda r: r["budget"].update({name: replacement}))
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-33")
def test_pc2_q_is_not_the_birth_qualification_of_the_pilot(w):
    with pytest.raises(lineage.LineageError) as raised:
        lineage.check_qualification(w.q, w.context["sentinel_record"])
    assert raised.value.code == "QUALIFICATION_NOT_FOR_THIS_SPEC"


@case("PC2-35", "PC2-80")
def test_qualification_items_keep_full_record_digest(w):
    needs = {}
    c._add(needs, c.QUAL, w.q, "decision/qualification", "a" * 64)
    c._add(needs, c.QUAL, w.q, "other-home/birth", "a" * 64)
    revoked = {**w.q, "state": "REVOKED"}
    c._add(needs, c.QUAL, revoked, "later/qualification", "b" * 64)
    assert len(needs) == 2 and needs[c.key(c.QUAL, w.q)].namespaces == ("decision/qualification", "other-home/birth")
    assert w.science().status == "PASS"  # the earlier q is evaluated unchanged
    later = World()
    later.q["state"] = "REVOKED"
    assert later.rehash().science().codes == ("SCIENTIFIC_DIVERGENCE",)


NATIVE_MUTATIONS = {
    "PC2-36": {"PC2": lambda d: d["parent"]["qualification"].update(reviewer_id="someone-else")},
    "PC2-36/canonical_record_hash": {"PC2": lambda d: d["parent"].update(
        record_sha256=f.digest(json.loads((ROOT / s.HISTORY_PATH).read_bytes())))},
    "PC2-37/r8q_evidence": {"R8Q": lambda d: d.update(evidence_sha256="1" * 64)},
    "PC2-37/r8q_criteria": {"R8Q": lambda d: d.update(criteria_sha256="1" * 64)},
    "PC2-37/flag_only": {"PC2": lambda d: d["parent"].update(mismatched=["evidence_sha256"])},
    "PC2-38/revision": {"PC2": lambda d: d.update(criteria_revision="p0")},
    "PC2-38/status": {"PC2": lambda d: d.update(criteria_status="SUPERSEDED")},
    "PC2-38/schema": {"PC2": lambda d: d.update(evidence_schema="colony-lab.pilot-evidence/1")},
    "PC2-38/scope": {"PC2": lambda d: d.update(scope="LIVE")},
    "PC2-38/state": {"PC2": lambda d: d.update(proposed_state="QUALIFIED_SIMULATED")},
    "PC2-38/failures": {"PC2": lambda d: d.update(failure_reasons=["x"])},
    "PC2-38/irregular": {"PC2": lambda d: d.update(code_irregular=["x"])},
    "PC2-38/deterministic": {"PC2": lambda d: d.update(deterministic_across_fresh_labs=1)},
    "PC2-38/source_only": {"PC2": lambda d: d["evaluator_runtime"].update(source_only=1)},
    "PC2-38/sandbox": {"PC2": lambda d: d["sandbox_view"].update(matches_subject=False)},
    "PC2-38/env_sandbox": {"PC2": lambda d: d["environment"].update(sandbox="UNVERIFIED")},
    "PC2-39/subject": {"C9": lambda d: d["subject"].update(agent_id="1" * 64)},
    "PC2-39/golden": {"C9": lambda d: d.update(golden_subject_code_matches=False)},
    "PC2-39/runtime": {"C9": lambda d: d["evaluator_runtime"].update(source_only=False)},
    "PC2-39/state": {"C9": lambda d: d.update(proposed_state="FAILED")},
    "PC2-39/criteria": {"C9": lambda d: d.update(criteria_revision="r7")},
    "PC2-40/not_claimed": {"PC2": lambda d: d["not_claimed"].pop()},
    "PC2-40/record_file": {"P1C": lambda d: d["parent"].update(record_file="../SENTINEL_QUALIFICATION_RECORD_R8.json")},
    "PC2-40/purpose": {"P1C": lambda d: d["pilot"].update(purpose="Another purpose.")},
    "PC2-40/permissions": {"P1C": lambda d: d["pilot"].update(lab_permissions=["GOVERNED_ARTIFACT_READ"])},
    "PC2-40/native_pilot": {"PC2": lambda d: d["pilot"].update(generation=True)},
    "PC2-41/omit": {"PC2": lambda d: [r.pop(5) for r in d["rounds"]]},
    "PC2-41/duplicate": {"PC2": lambda d: [r.__setitem__(5, copy.deepcopy(r[4])) for r in d["rounds"]]},
    "PC2-41/permute": {"PC2": lambda d: [r.insert(0, r.pop(1)) for r in d["rounds"]]},
    "PC2-41/failed": {"PC2": lambda d: [r[3].update(passed=False) for r in d["rounds"]]},
    "PC2-41/predicates": {"PC2": lambda d: [r[3].update(failed_predicates=["x"]) for r in d["rounds"]]},
    "PC2-41/one_round": {"PC2": lambda d: d["rounds"].pop()},
    "PC2-42/different_rounds": {"PC2": lambda d: d["rounds"][1][0].update(facts_sha256="1" * 64)},
    "PC2-42/malformed": {"PC2": lambda d: [r[0].update(facts_sha256="X" * 64) for r in d["rounds"]]},
    "PC2-41/passed_int": {"PC2": lambda d: [r[3].update(passed=1) for r in d["rounds"]]},
    "PC2-41/27_consistent": {"P1C": lambda d: d["birth_trials"].pop(11),
                             "PC2": lambda d: [r.pop(11) for r in d["rounds"]]},
    "PC2-38/criteria_pin": {"PC2": lambda d: d.update(criteria_sha256="1" * 64)},
    "PC2-38/missing_key": {"PC2": lambda d: d.pop("proposed_state")},
    "PC2-36/parent_agent": {"PC2": lambda d: d["parent"].update(agent_id="1" * 64)},
    "PC2-36/parent_spec": {"PC2": lambda d: d["parent"].update(agent_spec_id="1" * 64)},
    "PC2-37/matches_int": {"PC2": lambda d: d["parent"].update(matches_current_code=1)},
    "PC2-37/r8q_spec": {"R8Q": lambda d: d.update(agent_spec_id="1" * 64)},
    "PC2-37/r8q_state": {"R8Q": lambda d: d.update(state="FAILED")},
    "PC2-37/r8q_scope": {"R8Q": lambda d: d.update(scope="LIVE")},
    "PC2-39/c9_status": {"C9": lambda d: d.update(criteria_status="SUPERSEDED")},
    "PC2-39/c9_criteria_pin": {"C9": lambda d: d.update(criteria_sha256="1" * 64)},
    "PC2-39/c9_failures": {"C9": lambda d: d.update(failure_reasons=["x"])},
    "PC2-39/c9_irregular": {"C9": lambda d: d.update(code_irregular=["x"])},
    "PC2-39/c9_deterministic": {"C9": lambda d: d.update(deterministic_across_fresh_labs=1)},
    "PC2-40/p1c_schema": {"P1C": lambda d: d.update(criteria_schema="colony-lab.pilot-criteria/1")},
    "PC2-40/p1c_scope": {"P1C": lambda d: d.update(scope="LIVE")},
    "PC2-40/p1c_parent_revision": {"P1C": lambda d: d["parent"].update(criteria_revision="r7")},
    "PC2-40/p1c_evidence_file": {"P1C": lambda d: d["parent"].update(evidence_file="evidence/C8_sentinel_evidence.json")},
    "PC2-40/p1c_declared_diff": {"P1C": lambda d: d["pilot"].update(declared_diff=["display_name", "purpose"])},
    "PC2-40/p1c_parent_permissions": {"P1C": lambda d: d["pilot"].update(parent_lab_permissions=["DIAGNOSTIC_PRODUCE"])},
    "PC2-40/p1c_canonical_name": {"P1C": lambda d: d["pilot"].update(canonical_name="sentinel_pilot_02")},
    "PC2-40/p1c_display_name": {"P1C": lambda d: d["pilot"].update(display_name="Sentinel Pilot 02")},
    "PC2-40/native_extra_key": {"PC2": lambda d: d["pilot"].update(note="extra")},
    # Review 3: literal true, exact lists, exact round count, unique ids, full R8Q, no name folding.
    "PC2-38/sandbox_int": {"PC2": lambda d: d["sandbox_view"].update(matches_subject=1)},
    "PC2-39/golden_int": {"C9": lambda d: d.update(golden_subject_code_matches=1)},
    "PC2-39/runtime_int": {"C9": lambda d: d["evaluator_runtime"].update(source_only=1)},
    "PC2-41/predicates_none": {"PC2": lambda d: [r[3].update(failed_predicates=None) for r in d["rounds"]]},
    "PC2-41/predicates_empty_string": {"PC2": lambda d: [r[3].update(failed_predicates="") for r in d["rounds"]]},
    "PC2-41/three_rounds": {"PC2": lambda d: d["rounds"].append(copy.deepcopy(d["rounds"][0]))},
    "PC2-41/duplicate_criteria_id": {
        "P1C": lambda d: d["birth_trials"][1].update(id=d["birth_trials"][0]["id"]),
        "PC2": lambda d: [r[1].update(id=r[0]["id"]) for r in d["rounds"]]},
    "PC2-42/second_round_passed_int": {"PC2": lambda d: d["rounds"][1][3].update(passed=1)},
    "PC2-40/record_file_suffix": {"P1C": lambda d: d["parent"].update(record_file="RECORD_R8.json")},
    "PC2-37/parent_qualification_extra_key": {"PC2": lambda d: d["parent"]["qualification"].update(note="x")},
    "PC2-40/purpose_case": {"P1C": lambda d: d["pilot"].update(purpose=d["pilot"]["purpose"].upper())},
}


def _systematic_native_mutations():
    """Review 4: every C6 guard of _native, each against several near values, never one counterexample."""
    docs = {"PC2": json.loads((ROOT / pc2.PC2_PATH).read_bytes()), "C9": json.loads((ROOT / s.EVIDENCE_PATH).read_bytes()),
            "R8Q": json.loads((ROOT / s.HISTORY_PATH).read_bytes()), "P1C": json.loads((ROOT / pc2.P1C_PATH).read_bytes())}

    def get(doc, path):
        node = docs[doc]
        for key in path:
            node = node[key]
        return node

    def setter(path, value):
        def edit(d):
            for key in path[:-1]:
                d = d[key]
            d[path[-1]] = copy.deepcopy(value)
        return edit

    out = {}

    def add(case_id, doc, path, label, value):
        assert get(doc, path) != value or type(get(doc, path)) is not type(value)
        out[f"{case_id}/sys_{doc}_{'.'.join(path)}_{label}"] = {doc: setter(path, value)}

    empty = [("PC2-38", "PC2", ("failure_reasons",)), ("PC2-38", "PC2", ("code_irregular",)),
             ("PC2-37", "PC2", ("parent", "mismatched")), ("PC2-39", "C9", ("failure_reasons",)),
             ("PC2-39", "C9", ("code_irregular",))]
    for case_id, doc, path in empty:
        assert get(doc, path) == []
        for label, value in (("none", None), ("text", ""), ("zero", 0), ("false", False), ("object", {})):
            add(case_id, doc, path, label, value)
    literal = [("PC2-38", "PC2", ("deterministic_across_fresh_labs",)), ("PC2-38", "PC2", ("evaluator_runtime", "source_only")),
               ("PC2-38", "PC2", ("sandbox_view", "matches_subject")), ("PC2-37", "PC2", ("parent", "matches_current_code")),
               ("PC2-39", "C9", ("deterministic_across_fresh_labs",)), ("PC2-39", "C9", ("golden_subject_code_matches",)),
               ("PC2-39", "C9", ("evaluator_runtime", "source_only"))]
    for case_id, doc, path in literal:
        assert get(doc, path) is True
        for label, value in (("one", 1), ("text", "true"), ("list", [True])):
            add(case_id, doc, path, label, value)
    exact = [("PC2-38", "PC2", ("evidence_schema",)), ("PC2-38", "PC2", ("criteria_revision",)),
             ("PC2-38", "PC2", ("criteria_status",)), ("PC2-38", "PC2", ("scope",)),
             ("PC2-38", "PC2", ("proposed_state",)), ("PC2-38", "PC2", ("environment", "sandbox")),
             ("PC2-39", "C9", ("criteria_revision",)), ("PC2-39", "C9", ("criteria_status",)),
             ("PC2-39", "C9", ("proposed_state",)), ("PC2-37", "R8Q", ("state",)), ("PC2-37", "R8Q", ("scope",)),
             ("PC2-40", "P1C", ("criteria_schema",)), ("PC2-40", "P1C", ("revision",)), ("PC2-40", "P1C", ("scope",)),
             ("PC2-40", "P1C", ("parent", "criteria_revision")), ("PC2-40", "P1C", ("parent", "record_file")),
             ("PC2-40", "P1C", ("parent", "evidence_file")), ("PC2-40", "P1C", ("pilot", "canonical_name")),
             ("PC2-40", "P1C", ("pilot", "display_name")), ("PC2-40", "P1C", ("pilot", "purpose"))]
    for case_id, doc, path in exact:
        value = get(doc, path)
        variants = {"lower": value.lower(), "upper": value.upper(), "lead": " " + value, "trail": value + " "}
        for label, variant_value in variants.items():
            if variant_value != value:
                add(case_id, doc, path, label, variant_value)
    alternatives = [("PC2-38", "PC2", ("criteria_status",), "DRAFT"), ("PC2-39", "C9", ("criteria_status",), "DRAFT"),
                    ("PC2-37", "R8Q", ("scope",), "LIVE_SIMULATED"), ("PC2-37", "R8Q", ("state",), "REVOKED"),
                    ("PC2-40", "P1C", ("parent", "evidence_file"), s.EVIDENCE_PATH.rsplit("/", 1)[1][1:]),
                    ("PC2-40", "P1C", ("parent", "record_file"), s.HISTORY_PATH.rsplit("/", 1)[1][1:])]
    for case_id, doc, path, value in alternatives:
        add(case_id, doc, path, "alternative", value)
    sentinel_ids = {"agent_id": pc2.SENTINEL["agent_id"], "agent_spec_id": pc2.SENTINEL["agent_spec_id"]}
    pilot_ids = {"agent_id": pc2.PILOT["agent_id"], "agent_spec_id": pc2.PILOT["agent_spec_id"]}
    for case_id, doc, prefix in (("PC2-36", "PC2", ("parent",)), ("PC2-39", "C9", ("subject",)), ("PC2-37", "R8Q", ())):
        for key, value in sentinel_ids.items():
            assert get(doc, prefix + (key,)) == value
            add(case_id, doc, prefix + (key,), "pilot", pilot_ids[key])
            add(case_id, doc, prefix + (key,), "upper", value.upper())
    native = {"agent_id": pc2.SENTINEL["agent_id"], "agent_spec_id": pc2.SENTINEL["agent_spec_id"],
              "spec_artifact_hash": pc2.SENTINEL["spec_artifact_hash"], "lab_permissions": pc2.SENTINEL_PERMISSIONS,
              "declared_diff": [], "generation": 0}
    assert set(native) == set(get("PC2", ("pilot",)))
    for key, value in native.items():
        add("PC2-40", "PC2", ("pilot", key), "parent_value", value)
    out["PC2-40/sys_not_claimed_order"] = {"PC2": lambda d: d["not_claimed"].reverse()}
    out["PC2-41/sys_last_id"] = {"PC2": lambda d: [r[-1].update(id="P02-other") for r in d["rounds"]]}
    out["PC2-41/sys_last_failed"] = {"PC2": lambda d: [r[-1].update(passed=False) for r in d["rounds"]]}
    out["PC2-41/sys_last_predicates"] = {"PC2": lambda d: [r[-1].update(failed_predicates=["x"]) for r in d["rounds"]]}
    out["PC2-42/sys_last_facts"] = {"PC2": lambda d: [r[-1].update(facts_sha256="X" * 64) for r in d["rounds"]]}
    out["PC2-42/sys_facts_none"] = {"PC2": lambda d: [r[0].update(facts_sha256=None) for r in d["rounds"]]}
    assert not set(out) & set(NATIVE_MUTATIONS)
    return out


NATIVE_MUTATIONS.update(_systematic_native_mutations())


@case("PC2-36", "PC2-37", "PC2-38", "PC2-39", "PC2-40", "PC2-41", "PC2-42", "PC2-05")
@pytest.mark.parametrize("name", sorted(NATIVE_MUTATIONS))
def test_native_bindings_hold_behind_instrumented_pins(name):
    world = World().reseal(**NATIVE_MUTATIONS[name])
    tripwire = world.science()  # the raw pin, before any semantic guard
    if "P1C" in NATIVE_MUTATIONS[name]:
        assert (tripwire.status, tripwire.codes) == (c.NE, ("SCIENTIFIC_PROFILE_UNSUPPORTED",))
    else:
        assert tripwire.status == "FAIL" and "SCIENTIFIC_DIVERGENCE" in tripwire.codes
    instrumented = variant(world)
    assert World().science(variant(World())).status == "PASS"
    fact = world.science(instrumented)
    assert fact.status == "FAIL" and fact.codes == ("SCIENTIFIC_DIVERGENCE",)  # the semantic guard itself


@case("PC2-68")
def test_declared_environment_is_never_compared(w):
    w.reseal(PC2=lambda d: d["environment"].update(python="3.99.0", platform="other"))
    assert w.science(variant(w)).status == "PASS"


CLOSURE_MUTANTS = {
    "S/q": ('s_values = [q["subject_code_sha256"], st["subject_code_sha256"]]', 's_values = [st["subject_code_sha256"]]'),
    "S/statement": ('s_values = [q["subject_code_sha256"], st["subject_code_sha256"]]', 's_values = [q["subject_code_sha256"]]'),
    "S/pc2": ('s_values += [pc2["subject_code_sha256"], ', 's_values += ['),
    "S/c9": ('c9["subject"]["subject_code_sha256"], r8q["subject_code_sha256"]]', 'r8q["subject_code_sha256"]]'),
    "S/r8q": ('c9["subject"]["subject_code_sha256"], r8q["subject_code_sha256"]]', 'c9["subject"]["subject_code_sha256"]]'),
    "S/digest": ("s_values += [] if subject is None else [subject]", "s_values += []"),
    "P/q": ('p_values = [q["evaluator_code_sha256"], st["evaluator_code_sha256"]]', 'p_values = [st["evaluator_code_sha256"]]'),
    "P/statement": ('p_values = [q["evaluator_code_sha256"], st["evaluator_code_sha256"]]', 'p_values = [q["evaluator_code_sha256"]]'),
    "P/pc2": ('p_values += [pc2["pilot_code_sha256"]]', 'p_values += []'),
    "P/digest": ("p_values += [] if pilot is None else [pilot]", "p_values += []"),
    "P/pin_is_E": ("(PILOT_PIN, p_values)", "(EVALUATOR_PIN, p_values)"),
    "E/pc2": ('e_values += [pc2["sentinel_evaluator_code_sha256"], c9["evaluator_code_sha256"],',
              'e_values += [c9["evaluator_code_sha256"],'),
    "E/c9": ('c9["evaluator_code_sha256"],\n', '\n'),
    "E/r8q": ('                     r8q["evaluator_code_sha256"]]', '                     ]'),
    "E/digest": ("e_values += [] if evaluator is None else [evaluator]", "e_values += []"),
    "E/all": ("(EVALUATOR_PIN, e_values)", "(EVALUATOR_PIN, [])"),
}


def closure_scenarios():
    """Single-value divergences of S/P/E, each in claims, artifacts (instrumented) or digest."""
    def q_and_statement(field, role):
        def build():
            w = World()
            w.q[field] = "1" * 64 if role == "q" else w.q[field]
            w.st[field] = "1" * 64 if role == "statement" else w.st[field]
            return w.rehash()
        return build

    def artifact(alias, change):
        return lambda: World().reseal(**{alias: change})

    def digest(index):
        def build():
            w = World()
            w.digests[index] = "1" * 64
            return w
        return build

    return {
        "positive": World,
        "S/q": q_and_statement("subject_code_sha256", "q"),
        "S/statement": q_and_statement("subject_code_sha256", "statement"),
        "P/q": q_and_statement("evaluator_code_sha256", "q"),
        "P/statement": q_and_statement("evaluator_code_sha256", "statement"),
        "S/pc2": artifact("PC2", lambda d: d.update(subject_code_sha256="1" * 64)),
        "S/c9": artifact("C9", lambda d: d["subject"].update(subject_code_sha256="1" * 64)),
        "S/r8q": artifact("R8Q", lambda d: d.update(subject_code_sha256="1" * 64)),
        "P/pc2": artifact("PC2", lambda d: d.update(pilot_code_sha256="1" * 64)),
        "E/pc2": artifact("PC2", lambda d: d.update(sentinel_evaluator_code_sha256="1" * 64)),
        "E/c9": artifact("C9", lambda d: d.update(evaluator_code_sha256="1" * 64)),
        "E/r8q": artifact("R8Q", lambda d: d.update(evaluator_code_sha256="1" * 64)),
        "S/digest": digest(0), "E/digest": digest(1), "P/digest": digest(2),
    }


@case("PC2-06", "PC2-07", "PC2-08", "PC2-09")
@pytest.mark.parametrize("mutant", sorted(CLOSURE_MUTANTS))
def test_every_s_e_p_binding_mutant_is_killed(mutant):
    scenarios = closure_scenarios()
    killed = []
    for name, build in scenarios.items():
        world = build()
        expected = world.science(variant(world)).status
        assert expected == ("PASS" if name == "positive" else "FAIL"), name
        if world.science(variant(world, (CLOSURE_MUTANTS[mutant],))).status != expected:
            killed.append(name)
    assert killed, mutant


@case("PC2-58")
@pytest.mark.parametrize("q_criteria,s_criteria", [(pc2.P1C_PIN, s.CRITERIA_PIN), (s.CRITERIA_PIN, pc2.P1C_PIN)])
def test_selection_reads_q_criteria_and_statement_must_equal_it(w, q_criteria, s_criteria):
    w.q["criteria_sha256"], w.st["criteria_sha256"] = q_criteria, s_criteria
    w.rehash()
    assert w.statement().codes == ("STATEMENT_INVALID",)
    assert pc2.select(f.canonical(w.q), f.canonical(w.st)) == (
        pc2.PROFILE if q_criteria == pc2.P1C_PIN else pc2.R8_PROFILE)
    if q_criteria == pc2.P1C_PIN:
        assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-59")
def test_a_later_profile_version_re_evaluates_without_writing(w):
    v1 = variant(replace=(('PILOT_PIN = "97fb', 'PILOT_PIN = "07fb'), ('PROFILE = "pilot-p1-pc2-present-native-v0"',
                                                                    'PROFILE = "pilot-p1-pc2-present-native-v1"')))
    assert w.science().status == "PASS"
    assert w.science(v1).codes == ("SCIENTIFIC_DIVERGENCE",)
    assert not any(isinstance(v, (str, bytes)) and "v0" in str(v) for v in w.science().__dict__.values())


@case("PC2-60")
@pytest.mark.parametrize("target", ["statement", "qe", "both"])
def test_only_canonical_h_of_q_is_admitted(w, target):
    loose = hashlib.sha256(json.dumps(w.q, indent=1).encode()).hexdigest()
    assert loose != f.digest(w.q)
    qe, se = w.envelopes()
    if target in ("statement", "both"):
        w.st["qualification_record_sha256"] = loose
        se = sign(w.st, c.STATEMENT)
    if target in ("qe", "both"):
        qe = {**qe, "record_sha256": loose}
        integrity = verdict(w, qe, w.q, c.QUAL, trust_root())["integrity"]
        assert integrity != "PASS"
    assert w.statement(qe, se).codes == ("STATEMENT_INVALID",)


@case("PC2-63", "PC2-66")
@pytest.mark.parametrize("variant_name", ["qualification_only", "statement_only", "absent_issuer", "no_scope"])
def test_issuer_needs_both_kinds_in_the_current_lab_test_root(w, variant_name):
    qe, se = w.envelopes()
    roots = {"qualification_only": trust_root(issuer(scopes=(c.QUAL,))),
             "statement_only": trust_root(issuer(scopes=(c.STATEMENT,))),
             "absent_issuer": trust_root(issuer(name=OTHER_ISSUER, label="pc2-issuer-2")),
             "no_scope": trust_root(issuer(scopes=(c.ADM,)))}
    root_value = roots[variant_name]
    q_result = verdict(w, qe, w.q, c.QUAL, root_value)
    s_result = verdict(w, se, w.st, c.STATEMENT, root_value)
    assert "PASS" not in (q_result["authorization"] if variant_name != "qualification_only" else "x",
                          s_result["authorization"] if variant_name != "statement_only" else "x")
    failures = set(q_result["failures"]) | set(s_result["failures"])
    assert failures & ({"UNKNOWN_ISSUER"} if variant_name == "absent_issuer" else {"SCOPE_NOT_GRANTED"})
    if variant_name == "qualification_only":
        assert q_result["authorization"] == "PASS" and s_result["authorization"] != "PASS"
    if variant_name == "statement_only":
        assert s_result["authorization"] == "PASS" and q_result["authorization"] != "PASS"


@case("PC2-65", "PC2-53")
def test_outputs_never_claim_review_qualification_or_provenance(w):
    fact = w.science()
    assert fact.status == "PASS" and fact.accepted is False and fact.source_revision_provenance == c.NE
    assert set(fact.__dataclass_fields__) == {"status", "codes", "accepted", "source_revision_provenance"}
    assert not [n for n in vars(pc2) if re.search("qualif|review|issue|sign|admi", n, re.IGNORECASE)
                and n not in ("QUALIFICATION_FIELDS", "_qualification")]


@case("PC2-71")
def test_zero_writes_on_fail_ne_and_pass(w, monkeypatch):
    import builtins

    def refuse(*args, **kwargs):
        raise AssertionError("write or open attempted")
    for target, name in ((builtins, "open"), (os, "open"), (os, "remove"), (os, "unlink"), (os, "rename"),
                         (os, "replace"), (os, "mkdir"), (os, "write")):
        monkeypatch.setattr(target, name, refuse)
    results = {w.science().status, w.science(pilot_record=None).status}
    w.digests[0] = "c" * 64
    results.add(w.science().status)
    assert results == {"PASS", c.NE, "FAIL"}
    tree = ast.parse(inspect.getsource(pc2))
    calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not calls & {"open", "os.open", "os.read", "Path", "eval", "exec", "__import__",
                        "trust.verify_bundle", "trust._spend", "reg.load_policy"}


@case("PC2-79")
@pytest.mark.parametrize("state", ["FAILED", "IN_TRIAL", "REVOKED", "UNQUALIFIED"])
def test_a_signed_unqualified_state_is_never_pass(w, state):
    w.q["state"] = state
    assert w.rehash().statement().status == "PASS"
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)
    with pytest.raises(lineage.LineageError) as raised:
        lineage.check_qualification(w.q, w.context["pilot_record"])
    assert raised.value.code == "PARENT_NOT_QUALIFIED"


@case("PC2-74")
def test_r8_profile_selection_and_reader_unchanged(w):
    from tests.colony_admission import test_attestation_core as r8_tests
    assert pc2.select(f.canonical({"criteria_sha256": s.CRITERIA_PIN}), f.canonical({"scope": s.FRESH})) == pc2.R8_PROFILE
    assert pc2.select(b"not json", f.canonical(w.st)) is None
    assert s.scientific_bindings.__module__ == "colony_admission._attestation_statement"
    assert hasattr(r8_tests, "test_science_binds_actual_pinned_bytes_not_merely_matching_claims")


@case("PC2-50", "PC2-56", "PC2-73")
def test_p1_scenarios_g0_and_matrix_bytes_unchanged():
    def raw(path):
        return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    assert raw("docs/colony_admission/ADMISSION_CONTRACT.md") == \
        "e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd"
    assert raw("docs/colony_admission/SCENARIOS_A0.json") == \
        "4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1"
    assert raw("docs/colony_registrar/POLICY_G0.json") == "04c8905f6f7ad27f7e45fb8657f79b9c2288f8153f18338aa3b9c85f1e71465d"
    g0, g0_pin = reg.load_policy()
    assert g0_pin == "1226d889505e84b970be47b442c1db33ab85bcdba953a4f818a1f5a7dec4caff"
    assert pc2.P1C_PIN in g0["admissible_parent_criteria_sha256"]
    assert raw(MATRIX.relative_to(ROOT)) == "c5b170e3f8ac7898465458c8ad3bb1c85d74b0d7c57430f93b2b35941c0920dc"
    assert json.loads(MATRIX.read_bytes())["counts"]["executed"] == 0
    for path, digest in pc2.PINS.items():
        assert raw(path) == digest


def test_delivery_table_classifies_every_case_and_names_real_tests():
    matrix = [x["id"] for x in json.loads(MATRIX.read_bytes())["cases"]]
    assert len(matrix) == 80 == len(set(matrix))
    rows = re.findall(r"^\| (PC2-\d\d) \| ([A-Z0-9_]+) \|", DELIVERY.read_text(), re.MULTILINE)
    statuses = dict(rows)
    assert [x for x, _ in rows] == matrix
    allowed = {"IMPLEMENTED_C8_3", "PARTIAL_C8_3", "DEFERRED_C8_4", "REVIEW_GATE", "OUTSIDE_SCANNER"}
    assert set(statuses.values()) <= allowed
    tested = {x for x, v in statuses.items() if v in ("IMPLEMENTED_C8_3", "PARTIAL_C8_3")}
    assert set(CASES) == tested
    names = {n for n, v in globals().items() if n.startswith("test_") and callable(v)}
    assert all(set(v) <= names for v in CASES.values())
    listed = dict(re.findall(r"^\| (PC2-\d\d) \| [A-Z0-9_]+ \| [^|]* \| ([^|]*) \|", DELIVERY.read_text(), re.MULTILINE))
    for x in matrix:
        cell = set(re.findall(r"`(test_[a-z0-9_]+)`", listed[x]))
        assert cell == CASES.get(x, set()), x
    clauses = {x["id"]: x["clauses"] for x in json.loads(MATRIX.read_bytes())["cases"]}
    cited = dict(re.findall(r"^\| (PC2-\d\d) \| [A-Z0-9_]+ \| ([^|]*) \|", DELIVERY.read_text(), re.MULTILINE))
    for x in matrix:
        assert [v.strip() for v in cited[x].split(",")] == clauses[x], x


@pytest.mark.parametrize("path", sorted(pc2.PINS))
def test_absent_or_oversized_artifact_and_unknown_scope(w, path):
    # C13.0/C13.3 without a matrix case of their own: absence NE, size FAIL, scope FAIL.
    absent = World()
    absent.raw[path] = None
    assert (absent.science().status, absent.science().codes) == (c.NE, ("SCIENTIFIC_SOURCE_UNAVAILABLE",))
    del absent.raw[path]
    assert absent.science().codes == ("SCIENTIFIC_SOURCE_UNAVAILABLE",)
    w.raw[path] = b" " * (16 * 1024 * 1024 + 1)
    assert w.science().codes == ("SOURCE_LIMIT",)
    other = World()
    other.st["scope"] = "OTHER"
    assert other.science().codes == ("STATEMENT_INVALID",)


@case("PC2-29", "PC2-32")
@pytest.mark.parametrize("record", ["pilot_record", "sentinel_record"])
@pytest.mark.parametrize("forgery", ["record_hash", "individual_schema"])
def test_context_records_are_verified_not_only_compared(w, record, forgery):
    # The context is the one input no raw pin covers: lineage.verify_record must run on it.
    if forgery == "record_hash":
        w.context[record]["record_hash"] = "0" * 64
    else:
        w.reseal_record(record, lambda r: r.update(individual_schema="colony-lab.individual/9"))
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-27")
def test_context_must_be_the_closed_context_type(w):
    values = tuple(f.canonical(v) for v in w.context.values())
    fact = pc2.bindings(f.canonical(w.st), f.canonical(w.q), dict(w.raw), *w.digests, values)
    assert (fact.status, fact.codes) == (c.NE, ("SCIENTIFIC_SOURCE_UNAVAILABLE",))
    absent = pc2.bindings(f.canonical(w.st), f.canonical(w.q), dict(w.raw), *w.digests, None)
    assert (absent.status, absent.codes) == (c.NE, ("SCIENTIFIC_SOURCE_UNAVAILABLE",))


@case("PC2-13", "PC2-15", "PC2-16", "PC2-25")
@pytest.mark.parametrize("change", ["history_path", "q_schema", "statement_evidence", "statement_subject",
                                    "statement_subject_spec"])
def test_each_q_and_statement_binding_on_its_own(w, change):
    if change == "history_path":
        w.st["historical_record_path"] = "docs/colony_lab/evidence/PC2_pilot_evidence_copy.json"
        expected = "STATEMENT_INVALID"
    elif change == "q_schema":
        w.q["qualification_schema"] = "colony-lab.qualification/1"
        expected = "SCIENTIFIC_DIVERGENCE"
    elif change == "statement_evidence":
        w.st["evidence"] = [{"path": pc2.PC2_PATH, "sha256": pc2.PC2_PIN},
                            {"path": pc2.P1C_PATH, "sha256": pc2.P1C_PIN}]
        expected = "SCIENTIFIC_DIVERGENCE"
    elif change == "statement_subject":
        w.st["subject_agent_id"] = w.context["sentinel_record"]["agent_id"]
        expected = "SCIENTIFIC_DIVERGENCE"
    else:
        w.st["subject_agent_spec_id"] = w.context["sentinel_record"]["agent_spec_id"]
        expected = "SCIENTIFIC_DIVERGENCE"
    assert w.rehash().science().codes == (expected,)


@case("PC2-04")
def test_a_canonical_hash_equal_to_the_pin_is_not_a_raw_pin(w):
    # Instrument the PC2 pin as H(PC2): only SHA256(raw) may satisfy it.
    w.reseal(PC2=lambda d: None)
    canonical = f.digest(json.loads(w.raw[pc2.PC2_PATH]))
    assert canonical != w.pins[pc2.PC2_PATH]
    w.pins[pc2.PC2_PATH] = canonical
    w.q["evidence_sha256"] = w.st["historical_record_sha256"] = canonical
    w.st["evidence"] = [{"path": pc2.PC2_PATH, "sha256": canonical}]
    assert w.rehash().science(variant(w)).codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-05")
def test_a_divergent_artifact_dominates_an_absent_one(w):
    w.raw[s.CRITERIA_PATH] = None
    w.raw[pc2.PC2_PATH] += b"\n"
    assert w.science().status == "FAIL"


@case("PC2-05", "PC2-27")
def test_a_divergent_context_dominates_an_absent_artifact(w):
    w.raw[pc2.PC2_PATH] = None
    w.context["sentinel_record"]["record_hash"] = "0" * 64
    assert (w.science().status, w.science().codes) == ("FAIL", ("SCIENTIFIC_DIVERGENCE",))


@case("PC2-22")
def test_a_statement_without_scope_is_refused_not_raised(w):
    del w.st["scope"]
    fact = pc2.bindings(f.canonical(w.st), f.canonical(w.q), dict(w.raw), *w.digests, w.context_bytes())
    assert (fact.status, fact.codes) == ("FAIL", ("STATEMENT_INVALID",))


@case("PC2-61")
@pytest.mark.parametrize("change", ["float", "duplicate_key", "duplicate_same_value", "nan", "not_utf8"])
def test_strict_decoding_of_q(w, change):
    raw = f.canonical(w.q)
    marker = b'"state":"QUALIFIED_SIMULATED"'
    replacement = {"float": b'"state":1.5', "duplicate_key": marker + b',"state":"FAILED"',
                   "duplicate_same_value": marker + b"," + marker, "nan": b'"state":NaN',
                   "not_utf8": b'"state":"\xff"'}[change]
    raw = raw.replace(marker, replacement)
    assert raw != f.canonical(w.q)
    qe, se = w.envelopes()
    statement = s.statement(f.canonical(w.st), raw, f.canonical(qe), f.canonical(se))
    assert (statement.status, statement.codes) == ("FAIL", ("STATEMENT_INVALID",))
    science = pc2.bindings(f.canonical(w.st), raw, dict(w.raw), *w.digests, w.context_bytes())
    assert (science.status, science.codes) == ("FAIL", ("STORED_FILE_DIVERGENT",))


@case("PC2-61")
def test_uppercase_hex_in_q_is_not_normalised(w):
    w.q["subject_code_sha256"] = w.st["subject_code_sha256"] = pc2.SUBJECT_PIN.upper()
    assert w.rehash().statement().codes == ("STATEMENT_INVALID",)
    assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-25", "PC2-61")
@pytest.mark.parametrize("target", ["statement", "qualification", "sentinel_record", "sentinel_spec",
                                    "pilot_record", "pilot_spec"])
def test_decoding_bounds_of_q_statement_and_context(w, target):
    # C10.5: s <= 16 KiB, q and context records <= 64 KiB at decoding, before any comparison.
    limit = 16384 if target == "statement" else 65536
    if target in ("statement", "qualification"):
        record = w.st if target == "statement" else w.q
        record["padding"] = "x" * limit
        raw = f.canonical(record)
        args = (raw, f.canonical(w.q)) if target == "statement" else (f.canonical(w.st), raw)
        fact = pc2.bindings(*args, dict(w.raw), *w.digests, w.context_bytes())
    else:
        padded = {**w.context[target], "padding": "x" * limit}
        fact = w.science(**{target: f.canonical(padded)})
    assert (fact.status, fact.codes) == ("FAIL", ("SOURCE_LIMIT",))
    if target == "statement":
        assert pc2.select(f.canonical(w.q), raw) is None


@case("PC2-05")
@pytest.mark.parametrize("shape", ["exact_limit", "text", "dict_subclass", "empty"])
def test_artifact_size_type_and_mapping_type(w, shape):
    if shape == "exact_limit":
        w.raw[pc2.PC2_PATH] = b" " * (16 * 1024 * 1024)  # at the limit: pin, not size, refuses it
        assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)
    elif shape == "text":
        w.raw[pc2.PC2_PATH] = w.raw[pc2.PC2_PATH].decode()
        assert w.science().codes == ("SOURCE_LIMIT",)
    elif shape == "empty":
        w.raw[pc2.PC2_PATH] = b""  # present, so compared to its pin, never treated as absent
        assert w.science().codes == ("SCIENTIFIC_DIVERGENCE",)
    else:
        class Mapping(dict):
            pass
        fact = pc2.bindings(f.canonical(w.st), f.canonical(w.q), Mapping(w.raw), *w.digests, w.context_bytes())
        assert fact.status == "FAIL"


@case("PC2-05")
def test_a_pinned_artifact_above_the_decoding_bound(w):
    w.reseal(PC2=lambda d: d.update(padding="x" * 70000))
    assert len(w.raw[pc2.PC2_PATH]) > 65536
    assert w.science(variant(w)).codes == ("SOURCE_LIMIT",)


@case("PC2-41", "PC2-42", "PC2-38")
@pytest.mark.parametrize("change", ["upper_facts", "parent_not_object", "rounds_of_strings"])
def test_native_shapes_behind_instrumented_pins(change):
    edit = {"upper_facts": lambda d: [r[0].update(facts_sha256=r[0]["facts_sha256"].upper()) for r in d["rounds"]],
            "parent_not_object": lambda d: d.update(parent="sentinel"),
            "rounds_of_strings": lambda d: d.update(rounds=[["x"] * 28, ["x"] * 28])}[change]
    world = World().reseal(PC2=edit)
    assert world.science(variant(world)).codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-38")
def test_q_scope_is_bound_even_when_pc2_agrees(w):
    w.reseal(PC2=lambda d: d.update(scope="LIVE"))
    w.q["scope"] = "LIVE"
    assert w.rehash().science(variant(w)).codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-08", "PC2-09")
def test_a_divergent_closure_dominates_an_absent_one(w):
    w.digests[0], w.digests[1] = "c" * 64, None
    fact = w.science()
    assert (fact.status, fact.codes) == ("FAIL", ("SCIENTIFIC_DIVERGENCE",))

    class Digest(str):
        pass
    exact = World()
    exact.digests[2] = Digest(pc2.PILOT_PIN)
    assert exact.science().codes == ("SCIENTIFIC_DIVERGENCE",)


@case("PC2-22")
@pytest.mark.parametrize("scope", ["OTHER", None, 1])
def test_unknown_scope_under_p1_selects_nothing(w, scope):
    w.st["scope"] = scope
    assert pc2.select(f.canonical(w.q), f.canonical(w.st)) is None
