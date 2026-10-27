"""Private 3C inventory building blocks; no scan or positive public API.

The future scan owner must hold L1, acquire trust/logs and one ledger snapshot,
then revalidate and successfully close this context before exposing any facts.
This module alone establishes neither a population nor snapshot completeness.
"""

import os
import re

from . import _attestation_core as c
from . import evidence_observer as e
from . import formats as f
from . import observer as o
from ._population_core import HomeInput

_TASK = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}", re.ASCII)


class InventorySource(e._EvidenceAcquisition):
    """One shared FD/content/metadata owner with a cumulative private entry cap.

No ledger, lock, trust or log acquisition is initiated here. An owning scan must
use this instance for all phases, not give each home its own resource budget.
"""

    def __init__(self, stack):
        super().__init__(stack)
        self.private_entries = set()

    def _entry(self, parent, name):
        key = parent, name
        if key not in self.private_entries:
            e._limit(len(self.private_entries) < 8192, "private_entries")
            self.private_entries.add(key)

    def directory(self, root):
        fd = super().directory(root)
        self._entry(fd, "")
        return fd

    def optional_directory(self, parent, name, resource):
        fd = super().optional_directory(parent, name, resource)
        if fd is not None:
            self._entry(parent, name)
        return fd

    def metadata_file(self, parent, name, resource):
        value = super().metadata_file(parent, name, resource)
        self._entry(parent, name)
        return value

    def listing(self, fd, *, allowed=None, limit=None):
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                self._entry(fd, entry.name)
                if limit is not None:
                    e._limit(len(names) < limit, "homes" if limit == 65 else "private_entries")
                if allowed is not None:
                    o._need(entry.name in allowed, "SOURCE_NAMESPACE_INVALID")
                names.append(entry.name)
        result = tuple(sorted(names))
        if fd in self.inventories:
            o._need(result == self.inventories[fd], "SOURCE_CHANGED")
        else:
            self.inventories[fd] = result
        return result


def _leaf_allowed(name, directory):
    suffixes = (".json.tmp", ".json") if directory == "tasks" else (".json",)
    return any(name.endswith(suffix) and _TASK.fullmatch(name[:-len(suffix)])
               for suffix in suffixes)


def layout(source, parent, name, resource):
    """Observe the closed home layout, keeping opaque payloads unread."""
    home = source.optional_directory(parent, name, resource)
    o._need(home is not None, "SOURCE_CHANGED")
    names = source.listing(home, allowed=e._HOME_FILES | e._HOME_DIRS)
    directories, journal = set(), False
    for entry in names:
        path = resource + "/" + entry
        if entry in e._HOME_FILES:
            source.metadata_file(home, entry, path)
            continue
        fd = source.optional_directory(home, entry, path)
        o._need(fd is not None, "SOURCE_CHANGED")
        directories.add(entry)
        for leaf in source.listing(fd):
            o._need(leaf in e._STORES if entry == "j01-lab-memory"
                    else _leaf_allowed(leaf, entry), "SOURCE_NAMESPACE_INVALID")
            value = source.metadata_file(fd, leaf, path + "/" + leaf)
            if entry == "j01-lab-memory" and leaf == "activity.sqlite3":
                journal = value.st_size > 0
    return "OBSERVED" if e._HOME_DIRS <= directories and journal else "PARTIAL"


def home_names(source, lab):
    """Bound and validate the entire namespace before reading any home content."""
    for name in ("individuals", "admission-ops", "registrar-admissions", "admission-envelopes"):
        o._need(source.optional_directory(lab, name, name) is not None, "SOURCE_UNAVAILABLE")
    parent = source.optional_directory(lab, "individuals", "individuals")
    names = source.listing(parent, limit=65)
    for name in names:
        o._need(f.hex64(name), "SOURCE_NAMESPACE_INVALID")
        o._need(source.optional_directory(parent, name, "individuals/" + name) is not None,
                "SOURCE_CHANGED")
    return names


def acquire_homes(source, lab, names):
    """Acquire all own evidence via derived paths and the shared content cache.

Only names produced by home_names on this owner may be used. Missing stable JSON
or divergent stable JSON is retained as a local fact by the pure projection.
"""
    parent = source.optional_directory(lab, "individuals", "individuals")
    o._need(names == source.inventories.get(parent), "SOURCE_CHANGED")
    result = []
    for agent in names:
        base = "individuals/" + agent + "/"
        def read(path, limit=65536):
            return source.selected(lab, path, limit)[0]
        record, spec = read(base + "record.json"), read(base + "spec.json")
        q = adm = st = ind_env = adm_env = q_env = st_env = None
        try:
            if record is not None:
                rv = c.decode(record)
                ind_env = read("admission-envelopes/" + agent + "/individual-"
                               + f.digest(rv) + ".envelope.json", 16384)
                if rv.get("role") == "DESCENDANT":
                    q = read(base + "birth_qualification.json")
                    adm = read("registrar-admissions/" + agent + ".json")
                    prefix = "admission-envelopes/" + agent + "/"
                    if adm is not None:
                        adm_env = read(prefix + "admission-" + f.digest(c.decode(adm)) + ".envelope.json", 16384)
                    if q is not None:
                        qhash = f.digest(c.decode(q))
                        st = read(prefix + "statement-" + qhash + ".json", 16384)
                        q_env = read(prefix + "birth-qualification-" + qhash + ".envelope.json", 16384)
                        st_env = read(prefix + "statement-" + qhash + ".envelope.json", 16384)
        except c.CoreError:
            # Stable malformed records stay local. IO/capacity failures propagate.
            pass
        state = layout(source, parent, agent, "individuals/" + agent)
        result.append(HomeInput(agent, record, spec, q, adm, st, ind_env, adm_env, q_env, st_env, state))
    return tuple(result)
