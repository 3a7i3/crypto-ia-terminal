"""Journal d'audit local de SENTINEL-01 : opt-in, expurgé, borné, fail-closed.

Rétention proposée : un fichier par session de prototype, plafonné à 1 Mio ;
aucune rotation automatique (au-delà du plafond, l'écriture s'arrête et le run
le signale). Le journal ne contient ni réponse complète, ni contenu externe, ni
secret : seulement l'identité du run, l'intention, les outils, leurs états et
les codes de refus.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

from governance_tower.contracts import AgentRun
from governance_tower.redaction import redact

DEFAULT_MAX_BYTES = 1_048_576


class AuditUnavailable(RuntimeError):
    pass


class AuditLog:
    def __init__(self, path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        parent = self.path.parent
        if not parent.is_dir() or parent.is_symlink():
            raise AuditUnavailable("répertoire d'audit absent ou lien symbolique refusé")

    @staticmethod
    def record_for(run: AgentRun) -> dict:
        request, _ = redact(run.request[:200])
        return {
            "schema": "gt-audit/1",
            "run_id": run.run_id,
            "agent_id": run.agent_id,
            "capability": run.capability,
            "mode": run.mode,
            "started_at_utc": run.started_at_utc,
            "finished_at_utc": run.finished_at_utc,
            "intent": run.intent.value,
            "request_excerpt": request,
            "tools": [[c.tool, c.availability.value] for c in run.tool_calls],
            "refusals": [r.code for r in run.answer.refusals],
            "evidence_count": len(run.evidence),
            "findings": [f.finding_id for f in run.answer.findings],
        }

    def append(self, run: AgentRun) -> bool:
        """Ajoute une ligne ; retourne False (sans lever) si le plafond est atteint."""
        line = (json.dumps(self.record_for(run), sort_keys=True, ensure_ascii=False) + "\n").encode()
        with self._lock:
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags, 0o600)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    raise AuditUnavailable("cible d'audit non régulière")
                if st.st_size + len(line) > self.max_bytes:
                    return False
                os.write(fd, line)
                return True
            finally:
                os.close(fd)
