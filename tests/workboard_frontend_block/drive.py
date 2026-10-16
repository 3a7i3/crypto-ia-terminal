"""Pilote : lance 'final_block.sh activate' (script = parent, helper = enfant), attend un marqueur, applique UNE action.
Actions : kill_parent | kill_group | term_helper | hup_group | pty_loss (fermeture du maitre d'un vrai pty)."""

import fcntl
import os
import pty
import signal
import subprocess
import sys
import termios
import time

cleanup = sys.argv[1:] == ["cleanup"]
script, log, marker, action = (None,) * 4 if cleanup else sys.argv[1:5]
env = dict(os.environ, PATH=os.environ["SBX"] + "/bin:" + os.environ["PATH"])


def helper_pids():
    # The injected helper records its own namespace-local PID. Global pgrep can
    # return unrelated workers or host /proc PIDs that os.kill cannot address.
    try:
        with open(os.path.join(os.environ["SBX"], "helper-pids")) as stream:
            registered = [int(line) for line in stream if line.strip()]
    except FileNotFoundError:
        return []
    live = []
    for pid in registered:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        live.append(pid)
    return live


def kill_helpers():
    for pid in helper_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        os.unlink(os.path.join(os.environ["SBX"], "helper-pids"))
    except FileNotFoundError:
        pass


def wait_marker():
    for _ in range(80):
        time.sleep(0.25)
        with open(log, errors="replace") as stream:
            if marker in stream.read():
                return True
    return False


def pty_loss():
    master, slave = pty.openpty()

    def child():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        for fd in (0, 1, 2):
            os.dup2(slave, fd)
        if slave > 2:
            os.close(slave)
        os.close(master)

    proc = subprocess.Popen(
        ["bash", script, "activate"], env=env, preexec_fn=child, close_fds=True
    )
    os.close(slave)
    os.write(master, b"ACTIVER\n")
    seen = b""
    ok = False
    with open(log, "wb") as out:
        end = time.time() + 20
        while time.time() < end:
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            out.write(data)
            out.flush()
            seen += data
            if marker.encode() in seen:
                ok = True
                break
    if not ok:
        os.killpg(proc.pid, signal.SIGKILL)
        print("MARQUEUR ABSENT")
        sys.exit(3)
    os.close(master)
    print("rc script =", proc.wait(timeout=150))
    sys.exit(0)


def main():
    if action == "pty_loss":
        pty_loss()
    with open(log, "w") as out:
        proc = subprocess.Popen(
            ["bash", script, "activate"],
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        proc.stdin.write(b"ACTIVER\n")
        proc.stdin.close()
        if not wait_marker():
            os.killpg(proc.pid, signal.SIGKILL)
            print("MARQUEUR ABSENT")
            sys.exit(3)
        helpers = helper_pids()
        print("pid script parent =", proc.pid, "; pid helper(s) =", helpers)
        if action == "kill_parent":
            os.kill(proc.pid, signal.SIGKILL)
        elif action == "kill_group":
            os.killpg(proc.pid, signal.SIGKILL)
        elif action == "term_helper":
            for pid in helpers:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        elif action == "hup_group":
            os.killpg(proc.pid, signal.SIGHUP)
        else:
            sys.exit(4)
        print("action =", action)
        try:
            print("rc script =", proc.wait(timeout=150))
        except subprocess.TimeoutExpired:
            print("rc script = TIMEOUT")
            os.killpg(proc.pid, signal.SIGKILL)
        time.sleep(1)
        print("helper vivant apres l'action =", "OUI" if helper_pids() else "NON")


if cleanup:
    kill_helpers()
else:
    main()
