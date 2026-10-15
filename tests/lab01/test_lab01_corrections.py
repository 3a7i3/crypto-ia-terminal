"""LAB-01 — corrections de revue (#448) : jeton, export lisible, staging, bornes, audit."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from lab01 import api, export, guards, retention, runner
from lab01.events import EventLog
from lab01.ops import make_bundle

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "lab01" / "ops"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in guards.forbidden_env_names():
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    for name in guards.forbidden_env_names():
        mp.delenv(name, raising=False)
    try:
        d = tmp_path_factory.mktemp("corr") / "runs"
        runner.run_all(d)
    finally:
        mp.undo()
    return d


# ---- 3. authentification --------------------------------------------------------
@pytest.mark.parametrize(
    "bad", [None, "", "court", "x" * 31, "a b" + "c" * 40, "é" * 40]
)
def test_api_refuses_to_start_without_valid_token(tmp_path, bad):
    with pytest.raises(api.TokenError):
        api.build_server(tmp_path, 0, bad)  # même en loopback


def test_token_file_rules(tmp_path):
    f = tmp_path / "token"
    with pytest.raises(api.TokenError):
        api.read_token_file(None)
    with pytest.raises(api.TokenError):
        api.read_token_file(str(tmp_path / "absent"))
    f.write_text("k" * 40 + "\n")
    f.chmod(0o644)  # lisible par tous : refusé
    with pytest.raises(api.TokenError):
        api.read_token_file(str(f))
    f.chmod(0o640)
    assert api.read_token_file(str(f)) == "k" * 40
    f.write_text("trop-court\n")
    with pytest.raises(api.TokenError):
        api.read_token_file(str(f))


def test_cli_serve_requires_token_file(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "lab01", "serve", "--out", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0 and "token-file" in r.stderr
    bad = tmp_path / "tok"
    bad.write_text("short")
    bad.chmod(0o640)
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "lab01",
            "serve",
            "--out",
            str(tmp_path),
            "--token-file",
            str(bad),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0 and "REFUS" in r.stderr


def test_no_unauthenticated_mode_anywhere_in_deployable_code():
    for p in (
        list((ROOT / "lab01").rglob("*.py"))
        + list(OPS.glob("systemd/*"))
        + [OPS / "lab01_ops.sh"]
    ):
        assert "AUCUNE" not in p.read_text(), p


def test_docs_do_not_pass_token_in_process_arguments():
    for doc in (ROOT / "docs" / "lab").glob("*.md"):
        txt = doc.read_text()
        assert "Bearer $(sudo cat" not in txt, (
            doc
        )  # visible dans la liste des processus
        assert "sudo -E" not in txt, doc


# ---- 2. rapports exportés lisibles, jeton et production non élargis --------------
def test_export_is_sanitized_and_readable_by_observer(runs, tmp_path):
    dst = tmp_path / "reports"
    rep = export.export_reports(runs, dst)
    assert len(rep["exported"]) == 3 and rep["rejected"] == []
    assert stat.S_IMODE(dst.stat().st_mode) == 0o755
    for exp in rep["exported"]:
        assert stat.S_IMODE((dst / exp).stat().st_mode) == 0o755
        names = sorted(p.name for p in (dst / exp).iterdir())
        assert names == [
            "events.jsonl",
            "manifest.json",
            "result.json",
        ]  # ni packet ni bars
        for p in (dst / exp).iterdir():
            assert stat.S_IMODE(p.stat().st_mode) == 0o644
        m = json.loads((dst / exp / "manifest.json").read_text())
        assert "platform" not in m and "git_head" not in m
    idx = json.loads((dst / "EXPORT.json").read_text())
    assert (
        idx["provenance"] == "SYNTHETIC" and "packet.json" in idx["excluded_by_design"]
    )
    assert not (dst / "index.json").exists() and not any(
        "token" in str(p) for p in dst.rglob("*")
    )


def test_export_does_not_widen_runs(runs, tmp_path):
    before = {p: stat.S_IMODE(p.stat().st_mode) for p in runs.rglob("*")}
    export.export_reports(runs, tmp_path / "r")
    assert before == {p: stat.S_IMODE(p.stat().st_mode) for p in runs.rglob("*")}


def _copy_runs(runs, tmp_path):
    c = tmp_path / "copy"
    shutil.copytree(runs, c, ignore=shutil.ignore_patterns("_logs"))
    return c


def test_export_rejects_tampered_forbidden_and_symlinked(runs, tmp_path):
    c = _copy_runs(runs, tmp_path)
    a, b, d = sorted(p for p in c.iterdir() if p.name.startswith("LAB01-"))
    ev = a / "events.jsonl"  # altération : chaîne cassée
    ev.write_text(ev.read_text().replace('"SIGNAL_EMITTED"', '"SIGNAL_EDITED"', 1))
    res = b / "result.json"  # chaîne interdite (chemin de production)
    obj = json.loads(res.read_text())
    obj["note"] = "lu depuis /home/mathieu/crypto_ai_terminal/databases"
    res.write_text(json.dumps(obj))
    (d / "manifest.json").unlink()  # lien symbolique vers un fichier hors périmètre
    (d / "manifest.json").symlink_to("/etc/hostname")
    rep = export.export_reports(c, tmp_path / "out")
    reasons = {r["experiment_id"]: r["reason"] for r in rep["rejected"]}
    assert rep["exported"] == []
    assert reasons[a.name] == "EVENT_CHAIN_INVALID"
    assert reasons[b.name] == "FORBIDDEN_STRING_PRESENT"
    assert reasons[d.name].startswith("NOT_REGULAR_FILE")
    assert not any((tmp_path / "out" / x.name).exists() for x in (a, b, d))


def test_export_unit_has_no_token_no_network_no_production():
    txt = (OPS / "systemd" / "lab01-export.service").read_text()
    for needle in (
        "PrivateNetwork=yes",
        "ReadOnlyPaths=/srv/lab01/data/runs",
        "ReadWritePaths=/srv/lab01/data/reports",
        "UMask=0022",
        "/srv/lab01/token",
        "/home",
        "/opt/crypto-ai-terminal",
    ):
        assert needle in txt
    assert "InaccessiblePaths" in txt and "EnvironmentFile" not in txt
    run = (OPS / "systemd" / "lab01-run.service").read_text()
    assert "/srv/lab01/token" in run and "UMask=0077" in run  # runs reste privé


# ---- 4. installation privilégiée : staging, empreinte, pas de purge ---------------
def _stage(tmp_path):
    st = tmp_path / "stage"
    (st / "systemd").mkdir(parents=True)
    for rel in make_bundle.INSTALLER_FILES:
        shutil.copy(OPS / rel, st / rel)
    _m, sha = make_bundle.installer_manifest(tmp_path)
    shutil.move(tmp_path / "INSTALLER.sha256", st / "INSTALLER.sha256")
    return st, sha


def _ops(st, *args):
    return subprocess.run(
        ["bash", str(st / "lab01_ops.sh"), *args],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )


def test_staging_verification_accepts_exact_files(tmp_path):
    st, sha = _stage(tmp_path)
    r = _ops(st, "verify-staging", "--manifest-sha256", sha)
    assert r.returncode == 0 and "staging vérifié" in r.stdout


def test_staging_verification_refuses_tampering_extra_and_wrong_digest(tmp_path):
    st, sha = _stage(tmp_path)
    assert _ops(st, "verify-staging", "--manifest-sha256", "0" * 64).returncode == 5
    assert _ops(st, "verify-staging").returncode == 5  # empreinte publiée obligatoire
    unit = st / "systemd" / "lab01-run.service"
    original = unit.read_text()
    unit.write_text(original + "ExecStartPre=/bin/true\n")
    r = _ops(st, "verify-staging", "--manifest-sha256", sha)
    assert r.returncode == 5 and "diffère du manifeste" in r.stdout
    unit.write_text(original)
    (st / "systemd" / "extra.service").write_text("[Service]\n")
    r = _ops(st, "verify-staging", "--manifest-sha256", sha)
    assert r.returncode == 5 and "en trop ou manquants" in r.stdout


def test_apply_checks_staging_before_anything_else(tmp_path):
    st, sha = _stage(tmp_path)
    (st / "lab01_ops.sh").write_text(
        (st / "lab01_ops.sh").read_text() + "\n# modifié\n"
    )
    r = _ops(st, "apply", "--auth", "X", "--manifest-sha256", sha)
    assert (
        r.returncode in (3, 5) and "REFUS" in r.stdout
    )  # non root (3) ou manifeste (5)
    assert "APPLY terminé" not in r.stdout


def test_purge_is_not_offered_and_no_env_passthrough():
    script = (OPS / "lab01_ops.sh").read_text()
    r = subprocess.run(
        ["bash", str(OPS / "lab01_ops.sh"), "remove", "--purge"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 2 and "non prévu" in r.stdout
    assert "rm -rf" not in script and "userdel" not in script
    assert (
        "LAB01_AUTH" not in script and "LAB01_BUNDLE" not in script
    )  # pas d'environnement


def test_request_is_data_pinned_to_full_commit(tmp_path):
    _p, dig = make_bundle.build(tmp_path)
    _m, msha = make_bundle.installer_manifest(tmp_path)
    req = json.loads(make_bundle.write_request(tmp_path, dig, msha).read_text())
    assert req["operation"] == "lab01.apply" and req["not_an_authorization"] is True
    assert req["bundle_sha256"] == dig and req["installer_manifest_sha256"] == msha
    assert len(req["commit"]) == 40 or req["commit"] == "UNKNOWN"
    assert not any(isinstance(v, str) and v.startswith("#!") for v in req.values())
    manifest = (tmp_path / "INSTALLER.sha256").read_text()
    for rel in make_bundle.INSTALLER_FILES:
        assert (
            hashlib.sha256((OPS / rel).read_bytes()).hexdigest() + "  " + rel
            in manifest
        )


# ---- 5. bornes disque et rétention ------------------------------------------------
def test_data_volume_is_a_fixed_size_loop_mount():
    mnt = (OPS / "systemd" / "srv-lab01-data.mount").read_text()
    assert "What=/var/lib/lab01/lab01.img" in mnt and "Where=/srv/lab01/data" in mnt
    assert "noexec" in mnt and "nosuid" in mnt and "nodev" in mnt
    script = (OPS / "lab01_ops.sh").read_text()
    assert "truncate -s" in script and "mkfs.ext4" in script
    assert "stockage non borné" in script  # montage impossible => apply interrompu
    for name in ("lab01-run.service", "lab01-export.service", "lab01-api.service"):
        assert (
            "RequiresMountsFor=/srv/lab01/data" in (OPS / "systemd" / name).read_text()
        )


def test_quota_refuses_new_run_visibly(runs, tmp_path):
    c = _copy_runs(runs, tmp_path)
    with pytest.raises(guards.LabGuardError) as ei:
        runner.run_all(c, max_bytes=1)
    assert "LAB_QUOTA_EXCEEDED" in str(ei.value)


def test_prune_is_dry_run_by_default_and_never_touches_other_dirs(runs, tmp_path):
    c = _copy_runs(runs, tmp_path)
    (c / "reports").mkdir()
    (c / "reports" / "keep.txt").write_text("x")
    link = c / "LAB01-link_x-aaaaaaaaaaaa"
    link.symlink_to(tmp_path)
    exps = sorted(
        p.name
        for p in c.iterdir()
        if p.name.startswith("LAB01-") and p.is_dir() and not p.is_symlink()
    )
    dry = retention.prune(c, keep=1)
    assert dry["dry_run"] and len(dry["candidates"]) == 2 and dry["removed"] == []
    assert (
        sorted(
            p.name
            for p in c.iterdir()
            if p.is_dir() and not p.is_symlink() and p.name.startswith("LAB01-")
        )
        == exps
    )
    done = retention.prune(c, keep=1, apply=True)
    assert len(done["removed"]) == 2 and (c / "reports" / "keep.txt").exists()
    assert link.is_symlink() and tmp_path.exists()
    with pytest.raises(ValueError):
        retention.prune(c, keep=0)


# ---- 6. reproductibilité : déterministe vs non déterministe ---------------------
def test_only_declared_files_are_octet_identical(runs, tmp_path):
    other = tmp_path / "again"
    runner.run_all(other)
    for exp in (p.name for p in runs.iterdir() if p.name.startswith("LAB01-")):
        for name in ("events.jsonl", "result.json", "bars.json"):
            assert (runs / exp / name).read_bytes() == (other / exp / name).read_bytes()
        man = json.loads((runs / exp / "manifest.json").read_text())
        repro = man["reproducibility"]
        assert set(repro["deterministic_octet_identical"]) == {
            "events.jsonl",
            "result.json",
            "bars.json",
        }
        assert any("packet.json" in x for x in repro["non_deterministic"])
        assert any("manifest.json" in x for x in repro["non_deterministic"])
        assert "pas identique octet par octet" in repro["note"]


def test_docs_do_not_claim_whole_experiment_is_identical():
    txt = (ROOT / "docs" / "lab" / "LAB_01_PLAN.md").read_text()
    assert "octet par octet" in txt and "packet.json" in txt


# ---- 7. audit complémentaire corrigé --------------------------------------------
def _audit(tmp_path, fakes: dict[str, str], mode="user"):
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    fakes = {"vmstat": "echo vmstat-fake", **fakes}  # le vrai vmstat attend 10 s
    for name, body in fakes.items():
        (b / name).write_text("#!/bin/sh\n" + body + "\n")
        (b / name).chmod(0o755)
    return subprocess.run(
        ["bash", str(OPS / "lab01_audit.sh"), mode],
        capture_output=True,
        text=True,
        env={"PATH": f"{b}:/usr/bin:/bin"},
    )


def test_audit_never_reads_unit_files_or_secret_directives():
    code = "\n".join(
        ln
        for ln in (OPS / "lab01_audit.sh").read_text().splitlines()
        if not ln.lstrip().startswith("#")
    )
    assert (
        "systemctl cat" not in code
        and "Environment" not in code
        and "ExecStart" not in code
    )
    assert (
        "2>&1" not in code and "| head" not in code
    )  # ni erreur fusionnée, ni troncature muette


def test_audit_oom_error_is_not_read_as_zero(tmp_path):
    r = _audit(
        tmp_path,
        {"journalctl": "echo 'Failed to open journal: Permission denied' >&2; exit 1"},
    )
    assert "OOM : INDÉTERMINÉ" in r.stdout and "OOM : 0" not in r.stdout
    assert "Permission denied" in r.stdout


def test_audit_empty_journal_is_indeterminate_not_zero(tmp_path):
    r = _audit(tmp_path, {"journalctl": "exit 0"})
    assert "OOM : INDÉTERMINÉ" in r.stdout and "OOM : 0 " not in r.stdout


def test_audit_counts_oom_only_with_evidence(tmp_path):
    r = _audit(
        tmp_path,
        {
            "journalctl": "echo 'Oct 01 kernel: boot'; echo 'Oct 02 kernel: Out of memory: Killed process 1'"
        },
    )
    assert "OOM : 1 événement(s) sur 2 lignes" in r.stdout
    r = _audit(tmp_path, {"journalctl": "echo 'Oct 01 kernel: boot'"})
    assert "OOM : 0 événement(s) sur 1 lignes" in r.stdout


def test_audit_shows_denials_errors_and_truncation(tmp_path):
    fakes = {
        "sysctl": "echo 'sysctl: permission denied on key' >&2; exit 255",
        "ss": "i=0; while [ $i -lt 120 ]; do echo line$i; i=$((i+1)); done",
        "systemctl": "echo 'Failed to connect to bus' >&2; exit 1",
        "journalctl": "exit 0",
    }
    r = _audit(tmp_path, fakes)
    assert "[REFUSÉ" in r.stdout and "STDERR: sysctl: permission denied" in r.stdout
    assert "[SORTIE TRONQUÉE : 120 lignes au total, 80 affichées]" in r.stdout
    assert (
        "[ERREUR : échec rc=1" in r.stdout
        and "STDERR: Failed to connect to bus" in r.stdout
    )


def test_audit_separates_privileged_reads(tmp_path):
    sh = (OPS / "lab01_audit.sh").read_text()
    user_part = sh.split("user)")[1].split("priv)")[0]
    assert "nft" not in user_part and "iptables" not in user_part
    if os.geteuid() != 0:
        r = _audit(tmp_path, {}, mode="priv")
        assert r.returncode == 3 and "REFUS" in r.stdout


def test_eventlog_unused_import_guard():
    assert EventLog  # le module reste importable depuis les tests de correction
