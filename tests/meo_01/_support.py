"""SYNTHETIC helpers for MEO-01 tests: invented frames and journals, never provider output."""

import hashlib
from observability.market_flow import kraken_trades as kt

MS = 1_000_000
T0 = 1_795_128_000_000  # ms, a 5-minute UTC boundary
ACK = b'{"method":"subscribe","result":{"channel":"trade","snapshot":true,"symbol":"BTC/USDT"},"success":true}'
HEARTBEAT = b'{"channel":"heartbeat"}'


def rfc(ms, us=0):
    from datetime import datetime, timezone
    sec, rem = divmod(ms, 1000)
    return datetime.fromtimestamp(sec, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + ".%06dZ" % (rem * 1000 + us)


def item(tid, ms, *, side="buy", price="62000.5", qty="0.0012", symbol="BTC/USDT", us=0, ts=None):
    stamp = rfc(ms, us) if ts is None else ts
    return ('{"symbol":"%s","side":"%s","price":%s,"qty":%s,"ord_type":"limit","trade_id":%s,'
            '"timestamp":"%s"}' % (symbol, side, price, qty, tid, stamp))


def frame(items, typ="update"):
    return ('{"channel":"trade","type":"%s","data":[%s]}' % (typ, ",".join(items))).encode()


def journal(entries, *, evidence_kind="SYNTHETIC"):
    """entries: (recv_ms, kind, payload[, extra]) -> (manifest, events), as verify_journal returns them."""
    events = [{"seq": 0, "venue": "kraken", "kind": "ws_open", "recv_wall_ns": entries[0][0] * MS - MS,
               "recv_mono_ns": 0, "opcode": None, "payload": b""}]
    for e in entries:
        recv_ms, kind, payload = e[:3]
        extra = e[3] if len(e) > 3 else {}
        events.append({"seq": 0, "venue": extra.pop("venue", "kraken"), "kind": kind,
                       "recv_wall_ns": recv_ms * MS, "recv_mono_ns": recv_ms * MS,
                       "opcode": 1 if kind == "ws_message" else None, "payload": payload, **extra})
    for i, ev in enumerate(events):
        ev["seq"] = i + 1
    manifest = {"evidence_kind": evidence_kind, "status": "COMPLETED",
                "sealed": {"events": len(events), "events_sha256": "0" * 64, "frames_sha256": "0" * 64},
                "preflight": {"kraken_clock_offset_ms": 12}, "clock_end": {"kraken_offset_ms": -8},
                "clock_tolerance_ms": 2000, "code": {"digest": "f" * 64}}
    return manifest, events


def steady(n=700, *, start_ms=T0 - 60_000, every_ms=1_000, first_id=1000, skip=(), mutate=None):
    """A subscription followed by one trade per frame every ``every_ms`` (ids contiguous)."""
    rows = [(start_ms - 1, "ws_message", ACK)]
    for i in range(n):
        at = start_ms + i * every_ms
        tid = first_id + i
        if tid in skip:
            continue
        it = item(tid, at, side="buy" if i % 3 else "sell")
        if mutate:
            it = mutate(tid, at, it)
        rows.append((at + 40, "ws_message", frame([it])))
    return rows


def report(entries, **kw):
    manifest, events = journal(entries)
    return kt.replay_journal(manifest, events, **kw)


def sha(b):
    return hashlib.sha256(b).hexdigest()
