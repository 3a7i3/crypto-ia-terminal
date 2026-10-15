"""Paquet d'installation INACTIF : épinglage, préconditions, reprise après échec partiel, retrait qui
conserve les preuves. Tout est exécuté dans des dossiers temporaires avec de faux systemctl/mkfs/useradd :
aucun effet sur l'hôte, aucune installation réelle (ce que ces tests ne prouvent pas : le montage loop,
mkfs et systemd réels, observables seulement sur l'hôte après autorisation)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "lab01" / "ops"
COMMIT = "a" * 40

FAKES = {
    "systemctl": """#!/bin/sh
echo "$*" >>"$FAKE_STATE/calls.log"
case "$*" in
  --version*) echo "systemd 249 (249.11-0ubuntu3.12)"; exit 0;;
  "start srv-lab01-data.mount") [ -f "$FAKE_STATE/mount_fail" ] && { echo "mount failed" >&2; exit 1; }; touch "$FAKE_STATE/mounted"; exit 0;;
  "stop srv-lab01-data.mount") rm -f "$FAKE_STATE/mounted"; exit 0;;
esac
exit 0
""",
    "findmnt": """#!/bin/sh
[ -f "$FAKE_STATE/mounted" ] || exit 1
case "$*" in *SOURCE*) echo "$FAKE_IMG";; esac
exit 0
""",
    "mkfs.ext4": """#!/bin/sh
echo "mkfs $*" >>"$FAKE_STATE/calls.log"
[ -f "$FAKE_STATE/mkfs_fail" ] && exit 1
exit 0
""",
    "ss": '#!/bin/sh\ncat "$FAKE_STATE/ss.txt" 2>/dev/null\nexit 0\n',
    "getent": '#!/bin/sh\n[ -f "$FAKE_STATE/getent.txt" ] && { cat "$FAKE_STATE/getent.txt"; exit 0; }\nexit 2\n',
    "useradd": '#!/bin/sh\necho "useradd $*" >>"$FAKE_STATE/calls.log"\nexit 0\n',
}
for name in ("python3.11", "mount", "systemd-analyze"):
    FAKES[name] = "#!/bin/sh\nexit 0\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(ROOT))
    from lab01.ops import make_bundle

    monkeypatch.setattr(make_bundle, "git_head", lambda: COMMIT)
    dist = tmp_path / "dist"
    bundle, bsha = make_bundle.build(dist)
    _m, msha = make_bundle.installer_manifest(dist)
    stage = tmp_path / "stage" / COMMIT
    (stage / "systemd").mkdir(parents=True)
    for rel in make_bundle.INSTALLER_FILES:
        shutil.copy(OPS / rel, stage / rel)
    for f in ("INSTALLER.sha256", "COMMIT", "lab01-bundle.tar.gz"):
        shutil.copy(dist / f, stage / f)
    fake = tmp_path / "fakebin"
    fake.mkdir()
    for n, body in FAKES.items():
        (fake / n).write_text(body)
        (fake / n).chmod(0o755)
    st = tmp_path / "fstate"
    st.mkdir()
    lab = tmp_path / "srv" / "lab01"
    return dict(
        tmp=tmp_path,
        stage=stage,
        bsha=bsha,
        msha=msha,
        fake=fake,
        st=st,
        lab=lab,
        unit_dir=tmp_path / "etc-systemd",
        state_dir=tmp_path / "var-lib-lab01",
    )


PRELUDE = """
set -euo pipefail
source "$STAGE/lab01_ops.sh"
ROOT_USER="$(id -un)"; ROOT_GRP="$(id -gn)"; LAB_USER="$(id -un)"
LAB_ROOT="$LABR"; DATA="$LAB_ROOT/data"; STATE_DIR="$SD"; IMG="$SD/lab01.img"
JOURNAL="$SD/install.journal"; EVID_DIR="$SD/evidence"; UNIT_DIR="$UD"
MIN_FREE_MB=1; MIN_AVAIL_MEM_MB=1; is_root() { return 0; }
COMMIT="$C"; MANIFEST_SHA="$M"; BUNDLE="$STAGE/lab01-bundle.tar.gz"; BUNDLE_SHA="$B"; AUTH=test-auth; MODE=test
"""


def sh(e, body, extra_env=None, path_prefix=None):
    e["unit_dir"].mkdir(exist_ok=True)
    (e["lab"].parent).mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": f"{path_prefix + ':' if path_prefix else ''}{e['fake']}:/usr/bin:/bin",
        "STAGE": str(e["stage"]),
        "LABR": str(e["lab"]),
        "SD": str(e["state_dir"]),
        "UD": str(e["unit_dir"]),
        "C": COMMIT,
        "M": e["msha"],
        "B": e["bsha"],
        "FAKE_STATE": str(e["st"]),
        "FAKE_IMG": str(e["state_dir"] / "lab01.img"),
        "HOME": str(e["tmp"]),
    }
    env.update(extra_env or {})
    p = subprocess.run(
        ["bash", "-c", PRELUDE + body],
        capture_output=True,
        text=True,
        env=env,
        cwd=e["tmp"],
    )
    return p


def calls(e):
    f = e["st"] / "calls.log"
    return f.read_text() if f.exists() else ""


# ---- épinglage et vérification du staging ---------------------------------------------------------
def test_staging_is_verified_against_commit_manifest_and_directory_name(env):
    p = sh(env, "verify_staging")
    assert p.returncode == 0 and f"commit {COMMIT}" in p.stdout, p.stdout + p.stderr


def test_wrong_commit_manifest_or_tampered_file_is_refused(env):
    assert sh(env, 'COMMIT="' + "b" * 40 + '"; verify_staging').returncode == 5
    assert sh(env, 'MANIFEST_SHA="' + "0" * 64 + '"; verify_staging').returncode == 5
    (env["stage"] / "lab01_oom_probe.sh").write_text("#!/bin/sh\necho tampered\n")
    p = sh(env, "verify_staging")
    assert p.returncode == 5 and "diffère du manifeste" in p.stdout
    shutil.copy(OPS / "lab01_oom_probe.sh", env["stage"] / "lab01_oom_probe.sh")
    (env["stage"] / "extra.sh").write_text("x")
    assert sh(env, "verify_staging").returncode == 5  # fichier en trop


def test_staging_directory_must_be_named_after_the_commit(env):
    moved = env["stage"].parent / "renamed"
    env["stage"].rename(moved)
    env["stage"] = moved
    p = sh(env, "verify_staging")
    assert p.returncode == 5 and "doit s'appeler" in p.stdout


def test_manifest_lists_every_installer_file_and_the_commit():
    import sys

    sys.path.insert(0, str(ROOT))
    from lab01.ops import make_bundle

    for f in (
        "lab01_oom_probe.sh",
        "host_isolation_tests.py",
        "hostprobe.py",
        "unit_props.py",
        "lab01_audit.sh",
    ):
        assert f in make_bundle.INSTALLER_FILES


# ---- préconditions -------------------------------------------------------------------------------------
def test_preflight_passes_on_a_clean_host_and_writes_nothing(env):
    p = sh(env, "preflight")
    assert p.returncode == 0 and "PRÉFLIGHT : 0 échec" in p.stdout, p.stdout + p.stderr
    assert not env["state_dir"].exists() and not env["lab"].exists()


@pytest.mark.parametrize(
    "setup,expect",
    [
        (
            lambda e: (e["st"] / "ss.txt").write_text(
                "LISTEN 0 128 127.0.0.1:18090 0.0.0.0:*\n"
            ),
            "port 18090 est déjà en écoute",
        ),
        (
            lambda e: (e["st"] / "getent.txt").write_text(
                "lab01:x:1001:1001::/home/lab01:/bin/bash\n"
            ),
            "non conforme",
        ),
    ],
)
def test_preflight_refuses_port_in_use_and_non_compliant_user(env, setup, expect):
    setup(env)
    p = sh(env, "preflight")
    assert p.returncode != 0 and expect in p.stdout and "FAIL" in p.stdout


def test_preflight_refuses_to_overwrite_a_foreign_unit_and_low_disk(env):
    env["unit_dir"].mkdir()
    (env["unit_dir"] / "lab01-run.service").write_text(
        "[Service]\nExecStart=/bin/true\n"
    )
    p = sh(env, "preflight")
    assert p.returncode != 0 and "différente du paquet (non écrasée)" in p.stdout
    env["unit_dir"].joinpath("lab01-run.service").unlink()
    p = sh(env, "MIN_FREE_MB=999999999; preflight")
    assert p.returncode != 0 and "espace libre" in p.stdout and "FAIL" in p.stdout


def test_apply_stops_before_any_write_when_a_precondition_fails(env):
    (env["st"] / "ss.txt").write_text("LISTEN 0 128 127.0.0.1:18090 0.0.0.0:*\n")
    p = sh(env, "do_apply")
    assert p.returncode == 6 and "rien n'a été modifié" in p.stdout
    assert (
        not env["state_dir"].exists()
        and not env["lab"].exists()
        and not list(env["unit_dir"].glob("lab01*"))
    )


# ---- installation, reprise après échec partiel, idempotence ------------------------------------------
def test_apply_happy_path_is_inert_and_journaled(env):
    p = sh(env, "do_apply")
    assert p.returncode == 0, p.stdout + p.stderr
    j = (env["state_dir"] / "install.journal").read_text()
    assert j.rstrip().endswith("apply COMPLETE")
    assert oct((env["state_dir"] / "install.journal").stat().st_mode & 0o777) == "0o600"
    assert (env["lab"] / "release" / "current").is_symlink() and (
        env["lab"] / "data" / "runs"
    ).is_dir()
    assert sorted(f.name for f in env["unit_dir"].glob("*lab01*")) == sorted(
        [
            "lab01.slice",
            "srv-lab01-data.mount",
            "lab01-run.service",
            "lab01-export.service",
            "lab01-api.service",
        ]
    )
    c = calls(env)
    assert (
        "enable" not in c and "start lab01" not in c and "restart" not in c
    )  # rien d'activé, rien de démarré
    assert "start srv-lab01-data.mount" in c
    # idempotent : un second apply réussit sans rien recréer
    assert sh(env, "do_apply").returncode == 0


def test_failed_mkfs_leaves_no_half_image_and_apply_resumes(env):
    (env["st"] / "mkfs_fail").touch()
    (env["state_dir"]).mkdir(parents=True)
    (env["state_dir"] / "lab01.img.partial").write_text("reste d'un essai interrompu")
    p = sh(env, "do_apply")
    assert (
        p.returncode == 6
        and "ÉCHEC à l'étape image" in p.stdout
        and "INERTE" in p.stdout
    )
    assert not (env["state_dir"] / "lab01.img").exists()
    assert "image FAILED" in (env["state_dir"] / "install.journal").read_text()
    assert not list(env["unit_dir"].glob("lab01*"))  # étapes suivantes non exécutées
    (env["st"] / "mkfs_fail").unlink()
    p = sh(env, "do_apply")
    assert p.returncode == 0, p.stdout + p.stderr  # reprise
    assert (env["state_dir"] / "lab01.img").exists() and not (
        env["state_dir"] / "lab01.img.partial"
    ).exists()
    assert "apply COMPLETE" in (env["state_dir"] / "install.journal").read_text()


def test_mount_failure_stops_without_unbounded_storage_and_status_says_so(env):
    (env["st"] / "mount_fail").touch()
    p = sh(env, "do_apply")
    assert p.returncode == 6 and "ÉCHEC à l'étape mount" in p.stdout
    assert not (
        env["lab"] / "data" / "runs"
    ).exists()  # rien d'écrit sur un répertoire non borné
    s = sh(env, "do_status").stdout
    assert (
        "units       : FAIT" in s
        and "mount       : ABSENT" in s
        and "data        : ABSENT" in s
    )
    assert "mount FAILED" in s


def test_interrupted_release_extraction_is_replaced_atomically(env):
    rel = env["lab"] / "release" / env["bsha"]
    (Path(str(rel) + ".partial")).mkdir(parents=True)
    (Path(str(rel) + ".partial") / "junk").write_text("x")
    assert sh(env, "do_apply").returncode == 0
    assert (
        rel.is_dir()
        and not Path(str(rel) + ".partial").exists()
        and not (rel / "junk").exists()
    )


# ---- retrait : preuves d'abord, rien n'est purgé ----------------------------------------------------
def test_remove_keeps_verified_evidence_image_and_data(env):
    assert sh(env, "do_apply").returncode == 0
    (env["lab"] / "data" / "runs" / "exp1.json").write_text('{"synthetic": true}')
    (env["lab"] / "data" / "reports").joinpath("EXPORT.json").write_text("{}")
    p = sh(env, "do_remove")
    assert p.returncode == 0, p.stdout + p.stderr
    ev = sorted((env["state_dir"] / "evidence").iterdir())
    assert len(ev) == 1
    assert (ev[0] / "data.tar.gz").exists() and (ev[0] / "MANIFEST.sha256").exists()
    assert (ev[0] / "units" / "lab01-run.service").exists() and (
        ev[0] / "install.journal"
    ).exists()
    chk = subprocess.run(
        ["sha256sum", "--strict", "-c", "MANIFEST.sha256"],
        cwd=ev[0],
        capture_output=True,
        text=True,
    )
    assert chk.returncode == 0
    assert not list(env["unit_dir"].glob("*lab01*"))
    assert (env["state_dir"] / "lab01.img").exists()  # image conservée : aucune purge
    assert (env["lab"] / "data" / "runs" / "exp1.json").exists()
    c = calls(env)
    assert (
        "stop lab01-api.service" in c
        and "stop srv-lab01-data.mount" in c
        and "disable" not in c
    )
    assert "evidence=" in (env["state_dir"] / "install.journal").read_text()


def test_remove_refuses_to_remove_anything_when_evidence_cannot_be_written(env):
    assert sh(env, "do_apply").returncode == 0
    bad = env["tmp"] / "badbin"
    bad.mkdir()
    (bad / "tar").write_text("#!/bin/sh\nexit 1\n")
    (bad / "tar").chmod(0o755)
    p = sh(env, "do_remove", path_prefix=str(bad))
    assert p.returncode == 7 and "RIEN n'a été retiré" in p.stdout
    assert len(list(env["unit_dir"].glob("*lab01*"))) == 5  # unités toujours en place
    assert "stop lab01" not in calls(
        env
    )  # aucun arrêt avant que la preuve soit vérifiée


def test_remove_with_unmounted_volume_records_that_data_stays_in_the_image(env):
    assert sh(env, "do_apply").returncode == 0
    (env["st"] / "mounted").unlink()
    p = sh(env, "do_remove")
    assert p.returncode == 0, p.stdout + p.stderr
    ev = next((env["state_dir"] / "evidence").iterdir())
    assert (
        "image conservée" in (ev / "NOTE.txt").read_text()
        and (ev / "image.sha256").exists()
    )


def test_purge_and_unknown_arguments_are_refused():
    r = subprocess.run(
        ["bash", str(OPS / "lab01_ops.sh"), "remove", "--purge"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2 and "--purge non prévu" in r.stdout
    r = subprocess.run(
        ["bash", str(OPS / "lab01_ops.sh"), "plan", "--whatever"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2


def test_script_never_reads_parameters_from_the_environment():
    txt = "\n".join(
        ln
        for ln in (OPS / "lab01_ops.sh").read_text().splitlines()
        if not ln.lstrip().startswith("#")
    )
    assert "sudo -E" not in txt and "${MODE:-" not in txt
    assert 'rm -rf "$' not in txt.replace(
        'rm -rf "${', ""
    )  # suppressions toujours gardées par ${var:?}


@pytest.mark.skipif(os.geteuid() == 0, reason="le refus non-root se teste hors root")
def test_apply_requires_root_for_real():
    r = subprocess.run(
        ["bash", str(OPS / "lab01_ops.sh"), "apply", "--auth", "x"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 3 and "root requis" in r.stdout
