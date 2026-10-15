"""G2 — inactive installation of the passive-publisher units (prepared, never run on the VPS).

The G2 script is exercised against a fake systemd world: `systemctl` and `systemd-analyze` are
shims, the unit directory, state directory and output directory are temporary directories
(G2_TEST=1 redirects the paths). The fake `systemctl` records every call, and any sub-command
other than `show` and `daemon-reload` is a test failure: G2 may never enable, start, stop or
restart anything.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
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

pytestmark = pytest.mark.skipif(
    os.geteuid() != 0,
    reason="install -o root -g root needs root; the script itself is root-only",
)

SYSTEMCTL = r"""#!/usr/bin/env python3
import os, sys
fake = os.environ["FAKE"]; unitdir = os.environ["G2_UNITDIR"]
args = sys.argv[1:]
with open(os.path.join(fake, "calls.log"), "a") as f:
    f.write(" ".join(args) + "\n")
def rd(name, default=""):
    p = os.path.join(fake, name)
    return open(p).read().strip() if os.path.exists(p) else default
GUARDED = @@GUARDED@@
if args[:1] == ["daemon-reload"]:
    hook = os.path.join(fake, "reload_hook")
    if os.path.exists(hook):
        os.system("sh " + hook)
    sys.exit(int(rd("reload_rc", "0")))
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
    if p == "LoadState":
        return "loaded" if exists else "not-found"
    if p == "ActiveState":
        return rd("active_" + unit, "inactive")
    if p == "UnitFileState":
        return rd("ufs_" + unit, ("disabled" if unit.endswith(".timer") else "static") if exists else "")
    if p == "ExecMainStartTimestampMonotonic":
        return "0"
    if p == "NeedDaemonReload":
        return "no"
    return ""
if value:
    print(prop(props[0]))
else:
    for p in props:
        print(p + "=" + prop(p))
""".replace("@@GUARDED@@", repr(GUARDED))


@pytest.fixture(scope="module")
def build_g2():
    sys.path.insert(0, str(DIR))
    try:
        import build_g2 as module
    finally:
        sys.path.remove(str(DIR))
    return module


class World:
    def __init__(self, tmp_path: Path, build):
        self.root = tmp_path
        self.fake = tmp_path / "fake"
        self.shims = tmp_path / "shims"
        self.units = tmp_path / "etc-systemd-system"
        self.state = tmp_path / "var-lib-g2"
        self.out = tmp_path / "home" / "operator_presentation"
        self.work = tmp_path / "tmp"
        for d in (self.fake, self.shims, self.units, self.out.parent, self.work):
            d.mkdir(parents=True)
        (self.shims / "systemctl").write_text(SYSTEMCTL, encoding="utf-8")
        (self.shims / "systemd-analyze").write_text(
            '#!/bin/sh\necho "analyze $*" >> "$FAKE/analyze.log"\nexit "${SA_RC:-0}"\n',
            encoding="utf-8",
        )
        for shim in self.shims.iterdir():
            shim.chmod(0o755)
        self.script = tmp_path / "g2.sh"
        self.script.write_text(build.build(), encoding="utf-8")
        self.build = build

    def env(self, **extra):
        env = {
            "PATH": f"{self.shims}:/usr/bin:/bin",
            "FAKE": str(self.fake),
            "G2_TEST": "1",
            "G2_UNITDIR": str(self.units),
            "G2_STATE": str(self.state),
            "G2_OUTDIR": str(self.out),
            "G2_OWNER": "root",
            "TMPDIR": str(self.work),
        }
        env.update(extra)
        return env

    def run(self, mode, **extra):
        return subprocess.run(
            ["sh", str(self.script), mode],
            capture_output=True,
            text=True,
            env=self.env(**extra),
            timeout=60,
            check=False,
        )

    def tree(self):
        snap = {}
        for base in (self.units, self.state, self.out.parent):
            for p in sorted(base.rglob("*")) if base.exists() else []:
                snap[str(p)] = (
                    p.is_dir(),
                    p.read_bytes() if p.is_file() else None,
                    stat.S_IMODE(p.stat().st_mode),
                )
        return snap

    def calls(self):
        p = self.fake / "calls.log"
        return p.read_text().splitlines() if p.exists() else []

    def forbidden(self):
        p = self.fake / "forbidden.log"
        return p.read_text() if p.exists() else ""

    def set(self, name, text):
        (self.fake / name).write_text(text, encoding="utf-8")


@pytest.fixture()
def world(tmp_path, build_g2):
    return World(tmp_path, build_g2)


def summary(result):
    return result.stdout.split("== summary")[-1]


def unit_files(world):
    return sorted(p.name for p in world.units.iterdir())


# --------------------------------------------------------------------- source properties


def test_generated_g2_files_have_no_drift(build_g2):
    assert (DIR / "g2_install_inactive.sh").read_text(
        encoding="utf-8"
    ) == build_g2.build()
    assert (DIR / "g2_paste_block.sh").read_text(
        encoding="utf-8"
    ) == build_g2.build_paste()


def test_embedded_units_are_the_reviewed_files_and_events_is_not_in_the_package(
    build_g2,
):
    script = build_g2.build()
    assert build_g2.G2_PUBLISHERS == ["runtime-service", "storage"]
    assert "crypto-publish-events" not in script
    for name, digest in build_g2.unit_hashes().items():
        assert digest == hashlib.sha256((DIR / name).read_bytes()).hexdigest()
        body = (DIR / name).read_text(encoding="utf-8")
        assert body in script and f"{name}) echo {digest} ;;" in script


def test_script_never_enables_starts_or_restarts_anything(build_g2):
    script = build_g2.build()
    code = "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("#")
    )
    # strip the embedded unit files (they legitimately contain words like `Restart`/`WantedBy`)
    code = re.sub(r"cat > \"\$W/units/[^\n]+\n.*?\nG2_EOF\n", "", code, flags=re.DOTALL)
    subs = {sub.rstrip(";") for sub in re.findall(r"systemctl\s+(\S+)", code)}
    assert subs == {"show", "daemon-reload"}, subs
    for forbidden in (
        "enable",
        "disable",
        "start",
        "stop",
        "restart",
        "reload-or",
        "mask",
        "link",
        "kill",
        "--now",
        "sudo",
        "EnvironmentFile",
        ".env",
        "git ",
        "curl",
        "wget",
        "pip ",
    ):
        assert not re.search(rf"systemctl\s+{re.escape(forbidden)}\b", code), forbidden
    assert "sudo" not in code
    assert "rm -rf" not in code.replace('rm -rf "$W"', "").replace(
        'rm -rf "$STATE"', ""
    )


def test_package_services_have_no_install_section_and_timers_only_target_timers(
    build_g2,
):
    for name in build_g2.unit_names():
        text = (DIR / name).read_text(encoding="utf-8")
        if name.endswith(".service"):
            assert "[Install]" not in text and "WantedBy" not in text
            assert not re.search(
                r"^(Wants|Requires|Requisite|BindsTo|PartOf|Upholds)=",
                text,
                re.MULTILINE,
            )
        else:
            assert re.search(r"^WantedBy=timers\.target$", text, re.MULTILINE)


def test_paste_block_default_mode_is_plan_and_apply_escalates_only_through_sudo(
    build_g2,
):
    block = build_g2.build_paste()
    assert "MODE=${G2_MODE:-plan}; unset G2_MODE" in block
    assert (
        block.count("sudo ") == 1
        and 'apply|rollback) sudo sh "$D/g2.sh" "$MODE"' in block
    )
    digest = hashlib.sha256(build_g2.build().encode()).hexdigest()
    assert f'echo "{digest}  $D/g2.sh" | sha256sum -c -' in block


# --------------------------------------------------------------------- behaviour


def test_plan_and_verify_before_install_write_nothing(world):
    before = world.tree()
    plan = world.run("plan")
    assert plan.returncode == 0, plan.stdout + plan.stderr
    assert "RESULT: OK" in summary(plan) and "nothing was written (plan)" in plan.stdout
    assert (
        str(world.out) in plan.stdout and "absent (will be created 0700" in plan.stdout
    )
    assert world.tree() == before and world.calls() == [
        c for c in world.calls() if c.startswith("show")
    ]
    verify = world.run("verify")
    assert verify.returncode == 1 and "missing" in summary(
        verify
    )  # nothing installed yet
    assert world.tree() == before and world.forbidden() == ""


def test_apply_installs_inactive_units_and_nothing_else(world):
    result = world.run("apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: OK" in summary(result) and "UNCHANGED" in result.stdout
    assert unit_files(world) == [
        "crypto-publish-runtime-service.service",
        "crypto-publish-runtime-service.timer",
        "crypto-publish-storage.service",
        "crypto-publish-storage.timer",
    ]
    for p in world.units.iterdir():
        assert p.read_bytes() == (DIR / p.name).read_bytes()
        assert stat.S_IMODE(p.stat().st_mode) == 0o644
    assert (
        stat.S_IMODE(world.out.stat().st_mode) == 0o700
        and list(world.out.iterdir()) == []
    )
    assert stat.S_IMODE(world.state.stat().st_mode) == 0o700
    manifest = (world.state / "manifest").read_text().splitlines()
    assert manifest[0].startswith("V1|") and any(
        line.startswith("OUTDIR|") and line.endswith("|created") for line in manifest
    )
    assert sum(line.startswith("FILE|") for line in manifest) == 4
    assert world.calls().count("daemon-reload") == 1
    assert world.forbidden() == "" and all(
        c == "daemon-reload" or c.startswith("show ") for c in world.calls()
    )
    assert not list(world.units.rglob("*.wants")) and not [
        p for p in world.units.rglob("*") if p.is_symlink()
    ]
    assert world.run("verify").returncode == 0
    replan = world.run("plan")
    assert replan.returncode == 0 and "identical (will be left as is)" in replan.stdout
    again = world.run("apply")
    assert again.returncode == 1 and "already applied" in again.stdout


def test_apply_refuses_before_any_write_on_pending_daemon_reload(world):
    world.set("needreload_crypto-operator-api.service", "yes")
    before = world.tree()
    result = world.run("apply")
    assert result.returncode == 1 and "NeedDaemonReload=yes" in result.stdout
    assert "nothing was written" in result.stdout and world.tree() == before
    assert "daemon-reload" not in world.calls()


def test_apply_refuses_output_dir_with_other_mode_and_does_not_chmod_it(world):
    world.out.mkdir(mode=0o755)
    world.out.chmod(0o755)
    result = world.run("apply")
    assert result.returncode == 1 and "need 'root 700'" in result.stdout.replace(
        "(need '", "need '"
    ).replace("root 700')", "root 700'")
    assert stat.S_IMODE(world.out.stat().st_mode) == 0o755 and unit_files(world) == []
    assert not world.state.exists()


def test_apply_requires_root_and_writes_nothing_otherwise(world):
    _ = world.shims / "id"
    _.write_text(
        '#!/bin/sh\ncase "$1" in -u) echo 1000;; -un) echo operator;; *) exec /usr/bin/id "$@";; esac\n'
    )
    _.chmod(0o755)
    before = world.tree()
    result = world.run("apply")
    assert (
        result.returncode == 3
        and "must run as root" in result.stdout
        and world.tree() == before
    )


def test_verify_failure_stops_before_any_write(world):
    before = world.tree()
    result = world.run("apply", SA_RC="1")
    assert (
        result.returncode == 1
        and "systemd-analyze verify exit status 1" in result.stdout
    )
    assert "nothing was written" in result.stdout and world.tree() == before


def test_apply_detects_a_guarded_unit_that_changes_and_points_to_rollback(world):
    # the fake daemon-reload "restarts" the API: the before/after comparison must catch it
    world.set(
        "reload_hook",
        f'echo 4321 > "{world.fake}/g_crypto-operator-api.service_MainPID"\n',
    )
    result = world.run("apply")
    assert result.returncode == 1 and "guarded units CHANGED" in result.stdout
    assert "G2_MODE=rollback" in result.stdout


def test_apply_catches_a_unit_that_would_be_active_or_enabled(world):
    world.set("ufs_crypto-publish-storage.timer", "enabled")
    result = world.run("apply")
    assert (
        result.returncode == 1
        and "already enabled" in result.stdout
        and unit_files(world) == []
    )
    (world.fake / "ufs_crypto-publish-storage.timer").unlink()
    # installed, then something enables a timer behind our back: verify reports it
    assert world.run("apply").returncode == 0
    world.set("ufs_crypto-publish-storage.timer", "enabled")
    verify = world.run("verify")
    assert verify.returncode == 1 and "must be disabled" in verify.stdout
    world.set("ufs_crypto-publish-storage.timer", "disabled")
    world.set("active_crypto-publish-storage.service", "activating")
    assert world.run("verify").returncode == 1


def test_verify_detects_altered_installed_file(world):
    assert world.run("apply").returncode == 0
    target = world.units / "crypto-publish-storage.service"
    target.write_text(target.read_text() + "# tampered\n")
    result = world.run("verify")
    assert result.returncode == 1 and "differs from the reviewed hash" in result.stdout


def test_preexisting_different_unit_is_backed_up_and_restored_by_rollback(world):
    old = world.units / "crypto-publish-storage.timer"
    old.write_text("# somebody else's older file\n")
    original = old.read_bytes()
    result = world.run("apply")
    assert result.returncode == 0, result.stdout
    assert (
        "DIFFERENT" in result.stdout
        and (world.state / "backup" / old.name).read_bytes() == original
    )
    assert old.read_bytes() == (DIR / old.name).read_bytes()
    back = world.run("rollback")
    assert back.returncode == 0, back.stdout
    assert old.read_bytes() == original  # restored byte for byte
    assert unit_files(world) == [
        old.name
    ]  # the three other files were created by us and are gone
    assert not world.state.exists() and not world.out.exists()
    assert world.calls().count("daemon-reload") == 2 and world.forbidden() == ""


def test_rollback_removes_only_files_it_created_and_leaves_diverged_and_nonempty_things(
    world,
):
    foreign = world.units / "crypto-market-radar.service"
    foreign.write_text("# not ours\n")
    assert world.run("apply").returncode == 0
    diverged = world.units / "crypto-publish-runtime-service.service"
    diverged.write_text(diverged.read_text() + "# edited by hand after G2\n")
    (world.out / "runtime_service_snapshot.json").write_text("{}")
    back = world.run("rollback")
    assert (
        back.returncode == 1
        and "DIVERGED" in back.stdout
        and str(diverged) in back.stdout
    )
    assert diverged.exists() and foreign.read_text() == "# not ours\n"
    assert (
        world.out / "runtime_service_snapshot.json"
    ).exists()  # artifacts are never deleted
    assert (
        "not empty" in back.stdout
        and world.state.exists()
        and (world.state / "manifest").exists()
    )
    assert sorted(unit_files(world)) == [
        "crypto-market-radar.service",
        "crypto-publish-runtime-service.service",
    ]


def test_rollback_is_refused_while_a_publisher_unit_is_enabled_or_running(world):
    assert world.run("apply").returncode == 0
    world.set("ufs_crypto-publish-storage.timer", "enabled")
    before = world.tree()
    result = world.run("rollback")
    assert (
        result.returncode == 1 and "REFUSED" in result.stdout and world.tree() == before
    )
    world.set("ufs_crypto-publish-storage.timer", "disabled")
    world.set("active_crypto-publish-storage.timer", "active")
    assert world.run("rollback").returncode == 1


def test_rollback_without_manifest_does_nothing(world):
    result = world.run("rollback")
    assert (
        result.returncode == 1
        and "no manifest" in result.stdout
        and unit_files(world) == []
    )


def test_rollback_keeps_a_preexisting_output_directory(world):
    world.out.mkdir(mode=0o700)
    assert world.run("apply").returncode == 0
    assert "|existing" in (world.state / "manifest").read_text()
    assert world.run("rollback").returncode == 0 and world.out.is_dir()


def test_interruption_midway_leaves_a_manifest_that_rolls_back(world):
    # a failing install of the 2nd unit must not leave unrecorded files
    (world.shims / "install").write_text(
        '#!/bin/sh\ncase "$*" in *crypto-publish-runtime-service.timer*) exit 1;; esac\nexec /usr/bin/install "$@"\n'
    )
    (world.shims / "install").chmod(0o755)
    result = world.run("apply")
    assert result.returncode == 1
    (world.shims / "install").unlink()
    manifest = (world.state / "manifest").read_text()
    recorded = [
        line.split("|")[1] for line in manifest.splitlines() if line.startswith("FILE|")
    ]
    assert sorted(str(p) for p in world.units.iterdir()) == sorted(
        recorded
    )  # nothing unrecorded
    assert world.run("rollback").returncode == 0 and unit_files(world) == []


# --------------------------------------------------------------------- paste block


def _block_env(world):
    env = world.env()
    (world.shims / "sudo").write_text(
        '#!/bin/sh\necho "sudo $*" >> "$FAKE/sudo.log"\nexec "$@"\n'
    )
    (world.shims / "sudo").chmod(0o755)
    return env


def run_block(world, block, mode=None, **extra):
    env = _block_env(world)
    env.update(extra)
    prefix = f"G2_MODE={mode}\n" if mode else ""
    return subprocess.run(
        ["sh", "-c", prefix + block],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_paste_block_defaults_to_plan_and_uses_sudo_only_for_apply_and_rollback(
    world, build_g2
):
    block = build_g2.build_paste()
    before = world.tree()
    plan = run_block(world, block)
    assert (
        plan.returncode == 0
        and "G2 plan exit status: 0" in plan.stdout
        and world.tree() == before
    )
    assert not (world.fake / "sudo.log").exists()
    applied = run_block(world, block, mode="apply")
    assert applied.returncode == 0 and "G2 apply exit status: 0" in applied.stdout
    assert (world.fake / "sudo.log").read_text().count("sudo sh ") == 1
    assert not list(world.work.glob("g2blk.*")) and not list(
        world.work.glob("g2.*")
    )  # temp dirs removed
    rolled = run_block(world, block, mode="rollback")
    assert rolled.returncode == 0 and unit_files(world) == []


def test_paste_block_refuses_a_tampered_script_and_a_bad_mode(world, build_g2):
    block = build_g2.build_paste()
    tampered = block.replace(
        "systemctl daemon-reload;", "systemctl daemon-reload; echo pwned;", 1
    )
    assert tampered != block
    before = world.tree()
    result = run_block(world, tampered, mode="apply")
    assert (
        result.returncode == 1
        and "HASH MISMATCH: not run" in result.stdout
        and world.tree() == before
    )
    assert not (world.fake / "sudo.log").exists()
    bad = run_block(world, block, mode="enable")
    assert bad.returncode == 2 and "G2_MODE must be" in bad.stdout


# --------------------------------------------------------------------- G4 drop-in (not installed)


def test_g4_dropin_wires_only_runtime_service_and_storage_inside_the_output_directory():
    text = (DIR / "API_DROPIN_30-presentation-paths-rt-storage.conf").read_text(
        encoding="utf-8"
    )
    env = dict(re.findall(r"^Environment=([A-Z_]+)=(.+)$", text, re.MULTILINE))
    assert env == {
        "RUNTIME_SERVICE_SNAPSHOT_PATH": "/home/mathieu/operator_presentation/runtime_service_snapshot.json",
        "STORAGE_SNAPSHOT_PATH": "/home/mathieu/operator_presentation/storage_snapshot.json",
    }
    assert "EVENT_CENTER_SNAPSHOT_PATH" not in "\n".join(
        line for line in text.splitlines() if not line.startswith("#")
    )
    assert re.findall(r"^\[(\w+)\]$", text, re.MULTILINE) == ["Service"]
