"""FIXTURE_ONLY — collecteur synthétique (jamais exécuté par le banc)."""
import json

SOURCE_WS = "wss://example.invalid/stream"


def collect(out_dir, frames):
    with open(out_dir / "samples.jsonl", "a", encoding="utf-8") as log:
        log.writelines(json.dumps(frame) + "\n" for frame in frames)
