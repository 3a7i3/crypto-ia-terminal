"""Contrat commun d'une mission Observation — ``cat.observation.mission.v1``.

Banc isolé uniquement : ce module valide une mission, calcule son identité
déterministe et scelle un rapport. Il n'ouvre aucun réseau, ne lit aucun secret,
n'écrit dans aucune donnée de production et n'accorde aucune autorité. Un rapport
scellé n'est jamais « valide » par lui-même : la validation appartient au banc
de tests et à la revue humaine (docs/contracts/AGENT_OBSERVATION_MISSION_V1.md).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

MISSION_CONTRACT = "cat.observation.mission.v1"
REPORT_CONTRACT = "cat.observation.report.v1"
MISSION_IDENTITY_SCHEMA = "cat.observation.mission-identity.v1"

# Profils exécutables au banc. data-provenance-auditor : pilote (chaîne de dataset).
# repository-cartographer : cartographie statique d'une zone (PR #598, lot 2).
# Les deux autres profils n'ont qu'une fiche : une mission les visant est BLOCKED.
EXECUTABLE_AGENTS = ("data-provenance-auditor", "repository-cartographer")
QUESTION_KIND_BY_AGENT = {
    "data-provenance-auditor": "DATASET_PROVENANCE_CHAIN",
    "repository-cartographer": "REPOSITORY_MAP",
}
# Budget de fichiers d'une cartographie de zone (lot 2 : au plus 30 sources .py).
REPOSITORY_MAP_MAX_FILES = 30
OBSERVATION_AGENTS = ("data-provenance-auditor", "observability-cartographer",
                      "repository-cartographer", "repo-architect")

MISSION_STATUSES = ("COMPLETE", "PARTIAL", "BLOCKED", "FAILED")
PROOF_LEVELS = ("PROVEN", "SUPPORTED", "INFERRED", "INCONCLUSIVE", "NOT_FOUND")
EVIDENCE_TYPES = ("CODE", "CALL_SITE", "IMPORT", "LITERAL", "CAPTURE_FIELD", "FILE_STAT", "MISSION_INPUT")
CONFIDENCE = ("HIGH", "MEDIUM", "LOW")
QUESTION_KINDS = ("DATASET_PROVENANCE_CHAIN", "REPOSITORY_MAP")
UNITS = ("EPOCH_MS", "DURATION_MS", "UTC_ISO_SECONDS", "DECIMAL_STRING_BPS", "COUNT")

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UTC_SECONDS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
POINTER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[\*\])?(\.[A-Za-z_][A-Za-z0-9_]*(\[\*\])?)*$")

# Grammaire des chemins : celle de A1 §4 (repository_read_paths), appliquée ici.
_SECRET_NAME = re.compile(r"(^|/)(\.env[^/]*|id_rsa[^/]*|id_ed25519[^/]*|[^/]*\.(pem|key|p12|pfx))$", re.IGNORECASE)
_SECRET_DIR = re.compile(r"(^|/)secrets?/", re.IGNORECASE)


class MissionRejected(ValueError):
    """Entrée refusée avant toute lecture : la mission devient BLOCKED."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def canonical_bytes(value):
    """Sérialisation canonique (A1 §3.1, précédent research_candidate/candidate.py)."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256_json(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def path_violation(path):
    """Retourne un code de rejet si le chemin sort de la grammaire, sinon None."""
    if not isinstance(path, str) or not path or path != path.strip():
        return "SCOPE_PATH_INVALID"
    if unicodedata.normalize("NFC", path) != path:
        return "SCOPE_PATH_INVALID"
    if path.startswith("/") or "\\" in path or "//" in path or any(c in path for c in "*?[]"):
        return "SCOPE_PATH_INVALID"
    if any(part in ("..", ".") for part in path.rstrip("/").split("/")):
        return "SCOPE_PATH_INVALID"
    if _SECRET_NAME.search(path.rstrip("/")) or _SECRET_DIR.search(path if path.endswith("/") else path + "/"):
        return "SECRET_PATH_REQUESTED"
    return None


def is_secret_like(rel_path):
    return bool(_SECRET_NAME.search(rel_path) or _SECRET_DIR.search(rel_path))


def mission_identity(m):
    """Document d'identité : tout ce qui définit la question, rien d'horodaté."""
    return {
        "mission_identity_schema": MISSION_IDENTITY_SCHEMA,
        "agent_id": m["agent_id"],
        "profile": m["profile"],
        "analyzed_ref": m["analyzed_ref"],
        "scope": m["scope"],
        "question": m["question"],
        "budget": m["budget"],
        "capture": m["capture"],
    }


def compute_mission_id(m):
    return sha256_json(mission_identity(m))


def _keys(obj, keys, where):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", where)


def _int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def validate_mission(m):
    """Validation structurelle fermée. Lève MissionRejected ; ne corrige jamais."""
    _keys(m, ("contract", "agent_id", "profile", "mission_id", "analyzed_ref", "scope",
              "question", "budget", "capture"), "top")
    if m["contract"] != MISSION_CONTRACT:
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "contract")
    if m["agent_id"] not in OBSERVATION_AGENTS:
        raise MissionRejected("AGENT_UNKNOWN", str(m["agent_id"]))
    if m["agent_id"] not in EXECUTABLE_AGENTS:
        raise MissionRejected("AGENT_NOT_QUALIFIED_FOR_BENCH", m["agent_id"])
    p = m["profile"]
    _keys(p, ("source_path", "blob_sha1"), "profile")
    if path_violation(p["source_path"]) or not HEX40.match(str(p["blob_sha1"])):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "profile")
    ref = m["analyzed_ref"]
    _keys(ref, ("kind", "sha"), "analyzed_ref")
    if not ((ref["kind"] == "GIT_COMMIT" and HEX40.match(str(ref["sha"])))
            or (ref["kind"] == "FIXTURE_TREE" and HEX64.match(str(ref["sha"])))):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "analyzed_ref")
    s = m["scope"]
    _keys(s, ("read_paths",), "scope")
    paths = s["read_paths"]
    if not isinstance(paths, list) or not paths or paths != sorted(set(paths)):
        raise MissionRejected("SCOPE_ARRAY_NOT_CANONICAL", "read_paths must be sorted and unique")
    for path in paths:
        code = path_violation(path)
        if code:
            raise MissionRejected(code, path)
    kind = m["question"]["kind"] if isinstance(m["question"], dict) else None
    if kind not in QUESTION_KINDS or QUESTION_KIND_BY_AGENT[m["agent_id"]] != kind:
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.kind does not match agent_id")
    b = m["budget"]
    _keys(b, ("max_files", "max_bytes", "max_wall_ms"), "budget")
    if not (_int(b["max_files"], 1, 5000) and _int(b["max_bytes"], 1, 64_000_000) and _int(b["max_wall_ms"], 1, 600_000)):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "budget")
    if kind == "REPOSITORY_MAP":
        _validate_repository_map(m, paths)
    else:
        _validate_dataset_chain(m, paths)
    if not HEX64.match(str(m["mission_id"])) or m["mission_id"] != compute_mission_id(m):
        raise MissionRejected("MISSION_ID_MISMATCH", "mission_id is not the hash of its identity document")
    return m


def _validate_repository_map(m, paths):
    q = m["question"]
    _keys(q, ("kind", "zone_id", "text"), "question")
    if not SLUG.match(str(q["zone_id"])) or not isinstance(q["text"], str) or not 10 <= len(q["text"]) <= 600:
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.zone_id/text")
    if m["budget"]["max_files"] > REPOSITORY_MAP_MAX_FILES:
        raise MissionRejected("FILE_BUDGET_EXCEEDED", f"max_files > {REPOSITORY_MAP_MAX_FILES}")
    if m["capture"] is not None:
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "REPOSITORY_MAP takes no capture")


def _validate_dataset_chain(m, paths):
    q = m["question"]
    _keys(q, ("kind", "dataset_id", "text", "as_of_utc", "max_source_age_ms", "source_ts",
              "write_ts", "units", "join_checks", "observation_key"), "question")
    if not isinstance(q["dataset_id"], str) or not q["dataset_id"]:
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.dataset_id")
    if not isinstance(q["text"], str) or not 10 <= len(q["text"]) <= 600:
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.text")
    if not UTC_SECONDS.match(str(q["as_of_utc"])):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.as_of_utc")
    if q["max_source_age_ms"] is not None and not _int(q["max_source_age_ms"], 1, 2**53 - 1):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.max_source_age_ms")
    for k in ("source_ts", "write_ts"):
        if not POINTER.match(str(q[k])):
            raise MissionRejected("MISSION_SCHEMA_VIOLATION", f"question.{k}")
    if not isinstance(q["units"], dict) or not all(POINTER.match(k) and v in UNITS for k, v in q["units"].items()):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.units")
    if not isinstance(q["join_checks"], list):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.join_checks")
    for j in q["join_checks"]:
        _keys(j, ("left", "right", "relation"), "join_check")
        if not (POINTER.match(str(j["left"])) and POINTER.match(str(j["right"]))) \
                or j["relation"] not in ("EQUALS", "CONTAINED_IN", "SAME_LENGTH"):
            raise MissionRejected("MISSION_SCHEMA_VIOLATION", "join_check")
    ok = q["observation_key"]
    if not isinstance(ok, list) or not ok or not all(POINTER.match(str(x)) for x in ok):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "question.observation_key")
    c = m["capture"]
    _keys(c, ("capture_id", "path", "sha256", "kind"), "capture")
    if not SLUG.match(str(c["capture_id"])) or not HEX64.match(str(c["sha256"])) \
            or c["kind"] not in ("FIXTURE", "COMMITTED_FIXTURE", "AUTHORIZED_CAPTURE"):
        raise MissionRejected("MISSION_SCHEMA_VIOLATION", "capture")
    code = path_violation(c["path"])
    if code:
        raise MissionRejected(code, c["path"])
    if not any(c["path"] == r or (r.endswith("/") and c["path"].startswith(r)) for r in paths):
        raise MissionRejected("CAPTURE_OUT_OF_SCOPE", c["path"])


def seal_report(content, run):
    """Sépare le contenu déterministe des métadonnées d'exécution et scelle les deux."""
    content_sha = sha256_json(content)
    body = {"content": content, "content_sha256": content_sha, "run": run}
    return {**body, "report_sha256": sha256_json(body)}
