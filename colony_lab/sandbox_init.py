"""Init (pid 1) of a lab sandbox. Trusted: it runs before any individual code.

Started by the supervisor's setup script once the allowlisted root is built.
It forks the child, then until the child ends:

* reaps every process, orphans included;
* sums the CPU of the whole namespace (live, zombie and reaped processes) and
  kills everything above the budget, so forking does not multiply the budget;
* kills everything when the supervisor's lifeline pipe reaches EOF (supervisor
  stopped, timed out or died), so nothing outlives its supervisor.

Then it kills what is left and writes one status line on its own pipe. The
child cannot forge that line or trace this init (it holds capabilities the child
dropped); a signal the child sends it has no effect (namespace init, no handler). Python standard library only.
"""

import errno
import json
import os
import resource
import select
import signal
import sys

SETUP_FAILED = 97


def _namespace_cpu_s(tick: int) -> float:
    """CPU of every process but this init, plus what this init reaped."""
    own = os.times()
    total = own.children_user + own.children_system
    for name in os.listdir("/proc"):
        if not name.isdigit() or name == "1":
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as handle:
                fields = handle.read().rsplit(b")", 1)[1].split()
        except (OSError, IndexError):
            continue  # gone meanwhile: counted by whoever reaped it
        total += sum(int(value) for value in fields[11:15]) / tick  # utime stime cutime cstime
    return total


def _reap(child: int, state: dict) -> bool:
    """Reaps everything that exited; True once no process is left."""
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return True
        if pid == 0:
            return False
        if pid == child:
            state["status"] = status


def main(argv: list[str]) -> int:
    lifeline, report = int(argv[1]), int(argv[2])
    cpu, memory, processes = int(argv[3]), int(argv[4]), int(argv[5])
    command = argv[7:]
    if argv[6] != "--" or not command:
        return SETUP_FAILED
    exec_r, exec_w = os.pipe2(os.O_CLOEXEC)
    child = os.fork()
    if child == 0:
        try:
            os.close(lifeline)
            os.close(report)
            os.close(exec_r)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))  # per process; the total is enforced here
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_NPROC, (processes, processes))  # per user namespace
            os.execv(command[0], command)
        except BaseException:
            pass
        os.write(exec_w, b"x")
        os._exit(SETUP_FAILED)
    os.close(exec_w)
    tick = os.sysconf("SC_CLK_TCK")
    state: dict = {"status": None}
    reason = None
    while state["status"] is None and reason is None:
        try:
            ready, _, _ = select.select([lifeline], [], [], 0.05)
        except InterruptedError:
            ready = []
        if ready and not os.read(lifeline, 64):
            reason = "LIFELINE_CLOSED"
        _reap(child, state)
        if reason is None and _namespace_cpu_s(tick) > cpu:
            reason = "CPU_EXCEEDED"
    try:
        os.kill(-1, signal.SIGKILL)  # every process of the namespace but this init
    except OSError as exc:
        if exc.errno != errno.ESRCH:
            raise
    while not _reap(child, state):
        select.select([], [], [], 0.01)
    status = state["status"]
    line = {
        "reason": reason,
        "setup_failed": os.read(exec_r, 1) == b"x",
        "exit_code": os.WEXITSTATUS(status) if status is not None and os.WIFEXITED(status) else None,
        "signal": os.WTERMSIG(status) if status is not None and os.WIFSIGNALED(status) else None,
        "cpu_s": round(_namespace_cpu_s(tick), 3),
    }
    os.write(report, json.dumps(line, sort_keys=True).encode() + b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
