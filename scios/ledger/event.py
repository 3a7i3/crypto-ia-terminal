"""Event — l'atome de la couche L1.

KNOWLEDGE_MODEL §3.1 : cycle de vie `RECORDED` -> **jamais autre chose**.
C'est la seule chose non reconstructible du système : la connaissance,
les verdicts et le graphe se rederivent, un événement perdu est perdu.

Différence structurelle avec `Observation` :

    Event        "l'ordre a été rempli à 0.164592 le 2026-07-18T04:12Z"
    Observation  "le slippage médian vaut 0.19 % sur N=139"

Le premier est un fait brut horodaté, le second une agrégation qui suppose un
choix de métrique. `Event` n'hérite donc **pas** de la machinerie de
succession : il ne peut pas être révisé, seulement contredit par un autre
événement. C'est ce qui rend applicable la règle « aucun agent n'écrit dans
le ledger ».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scios.objects.base import ObjectError, Recorded


class EventSource(str, Enum):
    """D'où vient l'événement. Fermé : une source inconnue est un défaut."""

    RUNTIME = "runtime"
    EXCHANGE = "exchange"
    OBSERVER = "observer"
    IMPORT = "import"


@dataclass(frozen=True)
class Event(Recorded):
    """Fait brut horodaté, tel qu'émis. Aucune interprétation."""

    KIND = "Event"

    ts_utc: str = ""
    event_kind: str = ""
    source: str = EventSource.RUNTIME.value
    payload_data: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    policy_version: str | None = None
    deployment_id: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.ts_utc.strip():
            raise ObjectError(
                "ts_utc obligatoire — un événement sans instant n'en est pas un"
            )
        if not self.event_kind.strip():
            raise ObjectError("event_kind obligatoire")
        if self.source not in {s.value for s in EventSource}:
            raise ObjectError(
                f"source inconnue: {self.source!r} — valeurs admises: "
                + ", ".join(sorted(s.value for s in EventSource))
            )

    def payload(self) -> dict[str, Any]:
        return {
            "ts_utc": self.ts_utc,
            "event_kind": self.event_kind,
            "source": self.source,
            "trace_id": self.trace_id,
            "policy_version": self.policy_version,
            "deployment_id": self.deployment_id,
            "data": self.payload_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        from scios.objects.provenance import Provenance

        return cls(
            id=data["id"],
            created_at=data["created_at"],
            provenance=Provenance.from_dict(data["provenance"]),
            epoch_id=data.get("epoch_id"),
            schema_version=data.get("schema_version", "1.0.0"),
            ts_utc=data["ts_utc"],
            event_kind=data["event_kind"],
            source=data.get("source", EventSource.RUNTIME.value),
            payload_data=data.get("data", {}),
            trace_id=data.get("trace_id"),
            policy_version=data.get("policy_version"),
            deployment_id=data.get("deployment_id"),
        )
