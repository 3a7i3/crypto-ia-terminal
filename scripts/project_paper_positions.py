import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def project(events):
    positions = {}
    for event in sorted(events, key=lambda item: item["sequence"]):
        kind = event["event_type"]
        if kind not in {"POSITION_OPENED", "POSITION_CLOSED", "POSITION_UNRESOLVED"}:
            continue
        key = (event["paper_epoch_id"], event["trade_id"])
        if kind == "POSITION_OPENED":
            if key in positions:
                raise ValueError("Duplicate opening")
            positions[key] = {
                "epoch_id": key[0], "trade_id": key[1],
                "decision_id": event.get("decision_id"),
                "symbol": event["payload"]["symbol"],
                "side": event["payload"]["side"],
                "state": "OPEN", "history": [],
            }
        position = positions[key]
        if position["state"] != "OPEN":
            raise ValueError("Event after terminal position state")
        decision_id = event.get("decision_id")
        if decision_id and position["decision_id"] and decision_id != position["decision_id"]:
            raise ValueError("Conflicting decision references")
        position["decision_id"] = position["decision_id"] or decision_id
        position["history"].append({field: event[field] for field in
                                    ("event_id", "sequence", "timestamp", "event_type", "payload")})
        if kind != "POSITION_OPENED":
            position["state"] = kind.removeprefix("POSITION_")
    return list(positions.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    raw = args.archive.read_bytes()
    events = [json.loads(line) for line in raw.splitlines()]
    for field in ("event_id", "sequence"):
        if len({event[field] for event in events}) != len(events):
            raise ValueError(f"Duplicate {field}")
    registry = project(events)
    if registry != project(reversed(events)):
        raise ValueError("Replay differs")
    result = {"source_sha256": hashlib.sha256(raw).hexdigest(),
              "events": len(events), "positions": dict(Counter(p["state"] for p in registry)),
              "decision_references": sum(bool(p["decision_id"]) for p in registry)}
    if not args.summary:
        result["register"] = registry
    print(json.dumps(result, ensure_ascii=False))
