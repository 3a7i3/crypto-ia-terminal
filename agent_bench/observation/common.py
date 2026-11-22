"""Outils communs aux agents v2 (observability-cartographer, repo-architect).

Lecture du profil à sa version exacte, rapport BLOCKED/FAILED uniforme, constats au format du
contrat (§3), scellement. Aucun réseau, aucune écriture : ces fonctions retournent des valeurs.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from agent_bench.observation import contract as c


class Blocked(Exception):
    def __init__(self, code, detail="", profile=None):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.profile = code, detail, profile


def read_profile(mission, profile_root):
    """Retourne l'entrée d'inventaire du profil (`profile:<chemin>`) ou lève Blocked."""
    prof = mission["profile"]
    try:
        pdata = (Path(profile_root) / prof["source_path"]).read_bytes()
    except OSError as exc:
        raise Blocked("PROFILE_UNREADABLE", prof["source_path"]) from exc
    pread = {"path": "profile:" + prof["source_path"], "bytes": len(pdata),
             "sha256": hashlib.sha256(pdata).hexdigest()}
    if c.git_blob_sha1(pdata) != prof["blob_sha1"]:
        raise Blocked("PROFILE_VERSION_MISMATCH", prof["source_path"], pread)
    return pread


def evidence(path, line, symbol, etype, sha=None):
    if etype not in c.EVIDENCE_TYPES:
        raise ValueError(etype)
    return {"path": path, "line": line, "symbol": symbol, "evidence_type": etype, "file_sha256": sha}


def finding(category, code, claim, level, confidence, ev):
    if level not in c.PROOF_LEVELS or confidence not in c.CONFIDENCE:
        raise ValueError(level)
    ev = sorted(ev, key=lambda e: (e["path"], e["line"] or 0, e["symbol"] or ""))
    fid = c.sha256_json({"category": category, "code": code, "evidence": ev})[:16]
    return {"finding_id": fid, "category": category, "code": code, "claim": claim, "level": level,
            "confidence": confidence, "evidence": ev}


def sort_findings(items):
    return sorted(items, key=lambda f: (f["category"], f["code"], f["finding_id"]))


def blocked_content(mission, *, version_key, version, code, detail, profile=None, extra=None, limits=()):
    m = mission if isinstance(mission, dict) else {}
    out = {
        "contract": c.REPORT_CONTRACT, version_key: version,
        "agent_id": m.get("agent_id") if isinstance(m.get("agent_id"), str) else None,
        "profile": profile, "mission_id": m.get("mission_id") if isinstance(m.get("mission_id"), str) else None,
        "analyzed_ref": m.get("analyzed_ref") if isinstance(m.get("analyzed_ref"), dict) else None,
        "status": "BLOCKED", "sources": [profile] if profile else [], "findings": [], "unknowns": [],
        "runtime_measurements_required": [], "refused_paths": [],
        "errors": [{"code": code, "detail": detail}], "limits": list(limits),
    }
    out.update(extra or {})
    return out


def seal(content_fn, mission, *, clock=time.time_ns, failed_content):
    """Exécute `content_fn()` et scelle. Une exception interne devient FAILED, jamais un succès."""
    started = clock()
    t0 = time.monotonic()
    try:
        content = content_fn(t0)
    except Exception as exc:  # noqa: BLE001
        content = failed_content("INTERNAL_ERROR", type(exc).__name__)
        content["status"] = "FAILED"
    run = {"started_utc_ns": started, "ended_utc_ns": clock(),
           "duration_ms": round((time.monotonic() - t0) * 1000, 3),
           "sources_read": len(content["sources"])}
    return c.seal_report(content, run)
