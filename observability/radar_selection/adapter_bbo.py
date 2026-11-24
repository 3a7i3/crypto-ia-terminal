"""R1-B — replayed BBO windows -> light Radar observations (pure, no I/O).

Input: the artifacts that an offline replay of a sealed BBO journal already
produced (``radar_composite.bbo_pilot replay`` then ``bbo_history build``):

- the ``bbo-composite-history/1.0.0`` publication (the *anchor*), whose
  provenance lists the SHA-256 of every replayed window and of the sealed
  journal files;
- the journal ``manifest.json`` (bound to the anchor by the sealed hashes; it
  carries the native bindings checked against the venue catalogues);
- the ``MarketBboComposite`` windows ``window_N_primary.json``.

Nothing is replayed, rebuilt, fetched or recomputed here. Declared rules
(contract ``CAT_R1B_CONTRAT_LOT_RADAR``):

- price kind ``MID_BBO``: the published ``mid`` is copied as it is. If it is not
  exactly ``(bid + ask) / 2`` the observation is refused, never corrected;
- only instants with ``eligible = true`` and ``continuity = SYNCED`` give a
  sample; any other instant is omitted (never a null time) and listed with its
  reason in the L2 scope;
- Kraken: ``VERIFIED_TOP_N`` with the subscribed depth (the CRC32 of the WS v2
  book attests the first 10 levels on valid instants only); MEXC:
  ``TECHNICALLY_COMPATIBLE`` (no native checksum);
- the windows carry the first level only: the depth within 10 bps is UNKNOWN,
  the trade channel was not captured (activity UNKNOWN) and no cost was measured.

This module never imports ``bbo_pilot`` (which loads socket/ssl).
"""
from __future__ import annotations

from decimal import Decimal

from observability.radar_composite.bbo_history import validate_history
from observability.radar_composite.bbo_schema import validate_bbo
from observability.scanner_universe.catalogues import strict_json

from . import contract as c
from .fixture import RadarRefusal

VENUES = ("mexc", "kraken")
PRICE_KIND = "MID_BBO"
KRAKEN_CHECKSUM_LEVELS = 10   # Kraken WS v2 book CRC32 covers the top 10 levels
# Batch evidence kind <- evidence kind recorded by the BBO pilot. A corpus the pilot
# collected from the venues is OBSERVATION; read back offline it is HISTORICAL input
# (operator D2). MIXED and anything else is refused.
SOURCE_EVIDENCE_KIND = {"SYNTHETIC": "SYNTHETIC", "HISTORICAL": "OBSERVATION"}
UNKNOWN_REASONS = {"activity": "TRADE_CHANNEL_NOT_CAPTURED", "depth": "DEPTH_LEVELS_NOT_IN_ARTIFACT",
                   "cost": "COST_NOT_MEASURED"}


class ObservationRefusal(RadarRefusal):
    """One observation (or the observations of one source) refused with a stable code."""


def parse(raw: bytes, code: str):
    try:
        return strict_json(raw)
    except ValueError:
        raise RadarRefusal(code) from None


def anchor_pair(anchor: dict, pair: str) -> dict:
    """The validated pair entry of a bbo-composite-history publication."""
    errors = validate_history(anchor)
    if errors:
        raise RadarRefusal("ANCHOR_INVALID:" + ",".join(errors[:3])[:120])
    for p in anchor["pairs"]:
        if p["pair"] == pair:
            return p
    raise RadarRefusal("ANCHOR_PAIR_NOT_FOUND:" + str(pair)[:20])


def bind_manifest(manifest: dict, entry: dict, evidence_kind: str) -> dict:
    """Check that the journal manifest is the one the anchor was built from."""
    pv = entry["provenance"]
    sealed = manifest.get("sealed") if isinstance(manifest, dict) else None
    if not isinstance(sealed, dict) or sealed.get("events_sha256") != pv["events_sha256"] \
            or sealed.get("frames_sha256") != pv["frames_sha256"]:
        raise RadarRefusal("MANIFEST_NOT_BOUND_TO_ANCHOR")
    if manifest.get("pair") != entry["pair"] or manifest.get("status") != "COMPLETED":
        raise RadarRefusal("MANIFEST_NOT_BOUND_TO_ANCHOR")
    expected = SOURCE_EVIDENCE_KIND.get(evidence_kind)
    if expected is None or manifest.get("evidence_kind") != expected or entry["evidence_kind"] != expected:
        raise RadarRefusal("EVIDENCE_KIND_MIXED")
    inst, bindings = manifest.get("instrument"), manifest.get("bindings")
    if not isinstance(inst, dict) or not isinstance(bindings, dict) or set(bindings) != set(VENUES):
        raise RadarRefusal("MANIFEST_BINDINGS")
    out = {}
    for v in VENUES:
        b = bindings[v]
        if not isinstance(b, dict) or b.get("venue") != v or not isinstance(b.get("native_symbol"), str):
            raise RadarRefusal("MANIFEST_BINDINGS")
        out[v] = b["native_symbol"]
    if inst.get("market_kind") != "SPOT" or not isinstance(inst.get("base_asset_id"), str) \
            or not isinstance(inst.get("quote_asset_id"), str):
        raise RadarRefusal("MANIFEST_INSTRUMENT")
    return {"native": out, "base": inst["base_asset_id"], "quote": inst["quote_asset_id"]}


def check_windows(windows: list, entry: dict) -> dict:
    """Validated, contiguous windows on one grid; returns the coverage."""
    if not 1 <= len(windows) <= c.MAX_WINDOWS_PER_OBSERVATION:
        raise RadarRefusal("WINDOW_COUNT")
    step = None
    for i, w in enumerate(windows):
        errors = validate_bbo(w)
        if errors:
            raise RadarRefusal("WINDOW_INVALID:" + ",".join(errors[:3])[:120])
        if w["instrument"] != windows[0]["instrument"] or w["venues"] != windows[0]["venues"]:
            raise RadarRefusal("WINDOW_IDENTITY_MISMATCH")
        s = w["parameters"]["step_ms"]
        if step is None:
            step = s
        if s != step or (i and w["window"]["start_ms"] != windows[i - 1]["window"]["end_ms"]):
            raise RadarRefusal("WINDOW_GRID_MISMATCH")
        instants = [p["instant_ms"] for p in w["points"]]
        if instants[0] != w["window"]["start_ms"] or any(b - a != step for a, b in zip(instants, instants[1:])):
            raise RadarRefusal("WINDOW_GRID_MISMATCH")
        if i and instants[0] - windows[i - 1]["points"][-1]["instant_ms"] != step:
            raise RadarRefusal("WINDOW_GRID_MISMATCH")
    if windows[0]["instrument"].get("base_asset_id") is None:
        raise RadarRefusal("WINDOW_IDENTITY_MISMATCH")
    return {"start_ms": windows[0]["window"]["start_ms"], "end_ms": windows[-1]["window"]["end_ms"],
            "step_ms": step}


def _exclusion(point: dict, venue: str) -> str | None:
    src = point["sources"]
    if src is None:
        return "NOT_EVALUATED"
    s = src[venue]
    if not s["eligible"]:
        return "STATE_" + s["state"]
    if s["continuity"] != "SYNCED":
        return "CONTINUITY_" + str(s["continuity"])
    if s["bid"] is None or s["ask"] is None or s["mid"] is None:
        return "BBO_VALUE_MISSING"
    return None


def project(source_id: str, windows: list, binding: dict) -> list:
    """Two observations (MEXC, Kraken) from verified windows. Pure and deterministic.

    Raises ``ObservationRefusal`` with ``.venue`` for an observation that cannot be
    published as it is (e.g. ``MID_REPRESENTATION_MISMATCH``).
    """
    venues = windows[0]["venues"]
    step = windows[0]["parameters"]["step_ms"]
    points = [p for w in windows for p in w["points"]]
    out = []
    for v in VENUES:
        samples, excluded = [], []
        for p in points:
            why = _exclusion(p, v)
            if why is not None:
                excluded.append({"t_ms": p["instant_ms"], "reason": why})
                continue
            s = p["sources"][v]
            if Decimal(s["mid"]) != (Decimal(s["bid"]) + Decimal(s["ask"])) / 2:
                err = ObservationRefusal(f"MID_REPRESENTATION_MISMATCH:{v}@{p['instant_ms']}")
                err.venue = v
                raise err
            samples.append({"t_ms": p["instant_ms"], "price": s["mid"], "bid": s["bid"], "ask": s["ask"]})
        if len(excluded) > c.MAX_EXCLUDED_INSTANTS:
            err = ObservationRefusal("EXCLUDED_INSTANTS_BOUND")
            err.venue = v
            raise err
        ref = f"{source_id}#{v}"
        if v == "kraken":
            depth = venues["kraken"].get("depth")
            if depth != KRAKEN_CHECKSUM_LEVELS:
                err = ObservationRefusal("KRAKEN_DEPTH_NOT_CHECKSUM_DEPTH")
                err.venue = v
                raise err
            l2 = None if not samples else {
                "status": "VERIFIED_TOP_N", "evidence_ref": ref, "depth_levels": depth,
                "depth_quote_10bps": None,
                "scope": {"verified_by": "KRAKEN_CRC32", "valid_instants": len(samples),
                          "grid_instants": len(points), "excluded_instants": excluded}}
        else:
            l2 = None if not samples else {
                "status": "TECHNICALLY_COMPATIBLE", "evidence_ref": ref, "depth_levels": None,
                "depth_quote_10bps": None, "scope": None}
        out.append({
            "venue": v, "market_type": "SPOT", "native_symbol": binding["native"][v],
            "declared_base": binding["base"], "declared_quote": binding["quote"],
            "evidence_ref": ref, "price_kind": PRICE_KIND,
            "window": {"start_ms": points[0]["instant_ms"], "step_ms": step, "points": len(points)},
            "samples": samples, "activity": None, "l2": l2, "cost": None,
            "source_id": source_id, "unknown_reasons": dict(UNKNOWN_REASONS),
        })
    return out
