"""One-shot external witness. No runtime activation; see the lot B contract."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "PPL-EXTERNAL-WITNESS-RESULT-V2"
COORDINATION_SCHEMA = "PPL-WITNESS-COORDINATION-V1"
MIB = 1024 * 1024
TREE_BYTES = 16 * MIB
MAX_ENTRIES = 4096
OUTPUT_BYTES = 64 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COORD_KEYS = {
    "schema",
    "observation_sha256",
    "authority_store_root",
    "boot_id",
    "pid_namespace",
    "created_at",
    "expires_at",
    "operator",
    "reason",
    "start_paths_inhibited",
}


class Refusal(ValueError):
    """An explicit precondition is missing; no scientific inference is allowed."""


@dataclasses.dataclass(frozen=True)
class Request:
    manifest: str
    authority_root: str
    proof_dir: str
    coordination_file: str
    epoch: str
    observation_sha256: str
    timeout: float = 15.0
    max_age: float = 900.0


def _number(value: object, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Refusal("finite numeric limit required")
    if not minimum <= value <= maximum:
        raise Refusal("limit outside contract bounds")
    return float(value)


def _validate_request(request: Request) -> None:
    _number(request.timeout, 0.5, 60)
    _number(request.max_age, 0.001, 900)
    if not request.epoch or not _HEX.fullmatch(request.observation_sha256):
        raise Refusal("epoch and full observation SHA-256 required")
    for value in (
        request.manifest,
        request.authority_root,
        request.proof_dir,
        request.coordination_file,
    ):
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise Refusal("absolute paths required")


def _path(value: str, *, directory: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise Refusal("absolute path required")
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise Refusal("symlink path refused")
    info = path.lstat()
    wanted = stat.S_ISDIR if directory else stat.S_ISREG
    if not wanted(info.st_mode):
        raise Refusal("existing regular file/directory required")
    return path.resolve()


def _read(path: Path, maximum: int = MIB) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise Refusal("non-regular or oversized input")
        chunks = bytearray()
        while len(chunks) <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - len(chunks)))
            if not chunk:
                return bytes(chunks)
            chunks.extend(chunk)
        raise Refusal("input grew beyond size bound")
    finally:
        os.close(fd)


def _tree_budget(root: Path) -> None:
    total = count = 0
    pending = [(root, 0)]
    while pending:
        directory, depth = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise Refusal("tree entry bound exceeded")
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    if depth >= 4:
                        raise Refusal("tree depth bound exceeded")
                    pending.append((Path(entry.path), depth + 1))
                elif stat.S_ISREG(info.st_mode):
                    maximum = TREE_BYTES if entry.name.endswith(".jsonl") else MIB
                    if info.st_size > maximum:
                        raise Refusal("file size bound exceeded")
                    total += info.st_size
                    if total > TREE_BYTES:
                        raise Refusal("tree byte bound exceeded")
                else:
                    raise Refusal("non-regular tree entry")


def _overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _result(status: str, *, publication: str = "UNKNOWN", **extra: object) -> dict:
    return {
        "schema": SCHEMA,
        "command_status": status,
        "publication_state": publication,
        "quiescent": False,
        "operational_qualification": "NOT_QUALIFIED",
        "coordination_verified": False,
        **extra,
    }


def _coordination(request: Request, qp, now: float, *, budget_left: float = 0) -> str:
    raw = _read(_path(request.coordination_file))
    data = qp.strict_loads(raw)
    if not isinstance(data, dict) or set(data) != _COORD_KEYS:
        raise Refusal("coordination schema fields")
    if (
        data["schema"] != COORDINATION_SCHEMA
        or data["observation_sha256"] != request.observation_sha256
        or data["authority_store_root"] != str(Path(request.authority_root).resolve())
        or data["boot_id"] != qp.read_boot_id()
        or data["pid_namespace"] != qp.read_pid_namespace()
        or not data["boot_id"]
        or not data["pid_namespace"]
        or data["start_paths_inhibited"] is not True
    ):
        raise Refusal("coordination binding or declaration invalid")
    for name in ("operator", "reason"):
        if not isinstance(data[name], str) or not data[name].strip():
            raise Refusal("coordination author/reason required")
    created = _number(data["created_at"], 0, now)
    expiry = _number(data["expires_at"], 0, now + 900)
    if expiry <= now or not 0 < expiry - created <= 900:
        raise Refusal("coordination expired or lifetime invalid")
    if expiry <= now + budget_left + 0.1:
        raise Refusal("coordination window cannot cover remaining deadline")
    return hashlib.sha256(raw).hexdigest()


def _package_digest() -> str:
    """Exact Python source tree fingerprint, distinct from any observed code SHA."""
    root = Path(__file__).resolve().parents[1]
    files = {}
    for package in ("paper_trading", "execution_simulator"):
        for path in sorted((root / package).glob("*.py")):
            files[path.relative_to(root).as_posix()] = hashlib.sha256(
                _read(path)
            ).hexdigest()
    raw = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclasses.dataclass
class PublicationGuard:
    request: Request
    parent_pid: int
    deadline: float
    coordination_sha: str | None = None
    observation: object = None
    sample_started_at: float | None = None

    def check(self, qp, store=None) -> None:
        if os.getppid() != self.parent_pid:
            raise Refusal("caller disappeared or parent identity changed")
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise Refusal("worker deadline expired before publication")
        now = time.time()
        digest = _coordination(self.request, qp, now, budget_left=left)
        if self.coordination_sha is not None and digest != self.coordination_sha:
            raise Refusal("coordination changed")
        if self.observation is not None:
            age = now - self.observation.observed_at
            if age < 0 or age > min(
                self.request.max_age, self.observation.envelope["max_age_s"]
            ):
                raise Refusal("observation stale or future before publication")
        if store is not None:
            _tree_budget(store.directory)
            chain = store.scan()
            if chain.status != "OK":
                raise Refusal("proof chain UNRESOLVED before publication")
            if not chain.all_confirmed:
                raise Refusal("proof chain UNCONFIRMED before publication")
            observations = [r for r in chain.records if r.kind == qp.KIND_OBSERVATION]
            if (
                not observations
                or observations[-1].record_sha256 != self.request.observation_sha256
            ):
                raise Refusal("observation superseded before publication")


def _publication_store(qp, proof: Path, root: Path, guard: PublicationGuard):
    """B-only extension of A's publication hooks; no mutation of A's code."""

    class WitnessStore(qp.ProofStore):
        publication = "NOT_PUBLISHED"
        witness = None

        def _acquire_writer_lock(self):
            fd = super()._acquire_writer_lock()
            try:
                guard.check(qp, self)
            except BaseException:
                os.close(fd)
                raise
            return fd

        def append(self, kind, body, **kwargs):
            if kind != qp.KIND_WITNESS:
                raise Refusal("external witness cannot write O or SENTINEL")
            guard.check(qp, self)
            body = {
                **body,
                "coordination_verified": qp.observed(
                    False, "declaration only; not independently verified"
                ),
                "operational_qualification": qp.observed(
                    "NOT_QUALIFIED", "lot B source-only contract v2"
                ),
                "coordination_sha256": qp.observed(
                    guard.coordination_sha, "exact coordination bytes"
                ),
                "witness_sample_started_at": qp.observed(
                    guard.sample_started_at, "worker time.time before native probes"
                ),
                "witness_sample_completed_at": qp.observed(
                    time.time(), "worker time.time after native probes and ledger read"
                ),
                "worker_deadline_monotonic": qp.observed(
                    guard.deadline,
                    "time.monotonic; bound to witness_boot_id, not the observed process boot",
                ),
                "witness_boot_id": qp.observed(
                    qp.read_boot_id(), "current witness host boot id"
                ),
                "witness_parent_pid": qp.observed(
                    guard.parent_pid,
                    "expected launcher checked with getppid and PDEATHSIG",
                ),
                "publication_guard_atomic": qp.observed(
                    False,
                    "parent/deadline check immediately before link is not an atomic transaction with process death",
                ),
            }
            result = super().append(kind, body, **kwargs)
            self.publication = "CONFIRMED"
            self.witness["receipt_durable"] = result.receipt_durable
            return result

        def _link(self, source, target):
            if target.suffix == ".json":
                # Under A's writer flock, after all blocking waits and file fsync.
                guard.check(qp, self)
                envelope = qp.strict_loads(_read(source))
                if envelope["kind"] != qp.KIND_WITNESS:
                    raise Refusal("external witness cannot publish O or SENTINEL")
                guard.check(qp)
                super()._link(source, target)
                self.publication = "VISIBLE_UNCONFIRMED"
                self.witness = {
                    "seq": envelope["seq"],
                    "sha256": envelope["record_sha256"],
                    "receipt_durable": False,
                }
            else:
                # Completing a receipt for an already-visible record isn't a new sample.
                super()._link(source, target)
                if self.witness is not None:
                    self.publication = "CONFIRMED"

    return WitnessStore(proof, forbidden_roots=[root])


def _measurement_code(result: dict) -> int:
    if result["witness"]["receipt_durable"] is not True:
        return 11
    if result["quiescent"] is not True:
        return 10
    if result["coordination_verified"] is not True:
        return 12
    return 0  # Reserved: unreachable for this declarative-only witness.


def _measure(
    request: Request, *, guard: PublicationGuard | None = None
) -> tuple[dict, int]:
    # Lazy imports: no runtime constructor, dotenv, market client or Advisor.
    from paper_trading import ppl_quiescence_proof as qp
    from paper_trading.ppl_authority_runtime import (
        AuthorityManifestError,
        authority_manifest_sha256,
        load_authority_manifest,
    )

    store = None
    if guard is None:
        guard = PublicationGuard(
            request, os.getppid(), time.monotonic() + request.timeout
        )

    def facts():
        return {
            "publication": store.publication if store else "NOT_PUBLISHED",
            "witness": dict(store.witness) if store and store.witness else None,
        }

    def refused(exc):
        known = facts()
        published = known["publication"] in ("CONFIRMED", "VISIBLE_UNCONFIRMED")
        return _result(
            "PUBLISHED_UNVALIDATED" if published else "REFUSED",
            **known,
            error_type=type(exc).__name__,
            reason=str(exc)[:512],
        ), 21 if published else 20

    try:
        _validate_request(request)
        root = _path(request.authority_root, directory=True)
        proof = _path(request.proof_dir, directory=True)
        if _overlap(root, proof):
            raise Refusal("proof directory overlaps authority")
        _tree_budget(root)
        _tree_budget(proof)
        _path(str(root / ".ppl-event-store.lock"))
        manifest_path = _path(request.manifest)
        raw = _read(manifest_path)
        qp.strict_loads(raw)  # reject duplicate keys and non-finite JSON first
        manifest = load_authority_manifest(manifest_path)
        manifest_sha = authority_manifest_sha256(manifest)
        if hashlib.sha256(raw).hexdigest() != manifest_sha:
            raise Refusal("manifest bytes differ from native identity")
        if manifest.paper_epoch_id != request.epoch:
            raise Refusal("manifest epoch differs")
        guard.check(qp)
        store = _publication_store(qp, proof, root, guard)
        chain = store.scan()
        if chain.status != "OK":
            raise Refusal("proof chain UNRESOLVED")
        if not chain.all_confirmed:
            raise Refusal("proof chain UNCONFIRMED")
        observations = [r for r in chain.records if r.kind == qp.KIND_OBSERVATION]
        if (
            not observations
            or observations[-1].record_sha256 != request.observation_sha256
        ):
            raise Refusal("designated observation is not the latest")
        observation = observations[-1]
        guard.observation = observation
        body = observation.body
        expected = {
            "paper_epoch_id": request.epoch,
            "manifest_sha256": manifest_sha,
            "authority_store_root": str(root),
            "code_sha": manifest.code_sha,
            "config_snapshot_hash": manifest.config_snapshot_hash,
        }
        for name, value in expected.items():
            if not qp.is_observed(body, name) or body[name]["value"] != value:
                raise Refusal("observation binding differs: " + name)
        if qp.observed_value(body, "pid") == os.getpid():
            raise Refusal("witness must be a distinct process")
        now = time.time()
        age = now - observation.observed_at
        if age < 0 or age > min(request.max_age, observation.envelope["max_age_s"]):
            raise Refusal("observation stale or future")
        coordination_sha = _coordination(
            request, qp, now, budget_left=guard.deadline - time.monotonic()
        )
        guard.coordination_sha = coordination_sha
        package_sha = _package_digest()
        # Recheck immediately before publication. No automated recovery of old records.
        _tree_budget(root)
        _tree_budget(proof)
        if _coordination(request, qp, time.time()) != coordination_sha:
            raise Refusal("coordination changed during preflight")
        target = qp.AppendResult(
            observation.seq,
            observation.record_sha256,
            proof / qp._record_name(observation.seq, observation.record_sha256, "json"),
        )
        guard.sample_started_at = time.time()
        witness = qp.write_witness(
            store,
            target,
            store_root=root,
            epoch_id=request.epoch,
            now=guard.sample_started_at,
            max_age_s=request.max_age,
            witness_identity=f"PPL-EXTERNAL-WITNESS-V2:package={package_sha}:coord={coordination_sha}",
        )
        assessment = qp.assess(
            store,
            manifest=manifest,
            manifest_sha256=manifest_sha,
            store_root=root,
            now=time.time(),
            max_age_s=request.max_age,
        )
        reread = store.scan()
        last_o = [r for r in reread.records if r.kind == qp.KIND_OBSERVATION]
        records = [
            r for r in reread.records if r.record_sha256 == witness.record_sha256
        ]
        if (
            reread.status != "OK"
            or not reread.all_confirmed
            or not last_o
            or last_o[-1].record_sha256 != request.observation_sha256
            or len(records) != 1
            or records[0].kind != qp.KIND_WITNESS
            or reread.records[-1].record_sha256 != witness.record_sha256
            or qp.observed_value(records[0].body, "bound_observation_sha256")
            != request.observation_sha256
        ):
            raise Refusal("published witness cannot be confirmed against latest O")
        if _coordination(request, qp, time.time()) != coordination_sha:
            raise Refusal("coordination changed after publication")
        result = _result(
            "COMPLETED",
            publication="CONFIRMED",
            witness={
                "seq": witness.seq,
                "sha256": witness.record_sha256,
                "receipt_durable": witness.receipt_durable,
            },
            observation_sha256=request.observation_sha256,
            assessment=dataclasses.asdict(assessment),
            quiescent=assessment.quiescent,
            witness_package_sha256=package_sha,
            coordination_sha256=coordination_sha,
            measured_at=time.time(),
            clock_provenance="worker time.time(); parent monotonic deadline",
            limitations=[
                "coordination is declared, not independently verified",
                "stop is observed at T; later restart not excluded",
                "no independent supervisor exit status",
                "logical read only; native store opens existing lock a+b",
            ],
        )
        return result, _measurement_code(result)
    except qp.PersistUncertain as exc:
        known = facts()
        known["publication"] = "VISIBLE_UNCONFIRMED"
        known["witness"] = {
            "seq": exc.seq,
            "sha256": exc.record_sha256,
            "receipt_durable": False,
        }
        return _result("PERSISTENCE_ERROR", **known, error_type=type(exc).__name__), 30
    except qp.PersistError as exc:
        return _result(
            "PERSISTENCE_ERROR", **facts(), error_type=type(exc).__name__
        ), 30
    except OSError as exc:
        known = facts()
        if known["publication"] != "NOT_PUBLISHED":
            return _result(
                "PUBLISHED_UNVALIDATED", **known, error_type=type(exc).__name__
            ), 21
        return _result("IO_ERROR", **known, error_type=type(exc).__name__), 31
    except (
        Refusal,
        qp.QuiescenceRefusal,
        AuthorityManifestError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        return refused(exc)


def _arm_worker(parent_pid: int, deadline: float) -> None:
    """Also used by direct synthetic worker tests; production arms before imports."""
    import ctypes

    if sys.platform != "linux":
        raise Refusal("Linux parent-death guard required")
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise Refusal("cannot arm parent-death guard")
    if os.getppid() != parent_pid:
        os._exit(50)
    left = deadline - time.monotonic()
    if left <= 0:
        os._exit(40)
    signal.signal(signal.SIGALRM, lambda signum, frame: os._exit(40))
    signal.setitimer(signal.ITIMER_REAL, left)


def _worker(
    request: Request, *, parent_pid: int | None = None, deadline: float | None = None
) -> int:
    import resource

    parent_pid = os.getppid() if parent_pid is None else parent_pid
    deadline = time.monotonic() + request.timeout if deadline is None else deadline
    _arm_worker(parent_pid, deadline)
    _validate_request(request)
    resource.setrlimit(resource.RLIMIT_AS, (512 * MIB, 512 * MIB))
    cpu = math.ceil(request.timeout) + 2
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MIB, MIB))

    def no_network(event: str, args: tuple) -> None:
        if event.startswith("socket."):
            raise Refusal("network forbidden in witness")
        if event in ("subprocess.Popen", "os.fork", "os.forkpty", "os.posix_spawn"):
            raise Refusal("worker may not create descendants")

    sys.addaudithook(no_network)
    result, code = _measure(
        request, guard=PublicationGuard(request, parent_pid, deadline)
    )
    encoded = json.dumps(result, allow_nan=False, sort_keys=True)
    if len(encoded.encode()) > OUTPUT_BYTES:
        raise Refusal("result exceeds output bound")
    print(encoded)
    return code


def run(request: Request) -> tuple[dict, int]:
    """Parent: bounded worker lifetime, file-backed output, no native ledger read."""
    try:
        _validate_request(request)
    except (Refusal, TypeError, ValueError) as exc:
        return _result("REFUSED", publication="NOT_PUBLISHED", reason=str(exc)), 20
    deadline = time.monotonic() + request.timeout
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="ppl-witness-") as directory:
            stdout = Path(directory) / "stdout"
            stderr = Path(directory) / "stderr"
            root = str(Path(__file__).resolve().parents[1])
            # Arm before package imports. If the parent died before prctl, the
            # expected-parent comparison refuses the adopted worker before work.
            script = "\n".join(
                [
                    "import os,sys,time,signal,ctypes,json",
                    "parent=int(sys.argv[2]); deadline=float(sys.argv[3])",
                    "libc=ctypes.CDLL(None,use_errno=True)",
                    "if libc.prctl(1,signal.SIGKILL,0,0,0)!=0: os._exit(50)",
                    "if os.getppid()!=parent: os._exit(50)",
                    "left=deadline-time.monotonic()",
                    "if left<=0: os._exit(40)",
                    "signal.signal(signal.SIGALRM,lambda s,f:os._exit(40))",
                    "signal.setitimer(signal.ITIMER_REAL,left)",
                    "sys.path.insert(0," + repr(root) + ")",
                    "from paper_trading.ppl_quiescence_witness import Request,_worker",
                    "sys.exit(_worker(Request(**json.loads(sys.argv[1])),parent_pid=parent,deadline=deadline))",
                ]
            )
            try:
                with stdout.open("wb") as out, stderr.open("wb") as err:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-I",
                            "-B",
                            "-c",
                            script,
                            json.dumps(dataclasses.asdict(request), allow_nan=False),
                            str(os.getpid()),
                            str(deadline),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=out,
                        stderr=err,
                        start_new_session=True,
                        env={
                            "PATH": "/usr/bin:/bin",
                            "LANG": "C.UTF-8",
                            "TZ": "UTC",
                            "PYTHONDONTWRITEBYTECODE": "1",
                        },
                    )
                    try:
                        process.wait(timeout=max(0.001, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        return _result("TIMEOUT"), 40
                raw = _read(stdout, OUTPUT_BYTES)
                if process.returncode == 40:
                    return _result("TIMEOUT"), 40
                try:
                    result = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    return _result("WORKER_ERROR", returncode=process.returncode), 50
                if (
                    not isinstance(result, dict)
                    or result.get("schema") != SCHEMA
                    or process.returncode not in (0, 10, 11, 12, 20, 21, 30, 31)
                ):
                    return _result("WORKER_ERROR", returncode=process.returncode), 50
                return result, process.returncode
            finally:
                if process is not None and process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=2)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return _result(
            "WORKER_ERROR",
            publication="NOT_PUBLISHED" if process is None else "UNKNOWN",
            error_type=type(exc).__name__,
        ), 50


def main(argv: list[str] | None = None) -> int:
    class Parser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            raise Refusal(message)

    parser = Parser(description=__doc__)
    for name in (
        "manifest",
        "authority-root",
        "proof-dir",
        "coordination-file",
        "epoch",
        "observation-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--max-age", type=float, default=900.0)
    try:
        args = parser.parse_args(argv)
        result, code = run(Request(**vars(args)))
    except Refusal as exc:
        result, code = (
            _result("REFUSED", publication="NOT_PUBLISHED", reason=str(exc)),
            20,
        )
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
