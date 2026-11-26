"""S4-b — serve ONE sealed Radar export as a verified ``radar-projection/1.0.0``.

GET-only presentation. The reader:
- reads the bytes of one explicitly configured export file (bounded, no link);
- hands them to the S4-a verifier through ``project_bytes(raw)``, the only
  public producer of a verified projection, and serves those bytes unchanged;
- adds a separate service envelope ``radar-projection-service/1.0.0`` with
  E2 (publication freshness) and E1 (catalogue provenance relation with the
  Scanner publication, read through the existing ScannerUniverseReader).

It never builds, completes or rewrites a projection, never recomputes a score,
a decision or a rank, opens no network connection, starts no collector and
writes nothing. Unset path => NOT_CONFIGURED; a read failure or a verifier
refusal is a typed error, never an empty Radar.

Contract: ``docs/contracts/CAT_S4B_CONTRAT_SERVICE_RADAR.md``.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from observability.operator_api.bounded_file import read_regular_file
from observability.radar_projection import contract as pc
from observability.radar_projection.projection import project_bytes
from observability.radar_projection.verifier import ProjectionRefusal
from observability.radar_selection.fixture import canonical

SERVICE_SCHEMA = "radar-projection-service/1.0.0"
PATH_ENV = "OPERATOR_RADAR_EXPORT_PATH"
MAX_AGE_ENV = "OPERATOR_RADAR_PROJECTION_MAX_AGE_S"
# Provisional, NOT calibrated: there is no Radar publication cadence yet. Same
# order as the Scanner cadence (15 min). Overridable by configuration only.
DEFAULT_MAX_AGE_MS = 900_000
MAX_AGE_LIMIT_MS = 7 * 24 * 3600 * 1000
FUTURE_TOLERANCE_MS = 5_000

PUBLICATION_STATES = ("FRESH", "STALE", "PUBLISHED_IN_FUTURE")
SOURCE_RELATIONS = ("SAME_CATALOGUE_BYTES", "DIFFERENT_CATALOGUE_BYTES", "NOT_COMPARABLE")
GLOBAL_RELATIONS = ("CATALOGUE_PROVENANCE_MATCH", "CATALOGUE_PROVENANCE_MISMATCH", "CATALOGUE_PROVENANCE_UNKNOWN")
E1_STATEMENT = "CATALOGUE_BYTES_PROVENANCE_ONLY_NOT_UNIVERSE_IDENTITY"
SCOPE_STATEMENT = "SYNTHETIC_SOURCE_PROOF_ONLY_NOT_RUNTIME_PROOF"
SERVICE_STATUS = "PRESENTATION_ONLY_NOT_AN_ADMISSION_NOT_A_RUNTIME_AUTHORIZATION"
SCANNER_MARKETS = tuple(pc.SCANNER_MARKETS)


@dataclass(frozen=True)
class RadarProjectionReadResult:
    ok: bool
    body: bytes | None = None
    error_code: str | None = None
    refusal_code: str | None = None


def _max_age_ms(value) -> tuple[int, str]:
    raw = os.getenv(MAX_AGE_ENV) if value is None else value
    if raw is None or raw == "":
        return DEFAULT_MAX_AGE_MS, "PROVISIONAL_DEFAULT"
    try:
        ms = int(str(raw)) * 1000 if value is None else int(raw)
    except ValueError:
        return DEFAULT_MAX_AGE_MS, "PROVISIONAL_DEFAULT_INVALID_CONFIGURATION"
    if not 0 < ms <= MAX_AGE_LIMIT_MS:
        return DEFAULT_MAX_AGE_MS, "PROVISIONAL_DEFAULT_INVALID_CONFIGURATION"
    return ms, "CONFIGURED"


def publication_freshness(mtime_ms: int, now_ms: int, max_age_ms: int, basis: str) -> dict:
    """E2: freshness of the PUBLICATION (the served file), never of an observation."""
    age = now_ms - mtime_ms
    if age < -FUTURE_TOLERANCE_MS:
        state = "PUBLISHED_IN_FUTURE"
    elif age > max_age_ms:
        state = "STALE"
    else:
        state = "FRESH"
    return {"published_ms": mtime_ms, "published_basis": "FILE_MODIFICATION_TIME", "served_ms": now_ms,
            "age_ms": age, "max_age_ms": max_age_ms, "max_age_basis": basis, "state": state,
            "current": state == "FRESH"}


def _side(entries, key="market"):
    out = {}
    for e in entries or ():
        if isinstance(e, dict) and isinstance(e.get(key), str):
            out[e[key]] = e
    return out


def catalogue_provenance(projection: dict, scanner) -> dict:
    """E1 (option 2, accepted 2026-11-25): compare raw catalogue digests, market by market.

    ``scanner`` is a ScannerUniverseReadResult. A concordance of catalogue bytes
    is NEVER an identity of universes.
    """
    radar = _side(projection["scanner_universe"]["catalogue_sources"])
    scanner_doc = scanner.snapshot if getattr(scanner, "ok", False) else None
    scan = _side(scanner_doc.get("sources")) if scanner_doc else {}
    markets = []
    for market in SCANNER_MARKETS:
        r, s = radar.get(market), scan.get(market)
        reason = None
        if scanner_doc is None:
            reason = "SCANNER_PUBLICATION_UNAVAILABLE"
        elif r is None:
            reason = "RADAR_SOURCE_ABSENT"
        elif s is None:
            reason = "SCANNER_SOURCE_ABSENT"
        elif not r.get("raw_sha256") or not s.get("raw_sha256"):
            reason = "CATALOGUE_DIGESTS_EMPTY"
        elif "UNAVAILABLE" in (r.get("catalogue_state"), s.get("catalogue_state")):
            reason = "CATALOGUE_UNAVAILABLE"
        if reason:
            relation = "NOT_COMPARABLE"
        elif r["raw_sha256"] == s["raw_sha256"]:
            relation = "SAME_CATALOGUE_BYTES"
        else:
            relation = "DIFFERENT_CATALOGUE_BYTES"
        markets.append({"market": market, "relation": relation, "reason": reason,
                        "radar_raw_sha256": (r or {}).get("raw_sha256"),
                        "scanner_raw_sha256": (s or {}).get("raw_sha256"),
                        "scanner_source_current": (s or {}).get("current")})
    relations = [m["relation"] for m in markets]
    if "NOT_COMPARABLE" in relations:
        overall = "CATALOGUE_PROVENANCE_UNKNOWN"
    elif all(r == "SAME_CATALOGUE_BYTES" for r in relations):
        overall = "CATALOGUE_PROVENANCE_MATCH"
    else:
        overall = "CATALOGUE_PROVENANCE_MISMATCH"
    compared = None
    if scanner_doc is not None:
        compared = {"schema_version": scanner_doc.get("schema_version"), "status": scanner_doc.get("status"),
                    "computed_ms": scanner_doc.get("computed_ms"),
                    "scanner_universe_sha256_of_compared_publication": scanner_doc.get("universe_sha256")}
    return {"relation": overall, "statement": E1_STATEMENT, "markets": markets,
            "scanner_publication": compared,
            "scanner_error_code": None if scanner_doc is not None else (
                getattr(scanner, "error_code", None) or "SCANNER_READER_NOT_WIRED"),
            # The projection itself keeps scanner_universe.sha256 = null (NOT_AVAILABLE).
            "radar_scanner_universe_sha256": projection["scanner_universe"]["sha256"]}


class RadarProjectionReader:
    def __init__(self, path=None, *, scanner_read=None, now_fn=None, max_age_ms=None):
        configured = os.getenv(PATH_ENV) if path is None else path
        self.path = Path(configured) if configured else None
        self.scanner_read = scanner_read
        self.now_fn = now_fn or (lambda: time.time_ns() // 1_000_000)
        self.max_age_ms, self.max_age_basis = _max_age_ms(max_age_ms)

    def read(self) -> RadarProjectionReadResult:
        def failure(code, refusal=None):
            return RadarProjectionReadResult(False, error_code="RADAR_PROJECTION_" + code, refusal_code=refusal)

        if self.path is None:
            return failure("NOT_CONFIGURED")
        got = read_regular_file(self.path, pc.MAX_EXPORT_BYTES)
        if got.error:
            return failure(got.error)
        try:
            projection_bytes = project_bytes(got.raw)
        except ProjectionRefusal as exc:
            return failure("REFUSED", exc.code)
        projection = json.loads(projection_bytes)
        scanner = self.scanner_read() if self.scanner_read else None
        service = {
            "schema": SERVICE_SCHEMA,
            "projection_schema": projection["schema"],
            "projection_sha256": projection["projection_sha256"],
            "status": SERVICE_STATUS,
            "scope": {"evidence_kind": projection["evidence"]["kind"], "runtime_proof": False,
                      "statement": SCOPE_STATEMENT},
            "publication": publication_freshness(got.mtime_ms, self.now_fn(), self.max_age_ms, self.max_age_basis),
            "catalogue_provenance": catalogue_provenance(projection, scanner),
        }
        # The projection bytes are embedded verbatim (keys sorted: "projection" < "service"),
        # so the whole body is itself the canonical form of {"projection", "service"}.
        body = b'{"projection":' + projection_bytes.rstrip(b"\n") + b',"service":' + canonical(service) + b"}"
        return RadarProjectionReadResult(True, body=body)
