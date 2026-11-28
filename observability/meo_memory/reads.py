"""The three bounded local reads of MEO-04: Maintenant, Événements, Bilan (no HTTP, no UI).

Each read pins the knowledge bound K (journal head) it was served at, takes its
selection and order from the SQLite index, and takes every value it returns from
the reading proof, re-verified at read time (hash, recomposition, content hash
of each object). An index that disagrees with the proofs is INDEX_INCONSISTENT;
a missing proof is PROOF_UNAVAILABLE; a bad one is PROOF_CORRUPT. An empty
memory gives an EMPTY result, never one of these errors, and an error is never
turned into an empty result.
"""

from __future__ import annotations

import functools
import sqlite3

from . import canon as c
from .canon import MemoryRefusal
from .store import Store

MEMORY_LIMITS = [
    "MEO-04 memory of MEO-03 readings under PROBATION; it does not claim ADMITTED_PARTIAL.",
    "Imported evidence is not a live feed: no observation is fresh; its age is UNKNOWN (time_basis UNATTESTED).",
    "Native axes of different captures are not compared; overlapping captures are listed, never summed.",
    "knowledge_seq is the local import order; it is neither the receipt order nor the native axis.",
]
MARKING = ("evidence_kind", "source_evidence_kind", "admission", "quality", "time_basis", "axis",
           "qualification", "rule", "corpus_ref", "flow", "subscription_acknowledged_receipt_ns")


def _cursor_out(k: int, *keys) -> str:
    return ":".join(str(x) for x in (k,) + keys)


def _cursor_in(cursor, k: int, n: int, hex_tail: bool = False) -> tuple:
    if cursor is None:
        return None
    parts = str(cursor).split(":")
    digits = parts[:-1] if hex_tail else parts
    if len(parts) != n + 1 or not all(p.isascii() and p.isdigit() and len(p) <= 19 for p in digits) \
            or (hex_tail and not c.is_sha256(parts[-1])):
        raise MemoryRefusal(c.INVALID_REQUEST, "CURSOR_MALFORMED")
    if int(parts[0]) != k:
        raise MemoryRefusal(c.INVALID_REQUEST, "CURSOR_FROM_ANOTHER_KNOWLEDGE_BOUND")
    return tuple(parts[1:])


def _typed(fn):
    """A SQLite failure during a read (locked, damaged) is INDEX_INCONSISTENT, never an empty result."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except sqlite3.Error:
            raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_UNREADABLE") from None
    return wrapper


class Reader:
    def __init__(self, root, *, limits=None):
        self.store = Store(root) if limits is None else Store(root, limits=limits)

    def _page(self, limit) -> int:
        lim = self.store.limits
        n = lim.page_default if limit is None else limit
        if type(n) is not int or not 1 <= n <= lim.page_max:
            raise MemoryRefusal(c.INVALID_REQUEST, "PAGE_SIZE_OUT_OF_BOUNDS")
        return n

    def _view(self):
        # One SQLite read snapshot, checked in full against the journal and every proof of the bound
        # (all rows, all columns, schema, cardinalities) before anything is selected from it (RV01-01/02).
        journal, conn, self._parts = self.store.verified_view()
        k = len(journal)
        bound = {"partition": self.store.partition, "knowledge_seq": k,
                 "journal_head_sha256": journal[-1][1] if journal else None}
        return journal, conn, k, bound

    def _session(self, journal, cache, conn, seq: int) -> dict:
        """Session of the verified view: record and parts re-derived from its proofs."""
        if seq in cache:
            return cache[seq]
        rec, sha = journal[seq - 1]
        parts = self._parts[seq]
        session = parts["session"]
        out = {"record": rec, "import_sha256": sha, "parts": parts,
               "windows": {w["window_id"]: w["body"] for w in parts["windows"]},
               "events": {e["event_id"]: e["body"] for e in parts["events"]},
               "provenance": {"session_id": rec["session_id"], "knowledge_seq": seq, "import_sha256": sha,
                              "reading_sha256": rec["reading_sha256"],
                              "proofs": {p["role"]: p["sha256"] for p in rec["proofs"]},
                              "identity": rec["identity"], "native_bounds_ns": rec["native_bounds_ns"],
                              "receipt_bounds_ns": rec["receipt_bounds_ns"],
                              "verification": {k: rec["verification"][k] for k in ("seal", "replay", "reading")}},
               "marking": {k: session.get(k) for k in MARKING},
               "limits": session.get("limits")}
        cache[seq] = out
        return out

    def _freshness(self):
        state = "NOT_FRESH_SYNTHETIC" if self.store.partition == "SYNTHETIC" else "NOT_FRESH_HISTORICAL"
        return {"state": state, "age": "UNKNOWN",
                "reasons": ["IMPORTED_EVIDENCE_NOT_A_LIVE_FEED", "TIME_BASIS_UNATTESTED"]}

    # ------------------------------------------------------------------ Maintenant
    @_typed
    def now(self) -> dict:
        journal, conn, k, bound = self._view()
        base = {"read": "NOW", "knowledge_bound": bound, "freshness": self._freshness(),
                "order": "last import by knowledge_seq, then greatest native start_ns inside that capture",
                "memory_limits": MEMORY_LIMITS}
        if conn is None or k == 0:
            if conn is not None:
                conn.close()
            return {**base, "result": "EMPTY"}
        try:
            row = conn.execute("SELECT window_id FROM windows WHERE knowledge_seq=? ORDER BY start_ns DESC "
                               "LIMIT 1", (k,)).fetchone()
            if row is None:
                return {**base, "result": "EMPTY", "detail": "LAST_IMPORT_HAS_NO_WINDOW"}
            s = self._session(journal, {}, conn, k)
        finally:
            conn.close()
        return {**base, "result": "OBSERVATION", "window_id": row[0], "window": s["windows"][row[0]],
                "provenance": s["provenance"], "marking": s["marking"], "reading_limits": s["limits"]}

    # ------------------------------------------------------------------ Événements
    @_typed
    def events(self, *, limit=None, cursor=None, include_excluded=False, first_only=False) -> dict:
        n = self._page(limit)
        journal, conn, k, bound = self._view()
        scope = "ELIGIBLE_AND_EXCLUDED" if include_excluded else "ELIGIBLE_ONLY"
        base = {"read": "EVENTS", "knowledge_bound": bound, "scope": scope, "first_only": bool(first_only),
                "order": "knowledge_seq, native start_ns (integer), event_id", "page_size": n,
                "memory_limits": MEMORY_LIMITS}
        if conn is None:
            return {**base, "result": "EMPTY", "items": [], "next_cursor": None}
        try:  # a refused cursor must not leave the read transaction open (it would block the writer)
            after = _cursor_in(cursor, k, 3, hex_tail=True)
        except BaseException:
            conn.close()
            raise
        where, args = ["knowledge_seq <= ?"], [k]
        if not include_excluded:
            where.append("eligible = 1")
        if first_only:
            where.append("first_in_segment = 1")
        if after is not None:
            where.append("(knowledge_seq, start_ns, event_id) > (?, ?, ?)")
            args += [int(after[0]), int(after[1]), after[2]]
        try:
            cache, items = {}, []
            # Every session of the bound is re-verified: an empty page is a result only if no proof is
            # missing or corrupt and the index agrees with all of them.
            for seq in range(1, k + 1):
                self._session(journal, cache, conn, seq)
            rows = conn.execute("SELECT knowledge_seq, start_ns, event_id FROM events WHERE " + " AND ".join(where)
                                + " ORDER BY knowledge_seq, start_ns, event_id LIMIT ?", args + [n + 1]).fetchall()
            for seq, start, eid in rows[:n]:
                s = self._session(journal, cache, conn, seq)
                ev = s["events"][eid]
                items.append({"event_id": eid, "event": ev, "window": s["windows"][ev["window_id"]],
                              "documentary_only": not ev["eligible_for_first_desalignment"],
                              "session_id": s["record"]["session_id"], "knowledge_seq": seq})
            used = sorted({i["knowledge_seq"] for i in items})
            sessions = {seq: {"provenance": cache[seq]["provenance"], "marking": cache[seq]["marking"],
                              "first_desalignment_by_segment":
                                  cache[seq]["parts"]["session"]["first_desalignment_by_segment"]}
                        for seq in used}
        finally:
            conn.close()
        nxt = _cursor_out(k, *rows[n - 1]) if len(rows) > n else None
        return {**base, "result": "EVENTS" if items else "EMPTY", "items": items, "sessions": sessions,
                "next_cursor": nxt}

    # ------------------------------------------------------------------ Bilan
    @_typed
    def summary(self, *, limit=None, cursor=None) -> dict:
        n = self._page(limit)
        journal, conn, k, bound = self._view()
        base = {"read": "SUMMARY", "knowledge_bound": bound, "page_size": n,
                "totals_across_sessions": None,
                "totals_reason": "NOT_SUMMED: captures may overlap on the native axis",
                "memory_limits": MEMORY_LIMITS}
        if conn is None:
            return {**base, "result": "EMPTY", "sessions": [], "next_cursor": None}
        try:
            after = _cursor_in(cursor, k, 1)
        except BaseException:
            conn.close()
            raise
        start = int(after[0]) if after else 0
        try:
            seqs = list(range(start + 1, min(k, start + n + 1) + 1))  # from the journal, not the index
            bounds = [(rec["knowledge_seq"], rec["session_id"], _n(rec["native_bounds_ns"]["first"]),
                       _n(rec["native_bounds_ns"]["last"])) for rec, _sha in journal[:k]]
            out, cache = [], {}
            for seq in seqs[:n]:
                s = self._session(journal, cache, conn, seq)
                rows = list(s["windows"].values())
                evs = list(s["events"].values())
                me = next(b for b in bounds if b[0] == seq)
                overlaps = sorted(b[1] for b in bounds if b[0] != seq and None not in (b[2], b[3], me[2], me[3])
                                  and b[2] < me[3] and me[2] < b[3])
                out.append({
                    "session_id": s["record"]["session_id"], "knowledge_seq": seq,
                    "windows": len(rows),
                    "by_alignment": _count(w["alignment"] for w in rows),
                    "by_status": _count(w["status"] for w in rows),
                    "by_exclusion_reason": _count(w["exclusion_reason"] or "NONE" for w in rows),
                    "divergent_events": {"total": len(evs),
                                         "eligible": sum(1 for e in evs if e["eligible_for_first_desalignment"]),
                                         "excluded": sum(1 for e in evs if not e["eligible_for_first_desalignment"])},
                    "first_desalignment_by_segment": s["parts"]["session"]["first_desalignment_by_segment"],
                    "first_desalignment": s["parts"]["session"]["first_desalignment"],
                    "overlapping_sessions_native_conditional": overlaps,
                    "provenance": s["provenance"], "marking": s["marking"]})
                cache.clear()
        finally:
            conn.close()
        nxt = _cursor_out(k, seqs[n - 1]) if len(seqs) > n else None
        return {**base, "result": "SUMMARY" if out else "EMPTY", "sessions": out, "next_cursor": nxt}


def _n(text):
    return None if text is None else int(text)


def _count(values) -> dict:
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))
