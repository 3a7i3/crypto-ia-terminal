"""Offline run coherence check. Hash consistency is not an origin or scientific certificate."""

from pathlib import Path
import hashlib
import os
import re
import stat
from .plan import PilotPlan, canonical, requests
from .store import open_directory
from observability.market_venues.decoders import strict_json
from observability.market_venues.schema import validate_publication


def verify_run(path):
    path = Path(path)
    parent = open_directory(path.parent)
    try:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("RUN_DIRECTORY_CUSTODY")
        names = set(os.listdir(fd))

        def read(name, limit=512000):
            if name not in names or not re.fullmatch(
                r"[a-z0-9][a-z0-9._-]{0,95}", name
            ):
                raise ValueError("MISSING_OR_INVALID_EVIDENCE_NAME")
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                st = os.fstat(handle)
                if (
                    not stat.S_ISREG(st.st_mode)
                    or st.st_uid != os.getuid()
                    or stat.S_IMODE(st.st_mode) != 0o400
                    or st.st_size > limit
                ):
                    raise ValueError("EVIDENCE_CUSTODY_OR_SIZE")
                with os.fdopen(os.dup(handle), "rb") as stream:
                    return stream.read(limit + 1)
            finally:
                os.close(handle)

        header = strict_json(read("plan.json"))
        if (
            header["evidence_kind"] not in ("OBSERVATION", "SYNTHETIC")
            or header["run_id"] != path.name
            or not re.fullmatch(r"[a-f0-9]{40}", header["source_sha"])
        ):
            raise ValueError("RUN_HEADER_CHANGED")
        configured = PilotPlan(**header["plan"]["parameters"])
        if header["plan"] != configured.document():
            raise ValueError("PLAN_CHANGED")
        allow = {canonical(s.document()) for s in requests()}
        intents = {
            int(m.group(1)): n
            for n in names
            if (m := re.fullmatch(r"attempt-([0-9]{4}).intent.json", n))
        }
        receipts = {
            int(m.group(1)): n
            for n in names
            if (m := re.fullmatch(r"attempt-([0-9]{4}).receipt.json", n))
        }
        if len(intents) > 4 + 6 * configured.cycles or set(receipts) - set(intents):
            raise ValueError("ATTEMPT_ROSTER_MISMATCH")
        if sorted(intents) != list(range(1, len(intents) + 1)):
            raise ValueError("ATTEMPT_SEQUENCE_CHANGED")
        books = {}
        for index in sorted(intents):
            intent_raw = read(intents[index])
            intent = strict_json(intent_raw)
            if (
                intent["ordinal"] != index
                or canonical(intent["request"]) not in allow
                or intent["evidence_kind"] != header["evidence_kind"]
            ):
                raise ValueError("INTENT_CHANGED")
            if index not in receipts:
                continue
            receipt = strict_json(read(receipts[index]))
            if (
                receipt["ordinal"] != index
                or receipt["request"] != intent["request"]
                or receipt["intent_sha256"] != hashlib.sha256(intent_raw).hexdigest()
            ):
                raise ValueError("RECEIPT_CHANGED")
            raw_name = receipt["raw_file"]
            if raw_name is not None:
                if raw_name != f"response-{index:04d}.bin":
                    raise ValueError("RAW_REFERENCE_CHANGED")
                raw = read(raw_name, configured.max_response_bytes)
                if (
                    len(raw) != receipt["raw_bytes"]
                    or hashlib.sha256(raw).hexdigest() != receipt["raw_sha256"]
                ):
                    raise ValueError("RAW_HASH_CHANGED")
                if receipt["request"]["purpose"] == "book":
                    key = (
                        receipt["request"]["venue"],
                        receipt["request"]["native_symbol"],
                        receipt["raw_sha256"],
                        receipt["received_at_utc"],
                    )
                    books[key] = True
            elif receipt["raw_sha256"] is not None or receipt["raw_bytes"] is not None:
                raise ValueError("MISSING_RAW_MISREPRESENTED")
        publications = sorted(
            n for n in names if re.fullmatch(r"publication-[0-9]{4}.json", n)
        )
        for name in publications:
            doc = strict_json(read(name))
            if (
                not validate_publication(doc)
                or doc["evidence_kind"] != header["evidence_kind"]
            ):
                raise ValueError("PUBLICATION_CHANGED")
            for group in doc["groups"]:
                for row in group["rows"]:
                    h = row["source"]["payload_sha256"]
                    if (
                        h is not None
                        and (
                            row["venue"],
                            row["native_symbol"],
                            h,
                            row["received_at_utc"],
                        )
                        not in books
                    ):
                        raise ValueError("PUBLICATION_CAPTURE_LINK_MISSING")
        result = strict_json(read("run-result.json"))
        if (
            result["source_sha"] != header["source_sha"]
            or result["evidence_kind"] != header["evidence_kind"]
            or result["activation_authority_granted"] is not False
            or result["status"] not in ("COMPLETED", "STOPPED", "INCOMPLETE")
            or result["run_id"] != path.name
            or result["requests_attempted"] != len(intents)
            or result["cycles_published"] != len(publications)
        ):
            raise ValueError("RUN_RESULT_CHANGED")
        if result["status"] == "COMPLETED" and (
            len(publications) != configured.cycles
            or len(intents) != 4 + 6 * configured.cycles
            or result["stopped_reason"] is not None
        ):
            raise ValueError("FALSE_COMPLETE_RUN")
        if publications != [
            f"publication-{i:04d}.json" for i in range(1, len(publications) + 1)
        ]:
            raise ValueError("PUBLICATION_SEQUENCE_CHANGED")
        for i in range(1, len(publications) + 1):
            quality = strict_json(read(f"quality-{i:04d}.json"))
            if quality["cycle"] != i or quality["clock_id"] != path.name:
                raise ValueError("QUALITY_RECEIPT_CHANGED")
        pending = sorted(set(intents) - set(receipts))
        if pending and result["status"] != "INCOMPLETE":
            raise ValueError("PENDING_CAPTURE_HIDDEN")
        last = result["last_snapshot"]
        if last is None:
            if publications or "latest.json" in names:
                raise ValueError("UNRECORDED_PUBLICATION")
        else:
            if (
                last["file"] != publications[-1]
                or hashlib.sha256(read(last["file"])).hexdigest() != last["sha256"]
                or read("latest.json") != read(last["file"])
            ):
                raise ValueError("LATEST_REFERENCE_CHANGED")
        return {
            "status": "LOCAL_COHERENCE_PASS",
            "evidence_kind": header["evidence_kind"],
            "intents": len(intents),
            "receipts": len(receipts),
            "pending_ordinals": pending,
            "publications": len(publications),
            "run_status": result["status"],
            "capture_population_complete": not pending,
            "origin_certified": False,
            "scientific_certified": False,
        }
    finally:
        os.close(fd)
