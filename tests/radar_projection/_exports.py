"""Shared helpers for the S4-a tests: real Radar exports (SYNTHETIC, offline) and resealing.

The exports are produced by the current Radar engine from the committed fixtures and
the committed R1-B evidence, exactly as the ``export`` command writes them
(canonical JSON + newline). The engine is used here only to PRODUCE test inputs; the
verifier under test never imports it.
"""
from __future__ import annotations

import copy
import json

from observability.radar_selection import contract as c
from observability.radar_selection.engine import evaluate, evaluate_batch
from observability.radar_selection.fixture import canonical, sha256_hex
from observability.radar_selection.manual import empty_preferences
from tests.radar_selection import build_batches as bb
from tests.radar_selection._helpers import ROOT

FIXTURES = ROOT / "observability" / "radar_selection" / "fixtures"
BATCH = "r1b_syn_01_btc_atom"
SOURCES = ("r0_syn_01_calm", "r0_syn_02_volatile", "r0_syn_03_active_gaps", "r0_syn_04_incoherent", BATCH)
MISSIONS = tuple(c.MISSIONS)
CASES = [(s, m) for s in SOURCES for m in MISSIONS]
ARCHIVE = ROOT / "docs" / "research" / "radar_rref" / "archive"
_BLOBS = None


def blobs() -> dict:
    global _BLOBS
    if _BLOBS is None:
        _BLOBS = {str(p.relative_to(bb.EVIDENCE)): p.read_bytes() for p in bb.EVIDENCE.rglob("*") if p.is_file()}
    return dict(_BLOBS)


def evaluation(source: str, mission: str = "DEEP_OBSERVATION", prefs: dict | None = None) -> dict:
    if source == BATCH:
        raw = (bb.EVIDENCE / "batches" / f"{source}.json").read_bytes()
        return evaluate_batch(raw, blobs(), prefs, mission)
    return evaluate((FIXTURES / f"{source}.json").read_bytes(), prefs, mission)


def export(source: str, mission: str = "DEEP_OBSERVATION", prefs: dict | None = None) -> bytes:
    """Bytes of the ``export`` command: canonical JSON + newline."""
    return canonical(evaluation(source, mission, prefs)) + b"\n"


def prefs(selected=(), pinned=(), excluded=()) -> dict:
    p = empty_preferences()
    p.update(selected=sorted(selected), pinned=sorted(pinned), excluded=sorted(excluded))
    return p


def reseal(doc: dict) -> bytes:
    """Recompute the seal of a (tampered) document, as an attacker could."""
    doc = copy.deepcopy(doc)
    body = {k: v for k, v in doc.items() if k != "evaluation_sha256"}
    doc["evaluation_sha256"] = sha256_hex(canonical(body))
    return canonical(doc) + b"\n"


def loads(raw: bytes) -> dict:
    return json.loads(raw)


def market(doc: dict, mid: str) -> dict:
    for m in doc["markets"]:
        if m["market_id"] == mid:
            return m
    raise KeyError(mid)
