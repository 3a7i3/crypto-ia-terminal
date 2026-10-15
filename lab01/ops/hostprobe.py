"""Sondes exécutées DANS l'unité transitoire (stdlib seule, aucune écriture hors /tmp privé).

Lancé par host_isolation_tests.py : `python3.11 -I -c "<ce fichier>" '<json>'`.
Chaque sonde rapporte une observation du processus lui-même ; le verdict est rendu
par le lanceur, qui compare avec un essai témoin sans la directive testée.
"""

import json
import mmap
import os
import socket
import subprocess
import sys
import tempfile

ARGS = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
OUT = {}


def errname(exc):
    import errno

    return (
        errno.errorcode.get(exc.errno, f"E{exc.errno}")
        if getattr(exc, "errno", None)
        else type(exc).__name__
    )


def in_child(fn):
    """Exécute fn dans un enfant : 'ok', 'E<ERRNO>' ou 'SIG<n>' (tué par le filtre syscall)."""
    pid = os.fork()
    if pid == 0:
        try:
            fn()
        except OSError as exc:
            os._exit(100 + (exc.errno or 0) % 100)
        os._exit(0)
    _, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        return f"SIG{os.WTERMSIG(status)}"
    code = os.WEXITSTATUS(status)
    if code == 0:
        return "ok"
    import errno

    return errno.errorcode.get((code - 100) or 0, f"EXIT{code}")


def status_field(name):
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith(name + ":"):
                return line.split(":", 1)[1].strip()
    return None


def mountpoints():
    pts = set()
    with open("/proc/self/mountinfo") as fh:
        for line in fh:
            pts.add(line.split()[4].replace("\\040", " "))
    return pts


def write_try(path):
    try:
        fd, tmp = tempfile.mkstemp(dir=path, prefix=".lab01probe")
    except OSError as exc:
        return errname(exc)
    os.close(fd)
    os.unlink(tmp)
    return "ok"


def libc():
    import ctypes

    return ctypes.CDLL(None, use_errno=True)


def probe_nonewprivs():
    return status_field("NoNewPrivs")


def probe_caps():
    return {k: status_field(k) for k in ("CapEff", "CapBnd", "CapAmb")}


def probe_syscall():
    # nice() appartient à @resources : refusé par SystemCallFilter=~@resources (tue le processus).
    return {"seccomp": status_field("Seccomp"), "nice": in_child(lambda: os.nice(1))}


def probe_mdwe():
    try:
        mmap.mmap(-1, 4096, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
        return "ok"
    except OSError as exc:
        return errname(exc)


def probe_lockpers():
    def fn():
        lc = libc()
        if lc.personality(0x0008) == -1:  # PER_LINUX32
            import ctypes

            raise OSError(ctypes.get_errno(), "personality")

    return in_child(fn)


def probe_userns():
    def fn():
        import ctypes

        lc = libc()
        if lc.unshare(0x10000000) == -1:  # CLONE_NEWUSER
            raise OSError(ctypes.get_errno(), "unshare")

    return in_child(fn)


def probe_suid():
    fd, tmp = tempfile.mkstemp(dir="/tmp", prefix=".lab01suid")
    os.close(fd)
    try:
        os.chmod(tmp, 0o4755)
        return "ok"
    except OSError as exc:
        return errname(exc)
    finally:
        os.unlink(tmp)


def probe_af():
    res = {}
    for name, args in (
        ("AF_INET", (socket.AF_INET, socket.SOCK_STREAM)),
        ("AF_UNIX", (socket.AF_UNIX, socket.SOCK_STREAM)),
        ("AF_NETLINK", (socket.AF_NETLINK, socket.SOCK_RAW, 0)),
    ):
        try:
            socket.socket(*args).close()
            res[name] = "ok"
        except OSError as exc:
            res[name] = errname(exc)
    return res


def probe_netdev():
    with open("/proc/net/dev") as fh:
        names = [ln.split(":")[0].strip() for ln in fh.readlines()[2:]]
    return sorted(names)


def probe_ipdeny():
    def try_connect(host, port):
        s = socket.socket()
        s.settimeout(3)
        try:
            s.connect((host, port))
            return "ok"
        except socket.timeout:
            return "TIMEOUT"
        except OSError as exc:
            return errname(exc)
        finally:
            s.close()

    t = ARGS.get("listeners", {})
    if not t:
        return "N/A"
    return {
        "loopback": try_connect("127.0.0.1", t["loop_port"]),
        "hors_loopback": try_connect(t["host_ip"], t["host_port"]),
    }


def probe_write_ro():
    return {p: write_try(p) for p in ARGS.get("ro_paths", []) if os.path.isdir(p)}


def probe_write_rw():
    return {p: write_try(p) for p in ARGS.get("rw_paths", []) if os.path.isdir(p)}


def probe_inaccessible():
    pts = mountpoints()
    return {p: (p in pts) for p in ARGS.get("inacc_paths", []) if os.path.exists(p)}


def probe_tmp():
    name = ARGS.get("tmp_marker")
    if not name:
        return "N/A"
    with open(os.path.join("/tmp", name), "w") as fh:
        fh.write("x")
    return "written"


def probe_dev():
    return len(os.listdir("/dev"))


def probe_procsys():
    return bool(os.statvfs("/proc/sys").f_flag & os.ST_RDONLY)


def probe_cgroupfs():
    return bool(os.statvfs("/sys/fs/cgroup").f_flag & os.ST_RDONLY)


def probe_modules():
    p = os.path.realpath("/lib/modules")
    return {p: p in mountpoints()} if os.path.exists(p) else "N/A"


def exec_try(d):
    path = os.path.join(d, ".lab01exec")
    try:
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, 0o755)
        try:
            return "ok" if subprocess.run([path]).returncode == 0 else "rc!=0"
        except OSError as exc:
            return errname(exc)
    except OSError as exc:
        return errname(exc)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def probe_noexec():
    """Le même script s'exécute-t-il depuis chaque dossier ? (volume LAB : EACCES ; /tmp : témoin)."""
    return {d: exec_try(d) for d in ARGS.get("exec_dirs", []) if os.path.isdir(d)}


def probe_ids():
    import grp
    import pwd

    return {
        "user": pwd.getpwuid(os.getuid()).pw_name,
        "group": grp.getgrgid(os.getgid()).gr_name,
        "cwd": os.getcwd(),
    }


def probe_env():
    return sorted(os.environ)


def probe_umask():
    return status_field("Umask")


def probe_limits():
    wanted = {
        "Max open files": "NOFILE",
        "Max processes": "NPROC",
        "Max core file size": "CORE",
        "Max file size": "FSIZE",
    }
    out = {}
    with open("/proc/self/limits") as fh:
        for line in fh:
            for label, key in wanted.items():
                if line.startswith(label):
                    out[key] = line[len(label) :].split()[0]
    return out


def probe_cgroup():
    with open("/proc/self/cgroup") as fh:
        line = fh.read().strip().splitlines()[0]
    out = {"path": line.split("::", 1)[-1]}
    for name in ("memory.max", "memory.high", "memory.swap.max", "cpu.max", "pids.max"):
        try:
            with open(f"/sys/fs/cgroup/lab01.slice/{name}") as fh:
                out[name] = fh.read().strip()
        except OSError as exc:
            out[name] = "ABSENT:" + errname(exc)
    return out


PROBES = {k[6:]: v for k, v in dict(globals()).items() if k.startswith("probe_")}
for name in ARGS.get("only") or sorted(PROBES):
    try:
        OUT[name] = PROBES[name]()
    except (
        Exception
    ) as exc:  # une sonde qui échoue est INDÉTERMINÉE, jamais « refusée »
        OUT[name] = {"ERREUR": f"{type(exc).__name__}: {exc}"}
sys.stdout.write("PROBE-RESULT " + json.dumps(OUT, sort_keys=True) + "\n")
