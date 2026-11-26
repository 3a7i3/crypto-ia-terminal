"""Applicateur root du programmateur (P6-GOV-02) : T1–T4, en environnement temporaire uniquement.

L'applicateur est chargé depuis docs/ avec une configuration de test : racine temporaire, dossier
d'unités temporaire, propriétaire attendu = utilisateur courant, faux systemctl qui journalise ses
arguments. Aucun appel réel à systemd, aucune écriture hors de tmp_path.
"""
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs/agents/observation/pilot/schedule/cat-obs-schedule-apply.py"

FAKE_SYSTEMCTL = r'''
import json, os, sys
log, state = sys.argv[1], sys.argv[2]
args = sys.argv[3:]
with open(log, "a") as f:
    f.write(json.dumps(args) + "\n")
enabled = json.load(open(state)) if os.path.exists(state) else {}
if args[:1] == ["is-enabled"]:
    print("enabled" if enabled.get(args[1], True) else "disabled")
elif args[:1] == ["show"]:
    print("Thu 2026-11-26 18:00:00 UTC")
elif args[:2] == ["disable", "--now"]:
    enabled[args[2]] = False; json.dump(enabled, open(state, "w"))
elif args[:1] == ["enable"]:
    enabled[args[1]] = True; json.dump(enabled, open(state, "w"))
'''


def load():
    spec = importlib.util.spec_from_file_location("cat_obs_schedule_apply", SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ap = load()


@pytest.fixture()
def world(tmp_path):
    root = tmp_path / "schedule"
    (root / "requests").mkdir(parents=True)
    (root / "state").mkdir()
    os.chmod(root / "state", 0o750)
    units = tmp_path / "units"
    for unit, cal in (("cat-obs-cartographer", "hourly"), ("cat-obs-dpa", "*:30"), ("cat-obs-market", "*:3/10")):
        (units / f"{unit}.timer.d").mkdir(parents=True)
        (units / f"{unit}.timer").write_text("[Timer]\nOnCalendar=*:0/10\n")
        (units / f"{unit}.timer.d" / "rhythm.conf").write_text(f"[Timer]\nOnCalendar=\nOnCalendar={cal}\n")
        os.chmod(units / f"{unit}.timer.d", 0o755)
    fake = tmp_path / "fake_systemctl.py"
    fake.write_text(FAKE_SYSTEMCTL)
    log = tmp_path / "systemctl.log"
    logs = []
    cfg = ap.Config(root=str(root), units=str(units), request_owner_uid=os.getuid(), state_gid=-1,
                    expected_dir_uid=os.getuid(),
                    systemctl=[sys.executable, "-I", str(fake), str(log), str(tmp_path / "enabled.json")],
                    log=logs.append)
    return cfg, root, units, log, logs


def req(root, data=b"1h\n", mode=0o640):
    p = root / "requests" / "repository-cartographer.request"
    p.write_bytes(data)
    os.chmod(p, mode)
    return p


def calls(log):
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def rhythm(units, unit):
    return (units / f"{unit}.timer.d" / "rhythm.conf").read_text()


def state(root, agent):
    return json.loads((root / "state" / f"{agent}.json").read_text())


# --- comportement nominal -------------------------------------------------------------------------

@pytest.mark.parametrize("word,cal", [("10min", "*:0/10"), ("1h", "hourly")])
def test_applies_cartographer_and_publishes_three_states(world, word, cal):
    cfg, root, units, log, _ = world
    before = {u: rhythm(units, u) for u in ("cat-obs-dpa", "cat-obs-market")}
    req(root, (word + "\n").encode())
    assert ap.run(cfg) == 0
    assert rhythm(units, "cat-obs-cartographer") == f"[Timer]\nOnCalendar=\nOnCalendar={cal}\n"
    assert not (root / "requests" / "repository-cartographer.request").exists()
    s = state(root, "repository-cartographer")
    assert s["applied"] == word and s["last_request"]["result"] == "APPLIED" and s["writable"] is True
    assert state(root, "data-provenance-auditor")["applied"] == "1h"
    assert state(root, "market-observer")["applied"] == "10min"
    assert {u: rhythm(units, u) for u in ("cat-obs-dpa", "cat-obs-market")} == before
    mutating = [c for c in calls(log) if c[0] in ("enable", "disable", "restart", "stop", "start")]
    assert mutating == [["enable", "cat-obs-cartographer.timer"], ["restart", "cat-obs-cartographer.timer"]]
    assert ["daemon-reload"] in calls(log)
    assert oct(os.stat(root / "state" / "repository-cartographer.json").st_mode & 0o777) == "0o640"
    assert [p.name for p in (root / "state").iterdir() if p.name.startswith(".")] == []


def test_off_disables_only_the_cartographer(world):
    cfg, root, units, log, _ = world
    req(root, b"off\n")
    assert ap.run(cfg) == 0
    mutating = [c for c in calls(log) if c[0] in ("enable", "disable", "restart", "stop", "start")]
    assert mutating == [["disable", "--now", "cat-obs-cartographer.timer"], ["stop", "cat-obs-cartographer.service"]]
    assert state(root, "repository-cartographer")["applied"] == "off"
    assert state(root, "market-observer")["applied"] == "10min"


def test_no_request_is_a_no_op(world):
    cfg, root, _, log, _ = world
    assert ap.run(cfg) == 0
    assert calls(log) == [] and list((root / "state").iterdir()) == []


def test_publish_only_never_applies(world):
    cfg, root, units, log, _ = world
    req(root, b"10min\n")
    before = rhythm(units, "cat-obs-cartographer")
    assert ap.run(cfg, publish_only=True) == 0
    assert rhythm(units, "cat-obs-cartographer") == before
    assert (root / "requests" / "repository-cartographer.request").exists()
    assert all(c[0] in ("is-enabled", "show") for c in calls(log))


def test_unknown_drop_in_is_published_unknown_not_zero(world):
    cfg, root, units, _, _ = world
    (units / "cat-obs-market.timer.d" / "rhythm.conf").write_text("[Timer]\nOnCalendar=*:07\n")
    ap.run(cfg, publish_only=True)
    s = state(root, "market-observer")
    assert s["applied"] == "UNKNOWN" and s["next_utc"] is None and s["writable"] is False


# --- T1 : liens symboliques à l'emplacement des écritures ---------------------------------------

def test_t1_symlinked_state_target_is_replaced_not_followed(world, tmp_path):
    cfg, root, _, _, _ = world
    victim = tmp_path / "victim"
    victim.write_text("ROOT-OWNED\n")
    os.symlink(victim, root / "state" / "repository-cartographer.json")
    for name in ("repository-cartographer", "market-observer"):
        for i in range(4):  # temporaires prévisibles de l'ancienne version
            try:
                os.symlink(victim, root / "state" / f".{name}.json.{i}.tmp")
            except FileExistsError:
                pass
    req(root, b"1h\n")
    assert ap.run(cfg) == 0
    assert victim.read_text() == "ROOT-OWNED\n"
    p = root / "state" / "repository-cartographer.json"
    assert not p.is_symlink() and state(root, "repository-cartographer")["applied"] == "1h"


def test_t1_symlinked_drop_in_is_replaced_not_followed(world, tmp_path):
    cfg, root, units, _, _ = world
    victim = tmp_path / "victim.conf"
    victim.write_text("KEEP\n")
    d = units / "cat-obs-cartographer.timer.d" / "rhythm.conf"
    d.unlink()
    os.symlink(victim, d)
    req(root, b"10min\n")
    assert ap.run(cfg) == 0
    assert victim.read_text() == "KEEP\n" and not d.is_symlink()


def test_t1_state_dir_replaced_by_symlink_is_refused(world, tmp_path):
    cfg, root, _, _, _ = world
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.chmod(elsewhere, 0o755)
    os.rmdir(root / "state")
    os.symlink(elsewhere, root / "state")
    with pytest.raises(OSError):
        ap.run(cfg, publish_only=True)
    assert list(elsewhere.iterdir()) == []


def test_t1_group_writable_state_dir_is_refused(world):
    cfg, root, _, _, _ = world
    os.chmod(root / "state", 0o770)
    with pytest.raises(ap.Refused):
        ap.run(cfg, publish_only=True)
    assert list((root / "state").iterdir()) == []


# --- T2 : objets inattendus à la place de la demande --------------------------------------------

def assert_refused(cfg, root, units, log, logs, reason):
    before = rhythm(units, "cat-obs-cartographer")
    assert ap.run(cfg) == 1
    assert rhythm(units, "cat-obs-cartographer") == before
    assert not any(c[0] in ("enable", "disable", "restart", "stop", "daemon-reload") for c in calls(log))
    assert state(root, "repository-cartographer")["last_request"]["result"] == "REFUSED"
    assert any(reason in m for m in logs), logs
    assert not os.path.lexists(root / "requests" / "repository-cartographer.request")


def test_t2_request_symlink(world, tmp_path):
    cfg, root, units, log, logs = world
    target = tmp_path / "t"
    target.write_text("1h\n")
    os.symlink(target, root / "requests" / "repository-cartographer.request")
    assert_refused(cfg, root, units, log, logs, "lien symbolique")
    assert target.read_text() == "1h\n"


def test_t2_request_hardlink(world, tmp_path):
    cfg, root, units, log, logs = world
    other = root / "requests" / "other"
    other.write_text("1h\n")
    os.link(other, root / "requests" / "repository-cartographer.request")
    assert_refused(cfg, root, units, log, logs, "liens physiques")
    assert other.read_text() == "1h\n"


def test_t2_request_fifo_does_not_block(world):
    cfg, root, units, log, logs = world
    os.mkfifo(root / "requests" / "repository-cartographer.request")
    assert_refused(cfg, root, units, log, logs, "pas un fichier régulier")


def test_t2_request_directory(world):
    cfg, root, units, log, logs = world
    (root / "requests" / "repository-cartographer.request").mkdir()
    assert ap.run(cfg) == 1
    assert any("demande" in m for m in logs)
    assert not any(c[0] in ("enable", "restart") for c in calls(log))


# --- T3 : contenu et propriétaire ----------------------------------------------------------------

@pytest.mark.parametrize("data,reason", [
    (b"1h\n" + b" " * 70, "trop volumineuse"),
    ("1hé\n".encode(), "non ASCII"),
    (b"1h; rm -rf /\n", "hors liste"),
    (b"$(reboot)\n", "hors liste"),
    (b"1h\n\n", "hors liste"),
    (b" 1h\n", "hors liste"),
    (b"1min\n", "hors liste"),
    (b"\n", "hors liste"),
    (b"*:0/1\n", "hors liste"),
])
def test_t3_content_is_a_closed_list(world, data, reason):
    cfg, root, units, log, logs = world
    req(root, data)
    assert_refused(cfg, root, units, log, logs, reason)


def test_t3_executable_request(world):
    cfg, root, units, log, logs = world
    req(root, b"1h\n", 0o750)
    assert_refused(cfg, root, units, log, logs, "exécutable")


@pytest.mark.skipif(os.geteuid() != 0, reason="chown vers un autre uid : root requis")
def test_t3_wrong_owner(world):
    cfg, root, units, log, logs = world
    p = req(root, b"1h\n")
    os.chown(p, 65534, -1)
    assert_refused(cfg, root, units, log, logs, "propriétaire")


def test_t3_wrong_owner_by_config(world):
    cfg, root, units, log, logs = world
    cfg.request_owner_uid = os.getuid() + 1
    req(root, b"1h\n")
    assert_refused(cfg, root, units, log, logs, "propriétaire")


# --- T4 : substitution concurrente ---------------------------------------------------------------

def test_t4_concurrent_substitution_never_follows_or_corrupts(world, tmp_path):
    cfg, root, units, _, _ = world
    cfg.systemctl = ["/bin/true"]  # rapide : 1000 passages sans lancer d'interpréteur
    victim = tmp_path / "victim"
    victim.write_text("ROOT-OWNED\n")
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    rq = root / "requests" / "repository-cartographer.request"
    st = root / "state" / "repository-cartographer.json"
    stop = threading.Event()

    def attacker():
        i = 0
        while not stop.is_set():
            i += 1
            tmp = root / "requests" / f".a{i}"
            try:
                kind = i % 4
                if kind == 0:
                    os.symlink(victim, tmp)
                elif kind == 1:
                    os.symlink(fifo, tmp)
                elif kind == 2:
                    tmp.write_bytes(b"1h\n")
                    os.chmod(tmp, 0o640)
                else:
                    tmp.write_bytes(b"x" * 100)
                os.replace(tmp, rq)
                s_tmp = root / "state" / f".s{i}"
                os.symlink(victim, s_tmp)
                os.replace(s_tmp, st)
            except OSError:
                pass

    t = threading.Thread(target=attacker, daemon=True)
    t.start()
    outcomes = {0: 0, 1: 0}
    try:
        for _ in range(1000):
            rc = ap.run(cfg)
            outcomes[rc] = outcomes.get(rc, 0) + 1
    finally:
        stop.set()
        t.join(5)
    assert victim.read_text() == "ROOT-OWNED\n"
    conf = rhythm(units, "cat-obs-cartographer")
    assert conf in ("[Timer]\nOnCalendar=\nOnCalendar=hourly\n", "[Timer]\nOnCalendar=\nOnCalendar=*:0/10\n")
    assert rhythm(units, "cat-obs-dpa").endswith("OnCalendar=*:30\n")
    assert rhythm(units, "cat-obs-market").endswith("OnCalendar=*:3/10\n")
    leftovers = [p.name for p in (root / "state").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
    assert sum(outcomes.values()) == 1000
    print("T4 outcomes", outcomes)


# --- interface ligne de commande ------------------------------------------------------------------

def test_cli_refuses_arguments_and_non_root(tmp_path):
    import subprocess
    r = subprocess.run([sys.executable, "-I", "-B", str(SRC), "--apply", "1h"], capture_output=True, text=True)
    assert r.returncode == 2
    env = {"PATH": os.environ.get("PATH", "")}
    if os.geteuid() != 0:
        r = subprocess.run([sys.executable, "-I", "-B", str(SRC)], capture_output=True, text=True, env=env)
        assert r.returncode != 0 and "root" in r.stderr
    else:
        r = subprocess.run([sys.executable, "-I", "-B", str(SRC)], capture_output=True, text=True, env=env)
        assert r.returncode != 0 and "CAT_SCHEDULE_REQUEST_OWNER" in r.stderr


def test_source_has_no_shell_or_dpa_market_writes():
    src = SRC.read_text()
    assert "shell=True" not in src and "os.system" not in src
    assert src.count("safe_write(") == 3  # définition + état + drop-in du cartographe
