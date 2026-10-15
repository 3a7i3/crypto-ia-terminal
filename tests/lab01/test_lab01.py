"""LAB-01 — tests positifs et tests de refus (SYNTHETIC, sans réseau)."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

from lab01 import api, guards, risk, runner, strategy
from lab01.events import EventLog, verify_chain
from lab01.scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _no_ambient_secret_like_env(monkeypatch):
    """La CI définit des variables au nom d'exchange ; le garde les refuse à raison.
    Les tests partent d'un environnement propre (le test de refus fixe son propre env)."""
    for name in guards.forbidden_env_names():
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    for name in guards.forbidden_env_names():
        mp.delenv(name, raising=False)
    try:
        d = tmp_path_factory.mktemp("lab01") / "out"
        runner.run_all(d)
    finally:
        mp.undo()
    return d


def _result(out, name):
    p = next(out.glob(f"LAB01-{name}-*/result.json"))
    return json.loads(p.read_text())


# ---- positifs ---------------------------------------------------------------
def test_accepted_then_closed(out):
    r = _result(out, "accepted_closed")
    assert r["verdict"] == "PASS" and r["final_state"] == "POSTMORTEM_ANALYZED"
    assert r["synthetic_pnl_usd"] is not None and r["provenance"] == "SYNTHETIC"


def test_risk_rejection_is_justified(out):
    r = _result(out, "risk_rejected")
    assert r["verdict"] == "PASS" and r["final_state"] == "REJECTED"
    assert r["risk_reason_code"] == "VOLATILITY_ABOVE_LIMIT"
    ev = [
        json.loads(x)
        for x in next(out.glob("LAB01-risk_rejected-*/events.jsonl"))
        .read_text()
        .splitlines()
    ]
    rej = next(e for e in ev if e["type"] == "RISK_REJECTED")["payload"]
    assert rej["observed"] > rej["limit"] and rej["justification"]
    assert not {"ORDER_SUBMITTED", "ORDER_FILLED"} & {e["type"] for e in ev}


def test_execution_error_visible_and_traceable(out):
    r = _result(out, "execution_error")
    assert r["verdict"] == "PASS" and r["final_state"] == "FAILED"
    assert r["error_code"] == "SIMULATED_EXCHANGE_TIMEOUT"
    ev = [
        json.loads(x)
        for x in next(out.glob("LAB01-execution_error-*/events.jsonl"))
        .read_text()
        .splitlines()
    ]
    err = next(e for e in ev if e["type"] == "EXECUTION_ERROR")
    assert (
        err["trace_id"] == r["trace_id"] and err["experiment_id"] == r["experiment_id"]
    )


def test_every_event_is_synthetic_and_chained(out):
    for p in out.glob("LAB01-*/events.jsonl"):
        ev = [json.loads(x) for x in p.read_text().splitlines()]
        assert verify_chain(ev) and all(e["provenance"] == "SYNTHETIC" for e in ev)
        assert all(e["ts_synthetic"].startswith("2026-01-01T") for e in ev)


def test_reproducible_in_process_and_across_processes(out, tmp_path):
    rep = runner.verify_reproducible()
    assert all(
        x["reproducible"] and x["chain_valid"] and x["verdict"] == "PASS" for x in rep
    )
    other = tmp_path / "second"
    subprocess.run(
        [sys.executable, "-m", "lab01", "run", "--out", str(other)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    for name in SCENARIOS:
        assert (
            _result(out, name)["events_digest"] == _result(other, name)["events_digest"]
        )
        assert (
            _result(out, name)["experiment_id"] == _result(other, name)["experiment_id"]
        )


# ---- refus ------------------------------------------------------------------
def test_tampered_event_breaks_chain(out):
    p = next(out.glob("LAB01-accepted_closed-*/events.jsonl"))
    ev = [json.loads(x) for x in p.read_text().splitlines()]
    ev[3]["payload"]["tampered"] = True
    assert not verify_chain(ev)
    ev = [json.loads(x) for x in p.read_text().splitlines()]
    ev[2]["provenance"] = "PRODUCTION"
    assert not verify_chain(ev)


@pytest.mark.parametrize(
    "code,field,value",
    [
        ("CONFIDENCE_BELOW_MIN", "min_confidence", 99.0),
        ("R_MULTIPLE_BELOW_MIN", "min_r_multiple", 5.0),
        ("VOLATILITY_ABOVE_LIMIT", "max_realized_vol_bps", 1.0),
        ("MAX_NOTIONAL_EXCEEDED", "max_notional_pct", 1.0),
    ],
)
def test_each_risk_rule_rejects(code, field, value):
    from lab01.synthetic import generate_bars

    d = SCENARIOS["accepted_closed"].data
    bars = generate_bars(seed=d.seed, n=d.n_bars, shocks=dict(d.shocks))
    sig = next(
        s
        for i in range(len(bars))
        if (s := strategy.evaluate(bars, i, strategy.SignalConfig()))
    )
    assert risk.evaluate(sig, risk.RiskLimits()).approved
    v = risk.evaluate(sig, replace(risk.RiskLimits(), **{field: value}))
    assert not v.approved and v.reason_code == code


def test_network_is_denied_and_restored():
    with guards.deny_network():
        with pytest.raises(guards.NetworkDenied):
            socket.create_connection(("example.com", 80), timeout=1)
        with pytest.raises(guards.NetworkDenied):
            socket.getaddrinfo("example.com", 80)
        s = socket.socket()
        with pytest.raises(guards.NetworkDenied):
            s.connect(("127.0.0.1", 9))
        s.close()
    assert socket.getaddrinfo("localhost", 80)  # restauré


def test_secret_like_env_names_refuse_run(tmp_path):
    env = {
        "PATH": "/bin",
        "MEXC_API_KEY": "SENTINEL_VALUE_1",
        "TELEGRAM_BOT_TOKEN": "SENTINEL_VALUE_2",
    }
    assert guards.forbidden_env_names(env) == ["MEXC_API_KEY", "TELEGRAM_BOT_TOKEN"]
    with pytest.raises(guards.LabGuardError) as ei:
        guards.assert_clean_environment(env)
    assert "SENTINEL_VALUE" not in str(ei.value)  # noms seulement, jamais les valeurs


@pytest.mark.parametrize(
    "bad",
    [
        "/home/mathieu/crypto_ai_terminal/lab",
        "/opt/crypto-ai-terminal/operator/presentation/x",
        "/tmp/x/databases/lab",
        "/srv/claude-audit/out",
    ],
)
def test_output_in_production_tree_refused(bad):
    with pytest.raises(guards.LabGuardError):
        guards.assert_safe_output_dir(bad)


def test_unknown_scenario_refused(tmp_path):
    with pytest.raises(SystemExit):
        runner.run_all(tmp_path / "o", ["nope"])


# ---- API --------------------------------------------------------------------
def _serve(root, token=None):
    srv = api.build_server(root, 0, token)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _get(url, headers=None, method="GET"):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_api_get_only_and_projection(out):
    srv, base = _serve(out)
    try:
        code, body = _get(base + "/lab/experiments")
        j = json.loads(body)
        assert (
            code == 200
            and j["provenance"] == "SYNTHETIC"
            and len(j["experiments"]) == 3
        )
        eid = j["experiments"][0]["experiment_id"]
        assert _get(f"{base}/lab/experiments/{eid}")[0] == 200
        assert json.loads(_get(f"{base}/lab/experiments/{eid}/events")[1])["events"]
        for m in ("POST", "PUT", "DELETE", "PATCH"):
            assert _get(base + "/lab/health", method=m)[0] == 405
        assert b"SYNTH" in _get(base + "/")[1]
    finally:
        srv.shutdown()


@pytest.mark.parametrize(
    "path",
    [
        "/lab/experiments/..%2f..%2fetc%2fpasswd",
        "/lab/experiments/LAB01-x-zz",
        "/lab/experiments/../index.json",
        "/etc/passwd",
        "/lab/nope",
    ],
)
def test_api_rejects_bad_paths(out, path):
    srv, base = _serve(out)
    try:
        assert _get(base + path)[0] == 404
    finally:
        srv.shutdown()


def test_api_requires_token_when_configured(out):
    srv, base = _serve(out, token="t" * 32)
    try:
        assert _get(base + "/lab/experiments")[0] == 401
        assert (
            _get(base + "/lab/experiments", {"Authorization": "Bearer wrong"})[0] == 401
        )
        assert (
            _get(base + "/lab/experiments", {"Authorization": "Bearer " + "t" * 32})[0]
            == 200
        )
    finally:
        srv.shutdown()


def test_missing_artifacts_are_503_not_empty(tmp_path):
    srv, base = _serve(tmp_path)
    try:
        code, body = _get(base + "/lab/experiments")
        assert code == 503 and json.loads(body)["error"] == "LAB_ARTIFACT_MISSING"
    finally:
        srv.shutdown()


def test_api_refuses_non_loopback_bind(tmp_path):
    with pytest.raises(ValueError):
        api.build_server(tmp_path, 0, None, host="0.0.0.0")


def test_eventlog_ids_required():
    log = EventLog("LAB01-x-000000000000", "TR-1")
    log.emit("A", {"v": 1.123456789012})
    assert log.events[0]["payload"]["v"] == 1.12345679


# ---- paquet autonome ----------------------------------------------------------
def test_bundle_is_standalone_deterministic_and_equivalent(out, tmp_path):
    import hashlib
    import os
    import tarfile

    from lab01.ops import make_bundle

    a, da = make_bundle.build(tmp_path / "a")
    _b, db = make_bundle.build(tmp_path / "b")
    assert da == db  # archive déterministe
    names = tarfile.open(a).getnames()
    assert not [n for n in names if n.startswith(("databases", ".env", "config"))]
    dst = tmp_path / "unpacked"
    dst.mkdir()
    tarfile.open(a).extractall(dst, filter="data")
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(dst)}
    other = tmp_path / "bundle_out"
    subprocess.run(
        [sys.executable, "-m", "lab01", "run", "--out", str(other)],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    for name in SCENARIOS:  # mêmes identités que le dépôt : même code, même résultat
        assert (
            _result(out, name)["experiment_id"] == _result(other, name)["experiment_id"]
        )
        assert (
            _result(out, name)["events_digest"] == _result(other, name)["events_digest"]
        )
    assert hashlib.sha256(a.read_bytes()).hexdigest() == da


# ---- unités et script d'installation (statique : rien n'est installé) -----------
OPS = ROOT / "lab01" / "ops"


def _unit(name):
    return (OPS / "systemd" / name).read_text()


def test_units_have_no_production_dependency_or_secret_source():
    import re

    for name in ("lab01.slice", "lab01-run.service", "lab01-api.service"):
        txt = _unit(name)
        assert not re.search(
            r"^(Requires|Wants|After|Before|BindsTo|PartOf|Conflicts|Upholds|OnFailure)=",
            txt,
            re.M,
        )
        assert "EnvironmentFile" not in txt and "[Install]" not in txt
        assert "User=root" not in txt


def test_run_unit_denies_network_and_limits_writes():
    txt = _unit("lab01-run.service")
    for needle in (
        "PrivateNetwork=yes",
        "IPAddressDeny=any",
        "RestrictAddressFamilies=AF_UNIX",
        "ProtectSystem=strict",
        "ReadWritePaths=/srv/lab01/runs",
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=",
        "Slice=lab01.slice",
        "User=lab01",
    ):
        assert needle in txt
    assert "/home" in txt and "InaccessiblePaths" in txt


def test_api_unit_is_loopback_only_and_read_only():
    txt = _unit("lab01-api.service")
    assert "IPAddressAllow=127.0.0.0/8 ::1" in txt and "IPAddressDeny=any" in txt
    assert "ReadOnlyPaths=/srv/lab01/runs" in txt and "--token-file" in txt


def test_slice_bounds_whole_lab():
    txt = _unit("lab01.slice")
    for needle in ("MemoryMax=", "CPUQuota=", "TasksMax=", "MemorySwapMax=0"):
        assert needle in txt


def test_ops_script_refuses_without_authorization_and_plan_is_inert():
    sh = str(OPS / "lab01_ops.sh")
    assert subprocess.run(["bash", "-n", sh]).returncode == 0
    plan = subprocess.run(["bash", sh, "plan"], capture_output=True, text=True)
    assert plan.returncode == 0 and "rien n'est modifié" in plan.stdout
    for mode in ("apply", "remove"):
        r = subprocess.run(
            ["bash", sh, mode],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        assert r.returncode == 3 and "REFUS" in r.stdout


def _host_tests(tmp_path, seq):
    """Exécute lab01_host_tests.sh avec un systemd-run factice qui rend `seq` codes de sortie."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (tmp_path / "seq").write_text("\n".join(map(str, seq)) + "\n")
    (bindir / "systemd-run").write_text(
        f'#!/bin/sh\nf="{tmp_path}/seq"\nrc=$(head -n1 "$f"); sed -i 1d "$f"; exit "${{rc:-1}}"\n'
    )
    (bindir / "id").write_text("#!/bin/sh\necho 0\n")
    for f in bindir.iterdir():
        f.chmod(0o755)
    env = {"PATH": f"{bindir}:/usr/bin:/bin"}
    return subprocess.run(
        ["bash", str(OPS / "lab01_host_tests.sh")],
        capture_output=True,
        text=True,
        env=env,
    )


def test_host_refusal_tests_pass_only_when_os_refuses(tmp_path):
    r = _host_tests(tmp_path, [0] + [42] * 7 + [0])
    assert r.returncode == 0 and r.stdout.count("refusé par l'OS") == 7


def test_host_refusal_tests_fail_when_something_is_allowed(tmp_path):
    r = _host_tests(tmp_path, [0, 0] + [42] * 6 + [0])  # le réseau serait autorisé
    assert r.returncode == 1 and "AUTORISÉ (attendu : refusé)" in r.stdout


def test_host_refusal_tests_abort_when_tool_is_broken(tmp_path):
    r = _host_tests(tmp_path, [1] * 10)  # un outil en panne n'est pas un refus
    assert (
        r.returncode == 5
        and "ABANDON" in r.stdout
        and "refusé par l'OS" not in r.stdout
    )


def test_host_refusal_indeterminate_is_not_counted_as_refusal(tmp_path):
    r = _host_tests(tmp_path, [0, 1] + [42] * 6 + [0])
    assert r.returncode == 1 and "indéterminé" in r.stdout


def test_run_refuses_when_environment_has_secret_like_names(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "SENTINEL_VALUE_3")
    with pytest.raises(guards.LabGuardError) as ei:
        runner.run_all(tmp_path / "o")
    assert "MEXC_API_KEY" in str(ei.value) and "SENTINEL_VALUE" not in str(ei.value)
    assert not (tmp_path / "o" / "index.json").exists()
