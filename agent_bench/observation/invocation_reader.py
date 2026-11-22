"""Lecteur en lecture seule des preuves d'invocation (contrat v1).

Renvoie trois états séparés pour Système :
- connexion et preuve : AVAILABLE, ABSENT, ACCESS_DENIED, INCOMPLETE, INVALID, UNREADABLE ;
- activité : EN_COURS (bail de verrou valide), TERMINE (dernière invocation terminée),
  INDETERMINE (aucune preuve, ou verrou expiré) ;
- dernier résultat : COMPLETE, PARTIAL, BLOCKED, FAILED, ou None.

Règles :
- relire un ancien fichier ne rajeunit jamais son activité : last_activity_utc est la
  fin de l'invocation consignée, pas la date de lecture ;
- un fichier caché, un lien symbolique, un nom non conforme ou un fichier trop grand est
  ignoré ou refusé, jamais interprété ;
- l'invocation la plus récente qui est invalide rend l'état INVALID, sans repli silencieux
  sur une invocation plus ancienne.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from agent_bench.observation import invocation as inv

NAME_OK = re.compile(r"^(\d{8}T\d{6}Z)_([0-9a-f]{32})\.json$")
MAX_LIST = inv.MAX_FILES_LISTED


def _read_bounded(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("NOT_REGULAR")
        if st.st_size > inv.MAX_PROOF_BYTES:
            raise ValueError("TOO_LARGE")
        return os.read(fd, inv.MAX_PROOF_BYTES + 1)
    finally:
        os.close(fd)


def read_lock(reports: Path, runner_id: str, now_ts: float):
    lock = reports / "locks" / f"{runner_id}.lock"
    try:
        data = json.loads(_read_bounded(lock).decode("utf-8"))
    except FileNotFoundError:
        return {"present": False, "activity": None}
    except PermissionError:
        return {"present": None, "activity": "INDETERMINE", "reason": "ACCESS_DENIED"}
    except (ValueError, OSError):
        return {"present": True, "activity": "INDETERMINE", "reason": "VERROU_ILLISIBLE"}
    lease = inv.parse_utc(data.get("lease_until_utc"))
    started = inv.parse_utc(data.get("started_utc"))
    if lease is None or started is None:
        return {"present": True, "activity": "INDETERMINE", "reason": "VERROU_INCOMPLET"}
    if started > now_ts + inv.CLOCK_SKEW_S:
        return {"present": True, "activity": "INDETERMINE", "reason": "DATE_FUTURE"}
    if lease > now_ts:
        return {"present": True, "activity": "EN_COURS", "reason": "bail valide",
                "invocation_id": data.get("invocation_id"), "started_utc": data.get("started_utc"),
                "lease_until_utc": data.get("lease_until_utc")}
    return {"present": True, "activity": "INDETERMINE", "reason": "bail expiré : aucune exécution attestée"}


def read_status(reports: Path, *, mission_id: str, agent_id: str, runner_id: str, now_ts: float):
    """Résumé pour Système. Ne lève pas : toute erreur devient un état explicite."""
    out = {"contract": inv.INVOCATION_CONTRACT, "agent_id": agent_id, "runner_id": runner_id,
           "mission_id": mission_id, "observed_at_utc": inv.utc_now_iso(now_ts),
           "connection": None, "connection_reason": None, "activity": "INDETERMINE",
           "activity_reason": None, "last_activity_utc": None, "last_result": None,
           "last_state": None, "invocation_id": None, "lock": None}

    lock = read_lock(reports, runner_id, now_ts)
    out["lock"] = {k: v for k, v in lock.items() if k in ("present", "reason")}
    if lock.get("activity") == "EN_COURS":
        out["activity"] = "EN_COURS"
        out["activity_reason"] = lock["reason"]
    elif lock.get("present"):
        out["activity_reason"] = lock.get("reason")

    d = reports / "runs" / mission_id
    try:
        if not d.is_dir():
            out["connection"], out["connection_reason"] = "ABSENT", "aucun dossier de preuves"
            return out
        names = sorted(n for n in os.listdir(d) if not n.startswith("."))[-MAX_LIST:]
    except PermissionError:
        out["connection"], out["connection_reason"] = "ACCESS_DENIED", "lecture du dossier refusée"
        return out
    except OSError:
        out["connection"], out["connection_reason"] = "UNREADABLE", "dossier illisible"
        return out

    candidates = [n for n in names if NAME_OK.match(n)]
    if not candidates:
        out["connection"], out["connection_reason"] = "ABSENT", "aucune invocation consignée"
        return out

    latest = candidates[-1]
    try:
        env = json.loads(_read_bounded(d / latest).decode("utf-8"))
    except PermissionError:
        out["connection"], out["connection_reason"] = "ACCESS_DENIED", "lecture refusée"
        return out
    except (ValueError, OSError) as exc:
        out["connection"], out["connection_reason"] = "INVALID", f"fichier illisible ({exc.__class__.__name__})"
        return out

    verdict = inv.classify_latest(env, now_ts, agent_id=agent_id, runner_id=runner_id, mission_id=mission_id)
    out["invocation_id"] = env.get("invocation_id") if isinstance(env, dict) else None
    out["last_state"] = env.get("state") if isinstance(env, dict) else None
    if verdict["proof"] != "VALID":
        out["connection"] = "INCOMPLETE" if verdict["proof"] == "INCOMPLETE" else "INVALID"
        out["connection_reason"] = f"{verdict['proof']}: {verdict['reason']}"
        out["activity"] = "EN_COURS" if out["activity"] == "EN_COURS" else "INDETERMINE"
        return out

    out["connection"], out["connection_reason"] = "AVAILABLE", "dernière preuve valide"
    out["last_result"] = verdict["result_status"]
    if out["activity"] != "EN_COURS":
        # Une invocation terminée ne prouve pas une activité en cours. Sa date est la fin consignée.
        out["activity"] = "TERMINE"
        out["activity_reason"] = f"dernière invocation {env['state']}"
        out["last_activity_utc"] = env["ended_utc"]
    return out
