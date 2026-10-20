"""Colony lab supervisor: admits lab individuals and runs one task at a time in a sandbox.

LAB_ONLY. Nothing here reaches the VPS, the Advisor, an exchange or a secret
value, and nothing here is an A1 registration.

Sandbox (Linux, unprivileged), all of it required or the run is refused:

* user, network, mount and pid namespaces (``unshare``): no network interface,
  no visible outside process, killed with its parent (``--kill-child``);
* the whole filesystem remounted read-only; the lab root, ``/mnt``, ``/run``,
  ``/dev/shm``, the repository's ``.git`` and ``.env*`` and the home dotfiles
  hidden under empty read-only mounts;
* every capability dropped and ``no_new_privs`` set (``setpriv``), so the
  child cannot undo those mounts; empty environment;
* rlimits on CPU, address space, file size (0) and descriptors; a new
  session killed as a group on wall timeout, output overflow or stop.

Not proven by this module: reads of files outside the hidden list remain
possible, and the child runs under the operator's UNIX account. Those need a
distinct account and an allowlisted root, which is a separate gate.
"""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
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
POLL_S = 0.02
SANDBOX_EXIT = 97
_SYSTEM_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TASK_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_MISSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")
_HOME_SECRETS = (".ssh", ".aws", ".azure", ".config", ".gnupg", ".docker", ".kube", ".netrc",
                 ".git-credentials", ".pypirc", ".npmrc", ".ccr")
# Runs as the namespace's init (which the child cannot signal), drops every capability for
# the child and reports its exit status (128 + signal when it was killed).
_SANDBOX_SCRIPT = r"""
set -u
mount_bin=$1; setpriv_bin=$2; env_bin=$3; py=$4; child=$5; module=$6; shift 6
for target in "$@"; do
  case "$target" in
    d:*) "$mount_bin" -t tmpfs -o ro,size=4k,nosuid,nodev,noexec colony-hidden "${target#d:}" || exit 97 ;;
    f:*) "$mount_bin" --bind -o ro /dev/null "${target#f:}" || exit 97 ;;
    *) exit 97 ;;
  esac
done
"$mount_bin" -o remount,bind,ro / || exit 97
cd / || exit 97
"$setpriv_bin" --no-new-privs --inh-caps=-all --ambient-caps=-all --bounding-set=-all \
  "$env_bin" -i "$py" -I -B "$child" "$module"
exit $?
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
        self._groups: set[int] = set()
        self._groups_lock = threading.Lock()
        tools = {name: shutil.which(name, path=_SYSTEM_PATH) for name in ("unshare", "mount", "setpriv", "env")}
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

    @staticmethod
    def _kill(group: int) -> None:
        try:
            os.killpg(group, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    # ── Sandbox self-test ──────────────────────────────────────────────────
    def verify_sandbox(self) -> str:
        """Runs the probe child; any reachable network, writable path or visible hidden path fails closed."""
        if self._tools is None:
            self.sandbox = "UNAVAILABLE"
            return self.sandbox
        hidden = [target[2:] for target in self._hidden()]
        budget = {"cpu_seconds": 10, "wall_seconds": 30, "memory_bytes": 512 << 20, "output_bytes": 4096}
        payload = {"hidden": hidden, "write_targets": ["/", "/tmp", str(REPO), str(Path.home()),
                                                       str(self.root.parent)]}
        status, output, _ = self._spawn(_PROBE, {"task_id": "probe", "payload": payload}, budget)
        expected = {"network_denied": True, "writes_denied": True, "hidden_empty": True,
                    "capabilities_dropped": True, "environment_empty": True}
        self.sandbox = "VERIFIED" if status == "EXITED_0" and output == expected else "UNAVAILABLE"
        return self.sandbox

    def _hidden(self) -> list[str]:
        targets = ["d:" + str(self.root)]
        for path in (Path("/mnt"), Path("/run"), Path("/dev/shm"), Path("/media"), REPO / ".git"):
            if path.is_dir() and not path.is_symlink():
                targets.append("d:" + str(path))
            elif path.is_file():
                targets.append("f:" + str(path))
        candidates = sorted(REPO.glob(".env*")) + [Path.home() / name for name in _HOME_SECRETS]
        for path in candidates:
            if path.is_symlink():
                continue
            if path.is_dir():
                targets.append("d:" + str(path))
            elif path.is_file():
                targets.append("f:" + str(path))
        return targets

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
            else:
                verify_record(record, spec)
        except (LineageError, AttributeError) as exc:
            raise LabError(getattr(exc, "code", "INDIVIDUAL_INVALID")) from None
        if record["agent_id"] != agent_id:
            raise LabError("INDIVIDUAL_INVALID")
        return record, spec

    def admit(self, record: dict, spec: dict, *, parent_qualification: Any = None) -> dict:
        if record.get("role") == "DESCENDANT":
            parent, parent_spec = self.load(record["lineage"]["parent_agent_id"])
            try:
                check_qualification(parent_qualification, parent)
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
        usage = _read_json(home / "usage.json")
        if usage["runs"] >= budget["runs"]:
            return finish(recorder.exhausted(task_id, mission, "RUNS"))
        if len(journal.snapshot()[1]) + 2 > budget["journal_events"]:
            return finish(recorder.exhausted(task_id, mission, "JOURNAL_EVENTS"))
        if self.sandbox != "VERIFIED" and self.verify_sandbox() != "VERIFIED":
            return finish(recorder.deny(task_id, mission, "SANDBOX_UNAVAILABLE", "SANDBOX_UNAVAILABLE"))
        # The run is charged before it starts; a crash never refunds it.
        _replace(home / "usage.json", _dump({"runs": usage["runs"] + 1}))
        _write_new(home / "inflight.json", _dump({"task_id": task_id, "mission_id": mission}))
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
        argv = [tools["unshare"], "--user", "--map-root-user", "--net", "--mount", "--pid", "--fork",
                "--kill-child=SIGKILL", "--propagation", "private", "--mount-proc", "/bin/sh", "-c",
                _SANDBOX_SCRIPT, "colony-sandbox", tools["mount"], tools["setpriv"], tools["env"],
                self.python, str(CHILD), task_type.module, *self._hidden()]
        cpu, memory = budget["cpu_seconds"], budget["memory_bytes"]

        def limits() -> None:
            # The sandbox dies with the supervisor (PR_SET_PDEATHSIG), even after a SIGKILL of it.
            if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
                os._exit(SANDBOX_EXIT)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        payload = canonical_bytes({"task_id": task["task_id"], "payload": task["payload"]}, MAX_TASK_BYTES)
        started = time.monotonic()
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env={"PATH": _SYSTEM_PATH}, cwd="/", start_new_session=True,
                                preexec_fn=limits, close_fds=True)
        with self._groups_lock:
            self._groups.add(proc.pid)
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
        code = proc.wait()
        with self._groups_lock:
            self._groups.discard(proc.pid)
        for reader in readers:
            reader.join(5)
        elapsed = time.monotonic() - started
        if verdict is None and overflow.is_set():
            verdict = "OUTPUT_EXCEEDED"
        if verdict:
            return verdict, None, elapsed
        if code in (128 + signal.SIGXCPU, 128 + signal.SIGKILL):
            return "CPU_EXCEEDED", None, elapsed
        if code == 70:
            return "MEMORY_EXCEEDED", None, elapsed
        if code == SANDBOX_EXIT:
            return "SANDBOX_FAILED", None, elapsed
        if code != 0:
            return "EXITED_NONZERO", None, elapsed
        try:
            result = _strict_json(b"".join(chunks), "RESULT_INVALID")
        except LabError:
            return "RESULT_INVALID", None, elapsed
        if type(result) is not dict or set(result) != {"result_schema", "task_id", "output"} or \
                result["result_schema"] != RESULT_SCHEMA or result["task_id"] != task["task_id"]:
            return "RESULT_INVALID", None, elapsed
        return "EXITED_0", result["output"], elapsed


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
