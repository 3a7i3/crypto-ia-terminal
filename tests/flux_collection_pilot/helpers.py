import json
from pathlib import Path

from observability.flux_collection_pilot import protocol as P
from observability.flux_collection_pilot.runner import CampaignConfig, CampaignRunner
from observability.flux_collection_pilot.simulated import BOOK0, FakeClock, Feed, Script, ScriptedFactory
from observability.flux_collection_pilot.store import CampaignStore, raw_record
from observability.market_venues.pilot.capture import Instant

S = P.S


def healthy_items(seconds, *, l2_every=2, snapshot=True):
    items = []
    if snapshot:
        items.append((S // 10, lambda f: f.snapshot(BOOK0)))
        items.append((S // 10 + 1, lambda f: f.trades([("t0", "100.5", "0.1", "BUY", "auto")], kind="snapshot")))
    for sec in range(1, seconds + 1):
        items.append((sec * S, lambda f: f.heartbeat()))
        if sec % l2_every == 0:
            items.append((sec * S + 1, lambda f, n=sec: f.update([("bid", "100", str(2 + n))])))
    return items


def script(items, domain="CHANNEL"):
    feed, sc = Feed(domain), Script()
    for off, fn in sorted(items, key=lambda x: x[0]):  # counters follow TIME order
        sc.frame(off, fn(feed))
    return sc


def run(tmp_path, scripts, *, caps=P.PROTOCOL_CAPS, policy=P.DEFAULT_SEQUENCE_POLICY, mem=None, store_kw=None,
        cid="c1", clock=None):
    clock = clock or FakeClock()
    factory = ScriptedFactory(clock, scripts)
    cfg = CampaignConfig(cid, "test-digest", caps, policy)
    store = CampaignStore(tmp_path, cid, caps, **(store_kw or {}))
    res = CampaignRunner(cfg, factory, clock, store, mem).run()
    return res, factory, Path(tmp_path) / cid


def trigger(path):
    return json.loads((Path(path) / "trigger.json").read_bytes())


def final(path):
    return json.loads((Path(path) / "final.receipt.json").read_bytes())


def write_campaign(root, cid, sessions, *, caps=P.PROTOCOL_CAPS, policy="PER_CHANNEL"):
    """Write raw sessions directly (analysis entry): sessions = {"S01": [(utc, mono, raw_bytes), ...]}."""
    store = CampaignStore(root, cid, caps)
    store.write_atomic("intent.json", {"sequence_policy": policy})
    for sid, msgs in sessions.items():
        store.open_raw(sid)
        for i, (utc, mono, raw) in enumerate(msgs):
            store.append_raw(sid, raw_record(sid, i, i, Instant(utc, mono), raw))
        store.close_raw(sid)
    store.close()
    return Path(root) / cid
