"""Exécuteur ponctuel du Repository Cartographer (contrat d'invocation v1).

Ponctuel : une invocation par appel explicite. Aucun démon, aucun timer, aucune relance.

Garanties :
- un seul runner à la fois : verrou `locks/<runner_id>.lock` créé en O_EXCL ;
- verrou avec bail : un verrou dont le bail est dépassé est repris, et l'invocation
  précédente est consignée ABANDONED (aucun « en cours » permanent) ;
- publication atomique : l'enveloppe est écrite dans un fichier caché, puis liée sous son
  nom définitif par os.link, qui échoue si le nom existe (aucun écrasement) ;
- le lecteur ignore les fichiers cachés et les noms non conformes : un fichier incomplet
  ne devient jamais une preuve ;
- limites explicites : durée (signal d'alarme) et fichiers (budget de la mission, ≤ 30).
"""
from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import time
from pathlib import Path

from agent_bench.observation import contract as c
from agent_bench.observation import invocation as inv
from agent_bench.observation import repository_cartographer as rc

LOCK_LEASE_S = 600          # durée maximale d'un bail
MAX_RUN_S = 120             # limite de durée d'une invocation (durée mesurée : ~0,2 s)
NAME_RE = "{stamp}_{inv}.json"


class Refused(Exception):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class _Timeout(Exception):
    pass


def _now_s():
    return time.time()


def _stamp(ts):
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(ts))


def _git_head(root: Path):
    """SHA du checkout réellement présent, si le checkout est un dépôt git ; sinon None."""
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10, check=True)
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def _acquire_lock(lock: Path, runner_id, invocation_id, mission_id, now):
    body = json.dumps({"runner_id": runner_id, "invocation_id": invocation_id,
                       "mission_id": mission_id, "started_utc": inv.utc_now_iso(now),
                       "lease_until_utc": inv.utc_now_iso(now + LOCK_LEASE_S)}).encode()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640)
    except FileExistsError:
        old = json.loads(lock.read_text(encoding="utf-8"))
        lease = inv.parse_utc(old.get("lease_until_utc"))
        if lease is not None and lease > now:
            raise Refused("ALREADY_RUNNING", f"invocation {old.get('invocation_id')} en cours")
        # Bail dépassé : reprise explicite, l'ancienne invocation est consignée ABANDONED.
        taken = lock.with_name(lock.name + f".stale-{secrets.token_hex(4)}")
        try:
            os.rename(lock, taken)          # une seule reprise peut réussir
        except FileNotFoundError as exc:
            raise Refused("ALREADY_RUNNING", "reprise concurrente") from exc
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640)
        os.write(fd, body)
        os.close(fd)
        return old
    os.write(fd, body)
    os.close(fd)
    return None


def _publish(reports: Path, mission_id, envelope, started_ts):
    """Publication atomique sans écrasement. Retourne le chemin final."""
    d = reports / "runs" / mission_id
    d.mkdir(parents=True, exist_ok=True)
    name = NAME_RE.format(stamp=_stamp(started_ts), inv=envelope["invocation_id"])
    final = d / name
    tmp = d / f".{name}.partial"
    with open(tmp, "x", encoding="utf-8") as fh:
        json.dump(envelope, fh, ensure_ascii=False, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    try:
        os.link(tmp, final)                  # échoue si le nom existe : ancien fichier préservé
    except FileExistsError as exc:
        tmp.unlink(missing_ok=True)
        raise Refused("NAME_EXISTS", name) from exc
    tmp.unlink(missing_ok=True)
    return final


def _abandoned_record(reports: Path, old, runner_id, agent_id, now):
    """Consigne l'invocation dont le bail a expiré, sans rien inventer de son rapport."""
    if not old or not old.get("invocation_id"):
        return None
    env = {k: None for k in inv.ENVELOPE_KEYS}
    env.update({
        "contract": inv.INVOCATION_CONTRACT, "contract_version": inv.CONTRACT_VERSION,
        "invocation_id": old["invocation_id"], "agent_id": agent_id, "runner_id": runner_id,
        "mission_id": old.get("mission_id"), "profile_blob_sha1": None,
        "code_sha": None, "analysed_sha": None,
        "started_utc": old.get("started_utc"), "ended_utc": inv.utc_now_iso(now),
        "state": "ABANDONED", "exit_code": None,
        "interruption_reason": "bail de verrou expiré : invocation abandonnée",
        "report": None, "limits": None,
    })
    return env


def run_once(*, mission, checkout: Path, reports: Path, runner_id, agent_id="repository-cartographer",
             code_sha, analysed_sha, max_run_s=None, clock=_now_s):
    """Exécute une invocation. Retourne l'enveloppe publiée. Lève Refused sans rien publier
    pour un refus avant verrouillage ; un échec après verrouillage est publié (FAILED/TIMEOUT)."""
    if not (isinstance(code_sha, str) and inv.HEX40.match(code_sha)):
        raise Refused("CODE_SHA_INVALID")
    if not (isinstance(analysed_sha, str) and inv.HEX40.match(analysed_sha)):
        raise Refused("ANALYSED_SHA_INVALID")
    if not inv.ID_RE.match(runner_id):
        raise Refused("RUNNER_ID_INVALID")
    try:
        c.validate_mission(mission)
    except c.MissionRejected as exc:
        raise Refused("MISSION_REJECTED", exc.code) from exc
    if mission["agent_id"] != agent_id or mission["question"]["kind"] != "REPOSITORY_MAP":
        raise Refused("AGENT_NOT_QUALIFIED")
    if mission["analyzed_ref"] != {"kind": "GIT_COMMIT", "sha": analysed_sha}:
        raise Refused("ANALYSED_REF_MISMATCH")
    head = _git_head(checkout)
    if head is not None and head != code_sha:
        raise Refused("CHECKOUT_SHA_MISMATCH", f"checkout {head} ≠ code {code_sha}")

    # Limite de durée : celle de la mission (max_wall_ms), plafonnée par MAX_RUN_S.
    max_run_s = min(MAX_RUN_S, mission["budget"]["max_wall_ms"] / 1000) if max_run_s is None else max_run_s
    locks = reports / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock = locks / f"{runner_id}.lock"
    invocation_id = secrets.token_hex(16)
    now = clock()
    stale = _acquire_lock(lock, runner_id, invocation_id, mission["mission_id"], now)
    if stale is not None:
        rec = _abandoned_record(reports, stale, runner_id, agent_id, now)
        if rec is not None:
            _publish(reports, rec["mission_id"] or mission["mission_id"], rec, now)

    started_ts = clock()
    started = inv.utc_now_iso(started_ts)
    limits = {"max_files": mission["budget"]["max_files"], "max_run_s": max_run_s,
              "max_bytes": mission["budget"].get("max_bytes")}
    report, state, exit_code, reason = None, "FAILED", None, None

    def _alarm(_s, _f):
        raise _Timeout()

    old_handler = None
    try:
        if hasattr(signal, "SIGALRM"):
            old_handler = signal.signal(signal.SIGALRM, _alarm)
            signal.setitimer(signal.ITIMER_REAL, max_run_s)
        report = rc.audit_zone(mission, checkout, checkout, clock=clock)
        state, exit_code = "COMPLETED", 0
    except _Timeout:
        state, exit_code, reason = "TIMEOUT", None, f"durée > {max_run_s} s"
    except KeyboardInterrupt:
        state, reason = "INTERRUPTED", "interruption opérateur"
    except Exception as exc:  # noqa: BLE001 — une panne devient FAILED, jamais un succès
        state, exit_code, reason = "FAILED", 1, type(exc).__name__
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)

    try:
        ended_ts = clock()
        env = inv.make_envelope(
            invocation_id=invocation_id, agent_id=agent_id, runner_id=runner_id, mission=mission,
            code_sha=code_sha, analysed_sha=analysed_sha, started_utc=started,
            ended_utc=inv.utc_now_iso(ended_ts), state=state, exit_code=exit_code,
            interruption_reason=reason, report=report if state == "COMPLETED" else None,
            limits=limits)
        _publish(reports, mission["mission_id"], env, started_ts)
    finally:
        # Le verrou est libéré après publication (ou après échec signalé par l'exception).
        lock.unlink(missing_ok=True)
    return env
