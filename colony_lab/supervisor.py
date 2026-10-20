"""Colony lab supervisor: admits lab individuals and runs one task at a time in a sandbox.

LAB_ONLY. Nothing here reaches the VPS, the Advisor, an exchange or a secret
value, and nothing here is an A1 registration.

Sandbox (Linux, unprivileged), all of it required or the run is refused:

* user, network, mount and pid namespaces (``unshare``): no network interface,
  no visible outside process;
* a new read-only root (``pivot_root``) holding only an allowlist bound
  read-only: ``/usr``, the interpreter's prefixes, the repository and the host
  ``bin``/``lib``/``sbin`` links, plus ``/dev/{null,zero,random,urandom}`` and a
  fresh ``/proc``; the repository's ``.git``, ``.env*`` and ``docs/colony_lab``
  (criteria, golden answers, evidence) hidden under empty mounts. The old root is detached, so the lab root, ``/tmp``, the home
  directory and every UNIX socket outside the allowlist are absent;
* every capability dropped and ``no_new_privs`` set (``setpriv``), so the
  child cannot undo those mounts; empty environment;
* ``colony_lab/sandbox_init.py`` as namespace init: per-process rlimits
  (address space, file size 0, descriptors, at most ``MAX_PROCESSES``
  processes), a CPU budget summed over the whole namespace, and a lifeline
  pipe whose EOF (stop, timeout, supervisor death) kills every process;
* outcome classification from the init's own status pipe, never from an exit
  code the child could choose.

Not proven by this module: files inside the allowlist (repository, interpreter)
stay readable; the child runs under the operator's UNIX account; memory is
bounded per process (``MAX_PROCESSES`` x address space), not by a cgroup.
"""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from colony_lab.lineage import LineageError, check_qualification, verify_record
from sentinel_activity import SCHEMA_VERSION
from sentinel_activity.canonical import LedgerError, canonical_bytes
from sentinel_activity.redaction_v1 import redact
from sentinel_activity.store import ActivityStore, Limits

REPO = Path(__file__).resolve().parents[1]
CHILD = REPO / "colony_lab" / "child.py"
LAB_PREFIX = "colony-lab-"
TASK_SCHEMA = "colony-lab.task/0"
RESULT_SCHEMA = "colony-lab.result/0"
JOURNAL_DIR = "j01-lab-memory"
MAX_TASK_BYTES = 16_384
MAX_FILE_BYTES = 65_536
MAX_LINEAGE_DEPTH = 8
MAX_PROCESSES = 8  # per sandbox, init included (RLIMIT_NPROC of the user namespace)
POLL_S = 0.02
SANDBOX_EXIT = 97
_SYSTEM_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
INIT = REPO / "colony_lab" / "sandbox_init.py"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TASK_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_MISSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")
# Runs as the namespace's first process: builds the allowlisted read-only root, then execs the
# init. Directives: b:PATH bind read-only, l:PATH:TARGET symlink, d:PATH / f:PATH hide.
_SANDBOX_SCRIPT = r"""
set -u
R=$1; shift
mount -t tmpfs -o size=1m,mode=0755,nosuid,nodev colony-root "$R" || exit 97
mkdir "$R/dev" "$R/proc" "$R/.old" || exit 97
for device in null zero random urandom; do
  : > "$R/dev/$device" && mount --bind "/dev/$device" "$R/dev/$device" || exit 97
done
while [ $# -gt 0 ]; do
  item=$1; shift
  case "$item" in
    --) break ;;
    b:*) path=${item#b:}
         mkdir -p "$R$path" && mount --bind "$path" "$R$path" &&
           mount -o remount,bind,ro,nosuid,nodev "$R$path" || exit 97 ;;
    l:*) rest=${item#l:}; ln -s "${rest#*:}" "$R${rest%%:*}" || exit 97 ;;
    d:*) mount -t tmpfs -o ro,size=4k,nosuid,nodev,noexec colony-hidden "$R${item#d:}" || exit 97 ;;
    f:*) mount --bind -o ro /dev/null "$R${item#f:}" || exit 97 ;;
    *) exit 97 ;;
  esac
done
mount -t proc -o nosuid,nodev,noexec proc "$R/proc" || exit 97
cd "$R" && pivot_root . .old || exit 97
umount -l /.old && rmdir /.old || exit 97
mount -o remount,bind,ro / || exit 97
cd / && exec "$@"
exit 97
"""


@dataclass(frozen=True)
class TaskType:
    capability: str
    module: str


TASKS = {"SENTINEL_ASK": TaskType("DIAGNOSTIC_PRODUCE", "colony_lab.workers.sentinel")}
_PROBE = TaskType("NONE", "colony_lab.workers.probe")


class LabError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _lab_root(path: Any) -> Path:
    root = Path(path)
    if not root.is_absolute() or ".." in root.parts or not root.name.startswith(LAB_PREFIX):
        raise LabError("LAB_ROOT_DENIED")
    try:
        info = os.lstat(root)
    except OSError:
        raise LabError("LAB_ROOT_UNAVAILABLE") from None
    if not os.path.isdir(root) or os.path.islink(root) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise LabError("LAB_ROOT_DENIED")
    return root


def _write_new(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _replace(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    _write_new(tmp, data)
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_json(path: Path) -> Any:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise LabError("INDIVIDUAL_INVALID") from None
    with os.fdopen(fd, "rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise LabError("INDIVIDUAL_INVALID")
    return _strict_json(raw, "INDIVIDUAL_INVALID")


def _strict_json(raw: bytes, code: str) -> Any:
    def pairs(items):
        keys = [key for key, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate key")
        return dict(items)

    def constant(_):
        raise ValueError("non-finite number")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise LabError(code) from None


def _dump(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=1).encode() + b"\n"


def _redacted(value: Any) -> tuple[Any, int]:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        pairs = [_redacted(item) for item in value]
        return [item for item, _ in pairs], sum(count for _, count in pairs)
    if isinstance(value, dict):
        out, total = {}, 0
        for key, item in value.items():
            safe_key, key_count = redact(key)
            out[safe_key], count = _redacted(item)
            total += key_count + count
        return out, total
    return value, 0


def journal_policy(agent_id: str) -> dict:
    return {"version": "fixture-colony-lab-0", "producers": {
        "fixture-supervisor": {"actor_id": "fixture-colony-supervisor", "actor_kind": "SYSTEM",
                               "actor_version": None, "role": "OBSERVER"},
        "fixture-individual": {"actor_id": "fixture-ind-" + agent_id[:16], "actor_kind": "AGENT",
                               "actor_version": None, "role": "OBSERVER"}}}


class Supervisor:
    """External control over lab individuals; the individuals never hold a handle on it."""

    def __init__(self, lab_root: Path, *, missions: frozenset[str], tasks: dict[str, TaskType] = TASKS,
                 python: str = sys.executable) -> None:
        self.root = _lab_root(lab_root)
        self.stop_file = self.root / "STOP"
        self.missions = frozenset(missions)
        self.tasks = dict(tasks)
        self.python = python
        self._stopped = threading.Event()
        self._groups: dict[int, int] = {}  # process group -> lifeline write end
        self._groups_lock = threading.Lock()
        tools = {name: shutil.which(name, path=_SYSTEM_PATH)
                 for name in ("unshare", "mount", "umount", "pivot_root", "setpriv", "env")}
        self._tools = tools if all(tools.values()) else None
        self.sandbox = "UNVERIFIED"

    # ── External stop ──────────────────────────────────────────────────────
    @property
    def stopped(self) -> bool:
        """Latched by stop(); the STOP file is the operator's switch. Unreadable root counts as stopped."""
        try:
            return self._stopped.is_set() or os.path.lexists(self.stop_file) or not os.path.isdir(self.root)
        except OSError:
            return True

    def stop(self) -> None:
        self._stopped.set()
        with self._groups_lock:
            for group in list(self._groups):
                self._kill(group)

    def resume(self) -> bool:
        """Operator action: clears the latch only once the STOP file is gone."""
        if os.path.lexists(self.stop_file):
            return False
        self._stopped.clear()
        return True

    def _kill(self, group: int) -> None:
        """Closing the lifeline makes the sandbox init kill its namespace; the group kill is a backstop."""
        lifeline = self._groups.pop(group, None)
        if lifeline is not None:
            os.close(lifeline)
        try:
            os.killpg(group, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    # ── Sandbox self-test ──────────────────────────────────────────────────
    def verify_sandbox(self) -> str:
        """Runs the probe child; any reachable network or socket, writable path, visible hidden path
        or top-level entry outside the allowlist fails closed."""
        if self._tools is None:
            self.sandbox = "UNAVAILABLE"
            return self.sandbox
        layout = self._layout()
        budget = {"cpu_seconds": 10, "wall_seconds": 30, "memory_bytes": 512 << 20, "output_bytes": 16_384}
        with tempfile.TemporaryDirectory(prefix="colony-probe-") as outside, \
                socket.socket(socket.AF_UNIX) as named, socket.socket(socket.AF_UNIX) as abstract:
            named.bind(os.path.join(outside, "probe.sock"))
            named.listen(1)
            abstract_name = "colony-probe-" + os.urandom(8).hex()
            abstract.bind("\0" + abstract_name)
            abstract.listen(1)
            payload = {
                "hidden": [item[2:] for item in layout if item[:2] in ("d:", "f:")],
                "write_targets": sorted({"/", "/dev", "/tmp", str(REPO), str(Path.home()), str(self.root),
                                         str(self.root.parent), sys.prefix, outside}),
                "existing_files": [str(CHILD), str(INIT)],
                "unix_sockets": [os.path.join(outside, "probe.sock"), "@" + abstract_name],
            }
            status, output, _ = self._spawn(_PROBE, {"task_id": "probe", "payload": payload}, budget)
        allowed = {"dev", "proc"} | {Path(item[2:].split(":")[0]).parts[1] for item in layout
                                     if item[:2] in ("b:", "l:")}
        checks = ("network_denied", "unix_sockets_denied", "writes_denied", "existing_files_read_only",
                  "hidden_empty", "capabilities_dropped", "environment_empty")
        verified = status == "EXITED_0" and type(output) is dict and set(output) == {*checks, "root_entries"} \
            and all(output[name] is True for name in checks) \
            and type(output["root_entries"]) is list and set(output["root_entries"]) <= allowed
        self.sandbox = "VERIFIED" if verified else "UNAVAILABLE"
        return self.sandbox

    def _layout(self) -> list[str]:
        """Root directives: what the child sees (read-only binds and links) and what is hidden in it."""
        sources = {Path("/usr"), REPO, *(Path(p).resolve() for p in {sys.prefix, sys.base_prefix,
                                                                      sys.exec_prefix, sys.base_exec_prefix})}
        sources.add(Path(os.path.realpath(self.python)).parent)
        layout: list[str] = []
        for name in ("bin", "sbin", "lib", "lib32", "lib64", "libx32"):
            host = Path("/") / name
            if host.is_symlink():
                layout.append(f"l:{host}:{os.readlink(host)}")
            elif host.is_dir():
                sources.add(host)
        binds: list[Path] = []
        for path in sorted(sources, key=lambda p: (len(p.parts), str(p))):
            if path.is_dir() and path != Path("/") and not any(path.is_relative_to(b) for b in binds):
                binds.append(path)
        layout += ["b:" + str(path) for path in binds]
        # The qualification criteria, golden answers and evidence are the evaluator's, never the individual's.
        hidden = [REPO / ".git", *sorted(REPO.glob(".env*")), REPO / "docs" / "colony_lab"]
        if any(self.root.is_relative_to(b) for b in binds):
            hidden.append(self.root)
        for path in hidden:
            if path.is_symlink():
                continue
            if path.is_dir():
                layout.append("d:" + str(path))
            elif path.is_file():
                layout.append("f:" + str(path))
        return layout

    # ── Admission (lab only, never the A1 registry) ────────────────────────
    def _home(self, agent_id: str) -> Path:
        if type(agent_id) is not str or not _HEX64.fullmatch(agent_id):
            raise LabError("INDIVIDUAL_UNKNOWN")
        return self.root / "individuals" / agent_id

    def load(self, agent_id: str, _depth: int = 0) -> tuple[dict, dict]:
        """Record and spec, re-verified from the founder down on every load."""
        if _depth > MAX_LINEAGE_DEPTH:
            raise LabError("INDIVIDUAL_INVALID")
        home = self._home(agent_id)
        if not home.is_dir():
            raise LabError("INDIVIDUAL_UNKNOWN")
        record, spec = _read_json(home / "record.json"), _read_json(home / "spec.json")
        try:
            if type(record) is dict and record.get("role") == "DESCENDANT":
                parent_id = record.get("lineage", {}).get("parent_agent_id")
                parent, parent_spec = self.load(parent_id, _depth + 1)
                verify_record(record, spec, parent, parent_spec)
                check_qualification(_read_json(home / "birth_qualification.json"), parent,
                                    also_excluded=frozenset({record["agent_id"]}))
            else:
                verify_record(record, spec)
        except (LineageError, AttributeError, KeyError, TypeError) as exc:
            raise LabError(getattr(exc, "code", "INDIVIDUAL_INVALID")) from None
        if record["agent_id"] != agent_id:
            raise LabError("INDIVIDUAL_INVALID")
        return record, spec

    def admit(self, record: dict, spec: dict, *, parent_qualification: Any = None) -> dict:
        """Founders are admitted on a valid record alone (no gate: the operator chooses them);
        descendants need their parent's qualification."""
        if type(record) is not dict or type(record.get("lineage")) is not dict:
            raise LabError("RECORD_SCHEMA_VIOLATION")
        if record.get("role") == "DESCENDANT":
            parent, parent_spec = self.load(record["lineage"]["parent_agent_id"])
            try:
                check_qualification(parent_qualification, parent,
                                    also_excluded=frozenset({record.get("agent_id")}))
                verify_record(record, spec, parent, parent_spec)
            except LineageError as exc:
                raise LabError(exc.code) from None
        else:
            try:
                verify_record(record, spec)
            except LineageError as exc:
                raise LabError(exc.code) from None
        home = self._home(record["agent_id"])
        (self.root / "individuals").mkdir(mode=0o700, exist_ok=True)
        try:
            home.mkdir(mode=0o700)
        except FileExistsError:
            raise LabError("ALREADY_ADMITTED") from None
        for name in ("tasks", "results", JOURNAL_DIR):
            (home / name).mkdir(mode=0o700)
        _write_new(home / "spec.json", _dump(spec))
        _write_new(home / "record.json", _dump(record))
        if parent_qualification is not None:
            _write_new(home / "birth_qualification.json", _dump(parent_qualification))
        _write_new(home / "usage.json", _dump({"runs": 0}))
        events = record["budget"]["journal_events"]
        ActivityStore.create(home / JOURNAL_DIR, journal_policy(record["agent_id"]),
                             ledger_id="fixture-colony-" + record["agent_id"][:16],
                             limits=Limits(max_events=events, per_producer=events))
        return {"status": "ADMITTED_TO_LAB", "agent_id": record["agent_id"], "registry": record["registry"]}

    # ── Runs ───────────────────────────────────────────────────────────────
    @contextmanager
    def _exclusive(self, home: Path):
        fd = os.open(home, os.O_RDONLY)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LabError("BUSY") from None
            yield
        finally:
            os.close(fd)

    def run(self, agent_id: str, task: Any) -> dict:
        try:
            home = self._home(agent_id)
            if not home.is_dir():
                raise LabError("INDIVIDUAL_UNKNOWN")
            with self._exclusive(home):
                return self._run(home, agent_id, task)
        except LabError as exc:
            return _outcome(exc.code if exc.code in {"BUSY", "INDIVIDUAL_UNKNOWN"} else "INDIVIDUAL_INVALID",
                            exc.code, agent_id)

    def _run(self, home: Path, agent_id: str, task: Any) -> dict:
        record, _ = self.load(agent_id)
        try:
            journal = ActivityStore(home / JOURNAL_DIR)
        except LedgerError as exc:
            return _outcome("JOURNAL_UNAVAILABLE", exc.code, agent_id)
        recorder = _Recorder(journal, agent_id)
        recovered = self._recover(home, recorder)
        try:
            raw = canonical_bytes(task, MAX_TASK_BYTES)
        except LedgerError as exc:
            return recorder.deny("task-" + hashlib.sha256(repr(task).encode()).hexdigest()[:32], None,
                                 "TASK_INVALID", exc.code)
        digest = hashlib.sha256(raw).hexdigest()
        code = _task_failure(task)
        if code is not None:
            return recorder.deny("task-" + digest[:32], None, "TASK_INVALID", code)
        task_id, mission = task["task_id"], task["mission_id"]
        marker = home / "tasks" / (task_id + ".json")
        if os.path.lexists(marker):
            previous = _read_json(marker)
            status = "DUPLICATE_TASK" if previous.get("task_sha256") == digest else "TASK_ID_CONFLICT"
            return _outcome(status, previous.get("status"), agent_id, task_id)
        _write_new(marker, _dump({"task_sha256": digest, "status": "STARTED"}))

        def finish(result: dict) -> dict:
            _replace(marker, _dump({"task_sha256": digest, "status": result["status"], "code": result["code"]}))
            if recovered:
                result["recovered_interrupted_runs"] = recovered
            return result

        if self.stopped:
            return finish(recorder.deny(task_id, mission, "STOPPED", "EXTERNAL_STOP"))
        if mission not in self.missions:
            return finish(recorder.deny(task_id, mission, "REFUSED", "MISSION_NOT_ADMITTED"))
        task_type = self.tasks.get(task["task_type"])
        if task_type is None:
            return finish(recorder.deny(task_id, mission, "REFUSED", "TASK_TYPE_UNKNOWN"))
        if task_type.capability not in record["lab_permissions"]:
            return finish(recorder.deny(task_id, mission, "REFUSED", "CAPABILITY_NOT_GRANTED"))
        budget = record["budget"]
        usage = _usage(home)
        if usage["runs"] >= budget["runs"]:
            return finish(recorder.exhausted(task_id, mission, "RUNS"))
        if len(journal.snapshot()[1]) + 2 > budget["journal_events"]:
            return finish(recorder.exhausted(task_id, mission, "JOURNAL_EVENTS"))
        if self.sandbox != "VERIFIED" and self.verify_sandbox() != "VERIFIED":
            return finish(recorder.deny(task_id, mission, "SANDBOX_UNAVAILABLE", "SANDBOX_UNAVAILABLE"))
        # The run is claimed, then charged, before it starts; a crash at any point never refunds it.
        _write_new(home / "inflight.json", _dump({"task_id": task_id, "mission_id": mission,
                                                  "runs_after": usage["runs"] + 1}))
        _replace(home / "usage.json", _dump({"runs": usage["runs"] + 1}))
        status, output, elapsed = self._spawn(task_type, task, budget)
        result = self._settle(home, recorder, task_id, mission, status, output, elapsed)
        (home / "inflight.json").unlink()
        return finish(result)

    def _recover(self, home: Path, recorder: "_Recorder") -> list[str]:
        """A run left in flight by a supervisor crash is recorded as interrupted, never as done."""
        inflight = home / "inflight.json"
        if not os.path.lexists(inflight):
            return []
        claim = _read_json(inflight)
        task_id, mission = claim["task_id"], claim["mission_id"]
        usage = _usage(home)
        runs_after = claim.get("runs_after")
        if type(runs_after) is not int:
            runs_after = usage["runs"] + 1  # unreadable claim: charge again rather than ever refund
        if usage["runs"] < runs_after:  # crashed between the claim and the charge
            _replace(home / "usage.json", _dump({"runs": runs_after}))
        recorder.record("interrupted-" + task_id, "RUN_INTERRUPTED", mission, "SUPERVISOR_CRASH",
                        f"Lab run {task_id} was interrupted before its outcome was recorded")
        marker = home / "tasks" / (task_id + ".json")
        previous = _read_json(marker)
        _replace(marker, _dump({"task_sha256": previous["task_sha256"], "status": "INTERRUPTED",
                                "code": "SUPERVISOR_CRASH"}))
        inflight.unlink()
        return [task_id]

    def _settle(self, home, recorder, task_id, mission, status, output, elapsed) -> dict:
        if status == "STOPPED":
            return recorder.interrupted(task_id, mission, "EXTERNAL_STOP")
        if status == "WALL_TIMEOUT":
            return recorder.interrupted(task_id, mission, "WALL_TIMEOUT")
        if status in {"OUTPUT_EXCEEDED", "CPU_EXCEEDED", "MEMORY_EXCEEDED"}:
            return recorder.exhausted(task_id, mission, status.split("_")[0])
        if status == "SANDBOX_FAILED":
            self.sandbox = "UNAVAILABLE"
            return recorder.deny(task_id, mission, "SANDBOX_UNAVAILABLE", "SANDBOX_SETUP_FAILED")
        if status != "EXITED_0" or type(output) is not dict:
            return recorder.interrupted(task_id, mission, "CHILD_FAILED")
        safe, redactions = _redacted(output)
        body = _dump({"agent_id": recorder.agent_id, "task_id": task_id, "mission_id": mission,
                      "claims_are_untrusted": True, "output": safe, "output_redactions": redactions,
                      "elapsed_s": round(elapsed, 3)})
        _write_new(home / "results" / (task_id + ".json"), body)
        result_hash = hashlib.sha256(body).hexdigest()
        result = recorder.completed(task_id, mission, result_hash)
        result.update(output=safe, output_redactions=redactions, result_sha256=result_hash)
        return result

    def _spawn(self, task_type: TaskType, task: dict, budget: dict) -> tuple[str, Any, float]:
        if self._tools is None:
            return "SANDBOX_FAILED", None, 0.0
        tools = self._tools
        lifeline_r, lifeline_w = os.pipe2(os.O_CLOEXEC)
        report_r, report_w = os.pipe2(os.O_CLOEXEC)
        child = [tools["setpriv"], "--no-new-privs", "--inh-caps=-all", "--ambient-caps=-all",
                 "--bounding-set=-all", tools["env"], "-i", self.python, "-I", "-B", str(CHILD), task_type.module]
        init = [self.python, "-I", "-S", "-B", str(INIT), str(lifeline_r), str(report_w),
                str(budget["cpu_seconds"]), str(budget["memory_bytes"]), str(MAX_PROCESSES), "--", *child]
        argv = [tools["unshare"], "--user", "--map-root-user", "--net", "--mount", "--pid", "--fork",
                "--kill-child=SIGKILL", "--propagation", "private", "/bin/sh", "-c", _SANDBOX_SCRIPT,
                "colony-sandbox", str(self.root), *self._layout(), "--", *init]

        def die_with_supervisor() -> None:
            # Second layer behind the lifeline: the sandbox also dies with the supervisor process.
            if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
                os._exit(SANDBOX_EXIT)

        payload = canonical_bytes({"task_id": task["task_id"], "payload": task["payload"]}, MAX_TASK_BYTES)
        started = time.monotonic()
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env={"PATH": _SYSTEM_PATH}, cwd="/", start_new_session=True,
                                    preexec_fn=die_with_supervisor, close_fds=True,
                                    pass_fds=(lifeline_r, report_w))
        finally:
            os.close(lifeline_r)
            os.close(report_w)
        with self._groups_lock:
            self._groups[proc.pid] = lifeline_w
        limit = budget["output_bytes"]
        chunks: list[bytes] = []
        overflow = threading.Event()

        def read_stdout() -> None:
            size = 0
            while True:
                chunk = proc.stdout.read1(65_536)
                if not chunk:
                    return
                size += len(chunk)
                if size > limit:
                    overflow.set()
                    return
                chunks.append(chunk)

        def drain_stderr() -> None:  # never stored: it may echo untrusted or secret content
            while proc.stderr.read1(65_536):
                pass

        readers = [threading.Thread(target=read_stdout, daemon=True),
                   threading.Thread(target=drain_stderr, daemon=True)]
        for reader in readers:
            reader.start()
        try:
            proc.stdin.write(payload)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        verdict = None
        while proc.poll() is None:
            if self.stopped:
                verdict = "STOPPED"
            elif overflow.is_set():
                verdict = "OUTPUT_EXCEEDED"
            elif time.monotonic() - started > budget["wall_seconds"]:
                verdict = "WALL_TIMEOUT"
            if verdict:
                self._kill(proc.pid)
                break
            time.sleep(POLL_S)
        proc.wait()
        with self._groups_lock:
            lifeline = self._groups.pop(proc.pid, None)
        if lifeline is not None:
            os.close(lifeline)
        with os.fdopen(report_r, "rb") as handle:
            report = handle.read(4096)
        for reader in readers:
            reader.join(5)
        elapsed = time.monotonic() - started
        if verdict is None and overflow.is_set():
            verdict = "OUTPUT_EXCEEDED"
        if verdict:
            return verdict, None, elapsed
        return _classify(report, chunks, task["task_id"], budget["cpu_seconds"]) + (elapsed,)


def _classify(report: bytes, chunks: list[bytes], task_id: str, cpu_budget: int) -> tuple[str, Any]:
    """Outcome from the init's status line; the child's own exit code only distinguishes 0, 70 and other."""
    try:
        status = _strict_json(report, "SANDBOX_FAILED")
    except LabError:
        return "SANDBOX_FAILED", None  # the root or the init never came up
    if type(status) is not dict or status.get("setup_failed") is not False:
        return "SANDBOX_FAILED", None
    cpu = status.get("cpu_s")
    if status.get("reason") == "CPU_EXCEEDED" or (
            status.get("signal") == signal.SIGXCPU and type(cpu) in (int, float) and cpu >= cpu_budget):
        return "CPU_EXCEEDED", None
    if status.get("reason") is not None or status.get("signal") is not None:
        return "EXITED_NONZERO", None
    if status.get("exit_code") == 70:
        return "MEMORY_EXCEEDED", None  # reported by the child launcher on MemoryError: a self-claim
    if status.get("exit_code") != 0:
        return "EXITED_NONZERO", None
    try:
        result = _strict_json(b"".join(chunks), "RESULT_INVALID")
    except LabError:
        return "RESULT_INVALID", None
    if type(result) is not dict or set(result) != {"result_schema", "task_id", "output"} or \
            result["result_schema"] != RESULT_SCHEMA or result["task_id"] != task_id:
        return "RESULT_INVALID", None
    return "EXITED_0", result["output"]


def _usage(home: Path) -> dict:
    """Run counter; not tamper-proof (whoever writes the lab root can reset it), but never misread."""
    usage = _read_json(home / "usage.json")
    if type(usage) is not dict or set(usage) != {"runs"} or type(usage["runs"]) is not int or usage["runs"] < 0:
        raise LabError("INDIVIDUAL_INVALID")
    return usage


def _task_failure(task: Any) -> str | None:
    if type(task) is not dict or set(task) != {"task_schema", "task_id", "mission_id", "task_type", "payload"}:
        return "TASK_SCHEMA_VIOLATION"
    if task["task_schema"] != TASK_SCHEMA or type(task["payload"]) is not dict or \
            type(task["task_type"]) is not str:
        return "TASK_SCHEMA_VIOLATION"
    if type(task["task_id"]) is not str or not _TASK_ID.fullmatch(task["task_id"]):
        return "TASK_ID_INVALID"
    if type(task["mission_id"]) is not str or not _MISSION_ID.fullmatch(task["mission_id"]):
        return "MISSION_ID_INVALID"
    return None


def _outcome(status: str, code: str | None, agent_id: Any, task_id: str | None = None,
             event_id: str | None = None) -> dict:
    return {"status": status, "code": code, "agent_id": agent_id, "task_id": task_id, "journal_event": event_id,
            "output": None}


class _Recorder:
    """Writes the individual's own journal: its memory, kept by the supervisor."""

    def __init__(self, journal: ActivityStore, agent_id: str) -> None:
        self.journal = journal
        self.agent_id = agent_id

    def record(self, event_id: str, event_type: str, mission: str | None, code: str, summary: str,
               refs: list[str] | None = None, producer: str = "fixture-supervisor") -> str | None:
        policy = journal_policy(self.agent_id)["producers"][producer]
        candidate = {
            "schema_version": SCHEMA_VERSION, "event_id": event_id, "occurred_at_utc": None,
            "actor_id": policy["actor_id"], "actor_kind": policy["actor_kind"], "actor_version": None,
            "event_type": event_type, "quest_id": None, "correlation_id": mission, "causation_event_id": None,
            "source_kind": "SIMULATED", "summary": summary, "reason_declared": None,
            "payload": {"cost": None, "code": code, "related_event_id": None},
            "evidence_refs": refs or [], "authorization_ref": None,
        }
        try:
            return self.journal.append(candidate, producer_id=producer)["event_id"]
        except LedgerError:
            return None

    def _result(self, status, code, task_id, event_id) -> dict:
        if event_id is None:
            return _outcome("JOURNAL_UNAVAILABLE", code, self.agent_id, task_id)
        return _outcome(status, code, self.agent_id, task_id, event_id)

    def deny(self, task_id, mission, status, code) -> dict:
        event = self.record("denied-" + task_id, "POLICY_DENIED", mission, code,
                            f"Lab run refused with {code}")
        return self._result(status if status != "TASK_INVALID" else "REFUSED", code, task_id, event)

    def exhausted(self, task_id, mission, code) -> dict:
        event = self.record("budget-" + task_id, "BUDGET_EXHAUSTED", mission, code,
                            f"Lab budget {code} exhausted for task {task_id}")
        return self._result("BUDGET_EXHAUSTED", code, task_id, event)

    def interrupted(self, task_id, mission, code) -> dict:
        event = self.record("interrupted-" + task_id, "RUN_INTERRUPTED", mission, code,
                            f"Lab run {task_id} interrupted with {code}")
        return self._result("STOPPED" if code == "EXTERNAL_STOP" else "INTERRUPTED", code, task_id, event)

    def completed(self, task_id, mission, result_hash) -> dict:
        event = self.record("result-" + task_id, "OBSERVATION_RECORDED", mission, "RUN_COMPLETED",
                            f"Lab run {task_id} returned an untrusted result",
                            ["fixture:colony-lab/result/" + result_hash], producer="fixture-individual")
        return self._result("COMPLETED", "RUN_COMPLETED", task_id, event)
