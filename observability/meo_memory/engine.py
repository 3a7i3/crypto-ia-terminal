"""The single bridge from the memory to the scientific engine (operator decision MEO04-D01).

Dependency is one-way: the memory calls the MEO-01 replay and the MEO-03 reading
exactly as delivered and never the reverse. Nothing is recomputed here: at import
time the sealed capture is verified with ``kraken_trades.verify_journal``, then
replayed with ``kraken_trades.replay_journal`` and read with
``meo_reading.read_report``; the bytes of a supplied report or reading must be
identical to that re-run, otherwise the import is refused.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from observability.market_flow import kraken_trades as kt
from observability.market_flow import meo_reading as mr

from . import canon as c
from .canon import MemoryRefusal

REQUIRED_MEMBERS = ("manifest.json", "events.jsonl", "frames.bin")
REPORT_MEMBERS = ("report-original.json", "report-replay.json")
OPTIONAL_MEMBERS = REPORT_MEMBERS + ("preflight.json", "SHA256SUMS")
MEMBERS = REQUIRED_MEMBERS + OPTIONAL_MEMBERS
_SUMS_LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9._-]{1,80})")
_PARTITION_OF = {"HISTORICAL": "HISTORICAL", "SYNTHETIC": "SYNTHETIC"}


def engine_identity() -> dict:
    """Versions and source digests of the engine modules that produced the verified bytes."""
    modules = {"kraken_trades.py": kt, "meo_reading.py": mr, "trades.py": mr.tr,
               "exact.py": sys.modules[mr.exact.__module__]}
    return {"report_schema": kt.SCHEMA, "reading_schema": mr.SCHEMA,
            "rule": {"id": mr.RULE["id"], "version": mr.RULE["version"]},
            "code_sha256": {name: c.sha256(Path(m.__file__).read_bytes()) for name, m in sorted(modules.items())}}


def _check_sums(members: dict) -> None:
    raw = members.get("SHA256SUMS")
    if raw is None:
        return
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError:
        raise MemoryRefusal(c.PROOF_CORRUPT, "SHA256SUMS_MALFORMED") from None
    listed = {}
    for line in lines:
        m = _SUMS_LINE.fullmatch(line)
        if not m or m.group(2) in listed:
            raise MemoryRefusal(c.PROOF_CORRUPT, "SHA256SUMS_MALFORMED")
        listed[m.group(2)] = m.group(1)
    for name in REQUIRED_MEMBERS:
        if name not in listed:
            raise MemoryRefusal(c.PROOF_CORRUPT, "SHA256SUMS_INCOMPLETE:" + name)
    for name, digest in listed.items():
        if name not in members:
            raise MemoryRefusal(c.PROOF_UNAVAILABLE, "SEALED_MEMBER_MISSING:" + name)
        if c.sha256(members[name]) != digest:
            raise MemoryRefusal(c.PROOF_CORRUPT, "SHA256SUMS_MISMATCH:" + name)


def verify_capture(members: dict, reading_bytes: bytes | None) -> dict:
    """Verify a sealed capture, replay it, read it, and return the verified material."""
    for name in REQUIRED_MEMBERS:
        if name not in members:
            raise MemoryRefusal(c.PROOF_UNAVAILABLE, "CAPTURE_MEMBER_MISSING:" + name)
    _check_sums(members)
    manifest = c.strict_json(members["manifest.json"], c.PROOF_CORRUPT)
    try:
        events = kt.verify_journal(manifest, members["events.jsonl"], members["frames.bin"])
        report = kt.replay_journal(manifest, events)
    except kt.JournalRefusal as exc:
        raise MemoryRefusal(c.PROOF_CORRUPT, "SEAL_OR_JOURNAL:" + str(exc)) from None
    report_bytes = kt.canonical(report)
    report_origin = "RECOMPUTED_NO_SOURCE_FILE"
    for name in REPORT_MEMBERS:
        if name in members:
            if members[name] != report_bytes:
                raise MemoryRefusal(c.PROOF_CORRUPT, "REPLAY_NOT_REPRODUCED:" + name)
            report_origin = "SOURCE_FILE_BYTE_IDENTICAL_TO_REPLAY"
    try:
        reading = mr.read_report(report)
    except mr.ReadingRefusal as exc:
        raise MemoryRefusal(c.INPUT_REFUSED, "READING_REFUSED:" + str(exc)) from None
    computed = mr.canonical(reading)
    if reading_bytes is None:
        reading_origin = "RECOMPUTED_AT_IMPORT"
    elif reading_bytes != computed:
        raise MemoryRefusal(c.PROOF_CORRUPT, "READING_NOT_REPRODUCED")
    else:
        reading_origin = "SOURCE_FILE_BYTE_IDENTICAL_TO_READING"
    partition = _PARTITION_OF.get(reading["evidence_kind"])
    if partition is None:
        raise MemoryRefusal(c.INPUT_REFUSED, "EVIDENCE_KIND_NOT_STORABLE")
    flow, instrument = reading["flow"], manifest.get("instrument") or {}
    identity = {
        "partition": partition,
        "instrument": {"venue": flow["venue"], "instrument": flow["instrument"], "base": flow["base"],
                       "quote": flow["quote"], "market_kind": flow["market_kind"], "id_domain": flow["id_domain"],
                       "side_basis": (flow.get("side_convention") or {}).get("basis"),
                       "contract_identity": instrument.get("contract_identity"),
                       "settlement_asset_id": instrument.get("settlement_asset_id")},
        "session": {"manifest_sha256": c.sha256(members["manifest.json"]),
                    "events_sha256": manifest["sealed"]["events_sha256"],
                    "frames_sha256": manifest["sealed"]["frames_sha256"],
                    "capture": manifest.get("pilot")},
        "contract": reading["schema"],
        "rule": {"id": reading["rule"]["id"], "version": reading["rule"]["version"]},
    }
    receipts = [ev["recv_wall_ns"] for ev in events]
    return {"identity": identity, "reading": reading, "reading_bytes": computed, "reading_origin": reading_origin,
            "report_bytes": report_bytes, "report_origin": report_origin,
            # Receipt instants of the capture host (journal order); never a market or UTC instant.
            "receipt_bounds_ns": {"first": str(min(receipts)) if receipts else None,
                                  "last": str(max(receipts)) if receipts else None,
                                  "basis": "CAPTURE_HOST_RECEIPT_WALL_UNATTESTED"},
            "engine": engine_identity()}
