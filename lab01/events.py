"""Journal d'événements LAB : horodatage synthétique, provenance, chaîne de hachage."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from lab01 import PROVENANCE, SCHEMA_EVENT
from lab01.synthetic import BAR_SECONDS, SYNTHETIC_EPOCH


def norm(v):
    """Normalise récursivement (flottants arrondis) pour un hachage stable."""
    if isinstance(v, float):
        return round(v, 8)
    if isinstance(v, dict):
        return {str(k): norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    return v


def canonical(obj) -> str:
    return json.dumps(
        norm(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EventLog:
    def __init__(self, experiment_id: str, trace_id: str) -> None:
        self.experiment_id = experiment_id
        self.trace_id = trace_id
        self.events: list[dict] = []
        self._bar = 0
        self._local = 0

    def set_bar(self, i: int) -> None:
        if i != self._bar:
            self._bar, self._local = i, 0

    def emit(self, type_: str, payload: dict | None = None) -> dict:
        self._local += 1
        ts = SYNTHETIC_EPOCH + timedelta(
            seconds=BAR_SECONDS * self._bar, milliseconds=self._local
        )
        body = {
            "schema": SCHEMA_EVENT,
            "experiment_id": self.experiment_id,
            "trace_id": self.trace_id,
            "seq": len(self.events) + 1,
            "ts_synthetic": ts.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{ts.microsecond // 1000:03d}Z",
            "type": type_,
            "provenance": PROVENANCE,
            "payload": norm(payload or {}),
            "prev_hash": self.events[-1]["hash"] if self.events else "",
        }
        body["hash"] = sha256_hex(canonical(body))
        self.events.append(body)
        return body

    @property
    def digest(self) -> str:
        return self.events[-1]["hash"] if self.events else ""

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]


def verify_chain(events: list[dict]) -> bool:
    prev = ""
    for e in events:
        body = {k: v for k, v in e.items() if k != "hash"}
        if body.get("prev_hash") != prev or sha256_hex(canonical(body)) != e.get(
            "hash"
        ):
            return False
        if e.get("provenance") != PROVENANCE:
            return False
        prev = e["hash"]
    return True
