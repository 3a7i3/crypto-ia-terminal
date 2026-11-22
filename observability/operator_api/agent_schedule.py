"""Programmateur d'agent : SEULE écriture de l'API.

Exception gouvernée unique, décidée par Mathieu le 2026-11-22 07:23Z (carte de décision du fil
« mini terminal du cartographe »). Toute autre route reste en lecture seule.

L'API ne lance rien et ne touche pas à systemd. Elle dépose une DEMANDE (un mot d'une liste
fermée) dans `AGENT_SCHEDULE_CONTROL_PATH`. Un applicateur root distinct (unité .path) valide la
demande, règle le timer de l'agent et publie l'état appliqué dans `<agent>.status.json`.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

CONTROL_PATH = Path(os.getenv("AGENT_SCHEDULE_CONTROL_PATH", "/srv/cat-obs/control"))
RHYTHMS = ("10min", "1h", "off")
TEST_RHYTHMS = ("1min",)
SCHEDULABLE = ("repository-cartographer",)
MAX_STATUS_BYTES = 4096
# Rythmes calés sur l'horloge (OnCalendar *:0/10, hourly, *:*:00) : le prochain créneau se déduit
# de l'heure courante, ce qui garde « prochain » à jour après chaque passage.
SLOT_S = {"1min": 60, "10min": 600, "1h": 3600}


def allowed_rhythms() -> tuple[str, ...]:
    return RHYTHMS + (TEST_RHYTHMS if os.getenv("AGENT_SCHEDULE_ALLOW_TEST") == "1" else ())


def _utc(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def next_slot_utc(applied: str | None, now_ts: float) -> str | None:
    p = SLOT_S.get(applied or "")
    return _utc((int(now_ts) // p + 1) * p) if p else None


def read_schedule(agent: str, *, control: Path | None = None, now_ts: float | None = None) -> dict:
    root = control or CONTROL_PATH
    out = {"agent_id": agent, "allowed": list(allowed_rhythms()), "requested": None,
           "requested_utc": None, "applied": None, "applied_utc": None, "next_utc": None,
           "connection": "AVAILABLE", "reason": None}
    try:
        req = root / f"{agent}.rhythm"
        st = req.stat()
        val = req.read_text(encoding="ascii")[:16].strip()
        out["requested"] = val if val in RHYTHMS + TEST_RHYTHMS else "INVALID"
        out["requested_utc"] = _utc(st.st_mtime)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        out["connection"], out["reason"] = "UNREADABLE", type(exc).__name__
    try:
        s = json.loads((root / f"{agent}.status.json").read_bytes()[:MAX_STATUS_BYTES])
        for k in ("applied", "applied_utc", "next_utc"):
            v = s.get(k) if isinstance(s, dict) else None
            out[k] = v if isinstance(v, str) and len(v) <= 32 else None
        if out["applied"] in SLOT_S:
            out["next_utc"] = next_slot_utc(out["applied"], time.time() if now_ts is None else now_ts)
        elif out["applied"] == "off":
            out["next_utc"] = None
    except FileNotFoundError:
        out["reason"] = out["reason"] or "aucun état appliqué publié"
    except (OSError, ValueError) as exc:
        out["connection"], out["reason"] = "UNREADABLE", type(exc).__name__
    return out


def request_rhythm(agent: str, rhythm: str, *, control: Path | None = None) -> dict:
    if agent not in SCHEDULABLE:
        raise KeyError(agent)
    if rhythm not in allowed_rhythms():
        raise ValueError(rhythm)
    root = control or CONTROL_PATH
    tmp = root / f".{agent}.rhythm.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o660)
    try:
        os.write(fd, (rhythm + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, root / f"{agent}.rhythm")
    return read_schedule(agent, control=root)
