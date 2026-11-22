"""Lecteur borné : seul point d'entrée/sortie du pilote.

Toute lecture passe ici ; chaque fichier lu est inventorié (chemin, octets,
sha256). Un chemin hors périmètre, un lien symbolique ou un nom de secret n'est
jamais ouvert : il est consigné comme refus. Aucune écriture n'existe.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from agent_bench.observation.contract import is_secret_like, path_violation


class BudgetExceeded(RuntimeError):
    pass


class ScopedReader:
    def __init__(self, root, read_paths, *, max_files, max_bytes):
        self.root = Path(root).resolve()
        self.read_paths = tuple(read_paths)
        self.max_files = max_files
        self.max_bytes = max_bytes
        self.consulted = {}        # rel -> {"bytes", "sha256"}
        self.refused = {}          # rel -> code
        self.bytes_read = 0
        self._cache = {}

    def in_scope(self, rel):
        if path_violation(rel):
            return False
        return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in self.read_paths)

    def _refuse(self, rel, code):
        self.refused.setdefault(rel, code)

    def list_files(self):
        """Fichiers réguliers du périmètre, triés. Ne suit aucun lien ; n'ouvre rien."""
        out = set()
        for p in self.read_paths:
            target = self.root / p
            if p.endswith("/"):
                if not target.is_dir() or target.is_symlink():
                    continue
                for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
                    dirnames[:] = sorted(d for d in dirnames if d not in ("__pycache__", "node_modules"))
                    for name in filenames:
                        rel = (Path(dirpath) / name).relative_to(self.root).as_posix()
                        if is_secret_like(rel):
                            self._refuse(rel, "SKIPPED_SECRET_PATTERN")
                        elif (Path(dirpath) / name).is_symlink():
                            self._refuse(rel, "SKIPPED_SYMLINK")
                        else:
                            out.add(rel)
            elif target.is_file() and not target.is_symlink():
                out.add(p)
        return sorted(out)

    def read(self, rel):
        """Octets du fichier, ou None (refus consigné)."""
        if not self.in_scope(rel):
            return self._refuse(rel, "OUT_OF_SCOPE_NOT_READ")
        if is_secret_like(rel):
            return self._refuse(rel, "SKIPPED_SECRET_PATTERN")
        if rel in self.consulted:
            return self._cache[rel]
        if len(self.consulted) >= self.max_files:
            raise BudgetExceeded("max_files")
        path = self.root / rel
        if any(q.is_symlink() for q in (path, *path.parents) if self.root in (q, *q.parents)):
            return self._refuse(rel, "SKIPPED_SYMLINK")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return self._refuse(rel, "MISSING")
        with os.fdopen(fd, "rb") as fh:
            if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                return self._refuse(rel, "NOT_REGULAR_FILE")
            data = fh.read(self.max_bytes - self.bytes_read + 1)
        self.bytes_read += len(data)
        if self.bytes_read > self.max_bytes:
            raise BudgetExceeded("max_bytes")
        self.consulted[rel] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        self._cache[rel] = data
        return data

    def stat_mtime_ms(self, rel):
        """mtime du fichier (fait du système de fichiers, jamais une preuve de fraîcheur)."""
        if not self.in_scope(rel):
            return None
        st = os.stat(self.root / rel, follow_symlinks=False)
        return st.st_mtime_ns // 1_000_000

    def inventory(self):
        return [{"path": k, **v} for k, v in sorted(self.consulted.items())]

    def refusals(self):
        return [{"path": k, "code": v} for k, v in sorted(self.refused.items())]
