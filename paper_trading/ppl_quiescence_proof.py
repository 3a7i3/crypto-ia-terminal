"""PPL-QUIESCENCE-01 (lot A) — persisted, self-invalidating quiescence proof.

Pure source module.  It is wired into nothing: no Advisor, no simulator, no
installer.  See docs/contracts/PPL_QUIESCENCE_01_PERSISTED_PROOF.md.

Three things are kept strictly apart:

* **O — coherent observation** (``OBSERVATION`` record): produced in-process
  under ``sim._lock`` then ``runtime._lock``.  It proves a memory/durable
  agreement at one instant of one live process.  Never that it is stopped.
* **Seal** (``SENTINEL`` record): the process states "sealed at this ledger
  digest".  A process can write it and then be SIGKILLed: not a clean exit.
* **S — stop witness** (``WITNESS`` record): produced by a *separate* process.
  A free ``flock`` only says the inspected inode is not locked; the witness
  binds it to inode identity, pid+start time, pid namespace and boot id.

Every value is ``{status, value, provenance}``.  ``UNKNOWN``,
``NOT_AVAILABLE``, ``NOT_APPLICABLE`` and ``UNRESOLVED`` never carry a value
and are never coerced to ``0``/``False`` (the existing quiescence adapters are
refused rather than fed a fabricated zero).
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import time
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "PPL-QUIESCENCE-OBSERVATION-V1"
GATE_WIRING_PROTOCOL = "PPL-GATE-WIRING-V1"
# Lot A v1.3 (C1a): the declaration may name the dedicated counters protocol.
COUNTERS_PROTOCOL = "PPL-QUIESCENCE-COUNTERS-V1"
TRANSITION_NOT_APPLIED = "NOT_APPLIED"
TRANSITION_APPLIED_DURABLE_NOT_MEMORY = "APPLIED_DURABLE_NOT_MEMORY"
TRANSITION_UNRESOLVED = "UNRESOLVED"
GENESIS = "0" * 64

OBSERVED = "OBSERVED"
UNKNOWN = "UNKNOWN"
NOT_AVAILABLE = "NOT_AVAILABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNRESOLVED = "UNRESOLVED"
_STATUSES = frozenset({OBSERVED, UNKNOWN, NOT_AVAILABLE, NOT_APPLICABLE, UNRESOLVED})

KIND_OBSERVATION = "OBSERVATION"
KIND_SENTINEL = "SENTINEL"
KIND_WITNESS = "WITNESS"
_KINDS = frozenset({KIND_OBSERVATION, KIND_SENTINEL, KIND_WITNESS})

V_UNKNOWN = "UNKNOWN"
V_RUNNING = "RUNNING"
V_INTERRUPTED = "INTERRUPTED"
V_SEALED_STOPPED = "SEALED_THEN_STOPPED"
V_CLEAN_CONFIRMED = "CLEAN_STOP_CONFIRMED"
V_STALE = "STALE"
V_UNCERTAIN = "UNCERTAIN_PROOF"
V_UNRESOLVED_CHAIN = "UNRESOLVED_CHAIN"
V_QUIESCENT = (
    "QUIESCENT"  # not a verdict of its own: a flag over the two stopped verdicts
)

IDENTITY_FIELDS = (
    "paper_epoch_id",
    "manifest_sha256",
    "config_snapshot_hash",
    "code_sha",
    "source_sha",
    "authority_store_root",
)
LEDGER_FIELDS = (
    "ledger_last_sequence",
    "ledger_last_event_id",
    "ledger_size_bytes",
    "ledger_sha256",
    "ledger_event_count",
)
POSITION_FIELDS = (
    "durable_open_positions",
    "durable_unresolved_positions",
    "memory_open_positions",
    "memory_matches_durable",
)
ORDER_FIELDS = ("pending_order_count", "lifecycle_transitions_in_flight")
# Every counter that must be an OBSERVED, strictly typed, non-negative int equal to 0.
ZERO_COUNTER_FIELDS = (*ORDER_FIELDS, "admissions_in_flight")
ADMISSION_FIELDS = (
    "gate_state",
    "gate_marker_sha256",
    "runtime_consults_gate",
    "admissions_in_flight",
)
PROCESS_FIELDS = (
    "process_instance_id",
    "pid",
    "pid_starttime",
    "pid_namespace",
    "boot_id",
    "lock_path",
    "lock_dev",
    "lock_ino",
    "lock_ctime_ns",
    "lock_mtime_ns",
)
# (dev, ino) alone is not an identity: an inode number is recycled after unlink.
# ctime/mtime of the lock file are fixed for the process lifetime (it only
# flocks it), so a recreated file differs unless created in the same kernel tick.
LOCK_IDENTITY_FIELDS = ("lock_dev", "lock_ino", "lock_ctime_ns", "lock_mtime_ns")
GENERATION_FIELDS = ("simulator_generation",)

# Explicit required fields (all must be OBSERVED) for each outcome.
_SEALED_REQUIRED = (
    IDENTITY_FIELDS
    + LEDGER_FIELDS
    + PROCESS_FIELDS
    + POSITION_FIELDS
    + GENERATION_FIELDS
    + ("gate_state", "gate_marker_sha256")
)
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    V_INTERRUPTED: IDENTITY_FIELDS + LEDGER_FIELDS + PROCESS_FIELDS,
    V_SEALED_STOPPED: _SEALED_REQUIRED,
    V_CLEAN_CONFIRMED: _SEALED_REQUIRED,
    V_QUIESCENT: _SEALED_REQUIRED
    + ORDER_FIELDS
    + ("runtime_consults_gate", "admissions_in_flight"),
}


class QuiescenceRefusal(Exception):
    """A proof is refused (fail closed)."""


class PersistError(Exception):
    """Base for persistence failures."""


class PersistBlocked(PersistError):
    """Nothing was published (or the chain forbids appending): no sequence used."""


class PersistUncertain(PersistError):
    """A record is visible but its durability is not confirmed."""

    def __init__(self, message: str, *, seq: int, record_sha256: str) -> None:
        super().__init__(message)
        self.seq = seq
        self.record_sha256 = record_sha256


# --------------------------------------------------------------------- values


def observed(value: Any, provenance: str) -> dict[str, Any]:
    return {"status": OBSERVED, "value": value, "provenance": str(provenance)}


def _novalue(status: str, provenance: str) -> dict[str, Any]:
    return {"status": status, "value": None, "provenance": str(provenance)}


def unknown(provenance: str) -> dict[str, Any]:
    return _novalue(UNKNOWN, provenance)


def not_available(provenance: str) -> dict[str, Any]:
    return _novalue(NOT_AVAILABLE, provenance)


def not_applicable(provenance: str) -> dict[str, Any]:
    return _novalue(NOT_APPLICABLE, provenance)


def unresolved(provenance: str) -> dict[str, Any]:
    return _novalue(UNRESOLVED, provenance)


def is_value(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and set(item) == {"status", "value", "provenance"}
        and item["status"] in _STATUSES
        and isinstance(item["provenance"], str)
        and (item["status"] == OBSERVED or item["value"] is None)
    )


def is_observed(body: Mapping[str, Any], name: str) -> bool:
    item = body.get(name)
    return is_value(item) and item["status"] == OBSERVED


def observed_value(body: Mapping[str, Any], name: str) -> Any:
    return body[name]["value"] if is_observed(body, name) else None


def _count(item: Any) -> int | None:
    if is_value(item) and item["status"] == OBSERVED:
        number = item["value"]
        if type(number) is int and number >= 0:
            return number
    return None


# ------------------------------------------------------------------ canonical


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = val
    return result


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-finite JSON constant {name}")


def strict_loads(raw: bytes) -> Any:
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_no_duplicates,
        parse_constant=_reject_constant,
    )


def _finite(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise QuiescenceRefusal("timestamp must be a finite number")
    return float(value)


# ----------------------------------------------------------- process identity


_DEFAULT_PROC = "/proc"
_DEFAULT_BOOT_ID = "/proc/sys/kernel/random/boot_id"


def read_boot_id(path: str = _DEFAULT_BOOT_ID) -> str | None:
    try:
        text = Path(path).read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return text or None


def read_pid_starttime(
    pid: int, proc_root: str = _DEFAULT_PROC
) -> tuple[str, int | None]:
    """``("ALIVE", ticks)``, ``("GONE", None)`` or ``("UNKNOWN", None)``."""

    if type(pid) is not int or pid <= 0:
        return "UNKNOWN", None
    stat_path = Path(proc_root) / str(pid) / "stat"
    try:
        raw = stat_path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, ProcessLookupError):
        return "GONE", None
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return "GONE", None
        return "UNKNOWN", None
    try:
        fields = raw[raw.rindex(")") + 2 :].split()
        return "ALIVE", int(fields[19])
    except (ValueError, IndexError):
        return "UNKNOWN", None


def read_pid_namespace(proc_root: str = _DEFAULT_PROC) -> str | None:
    try:
        return os.readlink(str(Path(proc_root) / "self" / "ns" / "pid"))
    except OSError:
        return None


def current_process_identity(
    *,
    process_instance_id: str,
    lock_path: str,
    lock_fd: int | None,
    proc_root: str = _DEFAULT_PROC,
    boot_id_path: str = _DEFAULT_BOOT_ID,
    pid: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Identity of the *calling* process, as the process itself can observe it."""

    pid = os.getpid() if pid is None else pid
    prov = "self-observed in-process"
    out: dict[str, dict[str, Any]] = {
        "process_instance_id": observed(process_instance_id, prov)
        if isinstance(process_instance_id, str) and process_instance_id
        else unknown("process_instance_id not provided"),
        "pid": observed(pid, prov),
    }
    state, ticks = read_pid_starttime(pid, proc_root)
    out["pid_starttime"] = (
        observed(ticks, f"{proc_root}/{pid}/stat field 22")
        if state == "ALIVE"
        else unknown(f"start time unreadable ({state})")
    )
    ns = read_pid_namespace(proc_root)
    out["pid_namespace"] = (
        observed(ns, f"{proc_root}/self/ns/pid")
        if ns
        else unknown("pid namespace unreadable")
    )
    boot = read_boot_id(boot_id_path)
    out["boot_id"] = (
        observed(boot, boot_id_path) if boot else unknown("boot id unreadable")
    )
    out["lock_path"] = observed(str(lock_path), "configured instance lock path")
    if lock_fd is None:
        for name in LOCK_IDENTITY_FIELDS:
            out[name] = unknown("instance lock fd not provided")
    else:
        try:
            info = os.fstat(lock_fd)
            for name, val in zip(
                LOCK_IDENTITY_FIELDS,
                (info.st_dev, info.st_ino, info.st_ctime_ns, info.st_mtime_ns),
                strict=True,
            ):
                out[name] = observed(val, "fstat(lock_fd)")
        except OSError:
            for name in LOCK_IDENTITY_FIELDS:
                out[name] = unknown("fstat(lock_fd) failed")
    return out


def probe_stop_evidence(
    recorded: Mapping[str, Any],
    *,
    exit_evidence: Mapping[str, Any] | None = None,
    proc_root: str = _DEFAULT_PROC,
    boot_id_path: str = _DEFAULT_BOOT_ID,
) -> dict[str, dict[str, Any]]:
    """Witness-side inspection of a process recorded by an observation.

    ``process_stopped`` is ``OBSERVED True`` only when (a) the boot id differs
    from the recorded one, or (b) the pid is verifiably gone (absent, or reused
    with another start time, in the *same pid namespace*) **and** the very inode
    the process held is still there and free.  A free path alone never counts;
    an absent, replaced, ambiguous or unreadable lock gives ``UNKNOWN``.
    ``HELD`` lock or live pid gives ``OBSERVED False``.
    """

    out: dict[str, dict[str, Any]] = {}
    rec_boot = observed_value(recorded, "boot_id")
    cur_boot = read_boot_id(boot_id_path)
    boot_changed: bool | None = None
    if rec_boot is not None and cur_boot is not None:
        boot_changed = rec_boot != cur_boot
        out["boot_probe"] = observed(
            "CHANGED" if boot_changed else "SAME", f"{boot_id_path} vs recorded boot_id"
        )
    else:
        out["boot_probe"] = unknown("boot id missing on one side")

    # pid probe
    pid = observed_value(recorded, "pid")
    rec_start = observed_value(recorded, "pid_starttime")
    rec_ns = observed_value(recorded, "pid_namespace")
    cur_ns = read_pid_namespace(proc_root)
    pid_state = "UNKNOWN"
    if (
        pid is None
        or rec_start is None
        or rec_ns is None
        or cur_ns is None
        or rec_ns != cur_ns
    ):
        out["pid_probe"] = unknown(
            "pid, start time or pid namespace missing, or namespace differs from the recorded one"
        )
    else:
        state, ticks = read_pid_starttime(pid, proc_root)
        if state == "ALIVE":
            pid_state = "ALIVE" if ticks == rec_start else "GONE"
        else:
            pid_state = state
        if pid_state == "UNKNOWN":
            out["pid_probe"] = unknown("pid status unreadable")
        else:
            out["pid_probe"] = observed(
                pid_state, f"{proc_root}/<pid>/stat start time compare"
            )

    # lock probe (identity-bound)
    lock_state = _probe_lock(recorded)
    out["lock_probe"] = lock_state

    lock_value = lock_state["value"] if lock_state["status"] == OBSERVED else None
    if lock_value == "HELD" or pid_state == "ALIVE":
        out["process_stopped"] = observed(
            False, "lock held or pid alive with recorded start time"
        )
    elif boot_changed is True:
        out["process_stopped"] = observed(
            True, "boot id changed: the recorded process cannot exist"
        )
    elif pid_state == "GONE" and lock_value == "FREE_SAME_IDENTITY":
        out["process_stopped"] = observed(
            True,
            "pid gone (start time compared) and the recorded lock inode is present and free",
        )
    else:
        out["process_stopped"] = unknown(
            "stop not established: need pid gone AND recorded lock inode present and free "
            "(or a boot change); absent/replaced/ambiguous lock is UNKNOWN"
        )

    out["exit_status"] = _exit_status(exit_evidence, recorded)
    return out


def _probe_lock(recorded: Mapping[str, Any]) -> dict[str, Any]:
    path = observed_value(recorded, "lock_path")
    want = tuple(observed_value(recorded, n) for n in LOCK_IDENTITY_FIELDS)
    if path is None or any(v is None for v in want):
        return unknown("recorded lock identity incomplete")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return unknown(
            "lock file absent: clean unlink, replacement or never created are indistinguishable"
        )
    except OSError as exc:
        return unknown(f"lock file not inspectable: {exc.strerror}")
    try:
        opened = os.fstat(fd)
        try:
            by_path = os.lstat(path)
        except OSError:
            return unknown("lock path changed during inspection")
        if (opened.st_dev, opened.st_ino) != (
            by_path.st_dev,
            by_path.st_ino,
        ) or not stat.S_ISREG(opened.st_mode):
            return unknown("lock path identity ambiguous during inspection")
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_ctime_ns,
            opened.st_mtime_ns,
        ) != want:
            return unknown(
                "lock file replaced or modified: identity differs from the one the process held"
            )
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return observed(
                "HELD", "flock(LOCK_SH|LOCK_NB) refused on the recorded inode"
            )
        except OSError as exc:
            return unknown(f"flock probe failed: {exc.strerror}")
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            return unknown("flock probe could not release its own shared lock")
        return observed(
            "FREE_SAME_IDENTITY",
            "flock(LOCK_SH|LOCK_NB) acquired and released on the recorded inode (dev, ino equal)",
        )
    finally:
        os.close(fd)


def _exit_status(
    evidence: Mapping[str, Any] | None, recorded: Mapping[str, Any]
) -> dict[str, Any]:
    if evidence is None:
        return unknown("no independent exit-status evidence supplied")
    try:
        ok = (
            set(evidence) == {"source", "exit_code", "pid", "pid_starttime"}
            and isinstance(evidence["source"], str)
            and evidence["source"]
            and type(evidence["exit_code"]) is int
            and evidence["pid"] == observed_value(recorded, "pid")
            and evidence["pid_starttime"] == observed_value(recorded, "pid_starttime")
            and observed_value(recorded, "pid_starttime") is not None
        )
    except (KeyError, TypeError):
        ok = False
    if not ok:
        return unknown(
            "exit-status evidence malformed or not bound to the recorded pid and start time"
        )
    return observed(int(evidence["exit_code"]), f"supervisor:{evidence['source']}")


# --------------------------------------------------------------- observations


def _ledger_fingerprint(store_root: Path, epoch_id: str) -> dict[str, dict[str, Any]]:
    """Read-only fingerprint of the epoch file, cross-checked with the decoder."""

    from paper_trading.durable_event_store import DurableEventStore

    # DurableEventStore opens its lock file with a+b: never create it in an
    # authority store from a reader; a missing lock file means "not inspectable".
    if not (Path(store_root) / ".ppl-event-store.lock").is_file():
        return {
            n: unknown("authority store lock file absent: not inspected")
            for n in LEDGER_FIELDS
        }
    return _fingerprint_from(DurableEventStore(store_root), epoch_id)


def _fingerprint_from(store: Any, epoch_id: str) -> dict[str, dict[str, Any]]:
    prov = "epoch file bytes + DurableEventStore.load_epoch"
    names = LEDGER_FIELDS
    bad = {name: unresolved("ledger not readable or inconsistent") for name in names}
    try:
        path = store._epoch_path(epoch_id)
        raw = path.read_bytes()
        events = store.load_epoch(epoch_id)
    except Exception:  # noqa: BLE001 - fail closed: any read failure is UNRESOLVED/UNKNOWN
        return bad
    lines = [line for line in raw.splitlines() if line.strip()]
    if not events or len(lines) != len(events):
        return bad
    last = events[-1]
    if last.event_id.encode("utf-8") not in lines[-1]:
        return bad
    return {
        "ledger_last_sequence": observed(last.sequence, prov),
        "ledger_last_event_id": observed(last.event_id, prov),
        "ledger_size_bytes": observed(len(raw), prov),
        "ledger_sha256": observed(sha256_hex(raw), prov),
        "ledger_event_count": observed(len(events), prov),
    }


def gate_wiring_value(simulator: Any, code_sha: str) -> dict[str, Any]:
    """Provenance of ``runtime_consults_gate``.

    The current runtime exposes no ``ppl_gate_wiring_v1`` declaration and its
    sources never import ``ppl_admission_gate`` (audit of main@3ce529fc), so this
    is ``UNKNOWN``.  A declaration is only a statement by the same code under
    test; it is accepted only with the exact protocol id and the manifest code sha.
    """

    declaration = getattr(simulator, "ppl_gate_wiring_v1", None)
    if declaration is None:
        return unknown(
            f"simulator exposes no {GATE_WIRING_PROTOCOL} declaration "
            "(current runtime does not consult the admission gate)"
        )
    if (
        not isinstance(declaration, Mapping)
        or declaration.get("protocol") != GATE_WIRING_PROTOCOL
        or declaration.get("code_sha") != code_sha
        or type(declaration.get("consults_gate_under_lock")) is not bool
    ):
        return unresolved(
            f"{GATE_WIRING_PROTOCOL} declaration malformed or bound to another code sha"
        )
    return observed(
        declaration["consults_gate_under_lock"],
        f"RUNTIME_DECLARATION:{GATE_WIRING_PROTOCOL}@{code_sha}",
    )


def _published_counters_declaration(simulator: Any, code_sha: str) -> Mapping[str, Any] | None:
    """Lot A v1.3: the wiring declaration, only if it is valid AND names the
    dedicated counters protocol (contract C1 D-C1a-5).  Otherwise ``None`` and
    the observer keeps the v1.2 values (NOT_APPLICABLE / UNKNOWN)."""

    wiring = gate_wiring_value(simulator, code_sha)
    if wiring["status"] != OBSERVED or wiring["value"] is not True:
        return None
    declaration = simulator.ppl_gate_wiring_v1
    if declaration.get("counters_protocol") != COUNTERS_PROTOCOL:
        return None
    return declaration


def _strict_count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _transition_detail(
    started: Any, events: Any, memory_ids: list[str], chain_valid: bool
) -> list[dict[str, str]]:
    """Diagnostic only (contract C1 v0.3 §5.2): never changes the counter."""

    opened = {
        ev.trade_id for ev in events if getattr(ev, "event_type", None) == "POSITION_OPENED"
    }
    closed = {
        ev.trade_id for ev in events if getattr(ev, "event_type", None) == "POSITION_CLOSED"
    }
    memory = set(memory_ids)
    detail = []
    for kind, trade_id in sorted(started):
        if not chain_valid:
            cls = TRANSITION_UNRESOLVED
        elif kind == "OPEN" and trade_id not in opened and trade_id not in memory:
            cls = TRANSITION_NOT_APPLIED
        elif kind == "OPEN" and trade_id in opened and trade_id not in memory:
            cls = TRANSITION_APPLIED_DURABLE_NOT_MEMORY
        elif kind == "CLOSE" and trade_id not in closed and trade_id in memory:
            cls = TRANSITION_NOT_APPLIED
        elif kind == "CLOSE" and trade_id in closed and trade_id in memory:
            cls = TRANSITION_APPLIED_DURABLE_NOT_MEMORY
        else:
            cls = TRANSITION_UNRESOLVED
        detail.append({"kind": str(kind), "trade_id": str(trade_id), "class": cls})
    return detail


def observe_runtime(
    simulator: Any,
    runtime: Any,
    *,
    manifest: Any,
    manifest_sha256: str,
    gate: Any,
    identity: Mapping[str, Mapping[str, Any]],
    source_sha: str | None = None,
) -> dict[str, dict[str, Any]]:
    """O: coherent observation of a live simulator.  Read-only.

    Lock order is ``simulator._lock`` then ``runtime._lock`` (the order used by
    the authority OPEN/CLOSE path).  Nothing is mutated, closed or restarted.
    """

    authority = getattr(simulator, "_lifecycle_authority", None)
    if not getattr(authority, "ppl_is_authoritative", False):
        raise QuiescenceRefusal("observer requires a PPL_AUTHORITY simulator")
    epoch_id = manifest.paper_epoch_id
    declaration = _published_counters_declaration(simulator, manifest.code_sha)
    counters: dict[str, dict[str, Any]] = {}
    with simulator._lock, runtime._lock:  # order: simulator -> runtime
        if declaration is not None:
            # Lot A v1.3: authoritative values read under simulator._lock,
            # independent of any durable read (contract C1 v0.3 §5, §9).
            prov = f"simulator counter under sim._lock ({COUNTERS_PROTOCOL})"
            admissions = _strict_count(
                getattr(simulator, "_ppl_admissions_in_flight", None)
            )
            started_raw = getattr(simulator, "_ppl_started_transitions", None)
            started = set(started_raw) if isinstance(started_raw, set) else None
            counters["admissions_in_flight"] = (
                observed(admissions, prov)
                if admissions is not None
                else unresolved("admissions counter missing or not a strict int")
            )
            counters["lifecycle_transitions_in_flight"] = (
                observed(
                    len(started),
                    f"len(simulator._ppl_started_transitions) under sim._lock "
                    f"({COUNTERS_PROTOCOL})",
                )
                if started is not None
                else unresolved("started transitions set missing")
            )
        if declaration is None:
            # v1.2 behaviour preserved without a counters declaration: an
            # unreadable authority view propagates (contract A v1.3 §12).
            view = runtime.consistent_view()
        else:
            try:
                view = runtime.consistent_view()
            except Exception:  # noqa: BLE001 - recorded as UNRESOLVED below
                view = None
        ledger = _fingerprint_from(runtime.store, epoch_id)
        if view is not None:
            durable_open = sorted(view.projection.open_positions.keys())
            unresolved_pos = sorted(
                getattr(view.projection, "unresolved_positions", {}).keys()
            )
        else:
            durable_open = unresolved_pos = None
        memory_open = sorted(str(p.pos_id) for p in simulator._positions.values())
        if declaration is not None:
            started_now = getattr(simulator, "_ppl_started_transitions", None)
            chain_valid = view is not None and is_observed(ledger, "ledger_sha256")
            counters["lifecycle_transitions_detail"] = observed(
                _transition_detail(
                    started_now if isinstance(started_now, set) else set(),
                    view.events if view is not None else (),
                    memory_open,
                    chain_valid,
                ),
                "diagnostic only: durable/memory comparison per started key "
                "(never changes lifecycle_transitions_in_flight)",
            )
            counters["code_sha_provenance"] = observed(
                str(declaration.get("code_sha_provenance")),
                f"{GATE_WIRING_PROTOCOL} declaration (configuration, not attestation)",
            )
            counters["module_sha256"] = observed(
                declaration.get("module_sha256"),
                str(declaration.get("module_sha256_provenance")),
            )
        generation = getattr(simulator, "_legacy_generation", None)
        orders = getattr(simulator, "_orders", None)
        if isinstance(orders, dict):
            pending = sum(
                1
                for o in orders.values()
                if str(
                    getattr(getattr(o, "status", ""), "value", getattr(o, "status", ""))
                ).upper()
                == "PENDING"
            )
            pending_value = observed(
                pending, "len(simulator._orders where status=PENDING) under lock"
            )
        else:
            pending_value = unknown("simulator._orders unavailable")
        try:
            gate_state = gate.state()
            marker_present = bool(gate._marker_present())
            marker_sha = (
                sha256_hex(gate._closed_marker.read_bytes()) if marker_present else None
            )
            gate_value = observed(gate_state, "AdmissionGate.state()")
            marker_value = (
                observed(marker_sha, "sha256(<journal>.closed)")
                if marker_sha
                else not_available("no closure marker present")
            )
        except Exception:  # noqa: BLE001 - fail closed: any read failure is UNRESOLVED/UNKNOWN
            gate_value = unresolved("gate state unreadable")
            marker_value = unresolved("gate marker unreadable")
    prov_mem = "set equality under sim._lock then runtime._lock"
    if view is not None and is_observed(ledger, "ledger_sha256"):
        matches = observed(memory_open == durable_open, prov_mem)
    else:
        matches = unresolved("ledger unreadable: memory/durable comparison not trusted")
    body: dict[str, dict[str, Any]] = {
        "paper_epoch_id": observed(epoch_id, "manifest"),
        "manifest_sha256": observed(manifest_sha256, "authority_manifest_sha256"),
        "config_snapshot_hash": observed(manifest.config_snapshot_hash, "manifest"),
        "code_sha": observed(manifest.code_sha, "manifest"),
        "source_sha": observed(source_sha, "caller-supplied process source sha")
        if source_sha
        else unknown("process source sha not supplied"),
        "authority_store_root": observed(
            str(Path(runtime.store._root).resolve()), "runtime.store root, resolved"
        ),
        **ledger,
        "durable_open_positions": observed(
            durable_open, "consistent_view().projection.open_positions"
        )
        if durable_open is not None
        else unresolved("authority view unreadable"),
        "durable_unresolved_positions": observed(
            unresolved_pos, "consistent_view().projection.unresolved_positions"
        )
        if unresolved_pos is not None
        else unresolved("authority view unreadable"),
        "memory_open_positions": observed(
            memory_open, "simulator._positions under lock"
        ),
        "memory_matches_durable": matches,
        "pending_order_count": pending_value,
        "lifecycle_transitions_in_flight": not_applicable(
            "PPL_AUTHORITY path performs OPEN/CLOSE entirely under simulator._lock; "
            "the legacy counter is never incremented there and is not read as zero"
        ),
        "gate_state": gate_value,
        "gate_marker_sha256": marker_value,
        "runtime_consults_gate": gate_wiring_value(simulator, manifest.code_sha),
        "admissions_in_flight": unknown(
            "no admission-in-flight counter exists in the runtime"
        ),
        "simulator_generation": observed(
            int(generation), "simulator._legacy_generation (process-local, historical)"
        )
        if type(generation) is int
        else unknown("simulator generation unavailable"),
    }
    body.update(counters)  # lot A v1.3: only with a valid counters declaration
    for name in PROCESS_FIELDS:
        body[name] = (
            dict(identity[name])
            if name in identity
            else unknown("identity field missing")
        )
    return body


# --------------------------------------------------------------------- store

_NAME_RE = re.compile(r"^quiescence-(\d{8})-([0-9a-f]{16})\.json$")
_ENVELOPE_KEYS = frozenset(
    {
        "schema",
        "kind",
        "seq",
        "prev_record_sha256",
        "observed_at",
        "clock_provenance",
        "max_age_s",
        "body",
        "record_sha256",
    }
)


def _record_name(seq: int, sha: str, ext: str) -> str:
    return f"quiescence-{seq:08d}-{sha[:16]}.{ext}"


@dataclass(frozen=True)
class ChainRecord:
    seq: int
    record_sha256: str
    envelope: Mapping[str, Any]
    confirmed: bool

    @property
    def kind(self) -> str:
        return self.envelope["kind"]

    @property
    def body(self) -> Mapping[str, Any]:
        return self.envelope["body"]

    @property
    def observed_at(self) -> float:
        return float(self.envelope["observed_at"])


@dataclass(frozen=True)
class ChainView:
    status: str  # EMPTY | OK | UNRESOLVED
    records: tuple[ChainRecord, ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def all_confirmed(self) -> bool:
        return all(r.confirmed for r in self.records)


@dataclass(frozen=True)
class AppendResult:
    seq: int
    record_sha256: str
    path: Path
    # False: the receipt is visible but its directory entry was not confirmed
    # durable.  The record itself was already durable, so the outcome is sound;
    # if a crash drops the receipt the record reverts to *unconfirmed* (readers
    # refuse it until recover()).
    receipt_durable: bool = True


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


class ProofStore:
    """Dedicated, chained, single-writer store of proof records.

    Publication protocol (all under the writer ``flock``):
    tmp file -> write -> fsync(file) -> ``link`` (no overwrite) -> fsync(dir)
    -> receipt (``.ok``).  A record is **confirmed** only when its receipt
    exists; the receipt is created strictly after the directory fsync
    succeeded, so a visible receipt asserts a fact that was already true.  A
    visible record without receipt is *uncertain*: readers never accept it.
    A failure after publication but before the receipt is visible raises
    :class:`PersistUncertain` and keeps the sequence (no gap, no fork); the next
    writer must :meth:`recover` it before appending.  A failure of the *last*
    directory fsync (receipt already visible) is not an uncertainty about the
    record: it is reported as ``AppendResult.receipt_durable == False``.
    """

    def __init__(
        self,
        directory: os.PathLike[str] | str,
        *,
        forbidden_roots: Iterable[os.PathLike[str] | str] = (),
        lock_timeout: float = 5.0,
    ) -> None:
        path = Path(directory)
        forbidden_resolved = [Path(f).resolve() for f in forbidden_roots]

        def check_overlap() -> None:
            resolved = path.resolve()  # follows existing ancestors, symlinks included
            for forbidden in forbidden_resolved:
                if _paths_overlap(resolved, forbidden):
                    raise PersistBlocked("proof directory overlaps an authority root")

        check_overlap()  # BEFORE anything is created: a refusal leaves no trace
        try:
            path.mkdir(parents=True, exist_ok=True)
            info = path.lstat()
        except OSError as exc:
            raise PersistBlocked(f"proof directory unavailable: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise PersistBlocked("proof directory must be a real directory")
        check_overlap()
        self.directory = path.resolve()
        self._lock_timeout = float(lock_timeout)

    # -- low-level primitives (overridable for fault injection in tests) -----

    def _fsync_fd(self, fd: int) -> None:
        os.fsync(fd)

    def _fsync_directory(self) -> None:
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            self._fsync_fd(fd)
        finally:
            os.close(fd)

    def _link(self, source: Path, target: Path) -> None:
        os.link(source, target)

    @staticmethod
    def _write_all(fd: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "short write")
            view = view[written:]

    # -- writer lock ---------------------------------------------------------

    def _acquire_writer_lock(self) -> int:
        try:
            fd = os.open(
                self.directory / ".writer.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
        except OSError as exc:
            raise PersistBlocked(f"writer lock unavailable: {exc}") from exc
        deadline = time.monotonic() + self._lock_timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise PersistBlocked("writer lock timeout") from None
                time.sleep(0.005)
            except OSError as exc:
                os.close(fd)
                raise PersistBlocked(f"writer lock failed: {exc}") from exc

    # -- reading -------------------------------------------------------------

    def scan(self) -> ChainView:
        """Strict, read-only view.  Any anomaly is UNRESOLVED, never skipped."""

        try:
            names = sorted(os.listdir(self.directory))
        except OSError as exc:
            return ChainView("UNRESOLVED", (), (f"directory unreadable: {exc}",))
        by_seq: dict[int, list[str]] = {}
        for name in names:
            match = _NAME_RE.match(name)
            if match:
                by_seq.setdefault(int(match.group(1)), []).append(name)
        if not by_seq:
            return ChainView("EMPTY")
        reasons: list[str] = []
        expected = list(range(1, max(by_seq) + 1))
        if sorted(by_seq) != expected:
            reasons.append("sequence gap")
        for seq, files in by_seq.items():
            if len(files) > 1:
                reasons.append(f"fork at seq {seq}")
        if reasons:
            return ChainView("UNRESOLVED", (), tuple(reasons))
        records: list[ChainRecord] = []
        prev = GENESIS
        for seq in expected:
            name = by_seq[seq][0]
            path = self.directory / name
            try:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise ValueError("not a regular file")
                env = strict_loads(path.read_bytes())
                if not isinstance(env, dict) or set(env) != _ENVELOPE_KEYS:
                    raise ValueError("envelope fields")
                core = {k: v for k, v in env.items() if k != "record_sha256"}
                sha = sha256_hex(canonical(core))
                if (
                    env["record_sha256"] != sha
                    or not name.startswith(f"quiescence-{seq:08d}-{sha[:16]}")
                    or env["schema"] != SCHEMA
                    or env["kind"] not in _KINDS
                    or env["seq"] != seq
                    or env["prev_record_sha256"] != prev
                    or not isinstance(env["body"], dict)
                    or not all(is_value(v) for v in env["body"].values())
                ):
                    raise ValueError("hash, name, schema or chain mismatch")
                _finite(env["observed_at"])
                _finite(env["max_age_s"])
            except (OSError, ValueError, UnicodeDecodeError, QuiescenceRefusal) as exc:
                return ChainView("UNRESOLVED", tuple(records), (f"seq {seq}: {exc}",))
            records.append(ChainRecord(seq, sha, env, self._receipt_valid(seq, sha)))
            prev = sha
        return ChainView("OK", tuple(records))

    def _receipt_valid(self, seq: int, sha: str) -> bool:
        path = self.directory / _record_name(seq, sha, "ok")
        try:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                return False
            doc = strict_loads(path.read_bytes())
        except (OSError, ValueError, UnicodeDecodeError):
            return False
        return (
            isinstance(doc, dict)
            and doc.get("record_sha256") == sha
            and doc.get("seq") == seq
        )

    # -- writing -------------------------------------------------------------

    def append(
        self,
        kind: str,
        body: Mapping[str, Any],
        *,
        observed_at: float,
        clock_provenance: str,
        max_age_s: float,
    ) -> AppendResult:
        if kind not in _KINDS:
            raise PersistBlocked("unknown record kind")
        at = _finite(observed_at)
        age = _finite(max_age_s)
        if age <= 0:
            raise PersistBlocked("max_age_s must be positive")
        for name, item in body.items():
            if not is_value(item):
                raise PersistBlocked(
                    f"body field {name!r} is not a status/value/provenance triple"
                )
        lock_fd = self._acquire_writer_lock()
        try:
            chain = self.scan()
            if chain.status == "UNRESOLVED":
                raise PersistBlocked(f"chain unresolved: {'; '.join(chain.reasons)}")
            if chain.records and not chain.records[-1].confirmed:
                self._recover_locked(chain.records[-1])
                chain = self.scan()
            if any(not r.confirmed for r in chain.records):
                raise PersistBlocked(
                    "an earlier record is unconfirmed; recovery required"
                )
            seq = len(chain.records) + 1
            prev = chain.records[-1].record_sha256 if chain.records else GENESIS
            core = {
                "schema": SCHEMA,
                "kind": kind,
                "seq": seq,
                "prev_record_sha256": prev,
                "observed_at": at,
                "clock_provenance": str(clock_provenance),
                "max_age_s": age,
                "body": dict(body),
            }
            try:
                sha = sha256_hex(canonical(core))
                raw = canonical({**core, "record_sha256": sha})
            except (TypeError, ValueError) as exc:
                raise PersistBlocked(f"record not serializable: {exc}") from exc
            final = self.directory / _record_name(seq, sha, "json")
            self._publish_bytes(raw, final)  # raises PersistBlocked before visibility
            try:
                self._fsync_directory()
                receipt_durable = self._write_receipt(seq, sha, recovered=False)
            except OSError as exc:
                raise PersistUncertain(
                    f"record {seq} visible but durability not confirmed: {exc}",
                    seq=seq,
                    record_sha256=sha,
                ) from exc
            return AppendResult(seq, sha, final, receipt_durable)
        finally:
            os.close(lock_fd)

    def _publish_bytes(self, raw: bytes, final: Path) -> None:
        tmp = self.directory / f".tmp-{os.getpid()}-{uuid.uuid4().hex}"
        fd = -1
        try:
            fd = os.open(
                tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            self._write_all(fd, raw)
            self._fsync_fd(fd)
            os.close(fd)
            fd = -1
            self._link(tmp, final)
        except OSError as exc:
            raise PersistBlocked(f"not published: {exc}") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _write_receipt(self, seq: int, sha: str, *, recovered: bool) -> bool:
        """Publish the receipt.  Raises OSError if it is not visible.

        Returns False when it is visible but its directory fsync failed: the
        fact it asserts (record durable) was established before it was created.
        """

        raw = canonical(
            {
                "record_sha256": sha,
                "seq": seq,
                "recovered": recovered,
                "writer_pid": os.getpid(),
            }
        )
        final = self.directory / _record_name(seq, sha, "ok")
        try:
            self._publish_bytes(raw, final)
        except PersistBlocked as exc:
            cause = exc.__cause__
            if isinstance(cause, FileExistsError):
                pass  # an equivalent receipt already exists
            else:
                raise OSError(errno.EIO, str(exc)) from exc
        try:
            self._fsync_directory()
        except OSError:
            return False
        return True

    def _recover_locked(self, record: ChainRecord) -> None:
        """Re-prove an uncertain record: re-hash, fsync file and directory, then receipt."""

        path = self.directory / _record_name(record.seq, record.record_sha256, "json")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                core = {
                    k: v for k, v in record.envelope.items() if k != "record_sha256"
                }
                if sha256_hex(canonical(core)) != record.record_sha256:
                    raise OSError(errno.EIO, "record changed")
                self._fsync_fd(fd)
            finally:
                os.close(fd)
            self._fsync_directory()
            self._write_receipt(record.seq, record.record_sha256, recovered=True)
        except OSError as exc:
            raise PersistBlocked(
                f"recovery of record {record.seq} failed: {exc}"
            ) from exc

    def recover(self) -> tuple[int, ...]:
        """Confirm every uncertain record that can be re-proven.  Idempotent."""

        lock_fd = self._acquire_writer_lock()
        try:
            chain = self.scan()
            if chain.status == "UNRESOLVED":
                raise PersistBlocked(f"chain unresolved: {'; '.join(chain.reasons)}")
            done = []
            for record in chain.records:
                if not record.confirmed:
                    self._recover_locked(record)
                    done.append(record.seq)
            return tuple(done)
        finally:
            os.close(lock_fd)


# ------------------------------------------------------------------ assessment


@dataclass(frozen=True)
class Assessment:
    verdict: str
    quiescent: bool
    reasons: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    blocking: tuple[str, ...] = field(default_factory=tuple)
    observation_sha256: str | None = None
    historical_unknowns: tuple[str, ...] = ()


def _missing(verdict: str, body: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(n for n in REQUIRED_FIELDS[verdict] if not is_observed(body, n))


def _bound_identity_equal(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return all(
        is_observed(a, n) and is_observed(b, n) and a[n]["value"] == b[n]["value"]
        for n in PROCESS_FIELDS
    )


def assess(
    store: ProofStore,
    *,
    manifest: Any,
    manifest_sha256: str,
    store_root: os.PathLike[str] | str,
    now: float,
    max_age_s: float,
) -> Assessment:
    """Post-mortem capable verification.

    Uses only durable, re-readable evidence: the confirmed record chain, the
    authority ledger re-read now, and the witness's recorded probes.  It never
    claims to re-read a dead process's memory: the memory-derived fields of O
    (pending orders, generation, memory positions) are *historical statements
    bound to the ledger digest*, and are accepted only while that digest is
    unchanged.  Process liveness is established only by a fresh WITNESS record.
    """

    now_f = _finite(now)
    limit = _finite(max_age_s)
    chain = store.scan()
    if chain.status == "UNRESOLVED":
        return Assessment(V_UNRESOLVED_CHAIN, False, chain.reasons)
    if chain.status == "EMPTY":
        return Assessment(V_UNKNOWN, False, ("no proof record",))
    if not chain.all_confirmed:
        return Assessment(
            V_UNCERTAIN,
            False,
            ("a visible record has no durability receipt; run ProofStore.recover()",),
        )
    obs = next((r for r in reversed(chain.records) if r.kind == KIND_OBSERVATION), None)
    if obs is None:
        return Assessment(V_UNKNOWN, False, ("no observation record",))
    seal = next(
        (
            r
            for r in reversed(chain.records)
            if r.kind == KIND_SENTINEL and r.seq > obs.seq
        ),
        None,
    )
    wit = next((r for r in reversed(chain.records) if r.kind == KIND_WITNESS), None)

    def stale(record: ChainRecord) -> str | None:
        age = now_f - record.observed_at
        if age < 0:
            return f"seq {record.seq} observed in the future"
        if age > min(limit, float(record.envelope["max_age_s"])):
            return f"seq {record.seq} older than max_age_s"
        return None

    for record in (obs, seal, wit):
        if record is not None:
            reason = stale(record)
            if reason:
                return Assessment(
                    V_STALE, False, (reason,), observation_sha256=obs.record_sha256
                )

    body = obs.body
    expect = {
        "paper_epoch_id": manifest.paper_epoch_id,
        "manifest_sha256": manifest_sha256,
        "config_snapshot_hash": manifest.config_snapshot_hash,
        "code_sha": manifest.code_sha,
        "authority_store_root": str(Path(store_root).resolve()),
    }
    for name, want in expect.items():
        if not is_observed(body, name) or body[name]["value"] != want:
            return Assessment(
                V_STALE,
                False,
                (f"binding {name} differs",),
                observation_sha256=obs.record_sha256,
            )

    root = Path(store_root)
    current = _ledger_fingerprint(root, manifest.paper_epoch_id)
    if not is_observed(current, "ledger_sha256"):
        return Assessment(
            V_UNKNOWN,
            False,
            ("authority ledger not readable now",),
            observation_sha256=obs.record_sha256,
        )

    # Witness: the only source of "stopped".
    if wit is None or wit.seq < obs.seq:
        return Assessment(
            V_UNKNOWN,
            False,
            ("no stop witness after the last observation",),
            observation_sha256=obs.record_sha256,
        )
    wbody = wit.body
    if not _bound_identity_equal(wbody, body):
        return Assessment(
            V_UNKNOWN,
            False,
            ("witness not bound to the observed process",),
            observation_sha256=obs.record_sha256,
        )
    if not (
        is_observed(wbody, "bound_observation_sha256")
        and wbody["bound_observation_sha256"]["value"] == obs.record_sha256
        and is_observed(wbody, "ledger_sha256_recomputed")
    ):
        return Assessment(
            V_UNKNOWN,
            False,
            ("witness bound to another observation",),
            observation_sha256=obs.record_sha256,
        )
    if wbody["ledger_sha256_recomputed"]["value"] != current["ledger_sha256"]["value"]:
        return Assessment(
            V_STALE,
            False,
            ("ledger changed after the witness",),
            observation_sha256=obs.record_sha256,
        )
    stopped = wbody.get("process_stopped")
    if is_observed(wbody, "process_stopped") and stopped["value"] is False:
        return Assessment(
            V_RUNNING,
            False,
            ("witness saw a live holder or pid",),
            observation_sha256=obs.record_sha256,
        )
    if not is_observed(wbody, "process_stopped") or stopped["value"] is not True:
        return Assessment(
            V_UNKNOWN,
            False,
            ("process stop not established by the witness",),
            observation_sha256=obs.record_sha256,
        )

    unknowns = tuple(
        n
        for n in (
            "pending_order_count",
            "lifecycle_transitions_in_flight",
            "admissions_in_flight",
        )
        if not is_observed(body, n)
    )
    ledger_same_as_obs = (
        is_observed(body, "ledger_sha256")
        and body["ledger_sha256"]["value"] == current["ledger_sha256"]["value"]
    )
    sealed_ok = False
    if seal is not None:
        sb = seal.body
        # O.ledger == seal.ledger == witness.ledger == current ledger, all required.
        sealed_ok = (
            ledger_same_as_obs
            and is_observed(sb, "seals_record_sha256")
            and sb["seals_record_sha256"]["value"] == obs.record_sha256
            and is_observed(sb, "ledger_sha256")
            and sb["ledger_sha256"]["value"] == current["ledger_sha256"]["value"]
            and _bound_identity_equal(sb, body)
        )
    if not sealed_ok:
        miss = _missing(V_INTERRUPTED, body)
        if miss:
            return Assessment(
                V_UNKNOWN,
                False,
                ("identity/ledger/process fields incomplete",),
                miss,
                observation_sha256=obs.record_sha256,
            )
        return Assessment(
            V_INTERRUPTED,
            False,
            (
                "stopped without a valid seal"
                + (
                    ""
                    if ledger_same_as_obs
                    else "; ledger moved past the last observation"
                ),
            ),
            blocking=("no valid seal",),
            observation_sha256=obs.record_sha256,
            historical_unknowns=(
                "pending_order_count",
                "lifecycle_transitions_in_flight",
                "admissions_in_flight",
            ),
        )

    clean = is_observed(wbody, "exit_status") and wbody["exit_status"]["value"] == 0
    verdict = V_CLEAN_CONFIRMED if clean else V_SEALED_STOPPED
    miss = _missing(verdict, body)
    if miss:
        return Assessment(
            V_UNKNOWN,
            False,
            ("required fields not OBSERVED",),
            miss,
            observation_sha256=obs.record_sha256,
        )

    blocking: list[str] = []
    miss_q = _missing(V_QUIESCENT, body)
    blocking += [f"field {n} not OBSERVED" for n in miss_q]
    if body["gate_state"]["value"] != "CLOSED":
        blocking.append("gate not CLOSED")
    if body["durable_open_positions"]["value"] or current_open(root, manifest) != []:
        blocking.append("open positions (recorded or recomputed from the ledger now)")
    if body["durable_unresolved_positions"]["value"]:
        blocking.append("unresolved positions")
    if body["memory_matches_durable"]["value"] is not True:
        blocking.append("memory differs from durable")
    for n in ZERO_COUNTER_FIELDS:
        if _count(body.get(n)) != 0:
            blocking.append(f"{n} is not an OBSERVED zero")
    if not (
        is_observed(body, "runtime_consults_gate")
        and body["runtime_consults_gate"]["value"] is True
        and str(body["runtime_consults_gate"]["provenance"]).startswith(
            f"RUNTIME_DECLARATION:{GATE_WIRING_PROTOCOL}@"
        )
    ):
        blocking.append(
            "runtime does not consult the admission gate (not wired or unknown)"
        )
    return Assessment(
        verdict,
        not blocking,
        (),
        miss_q,
        tuple(blocking),
        obs.record_sha256,
        unknowns,
    )


def current_open(root: Path, manifest: Any) -> list[str]:
    """Open positions recomputed from the ledger now (``["?"]`` if unreadable)."""

    from paper_trading.durable_event_store import DurableEventStore
    from paper_trading.paper_portfolio_ledger import project

    try:
        events = DurableEventStore(root).load_epoch(manifest.paper_epoch_id)
        return sorted(project(events).open_positions.keys())
    except Exception:  # noqa: BLE001 - fail closed: any read failure is UNRESOLVED/UNKNOWN
        return ["?"]


# -------------------------------------------------------------------- adapters


def to_epoch_rotation_quiescence(
    assessment: Assessment, observation_body: Mapping[str, Any]
) -> Any:
    """Adapter for the existing ``EpochRotationQuiescence``.

    Refuses unless every field is a real OBSERVED measurement and the
    assessment is quiescent: ``UNKNOWN``/``NOT_APPLICABLE`` are never turned
    into ``0``/``False`` to satisfy the existing dataclass.
    """

    from paper_trading.ppl_authority_runtime import EpochRotationQuiescence

    if not assessment.quiescent:
        raise QuiescenceRefusal(
            "assessment is not quiescent: "
            + "; ".join(assessment.blocking or assessment.reasons)
        )
    pending = _count(observation_body.get("pending_order_count"))
    transitions = _count(observation_body.get("lifecycle_transitions_in_flight"))
    admissions = _count(observation_body.get("admissions_in_flight"))
    open_positions = observation_body.get("durable_open_positions")
    if (
        pending is None
        or transitions is None
        or admissions is None
        or not is_observed(observation_body, "durable_open_positions")
    ):
        raise QuiescenceRefusal("a required counter is not an OBSERVED measurement")
    if pending != 0 or transitions != 0 or admissions != 0:
        raise QuiescenceRefusal(
            "a counter is not zero: in-flight work is not quiescent"
        )
    return EpochRotationQuiescence(
        authority_open_positions=len(open_positions["value"]),
        authority_pending_orders=pending,
        authority_transitions_in_flight=transitions,
        authority_process_stopped=True,
    )


# ------------------------------------------------------------------ writers


def write_observation(
    store: ProofStore,
    body: Mapping[str, Any],
    *,
    now: float,
    max_age_s: float = 900.0,
    clock_provenance: str = "time.time() of the writing host",
) -> AppendResult:
    return store.append(
        KIND_OBSERVATION,
        body,
        observed_at=now,
        clock_provenance=clock_provenance,
        max_age_s=max_age_s,
    )


def _persisted_observation(
    store: ProofStore,
    observation: AppendResult,
    observation_body: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    """Body of the confirmed, latest OBSERVATION designated by ``observation``.

    Seals and witnesses are derived from the *persisted* record, never from a
    caller-supplied snapshot; a supplied body must equal it byte for byte.
    """

    chain = store.scan()
    if chain.status != "OK":
        raise QuiescenceRefusal(
            "proof chain is not readable: " + "; ".join(chain.reasons)
        )
    record = next((r for r in chain.records if r.seq == observation.seq), None)
    if (
        record is None
        or record.record_sha256 != observation.record_sha256
        or record.kind != KIND_OBSERVATION
    ):
        raise QuiescenceRefusal("designated record is not that OBSERVATION")
    if not record.confirmed:
        raise QuiescenceRefusal("designated OBSERVATION is not confirmed durable")
    latest = next(r for r in reversed(chain.records) if r.kind == KIND_OBSERVATION)
    if latest.seq != record.seq:
        raise QuiescenceRefusal(
            "a newer OBSERVATION exists: the designated one is superseded"
        )
    if observation_body is not None and canonical(dict(observation_body)) != canonical(
        dict(record.body)
    ):
        raise QuiescenceRefusal("supplied body is not the persisted OBSERVATION body")
    return record.body


def write_seal(
    store: ProofStore,
    observation: AppendResult,
    observation_body: Mapping[str, Any] | None = None,
    *,
    now: float,
    max_age_s: float = 900.0,
) -> AppendResult:
    """SENTINEL: the process states it sealed ``observation`` at its ledger digest.

    It is a statement, not an exit: a SIGKILL right after it leaves a sealed but
    not cleanly-exited process (``SEALED_THEN_STOPPED``, never ``CLEAN_STOP_CONFIRMED``).
    """

    observation_body = _persisted_observation(store, observation, observation_body)
    body: dict[str, Any] = {
        "seals_record_sha256": observed(
            observation.record_sha256, "OBSERVATION record sha"
        )
    }
    for name in ("ledger_sha256", *PROCESS_FIELDS):
        body[name] = dict(observation_body[name])
    body["exit_intent"] = observed(
        "SEALED", "process-written; does not assert that the process exited"
    )
    return store.append(
        KIND_SENTINEL,
        body,
        observed_at=now,
        clock_provenance="time.time() of the sealing process",
        max_age_s=max_age_s,
    )


def write_witness(
    store: ProofStore,
    observation: AppendResult,
    observation_body: Mapping[str, Any] | None = None,
    *,
    store_root: os.PathLike[str] | str,
    epoch_id: str,
    now: float,
    max_age_s: float = 900.0,
    exit_evidence: Mapping[str, Any] | None = None,
    proc_root: str = _DEFAULT_PROC,
    boot_id_path: str = _DEFAULT_BOOT_ID,
    witness_identity: str = "ppl_quiescence_proof.write_witness",
) -> AppendResult:
    """S: run by a separate process.  Read-only on the runtime and the authority store."""

    observation_body = _persisted_observation(store, observation, observation_body)
    probes = probe_stop_evidence(
        observation_body,
        exit_evidence=exit_evidence,
        proc_root=proc_root,
        boot_id_path=boot_id_path,
    )
    ledger = _ledger_fingerprint(Path(store_root), epoch_id)
    body: dict[str, Any] = dict(probes)
    for name in PROCESS_FIELDS:
        body[name] = dict(observation_body[name])
    body["bound_observation_sha256"] = observed(
        observation.record_sha256, "OBSERVATION record sha"
    )
    body["ledger_sha256_recomputed"] = (
        dict(ledger["ledger_sha256"])
        if is_observed(ledger, "ledger_sha256")
        else unknown("authority ledger not readable by the witness")
    )
    body["witness_identity"] = observed(
        f"{witness_identity}:pid{os.getpid()}", "witness process"
    )
    return store.append(
        KIND_WITNESS,
        body,
        observed_at=now,
        clock_provenance="time.time() of the witness host",
        max_age_s=max_age_s,
    )


__all__ = [
    "REQUIRED_FIELDS",
    "SCHEMA",
    "Assessment",
    "ChainView",
    "PersistBlocked",
    "PersistError",
    "PersistUncertain",
    "ProofStore",
    "QuiescenceRefusal",
    "assess",
    "current_process_identity",
    "observe_runtime",
    "probe_stop_evidence",
    "to_epoch_rotation_quiescence",
    "write_observation",
    "write_seal",
    "write_witness",
]
