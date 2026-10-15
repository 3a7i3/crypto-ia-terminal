#!/usr/bin/env python3
"""LAB-01 — tests d'isolation EFFECTIVE sur l'hôte (après installation autorisée ; root requis).

Principe : une directive présente dans un fichier d'unité n'est pas une preuve d'isolation.
Pour chaque restriction, une unité transitoire reçoit EXACTEMENT les propriétés relues dans
le fichier d'unité prévu (unit_props.py, source unique) ; une sonde exécutée dans le processus
observe l'effet réel ; un ESSAI TÉMOIN sans la directive doit montrer l'effet inverse, sinon le
refus n'est pas attribuable à la directive et le verdict est INDÉTERMINÉ.
Verdicts : OK | KO (restriction non effective) | INDÉTERMINÉ | NON APPLICABLE | NON SONDÉE (motif).
Codes de sortie : 0 tout OK ; 1 au moins un KO ; 4 INDÉTERMINÉ sans KO ; 5 abandon (contrôle) ;
3 pas root. Aucune unité de production n'est touchée ; aucun secret n'est lu.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import unit_props as up  # noqa: E402

PY = "/usr/bin/python3.11"
PROBE_CODE = (HERE / "hostprobe.py").read_text(encoding="utf-8")
LAB = "/srv/lab01"
DATA = f"{LAB}/data"
ABSENT_OK = "N/A"
SECRET_WORDS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "BINANCE",
    "MEXC",
    "BYBIT",
    "OKX",
    "TESTNET",
)
ALLOWED_ENV = {
    "PYTHONPATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONNOUSERSITE",
    "PATH",
    "LANG",
    "LC_ALL",
    "HOME",
    "LOGNAME",
    "USER",
    "SHELL",
    "INVOCATION_ID",
    "JOURNAL_STREAM",
    "SYSTEMD_EXEC_PID",
    "TERM",
    "MANAGERPID",
    "SYSTEMD_INVOCATION_ID",
    "LISTEN_PID",
    "LISTEN_FDS",
    "NOTIFY_SOCKET",
    "PWD",
    "XDG_RUNTIME_DIR",
    "OLDPWD",
    "_",
    "SHLVL",
}

Runner = "callable(list[str], int) -> tuple[int, str, str]"


def default_runner(cmd, timeout=90):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def size_bytes(v: str) -> int:
    v = v.strip()
    mult = {"K": 1024, "M": 1024**2, "G": 1024**3}
    return int(v[:-1]) * mult[v[-1]] if v[-1] in mult else int(v)


def sd_args(unit, props, systemd_run="systemd-run"):
    cmd = [
        systemd_run,
        "--quiet",
        "--wait",
        "--collect",
        "--pipe",
        "--slice=lab01.slice",
    ]
    for k, v in props:
        cmd += ["-p", f"{k}={v}"]
    return cmd


def run_variant(unit, props, args, runner, systemd_run="systemd-run"):
    """Une unité transitoire avec `props` ; retourne le dict des sondes (ou {'__erreur__': ...})."""
    marker = f".lab01-tmp-{uuid.uuid4().hex[:12]}"
    payload = dict(args, tmp_marker=marker)
    cmd = sd_args(unit, props, systemd_run) + [
        PY,
        "-I",
        "-c",
        PROBE_CODE,
        json.dumps(payload),
    ]
    rc, out, err = runner(cmd, 90)
    host_vis = os.path.exists(f"/tmp/{marker}")
    if host_vis:
        os.unlink(f"/tmp/{marker}")
    for line in out.splitlines():
        if line.startswith("PROBE-RESULT "):
            res = json.loads(line[len("PROBE-RESULT ") :])
            res["tmp"] = {"written": res.get("tmp"), "host_visible": host_vis}
            return res
    return {"__erreur__": f"rc={rc} stderr={err.strip()[:300]!r}"}


def zero(h):
    return h is not None and int(h, 16) == 0


def denied(v):
    return isinstance(v, str) and v != "ok"


def all_denied(d, keys):
    return all(denied(d.get(k)) for k in keys)


def per_path(res, paths, pred):
    """Évalue pred sur les chemins présents. Un chemin du LAB absent est un ÉCHEC (installation
    incomplète), jamais « non applicable » ; seuls les chemins étrangers au LAB peuvent manquer."""
    if not isinstance(res, dict):
        return None
    required = [p for p in paths if p.startswith(LAB) and p != f"{LAB}/token"]
    if any(p not in res for p in required):
        return False
    present = [p for p in paths if p in res]
    return None if not present else all(pred(res[p]) for p in present)


def build_checks(cfg):
    """Contrôles par unité : (id, directives, sonde, retrait_base, retrait_témoin, attendu, témoin)."""
    C = []

    def add(
        cid, directives, probe, expect, ctl=None, base_remove=(), control_remove=()
    ):
        C.append(
            dict(
                id=cid,
                directives=directives,
                probe=probe,
                expect=expect,
                ctl=ctl,
                base_remove=set(base_remove),
                control_remove=set(control_remove),
            )
        )

    add(
        "NoNewPrivileges",
        ["NoNewPrivileges"],
        "nonewprivs",
        lambda r: r == "1",
        lambda r: r == "0",
        control_remove={"NoNewPrivileges"},
    )
    add(
        "CapabilityBoundingSet/AmbientCapabilities",
        ["CapabilityBoundingSet", "AmbientCapabilities"],
        "caps",
        lambda r: all(zero(r.get(k)) for k in ("CapEff", "CapBnd", "CapAmb")),
        lambda r: not zero(r.get("CapBnd")),
        control_remove={"CapabilityBoundingSet", "AmbientCapabilities"},
    )
    add(
        "SystemCallFilter",
        ["SystemCallFilter"],
        "syscall",
        lambda r: r.get("seccomp") == "2" and denied(r.get("nice")),
        lambda r: r.get("nice") == "ok",
        control_remove={"SystemCallFilter"},
    )
    add(
        "MemoryDenyWriteExecute",
        ["MemoryDenyWriteExecute"],
        "mdwe",
        denied,
        lambda r: r == "ok",
        control_remove={"MemoryDenyWriteExecute"},
    )
    add(
        "LockPersonality",
        ["LockPersonality"],
        "lockpers",
        denied,
        lambda r: r == "ok",
        control_remove={"LockPersonality"},
    )
    add(
        "RestrictNamespaces",
        ["RestrictNamespaces"],
        "userns",
        denied,
        lambda r: r == "ok",
        control_remove={"RestrictNamespaces"},
    )
    add(
        "RestrictSUIDSGID",
        ["RestrictSUIDSGID"],
        "suid",
        denied,
        lambda r: r == "ok",
        control_remove={"RestrictSUIDSGID"},
    )
    if cfg["private_net"]:
        add(
            "RestrictAddressFamilies",
            ["RestrictAddressFamilies"],
            "af",
            lambda r: (
                r.get("AF_UNIX") == "ok" and all_denied(r, ("AF_INET", "AF_NETLINK"))
            ),
            lambda r: r.get("AF_INET") == "ok" and r.get("AF_NETLINK") == "ok",
            control_remove={"RestrictAddressFamilies"},
        )
        add(
            "PrivateNetwork",
            ["PrivateNetwork"],
            "netdev",
            lambda r: r == ["lo"],
            lambda r: r != ["lo"],
            control_remove={"PrivateNetwork"},
        )
        add(
            "IPAddressDeny",
            ["IPAddressDeny"],
            "ipdeny",
            lambda r: isinstance(r, dict) and denied(r.get("loopback")),
            lambda r: isinstance(r, dict) and r.get("loopback") == "ok",
            base_remove={"PrivateNetwork"},
            control_remove={"PrivateNetwork", "IPAddressDeny"},
        )
    else:
        add(
            "RestrictAddressFamilies",
            ["RestrictAddressFamilies"],
            "af",
            lambda r: (
                r.get("AF_INET") == "ok"
                and r.get("AF_UNIX") == "ok"
                and denied(r.get("AF_NETLINK"))
            ),
            lambda r: r.get("AF_NETLINK") == "ok",
            control_remove={"RestrictAddressFamilies"},
        )
        add(
            "IPAddressDeny/IPAddressAllow",
            ["IPAddressDeny", "IPAddressAllow"],
            "ipdeny",
            lambda r: (
                isinstance(r, dict)
                and r.get("loopback") == "ok"
                and r.get("hors_loopback") in ("TIMEOUT", "EPERM")
            ),
            lambda r: isinstance(r, dict) and r.get("hors_loopback") == "ok",
            control_remove={"IPAddressDeny", "IPAddressAllow"},
        )
    add(
        "ProtectSystem=strict",
        ["ProtectSystem"],
        "write_ro",
        lambda r: per_path(r, cfg["sys_ro"], lambda v: v == "EROFS"),
        lambda r: per_path(r, cfg["sys_ro"], lambda v: v != "EROFS"),
        control_remove={"ProtectSystem"},
    )
    if cfg["ro_paths"]:
        add(
            "ReadOnlyPaths",
            ["ReadOnlyPaths"],
            "write_ro",
            lambda r: per_path(r, cfg["ro_paths"], lambda v: v == "EROFS"),
            lambda r: per_path(r, cfg["ro_paths"], lambda v: v != "EROFS"),
            control_remove={"ReadOnlyPaths"},
        )
    if cfg["rw_paths"]:
        add(
            "ReadWritePaths",
            ["ReadWritePaths"],
            "write_rw",
            lambda r: per_path(r, cfg["rw_paths"], lambda v: v == "ok"),
            lambda r: per_path(r, cfg["rw_paths"], lambda v: v == "EROFS"),
            control_remove={"ReadWritePaths"},
        )
    add(
        "ProtectHome",
        ["ProtectHome"],
        "inaccessible",
        lambda r: per_path(r, ["/home", "/root"], bool),
        lambda r: per_path(r, ["/home", "/root"], lambda v: not v),
        control_remove={"ProtectHome", "InaccessiblePaths"},
    )
    add(
        "InaccessiblePaths",
        ["InaccessiblePaths"],
        "inaccessible",
        lambda r: per_path(r, cfg["inacc"], bool),
        lambda r: per_path(r, cfg["inacc"], lambda v: not v),
        control_remove={"InaccessiblePaths"},
    )
    if cfg["token_readable"]:
        add(
            "jeton lisible par l'API (non masqué)",
            [],
            "inaccessible",
            lambda r: per_path(r, [f"{LAB}/token"], lambda v: not v),
        )
    add(
        "PrivateTmp",
        ["PrivateTmp"],
        "tmp",
        lambda r: r["written"] == "written" and r["host_visible"] is False,
        lambda r: r["written"] == "written" and r["host_visible"] is True,
        control_remove={"PrivateTmp"},
    )
    add(
        "PrivateDevices",
        ["PrivateDevices"],
        "dev",
        lambda r: isinstance(r, int) and r < 30,
        lambda r: isinstance(r, int) and r >= 30,
        control_remove={"PrivateDevices"},
    )
    add(
        "ProtectKernelTunables",
        ["ProtectKernelTunables"],
        "procsys",
        lambda r: r is True,
        lambda r: r is False,
        control_remove={"ProtectKernelTunables"},
    )
    add(
        "ProtectControlGroups",
        ["ProtectControlGroups"],
        "cgroupfs",
        lambda r: r is True,
        lambda r: r is False,
        control_remove={"ProtectControlGroups"},
    )
    add(
        "ProtectKernelModules",
        ["ProtectKernelModules"],
        "modules",
        lambda r: None if r == ABSENT_OK else all(r.values()),
        lambda r: None if r == ABSENT_OK else not any(r.values()),
        control_remove={"ProtectKernelModules"},
    )
    # volume noexec : le même script s'exécute depuis /tmp (témoin interne) et pas depuis le volume.
    if cfg["rw_paths"]:
        add(
            "volume noexec (option de montage)",
            [],
            "noexec",
            lambda r: (
                isinstance(r, dict)
                and r.get(cfg["rw_paths"][0]) == "EACCES"
                and r.get("/tmp") == "ok"
            ),
        )
    # relectures d'effet : valeur effective, sans essai témoin (déterministe).
    add(
        "User/Group/WorkingDirectory",
        ["User", "Group", "WorkingDirectory"],
        "ids",
        lambda r: r == {"user": "lab01", "group": "lab01", "cwd": "/"},
    )
    add("Environment (aucun secret)", ["Environment"], "env", env_ok)
    add("UMask", ["UMask"], "umask", lambda r: r == cfg["umask"])
    add(
        "Limit*",
        ["LimitNOFILE", "LimitNPROC", "LimitCORE", "LimitFSIZE"],
        "limits",
        lambda r: all(r.get(k) == v for k, v in cfg["limits"].items()),
    )
    add(
        "lab01.slice (plafonds effectifs)",
        ["Slice"],
        "cgroup",
        lambda r: cgroup_ok(r, cfg["slice"]),
    )
    return C


def env_ok(names):
    bad = [
        n
        for n in names
        if any(w in n.upper() for w in SECRET_WORDS) or n not in ALLOWED_ENV
    ]
    return not bad


def cgroup_ok(r, lim):
    want = {
        "memory.max": str(size_bytes(lim["MemoryMax"])),
        "memory.high": str(size_bytes(lim["MemoryHigh"])),
        "memory.swap.max": str(size_bytes(lim["MemorySwapMax"])),
        "cpu.max": f"{int(lim['CPUQuota'].rstrip('%')) * 1000} 100000",
        "pids.max": lim["TasksMax"],
    }
    return "lab01.slice" in r.get("path", "") and all(
        r.get(k) == v for k, v in want.items()
    )


def unit_cfg(unit, unit_dir):
    props = dict((k, v) for k, v in up.sandbox_props(unit, unit_dir))
    ids = {k: v for k, v in up.sandbox_props(unit, unit_dir)}
    lim = {}
    for key, name in (
        ("LimitNOFILE", "NOFILE"),
        ("LimitNPROC", "NPROC"),
        ("LimitCORE", "CORE"),
        ("LimitFSIZE", "FSIZE"),
    ):
        if key in ids:
            lim[name] = str(size_bytes(ids[key]))
    inacc = [p.lstrip("-") for p in props.get("InaccessiblePaths", "").split()]
    ro = [p for p in props.get("ReadOnlyPaths", "").split()]
    rw = [p for p in props.get("ReadWritePaths", "").split()]
    return dict(
        unit=unit,
        private_net=props.get("PrivateNetwork") == "yes",
        umask=props.get("UMask", "").zfill(4),
        inacc=[p for p in inacc if p not in ("/home", "/root")],
        ro_paths=ro,
        rw_paths=rw,
        sys_ro=["/etc", "/usr", f"{LAB}/release"],
        token_readable=f"-{LAB}/token" not in props.get("InaccessiblePaths", "").split()
        and f"{LAB}/token" not in inacc,
        limits=lim,
        slice=up.slice_limits(unit_dir),
    )


def probe_args(cfg, listeners):
    return dict(
        ro_paths=cfg["sys_ro"] + cfg["ro_paths"],
        rw_paths=cfg["rw_paths"],
        inacc_paths=["/home", "/root"] + cfg["inacc"] + [f"{LAB}/token"],
        exec_dirs=cfg["rw_paths"][:1] + ["/tmp"],
        exec_dir=(cfg["rw_paths"] or ["/tmp"])[0],
        listeners=listeners,
    )


def make_listeners():
    """Deux écouteurs côté hôte (root) : un en loopback, un sur l'adresse non-loopback de l'hôte."""
    socks, info = [], {}
    a = socket.socket()
    a.bind(("127.0.0.1", 0))
    a.listen(4)
    socks.append(a)
    info["loop_port"] = a.getsockname()[1]
    try:
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.connect(
            ("192.0.2.1", 9)
        )  # aucune donnée émise : sert à connaître l'adresse source
        info["host_ip"] = u.getsockname()[0]
        u.close()
        b = socket.socket()
        b.bind(("0.0.0.0", 0))
        b.listen(4)
        socks.append(b)
        info["host_port"] = b.getsockname()[1]
    except OSError:
        info = {}
    return socks, info


def evaluate(units, unit_dir, runner, systemd_run="systemd-run", log=print):
    results, listeners_socks = [], []
    socks, info = make_listeners()
    listeners_socks = socks
    try:
        for unit in units:
            full_props = up.sandbox_props(unit, unit_dir)
            cfg = unit_cfg(unit, unit_dir)
            args = probe_args(cfg, info if info.get("host_ip") else {})
            cache = {}

            def variant(remove):
                key = frozenset(remove)
                if key not in cache:
                    cache[key] = run_variant(
                        unit,
                        up.without(full_props, set(remove)),
                        args,
                        runner,
                        systemd_run,
                    )
                return cache[key]

            base = variant(set())
            if "__erreur__" in base:
                log(
                    f"ABANDON {unit} : contrôle d'exécution échoué : {base['__erreur__']}"
                )
                return None
            log(
                f"OK  {unit} : contrôle — l'unité transitoire s'exécute avec les propriétés relues du fichier"
            )
            for chk in build_checks(cfg):
                results.append((unit, chk["id"], verdict(chk, variant)))
                log(
                    f"{results[-1][2][0]:<12} {unit} : {chk['id']} — {results[-1][2][1]}"
                )
    finally:
        for s in listeners_socks:
            s.close()
    return results


def verdict(chk, variant):
    full = variant(chk["base_remove"])
    if "__erreur__" in full:
        return "INDÉTERMINÉ", full["__erreur__"]
    r = full.get(chk["probe"])
    if isinstance(r, dict) and "ERREUR" in r:
        return "INDÉTERMINÉ", f"la sonde a échoué : {r['ERREUR']}"
    ok = chk["expect"](r)
    if ok is None:
        return "NON APPLICABLE", "chemin ou objet absent de l'hôte"
    if not ok:
        return (
            "KO",
            f"restriction NON effective (observé : {json.dumps(r, sort_keys=True)[:200]})",
        )
    if chk["ctl"] is None:
        return "OK", "effet relevé dans le processus"
    ctl = variant(chk["control_remove"])
    rc = ctl.get(chk["probe"]) if "__erreur__" not in ctl else None
    if rc is None or (isinstance(rc, dict) and "ERREUR" in rc):
        return "INDÉTERMINÉ", "essai témoin indisponible"
    cok = chk["ctl"](rc)
    if cok is None:
        return "NON APPLICABLE", "chemin ou objet absent de l'hôte"
    if cok:
        return (
            "OK",
            "refusé avec la directive, autorisé sans elle (témoin) : attribuable à la directive",
        )
    return (
        "INDÉTERMINÉ",
        f"le témoin sans la directive ne montre pas l'effet inverse (observé : {json.dumps(rc)[:120]})",
    )


def installed_matches(unit_dir, installed_dir="/etc/systemd/system"):
    out = []
    for name in ["lab01.slice", "srv-lab01-data.mount"] + [
        f"{u}.service" for u in up.UNITS
    ]:
        a, b = Path(unit_dir) / name, Path(installed_dir) / name
        same = b.is_file() and a.read_bytes() == b.read_bytes()
        out.append(
            (
                "*",
                f"unité installée identique au fichier prévu : {name}",
                ("OK", "octet pour octet")
                if same
                else ("KO", "absente ou différente de celle du paquet vérifié"),
            )
        )
    return out


def coverage_report(unit_dir):
    rows = []
    for u in up.UNITS:
        for k, v in up.sandbox_props(u, unit_dir):
            kind, _, why = up.COVERAGE.get(
                k, "exempt:couverture non déclarée"
            ).partition(":")
            rows.append((u, k, "NON SONDÉE" if kind == "exempt" else "couverte", why))
    return rows


def functional(unit_dir, runner, systemd_run="systemd-run", log=print):
    """Lance les VRAIES commandes ExecStart sous les propriétés réelles (compatibilité du bac à sable)."""
    res = []
    for unit in ("lab01-run", "lab01-export"):
        argv = up.exec_start(unit, unit_dir).split()
        cmd = sd_args(unit, up.sandbox_props(unit, unit_dir), systemd_run) + argv
        rc, _, err = runner(cmd, 300)
        res.append(
            (
                unit,
                "commande réelle sous le bac à sable",
                ("OK", "rc=0") if rc == 0 else ("KO", f"rc={rc} {err.strip()[:200]}"),
            )
        )
        log(f"{res[-1][2][0]:<12} {unit} : exécution réelle — {res[-1][2][1]}")
    tok = Path(f"{LAB}/token")
    if not tok.is_file():
        res.append(
            (
                "lab01-api",
                "démarrage réel et jeton",
                ("INDÉTERMINÉ", "jeton absent : non exécuté"),
            )
        )
        return res
    return res + api_functional(unit_dir, runner, systemd_run, tok, log)


def api_functional(unit_dir, runner, systemd_run, tok, log):
    name = "lab01-api-hosttest"
    argv = up.exec_start("lab01-api", unit_dir).split()
    cmd = [systemd_run, "--quiet", f"--unit={name}", "--slice=lab01.slice"]
    for k, v in up.sandbox_props("lab01-api", unit_dir):
        cmd += ["-p", f"{k}={v}"]
    rc, _, err = runner(cmd + argv, 30)
    if rc != 0:
        return [("lab01-api", "démarrage réel", ("KO", f"rc={rc} {err.strip()[:200]}"))]
    import time

    token = tok.read_text().strip()
    codes = {}
    try:
        for label, hdr in (
            ("avec jeton", {"Authorization": f"Bearer {token}"}),
            ("sans jeton", {}),
        ):
            for _ in range(20):
                try:
                    req = urllib.request.Request(
                        "http://127.0.0.1:18090/lab/experiments", headers=hdr
                    )
                    codes[label] = urllib.request.urlopen(req, timeout=3).status
                    break
                except urllib.error.HTTPError as exc:
                    codes[label] = exc.code
                    break
                except OSError:
                    time.sleep(0.5)
    finally:
        runner(["systemctl", "stop", f"{name}.service"], 30)
    ok = codes.get("avec jeton") == 200 and codes.get("sans jeton") == 401
    return [
        (
            "lab01-api",
            "démarrage réel : 200 avec jeton, 401 sans",
            ("OK", str(codes)) if ok else ("KO", str(codes)),
        )
    ]


def main(argv=None, runner=default_runner):
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--unit-dir", default=str(up.UNIT_DIR))
    ap.add_argument("--systemd-run", default="systemd-run")
    ap.add_argument("--installed-dir", default="/etc/systemd/system")
    ap.add_argument(
        "--functional",
        action="store_true",
        help="lance aussi les vraies commandes (run, export, api)",
    )
    ap.add_argument("--list-coverage", action="store_true")
    a = ap.parse_args(argv)
    unit_dir = Path(a.unit_dir)
    if a.list_coverage:
        for u, k, s, why in coverage_report(unit_dir):
            print(f"{s:<11} {u}: {k} {why}")
        return 1 if up.coverage_gaps(unit_dir) else 0
    if os.geteuid() != 0:
        print("REFUS : root requis")
        return 3
    gaps = up.coverage_gaps(unit_dir)
    if gaps:
        print("KO  directives sans sonde ni exemption déclarée :", *gaps, sep="\n  ")
        return 1
    if (
        not Path("/sys/fs/cgroup/lab01.slice").exists()
        and not Path("/etc/systemd/system/lab01.slice").exists()
    ):
        print("ABANDON : lab01.slice absente (LAB non installé)")
        return 5
    rows = installed_matches(unit_dir, a.installed_dir)
    for u, cid, (v, why) in rows:
        print(f"{v:<12} {cid} — {why}")
    ev = evaluate(up.UNITS, unit_dir, runner, a.systemd_run)
    if ev is None:
        return 5
    rows += ev
    if a.functional:
        rows += functional(unit_dir, runner, a.systemd_run)
    print("--- directives NON sondées (dites explicitement, jamais supposées) ---")
    for u, k, s, why in coverage_report(unit_dir):
        if s == "NON SONDÉE":
            print(f"NON SONDÉE   {u}: {k} — {why}")
    counts = {}
    for _, _, (v, _) in rows:
        counts[v] = counts.get(v, 0) + 1
    print("RÉSUMÉ :", json.dumps(counts, ensure_ascii=False, sort_keys=True))
    if counts.get("KO"):
        return 1
    return 4 if counts.get("INDÉTERMINÉ") else 0


if __name__ == "__main__":
    sys.exit(main())
