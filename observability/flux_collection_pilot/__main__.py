"""CLI: ``demo`` (synthetic, offline), ``replay``, ``verify`` and the LOCKED ``live`` entry.

    python -m observability.flux_collection_pilot demo   --out /private/dir/demo-1
    python -m observability.flux_collection_pilot replay /private/dir/demo-1/demo-1
    python -m observability.flux_collection_pilot verify /private/dir/demo-1/demo-1
    python -m observability.flux_collection_pilot live   --manifest approved.json   # refused unless authorised

Exit codes: 0 ok; 2 usage/refusal of an argument; 3 live locked (before any network); 4 incomplete/corrupt.
"""

import argparse
import json
import os
import sys

from . import protocol as P
from . import analysis, store as st
from .live_gate import LiveLocked, require_live_authorization
from .runner import CampaignConfig, CampaignRunner
from .simulated import FakeClock, Feed, ScriptedFactory, healthy_script


def synthetic_demo(root, campaign_id):
    """The reference synthetic campaign: 62 s healthy, planned cut, reconnect with snapshot, 180 s cap."""
    clock = FakeClock()
    s1 = healthy_script(Feed("CHANNEL"), seconds=62)
    s2 = healthy_script(Feed("CHANNEL"), seconds=130)
    factory = ScriptedFactory(clock, [s1, s2])
    cfg = CampaignConfig(campaign_id, P.package_digest(), clock_checks={"before": "SYNTHETIC", "after": "SYNTHETIC"})
    store = st.CampaignStore(root, campaign_id, cfg.caps)
    return CampaignRunner(cfg, factory, clock, store).run()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="flux_collection_pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--out", required=True)
    d.add_argument("--id", default="demo-1")
    r = sub.add_parser("replay")
    r.add_argument("campaign")
    r.add_argument("--policy", choices=P.SEQUENCE_POLICIES)
    r.add_argument("--full", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("campaign")
    lv = sub.add_parser("live")
    lv.add_argument("--manifest")
    a = ap.parse_args(argv)
    if a.cmd == "demo":
        res = synthetic_demo(a.out, a.id)
        print(json.dumps({"end_reason": res.end_reason, "complete": res.complete, "messages": res.messages,
                          "bytes_written": res.bytes_written, "path": res.path}, sort_keys=True))
        return 0 if res.complete else 4
    if a.cmd == "replay":
        rep = analysis.analyze(a.campaign, policy=a.policy)
        print(json.dumps(rep if a.full else {"report_sha256": rep["report_sha256"], "policy": rep["policy"],
                                             "campaign_end_reason": rep["campaign_end_reason"]}, sort_keys=True, indent=2))
        return 0
    if a.cmd == "verify":
        rep = st.verify_campaign(a.campaign)
        print(json.dumps(rep, sort_keys=True, indent=2))
        return 0 if rep["status"] == "COMPLETE_VERIFIED" else 4
    try:  # live: the lock is evaluated first; no network object exists before it passes
        approval = require_live_authorization(a.manifest, os.environ)
    except LiveLocked as e:
        print("LIVE_LOCKED: %s" % e, file=sys.stderr)
        return 3
    from .live_transport import LiveTransport
    from .memory import MemoryGuard, apply_data_limit
    from observability.market_venues.pilot.capture import SystemClock

    limit = approval.caps.max_memory_bytes
    apply_data_limit(limit)
    cfg = CampaignConfig("live-" + approval.manifest_sha256[:12], approval.package_digest, approval.caps,
                         approval.sequence_policy, "LIVE", approval.manifest_sha256,
                         clock_checks=approval.manifest.get("observer_clock"))
    store = st.CampaignStore(approval.manifest["storage"]["root"], cfg.campaign_id, cfg.caps)
    res = CampaignRunner(cfg, lambda: LiveTransport(approval), SystemClock(), store, MemoryGuard(limit)).run()
    print(json.dumps({"end_reason": res.end_reason, "complete": res.complete, "path": res.path}, sort_keys=True))
    return 0 if res.complete else 4


if __name__ == "__main__":
    sys.exit(main())
