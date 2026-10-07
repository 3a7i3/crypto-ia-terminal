import copy
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from observability.ppl_comparison import build_ppl_comparison_snapshot
from observability.ppl_accounting_history import build_history
from observability.operator_api.ppl_accounting_history_reader import read_history, validate_history
from paper_trading.ledger_events import make_epoch_created_event, make_position_opened_event, make_position_closed_event, make_position_unresolved_event


def source():
    events = [make_epoch_created_event(event_id='epoch-event', paper_epoch_id='burn-test', sequence=1, timestamp=100., initial_virtual_capital=100., code_sha='a'*40, config_snapshot_hash='b'*64, schema_version=2),
              make_position_opened_event(event_id='open-event', paper_epoch_id='burn-test', sequence=2, timestamp=110., trade_id='trade', symbol='TEST/USDT', side='LONG', principal=10., entry_price=10., entry_fee=.01, schema_version=2, tp_price=12., sl_price=9., timeout_at=200., recovery_eligible_until=300.),
              make_position_closed_event(event_id='close-event', paper_epoch_id='burn-test', sequence=3, timestamp=120., trade_id='trade', exit_price=11., exit_fee=.02, schema_version=2)]
    view = SimpleNamespace(events=events, paper_epoch_id='burn-test', last_error=None)
    sim = SimpleNamespace(_lifecycle_authority=SimpleNamespace(ppl_is_authoritative=True), _authority_runtime=SimpleNamespace(consistent_view=lambda:view))
    doc = build_ppl_comparison_snapshot(sim, cycle=1, process_instance_id='p', source_sha='a'*40, now_fn=lambda:150.)
    manifest = {'paper_epoch_id':'burn-test','ppl_event_schema_version':2,'epoch_role':'BURN_IN_EXPERIMENT','manifest_schema_version':3,'created_at':100., **dict(events[0].payload)}
    return doc, manifest


def build(doc=None, manifest=None):
    d,m=source()
    return build_history(json.dumps(d if doc is None else doc).encode(), json.dumps(m if manifest is None else manifest).encode(), producer_sha='c'*40)


def test_net_fees_projection_and_published_shares():
    h=build()
    assert validate_history(h)
    last=h['samples'][-1]
    assert float(last['realized_pnl']) == pytest.approx(.97)
    assert float(last['available_cash']) == pytest.approx(100.97)
    assert float(last['fees_paid']) == pytest.approx(.03)
    assert h['checkpoint_verified'] is False
    assert h['allocation']['segments'][0]['share']=='1'


@pytest.mark.parametrize('mutation', ['gap','duplicate','epoch','capital','schema','time','authority','future_event'])
def test_rejects_unproven_or_corrupted_boundary(mutation):
    d,m=source()
    if mutation=='gap': d['ppl_events'][1]['sequence']=3
    if mutation=='duplicate': d['ppl_events'][1]['event_id']=d['ppl_events'][0]['event_id']
    if mutation=='epoch': m['paper_epoch_id']='other'
    if mutation=='capital': m['initial_virtual_capital']=999.
    if mutation=='schema': m['ppl_event_schema_version']=1
    if mutation=='time': d['ppl_events'][2]['timestamp']=105.
    if mutation=='authority': d['ppl_source']['authority']='NONE'
    if mutation=='future_event': d['ppl_events'][2]['timestamp']=200.
    with pytest.raises(Exception): build(d,m)


def test_missing_marks_never_generate_equity_and_unresolved_stays_separate():
    d,m=source()
    opened=copy.deepcopy(d['ppl_events'][1]);opened.update(event_id='open-2',trade_id='trade-2',sequence=4,timestamp=130.)
    unresolved={'event_id':'unresolved-2','trade_id':'trade-2','decision_id':None,'sequence':5,'timestamp':140.,'event_type':'POSITION_UNRESOLVED','payload':{'reason':'missing-outcome'}}
    d['ppl_events'] += [opened,unresolved]
    h=build(d,m)
    assert float(h['samples'][-1]['unresolved_capital'])==10.
    assert float(h['samples'][-1]['realized_pnl'])==pytest.approx(.97)
    assert all('equity' not in row for row in h['samples'])
    assert validate_history(h)


def test_transport_preserves_source_age_and_fails_closed(tmp_path,monkeypatch):
    from observability.operator_api import app as api
    from observability.operator_api import ppl_accounting_history_reader as reader
    path=tmp_path/'history.json';h=build();path.write_text(json.dumps(h))
    payload,error=read_history(path,now=500.)
    assert error is None and payload['freshness_classification']=='STALE'
    assert payload['snapshot_age_s']==350.
    monkeypatch.setattr(reader,'read_history',lambda:read_history(path,now=500.))
    client=TestClient(api.app)
    response=client.get('/api/operator/v1/ppl-accounting-history')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['samples']==h['samples']
    assert client.post('/api/operator/v1/ppl-accounting-history').status_code==405
    h['allocation']['segments'][0]['share']='.5';path.write_text(json.dumps(h))
    assert client.get('/api/operator/v1/ppl-accounting-history').status_code==503
    path.unlink();assert read_history(path)[1]=='HISTORY_NOT_AVAILABLE'
