"""Relevé OOM : les états ACCÈS_REFUSÉ, RÉTENTION_INSUFFISANTE, AUCUNE_CORRESPONDANCE, ÉVÉNEMENTS
et ERREUR restent distincts ; une erreur n'est jamais présentée comme « aucun événement »."""

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "lab01" / "ops" / "lab01_oom_probe.sh"
FAKE = """#!/bin/sh
D="$FAKE_DIR"
case " $* " in
  *" -n 1 "*) f=probe;;
  *" -g "*)   f=match;;
  *)          f=all;;
esac
[ -f "$D/$f.out" ] && cat "$D/$f.out"
[ -f "$D/$f.err" ] && cat "$D/$f.err" >&2
exit "$(cat "$D/$f.rc" 2>/dev/null || echo 0)"
"""


def run(tmp_path, **files):
    d = tmp_path / "fake"
    d.mkdir()
    (tmp_path / "bin").mkdir()
    jc = tmp_path / "bin" / "journalctl"
    jc.write_text(FAKE)
    jc.chmod(0o755)
    for name, content in files.items():
        (d / name.replace("_", ".", 1)).write_text(str(content))
    env = {
        "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin",
        "FAKE_DIR": str(d),
        "TMPDIR": str(tmp_path),
    }
    p = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)
    state = [ln for ln in p.stdout.splitlines() if ln.startswith("ÉTAT_OOM=")]
    return p, (state[0].split("=", 1)[1] if state else None)


def entries(days_ago_first, n=5):
    now = int(time.time())
    first = now - int(days_ago_first * 86400)
    return "".join(f"{first + i * 1000}.0 host kernel: msg {i}\n" for i in range(n))


def test_access_denied_is_not_zero(tmp_path):
    p, st = run(
        tmp_path,
        probe_rc=1,
        probe_err="No journal files were opened due to insufficient permissions.\n",
    )
    assert (
        st == "ACCÈS_REFUSÉ"
        and "≠ 0" in p.stdout
        and "AUCUNE_CORRESPONDANCE" not in p.stdout
    )
    assert p.returncode == 0  # le code retour ne dit rien du résultat


def test_no_match_with_full_retention(tmp_path):
    p, st = run(tmp_path, probe_out="1.0 x\n", all_out=entries(30), match_rc=1)
    assert st == "AUCUNE_CORRESPONDANCE" and "14 jours complets" in p.stdout


def test_insufficient_retention_is_not_absence(tmp_path):
    p, st = run(tmp_path, probe_out="1.0 x\n", all_out=entries(3), match_rc=1)
    assert st == "RÉTENTION_INSUFFISANTE" and "n'est pas prouvée" in p.stdout


def test_events_are_counted_and_display_is_bounded(tmp_path):
    lines = "".join(
        f"2026-10-10T00:00:{i:02d}+0000 host kernel: Out of memory: Killed process {i}\n"
        for i in range(30)
    )
    p, st = run(
        tmp_path, probe_out="1.0 x\n", all_out=entries(30), match_out=lines, match_rc=0
    )
    assert st == "ÉVÉNEMENTS" and "30 ligne(s) OOM" in p.stdout
    assert "[AFFICHAGE LIMITÉ : 20 lignes sur 30]" in p.stdout
    assert p.stdout.count("Killed process") == 20


def test_events_with_short_retention_carry_the_caveat(tmp_path):
    p, st = run(
        tmp_path,
        probe_out="1.0 x\n",
        all_out=entries(2),
        match_out="2026-10-14T00:00:00+0000 host kernel: Out of memory: Killed process 1\n",
        match_rc=0,
    )
    assert st == "ÉVÉNEMENTS" and "RÉTENTION_INSUFFISANTE" in p.stdout


def test_search_failure_is_an_error_not_no_match(tmp_path):
    p, st = run(
        tmp_path,
        probe_out="1.0 x\n",
        all_out=entries(30),
        match_rc=2,
        match_err="Failed to compile pattern\n",
    )
    assert st == "ERREUR" and "AUCUNE_CORRESPONDANCE" not in p.stdout
    assert "Failed to compile pattern" in p.stdout


def test_unreadable_oldest_entry_is_an_error(tmp_path):
    p, st = run(tmp_path, probe_out="1.0 x\n", all_out="", match_rc=1)
    assert st == "ERREUR"


def test_script_is_read_only_and_cleans_up(tmp_path):
    txt = SCRIPT.read_text()
    for forbidden in (
        "sudo",
        "usermod",
        "gpasswd",
        "chmod",
        "chown",
        "setfacl",
        "systemctl",
    ):
        assert forbidden not in txt.replace("# ", ""), forbidden
    run(tmp_path, probe_rc=1, probe_err="insufficient permissions\n")
    assert not list(tmp_path.glob("lab01-oom.*"))
