"""Canonical forms, strict JSON, typed refusals and logical identities (pure).

Canonical JSON is the one already used by the MEO-01 report and the MEO-03
reading: sorted keys, ASCII, no spaces. A logical identity is the SHA-256 of a
closed preimage (partition, instrument, capture session, contract, rule, native
segment, window bounds, object type). It never contains a local path, an import
instant or the hash of a whole reading, so it stays distinct from the content
hash of the object it names.
"""

from __future__ import annotations

import hashlib
import json

IDENTITY_SCHEMA = "meo-memory-identity/1"
PARTITIONS = ("HISTORICAL", "SYNTHETIC")

# Error categories a caller can tell apart; an empty result is never one of them.
NOT_CONFIGURED = "NOT_CONFIGURED"
PROOF_UNAVAILABLE = "PROOF_UNAVAILABLE"
PROOF_CORRUPT = "PROOF_CORRUPT"
CONFLICT = "CONFLICT"
INDEX_INCONSISTENT = "INDEX_INCONSISTENT"
INPUT_REFUSED = "INPUT_REFUSED"
BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
WRITER_BUSY = "WRITER_BUSY"
PUBLICATION_UNCERTAIN = "PUBLICATION_UNCERTAIN"
INVALID_REQUEST = "INVALID_REQUEST"


class MemoryRefusal(Exception):
    """A typed refusal: ``category`` is stable, ``detail`` explains the case."""

    def __init__(self, category: str, detail: str = ""):
        super().__init__(f"{category}:{detail}" if detail else category)
        self.category = category
        self.detail = detail


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_sha256(text) -> bool:
    return isinstance(text, str) and len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise MemoryRefusal(INPUT_REFUSED, "JSON_DUPLICATE_KEY")
        out[k] = v
    return out


def _no_float(text):
    raise MemoryRefusal(INPUT_REFUSED, "JSON_FLOAT_FORBIDDEN")


def _no_constant(text):
    raise MemoryRefusal(INPUT_REFUSED, "JSON_CONSTANT_FORBIDDEN")


def strict_json(raw: bytes, category: str = INPUT_REFUSED):
    """Parse UTF-8 JSON without BOM, duplicate keys, floats, NaN or Infinity."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raise MemoryRefusal(category, "JSON_BOM")
    try:
        text = raw.decode("utf-8")
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_float=_no_float,
                          parse_constant=_no_constant)
    except MemoryRefusal as exc:
        raise MemoryRefusal(category, exc.detail) from None
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise MemoryRefusal(category, "JSON_MALFORMED") from None


def logical_id(base: dict, kind: str, scope: dict) -> str:
    """Identity of one memory object; ``base`` holds partition/instrument/session/contract/rule."""
    return sha256(canonical({"schema": IDENTITY_SCHEMA, **base, "type": kind, "scope": scope}))


def window_scope(w: dict) -> dict:
    return {"segment": w.get("cvd_segment"), "start_ns": w["start_ns"], "end_ns": w["end_ns"]}


def decompose(reading: dict, base: dict) -> dict:
    """Split a reading into one session object, its windows and its divergent event references.

    Nothing is dropped: windows are kept whatever their state (UNKNOWN, excluded,
    not covered) and verbatim; an event only references its window and carries
    the qualifiers of ``divergent_windows`` (no measure is duplicated).
    """
    session = {k: v for k, v in reading.items() if k not in ("windows", "divergent_windows")}
    windows = []
    by_start = {}
    for w in reading["windows"]:
        wid = logical_id(base, "WINDOW", window_scope(w))
        windows.append({"window_id": wid, "body": w, "content_sha256": sha256(canonical(w))})
        by_start[w["start_ns"]] = wid
    firsts = {(f["segment"], f["start_ns"]) for f in reading.get("first_desalignment_by_segment") or []}
    events = []
    for d in reading["divergent_windows"]:
        if d["start_ns"] not in by_start:
            raise MemoryRefusal(INPUT_REFUSED, "EVENT_WITHOUT_WINDOW")
        body = {"window_id": by_start[d["start_ns"]], "start_ns": d["start_ns"], "segment": d["segment"],
                "eligible_for_first_desalignment": d["eligible_for_first_desalignment"],
                "exclusion_reason": d["exclusion_reason"],
                "first_in_segment": (d["segment"], d["start_ns"]) in firsts}
        eid = logical_id(base, "DIVERGENT_EVENT", {"segment": d["segment"], "start_ns": d["start_ns"]})
        events.append({"event_id": eid, "body": body, "content_sha256": sha256(canonical(body))})
    sid = logical_id(base, "SESSION", {})
    return {"session_id": sid, "session": session, "session_content_sha256": sha256(canonical(session)),
            "windows": windows, "events": events}


def recompose(parts: dict) -> dict:
    """Inverse of ``decompose``: the original reading, byte for byte once canonical."""
    reading = dict(parts["session"])
    reading["windows"] = [w["body"] for w in parts["windows"]]
    reading["divergent_windows"] = [{k: e["body"][k] for k in ("start_ns", "segment",
                                                                "eligible_for_first_desalignment",
                                                                "exclusion_reason")}
                                    for e in parts["events"]]
    return reading
