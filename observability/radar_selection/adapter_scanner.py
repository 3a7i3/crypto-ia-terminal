"""R1-B — Scanner V1 run -> catalogue references of a radar-batch (pure, no I/O).

A Scanner run directory (``observability.scanner_universe.collect``) holds the
five raw catalogue responses and a ``manifest.json`` with, per document, the
reception time, the error code and the SHA-256 and size of the raw bytes. This
adapter only turns that manifest into references; it never parses, copies or
re-serialises a catalogue (operator decision D1, 2026-11-24).
"""
from __future__ import annotations

import hashlib
import re

from observability.scanner_universe.catalogues import strict_json

from .fixture import CATALOGUE_DOCUMENTS, RadarRefusal

_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_ERROR = re.compile(r"[A-Za-z0-9_]{1,80}", re.ASCII)  # Scanner codes: HTTP_404, TRANSPORT_URLError...


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def _int(v) -> bool:
    return type(v) is int and 0 <= v <= 2**53 - 1


def manifest_entries(manifest_raw: bytes) -> dict:
    """Validated ``documents`` of a Scanner run manifest. Raises ``RadarRefusal``."""
    try:
        doc = strict_json(manifest_raw)
    except ValueError:
        raise RadarRefusal("CATALOGUE_MANIFEST_MALFORMED") from None
    docs = doc.get("documents") if isinstance(doc, dict) else None
    if not isinstance(docs, dict) or set(docs) != set(CATALOGUE_DOCUMENTS):
        raise RadarRefusal("CATALOGUE_MANIFEST_DOCUMENTS")
    out = {}
    for name in CATALOGUE_DOCUMENTS:
        e = docs[name]
        if not isinstance(e, dict):
            raise RadarRefusal("CATALOGUE_MANIFEST_ENTRY:" + name)
        sha, size, received, error = e.get("sha256"), e.get("bytes"), e.get("received_ms"), e.get("error")
        if error is None:
            if not (isinstance(sha, str) and _HEX64.fullmatch(sha) and _int(size) and size > 0 and _int(received)):
                raise RadarRefusal("CATALOGUE_MANIFEST_ENTRY:" + name)
        else:
            if not (isinstance(error, str) and _ERROR.fullmatch(error)) \
                    or sha is not None or size is not None:
                raise RadarRefusal("CATALOGUE_MANIFEST_ENTRY:" + name)
        out[name] = {"sha256": sha, "bytes": size, "received_ms": received if _int(received) else None,
                     "error": error}
    return out


def catalogue_refs(manifest_raw: bytes, run_ref: str) -> dict:
    """Batch fields ``catalogue_manifest`` and ``catalogue_refs`` for one Scanner run.

    ``run_ref`` is the run directory relative to the evidence root
    (``scanner/runs/<run_id>``); the raw files keep the Scanner names.
    """
    entries = manifest_entries(manifest_raw)
    refs = {}
    for name in CATALOGUE_DOCUMENTS:
        e = entries[name]
        if e["error"] is None:
            refs[name] = {"ref": f"{run_ref}/{name}.json", "sha256": e["sha256"], "bytes": e["bytes"],
                          "received_ms": e["received_ms"], "error": None}
        else:
            refs[name] = {"ref": None, "sha256": None, "bytes": None,
                          "received_ms": e["received_ms"], "error": e["error"]}
    return {"catalogue_manifest": {"ref": f"{run_ref}/manifest.json", "sha256": sha256_hex(manifest_raw)},
            "catalogue_refs": refs}
