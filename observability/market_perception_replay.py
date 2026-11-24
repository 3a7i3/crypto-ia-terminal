"""Operator CLI for the CH1-02 Kraken-only replay (``observability.market_flow.kraken_replay``).

OPERATOR GESTURE / SOURCE TOOL. It opens no connection, reads no clock and touches no
service, runtime, PAPER, PPL or FIN state. It reads the three files of one sealed BBO
journal named by the operator, verifies the seal, replays up to an explicit receipt
bound and publishes one canonical JSON document at a destination the operator chooses:

    python -m observability.market_perception_replay verify \\
        --manifest M --events E --frames F [--manifest-sha256 HEX]
    python -m observability.market_perception_replay replay \\
        --manifest M --events E --frames F --receipt-bound N \\
        --corpus-id ID --evidence-kind {SYNTHETIC,HISTORICAL} --out FILE [--manifest-sha256 HEX]

- ``verify`` writes nothing; it prints the seal and the number of sealed events, which
  is the receipt bound of a full replay.
- ``--manifest-sha256`` is required for HISTORICAL: the manifest carries the hashes of
  the two other files, so pinning it binds the replay to the admitted corpus.
- The destination must not exist and its directory must exist. The document is written
  to a private temporary file next to it, flushed, read back and checked by SHA-256, then
  linked into place without ever replacing a file.
- Nothing is written when an input, the pin, the seal or the replay is refused.
- On success it prints the number of records, the exact size in bytes and the SHA-256
  of the document.

Exit codes: 0 done, 2 usage, 3 refused (nothing written), 4 write failed (nothing left
at the destination).
"""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile

from observability.market_flow import kraken_replay as kr

MAX_INPUT_BYTES = 1 << 30  # per file; the admitted Kraken corpus is about 25 MB in all
EXIT_OK, EXIT_USAGE, EXIT_REFUSED, EXIT_WRITE_FAILED = 0, 2, 3, 4
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_BOUND = re.compile(r"[1-9][0-9]{0,11}", re.ASCII)
_CHUNK = 1 << 20


class CliRefusal(Exception):
    """Refused before anything was written at the destination."""

    def __init__(self, reason, subject=None):
        super().__init__(reason)
        self.reason, self.subject = reason, subject


class WriteFailure(Exception):
    """The document could not be published; nothing was left at the destination."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def read_regular_file(path, subject):
    """Read a whole regular file, refusing anything else or anything too large."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        raise CliRefusal("INPUT_UNREADABLE", subject) from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise CliRefusal("INPUT_NOT_REGULAR_FILE", subject)
        if info.st_size > MAX_INPUT_BYTES:
            raise CliRefusal("INPUT_TOO_LARGE", subject)
        chunks, total = [], 0
        while True:
            try:
                chunk = os.read(fd, _CHUNK)
            except OSError:
                raise CliRefusal("INPUT_UNREADABLE", subject) from None
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise CliRefusal("INPUT_TOO_LARGE", subject)
            chunks.append(chunk)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    if len(data) != info.st_size:
        raise CliRefusal("INPUT_CHANGED_WHILE_READING", subject)
    return data


def read_journal(args):
    files = tuple(read_regular_file(getattr(args, name), name) for name in ("manifest", "events", "frames"))
    if args.manifest_sha256 is not None and hashlib.sha256(files[0]).hexdigest() != args.manifest_sha256:
        raise CliRefusal("MANIFEST_PIN_MISMATCH", "manifest")
    return files


def check_destination(out):
    """Fail fast; the link in ``publish`` is what finally guarantees no overwrite."""
    if not os.path.basename(out):
        raise CliRefusal("OUTPUT_PATH_INVALID", "out")
    if os.path.lexists(out):
        raise CliRefusal("OUTPUT_EXISTS", "out")
    if not os.path.isdir(os.path.dirname(os.path.abspath(out))):
        raise CliRefusal("OUTPUT_DIRECTORY_MISSING", "out")


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _remove(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _sync_directory(path):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass  # best effort: some filesystems cannot sync a directory
    finally:
        os.close(fd)


def publish(out, data):
    """Publish ``data`` at ``out`` without replacing anything; return the SHA-256 read back."""
    digest = hashlib.sha256(data).hexdigest()
    directory = os.path.dirname(os.path.abspath(out))
    try:
        fd, temporary = tempfile.mkstemp(prefix="." + os.path.basename(out) + ".", suffix=".partial",
                                         dir=directory)
    except OSError:
        raise WriteFailure("OUTPUT_TEMPORARY_FILE_FAILED") from None
    try:
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            written = read_regular_file(temporary, "out")
        except CliRefusal:
            raise WriteFailure("OUTPUT_READBACK_FAILED") from None
        if hashlib.sha256(written).hexdigest() != digest:
            raise WriteFailure("OUTPUT_READBACK_MISMATCH")
        os.link(temporary, out)  # refuses an existing destination, unlike a rename
    except FileExistsError:
        raise CliRefusal("OUTPUT_EXISTS", "out") from None
    except OSError:
        raise WriteFailure("OUTPUT_WRITE_FAILED") from None
    finally:
        _remove(temporary)
    _sync_directory(directory)
    return digest


def _hashes(seal):
    return {k: v for k, v in seal.items() if k != "events_total"}


def run_verify(args):
    seal = kr.verify_seal(*read_journal(args))
    return {"status": "SEAL_VERIFIED", "events_total": int(seal["events_total"]), "seal": _hashes(seal),
            "manifest_pin": "MATCHED" if args.manifest_sha256 is not None else "NOT_GIVEN"}


def run_replay(args):
    check_destination(args.out)
    if args.evidence_kind == "HISTORICAL" and args.manifest_sha256 is None:
        raise CliRefusal("MANIFEST_PIN_REQUIRED_FOR_HISTORICAL", "manifest")
    document, seal = kr.replay(*read_journal(args), corpus_id=args.corpus_id,
                               evidence_kind=args.evidence_kind, receipt_bound=args.receipt_bound)
    digest = publish(args.out, document)
    doc = json.loads(document)
    counts = {}
    for item in doc["records"]:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    return {"status": "WRITTEN", "out": os.path.abspath(args.out), "bytes": len(document), "sha256": digest,
            "records": dict(sorted(counts.items())), "records_total": len(doc["records"]),
            "silences": len(doc["silences"]), "breaks": len(doc["breaks"]),
            "receipt_bound": int(doc["journal_prefix"]["receipt_bound"]),
            "events_total": int(seal["events_total"]), "corpus_id": doc["corpus_id"],
            "evidence_kind": doc["evidence_kind"], "replay_version": doc["replay_version"],
            "seal": _hashes(seal),
            "manifest_pin": "MATCHED" if args.manifest_sha256 is not None else "NOT_GIVEN"}


def _bound(text):
    if not _BOUND.fullmatch(text):
        raise argparse.ArgumentTypeError("a receipt sequence number: 1, 2, 3, ...")
    return int(text)


def _hex64(text):
    if not _HEX64.fullmatch(text):
        raise argparse.ArgumentTypeError("64 lowercase hexadecimal characters")
    return text


def parser():
    ap = argparse.ArgumentParser(prog="market_perception_replay",
                                 description="CH1-02 Kraken-only replay of a sealed BBO journal (operator gesture).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("verify", "replay"):
        s = sub.add_parser(name)
        s.add_argument("--manifest", required=True, help="manifest.json of the sealed journal")
        s.add_argument("--events", required=True, help="events.jsonl of the sealed journal")
        s.add_argument("--frames", required=True, help="frames.bin of the sealed journal")
        s.add_argument("--manifest-sha256", type=_hex64, help="admitted hash of manifest.json")
        if name == "replay":
            s.add_argument("--receipt-bound", type=_bound, required=True,
                           help="last receipt sequence number replayed (the sealed total for a full replay)")
            s.add_argument("--corpus-id", required=True)
            s.add_argument("--evidence-kind", choices=("HISTORICAL", "SYNTHETIC"), required=True)
            s.add_argument("--out", required=True, help="destination file; must not exist")
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        summary = run_verify(args) if args.cmd == "verify" else run_replay(args)
    except CliRefusal as exc:
        print(json.dumps({"status": "REFUSED", "reason": exc.reason, "subject": exc.subject}, sort_keys=True),
              file=sys.stderr)
        return EXIT_REFUSED
    except kr.ReplayRefusal as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc), "subject": "journal"}, sort_keys=True),
              file=sys.stderr)
        return EXIT_REFUSED
    except WriteFailure as exc:
        print(json.dumps({"status": "WRITE_FAILED", "reason": exc.reason, "subject": "out"}, sort_keys=True),
              file=sys.stderr)
        return EXIT_WRITE_FAILED
    print(json.dumps(summary, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
