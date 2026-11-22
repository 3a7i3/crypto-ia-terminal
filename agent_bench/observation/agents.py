"""Registre d'exécution des agents d'observation et dossier de stockage de chacun.

Une ligne par agent : type de question, runner proposé, fonction d'analyse, bornes et **dossier
de stockage sur le VPS**. Règle données (Mathieu, 2026-11-22) : les rapports restent sur le disque
du VPS, jamais dans GitHub ; ils n'ont qu'une valeur momentanée (``keep_last``, pas d'archive).

Disposition d'un dossier d'agent (créée par l'exécuteur au premier passage, sauf MANIFEST.json et
summary.json, écrits par ce module sur demande) :

    <storage_dir>/
      MANIFEST.json                 identité de l'agent et disposition (ce module, ``manifest``)
      summary.json                  résumé borné des preuves, pour l'inventaire de stockage (``summary``)
      locks/<runner_id>.lock        verrou noyau de l'exécuteur
      runs/<mission_id>/<AAAAMMJJThhmmssZ>_<invocation_id>.json   une enveloppe par passage
      mission/                      mission courante dérivée (suivi de main, si utilisé)

Racine : ``/srv/cat-obs/agent-reports/observation/<agent>`` (arborescence par famille préparée sur
le VPS le 22/11). Le cartographe garde son dossier historique ``/srv/cat-obs/reports`` (installé le 22/11) : le
déplacer est une décision séparée. Ce module n'installe rien, ne crée aucun utilisateur ni unité.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_bench.observation import contract as c
from agent_bench.observation import invocation as inv

STORAGE_CONTRACT = "cat.observation.agent-storage.v1"
SUMMARY_CONTRACT = "cat.observation.agent-storage-summary.v1"
# Arborescence préparée sur le VPS le 2026-11-22 (~22:03Z, script cat-agent-report-dirs-prepare.sh) :
# /srv/cat-obs/agent-reports/<famille>/<agent>, une famille par groupe du registre Système.
STORAGE_ROOT = "/srv/cat-obs/agent-reports/observation"
MAX_SUMMARY_ENTRIES = 5000


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    question_kind: str
    mission_contract: str
    runner_id: str
    profile_path: str
    storage_dir: str
    max_files: int
    keep_last: int
    schedule: str
    status: str


AGENTS = {
    "repository-cartographer": AgentSpec(
        "repository-cartographer", "REPOSITORY_MAP", c.MISSION_CONTRACT, "obs-repo-cartographer-ro-01",
        ".github/agents/repository-cartographer.agent.md", "/srv/cat-obs/reports",
        c.REPOSITORY_MAP_MAX_FILES, 20, "SUIVI_DE_MAIN", "INSTALLE"),
    "data-provenance-auditor": AgentSpec(
        "data-provenance-auditor", "DATASET_PROVENANCE_CHAIN", c.MISSION_CONTRACT, "obs-data-provenance-ro-01",
        ".github/agents/data-provenance-auditor.agent.md", f"{STORAGE_ROOT}/data-provenance-auditor",
        inv.MAX_FILES_BY_KIND["DATASET_PROVENANCE_CHAIN"], 20, "SUIVI_DE_MAIN", "NON_INSTALLE"),
    "observability-cartographer": AgentSpec(
        "observability-cartographer", "METRIC_SURFACE_MAP", c.MISSION_CONTRACT_V2, "obs-observability-ro-01",
        ".github/agents/observability-cartographer.agent.md", f"{STORAGE_ROOT}/observability-cartographer",
        c.METRIC_SURFACE_MAX_FILES, 20, "SUIVI_DE_MAIN", "NON_INSTALLE"),
    "repo-architect": AgentSpec(
        "repo-architect", "CHANGE_IMPACT", c.MISSION_CONTRACT_V2, "obs-repo-architect-ro-01",
        ".github/repo-architect.agent.md", f"{STORAGE_ROOT}/repo-architect",
        c.CHANGE_IMPACT_MAX_FILES, 20, "A_LA_DEMANDE", "NON_INSTALLE"),
}


def spec(agent_id) -> AgentSpec:
    try:
        return AGENTS[agent_id]
    except KeyError as exc:
        raise ValueError(f"AGENT_UNKNOWN: {agent_id}") from exc


def manifest(agent_id) -> dict:
    """Document statique décrivant le dossier : ce que GPT/l'inventaire peut répertorier."""
    s = spec(agent_id)
    return {
        "contract": STORAGE_CONTRACT, **asdict(s),
        "domain": "observation-reports", "authority": "OBSERVATION", "git_policy": "NEVER",
        "retention": {"kind": "KEEP_LAST", "n": s.keep_last, "archive": "NONE"},
        "layout": {"runs": "runs/<mission_id>/<AAAAMMJJThhmmssZ>_<invocation_id>.json",
                   "locks": "locks/<runner_id>.lock", "mission": "mission/", "summary": "summary.json"},
        "envelope_contract": inv.INVOCATION_CONTRACT,
        "max_dir_entries": inv.MAX_DIR_ENTRIES,
    }


def _bounded_scandir(fd):
    with os.scandir(fd) as it:
        for i, e in enumerate(it):
            if i >= inv.MAX_DIR_ENTRIES:
                raise ValueError("REPORTS_DIR_OVERFLOW")
            yield e


def summary(agent_id, root: Path, *, now_ts=None) -> dict:
    """Résumé borné des preuves d'un dossier d'agent. Lecture seule, ne suit aucun lien.

    Compte, par dossier de mission, les enveloppes au nom canonique et leur volume ; lit la plus
    récente pour en rapporter l'état. Une panne de lecture n'est pas une population vide :
    `readable=false` et un motif, jamais des zéros.
    """
    s = spec(agent_id)
    out = {"contract": SUMMARY_CONTRACT, "agent_id": agent_id, "runner_id": s.runner_id,
           "storage_dir": str(root), "observed_at_utc": inv.utc_now_iso(now_ts), "readable": False,
           "reason": None, "missions": None, "envelopes": None, "bytes": None, "latest": None}
    try:
        rfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        out["reason"] = "DOSSIER_ABSENT"
        return out
    except OSError as exc:
        out["reason"] = f"ILLISIBLE:{type(exc).__name__}"
        return out
    try:
        try:
            runs = os.open("runs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=rfd)
        except FileNotFoundError:
            out.update(readable=True, reason="AUCUN_PASSAGE", missions=0, envelopes=0, bytes=0)
            return out
        missions = envelopes = total = 0
        latest = None
        try:
            for m in _bounded_scandir(runs):
                if not (m.is_dir(follow_symlinks=False) and inv.HEX64.match(m.name)):
                    continue
                missions += 1
                mfd = os.open(m.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=runs)
                try:
                    for e in _bounded_scandir(mfd):
                        if not inv.NAME_RE.match(e.name):
                            continue
                        st = e.stat(follow_symlinks=False)
                        if not stat.S_ISREG(st.st_mode):
                            continue
                        envelopes += 1
                        total += st.st_size
                        key = (e.name[:16], e.name)
                        if latest is None or key > latest[0]:
                            latest = (key, m.name, e.name)
                finally:
                    os.close(mfd)
        finally:
            os.close(runs)
        out.update(readable=True, missions=missions, envelopes=envelopes, bytes=total)
        if latest:
            _, mid, name = latest
            info = {"mission_id": mid, "file": name, "state": None, "result_status": None,
                    "started_utc": None, "ended_utc": None, "content_sha256": None}
            try:
                fd = os.open(f"runs/{mid}/{name}", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=rfd)
                with os.fdopen(fd, "rb") as fh:
                    env = inv.json_load_bounded(fh.read(inv.MAX_PROOF_BYTES + 1))
                for key in ("state", "result_status", "started_utc", "ended_utc", "content_sha256"):
                    info[key] = env.get(key) if isinstance(env, dict) else None
            except (OSError, ValueError):
                info["state"] = "ILLISIBLE"
            out["latest"] = info
        return out
    except ValueError as exc:
        out.update(readable=False, reason=str(exc).split(":")[0])
        return out
    except OSError as exc:
        out.update(readable=False, reason=f"ILLISIBLE:{type(exc).__name__}")
        return out
    finally:
        os.close(rfd)


def _atomic_write(path: Path, data: bytes):
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o640)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m agent_bench.observation.agents",
                                 description="Registre des agents d'observation et de leurs dossiers de stockage.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="registre complet (JSON)")
    pm = sub.add_parser("manifest", help="MANIFEST.json d'un agent")
    pm.add_argument("--agent", required=True)
    pm.add_argument("--write", action="store_true", help="écrit <dossier>/MANIFEST.json au lieu d'afficher")
    pm.add_argument("--root", default=None, help="dossier de l'agent (défaut : celui du registre)")
    ps = sub.add_parser("summary", help="résumé borné des preuves d'un agent")
    ps.add_argument("--agent", required=True)
    ps.add_argument("--root", default=None)
    ps.add_argument("--write", action="store_true", help="écrit <dossier>/summary.json")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            print(json.dumps({aid: manifest(aid) for aid in sorted(AGENTS)}, ensure_ascii=False, indent=2))
            return 0
        root = Path(a.root or spec(a.agent).storage_dir)
        doc = manifest(a.agent) if a.cmd == "manifest" else summary(a.agent, root)
        data = (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        if a.write:
            _atomic_write(root / ("MANIFEST.json" if a.cmd == "manifest" else "summary.json"), data)
        else:
            sys.stdout.write(data.decode())
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"outcome": "REFUSED", "detail": f"{type(exc).__name__}:{str(exc)[:80]}"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
