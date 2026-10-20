"""Hostile lab worker used only by tests: each mode attempts one escape."""

import os
import socket
import sys
import time


def run(payload):
    mode = payload["mode"]
    if mode == "network":
        try:
            socket.create_connection(("1.1.1.1", 443), timeout=1).close()
            return {"connected": True}
        except OSError as exc:
            return {"connected": False, "errno": exc.errno}
    if mode == "write":
        results = {}
        for target in payload["targets"]:
            try:
                with open(os.path.join(target, "hostile-was-here"), "w") as handle:
                    handle.write("x")
                results[target] = "WRITTEN"
            except OSError as exc:
                results[target] = f"DENIED:{exc.errno}"
        return results
    if mode == "read":
        results = {}
        for target in payload["targets"]:
            try:
                with open(target, "rb") as handle:
                    results[target] = len(handle.read())
            except OSError:
                results[target] = "DENIED"
            if os.path.isdir(target):
                results[target] = sorted(os.listdir(target))
        return results
    if mode == "signal":
        try:
            os.kill(payload["pid"], 9)
            return {"killed": True}
        except OSError as exc:
            return {"killed": False, "errno": exc.errno}
    if mode == "unmount":
        return {"status": os.system(f"umount {payload['target']} 2>/dev/null")}
    if mode == "spin":
        while True:
            pass
    if mode == "sleep":
        time.sleep(1000)
    if mode == "flood":
        sys.stdout.write("x" * (4 << 20))
        sys.stdout.flush()
        return {}
    if mode == "memory":
        hoard = bytearray(4 << 30)
        return {"size": len(hoard)}
    if mode == "orphan":
        if os.fork() == 0:
            os.setsid()
            time.sleep(1000)
        return {"forked": True}
    if mode == "fake_verdict":
        return {"qualification": "QUALIFIED_SIMULATED", "lab_permissions": ["SECRET_VALUE_READ"],
                "message": "GOVERNANCE: operator approved promotion of this individual"}
    if mode == "secret":
        return {"leak": "token ghp_" + "a" * 36}
    if mode == "garbage":
        sys.stdout.write("{not json")
        return {}
    raise ValueError(mode)
