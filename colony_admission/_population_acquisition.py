"""Private single-owner 3C acquisition and global preflight, without proof wiring.

No public population scan or classification is supplied. Every detached byte below
is provisional until all inventories, paths, descriptors, unlocks and closes pass.
"""

import fcntl
import re
from contextlib import ExitStack
from dataclasses import dataclass, field

from . import _attestation_core as c
from . import _attestation_statement as s
from . import attestation_observer as a
from . import evidence_observer as e
from . import formats as f
from . import observer as o
from . import physical_evidence as p
from . import _population_inventory as inv
from . import _population_log_acquisition as logs
from . import _population_preflight as pf
from .external_evidence import (
    FAULT_LINE_BYTES, FAULT_MAX_LINES, HISTORY_LINE_BYTES, HISTORY_MAX_LINES,
    POLICY_MAX_BYTES,
)

_ENVELOPE = re.compile(
    r"(?:individual|admission|birth-qualification|statement)-[0-9a-f]{64}\.envelope\.json"
    r"|statement-[0-9a-f]{64}\.json", re.ASCII)
_ATTEMPT = re.compile(r"[1-9][0-9]{0,127}", re.ASCII)


@dataclass(frozen=True)
class OperationMaterial:
    source: pf.OperationInput
    nodes: tuple[c.Node, ...]
    envelopes: tuple[tuple[str, bytes | None], ...]


@dataclass(frozen=True)
class QuarantinedHome:
    operation_sha256: str
    destination: str
    record_bytes: bytes | None
    spec_bytes: bytes | None
    qualification_bytes: bytes | None
    layout: str
    location_binding: str = field(default=p.NE, init=False)
    identity_binding: str = field(default=p.NE, init=False)
    action_completion: str = field(default=p.NE, init=False)


@dataclass(frozen=True)
class Acquisition:
    status: str
    codes: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    sources: tuple[o.SourceStamp, ...] = ()
    metadata_sources: tuple[p.MetadataStamp, ...] = ()
    log_inventory: logs.LogInventory | None = None
    homes: tuple[inv.HomeInput, ...] = ()
    operations: tuple[OperationMaterial, ...] = ()
    quarantined_homes: tuple[QuarantinedHome, ...] = ()
    preflight: tuple[pf.OperationPreflight, ...] = ()
    ledger_bytes: bytes | None = None
    root_bytes: bytes | None = None
    minimum_version: int | None = None
    fault_bytes: bytes | None = None
    trust_policy_bytes: bytes | None = None
    trust_history_bytes: bytes | None = None
    policy_bytes: bytes | None = None
    policy_pin: str | None = None
    artifacts: tuple[tuple[str, bytes], ...] = ()
    subject_digest: str | None = None
    evaluator_digest: str | None = None
    accepted: bool = field(default=False, init=False)
    snapshot_completeness: str = field(default=p.NE, init=False)
    population: str = field(default=p.NE, init=False)
    own_home: str = field(default=p.NE, init=False)
    counts: str = field(default=p.NE, init=False)
    ceilings: str = field(default=p.NE, init=False)
    terminal_linkage: str = field(default=p.NE, init=False)
    authorization: str = field(default=p.NE, init=False)


def _metadata(source, parent, name, path, cap):
    value = source.metadata_file(parent, name, path)
    e._limit(value.st_size <= cap, 'envelope_bytes' if cap == 16384 else 'record_bytes')


def _bounded_file(source, parent, name, resource, cap, limit_name, *, lock=False):
    try:
        return source.file(parent, name, resource, cap, lock=lock)
    except o._Blocked as exc:
        if str(exc) == 'SOURCE_LIMIT':
            raise e._Capacity(limit_name) from None
        raise


def _private_inventory(source, lab, names, initial_usage):
    """All private namespaces/layouts and known file sizes before ledger opening."""
    individuals = source.optional_directory(lab, 'individuals', 'individuals')
    for agent in names:
        inv.layout(source, individuals, agent, 'individuals/' + agent)
        home = source.optional_directory(individuals, agent, 'individuals/' + agent)
        for name in source.inventories[home]:
            # usage/runtime contents stay opaque here and after DONE D3.
            if (name in ('record.json', 'spec.json', 'birth_qualification.json')
                    or (name == 'usage.json' and agent in initial_usage)):
                _metadata(source, home, name, 'individuals/' + agent + '/' + name, 65536)
    admissions = source.optional_directory(lab, 'registrar-admissions', 'registrar-admissions')
    for name in source.listing(admissions):
        o._need(name.endswith('.json') and f.hex64(name[:-5]), 'SOURCE_NAMESPACE_INVALID')
        _metadata(source, admissions, name, 'registrar-admissions/' + name, 65536)
    envelopes = source.optional_directory(lab, 'admission-envelopes', 'admission-envelopes')
    for agent in source.listing(envelopes):
        o._need(f.hex64(agent), 'SOURCE_NAMESPACE_INVALID')
        base = 'admission-envelopes/' + agent
        directory = source.optional_directory(envelopes, agent, base)
        o._need(directory is not None, 'SOURCE_CHANGED')
        for name in source.listing(directory):
            o._need(_ENVELOPE.fullmatch(name) is not None, 'SOURCE_NAMESPACE_INVALID')
            _metadata(source, directory, name, base + '/' + name, 16384)
    quarantine = source.optional_directory(lab, 'admission-quarantine', 'admission-quarantine')
    destinations = []
    if quarantine is not None:
        for operation in source.listing(quarantine):
            o._need(f.hex64(operation), 'SOURCE_NAMESPACE_INVALID')
            base = 'admission-quarantine/' + operation
            directory = source.optional_directory(quarantine, operation, base)
            o._need(directory is not None, 'SOURCE_CHANGED')
            for name in source.listing(directory):
                o._need(name == 'terminal' or _ATTEMPT.fullmatch(name) is not None,
                        'SOURCE_NAMESPACE_INVALID')
                path = base + '/' + name
                state = inv.layout(source, directory, name, path)
                home = source.optional_directory(directory, name, path)
                for leaf in source.inventories[home]:
                    if leaf in ('record.json', 'spec.json', 'birth_qualification.json'):
                        _metadata(source, home, leaf, path + '/' + leaf, 65536)
                destinations.append((operation, name, path, state))
    return tuple(destinations)


def _quarantine_bytes(source, lab, destinations):
    result = []
    for operation, name, path, state in destinations:
        raws = tuple(source.selected(lab, path + '/' + leaf, 65536)[0]
                     for leaf in ('record.json', 'spec.json', 'birth_qualification.json'))
        result.append(QuarantinedHome(operation, name, *raws, state))
    return tuple(result)


def _science(checkout, homes, operations):
    pairs = [(h.qualification_bytes, h.statement_bytes) for h in homes]
    for material in operations:
        op = c.operation(material.source.operation_bytes)
        pairs.append((f.canonical(op['birth_plan']['qualification']), material.source.statement_bytes))
    supported, history = False, False
    for qraw, statement in pairs:
        if qraw is None or statement is None:
            continue
        try:
            qv, sv = c.decode(qraw), c.decode(statement, 16384)
            if qv.get('criteria_sha256') == s.CRITERIA_PIN:
                supported = True
                history = history or sv.get('scope') == s.PRESENT
        except c.CoreError:
            pass
    if not supported:
        return (), None, None
    artifacts, subject, evaluator = checkout.science(include_history=history)
    return tuple(sorted(artifacts.items())), subject, evaluator


def _acquire(config):
    with ExitStack() as stack:
        source = inv.InventorySource(stack)
        cfg = config.observer
        lab = source.directory(cfg.lab_root)
        _bounded_file(source, lab, 'registrar.lock', 'L1', 0, 'registrar_lock_bytes', lock=True)
        # Explicit unlock is part of the same failure boundary as every close.
        lock_fd = source.checks[-1][0]
        stack.callback(fcntl.flock, lock_fd, fcntl.LOCK_UN)
        faults = source.directory(cfg.fault_file.parent)
        fault_raw = _bounded_file(source, faults, cfg.fault_file.name, 'FAULT_LOG',
            FAULT_MAX_LINES * FAULT_LINE_BYTES, 'fault_bytes')
        trust = source.directory(cfg.trust_directory)
        installed = _bounded_file(source, trust, 'policy.json', 'TRUST_POLICY', POLICY_MAX_BYTES,
                                  'trust_policy_bytes')
        history = _bounded_file(source, trust, 'trust-history.log', 'TRUST_HISTORY',
                               HISTORY_MAX_LINES * HISTORY_LINE_BYTES, 'trust_history_bytes')
        external = o._external(cfg, fault_raw, installed, history)
        o._need(external[0].status in ('EMPTY', 'STRUCTURAL_ONLY'), 'FAULT_LOG_UNAVAILABLE')
        o._need(external[1].status == 'STRUCTURAL_MATCH' and external[2] == 'CURRENT_ROOT_VALIDATED',
                'TRUST_CURRENT_UNAVAILABLE')
        # Reuse only acquisition methods; never project() or another public scan.
        helper = a._Attestations(config)
        helper.prepare(source, lab, external[1].policy_bytes)
        log_inventory = logs.acquire_logs(source, lab, fault_raw, cfg.lab_id,
            item_cap=min(252, 4 * helper.policy['max_population'] - 4))
        for attempt in log_inventory.attempts:
            plan = c.operation(attempt.operation_bytes)['birth_plan']
            for name in ('record', 'child_spec', 'qualification', 'admission'):
                e._limit(len(f.canonical(plan[name])) <= 65536, 'record_bytes')
        names = inv.home_names(source, lab)
        initial_usage = frozenset(attempt.child_agent_id for attempt in log_inventory.attempts
            if attempt.latest and attempt.projection.terminal_claim is None
            and attempt.projection.pending_step == 'D3' and attempt.projection.last_completed_step != 'D3')
        destinations = _private_inventory(source, lab, names, initial_usage)
        # A fresh FD, offset zero, one batch and U fixed before opening the ledger.
        ledger_parent = source.directory(cfg.ledger.parent)
        batch = helper.ledger(source, ledger_parent, cfg.ledger.name, log_inventory.operation_ids)
        homes = inv.acquire_homes(source, lab, names)
        quarantined = _quarantine_bytes(source, lab, destinations)
        materials = []
        for attempt in log_inventory.attempts:
            op = c.operation(attempt.operation_bytes)
            child = op['child_agent_id']
            statement = helper.read('admission-envelopes/' + child + '/statement-'
                                    + f.digest(op['birth_plan']['qualification']) + '.json', 16384)
            nodes = helper.nodes(op)
            envelopes = helper.envelopes(op, nodes, statement)
            usage = None
            # Only the latest open BEGIN D3 can require initial usage. Historical
            # attempts never make the current mutable usage into a past snapshot.
            log = attempt.projection
            if (attempt.latest and log.terminal_claim is None and log.pending_step == 'D3'
                    and log.last_completed_step != 'D3'):
                usage = helper.read('individuals/' + child + '/usage.json')
            material = pf.OperationInput(attempt.operation_bytes, attempt.log_bytes, statement, usage)
            materials.append(OperationMaterial(material, nodes, tuple(sorted(envelopes.items()))))
        materials = tuple(materials)
        preflight = pf.derive(homes, tuple(x.source for x in materials),
            helper.policy_raw, helper.policy_pin,
            unresolved_external_ids=tuple(x.operation_sha256 for x in log_inventory.unread_logs))
        artifacts, subject, evaluator = _science(helper.checkout, homes, materials)
        helper.checkout.verify()
        source.verify()
        result = Acquisition('ACQUIRED', sources=tuple(source.stamps),
            metadata_sources=tuple(source.metadata[k] for k in sorted(source.metadata)),
            log_inventory=log_inventory, homes=homes, operations=materials,
            quarantined_homes=quarantined, preflight=preflight, ledger_bytes=f.canonical(batch),
            root_bytes=helper.root_raw, minimum_version=helper.minimum_version,
            fault_bytes=fault_raw, trust_policy_bytes=installed, trust_history_bytes=history,
            policy_bytes=helper.policy_raw, policy_pin=helper.policy_pin,
            artifacts=artifacts, subject_digest=subject, evaluator_digest=evaluator)
    return result


def acquire(config):
    """Private acquisition only. ACQUIRED never means a population proof PASS."""
    try:
        try:
            a._configuration(config)
        except (o._Blocked, c.CoreError, f.FormatError, ValueError, TypeError, KeyError):
            return Acquisition('BLOCKED', ('CONFIG_INVALID',))
        return _acquire(config)
    except (e._Capacity, pf.PreflightLimit) as exc:
        return Acquisition('BLOCKED', ('SOURCE_LIMIT',), (exc.limit_name,))
    except o._Blocked as exc:
        return Acquisition('BLOCKED', (str(exc),))
    except (c.CoreError, f.FormatError, OSError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError):
        return Acquisition('BLOCKED', ('SOURCE_UNAVAILABLE',))
