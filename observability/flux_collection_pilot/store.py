"""Private, campaign-local, durable storage with an exact byte budget.

- The root must be absolute, symlink-free and OUTSIDE any git work tree (campaign
  files and captures never go to Git or to Flux); the campaign directory is created
  exclusively with mode 0700 and files with 0600.
- Every byte written (raw lines, intents, receipts, trigger) counts against
  ``caps.max_disk_bytes``. Raw appends may only use ``max_disk_bytes - reserve_bytes``;
  the trigger record and the final receipt use the reserve (``final=True``).
- Receipts are written write-tmp -> fsync -> rename -> fsync(dir). A crash leaves a
  ``.tmp`` and/or a partial last raw line, which ``verify_campaign`` reports
  instead of silently accepting.
"""

import base64
import hashlib
import json
import os
import re
from pathlib import Path


class StoreError(RuntimeError):
    pass


class DiskBudgetExceeded(StoreError):
    pass


class WriteFailed(StoreError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def inside_git_worktree(path):
    p = Path(path)
    return any((q / ".git").exists() for q in (p, *p.parents))


def raw_record(session, idx, campaign_idx, instant, raw):
    rec = {"v": 1, "session": session, "idx": idx, "campaign_idx": campaign_idx,
           "recv_utc_ns": instant.utc_ns, "recv_mono_ns": instant.monotonic_ns,
           "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    try:
        rec["raw"] = raw.decode("utf-8")
    except UnicodeDecodeError:
        rec["raw_b64"] = base64.b64encode(raw).decode()
    return rec


def record_bytes(rec):
    if "raw" in rec:
        return rec["raw"].encode("utf-8")
    return base64.b64decode(rec["raw_b64"])


class CampaignStore:
    def __init__(self, root, campaign_id, caps, *, write=os.write, fsync=os.fsync):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(campaign_id)):
            raise ValueError("INVALID_CAMPAIGN_ID")
        root = str(root)
        if not os.path.isabs(root) or os.path.realpath(root) != root or ".." in root.split(os.sep):
            raise ValueError("ABSOLUTE_SYMLINK_FREE_ROOT_REQUIRED")
        if not os.path.isdir(root):
            raise ValueError("ROOT_NOT_A_DIRECTORY")
        if inside_git_worktree(root):
            raise ValueError("CAMPAIGN_ROOT_INSIDE_GIT_WORKTREE_REFUSED")
        self.caps, self._write, self._fsync = caps, write, fsync
        self.path = Path(root) / campaign_id
        os.mkdir(self.path, 0o700)  # exclusive: refuses an existing campaign
        self.dir_fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
        self._fsync(self.dir_fd)
        self.used = 0
        self._raw = {}  # session -> dict(fd, sha, bytes, lines)

    # -- low level ----------------------------------------------------
    def _write_all(self, fd, data):
        view = memoryview(data)
        try:
            while view:
                n = self._write(fd, view)
                if not n:
                    raise OSError("ZERO_WRITE")
                view = view[n:]
        except OSError as e:
            raise WriteFailed(str(e)) from e

    def _budget(self, n, final):
        ceiling = self.caps.max_disk_bytes if final else self.caps.max_disk_bytes - self.caps.reserve_bytes
        if self.used + n > ceiling:
            raise DiskBudgetExceeded("DISK_BUDGET")

    # -- raw stream ---------------------------------------------------
    def open_raw(self, session):
        name = "%s.raw.jsonl" % session
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.dir_fd)
        self._raw[session] = {"fd": fd, "sha": hashlib.sha256(), "bytes": 0, "lines": 0, "name": name}
        self._fsync(self.dir_fd)

    def append_raw(self, session, rec):
        line = _canonical(rec) + b"\n"
        self._budget(len(line), final=False)  # checked BEFORE writing anything
        w = self._raw[session]
        self._write_all(w["fd"], line)
        w["sha"].update(line)
        w["bytes"] += len(line)
        w["lines"] += 1
        self.used += len(line)

    def sync_raw(self, session):
        try:
            self._fsync(self._raw[session]["fd"])
        except OSError as e:
            raise WriteFailed(str(e)) from e

    def raw_state(self, session):
        w = self._raw[session]
        return {"file": w["name"], "bytes": w["bytes"], "lines": w["lines"], "sha256": w["sha"].hexdigest()}

    def close_raw(self, session):
        w = self._raw.pop(session, None)
        if w:
            try:
                self._fsync(w["fd"])
            finally:
                os.close(w["fd"])

    # -- atomic small files -------------------------------------------
    def write_atomic(self, name, value, *, final=False):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,95}", name) or name.endswith(".tmp"):
            raise ValueError("INVALID_FILE_NAME")
        data = _canonical(value) + b"\n"
        self._budget(len(data), final)
        tmp = name + ".tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.dir_fd)
        except OSError as e:
            raise WriteFailed(str(e)) from e
        try:
            self._write_all(fd, data)
            try:
                self._fsync(fd)
            except OSError as e:
                raise WriteFailed(str(e)) from e
        finally:
            os.close(fd)
        try:
            os.rename(tmp, name, src_dir_fd=self.dir_fd, dst_dir_fd=self.dir_fd)
            self._fsync(self.dir_fd)
        except OSError as e:
            raise WriteFailed(str(e)) from e
        self.used += len(data)
        return hashlib.sha256(data).hexdigest()

    def inventory(self):
        out = {}
        for p in sorted(self.path.iterdir()):
            if p.name == "final.receipt.json" or p.name.endswith(".tmp"):
                continue
            b = p.read_bytes()
            out[p.name] = {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
        return out

    def close(self):
        for s in list(self._raw):
            try:
                self.close_raw(s)
            except OSError:
                pass
        if self.dir_fd is not None:
            os.close(self.dir_fd)
            self.dir_fd = None


def read_raw_file(path):
    """(records, problems). A partial or unparsable last line is reported, not read."""
    data = Path(path).read_bytes()
    problems, records = [], []
    if not data:
        return records, problems, data
    lines = data.split(b"\n")
    tail = lines.pop()  # text after the last newline (b"" when the file ends cleanly)
    if tail:
        problems.append("RAW_PARTIAL_LAST_LINE")
    for i, ln in enumerate(lines):
        try:
            rec = json.loads(ln)
            record_bytes(rec)
        except (ValueError, KeyError, TypeError):
            problems.append("RAW_LINE_UNPARSABLE:%d" % i)
            continue
        records.append(rec)
    return records, problems, data


def verify_campaign(path):
    """Independent check of a campaign directory. Never raises on damage."""
    base = Path(path)
    problems = []
    files = sorted(p.name for p in base.iterdir())
    for n in files:
        if n.endswith(".tmp"):
            problems.append("TMP_FILE_PRESENT:" + n)
    final = None
    if "final.receipt.json" in files:
        try:
            final = json.loads((base / "final.receipt.json").read_bytes())
        except ValueError:
            problems.append("FINAL_RECEIPT_UNPARSABLE")
    else:
        problems.append("FINAL_RECEIPT_MISSING")
    sessions = {}
    for n in files:
        if not n.endswith(".raw.jsonl"):
            continue
        sess = n[: -len(".raw.jsonl")]
        recs, probs, data = read_raw_file(base / n)
        sessions[sess] = {"complete_lines": len(recs), "sha256": hashlib.sha256(data).hexdigest(),
                          "bytes": len(data), "problems": probs}
        problems += [sess + ":" + p for p in probs]
        if [r["idx"] for r in recs] != list(range(len(recs))):
            problems.append(sess + ":RAW_INDEX_NOT_CONTIGUOUS")
    if final is not None:
        for name, meta in final.get("files", {}).items():
            p = base / name
            if not p.exists():
                problems.append("LISTED_FILE_MISSING:" + name)
            elif hashlib.sha256(p.read_bytes()).hexdigest() != meta["sha256"]:
                problems.append("HASH_MISMATCH:" + name)
    status = "INCOMPLETE" if final is None else ("COMPLETE_VERIFIED" if final.get("complete") is True else "INCOMPLETE_BY_RECEIPT")
    if any(p.startswith("HASH_MISMATCH") or "UNPARSABLE" in p for p in problems):
        status = "CORRUPT"
    elif problems and status == "COMPLETE_VERIFIED":
        status = "INCOMPLETE"
    return {"status": status, "problems": problems, "sessions": sessions,
            "end_reason": None if final is None else final.get("end_reason")}
