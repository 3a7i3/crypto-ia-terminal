"""G3 — one-shot systemd trials of one passive publisher (prepared, never run on the VPS).

Exercised against a fake systemd world: `systemctl`, `curl`, `runuser` and the deployed-release
interpreter are shims; the unit and output directories are temporary (G3_TEST=1 redirects the
paths). The fake `systemctl` records every call; the only verbs allowed are `show` and `start` of
the one selected publisher service — anything else is a test failure. Proves the script logic,
not the behaviour of systemd on the host.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "deploy" / "passive_publishers"
GUARDED = (
    "crypto-advisor.service",
    "crypto-operator-api.service",
    "crypto-operator-web.service",
)
ART = {
    "runtime-service": "runtime_service_snapshot.json",
    "storage": "storage_snapshot.json",
}

pytestmark = pytest.mark.skipif(
    os.geteuid() != 0, reason="the run mode is root-only (protected-copy check)"
)

SYSTEMCTL = r"""#!/usr/bin/env python3
import os, sys, time
fake = os.environ["FAKE"]; unitdir = os.environ["G3_UNITDIR"]; outdir = os.environ["G3_OUTDIR"]
args = sys.argv[1:]
with open(os.path.join(fake, "calls.log"), "a") as f:
    f.write(" ".join(args) + "\n")
def rd(name, default=""):
    p = os.path.join(fake, name)
    return open(p).read().strip() if os.path.exists(p) else default
GUARDED = @@GUARDED@@
OURS = ("crypto-publish-runtime-service.service", "crypto-publish-storage.service")
ARTS = {"crypto-publish-runtime-service.service": "runtime_service_snapshot.json",
        "crypto-publish-storage.service": "storage_snapshot.json"}
if args[:1] == ["start"] and len(args) == 2 and args[1] in OURS:
    n = int(rd("count", "0")) + 1
    open(os.path.join(fake, "count"), "w").write(str(n))
    if rd("g_change_on_start"):
        open(os.path.join(fake, "g_crypto-advisor.service_NRestarts"), "w").write("1")
    if rd("timer_on_start"):
        open(os.path.join(fake, "active_crypto-publish-storage.timer"), "w").write("active")
    if not rd("no_write"):
        tmp = os.path.join(outdir, ".tmp"); target = os.path.join(outdir, ARTS[args[1]])
        open(tmp, "w").write('{"n": %d}' % n); os.chmod(tmp, 0o600); os.replace(tmp, target)
    if rd("extra_file"):
        open(os.path.join(outdir, "leftover.tmp"), "w").write("x")
    sys.exit(int(rd("start_rc", "0")))
if args[:1] != ["show"]:
    with open(os.path.join(fake, "forbidden.log"), "a") as f:
        f.write(" ".join(args) + "\n")
    sys.exit(1)
props, value, unit, i = [], False, None, 1
while i < len(args):
    a = args[i]
    if a == "-p":
        props.append(args[i + 1]); i += 2; continue
    if a == "--value":
        value = True
    elif a == "--":
        unit = args[i + 1]; i += 1
    i += 1
DEFAULTS = {"ActiveState": "active", "SubState": "running", "MainPID": "1234", "NRestarts": "0",
            "InvocationID": "abc", "ActiveEnterTimestamp": "Mon 2026-09-27", "DropInPaths": ""}
def prop(p):
    if unit in GUARDED:
        if p == "NeedDaemonReload":
            return rd("needreload_" + unit, "no")
        return rd("g_" + unit + "_" + p, DEFAULTS.get(p, ""))
    exists = os.path.exists(os.path.join(unitdir, unit))
    n = rd("count", "0")
    if p == "LoadState":
        return "loaded" if exists else "not-found"
    if p == "ActiveState":
        return rd("active_" + unit, "inactive")
    if p == "UnitFileState":
        return rd("ufs_" + unit, ("disabled" if unit.endswith(".timer") else "static") if exists else "")
    if p == "NeedDaemonReload":
        return rd("needreload_" + unit, "no")
    if p == "Result":
        return rd("result_" + n, "success")
    if p == "ExecMainStatus":
        return rd("status_" + n, "0")
    if p == "ExecMainCode":
        return "1"
    if p == "ExecMainStartTimestampMonotonic":
        return "0" if n == "0" else "1000000"
    if p == "ExecMainExitTimestampMonotonic":
        return "1250000"
    if p == "MemoryPeak":
        return rd("mempeak", "1048576")
    if p == "CPUUsageNSec":
        return "90000000"
    return ""
if value:
    print(prop(props[0]))
else:
    for p in props:
        print(p + "=" + prop(p))
""".replace("@@GUARDED@@", repr(GUARDED))


@pytest.fixture(scope="module")
def build_g3():
    sys.path.insert(0, str(DIR))
    try:
        import build_g3 as module
    finally:
        sys.path.remove(str(DIR))
    return module


class World:
    def __init__(self, tmp_path: Path, build):
        self.root = tmp_path
        self.fake = tmp_path / "fake"
        self.shims = tmp_path / "shims"
        self.units = tmp_path / "etc-systemd-system"
        self.out = tmp_path / "home" / "operator_presentation"
        self.src = tmp_path / "src"
        self.work = tmp_path / "tmp"
        for d in (self.fake, self.shims, self.units, self.out, self.src, self.work):
            d.mkdir(parents=True)
        self.out.chmod(0o700)
        for unit in build.unit_names(build.G3_PUBLISHERS):
            shutil.copy(DIR / unit, self.units / unit)
            (self.units / unit).chmod(0o644)
        (self.shims / "systemctl").write_text(SYSTEMCTL, encoding="utf-8")
        (self.shims / "curl").write_text(
            '#!/bin/sh\necho "${FAKE_HEALTH:-200}"\n', encoding="utf-8"
        )
        (self.shims / "runuser").write_text(
            '#!/bin/sh\nshift 3\nexec "$@"\n', encoding="utf-8"
        )
        (self.shims / "journalctl").write_text(
            "#!/bin/sh\necho journal-line\n", encoding="utf-8"
        )
        (self.shims / "python-deployed").write_text(
            f'#!/bin/sh\ncase "$2" in import*) exit 0;; esac\nRC=$(cat "{self.fake}/contract_rc" 2>/dev/null || echo 0)\n'
            'if [ "$RC" != 0 ]; then echo "contract-valid=False {}"; exit "$RC"; fi\n'
            'echo "contract-valid=True {}"\n',
            encoding="utf-8",
        )
        for shim in self.shims.iterdir():
            shim.chmod(0o755)
        self.script = tmp_path / "g3.sh"
        self.script.write_text(build.build(), encoding="utf-8")
        self.build = build

    def env(self, **extra):
        env = {
            "PATH": f"{self.shims}:/usr/bin:/bin",
            "FAKE": str(self.fake),
            "G3_TEST": "1",
            "G3_UNITDIR": str(self.units),
            "G3_OUTDIR": str(self.out),
            "G3_OWNER": "root",
            "G3_SRC": str(self.src),
            "G3_PYBIN": str(self.shims / "python-deployed"),
            "G3_GAP": "0",
            "TMPDIR": str(self.work),
        }
        env.update(extra)
        return env

    def run(self, mode, pub="runtime-service", **extra):
        return subprocess.run(
            ["sh", str(self.script), mode, pub],
            capture_output=True,
            text=True,
            env=self.env(**extra),
            timeout=60,
            check=False,
        )

    def calls(self):
        p = self.fake / "calls.log"
        return p.read_text().splitlines() if p.exists() else []

    def starts(self):
        return [c for c in self.calls() if c.startswith("start")]

    def forbidden(self):
        p = self.fake / "forbidden.log"
        return p.read_text() if p.exists() else ""

    def set(self, name, text):
        (self.fake / name).write_text(text, encoding="utf-8")

    def out_files(self):
        return sorted(p.name for p in self.out.iterdir())


@pytest.fixture()
def world(tmp_path, build_g3):
    return World(tmp_path, build_g3)


def summary(result):
    return result.stdout.split("== summary")[-1]


# --------------------------------------------------------------------- source properties


def test_generated_g3_files_have_no_drift(build_g3):
    assert (DIR / "g3_trials.sh").read_text(encoding="utf-8") == build_g3.build()
    assert (DIR / "g3_paste_block.sh").read_text(
        encoding="utf-8"
    ) == build_g3.build_paste()


def test_expected_hashes_are_the_reviewed_unit_files(build_g3):
    text = build_g3.build()
    for unit, digest in build_g3.unit_hashes(build_g3.G3_PUBLISHERS).items():
        assert hashlib.sha256((DIR / unit).read_bytes()).hexdigest() == digest
        assert f"{unit}) echo {digest} ;;" in text
    assert "events" not in text.split("OURS=")[1].splitlines()[0]


def test_script_never_uses_forbidden_verbs(build_g3):
    code = "\n".join(
        line
        for line in build_g3.build().splitlines()
        if not line.lstrip().startswith("#")
    )
    for forbidden in (
        "systemctl enable",
        "systemctl stop",
        "systemctl restart",
        "systemctl reload",
        "daemon-reload",
        "systemctl link",
        "systemctl mask",
        "systemctl disable",
        "systemctl edit",
        "sudo",
        "EnvironmentFile",
        ".env",
    ):
        assert forbidden not in code, forbidden
    verbs = {
        line.split("systemctl", 1)[1].split()[0]
        for line in code.splitlines()
        if "systemctl " in line
    }
    assert verbs <= {"show", "start"}, verbs


# --------------------------------------------------------------------- plan


def test_plan_ok_starts_and_writes_nothing(world):
    r = world.run("plan")
    assert r.returncode == 0, r.stdout
    assert "RESULT: OK (preconditions hold)" in r.stdout
    assert world.starts() == [] and world.forbidden() == ""
    assert world.out_files() == []
    assert list(world.work.iterdir()) == []


@pytest.mark.parametrize(
    "mutate,needle",
    [
        (
            lambda w: (w.units / "crypto-publish-storage.timer").write_text("tampered"),
            "hash",
        ),
        (
            lambda w: w.set("needreload_crypto-advisor.service", "yes"),
            "NeedDaemonReload",
        ),
        (
            lambda w: w.set("ufs_crypto-publish-runtime-service.timer", "enabled"),
            "must be disabled",
        ),
        (
            lambda w: w.set("active_crypto-publish-storage.service", "active"),
            "must be inactive",
        ),
        (lambda w: w.out.chmod(0o755), "need 'root 700'"),
        (lambda w: shutil.rmtree(w.out), "does not exist"),
    ],
)
def test_preconditions_refuse_without_starting(world, mutate, needle):
    mutate(world)
    r = world.run("plan")
    assert r.returncode == 1 and needle in r.stdout
    assert world.starts() == []


def test_health_not_200_refuses(world):
    r = world.run("plan", FAKE_HEALTH="503")
    assert r.returncode == 1 and "healthz before is 503" in r.stdout


def test_validators_not_importable_refuses(world):
    (world.shims / "python-deployed").write_text(
        "#!/bin/sh\nexit 1\n", encoding="utf-8"
    )
    r = world.run("plan")
    assert r.returncode == 1 and "cannot be imported" in r.stdout


def test_usage_errors(world):
    assert world.run("plan", pub="events").returncode == 2
    assert world.run("start").returncode == 2


# --------------------------------------------------------------------- run


@pytest.mark.parametrize("pub", ["runtime-service", "storage"])
def test_run_three_trials_of_one_publisher_only(world, pub):
    r = world.run("run", pub=pub)
    assert r.returncode == 0, r.stdout
    assert "RESULT: OK (all checks passed)" in r.stdout
    assert "trials passed: 3/3" in r.stdout
    assert world.starts() == [f"start crypto-publish-{pub}.service"] * 3
    assert world.forbidden() == ""
    assert world.out_files() == [ART[pub]]
    assert "UNCHANGED" in r.stdout and "MemoryPeak=1048576" in r.stdout
    assert "duration=250ms" in r.stdout


def test_memory_peak_unset_is_not_available_not_zero(world):
    world.set("mempeak", "[not set]")
    r = world.run("run")
    assert r.returncode == 0 and "MemoryPeak=NOT_AVAILABLE" in r.stdout


def test_failure_stops_the_series_and_repairs_nothing(world):
    world.set("result_2", "failed")
    world.set("status_2", "1")
    r = world.run("run")
    assert r.returncode == 1
    assert "RESULT: FAILED" in summary(r) and "Result=failed" in r.stdout
    assert len(world.starts()) == 2
    assert world.forbidden() == "" and world.out_files() == [ART["runtime-service"]]


def test_invalid_contract_stops_at_first_trial(world):
    world.set("contract_rc", "1")
    r = world.run("run")
    assert r.returncode == 1 and "contract check exit status 1" in r.stdout
    assert len(world.starts()) == 1


def test_artifact_not_refreshed_is_a_failure(world):
    world.set("no_write", "1")
    r = world.run("run")
    assert r.returncode == 1 and "missing or not a regular file" in r.stdout
    assert len(world.starts()) == 1


def test_stale_artifact_is_not_accepted_as_fresh(world):
    (world.out / ART["runtime-service"]).write_text("{}")
    (world.out / ART["runtime-service"]).chmod(0o600)
    world.set("no_write", "1")
    r = world.run("run")
    assert r.returncode == 1 and "was not refreshed" in r.stdout


def test_start_failure_is_counted(world):
    world.set("start_rc", "1")
    r = world.run("run")
    assert r.returncode == 1 and "systemctl start exit status 1" in r.stdout


def test_leftover_file_in_output_dir_fails(world):
    world.set("extra_file", "1")
    r = world.run("run")
    assert r.returncode == 1 and "unexpected files" in r.stdout


def test_guarded_unit_change_fails(world):
    world.set("g_change_on_start", "1")
    r = world.run("run")
    assert r.returncode == 1 and "Advisor/API/web CHANGED" in r.stdout
    assert len(world.starts()) == 1


def test_timer_becoming_active_fails(world):
    world.set("timer_on_start", "1")
    r = world.run("run")
    assert r.returncode == 1 and "must stay inactive/disabled" in r.stdout


def test_run_refuses_unprotected_script(world):
    world.script.chmod(0o666)
    r = world.run("run")
    assert r.returncode == 3 and world.starts() == []
    assert "protected" in r.stdout


def test_run_refuses_group_writable_directory(world):
    world.script.chmod(0o644)
    world.root.chmod(0o777)
    try:
        r = world.run("run")
    finally:
        world.root.chmod(0o755)
    assert r.returncode == 3 and world.starts() == []


# --------------------------------------------------------------------- paste block


def block_run(world, build, mode, pub, tamper=False):
    text = build.build_paste()
    if tamper:
        text = text.replace("RESULT: OK", "RESULT: OK ", 1)
    path = world.root / "block.sh"
    path.write_text(text, encoding="utf-8")
    env = world.env(G3_MODE=mode, G3_PUB=pub)
    return subprocess.run(
        ["sh", str(path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_paste_block_plan_runs_the_hashed_script(world, build_g3):
    r = block_run(world, build_g3, "plan", "storage")
    assert r.returncode == 0, r.stdout
    assert "RESULT: OK (preconditions hold)" in r.stdout
    assert "G3 plan storage exit status: 0" in r.stdout
    assert world.starts() == []


def test_paste_block_tamper_is_refused_before_running(world, build_g3):
    r = block_run(world, build_g3, "plan", "storage", tamper=True)
    assert (
        r.returncode != 0 and "HASH MISMATCH OF THE PROTECTED COPY: not run" in r.stdout
    )
    assert world.calls() == []
    assert not list(Path("/run").glob("g3priv.*"))


def test_paste_block_usage_errors(world, build_g3):
    assert block_run(world, build_g3, "start", "storage").returncode == 2
    assert block_run(world, build_g3, "plan", "events").returncode == 2
    assert block_run(world, build_g3, "plan", "").returncode == 2


def test_paste_block_uses_sudo_only_for_run(build_g3):
    text = build_g3.build_paste()
    assert 'case "$MODE" in run) PRIV=sudo;; esac' in text
    assert text.count("sudo") == 1
