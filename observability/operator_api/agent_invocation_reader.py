"""Lecteur en lecture seule des preuves d'invocation d'agents (contrat v1).

Aucune écriture, aucun verrou pris, aucun lancement. Le chemin des rapports vient de
`AGENT_INVOCATION_REPORTS_PATH` (défaut : `/srv/cat-obs/reports`) et n'est jamais renvoyé
au client. Seuls les agents listés ci-dessous sont lisibles, avec leur identité attendue.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from agent_bench.observation import invocation as inv
from agent_bench.observation import invocation_reader as rd

DEFAULT_REPORTS_PATH = Path(os.getenv("AGENT_INVOCATION_REPORTS_PATH", "/srv/cat-obs/reports"))
# Suivi de main (décision Mathieu 2026-11-22 10:28Z) : l'unité de suivi publie ici l'identifiant
# de la mission courante. Absent ou illisible : mission figée par défaut.
FOLLOW_PATH = Path(os.getenv("AGENT_INVOCATION_FOLLOW_PATH", "/srv/cat-obs/follow"))

# Cibles autorisées : identité attendue, pas de chemin ni de nom libre.
TARGETS = {
    "repository-cartographer": {
        "agent_id": "repository-cartographer",
        "runner_id": "obs-repo-cartographer-ro-01",
        "mission_id": "02e0f78f43d1062ee0efed015ad9fe37329dbe480062f02c53e32c82e19fdece",
        "profile_blob_sha1": "dd414cad0c9b73c5106d6593dd603966db14ec83",
    },
}


def _current(spec: dict, follow: Path | None = None) -> dict:
    """Identité attendue, avec la mission courante publiée par le suivi de main si valide."""
    try:
        raw = ((follow or FOLLOW_PATH) / f"{spec['agent_id']}.mission").read_bytes()[:80]
        mid = raw.decode("ascii").strip()
    except (OSError, UnicodeDecodeError):
        return spec
    return {**spec, "mission_id": mid} if inv.HEX64.match(mid) else spec


def read_agent_invocation(target: str, *, reports: Path | None = None, now_ts: float | None = None) -> dict:
    if target not in TARGETS:
        raise KeyError(target)
    spec = _current(TARGETS[target])
    now = time.time() if now_ts is None else now_ts
    try:
        summary = rd.read_status(reports or DEFAULT_REPORTS_PATH, mission_id=spec["mission_id"],
                                 agent_id=spec["agent_id"], runner_id=spec["runner_id"], now_ts=now,
                                 expected_profile_blob=spec["profile_blob_sha1"])
    except Exception:  # noqa: BLE001 — jamais une exception brute vers le client
        summary = {"contract": inv.INVOCATION_CONTRACT, "agent_id": spec["agent_id"],
                   "runner_id": spec["runner_id"], "mission_id": spec["mission_id"],
                   "server_observed_at_utc": inv.utc_iso(now), "connection": "UNREADABLE",
                   "connection_reason": "lecture impossible", "activity": "INDETERMINE",
                   "activity_reason": None, "life_observed": False, "lease_until_utc": None,
                   "last_activity_utc": None, "last_mission_age_s": None, "mission_overdue": False,
                   "last_result": None, "last_state": None, "invocation_id": None,
                   "display": {"light": "GRAY", "label": "Non attesté", "reason": "lecture impossible",
                               "valid_until_utc": None}}
    summary["read_only"] = True
    return summary


def read_agent_history(target: str, *, reports: Path | None = None, now_ts: float | None = None) -> dict:
    if target not in TARGETS:
        raise KeyError(target)
    spec = _current(TARGETS[target])
    now = time.time() if now_ts is None else now_ts
    try:
        out = rd.read_history(reports or DEFAULT_REPORTS_PATH, mission_id=spec["mission_id"],
                              agent_id=spec["agent_id"], runner_id=spec["runner_id"], now_ts=now,
                              expected_profile_blob=spec["profile_blob_sha1"])
    except Exception:  # noqa: BLE001 — jamais une exception brute vers le client
        out = {"contract": inv.INVOCATION_CONTRACT, "agent_id": spec["agent_id"],
               "mission_id": spec["mission_id"], "server_observed_at_utc": inv.utc_iso(now),
               "connection": "UNREADABLE", "connection_reason": "lecture impossible",
               "total": None, "items": []}
    out["read_only"] = True
    return out
