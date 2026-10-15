"""Tests locaux des tests d'isolation hôte : logique, couverture, détection d'une restriction absente.

Ils ne prouvent PAS l'isolation de l'hôte (aucun systemd ici) : ils prouvent que le lanceur
relit les unités prévues, refuse une dérive, distingue refus attribuable / indéterminé / non effectif.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lab01" / "ops"))
import host_isolation_tests as h  # noqa: E402
import unit_props as up  # noqa: E402


def emulating_runner(cmd, timeout):
    """Faux systemd-run : n'émule QUE NoNewPrivileges, CapabilityBoundingSet vide et PrivateNetwork."""
    props, i = {}, 0
    while i < len(cmd):
        if cmd[i] == "-p":
            k, _, v = cmd[i + 1].partition("=")
            props[k] = v
            i += 2
        else:
            i += 1
    ci = cmd.index("-c")
    argv = [sys.executable, "-I", "-c", cmd[ci + 1], cmd[ci + 2]]
    pre = []
    if props.get("NoNewPrivileges") == "yes":
        pre.append("--no-new-privs")
    if props.get("CapabilityBoundingSet", "x") == "":
        pre.append("--bounding-set=-all")
    wrap = ["setpriv", *pre] if pre else []
    if props.get("PrivateNetwork") == "yes":
        wrap = ["unshare", "-n", *wrap]
    p = subprocess.run(wrap + argv, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def test_every_unit_directive_is_probed_or_explicitly_exempt():
    assert up.coverage_gaps() == []


def test_unknown_directive_is_a_gap(tmp_path):
    d = tmp_path / "systemd"
    shutil.copytree(up.UNIT_DIR, d)
    f = d / "lab01-run.service"
    f.write_text(f.read_text() + "SomeNewSandboxKnob=yes\n")
    assert up.coverage_gaps(d) == ["lab01-run: SomeNewSandboxKnob"]
    assert h.main(["--unit-dir", str(d), "--list-coverage"]) == 1


def test_props_come_from_the_unit_files_not_from_the_test():
    props = up.sandbox_props("lab01-run")
    keys = [k for k, _ in props]
    assert "ExecStart" not in keys and "Type" not in keys
    assert (
        keys.count("SystemCallFilter") == 2
    )  # les deux lignes du fichier, dans l'ordre
    assert ("RequiresMountsFor", "/srv/lab01/data") in props
    assert ("MemoryDenyWriteExecute", "yes") in props
    assert up.without(props, {"MemoryDenyWriteExecute"}) != props


def test_nonexistent_foreign_paths_cannot_fail_the_namespace_setup():
    """Défaut réel corrigé : un chemin inexistant dans InaccessiblePaths fait échouer l'unité (226/NAMESPACE)
    sauf préfixe « - ». Seuls /home, /root et le volume LAB (créés par apply) peuvent être sans préfixe."""
    for u in up.UNITS:
        for k, v in up.sandbox_props(u):
            if k == "InaccessiblePaths":
                for p in v.split():
                    assert (
                        p.startswith("-")
                        or p in ("/home", "/root")
                        or p.startswith("/srv/lab01/data/")
                    ), (u, p)


def test_install_files_do_not_depend_on_the_environment():
    sh = (ROOT / "lab01/ops/lab01_host_tests.sh").read_text()
    assert "host_isolation_tests.py" in sh and "sudo -E" not in sh


@pytest.mark.skipif(
    subprocess.run(["unshare", "-n", "true"], capture_output=True).returncode != 0
    or subprocess.run(
        ["setpriv", "--no-new-privs", "true"], capture_output=True
    ).returncode
    != 0,
    reason="unshare/setpriv indisponibles",
)
def test_emulated_restrictions_are_attributed_and_missing_ones_are_reported_ko():
    ev = h.evaluate(["lab01-run"], up.UNIT_DIR, emulating_runner, log=lambda *a: None)
    verdicts = {cid: v for _, cid, (v, _) in ev}
    # restrictions réellement posées par l'émulation : refus attribuable (témoin sans la directive autorisé)
    assert verdicts["NoNewPrivileges"] == "OK"
    assert verdicts["CapabilityBoundingSet/AmbientCapabilities"] == "OK"
    assert verdicts["PrivateNetwork"] == "OK"
    # restrictions écrites dans le fichier mais NON posées par l'émulation : jamais « OK »
    for cid in (
        "MemoryDenyWriteExecute",
        "RestrictNamespaces",
        "ProtectSystem=strict",
        "PrivateTmp",
        "PrivateDevices",
        "SystemCallFilter",
        "IPAddressDeny",
        "InaccessiblePaths",
    ):
        assert verdicts[cid] == "KO", cid


def _chk(expect, ctl):
    return dict(
        id="x",
        probe="p",
        expect=expect,
        ctl=ctl,
        base_remove=set(),
        control_remove={"D"},
    )


def test_verdict_requires_a_control_that_shows_the_opposite_effect():
    def variants(full, ctl):
        return lambda remove: {"p": ctl} if remove else {"p": full}

    ok = h.verdict(
        _chk(lambda r: r == "denied", lambda r: r == "ok"), variants("denied", "ok")
    )
    assert ok[0] == "OK"
    # refusé aussi sans la directive : le refus vient d'ailleurs (droits Unix, autre directive)
    indet = h.verdict(
        _chk(lambda r: r == "denied", lambda r: r == "ok"), variants("denied", "denied")
    )
    assert indet[0] == "INDÉTERMINÉ"
    ko = h.verdict(
        _chk(lambda r: r == "denied", lambda r: r == "ok"), variants("ok", "ok")
    )
    assert ko[0] == "KO"
    err = h.verdict(
        _chk(lambda r: True, None), lambda remove: {"p": {"ERREUR": "boom"}}
    )
    assert err[0] == "INDÉTERMINÉ"
    broken = h.verdict(
        _chk(lambda r: True, None), lambda remove: {"__erreur__": "rc=1"}
    )
    assert broken[0] == "INDÉTERMINÉ"


def test_missing_lab_path_is_a_failure_but_foreign_path_may_be_absent():
    assert h.per_path({}, ["/srv/lab01/data/runs"], lambda v: True) is False
    assert h.per_path({}, ["/opt/crypto-ai-terminal"], lambda v: True) is None
    assert (
        h.per_path({"/opt/crypto-ai-terminal": True}, ["/opt/crypto-ai-terminal"], bool)
        is True
    )


def test_effective_readbacks():
    lim = up.slice_limits()
    good = {
        "path": "/lab01.slice/x.service",
        "memory.max": "268435456",
        "memory.high": "201326592",
        "memory.swap.max": "0",
        "cpu.max": "25000 100000",
        "pids.max": "64",
    }
    assert h.cgroup_ok(good, lim)
    assert not h.cgroup_ok(
        dict(good, **{"memory.max": "max"}), lim
    )  # plafond non appliqué
    assert h.env_ok(["PYTHONPATH", "PATH"]) and not h.env_ok(["PATH", "MEXC_API_KEY"])
    assert h.size_bytes("4M") == 4194304


def test_installed_units_must_match_the_verified_files(tmp_path):
    inst = tmp_path / "etc"
    inst.mkdir()
    rows = h.installed_matches(up.UNIT_DIR, inst)
    assert {v for _, _, (v, _) in rows} == {"KO"}  # rien d'installé
    for f in up.UNIT_DIR.iterdir():
        shutil.copy(f, inst / f.name)
    assert {v for _, _, (v, _) in h.installed_matches(up.UNIT_DIR, inst)} == {"OK"}
    (inst / "lab01-run.service").write_text("[Service]\n")
    assert any(v == "KO" for _, _, (v, _) in h.installed_matches(up.UNIT_DIR, inst))


def test_driver_refuses_without_root(monkeypatch):
    monkeypatch.setattr(h.os, "geteuid", lambda: 1000)
    assert h.main([]) == 3
