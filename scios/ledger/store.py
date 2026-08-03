"""EventLedger — journal L1, append-only, sans révision possible.

Différence de contrat avec `ObjectStore` (L2) : le magasin d'objets accepte la
succession, le ledger **ne l'accepte pas**. Il n'expose aucune méthode de
révision, et il refuse d'écrire autre chose qu'un `Event`.

Cette asymétrie est la traduction technique de la règle : *aucun agent ne
modifie un événement ; tout agent peut créer une observation.*
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterable, Iterator

from scios.ledger.event import Event
from scios.objects.base import ObjectError, fingerprint_dict, utc_now
from scios.objects.identity import IdRegistry


class LedgerError(RuntimeError):
    """Violation d'un invariant du ledger."""


class EventLedger:
    """Journal append-only des événements.

    Partage le registre d'identité du magasin d'objets : l'unicité des
    identifiants est une propriété **globale**, pas une propriété par journal.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._journal = self._root / "events.jsonl"
        self._lock = threading.Lock()
        self.ids = IdRegistry(self._root / "identity.jsonl")

    @property
    def journal(self) -> Path:
        return self._journal

    # ── écriture ─────────────────────────────────────────────────────────────

    def append_many(self, events: Iterable[Event]) -> int:
        """Journalise des événements. Retourne le nombre écrit."""
        batch = list(events)
        for evt in batch:
            if not isinstance(evt, Event):
                raise LedgerError(
                    f"le ledger n'accepte que des Event, reçu {type(evt).__name__} — "
                    "les objets dérivés appartiennent au magasin L2"
                )
            if not self.ids.is_allocated(evt.id):
                raise LedgerError(
                    f"{evt.id} n'a pas été alloué par le registre d'identité"
                )
        written_at = utc_now()
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            with self._journal.open("a", encoding="utf-8") as fh:
                for evt in batch:
                    record = {
                        "_written_at": written_at,
                        "_fingerprint": evt.fingerprint(),
                        **evt.to_dict(),
                    }
                    fh.write(
                        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                    )
        return len(batch)

    def append(self, event: Event) -> Event:
        self.append_many([event])
        return event

    # ── lecture ──────────────────────────────────────────────────────────────

    def read_all(self) -> Iterator[Event]:
        if not self._journal.exists():
            return
        with self._journal.open(encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise LedgerError(
                        f"{self._journal}:{line_no} ledger corrompu: {exc}"
                    ) from exc
                if rec.get("kind") != "Event":
                    raise LedgerError(
                        f"{self._journal}:{line_no} objet non-Event dans le ledger: "
                        f"{rec.get('kind')!r}"
                    )
                yield Event.from_dict(rec)

    def count(self) -> int:
        return sum(1 for _ in self.read_all())

    def by_id(self) -> dict[str, Event]:
        return {e.id: e for e in self.read_all()}

    # ── intégrité ────────────────────────────────────────────────────────────

    def verify(self) -> list[str]:
        """Contrôle d'intégrité. Liste vide = ledger sain."""
        problems: list[str] = []
        if not self._journal.exists():
            return problems
        seen: set[str] = set()
        with self._journal.open(encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                rec = json.loads(raw)
                try:
                    evt = Event.from_dict(rec)
                except (ObjectError, KeyError, ValueError) as exc:
                    problems.append(f"ligne {line_no}: événement invalide — {exc}")
                    continue
                expected = rec.get("_fingerprint")
                if expected and fingerprint_dict(rec) != expected:
                    problems.append(
                        f"ligne {line_no}: empreinte incohérente pour {evt.id} — "
                        "contenu altéré après écriture"
                    )
                if evt.id in seen:
                    problems.append(
                        f"ligne {line_no}: {evt.id} apparaît deux fois — un "
                        "événement n'est jamais réécrit"
                    )
                seen.add(evt.id)
                if not self.ids.is_allocated(evt.id):
                    problems.append(
                        f"ligne {line_no}: {evt.id} absent du registre d'identité"
                    )
        return problems
