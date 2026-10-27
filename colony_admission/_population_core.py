"""Private 3C own-home proofs on detached material, without population authority.

No public scanner uses this partial tranche. The acquisition owner must supply
one complete/stable inventory, trust and ledger snapshot. OWN, partitions,
counts, action/fault correspondences and global completeness are not provided.
"""

from dataclasses import dataclass, field

from colony_lab import lineage
from colony_lab.a1_identity import IdentityError
from colony_registrar import registrar as reg

from . import _attestation_core as c
from . import attestation_evidence as a
from . import formats as f
from . import physical_evidence as p

NE = p.NE


@dataclass(frozen=True)
class HomeInput:
    agent_id: str
    record_bytes: bytes | None
    spec_bytes: bytes | None
    qualification_bytes: bytes | None = None
    admission_bytes: bytes | None = None
    statement_bytes: bytes | None = None
    individual_envelope: bytes | None = None
    admission_envelope: bytes | None = None
    qualification_envelope: bytes | None = None
    statement_envelope: bytes | None = None
    layout: str = "NOT_EVALUATED"


@dataclass(frozen=True)
class Structure:
    agent_id: str
    status: str = NE
    branch: tuple[str, ...] = ()  # founder -> this home, never a positive prefix
    codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class HomeProof:
    agent_id: str
    classification: str = NE
    counted: str = "NE"
    structure: str = NE
    birth_proof: str = NE
    individual_proof: str = NE
    scientific_bindings: str = NE
    identity_exclusions: str = NE
    codes: tuple[str, ...] = ()
    execution_restriction: str | None = None
    accepted: bool = field(default=False, init=False)
    completeness: str = field(default=NE, init=False)
    authorization: str = field(default=NE, init=False)
    filiation: str = field(default=NE, init=False)


def structures(homes):
    """Verify actual founder-to-home lineages without a pseudo birth operation."""
    c.need(type(homes) is tuple and len(homes) <= 65, "SOURCE_LIMIT")
    c.need(all(type(h) is HomeInput and f.hex64(h.agent_id) for h in homes), "SOURCE_NAMESPACE_INVALID")
    by_id = {h.agent_id: h for h in homes}
    c.need(len(by_id) == len(homes), "SOURCE_NAMESPACE_INVALID")
    facts = []
    for home in sorted(homes, key=lambda h: h.agent_id):
        try:
            chain, visited, agent = [], set(), home.agent_id
            while True:
                c.need(agent not in visited, "LINEAGE_INVALID")
                c.need(len(chain) < 9, "SOURCE_LIMIT")
                visited.add(agent)
                c.need(agent in by_id, "LINEAGE_INVALID")
                node = by_id[agent]
                c.need(node.record_bytes is not None and node.spec_bytes is not None, "STORED_FILE_MISSING")
                record, spec = c.decode(node.record_bytes), c.decode(node.spec_bytes)
                c.need(record.get("agent_id") == agent, "RECORD_SPEC_MISMATCH")
                chain.append((record, spec))
                if record.get("role") == "FOUNDER":
                    break
                c.need(record.get("role") == "DESCENDANT", "LINEAGE_INVALID")
                agent = record.get("lineage", {}).get("parent_agent_id")
                c.need(f.hex64(agent), "LINEAGE_INVALID")
            previous = previous_spec = None
            for record, spec in reversed(chain):
                lineage.verify_record(record, spec, previous, previous_spec)
                previous, previous_spec = record, spec
            facts.append(Structure(home.agent_id, "PASS", tuple(r["agent_id"] for r, _ in reversed(chain))))
        except c.CoreError as exc:
            if str(exc) == "SOURCE_LIMIT":
                raise
            facts.append(Structure(home.agent_id, "FAIL", codes=(str(exc),)))
        except (lineage.LineageError, IdentityError) as exc:
            facts.append(Structure(home.agent_id, "FAIL", codes=(exc.code,)))
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
            facts.append(Structure(home.agent_id, "FAIL", codes=("LINEAGE_INVALID",)))
    return tuple(facts)


def _envelope(kind, raw, envelope_raw, root_raw, root_pin, minimum_version, lab_id, excluded):
    if raw is None or envelope_raw is None:
        return "FAIL", ("ATTESTATION_MISSING",), NE
    try:
        record, env = c.decode(raw), c.decode(envelope_raw, 16384)
        k = c.key(kind, record)
        required = c.Need(k, f.canonical(record), ("own",), (f.digest(env),))
        fact = c.item_fact(required, (envelope_raw,), root_raw, pin_sha256=root_pin,
                           minimum_version=minimum_version, lab_id=lab_id)
        c.need(type(env.get("issuer_id")) is str, "FROZEN_ITEM_DIVERGENT")
        # All actual homes, including AWAITING/SUSPENDED, belong to exclusions.
        if any(agent[:16] in env["issuer_id"] for agent in excluded):
            return "FAIL", ("SELF_ADMISSION_DENIED" if kind == c.ADM else "SELF_QUALIFICATION_DENIED",), "FAIL"
        states = (fact.integrity, fact.authenticity, fact.issuer_authorization)
        if all(x == "PASS" for x in states):
            return "PASS", (), "PASS"
        if fact.genuine_but_revoked is True and set(fact.codes) <= {"KEY_REVOKED", "ENVELOPE_REVOKED"}:
            return "REVOKED", fact.codes, "PASS"
        return "FAIL", fact.codes or ("FROZEN_ITEM_DIVERGENT",), "PASS"
    except (c.CoreError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return "FAIL", ("FROZEN_ITEM_DIVERGENT",), NE


def _birth_binding(home, by_id, snapshots, policy_raw, policy_pin, excluded, envelopes):
    """Bind all three own presented roles, not just admission's consumed /1."""
    try:
        c.need(all(raw is not None for raw in (home.qualification_bytes, home.admission_bytes,
                                               home.statement_bytes)), "ATTESTATION_MISSING")
        record, spec = c.decode(home.record_bytes), c.decode(home.spec_bytes)
        q, adm = c.decode(home.qualification_bytes), c.decode(home.admission_bytes)
        parent = c.decode(by_id[record["lineage"]["parent_agent_id"]].record_bytes)
        selected = c.policy(policy_raw, policy_pin)
        c._admission(adm, q, record, parent, selected, policy_pin, excluded)
        matching = []
        for op_raw, terminal, row_raw in snapshots:
            op = c.operation(op_raw)
            if op["child_agent_id"] == home.agent_id and terminal == "COMMITTED":
                matching.append((op, row_raw))
        c.need(len(matching) == 1, "BIRTH_COMMIT_UNPROVEN")
        op, _ = matching[0]
        plan = op["birth_plan"]
        for key, value in (("record", record), ("child_spec", spec), ("qualification", q), ("admission", adm),
                           ("parent", parent)):
            c.need(f.canonical(plan[key]) == f.canonical(value), "BIRTH_COMMIT_DIVERGENT")
        c.need(op["child_agent_spec_id"] == record["agent_spec_id"] and op["policy_sha256"] == policy_pin,
               "BIRTH_COMMIT_DIVERGENT")
        node = c.Node(home.agent_id, home.record_bytes, home.spec_bytes, home.qualification_bytes,
                      home.admission_bytes, home.statement_bytes)
        c.need(c.ancestor_commit(node, snapshots, home.admission_envelope)[0] == "PASS", "BIRTH_COMMIT_UNPROVEN")
        for role, kind, raw in (("admission", c.ADM, home.admission_bytes),
                                ("qualification", c.QUAL, home.qualification_bytes),
                                ("statement", c.STATEMENT, home.statement_bytes)):
            value, env = c.decode(raw, 16384 if kind == c.STATEMENT else 65536), c.decode(envelopes[role], 16384)
            digest, env_hash = f.digest(value), f.digest(env)
            c.need(op["presented"][role] == {"record_sha256": digest, "envelope_sha256": env_hash},
                   "BIRTH_COMMIT_DIVERGENT")
            k = c.key(kind, value)
            items = [x for x in op["items"] if c.Key(x["kind"], x["subject"]["agent_id"],
                x["subject"]["agent_spec_id"], x["record_sha256"]) == k]
            c.need(len(items) == 1 and items[0]["role"] == "DECISION"
                   and items[0]["envelope_sha256"] == env_hash, "BIRTH_COMMIT_DIVERGENT")
        return "PASS", ()
    except (c.CoreError, lineage.LineageError, reg.RegistrarError, IdentityError) as exc:
        return "FAIL", (str(exc) if isinstance(exc, c.CoreError) else exc.code,)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return "FAIL", ("BIRTH_COMMIT_DIVERGENT",)


def own_proofs(homes, snapshots, root_raw, *, root_pin, minimum_version, lab_id,
               policy_raw, policy_pin, artifacts=None, subject_digest=None, evaluator_digest=None):
    """Private own-proof subset; never returns OWN/exclusion or a complete scan.

Snapshots are canonical (operation bytes, terminal, ledger observation bytes)
    from one future acquisition owner. Frozen item caps and lineage bounds are
    checked before signatures here; the owner must also preflight the full
    derived K/N/P/F graph before calling this function. Unresolved/open
    candidates stay NE in this tranche.
"""
    selected = c.policy(policy_raw, policy_pin)
    c.need(type(snapshots) is tuple and len(snapshots) <= 256, "SOURCE_LIMIT")
    pending = set()
    for op_raw, terminal, row_raw in snapshots:
        op = c.operation(op_raw)
        c.need(len(op["items"]) <= min(252, 4 * selected["max_population"] - 4), "SOURCE_LIMIT")
        if terminal is None:
            pending.add(op["child_agent_id"])
    structural = structures(homes)
    by_id = {h.agent_id: h for h in homes}
    excluded = frozenset(by_id) | pending
    all_bound = all(x.status == "PASS" for x in structural)
    results = []
    for structure in structural:
        home = by_id[structure.agent_id]
        if structure.status != "PASS":
            results.append(HomeProof(home.agent_id, "UNAUTHENTICATED", "BLOCKING", "FAIL", codes=structure.codes))
            continue
        if home.agent_id in pending:
            results.append(HomeProof(home.agent_id, structure="PASS", codes=("OWN_HOME_NOT_EVALUATED",)))
            continue
        record = c.decode(home.record_bytes)
        founder = record["role"] == "FOUNDER"
        envelopes = {"admission": home.admission_envelope, "qualification": home.qualification_envelope,
                     "statement": home.statement_envelope}
        binding, codes = (NE, ("NOT_APPLICABLE_FOUNDER",)) if founder else _birth_binding(
            home, by_id, snapshots, policy_raw, policy_pin, excluded, envelopes)
        env_args = (root_raw, root_pin, minimum_version, lab_id, excluded)
        states, exclusions = [], []
        if home.individual_envelope is None and not founder:
            individual = NE
        else:
            individual, errors, identity = _envelope(c.IND, home.record_bytes, home.individual_envelope, *env_args)
            states.append(individual)
            exclusions.append(identity)
            codes += errors
        scientific, birth = NE, NE
        if not founder:
            birth_states = []
            for role, kind, raw in (("admission", c.ADM, home.admission_bytes),
                                    ("qualification", c.QUAL, home.qualification_bytes),
                                    ("statement", c.STATEMENT, home.statement_bytes)):
                state, errors, identity = _envelope(kind, raw, envelopes[role], *env_args)
                states.append(state)
                birth_states.append("FAIL" if state == "REVOKED" else state)
                exclusions.append(identity)
                codes += errors
            qfact = a._qualification(home.agent_id, home.statement_bytes, home.qualification_bytes,
                {home.agent_id + "/" + role: env for role, env in envelopes.items()},
                artifacts or {}, subject_digest, evaluator_digest)
            scientific = qfact.scientific.status
            states.append(qfact.statement.status)
            codes += qfact.statement.codes + qfact.scientific.codes
            birth = a.aggregate((binding, scientific, qfact.statement.status, *birth_states))
        # A genuine revocation prevents a PASS birth proof, but is treated
        # separately for conservative SUSPENDED counting, never as forged data.
        failed = binding == "FAIL" or scientific == "FAIL" or "FAIL" in states
        unknown = (not all_bound or (not founder and scientific != "PASS")
                   or any(x == NE for x in states))
        if failed:
            classification, counted = "UNAUTHENTICATED", "BLOCKING"
        elif unknown:
            classification, counted = NE, "NE"
            codes += ("CLASSIFICATION_NOT_EVALUATED",)
        elif "REVOKED" in states:
            classification, counted = "SUSPENDED", "INCLUDED"
        elif not founder and home.individual_envelope is None:
            classification, counted = "AWAITING_INDIVIDUAL_ATTESTATION", "INCLUDED"
        else:
            classification, counted = "AUTHENTICATED", "INCLUDED"
        individual_proof = "FAIL" if individual == "REVOKED" else individual
        results.append(HomeProof(home.agent_id, classification, counted, "PASS", birth, individual_proof,
            scientific, a.aggregate(exclusions) if all_bound else NE, p.unique(codes),
            "EXECUTION_SUSPENDED" if classification == "SUSPENDED" else None))
    return tuple(results)
