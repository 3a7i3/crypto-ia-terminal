#!/usr/bin/env python3
"""Ingère le journal de trades de production dans le ledger d'événements.

Producteur réel de la couche L1. Lit un export de `databases/paper_trades.jsonl`
et produit un `Event` par ligne, **sans agréger ni interpréter** : une ligne du
journal est un fait horodaté, elle devient un événement tel quel.

Ce que l'ingesteur ne fait PAS :
  - il ne calcule aucune métrique (ce serait une Observation) ;
  - il ne filtre pas selon la borne d'époque (ce serait une décision
    scientifique ; le ledger conserve tout, l'époque est un attribut) ;
  - il ne corrige aucune ligne malformée — il les compte et les signale.

Idempotence : refuse de tourner si le ledger existe déjà. Les identifiants ne
sont jamais réattribués, une seconde passe créerait des doublons.

Usage :
    python tools/ingest_trade_events.py --source databases/paper_trades.prod-*.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scios.ledger import Event, EventLedger, EventSource  # noqa: E402
from scios.objects.base import utc_now  # noqa: E402
from scios.objects.provenance import measurement  # noqa: E402

# Borne canonique du dataset propre (ADR-0017). Sert uniquement à ÉTIQUETER
# les événements, jamais à les exclure : le ledger conserve tout.
CLEAN_SINCE_V4 = datetime(2026, 7, 17, 1, 30, tzinfo=timezone.utc)
EPOCH_V4 = "EPO-004"


def _ts_iso(rec: dict) -> str | None:
    if rec.get("ts_iso"):
        return str(rec["ts_iso"])
    ts = rec.get("ts")
    if ts is None:
        return None
    try:
        return (
            datetime.fromtimestamp(float(ts), tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    except (TypeError, ValueError, OSError):
        return None


def _epoch_of(ts_iso: str) -> str | None:
    try:
        moment = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return EPOCH_V4 if moment >= CLEAN_SINCE_V4 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--root", default="knowledge")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parent.parent
    source = Path(args.source)
    if not source.is_absolute():
        source = repo / source
    ledger = EventLedger(repo / args.root)

    if ledger.journal.exists():
        print(
            f"{ledger.journal} existe déjà — ingestion refusée.\n"
            "Un événement n'est jamais réécrit et un identifiant jamais "
            "réattribué : relancer créerait des doublons."
        )
        return 1

    prov = measurement(
        tool="tools/ingest_trade_events.py",
        method=(
            f"lecture ligne à ligne de {source.name}, un Event par ligne, "
            "sans agrégation ni filtrage"
        ),
        limitations=(
            "le journal source est produit par le moteur de production : les "
            "champs absents des lignes anciennes le restent ; les lignes "
            "malformées sont comptées et non ingérées ; aucun deployment_id "
            "n'est renseigné, l'objet Deployment n'existe pas encore"
        ),
        inputs=(str(source.relative_to(repo)),),
    )

    raw_lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    parsed: list[dict] = []
    malformed = 0
    undated = 0
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        ts = _ts_iso(rec)
        if ts is None:
            undated += 1
            continue
        parsed.append({"rec": rec, "ts": ts})

    ids = ledger.ids.allocate_many("Event", 2026, len(parsed))
    created = utc_now()
    events = []
    for identifier, item in zip(ids, parsed):
        rec, ts = item["rec"], item["ts"]
        events.append(
            Event(
                id=identifier,
                created_at=created,
                provenance=prov,
                epoch_id=_epoch_of(ts),
                ts_utc=ts,
                event_kind=f"TRADE_{str(rec.get('event', 'UNKNOWN')).upper()}",
                source=EventSource.IMPORT.value,
                payload_data=rec,
                policy_version=rec.get("runtime_config_version"),
            )
        )

    ledger.append_many(events)

    in_epoch = sum(1 for e in events if e.epoch_id == EPOCH_V4)
    print(f"lignes lues        : {len(raw_lines)}")
    print(f"malformées         : {malformed}")
    print(f"sans horodatage    : {undated}")
    print(f"événements ingérés : {len(events)}")
    print(f"  dont époque V4   : {in_epoch}")
    problems = ledger.verify()
    print("intégrité          :", "OK" if not problems else problems[:3])
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
