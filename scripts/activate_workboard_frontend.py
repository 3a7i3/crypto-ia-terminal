"""Operator-run frontend release. Default inspect-only; never restart Advisor/API."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request

# Bundle source: main after #451 (GitHub sync + 32-mission register). Frontend-only.
SOURCE_SHA = "8ff089b26cd15190e8be34c11b75b0b17c471ef6"
# Operator-reported previous release (bdca77f activation, GOV-286-WEB-FRONTEND-bdca77f).
# The preflight does not trust that report: it refuses unless the web unit really serves it.
PREVIOUS = "/opt/crypto-ai-terminal/operator/releases/bdca77f9bcf306c17846985faef870844fdd1334/frontend"
RELEASE = Path("/opt/crypto-ai-terminal/operator/releases") / SOURCE_SHA
# Previous activation reported a drop-in named 99-workboard.conf. systemd applies drop-ins in
# lexical order and "2" sorts after "." so this one wins; removing it restores the previous release.
PREVIOUS_DROPIN = "99-workboard.conf"
DROPIN = Path("/etc/systemd/system/crypto-operator-web.service.d/99-workboard2.conf")
WEB = "crypto-operator-web.service"
UNCHANGED = ("crypto-advisor.service", "crypto-operator-api.service")
# daemon-reload is manager-wide: it must not apply someone else's pending unit change to any of these.
RELOAD_GUARDED = (WEB, *UNCHANGED)
PROPERTIES = (
    "MainPID",
    "NRestarts",
    "ExecMainStartTimestamp",
    "ActiveState",
    "SubState",
)
SERVER = "frontend/scripts/web01_local_frontend_server.mjs"


def verified_files(raw: bytes, expected_sha: str) -> tuple[dict, dict[str, bytes]]:
    if len(raw) > 4_000_000 or hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("ARCHIVE_HASH_OR_SIZE_MISMATCH")
    files = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if (
                not member.isfile()
                or name.is_absolute()
                or ".." in name.parts
                or member.name in files
                or not (
                    member.name == "manifest.json"
                    or member.name == SERVER
                    or member.name.startswith("frontend/dist/")
                )
            ):
                raise ValueError("UNSAFE_ARCHIVE_MEMBER")
            total += member.size
            if total > 8_000_000:
                raise ValueError("UNBOUNDED_ARCHIVE")
            files[member.name] = archive.extractfile(member).read()
    manifest = json.loads(files.pop("manifest.json"))
    if manifest["source_sha"] != SOURCE_SHA or manifest["scope"] != "FRONTEND_ONLY":
        raise ValueError("WRONG_RELEASE_SCOPE")
    if set(files) != set(manifest["files"]):
        raise ValueError("MANIFEST_MEMBERS_MISMATCH")
    for name, data in files.items():
        if hashlib.sha256(data).hexdigest() != manifest["files"][name]:
            raise ValueError("FILE_HASH_MISMATCH")
    if "frontend/dist/index.html" not in files or SERVER not in files:
        raise ValueError("MISSING_FRONTEND")
    return manifest, files


def command(*args: str) -> str:
    return subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=30
    ).stdout


def service_state(service: str) -> dict:
    output = command(
        "systemctl", "show", service, *[f"--property={p}" for p in PROPERTIES]
    )
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def web_directory() -> str:
    return command(
        "systemctl",
        "show",
        WEB,
        "--property=WorkingDirectory",
        "--value",
    ).strip()


def verify_served(files: dict[str, bytes]) -> None:
    for name, expected in files.items():
        if not name.startswith("frontend/dist/"):
            continue
        route = name.removeprefix("frontend/dist/")
        with urllib.request.urlopen(
            "http://127.0.0.1:8181/" + route, timeout=5
        ) as response:
            if (
                hashlib.sha256(response.read()).digest()
                != hashlib.sha256(expected).digest()
            ):
                raise ValueError("SERVED_ASSET_HASH_MISMATCH")
    with urllib.request.urlopen(
        "http://127.0.0.1:8181/direction/travaux", timeout=5
    ) as response:
        if response.read() != files["frontend/dist/index.html"]:
            raise ValueError("SPA_ENTRYPOINT_MISMATCH")


def need_daemon_reload() -> dict[str, str]:
    return {
        service: command(
            "systemctl", "show", service, "--property=NeedDaemonReload", "--value"
        ).strip()
        for service in RELOAD_GUARDED
    }


def assert_no_pending_reload(code: str) -> dict[str, str]:
    """Anything but an explicit "no" (including an empty or unreadable value) refuses."""
    state = need_daemon_reload()
    if any(value != "no" for value in state.values()):
        raise ValueError(f"{code}: {json.dumps(state, sort_keys=True)}")
    return state


def dropin_tmp() -> Path:
    # Not "*.conf": systemd ignores it while it exists, so a half-written file is never loaded.
    return DROPIN.with_name(f".{DROPIN.name}.tmp")


def link_dropin_atomic(content: str, owned: list | None = None) -> None:
    """Complete content or nothing: write+fsync a private file, then link() it into place.

    link() is atomic and fails with FileExistsError if DROPIN exists, so an existing
    file is never replaced and a crash can never leave a truncated DROPIN.
    """
    tmp = dropin_tmp()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    if owned is not None:
        owned.append(tmp)  # only a temp file this run created may be removed by the restore
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        os.link(tmp, DROPIN)
    finally:
        tmp.unlink(missing_ok=True)


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def restore_previous(created: bool, tmp_owned: bool = False) -> list[str]:
    """Undo only what this run created. Every failed step is counted, none stops the others."""
    failures: list[str] = []

    def step(name: str, action) -> object:
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - each failure is reported, not hidden
            failures.append(f"{name}: {exc!r}")
            return None

    # Decided on the config systemd has loaded NOW, before the reload changes the answer.
    try:
        loaded_new = web_directory() != PREVIOUS
    except Exception as exc:  # noqa: BLE001
        failures.append(f"web_directory_before: {exc!r}")
        loaded_new = True
    if created:
        step("unlink_dropin", lambda: DROPIN.unlink())
    if tmp_owned:
        step("unlink_tmp", lambda: dropin_tmp().unlink(missing_ok=True))
    # Nothing was mutated and nothing loaded: no reload at all (it is manager-wide).
    if created or loaded_new:
        def read_foreign() -> dict:
            return {
                service: command(
                    "systemctl", "show", service, "--property=NeedDaemonReload", "--value"
                ).strip()
                for service in UNCHANGED
            }

        foreign = step("read_foreign_pending", read_foreign) or {"unreadable": "yes"}
        if any(value != "no" for value in foreign.values()):
            # A pending change on Advisor/API is someone else's: reloading would apply it.
            failures.append(
                "daemon_reload_skipped_foreign_pending: "
                + json.dumps(foreign, sort_keys=True)
            )
        else:
            step("daemon_reload", lambda: command("systemctl", "daemon-reload"))
            if loaded_new:
                step("restart_web", lambda: command("systemctl", "restart", WEB))

    def check_directory() -> None:
        if web_directory() != PREVIOUS:
            raise ValueError("WORKING_DIRECTORY_NOT_RESTORED")

    step("web_directory_after", check_directory)
    step(
        "need_daemon_reload_after",
        lambda: assert_no_pending_reload("NEED_DAEMON_RELOAD_AFTER_RESTORE"),
    )
    if created and DROPIN.exists():
        failures.append("dropin_still_present")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    manifest, files = verified_files(args.archive.read_bytes(), args.sha256)
    before = {s: service_state(s) for s in UNCHANGED}
    current_link = Path("/opt/crypto-ai-terminal/operator/current")
    current_target = os.readlink(current_link)
    if (
        web_directory() != PREVIOUS
        or DROPIN.exists()
        or dropin_tmp().exists()
        or RELEASE.exists()
    ):
        raise ValueError("PREVIOUS_RELEASE_OR_OVERRIDE_CHANGED")
    if any(
        v["ActiveState"] != "active" or v["SubState"] != "running"
        for v in before.values()
    ):
        raise ValueError("PROTECTED_SERVICE_NOT_RUNNING")
    reload_before = assert_no_pending_reload("NEED_DAEMON_RELOAD_PENDING")
    result = {
        "source_sha": SOURCE_SHA,
        "archive_sha256": args.sha256,
        "previous_web": PREVIOUS,
        "protected_services_before": before,
        "need_daemon_reload_before": reload_before,
        "current_link_untouched": current_target,
        "source_merge_sha": manifest.get("source_merge_sha"),
        "runtime_certification": "NOT_CERTIFIED",
    }
    if not args.activate:
        print(
            json.dumps({**result, "disposition": "INSPECT_ONLY_NO_MUTATION"}, indent=2)
        )
        return 0
    # Receipt is an operator-reviewed source gate, not an independent signature.
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("source_merge_sha") or ""):
        raise ValueError("MERGED_SOURCE_GATE_MISSING")
    if os.geteuid() != 0:
        raise PermissionError("PRIVILEGED_OPERATOR_REQUIRED")
    created = False
    tmp_owned: list = []
    try:
        RELEASE.mkdir(mode=0o755)
        for name, data in files.items():
            target = RELEASE / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            target.write_bytes(data)
            target.chmod(0o644)
        (RELEASE / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True)
        )
        (RELEASE / "manifest.json").chmod(0o644)
        DROPIN.parent.mkdir(exist_ok=True, mode=0o755)
        link_dropin_atomic(
            owned=tmp_owned,
            content=f"[Service]\nWorkingDirectory={RELEASE}/frontend\nExecStart=\nExecStart=/usr/bin/env node {RELEASE}/{SERVER}\n"
        )
        created = True
        fsync_dir(DROPIN.parent)
        command("systemctl", "daemon-reload")
        command("systemctl", "restart", WEB)
        last_error = None
        for _ in range(10):
            try:
                verify_served(files)
                last_error = None
                break
            except (OSError, ValueError) as exc:
                last_error = exc
                time.sleep(1)
        if last_error:
            raise last_error
        after = {s: service_state(s) for s in UNCHANGED}
        if after != before or os.readlink(current_link) != current_target:
            raise ValueError("PROTECTED_BOUNDARY_CHANGED")
        reload_after = assert_no_pending_reload("NEED_DAEMON_RELOAD_AFTER_ACTIVATE")
        result.update(
            {
                "disposition": "FRONTEND_ASSETS_SERVED_HASH_VERIFIED",
                "protected_services_after": after,
                "need_daemon_reload_after": reload_after,
                "new_web": service_state(WEB),
                "browser_runtime_proof": "PENDING",
            }
        )
        (RELEASE / "activation-proof.json").write_text(
            json.dumps(result, indent=2, sort_keys=True)
        )
        (RELEASE / "activation-proof.json").chmod(0o644)
        print(json.dumps(result, indent=2))
        return 0
    except BaseException:
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(signum, signal.SIG_IGN)
        failures = restore_previous(created, bool(tmp_owned))
        # The release directory is kept for forensics; the block owns the evidence copy.
        print(
            json.dumps(
                {
                    "restore": "INCOMPLETE" if failures else "OK",
                    "failure_count": len(failures),
                    "failures": failures,
                    "release_kept": str(RELEASE),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
