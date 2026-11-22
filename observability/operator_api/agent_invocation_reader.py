"""Lecteur en lecture seule des preuves d'invocation d'agents (contrat v1).

Aucune écriture, aucun verrou créé, aucun lancement. Le chemin des rapports vient de
`AGENT_INVOCATION_REPORTS_PATH` (défaut : `/srv/cat-obs/reports`) et n'est jamais renvoyé
au client. Seuls les agents listés ci-dessous sont lisibles.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from agent_bench.observation import invocation_reader as rd

DEFAULT_REPORTS_PATH = Path(os.getenv("AGENT_INVOCATION_REPORTS_PATH", "/srv/cat-obs/reports"))

# Cibles autorisées : identité attendue, pas de chemin ni de nom libre.
TARGETS = {
    "repository-cartographer": {
        "agent_id": "repository-cartographer",
        "runner_id": "obs-repo-cartographer-ro-01",
        "mission_id": "02e0f78f43d1062ee0efed015ad9fe37329dbe480062f02c53e32c82e19fdece",
    },
}


def read_agent_invocation(target: str, *, reports: Path | None = None, now_ts: float | None = None) -> dict:
    spec = TARGETS.get(target)
    if spec is None:
        raise KeyError(target)
    now = time.time() if now_ts is None else now_ts
    try:
        summary = rd.read_status(reports or DEFAULT_REPORTS_PATH, mission_id=spec["mission_id"],
                                 agent_id=spec["agent_id"], runner_id=spec["runner_id"], now_ts=now)
    except Exception:  # noqa: BLE001 — jamais une exception brute vers le client
        summary = {"connection": "UNREADABLE", "connection_reason": "lecture impossible",
                   "activity": "INDETERMINE", "activity_reason": None, "last_activity_utc": None,
                   "last_result": None, "last_state": None, "invocation_id": None, "lock": None,
                   "observed_at_utc": None, "agent_id": spec["agent_id"], "runner_id": spec["runner_id"],
                   "mission_id": spec["mission_id"]}
    summary["read_only"] = True
    return summary
