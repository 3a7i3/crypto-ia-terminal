"""Private, bounded checkout reader sharing the enclosing acquisition lifetime.

No code in the submitted checkout is imported. All returned bytes remain
provisional until both this inventory and the shared FD checks/closes succeed.
"""

import hashlib
import os
import stat

from . import observer as o
from . import _attestation_statement as s
from .evidence_observer import _limit

PER_FILE_BYTES = 16 * 1024 * 1024
CHECKOUT_BYTES = 32 * 1024 * 1024
CHECKOUT_FILES = 4096
CHECKOUT_ENTRIES = 8192
SUBJECT_ROOTS = (
    "colony_lab/__init__.py", "colony_lab/workers/__init__.py",
    "colony_lab/workers/sentinel.py", "governance_tower",
    "observability/__init__.py", "observability/event_center_contract.py",
    "observability/runtime_service_contract.py", "observability/storage_contract.py",
)
EVALUATOR_ROOTS = ("colony_lab", "sentinel_activity")


class Checkout:
    """One cache/inventory over a checkout; descriptors belong to ``source``."""

    def __init__(self, source, root):
        o._path(root)
        self.source = source
        self.directories, self.files, self.contents = {}, {}, {}
        self.inventories, self.absences = {}, set()
        self.entry_keys, self.file_keys = set(), set()
        self.content_count = 0
        current = source._fd("/", os.O_RDONLY | os.O_DIRECTORY)
        for index, name in enumerate(root.parts[1:]):
            parent = current
            current = source._fd(name, os.O_RDONLY | os.O_DIRECTORY, parent=parent)
            value = os.fstat(current)
            o._need(stat.S_ISDIR(value.st_mode), "SOURCE_UNAVAILABLE")
            source.checks.append((current, parent, name, o._identity(value)))
            if index == len(root.parts) - 2:
                self._permissions(value, directory=True)
        self.root = current
        self.directories[""] = current
        self._entry("", "")
        source.stamp(current, "CHECKOUT:.")

    @staticmethod
    def _permissions(value, *, directory=False):
        valid_type = stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode)
        o._need(valid_type and value.st_uid == os.geteuid() and not value.st_mode & 0o022
                and (directory or value.st_nlink == 1), "SOURCE_PERMISSIONS")
        o._need(bool(value.st_mode & stat.S_IRUSR)
                and (not directory or bool(value.st_mode & stat.S_IXUSR)), "SOURCE_UNAVAILABLE")

    def _entry(self, directory, name):
        key = directory, name
        if key not in self.entry_keys:
            _limit(len(self.entry_keys) < CHECKOUT_ENTRIES, "checkout_entries")
            self.entry_keys.add(key)

    def _listing(self, path, fd):
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                self._entry(path, entry.name)
                names.append(entry.name)
        result = tuple(sorted(names))
        if path in self.inventories:
            o._need(result == self.inventories[path], "SOURCE_CHANGED")
        else:
            self.inventories[path] = result
        return result

    def _absent(self, parent_path, parent, name):
        self._listing(parent_path, parent)
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            self.absences.add((parent, name))
            return
        raise o._Blocked("SOURCE_CHANGED")

    @staticmethod
    def _path(path):
        o._need(s.safe_path(path), "SOURCE_PATH_FORBIDDEN")

    def _directory(self, path):
        if path in self.directories:
            return self.directories[path]
        self._path(path)
        parts = path.split("/")
        parent_path = "/".join(parts[:-1])
        parent = self._directory(parent_path)
        if parent is None:
            self.directories[path] = None
            return None
        self._listing(parent_path, parent)
        try:
            fd = self.source._fd(parts[-1], os.O_RDONLY | os.O_DIRECTORY, parent=parent)
        except FileNotFoundError:
            self._absent(parent_path, parent, parts[-1])
            self.directories[path] = None
            return None
        value = os.fstat(fd)
        self._permissions(value, directory=True)
        self.source.checks.append((fd, parent, parts[-1], o._identity(value)))
        self.source.stamp(fd, "CHECKOUT:" + path)
        self.directories[path] = fd
        return fd

    def _file(self, path):
        if path in self.files:
            return self.files[path]
        self._path(path)
        parts = path.split("/")
        parent_path = "/".join(parts[:-1])
        parent = self._directory(parent_path)
        if parent is None:
            self.files[path] = None
            return None
        self._listing(parent_path, parent)
        try:
            fd = self.source._fd(parts[-1], os.O_RDONLY, parent=parent)
        except FileNotFoundError:
            self._absent(parent_path, parent, parts[-1])
            self.files[path] = None
            return None
        value = os.fstat(fd)
        self._permissions(value)
        _limit(len(self.file_keys) < CHECKOUT_FILES, "checkout_files")
        self.file_keys.add(path)
        self.source.checks.append((fd, parent, parts[-1], o._identity(value)))
        self.source.stamp(fd, "CHECKOUT:" + path)
        self.files[path] = fd, value
        return fd, value

    def selected(self, path, limit=PER_FILE_BYTES):
        """Acquire once; None denotes a stable absence beneath an acquired parent."""
        self._path(path)
        _limit(type(limit) is int and 0 <= limit <= PER_FILE_BYTES, "checkout_file_bytes")
        if path in self.contents:
            raw = self.contents[path]
            _limit(raw is None or len(raw) <= limit, "checkout_file_bytes")
            return raw
        acquired = self._file(path)
        if acquired is None:
            self.contents[path] = None
            return None
        fd, before = acquired
        _limit(before.st_size <= limit, "checkout_file_bytes")
        remaining = CHECKOUT_BYTES - self.content_count
        _limit(before.st_size <= remaining, "checkout_bytes")
        cap = min(limit, remaining)
        chunks, count = [], 0
        while True:
            chunk = os.read(fd, min(65536, cap + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            _limit(count <= cap, "checkout_file_bytes" if cap == limit else "checkout_bytes")
            chunks.append(chunk)
        raw = b"".join(chunks)
        o._need(o._identity(before) == o._identity(os.fstat(fd)), "SOURCE_CHANGED")
        self.content_count += len(raw)
        self.contents[path] = raw
        self.source.stamps.append(o.SourceStamp("CHECKOUT:" + path, before.st_dev, before.st_ino,
            len(raw), before.st_mtime_ns, before.st_ctime_ns, hashlib.sha256(raw).hexdigest()))
        return raw

    def _closure(self, roots):
        files, todo = set(), list(roots)
        while todo:
            path = todo.pop()
            self._path(path)
            parts = path.split("/")
            parent = self._directory("/".join(parts[:-1]))
            o._need(parent is not None, "SCIENTIFIC_SOURCE_UNAVAILABLE")
            try:
                value = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                # A stat failure cannot establish a stable absence observation.
                raise o._Blocked("SCIENTIFIC_SOURCE_UNAVAILABLE") from None
            if stat.S_ISDIR(value.st_mode):
                fd = self._directory(path)
                o._need(fd is not None, "SOURCE_CHANGED")
                names = self._listing(path, fd)
                if parts[-1] == "__pycache__":
                    for name in names:
                        leaf = path + "/" + name
                        self._path(leaf)
                        cached = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        o._need(stat.S_ISREG(cached.st_mode) and name.endswith(".pyc"), "SOURCE_CODE_IRREGULAR")
                        self._file(leaf)  # retain FD/metadata; never read cached content
                else:
                    todo.extend(path + "/" + name for name in names)
            elif stat.S_ISREG(value.st_mode):
                o._need(self.selected(path) is not None, "SOURCE_CHANGED")
                files.add(path)
            else:
                raise o._Blocked("SOURCE_CODE_IRREGULAR")
        return files

    def science(self, include_history=False):
        """Acquire only the closed R8/C9 profile and its complete code closures."""
        paths = (s.CRITERIA_PATH, s.EVIDENCE_PATH) + ((s.HISTORY_PATH,) if include_history else ())
        artifacts = {path: self.selected(path) for path in paths}
        o._need(all(raw is not None for raw in artifacts.values()), "SCIENTIFIC_SOURCE_UNAVAILABLE")
        subject = self._closure(SUBJECT_ROOTS)
        evaluator = self._closure(EVALUATOR_ROOTS) - subject
        subject_digest = s.code_digest(tuple((path, self.contents[path]) for path in sorted(subject)))
        evaluator_digest = s.code_digest(tuple((path, self.contents[path]) for path in sorted(evaluator)))
        return artifacts, subject_digest, evaluator_digest

    def verify(self):
        for path, expected in tuple(self.inventories.items()):
            o._need(self._listing(path, self.directories[path]) == expected, "SOURCE_CHANGED")
        for parent, name in self.absences:
            try:
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise o._Blocked("SOURCE_CHANGED")
