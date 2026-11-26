"""Groupe E — sécurité et isolation. Les contrôles d'exécution passent par des
processus séparés : la garde hors réseau est irréversible dans un processus."""
import ast
import hashlib
import json
import subprocess

import pytest

from observability.radar_selection import contract as c
from observability.radar_selection.engine import evaluate
from observability.radar_selection.fixture import RadarRefusal, canonical
from tests.radar_selection._helpers import NAMES, ROOT, clone, cli, doc, ev, path, python, raw, tree

PACKAGE = ROOT / "observability" / "radar_selection"
STDLIB_ALLOWED = {"__future__", "hashlib", "json", "re", "decimal", "dataclasses", "pathlib", "os", "sys",
                  "shlex", "textwrap", "time", "tracemalloc", "stat",
                  "errno"}  # errno: R1-B security review, ELOOP from O_NOFOLLOW in refs.py
# R1-B (plan accepted 2026-11-24, lot L4): the BBO adapter reuses the existing pure
# validators of the replayed windows and of their anchor instead of a second validator.
# Their import chain opens no transport (checked below by the forbidden-module tests).
INTERNAL_ALLOWED = {"observability.scanner_universe.catalogues", "observability.scanner_universe.universe",
                    "observability.radar_selection.terminal",
                    "observability.radar_composite.bbo_schema", "observability.radar_composite.bbo_history"}
# urllib.parse is pure string handling (imported by pathlib on Python 3.11): only
# the transport modules are forbidden.
FORBIDDEN_EXACT = ("urllib.request", "http.client", "http.server", "ftplib", "smtplib", "xmlrpc.client")
FORBIDDEN_MODULES = ("socket", "ssl", "subprocess", "multiprocessing", "threading", "asyncio",
                     "sqlite3", "requests", "aiohttp", "websocket", "websockets", "ccxt", "core", "paper_trading",
                     "financial_institute", "scripts", "quant_hedge_ai", "risk", "governance")


def _imports():
    found = set()
    for f in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {(f.name, a.name) for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                found.add((f.name, node.module))
    return found


def _loaded_after(cwd, extra=""):
    code = ("import sys\nfrom observability.radar_selection import terminal\n"
            f"{extra}\n"
            f"bad = sorted(m for m in sys.modules if m.split('.')[0] in {FORBIDDEN_MODULES!r} or m in {FORBIDDEN_EXACT!r})\n"
            "print(bad)")
    rc, out, err = python(code, cwd)
    assert rc == 0, err
    return out.strip()


def test_E01_fully_offline_execution(tmp_path):
    for mod in _imports():
        assert mod[1] in STDLIB_ALLOWED | INTERNAL_ALLOWED, mod
    run = ("from observability.radar_selection.terminal import main\n"
           "import io\nmain(['--fixture','calm','status'], stdout=io.StringIO())")
    assert _loaded_after(tmp_path, run) == "[]"
    probe = ("from observability.radar_selection.terminal import install_offline_guard\n"
             "install_offline_guard(None)\n"
             "import socket, urllib.request\n"
             "for f in (lambda: socket.create_connection(('192.0.2.1', 443), timeout=1),\n"
             "          lambda: socket.getaddrinfo('example.com', 443),\n"
             "          lambda: urllib.request.urlopen('https://api.kraken.com/0/public/Time', timeout=1)):\n"
             "    try:\n        f(); print('OPEN')\n"
             "    except PermissionError as e: print('BLOCKED', e)\n"
             "    except Exception as e: print('BLOCKED_WRAPPED', type(e).__name__, e)\n")
    rc, out, err = python(probe, tmp_path)
    assert rc == 0, err
    lines = out.strip().splitlines()
    assert len(lines) == 3 and all(x.startswith("BLOCKED") and "RADAR_OFFLINE_GUARD" in x for x in lines), out


def test_E02_no_private_exchange_access():
    text = "\n".join(f.read_text(encoding="utf-8").lower() for f in sorted(PACKAGE.glob("*.py")))
    for needle in ("api_key", "apikey", "api_secret", "hmac", "x-mbx", "privateapi", "/order", "listenkey",
                   "wss://", "https://"):
        assert needle not in text, needle


def test_E03_no_paper_order(tmp_path):
    for _, mod in _imports():
        assert mod.split(".")[0] not in ("paper_trading", "core", "quant_hedge_ai", "scripts"), mod
    e = ev("calm")
    assert e["mode"]["paper"] == "DISABLED" and e["authority"]["execution_authority"] is False
    assert "order" not in canonical(e).decode().lower().replace("border", "")


def test_E04_no_fin_ppl_or_advisor_access(tmp_path):
    for _, mod in _imports():
        assert not any(k in mod for k in ("financial", "ppl", "advisor", "risk", "operator", "decision")), mod
    run = ("from observability.radar_selection.terminal import main\nimport io\n"
           "main(['--fixture','incoherent','export'], stdout=io.StringIO())\n"
           "import sys\nprint(sorted(m for m in sys.modules if any(k in m for k in "
           "('financial','ppl','advisor','risk_gate','operator_api','paper'))))")
    rc, out, err = python(run, tmp_path)
    assert rc == 0, err
    assert out.strip().splitlines()[-1] == "[]"


def test_E05_no_service_started(tmp_path):
    probe = ("from observability.radar_selection.terminal import install_offline_guard\n"
             "install_offline_guard(None)\nimport os, subprocess\n"
             "for f in (lambda: subprocess.run(['true']), lambda: os.system('true'), lambda: os.fork()):\n"
             "    try:\n        f(); print('STARTED')\n"
             "    except PermissionError as e: print('BLOCKED', e)\n")
    rc, out, err = python(probe, tmp_path)
    assert rc == 0, err
    assert out.strip().splitlines() == ["BLOCKED RADAR_OFFLINE_GUARD:subprocess.Popen",
                                        "BLOCKED RADAR_OFFLINE_GUARD:os.system",
                                        "BLOCKED RADAR_OFFLINE_GUARD:os.fork"]


def test_E06_no_file_written_outside_allowed_directory(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    state = work / "state"
    before = tree(tmp_path)
    for args in (["scan"], ["select", "mexc:spot:BTC/USDT"], ["exclude", "kraken:perp:BTC/USD"], ["history"]):
        assert cli(["--fixture", "calm", "--state-dir", str(state), *args], work)[0] == 0
    after = tree(tmp_path)
    changed = {k for k in after if before.get(k) != after[k]} | (set(before) - set(after))
    assert changed == {"work/state/history.json", "work/state/preferences.json"}
    probe = ("from observability.radar_selection.terminal import install_offline_guard\n"
             f"install_offline_guard(__import__('pathlib').Path({str(state)!r}))\n"
             f"(__import__('pathlib').Path({str(state)!r}) / 'ok.txt').write_text('x')\n"
             "for target in ('outside.txt', '../escape.txt'):\n"
             "    try:\n        open(target, 'w').write('x'); print('WRITTEN')\n"
             "    except PermissionError as e: print('BLOCKED', e)\n")
    rc, out, err = python(probe, work)
    assert rc == 0, err
    assert out.strip().splitlines() == ["BLOCKED RADAR_WRITE_OUTSIDE_STATE_DIR"] * 2
    assert not (work / "outside.txt").exists() and not (tmp_path / "escape.txt").exists()
    # Without --state-dir nothing at all may be written.
    rc, out, err = cli(["--fixture", "calm", "select", "mexc:spot:BTC/USDT"], work)
    assert rc == 4 and "STATE_DIR_REQUIRED" in err


@pytest.mark.parametrize("name", NAMES)
def test_E07_test_budgets_respected(tmp_path, name):
    rc, out, err = cli(["--fixture", name, "bench", "3"], tmp_path)
    assert rc == 0, err
    assert "Budget de test: RESPECTÉ" in out and "Empreintes distinctes: 1" in out
    assert "Budget de production: NOT_MEASURED" in out
    e = ev(name)
    u, lim = e["budgets"]["usage"], e["budgets"]["limits"]
    assert u["input_bytes"] <= lim["max_input_bytes"]
    assert u["instruments_evaluated"] <= lim["max_instruments_per_cycle"]
    assert len(canonical(e)) <= lim["max_output_bytes"]
    assert e["budgets"]["production"] == {"status": "NOT_MEASURED", "values": None}


def test_E08_excessive_input_refused_cleanly(tmp_path):
    small = c.Budgets(**{**c.TEST_BUDGETS.as_dict(), "max_input_bytes": 1_000})
    with pytest.raises(RadarRefusal) as exc:
        evaluate(path("calm").read_bytes(), None, "DEEP_OBSERVATION", small)
    assert exc.value.code == "INPUT_TOO_LARGE"
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (c.TEST_BUDGETS.max_input_bytes + 1) + b"{}")
    rc, out, err = cli(["--fixture", str(big), "status"], tmp_path)
    assert rc == 3 and out == "" and "ENTRÉE REFUSÉE: INPUT_TOO_LARGE" in err
    d = clone(doc("calm"))
    d["observations"][0]["samples"] = d["observations"][0]["samples"] * 9
    with pytest.raises(RadarRefusal) as exc:
        ev(d)
    assert exc.value.code in ("SAMPLES_BOUND", "OBSERVATION_TOO_LARGE")
    # Instrument ceiling: the rest is visibly not evaluated, never silently dropped.
    few = c.Budgets(**{**c.TEST_BUDGETS.as_dict(), "max_instruments_per_cycle": 5})
    e = evaluate(path("calm").read_bytes(), None, "DEEP_OBSERVATION", few)
    assert e["counts"]["evaluated"] == 5 and len(e["markets"]) == 23
    skipped = [m for m in e["markets"] if "BUDGET_NOT_EVALUATED" in [r["code"] for r in m["admissibility"]["reasons"]]]
    assert len(skipped) == e["counts"]["authorized"] - 5
    assert all(m["admissibility"]["decision"] == "UNKNOWN" for m in skipped)


@pytest.mark.parametrize("mutation,code", [
    (lambda b: b[:-20], "INPUT_MALFORMED"),
    (lambda b: b.replace(b'"dataset_id"', b'"dataset_id": "X", "dataset_id"', 1), "DUPLICATE_KEY"),
    (lambda b: b.replace(b'"evaluation_time_ms": ', b'"evaluation_time_ms": 1.5, "x": ', 1), "FLOAT_NOT_ALLOWED"),
    (lambda b: b.replace(b'"SYNTHETIC"', b'"LIVE"', 1), "EVIDENCE_KIND_NOT_ALLOWED_IN_R0"),
    (lambda b: b.replace(b'"fixture_schema"', b'"unexpected": 1, "fixture_schema"', 1), "KEYS_MISMATCH"),
    (lambda b: b"\xff\xfe", "INPUT_MALFORMED"),
    (lambda b: b"", "INPUT_EMPTY"),
])
def test_E09_malformed_input_refused_cleanly(tmp_path, mutation, code):
    bad = tmp_path / "bad.json"
    bad.write_bytes(mutation(path("calm").read_bytes()))
    state = tmp_path / "state"
    rc, out, err = cli(["--fixture", str(bad), "--state-dir", str(state), "scan"], tmp_path)
    assert rc == 3 and out == "" and f"ENTRÉE REFUSÉE: {code}" in err, err
    assert list(state.iterdir()) == []


def test_E10_byte_identical_evaluations_and_sha256(tmp_path):
    for name in NAMES:
        r1 = cli(["--fixture", name, "export"], tmp_path)
        r2 = cli(["--fixture", name, "export"], tmp_path)
        assert r1[0] == r2[0] == 0
        assert r1[1].encode() == r2[1].encode()
        assert hashlib.sha256(r1[1].encode()).hexdigest() == hashlib.sha256(r2[1].encode()).hexdigest()
        doc_ = json.loads(r1[1])
        claimed = doc_.pop("evaluation_sha256")
        assert hashlib.sha256(canonical(doc_)).hexdigest() == claimed
        assert canonical(ev(name)) + b"\n" == r1[1].encode()


def test_E11_no_change_to_cat_database_or_runtime(tmp_path):
    status = lambda: subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,  # noqa: E731
                                    capture_output=True, text=True, check=True).stdout
    before = status()
    for args in (["status"], ["scan"], ["export"], ["candidates"]):
        assert cli(["--fixture", "calm", *args], ROOT)[0] == 0
    assert status() == before
    text = "\n".join(f.read_text(encoding="utf-8") for f in sorted(PACKAGE.glob("*.py")))
    for needle in ("databases/", "sqlite", "systemd", "jsonl", "paper_epoch", "PB_MAX_POSITIONS", "FEATURE_AUTO_CALIBRATION"):
        assert needle not in text, needle


def test_E12_candidate_proposal_creates_no_deep_observation_job(tmp_path):
    state = tmp_path / "state"
    rc, out, _ = cli(["--fixture", "volatile", "--state-dir", str(state), "scan"], tmp_path)
    assert rc == 0 and "Aucune analyse approfondie, collecte L2 ou expérience n'est lancée." in out
    assert sorted(p.name for p in state.iterdir()) == ["history.json"]
    e = ev("volatile")
    assert e["deep_observation_jobs"] == [] and len(e["candidates"]) == 3
    assert e["authority"] == {"execution_authority": False, "collection_authority": False,
                              "experiment_authority": False, "proposal_status": "PROPOSED_NOT_AUTHORIZED"}
    assert all(x["status"] == "PROPOSED_NOT_AUTHORIZED" for x in e["candidates"])
    hist = json.loads((state / "history.json").read_text())
    assert hist["entries"][0]["candidates"] == [x["market_id"] for x in e["candidates"]]


def test_history_is_bounded(tmp_path):
    state = tmp_path / "state"
    small = c.TEST_BUDGETS.max_kept_evaluations
    from observability.radar_selection.manual import append_history
    state.mkdir()
    e = ev("calm")
    for _ in range(small + 5):
        entries = append_history(state, e, small)
    assert len(entries) == small
    assert not list(state.glob(".*.tmp"))


def test_reused_thresholds_match_their_sources():
    from observability.radar_selection import contract
    from observability.radar_composite import bbo_pilot, pilot
    from observability.scanner_universe import universe
    assert contract.CONTINUITY_GOOD == str(bbo_pilot.FLUX_VIABLE_RATIO)
    assert contract.CONTINUITY_VIABLE == f"{pilot.VIABLE_RATIO:.2f}"
    assert contract.CONTINUITY_PARTIAL == f"{pilot.PARTIAL_RATIO:.2f}"
    assert contract.FUTURE_TOLERANCE_MS == universe.FUTURE_TOLERANCE_MS


def test_fixtures_are_reproducible_and_synthetic():
    from tests.radar_selection import build_fixtures
    for name, builder in build_fixtures.FIXTURES.items():
        assert (PACKAGE / "fixtures" / name).read_bytes() == build_fixtures.render(builder), name
        d = json.loads((PACKAGE / "fixtures" / name).read_text())
        assert d["evidence_kind"] == "SYNTHETIC"
        venues = {(o["venue"], o["market_type"]) for o in d["observations"]}
        assert {("kraken", "SPOT"), ("kraken", "PERPETUAL"), ("mexc", "SPOT"), ("mexc", "PERPETUAL")} <= venues
    assert raw(doc("calm"))  # loadable
