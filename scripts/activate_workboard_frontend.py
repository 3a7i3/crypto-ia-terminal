"""Operator-run frontend release. Default inspect-only; never restart Advisor/API."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import time
import urllib.request

SOURCE_SHA = "bdca77f9bcf306c17846985faef870844fdd1334"
PREVIOUS = "/opt/crypto-ai-terminal/operator/releases/1728b3ad952b87d903ccb7442579000da292b848/frontend"
RELEASE = Path("/opt/crypto-ai-terminal/operator/releases") / SOURCE_SHA
DROPIN = Path("/etc/systemd/system/crypto-operator-web.service.d/99-workboard.conf")
UNCHANGED = ("crypto-advisor.service", "crypto-operator-api.service")
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
        "crypto-operator-web.service",
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
    if web_directory() != PREVIOUS or DROPIN.exists() or RELEASE.exists():
        raise ValueError("PREVIOUS_RELEASE_OR_OVERRIDE_CHANGED")
    if any(
        v["ActiveState"] != "active" or v["SubState"] != "running"
        for v in before.values()
    ):
        raise ValueError("PROTECTED_SERVICE_NOT_RUNNING")
    result = {
        "source_sha": SOURCE_SHA,
        "archive_sha256": args.sha256,
        "previous_web": PREVIOUS,
        "protected_services_before": before,
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
    activated = False
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
        with DROPIN.open("x") as stream:
            stream.write(
                f"[Service]\nWorkingDirectory={RELEASE}/frontend\nExecStart=\nExecStart=/usr/bin/env node {RELEASE}/{SERVER}\n"
            )
        DROPIN.chmod(0o644)
        activated = True
        command("systemctl", "daemon-reload")
        command("systemctl", "restart", "crypto-operator-web.service")
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
        result.update(
            {
                "disposition": "FRONTEND_ASSETS_SERVED_HASH_VERIFIED",
                "protected_services_after": after,
                "new_web": service_state("crypto-operator-web.service"),
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
        if activated:
            DROPIN.unlink()
            command("systemctl", "daemon-reload")
            command("systemctl", "restart", "crypto-operator-web.service")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
