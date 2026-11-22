"""FIXTURE_ONLY — producteur synthétique."""
import json
import os
from pathlib import Path

SCHEMA = "fix-history/1.0.0"


def validate(doc):
    errors = []
    if doc.get("schema_version") != SCHEMA:
        errors.append("SCHEMA")
    return errors


def publish(evidence_dir, generated_at_utc):
    lines = (Path(evidence_dir) / "samples.jsonl").read_text(encoding="utf-8").splitlines()
    doc = {"schema_version": SCHEMA, "generated_at_utc": generated_at_utc, "series": [json.loads(x) for x in lines]}
    target = Path(os.getenv("FIX_HISTORY_PATH"))
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
    os.replace(tmp, target)
