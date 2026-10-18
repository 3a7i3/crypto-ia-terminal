"""One-shot, explicitly invoked synthetic scenario. No worker or live adapter."""

import hashlib
from pathlib import Path

from sentinel_activity import SCHEMA_VERSION
from sentinel_activity.canonical import require
from sentinel_activity.integrity import report
from sentinel_activity.store import ActivityStore, utc_now


ARTIFACT = b'SIMULATED: diagnostic artifact; no external action was executed.'


def run_demo(root: Path, *, clock=utc_now) -> dict:
    roles = {'sentinel': ('AGENT', 'PROPOSER'), 'operator': ('OPERATOR', 'OPERATOR'),
             'secretary': ('SYSTEM', 'SECRETARIAT'), 'a': ('AGENT', 'WORKER'),
             'b': ('AGENT', 'WORKER'), 'reviewer': ('AGENT', 'REVIEWER'), 'closer': ('SYSTEM', 'CLOSER')}
    policy = {'version': 'fixture-demo-policy-1', 'producers': {
        'fixture-' + name: {'actor_id': 'fixture-' + name, 'actor_kind': kind,
                           'actor_version': None, 'role': role}
        for name, (kind, role) in roles.items()}}
    store = ActivityStore.create(root, policy, ledger_id='fixture-demo-journal', clock=clock)
    artifact_hash = hashlib.sha256(ARTIFACT).hexdigest()
    narrative = [
        ('QUEST_PROPOSED', 'sentinel', {'title': 'Synthetic simulator diagnostic',
         'scope': ['fixture:lab'], 'budget_units': 2, 'acceptance_criteria': ['Independent synthetic review']}),
        ('QUEST_APPROVED', 'operator', {'proposal_event_id': 'fixture-demo-1'}),
        ('QUEST_PUBLISHED', 'secretary', {'approval_event_id': 'fixture-demo-2'}),
        ('QUEST_ACCEPTED', 'a', {}), ('QUEST_DECLINED', 'b', {}),
        ('WORK_STARTED', 'a', {'attempt': 1}),
        ('ARTIFACT_SUBMITTED', 'a', {'attempt': 1, 'artifact_ref': 'fixture:demo-artifact',
                                   'artifact_sha256': artifact_hash}),
        ('REVIEW_PASSED', 'reviewer', {'submission_event_id': 'fixture-demo-7'}),
        ('QUEST_COMPLETED', 'closer', {'review_event_id': 'fixture-demo-8'}),
    ]
    last_candidate = None
    last_record = None
    for index, (event_type, actor, payload) in enumerate(narrative, 1):
        if index > 1:
            payload = {**payload, 'expected_revision': index - 1}
        refs = ['fixture:demo-proof']
        if event_type == 'ARTIFACT_SUBMITTED':
            refs = ['fixture:demo-artifact']
        elif event_type.startswith('REVIEW_'):
            refs = ['fixture:sha256:' + artifact_hash]
        last_candidate = {
            'schema_version': SCHEMA_VERSION, 'event_id': 'fixture-demo-' + str(index),
            'occurred_at_utc': None, 'actor_id': 'fixture-' + actor, 'actor_kind': roles[actor][0],
            'actor_version': None, 'event_type': event_type, 'quest_id': 'fixture-demo-quest',
            'correlation_id': 'fixture-demo-flow',
            'causation_event_id': 'fixture-demo-' + str(index - 1) if index > 1 else None,
            'source_kind': 'SIMULATED', 'summary': 'SIMULATED ' + event_type,
            'reason_declared': 'Synthetic budget insufficient' if actor == 'b' else 'Synthetic declared reason',
            'payload': {**payload, 'cost': None}, 'evidence_refs': refs,
            'authorization_ref': 'fixture:publication-only' if index in {2, 3} else None,
        }
        last_record = store.append(last_candidate, producer_id='fixture-' + actor)
    reopened = ActivityStore(root, clock=clock)
    retry = reopened.append(last_candidate, producer_id='fixture-closer')
    require(retry == last_record, 'CORRUPTED')
    meta, events, projection = reopened.snapshot()
    return {**report(meta, events), 'projection': projection, 'retry_added_events': 0,
            'real_agents_running': 'NOT_PROVEN', 'runtime_authority': 'NONE'}
