"""Bounded synthetic benchmark; run from repository root, never production."""

import hashlib
import json
import pathlib
import platform
import subprocess
import sys

WORKER = r"""
import json,hashlib,pathlib,sys,platform,resource,time,importlib.util,types
root=pathlib.Path.cwd(); pkg=types.ModuleType('research_data'); pkg.__path__=[]; sys.modules['research_data']=pkg
for name in ('stress_d1_evidence_contract','future_capture_core'):
 spec=importlib.util.spec_from_file_location('research_data.'+name,root/'research_data'/f'{name}.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
m=sys.modules['research_data.future_capture_core']; scenario=sys.argv[1]
identity=dict(stream_id='SYNTHETIC',producer_id='SYNTHETIC',producer_version='1',process_boot_id='LAB',paper_epoch_id='SYNTHETIC',code_sha='a'*40,config_sha256='b'*64,capture_campaign_id='SYNTHETIC')
c=m.BoundedCapture(identity=identity,limits=m.CaptureLimits(4096,16*1024*1024,64*1024))
pad='x'*(2048 if scenario=='count' else 64000)
def raw(i):
 return json.dumps(dict(identity,schema_version='FUTURE_NATIVE_EVENT_V1',producer_sequence=i,event_id=f'e{i}',event_time_utc='2026-10-12T00:00:00Z',monotonic_ns=i,clock_domain='LAB',clock_quality='UNKNOWN',payload={'padding':pad}),separators=(',',':')).encode()
rss=lambda:resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
base=rss(); t=time.perf_counter_ns(); cpu=time.process_time_ns(); accepted=0; lat=[]
for i in range(1,8193):
 b=raw(i); a=time.perf_counter_ns(); ok=c.append(b); lat.append(time.perf_counter_ns()-a)
 if ok: accepted+=1
 if i==4096: after_first=rss()
elapsed=time.perf_counter_ns()-t; cpu=time.process_time_ns()-cpu; after_refused=rss()
t=time.perf_counter_ns(); s=c.seal(); seal=time.perf_counter_ns()-t; d=json.loads(s.manifest_bytes)
assert accepted==d['accepted_events']==len(s.events)
assert sum(map(len,s.events))==d['accepted_bytes']<=16*1024*1024
assert len(s.events)<=4096 and all(len(x)<=64*1024 for x in s.events)
assert sum(d['refusals'].values())==8192-accepted
assert d['capture_status']=='INCOMPLETE' and d['declared_sequence_gap_count']==0
assert hashlib.sha256(s.manifest_bytes).hexdigest()==s.manifest_sha256
assert d['future_capture_activation']==d['paper_stress_runtime_go']=='DENIED'
assert not any(n.startswith(('core','runtime','paper_trading','observability')) for n in sys.modules)
lat.sort()
print(json.dumps(dict(scenario=scenario,accepted_events=accepted,accepted_bytes=d['accepted_bytes'],refusals=d['refusals'],declared_sequence_gap_count=d['declared_sequence_gap_count'],rss_baseline_bytes=base,rss_after_4096_bytes=after_first,rss_after_8192_bytes=after_refused,rss_after_seal_bytes=rss(),append_p99_us=lat[int(.99*(len(lat)-1))]/1000,ingest_wall_ms_including_generation=elapsed/1e6,ingest_cpu_ms_including_generation=cpu/1e6,seal_ms=seal/1e6,manifest_sha256=s.manifest_sha256,bounds_assertions='PASS',runtime_modules_loaded=False)))
"""


def main():
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "source_sha256": hashlib.sha256(
                    pathlib.Path("research_data/future_capture_core.py").read_bytes()
                ).hexdigest(),
                "worker_sha256": hashlib.sha256(WORKER.encode()).hexdigest(),
            }
        )
    )
    for scenario in ("count", "bytes"):
        for repetition in range(1, 4):
            r = subprocess.run(
                [sys.executable, "-I", "-B", "-c", WORKER, scenario],
                check=True,
                capture_output=True,
                text=True,
            )
            d = json.loads(r.stdout)
            d["repetition"] = repetition
            print(json.dumps(d))


if __name__ == "__main__":
    main()
