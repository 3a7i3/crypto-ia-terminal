"""Chargement strict des références gelées déclarées (``pinned_references.json``)."""

from __future__ import annotations

import json
from pathlib import Path

from governance_tower.contracts import (
    ContractError,
    EvidenceRef,
    PinnedReference,
    Provenance,
    SourceKind,
)

DEFAULT_PATH = Path(__file__).resolve().parent / "pinned_references.json"
_TOP_KEYS = {"schema", "nature", "warning", "references"}
_REF_KEYS = {
    "reference_id",
    "epoch_id",
    "runtime_source_sha",
    "config_sha256",
    "declared_in",
    "status_date",
    "locator",
}


def load_pinned_references(path: Path = DEFAULT_PATH, *, collected_at_utc: str) -> tuple[PinnedReference, ...]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise ContractError("références gelées : fichier refusé")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or set(doc) != _TOP_KEYS:
        raise ContractError("références gelées : clés inattendues")
    if doc["schema"] != "gt-pinned-references/1" or doc["nature"] != "DECLARED_REFERENCE":
        raise ContractError("références gelées : schéma ou nature inattendus")
    out = []
    for raw in doc["references"]:
        if not isinstance(raw, dict) or set(raw) != _REF_KEYS:
            raise ContractError("référence gelée : clés inattendues")
        evidence = EvidenceRef(
            evidence_id=f"ref-{raw['reference_id'].lower().replace('_', '-')}",
            source=SourceKind.DECLARED_REFERENCE,
            locator=raw["locator"],
            provenance=Provenance.DECLARED_REFERENCE,
            collected_at_utc=collected_at_utc,
            source_sha=raw["runtime_source_sha"],
            note=f"Déclaré dans {raw['declared_in']} (état {raw['status_date']}) ; non observé.",
        )
        out.append(
            PinnedReference(
                reference_id=raw["reference_id"],
                epoch_id=raw["epoch_id"],
                runtime_source_sha=raw["runtime_source_sha"],
                config_sha256=raw["config_sha256"],
                declared_in=raw["declared_in"],
                status_date=raw["status_date"],
                evidence=evidence,
            )
        )
    return tuple(out)
