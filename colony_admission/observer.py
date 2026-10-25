"""Bounded, read-only evidence acquisition and operation-log inventory; never admission."""

import fcntl
import hashlib
import os
import stat
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from colony_trust import trust

from . import formats as f
from .external_evidence import FAULT_LINE_BYTES, FAULT_MAX_LINES, HISTORY_LINE_BYTES, HISTORY_MAX_LINES
from .external_evidence import POLICY_MAX_BYTES, project_fault_log, project_installed_trust
from .oplog import LogProjection, project_log


class _Blocked(Exception):
    pass


@dataclass(frozen=True)
class ObserverConfig:
    lab_root: Path
    ledger: Path
    trust_directory: Path
    fault_file: Path
    checkout_root: Path
    lab_id: str
    root_pin: str
    minimum_root_version: int


@dataclass(frozen=True)
class SourceStamp:
    resource: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    sha256: str


@dataclass(frozen=True)
class Observation:
    status: str
    blockers: tuple[str, ...]
    sources: tuple[SourceStamp, ...] = ()
    log: LogProjection | None = None
    root_status: str = "NOT_EVALUATED"
    ledger_bytes: bytes | None = None
    provenance: str = "NOT_EVALUATED"
    accepted: bool = field(default=False, init=False)
    authorization: str = field(default="NOT_EVALUATED", init=False)
    completeness: str = field(default="NOT_EVALUATED", init=False)
    durability: str = field(default="NOT_EVALUATED", init=False)
    rotation: str = field(default="NOT_EVALUATED", init=False)


@dataclass(frozen=True)
class ChildObservation:
    child_agent_id: str
    log: LogProjection
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class LabObservation:
    status: str
    blockers: tuple[str, ...]
    sources: tuple[SourceStamp, ...] = ()
    children: tuple[ChildObservation, ...] = ()
    pending_operations: tuple[str, ...] = ()
    ledger_bytes: bytes | None = None
    root_status: str = "NOT_EVALUATED"
    provenance: str = "NOT_EVALUATED"
    accepted: bool = field(default=False, init=False)
    authorization: str = field(default="NOT_EVALUATED", init=False)
    completeness: str = field(default="NOT_EVALUATED", init=False)
    durability: str = field(default="NOT_EVALUATED", init=False)
    rotation: str = field(default="NOT_EVALUATED", init=False)


MAX_SCAN_BYTES = 32 * 1024 * 1024


def _need(condition, code="SOURCE_UNAVAILABLE"):
    if not condition:
        raise _Blocked(code)


def _path(value):
    _need(isinstance(value, Path) and value.is_absolute(), "CONFIG_INVALID")
    _need(str(value) == os.path.normpath(str(value)) and ".." not in value.parts
          and value != Path("/"), "CONFIG_INVALID")
    return value


def _within(value, root):
    return value == root or root in value.parents


def _config(config):
    _need(type(config) is ObserverConfig, "CONFIG_INVALID")
    for name in ("lab_root", "ledger", "trust_directory", "fault_file", "checkout_root"):
        _path(getattr(config, name))
    f.require(f.hex64(config.root_pin))
    f.require(type(config.minimum_root_version) is int and config.minimum_root_version > 0)
    f.require(type(config.lab_id) is str and bool(f.NAME.fullmatch(config.lab_id)))
    roots = (config.lab_root, config.ledger.parent, config.trust_directory, config.fault_file.parent)
    for index, root in enumerate(roots):
        _need(not _within(root, config.checkout_root) and not _within(config.checkout_root, root),
              "CONFIG_OVERLAP")
        for other in roots[:index]:
            _need(not _within(root, other) and not _within(other, root), "CONFIG_OVERLAP")


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class _Acquisition:
    def __init__(self, stack):
        self.stack, self.checks, self.stamps = stack, [], []

    def _fd(self, path, flags, *, parent=None):
        fd = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
        self.stack.callback(os.close, fd)
        return fd

    def directory(self, root):
        current = self._fd("/", os.O_RDONLY | os.O_DIRECTORY)
        for index, part in enumerate(root.parts[1:]):
            parent = current
            current = self._fd(part, os.O_RDONLY | os.O_DIRECTORY, parent=parent)
            value = os.fstat(current)
            _need(stat.S_ISDIR(value.st_mode))
            self.checks.append((current, parent, part, _identity(value)))
            if index == len(root.parts) - 2:
                self.private_directory(value)
        return current

    @staticmethod
    def private_directory(value):
        _need(stat.S_ISDIR(value.st_mode) and stat.S_IMODE(value.st_mode) == 0o700
              and value.st_uid == os.geteuid(), "SOURCE_PERMISSIONS")

    def subdirectory(self, parent, name):
        fd = self._fd(name, os.O_RDONLY | os.O_DIRECTORY, parent=parent)
        value = os.fstat(fd)
        self.private_directory(value)
        self.checks.append((fd, parent, name, _identity(value)))
        return fd

    def file_descriptor(self, parent, name, limit, *, lock=False):
        fd = self._fd(name, os.O_RDONLY, parent=parent)
        before = os.fstat(fd)
        _need(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
              and before.st_nlink == 1 and before.st_uid == os.geteuid(), "SOURCE_PERMISSIONS")
        if lock:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise _Blocked("REGISTRAR_BUSY") from None
        _need(before.st_size <= limit, "SOURCE_LIMIT")
        self.checks.append((fd, parent, name, _identity(before)))
        return fd, before

    def file(self, parent, name, resource, limit, *, lock=False):
        fd, before = self.file_descriptor(parent, name, limit, lock=lock)
        chunks, count = [], 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - count))
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
            _need(count <= limit, "SOURCE_LIMIT")
        raw = b"".join(chunks)
        _need(_identity(before) == _identity(os.fstat(fd)), "SOURCE_CHANGED")
        self.stamps.append(SourceStamp(resource, before.st_dev, before.st_ino, len(raw),
                                       before.st_mtime_ns, before.st_ctime_ns, hashlib.sha256(raw).hexdigest()))
        return raw

    def verify(self):
        for fd, parent, name, expected in self.checks:
            _need(_identity(os.fstat(fd)) == expected, "SOURCE_CHANGED")
            _need(_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                  "SOURCE_CHANGED")


def _external(config, fault_raw, policy_raw, history_raw):
    faults = project_fault_log(fault_raw, config.lab_id)
    policy = project_installed_trust(policy_raw, history_raw, config.lab_id)
    blockers, root_status = [], "NOT_EVALUATED"
    if faults.status not in ("EMPTY", "STRUCTURAL_ONLY"):
        blockers.append("FAULT_LOG_UNAVAILABLE")
    elif faults.fault_claims:
        blockers.append("STICKY_FAULT")
    if faults.termination_claims:
        blockers.append("EXTERNAL_TERMINATION_NOT_EVALUATED")
    if policy.status != "STRUCTURAL_MATCH":
        blockers.append("TRUST_CURRENT_UNAVAILABLE")
    else:
        value = f.loads(policy.policy_bytes)
        try:
            _need(value["pin"] == config.root_pin, "TRUST_ROOT_PIN_MISMATCH")
            trust.check_root(value["root"], pin_sha256=config.root_pin,
                             minimum_version=max(config.minimum_root_version, value["minimum_version"]),
                             lab_id=config.lab_id)
            root_status = "CURRENT_ROOT_VALIDATED"
        except (trust.TrustError, _Blocked):
            blockers.append("TRUST_CURRENT_UNAVAILABLE")
    return faults, policy, root_status, tuple(blockers)


def _join(config, child, fault_raw, policy_raw, history_raw, log_raw, ledger, *, external=None):
    faults, policy, root_status, common = external or _external(config, fault_raw, policy_raw, history_raw)
    blockers = list(common)
    log = project_log(log_raw)
    if log.status in ("CORRUPT", "TORN_TAIL", "EMPTY", "PREPARATION_INCOMPLETE"):
        blockers.append("OPERATION_LOG_UNAVAILABLE")
        return log, root_status, blockers
    # Only canonical prepared/event bytes already accepted by the pure projection
    # participate in the join. ACK fragments remain lexical, not identity sources.
    events, prepared_seen = [], False
    for line in log_raw.splitlines():
        try:
            event = f.loads(line)
        except f.FormatError:
            continue
        prepared_seen = prepared_seen or event["event"] == "PREPARED"
        if prepared_seen and policy.status == "STRUCTURAL_MATCH":
            if (event["current_root_version"] > policy.root_version
                    or (event["current_root_version"] == policy.root_version
                        and event["current_root_sha256"] != policy.root_sha256)):
                blockers.append("OPERATION_ROOT_INCONSISTENT")
        if event["event"] == "PREPARED":
            old = event["data"]["operation"]
            if old["lab_id"] != config.lab_id or old["child_agent_id"] != child:
                blockers.append("OPERATION_BINDING_MISMATCH")
        if event.get("operation_sha256") == log.operation_sha256:
            events.append(event)
    prepared = next((e for e in events if e.get("event") == "PREPARED"), None)
    if prepared is None:
        blockers.append("OPERATION_BINDING_MISSING")
        return log, root_status, blockers
    operation = prepared["data"]["operation"]
    if operation["lab_id"] != config.lab_id or operation["child_agent_id"] != child:
        blockers.append("OPERATION_BINDING_MISMATCH")
    if policy.status == "STRUCTURAL_MATCH":
        if (operation["historical_root_version"] > policy.root_version
                or (operation["historical_root_version"] == policy.root_version
                    and operation["historical_root_sha256"] != policy.root_sha256)):
            blockers.append("OPERATION_ROOT_INCONSISTENT")
    known = {claim.entry_sha256: claim for claim in faults.fault_claims}
    phase = None
    for event in events:
        if event["event"] == "BEGIN":
            phase = event["step"]
        elif event["event"] in ("QUARANTINE_BEGIN", "SET_ASIDE_BEGIN"):
            phase = event["event"].removesuffix("_BEGIN")
        if event["event"] != "DURABILITY_FAULT":
            continue
        claim = known.get(event["data"]["fault_sha256"])
        if (claim is None or claim.operation_sha256 != log.operation_sha256
                or claim.child_agent_id != child or claim.attempt != log.attempt
                or claim.step != event["step"] or claim.phase != phase):
            blockers.append("FAULT_LINK_MISMATCH")
    if ledger["status"] not in ("NO_OPERATION_ENTRY", "OPERATION_ENTRY_PRESENT"):
        blockers.append("LEDGER_UNAVAILABLE")
    elif ledger["operation_sha256"] != log.operation_sha256:
        blockers.append("LEDGER_OPERATION_MISMATCH")
    elif ledger["status"] == "OPERATION_ENTRY_PRESENT":
        if ledger["entry"]["envelope_sha256"] != operation["presented"]["admission"]["envelope_sha256"]:
            blockers.append("LEDGER_ENVELOPE_MISMATCH")
        if log.terminal_claim in ("ABANDONED", "REFUSED"):
            blockers.append("OPERATION_STATE_INCONSISTENT")
        if (log.last_completed_step == "D0" and log.pending_step != "D1"
                and log.terminal_claim != "FAILED_CONSUMED"):
            blockers.append("OPERATION_STATE_INCONSISTENT")
    elif log.last_completed_step not in (None, "D0") or log.terminal_claim == "FAILED_CONSUMED":
        blockers.append("OPERATION_STATE_INCONSISTENT")
    return log, root_status, blockers


class FileObserver:
    """Operator-bound diagnostic reader. observe() accepts a child id only."""

    def __init__(self, config: ObserverConfig):
        _config(config)
        self._config = config

    def observe(self, child_agent_id: str) -> Observation:
        try:
            f.require(f.hex64(child_agent_id))
            return self._observe(child_agent_id)
        except _Blocked as exc:
            return Observation("BLOCKED", (str(exc),))
        except (OSError, ValueError, TypeError, f.FormatError):
            return Observation("BLOCKED", ("SOURCE_UNAVAILABLE",))

    def _observe(self, child):
        config = self._config
        with ExitStack() as stack:
            source = _Acquisition(stack)
            lab = source.directory(config.lab_root)
            source.file(lab, "registrar.lock", "L1", 0, lock=True)
            faults = source.directory(config.fault_file.parent)
            fault_raw = source.file(faults, config.fault_file.name, "FAULT_LOG", FAULT_MAX_LINES * FAULT_LINE_BYTES)
            installed = source.directory(config.trust_directory)
            policy = source.file(installed, "policy.json", "TRUST_POLICY", POLICY_MAX_BYTES)
            history = source.file(installed, "trust-history.log", "TRUST_HISTORY",
                                  HISTORY_MAX_LINES * HISTORY_LINE_BYTES)
            operations = source.subdirectory(lab, "admission-ops")
            log_raw = source.file(operations, child + ".log", "OPERATION_LOG", f.MAX_LOG)
            log = project_log(log_raw)
            _need(log.operation_sha256 is not None, "OPERATION_LOG_UNAVAILABLE")
            ledger_parent = source.directory(config.ledger.parent)
            batch = _ledger(source, ledger_parent, config.ledger.name, (log.operation_sha256,))
            ledger = batch["observations"][0]
            result_log, root_status, blockers = _join(config, child, fault_raw, policy, history, log_raw, ledger)
            source.verify()
            result = Observation("BLOCKED" if blockers else "OBSERVED", tuple(dict.fromkeys(blockers)),
                                 tuple(source.stamps), result_log, root_status, f.canonical(ledger),
                                 "BOUND_FILES_OBSERVED")
        # A close error propagates through observe and discards the provisional payload.
        return result

    def scan(self) -> LabObservation:
        """Acquire the entire bounded operation-log directory; no resume/action."""
        try:
            return self._scan()
        except _Blocked as exc:
            return LabObservation("BLOCKED", (str(exc),))
        except (OSError, ValueError, TypeError, f.FormatError):
            return LabObservation("BLOCKED", ("SOURCE_UNAVAILABLE",))

    def _scan(self):
        config = self._config
        with ExitStack() as stack:
            source = _Acquisition(stack)
            lab = source.directory(config.lab_root)
            source.file(lab, "registrar.lock", "L1", 0, lock=True)
            faults = source.directory(config.fault_file.parent)
            fault_raw = source.file(faults, config.fault_file.name, "FAULT_LOG", FAULT_MAX_LINES * FAULT_LINE_BYTES)
            installed = source.directory(config.trust_directory)
            policy = source.file(installed, "policy.json", "TRUST_POLICY", POLICY_MAX_BYTES)
            history = source.file(installed, "trust-history.log", "TRUST_HISTORY",
                                  HISTORY_MAX_LINES * HISTORY_LINE_BYTES)
            external = _external(config, fault_raw, policy, history)
            operations = source.subdirectory(lab, "admission-ops")
            names = _names(operations)
            logs, total, operations_seen = [], 0, set()
            blockers = list(external[3])
            for name in names:
                raw = source.file(operations, name, "OPERATION_LOG:" + name[:-4],
                                  min(f.MAX_LOG, MAX_SCAN_BYTES - total))
                total += len(raw)
                log = project_log(raw)
                if log.operation_sha256 is not None:
                    if log.operation_sha256 in operations_seen:
                        blockers.append("DUPLICATE_OPERATION")
                    operations_seen.add(log.operation_sha256)
                logs.append((name[:-4], raw, log))
            ledger_parent = source.directory(config.ledger.parent)
            batch = _ledger(source, ledger_parent, config.ledger.name, tuple(sorted(operations_seen)))
            rows = {row["operation_sha256"]: row for row in batch["observations"]}
            children, pending = [], set()
            for child, raw, log in logs:
                if log.operation_sha256 is None:
                    errors = ["OPERATION_LOG_UNAVAILABLE"]
                else:
                    _, _, errors = _join(config, child, fault_raw, policy, history, raw,
                                          rows[log.operation_sha256], external=external)
                    if log.terminal_claim is None:
                        pending.add(log.operation_sha256)
                children.append(ChildObservation(child, log, tuple(dict.fromkeys(errors))))
                blockers.extend(errors)
            if len(pending) > 1:
                blockers.append("OPERATION_PENDING")
            if not logs and batch["legacy_entries"]:
                blockers.append("LEGACY_LEDGER_UNBOUND")
            _need(_names(operations) == names, "SOURCE_CHANGED")
            source.verify()
            result = LabObservation("BLOCKED" if blockers else "OBSERVED", tuple(dict.fromkeys(blockers)),
                                    tuple(source.stamps), tuple(children), tuple(sorted(pending)),
                                    f.canonical(batch), external[2], "BOUND_FILES_OBSERVED")
        return result


def _ledger(source, parent, name, operations):
    fd, before = source.file_descriptor(parent, name, trust.INSPECTION_MAX_BYTES)
    batch = trust.inspect_operations_fd(fd, operations)
    _need(batch["status"] == "OBSERVED", batch["status"])
    source.stamps.append(SourceStamp("LEDGER", before.st_dev, before.st_ino, before.st_size,
                                    before.st_mtime_ns, before.st_ctime_ns, batch["ledger_sha256"]))
    return batch


def _names(directory):
    names = []
    with os.scandir(directory) as entries:
        for entry in entries:
            _need(len(names) < 256, "OPERATION_LOGS_FULL")
            name = entry.name
            _need(name.endswith(".log") and f.hex64(name[:-4]), "OPERATION_NAMESPACE_INVALID")
            names.append(name)
    return tuple(sorted(names))
