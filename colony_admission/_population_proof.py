"""Private 3C home classification and exact OWN inside the single owner.

Pure comparisons on the owner's retained snapshot, after its global preflight.
No IO, public scan, count, partition, ceiling, action or authority is supplied.
"""

from dataclasses import dataclass, field, replace

from . import _attestation_core as c
from . import _population_core as pc
from . import attestation_evidence as a
from . import formats as f
from . import physical_evidence as p

NE = p.NE


@dataclass(frozen=True)
class OperationProof:
    child_agent_id: str
    operation_sha256: str
    attempt: int
    scope: str
    source_state: str
    decision: a.OperationAttestations | None = None
    own_agent_id: str | None = None
    own_home: str = NE
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    population_partition: str = field(default=NE, init=False)
    frozen_completeness: str = field(default=NE, init=False)
    counts: str = field(default=NE, init=False)
    plan_match: str = field(default=NE, init=False)
    ceilings: str = field(default=NE, init=False)
    authorization: str = field(default=NE, init=False)


@dataclass(frozen=True)
class ProofSet:
    homes: tuple[pc.HomeProof, ...]
    operations: tuple[OperationProof, ...]
    classification: str
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    population: str = field(default=NE, init=False)
    snapshot_completeness: str = field(default=NE, init=False)
    global_identity_exclusions: str = field(default=NE, init=False)
    counts: str = field(default=NE, init=False)
    ceilings: str = field(default=NE, init=False)
    authorization: str = field(default=NE, init=False)


def _effective_d3(log):
    # BEGIN D3 not cancelled, or DONE D3; d3_started alone survives cancellation.
    return ((log.status == 'INTERRUPTED' and log.pending_step == 'D3')
            or (log.status in ('OPEN', 'RECOVERED') and log.last_completed_step == 'D3'))


def _awaiting_action(log):
    # A partial D3 waiting for its quarantine keeps the old home, never as OWN.
    return log.status in ('QUARANTINING', 'BLOCKED_DURABILITY') or (
        log.recovery_step == 'D3' and log.recovery_result == 'PARTIAL')


def _own_contradiction(decision, op, envelopes=None, excluded=()):
    """Only the candidate's own presented proofs, not its ancestors' problems."""
    presented = {op['presented'][role]['record_sha256'] for role in ('admission', 'qualification', 'statement')}
    for item in decision.items:
        if item.key.record_sha256 not in presented:
            continue
        if item.presence == 'DIVERGENT':
            return True
        if (a.aggregate((item.integrity, item.authenticity, item.issuer_authorization)) == 'FAIL'
                and item.genuine_but_revoked is not True):
            return True
    child = op['child_agent_id']
    if any(x.namespace == child and 'FAIL' in (x.statement.status, x.scientific.status)
           for x in decision.qualifications):
        return True
    if any(x.namespace == child + '/admission' and x.comparison == 'FAIL' for x in decision.consumptions):
        return True
    # Self-issued candidate envelopes only; an ancestor's self issue is its own home's fault.
    for role in ('admission', 'qualification', 'statement'):
        raw = (envelopes or {}).get(child + '/' + role)
        try:
            issuer = c.decode(raw, 16384)['issuer_id'] if raw is not None else None
        except (c.CoreError, TypeError, KeyError):
            continue
        if type(issuer) is str and any(agent[:16] in issuer for agent in excluded):
            return True
    return False


def _candidate(home, structure, op, log, usage, decision, potential, coverage, envelopes=None, excluded=()):
    """Classify the open operation's own home; OWN is never granted by ID alone."""
    child = home.agent_id
    material = {'individuals/' + child + '/' + name: (raw, 'LAB') for name, raw in (
        ('spec.json', home.spec_bytes), ('record.json', home.record_bytes),
        ('birth_qualification.json', home.qualification_bytes), ('usage.json', usage))}
    d3, errors = p.compare_d3(op, log, material, True, home.layout)
    plan = op['birth_plan']
    expected = (('spec.json', plan['child_spec']), ('record.json', plan['record']),
                ('birth_qualification.json', plan['qualification']))
    stored = tuple((material['individuals/' + child + '/' + name][0], p.storage_bytes(value))
                   for name, value in expected)
    conflict = any(raw is not None and raw != wanted and not wanted.startswith(raw) for raw, wanted in stored)
    prefix = any(raw is not None and raw != wanted for raw, wanted in stored)
    if log.last_completed_step != 'D3' and usage is not None:
        # Initial usage must be exactly {runs:0}; a run or other content is a conflict.
        wanted = p.storage_bytes({'runs': 0})
        conflict = conflict or (usage != wanted and not wanted.startswith(usage))
        prefix = prefix or usage != wanted
    if conflict:
        return pc.HomeProof(child, 'UNAUTHENTICATED', 'BLOCKING', structure.status,
                            codes=p.unique(tuple(errors) + ('HOME_CONFLICT', 'POPULATION_UNAUTHENTICATED')))
    if not log.d3_started or 'OPERATION_STATE_INCONSISTENT' in errors or not (
            _effective_d3(log) or _awaiting_action(log)):
        return pc.HomeProof(child, 'UNAUTHENTICATED', 'BLOCKING', structure.status,
                            codes=p.unique(tuple(errors) + ('OPERATION_STATE_INCONSISTENT', 'POPULATION_UNAUTHENTICATED')))
    # A strict prefix of an interrupted, not completed D3 write is not a forgery;
    # it is never parsed into a structure, OWN or count.
    if prefix or _awaiting_action(log) or d3.identity_state not in ('IDENTITY_MATCH', 'INITIAL_MATCH'):
        return pc.HomeProof(child, structure=NE if prefix else structure.status,
                            codes=p.unique(tuple(errors) + ('OWN_HOME_INCOMPLETE', 'CLASSIFICATION_NOT_EVALUATED')))
    if structure.status != 'PASS':
        return pc.HomeProof(child, 'UNAUTHENTICATED', 'BLOCKING', structure.status,
                            codes=p.unique(structure.codes + ('POPULATION_UNAUTHENTICATED',)))
    if decision is not None and _own_contradiction(decision, op, envelopes, excluded):
        return pc.HomeProof(child, 'UNAUTHENTICATED', 'BLOCKING', 'PASS',
                            codes=p.unique(decision.blockers + ('POPULATION_UNAUTHENTICATED',)))
    consumed = decision is not None and any(x.namespace == child + '/admission'
        and x.status == 'CONSUMED_BY_THIS_OPERATION' and x.comparison == 'PASS' for x in decision.consumptions)
    if (potential == child and decision is not None and decision.branch_attestations == 'PASS'
            and consumed and coverage == 'MATCH'):
        return pc.HomeProof(child, 'OWN_OPERATION', 'EXCLUDED_OWN', 'PASS',
                            scientific_bindings=decision.scientific_bindings,
                            identity_exclusions=decision.known_identity_exclusions)
    codes = ('CLASSIFICATION_NOT_EVALUATED',) + tuple(errors) + (decision.blockers if decision is not None else ())
    if potential != child:
        codes += ('OWN_HOME_INCOMPLETE',)
    if not consumed:
        codes += ('BIRTH_COMMIT_UNPROVEN',)
    if coverage != 'MATCH':
        codes += ('LEDGER_OPERATION_UNBOUND',)
    return pc.HomeProof(child, codes=p.unique(codes))


def prove(homes, attempts, materials, preflight, external, ledger_bytes, root_raw, *, root_pin,
          minimum_version, lab_id, policy_raw, policy_pin, artifacts, subject_digest, evaluator_digest):
    """Classify every acquired home; called by the owner after its global preflight.

All inputs are the owner's single retained snapshot: readable attempts and their
materials in the same order, the one ledger batch and its external bindings.
"""
    c.need(type(attempts) is tuple and type(materials) is tuple and len(attempts) == len(materials),
           'CONFIG_INVALID')
    batch = f.loads(ledger_bytes)
    rows = {row['operation_sha256']: row for row in batch['observations']}
    snapshots = tuple((x.operation_bytes, x.projection.terminal_claim,
                       f.canonical(rows[x.projection.operation_sha256])) for x in attempts)
    scopes = {x.operation_sha256: x for x in preflight}
    coverage = external.ledger_coverage.status
    artifacts = dict(artifacts)
    operations, open_by_child = [], {}
    for attempt, material in zip(attempts, materials):
        c.need(material.source.operation_bytes == attempt.operation_bytes, 'OPERATION_BINDING_MISMATCH')
        op = c.operation(attempt.operation_bytes)
        digest, log = f.digest(op), attempt.projection
        fact = scopes[digest]
        if fact.scope != 'CURRENT_OPEN':
            operations.append(OperationProof(op['child_agent_id'], digest, op['attempt'], 'HISTORICAL',
                log.status, codes=('HISTORICAL_POPULATION_NOT_EVALUATED',)))
            continue
        decision = a.project(attempt.operation_bytes, material.nodes, material.source.statement_bytes,
            dict(material.envelopes), snapshots, root_raw, root_pin=root_pin, minimum_version=minimum_version,
            lab_id=lab_id, policy_bytes=policy_raw, policy_pin=policy_pin, artifacts=artifacts,
            subject_digest=subject_digest, evaluator_digest=evaluator_digest, latest=True,
            source_state=log.status, ledger_complete=coverage == 'MATCH')
        open_by_child[op['child_agent_id']] = (op, log, material.source.usage_bytes, decision,
                                               fact.potential_own_agent_id, fact.codes, dict(material.envelopes))
        operations.append(OperationProof(op['child_agent_id'], digest, op['attempt'], 'CURRENT_OPEN',
            log.status, decision, codes=p.unique(fact.codes + decision.blockers)))
    structures = {x.agent_id: x for x in pc.structures(homes)}
    base = pc.own_proofs(homes, snapshots, root_raw, root_pin=root_pin, minimum_version=minimum_version,
        lab_id=lab_id, policy_raw=policy_raw, policy_pin=policy_pin, artifacts=artifacts,
        subject_digest=subject_digest, evaluator_digest=evaluator_digest)
    by_id = {h.agent_id: h for h in homes}
    terminals = {x.child_agent_id: x for x in external.terminals}
    results = []
    for proof in base:
        agent = proof.agent_id
        if agent in terminals and proof.structure == 'PASS':
            # Its log stays unread: a linked termination plus a present home is a
            # contradiction; an unproven claim cannot establish absence of COMMITTED.
            linkage = terminals[agent].terminal_linkage
            if linkage == 'PASS':
                proof = pc.HomeProof(agent, 'UNAUTHENTICATED', 'BLOCKING', 'PASS',
                    codes=('OPERATION_LOG_FAULTY', 'BIRTH_COMMIT_UNPROVEN', 'POPULATION_UNAUTHENTICATED'))
            elif linkage == 'FAIL':
                proof = pc.HomeProof(agent, 'UNAUTHENTICATED', 'BLOCKING', 'PASS',
                    codes=('OPERATION_LOG_FAULTY', 'EXTERNAL_TERMINATION_DIVERGENT', 'POPULATION_UNAUTHENTICATED'))
            else:
                proof = pc.HomeProof(agent, structure='PASS', codes=(
                    'OPERATION_LOG_FAULTY', 'EXTERNAL_TERMINATION_UNPROVEN', 'CLASSIFICATION_NOT_EVALUATED'))
        elif agent in open_by_child:
            op, log, usage, decision, potential, codes, envelopes = open_by_child[agent]
            excluded = frozenset(by_id) | set(decision.branch) | {agent}
            proof = _candidate(by_id[agent], structures[agent], op, log, usage, decision, potential, coverage,
                               envelopes, excluded)
            if 'OPERATION_PENDING' in codes and proof.classification == 'OWN_OPERATION':
                proof = pc.HomeProof(agent, structure='PASS', codes=('OPERATION_PENDING',))
            elif 'OPERATION_PENDING' in codes:
                proof = replace(proof, codes=p.unique(proof.codes + ('OPERATION_PENDING',)))
        elif proof.classification == 'UNAUTHENTICATED':
            proof = replace(proof, codes=p.unique(proof.codes + ('POPULATION_UNAUTHENTICATED',)))
        results.append(proof)
    classes = [x.classification for x in results]
    status = 'FAIL' if 'UNAUTHENTICATED' in classes else NE if NE in classes else 'PASS'
    own = [x.agent_id for x in results if x.classification == 'OWN_OPERATION']
    final = []
    for operation in operations:
        if operation.scope == 'CURRENT_OPEN':
            mine = operation.child_agent_id in own
            state = 'PASS' if mine else NE
            operation = replace(operation, own_agent_id=operation.child_agent_id if mine else None,
                                own_home=state)
        final.append(operation)
    codes = p.unique(tuple(code for x in results for code in x.codes))
    return ProofSet(tuple(results), tuple(sorted(final, key=lambda x: (x.child_agent_id, x.attempt,
                    x.operation_sha256))), status, codes)
