"""MEO-04 durable store: immutable proofs, append-only import journal, derived SQLite index.

Authority and derivation
    The proofs (content addressed by SHA-256) and the import journal are the
    authority. SQLite is a derived index: it can be dropped and rebuilt from the
    journal and the proofs, and it can neither create nor remove an import.

Layout under one explicit private root (created by ``init``, outside the repository)
    meo-memory-root.json        partition (HISTORICAL or SYNTHETIC) and byte budget
    writer.lock                 single-writer lock (flock)
    proofs/<hh>/<sha256>        immutable proof bytes, mode 0400
    journal/<seq:012d>.json     immutable import records; seq = local knowledge sequence
    tmp/                        temporary files (same filesystem); leftovers are orphans
    index/memory.sqlite         derived index; retired indexes are renamed, never deleted

Publication order of one import (serialized by the writer lock)
    proofs: temp file -> fsync -> link without replace -> fsync directory;
    record: temp file -> fsync -> link without replace -> fsync directory;
    index: one SQLite transaction (synchronous=FULL) -> acknowledgement.
    A failed directory fsync is PUBLICATION_UNCERTAIN: nothing is acknowledged.

Visibility boundary
    A reader sees an import only when its record is in the verified journal AND
    the index head equals the journal head. Otherwise reads are refused with
    INDEX_INCONSISTENT: a partial view is never served as complete. ``recover``
    (writer) re-syncs the journal directory, verifies the pending records and
    their proofs, and brings the index to the journal head, or rebuilds it.
"""

from __future__ import annotations

import fcntl
import os
import re
import secrets
import sqlite3
import stat
import tarfile
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from observability.operator_api.bounded_file import read_regular_file
from observability.radar_selection import refs
from observability.radar_selection.fixture import RadarRefusal

from . import canon as c
from . import engine
from .canon import MemoryRefusal

ROOT_SCHEMA = "meo-memory-root/1"
RECORD_SCHEMA = "meo-memory-import/1"
INDEX_SCHEMA = "meo-memory-index/1"
PRODUCER = "meo-memory/0.1"
MARKER = "meo-memory-root.json"
LOCK = "writer.lock"
SUBDIRS = ("proofs", "journal", "tmp", "index")
INDEX = "memory.sqlite"
REPO_ROOT = Path(__file__).resolve().parents[2]
MiB = 1024 * 1024
_JOURNAL_NAME = re.compile(r"[0-9]{12}\.json")
_HEX = re.compile(r"[0-9a-f]{64}")
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_NEW_FILE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
INT64_MAX = 2 ** 63 - 1
# Proofs every import record must reference (RV01-02). Every other recorded proof (archive, SHA256SUMS,
# preflight, source reports) is mandatory too once recorded: a record never lists an optional proof.
REQUIRED_ROLES = ("events.jsonl", "frames.bin", "manifest.json", "reading", "replay-report")
_PAGE = 4096
_EMPTY_INDEX_BYTES = 12 * _PAGE   # schema of an empty index (4 tables, 2 indexes, 4 automatic indexes)
_ROW_BYTES = 1024                 # pre-check allowance per indexed row


@dataclass(frozen=True)
class Limits:
    """Explicit ceilings (bytes, counts). Every one of them refuses rather than truncates."""
    manifest_bytes: int = 64 * 1024
    journal_bytes: int = 64 * MiB          # events.jsonl and frames.bin, each
    small_member_bytes: int = 8 * MiB      # reports, preflight, SHA256SUMS, reading
    archive_bytes: int = 128 * MiB
    archive_members: int = 16
    import_bytes: int = 192 * MiB          # all inputs of one import, archive included
    record_bytes: int = 4 * MiB
    journal_records: int = 10_000
    root_entries: int = 200_000
    reserve_bytes: int = 16 * MiB          # kept free inside the root budget
    default_budget_bytes: int = 1024 * MiB
    max_budget_bytes: int = 2048 * MiB
    page_default: int = 20
    page_max: int = 100
    sessions_per_read: int = 256           # sessions re-verified against their proofs by one read
    proof_bytes_per_check: int = 512 * MiB  # proof bytes hashed by one verification pass (all sessions of K)


LIMITS = Limits()


class SimulatedCrash(BaseException):
    """Raised by a test fault hook to stop the writer at a named boundary."""


def _fsync_dir(fd: int) -> None:
    os.fsync(fd)


def _member_cap(name: str, limits: Limits) -> int:
    if name == "manifest.json":
        return limits.manifest_bytes
    if name in ("events.jsonl", "frames.bin"):
        return limits.journal_bytes
    return limits.small_member_bytes


def check_root_path(root) -> str:
    """The root must be an absolute, canonical, private directory outside the repository."""
    p = os.fspath(root)
    if not os.path.isabs(p):
        raise MemoryRefusal(c.INVALID_REQUEST, "ROOT_NOT_ABSOLUTE")
    if os.path.realpath(p) != os.path.normpath(p):
        raise MemoryRefusal(c.NOT_CONFIGURED, "ROOT_PATH_NOT_CANONICAL")
    real = os.path.normpath(p)
    repo = str(REPO_ROOT)
    if real == repo or real.startswith(repo + os.sep):
        raise MemoryRefusal(c.INVALID_REQUEST, "ROOT_INSIDE_REPOSITORY")
    try:
        st = os.lstat(real)
    except FileNotFoundError:
        raise MemoryRefusal(c.NOT_CONFIGURED, "ROOT_MISSING") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise MemoryRefusal(c.NOT_CONFIGURED, "ROOT_NOT_A_DIRECTORY")
    if st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise MemoryRefusal(c.NOT_CONFIGURED, "ROOT_NOT_PRIVATE")
    return real


def init_root(root, partition: str, budget_bytes: int | None = None, limits: Limits = LIMITS) -> dict:
    """Create the layout of an empty private root. Never touches an existing non-empty directory."""
    if partition not in c.PARTITIONS:
        raise MemoryRefusal(c.INVALID_REQUEST, "PARTITION_UNKNOWN")
    budget = limits.default_budget_bytes if budget_bytes is None else budget_bytes
    if not (limits.reserve_bytes < budget <= limits.max_budget_bytes):
        raise MemoryRefusal(c.INVALID_REQUEST, "BUDGET_OUT_OF_RANGE")
    p = os.fspath(root)
    if os.path.isabs(p) and not os.path.lexists(p):
        parent = os.path.dirname(os.path.normpath(p))
        if os.path.realpath(parent) != parent:
            raise MemoryRefusal(c.NOT_CONFIGURED, "ROOT_PATH_NOT_CANONICAL")
        if parent == str(REPO_ROOT) or parent.startswith(str(REPO_ROOT) + os.sep):
            raise MemoryRefusal(c.INVALID_REQUEST, "ROOT_INSIDE_REPOSITORY")
        os.mkdir(p, 0o700)
    real = check_root_path(p)
    marker = {"schema": ROOT_SCHEMA, "partition": partition, "budget_bytes": budget}
    rootfd = os.open(real, _DIR_FLAGS)
    try:
        existing = sorted(os.listdir(rootfd))
        if existing:
            if existing == sorted((MARKER, LOCK) + SUBDIRS):
                current = Store(real, limits=limits).marker
                if current == marker:
                    return {"result": "NO_OP", "marker": marker}
            raise MemoryRefusal(c.INVALID_REQUEST, "ROOT_NOT_EMPTY")
        for d in SUBDIRS:
            os.mkdir(d, 0o700, dir_fd=rootfd)
        fd = os.open(LOCK, _NEW_FILE, 0o600, dir_fd=rootfd)
        os.close(fd)
        fd = os.open(MARKER, _NEW_FILE, 0o400, dir_fd=rootfd)
        with os.fdopen(fd, "wb") as fh:
            fh.write(c.canonical(marker))
            fh.flush()
            os.fsync(fh.fileno())
        _fsync_dir(rootfd)
    finally:
        os.close(rootfd)
    index = Store(real, limits=limits).recover()  # empty derived index, so a refused import writes nothing
    return {"result": "INITIALIZED", "marker": marker, "index": index["action"]}


class Store:
    """Open view of one initialized root. Readers use it as is; the writer takes the lock."""

    def __init__(self, root, *, limits: Limits = LIMITS, fault=None):
        self.root = check_root_path(root)
        self.limits = limits
        self._fault = fault
        self.warnings: list = []
        try:
            refs.evidence_root(self.root)
        except RadarRefusal:
            raise MemoryRefusal(c.NOT_CONFIGURED, "ROOT_NOT_A_DIRECTORY") from None
        try:
            raw = self._read_ref(MARKER, 4096)
        except MemoryRefusal as exc:
            raise MemoryRefusal(c.NOT_CONFIGURED, "MARKER_" + exc.category) from None
        marker = c.strict_json(raw, c.NOT_CONFIGURED)
        if not isinstance(marker, dict) or marker.get("schema") != ROOT_SCHEMA \
                or marker.get("partition") not in c.PARTITIONS or type(marker.get("budget_bytes")) is not int:
            raise MemoryRefusal(c.NOT_CONFIGURED, "MARKER_INVALID")
        for d in SUBDIRS:
            try:
                st = os.lstat(os.path.join(self.root, d))
            except FileNotFoundError:
                raise MemoryRefusal(c.NOT_CONFIGURED, "LAYOUT_MISSING:" + d) from None
            if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise MemoryRefusal(c.NOT_CONFIGURED, "LAYOUT_INVALID:" + d)
        self.marker = marker
        self.partition = marker["partition"]

    # ------------------------------------------------------------------ low level
    def _cp(self, name: str) -> None:
        if self._fault is not None:
            self._fault(name)

    def _read_ref(self, ref: str, max_bytes: int) -> bytes:
        try:
            return refs.read_ref(self.root, ref, max_bytes)
        except RadarRefusal as exc:
            code = str(exc).split(":", 1)[0]
            if code == "REF_MISSING":
                raise MemoryRefusal(c.PROOF_UNAVAILABLE, ref) from None
            if code.startswith("EVIDENCE_ROOT"):
                raise MemoryRefusal(c.NOT_CONFIGURED, code) from None
            raise MemoryRefusal(c.PROOF_CORRUPT, f"{code}:{ref}") from None

    def _open_dir(self, *parts: str) -> int:
        fd = os.open(self.root, _DIR_FLAGS)
        try:
            for part in parts:
                nxt = os.open(part, _DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = nxt
        except OSError:
            os.close(fd)
            raise MemoryRefusal(c.PROOF_CORRUPT, "LAYOUT_UNSAFE:" + "/".join(parts)) from None
        return fd

    def read_proof(self, ref: dict) -> bytes:
        sha, size = ref["sha256"], ref["bytes"]
        if not _HEX.fullmatch(sha) or type(size) is not int or size < 0:
            raise MemoryRefusal(c.PROOF_CORRUPT, "PROOF_REF_INVALID")
        data = self._read_ref(f"proofs/{sha[:2]}/{sha}", size)
        if len(data) != size or c.sha256(data) != sha:
            raise MemoryRefusal(c.PROOF_CORRUPT, "PROOF_HASH_MISMATCH:" + sha)
        return data

    # ------------------------------------------------------------------ journal (authority)
    def load_journal(self) -> list:
        """Verified import records in knowledge order: [(record, record_sha256), ...]."""
        fd = self._open_dir("journal")
        try:
            names = os.listdir(fd)
        finally:
            os.close(fd)
        if len(names) > self.limits.journal_records:
            raise MemoryRefusal(c.BUDGET_EXCEEDED, "JOURNAL_RECORDS")
        if any(not _JOURNAL_NAME.fullmatch(n) for n in names):
            raise MemoryRefusal(c.PROOF_CORRUPT, "JOURNAL_UNEXPECTED_ENTRY")
        seqs = sorted(int(n[:12]) for n in names)
        if seqs != list(range(1, len(seqs) + 1)):
            raise MemoryRefusal(c.PROOF_UNAVAILABLE, "JOURNAL_GAP")
        out, prev = [], None
        for seq in seqs:
            raw = self._read_ref(f"journal/{seq:012d}.json", self.limits.record_bytes)
            rec = c.strict_json(raw, c.PROOF_CORRUPT)
            if c.canonical(rec) != raw or not isinstance(rec, dict) or rec.get("schema") != RECORD_SCHEMA:
                raise MemoryRefusal(c.PROOF_CORRUPT, f"RECORD_NOT_CANONICAL:{seq}")
            if rec.get("knowledge_seq") != seq or rec.get("predecessor_sha256") != prev \
                    or rec.get("partition") != self.partition:
                raise MemoryRefusal(c.PROOF_CORRUPT, f"RECORD_CHAIN_BROKEN:{seq}")
            prev = c.sha256(raw)
            out.append((rec, prev))
        return out

    def session_parts(self, rec: dict, budget: list | None = None) -> dict:
        """Verify EVERY proof of one record (availability, size, SHA-256), the links between the record,
        its proofs and its reading, then re-derive the session from the reading proof (RV01-02).

        ``budget`` is a one-element list of proof bytes still allowed in the current verification pass.
        """
        seq = rec["knowledge_seq"]
        roles = [p["role"] for p in rec["proofs"]]
        if len(set(roles)) != len(roles):
            raise MemoryRefusal(c.PROOF_CORRUPT, f"RECORD_DUPLICATE_ROLE:{seq}")
        for role in REQUIRED_ROLES:
            if role not in roles:
                raise MemoryRefusal(c.PROOF_CORRUPT, f"RECORD_REQUIRED_PROOF_MISSING:{role}")
        by_role, kept = {p["role"]: p["sha256"] for p in rec["proofs"]}, {}
        for ref in rec["proofs"]:
            if budget is not None:
                budget[0] -= _ref_bytes(ref)
                if budget[0] < 0:
                    raise MemoryRefusal(c.BUDGET_EXCEEDED, "PROOF_BYTES_PER_CHECK")
            data = self.read_proof(ref)
            if ref["role"] in ("reading", "replay-report"):
                kept[ref["role"]] = data
        raw = kept["reading"]
        reading = c.strict_json(raw, c.PROOF_CORRUPT)
        session, corpus = rec["identity"]["session"], reading.get("corpus_ref") or {}
        links = {
            "manifest": session["manifest_sha256"] == by_role["manifest.json"],
            "events": session["events_sha256"] == by_role["events.jsonl"] == corpus.get("events_sha256"),
            "frames": session["frames_sha256"] == by_role["frames.bin"] == corpus.get("frames_sha256"),
            "reading": rec["reading_sha256"] == by_role["reading"],
            "report": corpus.get("source_report_sha256") == by_role["replay-report"]
            and all(by_role[r] == by_role["replay-report"] for r in engine.REPORT_MEMBERS if r in by_role),
        }
        for what, ok in links.items():
            if not ok:
                raise MemoryRefusal(c.PROOF_CORRUPT, f"RECORD_PROOF_LINK:{what}:{seq}")
        parts = c.decompose(reading, rec["identity"])
        if c.canonical(c.recompose(parts)) != raw:
            raise MemoryRefusal(c.PROOF_CORRUPT, "READING_NOT_RECOMPOSABLE")
        if parts["session_id"] != rec["session_id"] \
                or parts["session_content_sha256"] != rec["session_content_sha256"] \
                or _listing(parts) != (rec["windows"], rec["events"]):
            raise MemoryRefusal(c.PROOF_CORRUPT, "RECORD_PROOF_MISMATCH:" + str(rec["knowledge_seq"]))
        return parts

    # ------------------------------------------------------------------ index (derived)
    @property
    def index_path(self) -> str:
        return os.path.join(self.root, "index", INDEX)

    def _index_exists(self) -> bool:
        try:
            st = os.lstat(self.index_path)
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(st.st_mode):
            raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_NOT_A_REGULAR_FILE")
        return True

    def connect_ro(self):
        uri = "file:" + quote(self.index_path) + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, isolation_level=None)
        conn.execute("PRAGMA query_only=1")
        return conn

    def index_state(self, conn) -> tuple:
        rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        if rows.get("schema") != INDEX_SCHEMA or rows.get("partition") != self.partition \
                or not str(rows.get("head_seq", "")).isdigit() or "head_sha256" not in rows:
            raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_SCHEMA_OR_PARTITION")
        return int(rows["head_seq"]), rows["head_sha256"] or None

    @staticmethod
    def expected_rows(journal: list, parts_by_seq: dict) -> dict:
        """Every row the index must hold for this journal, derived only from records and proofs."""
        rows = {"sessions": [], "windows": [], "events": []}
        for rec, sha in journal:
            rows_one = _rows(rec, sha, parts_by_seq[rec["knowledge_seq"]])
            for t in rows:
                rows[t] += rows_one[t]
        head = (str(len(journal)), journal[-1][1] if journal else "")
        rows["meta"] = [("head_seq", head[0]), ("head_sha256", head[1])]
        return rows

    def check_index(self, conn, journal: list, parts_by_seq: dict) -> None:
        """Compare the whole index with the authority: schema, meta, and every column of every row
        (selection, filter, order and link columns included). Missing or extra rows are inconsistencies."""
        try:
            schema = conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name").fetchall()
            if [tuple(r) for r in schema] != _expected_schema():
                raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_DISAGREES_WITH_PROOF:schema")
            want = self.expected_rows(journal, parts_by_seq)
            want["meta"] = sorted(want["meta"] + [("partition", self.partition), ("schema", INDEX_SCHEMA)])
            for table in ("meta", "sessions", "windows", "events"):
                got = sorted((tuple(r) for r in conn.execute(f"SELECT * FROM {table}")), key=lambda r: r[0])
                if got != sorted(want[table], key=lambda r: r[0]):
                    raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_DISAGREES_WITH_PROOF:" + table)
        except sqlite3.Error:
            raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_UNREADABLE") from None

    def verified_parts(self, journal: list) -> dict:
        """All sessions of the bound, each verified against all its proofs, within the per-pass bounds."""
        if len(journal) > self.limits.sessions_per_read:
            raise MemoryRefusal(c.BUDGET_EXCEEDED, "SESSIONS_PER_READ")
        budget = [self.limits.proof_bytes_per_check]
        return {rec["knowledge_seq"]: self.session_parts(rec, budget) for rec, _sha in journal}

    def verified_view(self):
        """(journal, connection inside an open read transaction, parts) for a fully verified bound K.

        The read transaction pins one SQLite snapshot for the whole read; the snapshot is then
        checked against the journal and every proof before anything is selected from it.
        """
        journal, conn = self.consistent_view()
        if conn is None:
            return journal, None, {}
        try:
            conn.execute("BEGIN")
            head = self.index_state(conn)  # first read inside the transaction: takes the snapshot
            if head != (len(journal), journal[-1][1] if journal else None):
                raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_CHANGED_DURING_READ")
            parts = self.verified_parts(journal)
            self.check_index(conn, journal, parts)
        except BaseException:
            conn.close()
            raise
        return journal, conn, parts

    def consistent_view(self):
        """(journal, read-only connection) when the index head equals the journal head."""
        journal = self.load_journal()
        if not self._index_exists():
            if journal:
                raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_MISSING")
            return journal, None
        try:
            conn = self.connect_ro()
            head = self.index_state(conn)
        except (sqlite3.Error, ValueError, KeyError):
            raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_UNREADABLE") from None
        expected = (len(journal), journal[-1][1] if journal else None)
        if head != expected:
            conn.close()
            detail = "INDEX_BEHIND_JOURNAL" if head[0] < expected[0] else \
                "INDEX_AHEAD_OF_JOURNAL" if head[0] > expected[0] else "INDEX_FORKED_FROM_JOURNAL"
            raise MemoryRefusal(c.INDEX_INCONSISTENT, detail)
        return journal, conn

    # ------------------------------------------------------------------ writer
    @contextmanager
    def writer(self):
        try:
            fd = os.open(os.path.join(self.root, LOCK), os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        except OSError:
            raise MemoryRefusal(c.NOT_CONFIGURED, "LOCK_UNAVAILABLE") from None
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise MemoryRefusal(c.WRITER_BUSY, "ANOTHER_WRITER_HOLDS_THE_LOCK") from None
            yield
        finally:
            os.close(fd)

    def _publish(self, dir_parts: tuple, name: str, data: bytes, what: str) -> str:
        """Temp file -> fsync -> link without replace -> fsync directory. Returns CREATED or PRESENT."""
        tmpd = self._open_dir("tmp")
        dstd = self._open_dir(*dir_parts)
        tname = f"{what}-{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(tname, _NEW_FILE, 0o600, dir_fd=tmpd)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
                os.fchmod(fh.fileno(), 0o400)
            self._cp(what + "_tmp_written")
            try:
                os.link(tname, name, src_dir_fd=tmpd, dst_dir_fd=dstd, follow_symlinks=False)
                outcome = "CREATED"
            except FileExistsError:
                outcome = "PRESENT"
            self._cp(what + "_linked")
            try:
                _fsync_dir(dstd)
            except OSError:
                raise MemoryRefusal(c.PUBLICATION_UNCERTAIN, f"DIRECTORY_FSYNC_FAILED:{what}") from None
            os.unlink(tname, dir_fd=tmpd)
            try:
                _fsync_dir(tmpd)
            except OSError:
                self.warnings.append("TMP_DIRECTORY_FSYNC_FAILED")  # a leftover temp is only an orphan
            return outcome
        finally:
            os.close(tmpd)
            os.close(dstd)

    def _publish_proof(self, data: bytes) -> str:
        sha = c.sha256(data)
        pd = self._open_dir("proofs")
        try:
            try:
                os.mkdir(sha[:2], 0o700, dir_fd=pd)
            except FileExistsError:
                pass
            try:  # always: a sub-directory created by an attempt whose fsync failed becomes durable here
                _fsync_dir(pd)
            except OSError:
                raise MemoryRefusal(c.PUBLICATION_UNCERTAIN, "DIRECTORY_FSYNC_FAILED:proofs") from None
        finally:
            os.close(pd)
        outcome = self._publish(("proofs", sha[:2]), sha, data, "proof")
        if outcome == "PRESENT":  # never overwritten: the existing bytes must be the same proof
            self.read_proof({"sha256": sha, "bytes": len(data)})
        return outcome

    def _root_usage(self) -> int:
        total, entries = 0, 0
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            for n in dirnames + filenames:
                entries += 1
                if entries > self.limits.root_entries:
                    raise MemoryRefusal(c.BUDGET_EXCEEDED, "ROOT_ENTRIES")
                st = os.lstat(os.path.join(dirpath, n))
                total += st.st_size if stat.S_ISREG(st.st_mode) else 0
        return total

    def _check_budget(self, new_bytes: int) -> int:
        """Refuse before writing; return the bytes still allowed (index, temporaries, retired and SQLite
        journals included in the usage, the reserve excluded)."""
        room = self.marker["budget_bytes"] - self.limits.reserve_bytes - self._root_usage()
        if new_bytes > room:
            raise MemoryRefusal(c.BUDGET_EXCEEDED, "ROOT_BUDGET")
        return room

    def _estimate_index_bytes(self) -> int:
        """Pre-check size of a rebuilt index: the current one, or the empty schema plus a row allowance."""
        rows = sum(1 + len(rec["windows"]) + len(rec["events"]) for rec, _sha in self.load_journal())
        current = os.lstat(self.index_path).st_size if self._index_exists() else 0
        return max(current, _EMPTY_INDEX_BYTES + _ROW_BYTES * rows)

    def _connect_rw(self, path: str):
        conn = sqlite3.connect(path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @staticmethod
    def _create_schema(conn, partition: str) -> None:
        """Only on a fresh file in tmp/ (rebuild): the file becomes the index by rename, after this."""
        conn.executescript(SCHEMA_SQL)
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany("INSERT INTO meta(key, value) VALUES (?, ?)",
                         [("schema", INDEX_SCHEMA), ("partition", partition), ("head_seq", "0"),
                          ("head_sha256", "")])
        conn.execute("COMMIT")

    def _index_record(self, conn, rec: dict, rec_sha: str, parts: dict) -> None:
        """Insert one import in ONE transaction, moving the index head with it."""
        seq = rec["knowledge_seq"]
        conn.execute("BEGIN IMMEDIATE")
        try:
            head = self.index_state(conn)
            if head[0] != seq - 1:
                raise MemoryRefusal(c.INDEX_INCONSISTENT, "INDEX_HEAD_NOT_PREDECESSOR")
            rows = _rows(rec, rec_sha, parts)
            conn.executemany("INSERT INTO sessions VALUES (?,?,?,?,?)", rows["sessions"])
            conn.executemany("INSERT INTO windows VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows["windows"])
            conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)", rows["events"])
            conn.execute("UPDATE meta SET value=? WHERE key='head_seq'", (str(seq),))
            conn.execute("UPDATE meta SET value=? WHERE key='head_sha256'", (rec_sha,))
            self._cp("index_transaction_open")
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    def _rebuild(self, journal: list, parts_by_seq: dict | None = None) -> dict:
        """Build a fresh index from the journal and the proofs only, then swap it in (old one retired).

        Budget (RV01-03): refused before writing when the estimate does not fit; while writing, the
        temporary file is capped to the room left (``max_page_count``, journal kept in memory for this
        unpublished file). A refused rebuild removes only its own unpublished temporary file and leaves
        the previous index, the journal and the proofs untouched.
        """
        if parts_by_seq is None:
            parts_by_seq = self.verified_parts(journal)
        room = self._check_budget(self._estimate_index_bytes())
        tmpname = f"index-{secrets.token_hex(8)}.sqlite"
        tmppath = os.path.join(self.root, "tmp", tmpname)
        conn = sqlite3.connect(tmppath, isolation_level=None)
        try:
            conn.execute(f"PRAGMA page_size={_PAGE}")
            conn.execute("PRAGMA journal_mode=MEMORY")
            conn.execute(f"PRAGMA max_page_count={max(room // _PAGE, 1)}")
            self._create_schema(conn, self.partition)
            for rec, sha in journal:
                self._index_record(conn, rec, sha, parts_by_seq[rec["knowledge_seq"]])
            conn.close()
        except BaseException as exc:
            conn.close()
            self._drop_unpublished(tmpname)
            if isinstance(exc, sqlite3.OperationalError) and "full" in str(exc):
                raise MemoryRefusal(c.BUDGET_EXCEEDED, "ROOT_BUDGET:DURING_REBUILD") from None
            if isinstance(exc, sqlite3.Error):  # RV02-02: typed, never a raw SQLite exception
                raise MemoryRefusal(c.INDEX_INCONSISTENT, f"INDEX_WRITE_FAILED:{type(exc).__name__}") from None
            raise
        if os.lstat(tmppath).st_size > room:
            self._drop_unpublished(tmpname)
            raise MemoryRefusal(c.BUDGET_EXCEEDED, "ROOT_BUDGET:DURING_REBUILD")
        fd = os.open(tmppath, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        tmpd, idxd = self._open_dir("tmp"), self._open_dir("index")
        try:
            retired = None
            if self._index_exists():
                retired = f"retired-{len(journal):012d}-{secrets.token_hex(4)}.sqlite"
                os.rename(INDEX, retired, src_dir_fd=idxd, dst_dir_fd=idxd)
            os.rename(tmpname, INDEX, src_dir_fd=tmpd, dst_dir_fd=idxd)
            try:
                _fsync_dir(idxd)
                _fsync_dir(tmpd)
            except OSError:
                raise MemoryRefusal(c.PUBLICATION_UNCERTAIN, "DIRECTORY_FSYNC_FAILED:index") from None
        finally:
            os.close(tmpd)
            os.close(idxd)
        return {"rebuilt_records": len(journal), "retired_index": retired}

    def _drop_unpublished(self, tmpname: str) -> None:
        """Remove a temporary index this very call created and never published (not evidence, not state)."""
        tmpd = self._open_dir("tmp")
        try:
            try:
                os.unlink(tmpname, dir_fd=tmpd)
            except FileNotFoundError:
                pass
            try:
                _fsync_dir(tmpd)
            except OSError:
                self.warnings.append("TMP_DIRECTORY_FSYNC_FAILED")
        finally:
            os.close(tmpd)

    def _sync_proof_dirs(self, journal: list) -> None:
        """fsync proofs/ and every proofs/<hh>/ the journal references (a failed fsync stays uncertain)."""
        dirs = sorted({ref["sha256"][:2] for rec, _sha in journal for ref in rec["proofs"]
                       if _HEX.fullmatch(ref["sha256"])})
        for parts in [("proofs",)] + [("proofs", d) for d in dirs]:
            try:
                fd = self._open_dir(*parts)
            except MemoryRefusal:
                continue  # a missing directory is reported by the proof verification itself
            try:
                _fsync_dir(fd)
            except OSError:
                raise MemoryRefusal(c.PUBLICATION_UNCERTAIN, "DIRECTORY_FSYNC_FAILED:proofs") from None
            finally:
                os.close(fd)

    def _reconcile(self) -> dict:
        """Writer only: make the index equal to the verified journal head (apply or rebuild)."""
        jd = self._open_dir("journal")
        try:
            _fsync_dir(jd)  # a record linked before a failed fsync becomes durable now, or stays uncertain
        except OSError:
            raise MemoryRefusal(c.PUBLICATION_UNCERTAIN, "DIRECTORY_FSYNC_FAILED:journal") from None
        finally:
            os.close(jd)
        journal = self.load_journal()
        self._sync_proof_dirs(journal)
        # Every proof of every record is verified first: a recovery is never acknowledged on missing
        # or corrupt evidence (RV01-02). Nothing below is derived from anything else.
        parts = self.verified_parts(journal)
        n = len(journal)
        if not self._index_exists():
            action = "INDEX_CREATED" if not journal else "REBUILT"
            return {"action": action, **self._rebuild(journal, parts), "journal_head": n}
        try:
            conn = self._connect_rw(self.index_path)  # rolls back a hot journal left by a crash
            try:
                ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                head = self.index_state(conn) if ok else None
            finally:
                conn.close()
        except (sqlite3.Error, MemoryRefusal):
            ok, head = False, None
        action, applied = None, 0
        if ok and head == (n, journal[-1][1] if journal else None):
            action = "NONE"
        elif ok and head[0] < n and (head[0] == 0 and head[1] is None or
                                     head[0] > 0 and journal[head[0] - 1][1] == head[1]):
            pending = journal[head[0]:]
            # RV02-02: the indexed prefix is verified row by row before anything is applied onto it;
            # an inconsistent prefix (parasite, missing or modified row) is rebuilt from the authority.
            if self._prefix_consistent(journal[:head[0]], parts):
                self._check_budget(sum(2 * _ROW_BYTES * (1 + len(r["windows"]) + len(r["events"])) + _PAGE * 4
                                       for r, _s in pending))
                try:
                    conn = self._connect_rw(self.index_path)
                    try:
                        for rec, sha in pending:
                            self._index_record(conn, rec, sha, parts[rec["knowledge_seq"]])
                    finally:
                        conn.close()
                    action, applied = "APPLIED_PENDING", n - head[0]
                except sqlite3.Error:
                    action = None  # not applied (transaction rolled back): rebuilt from the authority below
        if action is not None:  # the head matches: every row must match too (RV01-01)
            conn = self.connect_ro()
            try:
                self.check_index(conn, journal, parts)
                out = {"action": action, "journal_head": n}
                return {**out, "applied": applied} if action == "APPLIED_PENDING" else out
            except MemoryRefusal:
                pass
            finally:
                conn.close()
        try:
            return {"action": "REBUILT", **self._rebuild(journal, parts), "journal_head": n}
        except sqlite3.Error as exc:  # RV02-02: never a raw SQLite exception as an operational result
            raise MemoryRefusal(c.INDEX_INCONSISTENT, f"INDEX_WRITE_FAILED:{type(exc).__name__}") from None

    def _prefix_consistent(self, prefix: list, parts: dict) -> bool:
        conn = self.connect_ro()
        try:
            self.check_index(conn, prefix, {r["knowledge_seq"]: parts[r["knowledge_seq"]] for r, _s in prefix})
            return True
        except MemoryRefusal:
            return False
        finally:
            conn.close()

    def recover(self) -> dict:
        with self.writer():
            return self._reconcile()

    def rebuild(self) -> dict:
        with self.writer():
            self._reconcile()
            journal = self.load_journal()
            return {"action": "REBUILT", **self._rebuild(journal), "journal_head": len(journal)}

    # ------------------------------------------------------------------ inputs
    def _read_input(self, path: Path, cap: int, *, optional=False):
        res = read_regular_file(path, cap)
        if res.error is None:
            return res.raw
        if res.error == "MISSING":
            if optional:
                return None
            raise MemoryRefusal(c.PROOF_UNAVAILABLE, "INPUT_MISSING:" + path.name)
        if res.error == "TOO_LARGE":
            raise MemoryRefusal(c.BUDGET_EXCEEDED, "INPUT_TOO_LARGE:" + path.name)
        raise MemoryRefusal(c.INPUT_REFUSED, f"INPUT_{res.error}:{path.name}")

    def _read_capture_dir(self, directory) -> dict:
        d = Path(directory)
        members = {}
        for name in engine.MEMBERS:
            raw = self._read_input(d / name, _member_cap(name, self.limits),
                                   optional=name not in engine.REQUIRED_MEMBERS)
            if raw is not None:
                members[name] = raw
        return members

    def _read_archive(self, raw: bytes) -> dict:
        members, total = {}, 0
        try:
            with tarfile.open(fileobj=BytesIO(raw), mode="r:gz") as tar:
                count = 0
                while True:
                    info = tar.next()
                    if info is None:
                        break
                    count += 1
                    if count > self.limits.archive_members:
                        raise MemoryRefusal(c.INPUT_REFUSED, "ARCHIVE_TOO_MANY_MEMBERS")
                    name = info.name[2:] if info.name.startswith("./") else info.name
                    if not info.isreg() or name not in engine.MEMBERS or name in members:
                        raise MemoryRefusal(c.INPUT_REFUSED, "ARCHIVE_MEMBER_REFUSED:" + info.name[:80])
                    if info.size > _member_cap(name, self.limits):
                        raise MemoryRefusal(c.BUDGET_EXCEEDED, "ARCHIVE_MEMBER_TOO_LARGE:" + name)
                    total += info.size
                    if total > self.limits.import_bytes:
                        raise MemoryRefusal(c.BUDGET_EXCEEDED, "IMPORT_BYTES")
                    data = tar.extractfile(info).read(info.size + 1)
                    if len(data) != info.size:
                        raise MemoryRefusal(c.INPUT_REFUSED, "ARCHIVE_MEMBER_TRUNCATED:" + name)
                    members[name] = data
        except (tarfile.TarError, EOFError, OSError):
            raise MemoryRefusal(c.INPUT_REFUSED, "ARCHIVE_MALFORMED") from None
        return members

    # ------------------------------------------------------------------ import
    def import_capture(self, *, partition: str, capture_dir=None, archive=None, reading=None) -> dict:
        """Verify, re-run, then publish one capture and its reading. Idempotent; conflicts refused."""
        if (capture_dir is None) == (archive is None):
            raise MemoryRefusal(c.INVALID_REQUEST, "EXACTLY_ONE_OF_CAPTURE_OR_ARCHIVE")
        if partition != self.partition:
            raise MemoryRefusal(c.INPUT_REFUSED, "PARTITION_MISMATCH_WITH_ROOT")
        with self.writer():
            self._reconcile()
            extra = {}
            if archive is not None:
                araw = self._read_input(Path(archive), self.limits.archive_bytes)
                members = self._read_archive(araw)
                extra["archive.tar.gz"] = araw
            else:
                members = self._read_capture_dir(capture_dir)
            rraw = None if reading is None else self._read_input(Path(reading), self.limits.small_member_bytes)
            if sum(map(len, members.values())) + sum(map(len, extra.values())) + len(rraw or b"") \
                    > self.limits.import_bytes:
                raise MemoryRefusal(c.BUDGET_EXCEEDED, "IMPORT_BYTES")
            v = engine.verify_capture(members, rraw)
            if v["identity"]["partition"] != self.partition:
                raise MemoryRefusal(c.INPUT_REFUSED, "PARTITION_MISMATCH_WITH_EVIDENCE")
            parts = c.decompose(v["reading"], v["identity"])
            if c.canonical(c.recompose(parts)) != v["reading_bytes"]:
                raise MemoryRefusal(c.INPUT_REFUSED, "READING_NOT_RECOMPOSABLE")
            for w in parts["windows"]:
                _i(w["body"]["start_ns"]), _i(w["body"]["end_ns"])
            journal = self.load_journal()
            known = self._known(journal, parts)
            if known is not None:
                return known
            proofs = {**members, **extra, "reading": v["reading_bytes"], "replay-report": v["report_bytes"]}
            refs_ = sorted(({"role": role, "sha256": c.sha256(b), "bytes": len(b)} for role, b in proofs.items()),
                           key=lambda r: r["role"])
            unique = {c.sha256(b): b for b in proofs.values()}
            windows = [w["body"] for w in parts["windows"]]
            seq = len(journal) + 1
            rec = {
                "schema": RECORD_SCHEMA, "producer": PRODUCER, "partition": self.partition,
                "knowledge_seq": seq, "predecessor_sha256": journal[-1][1] if journal else None,
                "session_id": parts["session_id"], "session_content_sha256": parts["session_content_sha256"],
                "reading_sha256": c.sha256(v["reading_bytes"]), "identity": v["identity"],
                "proofs": refs_,
                "verification": {"seal": "VERIFIED", "replay": v["report_origin"], "reading": v["reading_origin"],
                                 "engine": v["engine"]},
                "native_bounds_ns": {"first": windows[0]["start_ns"] if windows else None,
                                     "last": windows[-1]["end_ns"] if windows else None, "axis": "NATIVE"},
                "receipt_bounds_ns": v["receipt_bounds_ns"],
                "windows": _listing(parts)[0], "events": _listing(parts)[1],
            }
            # RV02-01: refuse, before any publication, an import whose result could no longer be
            # verified in one pass (same accounting as verified_parts / session_parts).
            if seq > self.limits.sessions_per_read:
                raise MemoryRefusal(c.BUDGET_EXCEEDED, "SESSIONS_PER_READ")
            if sum(_ref_bytes(r) for old, _s in journal for r in old["proofs"]) + sum(map(_ref_bytes, refs_)) \
                    > self.limits.proof_bytes_per_check:
                raise MemoryRefusal(c.BUDGET_EXCEEDED, "PROOF_BYTES_PER_CHECK")
            raw_rec = c.canonical(rec)
            if len(raw_rec) > self.limits.record_bytes:
                raise MemoryRefusal(c.BUDGET_EXCEEDED, "RECORD_BYTES")
            self._check_budget(sum(map(len, unique.values())) + len(raw_rec) + 4 * len(v["reading_bytes"]) + MiB)
            created = {}
            for sha, data in sorted(unique.items()):
                created[sha] = self._publish_proof(data)
            self._cp("proofs_durable")
            if self._publish(("journal",), f"{seq:012d}.json", raw_rec, "record") != "CREATED":
                raise MemoryRefusal(c.CONFLICT, "KNOWLEDGE_SEQ_TAKEN")
            self._cp("record_durable")
            rec_sha = c.sha256(raw_rec)
            conn = self._connect_rw(self.index_path)
            try:
                self._index_record(conn, rec, rec_sha, parts)
            finally:
                conn.close()
            self._cp("index_committed")
            return {"result": "IMPORTED", "partition": self.partition, "knowledge_seq": seq,
                    "import_sha256": rec_sha, "session_id": parts["session_id"],
                    "reading_sha256": rec["reading_sha256"], "windows": len(parts["windows"]),
                    "events": len(parts["events"]),
                    "proofs": {r["role"]: r["sha256"] for r in refs_},
                    "proofs_created": sorted(s for s, o in created.items() if o == "CREATED"),
                    "warnings": list(self.warnings)}

    def _known(self, journal: list, parts: dict):
        """NO_OP for an identical session, CONFLICT for the same identities with other content."""
        new_w, new_e = _listing(parts)
        ids = {w["window_id"]: w["content_sha256"] for w in new_w}
        ids.update({e["event_id"]: e["content_sha256"] for e in new_e})
        for rec, sha in journal:
            if rec["session_id"] == parts["session_id"]:
                if rec["session_content_sha256"] == parts["session_content_sha256"] \
                        and (rec["windows"], rec["events"]) == (new_w, new_e):
                    return {"result": "NO_OP", "partition": self.partition, "knowledge_seq": rec["knowledge_seq"],
                            "import_sha256": sha, "session_id": rec["session_id"],
                            "reading_sha256": rec["reading_sha256"], "windows": len(new_w), "events": len(new_e)}
                raise MemoryRefusal(c.CONFLICT, "SESSION_CONTENT_DIFFERS:" + rec["session_id"])
            for item in rec["windows"] + rec["events"]:
                key = item.get("event_id") or item["window_id"]
                if key in ids and ids[key] != item["content_sha256"]:
                    raise MemoryRefusal(c.CONFLICT, "OBJECT_CONTENT_DIFFERS:" + key)
        return None

    # ------------------------------------------------------------------ audit
    def verify(self) -> dict:
        """Read-only audit: journal chain, every proof, index head, orphans. Findings, never repairs."""
        findings, referenced = [], set()
        try:
            journal = self.load_journal()
        except MemoryRefusal as exc:
            return {"state": "INCONSISTENT", "findings": [{"category": exc.category, "detail": exc.detail}]}
        budget = [self.limits.proof_bytes_per_check]
        for rec, _sha in journal:
            for ref in rec["proofs"]:
                referenced.add(ref["sha256"])
            try:
                self.session_parts(rec, budget)
            except MemoryRefusal as exc:
                findings.append({"category": exc.category, "detail": exc.detail, "seq": rec["knowledge_seq"]})
        if not findings:
            try:
                _j, conn, _parts = self.verified_view()
                if conn is not None:
                    conn.close()
            except MemoryRefusal as exc:
                findings.append({"category": exc.category, "detail": exc.detail})
        stored = set()
        for dirpath, _dirs, files in os.walk(os.path.join(self.root, "proofs"), followlinks=False):
            stored.update(files)
        tmp = os.listdir(os.path.join(self.root, "tmp"))
        return {"state": "CONSISTENT" if not findings else "INCONSISTENT", "findings": findings,
                "journal_head": len(journal), "proofs_referenced": len(referenced),
                "orphan_proofs": sorted(stored - referenced), "orphan_temporaries": len(tmp),
                "root_bytes": self._root_usage(), "budget_bytes": self.marker["budget_bytes"]}


def _ref_bytes(ref: dict) -> int:
    """Bytes a proof ref counts for in a verification pass (shared by import and verification)."""
    return ref["bytes"] if type(ref["bytes"]) is int else 0


def _i(text) -> int:
    """Native nanoseconds as a 64-bit integer (numeric order, never lexical)."""
    if text is None:
        return None
    v = int(text)
    if not 0 <= v <= INT64_MAX:
        raise MemoryRefusal(c.INPUT_REFUSED, "TIMESTAMP_OUT_OF_RANGE")
    return v


def _rows(rec: dict, rec_sha: str, parts: dict) -> dict:
    """The index rows of one import (the single definition used to write AND to check the index)."""
    seq, sid, nb = rec["knowledge_seq"], rec["session_id"], rec["native_bounds_ns"]
    return {
        "sessions": [(sid, seq, rec_sha, _i(nb["first"]), _i(nb["last"]))],
        "windows": [(w["window_id"], sid, seq, _i(w["body"]["start_ns"]), _i(w["body"]["end_ns"]),
                     w["body"].get("cvd_segment"), w["body"]["status"], w["body"]["alignment"],
                     int(bool(w["body"]["eligible_for_first_desalignment"])), w["body"]["exclusion_reason"],
                     w["content_sha256"]) for w in parts["windows"]],
        "events": [(e["event_id"], sid, seq, e["body"]["window_id"], _i(e["body"]["start_ns"]), e["body"]["segment"],
                    int(bool(e["body"]["eligible_for_first_desalignment"])), e["body"]["exclusion_reason"],
                    int(e["body"]["first_in_segment"]), e["content_sha256"]) for e in parts["events"]],
    }


_SCHEMA_CACHE: list = []


def _expected_schema() -> list:
    if not _SCHEMA_CACHE:
        mem = sqlite3.connect(":memory:")
        try:
            mem.executescript(SCHEMA_SQL)
            _SCHEMA_CACHE.extend(tuple(r) for r in mem.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name"))
        finally:
            mem.close()
    return list(_SCHEMA_CACHE)


def _listing(parts: dict) -> tuple:
    return ([{"window_id": w["window_id"], "content_sha256": w["content_sha256"]} for w in parts["windows"]],
            [{"event_id": e["event_id"], "window_id": e["body"]["window_id"], "content_sha256": e["content_sha256"]}
             for e in parts["events"]])


SCHEMA_SQL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sessions (session_id TEXT PRIMARY KEY, knowledge_seq INTEGER NOT NULL UNIQUE,
  import_sha256 TEXT NOT NULL, native_first_ns INTEGER, native_last_ns INTEGER);
CREATE TABLE windows (window_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, knowledge_seq INTEGER NOT NULL,
  start_ns INTEGER NOT NULL, end_ns INTEGER NOT NULL, segment INTEGER, status TEXT NOT NULL,
  alignment TEXT NOT NULL, eligible INTEGER NOT NULL, exclusion_reason TEXT, content_sha256 TEXT NOT NULL);
CREATE TABLE events (event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, knowledge_seq INTEGER NOT NULL,
  window_id TEXT NOT NULL, start_ns INTEGER NOT NULL, segment INTEGER, eligible INTEGER NOT NULL,
  exclusion_reason TEXT, first_in_segment INTEGER NOT NULL, content_sha256 TEXT NOT NULL);
CREATE INDEX windows_order ON windows (knowledge_seq, start_ns);
CREATE INDEX events_order ON events (knowledge_seq, start_ns, event_id);
"""
