"""Acquisition owner for the separate physical-evidence diagnostic, never an action."""

import os
import hashlib
from contextlib import ExitStack
from dataclasses import replace

from . import formats as f
from . import observer as o
from . import physical_evidence as p
from .external_evidence import FAULT_LINE_BYTES, FAULT_MAX_LINES, HISTORY_LINE_BYTES, HISTORY_MAX_LINES
from .external_evidence import POLICY_MAX_BYTES
from .oplog import project_log


class _Capacity(o._Blocked):
    def __init__(self, name):
        super().__init__("SOURCE_LIMIT")
        self.limit_name = name


def _limit(condition, name):
    if not condition:
        raise _Capacity(name)


class _EvidenceAcquisition(o._Acquisition):
    def __init__(self, stack):
        super().__init__(stack)
        self.fds, self.directories, self.contents = {}, {}, {}
        self.metadata, self.inventories, self.absences = {}, {}, set()
        self.count, self.content_count = 0, 0

    def _fd(self, path, flags, *, parent=None):
        _limit(self.count < p.Limits().descriptors, "descriptors")
        fd = super()._fd(path, flags, parent=parent)
        self.count += 1
        return fd

    def file(self, parent, name, resource, limit, *, lock=False):
        try:
            return super().file(parent, name, resource, limit, lock=lock)
        except o._Blocked as exc:
            if str(exc) == "SOURCE_LIMIT" and resource.startswith("OPERATION_LOG:"):
                raise _Capacity("per_log_bytes" if limit == f.MAX_LOG else "log_bytes") from None
            raise

    def directory(self, root):
        if root not in self.directories:
            self.directories[root] = super().directory(root)
            self.stamp(self.directories[root], "BOUND_DIRECTORY:" + str(len(self.directories)))
        return self.directories[root]

    def stamp(self, fd, resource):
        v = os.fstat(fd)
        self.metadata[resource] = p.MetadataStamp(resource, v.st_dev, v.st_ino, v.st_mode,
            v.st_uid, v.st_nlink, v.st_size, v.st_mtime_ns, v.st_ctime_ns)

    def listing(self, fd, *, allowed=None, limit=None):
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                if limit is not None:
                    _limit(len(names) < limit, "home_entries" if allowed == _HOME_FILES | _HOME_DIRS else "journal_entries")
                if allowed is not None:
                    o._need(entry.name in allowed, "STORED_NAMESPACE_INVALID")
                names.append(entry.name)
        result = tuple(sorted(names))
        if fd in self.inventories:
            o._need(self.inventories[fd] == result, "SOURCE_CHANGED")
        else:
            self.inventories[fd] = result
        return result

    def optional_directory(self, parent, name, resource):
        key = parent, name
        if key in self.fds:
            return self.fds[key]
        try:
            fd = self._fd(name, os.O_RDONLY | os.O_DIRECTORY, parent=parent)
        except FileNotFoundError:
            self.absent(parent, name)
            self.fds[key] = None
            return None
        value = os.fstat(fd)
        self.private_directory(value)
        self.checks.append((fd, parent, name, o._identity(value)))
        self.fds[key] = fd
        self.stamp(fd, resource)
        return fd

    def absent(self, parent, name):
        self.listing(parent)
        self.absences.add((parent, name))

    def metadata_file(self, parent, name, resource):
        key = parent, name
        if key not in self.fds:
            fd, _ = self.file_descriptor(parent, name, 2**63 - 1)
            self.fds[key] = fd
            self.stamp(fd, resource)
        return os.fstat(self.fds[key])

    def selected(self, lab, path, limit):
        if path in self.contents:
            return self.contents[path]
        parent, resource = lab, "LAB"
        parts = path.split("/")
        for index, name in enumerate(parts[:-1]):
            next_resource = "/".join(parts[:index + 1])
            directory = self.optional_directory(parent, name, next_resource)
            if directory is None:
                self.contents[path] = (None, resource)
                return self.contents[path]
            parent, resource = directory, next_resource
        key = parent, parts[-1]
        remaining = min(limit, p.Limits().content_bytes - self.content_count)
        if key in self.fds:
            fd = self.fds[key]
            before = os.fstat(fd)
            _limit(before.st_size <= limit, "envelope_bytes" if limit == 16384 else "record_bytes")
            _limit(before.st_size <= remaining, "content_bytes")
        else:
            try:
                fd = self._fd(parts[-1], os.O_RDONLY, parent=parent)
            except FileNotFoundError:
                self.absent(parent, parts[-1])
                self.contents[path] = None, resource
                return self.contents[path]
            fd, before = self.checked_file_descriptor(fd, parent, parts[-1], 2**63 - 1)
            _limit(before.st_size <= limit, "envelope_bytes" if limit == 16384 else "record_bytes")
            _limit(before.st_size <= remaining, "content_bytes")
            self.fds[key] = fd
        chunks, count = [], 0
        while True:
            chunk = os.read(fd, min(65536, remaining + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            _limit(count <= remaining, "content_bytes" if remaining < limit else "envelope_bytes" if limit == 16384 else "record_bytes")
            chunks.append(chunk)
        raw = b"".join(chunks)
        o._need(o._identity(os.fstat(fd)) == o._identity(before), "SOURCE_CHANGED")
        self.stamps.append(o.SourceStamp(path, before.st_dev, before.st_ino, len(raw),
            before.st_mtime_ns, before.st_ctime_ns, hashlib.sha256(raw).hexdigest()))
        if raw is not None:
            self.content_count += len(raw)
        self.contents[path] = raw, resource
        return self.contents[path]

    def verify(self):
        for fd, names in tuple(self.inventories.items()):
            o._need(self.listing(fd) == names, "SOURCE_CHANGED")
        for parent, name in self.absences:
            try:
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise o._Blocked("SOURCE_CHANGED")
        super().verify()


_HOME_FILES = frozenset({"spec.json", "record.json", "birth_qualification.json", "usage.json",
                         "usage.json.tmp", "inflight.json"})
_HOME_DIRS = frozenset({"tasks", "results", "j01-lab-memory"})
_STORES = frozenset({"activity.sqlite3", "activity.sqlite3-wal", "activity.sqlite3-shm", "activity.sqlite3-journal"})


def _layout(source, roots, child):
    home_name = "individuals/" + child
    home = source.optional_directory(roots["individuals"], child, home_name)
    if home is None:
        return False, "ABSENT"
    names = source.listing(home, allowed=_HOME_FILES | _HOME_DIRS, limit=p.Limits().home_entries)
    directories, store = set(), False
    for name in names:
        resource = home_name + "/" + name
        if name in _HOME_FILES:
            source.metadata_file(home, name, resource)
        else:
            fd = source.optional_directory(home, name, resource)
            o._need(fd is not None, "SOURCE_CHANGED")
            directories.add(name)
            if name != "j01-lab-memory":
                continue
            entries = source.listing(fd, allowed=_STORES, limit=p.Limits().journal_entries)
            for leaf in entries:
                value = source.metadata_file(fd, leaf, resource + "/" + leaf)
                if leaf == "activity.sqlite3":
                    store = value.st_size > 0
    ready = _HOME_DIRS <= directories and store
    return True, "OBSERVED" if ready else "PARTIAL"


def _attempts(raw, whole):
    """Validated whole-file prefixes preserve original physical/reserve positions."""
    lines = raw.split(b"\n")
    for summary in whole.history:
        prefix = b"\n".join(lines[:summary.end_line]) + b"\n"
        projected = project_log(prefix)
        o._need(projected.operation_sha256 == summary.operation_sha256
                and projected.status not in ("CORRUPT", "TORN_TAIL", "EMPTY", "PREPARATION_INCOMPLETE"),
                "OPERATION_LOG_UNAVAILABLE")
        prepared = f.loads(lines[summary.start_line - 1])["data"]["operation"]
        yield prefix, projected, prepared


def _coverage(batch):
    total, legacy = batch["ledger_entries"], batch["legacy_entries"]
    matched = sum(row["operation_entries"] for row in batch["observations"])
    errors = []
    if legacy:
        errors.append("LEGACY_LEDGER_UNBOUND")
    if total != matched:
        errors.append("LEDGER_OPERATION_UNBOUND")
    conflict = any(row["status"] == "CONFLICT" for row in batch["observations"])
    if conflict:
        errors.append("LEDGER_UNAVAILABLE")
    status = "LEGACY_UNBOUND" if legacy else "UNBOUND" if total != matched or conflict else "MATCH"
    return p.LedgerCoverage(status, total, legacy, matched, total - matched), errors


def scan_evidence(config):
    """Return no provisional payload on acquisition, foundational or close failure."""
    try:
        return _scan(config)
    except o._Blocked as exc:
        code = str(exc)
        reached = (exc.limit_name,) if isinstance(exc, _Capacity) else ("operations",) if code == "HISTORY_OPERATION_LIMIT" else ("logs",) if code == "OPERATION_LOGS_FULL" else ()
        return p.PhysicalEvidence("BLOCKED", (code,), limits=replace(p.Limits(), reached=reached))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return p.PhysicalEvidence("BLOCKED", ("SOURCE_UNAVAILABLE",))


def _scan(config):
    with ExitStack() as stack:
        source = _EvidenceAcquisition(stack)
        lab = source.directory(config.lab_root)
        source.stamp(lab, "LAB")
        source.file(lab, "registrar.lock", "L1", 0, lock=True)
        faults = source.directory(config.fault_file.parent)
        fault_raw = source.file(faults, config.fault_file.name, "FAULT_LOG", FAULT_MAX_LINES * FAULT_LINE_BYTES)
        installed = source.directory(config.trust_directory)
        policy = source.file(installed, "policy.json", "TRUST_POLICY", POLICY_MAX_BYTES)
        history = source.file(installed, "trust-history.log", "TRUST_HISTORY", HISTORY_MAX_LINES * HISTORY_LINE_BYTES)
        external = o._external(config, fault_raw, policy, history)
        o._need(external[0].status in ("EMPTY", "STRUCTURAL_ONLY"), "FAULT_LOG_UNAVAILABLE")
        o._need(external[1].status == "STRUCTURAL_MATCH" and external[2] == "CURRENT_ROOT_VALIDATED",
                "TRUST_CURRENT_UNAVAILABLE")
        blockers = list(external[3])
        roots = {}
        for name in ("admission-ops", "registrar-admissions", "admission-envelopes", "individuals"):
            fd = source.optional_directory(lab, name, name)
            o._need(fd is not None, "SOURCE_UNAVAILABLE")
            roots[name] = fd
        names = o._names(roots["admission-ops"])
        attempts, seen, total, pending = [], set(), 0, set()
        for name in names:
            child = name[:-4]
            raw = source.file(roots["admission-ops"], name, "OPERATION_LOG:" + child,
                              min(f.MAX_LOG, o.MAX_SCAN_BYTES - total))
            total += len(raw)
            whole = project_log(raw)
            if whole.status in ("CORRUPT", "TORN_TAIL", "EMPTY", "PREPARATION_INCOMPLETE"):
                # Preserve external blockers in the error, without salvaging log prefixes.
                if "EXTERNAL_TERMINATION_NOT_EVALUATED" in blockers:
                    raise o._Blocked("EXTERNAL_TERMINATION_NOT_EVALUATED")
                raise o._Blocked("OPERATION_LOG_UNAVAILABLE")
            for prefix, log, op in _attempts(raw, whole):
                o._need(log.operation_sha256 not in seen, "DUPLICATE_OPERATION")
                o._need(op["lab_id"] == config.lab_id and op["child_agent_id"] == child,
                        "OPERATION_BINDING_MISMATCH")
                seen.add(log.operation_sha256)
                o._need(len(seen) <= p.Limits().operations, "HISTORY_OPERATION_LIMIT")
                _limit(len(op["items"]) <= p.Limits().item_references, "item_references")
                attempts.append((child, prefix, log, op, log.operation_sha256 == whole.operation_sha256))
            if whole.terminal_claim is None:
                pending.add(whole.operation_sha256)
        ledger_parent = source.directory(config.ledger.parent)
        batch = o._ledger(source, ledger_parent, config.ledger.name, tuple(sorted(seen)))
        rows = {row["operation_sha256"]: row for row in batch["observations"]}
        coverage, errors = _coverage(batch)
        blockers.extend(errors)
        if len(pending) > 1:
            blockers.append("OPERATION_PENDING")
        operations = []
        for child, raw, log, op, latest in attempts:
            ledger_row = rows[log.operation_sha256]
            _, _, errors = o._join(config, child, fault_raw, policy, history, raw, ledger_row, external=external)
            completed_d2 = log.last_completed_step in ("D2", "D3")
            envelope_available = False
            d2, d3, envelope = p.D2Fact("SUPERSEDED_NOT_EVALUATED"), p.D3Fact("SUPERSEDED_NOT_EVALUATED"), None
            try:
                p.frozen_material(op)
            except (f.FormatError, KeyError, TypeError, ValueError):
                errors.append("FROZEN_MATERIAL_INVALID")
                valid = False
            else:
                valid = True
            if latest and valid:
                material = {path: source.selected(lab, path, limit) for _, path, limit in p.d2_paths(op)}
                d2, decoded, extra = p.compare_d2(op, material, o.trust._envelope_shape)
                errors.extend(extra)
                admission_fact = next(x for x in d2.files if x.role == "admission_envelope")
                envelope_available = admission_fact.presence == "PRESENT"
                if envelope_available:
                    if admission_fact.comparison == "DIGEST_BINDING_MATCH":
                        envelope = decoded.get("admission_envelope")
                    else:
                        errors.append("LEDGER_ENVELOPE_MISMATCH")
                if completed_d2 and d2.material_state != "MATERIAL_MATCH":
                    errors.append("OPERATION_STATE_INCONSISTENT")
                home_present, layout = _layout(source, roots, child)
                files = ("spec.json", "record.json", "birth_qualification.json")
                if log.last_completed_step != "D3":
                    files += ("usage.json",)
                home_material = {f"individuals/{child}/{name}": source.selected(lab, f"individuals/{child}/{name}", 65536)
                                 for name in files}
                d3, extra = p.compare_d3(op, log, home_material, home_present, layout)
                errors.extend(extra)
            elif latest:
                d2, d3 = p.D2Fact(), p.D3Fact()
            d1, extra = p.compare_d1(op, log, ledger_row, envelope, latest=latest, completed_d2=completed_d2,
                                       envelope_available=envelope_available)
            errors.extend(extra)
            events = []
            for line in raw.split(b"\n"):
                try:
                    event = f.loads(line)
                except f.FormatError:
                    continue
                if event.get("operation_sha256") == log.operation_sha256:
                    events.append(event)
            if (external[0].termination_claims or any(e["event"] in
                ("QUARANTINE_BEGIN", "QUARANTINE_DONE", "SET_ASIDE_BEGIN", "SET_ASIDE_DONE", "TERMINATED") for e in events)):
                errors.append("ACTION_EVIDENCE_NOT_EVALUATED")
            operations.append(p.OperationEvidence(child, log.operation_sha256, log.attempt, latest,
                              log, d1, d2, d3, p.unique(errors)))
            blockers.extend(errors)
        o._need(o._names(roots["admission-ops"]) == names, "SOURCE_CHANGED")
        source.verify()
        result = p.PhysicalEvidence("BLOCKED" if blockers else "OBSERVED", p.unique(blockers), tuple(source.stamps),
            tuple(source.metadata[key] for key in sorted(source.metadata)),
            tuple(sorted(operations, key=lambda x: (x.child_agent_id, x.attempt))), tuple(sorted(pending)),
            f.canonical(batch), coverage)
    return result
