"""Programmateur d'agent : SEULE écriture de l'API (exception gouvernée).

Exception d'écriture du Repository Cartographer, décidée le 2026-11-22 à 07:23Z, fusionnée par
#600 et ratifiée le 2026-11-26 (P6-GOV-01). Durcie par P6-GOV-02 :

- l'API dépose une DEMANDE (un mot d'une liste fermée) dans ``<racine>/requests/`` — seul dossier
  où elle peut écrire — et ne relit jamais ce dossier ;
- un applicateur root distinct, réservé au cartographe, valide la demande sur le descripteur
  ouvert, l'applique au timer et publie l'état dans ``<racine>/state/``, où seul root écrit ;
- l'API lit les états des trois agents en lecture seule (le DPA et le Market Observer n'ont
  aucune demande possible).

L'API ne lance rien et ne touche pas à systemd.
"""
from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path

SCHEDULE_ROOT = Path(os.getenv("AGENT_SCHEDULE_ROOT", "/srv/cat-obs/schedule"))
RHYTHMS = ("10min", "1h", "off")
TEST_RHYTHMS = ("1min",)
WRITABLE = ("repository-cartographer",)
SCHEDULABLE = ("repository-cartographer", "data-provenance-auditor", "market-observer")
MAX_STATUS_BYTES = 4096
MAX_BODY_BYTES = 256
# Limitation des demandes répétées (en mémoire, par processus API).
MIN_INTERVAL_S = 30
MAX_PER_HOUR = 12
# Rythmes calés sur l'horloge (OnCalendar *:0/10, hourly, *:*:00) : le prochain créneau se déduit
# de l'heure courante, ce qui garde « prochain » à jour après chaque passage.
SLOT_S = {"1min": 60, "10min": 600, "1h": 3600}
# Décalage par agent pour ne pas tomber sur le même créneau : le DPA tourne à :05/10 et :30,
# l'Observateur Marché à :03/10 et :45.
SLOT_OFFSET_S = {"data-provenance-auditor": {"10min": 300, "1h": 1800},
                 "market-observer": {"10min": 180, "1h": 2700}}

_lock = threading.Lock()
_accepted: list[float] = []            # horodatages des demandes acceptées (dernière heure)
_requested: dict[str, tuple[str, float]] = {}  # dernière demande acceptée par agent


def requests_dir(root: Path | None = None) -> Path:
    return (root or SCHEDULE_ROOT) / "requests"


def state_dir(root: Path | None = None) -> Path:
    return (root or SCHEDULE_ROOT) / "state"


def allowed_rhythms() -> tuple[str, ...]:
    return RHYTHMS + (TEST_RHYTHMS if os.getenv("AGENT_SCHEDULE_ALLOW_TEST") == "1" else ())


def _utc(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def next_slot_utc(applied: str | None, now_ts: float, agent: str | None = None) -> str | None:
    p = SLOT_S.get(applied or "")
    if not p:
        return None
    off = SLOT_OFFSET_S.get(agent or "", {}).get(applied or "", 0)
    return _utc(((int(now_ts) - off) // p + 1) * p + off)


def _read_state_bytes(path: Path) -> bytes:
    """Lit un état publié sans suivre de lien ni bloquer sur un objet inattendu."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("NOT_A_REGULAR_FILE")
        return os.read(fd, MAX_STATUS_BYTES + 1)[:MAX_STATUS_BYTES]
    finally:
        os.close(fd)


def read_schedule(agent: str, *, root: Path | None = None, now_ts: float | None = None) -> dict:
    now = time.time() if now_ts is None else now_ts
    out = {"agent_id": agent, "allowed": list(allowed_rhythms()) if agent in WRITABLE else [],
           "writable": agent in WRITABLE, "requested": None, "requested_utc": None,
           "applied": None, "applied_utc": None, "next_utc": None,
           "connection": "AVAILABLE", "reason": None}
    with _lock:
        req = _requested.get(agent)
    if req:
        out["requested"], out["requested_utc"] = req[0], _utc(req[1])
    try:
        s = json.loads(_read_state_bytes(state_dir(root) / f"{agent}.json"))
        for k in ("applied", "applied_utc", "next_utc"):
            v = s.get(k) if isinstance(s, dict) else None
            out[k] = v if isinstance(v, str) and len(v) <= 32 else None
        if out["applied"] in SLOT_S:
            out["next_utc"] = next_slot_utc(out["applied"], now, agent)
        elif out["applied"] == "off":
            out["next_utc"] = None
    except FileNotFoundError:
        out["reason"] = "aucun état appliqué publié"
    except (OSError, ValueError) as exc:
        out["connection"], out["reason"] = "UNREADABLE", type(exc).__name__
    return out


def throttle(agent: str, rhythm: str, applied: str | None, now: float | None = None) -> tuple[str, int]:
    """("ACCEPT"|"UNCHANGED"|"THROTTLED", retry_after_s). N'enregistre rien.

    UNCHANGED : le rythme demandé est déjà le rythme appliqué publié par l'applicateur."""
    now = time.time() if now is None else now
    if applied == rhythm:
        return "UNCHANGED", 0
    with _lock:
        _accepted[:] = [t for t in _accepted if now - t < 3600]
        if _accepted and now - _accepted[-1] < MIN_INTERVAL_S:
            return "THROTTLED", int(MIN_INTERVAL_S - (now - _accepted[-1])) + 1
        if len(_accepted) >= MAX_PER_HOUR:
            return "THROTTLED", int(3600 - (now - _accepted[0])) + 1
    return "ACCEPT", 0


def reset_memory() -> None:
    """Tests uniquement."""
    with _lock:
        _accepted.clear()
        _requested.clear()


def request_rhythm(agent: str, rhythm: str, *, root: Path | None = None, now: float | None = None) -> dict:
    """Dépose la demande ``<agent>.request`` ; aucune autre écriture, aucune lecture du dossier."""
    if agent not in WRITABLE:
        raise KeyError(agent)
    if rhythm not in allowed_rhythms():
        raise ValueError(rhythm)
    now = time.time() if now is None else now
    d = requests_dir(root)
    tmp = f".{agent}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    # O_PATH : le dossier est en 2730 (écriture + traversée, sans lecture) ; O_DIRECTORY|O_NOFOLLOW
    # refuse un lien posé à sa place.
    dfd = os.open(d, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640, dir_fd=dfd)
        try:
            os.write(fd, (rhythm + "\n").encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(tmp, f"{agent}.request", src_dir_fd=dfd, dst_dir_fd=dfd)
        except OSError:
            os.unlink(tmp, dir_fd=dfd)
            raise
    finally:
        os.close(dfd)
    with _lock:
        _accepted.append(now)
        _requested[agent] = (rhythm, now)
    return read_schedule(agent, root=root)
