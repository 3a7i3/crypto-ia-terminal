"""Bounded public BBO pilot: BTC/USDT then ATOM/USDT Spot, MEXC + Kraken.

MEXC: protobuf aggregated diff depth over WebSocket, joined to the REST depth
snapshot with the official version procedure. Kraken: WS v2 ``book`` depth 10
with the CRC32 checksum verified on every message. Public data only: no key,
account, order, service, systemd unit or app wiring.

Every frame is kept raw with its wall and monotonic receipt times and its
sha256; the results are produced only by the offline replay, which rebuilds
the books from those frames, instant by instant.

Usage (from a checkout of the exact commit):
    python3 -m observability.radar_composite.bbo_pilot dry-run --pair BTC --out DIR
    python3 -m observability.radar_composite.bbo_pilot replay DIR
    python3 -m observability.radar_composite.bbo_pilot run --pair BTC --out DIR \\
        --radar-collector PATH --radar-collector-sha256 HEX --confirm-public-collection BBO-PILOT
``run`` opens public network connections and is only for a separately
authorised runtime GO.

Public preflight (BTC only, separate GO, transport and formats only):
    python3 -m observability.radar_composite.bbo_pilot dry-run-probe --out DIR
    python3 -m observability.radar_composite.bbo_pilot probe --out DIR \\
        --radar-collector PATH --radar-collector-sha256 HEX --confirm-public-collection BBO-PROBE

Exit codes: 0 completed, 2 stopped by a stop condition, 3 preflight refused,
4 usage / evidence error, 5 probe completed with an expected observation missing.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import heapq
import json
import os
import platform
import random
import select
import signal
import socket
import ssl
import sys
import time
import urllib.parse
from decimal import Decimal
from pathlib import Path

from . import bbo_book as bk
from . import bbo_wire as wire
from . import pilot as l3
from .bbo_schema import validate_bbo
from .composite import PERIOD_MS
from .decoders import strict_json
from .instruments import instrument_dict

PILOT = "CAT-RADAR-KRAKEN-MEXC-01/BBO"
PILOT_VERSION = 1
STEP_MS = 10_000
POINTS = 30
WARMUP_MS = 60_000              # books connected and joined 60 s before the boundary
PREFLIGHT_LEAD_MS = 75_000      # REST identity and clocks before the warm-up
PING_EVERY_MS = 1_000
LIVENESS_MS = 2_000             # primary L (pilot hypothesis)
GAP_MAX_BPS = Decimal(50)       # primary G, closed boundary |gap| <= G
SENS_LIVENESS_S = (1, 2, 5, 10)
SENS_GAP_BPS = (10, 25, 50, 100)
FLUX_VIABLE_RATIO = 0.95
VIABLE_RATIO = l3.VIABLE_RATIO      # 0.80, same classes as L3
PARTIAL_RATIO = l3.PARTIAL_RATIO    # 0.50
STOP_HTTP = (403, 418, 429, 451)
MAX_RECONNECTS = 3
MAX_RESYNCS = 3
MEXC_WS = "wss://wbs-api.mexc.com/ws"
KRAKEN_WS = "wss://ws.kraken.com/v2"
MEXC_DEPTH_LIMIT = 5000
KRAKEN_DEPTH = 10
CONNECT_TIMEOUT_S = 6.0         # TCP + TLS + WebSocket handshake, capped by the remaining budget
SEND_TIMEOUT_S = 2.0            # one outgoing frame, capped by the remaining budget
CLOSE_TIMEOUT_S = 1.0
REST_TIMEOUT_S = l3.TIMEOUT_S   # urllib timeout of the L3 transport (4 s per socket operation)
REST_MARGIN_S = 1.0
# Storage cap = frames.bin + events.jsonl + manifest.json of one run (replay/ excluded).
# Ordinary records stop at cap - reserve; the reserve keeps room for the stop
# event, closes and the sealed manifest (at most MANIFEST_MAX_BYTES).
STORAGE_RESERVE_BYTES = 64 * 1024
MANIFEST_MAX_BYTES = 32 * 1024
REST_BUDGET = {("mexc", "depth"): 1 + MAX_RESYNCS, ("mexc", "exchangeInfo"): 1, ("mexc", "time"): 2,
               ("kraken", "assetPairs"): 1, ("kraken", "assets"): 1, ("kraken", "time"): 2}
CAPS = {"max_frames": 200_000, "max_frame_bytes": wire.MAX_MESSAGE_BYTES,
        "max_storage_bytes": 300 * 1024 * 1024}
# Public preflight: BTC only, own caps, qualifies transport and formats only.
PROBE = {"pair": "BTC", "max_seconds": 150, "observe_min_ms": 15_000, "observe_max_ms": 90_000,
         "max_reconnects": 0, "max_resyncs": 1,
         "rest": {("mexc", "depth"): 2, ("mexc", "exchangeInfo"): 1, ("mexc", "time"): 2,
                  ("kraken", "assetPairs"): 1, ("kraken", "assets"): 1, ("kraken", "time"): 2},
         "caps": {"max_frames": 20_000, "max_frame_bytes": wire.MAX_MESSAGE_BYTES,
                  "max_storage_bytes": 20 * 1024 * 1024}}
PROBE_REQUIRED = (
    "python_3_10", "rest_identity_and_clocks", "mexc_ws_open", "kraken_ws_open",
    "mexc_subscription_ack", "mexc_diff_decoded", "mexc_symbol_echo", "mexc_join",
    "mexc_continuity_after_join", "mexc_pong", "kraken_subscribe_ok", "kraken_symbol_echo",
    "kraken_snapshot_checksum", "kraken_update_checksum", "kraken_pong",
)
PROBE_INFORMATIVE = ("kraken_heartbeat",)
HYPOTHESES = {
    "A-ORDER": "the server sends on one connection in order: a PONG received after "
               "earlier diffs proves those diffs were delivered (to qualify at runtime)",
    "SOURCE_TIMES_INFORMATIVE": "MEXC sendTime/createTime and Kraken timestamp are kept "
                                "but never used for freshness",
}

BBO_PAIRS = {
    "BTC": {"mexc_ws_symbol": "BTCUSDT", "kraken_ws_symbol": "BTC/USDT",
            "windows": 2, "max_seconds": 780},
    "ATOM": {"mexc_ws_symbol": "ATOMUSDT", "kraken_ws_symbol": "ATOM/USDT",
             "windows": 3, "max_seconds": 1080},
}
CODE_FILES = ("bbo_book.py", "bbo_wire.py", "bbo_pilot.py", "bbo_schema.py",
              "pilot.py", "instruments.py", "decoders.py", "composite.py")


def mexc_channel(symbol):
    return f"spot@public.aggre.depth.v3.api.pb@100ms@{symbol}"


def cfg(pair):
    if pair not in BBO_PAIRS:
        raise l3.Refused("unknown pair")
    return {**l3.PAIRS[pair], **BBO_PAIRS[pair]}


def rest_urls(pair):
    out = dict(l3.urls(pair))
    out.pop(("mexc", "trades"))
    out.pop(("kraken", "trades"))
    q = urllib.parse.urlencode({"symbol": cfg(pair)["mexc"], "limit": MEXC_DEPTH_LIMIT})
    out[("mexc", "depth")] = f"{l3.MEXC}/api/v3/depth?{q}"
    return out


def subscribe_msgs(c):
    return {
        "mexc": json.dumps({"method": "SUBSCRIPTION", "params": [mexc_channel(c["mexc_ws_symbol"])]}),
        "kraken": json.dumps({"method": "subscribe", "params": {
            "channel": "book", "symbol": [c["kraken_ws_symbol"]], "depth": KRAKEN_DEPTH,
            "snapshot": True}}),
    }


def kraken_unsubscribe(c):
    return json.dumps({"method": "unsubscribe", "params": {
        "channel": "book", "symbol": [c["kraken_ws_symbol"]], "depth": KRAKEN_DEPTH}})


def code_identity():
    root = Path(__file__).resolve().parent
    ident = l3.code_identity()
    ident["files_sha256"] = {n: hashlib.sha256((root / n).read_bytes()).hexdigest()
                             for n in CODE_FILES}
    return ident


def new_engine(c):
    return bk.Engine(c["mexc_ws_symbol"], mexc_channel(c["mexc_ws_symbol"]),
                     c["kraken_ws_symbol"], KRAKEN_DEPTH)


# ---------------------------------------------------------------- evidence

class Evidence:
    """New directory; append-only event log; raw frames concatenated in frames.bin."""

    def __init__(self, out, clock, max_storage_bytes=None):
        self.out = Path(out)
        if self.out.exists() and any(self.out.iterdir()):
            raise l3.Refused("evidence directory must be new or empty")
        self.out.mkdir(parents=True, exist_ok=True)
        os.chmod(self.out, 0o750)
        # Long-lived append handles, closed by seal(); a context manager cannot span the run.
        self.log = open(self.out / "events.jsonl", "ab")  # noqa: SIM115
        self.raw = open(self.out / "frames.bin", "ab")  # noqa: SIM115
        self.offset = 0
        self.log_bytes = 0
        self.seq = 0
        self.cap = max_storage_bytes
        if self.cap is not None and self.cap <= STORAGE_RESERVE_BYTES + MANIFEST_MAX_BYTES:
            raise l3.Refused("storage cap smaller than the reserve")
        self.critical = 0
        self.clock = clock
        self.anchor_wall = clock.wall_ms()
        self.anchor_mono = clock.mono_ms()

    def t_ms(self, mono):
        return self.anchor_wall + (mono - self.anchor_mono)

    def used(self):
        return self.offset + self.log_bytes

    def record(self, venue, kind, payload=b"", *, final=False, **extra):
        """Append one event. The storage budget is checked before any byte is written.

        Ordinary records may use the cap minus the reserve; ``final`` records
        (stop, closes) may use the reserve, never the room kept for the manifest.
        """
        wall, mono = self.clock.wall_ms(), self.clock.mono_ms()
        digest = hashlib.sha256(payload).hexdigest()
        entry = {"seq": self.seq + 1, "venue": venue, "kind": kind, "recv_wall_ms": wall,
                 "recv_mono_ms": mono, "t_ms": self.t_ms(mono), "offset": self.offset,
                 "bytes": len(payload), "sha256": digest, **extra}
        line = (json.dumps(entry, sort_keys=True) + "\n").encode()
        if self.cap is not None:
            limit = self.cap - MANIFEST_MAX_BYTES - (0 if final else STORAGE_RESERVE_BYTES)
            if self.used() + len(payload) + len(line) > limit:
                if final:
                    raise PilotStop("STORAGE_RESERVE_EXHAUSTED", refused_kind=kind)
                raise PilotStop("BUDGET_STORAGE_EXHAUSTED", refused_kind=kind, refused_venue=venue,
                                refused_bytes=len(payload), refused_sha256=digest,
                                used_bytes=self.used(), cap_bytes=self.cap)
        self.critical += 1
        try:
            self.seq += 1
            self.raw.write(payload)
            self.raw.flush()
            self.offset += len(payload)
            self.log.write(line)
            self.log.flush()
            self.log_bytes += len(line)
        finally:
            self.critical -= 1
        return entry

    def sync(self):
        for fh in (self.raw, self.log):
            fh.flush()
            os.fsync(fh.fileno())

    def manifest(self, data):
        text = json.dumps(data, indent=2, sort_keys=True) + "\n"
        if len(text.encode()) > MANIFEST_MAX_BYTES:
            raise l3.Refused("manifest larger than its reserved room")
        tmp = self.out / "manifest.json.tmp"
        tmp.write_text(text)
        os.replace(tmp, self.out / "manifest.json")

    def seal(self):
        self.sync()
        self.log.close()
        self.raw.close()
        return {"events": self.seq,
                "events_sha256": hashlib.sha256((self.out / "events.jsonl").read_bytes()).hexdigest(),
                "frames_sha256": hashlib.sha256((self.out / "frames.bin").read_bytes()).hexdigest(),
                "frames_bytes": self.offset, "events_bytes": self.log_bytes,
                "storage_cap_bytes": self.cap,
                "storage_scope": "frames.bin + events.jsonl + manifest.json (replay/ excluded)"}


# ---------------------------------------------------------------- runner

class PilotStop(l3.Stop):
    """A stop with its context, written into the stop event and the manifest."""

    def __init__(self, code, **detail):
        super().__init__(code)
        self.detail = detail


def stop_class(code):
    if code is None:
        return None
    for prefix, cls in (("PREFLIGHT", "PREFLIGHT"), ("MEXC_MARGIN", "PREFLIGHT"), ("HTTP_", "REST"),
                        ("KRAKEN_RATE_LIMIT", "REST"), ("THREE_CONSECUTIVE", "REST"),
                        ("WS_", "TRANSPORT"), ("WATCHDOG", "BUDGET"), ("BUDGET_", "BUDGET"),
                        ("STORAGE_", "BUDGET"), ("FRAME_TOO_LARGE", "BUDGET")):
        if code.startswith(prefix):
            return cls
    if code.endswith(("PROVIDER_ERROR", "SUBSCRIBE_REFUSED")):
        return "PROVIDER"
    if "RESYNC" in code:
        return "CONTINUITY"
    return "OTHER"


class KrakenAudit:
    """Shadow recomputation of every Kraken book checksum, for diagnosis only.

    It never admits or rejects a book (the engine does). On a mismatch it keeps
    what reproduces the comparison: instrument, message type, received and
    computed checksums and the exact top-10 texts used. The cause stays
    unknown: no normalisation of the literals is ever tried.
    """

    def __init__(self, symbol, depth=KRAKEN_DEPTH):
        self.symbol, self.depth = symbol, depth
        self.book = bk._Book()
        self.synced = False
        self.results = []

    def on_disconnect(self):
        self.book.clear()
        self.synced = False

    def check(self, seq, t_ms, payload):
        try:
            doc = bk.kraken_json(payload)
        except ValueError:
            return []
        if not isinstance(doc, dict) or doc.get("channel") != "book" \
                or doc.get("type") not in ("snapshot", "update"):
            return []
        out = []
        for item in doc.get("data") or []:
            if not isinstance(item, dict) or item.get("symbol") != self.symbol:
                continue
            kind = doc["type"]
            if kind == "update" and not self.synced:
                continue
            base = bk._Book()
            if kind == "update":
                base.bids, base.asks = dict(self.book.bids), dict(self.book.asks)
            try:
                for side, key in (("bid", "bids"), ("ask", "asks")):
                    for level in item.get(key) or []:
                        base.set_level(side, level["price"], level["qty"])
                base.truncate(self.depth)
                received = int(item["checksum"])
            except (ValueError, KeyError, TypeError):
                self.synced = False
                self.book.clear()
                continue
            asks = [(v[1], v[2]) for _, v in base.sorted_asks()[:bk.KRAKEN_CHECKSUM_LEVELS]]
            bids = [(v[1], v[2]) for _, v in base.sorted_bids()[:bk.KRAKEN_CHECKSUM_LEVELS]]
            computed = bk.kraken_checksum(asks, bids)
            match = computed == received
            r = {"frame_seq": seq, "t_ms": t_ms, "instrument": self.symbol, "message_type": kind,
                 "checksum_received": received, "checksum_computed": computed, "match": match}
            if not match:
                r.update(diagnosis="CHECKSUM_MISMATCH", cause="UNKNOWN",
                         top10_asks=asks, top10_bids=bids, timestamp=item.get("timestamp"))
                self.synced = False
                self.book.clear()
            else:
                self.book = base
                self.synced = True
            self.results.append(r)
            out.append(r)
        return out


class Observer:
    """Expected observations of the public preflight, derived from events only."""

    def __init__(self, engine, audit):
        self.engine, self.audit = engine, audit
        self.seen = {}
        self.mexc_after_join = 0

    def mark(self, name, seq):
        self.seen.setdefault(name, seq)

    def feed(self, ev, before):
        venue, kind, seq = ev["venue"], ev["kind"], ev["seq"]
        src = self.engine.sources.get(venue)
        if kind == "ws_open":
            self.mark(f"{venue}_ws_open", seq)
        if src is None:
            return
        c = src.counters
        if venue == "mexc":
            if c.get("subscribed"):
                self.mark("mexc_subscription_ack", seq)
            if c.get("diffs"):
                self.mark("mexc_diff_decoded", seq)
                if not c.get("foreign_frame"):
                    self.mark("mexc_symbol_echo", seq)
            if any(j["outcome"] == "JOINED" for j in src.join_log):
                self.mark("mexc_join", seq)
            if (kind == "ws_message" and before["continuity"] == "SYNCED"
                    and src.continuity == "SYNCED" and src.last_to is not None
                    and before["last_to"] is not None and src.last_to > before["last_to"]):
                self.mexc_after_join += 1
                self.mark("mexc_continuity_after_join", seq)
            if c.get("pong"):
                self.mark("mexc_pong", seq)
        else:
            if c.get("subscribe_ok"):
                self.mark("kraken_subscribe_ok", seq)
            if c.get("pong"):
                self.mark("kraken_pong", seq)
            if c.get("heartbeat"):
                self.mark("kraken_heartbeat", seq)
            res = self.audit.results
            if res and not c.get("foreign_frame"):
                self.mark("kraken_symbol_echo", seq)
            if any(r["message_type"] == "snapshot" and r["match"] for r in res):
                self.mark("kraken_snapshot_checksum", seq)
            if any(r["message_type"] == "update" and r["match"] for r in res):
                self.mark("kraken_update_checksum", seq)

    def report(self, manifest):
        synthetic = manifest["evidence_kind"] == "SYNTHETIC"
        py = manifest.get("python", "")
        out = {}
        for name in PROBE_REQUIRED + PROBE_INFORMATIVE:
            if name == "python_3_10":
                ok = py.startswith("3.10.")
                status = "OBSERVED" if ok else ("NOT_REQUIRED_SYNTHETIC" if synthetic else "MISSING")
                out[name] = {"status": status, "detail": f"python {py}"}
            elif name == "rest_identity_and_clocks":
                pre = manifest.get("preflight")
                out[name] = {"status": "OBSERVED" if pre else "MISSING", "detail": pre}
            else:
                seq = self.seen.get(name)
                status = "OBSERVED" if seq is not None else (
                    "MISSING" if name in PROBE_REQUIRED else "NOT_OBSERVED")
                if seq is None and name.startswith("kraken_") and name.endswith("_checksum"):
                    kind = "snapshot" if "snapshot" in name else "update"
                    if any(r["message_type"] == kind and not r["match"] for r in self.audit.results):
                        status = "CHECKSUM_MISMATCH"
                out[name] = {"status": status, "first_seq": seq,
                             "required": name in PROBE_REQUIRED}
        return out

class BboPilot:
    # Same identity and clock preflight as L3 (reused, not copied).
    preflight = l3.Pilot.preflight
    _offset = l3.Pilot._offset

    def __init__(self, pair, out, session, clock, *, evidence_kind="OBSERVATION",
                 radar_check=None, caps=None, mode="collect", watchdog_s=None):
        if mode not in ("collect", "probe"):
            raise l3.Refused("unknown mode")
        if mode == "probe" and pair != PROBE["pair"]:
            raise l3.Refused("the public preflight is BTC only")
        self.mode = mode
        self.pair, self.cfg = pair, cfg(pair)
        self.urls = rest_urls(pair)
        self.session, self.clock = session, clock
        self.kind = evidence_kind
        self.radar_check = radar_check
        if mode == "probe":
            self.max_seconds = PROBE["max_seconds"]
            self.rest_budget = dict(PROBE["rest"])
            self.max_reconnects, self.max_resyncs = PROBE["max_reconnects"], PROBE["max_resyncs"]
            self.caps = {**PROBE["caps"], **(caps or {})}
        else:
            self.max_seconds = self.cfg["max_seconds"]
            self.rest_budget = dict(REST_BUDGET)
            self.max_reconnects, self.max_resyncs = MAX_RECONNECTS, MAX_RESYNCS
            self.caps = {**CAPS, **(caps or {})}
        self.watchdog_s = self.max_seconds if watchdog_s is None else watchdog_s
        self.evidence = Evidence(out, clock, self.caps["max_storage_bytes"])
        self.engine = new_engine(self.cfg)
        self.audit = KrakenAudit(self.cfg["kraken_ws_symbol"])
        self.observer = Observer(self.engine, self.audit)
        self.stop_detail = None
        self._deadline_pending = False
        self.rest_used = {k: 0 for k in self.rest_budget}
        self.reconnects = {"mexc": 0, "kraken": 0}
        self.resyncs = {"mexc": 0, "kraken": 0}
        self.snapshots = 0
        self.frames = 0
        self.failures = 0
        self.t0 = None
        self.stop_code = None
        self.ping_id = 0

    # -- REST (allow-listed GET), same checks as L3 plus HTTP 451
    def get(self, venue, endpoint, *, purpose):
        key = (venue, endpoint)
        if self.rest_used[key] >= self.rest_budget[key]:
            raise l3.Stop(f"BUDGET_REST_{venue.upper()}_{endpoint.upper()}")
        self._check_duration()
        if self._remaining_s() < REST_TIMEOUT_S + REST_MARGIN_S:
            raise PilotStop("BUDGET_DURATION_INSUFFICIENT_FOR_REST", endpoint=f"{venue}.{endpoint}",
                            remaining_s=round(self._remaining_s(), 3))
        self.rest_used[key] += 1
        sent = self.clock.wall_ms()
        status, headers, body, error = self.session.rest(self.urls[key])
        entry = self._record(venue, "rest_depth" if endpoint == "depth" else "rest", body,
                                     endpoint=endpoint, purpose=purpose, url=self.urls[key],
                                     sent_ms=sent, status=status, error=error,
                                     headers={k.lower(): v for k, v in headers.items()
                                              if k.lower() in l3.KEPT_HEADERS})
        entry["received_ms"] = entry["recv_wall_ms"]
        if status in STOP_HTTP:
            raise l3.Stop(f"HTTP_{status}")
        failed = status != 200
        if venue == "kraken" and status == 200:
            try:
                errs = strict_json(body).get("error")
            except (ValueError, AttributeError):
                errs, failed = None, True
            if errs:
                text = " ".join(map(str, errs))
                if any(s in text for s in ("Too many requests", "Rate limit", "Temporary lockout")):
                    raise l3.Stop("KRAKEN_RATE_LIMIT")
                failed = True
        self.failures = self.failures + 1 if failed else 0
        if self.failures >= l3.MAX_CONSECUTIVE_FAILURES:
            raise l3.Stop("THREE_CONSECUTIVE_FAILURES")
        return entry, body, failed

    def _remaining_s(self):
        if self.t0 is None:
            return float(self.max_seconds)
        return self.max_seconds - (self.clock.mono_ms() - self.t0) / 1000

    def _check_duration(self):
        if self.t0 is not None and self._remaining_s() <= 0:
            raise l3.Stop("BUDGET_DURATION_EXHAUSTED")

    def _bounded(self, cap_s):
        """Timeout of one network operation: its own cap, never past the run budget."""
        left = self._remaining_s()
        if left <= 0:
            raise l3.Stop("BUDGET_DURATION_EXHAUSTED")
        return min(cap_s, left)

    # -- watchdog: a blocked call cannot outlive the budget
    def _arm_watchdog(self):
        if self.watchdog_s is None or not hasattr(signal, "setitimer"):
            return "UNAVAILABLE"
        try:
            self._previous_handler = signal.signal(signal.SIGALRM, self._on_deadline)
        except ValueError:  # not the main thread
            return "UNAVAILABLE_NOT_MAIN_THREAD"
        signal.setitimer(signal.ITIMER_REAL, float(self.watchdog_s))
        return f"ARMED_{self.watchdog_s}s"

    def _disarm_watchdog(self):
        if getattr(self, "_previous_handler", None) is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self._previous_handler)
            self._previous_handler = None

    def _on_deadline(self, signum, frame):
        if self.evidence.critical:
            self._deadline_pending = True  # never cut a record in half
            return
        raise PilotStop("WATCHDOG_DEADLINE", watchdog_s=self.watchdog_s)

    def _record(self, *args, **kw):
        entry = self.evidence.record(*args, **kw)
        if self._deadline_pending and not kw.get("final"):
            self._deadline_pending = False
            raise PilotStop("WATCHDOG_DEADLINE", watchdog_s=self.watchdog_s)
        return entry

    # -- WebSocket side
    def _open(self, venue, purpose):
        timeout = self._bounded(CONNECT_TIMEOUT_S)
        try:
            self.session.open(venue, timeout_s=timeout)
        except (wire.WireError, OSError) as exc:
            code = exc.code if isinstance(exc, wire.WireError) else type(exc).__name__.upper()
            self._feed(self._record(venue, "ws_error", b"", detail=code, purpose=purpose,
                                    timeout_s=round(timeout, 3)))
            raise PilotStop(f"WS_REFUSED_{venue.upper()}", detail=code, timeout_s=round(timeout, 3)) from exc
        self._feed(self._record(venue, "ws_open", b"", purpose=purpose))
        self._send(venue, subscribe_msgs(self.cfg)[venue], "subscribe")

    def _send(self, venue, text, purpose):
        timeout = self._bounded(SEND_TIMEOUT_S)
        try:
            self.session.send_text(venue, text, timeout_s=timeout)
        except (wire.WireError, OSError) as exc:
            code = exc.code if isinstance(exc, wire.WireError) else type(exc).__name__.upper()
            self._record(venue, "send_failed", text.encode(), purpose=purpose, detail=code,
                         timeout_s=round(timeout, 3))
            stop = "WS_SEND_TIMEOUT" if code == "SEND_TIMEOUT" else "WS_SEND_FAILED"
            raise PilotStop(f"{stop}_{venue.upper()}", detail=code, purpose=purpose,
                            timeout_s=round(timeout, 3)) from exc
        self._record(venue, "sent", text.encode(), purpose=purpose)

    def _feed(self, entry, payload=b""):
        ev = {**entry, "payload": payload}
        venue = ev["venue"]
        src = self.engine.sources.get(venue)
        before = {"continuity": src.continuity, "last_to": getattr(src, "last_to", None)} if src else None
        if venue == "kraken" and ev["kind"] in ("ws_close", "ws_error", "gave_up"):
            self.audit.on_disconnect()
        diags = []
        if venue == "kraken" and ev["kind"] == "ws_message" and ev.get("opcode") == wire.OP_TEXT:
            diags = [r for r in self.audit.check(ev["seq"], ev["t_ms"], payload) if not r["match"]]
        actions = self.engine.apply(ev)
        self.observer.feed(ev, before)
        for r in diags:
            # Raw message kept again next to what reproduces the comparison.
            self._record("kraken", "checksum_mismatch", payload,
                         **{k: v for k, v in r.items() if k != "t_ms"})
        for venue_, action in actions:
            self._act(venue_, action)

    def _act(self, venue, action):
        if action == "NEED_SNAPSHOT":
            if self.snapshots >= 1:
                self.resyncs["mexc"] += 1
                if self.resyncs["mexc"] > self.max_resyncs:
                    raise l3.Stop("MEXC_RESYNC_BUDGET_EXHAUSTED")
            self.snapshots += 1
            entry, body, _ = self.get("mexc", "depth", purpose="snapshot")
            self._feed(entry, body)
        elif action == "NEED_RESUBSCRIBE":
            self.resyncs["kraken"] += 1
            if self.resyncs["kraken"] > self.max_resyncs:
                raise l3.Stop("KRAKEN_RESYNC_BUDGET_EXHAUSTED")
            self._send("kraken", kraken_unsubscribe(self.cfg), "resync_unsubscribe")
            self._send("kraken", subscribe_msgs(self.cfg)["kraken"], "resync_subscribe")
        elif action == "SUBSCRIBE_REFUSED":
            raise l3.Stop("KRAKEN_SUBSCRIBE_REFUSED")

    def _ping(self):
        self.ping_id += 1
        self._send("mexc", json.dumps({"method": "PING"}), "ping")
        self._send("kraken", json.dumps({"method": "ping", "req_id": self.ping_id}), "ping")

    def _receive(self, until):
        until = min(until, self.clock.wall_ms() + int(self._bounded(PING_EVERY_MS / 1000) * 1000))
        for venue, kind, opcode, payload in self.session.poll(until):
            if kind == "ws_message":
                self.frames += 1
                if self.frames > self.caps["max_frames"]:
                    raise PilotStop("BUDGET_FRAMES_EXHAUSTED", refused_venue=venue,
                                    refused_bytes=len(payload))
                if len(payload) > self.caps["max_frame_bytes"]:
                    raise PilotStop("FRAME_TOO_LARGE", refused_venue=venue, refused_bytes=len(payload))
            entry = self._record(venue, kind, payload, opcode=opcode)
            self._provider_error(venue, kind, opcode, payload)
            self._feed(entry, payload)
            if kind in ("ws_close", "ws_error"):
                self.reconnects[venue] += 1
                if self.reconnects[venue] > self.max_reconnects:
                    self._feed(self._record(venue, "gave_up", b""))
                    raise l3.Stop(f"WS_RECONNECTS_EXHAUSTED_{venue.upper()}")
                self._open(venue, "reconnect")

    def _provider_error(self, venue, kind, opcode, payload):
        if kind != "ws_message" or opcode != wire.OP_TEXT:
            return
        try:
            doc = json.loads(payload)
        except ValueError:
            return
        if not isinstance(doc, dict):
            return
        if venue == "kraken" and doc.get("error") and doc.get("method") not in ("unsubscribe",):
            raise l3.Stop("KRAKEN_PROVIDER_ERROR")
        if venue == "mexc" and isinstance(doc.get("code"), int) and doc["code"] != 0:
            raise l3.Stop("MEXC_PROVIDER_ERROR")

    def run(self, start_ms=None):
        if self.mode == "probe":
            return self.run_probe()
        now = self.clock.wall_ms()
        if start_ms is None:
            start_ms = -(-(now + PREFLIGHT_LEAD_MS + 15_000) // PERIOD_MS) * PERIOD_MS
        n = self.cfg["windows"] * POINTS
        end_ms = start_ms + (n - 1) * STEP_MS + 1_000
        manifest = self._manifest(start_ms, end_ms, "WAITING")
        self.evidence.manifest(manifest)
        self.clock.sleep_until_wall(start_ms - PREFLIGHT_LEAD_MS)

        def body():
            planned = (end_ms - (start_ms - PREFLIGHT_LEAD_MS) + 5_000) / 1000
            if planned > self.max_seconds:
                raise l3.Stop("PREFLIGHT_SLOT_DOES_NOT_FIT")
            manifest["preflight"] = self.preflight()
            self.clock.sleep_until_wall(start_ms - WARMUP_MS)
            self._collect(lambda: self.clock.wall_ms() >= end_ms, end_ms)
            return 0
        return self._execute(manifest, body)

    def run_probe(self):
        """Public preflight: transport, identity and formats. No composite conclusion."""
        manifest = self._manifest(None, None, "WAITING")
        self.evidence.manifest(manifest)
        state = {}

        def done():
            elapsed = self.clock.wall_ms() - state["opened_ms"]
            if elapsed >= PROBE["observe_max_ms"]:
                return True
            missing = [o for o in PROBE_REQUIRED
                       if o not in ("python_3_10", "rest_identity_and_clocks") and o not in self.observer.seen]
            return not missing and elapsed >= PROBE["observe_min_ms"]

        def body():
            manifest["preflight"] = self.preflight()
            state["opened_ms"] = self.clock.wall_ms()
            self._collect(done, state["opened_ms"] + PROBE["observe_max_ms"])
            report = self.observer.report(manifest)
            missing = [k for k, v in report.items() if v.get("required", True)
                       and v["status"] not in ("OBSERVED", "NOT_REQUIRED_SYNTHETIC")]
            manifest["probe_live"] = {"missing": missing}
            return 5 if missing else 0
        return self._execute(manifest, body)

    def _collect(self, finished, end_ms):
        for venue in bk.VENUES:
            self._open(venue, "initial")
        next_ping = self.clock.wall_ms()
        while not finished():
            self._check_duration()
            if self.clock.wall_ms() >= next_ping:
                self._ping()
                next_ping += PING_EVERY_MS
            self._receive(min(next_ping, end_ms))
            self.evidence.sync()
        for venue in bk.VENUES:
            self.session.close(venue, timeout_s=CLOSE_TIMEOUT_S)
            self._record(venue, "closed_by_pilot", b"")

    def _execute(self, manifest, body):
        manifest["status"] = "RUNNING"
        self.evidence.manifest(manifest)
        exit_code = 0
        self.t0 = self.clock.mono_ms()
        manifest["watchdog"] = self._arm_watchdog()
        try:
            exit_code = body()
            manifest["clock_end"] = {
                "mexc_offset_ms": self._offset(self.get("mexc", "time", purpose="clock_end")[0],
                                               self._last_body(), "mexc"),
                "kraken_offset_ms": self._offset(self.get("kraken", "time", purpose="clock_end")[0],
                                                 self._last_body(), "kraken"),
            }
            manifest["status"] = "COMPLETED"
        except l3.Stop as stop:
            self._disarm_watchdog()
            self.stop_code = stop.code
            self.stop_detail = getattr(stop, "detail", None) or None
            manifest["status"] = "STOPPED"
            exit_code = 3 if stop.code.startswith("PREFLIGHT") else 2
            with contextlib.suppress(l3.Stop):
                self.evidence.record("pilot", "stop", stop.code.encode(), final=True,
                                     stop_detail=self.stop_detail)
        finally:
            self._disarm_watchdog()
            for venue in bk.VENUES:
                try:
                    self.session.close(venue, timeout_s=CLOSE_TIMEOUT_S)
                except (OSError, wire.WireError) as exc:  # best effort close, never masks the stop
                    with contextlib.suppress(l3.Stop):
                        self.evidence.record(venue, "close_error", type(exc).__name__.encode(), final=True)
            manifest.update(stop_code=self.stop_code, stop_class=stop_class(self.stop_code),
                            stop_detail=self.stop_detail, exit_code=exit_code,
                            ended_wall_ms=self.clock.wall_ms(),
                            elapsed_ms=self.clock.mono_ms() - self.t0 if self.t0 else None,
                            rest_used={f"{v}.{e}": n for (v, e), n in self.rest_used.items()},
                            reconnects=self.reconnects, resyncs=self.resyncs, frames=self.frames,
                            sealed=self.evidence.seal())
            self.evidence.manifest(manifest)
        return exit_code

    def _last_body(self):
        log = (self.evidence.out / "events.jsonl").read_text().splitlines()
        entry = json.loads(log[-1])
        with open(self.evidence.out / "frames.bin", "rb") as fh:
            fh.seek(entry["offset"])
            return fh.read(entry["bytes"])

    def _manifest(self, start_ms, end_ms, status):
        ins, binds = l3.bindings(self.pair)
        c = self.cfg
        return {
            "pilot": PILOT, "pilot_version": PILOT_VERSION, "pair": self.pair,
            "evidence_kind": self.kind, "status": status, "market_type": "SPOT",
            "instrument": instrument_dict(ins),
            "bindings": {v: b.as_dict() for v, b in binds.items()},
            "ws": {"mexc": {"url": MEXC_WS, "symbol": c["mexc_ws_symbol"],
                            "channel": mexc_channel(c["mexc_ws_symbol"])},
                   "kraken": {"url": KRAKEN_WS, "symbol": c["kraken_ws_symbol"], "depth": KRAKEN_DEPTH}},
            "mode": self.mode,
            "window_start_ms": start_ms, "windows": c["windows"] if self.mode == "collect" else 0,
            "end_ms": end_ms,
            "clock_anchor": {"wall_ms": self.evidence.anchor_wall, "mono_ms": self.evidence.anchor_mono},
            "grid": {"step_ms": STEP_MS, "points_per_window": POINTS, "warmup_ms": WARMUP_MS,
                     "preflight_lead_ms": PREFLIGHT_LEAD_MS, "ping_every_ms": PING_EVERY_MS},
            "budget": {"max_seconds": self.max_seconds,
                       "rest": {f"{v}.{e}": n for (v, e), n in self.rest_budget.items()},
                       "max_reconnects_per_venue": self.max_reconnects,
                       "max_resyncs_per_source": self.max_resyncs,
                       "timeouts_s": {"connect": CONNECT_TIMEOUT_S, "send": SEND_TIMEOUT_S,
                                      "close": CLOSE_TIMEOUT_S, "rest": REST_TIMEOUT_S,
                                      "capped_by_remaining_budget": True},
                       "watchdog_s": self.watchdog_s,
                       "storage": {"scope": "frames.bin + events.jsonl + manifest.json",
                                   "reserve_bytes": STORAGE_RESERVE_BYTES,
                                   "manifest_max_bytes": MANIFEST_MAX_BYTES},
                       **self.caps},
            "probe": ({"observe_min_ms": PROBE["observe_min_ms"], "observe_max_ms": PROBE["observe_max_ms"],
                       "required": list(PROBE_REQUIRED), "informative": list(PROBE_INFORMATIVE),
                       "scope": "transport and formats only; no composite viability conclusion"}
                      if self.mode == "probe" else None),
            "stop_rules": {"http": list(STOP_HTTP), "consecutive_rest_failures": l3.MAX_CONSECUTIVE_FAILURES,
                           "ws_refused": True, "provider_error": True, "mexc_margin_required": True},
            "parameters_primary": params(LIVENESS_MS, GAP_MAX_BPS),
            "pre_registered": {"flux_viable_ratio": FLUX_VIABLE_RATIO, "viable_ratio": VIABLE_RATIO,
                               "partial_ratio": PARTIAL_RATIO, "sensitivity_liveness_s": list(SENS_LIVENESS_S),
                               "sensitivity_gap_bps": list(SENS_GAP_BPS)},
            "hypotheses": HYPOTHESES,
            "endpoints": {f"{v}.{e}": u for (v, e), u in self.urls.items()},
            "code": code_identity(), "host": platform.node(), "python": platform.python_version(),
            "created_wall_ms": self.clock.wall_ms(),
        }


def params(liveness_ms, gap_bps):
    return {"liveness_max_ms": int(liveness_ms), "gap_max_bps": str(gap_bps),
            "gap_boundary": "CLOSED", "weights": "EQUAL", "reference_venue": bk.REFERENCE,
            "step_ms": STEP_MS, "points_per_window": POINTS}


# ---------------------------------------------------------------- replay

def load(out):
    """Verify the sealed evidence and return (manifest, events with payloads)."""
    out = Path(out)
    manifest = json.loads((out / "manifest.json").read_text())
    sealed = manifest.get("sealed")
    log_bytes = (out / "events.jsonl").read_bytes()
    raw = (out / "frames.bin").read_bytes()
    if not sealed:
        raise l3.Refused("evidence not sealed")
    if hashlib.sha256(log_bytes).hexdigest() != sealed["events_sha256"]:
        raise l3.Refused("event log does not match its sealed hash")
    if hashlib.sha256(raw).hexdigest() != sealed["frames_sha256"]:
        raise l3.Refused("frames do not match their sealed hash")
    anchor = manifest["clock_anchor"]
    events, prev_seq, prev_mono = [], 0, None
    for line in log_bytes.decode().splitlines():
        e = json.loads(line)
        payload = raw[e["offset"]:e["offset"] + e["bytes"]]
        if len(payload) != e["bytes"] or hashlib.sha256(payload).hexdigest() != e["sha256"]:
            raise l3.Refused(f"frame {e['seq']} does not match its hash")
        if e["seq"] != prev_seq + 1 or (prev_mono is not None and e["recv_mono_ms"] < prev_mono):
            raise l3.Refused(f"event {e['seq']} out of order")
        if e["t_ms"] != anchor["wall_ms"] + e["recv_mono_ms"] - anchor["mono_ms"]:
            raise l3.Refused(f"event {e['seq']} time inconsistent with the monotonic anchor")
        prev_seq, prev_mono = e["seq"], e["recv_mono_ms"]
        events.append({**e, "payload": payload})
    if len(events) != sealed["events"]:
        raise l3.Refused("event count differs from the seal")
    return manifest, events


def _source_point(snap, state, values, t):
    eligible = state in bk.ELIGIBLE
    v = values or {}
    return {
        "state": state, "eligible": eligible,
        "bid": bk.fmt(v.get("bid")), "ask": bk.fmt(v.get("ask")),
        "bid_qty": bk.fmt(v.get("bid_qty")), "ask_qty": bk.fmt(v.get("ask_qty")),
        "mid": bk.fmt(v.get("mid")), "spread_bps": bk.fmt(v.get("spread_bps"), 6),
        "continuity": snap["continuity"], "lost_reason": snap["lost_reason"],
        "quote_as_of_ms": snap["last_update_ms"],
        "quote_age_ms": None if snap["last_update_ms"] is None else t - snap["last_update_ms"],
        "last_top_change_ms": snap["last_top_change_ms"],
        "liveness_ms": snap["last_liveness_ms"],
        "liveness_age_ms": None if snap["last_liveness_ms"] is None else t - snap["last_liveness_ms"],
        "source_timestamp": snap["source_ts"],
    }


def publication(manifest, w, instants, snaps, evaluated_until, liveness_ms, gap_bps):
    points, comp_series = [], []
    series = {v: [] for v in bk.VENUES}
    cats = {c: 0 for c in bk.CATEGORIES}
    states = {v: {s: 0 for s in bk.SOURCE_STATES} for v in bk.VENUES}
    for t, snap in zip(instants, snaps):
        if evaluated_until is not None and t > evaluated_until:
            cats[bk.NOT_EVALUATED] += 1
            comp_series.append(None)
            for v in bk.VENUES:
                series[v].append(None)
            points.append({"instant_ms": t, "category": bk.NOT_EVALUATED, "composite_mid": None,
                           "mid_gap_bps": None, "sources": None})
            continue
        r = bk.evaluate_pair(snap, t, liveness_ms, gap_bps)
        cats[r["category"]] += 1
        comp_series.append(r["composite_mid"])
        for v in bk.VENUES:
            states[v][r["states"][v]] += 1
            series[v].append(r["values"][v]["mid"] if r["values"][v] else None)
        points.append({
            "instant_ms": t, "category": r["category"],
            "composite_mid": bk.fmt(r["composite_mid"]),
            "mid_gap_bps": bk.fmt(r["gap_bps"], 6),
            "sources": {v: _source_point(snap[v], r["states"][v], r["values"][v], t) for v in bk.VENUES},
        })

    def fmt_candle(c):
        return {k: (bk.fmt(x) if k in ("open", "high", "low", "close") else x) for k, x in c.items()}

    return {
        "schema": "MarketBboComposite", "schema_version": "1.0.0",
        "pilot": PILOT, "evidence_kind": manifest["evidence_kind"],
        "instrument": manifest["instrument"], "market_type": "SPOT",
        "venues": manifest["ws"], "parameters": params(liveness_ms, gap_bps),
        "window": {"index": w, "start_ms": instants[0], "end_ms": instants[0] + PERIOD_MS},
        "points": points,
        "counts": {"by_category": cats, "by_source_state": states},
        "candles": {"composite": fmt_candle(bk.candle(comp_series)),
                    **{v: fmt_candle(bk.candle(series[v])) for v in bk.VENUES}},
    }


def audit_pass(c, events):
    """Second offline pass: Kraken checksum audit and preflight observations."""
    engine = new_engine(c)
    audit = KrakenAudit(c["kraken_ws_symbol"])
    observer = Observer(engine, audit)
    live_diags = []
    for ev in events:
        venue, kind = ev["venue"], ev["kind"]
        if kind == "checksum_mismatch":
            live_diags.append({k: ev[k] for k in ("frame_seq", "checksum_received", "checksum_computed")})
            continue
        src = engine.sources.get(venue)
        before = {"continuity": src.continuity, "last_to": getattr(src, "last_to", None)} if src else None
        if venue == "kraken" and kind in ("ws_close", "ws_error", "gave_up"):
            audit.on_disconnect()
        if venue == "kraken" and kind == "ws_message" and ev.get("opcode") == wire.OP_TEXT:
            audit.check(ev["seq"], ev["t_ms"], ev["payload"])
        engine.apply(ev)
        observer.feed(ev, before)
    mismatches = [r for r in audit.results if not r["match"]]
    replayed = [{k: r[k] for k in ("frame_seq", "checksum_received", "checksum_computed")} for r in mismatches]
    if replayed != live_diags:
        raise l3.Refused("checksum diagnostics recorded live differ from the replay")
    by_kind = {}
    for r in audit.results:
        k = by_kind.setdefault(r["message_type"], {"match": 0, "mismatch": 0})
        k["match" if r["match"] else "mismatch"] += 1
    kraken = {"checked_by_type": by_kind, "mismatches": mismatches,
              "engine_counters": dict(sorted(engine.sources["kraken"].counters.items()))}
    return engine, observer, kraken


def probe_replay(out, manifest, events):
    c = cfg(manifest["pair"])
    engine, observer, kraken = audit_pass(c, events)
    obs = observer.report(manifest)
    missing = [k for k, v in obs.items() if v.get("required", True)
               and v["status"] not in ("OBSERVED", "NOT_REQUIRED_SYNTHETIC")]
    mexc = engine.sources["mexc"]
    report = {
        "pair": manifest["pair"], "mode": "probe", "status": manifest["status"],
        "stop_code": manifest.get("stop_code"), "stop_class": manifest.get("stop_class"),
        "evidence_kind": manifest["evidence_kind"], "python": manifest.get("python"),
        "code": manifest["code"], "rest_used": manifest.get("rest_used"),
        "frames": manifest.get("frames"), "events": manifest["sealed"]["events"],
        "observations": obs, "missing_required": missing,
        "verdict": ("PROBE_STOPPED" if manifest["status"] != "COMPLETED" else
                    "PROBE_QUALIFIED" if not missing else "PROBE_INCOMPLETE"),
        "scope": "transport and formats only; no composite viability conclusion",
        "mexc": {"join_log": mexc.join_log, "breaks": mexc.breaks,
                 "diffs_after_join_contiguous": observer.mexc_after_join,
                 "counters": dict(sorted(mexc.counters.items()))},
        "kraken": {**kraken, "breaks": engine.sources["kraken"].breaks},
    }
    rdir = Path(out) / "replay"
    rdir.mkdir(exist_ok=True)
    (rdir / "probe_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def replay(out):
    """Offline: rebuild books from the frames, instant by instant, and summarise."""
    out = Path(out)
    manifest, events = load(out)
    if manifest.get("mode") == "probe":
        return probe_replay(out, manifest, events)
    c = cfg(manifest["pair"])
    _, _, kraken_audit = audit_pass(c, events)
    n = manifest["windows"] * POINTS
    instants = [manifest["window_start_ms"] + i * STEP_MS for i in range(n)]
    engine = new_engine(c)
    snaps = bk.sample(engine, events, instants)
    stop_t = None
    if manifest["status"] != "COMPLETED":
        stops = [e["t_ms"] for e in events if e["kind"] == "stop"]
        stop_t = stops[-1] if stops else (events[-1]["t_ms"] if events else instants[0] - 1)
    rdir = out / "replay"
    rdir.mkdir(exist_ok=True)
    windows = []
    for w in range(manifest["windows"]):
        sl = slice(w * POINTS, (w + 1) * POINTS)
        pub = publication(manifest, w, instants[sl], snaps[sl], stop_t, LIVENESS_MS, GAP_MAX_BPS)
        errors = validate_bbo(pub)
        if errors:
            raise l3.Refused(f"replayed publication fails validation: {errors[:3]}")
        (rdir / f"window_{w}_primary.json").write_text(json.dumps(pub, indent=2, sort_keys=True) + "\n")
        sens = {}
        for ls in SENS_LIVENESS_S:
            for g in SENS_GAP_BPS:
                p = publication(manifest, w, instants[sl], snaps[sl], stop_t, ls * 1000, Decimal(g))
                sens[f"L{ls}s_G{g}bps"] = p["counts"]["by_category"][bk.COMPOSITE]
        flux_sens = {}
        for ls in SENS_LIVENESS_S:
            p = publication(manifest, w, instants[sl], snaps[sl], stop_t, ls * 1000, GAP_MAX_BPS)
            flux_sens[f"L{ls}s"] = {v: sum(p["counts"]["by_source_state"][v][s] for s in bk.ELIGIBLE)
                                    for v in bk.VENUES}
        cats = pub["counts"]["by_category"]
        windows.append({
            "window": w, "start_ms": instants[sl][0], "planned": POINTS,
            "evaluated": POINTS - cats[bk.NOT_EVALUATED], "composite": cats[bk.COMPOSITE],
            "by_category": cats, "by_source_state": pub["counts"]["by_source_state"],
            "candles": {k: v["status"] for k, v in pub["candles"].items()},
            "sensitivity_composite": sens, "sensitivity_flux_eligible": flux_sens,
        })
    evaluated = sum(w["evaluated"] for w in windows)
    composite = sum(w["composite"] for w in windows)
    ratio = None if evaluated == 0 else composite / evaluated
    verdict = ("NO_EVALUATED_INSTANT" if ratio is None else
               "COMPOSITE_VIABLE_AT_PRIMARY" if ratio >= VIABLE_RATIO else
               "PARTIAL_AT_PRIMARY" if ratio >= PARTIAL_RATIO else "NOT_VIABLE_AT_PRIMARY")
    flux = {}
    for v, src in engine.sources.items():
        eligible = sum(w["by_source_state"][v][s] for w in windows for s in bk.ELIGIBLE)
        unchanged = sum(w["by_source_state"][v][bk.UNCHANGED_VERIFIED] for w in windows)
        unresolved = sum(1 for b in src.breaks if b["resolved_at_ms"] is None)
        r = None if evaluated == 0 else eligible / evaluated
        flux[v] = {"eligible": eligible, "of_which_unchanged_verified": unchanged,
                   "evaluated": evaluated, "ratio": r, "breaks": src.breaks,
                   "unresolved_breaks": unresolved, "counters": dict(sorted(src.counters.items())),
                   "join_log": getattr(src, "join_log", []),
                   "verdict": ("NO_EVALUATED_INSTANT" if r is None else
                               "FLUX_VIABLE" if r >= FLUX_VIABLE_RATIO and unresolved == 0
                               else "FLUX_NOT_VIABLE")}
    summary = {
        "pair": manifest["pair"], "status": manifest["status"], "stop_code": manifest.get("stop_code"),
        "evidence_kind": manifest["evidence_kind"], "code": manifest["code"],
        "rest_used": manifest.get("rest_used"), "reconnects": manifest.get("reconnects"),
        "resyncs": manifest.get("resyncs"), "frames": manifest.get("frames"),
        "events": manifest["sealed"]["events"], "windows": windows, "flux": flux,
        "stop_class": manifest.get("stop_class"), "stop_detail": manifest.get("stop_detail"),
        "kraken_checksum_audit": kraken_audit,
        "totals": {"planned": POINTS * len(windows), "evaluated": evaluated, "composite": composite,
                   "composite_ratio_over_evaluated": ratio, "verdict_pre_registered": verdict,
                   "complete_composite_candles": sum(w["candles"]["composite"] == "COMPLETE"
                                                     for w in windows)},
    }
    (rdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


# ---------------------------------------------------------------- real transport (runtime GO only)

class WsConnection:
    """Blocking-connect, select-driven RFC 6455 client over stdlib ssl."""

    def __init__(self, url, timeout_s=CONNECT_TIMEOUT_S):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "wss" or url not in (MEXC_WS, KRAKEN_WS):
            raise l3.Refused("WebSocket URL outside the allow-list")
        # One deadline for TCP connect, TLS and the HTTP upgrade together.
        # Name resolution is not interruptible here: the pilot watchdog covers it.
        deadline = time.monotonic() + timeout_s
        raw = socket.create_connection((parts.hostname, 443), timeout=timeout_s)
        try:
            raw.settimeout(max(0.001, deadline - time.monotonic()))
            ctx = ssl.create_default_context()
            self.sock = ctx.wrap_socket(raw, server_hostname=parts.hostname)
            key = wire.new_key()
            wire.send_all_bounded(self.sock, wire.handshake_request(parts.hostname, parts.path or "/", key),
                                  deadline - time.monotonic())
            head = b""
            while b"\r\n\r\n" not in head:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise wire.WireError("HANDSHAKE_TIMEOUT")
                self.sock.settimeout(left)
                try:
                    chunk = self.sock.recv(4096)
                except TimeoutError as exc:
                    raise wire.WireError("HANDSHAKE_TIMEOUT") from exc
                if not chunk or len(head) > 16_384:
                    raise wire.WireError("HANDSHAKE_INCOMPLETE")
                head += chunk
            _, rest = wire.parse_handshake_response(head, key)
        except BaseException:
            raw.close()
            raise
        self.sock.setblocking(False)
        self.parser = wire.FrameParser()
        self.pending = self.parser.feed(rest)

    def send_text(self, text, timeout_s=SEND_TIMEOUT_S):
        wire.send_all_bounded(self.sock, wire.encode_client_frame(wire.OP_TEXT, text.encode()), timeout_s)

    def send_control(self, opcode, payload=b"", timeout_s=SEND_TIMEOUT_S):
        wire.send_all_bounded(self.sock, wire.encode_client_frame(opcode, payload), timeout_s)

    def read(self):
        out, self.pending = self.pending, []
        while True:
            try:
                data = self.sock.recv(65536)
            except (ssl.SSLWantReadError, BlockingIOError):
                return out, False
            if not data:
                return out, True
            out += self.parser.feed(data)
            if not self.sock.pending():
                return out, False

    def close(self, timeout_s=CLOSE_TIMEOUT_S):
        try:
            self.send_control(wire.OP_CLOSE, wire.close_payload(1000), timeout_s)
        except (OSError, wire.WireError):
            pass  # closing anyway; the socket is released below
        self.sock.close()


class RealSession:
    def __init__(self, pair, clock):
        self.urls = {"mexc": MEXC_WS, "kraken": KRAKEN_WS}
        self.rest_transport = l3.UrllibTransport(rest_urls(pair).values())
        self.conns = {}
        self.clock = clock

    def rest(self, url):
        return self.rest_transport(url)

    def open(self, venue, timeout_s=CONNECT_TIMEOUT_S):
        self.conns[venue] = WsConnection(self.urls[venue], timeout_s)

    def send_text(self, venue, text, timeout_s=SEND_TIMEOUT_S):
        conn = self.conns.get(venue)
        if conn is None:
            raise wire.WireError("SEND_NOT_CONNECTED")
        conn.send_text(text, timeout_s)

    def close(self, venue, timeout_s=CLOSE_TIMEOUT_S):
        conn = self.conns.pop(venue, None)
        if conn is not None:
            conn.close(timeout_s)

    def poll(self, until_wall_ms):
        timeout = max(0.0, (until_wall_ms - self.clock.wall_ms()) / 1000)
        ready = [c for c in self.conns.values() if c.pending]
        if not ready:
            socks = {c.sock: c for c in self.conns.values()}
            r, _, _ = select.select(list(socks), [], [], timeout)
            ready = [socks[s] for s in r]
        events = []
        for venue, conn in list(self.conns.items()):
            if conn not in ready:
                continue
            try:
                msgs, closed = conn.read()
            except wire.WireError as exc:
                events.append((venue, "ws_error", None, exc.code.encode()))
                self.conns.pop(venue).sock.close()
                continue
            except OSError as exc:
                events.append((venue, "ws_error", None, type(exc).__name__.encode()))
                self.conns.pop(venue).sock.close()
                continue
            for opcode, payload in msgs:
                if opcode == wire.OP_PING:
                    events.append((venue, "ws_control", opcode, payload))
                    try:
                        conn.send_control(wire.OP_PONG, payload, SEND_TIMEOUT_S)
                    except (OSError, wire.WireError) as exc:
                        code = exc.code if isinstance(exc, wire.WireError) else type(exc).__name__
                        events.append((venue, "ws_error", None, f"PONG_{code}".encode()))
                        closed = True
                        break
                elif opcode == wire.OP_PONG:
                    events.append((venue, "ws_control", opcode, payload))
                elif opcode == wire.OP_CLOSE:
                    events.append((venue, "ws_close", opcode, payload))
                    closed = True
                else:
                    events.append((venue, "ws_message", opcode, payload))
            if closed:
                if not events or events[-1][:2] not in ((venue, "ws_close"), (venue, "ws_error")):
                    events.append((venue, "ws_close", None, b""))
                self.conns.pop(venue).sock.close()
        return events


def bbo_margin_check(collector_path, expected_sha256):
    """The deployed Radar collector must be the audited file and never call /api/v3/depth."""
    def check():
        try:
            data = Path(collector_path).read_bytes()
        except OSError:
            return False, "RADAR_COLLECTOR_UNREADABLE"
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256:
            return False, f"RADAR_COLLECTOR_CHANGED:{digest}"
        if b"/api/v3/depth" in data:
            return False, "RADAR_USES_DEPTH_ENDPOINT"
        return True, f"RADAR_COLLECTOR_AUDITED:{digest}:NO_DEPTH_ENDPOINT:WEIGHT_ESTIMATE_ONLY"
    return check


# ---------------------------------------------------------------- synthetic venues (no network)

SIM_PROFILES = {
    # tick sizes in quote units; activity periods in ms
    "BTC": {"mid": 62000.0, "mexc_tick": "0.01", "kraken_tick": "0.1", "kraken_offset_bps": 3,
            "mexc_every_ms": 200, "kraken_every_ms": 500, "faults": [
                ("mexc_gap", 0, 65_500), ("kraken_bad_checksum", 1, 95_000),
                ("kraken_silence", 1, 147_000, 151_000)]},
    "ATOM": {"mid": 8.0, "mexc_tick": "0.001", "kraken_tick": "0.0001", "kraken_offset_bps": 20,
             "mexc_every_ms": 1_000, "kraken_every_ms": 15_000, "faults": [
                 ("mexc_disconnect", 1, 42_000), ("kraken_offset_bps", 2, 0, 300_000, 70)]},
}


class FakeVenues:
    """Deterministic synthetic MEXC/Kraken books behind the session interface.

    MEXC diffs are protobuf-encoded with the field numbers of the official
    .proto; Kraken messages are JSON with numeric literals and a CRC32
    computed with the official algorithm. Faults are scheduled per window.
    """

    def __init__(self, pair, clock, *, seed=7, start_ms=None, profile=None, latency_ms=30):
        self.c = cfg(pair)
        self.p = copy.deepcopy(profile or SIM_PROFILES[pair])
        self.clock, self.latency = clock, latency_ms
        self.rng = random.Random(seed)
        self.rest_fake = l3.FakeExchanges(pair, clock)
        self.depth_url = rest_urls(pair)[("mexc", "depth")]
        self.start_ms = start_ms
        self.queue, self.order = [], 0
        self.open_ = {"mexc": False, "kraken": False}
        self.sub = {"mexc": False, "kraken": False}
        self.version = 1_000_000
        self.mid = self.p["mid"]
        self.books = {"mexc": ({}, {}), "kraken": ({}, {})}
        self.next_tick = {"mexc": None, "kraken": None}
        self.kraken_quiet_since = None
        self.offset_bps = self.p["kraken_offset_bps"]
        self._fired = set()
        self._rebuild("mexc")
        self._rebuild("kraken")

    # -- book model
    def _levels(self, venue):
        tick = Decimal(self.p[f"{venue}_tick"])
        mid = Decimal(repr(self.mid * (1 + (self.offset_bps / 1e4 if venue == "kraken" else 0))))
        center = (mid / tick).to_integral_value()
        n = 12
        bids = {}
        asks = {}
        for k in range(n):
            q = Decimal(self.rng.randint(1, 400_000)).scaleb(-8)
            bids[(center - 1 - k) * tick] = q
            q = Decimal(self.rng.randint(1, 400_000)).scaleb(-8)
            asks[(center + 1 + k) * tick] = q
        return bids, asks

    def _rebuild(self, venue):
        self.books[venue] = self._levels(venue)

    def _text(self, venue, d, qty=False):
        if qty:
            return format(d.quantize(Decimal("0.00000001")), "f")
        tick = Decimal(self.p[f"{venue}_tick"])
        return format(d.quantize(tick), "f")

    def _step(self, venue):
        old_b, old_a = self.books[venue]
        self.mid *= 1 + self.rng.choice((-1, 0, 0, 1)) * 0.00002
        new_b, new_a = self._levels(venue)
        self.books[venue] = (new_b, new_a)
        diff_b = [(p, new_b.get(p, Decimal(0))) for p in sorted(set(old_b) | set(new_b), reverse=True)
                  if old_b.get(p) != new_b.get(p)]
        diff_a = [(p, new_a.get(p, Decimal(0))) for p in sorted(set(old_a) | set(new_a))
                  if old_a.get(p) != new_a.get(p)]
        return diff_b, diff_a

    # -- faults
    def _fault(self, name, now):
        for f in self.p["faults"]:
            if f[0] != name or self.start_ms is None:
                continue
            base = self.start_ms + f[1] * PERIOD_MS
            if len(f) == 3 and now >= base + f[2] and (f, ) not in self._fired:
                self._fired.add((f, ))
                return f
            if len(f) >= 4 and base + f[2] <= now < base + f[3]:
                return f
        return None

    # -- session interface
    def rest(self, url):
        self.clock.now += 120
        if url == self.depth_url:
            bids, asks = self.books["mexc"]
            body = {"lastUpdateId": self.version,
                    "bids": [[self._text("mexc", p), self._text("mexc", q, True)]
                             for p, q in sorted(bids.items(), reverse=True)],
                    "asks": [[self._text("mexc", p), self._text("mexc", q, True)]
                             for p, q in sorted(asks.items())]}
            return 200, {"Content-Type": "application/json"}, json.dumps(body).encode(), None
        self.clock.now -= 120
        return self.rest_fake(url)

    def open(self, venue, timeout_s=None):
        self.clock.now += 50
        self.open_[venue] = True
        self.sub[venue] = False

    def close(self, venue, timeout_s=None):
        self.open_[venue] = False
        self.sub[venue] = False
        self.next_tick[venue] = None
        self.queue = [q for q in self.queue if q[2] != venue]
        heapq.heapify(self.queue)

    def _push(self, at, venue, kind, opcode, payload):
        self.order += 1
        heapq.heappush(self.queue, (at, self.order, venue, kind, opcode, payload))

    def send_text(self, venue, text, timeout_s=None):
        doc = json.loads(text)
        at = self.clock.now + self.latency
        if venue == "mexc":
            if doc.get("method") == "SUBSCRIPTION":
                self.sub["mexc"] = True
                self._push(at, "mexc", "ws_message", wire.OP_TEXT,
                           json.dumps({"id": 0, "code": 0, "msg": doc["params"][0]}).encode())
                self.next_tick["mexc"] = at + 10
            elif doc.get("method") == "PING":
                self._push(at, "mexc", "ws_message", wire.OP_TEXT,
                           json.dumps({"id": 0, "code": 0, "msg": "PONG"}).encode())
            return
        method = doc.get("method")
        if method == "ping":
            if not self._fault("kraken_silence", at):
                self._push(at, "kraken", "ws_message", wire.OP_TEXT, json.dumps(
                    {"method": "pong", "req_id": doc["req_id"], "time_in": "x", "time_out": "x"}).encode())
        elif method == "unsubscribe":
            self.sub["kraken"] = False
            self.next_tick["kraken"] = None
            self._push(at, "kraken", "ws_message", wire.OP_TEXT, json.dumps(
                {"method": "unsubscribe", "success": True, "result": doc["params"]}).encode())
        elif method == "subscribe":
            self.sub["kraken"] = True
            self._push(at, "kraken", "ws_message", wire.OP_TEXT, json.dumps(
                {"method": "subscribe", "success": True, "result": doc["params"]}).encode())
            self._push(at + 1, "kraken", "ws_message", wire.OP_TEXT, self._kraken_msg("snapshot"))
            self.next_tick["kraken"] = at + self.p["kraken_every_ms"]

    def _kraken_msg(self, kind, diff=None, corrupt=False):
        bids, asks = self.books["kraken"]
        if kind == "snapshot":
            sb = sorted(bids.items(), reverse=True)[:KRAKEN_DEPTH]
            sa = sorted(asks.items())[:KRAKEN_DEPTH]
        else:
            sb, sa = diff
        def lv(items):
            return "[" + ",".join(
                f'{{"price":{self._text("kraken", p)},"qty":{self._text("kraken", q, True)}}}'
                for p, q in items) + "]"
        top_a = [(self._text("kraken", p), self._text("kraken", q, True)) for p, q in sorted(asks.items())[:10]]
        top_b = [(self._text("kraken", p), self._text("kraken", q, True))
                 for p, q in sorted(bids.items(), reverse=True)[:10]]
        ck = bk.kraken_checksum(top_a, top_b) ^ (1 if corrupt else 0)
        symbol = self.c["kraken_ws_symbol"]
        return (f'{{"channel":"book","type":"{kind}","data":[{{"symbol":"{symbol}","bids":{lv(sb)},'
                f'"asks":{lv(sa)},"checksum":{ck},"timestamp":"2026-11-20T00:00:00.000000Z"}}]}}').encode()

    def _emit_tick(self, venue, at):
        if venue == "mexc":
            if self._fault("mexc_disconnect", at):
                self.close("mexc")
                self._push(at, "mexc", "ws_close", wire.OP_CLOSE, wire.close_payload(1001))
                return
            diff_b, diff_a = self._step("mexc")
            k = self.rng.randint(1, 3)
            frm, to = self.version + 1, self.version + k
            self.version = to
            self.next_tick["mexc"] = at + self.p["mexc_every_ms"]
            if self._fault("mexc_gap", at):
                return  # diff lost in transit: the client must see a version gap
            body = wire.encode_aggre_depths(
                [(self._text("mexc", p), self._text("mexc", q, True)) for p, q in diff_a],
                [(self._text("mexc", p), self._text("mexc", q, True)) for p, q in diff_b],
                frm, to, event_type=mexc_channel(self.c["mexc_ws_symbol"]).rsplit("@", 1)[0])
            push = wire.encode_mexc_push(mexc_channel(self.c["mexc_ws_symbol"]), self.c["mexc_ws_symbol"],
                                         body, send_time=at - 5, create_time=at - 8)
            self._push(at, "mexc", "ws_message", wire.OP_BINARY, push)
            return
        f = self._fault("kraken_offset_bps", at)
        self.offset_bps = f[4] if f else self.p["kraken_offset_bps"]
        if self._fault("kraken_silence", at):
            self.next_tick["kraken"] = at + self.p["kraken_every_ms"]
            return
        diff_b, diff_a = self._step("kraken")
        bids, asks = self.books["kraken"]
        top_b = set(sorted(bids, reverse=True)[:KRAKEN_DEPTH])
        top_a = set(sorted(asks)[:KRAKEN_DEPTH])
        # Only levels inside the subscribed depth are sent (removals included).
        diff_b = [(p, q) for p, q in diff_b if p in top_b or q == 0]
        diff_a = [(p, q) for p, q in diff_a if p in top_a or q == 0]
        corrupt = bool(self._fault("kraken_bad_checksum", at))
        self._push(at, "kraken", "ws_message", wire.OP_TEXT,
                   self._kraken_msg("update", (diff_b, diff_a), corrupt=corrupt))
        self.next_tick["kraken"] = at + self.p["kraken_every_ms"]

    def _heartbeats(self, until):
        # Kraken: heartbeat about once per second without other channel updates.
        if not self.sub["kraken"]:
            return
        last = self.kraken_quiet_since or self.clock.now
        t = last + 1000
        while t <= until:
            if not self._fault("kraken_silence", t):
                self._push(t, "kraken", "ws_message", wire.OP_TEXT, b'{"channel":"heartbeat"}')
            t += 1000
        self.kraken_quiet_since = t - 1000

    def poll(self, until_wall_ms):
        while True:
            cands = [(t, v) for v, t in self.next_tick.items() if t is not None and self.sub[v]]
            nxt = min(cands) if cands else None
            if nxt is not None and nxt[0] <= until_wall_ms and (not self.queue or nxt[0] < self.queue[0][0]):
                self.next_tick[nxt[1]] = None
                self._emit_tick(nxt[1], nxt[0])
                continue
            break
        if self.p["kraken_every_ms"] > 1000:
            self._heartbeats(until_wall_ms)
        if self.queue and self.queue[0][0] <= until_wall_ms:
            at, _, venue, kind, opcode, payload = heapq.heappop(self.queue)
            self.clock.now = max(self.clock.now, at)
            if not self.open_.get(venue) and kind != "ws_close":
                return []
            return [(venue, kind, opcode, payload)]
        self.clock.now = max(self.clock.now, until_wall_ms)
        return []


# ---------------------------------------------------------------- CLI

DRY_RUN_START_MS = 1_795_128_000_000
CONFIRM_TOKEN = "BBO-PILOT"


PROBE_CONFIRM_TOKEN = "BBO-PROBE"


def dry_run(pair, out, *, caps=None, profile=None, session_cls=None, watchdog_s=None):
    clock = l3.FakeClock(DRY_RUN_START_MS - 120_000)
    start = DRY_RUN_START_MS
    session = (session_cls or FakeVenues)(pair, clock, start_ms=start, profile=profile)
    pilot = BboPilot(pair, out, session, clock, evidence_kind="SYNTHETIC", caps=caps,
                     watchdog_s=watchdog_s)
    return pilot, pilot.run(start_ms=start)


def dry_run_probe(out, *, profile=None, session_cls=None, caps=None, watchdog_s=None):
    clock = l3.FakeClock(DRY_RUN_START_MS - 120_000)
    prof = copy.deepcopy(profile or SIM_PROFILES["BTC"])
    if profile is None:
        prof["faults"] = []
    session = (session_cls or FakeVenues)("BTC", clock, start_ms=None, profile=prof)
    pilot = BboPilot("BTC", out, session, clock, evidence_kind="SYNTHETIC", mode="probe",
                     caps=caps, watchdog_s=watchdog_s)
    return pilot, pilot.run()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbo_pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "dry-run", "probe", "dry-run-probe"):
        s = sub.add_parser(name)
        if name in ("run", "dry-run"):
            s.add_argument("--pair", choices=sorted(BBO_PAIRS), required=True)
        s.add_argument("--out", required=True)
        if name in ("run", "probe"):
            s.add_argument("--radar-collector", required=True)
            s.add_argument("--radar-collector-sha256", required=True)
            s.add_argument("--confirm-public-collection", required=True)
    r = sub.add_parser("replay")
    r.add_argument("out")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "replay":
            result = replay(a.out)
            print(json.dumps(result.get("totals") or {"verdict": result["verdict"],
                                                       "missing_required": result["missing_required"]},
                             indent=2, sort_keys=True))
            return 0
        if a.cmd == "dry-run":
            pilot, code = dry_run(a.pair, a.out)
        elif a.cmd == "dry-run-probe":
            pilot, code = dry_run_probe(a.out)
        else:
            token = CONFIRM_TOKEN if a.cmd == "run" else PROBE_CONFIRM_TOKEN
            if a.confirm_public_collection != token:
                raise l3.Refused(f"public {a.cmd} requires --confirm-public-collection {token}")
            pair = a.pair if a.cmd == "run" else PROBE["pair"]
            clock = l3.RealClock()
            pilot = BboPilot(pair, a.out, RealSession(pair, clock), clock,
                             mode="collect" if a.cmd == "run" else "probe",
                             radar_check=bbo_margin_check(a.radar_collector, a.radar_collector_sha256))
            code = pilot.run()
        result = replay(a.out)
        print(json.dumps({"exit_code": code, "stop_code": pilot.stop_code, "frames": pilot.frames,
                          "result": result.get("totals") or {
                              "verdict": result["verdict"], "missing_required": result["missing_required"]}},
                         indent=2, sort_keys=True))
        return code
    except l3.Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
