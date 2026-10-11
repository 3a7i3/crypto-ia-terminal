"""Synthetic-only regression gates for #404 D1 offline provisional captures."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_data.stress_d1_capture import CaptureBlocked, capture

BOUNDARY = 'd60d1b73e48d2ff567e62469b96df0799c9711ffc90bd3f24697f17b5d6ac78e'


def canonical(v):
    return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()


class TestD1Capture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        self.input = base/'readonly_research_staging'
        self.output = base/'research_capture_output'
        self.input.mkdir()
        self.output.mkdir()
        self.raw = {
            'decision_packets':[{'packet_id':'packet-1','metadata':{'trace_id':'trace-1'},'created_at':1790812801}],
            'decision_identity_records':[{'decision_id':'trace-1','ts':1790812801}],
            'admission_ledger':[{'event':'ADMISSION_ATTEMPT','attempt_id':'attempt-1','symbol':'BTC/USDT','ts':1790812801},
                                {'event':'ADMISSION_OUTCOME','attempt_id':'attempt-1','symbol':'BTC/USDT','ts':1790812802}],
            'rejection_store':[{'observation_id':'rejection-1','packet_id':'packet-2','ts':1790812803}],
        }
        self.write_request()

    def write_request(self):
        sources=[]
        for kind,rows in self.raw.items():
            raw=b''.join(canonical(row) for row in rows)
            name=f'{kind}.jsonl'
            (self.input/name).write_bytes(raw)
            sources.append({'kind':kind,'path':name,'sha256':hashlib.sha256(raw).hexdigest()})
        req={'schema_version':'PAPER_STRESS_D1_CAPTURE_REQUEST_V1',
             'source_class':'PRESTAGED_IMMUTABLE_RESEARCH_COPY',
             'paper_epoch_id':'BURN-IN-EPOCH-01-20260926T064144Z',
             'source_boundary_id':BOUNDARY,
             'runtime_source_sha':'116634be0d3c015cce1cfa58be7da7255414fbfd',
             'experiment_config_sha256':'9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4',
             'window_start_utc':'2026-10-01T00:00:00Z',
             'window_end_utc':'2026-10-02T00:00:00Z','sources':sources}
        (self.input/'capture_request.json').write_bytes(canonical(req))

    def run_capture(self):
        return capture(self.input,self.input/'capture_request.json',self.output)

    def test_provisional_never_go(self):
        info=self.run_capture()
        self.assertEqual(info['status'],'D1_PROVISIONAL_BUNDLE_CREATED')
        self.assertFalse(info['counterfactual_go'])
        root=self.output/info['dataset_id']
        self.assertTrue((root/'manifest.json').is_file())
        m=json.loads((root/'manifest.json').read_text())
        self.assertEqual(m['coverage']['structural_status'],'CONSISTENT_SUBSET_ONLY')
        self.assertEqual(m['coverage']['admission_pairs']['paired'],1)
        self.assertFalse(m['producer_denominator_certified'])
        self.assertEqual(m['coverage']['independent_producer_denominator'],'NOT_PROVEN')
        with self.assertRaisesRegex(CaptureBlocked,'DATASET_ALREADY_EXISTS'):
            self.run_capture()

    def test_missing_causal_timestamp_is_reported(self):
        self.raw['decision_identity_records'][0].pop('ts')
        self.write_request()
        info=self.run_capture()
        m=json.loads((self.output/info['dataset_id']/'manifest.json').read_text())
        self.assertEqual(m['coverage']['structural_status'],'BLOCKED')
        self.assertIn('CAUSAL_TIMESTAMP_COVERAGE_GAP',m['coverage']['structural_failures'])
        self.assertFalse(m['counterfactual_go'])

    def test_mutated_bytes_refused_before_publish(self):
        with (self.input/'admission_ledger.jsonl').open('ab') as f:
            f.write(b'{}\n')
        with self.assertRaisesRegex(CaptureBlocked,'SOURCE_SHA_MISMATCH'):
            self.run_capture()
        self.assertFalse(list(self.output.iterdir()))

    def test_duplicate_attempt_detected(self):
        self.raw['admission_ledger'].insert(1,dict(self.raw['admission_ledger'][0]))
        self.write_request()
        info=self.run_capture()
        m=json.loads((self.output/info['dataset_id']/'manifest.json').read_text())
        self.assertEqual(m['coverage']['structural_status'],'BLOCKED')
        self.assertIn('DUPLICATE_ADMISSION_EVENT_ID',m['coverage']['structural_failures'])
        self.assertFalse(m['counterfactual_go'])

    def test_orphan_outcome_is_not_zero(self):
        self.raw['admission_ledger']=self.raw['admission_ledger'][1:]
        self.write_request()
        info=self.run_capture()
        cov=json.loads((self.output/info['dataset_id']/'manifest.json').read_text())['coverage']
        self.assertEqual(cov['admission_pairs']['orphan_outcomes'],1)
        self.assertIn('ADMISSION_ORPHAN_OR_UNPAIRED',cov['structural_failures'])

    def test_bad_json_and_symlink_refused(self):
        (self.input/'decision_packets.jsonl').write_bytes(b'{"packet_id":"a","packet_id":"b"}\n')
        doc=json.loads((self.input/'capture_request.json').read_text())
        doc['sources'][0]['sha256']=hashlib.sha256((self.input/'decision_packets.jsonl').read_bytes()).hexdigest()
        (self.input/'capture_request.json').write_bytes(canonical(doc))
        with self.assertRaisesRegex(CaptureBlocked,'DUPLICATE_JSON_KEY'):
            self.run_capture()
        self.write_request()
        p=self.input/'decision_packets.jsonl'
        p.rename(self.input/'original.jsonl')
        p.symlink_to(self.input/'original.jsonl')
        with self.assertRaisesRegex(CaptureBlocked,'UNSAFE_SOURCE_FILE'):
            self.run_capture()

    def test_source_must_be_an_explicit_research_staging_root(self):
        unapproved=self.input.parent/'unapproved'
        unapproved.mkdir()
        with self.assertRaisesRegex(CaptureBlocked,'APPROVED_RESEARCH_STAGING_ROOT_REQUIRED'):
            capture(unapproved,unapproved/'capture_request.json',self.output)

    def test_missing_kind_and_live_runtime_path_refused(self):
        req=self.input/'capture_request.json'
        doc=json.loads(req.read_text())
        doc['sources']=doc['sources'][:-1]
        req.write_bytes(canonical(doc))
        with self.assertRaisesRegex(CaptureBlocked,'ALL_FOUR_COMPONENT_KINDS_REQUIRED'):
            self.run_capture()
        doc['sources'].append({'kind':'rejection_store','path':'databases/rejections.jsonl','sha256':'a'*64})
        req.write_bytes(canonical(doc))
        with self.assertRaisesRegex(CaptureBlocked,'PRODUCTION_SOURCE_PATH_FORBIDDEN'):
            self.run_capture()

if __name__=='__main__': unittest.main()