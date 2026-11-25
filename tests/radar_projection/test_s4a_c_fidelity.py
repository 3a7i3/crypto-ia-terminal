"""S4-a — SA5 (scientific fields faithful), SA6 (unknown states preserved), SA8 (deterministic).

Differential tests over the 15 current exports (4 fixtures + 1 batch, 3 missions),
with and without operator preferences. Equality is checked on the canonical form,
so ``null``, ``0`` and ``false`` stay distinct.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from observability.radar_projection import contract as pc
from observability.radar_projection.projection import build_projection, project, projection_bytes
from observability.radar_projection.verifier import IDENTITY_KEYS, verify_export
from observability.radar_selection.fixture import canonical, sha256_hex
from tests.radar_projection._exports import BATCH, CASES, ROOT, export, loads, prefs
from tests.radar_selection._helpers import session

SAME = canonical  # strict equality helper: compare canonical bytes


def same(a, b) -> bool:
    return SAME(a) == SAME(b)


def check_faithful(raw: bytes) -> dict:
    src = loads(raw)
    p = project(raw)
    assert p["source"] == {"evaluation_schema": src["schema_version"], "rules_version": src["rules_version"],
                           "ranking_version": src["ranking_version"], "evaluation_sha256": src["evaluation_sha256"],
                           "export_sha256": sha256_hex(raw), "export_bytes": len(raw)}
    for key in ("dataset", "inputs", "mission", "policy", "candidates", "candidates_empty_reason", "budgets",
                "evaluation_time_ms"):
        assert same(p[key], src[key]), key
    assert same(p["evidence"], {"kind": src["dataset"]["evidence_kind"], "mode": src["mode"]})
    assert same(p["population"], {"counts": src["counts"], "orphan_observations": src["orphan_observations"]})
    assert same(p["preferences"], {"preferences_sha256": src["preferences_sha256"], "manual": src["manual"]})
    assert same(p["scanner_universe"]["catalogue_sources"], src["sources"])
    assert same({k: p["authority"][k] for k in src["authority"]}, src["authority"])
    assert p["authority"]["admission"] == src["dataset"]["admission"] == "NONE"
    assert p["authority"]["deep_observation_jobs"] == src["deep_observation_jobs"] == []
    ranks = {c["market_id"]: c["rank"] for c in src["candidates"]}
    assert len(p["instruments"]) == len(src["markets"])
    for inst, m in zip(p["instruments"], src["markets"]):
        assert same(inst["identity"], {k: m[k] for k in IDENTITY_KEYS})
        for k in ("catalogue", "change", "previous", "lifecycle", "observation", "admissibility", "criteria",
                  "score", "manual"):
            assert same(inst[k], m[k]), (m["market_id"], k)
        assert inst["rank"] == ranks.get(m["market_id"])
    # Nothing scientific is lost: every market field is carried by exactly one projection field.
    assert set(inst) - {"identity", "rank"} | set(IDENTITY_KEYS) == set(m)
    return p


@pytest.mark.parametrize("source,mission", CASES)
def test_SA5_projection_is_faithful_to_the_export(source, mission):
    p = check_faithful(export(source, mission))
    assert p["mission"]["id"] == mission


@pytest.mark.parametrize("source", ["r0_syn_04_incoherent", "r0_syn_01_calm", BATCH])
def test_SA5_operator_preferences_are_carried_not_applied(source):
    first = loads(export(source))
    top = first["candidates"][0]["market_id"]
    other = first["markets"][0]["market_id"]
    p = prefs(selected=[other, "ghost:spot:NONE/NONE"], pinned=[other], excluded=[top])
    raw = export(source, prefs=p)
    proj = check_faithful(raw)
    assert top not in [c["market_id"] for c in proj["candidates"]]
    inst = {i["identity"]["market_id"]: i for i in proj["instruments"]}
    assert inst[top]["manual"]["excluded"] is True
    # Exclusion is an operator preference: decision and score are unchanged.
    assert same(inst[top]["admissibility"], next(m for m in first["markets"] if m["market_id"] == top)["admissibility"])
    ghost = [it for it in proj["preferences"]["manual"]["selected"] if it["market_id"] == "ghost:spot:NONE/NONE"]
    assert ghost == [{"market_id": "ghost:spot:NONE/NONE", "present": False, "decision": "UNKNOWN",
                      "presented_as_admissible": False, "note": "NOT_IN_UNIVERSE"}]


def test_SA5_all_admissible_excluded_keeps_the_engine_reason():
    first = loads(export("r0_syn_04_incoherent"))
    scored = [m["market_id"] for m in first["markets"] if m["score"] is not None]
    proj = check_faithful(export("r0_syn_04_incoherent", prefs=prefs(excluded=scored)))
    assert proj["candidates"] == [] and proj["candidates_empty_reason"] == "ADMISSIBLE_MARKETS_ALL_EXCLUDED"


def test_SA5_rank_is_the_published_rank_and_null_outside_candidates():
    p = project(export("r0_syn_04_incoherent"))
    ranked = [(i["identity"]["market_id"], i["rank"]) for i in p["instruments"] if i["rank"] is not None]
    assert sorted(ranked, key=lambda x: x[1]) == [(c["market_id"], c["rank"]) for c in p["candidates"]]
    assert all(i["score"] is not None for i in p["instruments"] if i["rank"] is not None)


def test_SA5_the_real_export_command_output_is_accepted():
    code, text = session("incoherent").run(["export"])
    assert code == 0
    raw = text.encode("utf-8")
    assert raw == export("r0_syn_04_incoherent")
    check_faithful(raw)


# ---------------------------------------------------------------- SA6
def _nulls(value, path="$"):
    if value is None:
        yield path
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _nulls(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _nulls(v, f"{path}[{i}]")


@pytest.mark.parametrize("source,mission", CASES)
def test_SA6_every_null_of_a_market_stays_null_in_its_instrument(source, mission):
    raw = export(source, mission)
    src, p = loads(raw), project(raw)
    for inst, m in zip(p["instruments"], src["markets"]):
        flat = {**inst["identity"], **{k: v for k, v in inst.items() if k not in ("identity", "rank")}}
        assert sorted(_nulls(flat)) == sorted(_nulls(m)), m["market_id"]


@pytest.mark.parametrize("source,mission", CASES)
def test_SA6_unknown_is_never_scored_ranked_or_zeroed(source, mission):
    p = project(export(source, mission))
    for inst in p["instruments"]:
        decision = inst["admissibility"]["decision"]
        if decision != "ADMISSIBLE":
            assert inst["score"] is None and inst["rank"] is None
        for name, crit in inst["criteria"].items():
            if crit["state"] in ("UNKNOWN", "INVALID"):
                assert crit["reason"], (inst["identity"]["market_id"], name)
        if not inst["observation"]["present"]:
            assert inst["lifecycle"]["recent_data"] in ("ABSENT", "UNKNOWN")
            assert inst["observation"]["reason"]


def test_SA6_unknown_population_is_visible():
    p = project(export("r0_syn_04_incoherent"))
    assert p["population"]["counts"]["unknown"] == 6
    assert sum(i["admissibility"]["decision"] == "UNKNOWN" for i in p["instruments"]) == 6
    assert len(p["population"]["orphan_observations"]) == 2
    assert p["scanner_universe"]["sha256"] is None
    assert p["scanner_universe"]["state"] == "NOT_AVAILABLE"
    assert p["budgets"]["production"] == {"status": "NOT_MEASURED", "values": None}


# ---------------------------------------------------------------- SA8
@pytest.mark.parametrize("source,mission", CASES)
def test_SA8_projection_is_a_pure_function_of_the_bytes(source, mission):
    raw = export(source, mission)
    a, b = project(raw), project(bytes(raw))
    assert projection_bytes(a) == projection_bytes(b)
    body = {k: v for k, v in a.items() if k != "projection_sha256"}
    assert a["projection_sha256"] == sha256_hex(canonical(body))
    assert build_projection(verify_export(raw)) == a


def test_SA8_projection_does_not_depend_on_the_final_newline_except_for_the_export_digest():
    raw = export("r0_syn_01_calm")
    a, b = project(raw), project(raw[:-1])
    assert a["source"]["export_sha256"] != b["source"]["export_sha256"]
    strip = lambda p: {k: v for k, v in p.items() if k not in ("source", "projection_sha256")}  # noqa: E731
    assert strip(a) == strip(b)
    assert a["source"]["evaluation_sha256"] == b["source"]["evaluation_sha256"]


def test_SA8_identical_bytes_across_processes_and_hash_seeds(tmp_path):
    raw = export(BATCH)
    src = tmp_path / "export.json"
    src.write_bytes(raw)
    code = ("import sys;from observability.radar_projection.projection import project,projection_bytes;"
            "sys.stdout.buffer.write(projection_bytes(project(open(sys.argv[1],'rb').read())))")
    outs = []
    for seed in ("0", "1", "4242"):
        env = {"PYTHONPATH": str(ROOT), "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1",
               "PATH": "/usr/bin:/bin"}
        proc = subprocess.run([sys.executable, "-c", code, str(src)], capture_output=True, env=env,
                              cwd=tmp_path, timeout=60)
        assert proc.returncode == 0, proc.stderr
        outs.append(proc.stdout)
    assert outs[0] == outs[1] == outs[2] == projection_bytes(project(raw))


def test_SA8_no_clock_is_read(monkeypatch):
    import datetime
    import time

    def boom(*a, **k):
        raise AssertionError("clock read")

    raw = export("r0_syn_04_incoherent")
    for name in ("time", "time_ns", "monotonic", "perf_counter"):
        monkeypatch.setattr(time, name, boom)

    class NoNow(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            boom()

        @classmethod
        def utcnow(cls):
            boom()

    monkeypatch.setattr(datetime, "datetime", NoNow)
    assert project(raw)["schema"] == pc.PROJECTION_SCHEMA
