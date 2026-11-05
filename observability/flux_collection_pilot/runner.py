"""Bounded collection state machine (synchronous, injected clock, injected transport).

Protocol: at most two connections; the first, if healthy, is cut on purpose after
``planned_cut_ns``; one reconnect at most; global caps on duration, messages and
bytes; first cap, access refusal, heartbeat silence, local loss, size/format
anomaly or suspicious L2 sequence STOPS the whole collection (no reconnect after a
safety stop). Time comes from ``clock.sample()`` only (monotonic for every delay).

Tie rules (stated, tested): a frame that arrives exactly at a deadline is read
before the deadline is judged (silence, duration and cut are checked at the top of
each loop with ``>=`` on the elapsed value).
"""

from dataclasses import dataclass, field
import hashlib

from . import protocol as P
from .memory import CHECK_EVERY
from .messages import MessageRefusal, parse_message
from .sequence import GAP, REPEAT, REWIND, SequenceTracker
from .store import DiskBudgetExceeded, CampaignStore, StoreError, WriteFailed, raw_record
from .transport import (AccessRefused, ConnectFailed, ConnectionClosed, FrameTooLarge, LocalLoss,
                        TransportError, subscribe_messages)

LIMIT_STATUS = {
    "connections": "ENFORCED_IN_CODE: ConnectionBudget refuses a third connection",
    "planned_cut": "ENFORCED_IN_CODE: monotonic clock, only after a healthy first session",
    "duration": "ENFORCED_IN_CODE: monotonic, checked before every recv; recv timeout bounded by the remaining time (the live transport must honour it)",
    "messages": "ENFORCED_IN_CODE: stops at the cap, message n+1 is never read",
    "disk_bytes": "ENFORCED_IN_CODE: exact byte accounting with a reserve; no kernel quota is set by the package",
    "message_size": "ENFORCED_IN_CODE after receipt; the live transport must also bound BEFORE accumulating (max_size)",
    "memory": "PARTIAL: RSS monitor in the runner + RLIMIT_DATA by the launcher; cgroup MemoryMax is NOT configured by the package",
    "silence": "ENFORCED_IN_CODE: monotonic since the last heartbeat (or session open)",
}


class ConnectionCapExceeded(RuntimeError):
    pass


class ConnectionBudget:
    def __init__(self, maximum):
        self.maximum, self.used = maximum, 0

    def acquire(self):
        if self.used >= self.maximum:
            raise ConnectionCapExceeded("CONNECTION_CAP")
        self.used += 1
        return self.used


@dataclass(frozen=True)
class CampaignConfig:
    campaign_id: str
    package_digest: str
    caps: P.Caps = P.PROTOCOL_CAPS
    sequence_policy: str = P.DEFAULT_SEQUENCE_POLICY
    evidence_kind: str = "SYNTHETIC"  # "LIVE" only through live_gate
    manifest_sha256: object = None
    clock_checks: object = None  # operator observer-clock checks (before/after), recorded as supplied


@dataclass
class CampaignResult:
    end_reason: str
    complete: bool
    sessions: list
    messages: int
    bytes_written: int
    path: str
    trigger: object = None
    final_receipt_written: bool = False
    problems: list = field(default_factory=list)


class _Stop(Exception):
    def __init__(self, reason, *, idx=None, raw=None, stored=False, detail=None, oversize=None):
        super().__init__(reason)
        self.reason, self.idx, self.raw, self.stored = reason, idx, raw, stored
        self.detail, self.oversize = detail, oversize


class CampaignRunner:
    def __init__(self, config, transport_factory, clock, store, memory_guard=None):
        if not isinstance(store, CampaignStore):
            raise TypeError("STORE_REQUIRED")
        if config.evidence_kind == "LIVE" and memory_guard is None:
            raise ValueError("MEMORY_GUARD_REQUIRED_FOR_LIVE")
        if not config.caps.within(P.PROTOCOL_CAPS):
            raise ValueError("CAPS_ABOVE_PROTOCOL")
        self.cfg, self.factory, self.clock, self.store, self.mem = config, transport_factory, clock, store, memory_guard
        self.budget = ConnectionBudget(config.caps.max_connections)
        self.msgs = 0
        self.sessions = []
        self.trigger = None
        self.problems = []

    # ------------------------------------------------------------------
    def run(self):
        c, caps = self.cfg, self.cfg.caps
        self.t0 = self.clock.sample()
        reason = None
        try:
            self.store.write_atomic("intent.json", {
                "pilot": "coinbase-btc-usd", "provider": P.PROVIDER, "host": P.HOST, "product": P.PRODUCT,
                "subscriptions": list(P.SUBSCRIBE_CHANNELS), "caps": caps.document(),
                "sequence_policy": c.sequence_policy, "evidence_kind": c.evidence_kind,
                "package_digest": c.package_digest, "manifest_sha256": c.manifest_sha256,
                "started_utc_ns": self.t0.utc_ns, "started_mono_ns": self.t0.monotonic_ns,
            })
            n = 0
            while True:
                n += 1
                try:
                    self.budget.acquire()
                except ConnectionCapExceeded:
                    reason = P.CONNECTION_CAP
                    break
                reason = self._session(n)
                if reason != P.PLANNED_CUT:
                    break
        except StoreError as e:
            self.problems.append("STORE:" + str(e))
            reason = P.WRITE_FAILED
        except Exception as e:  # a bug must end the run as INCOMPLETE, never as a silent success
            self.problems.append("INTERNAL:" + type(e).__name__)
            reason = P.INTERNAL_ERROR
        return self._finish(reason)

    # ------------------------------------------------------------------
    def _session(self, n):
        c = self.cfg
        sid = "S%02d" % n
        info = {"session": sid, "connection_ordinal": n, "messages": 0, "heartbeats": 0, "snapshots": 0,
                "channels": {}, "end_reason": None}
        self.sessions.append(info)
        self.store.open_raw(sid)
        transport = None
        reason = None
        tracker = SequenceTracker(c.sequence_policy)  # fresh per session: nothing carried across sessions
        try:
            if self.mem:
                self._memory()
            transport = self.factory()
            transport.open(subscribe_messages(P.PRODUCT, P.SUBSCRIBE_CHANNELS))
            s0 = self.clock.sample()
            info.update(opened_utc_ns=s0.utc_ns, opened_mono_ns=s0.monotonic_ns,
                        subscribe_sha256=hashlib.sha256(P.canonical(subscribe_messages(P.PRODUCT, P.SUBSCRIBE_CHANNELS))).hexdigest())
            reason = self._loop(n, info, transport, tracker, s0)
        except _Stop as s:
            reason = self._record_stop(s, sid, info)
        except AccessRefused as e:
            reason = self._record_stop(_Stop(P.ACCESS_REFUSED, detail=str(e)), sid, info)
        except ConnectFailed as e:
            reason = self._record_stop(_Stop(P.CONNECT_FAILED, detail=str(e)), sid, info)
        except TransportError as e:
            reason = self._record_stop(_Stop(P.CONNECT_FAILED, detail=type(e).__name__), sid, info)
        finally:
            if transport is not None:
                try:
                    transport.close()
                except Exception:
                    self.problems.append("TRANSPORT_CLOSE_FAILED")
            end = self.clock.sample()
            info.update(end_reason=reason, ended_utc_ns=end.utc_ns, ended_mono_ns=end.monotonic_ns,
                        sequence=tracker.report(), raw=self.store.raw_state(sid))
            try:
                self.store.close_raw(sid)
            except OSError as e:
                self.problems.append("RAW_CLOSE_FAILED:" + str(e))
        return reason

    def _memory(self):
        ok, why, value = self.mem.check()
        if not ok:
            raise _Stop(P.MEMORY_UNVERIFIABLE if why == "MEMORY_UNVERIFIABLE" else P.MEMORY_CAP,
                        detail={"rss_bytes": value, "limit": self.mem.limit})

    def _loop(self, n, info, transport, tracker, s0):
        caps = self.cfg.caps
        sid = info["session"]
        last_hb = s0.monotonic_ns
        last_mono = s0.monotonic_ns
        idx = 0
        while True:
            now = self.clock.sample()
            if now.monotonic_ns < last_mono:
                raise _Stop(P.CLOCK_ANOMALY, detail={"previous": last_mono, "now": now.monotonic_ns})
            last_mono = now.monotonic_ns
            elapsed = now.monotonic_ns - self.t0.monotonic_ns
            since_hb = now.monotonic_ns - last_hb
            in_session = now.monotonic_ns - s0.monotonic_ns
            if since_hb >= caps.silence_ns:
                raise _Stop(P.SILENCE_HEARTBEAT, detail={"silence_ns": since_hb})
            if elapsed >= caps.max_duration_ns:
                return P.DURATION_CAP
            timeout = min(caps.max_duration_ns - elapsed, caps.silence_ns - since_hb)
            if n == 1:
                if in_session >= caps.planned_cut_ns:
                    if info["heartbeats"] > 0 and info["snapshots"] > 0:
                        return P.PLANNED_CUT
                    raise _Stop(P.SESSION_UNHEALTHY_AT_CUT,
                                detail={"heartbeats": info["heartbeats"], "snapshots": info["snapshots"]})
                timeout = min(timeout, caps.planned_cut_ns - in_session)
            try:
                frame = transport.recv(timeout)
            except FrameTooLarge as e:
                raise _Stop(P.MESSAGE_TOO_LARGE, oversize=e.size, detail={"bytes": e.size}) from None
            except LocalLoss as e:
                raise _Stop(P.LOCAL_LOSS, detail=str(e)) from None
            except AccessRefused as e:
                raise _Stop(P.ACCESS_REFUSED, detail=str(e)) from None
            except ConnectionClosed as e:
                raise _Stop(P.CONNECTION_LOST, detail=str(e)) from None
            if frame is None:
                continue
            rcv = self.clock.sample()
            raw = bytes(frame.raw)
            if len(raw) > caps.max_message_bytes:
                raise _Stop(P.MESSAGE_TOO_LARGE, raw=raw[:4096], oversize=len(raw), detail={"bytes": len(raw)})
            rec = raw_record(sid, idx, self.msgs, rcv, raw)
            try:
                self.store.append_raw(sid, rec)
            except DiskBudgetExceeded:
                raise _Stop(P.DISK_CAP, idx=idx, raw=raw, detail={"used": self.store.used}) from None
            except WriteFailed as e:
                raise _Stop(P.WRITE_FAILED, idx=idx, raw=raw, detail=str(e)) from None
            self.msgs += 1
            info["messages"] += 1
            this = idx
            idx += 1
            try:
                msg = parse_message(raw)
            except MessageRefusal as e:
                code = P.UNEXPECTED_PRODUCT if str(e) == "UNEXPECTED_PRODUCT" else P.MALFORMED_MESSAGE
                raise _Stop(code, idx=this, stored=True, detail=str(e)) from None
            if msg.kind == "error":
                raise _Stop(P.PROVIDER_ERROR, idx=this, stored=True, detail=(msg.error_text or "")[:200])
            info["channels"][msg.channel] = info["channels"].get(msg.channel, 0) + 1
            verdict = tracker.observe(this, msg.channel, msg.seq, msg.products)
            if verdict["kind"] in (GAP, REPEAT, REWIND):
                raise _Stop(P.L2_SEQUENCE_SUSPECT, idx=this, stored=True, detail=verdict)
            if msg.channel == P.HEARTBEAT_CHANNEL:
                info["heartbeats"] += 1
                last_hb = rcv.monotonic_ns
            info["snapshots"] += msg.snapshots
            if self.msgs >= caps.max_messages:
                raise _Stop(P.MESSAGE_CAP, idx=this, stored=True)
            if self.mem and self.msgs % CHECK_EVERY == 0:
                self._memory()
            if self.msgs % 1000 == 0:
                self.store.sync_raw(sid)

    # ------------------------------------------------------------------
    def _record_stop(self, s, sid, info):
        trig = {"reason": s.reason, "session": sid, "idx": s.idx, "campaign_message_count": self.msgs,
                "detail": s.detail, "raw_in_session_file": bool(s.stored)}
        if s.raw is not None and not s.stored:
            import base64
            trig["raw_b64"] = base64.b64encode(s.raw).decode()
            trig["raw_sha256_of_stored_bytes"] = hashlib.sha256(s.raw).hexdigest()
            trig["raw_bytes_total"] = s.oversize if s.oversize is not None else len(s.raw)
            trig["raw_truncated"] = s.oversize is not None and s.oversize > len(s.raw)
        elif s.oversize is not None:
            trig["raw_bytes_total"] = s.oversize
        try:
            self.store.write_atomic("trigger.json", trig, final=True)
            trig["written"] = True
        except StoreError as e:
            trig["written"] = False
            self.problems.append("TRIGGER_NOT_WRITTEN:" + str(e))
        self.trigger = trig
        return s.reason

    def _finish(self, reason):
        c = self.cfg
        end = self.clock.sample()
        complete = reason in P.COMPLETE_REASONS and len(self.sessions) == 2 and not self.problems
        incomplete_reasons = []
        for info in self.sessions:
            if info["snapshots"] < 1:  # a session without a usable L2 snapshot leaves no exploitable book
                incomplete_reasons.append("SESSION_WITHOUT_SNAPSHOT:" + info["session"])
        if incomplete_reasons:
            complete = False
        session_ok = True
        for info in self.sessions:
            sid = info["session"]
            try:
                self.store.write_atomic("%s.receipt.json" % sid.lower(), info, final=True)
            except StoreError as e:
                session_ok = False
                self.problems.append("SESSION_RECEIPT_NOT_WRITTEN:%s:%s" % (sid, e))
        final_written = False
        complete = complete and session_ok
        final = {
            "pilot": "coinbase-btc-usd", "pilot_package_digest": c.package_digest, "evidence_kind": c.evidence_kind,
            "complete": False, "end_reason": reason, "caps": c.caps.document(), "sequence_policy": c.sequence_policy,
            "connections_opened": self.budget.used, "messages": self.msgs, "bytes_written": self.store.used,
            "trigger": None if self.trigger is None else {k: self.trigger.get(k) for k in ("reason", "session", "idx", "written")},
            "started_utc_ns": self.t0.utc_ns, "started_mono_ns": self.t0.monotonic_ns,
            "ended_utc_ns": end.utc_ns, "ended_mono_ns": end.monotonic_ns,
            "observer_clock_checks": c.clock_checks if c.clock_checks is not None else "NOT_SUPPLIED",
            "limits": LIMIT_STATUS, "problems": list(self.problems), "incomplete_reasons": incomplete_reasons,
            "hypotheses_unproven": ["A-SNAP-FULL", "A-SEND-AS-OF", "provider clock offset", "taker/maker convention",
                                    "sequence_num domain (see per-session hypotheses)"],
            "manifest_sha256": c.manifest_sha256,
        }
        try:
            final["files"] = self.store.inventory()
            final["complete"] = bool(complete)
            self.store.write_atomic("final.receipt.json", final, final=True)
            final_written = True
        except (StoreError, OSError) as e:
            self.problems.append("FINAL_RECEIPT_NOT_WRITTEN:" + str(e))
            complete = False
        result = CampaignResult(reason, bool(complete and final_written), self.sessions, self.msgs, self.store.used,
                                str(self.store.path), self.trigger, final_written, list(self.problems))
        self.store.close()
        return result
