"""Synthetic source -> real passive producer -> real Events GET fixture."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from observability.event_center_snapshot import publish_event_center
from observability.operator_api import app as api
from tests.cross_stack.generate_burn_in_fixture import NOW, generate as generate_burn


def generate(out_dir: Path):
    out_dir = Path(out_dir)
    generate_burn(out_dir)
    root = out_dir / "_producer" / "L_events"
    root.mkdir(parents=True, exist_ok=True)
    p12 = root / "alerts.jsonl"
    supervision = root / "audit.jsonl"
    p12.write_text(json.dumps({"rule": "MEMORY", "severity": "CRITICAL", "ts": NOW - 10,
                              "message": "SECRET_CONTEXT_DO_NOT_EXPORT", "value": 91, "threshold": 90}) + "\n")
    supervision.write_text("\n".join(json.dumps(row) for row in [
        {"type": "drawdown", "severity": "warning", "timestamp": "2027-01-15T08:05:00Z", "context": {"token": "SECRET_CONTEXT_DO_NOT_EXPORT"}},
        {"type": "legacy", "severity": "info", "timestamp": "2027-01-15T08:04:00"},
        {"correction": True, "alert": {"type": "legacy", "severity": "info", "timestamp": "2027-01-15T08:04:00"}},
    ]) + "\n")
    artifact = root / "event_center_snapshot.json"
    publish_event_center(artifact, generated_at_utc=datetime.fromtimestamp(NOW, timezone.utc).isoformat().replace("+00:00", "Z"),
                         p12_alerts=p12, supervision_alerts=supervision,
                         ppl_lifecycles=out_dir / "_producer" / "J_burn_in" / "burn_in_status_snapshot.json")
    prior = api.get_event_center_reader()
    try:
        api.configure_event_center_reader(artifact, now_fn=lambda: NOW + 5)
        with TestClient(api.app) as client:
            response = client.get("/api/operator/v1/events")
    finally:
        api._event_center_reader = prior
    result = {"http_status": response.status_code, "body": response.json()}
    (out_dir / "L_events.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    result = generate(parser.parse_args().out)
    if result["http_status"] != 200:
        raise SystemExit("Event Center fixture failed")
    print("APP_EVENTS_01_CROSS_STACK_FIXTURE=PASS")
