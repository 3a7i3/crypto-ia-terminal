"""Simulated clock, scripted transport and synthetic Coinbase-like feed builder.

Invented data only: nothing here is provider output, and the transport reports
``evidence_kind == "SYNTHETIC"``. Time is injected: ``recv`` advances the fake
clock instead of sleeping.
"""

from collections import deque
from dataclasses import dataclass, field
import json

from observability.market_venues.pilot.capture import Instant
from . import protocol
from .transport import (AccessRefused, ConnectionClosed, Frame, FrameTooLarge, LocalLoss,
                        Transport)

EPOCH_NS = 1_793_000_000 * protocol.S  # an arbitrary synthetic UTC instant in 2026


class FakeClock:
    def __init__(self, utc_ns=EPOCH_NS, mono_ns=5 * protocol.S):
        self.utc, self.mono = utc_ns, mono_ns
        self.skew_ns = 0  # added to UTC at every advance: monotonic and UTC then differ, as on a real host
        self.samples = 0

    def sample(self):
        self.samples += 1
        return Instant(self.utc, self.mono)

    def advance(self, ns):
        self.mono += ns
        self.utc += ns + (self.skew_ns if ns else 0)


@dataclass
class Script:
    """One connection's scripted life. ``events``: (offset_ns_from_open, kind, payload)."""

    events: list = field(default_factory=list)
    refuse_open: object = None  # an exception instance raised by open()

    def frame(self, offset_ns, raw):
        self.events.append((offset_ns, "frame", raw if isinstance(raw, bytes) else raw.encode()))
        return self

    def close(self, offset_ns):
        self.events.append((offset_ns, "close", None))
        return self

    def loss(self, offset_ns):
        self.events.append((offset_ns, "loss", None))
        return self

    def too_large(self, offset_ns, size=10**7):
        self.events.append((offset_ns, "large", size))
        return self

    def refuse(self, offset_ns):
        self.events.append((offset_ns, "refuse", None))
        return self


class SimulatedTransport(Transport):
    evidence_kind = "SYNTHETIC"

    def __init__(self, clock, script):
        self.clock, self.script = clock, script
        self.opened_at = None
        self.subscribed = None
        self.closed = False
        self._queue = deque(sorted(script.events, key=lambda e: e[0]))

    def open(self, subscribe_messages):
        if self.script.refuse_open is not None:
            raise self.script.refuse_open
        self.opened_at = self.clock.mono
        self.subscribed = list(subscribe_messages)

    def recv(self, timeout_ns):
        if self.closed or self.opened_at is None:
            raise ConnectionClosed("NOT_OPEN")
        if self._queue:
            at, kind, payload = self._queue[0]
            wait = self.opened_at + at - self.clock.mono
            if wait <= timeout_ns:
                self.clock.advance(max(0, wait))
                self._queue.popleft()
                if kind == "frame":
                    return Frame(payload)
                if kind == "close":
                    self.closed = True
                    raise ConnectionClosed("PEER_CLOSED")
                if kind == "loss":
                    raise LocalLoss("QUEUE_OVERFLOW")
                if kind == "large":
                    raise FrameTooLarge(payload)
                if kind == "refuse":
                    raise AccessRefused("POLICY_CLOSE_1008")
        self.clock.advance(timeout_ns)
        return None

    def close(self):
        self.closed = True


class ScriptedFactory:
    """One script per connection; asking for more connections than scripted fails loudly."""

    def __init__(self, clock, scripts):
        self.clock, self.scripts, self.built = clock, list(scripts), []

    def __call__(self):
        if len(self.built) >= len(self.scripts):
            raise AssertionError("UNSCRIPTED_CONNECTION_REQUESTED")
        t = SimulatedTransport(self.clock, self.scripts[len(self.built)])
        self.built.append(t)
        return t


class Feed:
    """Builds well-formed synthetic messages with a chosen counter domain.

    domain: "CONNECTION" (one counter over all messages), "CHANNEL" (one per channel).
    """

    def __init__(self, domain="CHANNEL", start=0, send_ns=EPOCH_NS):
        self.domain, self.start, self.send_ns = domain, start, send_ns
        self.counters = {}
        self.hb = 0

    def _seq(self, channel):
        key = "*" if self.domain == "CONNECTION" else channel
        n = self.counters.get(key, self.start)
        self.counters[key] = n + 1
        return n

    def skip(self, channel, n=1):
        key = "*" if self.domain == "CONNECTION" else channel
        self.counters[key] = self.counters.get(key, self.start) + n

    @staticmethod
    def iso(ns):
        s, f = divmod(ns, protocol.S)
        import datetime as _d
        t = _d.datetime(1970, 1, 1, tzinfo=_d.timezone.utc) + _d.timedelta(seconds=s)
        return t.strftime("%Y-%m-%dT%H:%M:%S") + (".%09dZ" % f)

    def envelope(self, channel, events, *, seq=None, timestamp="auto"):
        d = {"channel": channel, "client_id": "", "sequence_num": self._seq(channel) if seq is None else seq,
             "events": events}
        if timestamp == "auto":
            d["timestamp"] = self.iso(self.send_ns)
        elif timestamp is not None:
            d["timestamp"] = timestamp
        return json.dumps(d, separators=(",", ":")).encode()

    def heartbeat(self, **kw):
        self.hb += 1
        return self.envelope("heartbeats", [{"current_time": self.iso(self.send_ns), "heartbeat_counter": self.hb}], **kw)

    def l2(self, kind, levels, *, event_time="auto", product="BTC-USD", **kw):
        ups = []
        for side, price, qty in levels:
            u = {"side": side, "price_level": price, "new_quantity": qty}
            if event_time == "auto":
                u["event_time"] = self.iso(self.send_ns)
            elif event_time is not None:
                u["event_time"] = event_time
            ups.append(u)
        return self.envelope("l2_data", [{"type": kind, "product_id": product, "updates": ups}], **kw)

    def snapshot(self, levels, **kw):
        return self.l2("snapshot", levels, **kw)

    def update(self, levels, **kw):
        return self.l2("update", levels, **kw)

    def trades(self, trades, kind="update", product="BTC-USD", **kw):
        ts = [{"trade_id": i, "product_id": product, "price": p, "size": s, "side": side,
               "time": tm if tm != "auto" else self.iso(self.send_ns)}
              for i, p, s, side, tm in trades]
        return self.envelope("market_trades", [{"type": kind, "trades": ts}], **kw)


BOOK0 = [("bid", "100", "2"), ("bid", "99.5", "1"), ("offer", "101", "3"), ("offer", "102", "4")]


def healthy_script(feed, *, seconds, start_snapshot=True, heartbeat_every_s=1, l2_every_s=2):
    """A clean synthetic stream: snapshot + trades first, heartbeats each second, updates."""
    s = protocol.S
    sc = Script()
    if start_snapshot:
        sc.frame(s // 10, feed.snapshot(BOOK0))
        sc.frame(s // 10 + 1, feed.trades([("t0", "100.5", "0.1", "BUY", "auto")], kind="snapshot"))
    n = 0
    for sec in range(1, seconds + 1):
        sc.frame(sec * s, feed.heartbeat())
        if sec % l2_every_s == 0:
            n += 1
            sc.frame(sec * s + 1, feed.update([("bid", "100", str(2 + n))]))
    return sc
