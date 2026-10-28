"""Public 3C PopulationObserver: one bounded SOURCE_ONLY population observation.

Every field is a diagnostic. OBSERVED has no authority: no birth, admission,
run, quarantine, set-aside, recovery or trust action is permitted by it.
"""

import hashlib
from dataclasses import dataclass, field

from . import _attestation_core as c
from . import _population_acquisition as owner
from . import attestation_evidence as a
from . import attestation_observer as ao
from . import formats as f
from . import observer as o
from . import physical_evidence as p
from ._population_counts import Ceilings, Counts
from ._population_external import TerminalBinding
from ._population_faults import ActionFact, FaultBinding

NE = p.NE
SCHEMA = 'colony-admission.population-evidence/0'
# Scope limits that are explicitly non-blocking by themselves (§3, §5, §9, §11).
_NON_BLOCKING = frozenset({'NOT_APPLICABLE_FOUNDER', 'HISTORICAL_POPULATION_NOT_EVALUATED',
                           'NO_CURRENT_OPEN_OPERATION', 'NO_RUNTIME_OBSERVATION'})


@dataclass(frozen=True)
class PopulationConfig:
    attestations: ao.AttestationConfig


@dataclass(frozen=True)
class PopulationLimits(a.AttestationLimits):
    homes: int = 65
    private_entries: int = 8192
    union_operations: int = 256


@dataclass(frozen=True)
class HomeFact:
    agent_id: str
    spec_id: str | None
    record_sha256: str | None
    role: str | None
    parent_agent_id: str | None
    founder_agent_id: str | None
    generation: int | None
    files: tuple[p.FileFact, ...]
    layout: str
    classification: str
    classification_codes: tuple[str, ...]
    birth_proof: str
    individual_proof: str
    scientific_bindings: str
    identity_exclusions: str
    counted: str
    execution_restriction: str | None
    accepted: bool = field(default=False, init=False)
    authorization: str = field(default=NE, init=False)
    filiation: str = field(default=NE, init=False)


@dataclass(frozen=True)
class ItemFact:
    """One extended 3B need or one frozen PREPARED item; immutable values only.

    DECISION needs carry 3B's namespaces and its sorted frozen envelope digests.
    POPULATION needs carry one (namespace, envelope digest or None) pair per copy,
    positionally. Items carry their single frozen envelope digest.
    """
    kind: str
    agent_id: str
    agent_spec_id: str
    record_sha256: str
    role: str
    namespaces: tuple[str, ...] = ()
    envelope_sha256s: tuple[str | None, ...] = ()


@dataclass(frozen=True)
class OperationPopulation:
    child_agent_id: str
    operation_sha256: str
    attempt: int
    child_agent_spec_id: str
    latest: bool
    source_state: str
    scope: str
    own_home: str
    own_agent_id: str | None
    needs: tuple[ItemFact, ...]
    items: tuple[ItemFact, ...]
    decision_partition: str
    branch_attestations: str
    population_partition: str
    frozen_completeness: str
    counts: Counts
    plan_match: str
    ceilings: Ceilings
    blockers: tuple[str, ...]
    accepted: bool = field(default=False, init=False)
    authorization: str = field(default=NE, init=False)


@dataclass(frozen=True)
class PopulationEvidence:
    status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    sources: tuple = ()
    metadata_sources: tuple[p.MetadataStamp, ...] = ()
    limits: PopulationLimits = field(default_factory=PopulationLimits)
    ledger_bytes: bytes | None = None
    ledger_coverage: p.LedgerCoverage = field(default_factory=p.LedgerCoverage)
    log_coverage: str = NE
    homes: tuple[HomeFact, ...] = ()
    operations: tuple[OperationPopulation, ...] = ()
    external_terminations: tuple[TerminalBinding, ...] = ()
    fault_bindings: tuple[FaultBinding, ...] = ()
    action_facts: tuple[ActionFact, ...] = ()
    inventory: str = NE
    population: str = NE
    snapshot_completeness: str = NE
    global_identity_exclusions: str = NE
    schema: str = field(default=SCHEMA, init=False)
    accepted: bool = field(default=False, init=False)
    completeness: str = field(default=NE, init=False)
    authorization: str = field(default=NE, init=False)
    durability: str = field(default=NE, init=False)
    rotation: str = field(default=NE, init=False)
    recovery: str = field(default=NE, init=False)
    source_revision_provenance: str = field(default=NE, init=False)
    operational_completeness: str = field(default=NE, init=False)


def _file(name, path, raw):
    if raw is None:
        return p.FileFact(name, path, 'LAB', 'ABSENT')
    try:
        record = f.digest(c.decode(raw))
    except c.CoreError:
        record = None
    return p.FileFact(name, path, 'LAB', 'PRESENT', size_bytes=len(raw),
                      raw_sha256=hashlib.sha256(raw).hexdigest(), record_sha256=record)


def _home(home, proof):
    base = 'individuals/' + home.agent_id + '/'
    files = tuple(_file(name, base + name, raw) for name, raw in (
        ('record.json', home.record_bytes), ('spec.json', home.spec_bytes),
        ('birth_qualification.json', home.qualification_bytes)))
    spec = record_hash = role = parent = founder = generation = None
    try:
        record = c.decode(home.record_bytes)
        spec, record_hash = record.get('agent_spec_id'), f.digest(record)
        if proof.structure == 'PASS':
            # §2: role and lineage are exposed only once validated, never as raw values.
            role = record['role'] if record['role'] in ('FOUNDER', 'DESCENDANT') else None
            lineage = record['lineage']
            parent, founder = lineage.get('parent_agent_id'), lineage['founder_agent_id']
            generation = lineage['generation']
    except (c.CoreError, TypeError, KeyError, AttributeError):
        pass
    return HomeFact(home.agent_id, spec if f.hex64(spec) else None, record_hash, role, parent, founder,
                    generation, files, home.layout, proof.classification, proof.codes, proof.birth_proof,
                    proof.individual_proof, proof.scientific_bindings, proof.identity_exclusions,
                    proof.counted, proof.execution_restriction)


def _needs(decision, cur):
    """3B DECISION needs extended with the POPULATION needs, each with its copies."""
    facts = [ItemFact(n.key.kind, n.key.agent_id, n.key.agent_spec_id, n.key.record_sha256, 'DECISION',
                      n.namespaces, n.envelope_sha256s) for n in (decision.needs if decision else ())]
    facts += [ItemFact(k.kind, k.agent_id, k.agent_spec_id, k.record_sha256, 'POPULATION', namespaces, digests)
              for k, namespaces, digests in cur.population_needs]
    return tuple(sorted(facts, key=lambda x: (c.Key(x.kind, x.agent_id, x.agent_spec_id, x.record_sha256), x.role)))


def _items(op):
    return tuple(ItemFact(x['kind'], x['subject']['agent_id'], x['subject']['agent_spec_id'], x['record_sha256'],
                          x['role'], envelope_sha256s=(x['envelope_sha256'],)) for x in op['items'])


def _global_exclusions(homes, current):
    """§2 identity exclusions over the whole universe; FAIL dominates, gaps stay NE."""
    states = [x.identity_exclusions for x in homes] + [x.decision.known_identity_exclusions for x in current]
    if 'FAIL' in states:
        return 'FAIL'
    if any(x.structure != 'PASS' or x.counted not in ('INCLUDED', 'EXCLUDED_OWN') for x in homes):
        return NE
    # An absent permitted individual adds no issuer; a present one must be checked.
    if any(x.counted == 'INCLUDED' and x.identity_exclusions == NE and x.individual_proof != NE for x in homes):
        return NE
    if any(x.decision.known_identity_exclusions != 'PASS' for x in current):
        return NE
    return 'PASS'


def _evidence(acq):
    proofs = acq.proofs
    ordered = sorted(acq.homes, key=lambda h: h.agent_id)
    c.need([h.agent_id for h in ordered] == [x.agent_id for x in proofs.homes], 'SOURCE_UNAVAILABLE')
    homes = tuple(_home(h, x) for h, x in zip(ordered, proofs.homes))
    blockers, warnings = [], []
    for home in homes:
        if home.counted not in ('INCLUDED', 'EXCLUDED_OWN'):
            blockers.extend(home.classification_codes or ('CLASSIFICATION_NOT_EVALUATED',))
        else:
            warnings.extend(x for x in home.classification_codes if x in _NON_BLOCKING)
        if home.execution_restriction is not None:
            warnings.append(home.execution_restriction)
    attempts = {x.projection.operation_sha256: x for x in acq.log_inventory.attempts}
    operations, current = [], []
    for proof in proofs.operations:
        op = c.operation(attempts[proof.operation_sha256].operation_bytes)
        decision = proof.decision
        cur = proof.current
        if proof.scope == 'CURRENT_OPEN':
            current.append(proof)
            blockers.extend(x for x in proof.codes if x not in _NON_BLOCKING)
            if decision.branch_attestations != 'PASS':
                blockers.extend(decision.blockers or ('ATTESTATION_MISSING',))
            for state, code in ((cur.frozen_completeness, 'ATTESTATION_MISSING'),
                                (cur.counts.complete, 'CLASSIFICATION_NOT_EVALUATED'),
                                (cur.plan_match, 'POPULATION_CHANGED'), (cur.ceilings.aggregate, 'CEILING_FAIL')):
                if state != 'PASS':
                    blockers.extend(cur.codes or (code,))
        else:
            warnings.append('HISTORICAL_POPULATION_NOT_EVALUATED')
        operations.append(OperationPopulation(proof.child_agent_id, proof.operation_sha256, proof.attempt,
            op['child_agent_spec_id'], attempts[proof.operation_sha256].latest, proof.source_state, proof.scope,
            proof.own_home, proof.own_agent_id, _needs(decision, cur), _items(op),
            decision.decision_partition if decision else NE,
            decision.branch_attestations if decision else NE, cur.population_partition,
            cur.frozen_completeness, cur.counts, cur.plan_match, cur.ceilings, proof.codes))
    if not current:
        warnings.append('NO_CURRENT_OPEN_OPERATION')
    warnings.append('NO_RUNTIME_OBSERVATION')
    external = acq.external_bindings
    coverage = external.ledger_coverage
    if coverage.status != 'MATCH':
        blockers.extend(external.ledger_codes or ('LEDGER_OPERATION_UNBOUND',))
    for terminal in external.terminals:
        if terminal.terminal_linkage == 'FAIL':
            blockers.append('EXTERNAL_TERMINATION_DIVERGENT')
        elif terminal.terminal_linkage != 'PASS':
            blockers.append('EXTERNAL_TERMINATION_UNPROVEN')
    for fault in acq.fault_bindings:
        if fault.blocking:
            blockers.extend(fault.codes)
    for action in acq.action_facts:
        if action.blocking:
            blockers.extend(action.codes or ('ACTION_EVIDENCE_NOT_EVALUATED',))
    global_exclusions = _global_exclusions(proofs.homes, current)
    blockers = p.unique(blockers)
    inventory = 'PASS'
    log_coverage = 'PASS' if not acq.log_inventory.unread_logs and not external.unresolved_ids else NE
    population = proofs.classification
    snapshot = a.aggregate((inventory, population, global_exclusions,
                            'PASS' if coverage.status == 'MATCH' else NE,
                            *(x.current.frozen_completeness for x in current),
                            'FAIL' if any(x.blocking for x in acq.fault_bindings + acq.action_facts) else 'PASS',
                            'PASS' if not external.unresolved_ids else NE))
    if not blockers and snapshot != 'PASS':
        # §1: OBSERVED also needs every required comparison evaluated.
        blockers = ('CLASSIFICATION_NOT_EVALUATED',)
    status = 'OBSERVED' if not blockers else 'BLOCKED'
    return PopulationEvidence(status, blockers, p.unique(warnings), acq.sources, acq.metadata_sources,
        ledger_bytes=acq.ledger_bytes, ledger_coverage=coverage, log_coverage=log_coverage, homes=homes,
        operations=tuple(operations), external_terminations=external.terminals,
        fault_bindings=acq.fault_bindings, action_facts=acq.action_facts, inventory=inventory,
        population=population, snapshot_completeness=snapshot, global_identity_exclusions=global_exclusions)


class PopulationObserver:
    """Operator-bound reader. Each scan owns exactly one acquisition context."""

    def __init__(self, config: PopulationConfig):
        self._config = config

    def scan_population(self):
        if type(self._config) is not PopulationConfig:
            return PopulationEvidence('BLOCKED', ('CONFIG_INVALID',))
        acq = owner.acquire(self._config.attestations)
        if acq.status != 'ACQUIRED':
            return PopulationEvidence('BLOCKED', acq.codes, limits=PopulationLimits(reached=acq.limits))
        try:
            return _evidence(acq)
        except (c.CoreError, o._Blocked, f.FormatError, ValueError, TypeError, KeyError):
            return PopulationEvidence('BLOCKED', ('SOURCE_UNAVAILABLE',))
