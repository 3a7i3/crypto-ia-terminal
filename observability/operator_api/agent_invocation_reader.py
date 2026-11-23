"""Lecteur en lecture seule des preuves d'invocation d'agents (contrat v1).

Aucune écriture, aucun verrou pris, aucun lancement. Le chemin des rapports vient de
`AGENT_INVOCATION_REPORTS_PATH` (défaut : `/srv/cat-obs/reports`) et n'est jamais renvoyé
au client. Seuls les agents listés ci-dessous sont lisibles, avec leur identité attendue.

Chaque agent a son dossier (registre `agent_bench.observation.agents`) : le cartographe garde
`/srv/cat-obs/reports` ; le Data Provenance Auditor lit
`/srv/cat-obs/agent-reports/observation/data-provenance-auditor` (`DPA_REPORTS_PATH`), dont le
sous-dossier `mission/` porte le pointeur de mission courante publié par son suivi de main.
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

DPA_REPORTS_PATH = Path(os.getenv(
    "DPA_REPORTS_PATH", "/srv/cat-obs/agent-reports/observation/data-provenance-auditor"))

# Cibles autorisées : identité attendue, pas de chemin ni de nom libre.
TARGETS = {
    "repository-cartographer": {
        "agent_id": "repository-cartographer",
        "runner_id": "obs-repo-cartographer-ro-01",
        "mission_id": "02e0f78f43d1062ee0efed015ad9fe37329dbe480062f02c53e32c82e19fdece",
        "profile_blob_sha1": "dd414cad0c9b73c5106d6593dd603966db14ec83",
    },
    "data-provenance-auditor": {
        "agent_id": "data-provenance-auditor",
        "runner_id": "obs-data-provenance-ro-01",
        # Mission par défaut : pilote bbo-composite-history sur main 766f4fd7 (installation 23:15Z).
        "mission_id": "f99fb24b813364bad5af4a43c4be2da3debbe35dedc351b0ecffd5741a633de4",
        "profile_blob_sha1": "45447863514be83fa0b5830f4e1491b35a9b24b1",
    },
}


def _paths(agent_id: str) -> tuple[Path, Path]:
    """(dossier des rapports, dossier du pointeur de mission) d'un agent autorisé."""
    if agent_id == "data-provenance-auditor":
        return DPA_REPORTS_PATH, DPA_REPORTS_PATH / "mission"
    return DEFAULT_REPORTS_PATH, FOLLOW_PATH


def _current(spec: dict, follow: Path | None = None) -> dict:
    """Identité attendue, avec la mission courante publiée par le suivi de main si valide."""
    try:
        raw = ((follow or _paths(spec["agent_id"])[1]) / f"{spec['agent_id']}.mission").read_bytes()[:80]
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
        summary = rd.read_status(reports or _paths(target)[0], mission_id=spec["mission_id"],
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
        out = rd.read_history(reports or _paths(target)[0], mission_id=spec["mission_id"],
                              agent_id=spec["agent_id"], runner_id=spec["runner_id"], now_ts=now,
                              expected_profile_blob=spec["profile_blob_sha1"])
    except Exception:  # noqa: BLE001 — jamais une exception brute vers le client
        out = {"contract": inv.INVOCATION_CONTRACT, "agent_id": spec["agent_id"],
               "mission_id": spec["mission_id"], "server_observed_at_utc": inv.utc_iso(now),
               "connection": "UNREADABLE", "connection_reason": "lecture impossible",
               "total": None, "items": []}
    out["read_only"] = True
    return out
