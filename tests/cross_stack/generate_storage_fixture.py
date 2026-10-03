"""Real bounded metadata producer -> atomic artifact -> GET, synthetic only."""
import argparse
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from observability.storage_snapshot import publish_storage_snapshot
from observability.operator_api import app as api

NOW = 1_800_000_400.0
STAMP = "2027-01-15T08:06:40Z"


def generate(out_dir: Path):
    root = Path(out_dir) / "_producer" / "N_storage"
    source = root / "private-source"
    source.mkdir(parents=True, exist_ok=True)
    for name, raw in [("decision_packets_SECRET_1.jsonl", b"not JSON; private content\n"),
                      ("decision_packets_SECRET_2.jsonl", b""), ("ignored.jsonl", b"ignored")]:
        path = source / name
        path.write_bytes(raw)
        os.utime(path, (NOW - 10, NOW - 10))
    artifact = root / "storage_snapshot.json"
    publish_storage_snapshot(artifact, generated_at_utc=STAMP, source_directory=source)
    previous = api.get_storage_reader()
    try:
        api.configure_storage_reader(artifact, now_fn=lambda: NOW + 5)
        with TestClient(api.app) as client:
            response = client.get("/api/operator/v1/storage")
    finally:
        api._storage_reader = previous
    result = {"http_status": response.status_code, "body": response.json()}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "N_storage.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    result = generate(parser.parse_args().out)
    if result["http_status"] != 200 or result["body"]["source_status"] != "PRESENT":
        raise SystemExit("Storage fixture failed")
    print("APP_STORAGE_REAL_CHAIN=PASS")
