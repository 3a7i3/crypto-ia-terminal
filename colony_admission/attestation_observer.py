"""Single-owner, bounded SOURCE_ONLY acquisition of local attestation evidence.

No action, admission, replay, campaign or operational authority is exposed.
"""

from dataclasses import dataclass, replace

from colony_registrar import registrar as reg

from . import formats as f
from . import observer as o
from . import physical_evidence as p
from . import evidence_observer as e
from . import _attestation_core as c
from . import _attestation_statement as s
from ._attestation_checkout import Checkout
from . import attestation_evidence as a


@dataclass(frozen=True)
class AttestationConfig:
    observer: o.ObserverConfig
    registrar_policy_bytes: bytes | None = None
    registrar_policy_pin: str | None = None


def _configuration(config):
    o._need(type(config) is AttestationConfig, 'CONFIG_INVALID')
    o._config(config.observer)
    raw, pin = config.registrar_policy_bytes, config.registrar_policy_pin
    o._need((raw is None) == (pin is None), 'CONFIG_INVALID')
    if raw is not None:
        o._need(type(raw) is bytes and f.hex64(pin), 'CONFIG_INVALID')
        c.policy(raw, pin)


class AttestationObserver:
    """Operator-bound reader. Each scan owns exactly one acquisition context."""

    def __init__(self, config: AttestationConfig):
        self._config = config

    def scan_attestations(self):
        try:
            # Validate detached operator inputs before any filesystem access.
            try:
                _configuration(self._config)
            except (o._Blocked, c.CoreError, f.FormatError, ValueError, TypeError, KeyError):
                return a.AttestationEvidence('BLOCKED', ('CONFIG_INVALID',))
            return e._scan(self._config.observer, extension=_Attestations(self._config))
        except e._Capacity as exc:
            return a.AttestationEvidence('BLOCKED', ('SOURCE_LIMIT',),
                limits=replace(a.AttestationLimits(), reached=(exc.limit_name,)))
        except o._Blocked as exc:
            code = str(exc)
            reached = ('operations',) if code == 'HISTORY_OPERATION_LIMIT' else ('logs',) if code == 'OPERATION_LOGS_FULL' else ()
            return a.AttestationEvidence('BLOCKED', (code,),
                limits=replace(a.AttestationLimits(), reached=reached))
        except c.CoreError:
            return a.AttestationEvidence('BLOCKED', ('CONFIG_INVALID',))
        except (f.FormatError, OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            return a.AttestationEvidence('BLOCKED', ('SOURCE_UNAVAILABLE',))


class _Attestations:
    def __init__(self, config):
        self.config = config
        self.results = ()

    def prepare(self, source, lab, installed_raw):
        self.source, self.lab = source, lab
        self.checkout = Checkout(source, self.config.observer.checkout_root)
        raw, pin = self.config.registrar_policy_bytes, self.config.registrar_policy_pin
        if raw is None:
            raw = self.checkout.selected('docs/colony_registrar/POLICY_G0.json', 65536)
            o._need(raw is not None, 'SOURCE_UNAVAILABLE')
            pin = reg.POLICY_SHA256
        self.policy = c.policy(raw, pin)
        self.policy_raw, self.policy_pin = raw, pin
        installed = f.loads(installed_raw)
        self.root_raw = f.canonical(installed['root'])
        self.minimum_version = max(self.config.observer.minimum_root_version, installed['minimum_version'])

    def before_ledger(self, attempts):
        cap = min(252, 4 * self.policy['max_population'] - 4)
        for _, _, _, op, _ in attempts:
            e._limit(len(op['items']) <= cap, 'item_references')

    def ledger(self, source, parent, name, operations):
        # Same borrowed-FD inspector as 3A, with named 3B capacity failure.
        try:
            fd, before = source.file_descriptor(parent, name, o.trust.INSPECTION_MAX_BYTES)
        except o._Blocked as exc:
            if str(exc) == 'SOURCE_LIMIT':
                raise e._Capacity('ledger_bytes') from None
            raise
        batch = o.trust.inspect_operations_fd(fd, operations)
        if 'LEDGER_TOO_LARGE' in batch['failures']:
            raise e._Capacity('ledger_entries')
        o._need(batch['status'] == 'OBSERVED', batch['status'])
        source.stamps.append(o.SourceStamp('LEDGER', before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns, batch['ledger_sha256']))
        return batch

    def read(self, path, limit=65536):
        return self.source.selected(self.lab, path, limit)[0]

    def nodes(self, op):
        agent, seen, nodes = op['parent_agent_id'], set(), []
        while agent not in seen and len(nodes) < 9:
            if not f.hex64(agent):
                break
            seen.add(agent)
            base = 'individuals/' + agent + '/'
            record = self.read(base + 'record.json')
            spec = self.read(base + 'spec.json')
            if record is None or spec is None:
                break
            node = c.Node(agent, record, spec)
            try:
                value = c.decode(record)
                if value.get('role') == 'DESCENDANT':
                    q = self.read(base + 'birth_qualification.json')
                    adm = self.read('registrar-admissions/' + agent + '.json')
                    st = None
                    if q is not None:
                        try:
                            qhash = f.digest(c.decode(q))
                            st = self.read('admission-envelopes/' + agent + '/statement-' + qhash + '.json', 16384)
                        except c.CoreError:
                            pass
                    node = replace(node, qualification_bytes=q, admission_bytes=adm, statement_bytes=st)
                nodes.append(node)
                if value.get('role') != 'DESCENDANT':
                    break
                agent = value.get('lineage', {}).get('parent_agent_id')
            except (c.CoreError, TypeError, KeyError, AttributeError):
                nodes.append(node)
                break
        if len(nodes) == 9 and agent not in seen:
            raise e._Capacity('branch_nodes')
        return tuple(nodes)

    def envelopes(self, op, nodes, statement_raw):
        # Paths follow validated owner IDs and locally calculated record digests,
        # never a supplied statement/evidence pathname or frozen item pathname.
        result = {}
        objects = [(op['child_agent_id'], 'admission', f.canonical(op['birth_plan']['admission'])),
                   (op['child_agent_id'], 'qualification', f.canonical(op['birth_plan']['qualification'])),
                   (op['child_agent_id'], 'statement', statement_raw)]
        for node in nodes:
            objects.append((node.agent_id, 'individual', node.record_bytes))
            if node.qualification_bytes is not None:
                objects.extend(((node.agent_id, 'admission', node.admission_bytes),
                                (node.agent_id, 'qualification', node.qualification_bytes),
                                (node.agent_id, 'statement', node.statement_bytes)))
        qualification_hashes = {op['child_agent_id']: f.digest(op['birth_plan']['qualification'])}
        for node in nodes:
            if node.qualification_bytes is not None:
                try:
                    qualification_hashes[node.agent_id] = f.digest(c.decode(node.qualification_bytes))
                except c.CoreError:
                    pass
        for owner, role, raw in objects:
            result[owner + '/' + role] = None
            try:
                if role == 'statement':
                    digest = qualification_hashes.get(owner)
                    if digest is None:
                        continue
                elif raw is not None:
                    digest = f.digest(c.decode(raw))
                else:
                    continue
                prefix = 'birth-qualification' if role == 'qualification' else role
                path = 'admission-envelopes/' + owner + '/' + prefix + '-' + digest + '.envelope.json'
                result[owner + '/' + role] = self.read(path, 16384)
            except c.CoreError:
                continue
        return result

    def project(self, attempts, rows, physical, coverage):
        snapshots = tuple((f.canonical(op), log.terminal_claim, f.canonical(rows[log.operation_sha256]))
                          for _, _, log, op, _ in attempts)
        results = []
        for _, _, log, op, latest in attempts:
            if not latest:
                results.append(a.historical(f.canonical(op), log.status))
                continue
            nodes = self.nodes(op)
            child = op['child_agent_id']
            statement_path = 'admission-envelopes/' + child + '/statement-' + op['presented']['qualification']['record_sha256'] + '.json'
            st = self.read(statement_path, 16384)
            envelopes = self.envelopes(op, nodes, st)
            # This structural preflight precedes every signature. A derived
            # capacity failure invalidates the entire acquisition, not one item.
            bf = c.branch(f.canonical(op), nodes, self.policy_raw, self.policy_pin)
            pf = c.decision_partition(f.canonical(op), nodes, bf, st, self.policy_raw, self.policy_pin)
            if 'SOURCE_LIMIT' in pf.codes:
                raise e._Capacity('item_references')
            if 'BRANCH_DEPTH_LIMIT' in bf.codes:
                raise e._Capacity('branch_nodes')
            artifacts, subject, evaluator = {}, None, None
            qualified = [(f.canonical(op['birth_plan']['qualification']), st)]
            qualified.extend((n.qualification_bytes, n.statement_bytes) for n in nodes if n.qualification_bytes is not None)
            supported, history = False, False
            for qraw, sraw in qualified:
                if sraw is None:
                    continue
                try:
                    qv, sv = c.decode(qraw), c.decode(sraw, 16384)
                    if qv.get('criteria_sha256') == s.CRITERIA_PIN:
                        supported = True
                        history = history or sv.get('scope') == s.PRESENT
                except c.CoreError:
                    continue
            if supported:
                artifacts, subject, evaluator = self.checkout.science(include_history=history)
            result = a.project(f.canonical(op), nodes, st, envelopes, snapshots, self.root_raw,
                root_pin=self.config.observer.root_pin, minimum_version=self.minimum_version,
                lab_id=self.config.observer.lab_id, policy_bytes=self.policy_raw, policy_pin=self.policy_pin,
                artifacts=artifacts, subject_digest=subject, evaluator_digest=evaluator,
                latest=True, source_state=log.status, ledger_complete=coverage.status == 'MATCH')
            results.append(result)
        self.checkout.verify()
        self.results = tuple(sorted(results, key=lambda x: (x.child_agent_id, x.attempt, x.operation_sha256)))

    def finish(self, physical):
        blockers = p.unique(physical.blockers + tuple(code for result in self.results for code in result.blockers))
        return a.AttestationEvidence('BLOCKED' if blockers else 'OBSERVED', blockers,
            sources=physical.sources, metadata_sources=physical.metadata_sources,
            operations=self.results, pending_operations=physical.pending_operations,
            ledger_bytes=physical.ledger_bytes, ledger_coverage=physical.ledger_coverage,
            physical_operations=physical.operations)
