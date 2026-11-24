"""Groupe G — R1-B : lot radar-batch, références, adaptateurs Scanner et BBO.

SYNTHETIC uniquement, hors réseau. Plan accepté le 2026-11-24 (T01–T18, R02–R14 ;
R01 = suite R0 inchangée, groupes A à F). Les cas d'exécution du CLI passent par
des processus séparés : la garde hors réseau est irréversible dans un processus.
"""
import copy
import hashlib
import json
import os

import pytest

from observability.radar_selection import adapter_bbo as bbo
from observability.radar_selection import contract as c
from observability.radar_selection.batch import load_batch, refs, verify_batch
from observability.radar_selection.batch_build import build_batch, spec_refs
from observability.radar_selection.engine import evaluate, evaluate_batch
from observability.radar_selection.fixture import RadarRefusal, canonical
from observability.radar_selection.refs import evidence_root, read_ref
from tests.radar_selection import build_batches as bb
from tests.radar_selection._helpers import NAMES, ROOT, cli, codes, doc, market, path, python

EVIDENCE = bb.EVIDENCE
BATCH = EVIDENCE / bb.BATCH
SPEC = json.loads((EVIDENCE / bb.SPEC).read_text(encoding="utf-8"))
ALL_BLOBS = {str(p.relative_to(EVIDENCE)): p.read_bytes() for p in EVIDENCE.rglob("*") if p.is_file()}
KRAKEN_BTC = "kraken:spot:BTC/USDT"
KRAKEN_ATOM = "kraken:spot:ATOM/USDT"
MEXC_BTC = "mexc:spot:BTC/USDT"
MEXC_ATOM = "mexc:spot:ATOM/USDT"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def batch_doc() -> dict:
    return json.loads(BATCH.read_bytes())


def blobs() -> dict:
    return dict(ALL_BLOBS)


def run(d: dict | bytes, bl: dict | None = None, mission="DEEP_OBSERVATION") -> dict:
    raw = d if isinstance(d, bytes) else canonical(d)
    return evaluate_batch(raw, blobs() if bl is None else bl, None, mission)


def refused(ev: dict) -> dict:
    return {(r["venue"], r["native_symbol"]): r["reason"] for r in ev["inputs"]["refused_observations"]}


def rebuilt(spec_patch=None, blob_patch=None) -> tuple:
    """Rebuild a batch from the spec after patching blobs (re-pinning what changed)."""
    spec = copy.deepcopy(SPEC)
    bl = blobs()
    if blob_patch:
        blob_patch(bl)
    for s in spec["bbo_sources"]:
        s["anchor_sha256"] = sha(bl[s["anchor_ref"]])
        s["manifest_sha256"] = sha(bl[s["manifest_ref"]])
    spec["scanner_manifest_sha256"] = sha(bl[f"{spec['scanner_run']}/manifest.json"])
    if spec_patch:
        spec_patch(spec)
    return build_batch(spec, bl), bl


def edit_json(bl: dict, ref: str, fn) -> None:
    d = json.loads(bl[ref])
    fn(d)
    bl[ref] = (json.dumps(d, indent=1, sort_keys=True) + "\n").encode()


def repin_anchor_window(bl: dict, pair: str, index: int, new_bytes: bytes) -> None:
    def fn(a):
        for p in a["pairs"]:
            if p["pair"] == pair:
                p["provenance"]["window_sha256"][index] = sha(new_bytes)
    edit_json(bl, "bbo/bbo-composite-history.json", fn)


def fixture_as_batch(name: str) -> tuple:
    """An R0 radar-fixture expressed as a SYNTHETIC radar-batch with inline observations."""
    d = doc(name)
    bl, cat_refs, docs = {}, {}, {}
    for n, e in d["catalogues"].items():
        raw = canonical(e["body"]) if e["body"] is not None else None
        if raw is not None:
            bl[f"cat/{n}.json"] = raw
        cat_refs[n] = {"ref": f"cat/{n}.json" if raw else None, "sha256": sha(raw) if raw else None,
                       "bytes": len(raw) if raw else None, "received_ms": e["received_ms"], "error": e["error"]}
        docs[n] = {"url": "fixture", "received_ms": e["received_ms"], "error": e["error"], "http_status": None,
                   "sha256": cat_refs[n]["sha256"], "bytes": cat_refs[n]["bytes"]}
    manifest = json.dumps({"run_id": "FIXTURE", "documents": docs}).encode()
    bl["cat/manifest.json"] = manifest
    obs = []
    for o in d["observations"]:
        o = dict(o)
        o["source_id"] = None
        o["unknown_reasons"] = {}
        if o["l2"] is not None:
            o["l2"] = {**o["l2"], "scope": None}
        obs.append(o)
    batch = {"batch_schema": c.BATCH_SCHEMA, "adapter_version": c.ADAPTER_VERSION,
             "dataset_id": d["dataset_id"], "description": d["description"], "evidence_kind": "SYNTHETIC",
             "evaluation_time_ms": d["evaluation_time_ms"], "policy": d["policy"],
             "catalogue_manifest": {"ref": "cat/manifest.json", "sha256": sha(manifest)},
             "catalogue_refs": cat_refs, "source_access": d["source_access"],
             "previous_universe": d["previous_universe"], "sources": [], "observations": obs}
    return batch, bl


# ------------------------------------------------------------------ T01–T18

def test_T01_same_batch_same_bytes_same_digests():
    raw = BATCH.read_bytes()
    a, b = evaluate_batch(raw, blobs()), evaluate_batch(raw, blobs())
    assert canonical(a) == canonical(b)
    assert a["evaluation_sha256"] == b["evaluation_sha256"]
    assert a["dataset"]["sha256"] == sha(raw)


def test_T02_raw_catalogue_bytes_with_fractions_reach_parse_all_untouched(monkeypatch):
    raw_pairs = ALL_BLOBS[f"{bb.RUN}/kraken_asset_pairs.json"]
    assert b"0.26" in raw_pairs and b"0.0001" in ALL_BLOBS[f"{bb.RUN}/mexc_contract_detail.json"]
    seen = {}
    import observability.radar_selection.universe as uni
    real = uni.parse_all

    def spy(documents):
        seen.update({k: v["raw"] for k, v in documents.items()})
        return real(documents)
    monkeypatch.setattr(uni, "parse_all", spy)
    ev = run(batch_doc())
    for name in bb.URLS:
        assert seen[name] == ALL_BLOBS[f"{bb.RUN}/{name}.json"]
        assert seen[name] is not None
    manifest = json.loads(ALL_BLOBS[f"{bb.RUN}/manifest.json"])
    src = {s["market"]: s for s in ev["sources"]}
    assert src["KRAKEN_SPOT"]["raw_sha256"]["kraken_asset_pairs"] == manifest["documents"]["kraken_asset_pairs"]["sha256"]
    assert all(s["catalogue_state"] == "COMPLETE" for s in ev["sources"])
    assert market(ev, KRAKEN_BTC)["catalogue"]["provenance"] == "SCANNER_RAW_CATALOGUE"


def test_T03_falsified_catalogue_or_manifest_is_unavailable_never_invented():
    bl = blobs()
    bl[f"{bb.RUN}/kraken_assets.json"] = bl[f"{bb.RUN}/kraken_assets.json"] + b" "
    ev = run(batch_doc(), bl)
    assert ev["inputs"]["catalogues"]["kraken_assets"]["reason"] == "REF_SIZE_MISMATCH"
    src = {s["market"]: s for s in ev["sources"]}
    assert src["KRAKEN_SPOT"]["catalogue_state"] == "UNAVAILABLE"
    assert not any(m["venue"] == "kraken" and m["market_type"] == "SPOT" for m in ev["markets"])
    # Same size, other bytes.
    bl = blobs()
    data = bytearray(bl[f"{bb.RUN}/kraken_assets.json"])
    data[-2:-1] = b" "
    bl[f"{bb.RUN}/kraken_assets.json"] = bytes(data)
    ev = run(batch_doc(), bl)
    assert ev["inputs"]["catalogues"]["kraken_assets"]["reason"] == "REF_SHA_MISMATCH"
    # Falsified manifest: no catalogue is trusted.
    d = batch_doc()
    d["catalogue_manifest"]["sha256"] = "0" * 64
    ev = run(d)
    assert ev["inputs"]["catalogue_manifest"]["state"] == "REFUSED"
    assert all(s["catalogue_state"] == "UNAVAILABLE" for s in ev["sources"])
    assert ev["markets"] == [] and ev["candidates"] == []


def test_T04_altered_window_refuses_its_source_only():
    bl = blobs()
    ref = "bbo/BBO-BTC-DRY/replay/window_0_primary.json"
    bl[ref] = bl[ref].replace(b'"instant_ms"', b'"instant_ms" ', 1)
    ev = run(batch_doc(), bl)
    src = {s["source_id"]: s for s in ev["inputs"]["sources"]}
    assert src["bbo:BBO-BTC-DRY"]["state"] == "REFUSED"
    assert src["bbo:BBO-BTC-DRY"]["reason"] == "SOURCE_ARTIFACT_SHA_MISMATCH"
    assert src["bbo:BBO-ATOM-DRY"]["state"] == "VERIFIED"
    m = market(ev, MEXC_BTC)
    assert m["observation"]["present"] is False and m["observation"]["reason"] == "SOURCE_ARTIFACT_SHA_MISMATCH"
    assert m["lifecycle"]["recent_data"] == "UNKNOWN"
    assert market(ev, MEXC_ATOM)["observation"]["present"] is True


def test_T05_price_kind_mixed_is_refused():
    d = batch_doc()
    o = next(o for o in d["observations"] if o["native_symbol"] == "ATOMUSDT" and o["venue"] == "mexc")
    o["price_kind"] = "LAST_TRADE"
    ev = run(d)
    assert refused(ev)[("mexc", "ATOMUSDT")] == "PRICE_KIND_MIXED"


def test_T06_quote_mismatch_is_non_admissible():
    d = batch_doc()
    o = next(o for o in d["observations"] if o["native_symbol"] == "ATOMUSDT" and o["venue"] == "mexc")
    o["source_id"] = None              # inline synthetic, so the identity rule of R0 decides
    o["declared_quote"] = "USD"
    m = market(run(d), MEXC_ATOM)
    assert m["admissibility"]["decision"] == "NON_ADMISSIBLE"
    assert "IDENTITY_CONFLICT_DECLARED_QUOTE" in codes(m)
    # From a source, any change of the published observation is refused.
    d = batch_doc()
    o = next(o for o in d["observations"] if o["native_symbol"] == "ATOMUSDT" and o["venue"] == "mexc")
    o["declared_quote"] = "USD"
    assert refused(run(d))[("mexc", "ATOMUSDT")] == "OBSERVATION_NOT_DERIVED_FROM_SOURCE"


def test_T07_contract_type_mismatch_never_merges_perpetuals():
    # The BBO manifest binds a SPOT instrument; a non-spot binding is refused.
    def patch(bl):
        edit_json(bl, "bbo/BBO-ATOM-DRY/manifest.json", lambda m: m["instrument"].update(market_kind="PERPETUAL"))
    with pytest.raises(RadarRefusal) as e:
        rebuilt(blob_patch=patch)
    assert e.value.code in ("MANIFEST_INSTRUMENT", "MANIFEST_NOT_BOUND_TO_ANCHOR")
    # A spot observation never lands on a perpetual market (identity key includes the market type).
    d = batch_doc()
    o = next(o for o in d["observations"] if o["native_symbol"] == "ATOMUSDT" and o["venue"] == "mexc")
    o["source_id"], o["market_type"] = None, "PERPETUAL"
    ev = run(d)
    assert any(x["native_symbol"] == "ATOMUSDT" and x["market_type"] == "PERPETUAL"
               for x in ev["orphan_observations"])


def test_T08_activity_unknown_with_reason_never_zero():
    ev = run(batch_doc())
    for mid in (KRAKEN_ATOM, MEXC_ATOM, KRAKEN_BTC, MEXC_BTC):
        m = market(ev, mid)
        act = m["criteria"]["activity_volatility"]["activity"]
        assert act["state"] == "UNKNOWN" and act["reason"] == "TRADE_CHANNEL_NOT_CAPTURED"
        if m["score"]:
            assert "activity" in m["score"]["missing"] and "activity" not in m["score"]["components"]


def test_T09_depth_unknown_when_levels_absent():
    ev = run(batch_doc())
    for mid in (KRAKEN_ATOM, MEXC_ATOM):
        depth = market(ev, mid)["criteria"]["spread_depth"]["depth"]
        assert depth["state"] == "UNKNOWN" and depth["reason"] == "DEPTH_LEVELS_NOT_IN_ARTIFACT"
        assert "bid_quote_10bps" not in depth


def test_T10_invalid_instants_are_omitted_and_cited():
    # Natural case: the synthetic transport leaves one Kraken BTC instant FRESHNESS_UNKNOWN.
    d = batch_doc()
    k = next(o for o in d["observations"] if o["venue"] == "kraken" and o["native_symbol"] == "XBTUSDT")
    scope = k["l2"]["scope"]
    assert scope["grid_instants"] == 60 and scope["valid_instants"] == 59
    assert [e["reason"] for e in scope["excluded_instants"]] == ["STATE_FRESHNESS_UNKNOWN"]
    assert all(s["t_ms"] is not None for s in k["samples"]) and len(k["samples"]) == 59
    t = scope["excluded_instants"][0]["t_ms"]
    assert t not in [s["t_ms"] for s in k["samples"]]
    # Unit level: every other invalid state is omitted with its reason, never a null time.
    w = json.loads(ALL_BLOBS["bbo/BBO-BTC-DRY/replay/window_0_primary.json"])
    w["points"][3]["sources"]["kraken"].update(continuity="CONTINUITY_LOST")
    w["points"][4]["sources"]["kraken"].update(eligible=False, state="NOT_INITIALIZED")
    w["points"][5]["sources"] = None
    binding = {"native": {"mexc": "BTCUSDT", "kraken": "XBTUSDT"}, "base": "BTC", "quote": "USDT"}
    obs = {o["venue"]: o for o in bbo.project("bbo:x", [w], binding)}
    reasons = [e["reason"] for e in obs["kraken"]["l2"]["scope"]["excluded_instants"]]
    assert reasons == ["CONTINUITY_CONTINUITY_LOST", "STATE_NOT_INITIALIZED", "NOT_EVALUATED"]
    assert len(obs["kraken"]["samples"]) == 27 and len(obs["mexc"]["samples"]) == 29
    cont = market(evaluate_batch(BATCH.read_bytes(), blobs()), KRAKEN_BTC)["criteria"]["continuity"]
    assert cont["covered"] == 59 and cont["expected"] == 60


def test_T11_window_beyond_coverage():
    d = batch_doc()
    s = next(s for s in d["sources"] if s["source_id"] == "bbo:BBO-ATOM-DRY")
    o = next(o for o in d["observations"] if o["source_id"] == s["source_id"] and o["venue"] == "mexc")
    o["window"]["start_ms"] = s["coverage"]["start_ms"] - o["window"]["step_ms"]
    assert refused(run(d))[("mexc", "ATOMUSDT")] == "WINDOW_BEYOND_COVERAGE"
    d = batch_doc()
    d["sources"][0]["coverage"]["end_ms"] += 10_000
    ev = run(d)
    assert ev["inputs"]["sources"][0]["reason"] == "SOURCE_COVERAGE_MISMATCH"


def test_T12_missing_reference_keeps_markets_unknown():
    bl = blobs()
    del bl["bbo/BBO-ATOM-DRY/replay/window_2_primary.json"]
    ev = run(batch_doc(), bl)
    atom = next(s for s in ev["inputs"]["sources"] if s["source_id"] == "bbo:BBO-ATOM-DRY")
    assert atom["state"] == "REFUSED" and atom["reason"] == "SOURCE_ARTIFACT_SHA_MISMATCH"
    full = run(batch_doc())
    assert ev["counts"]["discovered"] == full["counts"]["discovered"]
    m = market(ev, MEXC_ATOM)
    assert m["observation"]["present"] is False and m["admissibility"]["decision"] == "UNKNOWN"
    # A whole catalogue missing: its markets become a visible UNAVAILABLE source, not an empty list.
    bl = blobs()
    del bl[f"{bb.RUN}/mexc_spot_exchange_info.json"]
    ev = run(batch_doc(), bl)
    assert ev["inputs"]["catalogues"]["mexc_spot_exchange_info"]["reason"] == "REF_MISSING"
    assert {s["market"]: s["catalogue_state"] for s in ev["sources"]}["MEXC_SPOT"] == "UNAVAILABLE"


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d["sources"].extend([copy.deepcopy(d["sources"][0])] * c.MAX_BATCH_SOURCES), "SOURCES_BOUND"),
    (lambda d: d["sources"][0]["artifacts"].extend([d["sources"][0]["artifacts"][0]] * c.MAX_WINDOWS_PER_OBSERVATION),
     "ARTIFACTS_BOUND"),
    (lambda d: d["sources"][0]["artifacts"][0].update(bytes=c.MAX_ARTIFACT_BYTES + 1), "INTEGER_EXPECTED"),
    (lambda d: d["observations"][0]["samples"].extend([d["observations"][0]["samples"][0]] * 300), "SAMPLES_BOUND"),
    (lambda d: d["observations"][0]["l2"]["scope"]["excluded_instants"].extend(
        [{"t_ms": 1, "reason": "X"}] * (c.MAX_EXCLUDED_INSTANTS + 1)) if d["observations"][0]["l2"]
        and d["observations"][0]["l2"]["scope"] else d["observations"][1]["l2"]["scope"]["excluded_instants"].extend(
        [{"t_ms": 1, "reason": "X"}] * (c.MAX_EXCLUDED_INSTANTS + 1)), "EXCLUDED_INSTANTS_BOUND"),
])
def test_T13_every_ceiling_refuses_with_a_stable_code(mutate, code):
    d = batch_doc()
    mutate(d)
    with pytest.raises(RadarRefusal) as e:
        load_batch(canonical(d))
    assert e.value.code == code


def test_T13_observation_byte_ceiling():
    import dataclasses
    small = dataclasses.replace(c.TEST_BUDGETS, max_observation_bytes=512)
    with pytest.raises(RadarRefusal) as e:
        load_batch(BATCH.read_bytes(), small)
    assert e.value.code == "OBSERVATION_TOO_LARGE"


def test_T13_input_and_reference_ceilings(tmp_path):
    with pytest.raises(RadarRefusal) as e:
        load_batch(b"{" + b" " * c.TEST_BUDGETS.max_input_bytes + b"}")
    assert e.value.code == "INPUT_TOO_LARGE"
    root = evidence_root(tmp_path)
    (tmp_path / "big.json").write_bytes(b"x" * 101)
    with pytest.raises(RadarRefusal) as e:
        read_ref(root, "big.json", 100)
    assert e.value.code == "REF_TOO_LARGE"
    d = batch_doc()
    for i in range(c.MAX_REFS):
        d["sources"][0]["artifacts"] = d["sources"][0]["artifacts"][:1]
    d["sources"] = [dict(d["sources"][0], source_id=f"s{i}",
                         artifacts=[dict(d["sources"][0]["artifacts"][0], ref=f"w/{i}/{j}.json") for j in range(8)])
                    for i in range(9)]
    d["observations"] = []
    with pytest.raises(RadarRefusal) as e:
        load_batch(canonical(d))
    assert e.value.code == "REFS_BOUND"


def test_T14_imports_and_offline_guard_with_evidence_root(tmp_path):
    rc, out, err = python(
        "import sys\nfrom observability.radar_selection import batch, batch_build, refs, adapter_bbo, "
        "adapter_scanner, engine, terminal\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('socket', 'ssl', 'subprocess', 'threading', "
        "'asyncio', 'trade_analysis', 'market_data', 'paper_trading', 'core') "
        "or m in ('urllib.request', 'http.client', 'observability.radar_composite.bbo_pilot'))\nprint(bad)", tmp_path)
    assert rc == 0, err
    assert out.strip() == "[]"
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    code = ("from pathlib import Path\nfrom observability.radar_selection.terminal import install_offline_guard\n"
            f"install_offline_guard(None, read_roots=[{str(EVIDENCE)!r}])\n"
            f"Path({str(EVIDENCE / bb.BATCH)!r}).read_bytes()\n"
            "try:\n"
            f"    Path({str(outside)!r}).read_bytes()\n    print('READ')\n"
            "except PermissionError as e:\n    print(e)\n"
            "import socket\n"
            "try:\n    socket.create_connection(('192.0.2.1', 443), timeout=1)\nexcept PermissionError as e:\n    print(e)\n"
            "try:\n    open('/tmp/r1b_guard_probe', 'w')\nexcept PermissionError as e:\n    print(e)\n")
    rc, out, err = python(code, tmp_path)
    assert rc == 0, err
    lines = out.split()
    assert "RADAR_READ_OUTSIDE_EVIDENCE_ROOT" in lines[0]
    assert lines[1].startswith("RADAR_OFFLINE_GUARD:socket")
    assert "RADAR_WRITE_OUTSIDE_STATE_DIR" in lines[2]


def test_T15_reference_stays_out_of_ranking_even_historical():
    ev = run(batch_doc())
    assert ev["reference"]["market_id"] == KRAKEN_BTC and ev["reference"]["in_ranking"] is False
    assert ev["reference"]["historical_admission"] == "NOT_YET_HISTORICALLY_ADMITTED"
    assert KRAKEN_BTC not in [x["market_id"] for x in ev["candidates"]]
    assert ev["dataset"]["admission"] == "NONE"
    hist = historical_batch()
    ev = run(*hist)
    assert ev["dataset"]["evidence_kind"] == "HISTORICAL" and ev["mode"]["evidence"] == "HISTORICAL"
    assert ev["dataset"]["admission"] == "NONE"
    assert KRAKEN_BTC not in [x["market_id"] for x in ev["candidates"]]
    assert ev["reference"]["historical_admission"] == "NOT_YET_HISTORICALLY_ADMITTED"
    for cand in ev["candidates"]:
        assert cand["limits"][0].startswith("Données HISTORICAL hors ligne")
        assert cand["status"] == "PROPOSED_NOT_AUTHORIZED"
    assert ev["deep_observation_jobs"] == []


def historical_batch() -> tuple:
    """The same evidence relabelled as a collected corpus (pilot kind OBSERVATION), read as a
    HISTORICAL batch, in memory only (code path test, not an admission)."""
    def patch(bl):
        edit_json(bl, "bbo/bbo-composite-history.json",
                  lambda a: [a.update(evidence_kind="OBSERVATION")] + [p.update(evidence_kind="OBSERVATION")
                                                                       for p in a["pairs"]])
        for pair in bb.BBO_PAIRS:
            edit_json(bl, f"bbo/BBO-{pair}-DRY/manifest.json", lambda m: m.update(evidence_kind="OBSERVATION"))

    def spec_patch(s):
        s["evidence_kind"] = "HISTORICAL"
    batch, bl = rebuilt(spec_patch, patch)
    return batch, bl


@pytest.mark.parametrize("kind", ["LIVE", "live", "PAPER", None])
def test_T16_live_or_unknown_evidence_kind_refused(kind):
    d = batch_doc()
    d["evidence_kind"] = kind
    with pytest.raises(RadarRefusal) as e:
        load_batch(canonical(d))
    assert e.value.code == "EVIDENCE_KIND_NOT_ALLOWED"


SCIENTIFIC = ("criteria", "admissibility", "score", "lifecycle", "manual", "change", "previous")
# Allowed differences, listed explicitly: dataset identity and input schema, catalogue provenance label.
ALLOWED_TOP = {"dataset", "inputs", "evaluation_sha256", "budgets"}


@pytest.mark.parametrize("name", NAMES)
def test_T17_same_science_from_fixture_or_batch(name):
    a = evaluate(path(name).read_bytes())
    batch, bl = fixture_as_batch(name)
    b = evaluate_batch(canonical(batch), bl)
    assert (a["rules_version"], a["ranking_version"], a["schema_version"]) == \
        (b["rules_version"], b["ranking_version"], b["schema_version"])
    assert set(a) == set(b)
    for k in set(a) - ALLOWED_TOP - {"markets"}:
        assert canonical(a[k]) == canonical(b[k]), k
    assert len(a["markets"]) == len(b["markets"])
    for ma, mb in zip(a["markets"], b["markets"]):
        for k in SCIENTIFIC:
            assert canonical(ma[k]) == canonical(mb[k]), (ma["market_id"], k)
        # Everything else per market is identical too, except the catalogue provenance label.
        assert set(ma) == set(mb)
        for k in set(ma) - {"catalogue"}:
            assert canonical(ma[k]) == canonical(mb[k]), (ma["market_id"], k)
        if ma["catalogue"]["provenance"] == "SYNTHETIC_FIXTURE_CATALOGUE":
            assert mb["catalogue"]["provenance"] == "SCANNER_RAW_CATALOGUE"
        else:   # e.g. PREVIOUS_CYCLE_IDENTITY for a market gone from the catalogue
            assert mb["catalogue"]["provenance"] == ma["catalogue"]["provenance"]
        assert {**ma["catalogue"], "provenance": None} == {**mb["catalogue"], "provenance": None}
    assert a["dataset"]["schema"] == c.FIXTURE_SCHEMA and b["dataset"]["schema"] == c.BATCH_SCHEMA


def test_T18_interrupted_write_leaves_nothing_and_resumes(tmp_path):
    from observability.radar_selection import batch_build
    state = tmp_path / "state"
    state.mkdir()
    real_write = os.write

    def boom(fd, data):
        real_write(fd, data[: len(data) // 2])
        raise OSError("disk")
    batch_build.os.write = boom
    try:
        with pytest.raises(OSError):
            batch_build._write_new(state, "lot.json", b"x" * 100)
    finally:
        batch_build.os.write = real_write
    assert sorted(p.name for p in state.iterdir()) == []
    dest = batch_build._write_new(state, "lot.json", b"x" * 100)
    assert dest.read_bytes() == b"x" * 100
    with pytest.raises(FileExistsError):
        batch_build._write_new(state, "lot.json", b"y")
    assert dest.read_bytes() == b"x" * 100
    # Same inputs, same document.
    first = bb.batch_bytes(EVIDENCE, blobs())
    assert first == bb.batch_bytes(EVIDENCE, blobs()) == BATCH.read_bytes()


# ------------------------------------------------------------------ R02–R14

def test_R02_radar_fixture_unchanged_refusals():
    d = doc("calm")
    d["evidence_kind"] = "HISTORICAL"
    with pytest.raises(RadarRefusal) as e:
        evaluate(canonical(d))
    assert e.value.code == "EVIDENCE_KIND_NOT_ALLOWED_IN_R0"
    with pytest.raises(RadarRefusal) as e:
        evaluate(path("calm").read_bytes().replace(b'"dataset_id"', b'"x": 0.5, "dataset_id"', 1))
    assert e.value.code == "FLOAT_NOT_ALLOWED"
    d = doc("calm")
    o = next(o for o in d["observations"] if o["l2"])
    o["l2"]["status"] = "VERIFIED_TOP_N"
    with pytest.raises(RadarRefusal) as e:
        evaluate(canonical(d))
    assert e.value.code == "VALUE_NOT_ALLOWED"


@pytest.mark.parametrize("field,value,code", [
    ("depth_levels", None, "L2_TOP_N_DEPTH_LEVELS_REQUIRED"),
    ("scope", None, "L2_TOP_N_SCOPE_REQUIRED"),
])
def test_R03_top_n_needs_depth_levels_and_scope(field, value, code):
    d = batch_doc()
    k = next(o for o in d["observations"] if o["l2"] and o["l2"]["status"] == "VERIFIED_TOP_N")
    k["l2"][field] = value
    with pytest.raises(RadarRefusal) as e:
        load_batch(canonical(d))
    assert e.value.code == code
    d = batch_doc()
    k = next(o for o in d["observations"] if o["l2"] and o["l2"]["status"] == "VERIFIED_TOP_N")
    m = next(o for o in d["observations"] if o["l2"] and o["l2"]["status"] == "TECHNICALLY_COMPATIBLE")
    m["l2"]["scope"] = copy.deepcopy(k["l2"]["scope"])
    with pytest.raises(RadarRefusal) as e:
        load_batch(canonical(d))
    assert e.value.code == "L2_SCOPE_ONLY_FOR_TOP_N"


def test_R04_no_source_observation_claims_a_verified_book():
    d = batch_doc()
    statuses = {o["l2"]["status"] for o in d["observations"] if o["l2"]}
    assert statuses == {"VERIFIED_TOP_N", "TECHNICALLY_COMPATIBLE"}
    batch, _ = historical_batch()
    assert "VERIFIED" not in {o["l2"]["status"] for o in batch["observations"] if o["l2"]}
    k = next(o for o in d["observations"] if o["l2"] and o["l2"]["status"] == "VERIFIED_TOP_N")
    k["l2"].update(status="VERIFIED", scope=None)
    with pytest.raises(RadarRefusal) as e:
        load_batch(canonical(d))
    assert e.value.code == "L2_VERIFIED_NOT_ALLOWED_FROM_SOURCE"


def test_R05_top_n_is_to_qualify_for_l2_depth_study():
    ev = run(batch_doc(), mission="L2_DEPTH_STUDY")
    m = market(ev, KRAKEN_ATOM)
    assert m["criteria"]["l2_quality"]["proof"] == "PROVEN_TOP_N"
    assert m["criteria"]["l2_quality"]["state"] == "PARTIAL"
    assert ("A_QUALIFIER", "L2_VERIFIED_TOP_N_ONLY") in [(r["decision"], r["code"]) for r in m["admissibility"]["reasons"]]
    assert m["admissibility"]["decision"] != "ADMISSIBLE"


def test_R06_top_n_weight_is_the_transitional_40_points():
    assert c.L2_POINTS == {"VERIFIED": 100, "VERIFIED_TOP_N": 40, "TECHNICALLY_COMPATIBLE": 40}
    assert c.RANKING_VERSION == "radar-ranking/1.2.0"
    ev = run(batch_doc())
    k, m = market(ev, KRAKEN_ATOM), market(ev, MEXC_ATOM)
    assert k["score"]["components"]["l2"] == 40 == m["score"]["components"]["l2"]


def test_R07_published_mid_mismatch_is_refused_not_corrected():
    w = json.loads(ALL_BLOBS["bbo/BBO-BTC-DRY/replay/window_0_primary.json"])
    s = w["points"][2]["sources"]["mexc"]
    s["mid"] = str(__import__("decimal").Decimal(s["mid"]) + __import__("decimal").Decimal("0.01"))
    binding = {"native": {"mexc": "BTCUSDT", "kraken": "XBTUSDT"}, "base": "BTC", "quote": "USDT"}
    with pytest.raises(bbo.ObservationRefusal) as e:
        bbo.project("bbo:x", [w], binding)
    assert e.value.code == "MID_REPRESENTATION_MISMATCH" and e.value.venue == "mexc"
    d = batch_doc()
    o = next(o for o in d["observations"] if o["venue"] == "mexc" and o["native_symbol"] == "ATOMUSDT")
    o["samples"][0]["price"] = str(__import__("decimal").Decimal(o["samples"][0]["price"]) + 1)
    assert refused(run(d))[("mexc", "ATOMUSDT")] == "OBSERVATION_NOT_DERIVED_FROM_SOURCE"


def test_R08_non_contiguous_windows_refused():
    spec = copy.deepcopy(SPEC)
    atom = next(s for s in spec["bbo_sources"] if s["pair"] == "ATOM")
    atom["window_refs"] = [atom["window_refs"][0], atom["window_refs"][2]]
    with pytest.raises(RadarRefusal) as e:
        build_batch(spec, blobs())
    assert e.value.code == "WINDOW_GRID_MISMATCH"


def test_R09_window_absent_from_anchor_refused():
    def patch(bl):
        repin_anchor_window(bl, "ATOM", 0, b"other")
    batch = batch_doc()
    bl = blobs()
    patch(bl)
    for s in batch["sources"]:
        s["anchor"]["sha256"] = sha(bl[s["anchor"]["ref"]])
    ev = run(batch, bl)
    atom = next(s for s in ev["inputs"]["sources"] if s["source_id"] == "bbo:BBO-ATOM-DRY")
    assert atom["reason"] in ("ARTIFACT_NOT_IN_ANCHOR", "ANCHOR_INVALID")


@pytest.mark.parametrize("ref,code", [
    ("../outside.json", "REF_SYNTAX"), ("/etc/passwd", "REF_SYNTAX"), ("a//b.json", "REF_SYNTAX"),
    ("./a.json", "REF_SYNTAX"), ("a\\b.json", "REF_SYNTAX"), ("é.json", "REF_SYNTAX"),
    ("link.json", "REF_SYMLINK"), ("dirlink/f.json", "REF_SYMLINK"), ("sub", "REF_NOT_REGULAR"),
    ("fifo", "REF_NOT_REGULAR"), ("nothere.json", "REF_MISSING"),
])
def test_R10_reference_resolution_refusals(tmp_path, ref, code):
    root_dir = tmp_path / "root"
    (root_dir / "sub").mkdir(parents=True)
    (root_dir / "sub" / "f.json").write_text("{}")
    (tmp_path / "outside.json").write_text("{}")
    os.symlink(tmp_path / "outside.json", root_dir / "link.json")
    os.symlink(tmp_path, root_dir / "dirlink")
    os.mkfifo(root_dir / "fifo")
    root = evidence_root(root_dir)
    with pytest.raises(RadarRefusal) as e:
        read_ref(root, ref, 1000)
    assert e.value.code == code
    assert read_ref(root, "sub/f.json", 1000) == b"{}"
    os.symlink(root_dir, tmp_path / "rootlink")
    with pytest.raises(RadarRefusal) as e:
        evidence_root(tmp_path / "rootlink")
    assert e.value.code == "EVIDENCE_ROOT_NOT_A_DIRECTORY"


def test_R11_scanner_error_keeps_its_code():
    def patch(bl):
        edit_json(bl, f"{bb.RUN}/manifest.json", lambda m: m["documents"]["mexc_contract_detail"].update(
            sha256=None, bytes=None, error="TRANSPORT_URLError", http_status=None))
    batch, bl = rebuilt(blob_patch=patch)
    assert batch["catalogue_refs"]["mexc_contract_detail"]["ref"] is None
    ev = run(batch, bl)
    rec = ev["inputs"]["catalogues"]["mexc_contract_detail"]
    assert rec["state"] == "UNAVAILABLE" and rec["reason"] == "TRANSPORT_URLError"
    src = {s["market"]: s for s in ev["sources"]}
    assert src["MEXC_PERPETUAL"]["catalogue_state"] == "UNAVAILABLE"


def test_R12_fixtures_are_reproducible():
    for rel, data in bb.generated().items():
        assert (EVIDENCE / rel).read_bytes() == data, rel
    prov = json.loads((EVIDENCE / "bbo" / "PROVENANCE.json").read_text())
    assert "SYNTHETIC" in prov["transport"]
    anchor = json.loads(ALL_BLOBS["bbo/bbo-composite-history.json"])
    assert anchor["evidence_kind"] == "SYNTHETIC"


def test_R13_batch_spec_and_refs_cover_exactly_the_evidence_used():
    d = batch_doc()
    wanted = set(refs(d))
    assert wanted <= set(ALL_BLOBS)
    assert set(spec_refs(SPEC)) <= wanted
    verified = verify_batch(load_batch(BATCH.read_bytes())["doc"], {k: ALL_BLOBS[k] for k in wanted})
    assert verified["inputs"]["refused_observations"] == []
    assert all(s["state"] == "VERIFIED" for s in verified["inputs"]["sources"])


def test_R14_terminal_shows_kind_scope_and_admission(tmp_path):
    rc, out, err = cli(["--batch", str(BATCH), "--evidence-root", str(EVIDENCE), "--width", "100",
                        "inspect", KRAKEN_ATOM], tmp_path)
    assert rc == 0, err
    assert "MODE: SYNTHETIC / OFFLINE" in out and "ADMISSION: NONE" in out
    flat = " ".join(out.split())   # the line wraps at the terminal width
    assert "carnet vérifié sur 10 niveaux (KRAKEN_CRC32), 90 instants valides sur 90" in flat
    assert "carnet vérifié" not in flat.replace("carnet vérifié sur", "")
    assert "preuve PROVEN_TOP_N" in flat and "motif : L2_VERIFIED_TOP_N_ONLY" in flat
    rc, out, err = cli(["--batch", str(BATCH), "--evidence-root", str(EVIDENCE), "evidence", KRAKEN_ATOM], tmp_path)
    assert rc == 0 and "bbo:BBO-ATOM-DRY · VERIFIED · corpus BBO-ATOM-DRY" in out
    assert "mathieu" not in out.lower() and "/home/" not in out
    rc, out, err = cli(["--batch", str(BATCH), "status"], tmp_path)
    assert rc == 4 and "BATCH_NEEDS_EVIDENCE_ROOT_AND_NO_FIXTURE" in err
    outside = tmp_path / "ev"
    outside.mkdir()
    rc, out, err = cli(["--batch", str(BATCH), "--evidence-root", str(outside), "status"], tmp_path)
    assert rc != 0
    assert tuple(sorted(p.name for p in tmp_path.iterdir())) == ("ev",)


def test_R14_batch_build_cli_writes_only_in_state_dir(tmp_path):
    state = tmp_path / "state"
    rc, out, err = _build_cli(["--evidence-root", str(EVIDENCE), "--spec", bb.SPEC, "--state-dir", str(state),
                               "--out", "lot.json"], tmp_path)
    assert rc == 0, err
    assert (state / "lot.json").read_bytes() == BATCH.read_bytes()
    assert "admission : NONE" in out
    rc, out, err = _build_cli(["--evidence-root", str(EVIDENCE), "--spec", bb.SPEC, "--state-dir", str(state),
                               "--out", "lot.json"], tmp_path)
    assert rc == 3
    assert sorted(p.name for p in state.iterdir()) == ["lot.json"]


def _build_cli(args, cwd):
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-m", "observability.radar_selection.batch_build", *args], cwd=cwd,
                       capture_output=True, text=True, env=env, timeout=60)
    return p.returncode, p.stdout, p.stderr


def test_R02_batch_kind_must_match_the_pilot_kind_of_every_source():
    # A HISTORICAL batch reads only corpora the pilot recorded as OBSERVATION; a SYNTHETIC
    # dry-run cannot be relabelled HISTORICAL (and MIXED is never accepted).
    with pytest.raises(RadarRefusal) as e:
        rebuilt(lambda s: s.update(evidence_kind="HISTORICAL"))
    assert e.value.code == "EVIDENCE_KIND_MIXED"
    batch, bl = historical_batch()
    batch["evidence_kind"] = "SYNTHETIC"
    ev = run(batch, bl)
    assert {s["state"] for s in ev["inputs"]["sources"]} == {"REFUSED"}


def test_R10_global_refusal_versus_local_degradation_in_the_cli(tmp_path):
    """Contract § 9: a dangerous reference refuses the whole batch; a missing one degrades its source."""
    import shutil
    ev_dir = tmp_path / "ev"
    shutil.copytree(EVIDENCE, ev_dir)
    window = ev_dir / "bbo" / "BBO-ATOM-DRY" / "replay" / "window_2_primary.json"
    window.unlink()
    rc, out, err = cli(["--batch", str(ev_dir / bb.BATCH), "--evidence-root", str(ev_dir), "evidence",
                        MEXC_ATOM], tmp_path)
    assert rc == 0, err
    assert "SOURCE_ARTIFACT_SHA_MISMATCH" in out
    (tmp_path / "elsewhere.json").write_bytes(ALL_BLOBS["bbo/BBO-ATOM-DRY/replay/window_2_primary.json"])
    os.symlink(tmp_path / "elsewhere.json", window)
    rc, out, err = cli(["--batch", str(ev_dir / bb.BATCH), "--evidence-root", str(ev_dir), "status"], tmp_path)
    assert rc == 3 and "REF_SYMLINK" in err and out == ""
