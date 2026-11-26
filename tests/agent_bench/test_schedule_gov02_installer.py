"""Installateur P6-GOV-02 (T10, T13) sur une racine factice, commandes système remplacées par des bouchons.

Vérifie : sauvegarde, retrait des unités DPA/Market, rythmes des trois timers inchangés, drop-ins
API/Web, retour arrière octet à octet. Aucun appel réel à systemctl ni groupadd.
"""
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "docs/agents/observation/pilot/schedule"
SCRIPT = HERE / "cat-obs-schedule-gov02-root.sh"
IS_ROOT = os.geteuid() == 0

STUB = """#!/bin/bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
case "$(basename "$0")" in
  systemctl) [ "$1" = is-enabled ] && { case "$2" in *dpa.path|*market.path|cat-obs-schedule.path) exit 0;; esac; exit 1; }; exit 0 ;;
  getent) exit 0 ;;
  install)
    # Hors root, -o/-g ne peuvent pas être appliqués : on les retire, le reste est la vraie commande.
    if [ "$(id -u)" != 0 ]; then a=(); while [ $# -gt 0 ]; do case "$1" in -o|-g) shift 2;; *) a+=("$1"); shift;; esac; done; set -- "${a[@]}"; fi
    exec /usr/bin/install "$@" ;;
esac
exit 0
"""


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture()
def fake(tmp_path):
    r = tmp_path / "root"
    units = r / "etc/systemd/system"
    for t, cal in (("cat-obs-cartographer", "hourly"), ("cat-obs-dpa", "*:30"), ("cat-obs-market", "*:3/10")):
        (units / f"{t}.timer.d").mkdir(parents=True)
        (units / f"{t}.timer").write_text("[Timer]\n")
        (units / f"{t}.timer.d/rhythm.conf").write_text(f"[Timer]\nOnCalendar=\nOnCalendar={cal}\n")
    for u in ("cat-obs-schedule", "cat-obs-schedule-dpa", "cat-obs-schedule-market"):
        (units / f"{u}.path").write_text(f"# ancienne {u}.path\n")
        (units / f"{u}.service").write_text(f"# ancien {u}.service\n")
    (r / "usr/local/sbin").mkdir(parents=True)
    (r / "usr/local/sbin/cat-obs-schedule-apply").write_text("#!/bin/bash\n# ancien applicateur bash (R1)\n")
    (r / "srv/cat-obs/control").mkdir(parents=True)
    os.chmod(r / "srv/cat-obs/control", 0o2770)
    (r / "root").mkdir()
    bins = tmp_path / "bin"
    bins.mkdir()
    for name in ("systemctl", "groupadd", "getent", "install"):
        (bins / name).write_text(STUB)
        os.chmod(bins / name, 0o755)
    log = tmp_path / "stub.log"
    grp = subprocess.run(["id", "-gn"], capture_output=True, text=True).stdout.strip()
    env = {**os.environ, "PATH": f"{bins}:{os.environ['PATH']}", "CAT_GOV02_ROOT": str(r), "CAT_GOV02_TEST": "1",
           "CAT_GOV02_GROUP_SCHED": grp, "CAT_GOV02_GROUP_READ": grp, "STUB_LOG": str(log)}
    return r, units, env, log


def run(env, *args):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60)


def rhythms(units):
    return {t: sha(units / f"{t}.timer.d/rhythm.conf") for t in ("cat-obs-cartographer", "cat-obs-dpa", "cat-obs-market")}


def test_refuses_bad_login_list(fake):
    _, _, env, _ = fake
    for bad in ("", "a b", "x;rm -rf /", "op@example.test,", "$(id)"):
        r = run(env, "install", bad)
        assert r.returncode != 0 and "invalide" in r.stderr


def test_t10_install_then_verify_then_rollback(fake):
    r, units, env, log = fake
    before_rhythms = rhythms(units)
    old = {p.name: p.read_bytes() for p in units.iterdir() if p.name.startswith("cat-obs-schedule")}
    old_applier = (r / "usr/local/sbin/cat-obs-schedule-apply").read_bytes()

    out = run(env, "install", "op@example.test,second@example.test")
    assert out.returncode == 0, out.stderr
    assert rhythms(units) == before_rhythms
    for gone in ("cat-obs-schedule-dpa.path", "cat-obs-schedule-dpa.service",
                 "cat-obs-schedule-market.path", "cat-obs-schedule-market.service"):
        assert not (units / gone).exists()
    assert sha(r / "usr/local/sbin/cat-obs-schedule-apply") == sha(HERE / "cat-obs-schedule-apply.py")
    assert sha(units / "cat-obs-schedule.path") == sha(HERE / "cat-obs-schedule.path")
    assert oct(os.stat(r / "srv/cat-obs/schedule/requests").st_mode & 0o7777) == "0o2730"
    assert oct(os.stat(r / "srv/cat-obs/schedule/state").st_mode & 0o7777) == "0o2750"
    assert os.stat(r / "srv/cat-obs/control").st_mode & 0o020 == 0
    api = (units / "crypto-operator-api.service.d/zzzzzzzzzzzzzz-schedule-gov02.conf").read_text()
    assert "ReadWritePaths=/srv/cat-obs/schedule/requests\n" in api
    assert "ReadWritePaths=\n" not in api and "SupplementaryGroups=\n" not in api  # ajouts seulement
    assert "Environment=CAT_OPERATOR_LOGINS=op@example.test,second@example.test" in api
    assert "UnsetEnvironment=AGENT_SCHEDULE_ALLOW_TEST" in api and "/srv/cat-obs/control" not in api
    web = (units / "crypto-operator-web.service.d/zzzzzz-schedule-gov02.conf").read_text()
    assert "CAT_OPERATOR_LOGINS=op@example.test,second@example.test" in web
    calls = log.read_text()
    assert "systemctl disable --now cat-obs-schedule.path cat-obs-schedule-dpa.path cat-obs-schedule-market.path" in calls
    assert "systemctl enable --now cat-obs-schedule.path" in calls
    sysctl = "\n".join(ln for ln in calls.splitlines() if ln.startswith("systemctl ") and not ln.startswith(("systemctl show", "systemctl is-enabled")))
    assert not any(x in sysctl for x in ("cat-obs-cartographer.timer", "cat-obs-dpa.timer", "cat-obs-market.timer",
                                        "crypto-operator-api", "crypto-operator-web", "restart"))

    v = run(env, "verify")
    if IS_ROOT:
        assert v.returncode == 0 and "verify OK" in v.stdout, v.stdout + v.stderr
    else:  # propriétaire root impossible hors root : seuls les écarts de propriétaire sont admis
        assert all(ln.startswith(("ÉCART requests", "ÉCART state")) for ln in v.stdout.splitlines() if "ÉCART" in ln)

    ts = next(p.name.rsplit("-", 1)[1] for p in (r / "root").iterdir() if p.name.startswith("p6-gov-02-backup-"))
    back = run(env, "rollback", ts)
    assert back.returncode == 0, back.stderr
    assert {p.name: p.read_bytes() for p in units.iterdir() if p.name.startswith("cat-obs-schedule")} == old
    assert (r / "usr/local/sbin/cat-obs-schedule-apply").read_bytes() == old_applier
    assert oct(os.stat(r / "srv/cat-obs/control").st_mode & 0o7777) == "0o2770"
    assert not (units / "crypto-operator-api.service.d/zzzzzzzzzzzzzz-schedule-gov02.conf").exists()
    assert rhythms(units) == before_rhythms
    assert (r / "srv/cat-obs/schedule").is_dir()  # conservé comme preuve
    assert "R1 est rouvert" in back.stdout


def test_t13_preflight_flags_planted_links_without_deleting(fake, tmp_path):
    r, _, env, _ = fake
    victim = tmp_path / "victim"
    victim.write_text("x")
    os.symlink(victim, r / "srv/cat-obs/control/.status.tmp")
    out = run(env, "preflight")
    assert out.returncode != 0 and "INCIDENT" in out.stderr
    assert os.path.islink(r / "srv/cat-obs/control/.status.tmp") and victim.read_text() == "x"
    assert run(env, "install", "op@example.test").returncode != 0
    assert not (r / "srv/cat-obs/schedule").exists()


def test_rollback_requires_a_real_backup(fake):
    _, _, env, _ = fake
    assert run(env, "rollback", "../../etc").returncode != 0
    assert run(env, "rollback", "20260101T000000Z").returncode != 0
