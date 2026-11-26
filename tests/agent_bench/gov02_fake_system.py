"""Bouchons des commandes système pour tester cat-obs-schedule-gov02-root.sh sur une racine factice.

Un seul fichier, appelé sous le nom de la commande (systemctl, pgrep, curl, …) via des liens.
État dans $STUB_DIR/state.json ; journal des appels dans $STUB_DIR/calls.log.
Injection d'échecs : $STUB_DIR/fail (une règle par ligne) :
  disable:<unité>     la désactivation échoue (code 1)
  sticky:<unité>      la désactivation « réussit » mais l'unité reste active
  restart:<unité>     le redémarrage échoue
  daemon-reload       le rechargement échoue
  kill:<verbe>        le script appelant reçoit SIGTERM pendant ce verbe (interruption)
  analyze             systemd-analyze verify échoue
Aucune de ces commandes ne touche le système réel.
"""
import json
import os
import re
import signal
import sys
from pathlib import Path

D = Path(os.environ["STUB_DIR"])
ROOT = Path(os.environ["CAT_GOV02_ROOT"])
UNITS = ROOT / "etc/systemd/system"
STATE = D / "state.json"


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {"units": {}, "pids": {}}


def save(st):
    STATE.write_text(json.dumps(st))


def rules():
    f = D / "fail"
    return set(f.read_text().split()) if f.exists() else set()


def log(name, args):
    with open(D / "calls.log", "a") as f:
        f.write(" ".join([name, *args]) + "\n")


def maybe_kill(verb):
    if f"kill:{verb}" in rules():
        os.kill(os.getppid(), signal.SIGTERM)


def unit(st, u):
    if u not in st["units"]:
        st["units"][u] = {"enabled": "disabled" if (UNITS / u).exists() else "", "active": "inactive"}
    return st["units"][u]


def directives(u):
    """Valeurs effectives d'une directive : fichier de base puis drop-ins triés ; « X= » vide remet à zéro."""
    files = []
    if (UNITS / u).is_file():
        files.append(UNITS / u)
    dd = UNITS / f"{u}.d"
    if dd.is_dir():
        files += sorted(p for p in dd.iterdir() if p.suffix == ".conf")
    out = {}
    for f in files:
        for line in f.read_text().splitlines():
            m = re.match(r"^([A-Za-z]+)=(.*)$", line)
            if not m:
                continue
            k, v = m.groups()
            if k in ("BindReadOnlyPaths", "Environment", "SupplementaryGroups", "ReadWritePaths"):
                out[k] = [] if v == "" else out.get(k, []) + [v]
            else:
                out[k] = [v]
    return {k: " ".join(v) for k, v in out.items()}


def systemctl(args):
    st = load()
    r = rules()
    if args[:1] == ["--version"]:
        print("systemd 249 (bouchon de test)")
        return 0
    verb, rest = args[0], args[1:]
    maybe_kill(verb)
    if verb == "is-enabled":
        e = unit(st, rest[0])["enabled"]
        print(e)
        save(st)
        return 0 if e == "enabled" else 1
    if verb == "is-active":
        a = unit(st, rest[0])["active"]
        print(a)
        save(st)
        return 0 if a == "active" else 3
    if verb in ("disable", "enable", "stop", "restart"):
        now = "--now" in rest
        for u in [x for x in rest if not x.startswith("--")]:
            if f"{verb}:{u}" in r:
                save(st)
                return 1
            s = unit(st, u)
            if verb == "disable":
                s["enabled"] = "disabled"
                if now and f"sticky:{u}" not in r:
                    s["active"] = "inactive"
            elif verb == "enable":
                s["enabled"] = "enabled"
                if now:
                    s["active"] = "active"
            elif verb == "stop":
                s["active"] = "inactive"
            else:
                s["active"] = "active"
                st["pids"][u] = st["pids"].get(u, 100) + 1
        save(st)
        return 0
    if verb == "daemon-reload":
        return 1 if "daemon-reload" in r else 0
    if verb == "show":
        u = rest[0]
        props = [rest[i + 1] for i, x in enumerate(rest) if x == "-p"]
        dv = directives(u)
        for p in props:
            v = str(st["pids"].get(u, 0)) if p == "MainPID" else dv.get(p, "")
            print(v if "--value" in rest else f"{p}={v}")
        save(st)
        return 0
    return 0


def curl(args):
    url = next(a for a in args if a.startswith("http"))
    codes = json.loads((D / "routes.json").read_text()) if (D / "routes.json").exists() else {}
    if "-w" in args:
        print(codes.get(url, "200"), end="")
        return 0
    if url.endswith(":8090/api/operator/v1/operator-identity"):
        print('{"identity":null,"authorized":false,"reason":"RELAY_TOKEN_INVALID"}')
    elif url.endswith(":8181/api/operator/v1/operator-identity"):
        print('{"identity":null,"authorized":false,"reason":"OPERATOR_IDENTITY_REQUIRED"}')
    else:
        print("{}")
    return 0


def pgrep(args):
    procs = (D / "procs").read_text().splitlines() if (D / "procs").exists() else []
    pat = args[-1]
    return 0 if any(pat in p for p in procs) else 1


def main():
    name = Path(sys.argv[0]).name
    args = sys.argv[1:]
    log(name, args)
    if name == "systemctl":
        return systemctl(args)
    if name == "curl":
        return curl(args)
    if name == "pgrep":
        return pgrep(args)
    if name == "systemd-analyze":
        return 1 if "analyze" in rules() else 0
    if name == "tailscale":
        print("https://example.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8181")
        return 0
    return 0  # groupadd, getent, journalctl


if __name__ == "__main__":
    sys.exit(main())
