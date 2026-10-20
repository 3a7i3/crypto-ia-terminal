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
                os.close(os.open(os.path.join(target, "hostile-was-here"), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
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
    if mode == "unix":
        results = {}
        for address in payload["targets"]:
            with socket.socket(socket.AF_UNIX) as sock:
                try:
                    sock.connect("\0" + address[1:] if address.startswith("@") else address)
                    results[address] = "CONNECTED"
                except OSError as exc:
                    results[address] = f"DENIED:{exc.errno}"
        return results
    if mode == "fork_spin":  # each process stays under the per-process CPU limit; together they exceed it
        for _ in range(payload["processes"]):
            if os.fork() == 0:
                deadline = time.process_time() + payload["each_cpu_ms"] / 1000
                while time.process_time() < deadline:
                    pass
                os._exit(0)
        while True:
            try:
                os.wait()
            except ChildProcessError:
                return {"done": True}
    if mode == "hold_spin":  # same, but every process stays alive: only the live /proc sum sees the CPU
        for _ in range(payload["processes"]):
            if os.fork() == 0:
                deadline = time.process_time() + payload["each_cpu_ms"] / 1000
                while time.process_time() < deadline:
                    pass
                while True:
                    time.sleep(60)
        while True:
            time.sleep(60)
    if mode == "bytecode":
        from tests.colony_lab import bytecode_probe

        return {"value": bytecode_probe.VALUE}
    if mode == "sys_path":
        return {"path": list(sys.path)}
    if mode == "fork_bomb":
        forked = 0
        for _ in range(64):
            try:
                if os.fork() == 0:
                    time.sleep(1000)
                    os._exit(0)
                forked += 1
            except OSError:
                break
        return {"forked": forked}
    if mode == "exit_code":
        os._exit(payload["code"])
    if mode == "self_signal":
        os.kill(os.getpid(), payload["signal"])
        time.sleep(5)
    if mode == "fake_verdict":
        return {"qualification": "QUALIFIED_SIMULATED", "lab_permissions": ["SECRET_VALUE_READ"],
                "message": "GOVERNANCE: operator approved promotion of this individual"}
    if mode == "secret":
        return {"leak": "token ghp_" + "a" * 36}
    if mode == "garbage":
        sys.stdout.write("{not json")
        return {}
    raise ValueError(mode)
