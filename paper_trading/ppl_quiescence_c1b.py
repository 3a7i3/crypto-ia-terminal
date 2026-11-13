"""PPL-QUIESCENCE-01 lot C1b — opt-in Advisor wiring (contract v0).

``docs/contracts/PPL_QUIESCENCE_01_LOT_C1B.md``.  This module is imported by
``core/advisor_loop.py`` **only** when at least one C1b variable is set.  It:

* validates the three explicit paths (gate journal, proof directory, identity
  lock) without creating anything (§2, §3);
* holds a dedicated, never-written identity lock for the process lifetime (§5);
* builds the epoch's :class:`AdmissionGate` from the *bound* authority runtime
  and checks that the checkout's claimed HEAD equals ``manifest.code_sha``
  before it may be declared to the simulator (§4);
* installs flag-only SIGTERM/SIGINT handlers (§6);
* at an orderly stop, writes an OBSERVATION then a SENTINEL (lot A) and returns
  a typed outcome (§6).

It never opens, closes or drains the gate, never issues or validates an
activation clearance, never reads ``epoch_role``, ``PB_MAX_POSITIONS``, fees,
capital or strategy variables, and never sends notifications.  A git HEAD is a
``CLAIMED_ONLY`` statement, never an attestation of the imported bytes.
"""

from __future__ import annotations

import fcntl
import logging
import os
import re
import signal
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

_log = logging.getLogger(__name__)

ENV_GATE_JOURNAL = "PPL_ADMISSION_GATE_JOURNAL"
ENV_PROOF_DIR = "PPL_QUIESCENCE_PROOF_DIR"
ENV_IDENTITY_LOCK = "PPL_ADVISOR_IDENTITY_LOCK"
C1B_ENV_VARS = (ENV_GATE_JOURNAL, ENV_PROOF_DIR, ENV_IDENTITY_LOCK)
# Read only for overlap checks (never interpreted otherwise).
_ENV_STORE_ROOT = "PPL_AUTHORITY_STORE_ROOT"
_ENV_TRADE_LOG = "PAPER_TRADE_LOG"

CODE_PROVENANCE = "GIT_HEAD_AT_BOOT"
CODE_EVIDENCE_STATUS = "CLAIMED_ONLY"
_CODE_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")

# Shutdown outcomes (contract §6).
SEALED = "SEALED"
SEALED_RECEIPT_NOT_DURABLE = "SEALED_RECEIPT_NOT_DURABLE"
NO_SIMULATOR = "NO_SIMULATOR"
IDENTITY_LOCK_CHANGED = "IDENTITY_LOCK_CHANGED"
OBSERVATION_FAILED = "OBSERVATION_FAILED"
PROOF_STORE_REFUSED = "PROOF_STORE_REFUSED"
OBSERVATION_NOT_PERSISTED = "OBSERVATION_NOT_PERSISTED"
OBSERVATION_UNCERTAIN = "OBSERVATION_UNCERTAIN"
SEAL_NOT_PERSISTED = "SEAL_NOT_PERSISTED"
SEAL_UNCERTAIN = "SEAL_UNCERTAIN"
SEAL_REFUSED = "SEAL_REFUSED"
EXIT_PROOF_NOT_SEALED = 3


class C1bRefusal(RuntimeError):
    """C1b refuses to start: fail closed, before any service is started."""


class C1bConfigRefusal(C1bRefusal):
    """Missing, partial, inconsistent or unsafe C1b configuration."""


class C1bIdentityRefusal(C1bRefusal):
    """Code identity or process identity lock cannot be established."""


# ------------------------------------------------------------------ config


def c1b_requested(env: Mapping[str, str]) -> bool:
    return any(str(env.get(name, "") or "").strip() for name in C1B_ENV_VARS)


@dataclass(frozen=True)
class C1bConfig:
    gate_journal: Path
    proof_dir: Path
    identity_lock: Path

    @property
    def gate_dir(self) -> Path:
        return self.gate_journal.parent


def _strict_path(raw: str, what: str) -> Path:
    """Absolute, no ``..``, no symlink among existing components.  Read-only."""

    if not isinstance(raw, str) or not raw.strip():
        raise C1bConfigRefusal(f"{what}: path required")
    raw = raw.strip()
    if not os.path.isabs(raw):
        raise C1bConfigRefusal(f"{what}: path must be absolute")
    path = Path(raw)
    if ".." in path.parts:
        raise C1bConfigRefusal(f"{what}: '..' is not allowed")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            break  # the rest does not exist: nothing more to inspect
        except OSError as exc:
            raise C1bConfigRefusal(f"{what}: {current} not inspectable: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise C1bConfigRefusal(f"{what}: symbolic link at {current}")
    return Path(os.path.normpath(str(path)))


def _overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def load_c1b_config(
    env: Mapping[str, str], *, legacy_lock_path: Optional[str] = None
) -> Optional[C1bConfig]:
    """Validate the opt-in configuration without creating anything (§2, §3)."""

    values = {name: str(env.get(name, "") or "").strip() for name in C1B_ENV_VARS}
    present = [name for name, value in values.items() if value]
    if not present:
        return None
    if len(present) != len(C1B_ENV_VARS):
        missing = sorted(set(C1B_ENV_VARS) - set(present))
        raise C1bConfigRefusal(
            "partial C1b configuration (all three paths are required): missing "
            + ", ".join(missing)
        )
    cfg = C1bConfig(
        gate_journal=_strict_path(values[ENV_GATE_JOURNAL], ENV_GATE_JOURNAL),
        proof_dir=_strict_path(values[ENV_PROOF_DIR], ENV_PROOF_DIR),
        identity_lock=_strict_path(values[ENV_IDENTITY_LOCK], ENV_IDENTITY_LOCK),
    )
    for path, want, what in (
        (cfg.gate_journal, stat.S_ISREG, ENV_GATE_JOURNAL),
        (cfg.proof_dir, stat.S_ISDIR, ENV_PROOF_DIR),
        (cfg.identity_lock, stat.S_ISREG, ENV_IDENTITY_LOCK),
    ):
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            continue
        if not want(info.st_mode):
            raise C1bConfigRefusal(f"{what}: existing path has the wrong file type")
    try:
        parent = os.lstat(cfg.identity_lock.parent)
    except FileNotFoundError:
        raise C1bConfigRefusal(
            f"{ENV_IDENTITY_LOCK}: parent directory does not exist (not created)"
        ) from None
    if not stat.S_ISDIR(parent.st_mode):
        raise C1bConfigRefusal(f"{ENV_IDENTITY_LOCK}: parent is not a directory")

    areas: list[tuple[str, Path]] = [
        ("gate directory", cfg.gate_dir),
        ("proof directory", cfg.proof_dir),
        ("identity lock", cfg.identity_lock),
    ]
    store_root = str(env.get(_ENV_STORE_ROOT, "") or "").strip()
    if store_root:
        areas.append(
            ("authority store root", _strict_path(store_root, _ENV_STORE_ROOT))
        )
    trade_log = str(env.get(_ENV_TRADE_LOG, "") or "").strip()
    if trade_log:
        areas.append(("PAPER_TRADE_LOG", Path(os.path.abspath(trade_log))))
    if legacy_lock_path:
        areas.append(("legacy advisor lock", Path(os.path.abspath(legacy_lock_path))))
    for i, (name_a, a) in enumerate(areas):
        for name_b, b in areas[i + 1 :]:
            if _overlap(a, b):
                raise C1bConfigRefusal(f"{name_a} overlaps {name_b}: {a} / {b}")
    return cfg


# ---------------------------------------------------------- identity lock


class IdentityLock:
    """Dedicated process-identity lock: flock held for life, file never written.

    The Advisor never calls :meth:`close`; the kernel releases the flock when
    the process dies, whatever the cause.  ``close`` exists for tests only.
    """

    def __init__(self, path: Path, fd: int) -> None:
        self.path = path
        self.fd = fd
        self.identity = self._fstat_identity()

    @classmethod
    def acquire(cls, path: os.PathLike[str] | str) -> "IdentityLock":
        lock_path = Path(path)
        # O_NONBLOCK: a FIFO planted at the path must not hang the boot.
        flags = (
            os.O_RDONLY
            | os.O_CREAT
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise C1bIdentityRefusal(f"identity lock cannot be opened: {exc}") from exc
        try:
            held = os.fstat(fd)
            if not stat.S_ISREG(held.st_mode):
                raise C1bIdentityRefusal("identity lock is not a regular file")
            if held.st_mode & 0o022:
                raise C1bIdentityRefusal(
                    "identity lock is writable by group or others (mode %o)"
                    % stat.S_IMODE(held.st_mode)
                )
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise C1bIdentityRefusal(
                    f"identity lock is held by another process: {exc}"
                ) from exc
            current = os.lstat(lock_path)
            if not stat.S_ISREG(current.st_mode) or (held.st_dev, held.st_ino) != (
                current.st_dev,
                current.st_ino,
            ):
                raise C1bIdentityRefusal("identity lock path was replaced during open")
            return cls(lock_path, fd)
        except BaseException:
            os.close(fd)
            raise

    def _fstat_identity(self) -> tuple[int, int, int, int]:
        info = os.fstat(self.fd)
        return (info.st_dev, info.st_ino, info.st_ctime_ns, info.st_mtime_ns)

    def verify(self) -> tuple[bool, str]:
        """Is the path still the very file this process holds, unmodified?"""

        try:
            held = self._fstat_identity()
            current = os.lstat(self.path)
        except FileNotFoundError:
            return False, "identity lock path removed"
        except OSError as exc:
            return False, f"identity lock not inspectable: {exc}"
        if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
            return False, "identity lock path is not a regular file"
        now = (current.st_dev, current.st_ino, current.st_ctime_ns, current.st_mtime_ns)
        if (now[0], now[1]) != (held[0], held[1]):
            return False, "identity lock path replaced by another inode"
        if held != self.identity or now != self.identity:
            return False, "identity lock file metadata changed (ctime/mtime)"
        return True, ""

    def close(self) -> None:  # tests only
        fd, self.fd = self.fd, -1
        if fd >= 0:
            os.close(fd)


# ------------------------------------------------------------ stop signals


def _on_main_thread() -> bool:
    return threading.current_thread() is threading.main_thread()


class StopSignals:
    """Flag-only SIGTERM/SIGINT handlers (contract §6, amended by §13.1).

    The handler makes **no call at all**: one comparison and one attribute
    assignment.  It therefore takes no lock (neither directly nor through a
    callee), performs no I/O and raises nothing; it can neither deadlock on the
    non-reentrant ``simulator._lock`` nor on any synchronisation primitive the
    interrupted main thread may hold, and it cannot tear a durable transition by
    an asynchronous exception.  A reentrant burst of signals is harmless.

    Rev1: the original candidate used a threading event, whose ``set`` and
    ``wait`` take an internal lock; a signal landing while the main thread held
    it deadlocked (independent review R1).  Waiting is now a bounded polling
    loop outside the handler (``POLL_S``); ``time.sleep`` takes no Python lock
    and resumes after the handler runs (PEP 475).
    """

    HANDLED = (signal.SIGTERM, signal.SIGINT)
    POLL_S = 0.1  # bound on how late a stop is seen during ``wait`` (§13.1)

    def __init__(self) -> None:
        self._signum: Optional[int] = None
        self._previous: dict[int, Any] = {}

    def _handler(self, signum, frame) -> None:  # noqa: ARG002 - signal API
        if self._signum is None:  # the first signal received is kept
            self._signum = signum

    def install(self) -> None:
        """Transactional (rev2, contract §13.4): either every handler is
        installed, or none is left installed and the original exception is
        re-raised unchanged (same object, same traceback)."""
        if not _on_main_thread():
            raise C1bConfigRefusal("C1b stop handlers require the main thread")
        installed: dict[int, Any] = {}
        try:
            for sig in self.HANDLED:
                installed[sig] = signal.signal(sig, self._handler)
        except BaseException as exc:
            for sig, previous in reversed(list(installed.items())):
                try:
                    signal.signal(sig, previous)
                except BaseException as restore_exc:  # noqa: BLE001 - noted below
                    exc.add_note(
                        f"C1b: restoring signal {int(sig)} failed: {restore_exc!r}"
                    )
            raise
        self._previous = installed

    def restore(self) -> None:  # tests only
        for sig, previous in self._previous.items():
            signal.signal(sig, previous)
        self._previous.clear()

    @property
    def signum(self) -> Optional[int]:
        return self._signum

    @property
    def requested(self) -> bool:
        return self._signum is not None

    def wait(self, timeout: float) -> bool:
        """Bounded wait, outside any handler: True as soon as a stop is seen
        (at most ``POLL_S`` after the signal), False when ``timeout`` elapses."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while self._signum is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(self.POLL_S, remaining))
        return True


# ---------------------------------------------------------------- prepare


@dataclass
class C1bPrepared:
    """Result of the pre-authority step: config, identity lock, stop handlers."""

    config: C1bConfig
    identity_lock: IdentityLock
    signals: StopSignals


def prepare_from_env(
    env: Mapping[str, str], *, legacy_lock_path: Optional[str] = None
) -> Optional[C1bPrepared]:
    """Before the PPL authority bootstrap: validate, take the identity lock,
    install the stop handlers.  ``None`` when C1b is not configured.

    Refusal classes (contract §13.2): configuration and main-thread refusals
    create nothing; a refusal after the lock was opened may leave the created
    lock file (released, never deleted)."""

    cfg = load_c1b_config(env, legacy_lock_path=legacy_lock_path)
    if cfg is None:
        return None
    # Class 1 precondition (contract §13.2): checked before the identity lock is
    # opened, so this refusal creates nothing.
    if not _on_main_thread():
        raise C1bConfigRefusal("C1b stop handlers require the main thread")
    # Class 2 from here: the lock file may be created; it is never deleted.
    lock = IdentityLock.acquire(cfg.identity_lock)
    signals = StopSignals()
    try:
        signals.install()
    except BaseException:
        lock.close()
        raise
    _log.info(
        "[C1b] identity lock held: %s (dev=%s ino=%s); stop handlers installed",
        lock.path,
        lock.identity[0],
        lock.identity[1],
    )
    return C1bPrepared(cfg, lock, signals)


# ------------------------------------------------------------- code identity


@dataclass(frozen=True)
class CodeIdentity:
    code_sha: str
    worktree_state: str
    provenance: str = CODE_PROVENANCE
    evidence_status: str = CODE_EVIDENCE_STATUS  # never VERIFIED / ATTESTED


def resolve_code_identity(manifest: Any, capture_fn: Callable[[], Any]) -> CodeIdentity:
    """Claimed checkout HEAD, which must equal ``manifest.code_sha`` (§4).

    The value comes from ``capture_fn`` (git), never from the manifest: the
    manifest is only the comparand.
    """

    try:
        evidence = capture_fn()
    except Exception as exc:  # noqa: BLE001 - identity unknown: refuse
        raise C1bIdentityRefusal(f"source evidence capture failed: {exc}") from exc
    source_sha = getattr(evidence, "source_sha", None)
    worktree = getattr(evidence, "worktree_state", None)
    if not isinstance(source_sha, str) or not _CODE_SHA_RE.fullmatch(source_sha):
        raise C1bIdentityRefusal("checkout HEAD unknown or malformed")
    if worktree != "CLEAN":
        raise C1bIdentityRefusal(f"checkout worktree is not CLEAN ({worktree})")
    if source_sha != getattr(manifest, "code_sha", None):
        raise C1bIdentityRefusal(
            "checkout HEAD differs from the authority manifest code_sha"
        )
    return CodeIdentity(code_sha=source_sha, worktree_state=worktree)


# ------------------------------------------------------------------ wiring


@dataclass
class C1bWiring:
    prepared: C1bPrepared
    gate: Any
    code: CodeIdentity
    manifest: Any
    manifest_sha256: str
    store_root: Path
    gate_state_at_boot: str = "UNKNOWN"

    @property
    def stop_requested(self) -> bool:
        return self.prepared.signals.requested

    @property
    def stop_signum(self) -> Optional[int]:
        return self.prepared.signals.signum

    @property
    def stop_by_sigint(self) -> bool:
        """SIGINT keeps the existing "arrêté manuellement" message; SIGTERM
        sends none (notifications are not modified by C1b)."""
        return self.prepared.signals.signum == signal.SIGINT

    def wait_stop(self, timeout: float) -> bool:
        return self.prepared.signals.wait(timeout)

    def simulator_kwargs(self) -> dict[str, Any]:
        return {"admission_gate": self.gate, "gate_wiring_code_sha": self.code.code_sha}


def bind_wiring(
    prepared: C1bPrepared,
    authority: Any,
    runtime: Any,
    *,
    capture_fn: Callable[[], Any],
) -> C1bWiring:
    """After the PPL authority bootstrap: identities and gate (§4)."""

    from paper_trading.ppl_admission_gate import AdmissionGate
    from paper_trading.ppl_authority_runtime import authority_manifest_sha256

    if not getattr(authority, "ppl_is_authoritative", False):
        raise C1bConfigRefusal("C1b requires PAPER lifecycle authority PPL_AUTHORITY")
    if runtime is None:
        raise C1bConfigRefusal("C1b requires a bound PPL authority runtime")
    manifest = runtime.manifest
    store_root = Path(str(runtime.store._root))
    cfg = prepared.config
    for name, area in (
        ("gate directory", cfg.gate_dir),
        ("proof directory", cfg.proof_dir),
        ("identity lock", cfg.identity_lock),
    ):
        if _overlap(area, store_root) or _overlap(area, store_root.resolve()):
            raise C1bConfigRefusal(f"{name} overlaps the bound authority store root")
    code = resolve_code_identity(manifest, capture_fn)
    manifest_sha = authority_manifest_sha256(manifest)
    gate = AdmissionGate(
        cfg.gate_journal,
        paper_epoch_id=manifest.paper_epoch_id,
        manifest_sha256=manifest_sha,
    )
    try:
        state = str(gate.state())
    except Exception as exc:  # noqa: BLE001 - informative only, never blocking
        state = f"UNREADABLE ({type(exc).__name__})"
    if state != "OPEN":
        _log.critical(
            "[C1b] admission gate state at boot = %s: every OPEN will be refused "
            "(fail-closed); CLOSE stays possible.  A gate opening path for this "
            "epoch role is a governance decision (D-EPOCH-PATH), not done here.",
            state,
        )
    _log.info(
        "[C1b] wired: epoch=%s manifest_sha256=%s code_sha=%s provenance=%s (%s, "
        "not an attestation) gate=%s state=%s",
        manifest.paper_epoch_id,
        manifest_sha,
        code.code_sha,
        code.provenance,
        code.evidence_status,
        cfg.gate_journal,
        state,
    )
    return C1bWiring(
        prepared=prepared,
        gate=gate,
        code=code,
        manifest=manifest,
        manifest_sha256=manifest_sha,
        store_root=store_root,
        gate_state_at_boot=state,
    )


# ---------------------------------------------------------------- shutdown


@dataclass(frozen=True)
class ShutdownOutcome:
    status: str
    detail: str = ""
    observation_sha256: Optional[str] = None
    seal_sha256: Optional[str] = None
    hooks_seen: tuple[str, ...] = field(default_factory=tuple)

    @property
    def sealed(self) -> bool:
        """O and SENTINEL confirmed with a durable receipt.  This is a process
        statement, NOT an attested clean stop (only the external witness and
        ``assess`` can conclude ``SEALED_THEN_STOPPED``)."""

        return self.status == SEALED

    @property
    def exit_code(self) -> int:
        return 0 if self.sealed else EXIT_PROOF_NOT_SEALED


def shutdown_proof(
    wiring: C1bWiring,
    simulator: Any,
    runtime: Any,
    *,
    process_instance_id: str,
    now_fn: Callable[[], float] = time.time,
    hooks: Optional[Mapping[str, Callable[[], None]]] = None,
) -> ShutdownOutcome:
    """Orderly-stop proof: OBSERVATION then SENTINEL (contract §6).

    ``hooks`` is a test seam (``after_stop``, ``after_observation``,
    ``after_seal``); the Advisor never passes it.  No lock is held when the
    proof store's writer lock is taken.
    """

    from paper_trading import ppl_quiescence_proof as qp
    from paper_trading.durable_event_store import EventStoreError

    hooks = dict(hooks or {})
    seen: list[str] = []

    def hook(name: str) -> None:
        fn = hooks.get(name)
        if fn is not None:
            seen.append(name)
            fn()

    def out(status: str, detail: str = "", **kw: Any) -> ShutdownOutcome:
        level = logging.INFO if status == SEALED else logging.CRITICAL
        _log.log(level, "[C1b] shutdown proof: %s %s", status, detail)
        return ShutdownOutcome(status, detail, hooks_seen=tuple(seen), **kw)

    if simulator is None or runtime is None:
        return out(NO_SIMULATOR, "no simulator or authority runtime to observe")
    try:
        simulator.stop()
    except Exception as exc:  # noqa: BLE001 - stop() only clears a flag
        _log.warning("[C1b] simulator.stop() raised: %s", exc)
    hook("after_stop")

    lock = wiring.prepared.identity_lock
    same, why = lock.verify()
    if not same:
        return out(IDENTITY_LOCK_CHANGED, why)
    try:
        identity = qp.current_process_identity(
            process_instance_id=process_instance_id,
            lock_path=str(lock.path),
            lock_fd=lock.fd,
        )
        body = qp.observe_runtime(
            simulator,
            runtime,
            manifest=wiring.manifest,
            manifest_sha256=wiring.manifest_sha256,
            gate=wiring.gate,
            identity=identity,
            source_sha=wiring.code.code_sha,
        )
    except (qp.QuiescenceRefusal, EventStoreError, OSError, Exception) as exc:  # noqa: BLE001
        return out(OBSERVATION_FAILED, f"{type(exc).__name__}: {exc}")

    cfg = wiring.prepared.config
    try:
        store = qp.ProofStore(
            cfg.proof_dir, forbidden_roots=[wiring.store_root, cfg.gate_dir]
        )
    except (qp.PersistError, OSError) as exc:
        return out(PROOF_STORE_REFUSED, f"{type(exc).__name__}: {exc}")

    try:
        observation = qp.write_observation(store, body, now=now_fn())
    except qp.PersistUncertain as exc:
        return out(OBSERVATION_UNCERTAIN, str(exc))
    except (qp.PersistError, OSError) as exc:
        return out(OBSERVATION_NOT_PERSISTED, f"{type(exc).__name__}: {exc}")
    hook("after_observation")

    try:
        seal = qp.write_seal(store, observation, now=now_fn())
    except qp.PersistUncertain as exc:
        return out(
            SEAL_UNCERTAIN, str(exc), observation_sha256=observation.record_sha256
        )
    except qp.QuiescenceRefusal as exc:
        return out(SEAL_REFUSED, str(exc), observation_sha256=observation.record_sha256)
    except (qp.PersistError, OSError) as exc:
        return out(
            SEAL_NOT_PERSISTED,
            f"{type(exc).__name__}: {exc}",
            observation_sha256=observation.record_sha256,
        )
    hook("after_seal")
    status = SEALED if seal.receipt_durable else SEALED_RECEIPT_NOT_DURABLE
    return out(
        status,
        "sentinel written; this is not an attested stop (external witness required)",
        observation_sha256=observation.record_sha256,
        seal_sha256=seal.record_sha256,
    )


__all__ = [
    "C1B_ENV_VARS",
    "CODE_EVIDENCE_STATUS",
    "CODE_PROVENANCE",
    "ENV_GATE_JOURNAL",
    "ENV_IDENTITY_LOCK",
    "ENV_PROOF_DIR",
    "EXIT_PROOF_NOT_SEALED",
    "C1bConfig",
    "C1bConfigRefusal",
    "C1bIdentityRefusal",
    "C1bPrepared",
    "C1bRefusal",
    "C1bWiring",
    "CodeIdentity",
    "IdentityLock",
    "ShutdownOutcome",
    "StopSignals",
    "bind_wiring",
    "c1b_requested",
    "load_c1b_config",
    "prepare_from_env",
    "resolve_code_identity",
    "shutdown_proof",
]
