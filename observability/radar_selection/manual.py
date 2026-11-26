"""R0-D — operator preferences (select, pin, exclude, reset) and bounded history.

A preference is an operator note, never an authorisation: selecting or pinning
a market starts no collection, no job and no experiment, and never changes its
scientific decision. Files are written only inside the explicit state directory,
atomically (temporary file, fsync, rename), so an interrupted command leaves
the previous file intact.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import contract as c
from .fixture import RadarRefusal, canonical, strict_loads

PREFS_FILE = "preferences.json"
HISTORY_FILE = "history.json"
LISTS = ("selected", "pinned", "excluded")
MAX_PREF_BYTES = 200_000


def empty_preferences() -> dict:
    return {"schema": c.PREFERENCES_SCHEMA, "selected": [], "pinned": [], "excluded": [],
            "seq": 0, "log": []}


def _validate(doc) -> dict:
    if not isinstance(doc, dict) or set(doc) != {"schema", *LISTS, "seq", "log"} \
            or doc["schema"] != c.PREFERENCES_SCHEMA or type(doc["seq"]) is not int:
        raise RadarRefusal("PREFERENCES_MALFORMED")
    for k in LISTS:
        if not isinstance(doc[k], list) or not all(isinstance(x, str) for x in doc[k]) \
                or doc[k] != sorted(set(doc[k])):
            raise RadarRefusal("PREFERENCES_MALFORMED:" + k)
    if not isinstance(doc["log"], list) or len(doc["log"]) > c.MAX_PREF_LOG:
        raise RadarRefusal("PREFERENCES_MALFORMED:log")
    return doc


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise


def load_preferences(state_dir: Path | None) -> dict:
    if state_dir is None:
        return empty_preferences()
    path = Path(state_dir) / PREFS_FILE
    if not path.exists():
        return empty_preferences()
    return _validate(strict_loads(path.read_bytes(), MAX_PREF_BYTES))


def save_preferences(state_dir: Path, prefs: dict) -> None:
    atomic_write(Path(state_dir) / PREFS_FILE, canonical(_validate(prefs)) + b"\n")


def apply(prefs: dict, action: str, market_id: str | None, markets: dict) -> dict:
    """Return new preferences. ``markets``: market_id -> evaluated entry.

    Refusals: unknown market (D02), market outside the authorised universe (D03).
    Exclusion of a known market is always accepted (it only removes it from the
    automatic proposals)."""
    new = {**prefs, **{k: list(prefs[k]) for k in LISTS}, "log": list(prefs["log"])}
    if action == "reset":
        new.update({k: [] for k in LISTS})
    else:
        entry = markets.get(market_id)
        if entry is None:
            raise RadarRefusal("UNKNOWN_MARKET:" + str(market_id)[:80])
        if action in ("select", "pin") and entry["lifecycle"]["authorized"] is not True:
            raise RadarRefusal("MARKET_NOT_AUTHORIZED:" + str(entry["lifecycle"]["authorization_reason"]))
        target = {"select": "selected", "pin": "pinned", "exclude": "excluded"}.get(action)
        if target is None:
            remove = {"unselect": "selected", "unpin": "pinned", "include": "excluded"}.get(action)
            if remove is None:
                raise RadarRefusal("UNKNOWN_ACTION:" + action)
            new[remove] = sorted(set(new[remove]) - {market_id})
        else:
            new[target] = sorted(set(new[target]) | {market_id})
    new["seq"] = prefs["seq"] + 1
    new["log"] = (new["log"] + [{"seq": new["seq"], "action": action, "market_id": market_id}])[-c.MAX_PREF_LOG:]
    return _validate(new)


def preferences_digest(prefs: dict) -> str:
    from .fixture import sha256_hex
    return sha256_hex(canonical({k: prefs[k] for k in LISTS}))


# ------------------------------------------------------------------ history

def load_history(state_dir: Path | None) -> list:
    if state_dir is None:
        return []
    path = Path(state_dir) / HISTORY_FILE
    if not path.exists():
        return []
    doc = strict_loads(path.read_bytes(), 2_000_000)
    if not isinstance(doc, dict) or doc.get("schema") != c.HISTORY_SCHEMA or not isinstance(doc.get("entries"), list):
        raise RadarRefusal("HISTORY_MALFORMED")
    return doc["entries"]


def append_history(state_dir: Path, evaluation: dict, max_kept: int) -> list:
    entries = load_history(state_dir)
    entry = {
        "evaluation_sha256": evaluation["evaluation_sha256"],
        "dataset_id": evaluation["dataset"]["id"], "dataset_sha256": evaluation["dataset"]["sha256"],
        "rules_version": evaluation["rules_version"], "ranking_version": evaluation["ranking_version"],
        "mission": evaluation["mission"]["id"], "evaluation_time_ms": evaluation["evaluation_time_ms"],
        "candidates": [x["market_id"] for x in evaluation["candidates"]],
        "counts": evaluation["counts"],
    }
    entries = (entries + [entry])[-max_kept:]
    atomic_write(Path(state_dir) / HISTORY_FILE,
                 canonical({"schema": c.HISTORY_SCHEMA, "max_kept": max_kept, "entries": entries}) + b"\n")
    return entries
