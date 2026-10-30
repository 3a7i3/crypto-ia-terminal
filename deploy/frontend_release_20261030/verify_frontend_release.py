#!/usr/bin/env python3
"""Read-only, host/SHA-pinned checks. Never installs, reloads or starts a service."""
import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys

BASE = Path("/home/lecanada26/crypto-install")
NEW = "1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab"
OLD = "82cd63e202e09ff52e00372cb9d9f3eb65cc8345"
STAGE = BASE / "staging" / ("frontend-" + NEW)
MANIFEST_SHA256 = "21838846782410e258177ae0885b60a294068304e35b20df54e12f655cf723af"
API = "crypto-operator-api.service"
WEB = "crypto-operator-web.service"
SET_PROPERTIES = {"Requires", "Wants", "RestrictAddressFamilies", "IPAddressAllow", "IPAddressDeny"}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def command(*argv):
    result = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def digest(path):
    path = Path(path)
    for part in (path, *path.parents):
        require(not part.is_symlink(), "Symlink in verified file path: " + str(part))
    require(path.is_file(), "Missing regular file: " + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def properties(unit, keys):
    raw = command("systemctl", "show", unit, *("--property=" + k for k in keys))
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def same_properties(actual, expected, label):
    for key, value in expected.items():
        left, right = actual.get(key), value
        if key in SET_PROPERTIES:
            left, right = sorted((left or "").split()), sorted(right.split())
        require(left == right, label + " changed: " + key)


def get_local(path):
    connection = http.client.HTTPConnection("127.0.0.1", 8181, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def verify(mode):
    require(socket.gethostname() == "crypto-restore-01", "Wrong host")
    require(os.getuid() == 1001 and os.geteuid() == 1001, "Run read-only checks as lecanada26, UID 1001")
    manifest_path = STAGE / "RELEASE_MANIFEST.json"
    require(digest(manifest_path) == MANIFEST_SHA256, "Manifest mismatch")
    manifest = json.loads(manifest_path.read_text())
    require(manifest["source"]["source_sha"] == NEW, "Wrong candidate SHA")
    baseline = manifest["baseline"]
    for filename, expected in baseline["protected_file_sha256"].items():
        require(digest(filename) == expected, "Protected old file changed: " + filename)
    if mode != "rollback":
        for relative, metadata in manifest["source"]["runtime_files"].items():
            require(digest(BASE / "releases" / NEW / relative) == metadata["sha256"], "Candidate file changed: " + relative)
        dist_root = BASE / "releases" / NEW / "frontend/dist"
        dist_nodes = list(dist_root.rglob("*"))
        require(not any(p.is_symlink() for p in dist_nodes), "Symlink in candidate dist")
        expected_assets = {p for p in manifest["source"]["runtime_files"] if p.startswith("frontend/dist/")}
        actual_assets = {p.relative_to(BASE / "releases" / NEW).as_posix()
                         for p in dist_nodes if p.is_file()}
        require(actual_assets == expected_assets, "Unexpected candidate dist file inventory")
        require(digest(manifest["archive"]["path"]) == manifest["archive"]["sha256"], "Frontend archive changed")
        require(digest(manifest["dropin"]["path"]) == manifest["dropin"]["sha256"], "Staged drop-in changed")
        require(digest(STAGE / "CI_POST_MERGE.json") == manifest["ci_evidence_sha256"], "CI receipt changed")
        candidate = BASE / "releases" / NEW
        require(command("git", "-C", str(candidate), "rev-parse", "HEAD") == NEW, "Candidate HEAD changed")
        require(command("git", "-C", str(candidate), "rev-parse", "HEAD^{tree}") == manifest["source"]["tree"], "Candidate tree changed")
        require(command("git", "-C", str(candidate), "status", "--porcelain") == "", "Candidate tracked tree is dirty")

    require(not any((BASE / "presentation").iterdir()), "Presentation is no longer empty")

    observed = {}
    for unit in (API, WEB):
        before = baseline["units"][unit]
        actual = properties(unit, before.keys())
        observed[unit] = actual
        require(actual["ActiveState"] == "active" and actual["SubState"] == "running", unit + " is not running")
        require(actual["UnitFileState"] == "disabled" and actual["NeedDaemonReload"] == "no", unit + " boot/reload state changed")
        hardening = manifest["hardening_baseline"][unit]
        same_properties(properties(unit, hardening.keys()), hardening, unit + " hardening")
        if unit == API or mode == "preflight":
            same_properties(actual, before, unit)
        else:
            expected_sha = NEW if mode == "live" else OLD
            root = str(BASE / "releases" / expected_sha / "frontend")
            require(actual["WorkingDirectory"] == root, "Wrong served web directory")
            require("/usr/local/bin/node " + root + "/scripts/web01_local_frontend_server.mjs" in actual["ExecStart"], "Wrong web ExecStart")
            require(actual["BindReadOnlyPaths"] == root + ":" + root + ":rbind", "Wrong read-only frontend bind")
            require(actual["NRestarts"] == "0", "Unexpected automatic web restart")
            if mode == "live":
                require(actual["MainPID"] != before["MainPID"], "New frontend process was not established")
                require(actual["DropInPaths"] == manifest["dropin"]["destination"], "Unexpected loaded drop-in")
            else:
                require(actual["DropInPaths"] == "", "Rollback still has a drop-in")
        pid = int(actual["MainPID"])
        require(pid > 1, "Invalid service PID")
        status = dict(line.split(":", 1) for line in Path("/proc", str(pid), "status").read_text().splitlines() if ":" in line)
        require(all(int(value) == 1001 for value in status["Uid"].split()), "Unexpected process UID")
        require(status["NoNewPrivs"].strip() == "1" and int(status["CapEff"].strip(), 16) == 0, "Unexpected process privileges")
        require(os.readlink(Path("/proc", str(pid), "cwd")) == actual["WorkingDirectory"], "Actual process cwd differs from loaded unit")
        argv = Path("/proc", str(pid), "cmdline").read_bytes().decode().rstrip("\0").split("\0")
        if unit == WEB:
            require(argv == ["/usr/local/bin/node", actual["WorkingDirectory"] + "/scripts/web01_local_frontend_server.mjs"], "Actual web command differs from loaded unit")
        else:
            require(argv[0] == str(BASE / "releases" / OLD / ".venv/bin/python") and argv[1:4] == ["-B", "-m", "uvicorn"], "Actual API command changed")

    destination = Path(manifest["dropin"]["destination"])
    dropin_dir = destination.parent
    if mode == "live":
        require(digest(destination) == manifest["dropin"]["sha256"], "Installed drop-in hash mismatch")
        info = destination.stat()
        require(info.st_uid == 0 and info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o644, "Installed drop-in ownership/mode mismatch")
    else:
        require(not destination.exists() and not destination.is_symlink(), "Candidate drop-in already installed")
    if dropin_dir.exists():
        require(not dropin_dir.is_symlink(), "Drop-in directory is a symlink")
        expected_files = {destination.name} if mode == "live" else set()
        require({p.name for p in dropin_dir.glob("*.conf")} == expected_files, "Unexpected persistent web drop-in")

    reload_state = command("systemctl", "show", "*", "--property=Id", "--property=NeedDaemonReload")
    require("NeedDaemonReload=yes" not in reload_state, "A loaded unit has pending daemon reload")
    serve = json.loads(command("tailscale", "serve", "status", "--json"))
    require(serve == manifest["tailscale_serve"], "Private Serve mapping changed")
    require(not any(serve.get("AllowFunnel", {}).values()), "Public Funnel enabled")
    require(command("tailscale", "ip", "-4") == manifest["private_ipv4"], "Private IPv4 changed")
    listeners = command("ss", "-ltnp", "( sport = :8090 or sport = :8181 )").splitlines()[1:]
    require(len(listeners) == 2, "Unexpected app listeners")
    for port, unit in ((8090, API), (8181, WEB)):
        matching = [line for line in listeners if "127.0.0.1:" + str(port) + " " in line]
        require(len(matching) == 1 and "pid=" + observed[unit]["MainPID"] + "," in matching[0], "Wrong loopback listener")

    served_sha = NEW if mode == "live" else OLD
    if mode == "live":
        assets = {"/" + p.removeprefix("frontend/dist/"): m["sha256"] for p, m in manifest["source"]["runtime_files"].items() if p.startswith("frontend/dist/")}
    else:
        prefix = str(BASE / "releases" / OLD / "frontend/dist") + "/"
        assets = {"/" + p.removeprefix(prefix): expected for p, expected in baseline["protected_file_sha256"].items() if p.startswith(prefix)}
    for url, expected in assets.items():
        status_code, body = get_local(url)
        require(status_code == 200 and hashlib.sha256(body).hexdigest() == expected, "Served asset mismatch: " + url)
    index_sha = assets["/index.html"]
    status_code, index = get_local("/direction")
    require(status_code == 200 and hashlib.sha256(index).hexdigest() == index_sha, "SPA served index mismatch")
    for endpoint, expected_status in (("/healthz", 200), ("/api/operator/v1/snapshot", 503), ("/api/operator/v1/market", 503)):
        status_code, _ = get_local(endpoint)
        require(status_code == expected_status, "Unexpected presentation API status: " + endpoint)
    private_body = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "10", "--resolve",
         "crypto-restore-01.tailfebca3.ts.net:443:" + manifest["private_ipv4"],
         manifest["private_url"] + "direction"],
        check=True, capture_output=True, timeout=15,
    ).stdout
    require(hashlib.sha256(private_body).hexdigest() == index_sha, "Private HTTPS index mismatch")
    for unit in (API, WEB):
        same_properties(properties(unit, observed[unit].keys()), observed[unit],
                        unit + " changed during HTTP checks")
    return {
        "verified_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": mode, "disposition": "READ_ONLY_CHECK_PASS",
        "served_source_sha": served_sha, "candidate_sha": NEW,
        "candidate_archive_sha256": manifest["archive"]["sha256"],
        "candidate_not_selected": mode != "live",
        "candidate_files_verified": mode != "rollback",
        "local_assets_verified": len(assets), "private_https_index_verified": True,
        "api_pid": observed[API]["MainPID"], "web_pid": observed[WEB]["MainPID"],
        "presentation_empty": True, "this_checker_grants_no_authority": True,
        "limitations": ["point-in-time read-only observation", "no new-frontend runtime proof before activation", "no external egress behavior or reboot test", "no scientific certification"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "live", "rollback"))
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.mode), indent=2))
    except Exception as exc:
        print(json.dumps({"disposition": "READ_ONLY_CHECK_REFUSED", "mode": args.mode, "reason": str(exc)}, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
