"""S4-b — GET service of the verified Radar projection (SB1 to SB10).

SYNTHETIC, offline. The reader reads one configured export file, calls the
S4-a ``project_bytes`` and serves those bytes verbatim inside a service
envelope carrying E2 (publication freshness) and E1 (catalogue provenance
against the Scanner publication). No collector, no score recomputation.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from observability.operator_api import radar_projection_reader as rr
from observability.operator_api.radar_projection_reader import RadarProjectionReader
from observability.operator_api.scanner_universe_reader import ScannerUniverseReader
from observability.radar_projection import contract as pc
from observability.radar_projection.projection import project_bytes
from observability.radar_selection.fixture import canonical, sha256_hex
from observability.scanner_universe.collect import encode, replay
from tests.radar_projection._exports import ARCHIVE, BATCH, CASES, ROOT, export, loads, reseal

SCANNER_RUN = ROOT / "tests" / "radar_selection" / "evidence" / "scanner" / "runs" / "20261117T163500Z"
READER = ROOT / "observability" / "operator_api" / "radar_projection_reader.py"
NOW = 1_800_000_000_000


def write(tmp_path: Path, raw: bytes, name="radar-export.json", mtime_ms=NOW) -> Path:
    p = tmp_path / name
    p.write_bytes(raw)
    os.utime(p, ns=(mtime_ms * 1_000_000, mtime_ms * 1_000_000))
    return p


def scanner_doc() -> dict:
    return replay(SCANNER_RUN)


def scanner_reader(tmp_path: Path, doc=None):
    p = write(tmp_path, encode(scanner_doc() if doc is None else doc), name="scanner-universe.json")
    return ScannerUniverseReader(p, now_fn=lambda: NOW).read


def reader(tmp_path, raw, *, now=NOW, scanner=None, mtime_ms=NOW, max_age_ms=None):
    return RadarProjectionReader(write(tmp_path, raw, mtime_ms=mtime_ms), scanner_read=scanner,
                                 now_fn=lambda: now, max_age_ms=max_age_ms)


def served(tmp_path, raw, **kw) -> dict:
    result = reader(tmp_path, raw, **kw).read()
    assert result.ok, (result.error_code, result.refusal_code)
    return json.loads(result.body)


# ---------------------------------------------------------------- SB1 verbatim projection
@pytest.mark.parametrize("source,mission", CASES)
def test_SB1_projection_bytes_are_served_verbatim(tmp_path, source, mission):
    raw = export(source, mission)
    result = reader(tmp_path, raw, scanner=scanner_reader(tmp_path)).read()
    assert result.ok
    expected = project_bytes(raw).rstrip(b"\n")
    assert result.body.startswith(b'{"projection":' + expected + b',"service":')
    doc = json.loads(result.body)
    assert canonical(doc) == result.body  # the whole body is canonical
    assert set(doc) == {"projection", "service"}
    assert doc["service"]["projection_sha256"] == doc["projection"]["projection_sha256"]
    body = {k: v for k, v in doc["projection"].items() if k != "projection_sha256"}
    assert sha256_hex(canonical(body)) == doc["projection"]["projection_sha256"]


def test_SB1_service_envelope_shape(tmp_path):
    s = served(tmp_path, export(BATCH), scanner=scanner_reader(tmp_path))["service"]
    assert set(s) == {"schema", "projection_schema", "projection_sha256", "status", "scope", "publication",
                      "catalogue_provenance"}
    assert s["schema"] == "radar-projection-service/1.0.0"
    assert s["projection_schema"] == pc.PROJECTION_SCHEMA
    assert s["status"] == "PRESENTATION_ONLY_NOT_AN_ADMISSION_NOT_A_RUNTIME_AUTHORIZATION"


# ---------------------------------------------------------------- SB2 typed read errors
def test_SB2_not_configured(monkeypatch):
    monkeypatch.delenv(rr.PATH_ENV, raising=False)
    assert RadarProjectionReader().read().error_code == "RADAR_PROJECTION_NOT_CONFIGURED"


def test_SB2_missing_directory_symlink_and_too_large(tmp_path):
    assert RadarProjectionReader(tmp_path / "absent.json").read().error_code == "RADAR_PROJECTION_MISSING"
    assert RadarProjectionReader(tmp_path).read().error_code == "RADAR_PROJECTION_INVALID_PATH"
    target = write(tmp_path, export("r0_syn_01_calm"))
    link = tmp_path / "link.json"
    link.symlink_to(target)
    assert RadarProjectionReader(link).read().error_code == "RADAR_PROJECTION_INVALID_PATH"
    big = write(tmp_path, b" " * (pc.MAX_EXPORT_BYTES + 1), name="big.json")
    assert RadarProjectionReader(big).read().error_code == "RADAR_PROJECTION_TOO_LARGE"


def test_SB2_symlinked_parent_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    write(real, export("r0_syn_01_calm"))
    (tmp_path / "alias").symlink_to(real)
    assert RadarProjectionReader(tmp_path / "alias" / "radar-export.json").read().error_code == \
        "RADAR_PROJECTION_INVALID_PATH"


def _swap_on_first_open(monkeypatch, real_dir, alias_target):
    """Replace ``real_dir`` by a symlink after every name-based check, at the reader's first open."""
    real_open = os.open

    def racing_open(name, flags, *args, **kwargs):
        if not real_dir.is_symlink():
            real_dir.rename(alias_target)
            real_dir.symlink_to(alias_target)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", racing_open)


def test_SB2_parent_swapped_for_symlink_during_resolution_is_refused(tmp_path, monkeypatch):
    # S4-B-RV1: the parent is a real directory when the path is examined and becomes a symlink
    # just before it is opened. The component-wise O_NOFOLLOW walk must refuse it.
    pub = tmp_path / "pub"
    pub.mkdir()
    write(pub, export("r0_syn_01_calm"))
    _swap_on_first_open(monkeypatch, pub, tmp_path / "elsewhere")
    assert RadarProjectionReader(pub / "radar-export.json").read().error_code == "RADAR_PROJECTION_INVALID_PATH"


def test_SB2_final_component_swapped_for_symlink_is_refused(tmp_path, monkeypatch):
    target = write(tmp_path, export("r0_syn_01_calm"), name="real.json")
    p = tmp_path / "radar-export.json"
    real_open = os.open

    def racing_open(name, flags, *args, **kwargs):
        if name == "radar-export.json" and not p.is_symlink():
            p.symlink_to(target)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", racing_open)
    assert RadarProjectionReader(p).read().error_code == "RADAR_PROJECTION_INVALID_PATH"


def test_SB2_no_name_based_symlink_check_is_relied_upon(tmp_path, monkeypatch):
    # Even if every name-based check lied, the kernel-level refusal still holds.
    real = tmp_path / "real"
    real.mkdir()
    write(real, export("r0_syn_01_calm"))
    (tmp_path / "alias").symlink_to(real)
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    assert RadarProjectionReader(tmp_path / "alias" / "radar-export.json").read().error_code == \
        "RADAR_PROJECTION_INVALID_PATH"


def test_SB2_dotdot_is_refused_and_relative_path_is_read(tmp_path, monkeypatch):
    sub = tmp_path / "sub"
    sub.mkdir()
    write(tmp_path, export("r0_syn_01_calm"))
    assert RadarProjectionReader(sub / ".." / "radar-export.json").read().error_code == \
        "RADAR_PROJECTION_INVALID_PATH"
    monkeypatch.chdir(tmp_path)
    assert RadarProjectionReader(Path("./radar-export.json")).read().ok


def test_SB2_file_changing_during_read_is_refused(tmp_path, monkeypatch):
    p = write(tmp_path, export("r0_syn_01_calm"))
    real = os.fstat
    calls = []

    def fstat(fd):
        st = real(fd)
        calls.append(1)
        if len(calls) == 2:
            os.utime(p, ns=(1, 1))
            return real(fd)
        return st

    monkeypatch.setattr(os, "fstat", fstat)
    assert RadarProjectionReader(p).read().error_code == "RADAR_PROJECTION_CHANGED_DURING_READ"


# ---------------------------------------------------------------- SB3 verifier refusals stay typed
@pytest.mark.parametrize("path", sorted(p for p in ARCHIVE.rglob("*.json") if p.name != "MANIFEST.json")[:3],
                         ids=lambda p: p.name)
def test_SB3_pre_rref_archive_is_refused_not_served(tmp_path, path):
    r = reader(tmp_path, path.read_bytes()).read()
    assert not r.ok and r.body is None
    assert (r.error_code, r.refusal_code) == ("RADAR_PROJECTION_REFUSED", "PRE_RREF_EVALUATION")


@pytest.mark.parametrize("raw,code", [
    (b"", "INPUT_EMPTY"),
    (b"\xff\xfe", "INPUT_MALFORMED"),
    (b'{"a":1.5}', "FLOAT_NOT_ALLOWED"),
])
def test_SB3_malformed_input_gives_the_verifier_code(tmp_path, raw, code):
    r = reader(tmp_path, raw).read()
    assert (r.error_code, r.refusal_code) == ("RADAR_PROJECTION_REFUSED", code)


def test_SB3_resealed_forgery_is_refused_and_refusal_carries_no_input(tmp_path):
    d = loads(export("r0_syn_04_incoherent"))
    d["authority"]["execution_authority"] = True
    d["mode"]["network"] = "X" * 10_000
    r = reader(tmp_path, reseal(d)).read()
    assert r.error_code == "RADAR_PROJECTION_REFUSED"
    assert r.refusal_code.isupper() and ":" not in r.refusal_code and len(r.refusal_code) <= 64


def test_SB3_historical_and_live_are_refused(tmp_path):
    d = loads(export(BATCH))
    d["dataset"]["evidence_kind"] = "LIVE"
    assert reader(tmp_path, reseal(d)).read().refusal_code == "EVIDENCE_LIVE_REFUSED"


# ---------------------------------------------------------------- SB4 E2 publication freshness
@pytest.mark.parametrize("age,state", [(0, "FRESH"), (900_000, "FRESH"), (900_001, "STALE"),
                                       (-5_000, "FRESH"), (-5_001, "PUBLISHED_IN_FUTURE")])
def test_SB4_publication_freshness(tmp_path, age, state):
    pub = served(tmp_path, export("r0_syn_01_calm"), now=NOW + age)["service"]["publication"]
    assert pub == {"published_ms": NOW, "published_basis": "FILE_MODIFICATION_TIME", "served_ms": NOW + age,
                   "age_ms": age, "max_age_ms": 900_000, "max_age_basis": "PROVISIONAL_DEFAULT", "state": state,
                   "current": state == "FRESH"}


def test_SB4_stale_publication_is_served_but_not_current_and_projection_unchanged(tmp_path):
    raw = export("r0_syn_04_incoherent")
    fresh = served(tmp_path, raw)
    stale = served(tmp_path, raw, now=NOW + 10**9)
    assert stale["service"]["publication"]["current"] is False
    assert stale["projection"] == fresh["projection"]


@pytest.mark.parametrize("env,ms,basis", [("60", 60_000, "CONFIGURED"), ("", 900_000, "PROVISIONAL_DEFAULT"),
                                          ("0", 900_000, "PROVISIONAL_DEFAULT_INVALID_CONFIGURATION"),
                                          ("-5", 900_000, "PROVISIONAL_DEFAULT_INVALID_CONFIGURATION"),
                                          ("abc", 900_000, "PROVISIONAL_DEFAULT_INVALID_CONFIGURATION"),
                                          ("9" * 4000, 900_000, "PROVISIONAL_DEFAULT_INVALID_CONFIGURATION")])
def test_SB4_max_age_configuration(monkeypatch, env, ms, basis):
    monkeypatch.setenv(rr.MAX_AGE_ENV, env)
    r = RadarProjectionReader("x")
    assert (r.max_age_ms, r.max_age_basis) == (ms, basis)


def test_SB4_freshness_is_never_inside_the_projection(tmp_path):
    a = served(tmp_path, export(BATCH), now=NOW)
    b = served(tmp_path, export(BATCH), now=NOW + 123_456)
    assert a["projection"] == b["projection"]
    assert not {"published_ms", "served_ms", "age_ms"} & set(a["projection"])


# ---------------------------------------------------------------- SB5 E1 catalogue provenance
def test_SB5_same_catalogue_bytes_is_a_match_not_an_identity(tmp_path):
    doc = served(tmp_path, export(BATCH), scanner=scanner_reader(tmp_path))
    e1 = doc["service"]["catalogue_provenance"]
    assert e1["relation"] == "CATALOGUE_PROVENANCE_MATCH"
    assert [m["relation"] for m in e1["markets"]] == ["SAME_CATALOGUE_BYTES"] * 4
    assert [m["market"] for m in e1["markets"]] == list(pc.SCANNER_MARKETS)
    assert e1["statement"] == "CATALOGUE_BYTES_PROVENANCE_ONLY_NOT_UNIVERSE_IDENTITY"
    # The projection keeps its E1 state: the scanner universe digest is still not carried.
    assert doc["projection"]["scanner_universe"]["sha256"] is None
    assert doc["projection"]["scanner_universe"]["state"] == "NOT_AVAILABLE"
    assert e1["radar_scanner_universe_sha256"] is None
    text = json.dumps(e1)
    assert "SAME_UNIVERSE" not in text and "UNIVERSE_MATCH" not in text


def test_SB5_one_changed_catalogue_is_a_mismatch(tmp_path):
    d = scanner_doc()
    d["sources"][0]["raw_sha256"] = {k: "0" * 64 for k in d["sources"][0]["raw_sha256"]}
    e1 = served(tmp_path, export(BATCH), scanner=scanner_reader(tmp_path, d))["service"]["catalogue_provenance"]
    assert e1["relation"] == "CATALOGUE_PROVENANCE_MISMATCH"
    assert [m["relation"] for m in e1["markets"]].count("DIFFERENT_CATALOGUE_BYTES") == 1


def test_SB5_r0_fixtures_never_match_real_catalogue_bytes(tmp_path):
    e1 = served(tmp_path, export("r0_syn_01_calm"), scanner=scanner_reader(tmp_path))["service"]["catalogue_provenance"]
    assert e1["relation"] in ("CATALOGUE_PROVENANCE_MISMATCH", "CATALOGUE_PROVENANCE_UNKNOWN")
    assert "SAME_CATALOGUE_BYTES" not in [m["relation"] for m in e1["markets"]]


def test_SB5_unavailable_scanner_gives_unknown_never_a_match(tmp_path):
    for scanner, code in [(None, "SCANNER_READER_NOT_WIRED"),
                          (ScannerUniverseReader(None).read, "SCANNER_UNIVERSE_NOT_CONFIGURED"),
                          (ScannerUniverseReader(tmp_path / "none.json").read, "SCANNER_UNIVERSE_MISSING")]:
        e1 = served(tmp_path, export(BATCH), scanner=scanner)["service"]["catalogue_provenance"]
        assert e1["relation"] == "CATALOGUE_PROVENANCE_UNKNOWN"
        assert e1["scanner_error_code"] == code and e1["scanner_publication"] is None
        assert {m["reason"] for m in e1["markets"]} == {"SCANNER_PUBLICATION_UNAVAILABLE"}


@pytest.mark.parametrize("mutate,reason", [
    (lambda d: d["sources"][1].update(raw_sha256={}), "CATALOGUE_DIGESTS_EMPTY"),
    (lambda d: d["sources"][2].update(catalogue_state="UNAVAILABLE", current=False), "CATALOGUE_UNAVAILABLE"),
])
def test_SB5_one_non_comparable_market_makes_the_relation_unknown(mutate, reason):
    # Applied to an accepted Scanner snapshot directly: the second case is not a valid
    # VERIFIED publication, so the Scanner reader itself would refuse it.
    d = scanner_doc()
    mutate(d)

    class Ok:
        ok, error_code, snapshot = True, None, d

    e1 = rr.catalogue_provenance(json.loads(project_bytes(export(BATCH))), Ok())
    assert e1["relation"] == "CATALOGUE_PROVENANCE_UNKNOWN"
    assert reason in [m["reason"] for m in e1["markets"]]


def test_SB5_relation_function_on_missing_sides():
    proj = json.loads(project_bytes(export(BATCH)))
    proj["scanner_universe"]["catalogue_sources"] = [
        x for x in proj["scanner_universe"]["catalogue_sources"] if x["market"] != "KRAKEN_PERPETUAL"]

    class Ok:
        ok, error_code = True, None
        snapshot = {"sources": [x for x in scanner_doc()["sources"] if x["market"] != "MEXC_SPOT"]}

    e1 = rr.catalogue_provenance(proj, Ok())
    assert e1["relation"] == "CATALOGUE_PROVENANCE_UNKNOWN"
    reasons = {m["reason"] for m in e1["markets"]}
    assert {"RADAR_SOURCE_ABSENT", "SCANNER_SOURCE_ABSENT"} <= reasons


# ---------------------------------------------------------------- SB6 scope and authority
def test_SB6_scope_is_explicitly_synthetic_and_authority_is_null(tmp_path):
    doc = served(tmp_path, export(BATCH))
    assert doc["service"]["scope"] == {"evidence_kind": "SYNTHETIC", "runtime_proof": False,
                                       "statement": "SYNTHETIC_SOURCE_PROOF_ONLY_NOT_RUNTIME_PROOF"}
    a = doc["projection"]["authority"]
    assert a["execution_authority"] is False and a["admission"] == "NONE" and a["deep_observation_jobs"] == []


# ---------------------------------------------------------------- SB7 determinism
def test_SB7_same_file_and_instant_give_identical_bytes(tmp_path):
    raw = export(BATCH)
    one = reader(tmp_path, raw, scanner=scanner_reader(tmp_path)).read().body
    two = reader(tmp_path, raw, scanner=scanner_reader(tmp_path)).read().body
    assert one == two


# ---------------------------------------------------------------- SB8 isolation of the reader
def test_SB8_reader_imports_no_engine_no_network_no_writer():
    tree = ast.parse(READER.read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(n.module)
    assert mods == {"__future__", "json", "os", "time", "dataclasses", "pathlib",
                    "observability.operator_api.bounded_file", "observability.radar_projection",
                    "observability.radar_projection.projection", "observability.radar_projection.verifier",
                    "observability.radar_selection.fixture"}
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not calls & {"open", "exec", "eval", "compile", "__import__"}
    src = READER.read_text(encoding="utf-8")
    for forbidden in ("evaluate", "select_candidates", "_build_projection", "score_market", "write_bytes"):
        assert forbidden not in src


def test_SB8_reader_does_not_write(tmp_path):
    p = write(tmp_path, export(BATCH))
    before = sorted(x.name for x in tmp_path.iterdir())
    RadarProjectionReader(p, now_fn=lambda: NOW).read()
    assert sorted(x.name for x in tmp_path.iterdir()) == before


# ---------------------------------------------------------------- SB9 HTTP route (needs fastapi)
def _client(monkeypatch, tmp_path, raw, scanner=True):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from observability.operator_api import app as api

    if scanner:
        p = write(tmp_path, encode(scanner_doc()), name="scanner-universe.json")
        api.configure_scanner_universe_reader(p, now_fn=lambda: NOW)
    else:
        api.configure_scanner_universe_reader(None)
        monkeypatch.delenv("OPERATOR_SCANNER_UNIVERSE_PATH", raising=False)
        api.configure_scanner_universe_reader()
    api.configure_radar_projection_reader(write(tmp_path, raw) if raw is not None else None,
                                          now_fn=lambda: NOW)
    return TestClient(api.app), api


def test_SB9_route_serves_the_body_verbatim(monkeypatch, tmp_path):
    raw = export(BATCH)
    client, api = _client(monkeypatch, tmp_path, raw)
    try:
        r = client.get("/api/operator/v1/radar-projection")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert r.headers["cache-control"] == "no-store"
        assert b'{"projection":' + project_bytes(raw).rstrip(b"\n") in r.content
        assert r.json()["service"]["catalogue_provenance"]["relation"] == "CATALOGUE_PROVENANCE_MATCH"
        assert client.post("/api/operator/v1/radar-projection").status_code == 405
        # The existing Scanner route keeps working with the same publication.
        assert client.get("/api/operator/v1/scanner-universe").status_code == 200
    finally:
        api.configure_radar_projection_reader(None)
        api.configure_scanner_universe_reader(None)


def test_SB9_route_refusal_and_unconfigured_are_typed_503(monkeypatch, tmp_path):
    monkeypatch.delenv(rr.PATH_ENV, raising=False)
    client, api = _client(monkeypatch, tmp_path, None, scanner=False)
    try:
        api.configure_radar_projection_reader()
        r = client.get("/api/operator/v1/radar-projection")
        assert (r.status_code, r.json()) == (503, {"error_code": "RADAR_PROJECTION_NOT_CONFIGURED"})
        archived = sorted(p for p in ARCHIVE.rglob("*.json") if p.name != "MANIFEST.json")[0]
        api.configure_radar_projection_reader(write(tmp_path, archived.read_bytes()))
        r = client.get("/api/operator/v1/radar-projection")
        assert r.status_code == 503
        assert r.json() == {"error_code": "RADAR_PROJECTION_REFUSED", "refusal_code": "PRE_RREF_EVALUATION"}
        assert r.headers["cache-control"] == "no-store"
    finally:
        api.configure_radar_projection_reader(None)
        api.configure_scanner_universe_reader(None)


# ---------------------------------------------------------------- SB10 no new producer
def test_SB10_no_new_collector_timer_or_writer_in_this_change():
    app_src = (ROOT / "observability" / "operator_api" / "app.py").read_text(encoding="utf-8")
    route_lines = [line for line in app_src.splitlines() if "radar-projection" in line]
    assert route_lines == ['@app.get("/api/operator/v1/radar-projection")']
    assert "radar_selection" not in app_src  # the engine is never wired into the API
