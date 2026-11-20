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

Exit codes: 0 completed, 2 stopped by a stop condition, 3 preflight refused,
4 usage / evidence error.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import heapq
import json
import os
import platform
import random
import select
import socket
import ssl
import sys
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
CONNECT_TIMEOUT_S = 6.0
REST_BUDGET = {("mexc", "depth"): 1 + MAX_RESYNCS, ("mexc", "exchangeInfo"): 1, ("mexc", "time"): 2,
               ("kraken", "assetPairs"): 1, ("kraken", "assets"): 1, ("kraken", "time"): 2}
CAPS = {"max_frames": 200_000, "max_frame_bytes": wire.MAX_MESSAGE_BYTES,
        "max_storage_bytes": 300 * 1024 * 1024}
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

    def __init__(self, out, clock):
        self.out = Path(out)
        if self.out.exists() and any(self.out.iterdir()):
            raise l3.Refused("evidence directory must be new or empty")
        self.out.mkdir(parents=True, exist_ok=True)
        os.chmod(self.out, 0o750)
        # Long-lived append handles, closed by seal(); a context manager cannot span the run.
        self.log = open(self.out / "events.jsonl", "a", encoding="utf-8")  # noqa: SIM115
        self.raw = open(self.out / "frames.bin", "ab")  # noqa: SIM115
        self.offset = 0
        self.seq = 0
        self.clock = clock
        self.anchor_wall = clock.wall_ms()
        self.anchor_mono = clock.mono_ms()

    def t_ms(self, mono):
        return self.anchor_wall + (mono - self.anchor_mono)

    def record(self, venue, kind, payload=b"", **extra):
        wall, mono = self.clock.wall_ms(), self.clock.mono_ms()
        self.seq += 1
        self.raw.write(payload)
        self.raw.flush()
        entry = {"seq": self.seq, "venue": venue, "kind": kind, "recv_wall_ms": wall,
                 "recv_mono_ms": mono, "t_ms": self.t_ms(mono), "offset": self.offset,
                 "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), **extra}
        self.offset += len(payload)
        self.log.write(json.dumps(entry, sort_keys=True) + "\n")
        self.log.flush()
        return entry

    def sync(self):
        for fh in (self.raw, self.log):
            fh.flush()
            os.fsync(fh.fileno())

    def manifest(self, data):
        tmp = self.out / "manifest.json.tmp"
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.out / "manifest.json")

    def seal(self):
        self.sync()
        self.log.close()
        self.raw.close()
        return {"events": self.seq,
                "events_sha256": hashlib.sha256((self.out / "events.jsonl").read_bytes()).hexdigest(),
                "frames_sha256": hashlib.sha256((self.out / "frames.bin").read_bytes()).hexdigest(),
                "frames_bytes": self.offset}


# ---------------------------------------------------------------- runner

class BboPilot:
    # Same identity and clock preflight as L3 (reused, not copied).
    preflight = l3.Pilot.preflight
    _offset = l3.Pilot._offset

    def __init__(self, pair, out, session, clock, *, evidence_kind="OBSERVATION",
                 radar_check=None, caps=None):
        self.pair, self.cfg = pair, cfg(pair)
        self.urls = rest_urls(pair)
        self.session, self.clock = session, clock
        self.kind = evidence_kind
        self.radar_check = radar_check
        self.caps = {**CAPS, **(caps or {})}
        self.evidence = Evidence(out, clock)
        self.engine = new_engine(self.cfg)
        self.rest_used = {k: 0 for k in REST_BUDGET}
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
        if self.rest_used[key] >= REST_BUDGET[key]:
            raise l3.Stop(f"BUDGET_REST_{venue.upper()}_{endpoint.upper()}")
        self._check_duration()
        self.rest_used[key] += 1
        sent = self.clock.wall_ms()
        status, headers, body, error = self.session.rest(self.urls[key])
        entry = self.evidence.record(venue, "rest_depth" if endpoint == "depth" else "rest", body,
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

    def _check_duration(self):
        if self.t0 is not None and self.clock.mono_ms() - self.t0 >= self.cfg["max_seconds"] * 1000:
            raise l3.Stop("BUDGET_DURATION_EXHAUSTED")

    # -- WebSocket side
    def _open(self, venue, purpose):
        try:
            self.session.open(venue)
        except (wire.WireError, OSError) as exc:
            code = exc.code if isinstance(exc, wire.WireError) else type(exc).__name__.upper()
            self._feed(self.evidence.record(venue, "ws_error", b"", detail=code, purpose=purpose))
            raise l3.Stop(f"WS_REFUSED_{venue.upper()}")
        self._feed(self.evidence.record(venue, "ws_open", b"", purpose=purpose))
        self._send(venue, subscribe_msgs(self.cfg)[venue], "subscribe")

    def _send(self, venue, text, purpose):
        self.session.send_text(venue, text)
        self.evidence.record(venue, "sent", text.encode(), purpose=purpose)

    def _feed(self, entry, payload=b""):
        ev = {**entry, "payload": payload}
        for venue, action in self.engine.apply(ev):
            self._act(venue, action)

    def _act(self, venue, action):
        if action == "NEED_SNAPSHOT":
            if self.snapshots >= 1:
                self.resyncs["mexc"] += 1
                if self.resyncs["mexc"] > MAX_RESYNCS:
                    raise l3.Stop("MEXC_RESYNC_BUDGET_EXHAUSTED")
            self.snapshots += 1
            entry, body, _ = self.get("mexc", "depth", purpose="snapshot")
            self._feed(entry, body)
        elif action == "NEED_RESUBSCRIBE":
            self.resyncs["kraken"] += 1
            if self.resyncs["kraken"] > MAX_RESYNCS:
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
        for venue, kind, opcode, payload in self.session.poll(until):
            if kind == "ws_message":
                self.frames += 1
                if self.frames > self.caps["max_frames"]:
                    raise l3.Stop("BUDGET_FRAMES_EXHAUSTED")
                if len(payload) > self.caps["max_frame_bytes"]:
                    raise l3.Stop("FRAME_TOO_LARGE")
            entry = self.evidence.record(venue, kind, payload, opcode=opcode)
            if self.evidence.offset > self.caps["max_storage_bytes"]:
                raise l3.Stop("BUDGET_STORAGE_EXHAUSTED")
            self._provider_error(venue, kind, opcode, payload)
            self._feed(entry, payload)
            if kind in ("ws_close", "ws_error"):
                self.reconnects[venue] += 1
                if self.reconnects[venue] > MAX_RECONNECTS:
                    self._feed(self.evidence.record(venue, "gave_up", b""))
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
        now = self.clock.wall_ms()
        if start_ms is None:
            start_ms = -(-(now + PREFLIGHT_LEAD_MS + 15_000) // PERIOD_MS) * PERIOD_MS
        n = self.cfg["windows"] * POINTS
        end_ms = start_ms + (n - 1) * STEP_MS + 1_000
        manifest = self._manifest(start_ms, end_ms, "WAITING")
        self.evidence.manifest(manifest)
        self.clock.sleep_until_wall(start_ms - PREFLIGHT_LEAD_MS)
        manifest["status"] = "RUNNING"
        self.evidence.manifest(manifest)
        exit_code = 0
        self.t0 = self.clock.mono_ms()
        try:
            planned = (end_ms - (start_ms - PREFLIGHT_LEAD_MS) + 5_000) / 1000
            if planned > self.cfg["max_seconds"]:
                raise l3.Stop("PREFLIGHT_SLOT_DOES_NOT_FIT")
            manifest["preflight"] = self.preflight()
            self.clock.sleep_until_wall(start_ms - WARMUP_MS)
            for venue in bk.VENUES:
                self._open(venue, "initial")
            next_ping = self.clock.wall_ms()
            while self.clock.wall_ms() < end_ms:
                self._check_duration()
                if self.clock.wall_ms() >= next_ping:
                    self._ping()
                    next_ping += PING_EVERY_MS
                self._receive(min(next_ping, end_ms))
                self.evidence.sync()
            for venue in bk.VENUES:
                self.session.close(venue)
                self.evidence.record(venue, "closed_by_pilot", b"")
            manifest["clock_end"] = {
                "mexc_offset_ms": self._offset(self.get("mexc", "time", purpose="clock_end")[0],
                                               self._last_body(), "mexc"),
                "kraken_offset_ms": self._offset(self.get("kraken", "time", purpose="clock_end")[0],
                                                 self._last_body(), "kraken"),
            }
            manifest["status"] = "COMPLETED"
        except l3.Stop as stop:
            self.stop_code = stop.code
            manifest["status"] = "STOPPED"
            exit_code = 3 if stop.code.startswith("PREFLIGHT") else 2
            self.evidence.record("pilot", "stop", stop.code.encode())
        finally:
            for venue in bk.VENUES:
                try:
                    self.session.close(venue)
                except OSError as exc:  # best effort close, never masks the stop
                    self.evidence.record(venue, "close_error", type(exc).__name__.encode())
            manifest.update(stop_code=self.stop_code, ended_wall_ms=self.clock.wall_ms(),
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
            "window_start_ms": start_ms, "windows": c["windows"], "end_ms": end_ms,
            "clock_anchor": {"wall_ms": self.evidence.anchor_wall, "mono_ms": self.evidence.anchor_mono},
            "grid": {"step_ms": STEP_MS, "points_per_window": POINTS, "warmup_ms": WARMUP_MS,
                     "preflight_lead_ms": PREFLIGHT_LEAD_MS, "ping_every_ms": PING_EVERY_MS},
            "budget": {"max_seconds": c["max_seconds"], "rest": {f"{v}.{e}": n for (v, e), n in REST_BUDGET.items()},
                       "max_reconnects_per_venue": MAX_RECONNECTS, "max_resyncs_per_source": MAX_RESYNCS,
                       **self.caps},
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


def replay(out):
    """Offline: rebuild books from the frames, instant by instant, and summarise."""
    out = Path(out)
    manifest, events = load(out)
    c = cfg(manifest["pair"])
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

    def __init__(self, url):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "wss" or url not in (MEXC_WS, KRAKEN_WS):
            raise l3.Refused("WebSocket URL outside the allow-list")
        raw = socket.create_connection((parts.hostname, 443), timeout=CONNECT_TIMEOUT_S)
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(raw, server_hostname=parts.hostname)
        key = wire.new_key()
        self.sock.sendall(wire.handshake_request(parts.hostname, parts.path or "/", key))
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk or len(head) > 16_384:
                raise wire.WireError("HANDSHAKE_INCOMPLETE")
            head += chunk
        _, rest = wire.parse_handshake_response(head, key)
        self.sock.setblocking(False)
        self.parser = wire.FrameParser()
        self.pending = self.parser.feed(rest)

    def send_text(self, text):
        self.sock.setblocking(True)
        try:
            self.sock.sendall(wire.encode_client_frame(wire.OP_TEXT, text.encode()))
        finally:
            self.sock.setblocking(False)

    def send_control(self, opcode, payload=b""):
        self.sock.setblocking(True)
        try:
            self.sock.sendall(wire.encode_client_frame(opcode, payload))
        finally:
            self.sock.setblocking(False)

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

    def close(self):
        try:
            self.send_control(wire.OP_CLOSE, wire.close_payload(1000))
        except OSError:
            pass
        self.sock.close()


class RealSession:
    def __init__(self, pair, clock):
        self.urls = {"mexc": MEXC_WS, "kraken": KRAKEN_WS}
        self.rest_transport = l3.UrllibTransport(rest_urls(pair).values())
        self.conns = {}
        self.clock = clock

    def rest(self, url):
        return self.rest_transport(url)

    def open(self, venue):
        self.conns[venue] = WsConnection(self.urls[venue])

    def send_text(self, venue, text):
        self.conns[venue].send_text(text)

    def close(self, venue):
        conn = self.conns.pop(venue, None)
        if conn is not None:
            conn.close()

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
                    conn.send_control(wire.OP_PONG, payload)
                    events.append((venue, "ws_control", opcode, payload))
                elif opcode == wire.OP_PONG:
                    events.append((venue, "ws_control", opcode, payload))
                elif opcode == wire.OP_CLOSE:
                    events.append((venue, "ws_close", opcode, payload))
                    closed = True
                else:
                    events.append((venue, "ws_message", opcode, payload))
            if closed:
                if not events or events[-1][1] != "ws_close":
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

    def open(self, venue):
        self.clock.now += 50
        self.open_[venue] = True
        self.sub[venue] = False

    def close(self, venue):
        self.open_[venue] = False
        self.sub[venue] = False
        self.next_tick[venue] = None
        self.queue = [q for q in self.queue if q[2] != venue]
        heapq.heapify(self.queue)

    def _push(self, at, venue, kind, opcode, payload):
        self.order += 1
        heapq.heappush(self.queue, (at, self.order, venue, kind, opcode, payload))

    def send_text(self, venue, text):
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


def dry_run(pair, out, *, caps=None, profile=None):
    clock = l3.FakeClock(DRY_RUN_START_MS - 120_000)
    start = DRY_RUN_START_MS
    session = FakeVenues(pair, clock, start_ms=start, profile=profile)
    pilot = BboPilot(pair, out, session, clock, evidence_kind="SYNTHETIC", caps=caps)
    return pilot, pilot.run(start_ms=start)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbo_pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "dry-run"):
        s = sub.add_parser(name)
        s.add_argument("--pair", choices=sorted(BBO_PAIRS), required=True)
        s.add_argument("--out", required=True)
        if name == "run":
            s.add_argument("--radar-collector", required=True)
            s.add_argument("--radar-collector-sha256", required=True)
            s.add_argument("--confirm-public-collection", required=True)
    r = sub.add_parser("replay")
    r.add_argument("out")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "replay":
            print(json.dumps(replay(a.out)["totals"], indent=2, sort_keys=True))
            return 0
        if a.cmd == "dry-run":
            pilot, code = dry_run(a.pair, a.out)
        else:
            if a.confirm_public_collection != CONFIRM_TOKEN:
                raise l3.Refused("runtime collection requires --confirm-public-collection BBO-PILOT")
            clock = l3.RealClock()
            pilot = BboPilot(a.pair, a.out, RealSession(a.pair, clock), clock,
                             radar_check=bbo_margin_check(a.radar_collector, a.radar_collector_sha256))
            code = pilot.run()
        summary = replay(a.out)
        print(json.dumps({"exit_code": code, "stop_code": pilot.stop_code, "frames": pilot.frames,
                          "totals": summary["totals"]}, indent=2, sort_keys=True))
        return code
    except l3.Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
