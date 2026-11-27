"""Script opérateur P6-GOV-02 (révision RV) sur une racine factice, commandes système en bouchons.

Couvre : C1 (confinement, échecs de désactivation, unité collante, applicateur persistant),
installation transactionnelle (préconditions, refus ambigus, interruptions, états partiels),
rollback sans réactivation de R1 (dont échecs de restauration et sauvegarde altérée) et verify.
Les bouchons ne démontrent rien sur systemd réel : verify le dit explicitement en mode test.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "docs/agents/observation/pilot/schedule"
SCRIPT = HERE / "cat-obs-schedule-gov02-root.sh"
FAKE = Path(__file__).with_name("gov02_fake_system.py")
IS_ROOT = os.geteuid() == 0
API_FILES = ("observability/operator_api/app.py", "observability/operator_api/agent_schedule.py",
             "observability/operator_api/operator_identity.py")
WEB_SERVER = "frontend/scripts/web01_local_frontend_server.mjs"
OLD_PATHS = ("cat-obs-schedule.path", "cat-obs-schedule-dpa.path", "cat-obs-schedule-market.path")
HIST_API = "/home/op/releases/CAT-P6-api"
NEW_API = "/opt/rel/api"
NEW_WEB = "/opt/rel/web"
LOGINS = "op@example.test"

INSTALL_STUB = """#!/bin/bash
echo "install $*" >> "$STUB_DIR/calls.log"
if [ "$(id -u)" != 0 ]; then a=(); while [ $# -gt 0 ]; do case "$1" in -o|-g) shift 2;; *) a+=("$1"); shift;; esac; done; set -- "${a[@]}"; fi
exec /usr/bin/install "$@"
"""


@pytest.fixture()
def box(tmp_path):
    r = tmp_path / "root"
    units = r / "etc/systemd/system"
    for t, cal in (("cat-obs-cartographer", "hourly"), ("cat-obs-dpa", "*:30"), ("cat-obs-market", "*:3/10")):
        (units / f"{t}.timer.d").mkdir(parents=True)
        (units / f"{t}.timer").write_text("[Timer]\n")
        (units / f"{t}.timer.d/rhythm.conf").write_text(f"[Timer]\nOnCalendar=\nOnCalendar={cal}\n")
    for u in ("cat-obs-schedule", "cat-obs-schedule-dpa", "cat-obs-schedule-market"):
        (units / f"{u}.path").write_text(f"# ancienne {u}.path\n")
        (units / f"{u}.service").write_text(f"# ancien {u}.service\n")
    for svc, extra in (("crypto-operator-api", f"WorkingDirectory={HIST_API}\nBindReadOnlyPaths={HIST_API}\n"),
                       ("crypto-operator-web", "BindReadOnlyPaths=\nBindReadOnlyPaths=/opt/hist/dist:/x /opt/hist/server.mjs:/y\n")):
        (units / f"{svc}.service.d").mkdir()
        (units / f"{svc}.service.d" / ("z" * 40 + "-p6-eb492705.conf")).write_text("[Service]\n" + extra)
    (r / "usr/local/sbin").mkdir(parents=True)
    (r / "usr/local/sbin/cat-obs-schedule-apply").write_text("#!/bin/bash\n# ancien applicateur bash (R1)\n")
    (r / "srv/cat-obs/control").mkdir(parents=True)
    os.chmod(r / "srv/cat-obs/control", 0o2770)
    (r / "root").mkdir()
    for d in (r / "srv", r / "srv/cat-obs", r / "usr/local/sbin", units, r / "etc", r / "etc/systemd", r / "usr", r / "usr/local"):
        os.chmod(d, 0o755)
    api = r / NEW_API.lstrip("/")
    for f in API_FILES:
        (api / f).parent.mkdir(parents=True, exist_ok=True)
        (api / f).write_bytes((ROOT / f).read_bytes())
    web = r / NEW_WEB.lstrip("/")
    (web / "dist").mkdir(parents=True)
    (web / "server").mkdir()
    (web / "server/web01_local_frontend_server.mjs").write_bytes((ROOT / WEB_SERVER).read_bytes())

    stub = tmp_path / "stub"
    stub.mkdir()
    st = {"units": {u: {"enabled": "enabled", "active": "active"} for u in OLD_PATHS},
          "pids": {"crypto-operator-api.service": 100, "crypto-operator-web.service": 200}}
    st["units"].update({f"{t}.timer": {"enabled": "enabled", "active": "active"}
                        for t in ("cat-obs-cartographer", "cat-obs-dpa", "cat-obs-market")})
    st["units"]["crypto-operator-web.service"] = {"enabled": "enabled", "active": "active"}
    st["units"]["crypto-operator-api.service"] = {"enabled": "enabled", "active": "active"}
    st["units"].update({s: {"enabled": "static", "active": "inactive"} for s in
                        ("cat-obs-schedule.service", "cat-obs-schedule-dpa.service", "cat-obs-schedule-market.service")})
    (stub / "state.json").write_text(json.dumps(st))
    bins = tmp_path / "bin"
    bins.mkdir()
    fake = bins / "fake.py"
    fake.write_text("#!/usr/bin/env python3\n" + FAKE.read_text())
    os.chmod(fake, 0o755)
    for name in ("systemctl", "pgrep", "curl", "groupadd", "getent", "journalctl", "systemd-analyze", "tailscale", "ss"):
        os.symlink(fake, bins / name)
    (bins / "install").write_text(INSTALL_STUB)
    os.chmod(bins / "install", 0o755)
    grp = subprocess.run(["id", "-gn"], capture_output=True, text=True, check=True).stdout.strip()
    env = {**os.environ, "PATH": f"{bins}:{os.environ['PATH']}", "CAT_GOV02_ROOT": str(r), "CAT_GOV02_TEST": "1",
           "CAT_GOV02_GROUP_SCHED": grp, "CAT_GOV02_GROUP_READ": grp, "CAT_GOV02_GROUP_RELAY": grp,
           "CAT_GOV02_WAIT_S": "1", "STUB_DIR": str(stub)}
    return {"r": r, "units": units, "env": env, "stub": stub}


def run(b, *args):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=b["env"], timeout=120, check=False)


def install(b):
    return run(b, "install", "--logins", LOGINS, "--api-release", NEW_API, "--web-release", NEW_WEB)


def state(b):
    return json.loads((b["stub"] / "state.json").read_text())


def calls(b):
    p = b["stub"] / "calls.log"
    return p.read_text().splitlines() if p.exists() else []


def fail(b, *rules):
    (b["stub"] / "fail").write_text("\n".join(rules) + "\n")


def rhythms(b):
    return {t: (b["units"] / f"{t}.timer.d/rhythm.conf").read_bytes() for t in ("cat-obs-cartographer", "cat-obs-dpa", "cat-obs-market")}


def old_paths_contained(b):
    s = state(b)["units"]
    return all(s[u]["enabled"] != "enabled" and s[u]["active"] != "active" for u in OLD_PATHS)


def last_state(b):
    return (b["r"] / "root/p6-gov-02-state").read_text().splitlines()[-1].split()[0]


def mutating(b):
    return [c for c in calls(b) if c.split()[:2][-1] in ("enable", "disable", "stop", "restart", "daemon-reload")
            and c.startswith("systemctl")]


# ── Mission 1 : C1 ────────────────────────────────────────────────────────────────────────────

def test_c1_check_is_read_only(box):
    out = run(box, "contain", "--check")
    assert out.returncode == 0 and "enabled=enabled" in out.stdout
    assert mutating(box) == [] and not list((box["r"] / "root").iterdir())


def test_c1_contains_only_the_three_old_path_units(box):
    before = rhythms(box)
    out = run(box, "contain")
    assert out.returncode == 0, out.stderr
    assert old_paths_contained(box)
    assert rhythms(box) == before
    s = state(box)["units"]
    assert all(s[f"{t}.timer"] == {"enabled": "enabled", "active": "active"} for t in ("cat-obs-cartographer", "cat-obs-dpa", "cat-obs-market"))
    assert mutating(box) == [f"systemctl disable --now {u}" for u in OLD_PATHS]
    c1 = next((box["r"] / "root").glob("p6-gov-02-c1-*"))
    assert (c1 / "c1.before").read_text() != (c1 / "c1.after").read_text()
    assert (c1 / "rhythms.before").read_text() == (c1 / "rhythms.after").read_text()
    again = run(box, "contain")  # idempotent
    assert again.returncode == 0 and "C1 déjà en place" in again.stdout


def test_c1_disable_failure_is_not_ignored(box):
    fail(box, "disable:cat-obs-schedule-dpa.path")
    out = run(box, "contain")
    assert out.returncode != 0 and "échec de la désactivation de cat-obs-schedule-dpa.path" in out.stderr
    assert state(box)["units"]["cat-obs-schedule-market.path"]["enabled"] == "enabled"  # rien d'autre tenté


def test_c1_sticky_unit_is_detected(box):
    fail(box, "sticky:cat-obs-schedule-market.path")
    out = run(box, "contain")
    assert out.returncode != 0 and "C1 incomplet" in out.stderr


def test_c1_running_old_applier_is_detected(box):
    (box["stub"] / "procs").write_text("4242 /bin/bash /usr/local/sbin/cat-obs-schedule-apply\n")
    out = run(box, "contain")
    assert out.returncode != 0 and "C1 incomplet" in out.stderr


# ── Mission 3 : installation transactionnelle ─────────────────────────────────────────────────

def test_install_happy_path_then_verify(box):
    before = rhythms(box)
    out = install(box)
    assert out.returncode == 0, out.stdout + out.stderr
    assert last_state(box) == "INSTALLED" and rhythms(box) == before
    assert old_paths_contained(box) or state(box)["units"]["cat-obs-schedule.path"]["active"] == "active"
    s = state(box)["units"]
    assert s["cat-obs-schedule-dpa.path"]["active"] != "active" and s["cat-obs-schedule-market.path"]["active"] != "active"
    assert s["cat-obs-schedule.path"] == {"enabled": "enabled", "active": "active"}
    units = box["units"]
    for gone in ("cat-obs-schedule-dpa.path", "cat-obs-schedule-dpa.service", "cat-obs-schedule-market.path", "cat-obs-schedule-market.service"):
        assert not (units / gone).exists()
    api = next((units / "crypto-operator-api.service.d").glob("*-p6-gov02.conf")).read_text()
    assert f"WorkingDirectory={NEW_API}" in api and "CAT_RELAY_TOKEN_FILE=/etc/cat-obs/relay.token" in api
    assert "ReadWritePaths=\n" not in api and "SupplementaryGroups=\n" not in api
    tok = box["r"] / "etc/cat-obs/relay.token"
    assert oct(tok.stat().st_mode & 0o777) == "0o640" and len(tok.read_text().strip()) == 64
    assert "relay.token" not in out.stdout and tok.read_text().strip() not in out.stdout + out.stderr
    assert os.stat(box["r"] / "srv/cat-obs/control").st_mode & 0o020 == 0
    order = [c for c in calls(box) if c.startswith("systemctl disable") or c.startswith("systemctl restart")]
    assert order[0].startswith("systemctl disable --now cat-obs-schedule.path"), "C1 avant toute autre mutation"
    v = run(box, "verify")
    assert v.returncode == 0, v.stdout + v.stderr
    assert "compatibilité systemd NON démontrée" in v.stdout


@pytest.mark.parametrize("case", ["logins", "release_mismatch", "release_missing", "control_suspect", "group_writable_parent", "analyze"])
def test_install_refusals_happen_before_any_mutation(box, case):
    args = ["install", "--logins", LOGINS, "--api-release", NEW_API, "--web-release", NEW_WEB]
    if case == "logins":
        args[2] = "op;rm -rf /"
    elif case == "release_mismatch":
        (box["r"] / NEW_API.lstrip("/") / API_FILES[1]).write_text("# modifié\n")
    elif case == "release_missing":
        args[4] = "/opt/absent"
    elif case == "control_suspect":
        os.symlink("/etc/shadow", box["r"] / "srv/cat-obs/control/.status.tmp")
    elif case == "group_writable_parent":
        os.chmod(box["r"] / "srv/cat-obs", 0o775)
    elif case == "analyze":
        fail(box, "analyze")
    out = run(box, *args)
    assert out.returncode != 0 and "REFUS" in out.stderr
    assert mutating(box) == [] and not (box["r"] / "root/p6-gov-02-state").exists()
    assert not (box["r"] / "srv/cat-obs/schedule").exists()
    if case == "control_suspect":
        assert os.path.islink(box["r"] / "srv/cat-obs/control/.status.tmp")


def test_reinstall_is_refused_when_installed_or_partial(box):
    assert install(box).returncode == 0
    again = install(box)
    assert again.returncode != 0 and "ambiguë" in again.stderr


@pytest.mark.parametrize("rule,phase", [("stop:crypto-operator-web.service", "web-stop"),
                                        ("start:crypto-operator-web.service", "web-start"),
                                        ("daemon-reload", "reload"),
                                        ("kill:daemon-reload", "reload"),
                                        ("kill:restart", "restart")])
def test_interrupted_install_is_partial_and_keeps_r1_contained(box, rule, phase):
    fail(box, rule)
    out = install(box)
    assert out.returncode != 0
    lines = (box["r"] / "root/p6-gov-02-state").read_text().splitlines()
    assert lines[-1].split()[:2] == ["PARTIAL", phase], lines
    assert "rollback" in out.stderr
    s = state(box)["units"]
    assert s["cat-obs-schedule-dpa.path"]["enabled"] != "enabled" and s["cat-obs-schedule-market.path"]["enabled"] != "enabled"
    assert install(box).returncode != 0  # réinstallation refusée tant que l'état est PARTIAL


def test_disable_failure_during_install_stops_before_new_chain(box):
    fail(box, "disable:cat-obs-schedule-market.path")
    out = install(box)
    assert out.returncode != 0
    assert (box["r"] / "root/p6-gov-02-state").read_text().splitlines()[-1].startswith("PARTIAL c1")
    assert not (box["r"] / "srv/cat-obs/schedule").exists() and not (box["r"] / "etc/cat-obs/relay.token").exists()


# ── Mission 4 : rollback sans R1 ──────────────────────────────────────────────────────────────

def ts_of(b):
    return next((b["r"] / "root").glob("p6-gov-02-backup-*")).name.rsplit("-", 1)[1]


def test_rollback_restores_history_without_reenabling_r1(box):
    before = rhythms(box)
    assert install(box).returncode == 0
    out = run(box, "rollback", ts_of(box))
    assert out.returncode == 0, out.stdout + out.stderr
    assert last_state(box) == "ROLLED_BACK"
    s = state(box)["units"]
    for u in OLD_PATHS:
        assert s[u]["enabled"] != "enabled" and s[u]["active"] != "active", u
    enables = [c for c in calls(box) if c.startswith("systemctl enable")]
    # celles de l'installation ; aucune au retour arrière
    assert enables == ["systemctl enable --now cat-obs-schedule.path", "systemctl enable --now crypto-operator-web.socket"], enables
    units = box["units"]
    assert not list((units / "crypto-operator-api.service.d").glob("*-p6-gov02.conf"))
    assert not (units / "cat-obs-schedule.path").exists() and not (units / "cat-obs-schedule-dpa.path").exists()
    show = subprocess.run(["systemctl", "show", "crypto-operator-api.service", "-p", "WorkingDirectory", "--value"],
                          capture_output=True, text=True, env=box["env"], check=True).stdout.strip()
    assert show == HIST_API
    assert rhythms(box) == before
    assert (box["r"] / "usr/local/sbin/cat-obs-schedule-apply").read_text() == \
        (HERE / "cat-obs-schedule-apply.py").read_text(), "l'ancien applicateur vulnérable n'est pas réinstallé"
    assert "indisponible en écriture" in out.stdout
    assert os.stat(box["r"] / "srv/cat-obs/control").st_mode & 0o020 == 0


def test_rollback_restore_failure_never_reopens_r1(box):
    assert install(box).returncode == 0
    fail(box, "restart:crypto-operator-api.service")
    out = run(box, "rollback", ts_of(box))
    assert out.returncode != 0 and "ne sont pas réactivées" in out.stderr
    assert (box["r"] / "root/p6-gov-02-state").read_text().splitlines()[-1].startswith("ROLLBACK_PARTIAL")
    s = state(box)["units"]
    assert all(s[u]["enabled"] != "enabled" for u in OLD_PATHS)


def test_rollback_refuses_altered_backup(box):
    assert install(box).returncode == 0
    ts = ts_of(box)
    (box["r"] / f"root/p6-gov-02-backup-{ts}/rhythms").write_text("altéré\n")
    n = len(mutating(box))
    out = run(box, "rollback", ts)
    assert out.returncode != 0 and "altérée" in out.stderr
    assert len(mutating(box)) == n
    assert list((box["units"] / "crypto-operator-api.service.d").glob("*-p6-gov02.conf"))


def test_rollback_rejects_bad_timestamps(box):
    assert run(box, "rollback", "../../etc").returncode != 0
    assert run(box, "rollback", "20260101T000000Z").returncode != 0


# ── Mission 5 : verify ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("drift", ["applier", "rhythm", "release", "route", "dpa_active", "control",
                                   "serve_tcp", "tcp_listener", "socket_gone"])
def test_verify_detects_drift(box, drift):
    assert install(box).returncode == 0
    if drift == "applier":
        (box["r"] / "usr/local/sbin/cat-obs-schedule-apply").write_text("# modifié\n")
    elif drift == "rhythm":
        (box["units"] / "cat-obs-dpa.timer.d/rhythm.conf").write_text("[Timer]\nOnCalendar=*:0/1\n")
    elif drift == "release":
        (box["r"] / NEW_API.lstrip("/") / API_FILES[0]).write_text("# modifié\n")
    elif drift == "route":
        (box["stub"] / "routes.json").write_text(json.dumps({"http://127.0.0.1:8090/api/operator/v1/runtime-service": "503"}))
    elif drift == "dpa_active":
        st = state(box)
        st["units"]["cat-obs-schedule-dpa.path"]["active"] = "active"
        (box["stub"] / "state.json").write_text(json.dumps(st))
    elif drift == "control":
        os.chmod(box["r"] / "srv/cat-obs/control", 0o2770)
    elif drift == "serve_tcp":
        st = state(box)
        st["serve"]["443"] = "http://127.0.0.1:8181"
        (box["stub"] / "state.json").write_text(json.dumps(st))
    elif drift == "tcp_listener":
        fail(box, "tcp8181")
    elif drift == "socket_gone":
        (box["r"] / "run/cat-operator-web.sock").unlink()
    v = run(box, "verify")
    assert v.returncode != 0 and "ÉCART" in v.stdout


def test_verify_without_install_fails(box):
    v = run(box, "verify")
    assert v.returncode != 0 and "ÉCART état" in v.stdout


# ── P6-GOV-03 : frontière d'identité par socket systemd ──────────────────────────────────────

def serve(b):
    return state(b)["serve"]


def test_install_moves_relay_to_root_socket_and_closes_tcp(box):
    out = install(box)
    assert out.returncode == 0, out.stdout + out.stderr
    units = box["units"]
    assert (units / "crypto-operator-web.socket").read_bytes() == (HERE / "crypto-operator-web.socket").read_bytes()
    sock_unit = (HERE / "crypto-operator-web.socket").read_text()
    for d in ("ListenStream=/run/cat-operator-web.sock", "SocketUser=root", "SocketGroup=root", "SocketMode=0600"):
        assert d in sock_unit
    web = next((units / "crypto-operator-web.service.d").glob("*-p6-gov02.conf")).read_text()
    assert "Requires=crypto-operator-web.socket" in web and "After=crypto-operator-web.socket" in web
    assert "Environment=CAT_WEB_LISTEN=systemd" in web
    assert (box["r"] / "run/cat-operator-web.sock").exists()
    ss = subprocess.run(["ss", "-ltnH", "sport = :8181"], capture_output=True, text=True, env=box["env"], check=True)
    assert ss.stdout == "", "aucun écouteur TCP 8181 après migration"
    assert serve(box) == {"443": "unix:/run/cat-operator-web.sock", "8443": "http://127.0.0.1:18908"}
    order = [c for c in calls(box) if c.startswith(("systemctl stop crypto-operator-web.service",
                                                     "systemctl enable --now crypto-operator-web.socket",
                                                     "systemctl start crypto-operator-web.service", "tailscale serve --bg"))]
    # P7-RUNTIME-R01 : Web arrêté, puis socket, puis Web (descripteur systemd), puis Serve
    assert [c.split()[1] for c in order] == ["stop", "enable", "start", "serve"], order
    assert not any("already active, refusing" in c for c in calls(box))
    b = next((box["r"] / "root").glob("p6-gov-02-backup-*"))
    assert "443 / http://127.0.0.1:8181" in (b / "serve.targets").read_text()
    v = run(box, "verify")
    assert v.returncode == 0, v.stdout + v.stderr
    for line in ("aucun écouteur TCP 8181", "tailscale serve 443 → socket", "autres entrées tailscale serve inchangées",
                 "relais (socket) : sans identité Tailscale refusé"):
        assert line in v.stdout, line


def test_install_refuses_when_serve_target_is_unexpected(box):
    st = state(box)
    st["serve"] = {"443": "http://127.0.0.1:9999", "8443": "http://127.0.0.1:18908"}
    (box["stub"] / "state.json").write_text(json.dumps(st))
    out = install(box)
    assert out.returncode != 0 and "ambiguë" in out.stderr
    assert mutating(box) == [] and not (box["r"] / "root/p6-gov-02-state").exists()


def test_install_fails_closed_if_relay_still_listens_on_tcp(box):
    fail(box, "tcp8181")
    out = install(box)
    assert out.returncode != 0 and "127.0.0.1:8181 encore à l'écoute après l'arrêt du Web" in out.stderr
    assert last_state(box) == "PARTIAL"
    assert (box["r"] / "root/p6-gov-02-state").read_text().splitlines()[-1].split()[:2] == ["PARTIAL", "web-stop"]
    assert state(box)["units"].get("crypto-operator-web.socket", {}).get("active") != "active", "socket jamais démarrée"
    assert serve(box)["443"] == "http://127.0.0.1:8181", "Serve n'est pas basculé tant que TCP reste ouvert"


def test_serve_failure_is_partial_and_rollback_restores_tcp_route(box):
    before = rhythms(box)
    fail(box, "serve")
    out = install(box)
    assert out.returncode != 0
    assert (box["r"] / "root/p6-gov-02-state").read_text().splitlines()[-1].split()[:2] == ["PARTIAL", "serve"]
    (box["stub"] / "fail").unlink()
    rb = run(box, "rollback", ts_of(box))
    assert rb.returncode == 0, rb.stdout + rb.stderr
    assert serve(box) == {"443": "http://127.0.0.1:8181", "8443": "http://127.0.0.1:18908"}
    assert not (box["units"] / "crypto-operator-web.socket").exists() and not (box["r"] / "run/cat-operator-web.sock").exists()
    assert old_paths_contained(box) and rhythms(box) == before


def test_rollback_restores_tcp_relay_and_serve_but_keeps_c1(box):
    assert install(box).returncode == 0
    out = run(box, "rollback", ts_of(box))
    assert out.returncode == 0, out.stdout + out.stderr
    assert serve(box) == {"443": "http://127.0.0.1:8181", "8443": "http://127.0.0.1:18908"}
    ss = subprocess.run(["ss", "-ltnH", "sport = :8181"], capture_output=True, text=True, env=box["env"], check=True)
    assert "127.0.0.1:8181" in ss.stdout
    assert state(box)["units"]["crypto-operator-web.socket"]["enabled"] != "enabled"
    assert not (box["units"] / "crypto-operator-web.socket").exists()
    assert old_paths_contained(box)
    seq = [c for c in calls(box) if "crypto-operator-web.socket" in c and "disable" in c or c.startswith("tailscale serve --bg")]
    assert seq[-2].startswith("systemctl disable --now crypto-operator-web.socket") and seq[-1].endswith("http://127.0.0.1:8181")
    assert "limite locale connue" in out.stdout


# ── P7-RUNTIME-R01 : transition TCP → socket et reprise après rollback ─────────────────────────

def test_r01_fake_systemd_refuses_socket_while_web_active(box):
    """Non-régression : le bouchon reproduit le refus réel de systemd 249 (journal du 2026-11-27 00:47:48Z)."""
    env = box["env"]
    subprocess.run(["systemctl", "restart", "crypto-operator-web.service"], env=env, check=True)
    r = subprocess.run(["systemctl", "enable", "--now", "crypto-operator-web.socket"], env=env, capture_output=True, check=False)
    assert r.returncode == 1
    assert any("Socket service crypto-operator-web.service already active, refusing" in c for c in calls(box))
    assert state(box)["units"]["crypto-operator-web.socket"]["active"] != "active"


def test_r01_old_order_reproduces_partial_restart(box):
    """L'ancien ordre (socket démarrée pendant que le Web tourne) échoue : c'est l'échec du 2026-11-27."""
    env = box["env"]
    subprocess.run(["systemctl", "restart", "crypto-operator-web.service"], env=env, check=True)
    script = "set -e; systemctl enable --now crypto-operator-web.socket; systemctl restart crypto-operator-web.service"
    old = subprocess.run(["bash", "-c", script], env=env, capture_output=True, check=False)
    assert old.returncode != 0


def test_r01_web_is_stopped_before_socket_and_relay_checked_before_serve(box):
    out = install(box)
    assert out.returncode == 0, out.stdout + out.stderr
    steps = [line.split()[1] for line in (box["r"] / "root/p6-gov-02-state").read_text().splitlines() if line.startswith("STEP ")]
    i = steps.index
    assert i("restart") < i("web-stop") < i("socket-start") < i("web-start") < i("relay-check") < i("serve"), steps
    c = calls(box)
    stop = c.index("systemctl stop crypto-operator-web.service")
    sock = c.index("systemctl enable --now crypto-operator-web.socket")
    assert stop < sock
    assert any("--unix-socket" in x for x in c[sock:]), "relais interrogé par la socket avant Serve"
    assert "relais servi par la socket" in out.stdout


def test_r01_relay_unreachable_on_socket_keeps_serve_on_tcp_and_rolls_back(box):
    (box["stub"] / "routes.json").write_text(json.dumps({"http://127.0.0.1:8181/": "502"}))
    out = install(box)
    assert out.returncode != 0 and "relais injoignable par la socket" in out.stderr
    assert (box["r"] / "root/p6-gov-02-state").read_text().splitlines()[-1].split()[:2] == ["PARTIAL", "relay-check"]
    assert serve(box)["443"] == "http://127.0.0.1:8181", "Serve non modifié avant la preuve du relais"
    (box["stub"] / "routes.json").unlink()
    rb = run(box, "rollback", ts_of(box))
    assert rb.returncode == 0, rb.stdout + rb.stderr
    assert last_state(box) == "ROLLED_BACK" and old_paths_contained(box)


def test_r01_reinstall_after_rollback_succeeds(box):
    before = rhythms(box)
    assert install(box).returncode == 0
    tok1 = (box["r"] / "etc/cat-obs/relay.token").read_text()
    assert run(box, "rollback", ts_of(box)).returncode == 0
    assert (box["r"] / "srv/cat-obs/schedule").is_dir(), "résidus inertes laissés par le rollback"
    again = install(box)
    assert again.returncode == 0, again.stdout + again.stderr
    assert last_state(box) == "INSTALLED"
    assert (box["r"] / "etc/cat-obs/relay.token").read_text() != tok1, "jeton régénéré"
    v = run(box, "verify")
    assert v.returncode == 0, v.stdout + v.stderr
    assert "état INSTALLED" in v.stdout and "cat-obs-schedule-dpa.path inactive" in v.stdout
    assert rhythms(box) == before


def test_r01_reinstall_after_partial_then_rollback_succeeds(box):
    fail(box, "start:crypto-operator-web.service")
    assert install(box).returncode != 0
    assert install(box).returncode != 0, "PARTIAL : réinstallation refusée avant rollback"
    (box["stub"] / "fail").unlink()
    assert run(box, "rollback", ts_of(box)).returncode == 0
    again = install(box)
    assert again.returncode == 0, again.stdout + again.stderr
    assert run(box, "verify").returncode == 0


def test_r01_reinstall_refused_when_previous_requests_remain(box):
    assert install(box).returncode == 0
    assert run(box, "rollback", ts_of(box)).returncode == 0
    req = box["r"] / "srv/cat-obs/schedule/requests/residuelle.json"
    req.write_text('{"rhythm": "1h"}')
    again = install(box)
    assert again.returncode != 0 and "demandes antérieures" in again.stderr
    assert req.exists() and last_state(box) == "ROLLED_BACK"
