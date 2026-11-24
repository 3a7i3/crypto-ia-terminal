"""R1-B — strict loading and verification of a ``radar-batch/1.0.0`` document (pure, no I/O).

A batch carries the minimal information the Radar needs and the references of
its proofs; raw market data stay with their producers. Contract:
``docs/contracts/CAT_R1B_CONTRAT_LOT_RADAR.md`` (operator decisions D1-D4 of
2026-11-24).

- ``load_batch`` checks the closed shape. A structural problem refuses the whole
  input with a stable code (never half-read).
- ``verify_batch`` receives the bytes of every reference (read by ``refs`` in the
  CLI, or built in memory by tests) and checks every fingerprint. The original
  catalogue bytes go to ``parse_all`` untouched. A failed source invalidates its
  own observations only; they stay visible as UNKNOWN with their code. Every
  source observation is re-derived from the verified windows and must be equal
  to the published one.

``evidence_kind`` is SYNTHETIC or HISTORICAL; LIVE is refused. HISTORICAL is an
offline input, never an admission (C2-C / C2-D stay UNKNOWN and outside).
"""
from __future__ import annotations

import re

from . import adapter_bbo as bbo
from . import adapter_scanner as scanner
from . import contract as c
from .fixture import (CATALOGUE_DOCUMENTS, POLICY_KEYS, PREVIOUS_KEYS, SCANNER_MARKETS, RadarRefusal, _dec,
                      _int, _keys, _opt_int, _str_list, _text, canonical, sha256_hex, strict_loads)

TOP_KEYS = {"batch_schema", "adapter_version", "dataset_id", "description", "evidence_kind",
            "evaluation_time_ms", "policy", "catalogue_manifest", "catalogue_refs", "source_access",
            "previous_universe", "sources", "observations"}
CAT_REF_KEYS = {"ref", "sha256", "bytes", "received_ms", "error"}
SOURCE_KEYS = {"source_id", "kind", "producer_module", "producer_commit", "corpus_id", "pair",
               "anchor", "manifest", "artifacts", "coverage"}
OBS_KEYS = {"venue", "market_type", "native_symbol", "declared_base", "declared_quote", "evidence_ref",
            "price_kind", "window", "samples", "activity", "l2", "cost", "source_id", "unknown_reasons"}
L2_KEYS = {"status", "evidence_ref", "depth_levels", "depth_quote_10bps", "scope"}
PRODUCER_MODULE = "observability.radar_composite.bbo_pilot"
_REF = re.compile(r"[A-Za-z0-9._-]{1,80}(/[A-Za-z0-9._-]{1,80}){0,7}", re.ASCII)
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_HEX40 = re.compile(r"[0-9a-f]{40}", re.ASCII)
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9:/_.~\-]{1,80}", re.ASCII)
_SCANNER_ERROR = re.compile(r"[A-Za-z0-9_]{1,80}", re.ASCII)
_PARSE_ALL_CODE = re.compile(r"[A-Z][A-Z0-9_]{1,79}", re.ASCII)


def _refuse(code: str, path: str = "") -> None:
    raise RadarRefusal(f"{code}:{path}" if path else code)


def valid_ref(ref) -> bool:
    """Relative POSIX path, no '.', '..', empty or absolute component (contract § 5)."""
    return isinstance(ref, str) and bool(_REF.fullmatch(ref)) \
        and all(part not in (".", "..") for part in ref.split("/"))


def _ref(v, path):
    if not valid_ref(v):
        _refuse("REF_SYNTAX", path)
    return v


def _sha(v, path):
    if not isinstance(v, str) or not _HEX64.fullmatch(v):
        _refuse("SHA256_EXPECTED", path)
    return v


def _pinned(v, path):
    _keys(v, {"ref", "sha256"}, path)
    _ref(v["ref"], path + ".ref")
    _sha(v["sha256"], path + ".sha256")


def _source(s, i):
    path = f"$.sources[{i}]"
    _keys(s, SOURCE_KEYS, path)
    if not isinstance(s["source_id"], str) or not _ID.fullmatch(s["source_id"]):
        _refuse("SOURCE_ID", path)
    if s["kind"] not in c.SOURCE_KINDS:
        _refuse("VALUE_NOT_ALLOWED", path + ".kind")
    if s["producer_module"] != PRODUCER_MODULE:
        _refuse("VALUE_NOT_ALLOWED", path + ".producer_module")
    if not isinstance(s["producer_commit"], str) or not _HEX40.fullmatch(s["producer_commit"]):
        _refuse("COMMIT_EXPECTED", path + ".producer_commit")
    if not isinstance(s["corpus_id"], str) or not _ID.fullmatch(s["corpus_id"]):
        _refuse("CORPUS_ID", path + ".corpus_id")
    _text(s["pair"], path + ".pair", nullable=False)
    _pinned(s["anchor"], path + ".anchor")
    _pinned(s["manifest"], path + ".manifest")
    arts = s["artifacts"]
    if not isinstance(arts, list) or not 1 <= len(arts) <= c.MAX_WINDOWS_PER_OBSERVATION:
        _refuse("ARTIFACTS_BOUND", path + ".artifacts")
    for j, a in enumerate(arts):
        ap = f"{path}.artifacts[{j}]"
        _keys(a, {"ref", "sha256", "bytes"}, ap)
        _ref(a["ref"], ap + ".ref")
        _sha(a["sha256"], ap + ".sha256")
        _int(a["bytes"], ap + ".bytes", 1, c.MAX_ARTIFACT_BYTES)
    cov = s["coverage"]
    _keys(cov, {"start_ms", "end_ms"}, path + ".coverage")
    _int(cov["start_ms"], path + ".coverage.start_ms", 1)
    _int(cov["end_ms"], path + ".coverage.end_ms", 1)
    if cov["end_ms"] <= cov["start_ms"]:
        _refuse("COVERAGE_EMPTY", path + ".coverage")


def _l2(l2, path, synthetic_inline):
    _keys(l2, L2_KEYS, path)
    if l2["status"] not in c.L2_STATUSES:
        _refuse("VALUE_NOT_ALLOWED", path + ".status")
    if l2["status"] == "VERIFIED" and not synthetic_inline:
        # No R1-B producer may claim a fully verified book (operator D3/D4).
        _refuse("L2_VERIFIED_NOT_ALLOWED_FROM_SOURCE", path + ".status")
    _text(l2["evidence_ref"], path + ".evidence_ref")
    _opt_int(l2["depth_levels"], path + ".depth_levels", 1, 10_000)
    d = l2["depth_quote_10bps"]
    if d is not None:
        _keys(d, {"bid", "ask"}, path + ".depth_quote_10bps")
        _dec(d["bid"], path + ".depth_quote_10bps.bid")
        _dec(d["ask"], path + ".depth_quote_10bps.ask")
    scope = l2["scope"]
    if l2["status"] != "VERIFIED_TOP_N":
        if scope is not None:
            _refuse("L2_SCOPE_ONLY_FOR_TOP_N", path + ".scope")
        return
    if l2["depth_levels"] is None:
        _refuse("L2_TOP_N_DEPTH_LEVELS_REQUIRED", path + ".depth_levels")
    if scope is None:
        _refuse("L2_TOP_N_SCOPE_REQUIRED", path + ".scope")
    _keys(scope, c.L2_SCOPE_KEYS, path + ".scope")
    if scope["verified_by"] not in c.L2_VERIFIERS:
        _refuse("VALUE_NOT_ALLOWED", path + ".scope.verified_by")
    valid = _int(scope["valid_instants"], path + ".scope.valid_instants", 1, 100_000)
    grid = _int(scope["grid_instants"], path + ".scope.grid_instants", 1, 100_000)
    ex = scope["excluded_instants"]
    if not isinstance(ex, list) or len(ex) > c.MAX_EXCLUDED_INSTANTS:
        _refuse("EXCLUDED_INSTANTS_BOUND", path + ".scope.excluded_instants")
    if valid + len(ex) != grid:
        _refuse("L2_SCOPE_COUNTS", path + ".scope")
    for k, e in enumerate(ex):
        _keys(e, {"t_ms", "reason"}, f"{path}.scope.excluded_instants[{k}]")
        _int(e["t_ms"], f"{path}.scope.excluded_instants[{k}].t_ms")
        if not isinstance(e["reason"], str) or not _CODE.fullmatch(e["reason"]):
            _refuse("ERROR_CODE", f"{path}.scope.excluded_instants[{k}].reason")


def _observation(o, i, budgets, evidence_kind):
    path = f"$.observations[{i}]"
    _keys(o, OBS_KEYS, path)
    if len(canonical(o)) > budgets.max_observation_bytes:
        _refuse("OBSERVATION_TOO_LARGE", path)
    synthetic_inline = o["source_id"] is None
    if synthetic_inline and evidence_kind != "SYNTHETIC":
        _refuse("HISTORICAL_OBSERVATION_WITHOUT_SOURCE", path)
    if not synthetic_inline and (not isinstance(o["source_id"], str) or not _ID.fullmatch(o["source_id"])):
        _refuse("SOURCE_ID", path + ".source_id")
    if o["venue"] not in c.VENUES:
        _refuse("VALUE_NOT_ALLOWED", path + ".venue")
    if o["market_type"] not in c.MARKET_TYPES:
        _refuse("VALUE_NOT_ALLOWED", path + ".market_type")
    _text(o["native_symbol"], path + ".native_symbol", nullable=False)
    for k in ("declared_base", "declared_quote"):
        _text(o[k], f"{path}.{k}")
    _text(o["evidence_ref"], path + ".evidence_ref", nullable=False)
    if o["price_kind"] not in c.PRICE_KINDS:
        _refuse("VALUE_NOT_ALLOWED", path + ".price_kind")
    w = o["window"]
    _keys(w, {"start_ms", "step_ms", "points"}, path + ".window")
    _int(w["start_ms"], path + ".window.start_ms", 1)
    _int(w["step_ms"], path + ".window.step_ms", 1, 86_400_000)
    _int(w["points"], path + ".window.points", 2, budgets.max_samples_per_observation)
    samples = o["samples"]
    if not isinstance(samples, list) or len(samples) > budgets.max_samples_per_observation:
        _refuse("SAMPLES_BOUND", path + ".samples")
    for j, s in enumerate(samples):
        sp = f"{path}.samples[{j}]"
        _keys(s, {"t_ms", "price", "bid", "ask"}, sp)
        _opt_int(s["t_ms"], sp + ".t_ms")
        for k in ("price", "bid", "ask"):
            _dec(s[k], f"{sp}.{k}")
    a = o["activity"]
    if a is not None:
        _keys(a, {"kind", "value", "evidence_ref"}, path + ".activity")
        _text(a["kind"], path + ".activity.kind", nullable=False)
        _opt_int(a["value"], path + ".activity.value")
        _text(a["evidence_ref"], path + ".activity.evidence_ref")
    if o["l2"] is not None:
        _l2(o["l2"], path + ".l2", synthetic_inline)
    cost = o["cost"]
    if cost is not None:
        _keys(cost, {"basis", "provenance", "network_kib_s", "cpu_pct", "memory_mib", "storage_mib_h",
                     "connections", "rate_limit_note"}, path + ".cost")
        if cost["basis"] not in c.COST_BASES or (cost["basis"] == "MEASURED" and not synthetic_inline):
            _refuse("VALUE_NOT_ALLOWED", path + ".cost.basis")
        _text(cost["provenance"], path + ".cost.provenance", nullable=False)
        for k in ("network_kib_s", "cpu_pct", "memory_mib", "storage_mib_h"):
            _dec(cost[k], f"{path}.cost.{k}")
        _opt_int(cost["connections"], path + ".cost.connections", 0, 1000)
        _text(cost["rate_limit_note"], path + ".cost.rate_limit_note")
    ur = o["unknown_reasons"]
    if not isinstance(ur, dict) or not set(ur) <= set(c.UNKNOWN_REASON_KEYS):
        _refuse("UNKNOWN_REASONS", path + ".unknown_reasons")
    present = {"activity": a is not None, "cost": cost is not None,
               "depth": o["l2"] is not None and o["l2"]["depth_quote_10bps"] is not None}
    for k, v in ur.items():
        if not isinstance(v, str) or not _CODE.fullmatch(v):
            _refuse("ERROR_CODE", f"{path}.unknown_reasons.{k}")
        if present[k]:
            _refuse("UNKNOWN_REASON_FOR_PRESENT_VALUE", f"{path}.unknown_reasons.{k}")


def load_batch(raw: bytes, budgets: c.Budgets = c.TEST_BUDGETS) -> dict:
    """Validate the closed shape of a batch and return it with its digest. Pure."""
    doc = strict_loads(raw, budgets.max_input_bytes)
    _keys(doc, TOP_KEYS, "$")
    if doc["batch_schema"] != c.BATCH_SCHEMA:
        _refuse("BATCH_SCHEMA", str(doc["batch_schema"])[:40])
    if doc["adapter_version"] != c.ADAPTER_VERSION:
        _refuse("ADAPTER_VERSION", str(doc["adapter_version"])[:40])
    if doc["evidence_kind"] not in c.BATCH_EVIDENCE_KINDS:
        _refuse("EVIDENCE_KIND_NOT_ALLOWED", str(doc["evidence_kind"])[:40])
    if not isinstance(doc["dataset_id"], str) or not _ID.fullmatch(doc["dataset_id"]):
        _refuse("DATASET_ID", "$.dataset_id")
    _text(doc["description"], "$.description", nullable=False)
    _int(doc["evaluation_time_ms"], "$.evaluation_time_ms", 1)
    p = doc["policy"]
    _keys(p, POLICY_KEYS, "$.policy")
    _str_list(p["venues"], "$.policy.venues", c.VENUES)
    _str_list(p["market_types"], "$.policy.market_types", c.MARKET_TYPES)
    _str_list(p["quotes"], "$.policy.quotes")
    _str_list(p["asset_classes"], "$.policy.asset_classes", ("CRYPTO", "STABLECOIN", "FIAT"))
    _str_list(p["deny"], "$.policy.deny")
    _pinned(doc["catalogue_manifest"], "$.catalogue_manifest")
    cats = doc["catalogue_refs"]
    _keys(cats, set(CATALOGUE_DOCUMENTS), "$.catalogue_refs")
    for name in CATALOGUE_DOCUMENTS:
        e, path = cats[name], f"$.catalogue_refs.{name}"
        _keys(e, CAT_REF_KEYS, path)
        _opt_int(e["received_ms"], path + ".received_ms", 1)
        if e["error"] is None:
            _ref(e["ref"], path + ".ref")
            _sha(e["sha256"], path + ".sha256")
            _int(e["bytes"], path + ".bytes", 1)
        elif not (isinstance(e["error"], str) and _SCANNER_ERROR.fullmatch(e["error"])) \
                or e["ref"] is not None or e["sha256"] is not None or e["bytes"] is not None:
            _refuse("REF_XOR_ERROR", path)
    access = doc["source_access"]
    if not isinstance(access, dict) or not set(access) <= set(SCANNER_MARKETS):
        _refuse("SOURCE_ACCESS", "$.source_access")
    for m, a in access.items():
        _keys(a, {"state", "reason"}, f"$.source_access.{m}")
        if a["state"] not in c.SOURCE_ACCESS[:3]:
            _refuse("VALUE_NOT_ALLOWED", f"$.source_access.{m}.state")
        if a["reason"] is not None and not _CODE.fullmatch(str(a["reason"])):
            _refuse("ERROR_CODE", f"$.source_access.{m}.reason")
    prev = doc["previous_universe"]
    if prev is not None:
        if not isinstance(prev, list) or len(prev) > c.MAX_FIXTURE_RECORDS:
            _refuse("PREVIOUS_UNIVERSE", "$.previous_universe")
        for i, e in enumerate(prev):
            _keys(e, PREVIOUS_KEYS, f"$.previous_universe[{i}]")
            if not isinstance(e["market_id"], str) or not _ID.fullmatch(e["market_id"]):
                _refuse("MARKET_ID", f"$.previous_universe[{i}].market_id")
            for k in ("native_symbol", "contract_type", "settlement_asset"):
                _text(e[k], f"$.previous_universe[{i}].{k}")
    sources = doc["sources"]
    if not isinstance(sources, list) or len(sources) > c.MAX_BATCH_SOURCES:
        _refuse("SOURCES_BOUND", "$.sources")
    for i, s in enumerate(sources):
        _source(s, i)
    ids = [s["source_id"] for s in sources]
    if len(set(ids)) != len(ids):
        _refuse("DUPLICATE_SOURCE_ID", "$.sources")
    obs = doc["observations"]
    if not isinstance(obs, list) or len(obs) > c.MAX_FIXTURE_RECORDS:
        _refuse("OBSERVATIONS_BOUND", "$.observations")
    for i, o in enumerate(obs):
        _observation(o, i, budgets, doc["evidence_kind"])
        if o["source_id"] is not None and o["source_id"] not in ids:
            _refuse("UNKNOWN_SOURCE_ID", f"$.observations[{i}].source_id")
    if len(refs(doc)) > c.MAX_REFS:
        _refuse("REFS_BOUND", "$")
    return {"doc": doc, "sha256": sha256_hex(bytes(raw)), "bytes": len(raw)}


def refs(doc: dict) -> dict:
    """Every reference of a loaded batch -> its size ceiling (what the CLI may read)."""
    from observability.scanner_universe.catalogues import MAX_RAW_BYTES
    out = {doc["catalogue_manifest"]["ref"]: c.MAX_ARTIFACT_BYTES}
    for e in doc["catalogue_refs"].values():
        if e["ref"] is not None:
            out[e["ref"]] = MAX_RAW_BYTES
    for s in doc["sources"]:
        out[s["anchor"]["ref"]] = c.MAX_ARTIFACT_BYTES
        out[s["manifest"]["ref"]] = c.MAX_ARTIFACT_BYTES
        for a in s["artifacts"]:
            out[a["ref"]] = c.MAX_ARTIFACT_BYTES
    return out


# ------------------------------------------------------------------ verification

def _blob(blobs: dict, ref: str, sha: str, size: int | None = None) -> bytes:
    data = blobs.get(ref)
    if data is None:
        raise RadarRefusal("REF_MISSING:" + ref)
    if size is not None and len(data) != size:
        raise RadarRefusal("REF_SIZE_MISMATCH:" + ref)
    if sha256_hex(data) != sha:
        raise RadarRefusal("REF_SHA_MISMATCH:" + ref)
    return data


def _catalogues(doc: dict, blobs: dict) -> tuple:
    """parse_all input from the original bytes, plus the verification record."""
    refs_ = doc["catalogue_refs"]
    record = {"catalogue_manifest": {**doc["catalogue_manifest"], "state": "VERIFIED", "reason": None},
              "catalogues": {}}
    manifest_error = None
    try:
        mraw = _blob(blobs, doc["catalogue_manifest"]["ref"], doc["catalogue_manifest"]["sha256"])
        entries = scanner.manifest_entries(mraw)
    except RadarRefusal as exc:
        manifest_error = "CATALOGUE_MANIFEST_" + exc.code
        record["catalogue_manifest"].update(state="REFUSED", reason=exc.code)
        entries = None
    documents = {}
    for name in CATALOGUE_DOCUMENTS:
        e = refs_[name]
        rec = {"ref": e["ref"], "sha256": e["sha256"], "state": "VERIFIED", "reason": None}
        if manifest_error:
            documents[name] = {"raw": None, "received_ms": None, "error": manifest_error}
            rec.update(state="REFUSED", reason=manifest_error)
        elif entries[name] != {k: e[k] for k in ("sha256", "bytes", "received_ms", "error")}:
            documents[name] = {"raw": None, "received_ms": None, "error": "CATALOGUE_REF_NOT_IN_MANIFEST"}
            rec.update(state="REFUSED", reason="CATALOGUE_REF_NOT_IN_MANIFEST")
        elif e["error"] is not None:
            # parse_all only takes upper-case codes; the Scanner's original text stays in the record.
            code = e["error"] if _PARSE_ALL_CODE.fullmatch(e["error"]) else "SCANNER_ERROR_NOT_CANONICAL"
            documents[name] = {"raw": None, "received_ms": e["received_ms"], "error": code}
            rec.update(state="UNAVAILABLE", reason=e["error"])
        else:
            try:
                raw = _blob(blobs, e["ref"], e["sha256"], e["bytes"])
                documents[name] = {"raw": raw, "received_ms": e["received_ms"], "error": None}
            except RadarRefusal as exc:
                documents[name] = {"raw": None, "received_ms": None, "error": exc.code}
                rec.update(state="REFUSED", reason=exc.code)
        record["catalogues"][name] = rec
    return documents, record


def _verify_source(s: dict, blobs: dict, evidence_kind: str) -> dict:
    """Verified windows and bindings of one source, or RadarRefusal with its code."""
    anchor = bbo.parse(_blob(blobs, s["anchor"]["ref"], s["anchor"]["sha256"]), "ANCHOR_MALFORMED")
    entry = bbo.anchor_pair(anchor, s["pair"])
    pv = entry["provenance"]
    if pv["collection_commit"] != s["producer_commit"]:
        raise RadarRefusal("PRODUCER_COMMIT_MISMATCH")
    if pv["archive_name"] != s["corpus_id"] + ".tar.gz":
        raise RadarRefusal("CORPUS_ID_MISMATCH")
    manifest = bbo.parse(_blob(blobs, s["manifest"]["ref"], s["manifest"]["sha256"]), "MANIFEST_MALFORMED")
    binding = bbo.bind_manifest(manifest, entry, evidence_kind)
    by_sha = {h: i for i, h in enumerate(pv["window_sha256"])}
    windows, positions = [], []
    for a in s["artifacts"]:
        if a["sha256"] not in by_sha:
            raise RadarRefusal("ARTIFACT_NOT_IN_ANCHOR:" + a["ref"])
        try:
            data = _blob(blobs, a["ref"], a["sha256"], a["bytes"])
        except RadarRefusal as exc:
            raise RadarRefusal("SOURCE_ARTIFACT_SHA_MISMATCH:" + exc.code) from None
        w = bbo.parse(data, "WINDOW_MALFORMED")
        pos = by_sha[a["sha256"]]
        if not isinstance(w, dict) or w.get("window", {}).get("index") != entry["windows"][pos]["index"]:
            raise RadarRefusal("WINDOW_NOT_AT_ANCHOR_POSITION")
        windows.append(w)
        positions.append(pos)
    if positions != list(range(positions[0], positions[0] + len(positions))):
        raise RadarRefusal("WINDOW_GRID_MISMATCH")
    cov = bbo.check_windows(windows, entry)
    if {"start_ms": cov["start_ms"], "end_ms": cov["end_ms"]} != s["coverage"]:
        raise RadarRefusal("SOURCE_COVERAGE_MISMATCH")
    return {"windows": windows, "binding": binding, "coverage": cov}


def verify_batch(doc: dict, blobs: dict) -> dict:
    """Check every reference of a loaded batch against the supplied bytes. Pure.

    Returns ``documents`` (parse_all input), the accepted ``observations`` and
    ``inputs``, the verification record published in the evaluation.
    """
    if not isinstance(blobs, dict) or not all(isinstance(v, (bytes, bytearray)) for v in blobs.values()):
        raise RadarRefusal("BLOBS_EXPECTED")
    documents, record = _catalogues(doc, blobs)
    sources_rec, verified = [], {}
    for s in doc["sources"]:
        rec = {"source_id": s["source_id"], "kind": s["kind"], "corpus_id": s["corpus_id"],
               "producer_commit": s["producer_commit"], "anchor_sha256": s["anchor"]["sha256"],
               "artifacts": len(s["artifacts"]), "state": "VERIFIED", "reason": None}
        try:
            verified[s["source_id"]] = _verify_source(s, blobs, doc["evidence_kind"])
            expected = {}
            try:
                for o in bbo.project(s["source_id"], verified[s["source_id"]]["windows"],
                                     verified[s["source_id"]]["binding"]):
                    expected[o["venue"]] = o
            except bbo.ObservationRefusal as exc:
                expected[exc.venue] = exc
            verified[s["source_id"]]["expected"] = expected
        except RadarRefusal as exc:
            rec.update(state="REFUSED", reason=exc.code)
            verified[s["source_id"]] = exc
        sources_rec.append(rec)

    accepted, refused = [], []
    for o in doc["observations"]:
        sid = o["source_id"]
        if sid is None:
            accepted.append(o)
            continue
        src = verified[sid]
        code = None
        if isinstance(src, RadarRefusal):
            code = src.code
        elif o["price_kind"] != bbo.PRICE_KIND:
            code = "PRICE_KIND_MIXED"
        else:
            cov, w = src["coverage"], o["window"]
            last = w["start_ms"] + (w["points"] - 1) * w["step_ms"]
            exp = src["expected"].get(o["venue"])
            if w["start_ms"] < cov["start_ms"] or last >= cov["end_ms"]:
                code = "WINDOW_BEYOND_COVERAGE"
            elif isinstance(exp, RadarRefusal):
                code = exp.code
            elif exp is None or canonical(exp) != canonical(o):
                code = "OBSERVATION_NOT_DERIVED_FROM_SOURCE"
        if code is None:
            accepted.append(o)
        else:
            refused.append({"venue": o["venue"], "market_type": o["market_type"],
                            "native_symbol": o["native_symbol"], "source_id": sid, "reason": code})
    refused.sort(key=lambda r: (r["venue"], r["market_type"], r["native_symbol"], r["source_id"]))
    return {"documents": documents, "observations": accepted,
            "inputs": {**record, "sources": sources_rec, "refused_observations": refused}}
